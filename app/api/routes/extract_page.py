"""
app/api/routes/extract_page.py
────────────────────────────────
v2 ingestion endpoints (Gemini 2.5 Flash extractor).

Endpoints:
  POST /api/v2/documents          — upload one or more PDF files
  POST /api/v2/documents/folder   — ingest all PDFs in a server-side folder path

Pipeline per file (identical to v1, only extraction engine differs):
  Validate → Save → Register (PostgreSQL) → Extract (Gemini 2.5 Flash)
  → Preprocess + Chunk → Embed (BGE) → Upsert (Qdrant) → Return JSON
"""

import logging
from pathlib import Path
from typing import List

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import ALLOWED_CLASSIFICATIONS
from app.database.session import get_db
from app.services.page_extraction_service import run_gemini_extraction
from extraction.gemini_client import GEMINI_MODEL as _EXTRACTION_MODEL
from app.services.ingest_pipeline import run_single_ingest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2", tags=["documents-v2"])


# ── Request body for folder ingestion ─────────────────────────────────────────

class FolderIngestRequest(BaseModel):
    folder_path: str
    classification: str


# ── Multi-file upload endpoint ────────────────────────────────────────────────

@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def ingest_files_gemini(
    files: List[UploadFile] = File(..., description="One or more PDF files to ingest"),
    classification: str = Form(
        ..., description="Document classification: History or Anthropology"
    ),
    db: Session = Depends(get_db),
):
    """
    Upload **one or more** PDF files and run the **Gemini 2.5 Flash** extraction pipeline
    for each file.

    Per-page flow (Gemini):
    - **text_service** → extract all text (headings, paragraphs, list items) verbatim
    - **table_service** → extract all tables
    - Both merged into a single page JSON; pages merged into final document JSON

    - **files**: Select one or multiple `.pdf` files (multipart/form-data)
    - **classification**: `History` or `Anthropology`

    Returns a list — one result object per uploaded file.

    **Pipeline:** Validate → Save → Register → Extract (Gemini 2.5 Flash)
    → Preprocess → Embed → Qdrant upsert
    """
    # ── Validate classification ───────────────────────────────────────────────
    if classification not in ALLOWED_CLASSIFICATIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid classification '{classification}'. "
                f"Allowed: {ALLOWED_CLASSIFICATIONS}"
            ),
        )

    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    # ── Validate that all uploads are PDFs before starting any pipeline ───────
    for f in files:
        filename = f.filename or ""
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail=f"'{filename}' is not a PDF. Only .pdf files are accepted.",
            )

    # ── Process each file sequentially ───────────────────────────────────────
    results = []
    for upload in files:
        filename = upload.filename or "unknown.pdf"
        logger.info(f"[v2] Processing upload: {filename}")
        pdf_bytes = await upload.read()
        result = run_single_ingest(
            filename=filename,
            classification=classification,
            pdf_bytes=pdf_bytes,
            db=db,
            extractor_fn=run_gemini_extraction,
        )
        results.append(result)

    return results


# ── Folder ingestion endpoint ─────────────────────────────────────────────────

@router.post("/documents/folder", status_code=status.HTTP_201_CREATED)
def ingest_folder_gemini(
    body: FolderIngestRequest,
    db: Session = Depends(get_db),
):
    """
    Ingest **all PDF files** found inside a server-side folder path using
    **Gemini 2.5 Flash** extraction.

    Provide the absolute path to a folder on the server that contains PDF files.
    The endpoint will recursively discover all `*.pdf` files and run the full
    ingestion pipeline for each one.

    ```json
    {
      "folder_path": "C:/data/pdfs/history",
      "classification": "History"
    }
    ```

    Returns a list — one result object per discovered PDF.

    **Pipeline:** Validate → Save → Register → Extract (Gemini 2.5 Flash)
    → Preprocess → Embed → Qdrant upsert
    """
    # ── Validate classification ───────────────────────────────────────────────
    if body.classification not in ALLOWED_CLASSIFICATIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid classification '{body.classification}'. "
                f"Allowed: {ALLOWED_CLASSIFICATIONS}"
            ),
        )

    # ── Validate folder path ──────────────────────────────────────────────────
    folder = Path(body.folder_path)
    if not folder.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Folder not found: '{body.folder_path}'",
        )
    if not folder.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Path is not a directory: '{body.folder_path}'",
        )

    # ── Discover PDFs ─────────────────────────────────────────────────────────
    pdf_files = sorted(folder.rglob("*.pdf"))
    if not pdf_files:
        raise HTTPException(
            status_code=400,
            detail=f"No PDF files found in folder: '{body.folder_path}'",
        )

    logger.info(
        f"[v2] Folder ingest — found {len(pdf_files)} PDFs in '{folder}' "
        f"| classification={body.classification}"
    )

    # ── Process each PDF sequentially ────────────────────────────────────────
    results = []
    for pdf_path in pdf_files:
        logger.info(f"[v2] Processing PDF from folder: {pdf_path.name}")
        try:
            pdf_bytes = pdf_path.read_bytes()
        except Exception as exc:
            logger.error(f"[v2] Cannot read '{pdf_path}': {exc}")
            results.append({
                "document_id": None,
                "original_filename": pdf_path.name,
                "classification": body.classification,
                "status": "failed",
                "error_message": f"Cannot read file: {exc}",
            })
            continue

        result = run_single_ingest(
            filename=pdf_path.name,
            classification=body.classification,
            pdf_bytes=pdf_bytes,
            db=db,
            extractor_fn=run_gemini_extraction,
        )
        results.append(result)

    return {
        "folder": str(folder),
        "classification": body.classification,
        "extraction_engine": _EXTRACTION_MODEL,
        "total_pdfs": len(pdf_files),
        "results": results,
    }
