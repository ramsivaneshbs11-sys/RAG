# 🚀 UPSC RAG Learning Assistant — Execution Guide

This document provides complete, updated instructions on how to run the application, whether in Development, Built-in Single-Port, or Full Docker mode.

---

## 🛠️ Prerequisites

1. **Docker Desktop** (Required) — [Download](https://www.docker.com/products/docker-desktop/)
   * Runs the **Qdrant Vector Database** (`qdrant_db` on port `6333`) and PostgreSQL.
   * *Must be running in the background.*
2. **Python** (v3.10 or higher) — [Download](https://www.python.org/)
3. **Node.js** (v18 or higher) — [Download](https://nodejs.org/) *(only needed if developing frontend)*

---

## ⚡ 1. The Quickest Way (Built-in Mode — Single Port :8000) ⭐

The React frontend is **pre-built** into `frontend/dist`. You only need to run the Python backend, which serves both the API and the web app together!

1. Make sure **Docker Desktop** is open (so `qdrant_db` is running).
2. Open a terminal in the project root folder and start FastAPI:
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
3. Open your browser and go to:
   * **Full Web Application & Chat**: [http://localhost:8000](http://localhost:8000)
   * **Interactive Swagger API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

> **No Node.js or `npm run dev` required in this mode!**

---

## 💻 2. Full Development Environment (Windows 1-Click Script)

If you are modifying React UI code and want live hot-reloading (HMR):

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

## 🐳 3. Full Docker Deployment

To run everything (Backend + Frontend + Qdrant + Postgres) inside Docker containers without installing Python locally:

```bash
docker compose up -d
```
* Access the app at: [http://localhost:8000](http://localhost:8000)
* Stop containers: `docker compose down`

---

## ⚙️ Environment Configuration (`.env`)

Ensure your `.env` file in the root directory contains the necessary API keys:

```env
# Gemini API Key (Gemini 3.8 Flash model)
GEMINI_API_KEY=your_gemini_api_key_here

# Groq API Key (Fast query intent classification)
GROQ_API_KEY=your_groq_api_key_here

# Qdrant Vector Database
QDRANT_HOST=localhost
QDRANT_PORT=6333

# PostgreSQL Database (Optional for local user sessions)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=upsc_rag
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
```

---

## 🔧 Useful Commands & Shortcuts

| Action | Command |
|:---|:---|
| **Rebuild Frontend after UI edits** | `cd frontend && npm run build` |
| **Check Qdrant Collections** | Open [http://localhost:6333/dashboard](http://localhost:6333/dashboard) |
| **Extract a Scanned PDF via Gemini Vision** | `python scripts/gemini_batch_extract.py "path/to/book.pdf"` |
| **Health Check Endpoint** | [http://localhost:8000/health](http://localhost:8000/health) |

---

## ❓ Troubleshooting

- **"Answer generation temporarily unavailable" / Model Unavailable**:
  * Check that your API keys in `.env` are valid.
  * The system automatically rotates through fallback Gemini API keys if one encounters temporary spikes.
- **Port 8000 or 5173 already in use**:
  * Run `.\start_dev.bat` (it auto-clears ports) or run:
    ```powershell
    netstat -ano | findstr :8000
    taskkill /PID <PID> /F
    ```
- **Qdrant Connection Refused**:
  * Ensure Docker Desktop is running. Start the container if needed: `docker start qdrant_db`.
