# 📚 UPSC AI Platform & Advanced RAG Engine

A production-grade, full-stack AI ecosystem designed specifically for **UPSC Civil Services Examination (CSE)** preparation. This platform combines an advanced **Retrieval-Augmented Generation (RAG)** pipeline grounded in standard UPSC textbooks and notes with an **Automated Multi-Slot Daily Current Affairs Engine**, an **Interactive MCQ Practice Suite**, an **Admin Document & Vector Management Portal**, and a **Modern Glassmorphic React Web Application**.

---

## 🏛️ System Architecture

```
                                  ┌──────────────────────────────────────────────────────────┐
                                  │            React 18 + Vite Glassmorphic UI               │
                                  │     (Chat Mentor, Daily News, MCQ Practice, Admin)       │
                                  │     * Tabs preserved in DOM (uninterrupted streaming)    │
                                  └─────────────┬───────────────────────────────┬────────────┘
                                                │ REST API / SSE                │
                                                ▼                               ▼
                                  ┌───────────────────────────┐   ┌──────────────────────────┐
                                  │    FastAPI Application    │   │  Static SPA Catch-All    │
                                  │       (app/main.py)       │   │  (Serves frontend/dist)  │
                                  └─────────────┬─────────────┘   └──────────────────────────┘
                                                │
                      ┌─────────────────────────┼─────────────────────────┐
                      ▼                         ▼                         ▼
         ┌─────────────────────────┐┌─────────────────────────┐┌─────────────────────────┐
         │     RAG Query Engine    ││   Daily News Engine     ││   MCQ Practice Engine   │
         │  • Intent Classification││  • APScheduler (6 slots)││  • Subject-wise Topics  │
         │  • Dense Vector Search  ││  • Tavily + Serper News ││  • Daily News MCQs      │
         │  • Cross-Encoder Rerank ││  • Qdrant + JSON Sync   ││  • Instant Explanations │
         │  • Anti-Hallucination   ││  • 3-point Summarization││  • GS 1-4 Paper Mapping │
         │  • Token Streaming (SSE)││  • Mains Issue Analysis ││  • Performance Tracking │
         └────────────┬────────────┘└───────────┬─────────────┘└───────────┬─────────────┘
                      │                         │                          │
                      └─────────────────────────┼──────────────────────────┘
                                                ▼
                      ┌────────────────────────────────────────────────────┐
                      │                Storage & Model Tier                │
                      │  • Vector DB: Qdrant (History, Anthro, News)       │
                      │  • Relational DB: PostgreSQL with SQLite Fallback  │
                      │  • Response & Scrape Caches: SQLite Caching Layer  │
                      │  • Embeddings: BAAI/bge-base-en-v1.5 (768-dim)     │
                      │  • Reranker: cross-encoder/ms-marco-MiniLM-L-6-v2  │
                      │  • Primary LLM: Gemini 3.8 Flash (google-genai)    │
                      │  • Fallback/Alt LLM: Groq (llama-3.3-70b-specdec)  │
                      └────────────────────────────────────────────────────┘
```

---

## ✨ Key Features & Recent Upgrades

### 1. 🤖 AI UPSC Mentor & Advanced RAG
* **Upgraded to Gemini 3.8 Flash**: Powered by Google's `gemini-3.8-flash` via the official `google-genai` SDK with automatic quota fallback rotation and dynamic mentor system prompts.
* **Alternative Groq Generation**: Zero-latency query intent classification and alternative answer synthesis via Groq (`llama-3.3-70b-specdec` / `openai/gpt-oss-120b`).
* **Multi-Mode Routing**: Dedicated handlers for **Prelims (Static concepts)**, **Mains (Structured analytical answers)**, and **Current Affairs**.
* **Triple-Layer Anti-Hallucination Shield**:
  1. *Score Gating*: Automatically returns "insufficient information" if context rerank scores fall below threshold.
  2. *Context-Only Constraints*: Strict prompts forbidding external assumptions.
  3. *Inline Citations*: Every claim is mapped to `[chk_xxx]` and traced back to source document page numbers.
* **Pre-Loaded Fast Inference**: Both `BAAI/bge-base-en-v1.5` embeddings and `ms-marco-MiniLM-L-6-v2` cross-encoder reranker are pre-warmed during server startup to eliminate cold-start latency.
* **Token Streaming**: Real-time Server-Sent Events (SSE) streaming at `/api/v1/query/stream`.

### 2. 📑 Dual PDF Ingestion Engine
* **v1 — Docling Layout Parser** (`POST /api/v1/documents`): Built for digital PDFs, preserving multi-column reading orders, headings, and markdown-formatted tables.
* **v2 — Gemini 3.8 Multimodal VLM** (`POST /api/v2/documents`): End-to-end extraction for scanned PDFs, handwritten study notes, diagrams, and historical maps.
* **Folder Batch Processing**: Ingest entire directories of books and notes using server-side batch endpoints (`/api/v1/documents/folder` & `/api/v2/documents/folder`).

### 3. 📰 Automated Multi-Slot Daily News & Current Affairs
* **6-Slot Daily Automation**: Automated scraping scheduled at 06:00, 09:00, 12:00, 15:00, 18:00, and 21:00 with startup catch-up logic to ensure current day's news is never missed.
* **Tavily & Serper Integration**: Real-time news discovery with dual fallback to DuckDuckGo/SearXNG.
* **Triple Format Outputs**:
  * **3-Bullet Summaries**: High-yield executive summaries for rapid morning revision.
  * **Mains Analysis**: Comprehensive breakdowns: *Context $\rightarrow$ Arguments For/Against $\rightarrow$ Policy Implications $\rightarrow$ Way Forward*.
  * **Daily Prelims MCQs**: Test knowledge directly from the day's events.
* **Dual Indexing**: Instant sync to both Qdrant `current_affairs_collection` and local JSON storage.

### 4. 📝 Interactive MCQ Practice Engine
* Subject-wise questions across **History, Geography, Polity, Economy, Environment**, and **Current Affairs**.
* Real-time validation with detailed pedagogical explanations and UPSC syllabus paper mapping (GS1, GS2, GS3, GS4).

### 5. 🛠️ Admin Management & Ingested Documents Portal
* **Manage Ingested Documents**: Dedicated dashboard view listing all ingested documents, chunk counts, page ranges, and timestamps.
* **1-Click Qdrant Vector Deletion**: Permanently delete documents and purge their vector embeddings from Qdrant, database records, and temporary storage in a single click.
* **Cache Telemetry & Control**: Live stats for SQLite response cache and article caches, with one-click purge controls.

### 6. 🎨 Resilient Single-Port Glassmorphic Web App
* **Single-Port Serving**: FastAPI directly serves the pre-built React 18 production bundle from `frontend/dist` on port `8000`.
* **Zero-Config SQLite Fallback**: If PostgreSQL is not running, the application automatically falls back to a local SQLite database (`data/upsc_rag.db`) without crashing.
* **DOM Tab Preservation**: Chat and MCQ practice views remain mounted in the DOM across tab navigation, ensuring background streaming answers and long PDF ingestions never abort when viewing other tabs.

---

## 📁 Repository Structure

```
.
├── app/                            # Core FastAPI Backend
│   ├── api/routes/                 # REST & SSE Route Handlers
│   │   ├── admin.py                # Cache stats, storage overview & flush endpoints
│   │   ├── classifications.py      # Dynamic subject classification router
│   │   ├── documents.py            # Docling digital PDF ingestion & document deletion
│   │   ├── extract_page.py         # Gemini 3.8 VLM scanned document ingestion
│   │   ├── mcq.py                  # MCQ practice generation & validation
│   │   ├── news.py                 # Daily news feeds, summaries & scraper trigger
│   │   ├── query.py                # Standard RAG query endpoint with citations
│   │   └── query_stream.py         # SSE token-streaming query endpoint
│   ├── core/                       # App settings, config & SQLite cache managers
│   ├── database/                   # PostgreSQL schema, SQLAlchemy models & SQLite fallback
│   ├── retrieval/                  # Vector search, reranker, query classifier & prompts
│   └── services/                   # Embeddings, Qdrant service & news scraper service
├── frontend/                       # React 18 + Vite + Tailwind Frontend
│   ├── dist/                       # Pre-compiled static assets served by FastAPI (:8000)
│   └── src/
│       ├── components/             # Layout, Navbar, Dashboard, Chat, MCQ, News, Admin
│       ├── context/                # App state, notes & user auth context
│       └── pages/                  # Home (Tab-preserved views), Login, MainFlow
├── data/                           # Extracted JSON, preprocessed chunks & SQLite databases
├── docs/                           # Architectural guides & evaluation specs
├── extraction/                     # PDF layout helpers & Docling extractors
├── metrics/                        # Retrieval & current affairs evaluation logs
├── pipeline/                       # Automated news scrapers, scheduler & backfill utilities
├── preprocessing/                  # Chunking strategies & text normalizers
├── requirements/                   # Modular requirement manifests (api, extraction)
├── scripts/                        # Ingestion, batch extract & evaluation CLI tools
├── tests/                          # Automated unit and integration test suite
├── uploads/                        # Temporary uploaded PDF storage
├── docker-compose.yml              # Multi-container orchestration (App + Qdrant)
├── Dockerfile                      # Multi-stage production container build
├── HOW_TO_RUN.md                   # Quick execution cheat sheet
├── requirements.txt                # Consolidated root Python dependencies
├── start_dev.bat                   # 1-Click Windows development launcher
└── README.md                       # Master documentation
```

---

## ⚡ How to Run the Application

You can run the application in any of the **4 modes** below depending on your workflow:

### Mode 1: The Quickest Way (Built-in Single Port :8000) ⭐
> **Recommended for most users.** The frontend is pre-built in `frontend/dist`. You do **not** need Node.js, `npm`, or PostgreSQL installed!

1. **Start Qdrant Vector Database**:
   Make sure Docker Desktop is open and run:
   ```bash
   docker run -d --name qdrant_db -p 6333:6333 -p 6334:6334 -v qdrant_storage:/qdrant/storage qdrant/qdrant:latest
   ```
   *(Or run `docker start qdrant_db` if previously created)*.

2. **Install Python Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Start FastAPI**:
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **Open in Browser**:
   * **Full Web Application & Chat**: [http://localhost:8000](http://localhost:8000)
   * **Interactive Swagger API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
   * **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

### Mode 2: 1-Click Windows Dev Launcher (`start_dev.bat`)
> **Best for Windows developers making real-time React UI edits.**

1. Ensure Docker Desktop is running (for Qdrant).
2. Double-click [`start_dev.bat`](file:///c:/Users/vishn/Downloads/RAG-main/RAG-main/start_dev.bat) or run from terminal:
   ```powershell
   .\start_dev.bat
   ```
   *This automated script:*
   * Automatically kills lingering processes on ports `8000` and `5173`.
   * Boots the FastAPI backend on `http://localhost:8000`.
   * Boots the Vite React dev server with Hot Module Reloading (HMR) on `http://localhost:5173`.
   * Automatically opens the browser window for you.

---

### Mode 3: Manual Dual-Terminal Setup (Backend + Frontend)
> **Best for macOS/Linux developers making real-time UI edits.**

#### Terminal 1 — Backend:
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Terminal 2 — Frontend:
```bash
cd frontend
npm install
npm run dev
```
* Access Vite Frontend at: [http://localhost:5173](http://localhost:5173)

---

### Mode 4: Full Containerized Deployment (Docker Compose)
> **Best for deploying everything inside isolated containers.**

```bash
docker compose up -d
```
* **Web Application**: [http://localhost:8000](http://localhost:8000)
* **Qdrant Vector Dashboard**: [http://localhost:6333/dashboard](http://localhost:6333/dashboard)
* **Stop Containers**: `docker compose down`

---

## ⚙️ Environment Configuration (`.env`)

Create or update your [`.env`](file:///c:/Users/vishn/Downloads/RAG-main/RAG-main/.env) file in the root directory:

```env
# ── Core LLM Providers ──
# Google Gemini 3.8 Flash (Required for scanned extraction & primary mentor answers)
# Get your key at: https://aistudio.google.com/app/apikey
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.8-flash

# Groq API (Fast intent routing & alternative generation)
# Get your free key at: https://console.groq.com/keys
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-specdec

# ── Qdrant Vector Database ──
QDRANT_HOST=localhost
QDRANT_PORT=6333

# ── Relational Database (Optional) ──
# If PostgreSQL is not running, the system automatically falls back to local SQLite!
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/upsc_rag

# ── Models & Retrieval ──
EMBEDDING_MODEL_NAME=BAAI/bge-base-en-v1.5
RERANKER_MODEL_NAME=cross-encoder/ms-marco-MiniLM-L-6-v2
RETRIEVAL_CANDIDATE_K=10

# ── News Search Engine API Keys (Optional but Recommended) ──
# Tavily: https://tavily.com (1,000 free queries/month)
TAVILY_API_KEY=your_tavily_api_key_here
# Serper: https://serper.dev (2,500 free queries/month)
SERPER_API_KEY=your_serper_api_key_here
```

---

## 🚀 Key API Endpoints Reference

| Category | Method | Endpoint | Description |
|:---|:---|:---|:---|
| **Query** | `POST` | `/api/v1/query` | Standard RAG Q&A with grounded citations & memory |
| **Query** | `POST` | `/api/v1/query/stream` | Server-Sent Events (SSE) token streaming answer |
| **Ingestion** | `POST` | `/api/v1/documents` | Upload & index digital PDFs using Docling layout parser |
| **Ingestion** | `POST` | `/api/v1/documents/folder` | Batch-ingest all digital PDFs from a server folder |
| **Ingestion** | `POST` | `/api/v2/documents` | Upload & index scanned/handwritten PDFs via Gemini VLM |
| **Ingestion** | `POST` | `/api/v2/documents/folder` | Batch-ingest scanned PDFs from a server folder |
| **Management** | `DELETE` | `/api/v1/documents/{id}` | Permanently delete document, database record & Qdrant vectors |
| **News** | `GET` | `/api/v1/news/daily` | Fetch today's curated UPSC current affairs articles |
| **News** | `POST` | `/api/v1/news/scrape` | Trigger an immediate manual news scraper run |
| **MCQ** | `POST` | `/api/v1/mcq/generate` | Generate Prelims-style MCQs for a given topic/subject |
| **Admin** | `GET` | `/api/v1/admin/storage/stats` | Qdrant vector counts, indexed documents & cache sizes |
| **Admin** | `GET` | `/api/v1/admin/cache/stats` | Response cache and article cache telemetry |
| **Admin** | `DELETE` | `/api/v1/admin/cache/all` | Purge both response cache and article cache |
| **System** | `GET` | `/health` | Application health check endpoint |

---

## 🛠️ Offline & Batch Ingestion Utilities

For ingesting massive books, NCERT textbooks, or historical documents offline:

| Task | Script Command |
|:---|:---|
| **Batch Ingest Scanned Books via Gemini** | `python scripts/run_scanned_ingestion.py` |
| **Single PDF Multimodal Extraction** | `python scripts/gemini_batch_extract.py "path/to/book.pdf"` |
| **Embed & Upsert Preprocessed JSON to Qdrant** | `python scripts/ingest_to_qdrant.py` |
| **Run Complete Document Pipeline** | `python scripts/run_pipeline.py` |
| **Trigger Daily News Scraper & Sync** | `python pipeline/daily_news_scraper.py` |
| **Backfill Historical News Data** | `python pipeline/run_backfill.py` |
| **Evaluate Retrieval Quality** | `python scripts/evaluate_all_quality.py` |

---

## 🧪 Testing

Run the automated test suite covering routing, anti-hallucination gating, embeddings, and API endpoints:
```powershell
pytest tests/ -v
```

---

## 📄 License
This project is licensed under the MIT License.
