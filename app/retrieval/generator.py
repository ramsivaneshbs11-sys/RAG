"""
app/retrieval/generator.py
───────────────────────────
Anti-Hallucination LLM Answer Generator.

Implements 3 layers of hallucination prevention:

  Layer 1 — Score Gate:
      If the best rerank_score is below RERANK_SCORE_THRESHOLD, the LLM is
      NOT called. Returns a fixed "insufficient information" response instead
      of risking a hallucinated answer.

  Layer 2 — Strict Context-Only System Prompt:
      A mode-specific prompt is selected via prompts.get_prompt(mode).
      Three modes are supported: prelims, mains, current_affairs.
      All prompts forbid outside knowledge and enforce citation.

  Layer 3 — Citation Enforcement:
      The model must tag every fact with [chunk_id] inline. The response
      includes a "citations" list so the caller can trace every claim back
      to the original source document and page.

Public API:
    generate_grounded_answer(query, chunks, source, mode) -> dict
"""

import json
import logging
import re
import requests
import google.genai as genai
import google.genai.types as genai_types

from app.core.config import GEMINI_API_KEY, GEMINI_MODEL, GROQ_API_KEY, GROQ_MODEL
from app.retrieval.prompts  import get_prompt, detect_query_intent_and_constraints
from app.retrieval.metrics  import timer as metrics_timer
from app.database.models import ChatMessage

logger = logging.getLogger(__name__)

# ── Configurable thresholds ────────────────────────────────────────────────────
# Minimum rerank_score for the best chunk to trigger LLM generation.
# cross-encoder/ms-marco-MiniLM-L-6-v2 typically returns scores in [-10, +10].
# A score < 0.0 means the cross-encoder found the chunk largely irrelevant.
RERANK_SCORE_THRESHOLD: float = 0.0

# Current Affairs uses a lower threshold because the ms-marco cross-encoder
# was trained on web-search pairs and scores news-style short text harshly.
# Scores of -3 to -7 are common for valid CA news chunks — do not gate them.
CA_RERANK_SCORE_THRESHOLD: float = -5.0

# ── Pre-compiled answer cleanup regexes (compiled once at import, reused per request) ──
_RE_CHK_PARENS  = re.compile(r'\((?:chk_\w+[\s,]*)+\)')   # (chk_001, chk_002)
_RE_CHK_BRACKETS = re.compile(r'\[(?:chk_\w+[\s,]*)+\]')  # [chk_001, chk_002]
_RE_CHK_BARE     = re.compile(r'chk_\w+')                   # bare chk_xxx leftovers
_RE_EMPTY_PARENS = re.compile(r'\(\s*,?\s*\)')              # empty parens ( )
_RE_PUNCT_SPACE  = re.compile(r'\s+([.,;:!?])')              # 'press .' -> 'press.'
_RE_MULTI_SPACE  = re.compile(r'  +')                        # double spaces
_RE_MULTI_NL     = re.compile(r'\n{3,}')                     # 3+ newlines -> 2


# ── Prompt selection is now handled by app/retrieval/prompts.py ───────────────
# Use generate_grounded_answer(..., mode="prelims"|"mains"|"current_affairs")
# to choose the appropriate system prompt. The default is "prelims".
def _sort_chunks_for_prompt(chunks: list[dict]) -> list[dict]:
    """
    Sort chunks so that sibling chunks from the same document appear in
    consecutive document reading order (by file_name and numeric chunk index)
    before being passed to the LLM.
    """
    def _sort_key(c):
        file_name = c.get("metadata", {}).get("file_name", "")
        chunk_id = c.get("chunk_id", "")
        try:
            _, num_str = chunk_id.rsplit("_", 1)
            num = int(num_str)
        except Exception:
            num = 9999
        return (file_name, num)

    return sorted(chunks, key=_sort_key)


def _clean_chunk_text(text: str) -> str:
    """Strip excessive whitespace/newlines from chunk text before building prompt.
    Reduces prompt token count by 20-30% for chunk-heavy context blocks."""
    # Collapse multiple blank lines to one
    text = _RE_MULTI_NL.sub('\n\n', text)
    # Collapse multiple spaces
    text = _RE_MULTI_SPACE.sub(' ', text)
    return text.strip()


def _build_context_block(chunks: list[dict]) -> str:
    """
    Format retrieved chunks into a numbered context block for the prompt.
    Each chunk is labelled with its chunk_id so the LLM can cite it.
    Text is pre-cleaned to reduce prompt token count.
    """
    sorted_chunks = _sort_chunks_for_prompt(chunks)
    lines = []
    for i, chunk in enumerate(sorted_chunks, 1):
        chunk_id = chunk.get("chunk_id", f"chunk_{i}")
        text     = _clean_chunk_text(chunk.get("text", ""))
        source   = chunk.get("source", "qdrant")
        meta     = chunk.get("metadata", {})
        page     = meta.get("page_num", meta.get("page", "?"))

        lines.append(
            f"[{chunk_id}] (source={source}, page={page})\n{text}"
        )
    return "\n\n---\n\n".join(lines)


def format_citations(citations: list[str], chunks: list[dict]) -> list[dict]:
    """
    Convert a list of raw chunk_ids into human-readable citation objects.
    Queries the PostgreSQL documents table to map UUID file names back to
    original uploaded filenames.

    Each citation object contains:
        chunk_id   (str)  — original chunk reference ID
        document   (str)  — original PDF filename (e.g. "Brain Tree VOL-1.pdf")
        pages      (any)  — page number(s) where the fact was found
        preview    (str)  — first 150 characters of the source passage

    Args:
        citations: List of chunk_id strings returned by the LLM.
        chunks:    The reranked chunks that were sent to the LLM.

    Returns:
        List of human-readable citation dicts.
    """
    chunk_map = {c.get("chunk_id", ""): c for c in chunks}
    
    # Pre-fetch original filenames from the PostgreSQL database
    file_ids = {c.get("file_id") for c in chunks if c.get("file_id")}
    file_id_to_name = {}
    if file_ids:
        try:
            from sqlalchemy import text
            from app.database.session import SessionLocal
            with SessionLocal() as db:
                query_str = text("SELECT id, original_filename FROM documents WHERE id IN :ids")
                rows = db.execute(query_str, {"ids": tuple(file_ids)}).fetchall()
                file_id_to_name = {r[0]: r[1] for r in rows}
        except Exception as e:
            logger.error(f"[Generator] Failed to fetch original filenames from DB: {e}")

    result = []
    for cid in citations:
        chunk = chunk_map.get(cid, {})
        meta  = chunk.get("metadata", {})
        file_id = chunk.get("file_id")

        # Resolve document name from DB lookup, falling back to metadata filenames
        doc_name = file_id_to_name.get(file_id) if file_id else None
        if not doc_name:
            doc_name = meta.get("file_name") or meta.get("document", "Unknown Source")

        page_val = meta.get("page_num", meta.get("page", None))
        pages_out = [page_val] if isinstance(page_val, int) else (page_val if isinstance(page_val, list) else None)
        text_snippet = chunk.get("text", "")
        preview = text_snippet[:150].strip() + ("..." if len(text_snippet) > 150 else "")

        # For web-sourced chunks (Tavily/Serper), URL is stored in metadata
        url = meta.get("url") or meta.get("source_url") or None

        result.append({
            "chunk_id": cid,
            "document": doc_name,
            "pages":    pages_out,
            "preview":  preview,
            "url":      url,
        })
    return result


def _call_groq(prompt: str, mode: str = "prelims", max_tokens: int | None = None) -> str:
    """
    Call the Groq API with the given prompt.
    Raises an exception on any failure (incl. 429 rate limit).
    """
    if not GROQ_API_KEY or not GROQ_API_KEY.strip():
        raise RuntimeError("GROQ_API_KEY is not configured.")
    logger.info(f"[Generator] Calling Groq API using model: {GROQ_MODEL}")
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY.strip()}",
        "Content-Type": "application/json",
    }
    if max_tokens is None:
        _MODE_TOKENS = {"mains": 1600, "current_affairs": 1024}
        max_tokens = _MODE_TOKENS.get(mode, 768)

    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _call_gemini(prompt: str) -> str:
    """
    Call the Gemini API with key rotation.
    Raises an exception if all keys fail.
    """
    api_keys = [k.strip() for k in re.split(r"[,;]", GEMINI_API_KEY) if k.strip()]
    if not api_keys:
        raise RuntimeError("GEMINI_API_KEY is not set or empty in .env")

    last_exception = None
    for idx, key in enumerate(api_keys):
        masked = f"{key[:8]}..." if len(key) > 8 else "***"
        try:
            logger.info(f"[Generator] Trying Gemini API Key {idx} ({masked}) ...")
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )
            return response.text or ""
        except Exception as exc:
            logger.warning(f"[Generator] Gemini API Key {idx} failed: {exc}. Trying next key...")
            last_exception = exc

    raise last_exception or RuntimeError("All Gemini API keys failed.")


def _clean_and_parse_json(raw: str) -> dict:
    """
    Robust JSON parser for LLM responses.
    Handles unescaped control characters, raw newlines inside strings,
    markdown code fences, and fallback text extraction.
    """
    if not raw or not raw.strip():
        raise ValueError("Empty LLM response string.")

    text = raw.strip()
    # Strip markdown code fences if model added them
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # Tier 1: Standard JSON parse with strict=False (allows raw unescaped newlines in JSON strings)
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError as err:
        logger.warning(f"[Generator] Standard json.loads failed ({err}). Trying regex extraction...")

    # Tier 2: Extract JSON object substring {...}
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1), strict=False)
        except json.JSONDecodeError:
            pass

    # Tier 3: Extract "answer" field manually if JSON string escaping broke
    answer_match = re.search(r'"answer"\s*:\s*"(.*?)"\s*,\s*"answered"', text, re.DOTALL)
    if not answer_match:
        answer_match = re.search(r'"answer"\s*:\s*"(.*)"', text, re.DOTALL)

    if answer_match:
        extracted_answer = answer_match.group(1).replace("\\n", "\n").replace('\\"', '"').strip()
        citations = list(set(re.findall(r"\[chk_\w+\]", extracted_answer)))
        return {
            "answer": extracted_answer,
            "answered": True,
            "citations": citations,
        }

    # Tier 4: Fallback — if LLM returned plain markdown instead of JSON, use plain text directly
    citations = list(set(re.findall(r"\[chk_\w+\]", text)))
    return {
        "answer": text,
        "answered": True,
        "citations": citations,
    }


# ── Chat Memory helpers ────────────────────────────────────────────────────────

def get_session_history(db, session_id: str, limit: int = 10) -> list[ChatMessage]:
    """Retrieve last N messages from database for the session_id, in chronological order."""
    if not session_id or db is None:
        return []
    try:
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
            .all()
        )
        return list(reversed(messages))
    except Exception as exc:
        logger.error(f"[Generator:DB] Failed to load chat history for session {session_id}: {exc}")
        return []


def save_chat_message(db, session_id: str, role: str, content: str):
    """Save a user or assistant message to the database."""
    if not session_id or db is None:
        return
    try:
        msg = ChatMessage(session_id=session_id, role=role, content=content)
        db.add(msg)
        db.commit()
    except Exception as exc:
        logger.error(f"[Generator:DB] Failed to save chat message: {exc}")
        db.rollback()


def format_history_for_prompt(messages: list[ChatMessage]) -> str:
    """Format a list of ChatMessage instances as user/assistant lines."""
    if not messages:
        return "No previous conversation history."
    lines = []
    for msg in messages:
        role = "User" if msg.role == "user" else "Assistant"
        content = msg.content
        try:
            # If the stored assistant response is a JSON string, extract just the answer
            parsed = json.loads(content)
            if "answer" in parsed:
                content = parsed["answer"]
        except Exception:
            pass
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def condense_query(query: str, history_str: str) -> str:
    """
    Given the user's new query and the conversation history,
    rewrite it into a standalone search query.
    """
    if not history_str.strip() or history_str == "No previous conversation history.":
        return query

    prompt = (
        "Given the following conversation history and a follow-up question, "
        "rewrite the follow-up question to be a standalone, self-contained search query. "
        "Do not answer the question; only return the rewritten question. "
        "Keep it concise and optimized for search engine retrieval.\n\n"
        "Conversation History:\n"
        f"{history_str}\n\n"
        f"Follow-up Question: {query}\n"
        "Standalone Question:"
    )
    try:
        logger.info(f"[Generator] Condensing query: '{query[:60]}'")
        rewritten = _call_gemini(prompt)
        rewritten_clean = rewritten.strip().strip('"').strip("'")
        logger.info(f"[Generator] Condensed query result: '{rewritten_clean[:80]}'")
        return rewritten_clean
    except Exception as exc:
        logger.warning(f"[Generator] Query condensation failed: {exc}. Using original query.")
        return query


def _call_gemini_grounded(query: str, system_instruction: str) -> dict:
    """
    Call the Gemini API with the native Google Search Grounding tool enabled.
    Uses key rotation across all keys in GEMINI_API_KEY.

    Returns a dict with:
        answer      (str)        — grounded markdown answer from Gemini
        answered    (bool)       — True if Gemini could answer from search results
        citations   (list[str])  — web source titles used (labelled src_001, etc.)
        rich_citations (list[dict]) — [{chunk_id, document, pages, preview, url}]
        search_queries (list[str]) — the Google Search queries Gemini executed

    Raises:
        RuntimeError if all API keys fail or SDK is not installed.
    """
    api_keys = [k.strip() for k in re.split(r"[,;]", GEMINI_API_KEY) if k.strip()]
    if not api_keys:
        raise RuntimeError("GEMINI_API_KEY is not set or empty in .env")

    last_exception = None
    for idx, key in enumerate(api_keys):
        masked = f"{key[:8]}..." if len(key) > 8 else "***"
        try:
            logger.info(
                f"[Generator:Grounding] Trying Gemini API Key {idx} ({masked}) "
                f"for Search Grounding..."
            )
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=query,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
                    temperature=0.0,
                ),
            )

            # ── Extract answer text ───────────────────────────────────────────
            answer_text = response.text.strip() if response.text else ""

            # ── Parse grounding metadata ──────────────────────────────────────
            search_queries: list[str] = []
            rich_citations: list[dict] = []
            citation_labels: list[str] = []

            if (
                response.candidates
                and response.candidates[0].grounding_metadata
            ):
                gm = response.candidates[0].grounding_metadata

                # Queries Gemini executed
                if gm.web_search_queries:
                    search_queries = list(gm.web_search_queries)

                # Grounding chunks = cited web sources
                if gm.grounding_chunks:
                    for src_idx, chunk in enumerate(gm.grounding_chunks):
                        if chunk.web:
                            label = f"src_{src_idx + 1:03d}"
                            citation_labels.append(label)
                            rich_citations.append({
                                "chunk_id": label,
                                "document": chunk.web.title or chunk.web.uri or "Web Source",
                                "pages":    None,
                                "preview":  "",
                                "url":      chunk.web.uri or "",
                            })

            answered = bool(answer_text)
            logger.info(
                f"[Generator:Grounding] Search Grounding succeeded. "
                f"Queries={search_queries}, sources={len(rich_citations)}"
            )
            return {
                "answer":         answer_text,
                "answered":       answered,
                "citations":      citation_labels,
                "rich_citations": rich_citations,
                "search_queries": search_queries,
            }

        except Exception as exc:
            logger.warning(
                f"[Generator:Grounding] Gemini API Key {idx} failed: {exc}. "
                f"Trying next key..."
            )
            last_exception = exc

    raise last_exception or RuntimeError("All Gemini API keys failed for Search Grounding.")


def generate_grounded_answer(
    query:  str,
    chunks: list[dict],
    source: str  = "qdrant",
    mode:   str  = "prelims",
    history_str: str = "",
    sub_mode: str = "summary",
) -> dict:
    """
    Generate a hallucination-resistant answer from retrieved chunks.

    Layer 1 — Score Gate: If best rerank_score < RERANK_SCORE_THRESHOLD,
               skip LLM and return "insufficient information".
    Layer 2 — Mode-specific prompt: Selected via get_prompt(mode, sub_mode).
               Modes: "prelims" | "mains" | "current_affairs".
               CA Sub-modes: "summary" | "mcq" | "explain" | "mains".
    Layer 3 — Citation enforcement: response includes cited chunk IDs.

    Groq ↔ Gemini Fallback:
        Tries Groq first. If Groq raises any exception (incl. 429 rate limit),
        automatically falls back to Gemini key-rotation before giving up.

    Args:
        query:  The user's original query.
        chunks: Reranked top-K chunks from the retrieval layer.
        source: "qdrant" or "web" — included in metadata.
        mode:   Prompt mode — "prelims" (default), "mains", or "current_affairs".
        history_str: Human-formatted sliding-window conversation history.
        sub_mode: For current_affairs: "summary" (default), "mcq", "explain", "mains".

    Returns:
        dict with keys:
            answer      (str)        — grounded answer or "insufficient info"
            answered    (bool)       — False if LLM could not answer from context
            citations   (list[str])  — chunk_ids cited in the answer
            gated       (bool)       — True if score gate blocked LLM call
            gate_reason (str | None) — reason for gating, if applicable
            mode        (str)        — prompt mode used
            sub_mode    (str)        — sub_mode used
    """
    # ── Layer 1: Score Gate ────────────────────────────────────────────────────
    if not chunks:
        logger.warning(f"[Generator] No chunks for query: '{query[:60]}' — gated.")
        return {
            "answer":         "I don't have enough information in my knowledge base to answer this question.",
            "answered":       False,
            "citations":      [],
            "rich_citations": [],
            "gated":          True,
            "gate_reason":    "No chunks retrieved from the knowledge base.",
            "mode":           mode,
            "sub_mode":       sub_mode,
        }

    best_rerank_score = max(c.get("rerank_score", 0.0) for c in chunks)
    # Mode-aware threshold: CA uses -5.0 (news text scores lower on MS-MARCO cross-encoder)
    effective_threshold = CA_RERANK_SCORE_THRESHOLD if mode == "current_affairs" else RERANK_SCORE_THRESHOLD
    if best_rerank_score < effective_threshold:
        logger.warning(
            f"[Generator] Score gate triggered — best rerank_score={best_rerank_score:.3f} "
            f"< threshold={effective_threshold} (mode={mode}) for query: '{query[:60]}'"
        )
        return {
            "answer":         "I don't have enough information in my knowledge base to answer this question.",
            "answered":       False,
            "citations":      [],
            "rich_citations": [],
            "gated":          True,
            "gate_reason": (
                f"Retrieval confidence too low (best rerank score: {best_rerank_score:.3f}). "
                "The question may be outside the scope of the available documents."
            ),
            "mode":           mode,
            "sub_mode":       sub_mode,
        }

    # ── Layer 2 + 3: Mode-specific Prompt with Citation Enforcement ─────────────
    context_block = _build_context_block(chunks)
    intent_info = detect_query_intent_and_constraints(query)
    archetype = intent_info.get("archetype", "standard_mains")
    word_limit = intent_info.get("word_limit", 250)

    # Dynamic token budget calculation (approx 1 token per 0.7 words + JSON schema buffer)
    if mode == "mains":
        if archetype == "indetail":
            calc_tokens = 2048
        elif archetype in ("summary", "brief"):
            calc_tokens = 800
        else:
            calc_tokens = max(1024, int(word_limit * 2.5))
    elif mode == "current_affairs":
        calc_tokens = 1200
    else:
        calc_tokens = 768

    try:
        selected_prompt = get_prompt(mode, sub_mode=sub_mode, query=query)
    except ValueError:
        logger.warning(
            f"[Generator] Unknown mode '{mode}' — falling back to 'prelims'."
        )
        selected_prompt = get_prompt("prelims")
        mode = "prelims"
    prompt = selected_prompt.format(
        context=context_block,
        query=query,
        history=history_str if history_str.strip() else "No previous conversation history.",
    )

    try:
        # ── Groq-first → Gemini-fallback chain with metrics ───────────────────
        raw = None
        provider_used = "n/a"
        groq_available   = bool(GROQ_API_KEY and GROQ_API_KEY.strip())
        gemini_available = bool(GEMINI_API_KEY and GEMINI_API_KEY.strip())

        with metrics_timer("gen", query=query, mode=mode) as ctx:
            if groq_available:
                try:
                    raw = _call_groq(prompt, mode=mode, max_tokens=calc_tokens)
                    provider_used = "groq"
                    logger.info("[Generator] Groq call succeeded.")
                except Exception as groq_exc:
                    logger.warning(
                        f"[Generator] Groq failed ({groq_exc}). "
                        f"Falling back to Gemini..."
                    )
                    if not gemini_available:
                        raise groq_exc

            if raw is None and gemini_available:
                logger.info("[Generator] Using Gemini API as fallback.")
                raw = _call_gemini(prompt)
                provider_used = "gemini"

            if raw is None:
                raise RuntimeError(
                    "No LLM API is configured (both GROQ_API_KEY and GEMINI_API_KEY are missing)."
                )

            # Estimate token usage (rough: 1 token ≈ 4 chars)
            ctx["input_tokens"]  = len(prompt) // 4
            ctx["output_tokens"] = len(raw) // 4
            ctx["provider"]      = provider_used

        # Use robust multi-tier JSON parsing (handles raw newlines and formatting glitches)
        result = _clean_and_parse_json(raw)

        answer    = result.get("answer", "").strip()
        answered  = bool(result.get("answered", False))
        citations = result.get("citations", [])

        # ── Strip ALL inline citation tags from user-facing answer ────────────
        # Uses pre-compiled regexes (compiled once at module load, reused every call)
        answer = _RE_CHK_PARENS.sub('', answer)   # (chk_001, chk_002)
        answer = _RE_CHK_BRACKETS.sub('', answer) # [chk_001, chk_002]
        answer = _RE_CHK_BARE.sub('', answer)      # bare chk_xxx leftovers
        answer = _RE_EMPTY_PARENS.sub('', answer)  # empty parens
        answer = _RE_PUNCT_SPACE.sub(r'\1', answer) # fix 'press .' -> 'press.'
        answer = _RE_MULTI_SPACE.sub(' ', answer).strip()

        logger.info(
            f"[Generator] answered={answered}, mode={mode}, archetype={archetype}, provider={provider_used}, "
            f"citations={citations}, query='{query[:60]}'"
        )

        rich_citations = format_citations(citations, chunks)

        return {
            "answer":          answer,
            "answered":        answered,
            "citations":       citations,
            "rich_citations":  rich_citations,
            "gated":           False,
            "gate_reason":     None,
            "mode":            mode,
            "archetype":       archetype,
            "word_limit":      word_limit,
        }

    except Exception as exc:
        logger.error(f"[Generator] LLM generation failed: {exc}")
        err_msg = str(exc).lower()
        if "429" in err_msg or "resource_exhausted" in err_msg or "quota" in err_msg or "rate" in err_msg:
            user_msg = "API rate limit reached. Please wait a few seconds and try again."
        else:
            user_msg = "I don't have enough information in my knowledge base to answer this question."

        return {
            "answer":         user_msg,
            "answered":       False,
            "citations":      [],
            "rich_citations": [],
            "gated":          True,
            "gate_reason":    f"LLM generation error: {exc}",
            "mode":           mode,
            "archetype":      archetype,
            "word_limit":     word_limit,
        }
