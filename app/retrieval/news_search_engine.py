"""
app/retrieval/news_search_engine.py
────────────────────────────────────
Dedicated Tavily + Serper dual-API news search engine for UPSC Current Affairs.

Architecture:
    News Query
        ↓
    news_search() — parallel orchestrator
        ↓
    ┌─────────────┴─────────────┐
    ↓                           ↓
 Tavily                      Serper
 (primary)                   (parallel/fallback)
 topic="news"                Google News API
    ↓                           ↓
    └─────────────┬─────────────┘
                  ↓
            Deduplication (URL-keyed, Tavily-first priority)
                  ↓
           TRUSTED_SITES filter
                  ↓
            Article chunking (180 words / 45 overlap)
                  ↓
            Chunk-compatible output → Reranker → LLM

API Keys required (add to .env):
    TAVILY_API_KEY=tvly-xxxxxxxxxxxx
    SERPER_API_KEY=xxxxxxxxxxxxxxxxxxxx

Fallback chain:
    1. Tavily (primary — returns rich content directly, no scraping needed)
    2. Serper (parallel — Google News JSON, fills gaps)
    3. scrape_article() fallback for any URL returned without full content
    4. Legacy parallel_search() (DDG+SearXNG+Bing) if both API keys are missing

Public API:
    news_search(user_query: str) -> list[dict]
        Returns chunk-compatible dicts ready for the reranker.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.core.config import (
    SEARCH_MAX_RESULTS,
    SEARCH_WORKER_COUNT,
    TRUSTED_SITES,
    TAVILY_API_KEY,
    SERPER_API_KEY,
)
from app.retrieval.search_pipeline import (
    scrape_article,
    is_trusted_url,
    _chunk_article_text,
    _MIN_ARTICLE_LENGTH,
)

logger = logging.getLogger(__name__)


# ─── Tavily Search Provider ────────────────────────────────────────────────────

def _tavily_search(query: str) -> list[dict[str, Any]]:
    """
    Call Tavily Search API with topic='news' for real-time news articles.

    Tavily returns structured results with title, url, content, and a relevance score.
    Content is included directly — no scraping required for Tavily results.

    Returns:
        List of result dicts with url, title, snippet, content, score, source='tavily'.
        Returns [] on any failure.
    """
    if not TAVILY_API_KEY:
        logger.debug("[NewsSearch:Tavily] No TAVILY_API_KEY configured — skipping.")
        return []

    try:
        import requests

        payload = {
            "api_key": TAVILY_API_KEY,
            "query": query,
            "topic": "news",                    # restrict to news articles
            "search_depth": "advanced",         # get full content snippets
            "max_results": SEARCH_MAX_RESULTS,
            "include_answer": False,
            "include_raw_content": False,
            "include_domains": TRUSTED_SITES if TRUSTED_SITES else [],
        }

        resp = requests.post(
            "https://api.tavily.com/search",
            json=payload,
            timeout=12,
        )

        if resp.status_code != 200:
            logger.warning(
                f"[NewsSearch:Tavily] HTTP {resp.status_code} — {resp.text[:200]}"
            )
            return []

        data = resp.json()
        results: list[dict[str, Any]] = []

        for idx, item in enumerate(data.get("results", [])):
            url = item.get("url", "")
            if not url:
                continue
            results.append({
                "url":     url,
                "title":   item.get("title", ""),
                "snippet": item.get("content", ""),   # Tavily provides content directly
                "content": item.get("content", ""),   # full text from Tavily
                "score":   item.get("score", 1.0 - idx * 0.05),
                "rank":    idx,
                "source":  "tavily",
            })

        logger.info(f"[NewsSearch:Tavily] {len(results)} results for '{query[:60]}'")
        return results

    except Exception as exc:
        logger.warning(f"[NewsSearch:Tavily] Search failed: {exc}")
        return []


# ─── Serper Search Provider ────────────────────────────────────────────────────

def _serper_search(query: str) -> list[dict[str, Any]]:
    """
    Call Serper Dev API (Google News) for supplementary news results.

    Serper queries Google's News index and returns structured article metadata.
    Content snippets are shorter than Tavily — scrape_article() is used as backup.

    Returns:
        List of result dicts with url, title, snippet, score, source='serper'.
        Returns [] on any failure.
    """
    if not SERPER_API_KEY:
        logger.debug("[NewsSearch:Serper] No SERPER_API_KEY configured — skipping.")
        return []

    try:
        import requests

        headers = {
            "X-API-KEY":   SERPER_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "q":   query,
            "num": SEARCH_MAX_RESULTS,
        }

        resp = requests.post(
            "https://google.serper.dev/news",
            json=payload,
            headers=headers,
            timeout=12,
        )

        if resp.status_code != 200:
            logger.warning(
                f"[NewsSearch:Serper] HTTP {resp.status_code} — {resp.text[:200]}"
            )
            return []

        data = resp.json()
        results: list[dict[str, Any]] = []

        for idx, item in enumerate(data.get("news", [])):
            url = item.get("link", "")
            if not url:
                continue
            results.append({
                "url":     url,
                "title":   item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "content": item.get("snippet", ""),   # Serper snippet only; scraped below if short
                "score":   round(1.0 - (idx / max(SEARCH_MAX_RESULTS, 1)), 4),
                "rank":    idx,
                "source":  "serper",
            })

        logger.info(f"[NewsSearch:Serper] {len(results)} results for '{query[:60]}'")
        return results

    except Exception as exc:
        logger.warning(f"[NewsSearch:Serper] Search failed: {exc}")
        return []


# ─── News Search Orchestrator ──────────────────────────────────────────────────

def news_search(user_query: str) -> list[dict[str, Any]]:
    """
    Parallel Tavily + Serper news search orchestrator.

    Fires both APIs concurrently, merges results with Tavily-first priority,
    deduplicates by URL, filters against TRUSTED_SITES, scrapes missing content,
    and returns chunk-compatible dicts for the reranker.

    Args:
        user_query: The raw user news query string.

    Returns:
        List of chunk-compatible dicts:
        {
            "chunk_id":  str,       # e.g. "ns_001"
            "text":      str,       # article content (from Tavily, Serper, or scraped)
            "score":     float,     # relevance score [0, 1]
            "metadata":  {
                "url":    str,
                "title":  str,
                "source": str,      # "tavily" | "serper"
                "sub_idx": int,
            },
            "source":    "web",
        }
    """
    logger.info(f"[NewsSearch] Running Tavily + Serper for: '{user_query[:80]}'")

    # ── Fire Tavily + Serper concurrently ───────────────────────────────────────
    provider_results: dict[str, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_map = {
            executor.submit(_tavily_search, user_query): "tavily",
            executor.submit(_serper_search, user_query): "serper",
        }
        for future in as_completed(future_map):
            provider = future_map[future]
            try:
                provider_results[provider] = future.result()
            except Exception as exc:
                logger.warning(f"[NewsSearch] Provider '{provider}' raised: {exc}")
                provider_results[provider] = []

    tavily_results = provider_results.get("tavily", [])
    serper_results = provider_results.get("serper", [])

    logger.info(
        f"[NewsSearch] Raw results — Tavily: {len(tavily_results)}, Serper: {len(serper_results)}"
    )

    # ── Merge: Tavily-first priority, Serper fills gaps ──────────────────────────
    seen_urls: set[str] = set()
    merged: list[dict[str, Any]] = []

    # Tavily first (higher content quality)
    for item in tavily_results:
        url = item.get("url", "")
        if not url or url in seen_urls:
            continue
        if TRUSTED_SITES and not is_trusted_url(url):
            logger.debug(f"[NewsSearch] Discarding untrusted Tavily URL: {url}")
            continue
        seen_urls.add(url)
        merged.append(item)

    # Serper fills remaining slots
    for item in serper_results:
        url = item.get("url", "")
        if not url or url in seen_urls:
            continue
        if TRUSTED_SITES and not is_trusted_url(url):
            logger.debug(f"[NewsSearch] Discarding untrusted Serper URL: {url}")
            continue
        seen_urls.add(url)
        merged.append(item)

    if not merged:
        logger.warning(
            f"[NewsSearch] No results after merge/dedup for '{user_query[:60]}'"
        )
        return []

    logger.info(f"[NewsSearch] {len(merged)} unique trusted URLs after dedup")

    # ── Scrape missing content (for Serper results with only short snippets) ─────
    # Tavily already returns full content — skip scraping for those.
    urls_needing_scrape = [
        item["url"]
        for item in merged
        if item.get("source") == "serper"
        and len(item.get("content", "")) < _MIN_ARTICLE_LENGTH
    ]

    scraped: dict[str, str] = {}
    if urls_needing_scrape:
        logger.info(
            f"[NewsSearch] Scraping {len(urls_needing_scrape)} Serper URLs for full content..."
        )
        with ThreadPoolExecutor(max_workers=SEARCH_WORKER_COUNT) as executor:
            future_map = {
                executor.submit(scrape_article, url): url
                for url in urls_needing_scrape
            }
            for future in as_completed(future_map):
                url = future_map[future]
                try:
                    scraped[url] = future.result()
                except Exception as exc:
                    logger.warning(f"[NewsSearch] Scrape failed for {url}: {exc}")
                    scraped[url] = ""

    # ── Build chunk dicts ──────────────────────────────────────────────────────
    chunks: list[dict[str, Any]] = []
    chunk_counter = 1

    for item in merged:
        url     = item["url"]
        title   = item.get("title", "")
        content = item.get("content", "")
        score   = item.get("score", 0.5)
        source  = item.get("source", "web")

        # Use Tavily content directly; for Serper use scraped text if available
        if source == "serper" and url in scraped and len(scraped[url]) >= _MIN_ARTICLE_LENGTH:
            content = scraped[url]

        # Final text: full content, fallback to title + snippet
        final_text = content.strip() if len(content.strip()) >= _MIN_ARTICLE_LENGTH else (
            f"{title}\n{item.get('snippet', '')}".strip()
        )

        if not final_text:
            continue

        # Split into overlapping chunks
        text_chunks = _chunk_article_text(final_text, max_words=180, overlap_words=45)

        for sub_idx, sub_text in enumerate(text_chunks):
            chunks.append({
                "chunk_id": f"ns_{chunk_counter:03d}",
                "text":     sub_text,
                "score":    score,
                "metadata": {
                    "url":     url,
                    "title":   title,
                    "source":  source,
                    "sub_idx": sub_idx,
                },
                "source": "web",
            })
            chunk_counter += 1

    logger.info(
        f"[NewsSearch] Returning {len(chunks)} chunks from {len(merged)} articles "
        f"(Tavily: {len(tavily_results)}, Serper: {len(serper_results)})"
    )
    return chunks
