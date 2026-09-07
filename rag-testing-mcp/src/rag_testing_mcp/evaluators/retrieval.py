"""
Retrieval quality evaluator.

Calculates Recall@1, Recall@3, Recall@5, Precision@K, and MRR
by comparing retrieved chunks against expected sources/pages.

Source matching priority:
  1. metadata.file_name (exact, normalized)
  2. metadata.file_name partial match (UUID contains keyword)
  3. chunk.source field (fallback)
  4. Keyword match: expected label appears in chunk text (semantic fallback)
"""

from __future__ import annotations
import re
from rag_testing_mcp.models import RAGQueryResponse, DatasetItem, RetrievalMetrics


def _normalize(s: str) -> str:
    """Lowercase, strip extension, whitespace, and hyphens."""
    return re.sub(r"[\s\-_]+", " ", s.lower().strip()
                  .replace(".pdf", "").replace(".docx", ""))


def _chunk_source_labels(chunk) -> list[str]:
    """Return all candidate source labels for a chunk (file_name + source + text keywords)."""
    labels = []
    # Priority 1: actual stored filename
    fname = chunk.metadata.get("file_name") or chunk.metadata.get("filename") or ""
    if fname:
        labels.append(_normalize(fname))
    # Priority 2: chunk.source field
    labels.append(_normalize(chunk.source))
    # Priority 3: infer from chunk text — extract nouns/domain words
    if chunk.text:
        labels.append(chunk.text[:200].lower())
    return labels


def _is_source_match(chunk, expected_label: str) -> bool:
    """Check if an expected label matches a chunk's source by any strategy."""
    norm_expected = _normalize(expected_label)
    candidate_labels = _chunk_source_labels(chunk)

    for label in candidate_labels:
        # Exact match
        if norm_expected == label:
            return True
        # Substring match (expected label is a category keyword like "anthropology")
        if norm_expected in label:
            return True
        # Partial UUID match: expected label is a UUID fragment
        if len(norm_expected) > 6 and norm_expected in label:
            return True

    return False


def evaluate_retrieval(
    response: RAGQueryResponse,
    dataset_item: DatasetItem,
) -> RetrievalMetrics:
    """Evaluate retrieval quality for a single question.

    If the dataset_item has no expected_sources and no expected_pages,
    returns status="not_available".
    """
    expected_sources = dataset_item.expected_sources
    expected_pages = dataset_item.expected_pages

    if not expected_sources and not expected_pages:
        return RetrievalMetrics(status="not_available")

    chunks = response.chunks
    if not chunks:
        return RetrievalMetrics(
            recall_at_1=0.0,
            recall_at_3=0.0,
            recall_at_5=0.0,
            precision_at_k=0.0,
            mrr=0.0,
        )

    expected_page_set = set(expected_pages or [])

    def _get_chunk_pages(chunk) -> set[int]:
        """Extract page numbers from chunk metadata (handles both int and list)."""
        pages: set[int] = set()
        for key in ("page_numbers", "page_number", "page", "pages"):
            val = chunk.metadata.get(key)
            if val is None:
                continue
            if isinstance(val, list):
                for p in val:
                    try:
                        pages.add(int(p))
                    except (ValueError, TypeError):
                        pass
            else:
                try:
                    pages.add(int(val))
                except (ValueError, TypeError):
                    pass
        return pages

    def _is_hit(idx: int) -> bool:
        """Check if chunk at idx matches expected source OR expected page."""
        chunk = chunks[idx]

        # Source matching: any expected source label matches this chunk
        source_match = False
        if expected_sources:
            source_match = any(_is_source_match(chunk, label) for label in expected_sources)

        # Page matching: chunk contains any of the expected page numbers
        page_match = False
        if expected_page_set:
            chunk_pages = _get_chunk_pages(chunk)
            page_match = bool(chunk_pages & expected_page_set)

        # If both are specified, require both to match
        if expected_sources and expected_page_set:
            return source_match and page_match
        # If only one is specified, that one must match
        return source_match or page_match

    # Recall@K: fraction of expected items found in top-K retrieved
    def recall_at_k(k: int) -> float:
        hits = sum(1 for i in range(min(k, len(chunks))) if _is_hit(i))
        total_expected = max(
            len(expected_sources or []),
            len(expected_page_set),
            1,
        )
        return round(hits / total_expected, 4)

    # Precision@K: fraction of top-K that are relevant
    k = len(chunks)
    precision_hits = sum(1 for i in range(k) if _is_hit(i))
    precision = round(precision_hits / max(k, 1), 4)

    # MRR: reciprocal rank of the first relevant result
    mrr = 0.0
    for i in range(len(chunks)):
        if _is_hit(i):
            mrr = round(1.0 / (i + 1), 4)
            break

    return RetrievalMetrics(
        recall_at_1=recall_at_k(1),
        recall_at_3=recall_at_k(3),
        recall_at_5=recall_at_k(5),
        precision_at_k=precision,
        mrr=mrr,
    )
