"""
Test suite for retrieval evaluator.
Uses mock data — no live RAG required.
"""

from rag_testing_mcp.models import RAGQueryResponse, RAGChunk, DatasetItem
from rag_testing_mcp.evaluators.retrieval import evaluate_retrieval


def _make_response(sources: list[str], pages: list[int | None] = None) -> RAGQueryResponse:
    chunks = []
    for i, s in enumerate(sources):
        meta = {}
        if pages and i < len(pages) and pages[i] is not None:
            meta["page"] = pages[i]
        chunks.append(RAGChunk(
            chunk_id=f"chk_{i}",
            text=f"Content from {s}",
            score=0.9 - i * 0.1,
            rerank_score=0.8 - i * 0.1,
            source=s,
            metadata=meta,
        ))
    return RAGQueryResponse(chunks=chunks, answered=True)


def test_perfect_recall():
    resp = _make_response(["anthropology.pdf", "history.pdf"], [8, 9])
    item = DatasetItem(id="t1", question="test", expected_sources=["anthropology.pdf"], expected_pages=[8])
    metrics = evaluate_retrieval(resp, item)
    assert metrics.recall_at_1 == 1.0
    assert metrics.mrr == 1.0


def test_no_match():
    resp = _make_response(["geography.pdf", "polity.pdf"])
    item = DatasetItem(id="t2", question="test", expected_sources=["anthropology.pdf"])
    metrics = evaluate_retrieval(resp, item)
    assert metrics.recall_at_1 == 0.0
    assert metrics.mrr == 0.0


def test_not_available_when_no_expected():
    resp = _make_response(["anthropology.pdf"])
    item = DatasetItem(id="t3", question="test")
    metrics = evaluate_retrieval(resp, item)
    assert metrics.status == "not_available"


def test_recall_at_3():
    resp = _make_response(["x.pdf", "y.pdf", "anthropology.pdf", "z.pdf"])
    item = DatasetItem(id="t4", question="test", expected_sources=["anthropology.pdf"])
    metrics = evaluate_retrieval(resp, item)
    assert metrics.recall_at_1 == 0.0
    assert metrics.recall_at_3 == 1.0
    assert metrics.mrr == round(1.0 / 3, 4)


def test_empty_chunks():
    resp = RAGQueryResponse(chunks=[], answered=True)
    item = DatasetItem(id="t5", question="test", expected_sources=["anthropology.pdf"])
    metrics = evaluate_retrieval(resp, item)
    assert metrics.recall_at_1 == 0.0
    assert metrics.precision_at_k == 0.0
