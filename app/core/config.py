import os
from pathlib import Path
from dotenv import load_dotenv

# ── Root of the daily/ workspace ───────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # daily/

# Load environment variables from the .env file
load_dotenv(BASE_DIR / ".env")  # reload configuration for Groq API activation

# ── PostgreSQL connection ──────────────────────────────────────────────────
# Set this as an environment variable or create a .env file.
# Format: postgresql://<user>:<password>@<host>:<port>/<dbname>
DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/upsc_rag",
)

# ── File storage directories ───────────────────────────────────────────────
UPLOAD_DIR: Path = BASE_DIR / "uploads"
EXTRACTED_DIR: Path = BASE_DIR / "data" / "extracted"
PREPROCESSED_DIR: Path = BASE_DIR / "data" / "preprocessed"

# Allowed document classifications (built-in base)
ALLOWED_CLASSIFICATIONS = ["History", "Anthropology"]


def get_all_allowed_classifications(db=None) -> list[str]:
    """
    Return all allowed classifications: built-in defaults + any dynamically registered
    classifications in the database.
    """
    classes = list(ALLOWED_CLASSIFICATIONS)
    if db is not None:
        try:
            from app.database import classification_repository as cls_repo
            dynamic = [c.name for c in cls_repo.list_classifications(db)]
            for name in dynamic:
                if name not in classes:
                    classes.append(name)
        except Exception:
            pass
    return classes

# ── Qdrant vector database ─────────────────────────────────────────────────
QDRANT_HOST: str = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT: int = int(os.environ.get("QDRANT_PORT", "6333"))

# One Qdrant collection per classification (lowercase)
QDRANT_COLLECTION_MAP: dict[str, str] = {
    "History":        "history_collection",
    "Anthropology":   "anthropology_collection",
    "CurrentAffairs": "current_affairs_collection",  # Daily news + live web articles
}

# ── Current Affairs Collection name shorthand ─────────────────────────────
CA_NEWS_COLLECTION: str = "current_affairs_collection"

# ── Embedding model ────────────────────────────────────────────────────────
EMBEDDING_MODEL_NAME: str = os.environ.get(
    "EMBEDDING_MODEL_NAME", "BAAI/bge-base-en-v1.5"
)
EMBEDDING_DIMENSION: int = 768  # Output dimension of BAAI/bge-base-en-v1.5

# ── Gemini (Endpoint 2) ──────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL:   str = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

# ── Groq API (Alternative Generation Layer) ──────────────────────────────────────
GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL:   str = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

# ── News Search Engine API Keys (Tavily + Serper) ─────────────────────────────
# Tavily: https://tavily.com (free tier: 1000 req/month)
# Serper: https://serper.dev (free tier: 2500 req/month)
# If both are empty, falls back to legacy DDG + SearXNG + Bing pipeline.
TAVILY_API_KEY: str = os.environ.get("TAVILY_API_KEY", "")
SERPER_API_KEY: str = os.environ.get("SERPER_API_KEY", "")


# ── Retrieval Layer ────────────────────────────────────────────────────────────
# Confidence thresholds for routing (see retrieval_layer_query_classification.md)
# Lowered HIGH from 0.80→0.70: Groq temperature=0.0 returns 0.55-0.68 for clear subject
# queries (e.g. "Indus Valley" → 0.56) which were incorrectly treated as medium_confidence.
HIGH_CONFIDENCE_THRESHOLD: float = float(os.environ.get("HIGH_CONFIDENCE_THRESHOLD", "0.70"))
LOW_CONFIDENCE_THRESHOLD:  float = float(os.environ.get("LOW_CONFIDENCE_THRESHOLD",  "0.50"))

# Number of candidate chunks sent to the reranker (first-stage retrieval)
RETRIEVAL_CANDIDATE_K: int = int(os.environ.get("RETRIEVAL_CANDIDATE_K", "15"))
# Number of final chunks returned after reranking (second-stage)
RETRIEVAL_FINAL_TOP_K: int = int(os.environ.get("RETRIEVAL_FINAL_TOP_K", "8"))

# Cross-encoder model for reranking (MiniLM-L-6-v2 is used for fast CPU retrieval)
RERANKER_MODEL_NAME: str = os.environ.get(
    "RERANKER_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2"
)

# ── Bidirectional Sibling Expansion ────────────────────────────────────────────
# How many chunks to expand in BOTH directions from a matched chunk.
# Radius=1 → fetches [N-1, N, N+1]   (default, safe for most queries)
# Radius=2 → fetches [N-2, N-1, N, N+1, N+2] (useful for long tables/lists)
# Keep low (1-2) to avoid sending too much irrelevant context to the LLM.
SIBLING_EXPANSION_RADIUS: int = int(os.environ.get("SIBLING_EXPANSION_RADIUS", "1"))

# Score decay per hop from the matched chunk (0.0 = no decay, 1.0 = zero score)
# Sibling scores are reduced so the reranker/LLM still prioritises the exact match.
# e.g. radius=2: hop-1 score = original * (1 - 0.15) = 0.85x
#                hop-2 score = original * (1 - 0.15)^2 = 0.72x
SIBLING_SCORE_DECAY: float = float(os.environ.get("SIBLING_SCORE_DECAY", "0.15"))

# ── Article Cache (for Current Affairs web scraping) ─────────────────────────
# Backend: "memory" (LRU, zero-dep), "sqlite" (persistent), or "redis" (networked)
ARTICLE_CACHE_BACKEND: str = os.environ.get("ARTICLE_CACHE_BACKEND", "memory")
# Max articles stored in-memory (only used when ARTICLE_CACHE_BACKEND="memory")
ARTICLE_CACHE_MAXSIZE: int = int(os.environ.get("ARTICLE_CACHE_MAXSIZE", "200"))
# Article cache TTL in seconds (6 hours default); used by sqlite & redis backends
ARTICLE_CACHE_TTL_SECONDS: int = int(os.environ.get("ARTICLE_CACHE_TTL_SECONDS", "21600"))
# Path to the SQLite cache DB file (only used when ARTICLE_CACHE_BACKEND="sqlite")
ARTICLE_CACHE_SQLITE_PATH: str = os.environ.get(
    "ARTICLE_CACHE_SQLITE_PATH",
    str(BASE_DIR / "data" / "article_cache.db"),
)

# ── Response Cache (for full RAG pipeline responses) ──────────────────────────
# Master on/off switch. Set RESPONSE_CACHE_ENABLED=false in .env to disable.
RESPONSE_CACHE_ENABLED: bool = (
    os.environ.get("RESPONSE_CACHE_ENABLED", "true").lower() == "true"
)
# TTL in seconds before a cached response expires. Default: 7 days.
RESPONSE_CACHE_TTL_SECONDS: int = int(
    os.environ.get("RESPONSE_CACHE_TTL_SECONDS", str(7 * 24 * 3600))
)
# Maximum number of entries kept in the cache (LRU eviction when exceeded).
RESPONSE_CACHE_MAXSIZE: int = int(os.environ.get("RESPONSE_CACHE_MAXSIZE", "1000"))
# Path to the SQLite DB file for the response cache.
RESPONSE_CACHE_SQLITE_PATH: Path = Path(
    os.environ.get(
        "RESPONSE_CACHE_SQLITE_PATH",
        str(BASE_DIR / "data" / "response_cache.db"),
    )
)

# ── Parallel Search ────────────────────────────────────────────────────────────
# Number of concurrent workers for parallel DuckDuckGo + SearXNG search calls
SEARCH_WORKER_COUNT: int = int(os.environ.get("SEARCH_WORKER_COUNT", "4"))
# Comma-separated trusted site domains used for UPSC current-affairs filtering.
# Narrowed to strictly target Daily News pipeline primary sources:
#   - The Hindu + PIB (the two main daily scraper sources)
#   - Key Indian mainstream news outlets for freshness
#   - Core UPSC coaching/reference portals for exam-focused content
TRUSTED_SITES: list[str] = [
    s.strip()
    for s in os.environ.get(
        "TRUSTED_SITES",
        # ── Primary Daily News Sources (mirrors news_scraper_service.py) ──────
        "thehindu.com,"
        "pib.gov.in,"
        # ── Mainstream Indian News Outlets ────────────────────────────────────
        "indianexpress.com,"
        "livemint.com,"
        "businessstandard.com,"
        "ndtv.com,"
        "timesofindia.indiatimes.com,"
        "thewire.in,"
        "scroll.in,"
        # ── Government & Legislative ──────────────────────────────────────────
        "prsindia.org,"
        # ── Core UPSC Coaching Portals ────────────────────────────────────────
        "insightsias.com,"
        "insightsonindia.com,"
        "drishtiias.com,"
        "iasbaba.com,"
        "civilsdaily.com",
    ).split(",")
    if s.strip()
]
# Max results to fetch from each search provider per query
SEARCH_MAX_RESULTS: int = int(os.environ.get("SEARCH_MAX_RESULTS", "8"))
# SearXNG public instance URL (can be overridden with self-hosted instance)
SEARXNG_URL: str = os.environ.get("SEARXNG_URL", "https://searx.be/search")

# ── Daily News Scraper ────────────────────────────────────────────────────────
# Cron schedule for automated news ingestion (default: 06:00 AM daily)
NEWS_SCRAPER_CRON_HOUR:   int = int(os.environ.get("NEWS_SCRAPER_CRON_HOUR",   "6"))
NEWS_SCRAPER_CRON_MINUTE: int = int(os.environ.get("NEWS_SCRAPER_CRON_MINUTE", "0"))
# How many days of news to retain in current_affairs_collection (rolling window)
NEWS_RETENTION_DAYS: int = int(os.environ.get("NEWS_RETENTION_DAYS", "365"))
# Max articles fetched per news source per run
NEWS_MAX_ARTICLES: int = int(os.environ.get("NEWS_MAX_ARTICLES", "8"))

# ── Observability ─────────────────────────────────────────────────────────────
# When True, logs per-stage latency (search / scrape / rerank / gen) to console
ENABLE_DETAILED_LOGGING: bool = (
    os.environ.get("ENABLE_DETAILED_LOGGING", "false").lower() == "true"
)
# Directory for CSV metrics output
METRICS_DIR: Path = BASE_DIR / "metrics"

# ── Ensure directories exist on startup

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
(UPLOAD_DIR / "history").mkdir(parents=True, exist_ok=True)
(UPLOAD_DIR / "anthropology").mkdir(parents=True, exist_ok=True)
EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
PREPROCESSED_DIR.mkdir(parents=True, exist_ok=True)
METRICS_DIR.mkdir(parents=True, exist_ok=True)
(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)  # for response_cache.db
