"""
app/retrieval/intent_router.py
──────────────────────────────
Pre-RAG Intent Router — runs BEFORE any embedding, Qdrant, reranking, or LLM call.

Architecture
────────────
User Query
    ↓
Pre-RAG Intent Router  ← (this module)
    ├── GREETING / CASUAL → Direct template response (0 RAG calls)
    ├── OUT_OF_SCOPE      → Polite refusal (0 RAG calls)
    ├── FOLLOW_UP         → Existing RAG pipeline (with conversation context)
    └── KNOWLEDGE         → Existing RAG pipeline

Intent Categories
─────────────────
GREETING     — Hi, Hello, Good morning, Hey there
CASUAL       — How are you?, Thanks, Bye, Who are you?, What can you do?
FOLLOW_UP    — Short/ambiguous query that follows a prior assistant turn
KNOWLEDGE    — Any factual / UPSC / domain query → full RAG
OUT_OF_SCOPE — Content the bot should gracefully decline

Design Principles
─────────────────
1. Zero LLM calls for GREETING/CASUAL — static template responses only.
2. Strict false-positive prevention: WH-questions (What/Who/Why/How/When) with
   content words are ALWAYS routed to KNOWLEDGE, never CASUAL.
3. Follow-up detection is conservative: only fires when conversation history
   has a prior assistant message AND the new query is context-dependent.
4. All routing decisions are logged with latency.
"""

import re
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Intent constants ─────────────────────────────────────────────────────────

GREETING    = "GREETING"
CASUAL      = "CASUAL"
FOLLOW_UP   = "FOLLOW_UP"
KNOWLEDGE   = "KNOWLEDGE"
OUT_OF_SCOPE = "OUT_OF_SCOPE"

ROUTE_DIRECT = "DIRECT_RESPONSE"
ROUTE_RAG    = "RAG"


# ─── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class IntentResult:
    intent:          str
    route:           str
    rag_bypassed:    bool
    direct_response: Optional[str]  # Non-None only when rag_bypassed=True
    confidence:      float          # 0.0–1.0 (pattern-match certainty)
    latency_ms:      float = 0.0
    details:         dict  = field(default_factory=dict)


# ─── Static template responses (no LLM call) ─────────────────────────────────

_GREETING_RESPONSES: dict[str, str] = {
    "hi":                  "Hi! How can I help with your UPSC preparation?",
    "hello":               "Hello! How can I help with your UPSC preparation?",
    "hey":                 "Hey! How can I help you today?",
    "hi there":            "Hi there! How can I assist you?",
    "hello there":         "Hello there! How can I assist you?",
    "good morning":        "Good morning! Ready to help with your UPSC prep today.",
    "good afternoon":      "Good afternoon! How can I help you?",
    "good evening":        "Good evening! What topic shall we explore today?",
    "good night":          "Good night! Come back anytime for your UPSC prep.",
    "namaste":             "Namaste! How can I assist you today?",
    "hey there":           "Hey there! How can I help?",
    "greetings":           "Greetings! How can I assist you with UPSC preparation?",
}

_DEFAULT_GREETING_RESPONSE = "Hello! How can I help you with your UPSC preparation?"

_CASUAL_RESPONSES: dict[str, str] = {
    "how are you":         "I'm doing well, thank you! How can I help you today?",
    "how are you doing":   "I'm doing well! What topic can I help you with?",
    "how do you do":       "I'm well, thank you! How can I assist you?",
    "thanks":              "You're welcome! Is there anything else I can help you with?",
    "thank you":           "You're welcome! Feel free to ask more questions anytime.",
    "thank you so much":   "You're very welcome! Happy to help.",
    "ty":                  "You're welcome!",
    "bye":                 "Goodbye! Best of luck with your UPSC preparation!",
    "goodbye":             "Goodbye! Have a great day!",
    "see you":             "See you! Keep up the great work on your prep!",
    "see you later":       "See you later! All the best!",
    "ok":                  "Got it! Let me know if you need anything else.",
    "okay":                "Sure! Let me know if you need any help.",
    "alright":             "Alright! Feel free to ask more questions.",
    "who are you":         "I'm an AI assistant specializing in UPSC preparation. I can answer questions on History, Polity, Geography, Economy, Environment, Current Affairs, and Anthropology.",
    "what are you":        "I'm an AI-powered UPSC study assistant that retrieves answers from curated study materials and current affairs.",
    "what can you do":     "I can answer UPSC questions across GS Paper 1–4, Anthropology, and Current Affairs. I support Prelims, Mains, and Current Affairs modes.",
    "what is your name":   "I'm your UPSC AI Assistant, here to help you crack the exam!",
    "who made you":        "I was built to help UPSC aspirants access study materials and current affairs quickly.",
    "are you an ai":       "Yes! I'm an AI assistant trained to help with UPSC preparation.",
    "are you a bot":       "Yes, I'm an AI-powered UPSC study bot!",
    "help":                "Of course! You can ask me questions on History, Polity, Geography, Economy, Environment, Science, Current Affairs, or Anthropology. What would you like to know?",
}

_DEFAULT_CASUAL_RESPONSE = "I'm here to help! Feel free to ask any UPSC-related questions."

_OUT_OF_SCOPE_RESPONSE = (
    "I'm specialized for UPSC preparation — I cover topics like History, Polity, "
    "Geography, Economy, Environment, Science & Technology, Current Affairs, and Anthropology. "
    "Could you rephrase your question in that context?"
)


# ─── Pattern sets ─────────────────────────────────────────────────────────────

# Pure greeting tokens/phrases (exact normalized match)
_GREETING_TOKENS: set[str] = {
    "hi", "hello", "hey", "hiya", "howdy", "greetings",
    "namaste", "namaskar", "vanakkam", "hai",
    "hi there", "hello there", "hey there",
    "good morning", "good afternoon", "good evening", "good night",
    "good day", "good morn",
}

# Casual phrases (normalized starts-with or exact match)
_CASUAL_PHRASES: list[str] = [
    "how are you", "how r u", "how ru", "how do you do", "how have you been",
    "how's it going", "hows it going", "what's up", "whats up", "sup",
    "thanks", "thank you", "ty", "thx", "thnks", "thnx", "thank u",
    "bye", "goodbye", "good bye", "see you", "see ya", "cya",
    "ttyl", "take care", "take care of yourself",
    "ok", "okay", "ok ok", "okey", "k", "kk",
    "alright", "alrighty", "cool", "great", "nice", "awesome",
    "got it", "understood", "i see", "makes sense",
    "who are you", "what are you", "what can you do", "what is your name",
    "who made you", "are you an ai", "are you a bot", "are you human",
    "what do you do", "tell me about yourself", "introduce yourself",
    "can you help", "help me", "help",
]

# Follow-up triggers: short/ambiguous queries that need prior context
_FOLLOWUP_AMBIGUOUS: set[str] = {
    "why", "how", "when", "what", "where", "who", "which",
    "why not", "how so", "then what", "and then",
    "explain this", "explain that", "elaborate", "elaborate more",
    "tell me more", "more details", "more about this", "more about that",
    "give me more", "and", "but why", "what about that", "what about this",
    "can you explain", "please explain", "please elaborate",
    "really", "how come", "what do you mean",
}

# Knowledge override: these patterns MUST always go to RAG even if short
_KNOWLEDGE_OVERRIDE_PREFIXES: tuple[str, ...] = (
    "what is", "what are", "what was", "what were", "what does", "what did",
    "who is", "who are", "who was", "who were",
    "why is", "why are", "why was", "why were", "why did", "why does",
    "how is", "how are", "how was", "how were", "how did", "how does",
    "when is", "when was", "when did", "when were",
    "where is", "where was", "where did",
    "which is", "which was",
    "explain", "describe", "define", "elaborate on", "discuss",
    "compare", "contrast", "differentiate", "analyse", "analyze",
    "what happened", "tell me about", "give me information",
    "what do you know about", "how does it work",
)

# Follow-up override: phrases that start with knowledge-override prefixes
# BUT are context-dependent follow-ups when conversation history exists.
# E.g. "explain this", "explain that" with a prior assistant turn.
_FOLLOWUP_OVERRIDE_PHRASES: frozenset[str] = frozenset({
    "explain this", "explain that", "describe this", "describe that",
    "elaborate on this", "elaborate on that",
    "tell me more about this", "tell me more about that",
    "what about this", "what about that",
})

# Bot-identity / self-referential phrases that look like WH-questions
# but are CASUAL (targeting the bot itself, not factual knowledge).
# These MUST be checked BEFORE the knowledge-override prefix list.
_BOT_IDENTITY_PHRASES: frozenset[str] = frozenset({
    "how are you", "how are you doing", "how are you today",
    "how have you been", "how do you do", "how r u", "how ru",
    "how's it going", "hows it going",
    "who are you", "what are you", "what can you do",
    "what is your name", "what's your name", "whats your name",
    "what are you called", "what do you do",
    "who made you", "who created you", "who built you",
    "are you an ai", "are you a bot", "are you human", "are you real",
    "tell me about yourself", "introduce yourself",
})

# Out-of-scope topics for a UPSC bot
_OOS_PATTERNS: list[str] = [
    r"\b(recipe|cooking|cook|food|restaurant)\b",
    r"\b(cricket|football|ipl|sports score|match result)\b",
    r"\b(movie|film|song|music|celebrity|actor|actress)\b",
    r"\b(stock|share price|crypto|bitcoin|nft)\b",
    r"\b(dating|relationship|love|girlfriend|boyfriend)\b",
]
_OOS_COMPILED = [re.compile(p, re.IGNORECASE) for p in _OOS_PATTERNS]


# ─── Normalizer ──────────────────────────────────────────────────────────────

def normalize_query(query: str) -> str:
    """Lowercase, strip leading/trailing whitespace, collapse internal spaces, remove trailing punctuation."""
    q = query.lower().strip()
    q = re.sub(r"\s+", " ", q)                   # collapse spaces
    q = re.sub(r"[!?.]+$", "", q).strip()        # strip trailing punctuation
    return q


# ─── Individual detectors ─────────────────────────────────────────────────────

def is_bot_identity_query(normalized: str) -> bool:
    """
    Returns True for self-referential queries about the bot (Who are you? How are you?).
    These look like WH-questions but are CASUAL, not KNOWLEDGE.
    Must be checked BEFORE is_knowledge_override().
    """
    return normalized in _BOT_IDENTITY_PHRASES


def is_knowledge_override(normalized: str) -> bool:
    """
    Returns True if the query definitely needs RAG regardless of length.
    Prevents WH-questions and academic starters from being misclassified.
    """
    return normalized.startswith(_KNOWLEDGE_OVERRIDE_PREFIXES)


def is_greeting(normalized: str) -> bool:
    """Exact match against greeting token set."""
    return normalized in _GREETING_TOKENS


def is_casual(normalized: str) -> bool:
    """Match against casual phrase list (exact or startswith for short inputs)."""
    for phrase in _CASUAL_PHRASES:
        if normalized == phrase:
            return True
        # Short casual queries may have slight suffixes ("ok thanks", "thanks a lot")
        if len(normalized) <= len(phrase) + 10 and normalized.startswith(phrase):
            return True
    return False


def is_follow_up(normalized: str, conversation_context: Optional[str]) -> bool:
    """
    Returns True only when:
    1. The query is in the ambiguous follow-up set, AND
    2. There IS conversation context (prior assistant turn exists).

    This prevents "Why?" from being CASUAL when it follows a prior answer.
    """
    if not conversation_context or conversation_context.strip() == "No previous conversation history.":
        return False
    return normalized in _FOLLOWUP_AMBIGUOUS


def is_out_of_scope(original: str) -> bool:
    """Check for off-topic patterns (sports scores, recipes, etc.)."""
    for pattern in _OOS_COMPILED:
        if pattern.search(original):
            return True
    return False


# ─── Response helpers ─────────────────────────────────────────────────────────

def get_direct_response(intent: str, normalized: str) -> str:
    """Return a static template response. No LLM call required."""
    if intent == GREETING:
        return _GREETING_RESPONSES.get(normalized, _DEFAULT_GREETING_RESPONSE)
    if intent == CASUAL:
        for phrase, response in _CASUAL_RESPONSES.items():
            if normalized == phrase or normalized.startswith(phrase):
                return response
        return _DEFAULT_CASUAL_RESPONSE
    if intent == OUT_OF_SCOPE:
        return _OUT_OF_SCOPE_RESPONSE
    return _DEFAULT_CASUAL_RESPONSE


# ─── Main classifier ─────────────────────────────────────────────────────────

def classify_intent(
    query: str,
    conversation_context: Optional[str] = None,
) -> IntentResult:
    """
    Classify user query intent using lightweight pattern matching.
    Zero embedding, zero Qdrant, zero LLM.

    Args:
        query: Raw user query string.
        conversation_context: Formatted prior conversation history (optional).

    Returns:
        IntentResult with intent, route, rag_bypassed, direct_response, confidence, latency_ms.
    """
    t0 = time.perf_counter()
    normalized = normalize_query(query)

    # ── Step 0: Bot-identity / wellbeing (before knowledge override) ─────────
    # Phrases like "How are you?", "Who are you?", "What can you do?" target
    # the bot itself. They must be classified as CASUAL even though they start
    # with WH-words. This check MUST run before is_knowledge_override().
    if is_bot_identity_query(normalized):
        response = get_direct_response(CASUAL, normalized)
        result = IntentResult(
            intent=CASUAL, route=ROUTE_DIRECT,
            rag_bypassed=True, direct_response=response, confidence=1.0,
            details={"reason": "bot_identity_query"},
        )
        result.latency_ms = (time.perf_counter() - t0) * 1000
        _log_intent(query, result)
        return result

    # ── Step 1: Knowledge override (highest domain priority) ─────────────────
    # Prevents WH-questions from ever being misclassified as CASUAL/GREETING.
    # Exception: if query is in FOLLOWUP_OVERRIDE_PHRASES and context exists,
    # treat as FOLLOW_UP instead (e.g. "explain this" after a prior answer).
    has_context = bool(
        conversation_context
        and conversation_context.strip()
        and conversation_context.strip() != "No previous conversation history."
    )
    if is_knowledge_override(normalized):
        if has_context and normalized in _FOLLOWUP_OVERRIDE_PHRASES:
            result = IntentResult(
                intent=FOLLOW_UP, route=ROUTE_RAG,
                rag_bypassed=False, direct_response=None, confidence=0.85,
                details={"reason": "follow_up_override_phrase_with_context"},
            )
            result.latency_ms = (time.perf_counter() - t0) * 1000
            _log_intent(query, result)
            return result
        result = IntentResult(
            intent=KNOWLEDGE, route=ROUTE_RAG,
            rag_bypassed=False, direct_response=None, confidence=0.99,
            details={"reason": "knowledge_override_prefix"},
        )
        result.latency_ms = (time.perf_counter() - t0) * 1000
        _log_intent(query, result)
        return result

    # ── Step 2: Out-of-scope check ────────────────────────────────────────────
    if is_out_of_scope(query):
        response = get_direct_response(OUT_OF_SCOPE, normalized)
        result = IntentResult(
            intent=OUT_OF_SCOPE, route=ROUTE_DIRECT,
            rag_bypassed=True, direct_response=response, confidence=0.95,
            details={"reason": "oos_pattern_match"},
        )
        result.latency_ms = (time.perf_counter() - t0) * 1000
        _log_intent(query, result)
        return result

    # ── Step 3: Greeting ──────────────────────────────────────────────────────
    if is_greeting(normalized):
        response = get_direct_response(GREETING, normalized)
        result = IntentResult(
            intent=GREETING, route=ROUTE_DIRECT,
            rag_bypassed=True, direct_response=response, confidence=1.0,
            details={"reason": "greeting_token_match"},
        )
        result.latency_ms = (time.perf_counter() - t0) * 1000
        _log_intent(query, result)
        return result

    # ── Step 4: Casual ────────────────────────────────────────────────────────
    if is_casual(normalized):
        response = get_direct_response(CASUAL, normalized)
        result = IntentResult(
            intent=CASUAL, route=ROUTE_DIRECT,
            rag_bypassed=True, direct_response=response, confidence=0.95,
            details={"reason": "casual_phrase_match"},
        )
        result.latency_ms = (time.perf_counter() - t0) * 1000
        _log_intent(query, result)
        return result

    # ── Step 5: Follow-up (requires prior context) ────────────────────────────
    if is_follow_up(normalized, conversation_context):
        result = IntentResult(
            intent=FOLLOW_UP, route=ROUTE_RAG,
            rag_bypassed=False, direct_response=None, confidence=0.85,
            details={"reason": "follow_up_with_context"},
        )
        result.latency_ms = (time.perf_counter() - t0) * 1000
        _log_intent(query, result)
        return result

    # ── Step 6: Default → KNOWLEDGE (full RAG) ───────────────────────────────
    result = IntentResult(
        intent=KNOWLEDGE, route=ROUTE_RAG,
        rag_bypassed=False, direct_response=None, confidence=0.80,
        details={"reason": "default_knowledge"},
    )
    result.latency_ms = (time.perf_counter() - t0) * 1000
    _log_intent(query, result)
    return result


# ─── Logging ─────────────────────────────────────────────────────────────────

def _log_intent(query: str, result: IntentResult) -> None:
    logger.info(
        f"[IntentRouter] Query='{query[:80]}' | Intent={result.intent} | "
        f"Route={result.route} | RAG_BYPASSED={result.rag_bypassed} | "
        f"Latency={result.latency_ms:.2f}ms"
    )
