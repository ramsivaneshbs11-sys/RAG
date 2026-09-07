"""
app/api/routes/news.py
──────────────────────
GET /api/v1/daily-news           — All news (last 5 days, filterable)
GET /api/v1/daily-news/stats     — Available dates & article counts
GET /api/v1/daily-news/day/{date}— Full day data (overview + articles)
GET /api/v1/daily-news/dates     — List of available dates
GET /api/v1/daily-news/important — Today's most-important articles
GET /api/v1/daily-news/article/{id} — Single article by ID
GET /api/v1/daily-news/analysis/{date} — Day analysis
POST /api/v1/daily-news/run-pipeline — Trigger pipeline manually
DELETE /api/v1/daily-news/cleanup — Remove old data

Data is read from ram_chatbot-main/backend/data/daily_news.json.
"""
from fastapi import APIRouter, HTTPException, Query
import json, os, logging
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["daily-news"])

# ── JSON DB path — resolves to ram_chatbot-main/backend/data/daily_news.json ──
_THIS_FILE = Path(__file__).resolve()
# RAG-main root is 3 levels up from app/api/routes/news.py
_RAG_MAIN_ROOT = _THIS_FILE.parents[3]   # c:\...\RAG-main\RAG-main
_REPO_ROOT     = _THIS_FILE.parents[4]   # c:\...\RAG-main

# Unified daily_news.json path — ram_chatbot-main/backend/data/ is the canonical location
_CANDIDATE_PATHS = [
    _REPO_ROOT     / "ram_chatbot-main" / "backend" / "data" / "daily_news.json",  # primary
    _RAG_MAIN_ROOT / "backend"          / "data"    / "daily_news.json",            # local fallback
    Path(r"C:\Users\vishn\Downloads\RAG-main\ram_chatbot-main\backend\data\daily_news.json"),
]

# Correct pipeline directory: RAG-main/pipeline/ (not ram_chatbot-main/pipeline/)
_PIPELINE_DIR = _RAG_MAIN_ROOT / "pipeline"


def _get_json_db_path() -> str:
    for p in _CANDIDATE_PATHS:
        if p.exists():
            return str(p)
    # Default: create in primary location
    return str(_CANDIDATE_PATHS[0])


JSON_DB_PATH = _get_json_db_path()
RETENTION_DAYS = 5


def _load_db() -> dict:
    path = _get_json_db_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_db(data: dict):
    path = _get_json_db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _last_n_dates(n: int) -> list[str]:
    return [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]


# ─── GET all news (last 5 days, flat list) ──────────────────────────────────
@router.get("/daily-news")
async def get_all_news(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
):
    db = _load_db()
    valid_dates = set(_last_n_dates(RETENTION_DAYS))
    articles = []

    for day_key, day_data in db.items():
        if day_key not in valid_dates:
            continue
        for art in day_data.get("articles", []):
            articles.append(art)

    if date:
        articles = [a for a in articles if a.get("date") == date]
    if category and category.lower() != "all":
        articles = [a for a in articles if a.get("tag", "").lower() == category.lower()]
    if priority and priority.lower() != "all":
        articles = [a for a in articles if a.get("priority", "").lower() == priority.lower()]
    if search:
        q = search.lower()
        articles = [a for a in articles if q in a.get("title", "").lower() or q in a.get("summary", "").lower()]

    articles.sort(key=lambda x: (x.get("date", ""), x.get("priority") == "high"), reverse=True)
    return {"articles": articles, "total": len(articles)}


# ─── GET full day data ───────────────────────────────────────────────────────
@router.get("/daily-news/day/{date}")
async def get_day_data(date: str):
    db = _load_db()
    if date not in db:
        raise HTTPException(404, f"No data found for {date}")
    day = db[date]
    articles = []
    for a in day.get("articles", []):
        articles.append({
            **a,
            "title":       a.get("title") or a.get("headline") or "Untitled",
            "tag":         a.get("tag") or a.get("category") or "Polity",
            "summary":     a.get("summary") or (a.get("analysis") or {}).get("summary") or "",
            "isImportant": a.get("isImportant") or a.get("is_most_important") or False,
        })
    return {
        "date":         date,
        "title":        day.get("title", f"UPSC Daily Briefing — {date}"),
        "overview":     day.get("overview", ""),
        "categories":   day.get("categories", {}),
        "source":       day.get("source", "The Hindu + PIB"),
        "last_updated": day.get("last_updated", ""),
        "articles":     articles,
        "total":        len(articles),
    }


# ─── GET analysis for a specific date ───────────────────────────────────────
@router.get("/daily-news/analysis/{date}")
async def get_daily_analysis(date: str):
    db = _load_db()
    if date not in db:
        raise HTTPException(404, f"No analysis found for {date}")
    return db[date].get("analysis", {})


# ─── GET today's most important articles ────────────────────────────────────
@router.get("/daily-news/important")
async def get_important_news():
    db = _load_db()
    today = datetime.now().strftime("%Y-%m-%d")
    day_data = db.get(today, {})
    important = [a for a in day_data.get("articles", []) if a.get("isImportant")]
    return {"articles": important, "date": today}


# ─── GET available dates ─────────────────────────────────────────────────────
@router.get("/daily-news/dates")
async def get_available_dates():
    db = _load_db()
    valid_dates = set(_last_n_dates(RETENTION_DAYS))
    available = sorted([d for d in db.keys() if d in valid_dates], reverse=True)
    return {"dates": available}


# ─── GET single article by id ────────────────────────────────────────────────
@router.get("/daily-news/article/{article_id}")
async def get_article(article_id: str):
    db = _load_db()
    for day_data in db.values():
        for art in day_data.get("articles", []):
            if art.get("id") == article_id:
                return art
    raise HTTPException(404, "Article not found")


# ─── POST: Trigger pipeline manually ────────────────────────────────────────
@router.post("/daily-news/run-pipeline")
async def run_pipeline_now():
    try:
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        from app.services.news_scraper_service import sync_all_daily_news

        # Run dual sync (Qdrant + JSON DB) in background thread so API doesn't block
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            await loop.run_in_executor(pool, sync_all_daily_news)

        return {"status": "success", "message": "News pipeline triggered and synced successfully."}
    except Exception as e:
        raise HTTPException(500, f"Pipeline error: {str(e)}")


# ─── DELETE: Cleanup old data ────────────────────────────────────────────────
@router.delete("/daily-news/cleanup")
async def cleanup_old_data():
    db = _load_db()
    threshold = (datetime.now() - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
    old_keys = [k for k in db if k < threshold]
    for k in old_keys:
        del db[k]
    _save_db(db)
    return {"removed_dates": old_keys, "remaining_dates": list(db.keys())}


# ─── GET stats ───────────────────────────────────────────────────────────────
@router.get("/daily-news/stats")
async def get_stats():
    db = _load_db()
    valid_dates = set(_last_n_dates(RETENTION_DAYS))
    total_articles = sum(len(v.get("articles", [])) for k, v in db.items() if k in valid_dates)
    return {
        "total_articles":   total_articles,
        "dates_available":  sorted([d for d in db if d in valid_dates], reverse=True),
        "last_updated":     max(db.keys()) if db else None,
    }
