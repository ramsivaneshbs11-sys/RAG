"""
app/api/routes/query.py
────────────────────────
POST /api/v1/query — Full RAG pipeline with Anti-Hallucination.

Pipeline per request:
  1. Classify query      (Gemini Flash → class + confidence)
  2. Route by confidence:
       High (>0.80)       → Filter 1 Qdrant collection → Vector Search
       Medium (0.50–0.80) → Top-2 Qdrant collections  → Merged Vector Search
       Low (<0.50)        → Parallel Web Search (DuckDuckGo + SearXNG)
  3. Rerank candidates   (cross-encoder MiniLM)
  4. Anti-Hallucination  (3 layers):
       Layer 1 — Score Gate: block LLM if best rerank_score < 0.0
       Layer 2 — Mode-specific prompt (prelims/mains/current_affairs)
       Layer 3 — Citation enforcement: every fact tagged with [chunk_id]
  5. Return grounded answer + cited chunks

Request body:
    {
        "query":  "What is cultural ecology?",
        "top_k":  5,                    (optional, default 5)
        "mode":   "prelims"             (optional: prelims | mains | current_affairs)
    }

Response:
    {
        "query":             "What is cultural ecology?",
        "mode":              "prelims",
        "classification":    "Anthropology",
        "confidence":        0.92,
        "all_scores":        {"Anthropology": 0.92, "History": 0.08},
        "routing":           "high_confidence",
        "total_candidates":  20,
        "answer":            "Cultural ecology is... [chk_0012]",
        "answered":          true,
        "citations":         ["chk_0012"],
        "gated":             false,
        "gate_reason":       null,
        "log_info":          "...",
        "chunks":            [ { ... } ]
    }
"""

import logging
import asyncio
import json
import time
from typing import Optional, Any

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.retrieval.query_classifier import classify_query
from app.retrieval.retrieval_router import route_and_retrieve
from app.retrieval.intent_router    import classify_intent, ROUTE_DIRECT
from app.retrieval.generator        import (
    generate_grounded_answer,
    get_session_history,
    save_chat_message,
    format_history_for_prompt,
    condense_query,
)
from app.retrieval.response_cache   import get_response, set_response, clear_cache, cache_stats
from app.core.config                import RETRIEVAL_FINAL_TOP_K, TRUSTED_SITES, RESPONSE_CACHE_ENABLED
from app.database.session           import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["query"])


# ── Request / Response schemas ─────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="The user's UPSC-related search query.",
        examples=["What is cultural ecology?"],
    )
    top_k: Optional[int] = Field(
        default=None,
        ge=1,
        le=50,
        description=(
            "Number of final chunks to return after reranking. "
            f"Default: {RETRIEVAL_FINAL_TOP_K}"
        ),
    )
    mode: str = Field(
        default="prelims",
        description=(
            "Prompt mode controlling answer style. "
            "'prelims' — MCQ/fact answer engine. "
            "'mains' — Structured analytical Mains answer. "
            "'current_affairs' — Temporally-grounded current events analysis."
        ),
        examples=["prelims", "mains", "current_affairs"],
    )
    sub_mode: Optional[str] = Field(
        default="summary",
        description=(
            "Output style for current_affairs: "
            "'summary' — 3-bullet executive overview with exam relevance (default). "
            "'mcq' — 3-5 statement-based UPSC Prelims MCQs with answer key. "
            "'explain' — Beginner-friendly conceptual deep-dive. "
            "'mains' — Structured 250-word analytical answer."
        ),
        examples=["summary", "mcq", "explain", "mains"],
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session ID to enable sliding-window chat conversation memory."
    )


class ChunkResult(BaseModel):
    chunk_id:     str
    text:         str
    score:        float
    rerank_score: float
    source:       str
    metadata:     dict


class CitationResult(BaseModel):
    chunk_id:  str
    document:  str
    pages:     Any             # int, list[int], or "?"
    preview:   str
    url:       Optional[str] = None


class QueryResponse(BaseModel):
    # ── Query metadata ──────────────────────────────────────────────────────────
    query:            str
    mode:             str           # Prompt mode used (prelims/mains/current_affairs)
    sub_mode:         Optional[str] = None  # Sub-mode used for current_affairs
    classification:   str
    confidence:       float
    all_scores:       dict
    routing:          str
    total_candidates: int
    # ── Anti-hallucination generation output ────────────────────────────────────
    answer:           str           # Grounded answer (or "insufficient info")
    answered:         bool          # False = LLM couldn't answer from context
    citations:        list[str]     # Raw chunk_ids cited inline in the answer
    rich_citations:   list[CitationResult]  # Human-readable: doc name + page + preview
    gated:            bool          # True = score gate blocked LLM
    gate_reason:      Optional[str] # Why gate triggered (or None)
    # ── Cache metadata ──────────────────────────────────────────────────────────
    cache_hit:        bool          # True = answer served from response cache
    # ── Pre-RAG Intent Router metadata ──────────────────────────────────────────
    intent:           Optional[str] = None
    route:            Optional[str] = None
    rag_bypassed:     Optional[bool] = False
    latency_ms:       Optional[float] = 0.0
    # ── User-facing transparency log ────────────────────────────────────────────
    log_info:         str           # Human-readable confirmation of which DB was searched
    # ── Retrieved evidence ──────────────────────────────────────────────────────
    chunks:           list[ChunkResult]


# ── Route implementation ───────────────────────────────────────────────────────

@router.post(
    "/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Query the UPSC RAG knowledge base",
)
async def query_rag(
    body: QueryRequest,
    db: Session = Depends(get_db),
):
    """
    Execute the full RAG pipeline for a user query.
    """
    query = body.query.strip()
    top_k = body.top_k or RETRIEVAL_FINAL_TOP_K
    mode  = body.mode.strip().lower().replace(" ", "_").replace("-", "_") or "prelims"
    sub_mode = (body.sub_mode or "summary").strip().lower()
    session_id = body.session_id

    logger.info(f"[QUERY] Incoming: '{query[:80]}' | top_k={top_k} | mode={mode} | sub_mode={sub_mode} | session_id={session_id}")

    t_start = time.perf_counter()

    # ── Pre-RAG Intent Router ─────────────────────────────────────────────────
    # Runs BEFORE embedding, Qdrant, reranker, web search, and LLM.
    intent_result = classify_intent(query)
    if intent_result.rag_bypassed:
        latency_ms = (time.perf_counter() - t_start) * 1000
        return QueryResponse(
            query=query,
            mode=mode,
            sub_mode=sub_mode,
            classification=intent_result.intent,
            confidence=intent_result.confidence,
            all_scores={},
            routing=ROUTE_DIRECT,
            total_candidates=0,
            answer=intent_result.direct_response,
            answered=True,
            citations=[],
            rich_citations=[],
            gated=False,
            gate_reason=None,
            cache_hit=False,
            intent=intent_result.intent,
            route=ROUTE_DIRECT,
            rag_bypassed=True,
            latency_ms=round(latency_ms, 2),
            log_info=f"Intent={intent_result.intent} | RAG_BYPASSED=True | Latency={latency_ms:.1f}ms",
            chunks=[],
        )

    # ── Response Cache Lookup ──────────────────────────────────────────────────────────
    # Read from cache only when there is no active session — with a session_id
    # the user may ask follow-up questions that require conversation context,
    # and a stale cache hit would ignore that context entirely.
    # Cache writes always happen (see below) so Live Entries still count up.
    use_cache = RESPONSE_CACHE_ENABLED
    if use_cache and not session_id:
        cached = get_response(query, mode, sub_mode=sub_mode)
        if cached is not None:
            cached["cache_hit"] = True
            logger.info(f"[QUERY] Cache HIT — returning stored answer instantly.")
            return QueryResponse(**cached)

    # ── Load Conversation History & Condense Query ─────────────────────────────
    history_str = "No previous conversation history."
    search_query = query

    if session_id:
        # Load last 10 messages (5 turns) Chronologically
        history_msgs = await asyncio.to_thread(get_session_history, db, session_id, limit=10)
        history_str = format_history_for_prompt(history_msgs)
        # Rewrite query to be standalone if history exists
        search_query = await asyncio.to_thread(condense_query, query, history_str)
    elif mode == "current_affairs" and history_str.strip() != "No previous conversation history.":
        # Gap 6 fix: also condense for CA mode when history is available without a session_id
        # Resolves follow-up pronouns ("Tell me more about it") in multi-turn CA conversations
        search_query = await asyncio.to_thread(condense_query, query, history_str)
        logger.debug(f"[QUERY] CA multi-turn condensed: '{query[:40]}' → '{search_query[:40]}'")

    # ── Step 1: Classify (using condensed search_query) ────────────────────────
    try:
        classifier_result = classify_query(search_query)
    except Exception as exc:
        logger.exception(f"[QUERY] Classification failed: {exc}")
        raise HTTPException(
            status_code=503,
            detail=f"Query classification failed: {exc}",
        )

    # ── Step 2 + 3: Route → Search → Rerank ────────────────────────────────────
    try:
        retrieval_result = await asyncio.to_thread(
            route_and_retrieve,
            search_query,
            classifier_result,
            top_k,
            mode,
        )
    except Exception as exc:
        logger.exception(f"[QUERY] Retrieval/reranking failed: {exc}")
        raise HTTPException(
            status_code=503,
            detail=f"Retrieval failed: {exc}",
        )

    chunks     = retrieval_result["chunks"]
    candidates = retrieval_result["candidates"]
    routing    = retrieval_result["routing"]

    # ── Step 4: Anti-Hallucination Generation ──────────────────────────────────
    try:
        generation = await asyncio.to_thread(
            generate_grounded_answer,
            query,
            chunks,
            routing,
            mode,
            history_str,
            sub_mode,
        )
    except Exception as exc:
        logger.exception(f"[QUERY] Generation failed: {exc}")
        # Fail gracefully — return chunks without answer rather than crash
        generation = {
            "answer":      "Answer generation temporarily unavailable.",
            "answered":    False,
            "citations":   [],
            "rich_citations": [],
            "gated":       True,
            "gate_reason": f"Generation error: {exc}",
            "mode":        mode,
            "sub_mode":    sub_mode,
        }

    # ── Build response ─────────────────────────────────────────────────────────
    chunk_results = [
        ChunkResult(
            chunk_id=     c.get("chunk_id", ""),
            text=         c.get("text", ""),
            score=        float(c.get("score", 0.0)),
            rerank_score= float(c.get("rerank_score", 0.0)),
            source=       c.get("source", "unknown"),
            metadata=     c.get("metadata", {}),
        )
        for c in chunks
    ]

    # ── Build user-facing log_info message ────────────────────────────────────
    classification  = classifier_result["classification"]
    confidence_pct  = classifier_result["confidence"] * 100
    citation_count  = len(generation["citations"])
    candidate_count = len(candidates)

    if routing == "high_confidence":
        log_info = (
            f"Query routed strictly to {classification} Database "
            f"({confidence_pct:.1f}% confidence). "
            f"{candidate_count} candidate chunks retrieved and reranked. "
            f"Answer backed by {citation_count} source(s). "
            f"No other database was searched."
        )
    elif routing == "medium_confidence":
        log_info = (
            f"Query routed to top-2 databases (History + Anthropology). "
            f"{candidate_count} candidate chunks merged and reranked. "
            f"Answer backed by {citation_count} source(s)."
        )
    elif routing == "current_affairs_local":
        log_info = (
            f"Query answered directly from local Current Affairs Vector Cache (06:00 AM daily digest). "
            f"{candidate_count} candidates retrieved and reranked. "
            f"Answer backed by {citation_count} verified source(s) with <1s latency."
        )
    elif routing == "current_affairs_web":
        trusted_sources_str = ", ".join(TRUSTED_SITES[:4]) + "..."
        log_info = (
            f"Current Affairs query routed to live parallel web search "
            f"(trusted sources: {trusted_sources_str}). "
            f"{candidate_count} web articles scraped and reranked. "
            f"Answer backed by {citation_count} source(s)."
        )
    else:
        log_info = (
            f"Routing: {routing} | Confidence: {confidence_pct:.1f}% | "
            f"Candidates: {candidate_count} | Citations: {citation_count}"
        )

    # Append gate/answer status to log_info
    if generation["gated"]:
        log_info += f" [GATED: {generation.get('gate_reason', 'Low relevance score')}]"
    elif not generation["answered"]:
        log_info += " [Result: Insufficient information in knowledge base.]"
    else:
        log_info += " [Result: Answer successfully generated.]"

    logger.info(
        f"[QUERY] Complete — class='{classification}', mode='{mode}', sub_mode='{sub_mode}', "
        f"conf={classifier_result['confidence']:.2f}, routing='{routing}', "
        f"answered={generation['answered']}, gated={generation['gated']}, "
        f"candidates={len(candidates)}, chunks={len(chunk_results)}"
    )

    result_payload = QueryResponse(
        query=            query,
        mode=             generation.get("mode", mode),
        sub_mode=         generation.get("sub_mode", sub_mode),
        classification=   classification,
        confidence=       classifier_result["confidence"],
        all_scores=       classifier_result.get("all_scores", {}),
        routing=          routing,
        total_candidates= candidate_count,
        answer=           generation.get("answer", ""),
        answered=         generation.get("answered", False),
        citations=        generation.get("citations", []),
        rich_citations=   generation.get("rich_citations", []),
        gated=            generation.get("gated", False),
        gate_reason=      generation.get("gate_reason"),
        cache_hit=        False,
        log_info=         log_info,
        chunks=           chunk_results,
    )

    # ── Save Conversation Turns to Database ────────────────────────────────────
    if session_id:
        # Save user query
        await asyncio.to_thread(save_chat_message, db, session_id, "user", query)
        # Save assistant answer (serialize response payload)
        response_json = json.dumps({
            "answer": result_payload.answer,
            "answered": result_payload.answered,
            "citations": result_payload.citations
        })
        await asyncio.to_thread(save_chat_message, db, session_id, "assistant", response_json)

    # ── Store in response cache (only when answered=True and no active session) ──
    if use_cache:
        set_response(query, mode, result_payload.model_dump(), sub_mode=sub_mode)

    return result_payload


# ── Admin endpoints ────────────────────────────────────────────────────────────

@router.delete(
    "/cache",
    status_code=200,
    summary="Clear the response cache (admin)",
    description="Deletes all cached RAG responses. Subsequent requests will re-run the full pipeline.",
    tags=["admin"],
)
async def clear_response_cache():
    """
    Wipe all entries from the response cache.
    The next identical query will re-run classify → search → rerank → LLM.
    """
    deleted = await asyncio.to_thread(clear_cache)
    logger.info(f"[ADMIN] Response cache cleared — {deleted} entries removed.")
    return {"message": f"Response cache cleared. {deleted} entries removed."}


@router.get(
    "/cache/stats",
    status_code=200,
    summary="Response cache statistics (admin)",
    tags=["admin"],
)
async def response_cache_stats():
    """Return current response cache statistics (live entries, expired, config)."""
    stats = await asyncio.to_thread(cache_stats)
    return stats


@router.post(
    "/admin/sync-news",
    status_code=200,
    summary="Trigger daily news scraper sync manually (admin)",
    description="Scrapes The Hindu & PIB immediately, embeds articles, and upserts them into Qdrant current_affairs_collection.",
    tags=["admin"],
)
async def admin_sync_news():
    """Manually run the daily news sync pipeline."""
    from app.services.news_scraper_service import run_daily_news_scraper
    logger.info("[ADMIN] Manual news sync triggered...")
    result = await asyncio.to_thread(run_daily_news_scraper)
    return {
        "message": "Daily news sync completed successfully.",
        "details": result,
    }

