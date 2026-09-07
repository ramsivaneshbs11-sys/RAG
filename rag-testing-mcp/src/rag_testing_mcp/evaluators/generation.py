"""
Answer quality and faithfulness evaluator.

Evaluates four distinct metrics:

  1. Answer Relevance    — Does the answer address the question?
  2. Faithfulness        — Are the answer's CLAIMS supported by the retrieved chunks?
                           Sentence-level: each sentence checked against chunk context.
  3. Groundedness        — Are specific FACTS (numbers, named entities, statistics)
                           explicitly present in the retrieved context?
                           This is STRICTER than faithfulness.
  4. Hallucination Risk  — Combined penalty from low faithfulness + ungrounded numbers.

Critical distinction:
  FACTUALLY CORRECT  ≠  SUPPORTED BY RETRIEVED CONTEXT
  A generally correct statement NOT backed by retrieved sources is a grounding problem.
"""

from __future__ import annotations

import re

from rag_testing_mcp.models import (
    RAGQueryResponse,
    DatasetItem,
    GenerationMetrics,
    FailureRecord,
    FailureType,
)


# ── Helpers ────────────────────────────────────────────────────────────

STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can",
    "had", "her", "was", "one", "our", "out", "has", "have", "been",
    "from", "this", "that", "with", "they", "will", "each", "make",
    "like", "long", "look", "many", "some", "than", "them", "then",
    "very", "when", "come", "could", "into", "more", "also", "back",
    "which", "their", "about", "would", "there", "these", "other",
    "thus", "such", "both", "only", "over", "most", "well", "were",
    "says", "said", "also", "upon", "during", "while", "since",
}


def _extract_numbers(text: str) -> list[str]:
    """Extract substantive numeric values from text.

    Always extracts:
      - Percentages (3.1%, 96%, 4%)  ← factual claims, never filter

    Filters out from bare numbers:
      - Single digits  (list markers 1. 2. 3.)
      - Years          (1700-2099)
      - Article/section refs  (Art.14, Art.32 etc., val ≤ 150 without decimal)
    """
    raw = re.findall(r'(?<!\d)(\d+(?:\.\d+)?)(%)? (?!\d)', text + ' ')
    if not raw:
        raw = re.findall(r'(\d+(?:\.\d+)?)(%?)', text)
    results = []
    for num_str, pct in raw:
        try:
            val = float(num_str)
        except ValueError:
            continue
        # ALWAYS keep percentages — they are factual claims
        if pct:
            results.append(num_str + pct)
            continue
        if val < 10:
            continue
        if 1700 <= val <= 2099:
            continue
        if val <= 150 and '.' not in num_str:
            continue
        results.append(num_str)
    return results


def _extract_sentences(text: str) -> list[str]:
    """Split text into claim-level sentences (skip bullets/headers)."""
    # Split on sentence-ending punctuation
    raw = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = []
    for s in raw:
        s = s.strip().lstrip('•·-–—*#> ')
        if len(s) > 15:  # skip trivial fragments
            sentences.append(s)
    return sentences


def _keywords(text: str) -> set[str]:
    """Extract meaningful keywords (≥4 chars, not stopwords)."""
    return set(re.findall(r"[a-zA-Z]{4,}", text.lower())) - STOPWORDS


def _sentence_support_ratio(sentence: str, context: str) -> float:
    """What fraction of the sentence's keywords are found in context?"""
    words = _keywords(sentence)
    if not words:
        return 1.0  # trivial sentence — assume supported
    context_lower = context.lower()
    matched = sum(1 for w in words if w in context_lower)
    return matched / len(words)


def _check_number_grounding(answer: str, context: str) -> list[str]:
    """Check whether numeric values in the answer exist in the retrieved context.

    Critical test: context says '3.1%' but answer says '4%' → GROUNDING_FAILURE.
    The number must appear LITERALLY in the context (exact or without % sign).
    """
    answer_numbers = _extract_numbers(answer)
    context_text = context.lower()
    ungrounded = []
    for num in answer_numbers:
        if num.lower() in context_text:
            continue
        num_clean = num.replace("%", "")
        if num_clean in context_text:
            continue
        # Also try with space: "96 %" → "96%"
        if num_clean + "%" in context_text:
            continue
        ungrounded.append(num)
    return ungrounded


def _named_entity_groundedness(answer: str, context: str) -> float:
    """Check that proper nouns / named entities in the answer appear in context.

    Uses heuristic: capitalized words ≥ 4 chars that appear in the answer
    should also appear (case-insensitive) in the retrieved context.
    Returns ratio of grounded named entities.
    """
    # Capitalised words in answer that aren't at sentence start
    named = re.findall(r'(?<!\.\s)(?<![!?\s][A-Z])([A-Z][a-z]{3,})', answer)
    if not named:
        return 1.0
    context_lower = context.lower()
    grounded = sum(1 for n in named if n.lower() in context_lower)
    return grounded / len(named)


# ── Main Evaluator ─────────────────────────────────────────────────────

def evaluate_generation(
    response: RAGQueryResponse,
    dataset_item: DatasetItem,
) -> tuple[GenerationMetrics, list[FailureRecord]]:
    """Evaluate answer quality, faithfulness, and groundedness.

    Faithfulness   = sentence-level claim support (% of sentences backed by context)
    Groundedness   = fact-level support (numbers + named entities in context)
    These are DISTINCT metrics. An answer can be faithful (general claims OK)
    but ungrounded (specific numbers not in chunks).

    Returns (metrics, failures).
    """
    failures: list[FailureRecord] = []

    # ── Gated / unanswered ─────────────────────────────────────────────
    if not response.answered or response.gated:
        return (
            GenerationMetrics(
                answer_relevance=0.0,
                faithfulness=0.0,
                groundedness=0.0,
                hallucination_risk=1.0,
            ),
            [FailureRecord(
                question_id=dataset_item.id,
                failure_type=FailureType.GENERATION_FAILURE,
                reason=response.gate_reason or "RAG did not generate an answer.",
            )],
        )

    answer = response.answer
    question = dataset_item.question

    # Build full context from retrieved chunks
    context = "\n".join(c.text for c in response.chunks if c.text)

    if not context.strip():
        return (
            GenerationMetrics(
                answer_relevance=0.0,
                faithfulness=0.0,
                groundedness=0.0,
                hallucination_risk=1.0,
                status="evaluated",
            ),
            [FailureRecord(
                question_id=dataset_item.id,
                failure_type=FailureType.RETRIEVAL_FAILURE,
                reason="No context chunks were retrieved to evaluate against.",
            )],
        )

    # ══════════════════════════════════════════════════════════════════
    # Metric 1: Answer Relevance
    # Does the answer address the question?
    # ══════════════════════════════════════════════════════════════════
    q_words = _keywords(question)
    a_words = _keywords(answer)

    if q_words:
        direct_overlap = len(q_words & a_words) / len(q_words)
        # Long detailed answers (UPSC mains) score higher even with low direct overlap
        length_bonus = min(len(a_words) / 80, 0.20)
        answered_bonus = 0.15 if response.answered else 0.0
        relevance_score = min(direct_overlap + length_bonus + answered_bonus, 1.0)
    else:
        relevance_score = 1.0 if response.answered else 0.0

    # Weight in reference answer comparison if available
    if dataset_item.reference_answer:
        ref_words = _keywords(dataset_item.reference_answer)
        if ref_words:
            ref_overlap = len(ref_words & a_words) / len(ref_words)
            relevance_score = (relevance_score * 0.6) + (ref_overlap * 0.4)

    answer_relevance = round(min(relevance_score, 1.0), 4)

    # ══════════════════════════════════════════════════════════════════
    # Metric 2: Faithfulness
    # Sentence-level: what fraction of answer sentences are supported by
    # at least 50% keyword overlap with the retrieved context?
    # ══════════════════════════════════════════════════════════════════
    sentences = _extract_sentences(answer)
    if not sentences:
        faithfulness = 1.0
    else:
        support_ratios = [_sentence_support_ratio(s, context) for s in sentences]
        # A sentence is "faithful" if ≥ 50% of its keywords are in context
        supported = sum(1 for r in support_ratios if r >= 0.5)
        faithfulness = round(supported / len(sentences), 4)

    if faithfulness < 0.5:
        failures.append(FailureRecord(
            question_id=dataset_item.id,
            failure_type=FailureType.GROUNDING_FAILURE,
            reason=(
                f"Low faithfulness ({faithfulness:.2f}): answer sentences are not "
                f"sufficiently supported by retrieved chunks."
            ),
        ))

    # ══════════════════════════════════════════════════════════════════
    # Metric 3: Groundedness  (DISTINCT from faithfulness)
    # Fact-level: are specific numbers and named entities in the answer
    # explicitly present in the retrieved chunks?
    # ══════════════════════════════════════════════════════════════════

    # 3a. Number grounding (critical — the 3.1% vs 4% test)
    ungrounded_numbers = _check_number_grounding(answer, context)
    number_penalty = min(len(ungrounded_numbers) * 0.15, 0.45)

    # 3b. Named entity grounding (proper nouns)
    ne_ratio = _named_entity_groundedness(answer, context)
    # Named entity check contributes 30% weight to groundedness
    ne_penalty = round((1.0 - ne_ratio) * 0.30, 4)

    # 3c. Sentence-level groundedness (stricter than faithfulness — requires ≥ 70%)
    if sentences:
        deep_supported = sum(1 for r in support_ratios if r >= 0.70)
        sentence_groundedness = deep_supported / len(sentences)
    else:
        sentence_groundedness = 1.0

    # Combine: sentence-level (50% weight) + NE (30%) + number (20%)
    raw_groundedness = (
        sentence_groundedness * 0.50
        + ne_ratio * 0.30
        + (1.0 - min(number_penalty, 0.45)) * 0.20
    )
    groundedness = round(max(raw_groundedness - number_penalty * 0.20, 0.0), 4)

    if ungrounded_numbers:
        failures.append(FailureRecord(
            question_id=dataset_item.id,
            failure_type=FailureType.GROUNDING_FAILURE,
            reason=(
                f"Answer contains numbers/values not found in retrieved context: "
                f"{ungrounded_numbers}. Possible hallucination."
            ),
        ))

    # ══════════════════════════════════════════════════════════════════
    # Metric 4: Hallucination Risk
    # Combined signal from faithfulness + groundedness failures.
    # ══════════════════════════════════════════════════════════════════
    # Weighted: faithfulness (60%) + groundedness (40%)
    hallucination_risk = round(
        (1.0 - faithfulness) * 0.60 + (1.0 - groundedness) * 0.40,
        4,
    )
    hallucination_risk = min(hallucination_risk, 1.0)

    return (
        GenerationMetrics(
            answer_relevance=answer_relevance,
            faithfulness=faithfulness,
            groundedness=groundedness,
            hallucination_risk=hallucination_risk,
        ),
        failures,
    )
