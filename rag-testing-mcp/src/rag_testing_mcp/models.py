"""
Pydantic schemas for rag-testing-mcp.

Covers:
  - RAG API request/response (mapped to the real UPSC RAG QueryResponse)
  - Dataset items (test cases)
  - Evaluation results, metrics, and failure classifications
"""

from __future__ import annotations

import enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ════════════════════════════════════════════════════════════════════════
# RAG API Schemas (mirrors the real QueryResponse from the UPSC RAG)
# ════════════════════════════════════════════════════════════════════════

class RAGQueryRequest(BaseModel):
    """Payload sent to POST /api/v1/query."""
    query: str
    top_k: int = 5
    mode: str = "prelims"
    sub_mode: str = "summary"
    session_id: Optional[str] = None


class RAGChunk(BaseModel):
    """A single retrieved chunk from the RAG response."""
    chunk_id: str = ""
    text: str = ""
    score: float = 0.0
    rerank_score: float = 0.0
    source: str = "unknown"
    metadata: dict[str, Any] = Field(default_factory=dict)


class RAGCitation(BaseModel):
    """A rich citation from the RAG response."""
    chunk_id: str = ""
    document: str = ""
    pages: Any = None  # int | list[int] | "?"
    preview: str = ""
    url: Optional[str] = None


class RAGQueryResponse(BaseModel):
    """Full response from the RAG API.  Fields that are not available
    from a particular RAG are set to their default / sentinel values."""
    query: str = ""
    mode: str = ""
    sub_mode: Optional[str] = None
    classification: str = ""
    confidence: float = 0.0
    all_scores: dict[str, float] = Field(default_factory=dict)
    routing: str = ""
    total_candidates: int = 0
    answer: str = ""
    answered: bool = False
    citations: list[str] = Field(default_factory=list)
    rich_citations: list[RAGCitation] = Field(default_factory=list)
    gated: bool = False
    gate_reason: Optional[str] = None
    cache_hit: bool = False
    log_info: str = ""
    chunks: list[RAGChunk] = Field(default_factory=list)

    # Timing (injected by our client, not from RAG itself)
    latency_ms: float = 0.0


# ════════════════════════════════════════════════════════════════════════
# Dataset Schemas
# ════════════════════════════════════════════════════════════════════════

class DatasetItem(BaseModel):
    """A single test case in the evaluation dataset."""
    id: str = ""
    question: str
    mode: str = "prelims"
    sub_mode: str = "summary"
    reference_answer: Optional[str] = None
    expected_sources: Optional[list[str]] = None
    expected_pages: Optional[list[int]] = None


# ════════════════════════════════════════════════════════════════════════
# Failure Classification
# ════════════════════════════════════════════════════════════════════════

class FailureType(str, enum.Enum):
    RETRIEVAL_FAILURE = "RETRIEVAL_FAILURE"
    GENERATION_FAILURE = "GENERATION_FAILURE"
    GROUNDING_FAILURE = "GROUNDING_FAILURE"
    CITATION_FAILURE = "CITATION_FAILURE"
    FRESHNESS_FAILURE = "FRESHNESS_FAILURE"
    ROUTING_FAILURE = "ROUTING_FAILURE"
    CACHE_FAILURE = "CACHE_FAILURE"
    WEB_SEARCH_FAILURE = "WEB_SEARCH_FAILURE"
    LATENCY_FAILURE = "LATENCY_FAILURE"
    API_FAILURE = "API_FAILURE"
    UNKNOWN = "UNKNOWN"


class FailureRecord(BaseModel):
    question_id: str
    failure_type: FailureType
    reason: str


# ════════════════════════════════════════════════════════════════════════
# Metric Results
# ════════════════════════════════════════════════════════════════════════

class RetrievalMetrics(BaseModel):
    recall_at_1: Optional[float] = None
    recall_at_3: Optional[float] = None
    recall_at_5: Optional[float] = None
    precision_at_k: Optional[float] = None
    mrr: Optional[float] = None
    status: str = "evaluated"  # "evaluated" | "not_available"


class GenerationMetrics(BaseModel):
    answer_relevance: Optional[float] = None
    faithfulness: Optional[float] = None
    groundedness: Optional[float] = None
    hallucination_risk: Optional[float] = None
    status: str = "evaluated"


class CitationMetrics(BaseModel):
    citation_score: float = 0.0
    supported_claims: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    status: str = "evaluated"


class LatencyStats(BaseModel):
    """Latency distribution for a full evaluation run.

    Tracks:
      - Overall stats (all queries)
      - Cache HIT stats (should be <200ms)
      - Cache MISS stats (real retrieval latency)
      - Per-routing-path breakdown
    """
    # Overall (all queries)
    average_ms: Optional[float] = None
    median_ms: Optional[float] = None
    p95_ms: Optional[float] = None
    p99_ms: Optional[float] = None
    min_ms: Optional[float] = None
    max_ms: Optional[float] = None
    sample_count: int = 0

    # Cache-aware breakdown
    cache_hit_avg_ms: Optional[float] = None
    cache_hit_p95_ms: Optional[float] = None
    cache_hit_count: int = 0
    cache_miss_avg_ms: Optional[float] = None
    cache_miss_p95_ms: Optional[float] = None
    cache_miss_count: int = 0

    # Per-routing path (routing_name -> avg_ms)
    by_routing: dict[str, float] = Field(default_factory=dict)

    # Budget SLA (pass/fail per tier)
    cache_hit_sla_ok: bool = True    # all cache hits < 500ms
    fresh_query_sla_ok: bool = True  # all cache misses < 15000ms

    status: str = "evaluated"


class RoutingStats(BaseModel):
    total_queries: int = 0
    routing_distribution: dict[str, int] = Field(default_factory=dict)
    cache_hits: int = 0
    cache_misses: int = 0
    cache_hit_rate: Optional[float] = None
    unnecessary_web_searches: int = 0
    status: str = "evaluated"


# ════════════════════════════════════════════════════════════════════════
# Per-Question Evaluation Result
# ════════════════════════════════════════════════════════════════════════

class QuestionResult(BaseModel):
    """Full evaluation result for a single dataset question."""
    id: str
    question: str
    mode: str = ""
    answer: str = ""
    answered: bool = False
    latency_ms: float = 0.0
    retrieval: RetrievalMetrics = Field(default_factory=RetrievalMetrics)
    generation: GenerationMetrics = Field(default_factory=GenerationMetrics)
    citation: CitationMetrics = Field(default_factory=CitationMetrics)
    routing: str = ""
    cache_hit: bool = False
    failures: list[FailureRecord] = Field(default_factory=list)
    error: Optional[str] = None  # non-None if the question hit an API error


# ════════════════════════════════════════════════════════════════════════
# Full Evaluation Run
# ════════════════════════════════════════════════════════════════════════

class EvaluationRun(BaseModel):
    """Aggregated results for a complete dataset evaluation run."""
    run_id: str
    timestamp: str
    dataset_path: str
    total_questions: int = 0
    successful: int = 0
    failed: int = 0
    error_count: int = 0
    results: list[QuestionResult] = Field(default_factory=list)
    retrieval_summary: RetrievalMetrics = Field(default_factory=RetrievalMetrics)
    generation_summary: GenerationMetrics = Field(default_factory=GenerationMetrics)
    latency: LatencyStats = Field(default_factory=LatencyStats)
    routing: RoutingStats = Field(default_factory=RoutingStats)
    failures: list[FailureRecord] = Field(default_factory=list)


# ════════════════════════════════════════════════════════════════════════
# Comparison
# ════════════════════════════════════════════════════════════════════════

class ComparisonResult(BaseModel):
    """Side-by-side comparison of two RAG versions."""
    version_a_url: str
    version_b_url: str
    dataset_path: str
    version_a: EvaluationRun
    version_b: EvaluationRun
    summary: dict[str, Any] = Field(default_factory=dict)
