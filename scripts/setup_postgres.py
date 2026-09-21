"""
scripts/setup_postgres.py
─────────────────────────
Automated PostgreSQL Setup, Health Check & SQLite-to-PostgreSQL Migration Utility.

Usage:
    python scripts/setup_postgres.py

What it does:
    1. Checks if PostgreSQL is reachable at DATABASE_URL.
    2. If not running, launches a Dockerized PostgreSQL container (port 5432).
    3. Initializes all required tables (documents, chat_messages, classifications).
    4. Detects existing data/upsc_rag.db (SQLite) and safely migrates records to PostgreSQL.
    5. Confirms everything is 100% operational.
"""

import os
import sys
import time
import subprocess
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv(BASE_DIR / ".env")

DEFAULT_PG_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/upsc_rag"
)
SQLITE_PATH = BASE_DIR / "data" / "upsc_rag.db"


def print_banner():
    print("=" * 65)
    print(" 🐘 UPSC RAG — PostgreSQL Automated Setup & Migration Script")
    print("=" * 65)


def check_postgres_connection(db_url: str) -> bool:
    """Attempt a quick connection to PostgreSQL."""
    try:
        engine = sa.create_engine(db_url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        return True
    except Exception:
        return False


def start_postgres_docker():
    """Attempt to start or launch a PostgreSQL Docker container."""
    print("\n[1/4] Checking PostgreSQL status...")
    if check_postgres_connection(DEFAULT_PG_URL):
        print("  ✓ PostgreSQL is already running and reachable!")
        return True

    print("  ⚠ PostgreSQL is not reachable on localhost:5432.")
    print("  🚀 Attempting to start PostgreSQL container via Docker...")

    # Check if container exists
    check_cmd = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=postgres_db", "--format", "{{.Names}}"],
        capture_output=True,
        text=True
    )
    container_exists = "postgres_db" in check_cmd.stdout

    if container_exists:
        print("  → Starting existing 'postgres_db' container...")
        subprocess.run(["docker", "start", "postgres_db"], check=False)
    else:
        print("  → Creating and running fresh 'postgres_db' container...")
        cmd = [
            "docker", "run", "-d",
            "--name", "postgres_db",
            "-p", "5432:5432",
            "-e", "POSTGRES_USER=postgres",
            "-e", "POSTGRES_PASSWORD=postgres",
            "-e", "POSTGRES_DB=upsc_rag",
            "-v", "upsc_postgres_data:/var/lib/postgresql/data",
            "postgres:15-alpine"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ❌ Docker run failed: {result.stderr}")
            print("\n  👉 Please ensure Docker Desktop is open, or start PostgreSQL manually.")
            return False

    # Wait for PostgreSQL to be ready
    print("  ⏳ Waiting for PostgreSQL to accept connections...")
    for _ in range(15):
        time.sleep(1)
        if check_postgres_connection(DEFAULT_PG_URL):
            print("  ✓ PostgreSQL container is now healthy and accepting connections!")
            return True

    print("  ❌ Timed out waiting for PostgreSQL to become ready.")
    return False


def initialize_tables(engine):
    """Create all schema tables in PostgreSQL."""
    print("\n[2/4] Creating database tables in PostgreSQL...")
    from app.database.session import Base
    from app.database.models import Document, ChatMessage  # noqa: F401
    from app.database.classification_models import Classification  # noqa: F401

    Base.metadata.create_all(bind=engine)
    print("  ✓ Tables created successfully (documents, chat_messages, classifications).")


def migrate_sqlite_data(pg_engine):
    """Migrate data from local SQLite database into PostgreSQL if SQLite exists."""
    print("\n[3/4] Checking for existing SQLite data to migrate...")
    if not SQLITE_PATH.exists() or SQLITE_PATH.stat().st_size == 0:
        print("  • No SQLite database (data/upsc_rag.db) found to migrate. Skipping.")
        return

    sqlite_url = f"sqlite:///{SQLITE_PATH}"
    sqlite_engine = sa.create_engine(sqlite_url)

    from app.database.models import Document, ChatMessage
    from app.database.classification_models import Classification

    SqliteSession = sessionmaker(bind=sqlite_engine)
    PgSession = sessionmaker(bind=pg_engine)

    sqlite_db = SqliteSession()
    pg_db = PgSession()

    try:
        # 1. Documents
        sqlite_docs = sqlite_db.query(Document).all()
        doc_count = 0
        for doc in sqlite_docs:
            if not pg_db.query(Document).filter_by(id=doc.id).first():
                pg_db.merge(doc)
                doc_count += 1

        # 2. Chat Messages
        sqlite_msgs = sqlite_db.query(ChatMessage).all()
        msg_count = 0
        for msg in sqlite_msgs:
            if not pg_db.query(ChatMessage).filter_by(id=msg.id).first():
                pg_db.merge(msg)
                msg_count += 1

        # 3. Classifications
        sqlite_classes = sqlite_db.query(Classification).all()
        class_count = 0
        for cl in sqlite_classes:
            if not pg_db.query(Classification).filter_by(name=cl.name).first():
                pg_db.merge(cl)
                class_count += 1

        pg_db.commit()
        print(f"  ✓ Migrated {doc_count} documents, {msg_count} chat messages, and {class_count} classifications from SQLite!")

    except Exception as exc:
        pg_db.rollback()
        print(f"  ⚠ SQLite migration encountered an issue (non-fatal): {exc}")
    finally:
        sqlite_db.close()
        pg_db.close()


def main():
    print_banner()

    # 1. Ensure PostgreSQL is up
    if not start_postgres_docker():
        sys.exit(1)

    # 2. Connect engine
    pg_engine = sa.create_engine(DEFAULT_PG_URL, pool_pre_ping=True)

    # 3. Create tables
    initialize_tables(pg_engine)

    # 4. Migrate SQLite data
    migrate_sqlite_data(pg_engine)

    print("\n[4/4] Final Verification...")
    with pg_engine.connect() as conn:
        doc_total = conn.execute(sa.text("SELECT COUNT(*) FROM documents")).scalar()
        msg_total = conn.execute(sa.text("SELECT COUNT(*) FROM chat_messages")).scalar()

    print("=" * 65)
    print(" 🎉 PostgreSQL is READY!")
    print(f"  • Connection URL : {DEFAULT_PG_URL}")
    print(f"  • Documents      : {doc_total}")
    print(f"  • Chat Messages  : {msg_total}")
    print("=" * 65)
    print("\nNext step: Start your backend as usual:")
    print("    python -m uvicorn app.main:app --port 8000 --reload")
    print("=" * 65)


if __name__ == "__main__":
    main()
