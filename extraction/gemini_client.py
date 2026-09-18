"""
gemini_client.py
─────────────────
Shared utilities for Gemini Vision extraction from scanned PDFs.

Responsibilities:
  - Initialise the google-genai Client from GEMINI_API_KEY env variable.
  - Render a single PDF page to JPEG bytes using PyMuPDF (fitz).
  - call_gemini()       → single-page API call (backward compatible).
  - call_gemini_batch() → NEW: send up to 5 page images in ONE API call,
                          reducing request count by 5× (500 pages = 100 requests).

Rollback Key Rotation (5 keys in .env):
  - Daily quota exhausted  → key permanently skipped for this Python session.
  - RPM / temporary error  → 15-second cool-down, then try next key (key stays active).
  - All keys exhausted     → raise RuntimeError.

Usage:
    from extraction.gemini_client import get_gemini_client, call_gemini, call_gemini_batch
"""

import os
import re
import time
import json
import logging
from pathlib import Path
from typing import List

import fitz  # PyMuPDF

logger = logging.getLogger("gemini_client")

# gemini-3.8-flash: Latest stable Flash model — best quality, fast, high daily quota.
GEMINI_MODEL = "gemini-3.8-flash"

# ── Batch settings ─────────────────────────────────────────────────────────────
MAX_BATCH_PAGES = 5   # pages per API call — sweet-spot for token budget & quality

# ── Page render settings ───────────────────────────────────────────────────────
# Reduced from 150 → 110 DPI:
#   5 pages × ~0.9 MB each ≈ 4.5 MB total — well under Gemini's 20 MB inline limit.
#   ~36% fewer input tokens vs 150 DPI while preserving OCR-readable text sharpness.
#   Updated to 5 batch pages.
PAGE_RENDER_DPI   = 110
PAGE_JPEG_QUALITY = 75
MAX_IMAGE_BYTES   = 3 * 1024 * 1024   # 3 MB per-page guard — re-render at 80 DPI if exceeded

# ── Rollback settings ──────────────────────────────────────────────────────────
# Keys whose DAILY quota is exhausted — permanently skipped for this Python session.
_EXHAUSTED_KEY_INDICES: set = set()
# Seconds to sleep before retrying the SAME key after a temporary RPM error.
RPM_COOLDOWN_SECONDS = 10
# Max retries on the same key before rolling over to the next key.
# Retrying 3 times with a 10s wait allows the rate limit to clear naturally
# and prevents rapid rotation that looks like spamming.
MAX_RPM_RETRIES = 3


# ── SDK import ─────────────────────────────────────────────────────────────────
try:
    from google import genai
    from google.genai import types as genai_types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logger.warning("google-genai SDK not installed. Run: pip install google-genai")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_api_keys() -> List[str]:
    """Parse GEMINI_API_KEY from env — supports comma/semicolon separated list."""
    raw = os.environ.get("GEMINI_API_KEY", "").strip()
    return [k.strip() for k in re.split(r"[,;]", raw) if k.strip()]


def is_daily_quota_error(exc: Exception) -> bool:
    """
    Return True if exception signals a HARD daily quota exhaustion.
    Return False for temporary RPM / per-minute rate-limit errors.
    """
    err_str = str(exc).lower()
    
    # If the error tells us to retry in a short amount of time, it is temporary RPM
    if "retry in" in err_str or "retry_delay" in err_str or "retrydelay" in err_str:
        return False
        
    # If it specifically mentions minute, it is temporary RPM
    if "minute" in err_str or "requestsperminute" in err_str or "rpm" in err_str:
        return False

    if "requestsperday" in err_str:
        return True
        
    if "generate_content_free_tier_requests" in err_str:
        # Check if the error explicitly mentions day/daily, meaning we hit the 1500 limit
        if "day" in err_str or "daily" in err_str:
            return True
        # Default to False (RPM) to prevent permanently disabling working keys on vague 429 errors
        return False
        
    if "daily" in err_str or "per day" in err_str:
        return True
        
    return False


def _safety_settings() -> list:
    """Return BLOCK_NONE safety settings for all harm categories."""
    return [
        genai_types.SafetySetting(
            category=genai_types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            threshold=genai_types.HarmBlockThreshold.BLOCK_NONE,
        ),
        genai_types.SafetySetting(
            category=genai_types.HarmCategory.HARM_CATEGORY_HARASSMENT,
            threshold=genai_types.HarmBlockThreshold.BLOCK_NONE,
        ),
        genai_types.SafetySetting(
            category=genai_types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            threshold=genai_types.HarmBlockThreshold.BLOCK_NONE,
        ),
        genai_types.SafetySetting(
            category=genai_types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            threshold=genai_types.HarmBlockThreshold.BLOCK_NONE,
        ),
    ]


# ── Client factory ──────────────────────────────────────────────────────────────

def get_gemini_client(key_index: int = 0):
    """
    Build and return a google.genai.Client using GEMINI_API_KEY from env.
    Supports comma/semicolon separated keys for failover rotation.

    Raises:
        ImportError:  If google-genai SDK is not installed.
        RuntimeError: If GEMINI_API_KEY is not set or is the placeholder value.
    """
    if not GENAI_AVAILABLE:
        raise ImportError("google-genai SDK not installed. Run: pip install google-genai")

    api_keys = _load_api_keys()
    if not api_keys or api_keys[0] == "your_gemini_api_key_here":
        raise RuntimeError(
            "GEMINI_API_KEY is not set. "
            "Add it to your .env file:\n"
            "  GEMINI_API_KEY=AIzaSy..."
        )

    selected_key = api_keys[key_index % len(api_keys)]
    return genai.Client(api_key=selected_key)


# ── Page renderer ───────────────────────────────────────────────────────────────

def render_page_to_jpeg(pdf_path: Path, page_number: int) -> bytes:
    """
    Render a single PDF page to JPEG bytes using PyMuPDF at PAGE_RENDER_DPI.

    Args:
        pdf_path:    Path to the PDF file.
        page_number: 1-indexed page number.

    Returns:
        JPEG image as bytes.

    Raises:
        ValueError:        If page_number is out of range.
        FileNotFoundError: If pdf_path does not exist.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)

    if page_number < 1 or page_number > total_pages:
        doc.close()
        raise ValueError(
            f"page_number={page_number} is out of range "
            f"(PDF has {total_pages} pages)."
        )

    page = doc[page_number - 1]
    mat  = fitz.Matrix(PAGE_RENDER_DPI / 72, PAGE_RENDER_DPI / 72)
    pix  = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    jpeg_bytes = pix.tobytes(output="jpeg", jpg_quality=PAGE_JPEG_QUALITY)
    doc.close()

    # Guard: re-render at 80 DPI if a single page image is still too large
    if len(jpeg_bytes) > MAX_IMAGE_BYTES:
        logger.warning(
            f"Page {page_number} image is {len(jpeg_bytes) / 1e6:.1f} MB — "
            f"exceeds {MAX_IMAGE_BYTES / 1e6:.0f} MB per-page guard. "
            f"Re-rendering at 80 DPI."
        )
        doc2 = fitz.open(str(pdf_path))
        mat2 = fitz.Matrix(80 / 72, 80 / 72)
        pix2 = doc2[page_number - 1].get_pixmap(matrix=mat2, colorspace=fitz.csRGB)
        jpeg_bytes = pix2.tobytes(output="jpeg", jpg_quality=65)
        doc2.close()

    return jpeg_bytes


# ── Core rollback rotation engine ───────────────────────────────────────────────

def _execute_with_rollback(contents: list) -> str:
    """
    Internal: Send 'contents' to Gemini with full rollback key rotation.

    Rotation rules (per-page, slow-and-steady):
      • RPM / temp error   → retry the SAME key up to MAX_RPM_RETRIES times,
                             sleeping RPM_COOLDOWN_SECONDS (60s) between each attempt.
                             If all retries on this key fail → roll to next key.
      • Daily quota error  → permanently mark key as exhausted, roll to next key immediately.
      • All keys exhausted → raise RuntimeError (caller saves progress and exits cleanly).

    Args:
        contents: The contents list to pass to generate_content().

    Returns:
        Raw text response string from Gemini.
    """
    api_keys = _load_api_keys()
    if not api_keys:
        raise RuntimeError("No API keys configured in GEMINI_API_KEY.")

    available_indices = [i for i in range(len(api_keys)) if i not in _EXHAUSTED_KEY_INDICES]
    if not available_indices:
        raise RuntimeError(
            f"All {len(api_keys)} configured API keys have exhausted their daily quota."
        )

    last_exception = None

    for idx in available_indices:
        key    = api_keys[idx]
        masked = f"{key[:8]}..." if len(key) > 8 else "***"
        client = genai.Client(api_key=key)

        # ── Per-key retry loop for RPM/temp errors ──────────────────────────
        for attempt in range(1, MAX_RPM_RETRIES + 1):
            try:
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=contents,
                    config=genai_types.GenerateContentConfig(
                        safety_settings=_safety_settings(),
                        temperature=0.0,   # deterministic for extraction
                    ),
                )

                # Check for safety / content blocks
                if response.candidates:
                    finish_reason = str(
                        getattr(response.candidates[0], "finish_reason", "")
                    ).upper()
                    if finish_reason in ("SAFETY", "RECITATION", "BLOCKED"):
                        logger.warning(
                            f"[rollback] Key {idx} — response blocked. Reason: {finish_reason}"
                        )
                        return ""

                return response.text or ""   # ✅ SUCCESS

            except Exception as exc:
                last_exception = exc

                if is_daily_quota_error(exc):
                    # Hard daily limit — permanently exhaust this key, no point retrying
                    _EXHAUSTED_KEY_INDICES.add(idx)
                    logger.warning(
                        f"[rollback] Key {idx} ({masked}) hit DAILY quota limit. "
                        f"Marked permanently exhausted. Rolling to next key..."
                    )
                    break   # exit retry loop → roll to next key

                else:
                    # Temporary RPM / network / server error
                    if attempt < MAX_RPM_RETRIES:
                        logger.warning(
                            f"[rollback] Key {idx} ({masked}) — temp error "
                            f"(attempt {attempt}/{MAX_RPM_RETRIES}): {exc}. "
                            f"Waiting {RPM_COOLDOWN_SECONDS}s before retry..."
                        )
                        time.sleep(RPM_COOLDOWN_SECONDS)
                    else:
                        # All retries on this key exhausted → roll to next key
                        logger.warning(
                            f"[rollback] Key {idx} ({masked}) failed all "
                            f"{MAX_RPM_RETRIES} attempts. Rolling to next key..."
                        )

    logger.error(f"[rollback] All available keys failed for model {GEMINI_MODEL}.")
    raise last_exception or RuntimeError("All API keys failed.")


# ── Single-page caller (backward compatible) ────────────────────────────────────

def call_gemini(client, image_bytes: bytes, prompt: str) -> str:
    """
    Send a single JPEG image + text prompt to Gemini 3.5 Flash and return raw text.

    Uses _execute_with_rollback() internally for automatic key rotation.
    The 'client' argument is accepted for backward compatibility but is not used
    — rotation builds fresh clients per key internally.

    Args:
        client:      A google.genai.Client instance (kept for backward compat).
        image_bytes: JPEG bytes of the rendered page.
        prompt:      Instruction text for Gemini.

    Returns:
        Raw text response from Gemini.
    """
    contents = [
        genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
        prompt,
    ]
    return _execute_with_rollback(contents)


# ── Batch prompt template ───────────────────────────────────────────────────────

_BATCH_PROMPT_TEMPLATE = """You are a precise OCR and document structure extractor for scanned PDFs.

You are given {n} scanned PDF page images IN ORDER (Page 1 is the first image, Page {n} is the last).

For EACH page image, extract ALL visible text into a structured JSON object.

RULES:
1. Extract every visible word and sentence accurately — no hallucination, no additions.
2. Classify each text unit with a block type:
   - "heading"    → section/chapter titles (bold, larger font, numbered like 1.1, 2.3)
   - "subheading" → sub-section titles
   - "paragraph"  → regular body text
   - "list_item"  → bullet points or numbered list items
   - "caption"    → figure/diagram captions
3. For TABLES: extract as a separate entry in the "tables" list.
   Use rows as arrays of cell strings: {{"rows": [["header1","header2"],["val1","val2"]]}}
4. SKIP completely: watermarks, Telegram channel headers, standalone page numbers, footer lines.
5. If a page is blank or has only watermarks/boilerplate: set "is_blank": true with empty lists.
6. Wrap key bold terms with **double asterisks** to preserve emphasis.

OUTPUT — return a JSON ARRAY of exactly {n} page objects in order:
[
  {{
    "page_num": <integer printed on the page, or 1-based sequential index>,
    "text_blocks": [
      {{"type": "heading",   "text": "..."}},
      {{"type": "paragraph", "text": "..."}},
      {{"type": "list_item", "text": "..."}}
    ],
    "tables": [
      {{"rows": [["col1","col2"],["val1","val2"]]}}
    ],
    "is_blank": false
  }}
]

Return ONLY the JSON array — no explanation, no markdown code fences, no extra text."""


# ── Batch caller (NEW — 5 pages per request) ────────────────────────────────────

def call_gemini_batch(images_bytes: List[bytes], page_nums: List[int]) -> List[dict]:
    """
    Send a batch of up to MAX_BATCH_PAGES (5) JPEG images in ONE Gemini API call.

    This reduces total API request count by 5×:
        500 pages / 5 = 100 requests instead of 500.
    Combined with 5 rollback keys (7,500 RPD):
        100 requests per PDF × 20 PDFs = 2,000 requests/day — well within limits.

    Uses _execute_with_rollback() for automatic key rotation.

    Args:
        images_bytes: List of JPEG byte strings, one per page (max MAX_BATCH_PAGES).
        page_nums:    Corresponding 1-indexed page numbers (used for logging/output).

    Returns:
        List of page dicts, one per page in the same order as images_bytes:
        [{"page_num": N, "text_blocks": [...], "tables": [...], "is_blank": bool}, ...]

    Raises:
        RuntimeError: If all API keys are exhausted.
        ValueError:   If more than MAX_BATCH_PAGES images are passed.
    """
    n = len(images_bytes)
    if n == 0:
        return []
    if n > MAX_BATCH_PAGES:
        raise ValueError(f"call_gemini_batch: max {MAX_BATCH_PAGES} pages per call, got {n}.")

    # Build contents: all images first, then the batch prompt
    contents = []
    for img_bytes in images_bytes:
        contents.append(
            genai_types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
        )
    contents.append(_BATCH_PROMPT_TEMPLATE.format(n=n))

    raw = _execute_with_rollback(contents)
    return _parse_batch_response(raw, page_nums)


def _parse_batch_response(raw: str, page_nums: List[int]) -> List[dict]:
    """
    Parse Gemini's batch JSON array response into a list of page dicts.
    Falls back gracefully if JSON is malformed or incomplete.
    """
    fallback = [
        {"page_num": pn, "text_blocks": [], "tables": [], "is_blank": True}
        for pn in page_nums
    ]

    if not raw or not raw.strip():
        logger.warning("[batch_parse] Empty response from Gemini — returning blank pages.")
        return fallback

    cleaned = raw.strip()

    # Strip accidental markdown code fences (```json ... ```)
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning(
            f"[batch_parse] JSON decode failed ({exc}). "
            f"Saving raw text as paragraph for all {len(page_nums)} page(s)."
        )
        return [
            {
                "page_num":   pn,
                "text_blocks": [{"type": "paragraph", "text": cleaned[:4000]}],
                "tables":      [],
                "is_blank":    False,
            }
            for pn in page_nums
        ]

    # Normalize: Gemini may return a single dict for a 1-page batch
    if isinstance(data, dict):
        data = [data]

    results = []
    for i, pn in enumerate(page_nums):
        if i < len(data):
            entry = data[i] if isinstance(data[i], dict) else {}
        else:
            logger.warning(
                f"[batch_parse] Expected {len(page_nums)} items, got {len(data)}. "
                f"Padding page {pn} as blank."
            )
            entry = {}

        page_result = {
            "page_num":   entry.get("page_num", pn),
            "text_blocks": entry.get("text_blocks", []),
            "tables":      entry.get("tables", []),
            "is_blank":    entry.get("is_blank", False),
        }
        # Auto-flag blank if both lists are empty
        if not page_result["text_blocks"] and not page_result["tables"]:
            page_result["is_blank"] = True

        results.append(page_result)

    return results
