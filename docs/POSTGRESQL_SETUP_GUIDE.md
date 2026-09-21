# 🐘 Future PostgreSQL Implementation Plan & Setup Guide

This guide is your ready-to-use reference whenever you decide to scale this project from local **SQLite** to **PostgreSQL** (e.g., when launching to **200+ students** or deploying to **AWS Cloud**).

---

## 🎯 When should you switch to PostgreSQL?

| Scenario | Recommended Database |
|:---|:---|
| Local laptop development & personal testing | **SQLite** (`data/upsc_rag.db`) — *Zero setup needed* |
| 1 to 10 users | **SQLite** (`data/upsc_rag.db`) |
| **200+ concurrent students (Production / AWS)** | **PostgreSQL** — *Prevents database write locks* |

---

## ⚡ Option 1: 1-Command Docker Setup (Quickest)

You do **not** need to install PostgreSQL as software on your computer. You can run it inside a Docker container:

```bash
docker run -d \
  --name postgres_db \
  -p 5432:5432 \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=upsc_rag \
  -v upsc_postgres_data:/var/lib/postgresql/data \
  postgres:15-alpine
```

### Enable it in your `.env`:
Open `.env` and set:
```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/upsc_rag
```

That's it! When you launch `python -m uvicorn app.main:app --port 8000`, the backend will connect to PostgreSQL and automatically create all tables (`documents`, `chat_messages`, `classifications`).

---

## 🐳 Option 2: Add to `docker-compose.yml`

If you want `docker compose up -d` to manage PostgreSQL alongside Qdrant and FastAPI, add this service block into your [`docker-compose.yml`](file:///c:/Users/vishn/Downloads/RAG-main/RAG-main/docker-compose.yml):

```yaml
  # ──────────────────────────── PostgreSQL Service ───────────────────────────
  postgres:
    image: postgres:15-alpine
    container_name: postgres_db
    restart: always
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: upsc_rag
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d upsc_rag"]
      interval: 10s
      timeout: 5s
      retries: 5
```

And in the `volumes:` section at the bottom of `docker-compose.yml`, add:
```yaml
volumes:
  postgres_data:
  qdrant_storage:
  app_cache:
```

---

## 📦 Option 3: Migration Script (Copy SQLite data into PostgreSQL)

If you have existing chat messages, study notes, or uploaded document records in `data/upsc_rag.db` that you want to move into PostgreSQL, run this Python script:

Save as `scripts/migrate_to_postgres.py`:

```python
"""
scripts/migrate_to_postgres.py
Migrates chat history, documents, and classifications from SQLite to PostgreSQL.
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv(BASE_DIR / ".env")

PG_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/upsc_rag")
SQLITE_PATH = BASE_DIR / "data" / "upsc_rag.db"

def migrate():
    print(f"Connecting to PostgreSQL: {PG_URL}")
    pg_engine = sa.create_engine(PG_URL)
    
    # 1. Ensure tables exist in PostgreSQL
    from app.database.session import Base
    from app.database.models import Document, ChatMessage
    from app.database.classification_models import Classification
    Base.metadata.create_all(bind=pg_engine)
    print("✓ Tables verified in PostgreSQL.")

    if not SQLITE_PATH.exists():
        print("No SQLite database found. Ready with fresh PostgreSQL tables!")
        return

    sqlite_engine = sa.create_engine(f"sqlite:///{SQLITE_PATH}")
    SqliteSession = sessionmaker(bind=sqlite_engine)
    PgSession = sessionmaker(bind=pg_engine)

    sqlite_db = SqliteSession()
    pg_db = PgSession()

    try:
        # Migrate Documents
        docs = sqlite_db.query(Document).all()
        for doc in docs:
            pg_db.merge(doc)
        print(f"✓ Migrated {len(docs)} documents.")

        # Migrate Chat Messages
        msgs = sqlite_db.query(ChatMessage).all()
        for msg in msgs:
            pg_db.merge(msg)
        print(f"✓ Migrated {len(msgs)} chat messages.")

        # Migrate Classifications
        classes = sqlite_db.query(Classification).all()
        for cl in classes:
            pg_db.merge(cl)
        print(f"✓ Migrated {len(classes)} classifications.")

        pg_db.commit()
        print("🎉 Migration completed successfully!")

    except Exception as e:
        pg_db.rollback()
        print(f"❌ Error during migration: {e}")
    finally:
        sqlite_db.close()
        pg_db.close()

if __name__ == "__main__":
    migrate()
```

---

## ☁️ Option 4: Deploying to AWS RDS (Production)

When deploying to AWS for 200+ students:
1. In the AWS Console, search for **Amazon RDS**.
2. Click **Create Database** $\rightarrow$ select **PostgreSQL**.
3. Template: **Free Tier** or **Production** (`db.t4g.micro` or `db.t4g.small`).
4. Set Master Username (`postgres`) and Master Password.
5. In **Connectivity**, make sure the Security Group allows inbound traffic on port `5432` from your EC2 instance.
6. Copy the **Endpoint URL** from AWS RDS and set it in your production `.env`:
   ```env
   DATABASE_URL=postgresql://postgres:your_password@your-rds-endpoint.rds.amazonaws.com:5432/upsc_rag
   ```
7. Start the app. The backend will connect directly to AWS RDS!
