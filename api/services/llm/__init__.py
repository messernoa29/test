"""LLM provider layer — dispatch between Anthropic and Gemini.

The rest of the app imports `get_llm_client()` and calls `.generate(...)`;
switching between providers is a one-env-var change.
"""

from api.services.llm.base import LLMClient, LLMResponse
from api.services.llm.factory import get_llm_client

__all__ = ["LLMClient", "LLMResponse", "get_llm_client"]
