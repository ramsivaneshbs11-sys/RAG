# ═══════════════════════════════════════════════════════════════════════════════
# Stage 1 — Build React Frontend
#   Uses Node.js ONLY for the build step.
#   The resulting dist/ (~1-3 MB) is copied into Stage 2; Node.js is discarded.
# ═══════════════════════════════════════════════════════════════════════════════
FROM node:20-alpine AS frontend-builder

WORKDIR /build/frontend

# Install dependencies first (layer-cached unless package.json changes)
COPY frontend/package*.json ./
RUN npm ci --silent

# Copy source and build
COPY frontend/ ./
RUN npm run build
# → output: /build/frontend/dist/


# ═══════════════════════════════════════════════════════════════════════════════
# Stage 2 — Python / FastAPI Backend (Production Image)
#   Only Python + compiled frontend assets land here.
#   No Node.js, no node_modules, no dev tooling.
# ═══════════════════════════════════════════════════════════════════════════════
FROM python:3.11-slim AS backend

# System packages needed by heavy ML deps (Docling, sentence-transformers, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libgomp1 \
        libpq-dev \
        poppler-utils \
        tesseract-ocr \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python dependencies ────────────────────────────────────────────────────────
# Copy requirements first for better layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ── Application source code ───────────────────────────────────────────────────
COPY . .

# ── Drop the compiled React dist from Stage 1 ─────────────────────────────────
# This replaces any stale/empty frontend/dist that may exist in source.
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

# ── Runtime environment ───────────────────────────────────────────────────────
# These are defaults; override via docker-compose env_file or AWS secrets.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_DISABLE_SYMLINKS=1 \
    PORT=8000

EXPOSE 8000

# ── Healthcheck so ECS / ALB knows when the container is ready ────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ── Start server ──────────────────────────────────────────────────────────────
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
