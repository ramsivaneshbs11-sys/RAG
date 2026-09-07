"""
app/retrieval/search_pipeline.py
──────────────────────────────────
Parallel web search pipeline for UPSC Current Affairs queries.

Search Engine Routing:
    If TAVILY_API_KEY or SERPER_API_KEY is configured (recommended), parallel_search()
    delegates to news_search_engine.news_search() which runs Tavily (primary) +
    Serper (fallback/parallel) concurrently for high-quality structured news results.

    If no API keys are set, falls back to the legacy DDG + SearXNG + Bing HTML
    scraping pipeline below.

Legacy Fallback chain:
    1. DuckDuckGo (ddgs.news) — primary, free, no key required
    2. SearXNG     — secondary, open-source, public instance
    3. Bing        — tertiary, HTML scraping
    4. Empty list  — if all fail (logged as a warning)

Site-filtering strategy:
    Queries are prefixed with a site: operator string targeting trusted UPSC
    sources (pib.gov.in, insightsias.com, etc.) to avoid low-quality results.
    The TRUSTED_SITES list is configurable via the TRUSTED_SITES env var.

Article scraping:
    After obtaining URLs, full article text is fetched via requests + BeautifulSoup.
    Results are cached in article_cache.py to avoid redundant network calls.

Public API:
    parallel_search(user_query: str) -> list[dict]
        Main entry point. Routes to Tavily+Serper or legacy DDG pipeline.

    scrape_article(url: str) -> str
        Fetches and parses the full text of a single article URL.
        Uses the article cache automatically.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests as http_requests

from app.core.config import (
    SEARCH_MAX_RESULTS,
    SEARCH_WORKER_COUNT,
    SEARXNG_URL,
    TRUSTED_SITES,
    TAVILY_API_KEY,
    SERPER_API_KEY,
)
from app.retrieval.article_cache import get_article, store_article

logger = logging.getLogger(__name__)

# ── Browser-like User-Agent to avoid basic bot detection ──────────────────────
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _USER_AGENT}

# ── Scraping constants ─────────────────────────────────────────────────────────
_SCRAPE_TIMEOUT = 5           # seconds per article request (reduced from 10 for speed)
_MIN_ARTICLE_LENGTH = 100     # chars — discard near-empty responses


# ── Query builder ──────────────────────────────────────────────────────────────

def build_site_filtered_query(user_query: str) -> str:
    """
    Prefix the user query with site: operators for trusted UPSC domains.

    Example output:
        "(site:pib.gov.in OR site:insightsias.com OR ...) Green Hydrogen Mission"
    """
    if not TRUSTED_SITES:
        return user_query
    site_filter = " OR ".join(f"site:{s}" for s in TRUSTED_SITES)
    return f"({site_filter}) {user_query}"


# ── Provider functions ─────────────────────────────────────────────────────────

def _duckduckgo_search(query: str) -> list[dict[str, Any]]:
    """
    Search DuckDuckGo using html.duckduckgo.com fallback and return result dicts.
    Returns [] on any failure.
    """
    try:
        url = "https://html.duckduckgo.com/html/"
        params = {"q": query}

        resp = http_requests.post(
            url,
            data=params,
            headers=_HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning(f"[SearchPipeline:DDG] HTTP {resp.status_code} from {url}")
            return []

        from bs4 import BeautifulSoup  # type: ignore
        soup = BeautifulSoup(resp.text, "html.parser")

        results: list[dict[str, Any]] = []
        idx = 0
        for parent in soup.find_all("div", class_="result__body"):
            title_a = parent.find("a", class_="result__url")
            snippet_a = parent.find("a", class_="result__snippet")
            if title_a and snippet_a:
                title = title_a.get_text(strip=True)
                href = title_a.get("href", "")
                snippet = snippet_a.get_text(strip=True)
                if not href:
                    continue
                results.append({
                    "url":     href,
                    "title":   title,
                    "snippet": snippet,
                    "rank":    idx,
                    "source":  "duckduckgo",
                })
                idx += 1
                if idx >= SEARCH_MAX_RESULTS:
                    break

        logger.info(f"[SearchPipeline:DDG] {len(results)} results for '{query[:60]}'")
        return results

    except Exception as exc:
        logger.warning(f"[SearchPipeline:DDG] Search failed: {exc}")
        return []



def _searxng_search(query: str) -> list[dict[str, Any]]:
    """
    Search the configured SearXNG instance and return result dicts.
    Returns [] on any failure.
    """
    try:
        params = {
            "q":          query,
            "format":     "json",
            "categories": "news,general",
        }
        resp = http_requests.get(
            SEARXNG_URL,
            params=params,
            headers=_HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning(
                f"[SearchPipeline:SearXNG] HTTP {resp.status_code} from {SEARXNG_URL}"
            )
            return []

        hits = resp.json().get("results", [])
        results: list[dict[str, Any]] = []
        for idx, hit in enumerate(hits[:SEARCH_MAX_RESULTS]):
            url = hit.get("url", "")
            if not url:
                continue
            results.append({
                "url":     url,
                "title":   hit.get("title", ""),
                "snippet": hit.get("content", ""),
                "rank":    idx,
                "source":  "searxng",
            })

        logger.info(f"[SearchPipeline:SearXNG] {len(results)} results for '{query[:60]}'")
        return results

    except Exception as exc:
        logger.warning(f"[SearchPipeline:SearXNG] Search failed: {exc}")
        return []


def _clean_bing_url(url: str) -> str:
    if "bing.com/ck/a" not in url:
        return url
    try:
        import urllib.parse
        import base64
        parsed = urllib.parse.urlparse(url)
        queries = urllib.parse.parse_qs(parsed.query)
        u_val = queries.get("u", [""])[0]
        if u_val:
            for strip_len in (2, 0, 1, 3):
                try:
                    candidate = u_val[strip_len:]
                    padding = "=" * (4 - len(candidate) % 4)
                    decoded = base64.b64decode(candidate + padding).decode("utf-8", errors="ignore")
                    if decoded.startswith("http://") or decoded.startswith("https://"):
                        return decoded
                except Exception:
                    continue
    except Exception as e:
        logger.warning(f"Failed to decode Bing redirection URL '{url}': {e}")
    return url


def _bing_search(query: str) -> list[dict[str, Any]]:
    """
    Search Bing HTML and return result dicts.
    Returns [] on any failure.
    """
    try:
        import urllib.parse
        from bs4 import BeautifulSoup  # type: ignore
        url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"

        resp = http_requests.get(
            url,
            headers=_HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning(f"[SearchPipeline:Bing] HTTP {resp.status_code} from {url}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[dict[str, Any]] = []
        idx = 0
        for item in soup.select("li.b_algo"):
            h2 = item.find("h2")
            if h2:
                a = h2.find("a")
                snippet_tag = item.find("p") or item.find("div", class_="b_caption")
                if a:
                    title = a.get_text(strip=True)
                    href = _clean_bing_url(a.get("href", ""))
                    snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
                    if not href:
                        continue
                    results.append({
                        "url":     href,
                        "title":   title,
                        "snippet": snippet,
                        "rank":    idx,
                        "source":  "bing",
                    })
                    idx += 1
                    if idx >= SEARCH_MAX_RESULTS:
                        break

        logger.info(f"[SearchPipeline:Bing] {len(results)} results for '{query[:60]}'")
        return results

    except Exception as exc:
        logger.warning(f"[SearchPipeline:Bing] Search failed: {exc}")
        return []


# ── Article scraper ────────────────────────────────────────────────────────────

def scrape_article(url: str) -> str:
    """
    Fetch and parse the full text of a web article.

    Uses the article cache (article_cache.py) to avoid redundant HTTP calls.
    Returns the cleaned paragraph text, or an empty string on failure.

    Args:
        url: Article URL to scrape.

    Returns:
        Plain text content of the article (paragraphs joined by newlines).
    """
    # 1. Cache check
    cached = get_article(url)
    if cached is not None:
        logger.debug(f"[SearchPipeline] Cache HIT for {url}")
        return cached

    # 2. Fetch
    try:
        resp = http_requests.get(url, headers=_HEADERS, timeout=_SCRAPE_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning(f"[SearchPipeline] Failed to fetch {url}: {exc}")
        return ""

    # 3. Parse with BeautifulSoup
    try:
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(resp.text, "lxml")

        # Remove boilerplate tags
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        paragraphs = [p.get_text(separator=" ", strip=True) for p in soup.find_all("p")]
        text = "\n".join(p for p in paragraphs if len(p) > 40)

        if len(text) < _MIN_ARTICLE_LENGTH:
            # Fallback: grab all visible text
            text = soup.get_text(separator="\n", strip=True)

    except ImportError:
        logger.warning("[SearchPipeline] 'beautifulsoup4' or 'lxml' not installed. Using raw text.")
        text = resp.text[:5000]
    except Exception as exc:
        logger.warning(f"[SearchPipeline] Parse error for {url}: {exc}")
        text = ""

    if text:
        store_article(url, text)
        logger.debug(f"[SearchPipeline] Cache MISS → stored {len(text)} chars for {url}")

    return text


# ── Helper for URL verification ───────────────────────────────────────────────

def is_trusted_url(url: str) -> bool:
    if not TRUSTED_SITES:
        return True
    try:
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower()
        
        # Build normalized set of trusted domains
        normalized_trusted = set()
        for s in TRUSTED_SITES:
            s_clean = s.lower().strip()
            normalized_trusted.add(s_clean)
            if s_clean == "insightsias.com":
                normalized_trusted.add("insightsonindia.com")
                
        for t_domain in normalized_trusted:
            if domain == t_domain or domain.endswith("." + t_domain):
                return True
    except Exception:
        pass
    return False


def clean_query_for_search(query: str) -> str:
    """
    Remove common question prefixes and conversational fillers from the query
    to optimize keyword matching for simple search scrapers.
    """
    import re
    q = query.lower().strip()
    q = q.rstrip('?.!,;').strip()
    
    prefixes = [
        r"^what\s+is\s+an\s+",
        r"^what\s+is\s+a\s+",
        r"^what\s+is\s+",
        r"^what\s+are\s+",
        r"^explain\s+",
        r"^discuss\s+",
        r"^define\s+",
        r"^describe\s+",
        r"^analyze\s+",
        r"^meaning\s+of\s+",
        r"^about\s+",
        r"^write\s+a\s+note\s+on\s+",
        r"^write\s+about\s+",
        r"^details\s+of\s+",
        r"^the\s+",
        r"^current\s+status\s+and\s+milestones\s+of\s+",
        r"^current\s+status\s+of\s+",
        r"^status\s+and\s+milestones\s+of\s+",
        r"^status\s+of\s+",
        r"^milestones\s+of\s+",
        r"^updates\s+on\s+",
    ]
    
    while True:
        matched_any = False
        for prefix in prefixes:
            matched = re.match(prefix, q)
            if matched:
                q = q[matched.end():].strip()
                matched_any = True
                break
        if not matched_any:
            break
            
    q = q.replace("'s", "")
    return q.strip()


def _clean_snippet_artifacts(text: str) -> str:
    """Clean broken web snippet ellipsis artifacts like 'Ne... afe' or 'word... word'."""
    import re
    # Remove broken mid-word ellipsis like 'Ne... afe' -> 'Nepal safe' or 'Ne safe'
    cleaned = re.sub(r'(\b[A-Za-z]{2,})\s*\.\.\.\s*([A-Za-z]{2,}\b)', r'\1 \2', text)
    # Remove standalone ellipses
    cleaned = re.sub(r'\s*\.\.\.\s*', ' ', cleaned)
    return cleaned.strip()


def _chunk_article_text(text: str, max_words: int = 250, overlap_words: int = 50) -> list[str]:
    """
    Split text into overlapping chunks at sentence boundaries to preserve complete facts.
    """
    import re
    cleaned_text = _clean_snippet_artifacts(text)
    words = cleaned_text.split()
    if len(words) <= max_words:
        return [cleaned_text]

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', cleaned_text)
    chunks = []
    current_chunk = []
    current_word_count = 0

    for sentence in sentences:
        s_words = sentence.split()
        s_count = len(s_words)

        if current_word_count + s_count > max_words and current_chunk:
            chunks.append(" ".join(current_chunk))
            # Keep last sentence for overlap
            current_chunk = [current_chunk[-1]] if len(current_chunk) > 1 else []
            current_word_count = sum(len(s.split()) for s in current_chunk)

        current_chunk.append(sentence)
        current_word_count += s_count

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks if chunks else [cleaned_text]


# ── Parallel orchestrator ──────────────────────────────────────────────────────

def parallel_search(user_query: str) -> list[dict[str, Any]]:
    """
    Main entry point for web search.

    Routing logic:
        - If TAVILY_API_KEY or SERPER_API_KEY is configured → delegates to
          news_search_engine.news_search() (Tavily primary + Serper fallback).
        - Otherwise falls back to legacy DDG + SearXNG + Bing HTML scraping.

    Returns a list of chunk-compatible dicts:
        {
            "chunk_id":  str,       # e.g. "ns_001" (Tavily/Serper) or "web_001" (legacy)
            "text":      str,       # full article text (or title+snippet as fallback)
            "score":     float,     # rank-based relevance score [0, 1]
            "metadata":  {
                "url":    str,
                "title":  str,
                "source": str,      # "tavily" | "serper" | "duckduckgo" | "searxng" | "bing"
            },
            "source":    "web",
        }

    Args:
        user_query: The original user query string.
    """
    # ── Route to Tavily + Serper engine if API keys are configured ───────────────
    if TAVILY_API_KEY or SERPER_API_KEY:
        logger.info(
            "[SearchPipeline] API keys detected → routing to Tavily+Serper news engine."
        )
        from app.retrieval.news_search_engine import news_search
        results = news_search(user_query)
        if results:
            logger.info(
                f"[SearchPipeline] Tavily+Serper returned {len(results)} chunks. "
                "Skipping legacy DDG/SearXNG/Bing pipeline."
            )
            return results
        # If both Tavily and Serper returned nothing, fall through to legacy pipeline
        logger.warning(
            "[SearchPipeline] Tavily+Serper returned 0 results. "
            "Falling back to legacy DDG+SearXNG+Bing pipeline."
        )

    # ── Legacy DDG + SearXNG + Bing fallback ─────────────────────────────────
    logger.info("[SearchPipeline] Using legacy DDG + SearXNG + Bing pipeline.")

    filtered_query = build_site_filtered_query(user_query)
    cleaned_query  = clean_query_for_search(user_query)

    # ── Dynamic search query injection ──────────────────────────────────────────
    # If the user has configured only 1 trusted site (e.g. TRUSTED_SITES = ["thehindu.com"]),
    # restrict search engines directly in the query: "query site:thehindu.com".
    # Otherwise, search broadly and filter in python.
    search_query = cleaned_query
    if len(TRUSTED_SITES) == 1:
        search_query = f"{cleaned_query} site:{TRUSTED_SITES[0]}"

    # ── Fire search providers concurrently (DDG, SearXNG, Bing) ────────────────
    # Strategy: send the clean keyword query to all 3 providers.
    # Post-search filtering by is_trusted_url() ensures only trusted UPSC domains survive.
    provider_results: dict[str, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=min(SEARCH_WORKER_COUNT, 3)) as executor:
        future_map = {
            executor.submit(_duckduckgo_search, search_query): "duckduckgo",
            executor.submit(_searxng_search,    search_query): "searxng",
            executor.submit(_bing_search,       search_query): "bing",
        }
        for future in as_completed(future_map):
            provider = future_map[future]
            try:
                provider_results[provider] = future.result()
            except Exception as exc:
                logger.warning(f"[SearchPipeline] Provider '{provider}' raised: {exc}")
                provider_results[provider] = []

    # ── Merge: DuckDuckGo, SearXNG, then Bing (fills gaps) ───────────────────
    seen_urls: set[str] = set()
    merged: list[dict[str, Any]] = []

    for provider_name in ("duckduckgo", "searxng", "bing"):
        for item in provider_results.get(provider_name, []):
            url = item.get("url", "")
            if not url or url in seen_urls:
                continue
            if not is_trusted_url(url):
                logger.info(f"[SearchPipeline] Discarding untrusted URL: {url}")
                continue
            seen_urls.add(url)
            merged.append(item)

    if not merged:
        logger.warning(f"[SearchPipeline] All search providers returned 0 results for '{user_query[:60]}'")
        return []

    logger.info(f"[SearchPipeline] {len(merged)} unique URLs after merge/dedup.")

    # ── Scrape articles concurrently ───────────────────────────────────────────
    scraped: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=SEARCH_WORKER_COUNT) as executor:
        future_map = {
            executor.submit(scrape_article, item["url"]): item["url"]
            for item in merged
        }
        for future in as_completed(future_map):
            url = future_map[future]
            try:
                scraped[url] = future.result()
            except Exception as exc:
                logger.warning(f"[SearchPipeline] Scrape failed for {url}: {exc}")
                scraped[url] = ""

    # ── Build chunk dicts ──────────────────────────────────────────────────────
    total = len(merged)
    chunks: list[dict[str, Any]] = []
    chunk_counter = 1
    
    for idx, item in enumerate(merged):
        url     = item["url"]
        title   = item.get("title", "")
        snippet = item.get("snippet", "")
        text    = scraped.get(url, "").strip()

        # Use full article text; fall back to title + snippet if scrape failed
        final_text = text if len(text) >= _MIN_ARTICLE_LENGTH else f"{title}\n{snippet}".strip()

        if not final_text:
            continue

        rank_score = round(1.0 - (idx / max(total, 1)), 4)
        
        # Word-split the article into smaller overlapping chunks
        text_chunks = _chunk_article_text(final_text, max_words=180, overlap_words=45)
        
        for sub_idx, sub_text in enumerate(text_chunks):
            chunks.append({
                "chunk_id": f"web_{chunk_counter:03d}",
                "text":     sub_text,
                "score":    rank_score,
                "metadata": {
                    "url":    url,
                    "title":  title,
                    "source": item.get("source", "web"),
                    "sub_idx": sub_idx,
                },
                "source": "web",
            })
            chunk_counter += 1

    logger.info(f"[SearchPipeline] Returning {len(chunks)} chunks for reranking.")
    return chunks
