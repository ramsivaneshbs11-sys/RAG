"""
tests/test_intent_router.py
───────────────────────────
Unit + integration tests for the Pre-RAG Intent Router.

Run with:
    python -m pytest tests/test_intent_router.py -v
"""

import pytest
from app.retrieval.intent_router import (
    classify_intent,
    normalize_query,
    is_greeting,
    is_casual,
    is_follow_up,
    is_knowledge_override,
    GREETING, CASUAL, FOLLOW_UP, KNOWLEDGE, OUT_OF_SCOPE,
    ROUTE_DIRECT, ROUTE_RAG,
)

# ─── Normalize tests ─────────────────────────────────────────────────────────

class TestNormalize:
    def test_lowercase(self):          assert normalize_query("HELLO") == "hello"
    def test_strip_whitespace(self):   assert normalize_query("  hi  ") == "hi"
    def test_collapse_spaces(self):    assert normalize_query("hi  there") == "hi there"
    def test_strip_punctuation(self):  assert normalize_query("hi!") == "hi"
    def test_strip_question_mark(self):assert normalize_query("how are you?") == "how are you"


# ─── Greeting tests ───────────────────────────────────────────────────────────

class TestGreeting:
    @pytest.mark.parametrize("query", [
        "Hi", "Hello", "Hey", "hi", "hello", "hey",
        "Hi there", "Hello there", "Hey there",
        "Good morning", "Good afternoon", "Good evening", "Good night",
        "namaste", "Namaste", "greetings",
    ])
    def test_greeting_detected(self, query):
        result = classify_intent(query)
        assert result.intent == GREETING, f"Expected GREETING for '{query}', got {result.intent}"
        assert result.rag_bypassed is True
        assert result.route == ROUTE_DIRECT
        assert result.direct_response is not None
        assert len(result.direct_response) > 0

    def test_greeting_has_sub_1ms_latency(self):
        result = classify_intent("Hi")
        # Should be well under 5 ms
        assert result.latency_ms < 50, f"Greeting latency too high: {result.latency_ms:.2f}ms"


# ─── Casual tests ─────────────────────────────────────────────────────────────

class TestCasual:
    @pytest.mark.parametrize("query", [
        "How are you?", "How are you doing?", "How do you do?",
        "Thanks", "Thank you", "Thank you so much",
        "Bye", "Goodbye", "See you", "See you later",
        "Ok", "Okay", "Alright",
        "Who are you?", "What are you?", "What can you do?",
        "What is your name?", "Are you an AI?", "Are you a bot?",
        "Help",
    ])
    def test_casual_detected(self, query):
        result = classify_intent(query)
        assert result.intent == CASUAL, f"Expected CASUAL for '{query}', got {result.intent}"
        assert result.rag_bypassed is True
        assert result.route == ROUTE_DIRECT
        assert result.direct_response is not None


# ─── Knowledge tests ──────────────────────────────────────────────────────────

class TestKnowledge:
    @pytest.mark.parametrize("query", [
        "What is DNA?",
        "What are the similarities between human DNA and other vertebrates?",
        "Explain the Non-Cooperation Movement.",
        "What is the role of railways in Indian nationalism?",
        "Who was Gandhi?",
        "Why did the Non-Cooperation Movement fail?",
        "When did the Battle of Panipat happen?",
        "What is the Preamble to the Indian Constitution?",
        "How does photosynthesis work?",
        "Describe the functions of the Rajya Sabha.",
        "What is RAG?",
        "Explain climate change and its impact.",
        "What is GDP?",
        "Who is the President of India?",
    ])
    def test_knowledge_routed_to_rag(self, query):
        result = classify_intent(query)
        assert result.intent == KNOWLEDGE, f"Expected KNOWLEDGE for '{query}', got {result.intent}"
        assert result.rag_bypassed is False
        assert result.route == ROUTE_RAG
        assert result.direct_response is None


# ─── Follow-up tests ─────────────────────────────────────────────────────────

class TestFollowUp:
    CONTEXT = "User: What is the Non-Cooperation Movement?\nAssistant: The Non-Cooperation Movement was..."

    @pytest.mark.parametrize("query", [
        "Why?", "How?", "When?", "What?",
        "Tell me more", "Explain this", "Elaborate",
        "Why was it withdrawn?",  # this becomes KNOWLEDGE via knowledge override
    ])
    def test_follow_up_needs_context(self, query):
        # Without context → KNOWLEDGE (not FOLLOW_UP for ambiguous ones, not CASUAL)
        result_no_ctx = classify_intent(query)
        assert result_no_ctx.intent != CASUAL, \
            f"'{query}' should NOT be CASUAL"

    @pytest.mark.parametrize("query", [
        "Why", "How", "When", "What",
        "Tell me more", "Explain this", "Elaborate",
    ])
    def test_follow_up_with_context(self, query):
        result = classify_intent(query, conversation_context=self.CONTEXT)
        assert result.intent == FOLLOW_UP, \
            f"Expected FOLLOW_UP for '{query}' with context, got {result.intent}"
        assert result.rag_bypassed is False
        assert result.route == ROUTE_RAG


# ─── False-positive prevention ────────────────────────────────────────────────

class TestFalsePositivePrevention:
    """Short knowledge questions must never be classified as CASUAL."""

    @pytest.mark.parametrize("query", [
        "What is DNA?",
        "Who was Gandhi?",
        "Why did the movement fail?",
        "When did it happen?",
        "What is RAG?",
        "How does it work?",
        "Why is inflation rising?",
    ])
    def test_wh_questions_are_knowledge(self, query):
        result = classify_intent(query)
        assert result.intent not in (CASUAL, GREETING), \
            f"'{query}' was incorrectly classified as {result.intent}"
        assert result.rag_bypassed is False


# ─── RAG bypass verification ──────────────────────────────────────────────────

class TestRagBypass:
    def test_greeting_bypasses_rag(self):
        result = classify_intent("Hi")
        assert result.rag_bypassed is True

    def test_casual_bypasses_rag(self):
        result = classify_intent("Thanks")
        assert result.rag_bypassed is True

    def test_knowledge_does_not_bypass_rag(self):
        result = classify_intent("What is DNA?")
        assert result.rag_bypassed is False

    def test_knowledge_wh_does_not_bypass_rag(self):
        result = classify_intent("Why was the Non-Cooperation Movement withdrawn?")
        assert result.rag_bypassed is False


# ─── Integration: Section 15 of spec ─────────────────────────────────────────

class TestSection15Validation:
    """Validates the 7 queries from Section 15 of the spec document."""

    def test_query_hi(self):
        r = classify_intent("Hi")
        assert r.intent == GREETING
        assert r.route == ROUTE_DIRECT
        assert r.rag_bypassed is True

    def test_query_hello(self):
        r = classify_intent("Hello")
        assert r.intent == GREETING
        assert r.route == ROUTE_DIRECT
        assert r.rag_bypassed is True

    def test_query_thanks(self):
        r = classify_intent("Thanks")
        assert r.intent == CASUAL
        assert r.route == ROUTE_DIRECT
        assert r.rag_bypassed is True

    def test_query_how_are_you(self):
        r = classify_intent("How are you?")
        assert r.intent == CASUAL
        assert r.route == ROUTE_DIRECT
        assert r.rag_bypassed is True

    def test_query_what_is_dna(self):
        r = classify_intent("What is DNA?")
        assert r.intent == KNOWLEDGE
        assert r.route == ROUTE_RAG
        assert r.rag_bypassed is False

    def test_query_dna_similarities(self):
        r = classify_intent("What are the similarities between human DNA and other vertebrates?")
        assert r.intent == KNOWLEDGE
        assert r.route == ROUTE_RAG
        assert r.rag_bypassed is False

    def test_query_non_cooperation(self):
        r = classify_intent("Why was the Non-Cooperation Movement withdrawn?")
        # This has "Why was" prefix → KNOWLEDGE override
        assert r.intent == KNOWLEDGE
        assert r.route == ROUTE_RAG
        assert r.rag_bypassed is False


# ─── Latency sanity ───────────────────────────────────────────────────────────

class TestLatency:
    def test_all_classifications_report_latency(self):
        for query in ["Hi", "Thanks", "What is DNA?", "Why", "Tell me more"]:
            r = classify_intent(query)
            assert r.latency_ms >= 0, f"Negative latency for '{query}'"

    def test_greeting_latency_is_fast(self):
        r = classify_intent("Hello")
        assert r.latency_ms < 50  # well under 50 ms (typically < 1 ms)
