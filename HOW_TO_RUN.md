# 🚀 UPSC RAG Learning Assistant — Execution Guide

This document provides complete, updated instructions on how to run the application across all supported environments.

---

## 🛠️ Prerequisites

1. **Docker Desktop** (Required) — [Download](https://www.docker.com/products/docker-desktop/)
   * Runs the **Qdrant Vector Database** (`qdrant_db` on port `6333`).
   * *Must be running in the background.*
2. **Python** (v3.10 or higher) — [Download](https://www.python.org/)
3. **Node.js** (v18 or higher) — [Download](https://nodejs.org/) *(only needed if developing or modifying React frontend code)*
4. **PostgreSQL** *(Optional)*: If PostgreSQL is not installed or running, the backend **automatically falls back to a local SQLite database** (`data/upsc_rag.db`) without any manual setup!

---

## ⚡ 1. The Quickest Way (Built-in Mode — Single Port :8000) ⭐

The React frontend is **pre-built** into `frontend/dist`. You only need to run the Python backend, which serves both the API and the full glassmorphic web application together!

1. Make sure **Docker Desktop** is open, and start Qdrant:
   ```bash
   docker start qdrant_db
   ```
   *(If you haven't created the container yet, run: `docker run -d --name qdrant_db -p 6333:6333 -p 6334:6334 -v qdrant_storage:/qdrant/storage qdrant/qdrant:latest`)*

2. Open a terminal in the project root folder and start FastAPI:
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. Open your browser:
   * **Full Web Application & Chat**: [http://localhost:8000](http://localhost:8000)
   * **Interactive Swagger API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
   * **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

> **No Node.js, `npm install`, or PostgreSQL setup required in this mode!**

---

## 💻 2. Full Development Environment (Windows 1-Click Script)

If you are modifying React UI code and want live Hot Module Reloading (HMR):

1. Make sure Docker Desktop is open.
2. In the project root, run:
   ```powershell
   .\start_dev.bat
   ```
   *This automatically:*
   * Kills any stuck processes on ports 8000 and 5173.
   * Starts FastAPI backend on `http://localhost:8000`.
   * Starts Vite React frontend on `http://localhost:5173`.
   * Opens the app in your browser automatically.

---

## 🐧 3. Manual Dual-Terminal Setup (macOS / Linux / Dev)

### Terminal 1 — Backend:
```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Terminal 2 — Frontend:
```bash
cd frontend
npm install
npm run dev
```
* **Development Frontend**: [http://localhost:5173](http://localhost:5173)

---

## 🐳 4. Full Docker Deployment

To run everything (Backend + Pre-built Frontend + Qdrant) inside Docker containers:

```bash
docker compose up -d
```
* Access the app at: [http://localhost:8000](http://localhost:8000)
* Stop containers: `docker compose down`

---

## ⚙️ Environment Configuration (`.env`)

Ensure your `.env` file in the root directory contains the necessary API keys:

```env
# ── Core LLM Providers ──
# Gemini 3.8 Flash API key (Required for primary mentor answers & scanned VLM ingestion)
# https://aistudio.google.com/app/apikey
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.8-flash

# Groq API key (Fast query intent routing & alternative generation)
# https://console.groq.com/keys
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-specdec

# ── Qdrant Vector Database ──
QDRANT_HOST=localhost
QDRANT_PORT=6333

# ── Relational Database (Optional - defaults to SQLite fallback if unavailable) ──
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/upsc_rag

# ── News Search Engine API Keys (Optional) ──
TAVILY_API_KEY=your_tavily_api_key_here
SERPER_API_KEY=your_serper_api_key_here
```

---

## 🔧 Useful Commands & Shortcuts

| Action | Command |
|:---|:---|
| **Rebuild Frontend after UI edits** | `cd frontend && npm run build` |
| **Check Qdrant Collections & Points** | Open [http://localhost:6333/dashboard](http://localhost:6333/dashboard) |
| **Extract a Scanned PDF via Gemini Vision** | `python scripts/gemini_batch_extract.py "path/to/book.pdf"` |
| **Batch Ingest Scanned Books Directory** | `python scripts/run_scanned_ingestion.py` |
| **Run Unit & Integration Tests** | `pytest tests/ -v` |
| **Trigger Daily News Scraper Manually** | `python pipeline/daily_news_scraper.py` |

---

## ❓ Troubleshooting

- **"Answer generation temporarily unavailable" / Model Spikes**:
  * Verify that `GEMINI_API_KEY` in `.env` is valid and active.
  * The backend automatically handles fallback rotation if an individual key encounters rate limits.
- **Port 8000 or 5173 already in use**:
  * Run `.\start_dev.bat` (it automatically terminates orphan processes) or run:
    ```powershell
    netstat -ano | findstr :8000
    taskkill /PID <PID> /F
    ```
- **Qdrant Connection Refused**:
  * Ensure Docker Desktop is running. Start the container with:
    ```bash
    docker start qdrant_db
    ```
- **PostgreSQL Connection Failed**:
  * No action required! The application automatically catches connection failures and uses local SQLite (`data/upsc_rag.db`) seamlessly.
