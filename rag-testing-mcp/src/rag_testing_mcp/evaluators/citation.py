"""
Citation correctness evaluator.

Checks whether the cited chunk IDs in the answer actually contain
content that supports the claims made.

Supports:
  1. Inline citation tags [chk_xxx] in answer text
  2. rich_citations list from the RAG response (primary)
  3. Plain citations[] list (chunk_id references)
"""

from __future__ import annotations

import re

from rag_testing_mcp.models import (
    RAGQueryResponse,
    DatasetItem,
    CitationMetrics,
    FailureRecord,
    FailureType,
)


def evaluate_citations(
    response: RAGQueryResponse,
    dataset_item: DatasetItem,
) -> tuple[CitationMetrics, list[FailureRecord]]:
    """Validate that cited sources actually support the answer."""
    failures: list[FailureRecord] = []
    citations = response.citations       # list of chunk_id strings
    rich_citations = response.rich_citations  # list of CitationResult (structured)
    chunks = response.chunks
    answer = response.answer

    # ── If the RAG answered but has no citations of any kind ──────────
    if not citations and not rich_citations:
        if response.answered and not response.gated:
            failures.append(FailureRecord(
                question_id=dataset_item.id,
                failure_type=FailureType.CITATION_FAILURE,
                reason="Answer was generated but contains no citations.",
            ))
            return CitationMetrics(citation_score=0.0, status="evaluated"), failures
        return CitationMetrics(citation_score=0.0, status="not_available"), failures

    # ── Build chunk text map ───────────────────────────────────────────
    chunk_map = {c.chunk_id: c.text for c in chunks if c.chunk_id}

    supported_claims: list[str] = []
    unsupported_claims: list[str] = []
    missing_sources: list[str] = []

    # ── Strategy 1: Use rich_citations (structured, most reliable) ─────
    if rich_citations:
        for rc in rich_citations:
            chunk_text = chunk_map.get(rc.chunk_id, "")
            if not chunk_text:
                # Check preview as fallback
                if rc.preview:
                    supported_claims.append(f"[{rc.chunk_id}] {rc.document} (preview match)")
                else:
                    missing_sources.append(rc.chunk_id)
                continue

            # Verify the citation preview appears in the chunk text
            if rc.preview:
                preview_words = set(re.findall(r"[a-zA-Z]{4,}", rc.preview.lower()))
                chunk_lower = chunk_text.lower()
                matched = sum(1 for w in preview_words if w in chunk_lower)
                if preview_words and matched / len(preview_words) >= 0.3:
                    supported_claims.append(f"[{rc.chunk_id}] {rc.document}")
                else:
                    unsupported_claims.append(f"[{rc.chunk_id}] preview not in chunk")
            else:
                # No preview — trust that the RAG linked it correctly
                supported_claims.append(f"[{rc.chunk_id}] {rc.document} (no preview)")

    # ── Strategy 2: Scan citations[] for inline [chk_xxx] in answer ───
    elif citations:
        for cite_id in citations:
            if cite_id not in chunk_map:
                missing_sources.append(cite_id)
                continue

            chunk_text = chunk_map[cite_id].lower()

            # Find the sentence near the citation tag in the answer
            pattern = rf"([^.!?]*?)\[?{re.escape(cite_id)}\]?"
            matches = re.findall(pattern, answer, re.IGNORECASE)

            if not matches:
                # Citation exists in list but not inline in answer text
                # Still count as supported — RAG listed it as a source
                supported_claims.append(f"[{cite_id}] (listed source)")
                continue

            for claim_text in matches:
                claim_text = claim_text.strip()
                if not claim_text:
                    continue
                words = set(re.findall(r"[a-zA-Z]{4,}", claim_text.lower()))
                if not words:
                    supported_claims.append(f"[{cite_id}] {claim_text[:60]}")
                    continue
                matched = sum(1 for w in words if w in chunk_text)
                if matched / len(words) >= 0.3:
                    supported_claims.append(f"[{cite_id}] {claim_text[:60]}")
                else:
                    unsupported_claims.append(f"[{cite_id}] {claim_text[:60]}")

    # ── Strategy 3: Verify expected_sources from dataset ──────────────
    if dataset_item.expected_sources:
        # Build set of all cited source identifiers from every available field
        cited_sources: set[str] = set()

        # PRIMARY: rich_citations.document = original PDF filename uploaded by user
        for rc in rich_citations:
            if rc.document:
                name = rc.document.lower().replace(".pdf", "")
                cited_sources.add(name)
                # Also add without numeric prefix if name like "145752353628ET" → "et"
                # We don't strip — keep full name for accurate matching

        # SECONDARY: chunks metadata.file_name = UUID filename
        for c in chunks:
            fname = c.metadata.get("file_name", "")
            if fname:
                cited_sources.add(fname.lower().replace(".pdf", ""))

        expected_set = {s.lower().replace(".pdf", "") for s in dataset_item.expected_sources}

        # Match strategies (in order of reliability):
        truly_missing = []
        for exp in expected_set:
            found = any(
                exp == cited                         # exact match
                or exp in cited                      # exp is substring of cited
                or cited in exp                      # cited is substring of exp
                or (len(exp) >= 6 and cited.startswith(exp[:6]))  # prefix match (UUID or name start)
                or (len(cited) >= 6 and exp.startswith(cited[:6]))
                for cited in cited_sources
            )
            if not found:
                truly_missing.append(exp)

        for m in truly_missing:
            missing_sources.append(f"Expected source '{m}' not found in citations")

    # ── Score ─────────────────────────────────────────────────────────
    total = len(supported_claims) + len(unsupported_claims) + len(missing_sources)
    citation_score = round(len(supported_claims) / max(total, 1), 4)

    if unsupported_claims:
        failures.append(FailureRecord(
            question_id=dataset_item.id,
            failure_type=FailureType.CITATION_FAILURE,
            reason=f"Unsupported claims: {unsupported_claims[:3]}",
        ))

    if missing_sources:
        failures.append(FailureRecord(
            question_id=dataset_item.id,
            failure_type=FailureType.CITATION_FAILURE,
            reason=f"Missing sources: {missing_sources[:3]}",
        ))

    return (
        CitationMetrics(
            citation_score=citation_score,
            supported_claims=supported_claims,
            unsupported_claims=unsupported_claims,
            missing_sources=missing_sources,
        ),
        failures,
    )
