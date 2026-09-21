"""
app/services/qdrant_service.py
───────────────────────────────
Connects to Qdrant vector database (running in Docker at localhost:6333),
manages per-classification collections, and upserts embedded vectors.

Collections:
    - history_collection
    - anthropology_collection

Payload stored per point:
    {
        "file_id":      str,
        "chunk_id":     str,
        "classification": str,
        "text":         str,
        "metadata":     dict,
    }
"""
import logging
import uuid
from typing import Any
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from app.core.config import (
    QDRANT_HOST,
    QDRANT_PORT,
    QDRANT_COLLECTION_MAP,
    EMBEDDING_DIMENSION,
)

logger = logging.getLogger(__name__)

_qdrant_client: QdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    """Return a singleton QdrantClient instance."""
    global _qdrant_client
    if _qdrant_client is None:
        logger.info(f"Connecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT} …")
        _qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        logger.info("Qdrant client connected ✓")
    return _qdrant_client


def ensure_collections():
    """
    Idempotently ensure that all required Qdrant collections exist.
    Called on FastAPI application startup.
    """
    try:
        client = get_qdrant_client()
        existing = {col.name for col in client.get_collections().collections}

        for classification, collection_name in QDRANT_COLLECTION_MAP.items():
            if collection_name not in existing:
                logger.info(
                    f"Creating Qdrant collection '{collection_name}' "
                    f"(dim={EMBEDDING_DIMENSION}, Cosine) for '{classification}' …"
                )
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=EMBEDDING_DIMENSION,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"Created collection '{collection_name}' ✓")
            else:
                logger.info(f"Qdrant collection '{collection_name}' exists ✓")
    except Exception as exc:
        logger.warning(
            f"Could not initialize Qdrant collections (is Qdrant running?): {exc}"
        )


def resolve_collection_name(classification: str) -> str:
    """Resolve Qdrant collection name for built-in or dynamic classifications."""
    if classification in QDRANT_COLLECTION_MAP:
        return QDRANT_COLLECTION_MAP[classification]

    # Check dynamic classifications in DB
    try:
        from app.database.session import SessionLocal
        from app.database.classification_models import Classification
        with SessionLocal() as db:
            c = db.query(Classification).filter(Classification.name == classification).first()
            if c and c.collection_name:
                return c.collection_name
    except Exception:
        pass

    clean_name = classification.strip().lower().replace(" ", "_")
    return f"{clean_name}_collection"


def run_qdrant_upsert(
    file_id: str,
    classification: str,
    embedded_chunks: list[dict],
) -> tuple[bool, str | None]:
    """
    Upsert embedded chunk vectors into the corresponding Qdrant collection.

    Args:
        file_id:         UUID of the document record.
        classification:  'History', 'Anthropology', or any registered dynamic subject.
        embedded_chunks: Output list from run_embedding().

    Returns:
        (success: bool, error_message: str | None)
    """
    collection_name = resolve_collection_name(classification)
    if not collection_name:
        error_msg = f"No Qdrant collection mapped for classification '{classification}'"
        logger.error(f"[{file_id}] {error_msg}")
        return False, error_msg

    if not embedded_chunks:
        error_msg = "No embedded chunks provided for Qdrant upsert."
        logger.error(f"[{file_id}] {error_msg}")
        return False, error_msg

    logger.info(
        f"[{file_id}] Upserting {len(embedded_chunks)} vectors to Qdrant "
        f"collection '{collection_name}' …"
    )

    try:
        client = get_qdrant_client()

        # Re-verify collection exists
        existing = {col.name for col in client.get_collections().collections}
        if collection_name not in existing:
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIMENSION,
                    distance=Distance.COSINE,
                ),
            )

        # Build PointStruct list
        points: list[PointStruct] = []
        for chunk in embedded_chunks:
            # Qdrant only accepts UUID or unsigned int as point ID.
            # Generate a deterministic UUID5 from (file_id + chunk_id) for stability.
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{file_id}:{chunk['chunk_id']}"))

            payload: dict[str, Any] = {
                "file_id": file_id,
                "chunk_id": chunk["chunk_id"],
                "classification": classification,
                "text": chunk["text"],
                "metadata": chunk.get("metadata", {}),
            }

            points.append(
                PointStruct(
                    id=point_id,
                    vector=chunk["vector"],
                    payload=payload,
                )
            )

        # Upsert in batch
        operation_info = client.upsert(
            collection_name=collection_name,
            points=points,
            wait=True,
        )

        logger.info(
            f"[{file_id}] Qdrant upsert complete ✓ — "
            f"collection='{collection_name}', status={operation_info.status}"
        )
        return True, None

    except Exception as exc:
        error_msg = f"Qdrant upsert failed: {exc}"
        logger.exception(f"[{file_id}] {error_msg}")
        return False, error_msg


def delete_document_vectors(
    file_id: str,
    classification: str,
) -> tuple[bool, int, str | None]:
    """
    Delete all Qdrant vector points belonging to a specific document.

    Args:
        file_id:        UUID of the document record.
        classification: 'History' or 'Anthropology' — determines which collection to target.

    Returns:
        (success: bool, deleted_count: int, error_message: str | None)
    """
    collection_name = QDRANT_COLLECTION_MAP.get(classification)
    if not collection_name:
        error_msg = f"No Qdrant collection mapped for classification '{classification}'"
        logger.error(f"[{file_id}] {error_msg}")
        return False, 0, error_msg

    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client = get_qdrant_client()

        # First count how many points exist for this file
        count_result = client.count(
            collection_name=collection_name,
            count_filter=Filter(
                must=[FieldCondition(key="file_id", match=MatchValue(value=file_id))]
            ),
            exact=True,
        )
        point_count = count_result.count

        if point_count == 0:
            logger.warning(
                f"[{file_id}] No vectors found in '{collection_name}' — nothing to delete."
            )
            return True, 0, None

        # Delete all matching points
        client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="file_id", match=MatchValue(value=file_id))]
            ),
            wait=True,
        )

        logger.info(
            f"[{file_id}] Deleted {point_count} vector(s) from "
            f"Qdrant collection '{collection_name}' ✓"
        )
        return True, point_count, None

    except Exception as exc:
        error_msg = f"Qdrant delete failed: {exc}"
        logger.exception(f"[{file_id}] {error_msg}")
        return False, 0, error_msg
