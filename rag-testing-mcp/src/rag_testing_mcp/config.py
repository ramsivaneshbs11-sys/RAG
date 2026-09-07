"""
Configuration loader for rag-testing-mcp.

Reads settings from environment variables and/or a .env file using
pydantic-settings.  No source-code changes needed to reconfigure.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configurable knobs for the RAG Testing MCP Server."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── RAG API Connection ─────────────────────────────────────────────
    rag_api_url: str = "http://localhost:8000"
    rag_query_endpoint: str = "/api/v1/query"
    rag_health_endpoint: str = "/health"
    rag_cache_stats_endpoint: str = "/api/v1/cache/stats"

    # ── Request Settings ───────────────────────────────────────────────
    request_timeout: int = 60
    max_retries: int = 2
    max_concurrency: int = 5

    # ── Evaluation Settings ────────────────────────────────────────────
    evaluation_output_dir: str = "evaluation/results"

    # ── Derived helpers ────────────────────────────────────────────────
    @property
    def query_url(self) -> str:
        return f"{self.rag_api_url}{self.rag_query_endpoint}"

    @property
    def health_url(self) -> str:
        return f"{self.rag_api_url}{self.rag_health_endpoint}"

    @property
    def cache_stats_url(self) -> str:
        return f"{self.rag_api_url}{self.rag_cache_stats_endpoint}"

    @property
    def results_dir(self) -> Path:
        p = Path(self.evaluation_output_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
