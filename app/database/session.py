import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import DATABASE_URL, BASE_DIR

logger = logging.getLogger(__name__)

# ── Declarative Base ───────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass

# ── Engine with Automatic SQLite Fallback ──────────────────────────────────
def _create_resilient_engine():
    # If explicitly set to SQLite or left empty, use SQLite directly with zero delay
    if not DATABASE_URL or DATABASE_URL.startswith("sqlite"):
        sqlite_path = BASE_DIR / "data" / "upsc_rag.db"
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"[Database] Using local SQLite database at {sqlite_path}.")
        return create_engine(
            f"sqlite:///{sqlite_path}",
            connect_args={"check_same_thread": False},
        )

    try:
        eng = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,   # detect stale connections
            connect_args={"connect_timeout": 2},
        )
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("[Database] Connected to primary database (PostgreSQL) successfully.")
        return eng
    except Exception as e:
        sqlite_path = BASE_DIR / "data" / "upsc_rag.db"
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        logger.warning(
            f"[Database] PostgreSQL connection failed ({e}). "
            f"Falling back to local SQLite database at {sqlite_path}."
        )
        return create_engine(
            f"sqlite:///{sqlite_path}",
            connect_args={"check_same_thread": False},
        )

engine = _create_resilient_engine()

# ── Session factory ────────────────────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Declarative Base ───────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── FastAPI dependency ─────────────────────────────────────────────────────
def get_db():
    """Yield a database session and close it after the request."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass
