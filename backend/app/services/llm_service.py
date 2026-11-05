"""Reusable structured-output LLM service (Google Gemini via the google-genai SDK).

``LLMService.generate_structured`` sends a prompt with a JSON Schema, then parses and
validates the reply with Pydantic in application code. The SDK call sits behind the
``LLMTransport`` protocol, so the API method can change without touching callers and
tests can use a fake transport (no paid calls in routine tests).

Retry policy (spec §8.3, §14):
- timeouts, rate limits (429) and server errors: up to ``max_retries`` retries with
  exponential backoff, honouring the provider's ``retryDelay`` hint when present;
- invalid structured output: up to ``invalid_output_retries`` re-asks;
- authentication, bad requests and blocked responses: no retry.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.schemas.extraction import APP_OWNED_FIELDS, llm_json_schema

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_MAX_BACKOFF_SECONDS = 60.0
# Finish reasons meaning the model refused or was stopped by a policy; not retried.
_BLOCKED_FINISH_REASONS = (
    "SAFETY",
    "PROHIBITED",
    "BLOCKLIST",
    "RECITATION",
    "SPII",
    "LANGUAGE",
)


class LLMError(RuntimeError):
    """An LLM call failed. ``code`` is stable and safe to show to users."""

    def __init__(
        self, code: str, message: str, *, retryable: bool = False, retry_after: float | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.retry_after = retry_after


@dataclass(slots=True)
class LLMUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None

    def add(self, other: LLMUsage) -> LLMUsage:
        def plus(a: int | None, b: int | None) -> int | None:
            return None if a is None and b is None else (a or 0) + (b or 0)

        return LLMUsage(
            plus(self.input_tokens, other.input_tokens),
            plus(self.output_tokens, other.output_tokens),
        )


@dataclass(slots=True)
class LLMResponse:
    text: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    model_version: str | None = None


@dataclass(slots=True)
class StructuredResult[M]:
    value: M
    attempts: int
    usage: LLMUsage
    duration_ms: int
    model_version: str | None


class LLMTransport(Protocol):
    def generate(
        self,
        *,
        system_instruction: str,
        prompt: str,
        json_schema: dict[str, Any],
        temperature: float,
        max_output_tokens: int,
    ) -> LLMResponse: ...


# ----- Gemini transport ---------------------------------------------------------------


def _retry_delay_seconds(details: Any) -> float | None:
    """Extract ``retryDelay`` (e.g. "13s") from a Google API error payload."""
    text = json.dumps(details) if not isinstance(details, str) else details
    match = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', text)
    return float(match.group(1)) if match else None


class GeminiTransport:
    """``models.generate_content`` with ``response_json_schema`` (google-genai SDK)."""

    def __init__(self, *, api_key: str, model_id: str, timeout_seconds: float) -> None:
        from google import genai
        from google.genai import types

        self._types = types
        self.model_id = model_id
        # The key is passed explicitly so a stray GOOGLE_API_KEY in the environment (which
        # the SDK would otherwise prefer) cannot select a different account.
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
        )

    def generate(
        self,
        *,
        system_instruction: str,
        prompt: str,
        json_schema: dict[str, Any],
        temperature: float,
        max_output_tokens: int,
    ) -> LLMResponse:
        from google.genai import errors

        config = self._types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_json_schema=json_schema,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        try:
            response = self._client.models.generate_content(
                model=self.model_id, contents=prompt, config=config
            )
        except errors.ClientError as exc:
            code = getattr(exc, "code", None)
            if code == 429:
                raise LLMError(
                    "rate_limited",
                    "The model provider rate-limited the request.",
                    retryable=True,
                    retry_after=_retry_delay_seconds(getattr(exc, "details", "")),
                ) from exc
            # The Gemini API answers an invalid key with HTTP 400 (reason API_KEY_INVALID).
            invalid_key = "API_KEY_INVALID" in str(getattr(exc, "details", "")) or (
                "api key not valid" in str(getattr(exc, "message", "")).lower()
            )
            if code in (401, 403) or invalid_key:
                raise LLMError("auth_failed", "The Gemini API key was rejected.") from exc
            if code == 404:
                raise LLMError(
                    "model_not_found", f"Model {self.model_id!r} is not available for this key."
                ) from exc
            raise LLMError("bad_request", f"The model rejected the request (HTTP {code}).") from exc
        except errors.ServerError as exc:
            raise LLMError(
                "provider_error", "The model provider returned a server error.", retryable=True
            ) from exc
        except Exception as exc:
            if "timeout" in type(exc).__name__.lower():
                raise LLMError("timeout", "The model request timed out.", retryable=True) from exc
            raise LLMError(
                "transport_error", f"Model request failed ({type(exc).__name__}).", retryable=True
            ) from exc
        return self._to_response(response)

    @staticmethod
    def _to_response(response: Any) -> LLMResponse:
        # A blocked prompt has no candidates, only a block reason; resending it will not help.
        feedback = getattr(response, "prompt_feedback", None)
        block_reason = getattr(feedback, "block_reason", None)
        if block_reason:
            raise LLMError("blocked", f"The provider blocked the prompt ({block_reason}).")
        candidates = getattr(response, "candidates", None) or []
        finish = str(getattr(candidates[0], "finish_reason", "") or "") if candidates else ""
        if any(reason in finish for reason in _BLOCKED_FINISH_REASONS):
            raise LLMError("blocked", f"The model declined to answer ({finish}).")
        if "MAX_TOKENS" in finish:
            raise LLMError(
                "truncated", "The model output was cut off at the token limit.", retryable=False
            )
        text = getattr(response, "text", None)
        if not text:
            raise LLMError("empty_response", "The model returned no content.", retryable=True)
        usage = getattr(response, "usage_metadata", None)
        answer_tokens = getattr(usage, "candidates_token_count", None)
        thinking_tokens = getattr(usage, "thoughts_token_count", None)
        # Thinking tokens are billed as output, so they are counted with the answer.
        output_tokens = (
            None
            if answer_tokens is None and thinking_tokens is None
            else (answer_tokens or 0) + (thinking_tokens or 0)
        )
        return LLMResponse(
            text=text,
            usage=LLMUsage(
                input_tokens=getattr(usage, "prompt_token_count", None),
                output_tokens=output_tokens,
            ),
            model_version=getattr(response, "model_version", None),
        )


# ----- Service --------------------------------------------------------------------------


def _strip_app_owned(node: Any) -> Any:
    """Drop fields the application owns, should the model include them anyway."""
    if isinstance(node, dict):
        return {k: _strip_app_owned(v) for k, v in node.items() if k not in APP_OWNED_FIELDS}
    if isinstance(node, list):
        return [_strip_app_owned(item) for item in node]
    return node


def _summarise_validation_error(exc: ValidationError, limit: int = 5) -> str:
    problems = [
        f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
        for err in exc.errors()[:limit]
    ]
    more = len(exc.errors()) - limit
    return "; ".join(problems) + (f"; and {more} more" if more > 0 else "")


class LLMService:
    def __init__(
        self,
        transport: LLMTransport,
        *,
        model_id: str,
        max_retries: int = 3,
        invalid_output_retries: int = 1,
        temperature: float = 0.1,
        max_output_tokens: int = 8192,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.transport = transport
        self.model_id = model_id
        self.max_retries = max_retries
        self.invalid_output_retries = invalid_output_retries
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self._sleep = sleep

    def generate_structured(
        self,
        response_model: type[T],
        *,
        system_instruction: str,
        prompt: str,
    ) -> StructuredResult[T]:
        schema = llm_json_schema(response_model)
        started = time.perf_counter()
        usage = LLMUsage()
        attempts = 0
        transient_failures = 0
        invalid_outputs = 0
        correction = ""

        while True:
            attempts += 1
            try:
                response = self.transport.generate(
                    system_instruction=system_instruction,
                    prompt=prompt + correction,
                    json_schema=schema,
                    temperature=self.temperature,
                    max_output_tokens=self.max_output_tokens,
                )
            except LLMError as exc:
                if not exc.retryable or transient_failures >= self.max_retries:
                    raise
                transient_failures += 1
                delay = exc.retry_after or min(2.0**transient_failures, _MAX_BACKOFF_SECONDS)
                logger.warning(
                    "LLM call failed (%s); retry %d/%d in %.1fs",
                    exc.code,
                    transient_failures,
                    self.max_retries,
                    delay,
                )
                self._sleep(min(delay, _MAX_BACKOFF_SECONDS))
                continue

            usage = usage.add(response.usage)
            try:
                payload = _strip_app_owned(json.loads(response.text))
                value = response_model.model_validate(payload)
            except (json.JSONDecodeError, ValidationError) as exc:
                detail = (
                    _summarise_validation_error(exc)
                    if isinstance(exc, ValidationError)
                    else f"not valid JSON ({exc.msg})"
                )
                if invalid_outputs >= self.invalid_output_retries:
                    raise LLMError(
                        "invalid_output", f"The model output did not match the schema: {detail}"
                    ) from exc
                invalid_outputs += 1
                logger.warning(
                    "LLM output invalid (%s); re-asking (%d/%d)",
                    detail[:200],
                    invalid_outputs,
                    self.invalid_output_retries,
                )
                correction = (
                    "\n\nYour previous answer was rejected because it did not match the "
                    f"required JSON schema ({detail}). Answer again with valid JSON only."
                )
                continue

            return StructuredResult(
                value=value,
                attempts=attempts,
                usage=usage,
                duration_ms=int((time.perf_counter() - started) * 1000),
                model_version=response.model_version,
            )
