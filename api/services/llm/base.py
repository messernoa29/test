"""Shared contract for LLM providers.

Every provider exposes the same `generate()` call. The response is wrapped
in a provider-agnostic `LLMResponse` so callers (the analyzer) never import
vendor SDKs directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Optional


StopReason = Literal["end", "max_tokens", "safety", "other"]


@dataclass
class LLMResponse:
    """Provider-agnostic response."""

    text: str
    stop_reason: StopReason
    raw_stop_reason: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class LLMClient(ABC):
    """Interface implemented by each provider."""

    name: str

    @abstractmethod
    def generate(
        self,
        *,
        system: str,
        user_prompt: str,
        max_tokens: int,
        enable_web_search: bool = True,
    ) -> LLMResponse:
        """Run a single generation with optional web search grounding."""
