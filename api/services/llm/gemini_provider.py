"""Gemini provider (Google AI Studio).

Uses the modern `google-genai` SDK. Grounding via the built-in
`google_search` tool plays the role of Anthropic's `web_search`.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from api.config import get_settings
from api.services.llm.base import LLMClient, LLMResponse, StopReason

logger = logging.getLogger(__name__)

# Rate-limit retry backoff (exponential-ish). The previous flat 62s × 5
# attempts could add 5 minutes per call — on the free tier, with ~10 LLM
# calls per audit, that ballooned audits to 60-90 min. Cap the pain.
_RATE_LIMIT_BACKOFF_S = [12, 25, 40]
_OVERLOAD_BACKOFF_S = [8, 20, 45]
_CONNECTION_RETRY_S = 5


class GeminiProvider(LLMClient):
    name = "gemini"

    def __init__(self) -> None:
        settings = get_settings()
        self._model = settings.gemini_model
        # Per-request HTTP timeout — the SDK has none by default, so a stalled
        # connection would hang a worker thread forever. 120s is plenty for a
        # generate call (web_search ones included).
        self._client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=genai_types.HttpOptions(timeout=120_000),  # ms
        )

    def generate(
        self,
        *,
        system: str,
        user_prompt: str,
        max_tokens: int,
        enable_web_search: bool = True,
    ) -> LLMResponse:
        tools: list[genai_types.Tool] = []
        if enable_web_search:
            tools.append(genai_types.Tool(google_search=genai_types.GoogleSearch()))

        config = genai_types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            temperature=0.3,
            tools=tools or None,
        )

        def _call():
            return self._client.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config=config,
            )

        overload_attempts = 0
        ratelimit_attempts = 0
        last_exception: Optional[Exception] = None

        for attempt in range(5):
            try:
                response = _call()
                return _to_response(response)
            except genai_errors.ClientError as e:
                status = getattr(e, "code", None)
                if status == 429:
                    if ratelimit_attempts < len(_RATE_LIMIT_BACKOFF_S):
                        delay = _RATE_LIMIT_BACKOFF_S[ratelimit_attempts]
                        ratelimit_attempts += 1
                        logger.warning(
                            "Gemini rate limit (attempt %d), sleeping %ds",
                            attempt + 1, delay,
                        )
                        time.sleep(delay)
                        last_exception = e
                        continue
                    raise
                # 4xx other than 429 are not retriable (bad request, auth)
                raise
            except genai_errors.ServerError as e:
                if overload_attempts < len(_OVERLOAD_BACKOFF_S):
                    delay = _OVERLOAD_BACKOFF_S[overload_attempts]
                    overload_attempts += 1
                    logger.warning(
                        "Gemini server error (attempt %d): %s — sleeping %ds",
                        attempt + 1, e, delay,
                    )
                    time.sleep(delay)
                    last_exception = e
                    continue
                raise
            except Exception as e:
                # Network/DNS issues bubble up as generic exceptions in the SDK
                if attempt < 2:
                    logger.warning(
                        "Gemini transient error (attempt %d): %s — retry in %ds",
                        attempt + 1, e, _CONNECTION_RETRY_S,
                    )
                    time.sleep(_CONNECTION_RETRY_S)
                    last_exception = e
                    continue
                raise

        if last_exception is not None:
            raise last_exception
        raise RuntimeError("GeminiProvider.generate exhausted retries")


def _to_response(response) -> LLMResponse:
    # `response.text` concatenates all text parts from candidates[0].
    text = (getattr(response, "text", None) or "").strip()

    raw_stop = None
    stop: StopReason = "end"
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        fr = getattr(candidates[0], "finish_reason", None)
        raw_stop = fr.name if fr is not None and hasattr(fr, "name") else str(fr or "")
        if raw_stop == "STOP":
            stop = "end"
        elif raw_stop == "MAX_TOKENS":
            stop = "max_tokens"
        elif raw_stop in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "SPII", "BLOCKLIST"):
            stop = "safety"
        else:
            stop = "other"

    usage = getattr(response, "usage_metadata", None)
    in_tokens = getattr(usage, "prompt_token_count", None) if usage else None
    out_tokens = getattr(usage, "candidates_token_count", None) if usage else None

    if stop != "end":
        logger.warning(
            "Gemini unusual finish_reason=%s (output=%s)", raw_stop, out_tokens
        )

    return LLMResponse(
        text=text,
        stop_reason=stop,
        raw_stop_reason=raw_stop,
        input_tokens=in_tokens,
        output_tokens=out_tokens,
    )
