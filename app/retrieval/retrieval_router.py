"""
app/retrieval/retrieval_router.py
──────────────────────────────────
Confidence-based retrieval router.

Routes the retrieval strategy based on the classifier confidence score:

    High   (> 0.80) → Filter to 1 collection  → Vector Search
    Medium (0.50–0.80) → Search Top-2 collections → Merge Results
    Low    (< 0.50)  → Global Retrieval (DuckDuckGo web search)

All paths feed into the cross-encoder Reranker → Top-K chunks.

Public API:
    route_and_retrieve(query, classifier_result, top_k) -> dict
"""

import logging
from typing import Any

from app.core.config import (
    QDRANT_COLLECTION_MAP,
    CA_NEWS_COLLECTION,
    HIGH_CONFIDENCE_THRESHOLD,
    LOW_CONFIDENCE_THRESHOLD,
    RETRIEVAL_CANDIDATE_K,
    RETRIEVAL_FINAL_TOP_K,
    PREPROCESSED_DIR,
)
from app.retrieval.vector_search    import search_collections
from app.retrieval.search_pipeline  import parallel_search
from app.retrieval.reranker         import rerank
from app.retrieval.sibling_expansion import expand_with_siblings

logger = logging.getLogger(__name__)


def _top_n_collections(all_scores: dict[str, float], n: int) -> list[str]:
    """
    Return the Qdrant collection names for the top-N scoring classes.

    Args:
        all_scores: {class_name: confidence_score} dict from the classifier.
        n:          Number of top classes to pick.

    Returns:
        List of Qdrant collection name strings (from QDRANT_COLLECTION_MAP).
        Skips any class that has no mapped collection.
    """
    sorted_classes = sorted(all_scores.items(), key=lambda x: x[1], reverse=True)
    collections    = []
    for cls, _ in sorted_classes[:n]:
        col = QDRANT_COLLECTION_MAP.get(cls)
        if col:
            collections.append(col)
    return collections


def route_and_retrieve(
    query:             str,
    classifier_result: dict[str, Any],
    top_k:             int | None = None,
    mode:              str = "prelims",
) -> dict[str, Any]:
    """
    Route the query to the correct retrieval strategy and return reranked chunks.

    Args:
        query:             The user's original query text.
        classifier_result: Output of query_classifier.classify_query().
        top_k:             Final number of chunks to return (default: RETRIEVAL_FINAL_TOP_K).
        mode:              Prompt mode passed through to the generator
                           ("prelims" | "mains" | "current_affairs").

    Returns:
        dict with:
            routing    (str)       — "high_confidence" / "medium_confidence" / "low_confidence" / "current_affairs_local" / "current_affairs_web"
            candidates (list[dict])— raw candidates before reranking
            chunks     (list[dict])— top-K reranked chunks
            mode       (str)       — prompt mode forwarded from caller
    """
    # ── Auto-detect Current Affairs Intent ──────────────────────────────────
    # If user asks about news/today/headlines/current affairs, force current_affairs mode
    # even if the UI dropdown is left on "prelims"
    query_lower = query.lower()
    ca_keywords = [
        "today news", "today's news", "news today", "daily news",
        "current affairs", "latest news", "today headlines", "today's headlines",
        "current news", "news summary", "news briefing", "today brief",
        "what is today news", "tell me today news", "whats today news",
        "news pathi", "today news pathi", "daily news update"
    ]
    if any(kw in query_lower for kw in ca_keywords):
        if mode != "current_affairs":
            logger.info(
                f"Router: Auto-detected Current Affairs intent in query '{query}' → Overriding mode '{mode}' to 'current_affairs'"
            )
            mode = "current_affairs"

    # ── Dynamic mode-specific top_k ──────────────────────────────────────────
    # Prelims  → 5 chunks  (sharp factual precision, fastest)
    # Current Affairs → 8 chunks  (multi-source web/local coverage)
    # Mains    → 10 chunks (broad analytical context for multi-dimensional answers)
    if top_k is None:
        if mode == "mains":
            top_k = 10
        elif mode == "current_affairs":
            top_k = 8
        else:  # prelims (default)
            top_k = RETRIEVAL_FINAL_TOP_K

    # ── Current Affairs Mode: Local Qdrant First → Rerank-Gated Web Fallback ───
    if mode == "current_affairs":
        logger.info(
            f"Router: mode='current_affairs' → Checking local '{CA_NEWS_COLLECTION}' first..."
        )
        candidates = []
        routing = "current_affairs_web"

        # 1. Try pre-scraped daily news collection in local Qdrant
        try:
            local_candidates = search_collections(
                query=query,
                collection_names=[CA_NEWS_COLLECTION],
                top_k=RETRIEVAL_CANDIDATE_K * 2,
            )
            # Accuracy fix: lower threshold 0.40→0.30 for broad news queries
            is_broad = any(kw in query_lower for kw in ["today news", "daily news", "news today", "today's news", "current affairs", "latest news"])
            threshold = 0.30 if is_broad else 0.40
            high_score_count = sum(1 for c in local_candidates if c.get("score", 0.0) >= threshold)
            if local_candidates and (high_score_count >= 1 or is_broad):
                candidates = local_candidates
                routing = "current_affairs_local"
                best_score = max(c.get("score", 0.0) for c in candidates)
                logger.info(
                    f"Router: [current_affairs] Found {len(candidates)} candidates in local Qdrant "
                    f"(best score: {best_score:.3f}, qualifying: {high_score_count}) ✓"
                )
        except Exception as exc:
            logger.warning(f"Router: Error querying local CA collection: {exc}")

        # 2. If not found in local news collection, fallback to live web search (Tavily+Serper)
        if not candidates:
            logger.info(
                "Router: [current_affairs] Not in local cache. Running web search (Tavily+Serper)..."
            )
            candidates = parallel_search(user_query=query)
            routing = "current_affairs_web"

        # 3. Rerank whatever we have
        top_chunks = rerank(query=query, candidates=candidates, top_k=top_k)

        # 4. Rerank-score gate: if local chunks are too weak (all scores < 0.0),
        #    the LLM will reject them anyway. Proactively run web search (Tavily+Serper)
        #    so the user gets a real answer instead of "insufficient info".
        if routing == "current_affairs_local":
            best_rerank = max((c.get("rerank_score", -999) for c in top_chunks), default=-999)
            if best_rerank < 0.0:
                logger.info(
                    f"Router: [current_affairs] Local rerank score too low ({best_rerank:.3f} < 0.0). "
                    "Triggering Tavily+Serper web search fallback..."
                )
                web_candidates = parallel_search(user_query=query)
                if web_candidates:
                    web_chunks = rerank(query=query, candidates=web_candidates, top_k=top_k)
                    web_best = max((c.get("rerank_score", -999) for c in web_chunks), default=-999)
                    if web_best > best_rerank:
                        logger.info(
                            f"Router: [current_affairs] Web search improved score "
                            f"{best_rerank:.3f} → {web_best:.3f}. Using web chunks ✓"
                        )
                        top_chunks = web_chunks
                        candidates = web_candidates
                        routing = "current_affairs_web_fallback"
                    else:
                        logger.info(
                            f"Router: [current_affairs] Web search did not improve score "
                            f"({web_best:.3f}). Keeping local chunks."
                        )

        top_chunks = expand_with_siblings(top_chunks, PREPROCESSED_DIR)

        logger.info(
            f"Router: [current_affairs] routing='{routing}', candidates={len(candidates)}, top_k={len(top_chunks)}"
        )
        return {
            "routing":    routing,
            "candidates": candidates,
            "chunks":     top_chunks,
            "mode":       mode,
        }

    confidence  = classifier_result["confidence"]
    all_scores  = classifier_result.get("all_scores", {})
    top_class   = classifier_result["classification"]

    # ── Route: High Confidence ─────────────────────────────────────────────────
    if confidence >= HIGH_CONFIDENCE_THRESHOLD:
        routing     = "high_confidence"
        collections = _top_n_collections(all_scores, n=1)

        logger.info(
            f"Router: HIGH confidence ({confidence:.2f}) → "
            f"Single collection: {collections}"
        )

        candidates = search_collections(
            query=query,
            collection_names=collections,
            top_k=RETRIEVAL_CANDIDATE_K,
        )


    # ── Route: Medium Confidence ───────────────────────────────────────────────
    elif confidence >= LOW_CONFIDENCE_THRESHOLD:
        routing     = "medium_confidence"
        collections = _top_n_collections(all_scores, n=2)

        logger.info(
            f"Router: MEDIUM confidence ({confidence:.2f}) → "
            f"Top-2 collections: {collections}"
        )

        candidates = search_collections(
            query=query,
            collection_names=collections,
            top_k=RETRIEVAL_CANDIDATE_K,
        )

    # ── Route: Low Confidence — Check Local Collections First, then Web ────────
    else:
        routing = "low_confidence_local"
        all_collections = list(QDRANT_COLLECTION_MAP.values())
        logger.info(
            f"Router: LOW confidence ({confidence:.2f}) → "
            f"Searching all local collections first: {all_collections}"
        )
        candidates = search_collections(
            query=query,
            collection_names=all_collections,
            top_k=RETRIEVAL_CANDIDATE_K,
        )

        # If local collections returned candidates, test them with reranker
        if candidates:
            top_chunks = rerank(query=query, candidates=candidates, top_k=top_k)
            best_local_score = max((c.get("rerank_score", -999) for c in top_chunks), default=-999)
            if best_local_score >= 0.0:
                logger.info(f"Router: Low confidence local search found relevant match (score: {best_local_score:.3f})")
            else:
                logger.info(f"Router: Local collections score too low ({best_local_score:.3f}). Trying web search fallback...")
                web_candidates = parallel_search(user_query=query)
                if web_candidates:
                    web_chunks = rerank(query=query, candidates=web_candidates, top_k=top_k)
                    web_best = max((c.get("rerank_score", -999) for c in web_chunks), default=-999)
                    if web_best > best_local_score:
                        candidates = web_candidates
                        top_chunks = web_chunks
                        routing = "low_confidence_web"
        else:
            logger.info("Router: No local candidates found. Running parallel web search...")
            candidates = parallel_search(user_query=query)
            top_chunks = rerank(query=query, candidates=candidates, top_k=top_k)
            routing = "low_confidence_web"

    # ── Rerank candidates → Top-K (for high/medium routes) ────────────────────
    if routing in ("high_confidence", "medium_confidence"):
        top_chunks = rerank(
            query=query,
            candidates=candidates,
            top_k=top_k,
        )

    # ── Cross-Collection Fallback ─────────────────────────────────────────────
    # If high/medium confidence routing returns all-negative rerank scores
    # (i.e. the classifier misrouted the query), retry with ALL collections
    # before triggering the score gate. This handles edge cases where a topic
    # belongs to a different collection than the classifier predicted.
    # Example: "Systema Naturae" → classified as History, but exists in Anthropology.
    FALLBACK_THRESHOLD = 0.0
    if routing in ("high_confidence", "medium_confidence"):
        best_score = max((c.get("rerank_score", -999) for c in top_chunks), default=-999)
        if best_score < FALLBACK_THRESHOLD:
            all_collections = list(QDRANT_COLLECTION_MAP.values())
            searched = set(collections)
            remaining = [c for c in all_collections if c not in searched]
            if remaining:
                logger.info(
                    f"Router: Cross-collection fallback — best score={best_score:.3f} < {FALLBACK_THRESHOLD}. "
                    f"Searching remaining collections: {remaining}"
                )
                fallback_candidates = search_collections(
                    query=query,
                    collection_names=remaining,
                    top_k=RETRIEVAL_CANDIDATE_K,
                )
                if fallback_candidates:
                    fallback_chunks = rerank(
                        query=query,
                        candidates=fallback_candidates,
                        top_k=top_k,
                    )
                    fallback_best = max(
                        (c.get("rerank_score", -999) for c in fallback_chunks), default=-999
                    )
                    if fallback_best > best_score:
                        logger.info(
                            f"Router: Fallback improved score {best_score:.3f} → {fallback_best:.3f}. "
                            f"Using fallback chunks."
                        )
                        top_chunks = fallback_chunks
                        candidates = fallback_candidates
                        routing = f"{routing}_cross_collection_fallback"

    # ── Sibling Expansion: inject next consecutive sub-chunk if split ───────────
    top_chunks = expand_with_siblings(top_chunks, PREPROCESSED_DIR)

    logger.info(
        f"Router: Retrieval complete — routing='{routing}', "
        f"candidates={len(candidates)}, top_k={len(top_chunks)}, mode='{mode}'"
    )

    return {
        "routing":    routing,
        "candidates": candidates,
        "chunks":     top_chunks,
        "mode":       mode,
    }
