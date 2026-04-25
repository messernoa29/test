"""Factory: pick the right LLM provider based on settings."""

from __future__ import annotations

from functools import lru_cache

from api.config import get_settings
from api.services.llm.base import LLMClient


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    provider = get_settings().llm_provider
    if provider == "anthropic":
        from api.services.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    if provider == "gemini":
        from api.services.llm.gemini_provider import GeminiProvider
        return GeminiProvider()
    raise RuntimeError(f"Unknown LLM provider: {provider!r}")
