"""Anthropic provider (Claude).

Resilient to the usual transient failures:
- 429 rate_limit_error : wait past the 60 s sliding window and retry
- 503 / 529 overloaded : exponential backoff, a couple of retries
- connection errors / timeouts : retry once with a shorter backoff
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from anthropic import (
    Anthropic,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    RateLimitError,
)
from anthropic.types import Message

from api.config import get_settings
from api.services.llm.base import LLMClient, LLMResponse, StopReason

logger = logging.getLogger(__name__)

_WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}

_RATE_LIMIT_COOLDOWN_S = 65
_OVERLOAD_BACKOFF_S = [10, 30]
_CONNECTION_RETRY_S = 5
_REQUEST_TIMEOUT_S = 120.0


class AnthropicProvider(LLMClient):
    name = "anthropic"

    def __init__(self) -> None:
        settings = get_settings()
        self._model = settings.anthropic_model
        self._client = Anthropic(
            api_key=settings.anthropic_api_key,
            timeout=_REQUEST_TIMEOUT_S,
            max_retries=0,  # we handle retries
        )

    def generate(
        self,
        *,
        system: str,
        user_prompt: str,
        max_tokens: int,
        enable_web_search: bool = True,
        temperature: float = 0.0,
    ) -> LLMResponse:
        tools = [_WEB_SEARCH_TOOL] if enable_web_search else []
        temp = max(0.0, float(temperature))

        def _call() -> Message:
            return self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temp,
                system=system,
                tools=tools,  # type: ignore[arg-type]
                messages=[{"role": "user", "content": user_prompt}],
            )

        overload_attempts = 0
        last_exception: Optional[Exception] = None

        for attempt in range(5):
            try:
                message = _call()
                return _to_response(message)
            except RateLimitError as e:
                logger.warning(
                    "Anthropic rate limit (attempt %d), sleeping %ds",
                    attempt + 1, _RATE_LIMIT_COOLDOWN_S,
                )
                time.sleep(_RATE_LIMIT_COOLDOWN_S)
                last_exception = e
            except APIStatusError as e:
                status = getattr(e, "status_code", None)
                if status in (503, 529) and overload_attempts < len(_OVERLOAD_BACKOFF_S):
                    delay = _OVERLOAD_BACKOFF_S[overload_attempts]
                    overload_attempts += 1
                    logger.warning(
                        "Anthropic overloaded (HTTP %s, attempt %d), sleeping %ds",
                        status, attempt + 1, delay,
                    )
                    time.sleep(delay)
                    last_exception = e
                    continue
                raise
            except (APIConnectionError, APITimeoutError) as e:
                logger.warning(
                    "Anthropic network error (attempt %d): %s — retrying in %ds",
                    attempt + 1, e, _CONNECTION_RETRY_S,
                )
                time.sleep(_CONNECTION_RETRY_S)
                last_exception = e

        if last_exception is not None:
            raise last_exception
        raise RuntimeError("AnthropicProvider.generate exhausted retries")


def _to_response(message: Message) -> LLMResponse:
    parts: list[str] = []
    for block in message.content:
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
    text = "\n".join(parts).strip()

    raw_stop = getattr(message, "stop_reason", None)
    stop: StopReason
    if raw_stop == "end_turn":
        stop = "end"
    elif raw_stop == "max_tokens":
        stop = "max_tokens"
    elif raw_stop == "refusal":
        stop = "safety"
    else:
        stop = "other"

    usage = getattr(message, "usage", None)
    in_tokens = getattr(usage, "input_tokens", None) if usage else None
    out_tokens = getattr(usage, "output_tokens", None) if usage else None

    if stop != "end":
        logger.warning(
            "Anthropic unusual stop=%s (output=%s)", raw_stop, out_tokens
        )

    return LLMResponse(
        text=text,
        stop_reason=stop,
        raw_stop_reason=raw_stop if isinstance(raw_stop, str) else None,
        input_tokens=in_tokens,
        output_tokens=out_tokens,
    )
