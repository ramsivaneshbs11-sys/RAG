"""
app/services/news_scraper_service.py
────────────────────────────────────
Automated News Scraper & Ingestion Pipeline for UPSC Current Affairs.

Fetches top daily articles from The Hindu and Press Information Bureau (PIB),
extracts and cleans content, creates layout/semantic chunks, generates BGE
embeddings, and upserts them directly into Qdrant's `current_affairs_collection`.

Features:
  - Idempotent: Uses SHA-256 hash of URL as part of deterministic UUID point ID
  - Automated 365-day rolling retention cleanup
  - GS Category heuristic tagging
  - Seamless integration with existing singleton embedding and Qdrant services
"""

import hashlib
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Dict, Optional

import requests
from bs4 import BeautifulSoup
from qdrant_client.models import PointStruct, Distance, VectorParams, Filter, FieldCondition, MatchValue, Range

from app.core.config import (
    CA_NEWS_COLLECTION,
    EMBEDDING_DIMENSION,
    NEWS_MAX_ARTICLES,
    NEWS_RETENTION_DAYS,
)
from app.services.qdrant_service import get_qdrant_client
from app.services.embedding_service import _get_model as get_embedding_model

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _USER_AGENT}


def _infer_gs_category(title: str, text: str) -> str:
    """Heuristic classifier to tag UPSC GS syllabus bucket."""
    combined = f"{title} {text}".lower()
    
    if any(k in combined for k in ["economy", "rbi", "inflation", "gdp", "tax", "banking", "rupee", "fiscal", "isro", "drdo", "ai", "space", "climate", "environment", "pollution", "wildlife", "security", "defense", "missile"]):
        return "GS-3"
    elif any(k in combined for k in ["constitution", "parliament", "supreme court", "high court", "governance", "treaty", "bilateral", "un", "diplomacy", "ambassador", "foreign policy"]):
        return "GS-2"
    elif any(k in combined for k in ["culture", "heritage", "monument", "history", "geography", "monsoon", "cyclone", "earthquake", "society", "women"]):
        return "GS-1"
    return "GS-2"


HINDU_SECTIONS = [
    "https://www.thehindu.com/news/national/",
    "https://www.thehindu.com/news/international/",
    "https://www.thehindu.com/business/Economy/",
    "https://www.thehindu.com/sci-tech/science/",
    "https://www.thehindu.com/sci-tech/energy-and-environment/",
]


def fetch_hindu_links(limit_per_section: int = 4) -> List[str]:
    """Fetches comprehensive national, international, economy & science news URLs from The Hindu across all 5 sections."""
    links: List[str] = []
    for section_url in HINDU_SECTIONS:
        try:
            resp = requests.get(section_url, headers=_HEADERS, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.content, "html.parser")
                sec_count = 0
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if ("/news/" in href or "/business/" in href or "/sci-tech/" in href or "/article" in href) and (href.endswith(".ece") or "article" in href):
                        full_url = href if href.startswith("http") else f"https://www.thehindu.com{href}"
                        if full_url not in links:
                            links.append(full_url)
                            sec_count += 1
                            if sec_count >= limit_per_section:
                                break
        except Exception as exc:
            logger.warning(f"NewsScraper: Failed to fetch section {section_url}: {exc}")
    return links


def fetch_pib_links(limit: int = NEWS_MAX_ARTICLES) -> List[str]:
    """Fetches official press release links from Press Information Bureau (PIB)."""
    url = "https://pib.gov.in/PressReleasePage.aspx"
    links: List[str] = []
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=12)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "PRID=" in href or "prid=" in href:
                    full_url = href if href.startswith("http") else f"https://pib.gov.in/{href.lstrip('/')}"
                    if full_url not in links:
                        links.append(full_url)
                        if len(links) >= limit:
                            break
    except Exception as exc:
        logger.warning(f"NewsScraper: Failed to fetch PIB links: {exc}")
    return links


def scrape_article_content(url: str) -> Optional[Dict[str, Any]]:
    """Scrapes clean title, body text, and publication date from a news URL."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=12)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.content, "html.parser")
        
        # Extract title
        title = ""
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text().strip()
        elif soup.title:
            title = soup.title.get_text().strip()

        # Extract paragraphs
        paragraphs = [
            p.get_text().strip()
            for p in soup.find_all("p")
            if len(p.get_text().strip()) > 40
        ]
        body = " ".join(paragraphs)
        
        if not title or len(body) < 100:
            return None

        # Source domain
        source = "thehindu.com" if "thehindu.com" in url else ("pib.gov.in" if "pib.gov.in" in url else "web")
        today_str = datetime.now().strftime("%Y-%m-%d")
        gs_category = _infer_gs_category(title, body)

        return {
            "title": title,
            "url": url,
            "text": body,
            "source": source,
            "date": today_str,
            "gs_category": gs_category,
        }
    except Exception as exc:
        logger.warning(f"NewsScraper: Failed to scrape {url}: {exc}")
        return None


def chunk_article_text(article: Dict[str, Any], chunk_size_words: int = 250) -> List[Dict[str, Any]]:
    """Splits full article body into semantic overlapping text chunks."""
    words = article["text"].split()
    chunks = []
    
    if len(words) <= chunk_size_words:
        chunks.append({
            "chunk_id": f"ca_{hashlib.sha256(article['url'].encode()).hexdigest()[:8]}_001",
            # Gap 4 fix: removed [SOURCE] prefix — noise token degrades BGE cosine similarity
            "text": f"{article['title']}\n\n{article['text']}",
            "metadata": {
                "title": article["title"],
                "url": article["url"],
                "source": article["source"],
                "source_label": article["source"].upper(),  # moved here for citation display
                "date": article["date"],
                "gs_category": article["gs_category"],
            }
        })
    else:
        step = chunk_size_words - 50  # 50 words overlap
        idx = 1
        for i in range(0, len(words), step):
            sub_words = words[i:i + chunk_size_words]
            if len(sub_words) < 30:
                continue
            chunk_text = " ".join(sub_words)
            chunks.append({
                "chunk_id": f"ca_{hashlib.sha256(article['url'].encode()).hexdigest()[:8]}_{idx:03d}",
                # Gap 4 fix: removed [SOURCE] prefix — noise token degrades BGE cosine similarity
                "text": f"{article['title']}\n\n{chunk_text}",
                "metadata": {
                    "title": article["title"],
                    "url": article["url"],
                    "source": article["source"],
                    "source_label": article["source"].upper(),  # moved here for citation display
                    "date": article["date"],
                    "gs_category": article["gs_category"],
                }
            })
            idx += 1

    return chunks


def ensure_ca_collection_exists():
    """Ensure the Qdrant current_affairs_collection exists with correct vector size."""
    client = get_qdrant_client()
    existing = {col.name for col in client.get_collections().collections}
    if CA_NEWS_COLLECTION not in existing:
        logger.info(f"NewsScraper: Creating collection '{CA_NEWS_COLLECTION}' (dim={EMBEDDING_DIMENSION})")
        client.create_collection(
            collection_name=CA_NEWS_COLLECTION,
            vectors_config=VectorParams(size=EMBEDDING_DIMENSION, distance=Distance.COSINE),
        )


def cleanup_old_news(retention_days: int = NEWS_RETENTION_DAYS) -> int:
    """Removes articles older than retention_days from current_affairs_collection."""
    try:
        client = get_qdrant_client()
        threshold_date = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d")
        
        # Scroll and find point IDs older than threshold date
        offset = None
        old_point_ids = []
        while True:
            records, offset = client.scroll(
                collection_name=CA_NEWS_COLLECTION,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for record in records:
                date_str = (record.payload or {}).get("metadata", {}).get("date")
                if date_str and date_str < threshold_date:
                    old_point_ids.append(record.id)
            if offset is None:
                break

        if old_point_ids:
            client.delete(
                collection_name=CA_NEWS_COLLECTION,
                points_selector=old_point_ids,
            )
            logger.info(f"NewsScraper: Cleanup completed — removed {len(old_point_ids)} articles older than {threshold_date}")
        return len(old_point_ids)
    except Exception as exc:
        logger.warning(f"NewsScraper: Cleanup error (non-fatal): {exc}")
        return 0


def run_daily_news_scraper() -> Dict[str, Any]:
    """
    Main orchestration routine:
    1. Collects links from The Hindu & PIB
    2. Scrapes & chunks articles
    3. Generates BGE embeddings in batch
    4. Upserts to Qdrant's current_affairs_collection
    5. Cleans up old vectors
    """
    logger.info("NewsScraper: Starting daily sync pipeline...")
    ensure_ca_collection_exists()

    links = fetch_hindu_links() + fetch_pib_links()
    logger.info(f"NewsScraper: Discovered {len(links)} candidate links")

    articles: List[Dict[str, Any]] = []
    for link in links:
        art = scrape_article_content(link)
        if art:
            articles.append(art)

    logger.info(f"NewsScraper: Successfully scraped {len(articles)} full articles")

    all_chunks: List[Dict[str, Any]] = []
    for art in articles:
        all_chunks.extend(chunk_article_text(art))

    if not all_chunks:
        logger.info("NewsScraper: No new chunks to index today.")
        return {"scraped_articles": len(articles), "chunks_upserted": 0, "status": "completed"}

    # Batch embedding
    logger.info(f"NewsScraper: Embedding {len(all_chunks)} chunks using BGE model...")
    embed_model = get_embedding_model()
    texts = [c["text"] for c in all_chunks]
    vectors = embed_model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    # Prepare Qdrant points with deterministic UUIDs based on chunk_id
    client = get_qdrant_client()
    points = []
    for chunk, vector in zip(all_chunks, vectors):
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["chunk_id"]))
        payload = {
            "chunk_id": chunk["chunk_id"],
            "text": chunk["text"],
            "classification": "CurrentAffairs",
            "metadata": chunk["metadata"],
        }
        points.append(PointStruct(id=point_id, vector=vector.tolist(), payload=payload))

    # Upsert
    client.upsert(collection_name=CA_NEWS_COLLECTION, points=points, wait=True)
    logger.info(f"NewsScraper: Successfully upserted {len(points)} vectors to '{CA_NEWS_COLLECTION}' ✓")

    # Cleanup
    cleanup_old_news()

    return {
        "scraped_articles": len(articles),
        "chunks_upserted": len(points),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "status": "success",
    }


def sync_all_daily_news(target_date: Optional[str] = None):
    """
    Automated dual-sync orchestrator:
    1. Runs Qdrant vector scraper/upsert (for RAG search)
    2. Runs pipeline/news_scheduler.py (for frontend Daily News UI)
    Called automatically by APScheduler every day and on server start.
    """
    logger.info("DailyNewsSync: Starting automated dual sync...")
    try:
        # 1. Qdrant vector sync
        run_daily_news_scraper()
    except Exception as exc:
        logger.warning(f"DailyNewsSync: Qdrant sync failed (continuing): {exc}")

    try:
        # 2. JSON database sync for UI
        # news_scheduler.py lives in RAG-main/pipeline/ (sibling of app/)
        import sys, importlib
        pipeline_dir = str(Path(__file__).resolve().parents[2] / "pipeline")
        if pipeline_dir not in sys.path:
            sys.path.insert(0, pipeline_dir)
        news_scheduler = importlib.import_module("news_scheduler")
        result = news_scheduler.run_pipeline(target_date=target_date)
        logger.info(f"DailyNewsSync: JSON sync result — {result}")
        logger.info("DailyNewsSync: Automated dual sync completed successfully ✓")
    except Exception as exc:
        logger.warning(f"DailyNewsSync: JSON sync failed: {exc}")

