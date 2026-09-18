"""
app/main.py
────────────
FastAPI application entry point.

Start server:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Interactive docs:
    http://localhost:8000/docs
"""
import logging
import sys
from pathlib import Path

# ── Ensure workspace root is on sys.path ───────────────────────────────────
_WORKSPACE_ROOT = Path(__file__).resolve().parent.parent  # daily/
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

# Disable HuggingFace symlinks on Windows (required for Docling models)
import os
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

from fastapi import FastAPI, Response
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.database.session import engine, Base
from app.database import classification_models  # noqa: F401 — registers Classification table with Base
from app.api.routes import documents
from app.api.routes import extract_page as extract_page_v2
from app.api.routes import query as query_route
from app.api.routes import classifications as classification_route  # dynamic classification management
from app.api.routes import query_stream as query_stream_route       # SSE streaming endpoint
from app.api.routes import news as news_route                       # Daily news endpoints
from app.api.routes import mcq as mcq_route                         # MCQ practice endpoints
from app.api.routes import admin as admin_route                     # Admin cache & storage endpoints
from app.services.qdrant_service import ensure_collections
from app.core.config import (
    RESPONSE_CACHE_ENABLED,
    RESPONSE_CACHE_TTL_SECONDS,
    RESPONSE_CACHE_MAXSIZE,
    RESPONSE_CACHE_SQLITE_PATH,
)


# ── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan: create tables + Qdrant collections on startup ───────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — creating database tables if needed …")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ready ✓")

    logger.info("Verifying Qdrant collections …")
    ensure_collections()

    # ── Pre-load the reranker model so first user request has no cold-start ──
    logger.info("Pre-loading cross-encoder reranker model …")
    from app.retrieval.reranker import preload_reranker
    preload_reranker()

    # ── Pre-load the BGE embedding model so first search request has no cold-start ──
    logger.info("Pre-loading BGE embedding model …")
    from app.services.embedding_service import _get_model as preload_embedding
    preload_embedding()

    # ── Initialise response cache ─────────────────────────────────────────
    from app.retrieval.response_cache import init_cache as init_response_cache
    init_response_cache(
        db_path     = RESPONSE_CACHE_SQLITE_PATH,
        ttl_seconds = RESPONSE_CACHE_TTL_SECONDS,
        max_entries = RESPONSE_CACHE_MAXSIZE,
        enabled     = RESPONSE_CACHE_ENABLED,
    )
    logger.info(
        f"Response cache ready ✔ "
        f"(enabled={RESPONSE_CACHE_ENABLED}, ttl={RESPONSE_CACHE_TTL_SECONDS}s)"
    )

    # ── Start Daily News Scraper Scheduler & Startup Auto-Catchup ───────────
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from app.services.news_scraper_service import sync_all_daily_news   # ← dual sync: Qdrant + daily_news.json
    from app.api.routes.news import _load_db

    import sys
    import asyncio
    from datetime import datetime
    from pathlib import Path as _Path
    _pipeline_dir = str(_Path(__file__).resolve().parent.parent / "pipeline")
    if _pipeline_dir not in sys.path:
        sys.path.insert(0, _pipeline_dir)

    # 1. Startup Catch-up: Check if today's news is missing. If so, run background sync.
    async def _startup_news_catchup():
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            db = _load_db()
            if today_str not in db:
                logger.info(f"DailyNewsSync: Today's news ({today_str}) not found on startup. Triggering background sync...")
                # Offload blocking sync to worker thread so server startup remains instant
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, sync_all_daily_news)
                logger.info(f"DailyNewsSync: Startup background sync for {today_str} completed ✓")
            else:
                logger.info(f"DailyNewsSync: Today's news ({today_str}) already present in database ✓")
        except Exception as exc:
            logger.warning(f"DailyNewsSync: Startup news catch-up error: {exc}")

    asyncio.create_task(_startup_news_catchup())

    # 2. Automated Multi-Slot Schedule: Runs at 06:00, 09:00, 12:00, 15:00, 18:00, 21:00
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        sync_all_daily_news,
        "cron",
        hour="6,9,12,15,18,21",
        minute=0,
        id="daily_news_scraper",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Daily news scraper scheduled for automated runs at 06:00, 09:00, 12:00, 15:00, 18:00, 21:00 daily ✓"
    )

    yield
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass
    logger.info("Shutting down …")




# ── FastAPI app ───────────────────────────────────────────────────────────
app = FastAPI(
    title="UPSC RAG — Document Ingestion & Retrieval API",
    description=(
        "## Ingestion Endpoints\n\n"
        "### v1 — Docling Extractor (digital PDFs)\n"
        "- `POST /api/v1/documents` — Upload **one or more** PDF files\n"
        "- `POST /api/v1/documents/folder` — Ingest all PDFs from a **server-side folder path**\n\n"
        "### v2 — Gemini 2.5 Flash Extractor (all PDFs)\n"
        "- `POST /api/v2/documents` — Upload **one or more** PDF files\n"
        "- `POST /api/v2/documents/folder` — Ingest all PDFs from a **server-side folder path**\n\n"
        "**Pipeline per file:** Validate → Save → Register (PostgreSQL) → Extract → "
        "Preprocess + Chunk → Embed (BGE) → Qdrant upsert\n\n"
        "---\n\n"
        "## Retrieval Endpoint\n\n"
        "- `POST /api/v1/query` — Intelligent retrieval layer\n\n"
        "**Pipeline:** Classify (Gemini Flash) → Route (High/Medium/Low confidence) → "
        "Vector Search (Qdrant) or Web Search (DuckDuckGo) → Rerank (MiniLM) → Top-K chunks"
    ),
    version="3.0.0",
    lifespan=lifespan,
)

# ── CORS Middleware ──────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Frontend dist path ───────────────────────────────────────────────────────
_DIST_DIR = _WORKSPACE_ROOT / "frontend" / "dist"
_ASSETS_DIR = _DIST_DIR / "assets"

# ── Mount compiled static assets (JS / CSS bundles from `npm run build`) ─────
# Only mounted when dist exists — safe to run without building frontend first.
if _ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR)), name="static-assets")
    logger.info(f"Serving compiled frontend assets from: {_ASSETS_DIR}")
else:
    logger.warning(
        "frontend/dist/assets not found — UI will not be served. "
        "Run `npm run build` inside the frontend/ directory to enable the React UI."
    )

# ── Favicon ───────────────────────────────────────────────────────────────────
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Handles browser favicon requests — serves from dist if available."""
    favicon_path = _DIST_DIR / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(str(favicon_path))
    return Response(status_code=204)

# ── Dynamic OpenAPI Fix for Swagger UI File Uploads ──────────────────────────
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # Recursively find application/octet-stream properties and change to format: binary
    def fix_binary_format(d):
        if isinstance(d, dict):
            if d.get("contentMediaType") == "application/octet-stream":
                d["format"] = "binary"
                del d["contentMediaType"]
            for v in d.values():
                fix_binary_format(v)
        elif isinstance(d, list):
            for v in d:
                fix_binary_format(v)

    fix_binary_format(openapi_schema)
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# ── Routers ───────────────────────────────────────────────────────────────
# Ingestion
app.include_router(documents.router)
app.include_router(extract_page_v2.router)
# Retrieval
app.include_router(query_route.router)
app.include_router(query_stream_route.router)   # SSE streaming variant
# Classification Management
app.include_router(classification_route.router)
# Daily News & MCQ (merged from ram_chatbot-main)
app.include_router(news_route.router)
app.include_router(mcq_route.router)
# Admin — Cache & Storage Management
app.include_router(admin_route.router)


# ── Health check ──────────────────────────────────────────────────────────
@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}


# ── SPA Catch-All: serves React index.html for all non-API browser routes ─────
# This MUST be registered LAST so API routes always take priority.
# Handles React Router paths like /home, /chat, /news, /admin etc.
@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str):
    """
    Catch-all route that serves the React SPA.

    Priority logic:
      1. If the path maps to a real static file inside dist/ (e.g. robots.txt), serve it.
      2. Otherwise fall back to index.html so React Router handles the path client-side.
      3. If dist/ does not exist yet (dev mode without a build), return a JSON hint.
    """
    if not _DIST_DIR.exists():
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "React UI not built yet. "
                    "Run `npm run build` inside the frontend/ directory, "
                    "then restart the server."
                )
            },
        )

    # Serve actual files (e.g. robots.txt, manifest.json) if they exist in dist root
    candidate = _DIST_DIR / full_path
    if candidate.exists() and candidate.is_file():
        return FileResponse(str(candidate))

    # For everything else (React routes) → return index.html
    return FileResponse(str(_DIST_DIR / "index.html"))
