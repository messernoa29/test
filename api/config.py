"""Runtime configuration loaded from env."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv

load_dotenv()

LLMProvider = Literal["anthropic", "gemini"]


class Settings:
    # Provider selection
    llm_provider: LLMProvider
    # Anthropic
    anthropic_api_key: str
    anthropic_model: str
    # Gemini
    gemini_api_key: str
    gemini_model: str
    # PageSpeed Insights (optional)
    pagespeed_api_key: Optional[str]
    # Database
    database_url: str
    # CORS
    allowed_origins: list[str]
    allowed_origin_regex: Optional[str]
    # Auth (HTTPBasic). Username fixed to "admin"; password via env.
    # When unset, the API runs unauthenticated (dev mode).
    auth_password: Optional[str]
    # Scheduler (APScheduler in-process)
    scheduler_enabled: bool
    scheduler_sitemap_cron: str   # cron string, e.g. "0 6 * * *"
    scheduler_perf_cron: str
    scheduler_seo_cron: str

    def __init__(self) -> None:
        provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
        if provider not in ("anthropic", "gemini"):
            raise RuntimeError(
                f"LLM_PROVIDER invalid: {provider!r}. Expected 'anthropic' or 'gemini'."
            )
        self.llm_provider = provider  # type: ignore[assignment]

        # Anthropic — required only when selected as provider
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

        # Gemini — required only when selected as provider. The SDK also
        # honours GOOGLE_API_KEY, but we use GEMINI_API_KEY for clarity and
        # let the SDK fall back transparently.
        self.gemini_api_key = (
            os.getenv("GEMINI_API_KEY", "").strip()
            or os.getenv("GOOGLE_API_KEY", "").strip()
        )
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3-flash")

        # PageSpeed Insights — optional (free quota 25 000 req/day with key).
        # If missing, the crawler skips CWV enrichment and the analyzer marks
        # performance as "estimation".
        self.pagespeed_api_key = os.getenv("PAGESPEED_API_KEY", "").strip() or None

        # Database — persistent storage for audits. Defaults to a local SQLite
        # file so dev never loses data at restart. Override with a Postgres URL
        # in prod (`postgresql+psycopg://user:pass@host/db`).
        default_sqlite = (
            Path(__file__).resolve().parent / "data" / "audit-bureau.db"
        )
        self.database_url = os.getenv(
            "DATABASE_URL", f"sqlite:///{default_sqlite}"
        ).strip()

        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY missing for LLM_PROVIDER=anthropic. "
                "Set it in api/.env or switch LLM_PROVIDER=gemini."
            )
        if self.llm_provider == "gemini" and not self.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY missing for LLM_PROVIDER=gemini. "
                "Get a key at https://aistudio.google.com/apikey."
            )

        raw_origins = os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3001",
        )
        self.allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
        # Optional regex pattern for Vercel preview deployments
        # (e.g. https://audit-bureau-git-main-*.vercel.app)
        self.allowed_origin_regex = os.getenv("ALLOWED_ORIGIN_REGEX", "").strip() or None

        # Auth — single shared password. Leave APP_PASSWORD unset to disable.
        self.auth_password = os.getenv("APP_PASSWORD", "").strip() or None

        # Scheduler — disabled by default. Enable with SCHEDULER_ENABLED=1.
        # All cron strings use 5 fields (minute hour day month weekday).
        self.scheduler_enabled = os.getenv(
            "SCHEDULER_ENABLED", "0"
        ).strip().lower() in ("1", "true", "yes")
        self.scheduler_sitemap_cron = os.getenv(
            "SCHEDULER_SITEMAP_CRON", "0 6 * * *"   # daily 06:00 UTC
        ).strip()
        self.scheduler_perf_cron = os.getenv(
            "SCHEDULER_PERF_CRON", "30 6 * * *"      # daily 06:30 UTC
        ).strip()
        self.scheduler_seo_cron = os.getenv(
            "SCHEDULER_SEO_CRON", "0 7 * * 1"        # Mondays 07:00 UTC
        ).strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
