"""
Test suite for generation (faithfulness/grounding) evaluator.
Includes the critical 3.1% vs 4% grounding test.
"""

from rag_testing_mcp.models import RAGQueryResponse, RAGChunk, DatasetItem, FailureType
from rag_testing_mcp.evaluators.generation import evaluate_generation


def _make_resp(answer: str, chunk_texts: list[str], answered: bool = True) -> RAGQueryResponse:
    chunks = [
        RAGChunk(chunk_id=f"chk_{i}", text=t, score=0.9, rerank_score=0.8, source="doc.pdf")
        for i, t in enumerate(chunk_texts)
    ]
    return RAGQueryResponse(answer=answer, answered=answered, chunks=chunks)


def test_grounding_failure_number_mismatch():
    """Critical test: context says 3.1% but answer says 4%."""
    resp = _make_resp(
        answer="Human DNA shares approximately 4% similarity with other vertebrates.",
        chunk_texts=["Studies show human DNA shares 3.1% similarity with other vertebrate species."],
    )
    item = DatasetItem(id="q001", question="DNA similarities")
    metrics, failures = evaluate_generation(resp, item)

    # Must flag grounding failure for the 4% number
    grounding_failures = [f for f in failures if f.failure_type == FailureType.GROUNDING_FAILURE]
    assert len(grounding_failures) > 0
    assert metrics.hallucination_risk > 0


def test_grounded_answer():
    """Answer uses the exact number from context — should pass."""
    resp = _make_resp(
        answer="Human DNA shares 3.1% similarity with other vertebrates.",
        chunk_texts=["Studies show human DNA shares 3.1% similarity with other vertebrate species."],
    )
    item = DatasetItem(id="q002", question="DNA similarities")
    metrics, failures = evaluate_generation(resp, item)
    grounding_failures = [f for f in failures if f.failure_type == FailureType.GROUNDING_FAILURE]
    assert len(grounding_failures) == 0
    assert metrics.faithfulness > 0.5


def test_gated_answer():
    """If the RAG was gated, report generation failure."""
    resp = _make_resp(answer="", chunk_texts=[], answered=False)
    resp.gated = True
    resp.gate_reason = "Low relevance score"
    item = DatasetItem(id="q003", question="test")
    metrics, failures = evaluate_generation(resp, item)
    assert metrics.answer_relevance == 0.0
    assert any(f.failure_type == FailureType.GENERATION_FAILURE for f in failures)


def test_high_faithfulness():
    resp = _make_resp(
        answer="Cultural ecology studies how societies adapt to environments through cultural means.",
        chunk_texts=[
            "Cultural ecology is the study of how human societies adapt to "
            "and modify their natural environments through cultural means."
        ],
    )
    item = DatasetItem(id="q004", question="What is cultural ecology?")
    metrics, failures = evaluate_generation(resp, item)
    assert metrics.faithfulness >= 0.5


def test_empty_context():
    resp = _make_resp(answer="Some answer.", chunk_texts=[])
    item = DatasetItem(id="q005", question="test")
    metrics, failures = evaluate_generation(resp, item)
    assert any(f.failure_type == FailureType.RETRIEVAL_FAILURE for f in failures)
