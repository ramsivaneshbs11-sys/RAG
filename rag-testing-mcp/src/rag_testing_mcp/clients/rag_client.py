"""
Async HTTP client for communicating with the live RAG API.

Features:
  - Configurable URL and endpoints (no hardcoded localhost)
  - Retry logic with configurable MAX_RETRIES
  - Timeout handling
  - Latency measurement injected into the response
  - Graceful handling of missing response fields ("not_available")
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from rag_testing_mcp.config import Settings
from rag_testing_mcp.models import RAGQueryRequest, RAGQueryResponse

logger = logging.getLogger(__name__)


class RAGClient:
    """Async HTTP client for the target RAG application."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._settings.request_timeout),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Health Check ───────────────────────────────────────────────────
    async def health_check(self) -> dict[str, Any]:
        """GET /health — returns status, url, and response_time_ms."""
        client = await self._get_client()
        url = self._settings.health_url
        start = time.perf_counter()

        for attempt in range(1, self._settings.max_retries + 1):
            try:
                resp = await client.get(url)
                elapsed_ms = (time.perf_counter() - start) * 1000
                resp.raise_for_status()
                data = resp.json()
                return {
                    "status": "healthy",
                    "url": url,
                    "response_time_ms": round(elapsed_ms, 2),
                    "details": data,
                }
            except httpx.TimeoutException:
                logger.warning(f"Health check timeout (attempt {attempt}/{self._settings.max_retries})")
                if attempt == self._settings.max_retries:
                    return {
                        "status": "unreachable",
                        "url": url,
                        "error": f"Timeout after {self._settings.request_timeout}s",
                    }
            except httpx.HTTPStatusError as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000
                return {
                    "status": "error",
                    "url": url,
                    "response_time_ms": round(elapsed_ms, 2),
                    "error": f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
                }
            except httpx.ConnectError:
                return {
                    "status": "unreachable",
                    "url": url,
                    "error": "Connection refused — is the RAG API running?",
                }
            except Exception as exc:
                return {
                    "status": "error",
                    "url": url,
                    "error": str(exc),
                }
        return {"status": "unreachable", "url": url, "error": "Max retries exceeded"}

    async def warmup_query(self) -> dict:
        """Send a lightweight warmup query to pre-load embedding + reranker models.
        
        Prevents cold-start latency on the first real evaluation query.
        Returns timing and whether warmup succeeded.
        """
        import time
        start = time.perf_counter()
        resp = await self.run_query("What is ecology?", mode="prelims", top_k=1)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "warmup": "complete" if not resp.answer.startswith("API_ERROR") else "failed",
            "warmup_latency_ms": round(elapsed_ms, 2),
            "note": "BGE embedding + cross-encoder reranker models are now warm.",
        }

    # ── Run Query ──────────────────────────────────────────────────────
    async def run_query(
        self,
        question: str,
        mode: str = "prelims",
        sub_mode: str = "summary",
        top_k: int = 5,
    ) -> RAGQueryResponse:
        """POST /api/v1/query — run a single question against the RAG."""
        client = await self._get_client()
        url = self._settings.query_url

        payload = RAGQueryRequest(
            query=question, top_k=top_k, mode=mode, sub_mode=sub_mode,
        ).model_dump()

        last_error: Exception | None = None
        for attempt in range(1, self._settings.max_retries + 1):
            try:
                start = time.perf_counter()
                resp = await client.post(url, json=payload)
                elapsed_ms = (time.perf_counter() - start) * 1000
                resp.raise_for_status()
                data = resp.json()
                # Inject measured latency
                data["latency_ms"] = round(elapsed_ms, 2)
                return RAGQueryResponse(**data)
            except httpx.TimeoutException as exc:
                logger.warning(f"Query timeout attempt {attempt}: {exc}")
                last_error = exc
            except httpx.HTTPStatusError as exc:
                logger.error(f"Query HTTP error: {exc.response.status_code}")
                last_error = exc
                break  # don't retry on 4xx/5xx
            except httpx.ConnectError as exc:
                logger.error(f"Query connection error: {exc}")
                last_error = exc
                break
            except Exception as exc:
                logger.error(f"Query unexpected error: {exc}")
                last_error = exc
                break

        # Return a minimal error response rather than crashing
        error_msg = str(last_error) if last_error else "Unknown error"
        return RAGQueryResponse(
            query=question,
            answer=f"API_ERROR: {error_msg}",
            answered=False,
            gated=True,
            gate_reason=f"API_ERROR: {error_msg}",
        )

    # ── Cache Stats ────────────────────────────────────────────────────
    async def get_cache_stats(self) -> dict[str, Any]:
        """GET /api/v1/cache/stats."""
        client = await self._get_client()
        url = self._settings.cache_stats_url
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            return {"cache_metrics": "unavailable", "error": str(exc)}

    # ── Run Query with custom URL (for A/B comparison) ─────────────────
    async def run_query_against(
        self,
        base_url: str,
        question: str,
        mode: str = "prelims",
        sub_mode: str = "summary",
        top_k: int = 5,
    ) -> RAGQueryResponse:
        """Run a query against an arbitrary RAG URL (for comparison)."""
        client = await self._get_client()
        url = f"{base_url}{self._settings.rag_query_endpoint}"

        payload = RAGQueryRequest(
            query=question, top_k=top_k, mode=mode, sub_mode=sub_mode,
        ).model_dump()

        try:
            start = time.perf_counter()
            resp = await client.post(url, json=payload)
            elapsed_ms = (time.perf_counter() - start) * 1000
            resp.raise_for_status()
            data = resp.json()
            data["latency_ms"] = round(elapsed_ms, 2)
            return RAGQueryResponse(**data)
        except Exception as exc:
            return RAGQueryResponse(
                query=question,
                answer=f"API_ERROR: {exc}",
                answered=False,
                gated=True,
                gate_reason=f"API_ERROR: {exc}",
            )
