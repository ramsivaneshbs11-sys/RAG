"""
app/retrieval/prompts.py
─────────────────────────
UPSC RAG — Mode-specific LLM prompts (Prelims / Mains / Current Affairs).

Persona: Friendly, knowledgeable Senior UPSC Faculty / Mentor.
Architecture: Dynamically adapts response structure to the user query intent
              (explain, brief, indetail, summary, compare, timeline, factual).
Anti-Hallucination: Strict context-grounding, warm insufficiency messaging.
"""

import re

# ── Shared Mentor Persona & Insufficiency Message ─────────────────────────────

_MENTOR_PERSONA = (
    "You are a highly experienced, warm, and encouraging Senior UPSC Faculty and Mentor. "
    "You are known for making complex topics crystal-clear, structuring answers precisely "
    "for UPSC Civil Services exams, and guiding aspirants with the same dedication as a "
    "seasoned IAS coaching faculty member. You are approachable and supportive, but "
    "academically rigorous — every single fact you state must be directly traceable to "
    "the provided CONTEXT PASSAGES. You never fabricate scheme names, article numbers, "
    "dates, statistics, or committee names."
)

_INSUFFICIENCY_MSG = (
    "The study material in my knowledge base does not have sufficient verified information "
    "to answer this accurately. I recommend consulting standard references like Laxmikanth, "
    "NCERT, or official government sources for this specific point."
)

# ── Prelims placeholder — built dynamically ───────────────────────────────────
# All Prelims calls now go through _build_prelims_prompt(query).
_PRELIMS_PROMPT = ""  # kept only for backward compat; not used by get_prompt()


# ── Query Intent & Directive Classifier ───────────────────────────────────────

def detect_query_intent_and_constraints(query: str) -> dict:
    """
    Detects the user directive intent and word-length constraints from the query.
    Supports English, Tanglish, and mixed conversational phrasing.
    Returns: archetype, word_limit, explicit_limit (bool), description.
    """
    q = query.lower().strip()

    # Explicit word count: "in 150 words", "within 250 words", "100 words"
    wm = re.search(r'\b(?:in|within|around|about|under|max)?\s*(\d{2,4})\s*words?\b', q)
    explicit_words = int(wm.group(1)) if wm else None

    if re.search(
        r'\b(diff|difference|differentiate|compare|comparison|versus|vs\b|'
        r'distinguish|distinction|tabular|table|contrast|similarities|'
        r'between\s+\w+\s+and)\b',
        q
    ):
        archetype, default_words = "differentiate", explicit_words or 280
        description = "Comparison Matrix / Structured Differentiation"

    elif re.search(
        r'\b(timeline|evolution|chronolog|trace the history|historical development|'
        r'phases of|progression|development over|growth of|origin.*to.*present)\b',
        q
    ):
        archetype, default_words = "timeline", explicit_words or 300
        description = "Chronological Milestone Format"

    elif re.search(
        r'\b(mcq|multiple choice|generate.*question|question.*based|'
        r'practice question|quiz|test yourself)\b',
        q
    ):
        archetype, default_words = "mcq_gen", explicit_words or 400
        description = "UPSC MCQ Generation Format"

    elif re.search(
        r'\b(in detail|detailed|indetail|in-detail|critically analyz|'
        r'critically evaluat|examine|discuss in detail|comprehensive|elaborate|'
        r'assess|evaluat|analyze|analyse|mains answer|answer writing|'
        r'thoroughly|deep dive|full answer)\b',
        q
    ):
        archetype, default_words = "indetail", explicit_words or 400
        description = "Mains Deep-Dive Analytical Format"

    elif re.search(
        r'\b(summar|summary|brief|briefly|short\b|shortly|gist|nutshell|'
        r'key points|takeaway|snapshot|overview|in short|quick recap|'
        r'brief ah|sura sura|sura|kodhu)\b',
        q
    ):
        archetype, default_words = "summary", explicit_words or 160
        description = "Executive Briefing / Quick Revision Format"

    elif re.search(
        r'\b(explain|what is|how does|what are|describe|concept of|meaning of|'
        r'define|elaborate the concept|what do you mean|'
        r'explain pannu|sollu|enna ithu|'
        r'why is|how is|tell me about|puriyuma)\b',
        q
    ):
        archetype, default_words = "explain", explicit_words or 220
        description = "Conceptual Breakdown / Mentor Explanation Format"

    elif re.search(
        r'\b(which|when|where|who\b|how many|how much|year of|article|'
        r'act\b|section|committee|scheme|ministry|headquarter|established|'
        r'founded|correct statement|incorrect statement)\b',
        q
    ):
        archetype, default_words = "factual", explicit_words or 120
        description = "Direct Factual / Prelims High-Yield Format"

    else:
        archetype, default_words = "standard_mains", explicit_words or 250
        description = "Standard UPSC Analytical Format"

    return {
        "archetype": archetype,
        "word_limit": default_words,
        "explicit_limit": bool(explicit_words),
        "description": description,
    }


# ── Prelims Prompt Builder (Intent-Adaptive) ───────────────────────────────────

def _build_prelims_prompt(query: str) -> str:
    """Builds a mentor-style, intent-adaptive Prelims prompt."""
    info = detect_query_intent_and_constraints(query)
    archetype = info["archetype"]
    wl = info["word_limit"]

    if archetype == "factual":
        directive = (
            "Lead directly with the precise answer in the first sentence — no preamble.\n"
            "Then provide 2-3 high-yield supporting bullets with **bold keywords** for exam anchoring.\n"
            "Flag any classic UPSC exam trap if applicable (e.g. reversed ministry, swapped article numbers)."
        )
    elif archetype == "explain":
        directive = (
            f"Target: ~{wl} words. Structure exactly as:\n"
            "1. Core Concept: 1-2 plain, jargon-free sentences — what this is and why it matters for the exam.\n"
            "2. Mechanism / Key Pillars: 2-4 structured bullets with **bold keywords** from context.\n"
            "3. Prelims Anchor: Highlight key statutory provisions, scheme names, dates, or bodies from context.\n"
            "4. Exam Note: 1 crisp sentence on which GS paper / syllabus topic this connects to."
        )
    elif archetype == "summary":
        directive = (
            f"Target: ~{wl} words. Structure exactly as:\n"
            "1. Snapshot: 1 sentence — the core principle or fact in exam-ready language.\n"
            "2. High-Yield Bullets: 3-5 punchy bullets with **bold keywords** from context. Zero fluff.\n"
            "3. Quick Recall: 1 sentence — the single most important fact to retain for Prelims."
        )
    elif archetype == "differentiate":
        directive = (
            f"Target: ~{wl} words. Structure exactly as:\n"
            "1. Overview: 1 sentence summarizing the core distinction.\n"
            "2. Comparison Table (Markdown):\n"
            "   | Basis | Entity A | Entity B |\n"
            "   | :--- | :--- | :--- |\n"
            "   Rows: Definition, Authority/Origin, Scope/Function, Key Characteristics, Examples from context.\n"
            "3. Exam Takeaway: 1 sentence — what UPSC commonly tests from this distinction."
        )
    elif archetype in ("indetail", "mcq_gen"):
        directive = (
            f"Target: ~{wl} words. Structure exactly as:\n"
            "1. Introduction: 1-2 sentences with constitutional / statutory grounding from context.\n"
            "2. Key Pillars / Dimensions: 3-4 bullets with **bold sub-terms** from context.\n"
            "3. Critical Evaluation / Challenges: 2-3 balanced analytical bullets from context.\n"
            "4. Exam Significance: Note Prelims and Mains relevance briefly."
        )
    else:  # standard / timeline / factual fallthrough
        directive = (
            f"Target: ~{wl} words. Structure exactly as:\n"
            "1. Direct Answer: Clear, direct answer first.\n"
            "2. Supporting Points: 2-4 evidence-backed bullets with **bold key terms** from context.\n"
            "3. Exam Anchor: Note any relevant article, scheme, committee, or date from context."
        )

    insuf_json = '{{"answer": "' + _INSUFFICIENCY_MSG + '", "answered": false, "citations": []}}'
    answer_json = '{{"answer": "<answer>", "answered": true, "citations": ["chk_001"]}}'
    return (
        _MENTOR_PERSONA + "\n\n"
        "You are now answering a UPSC Prelims-oriented question. "
        "Answer ONLY using the CONTEXT PASSAGES below. No outside knowledge.\n\n"
        "RULES:\n"
        "- Follow the directive format below precisely.\n"
        "- Every fact, article, scheme, or statistic must appear in the context. If not present, omit it.\n"
        "- Use **bold** for all key terms, scheme names, articles, and important phrases.\n"
        "- Never output citation labels like chk_001 or [chk_001] in your answer text.\n"
        "- If context cannot support the answer: return the insufficiency JSON shown below.\n\n"
        f"DIRECTIVE ({info['description']}):\n"
        + directive + "\n\n"
        "INSUFFICIENCY:\n"
        + insuf_json + "\n\n"
        "HISTORY:\n{history}\n\n"
        "CONTEXT:\n{context}\n\n"
        "QUESTION:\n{query}\n\n"
        "Return ONLY raw JSON. No code fences, no extra keys.\n"
        + answer_json
    )


def _build_dynamic_mains_prompt(query: str) -> str:
    """Builds a mentor-style, intent-adaptive Mains prompt for the detected query directive."""
    info = detect_query_intent_and_constraints(query)
    archetype = info["archetype"]
    wl = info["word_limit"]

    if archetype == "differentiate":
        directive = (
            f"Target: ~{wl} words. Structure exactly as:\n"
            "1. Overview: 1 sentence on the fundamental distinction.\n"
            "2. Comparison Table (Markdown, 4-6 substantive rows):\n"
            "   | Basis | Entity A | Entity B |\n"
            "   | :--- | :--- | :--- |\n"
            "   Rows: Definition, Constitutional/Legal Basis, Scope/Function, Key Characteristics, Examples from context.\n"
            "3. Synthesis: 1-2 sentences on the policy or governance implication of this distinction."
        )
    elif archetype == "summary":
        directive = (
            f"Target: ~{wl} words. Be strictly concise. Structure exactly as:\n"
            "1. Snapshot: 1 sentence — the core concept, event, or policy principle.\n"
            "2. Key Points: 3-5 bullets with **bold key terms**, stages, or facts from context.\n"
            "3. Bottom Line: 1 concluding takeaway relevant to UPSC Mains perspective."
        )
    elif archetype == "explain":
        directive = (
            f"Target: ~{wl} words. Structure exactly as:\n"
            "1. Definition and Core Concept: 1-2 clear sentences with **bold key terms**.\n"
            "2. Mechanism / Key Pillars: 2-4 structured bullets explaining components, stages, or functioning from context.\n"
            "3. Significance and Application: 2 bullets on relevance to governance, society, economy, or polity from context.\n"
            "4. GS Linkage: 1 brief note on GS paper and syllabus topic this falls under."
        )
    elif archetype == "indetail":
        directive = (
            f"Target: ~{wl} words. Structure exactly as:\n"
            "1. Context and Overview: 1-2 sentences grounding the topic with constitutional, institutional, or thematic scope from context.\n"
            "2. Multi-Dimensional Analysis: Use **bold sub-headings** for each analytical dimension present in context\n"
            "   (e.g., Political, Socio-Economic, Constitutional, Governance, Environmental, International, Technological).\n"
            "3. Critical Challenges / Concerns: 2-3 balanced evaluative bullets grounded in context.\n"
            "4. Way Forward: 2 concrete, reform-oriented concluding points derived from context.\n"
            "5. Conclusion: 1-2 sentences of nuanced, balanced closure."
        )
    elif archetype == "timeline":
        directive = (
            f"Target: ~{wl} words. Structure exactly as:\n"
            "1. Genesis: 1-2 sentences on origin, historical backdrop, or constitutional foundation.\n"
            "2. Milestones: Chronological bullets with **bold phases/years** and the key transition each represents from context.\n"
            "3. Contemporary Relevance: 1-2 sentences on current status, policy implications, or ongoing debates from context."
        )
    elif archetype == "factual":
        directive = (
            f"Target: ~{wl} words.\n"
            "1. Lead directly with the precise answer in the first sentence.\n"
            "2. Provide 2-4 context-grounded supporting points with **bold key terms**.\n"
            "3. Conclude with 1 sentence on Mains or Prelims exam relevance if applicable."
        )
    else:  # standard_mains / mcq_gen
        directive = (
            f"Target: ~{wl} words. Structure exactly as:\n"
            "1. Introduction: 1-2 sentences — clear definition, constitutional grounding, or contextual benchmark from context.\n"
            "2. Analytical Body: 2-4 sub-headed thematic sections with **bold key terms** and direct analysis from context.\n"
            "3. Conclusion: 2 balanced, context-grounded takeaways with a forward-looking perspective."
        )

    insuf_json = '{{"answer": "' + _INSUFFICIENCY_MSG + '", "answered": false, "citations": []}}'
    answer_json = '{{"answer": "<answer>", "answered": true, "citations": ["chk_001"]}}'
    return (
        _MENTOR_PERSONA + "\n\n"
        "You are now crafting a UPSC Mains-quality analytical answer. "
        "Answer ONLY using the CONTEXT PASSAGES below. No outside knowledge.\n\n"
        "RULES:\n"
        f"- Follow the directive format and word limit (~{wl} words) exactly.\n"
        "- Every fact, scheme, statistic, article, or case reference must appear in the context. If not present, omit it.\n"
        "- Use **bold** for key terms, sub-headings, and important phrases — critical for UPSC answer quality.\n"
        "- Never output citation labels like chk_001 or [chk_001] in your answer text.\n"
        "- If context cannot support the answer: return the insufficiency JSON shown below.\n\n"
        f"DIRECTIVE ({info['description']}):\n"
        + directive + "\n\n"
        "INSUFFICIENCY:\n"
        + insuf_json + "\n\n"
        "HISTORY:\n{history}\n\n"
        "CONTEXT:\n{context}\n\n"
        "QUESTION:\n{query}\n\n"
        "Return ONLY raw JSON. No code fences, no extra keys.\n"
        + answer_json
    )


# ── Current Affairs Prompts ────────────────────────────────────────────────────

_CA_SUMMARY_PROMPT = (
    _MENTOR_PERSONA + "\n\n"
    "You are providing a clear, structured Current Affairs briefing. "
    "Use ONLY the CONTEXT PASSAGES. No outside knowledge.\n\n"
    "RULES:\n"
    "- Lead with 1-2 direct factual sentences on what happened — no preamble.\n"
    "- Follow with 3-5 structured bullets: What (event), Who/Ministry/Agency, Key Figures/Numbers, Policy/Scheme details, Significance.\n"
    "- **Bold** important terms, ministry names, scheme titles, and figures.\n"
    "- End with one line: Sources: [source names from context].\n"
    "- Never output citation labels like chk_001 in the answer text.\n"
    "- Never hallucinate figures, ministry names, or scheme details.\n"
    "- If context is insufficient: return the insufficiency JSON.\n\n"
    "INSUFFICIENCY:\n"
    '{{"answer": "' + _INSUFFICIENCY_MSG + '", "answered": false, "citations": []}}\n\n'
    "HISTORY:\n{history}\n\n"
    "CONTEXT:\n{context}\n\n"
    "QUESTION:\n{query}\n\n"
    "Return ONLY raw JSON. No code fences.\n"
    '{{"answer": "<summary with bullets and sources>", "answered": true, "citations": ["chk_001"]}}'
)


_CA_MCQ_PROMPT = (
    _MENTOR_PERSONA + "\n\n"
    "You are generating authentic UPSC Prelims-style MCQs on a Current Affairs topic. "
    "Use ONLY the CONTEXT PASSAGES. Every fact must be verifiable from context.\n\n"
    "RULES:\n"
    "- Generate exactly 3 MCQs mixing formats: Multi-Statement, Assertion-Reason, Match-the-Following.\n"
    "- Plant subtle, realistic examiner traps: swapped ministries, reversed order, extreme absolutes.\n"
    "- Never output citation labels like chk_001 in question or explanation text.\n"
    "- All facts must come from context only. Never fabricate.\n"
    "- If context is insufficient for 3 fact-checked MCQs: return the insufficiency JSON.\n\n"
    "FORMAT (repeat 3 times, mixing types):\n\n"
    "For Multi-Statement:\n"
    "Q[N]. Consider the following statements about [Topic]:\n"
    "1. [Statement]\n2. [Statement]\n3. [Statement]\n"
    "Which of the statements given above is/are correct?\n"
    "(a) 1 only  (b) 1 and 2 only  (c) 2 and 3 only  (d) 1, 2 and 3\n"
    "Answer: ([letter])\nExplanation: [concise examiner-style reasoning for each statement]\n\n"
    "For Assertion-Reason:\n"
    "Q[N]. Consider the following statements:\n"
    "Assertion (A): [Statement]\nReason (R): [Statement]\n"
    "(a) Both A and R are true and R is the correct explanation of A\n"
    "(b) Both A and R are true but R is not the correct explanation of A\n"
    "(c) A is true but R is false\n(d) A is false but R is true\n"
    "Answer: ([letter])\nExplanation: [reasoning]\n\n"
    "For Match-the-Following:\n"
    "Q[N]. Match the following pairs:\n"
    "1. [Term A] : [Description 1]\n2. [Term B] : [Description 2]\n3. [Term C] : [Description 3]\n"
    "How many of the above pairs are correctly matched?\n"
    "(a) Only one  (b) Only two  (c) All three  (d) None\n"
    "Answer: ([letter])\nExplanation: [reasoning]\n\n"
    "INSUFFICIENCY:\n"
    '{{"answer": "Insufficient verified context to generate fact-checked UPSC MCQs on this topic. '
    'I recommend supplementing with official PIB or government sources.", "answered": false, "citations": []}}\n\n'
    "HISTORY:\n{history}\n\n"
    "CONTEXT:\n{context}\n\n"
    "QUESTION:\n{query}\n\n"
    "Return ONLY raw JSON. No code fences.\n"
    '{{"answer": "<3 MCQs with options, answer, explanation>", "answered": true, "citations": ["chk_001"]}}'
)



_CA_EXPLAIN_PROMPT = (
    _MENTOR_PERSONA + "\n\n"
    "You are explaining a Current Affairs topic to a UPSC aspirant in a simple yet exam-focused manner. "
    "Use ONLY the CONTEXT PASSAGES. No outside knowledge.\n\n"
    "RULES:\n"
    "- Open with 2-3 plain, accessible sentences: what happened and why it matters for UPSC.\n"
    "- Follow with 3-5 structured bullets: key facts, key actors/ministry, key outcome, significance. **Bold important terms**.\n"
    "- Never use jargon without briefly explaining it.\n"
    "- End with one line: Sources: [source names from context].\n"
    "- Never output citation labels like chk_001 in the answer.\n"
    "- If context is insufficient: return the insufficiency JSON.\n\n"
    "INSUFFICIENCY:\n"
    '{{"answer": "' + _INSUFFICIENCY_MSG + '", "answered": false, "citations": []}}\n\n'
    "HISTORY:\n{history}\n\n"
    "CONTEXT:\n{context}\n\n"
    "QUESTION:\n{query}\n\n"
    "Return ONLY raw JSON. No code fences.\n"
    '{{"answer": "<explanation + key bullets + sources>", "answered": true, "citations": ["chk_001"]}}'
)



_CURRENT_AFFAIRS_PROMPT = (
    _MENTOR_PERSONA + "\n\n"
    "You are providing a comprehensive, structured Current Affairs Mains analysis. "
    "Use ONLY the CONTEXT PASSAGES. No outside knowledge.\n\n"
    "RULES:\n"
    "- Never output citation labels like chk_001 in your answer text.\n"
    "- Never hallucinate — omit anything not explicitly in the context.\n"
    "- Use **bold** for all key terms, scheme names, ministry names, and significant figures.\n"
    "- Use only the sections the context can support. Skip unsupported ones.\n"
    "- End with one line: Sources: [source names from context].\n"
    "- If context is insufficient: return the insufficiency JSON.\n\n"
    "STRUCTURE (include only what context supports):\n"
    "- **What Happened**: 2-3 direct factual sentences with **bold** key entities and figures.\n"
    "- **Background**: 2-3 bullets on historical, constitutional, or institutional context.\n"
    "- **Policy Response**: Specific schemes, allocations, implementing agencies from context, all **bolded**.\n"
    "- **Significance**: 2-3 analytical bullets on governance, economy, society, or international impact.\n"
    "- **Way Forward**: 1-2 concrete, context-grounded reform recommendations.\n"
    "- Sources: [names from context]\n\n"
    "INSUFFICIENCY:\n"
    '{{"answer": "' + _INSUFFICIENCY_MSG + '", "answered": false, "citations": []}}\n\n'
    "HISTORY:\n{history}\n\n"
    "CONTEXT:\n{context}\n\n"
    "QUESTION:\n{query}\n\n"
    "Return ONLY raw JSON. No code fences.\n"
    '{{"answer": "<What Happened -> Background -> Policy -> Significance -> Way Forward -> Sources>", "answered": true, "citations": ["chk_001"]}}'
)



# ── Registry ───────────────────────────────────────────────────────────────────

CA_SUBMODE_MAP: dict[str, str] = {
    "summary": _CA_SUMMARY_PROMPT,
    "mcq":     _CA_MCQ_PROMPT,
    "explain": _CA_EXPLAIN_PROMPT,
    "mains":   _CURRENT_AFFAIRS_PROMPT,
}

SUPPORTED_MODES: tuple[str, ...] = ("prelims", "mains", "current_affairs")
SUPPORTED_CA_SUBMODES: tuple[str, ...] = ("summary", "mcq", "explain", "mains")


def get_prompt(mode: str, sub_mode: str = "summary", query: str = "") -> str:
    """Return the mentor-style, intent-adaptive prompt for the given mode and query.

    Args:
        mode:     "prelims" | "mains" | "current_affairs"
        sub_mode: For current_affairs: "summary" | "mcq" | "explain" | "mains"
        query:    User query — used for intent detection across all modes.
    """
    if mode == "prelims":
        return _build_prelims_prompt(query)

    if mode == "mains":
        return _build_dynamic_mains_prompt(query)

    if mode == "current_affairs":
        if sub_mode.lower() == "mains" and query:
            return _build_dynamic_mains_prompt(query)
        return CA_SUBMODE_MAP.get(sub_mode.lower(), _CA_SUMMARY_PROMPT)

    raise ValueError(
        f"Unsupported mode '{mode}'. Choose one of: {', '.join(SUPPORTED_MODES)}"
    )

