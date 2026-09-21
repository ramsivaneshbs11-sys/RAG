"""
app/api/routes/documents.py
────────────────────────────
v1 ingestion endpoints (Docling extractor).

Endpoints:
  POST /api/v1/documents               — upload one or more PDF files
  POST /api/v1/documents/folder        — ingest all PDFs in a server-side folder path
  POST /api/v1/documents/retry-failed  — resume all failed documents from embedding step

Pipeline per file (fully sequential):
  Validate → Save → Register (PostgreSQL) → Extract (Docling)
  → Preprocess + Chunk → Embed (BGE) → Upsert (Qdrant) → Return JSON
"""
import logging
from enum import Enum
from pathlib import Path
from typing import List

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import ALLOWED_CLASSIFICATIONS, get_all_allowed_classifications
from app.database.session import get_db
from app.database.models import Document
from app.database import repository
from app.services.extraction_service import run_extraction
from app.services.ingest_pipeline import run_single_ingest
from app.services.embedding_service import run_embedding
from app.services.qdrant_service import run_qdrant_upsert, delete_document_vectors

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["documents"])


# ── Request body for folder ingestion ─────────────────────────────────────────

class FolderIngestRequest(BaseModel):
    folder_path: str
    classification: str


# ── Multi-file upload endpoint ────────────────────────────────────────────────

@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def ingest_files(
    files: List[UploadFile] = File(..., description="One or more PDF files to ingest"),
    classification: str = Form(
        ..., description="Document classification e.g. History, Anthropology, or dynamic subject"
    ),
    db: Session = Depends(get_db),
):
    """
    Upload **one or more** PDF files and run the full ingestion pipeline for each.

    - **files**: Select one or multiple `.pdf` files (multipart/form-data)
    - **classification**: `History` or `Anthropology`

    Returns a list — one result object per uploaded file.

    Pipeline per file: Validate → Save → Register → Extract (Docling)
    → Preprocess → Embed → Qdrant upsert
    """
    # ── Validate classification ───────────────────────────────────────────────
    if classification not in ALLOWED_CLASSIFICATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid classification '{classification}'. Allowed: {ALLOWED_CLASSIFICATIONS}",
        )

    # ── Validate classification ───────────────────────────────────────────────
    allowed = get_all_allowed_classifications(db)
    if classification not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid classification '{classification}'. Allowed: {allowed}",
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
        logger.info(f"Processing upload: {filename}")
        pdf_bytes = await upload.read()
        result = run_single_ingest(
            filename=filename,
            classification=classification,
            pdf_bytes=pdf_bytes,
            db=db,
            extractor_fn=run_extraction,
        )
        results.append(result)

    return results


# ── Folder ingestion endpoint ─────────────────────────────────────────────────

@router.post("/documents/folder", status_code=status.HTTP_201_CREATED)
def ingest_folder(
    body: FolderIngestRequest,
    db: Session = Depends(get_db),
):
    """
    Ingest **all PDF files** found inside a server-side folder path.

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

    Pipeline per file: Validate → Save → Register → Extract (Docling)
    → Preprocess → Embed → Qdrant upsert
    """
    # ── Validate classification ───────────────────────────────────────────────
    allowed = get_all_allowed_classifications(db)
    if body.classification not in allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid classification '{body.classification}'. "
                f"Allowed: {allowed}"
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
        f"Folder ingest (v1) — found {len(pdf_files)} PDFs in '{folder}' "
        f"| classification={body.classification}"
    )

    # ── Process each PDF sequentially ────────────────────────────────────────
    results = []
    for pdf_path in pdf_files:
        logger.info(f"Processing PDF from folder: {pdf_path.name}")
        try:
            pdf_bytes = pdf_path.read_bytes()
        except Exception as exc:
            logger.error(f"Cannot read '{pdf_path}': {exc}")
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
            extractor_fn=run_extraction,
        )
        results.append(result)

    return {
        "folder": str(folder),
        "classification": body.classification,
        "total_pdfs": len(pdf_files),
        "results": results,
    }


# ── List documents endpoint ──────────────────────────────────────────────────

@router.get("/documents", status_code=status.HTTP_200_OK)
def list_documents(
    classification: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """
    List all documents tracked in the PostgreSQL database.

    Allows filtering by:
    - **classification**: e.g., "History", "Anthropology"
    - **status**: e.g., "ingested", "failed", "registered"

    Use this endpoint to **find the UUID (`file_id`)** of a specific document
    (like `Satyagraha.pdf`) so you can copy and pass it to the delete API.
    """
    query = db.query(Document)

    if classification:
        query = query.filter(Document.classification == classification)
    if status:
        query = query.filter(Document.status == status)

    docs = query.order_by(Document.created_at.desc()).all()

    return {
        "total": len(docs),
        "documents": [
            {
                "file_id": doc.id,
                "original_filename": doc.original_filename,
                "classification": doc.classification,
                "status": doc.status,
                "error_message": doc.error_message,
                "created_at": doc.created_at.isoformat(),
                "updated_at": doc.updated_at.isoformat(),
            }
            for doc in docs
        ],
    }


# ── Retry Helpers ─────────────────────────────────────────────────────────────

def _execute_document_retry(doc: Document, db: Session) -> dict:
    """
    Attempts to recover a failed document using either:
      1. Fast-path: Preprocessed JSON exists → runs BGE embedding & Qdrant upsert (~15s)
      2. Full-path: Preprocessed JSON missing but uploaded PDF exists → re-runs pipeline
    """
    entry = {
        "document_id": doc.id,
        "original_filename": doc.original_filename,
        "classification": doc.classification,
        "previous_error": doc.error_message,
    }

    # PATH A: Fast-path — preprocessed JSON exists on disk
    prep_path = Path(doc.preprocessed_json_path) if doc.preprocessed_json_path else None
    if prep_path and prep_path.exists():
        logger.info(f"[{doc.id}] Fast-path retry: using existing preprocessed JSON: {prep_path}")
        repository.update_document_status(db, doc.id, status="embedding")
        emb_success, embedded_chunks, emb_error = run_embedding(prep_path)
        if not emb_success:
            repository.update_document_status(db, doc.id, status="failed", error_message=emb_error)
            entry["status"] = "failed"
            entry["error"] = f"Embedding failed: {emb_error}"
            return entry

        qdrant_success, qdrant_error = run_qdrant_upsert(
            file_id=doc.id,
            classification=doc.classification,
            embedded_chunks=embedded_chunks,
        )
        if not qdrant_success:
            repository.update_document_status(db, doc.id, status="failed", error_message=qdrant_error)
            entry["status"] = "failed"
            entry["error"] = f"Qdrant upsert failed: {qdrant_error}"
            return entry

        repository.update_document_status(db, doc.id, status="ingested", error_message=None)
        entry["status"] = "ingested"
        entry["mode"] = "fast_path_resume"
        entry["vectors_upserted"] = len(embedded_chunks)
        return entry

    # PATH B: Full-path recovery — re-read uploaded PDF from disk if available
    pdf_path = Path(doc.file_path) if doc.file_path else None
    if pdf_path and pdf_path.exists():
        logger.info(f"[{doc.id}] Full-path retry: re-running extraction from saved PDF: {pdf_path}")
        try:
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            result = run_single_ingest(
                filename=doc.original_filename,
                classification=doc.classification,
                pdf_bytes=pdf_bytes,
                db=db,
                extractor_fn=run_extraction,
            )
            if result.get("status") == "success":
                entry["status"] = "ingested"
                entry["mode"] = "full_reingest"
                entry["vectors_upserted"] = result.get("chunks", 0)
                return entry
            else:
                entry["status"] = "failed"
                entry["error"] = result.get("error", "Re-ingestion failed")
                return entry
        except Exception as exc:
            logger.exception(f"[{doc.id}] Full-path retry exception: {exc}")
            entry["status"] = "failed"
            entry["error"] = str(exc)
            return entry

    # PATH C: Neither preprocessed JSON nor original PDF found on disk
    entry["status"] = "skipped"
    entry["reason"] = "Neither preprocessed JSON nor original PDF file found on disk."
    return entry


# ── Retry-failed endpoint ─────────────────────────────────────────────────────

@router.post("/documents/retry-failed", status_code=status.HTTP_200_OK)
def retry_failed_documents(
    db: Session = Depends(get_db),
):
    """
    Resume ingestion for all documents currently marked as **failed** in database.

    For each failed document this endpoint:
    - Fast-path: Uses preprocessed JSON on disk, skipping extraction entirely (~15s).
    - Full-path: If preprocessed JSON is missing, re-extracts from the saved PDF file.
    - Upserts the vectors to the correct Qdrant collection.
    - Updates status to `ingested` on success.
    """
    failed_docs = db.query(Document).filter(Document.status == "failed").all()

    if not failed_docs:
        return {
            "message": "No failed documents found. Everything is clean!",
            "recovered": 0,
            "skipped": 0,
            "still_failed": 0,
            "results": [],
        }

    logger.info(f"retry-failed: Found {len(failed_docs)} failed document(s). Starting recovery...")

    results = []
    recovered = 0
    skipped = 0
    still_failed = 0

    for doc in failed_docs:
        entry = _execute_document_retry(doc, db)
        results.append(entry)
        if entry["status"] == "ingested":
            recovered += 1
        elif entry["status"] == "skipped":
            skipped += 1
        else:
            still_failed += 1

    logger.info(
        f"retry-failed complete — recovered={recovered}, "
        f"skipped={skipped}, still_failed={still_failed}"
    )

    return {
        "message": f"Retry complete: {recovered} recovered, {still_failed} failed, {skipped} skipped.",
        "total_failed_found": len(failed_docs),
        "recovered": recovered,
        "skipped": skipped,
        "still_failed": still_failed,
        "results": results,
    }


# ── Single document retry endpoint ──────────────────────────────────────────

@router.post("/documents/{document_id}/retry", status_code=status.HTTP_200_OK)
def retry_single_document(
    document_id: str,
    db: Session = Depends(get_db),
):
    """
    Retry ingestion for a single specific failed document.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )

    logger.info(f"[{document_id}] Starting single document retry for '{doc.original_filename}'...")
    result = _execute_document_retry(doc, db)

    if result["status"] == "failed":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "Document recovery failed."),
        )

    return result


# ── Delete document endpoint ────────────────────────────────────────────────

@router.delete("/documents/{document_id}", status_code=status.HTTP_200_OK)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
):
    """
    Permanently delete a document and all its associated data.

    Cleans up all 4 storage layers in order:
    1. **Qdrant vectors** — removes all embedded vector points for this document
    2. **PostgreSQL record** — removes the document metadata row
    3. **Uploaded PDF file** — deletes the original PDF from the uploads directory
    4. **Extracted JSON** — deletes the Docling extraction output file
    5. **Preprocessed JSON** — deletes the chunked/preprocessed file

    Use this when the syllabus is updated and old content needs to be removed
    before uploading the revised version.

    - **document_id**: The UUID of the document (from `GET /api/v1/documents` or DB)
    """
    # ── Step 0: Look up the document in PostgreSQL ─────────────────────────
    doc = repository.get_document_by_id(db, document_id)
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{document_id}' not found in the database."
        )

    logger.info(
        f"[DELETE] Starting deletion of document '{doc.original_filename}' "
        f"(id={document_id}, classification={doc.classification})"
    )

    report = {
        "document_id":        document_id,
        "original_filename":  doc.original_filename,
        "classification":     doc.classification,
        "qdrant_vectors_deleted":  0,
        "postgres_record_deleted": False,
        "pdf_file_deleted":        False,
        "extracted_json_deleted":  False,
        "preprocessed_json_deleted": False,
        "warnings": [],
    }

    # ── Step 1: Delete vectors from Qdrant ─────────────────────────────
    qdrant_ok, deleted_count, qdrant_err = delete_document_vectors(
        file_id=document_id,
        classification=doc.classification,
    )
    if qdrant_ok:
        report["qdrant_vectors_deleted"] = deleted_count
        logger.info(f"[DELETE] Qdrant: {deleted_count} vector(s) deleted.")
    else:
        warn_msg = f"Qdrant deletion failed: {qdrant_err}"
        report["warnings"].append(warn_msg)
        logger.warning(f"[DELETE] {warn_msg}")

    # ── Step 2: Delete record from PostgreSQL ───────────────────────────
    # Save file paths before deleting record (we need them for disk cleanup)
    pdf_path             = Path(doc.file_path)                if doc.file_path             else None
    extracted_json_path  = Path(doc.extracted_json_path)     if doc.extracted_json_path  else None
    preprocessed_json_path = Path(doc.preprocessed_json_path) if doc.preprocessed_json_path else None

    db_deleted = repository.delete_document(db, document_id)
    report["postgres_record_deleted"] = db_deleted
    if db_deleted:
        logger.info(f"[DELETE] PostgreSQL record removed.")
    else:
        report["warnings"].append("PostgreSQL record was not found or could not be deleted.")

    # ── Step 3: Delete uploaded PDF from disk ──────────────────────────
    if pdf_path and pdf_path.exists():
        try:
            pdf_path.unlink()
            report["pdf_file_deleted"] = True
            logger.info(f"[DELETE] PDF file deleted: {pdf_path}")
        except Exception as exc:
            warn_msg = f"Could not delete PDF file '{pdf_path}': {exc}"
            report["warnings"].append(warn_msg)
            logger.warning(f"[DELETE] {warn_msg}")
    else:
        report["warnings"].append(f"PDF file not found on disk (path: {pdf_path}) — skipped.")

    # ── Step 4: Delete extracted JSON ─────────────────────────────────
    if extracted_json_path and extracted_json_path.exists():
        try:
            extracted_json_path.unlink()
            report["extracted_json_deleted"] = True
            logger.info(f"[DELETE] Extracted JSON deleted: {extracted_json_path}")
        except Exception as exc:
            warn_msg = f"Could not delete extracted JSON '{extracted_json_path}': {exc}"
            report["warnings"].append(warn_msg)
            logger.warning(f"[DELETE] {warn_msg}")
    else:
        report["warnings"].append("Extracted JSON not found on disk — skipped.")

    # ── Step 5: Delete preprocessed JSON ───────────────────────────────
    if preprocessed_json_path and preprocessed_json_path.exists():
        try:
            preprocessed_json_path.unlink()
            report["preprocessed_json_deleted"] = True
            logger.info(f"[DELETE] Preprocessed JSON deleted: {preprocessed_json_path}")
        except Exception as exc:
            warn_msg = f"Could not delete preprocessed JSON '{preprocessed_json_path}': {exc}"
            report["warnings"].append(warn_msg)
            logger.warning(f"[DELETE] {warn_msg}")
    else:
        report["warnings"].append("Preprocessed JSON not found on disk — skipped.")

    logger.info(
        f"[DELETE] Complete — document '{doc.original_filename}' fully purged. "
        f"Qdrant vectors: {report['qdrant_vectors_deleted']}, "
        f"DB: {report['postgres_record_deleted']}, "
        f"PDF: {report['pdf_file_deleted']}, "
        f"Warnings: {len(report['warnings'])}"
    )

    return {
        "message": f"Document '{doc.original_filename}' has been permanently deleted.",
        **report,
    }
