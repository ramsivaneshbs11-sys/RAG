"""
app/api/routes/query_stream.py
──────────────────────────────
POST /api/v1/query/stream — Server-Sent Events (SSE) streaming RAG pipeline.

Streams pipeline progress events to the client in real-time so the UI can
show "Searching…", "Analysing articles…", "Generating answer…" stages instead
of a blank loading screen.

Event format (text/event-stream):
    data: {"type": "progress", "stage": "searching",   "message": "🔍 Searching trusted sources..."}
    data: {"type": "progress", "stage": "scraping",    "message": "📄 Analysing 6 articles..."}
    data: {"type": "progress", "stage": "reranking",   "message": "⚡ Ranking relevant chunks..."}
    data: {"type": "progress", "stage": "generating",  "message": "✍️ Generating grounded answer..."}
    data: {"type": "result",   "payload": { ...full QueryResponse dict... }}
    data: {"type": "done"}
"""

import json
import logging
import asyncio
import time
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.retrieval.query_classifier     import classify_query
from app.retrieval.retrieval_router     import route_and_retrieve
from app.retrieval.intent_router        import classify_intent, GREETING, CASUAL, OUT_OF_SCOPE, ROUTE_DIRECT
from app.retrieval.generator            import (
    generate_grounded_answer,
    get_session_history,
    save_chat_message,
    format_history_for_prompt,
    condense_query,
)
from app.retrieval.response_cache       import get_response, set_response
from app.core.config                    import RETRIEVAL_FINAL_TOP_K, TRUSTED_SITES, RESPONSE_CACHE_ENABLED
from app.database.session               import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["query-stream"])


# ── Request schema (same as QueryRequest) ─────────────────────────────────────

class StreamQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: Optional[int] = Field(default=None, ge=1, le=50)
    mode: str = Field(default="prelims")
    sub_mode: Optional[str] = Field(default="summary")
    session_id: Optional[str] = Field(default=None)


# ── SSE helpers ───────────────────────────────────────────────────────────────

def _sse(payload: dict) -> str:
    """Format a dict as a single SSE data line."""
    return f"data: {json.dumps(payload)}\n\n"


def _progress(stage: str, message: str) -> str:
    return _sse({"type": "progress", "stage": stage, "message": message})


# ── Streaming generator ───────────────────────────────────────────────────────

async def _stream_pipeline(
    query: str,
    top_k: Optional[int],
    mode: str,
    sub_mode: str = "summary",
    session_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> AsyncGenerator[str, None]:
    """
    Run the full RAG pipeline and yield SSE events at each stage boundary.
    All blocking calls (search, rerank, LLM) are offloaded to asyncio.to_thread
    so the event loop is never blocked and SSE events are delivered immediately.
    """

    t_start = time.perf_counter()

    # ── Pre-RAG Intent Router ─────────────────────────────────────────────────
    # Runs BEFORE embedding, Qdrant, reranker, web search, and LLM.
    # Greetings and casual queries are answered instantly from static templates.
    intent_result = classify_intent(query)
    if intent_result.rag_bypassed:
        latency_ms = (time.perf_counter() - t_start) * 1000
        yield _progress("intent", f"👋 Detected {intent_result.intent} — responding directly...")
        yield _sse({
            "type": "result",
            "payload": {
                "query":            query,
                "mode":             mode,
                "sub_mode":         sub_mode,
                "classification":   intent_result.intent,
                "confidence":       intent_result.confidence,
                "all_scores":       {},
                "routing":          ROUTE_DIRECT,
                "total_candidates": 0,
                "answer":           intent_result.direct_response,
                "answered":         True,
                "citations":        [],
                "rich_citations":   [],
                "gated":            False,
                "gate_reason":      None,
                "cache_hit":        False,
                "intent":           intent_result.intent,
                "route":            ROUTE_DIRECT,
                "rag_bypassed":     True,
                "latency_ms":       round(latency_ms, 2),
                "log_info":         f"Intent={intent_result.intent} | RAG_BYPASSED=True | Latency={latency_ms:.1f}ms",
                "chunks":           [],
            },
        })
        yield _sse({"type": "done"})
        return

    # ── Cache Fast-Path ───────────────────────────────────────────────────────
    # Read from cache ONLY when there is no active session.
    # With a session_id, the user may be asking follow-up questions like
    # "tell me more" that depend on conversation history — returning a stale
    # cache hit would completely ignore that context and give a wrong answer.
    # We still WRITE to cache after generation (see below) so Live Entries grow.
    use_cache = RESPONSE_CACHE_ENABLED
    if use_cache and not session_id:
        cached = await asyncio.to_thread(get_response, query, mode, sub_mode=sub_mode)
        if cached is not None:
            cached["cache_hit"] = True
            cached.setdefault("intent", "KNOWLEDGE")
            cached.setdefault("route", "RAG")
            cached.setdefault("rag_bypassed", False)
            cached.setdefault("latency_ms", 0.0)
            logger.info(f"[STREAM] Cache HIT — short-circuiting pipeline for: '{query[:60]}'")
            yield _progress("cache", "⚡ Serving answer from cache instantly...")
            yield _sse({"type": "result", "payload": cached})
            yield _sse({"type": "done"})
            return

    # ── Stage 0: Load History & Condense Query ────────────────────────────────
    history_str = "No previous conversation history."
    search_query = query

    if session_id and db is not None:
        history_msgs = await asyncio.to_thread(get_session_history, db, session_id, limit=10)
        history_str = format_history_for_prompt(history_msgs)
        # Only condense if there is actual history (skip extra Gemini call on first-turn)
        if history_str and history_str != "No previous conversation history.":
            search_query = await asyncio.to_thread(condense_query, query, history_str)

    # ── Stage 1: Classify Query ───────────────────────────────────────────────
    yield _progress("classifying", "🏷️ Classifying query intent & syllabus scope...")
    try:
        classifier_result = await asyncio.to_thread(classify_query, search_query)
    except Exception as exc:
        logger.exception(f"[STREAM] Classification failed: {exc}")
        yield _sse({"type": "error", "message": f"Query classification failed: {exc}"})
        yield _sse({"type": "done"})
        return

    # ── Stage 2: Route & Search ───────────────────────────────────────────────
    routing_msg = "🔍 Searching relevant knowledge base..."
    if mode == "current_affairs":
        routing_msg = "🌐 Searching current affairs collection & trusted sources..."
    elif classifier_result.get("confidence", 0) >= 0.80:
        routing_msg = f"📚 Searching {classifier_result.get('classification', 'UPSC')} collection in Qdrant..."
    yield _progress("searching", routing_msg)

    try:
        retrieval_result = await asyncio.to_thread(
            route_and_retrieve,
            search_query,
            classifier_result,
            top_k,
            mode,
        )
    except Exception as exc:
        logger.exception(f"[STREAM] Retrieval failed: {exc}")
        yield _sse({"type": "error", "message": f"Retrieval failed: {exc}"})
        yield _sse({"type": "done"})
        return

    chunks     = retrieval_result["chunks"]
    candidates = retrieval_result["candidates"]
    routing    = retrieval_result["routing"]

    # ── Stage 3: Reranking Progress ───────────────────────────────────────────
    yield _progress(
        "reranking",
        f"⚡ Scored {len(candidates)} candidates → top {len(chunks)} high-relevance chunks selected."
    )

    # ── Stage 4: Generation ───────────────────────────────────────────────────
    yield _progress("generating", "✍️ Synthesizing grounded answer with citations...")
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
        logger.exception(f"[STREAM] Generation failed: {exc}")
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

    # ── Build final result payload ─────────────────────────────────────────────
    classification  = classifier_result.get("classification", "unknown")
    confidence      = classifier_result.get("confidence", 0.0)
    confidence_pct  = confidence * 100
    citation_count  = len(generation.get("citations", []))
    candidate_count = len(candidates)

    if routing == "current_affairs_local":
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
    elif routing == "high_confidence":
        log_info = (
            f"Routed to {classification} Database ({confidence_pct:.1f}% confidence). "
            f"{candidate_count} candidates reranked. "
            f"Answer backed by {citation_count} source(s)."
        )
    else:
        log_info = (
            f"Routing: {routing} | Confidence: {confidence_pct:.1f}% | "
            f"Candidates: {candidate_count} | Citations: {citation_count}"
        )

    if generation.get("gated"):
        log_info += f" [GATED: {generation.get('gate_reason', 'Low relevance score')}]"
    elif not generation.get("answered"):
        log_info += " [Result: Insufficient information in knowledge base.]"
    else:
        log_info += " [Result: Answer successfully generated.]"

    latency_ms = (time.perf_counter() - t_start) * 1000
    result_payload = {
        "query":            query,
        "mode":             generation.get("mode", mode),
        "sub_mode":         generation.get("sub_mode", sub_mode),
        "classification":   classification,
        "confidence":       confidence,
        "all_scores":       classifier_result.get("all_scores", {}),
        "routing":          routing,
        "total_candidates": candidate_count,
        "answer":           generation.get("answer", ""),
        "answered":         generation.get("answered", False),
        "citations":        generation.get("citations", []),
        "rich_citations":   generation.get("rich_citations", []),
        "gated":            generation.get("gated", False),
        "gate_reason":      generation.get("gate_reason"),
        "cache_hit":        False,
        "intent":           intent_result.intent,
        "route":            routing,
        "rag_bypassed":     False,
        "latency_ms":       round(latency_ms, 2),
        "log_info":         log_info,
        "chunks": [
            {
                "chunk_id":     c.get("chunk_id", ""),
                "text":         c.get("text", ""),
                "score":        float(c.get("score", 0.0)),
                "rerank_score": float(c.get("rerank_score", 0.0)),
                "source":       c.get("source", "unknown"),
                "metadata":     c.get("metadata", {}),
            }
            for c in chunks
        ],
    }

    yield _sse({"type": "result", "payload": result_payload})

    # ── Save Conversation Turns to Database ────────────────────────────────────
    if session_id and db is not None:
        await asyncio.to_thread(save_chat_message, db, session_id, "user", query)
        response_json = json.dumps({
            "answer": result_payload["answer"],
            "answered": result_payload["answered"],
            "citations": result_payload["citations"]
        })
        await asyncio.to_thread(save_chat_message, db, session_id, "assistant", response_json)

    # ── Write to response cache (always when enabled and answer was generated) ──
    # Writing regardless of session_id means future standalone queries for the
    # same question get instant cache hits, and Live Entries count up correctly.
    if use_cache:
        await asyncio.to_thread(set_response, query, mode, result_payload, sub_mode=sub_mode)

    yield _sse({"type": "done"})
    logger.info(
        f"[STREAM] Complete — mode={mode}, routing={routing}, "
        f"answered={generation.get('answered')}, chunks={len(chunks)}"
    )


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post(
    "/query/stream",
    summary="Streaming RAG query with real-time progress events (SSE)",
    description=(
        "Same as `/api/v1/query` but streams Server-Sent Events (SSE) at each "
        "pipeline stage so the UI can show live progress instead of a blank screen.\n\n"
        "Event types:\n"
        "- `progress` — stage label + human-readable message\n"
        "- `result`   — full answer payload (same schema as QueryResponse)\n"
        "- `error`    — pipeline error message\n"
        "- `done`     — stream complete signal"
    ),
    response_class=StreamingResponse,
)
async def stream_query(
    body: StreamQueryRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    query = body.query.strip()
    top_k = body.top_k
    mode  = body.mode.strip().lower().replace(" ", "_").replace("-", "_") or "prelims"
    sub_mode = (body.sub_mode or "summary").strip().lower()
    session_id = body.session_id

    logger.info(f"[STREAM] Incoming: '{query[:80]}' | top_k={top_k} | mode={mode} | sub_mode={sub_mode} | session_id={session_id}")

    return StreamingResponse(
        _stream_pipeline(query, top_k, mode, sub_mode, session_id, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control":  "no-cache",
            "X-Accel-Buffering": "no",      # Disable nginx buffering for SSE
            "Connection":     "keep-alive",
        },
    )

