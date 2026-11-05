"""LLMService retry/validation policy and GeminiTransport mapping, without network."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors
from pydantic import BaseModel, ConfigDict

from app.schemas.extraction import (
    APP_OWNED_FIELDS,
    OverviewResponse,
    TerminologyResponse,
)
from app.services.llm_service import (
    GeminiTransport,
    LLMError,
    LLMResponse,
    LLMService,
    LLMUsage,
    _retry_delay_seconds,
)

API_KEY = "test-key-not-real"


class Simple(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    count: int


class ScriptedTransport:
    """Returns (or raises) the scripted steps in order and records every call."""

    def __init__(self, steps: list[Any]) -> None:
        self.steps = list(steps)
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        *,
        system_instruction: str,
        prompt: str,
        json_schema: dict[str, Any],
        temperature: float,
        max_output_tokens: int,
    ) -> LLMResponse:
        self.calls.append(
            {
                "system": system_instruction,
                "prompt": prompt,
                "schema": json_schema,
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
            }
        )
        step = self.steps.pop(0)
        if isinstance(step, LLMError):
            raise step
        if isinstance(step, str):
            return LLMResponse(text=step, usage=LLMUsage(10, 5), model_version="m-001")
        return step


def _ok(text: str = '{"name": "a", "count": 1}', inp: int = 10, out: int = 5) -> LLMResponse:
    return LLMResponse(text=text, usage=LLMUsage(inp, out), model_version="m-001")


def _service(transport: Any, sleeps: list[float], **kwargs: Any) -> LLMService:
    return LLMService(transport, model_id="fake-model", sleep=sleeps.append, **kwargs)


# ----- success ---------------------------------------------------------------------------


def test_success_returns_validated_model_after_one_attempt() -> None:
    transport = ScriptedTransport([_ok('{"name": "alpha", "count": 3}')])
    sleeps: list[float] = []
    service = _service(transport, sleeps, temperature=0.2, max_output_tokens=1234)

    result = service.generate_structured(Simple, system_instruction="SYS", prompt="PROMPT")

    assert isinstance(result.value, Simple)
    assert result.value == Simple(name="alpha", count=3)
    assert result.attempts == 1
    assert result.usage == LLMUsage(10, 5)
    assert result.model_version == "m-001"
    assert result.duration_ms >= 0
    assert sleeps == []
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["system"] == "SYS"
    assert call["prompt"] == "PROMPT"
    assert call["temperature"] == 0.2
    assert call["max_output_tokens"] == 1234


def test_usage_is_summed_across_attempts() -> None:
    transport = ScriptedTransport(
        [
            LLMError("timeout", "timed out", retryable=True),
            _ok("not json", inp=100, out=7),
            _ok('{"name": "b", "count": 2}', inp=120, out=9),
        ]
    )
    sleeps: list[float] = []
    result = _service(transport, sleeps).generate_structured(
        Simple, system_instruction="s", prompt="p"
    )

    assert result.attempts == 3
    assert result.usage == LLMUsage(input_tokens=220, output_tokens=16)
    assert result.value.count == 2


def test_usage_stays_none_when_provider_reports_none() -> None:
    transport = ScriptedTransport(
        [LLMResponse(text='{"name": "a", "count": 1}', usage=LLMUsage(None, None))]
    )
    result = _service(transport, []).generate_structured(Simple, system_instruction="s", prompt="p")
    assert result.usage == LLMUsage(None, None)
    assert result.model_version is None


# ----- transient errors -------------------------------------------------------------------


@pytest.mark.parametrize("code", ["timeout", "rate_limited", "provider_error"])
def test_retryable_error_is_retried_then_succeeds(code: str) -> None:
    transport = ScriptedTransport([LLMError(code, "x", retryable=True), _ok()])
    sleeps: list[float] = []
    result = _service(transport, sleeps).generate_structured(
        Simple, system_instruction="s", prompt="p"
    )
    assert result.attempts == 2
    assert sleeps == [2.0]
    assert len(transport.calls) == 2


@pytest.mark.parametrize("code", ["timeout", "rate_limited", "provider_error"])
def test_retryable_error_raised_after_max_retries(code: str) -> None:
    transport = ScriptedTransport([LLMError(code, "x", retryable=True) for _ in range(10)])
    sleeps: list[float] = []
    with pytest.raises(LLMError) as info:
        _service(transport, sleeps, max_retries=3).generate_structured(
            Simple, system_instruction="s", prompt="p"
        )
    assert info.value.code == code
    assert len(transport.calls) == 4  # first try + 3 retries
    assert sleeps == [2.0, 4.0, 8.0]  # exponential backoff


def test_zero_max_retries_raises_on_first_transient_error() -> None:
    transport = ScriptedTransport([LLMError("timeout", "x", retryable=True), _ok()])
    sleeps: list[float] = []
    with pytest.raises(LLMError) as info:
        _service(transport, sleeps, max_retries=0).generate_structured(
            Simple, system_instruction="s", prompt="p"
        )
    assert info.value.code == "timeout"
    assert len(transport.calls) == 1
    assert sleeps == []


def test_backoff_is_capped_at_sixty_seconds() -> None:
    transport = ScriptedTransport(
        [LLMError("provider_error", "x", retryable=True) for _ in range(8)] + [_ok()]
    )
    sleeps: list[float] = []
    result = _service(transport, sleeps, max_retries=8).generate_structured(
        Simple, system_instruction="s", prompt="p"
    )
    assert result.attempts == 9
    assert sleeps == [2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0]
    assert max(sleeps) <= 60.0


def test_retry_after_hint_is_honoured() -> None:
    transport = ScriptedTransport(
        [LLMError("rate_limited", "x", retryable=True, retry_after=13.0), _ok()]
    )
    sleeps: list[float] = []
    _service(transport, sleeps).generate_structured(Simple, system_instruction="s", prompt="p")
    assert sleeps == [13.0]


def test_retry_after_hint_is_capped_at_sixty_seconds() -> None:
    transport = ScriptedTransport(
        [LLMError("rate_limited", "x", retryable=True, retry_after=3600.0), _ok()]
    )
    sleeps: list[float] = []
    _service(transport, sleeps).generate_structured(Simple, system_instruction="s", prompt="p")
    assert sleeps == [60.0]


@pytest.mark.parametrize(
    "code", ["auth_failed", "bad_request", "blocked", "truncated", "model_not_found"]
)
def test_non_retryable_error_raised_immediately(code: str) -> None:
    transport = ScriptedTransport([LLMError(code, "nope", retryable=False), _ok()])
    sleeps: list[float] = []
    with pytest.raises(LLMError) as info:
        _service(transport, sleeps).generate_structured(Simple, system_instruction="s", prompt="p")
    assert info.value.code == code
    assert len(transport.calls) == 1
    assert sleeps == []


# ----- invalid output ---------------------------------------------------------------------


def test_invalid_json_is_reasked_with_correction_note() -> None:
    transport = ScriptedTransport([_ok("this is not json"), _ok('{"name": "c", "count": 4}')])
    sleeps: list[float] = []
    result = _service(transport, sleeps).generate_structured(
        Simple, system_instruction="s", prompt="ORIGINAL"
    )

    assert result.attempts == 2
    assert result.value == Simple(name="c", count=4)
    assert sleeps == []  # re-asks do not back off
    assert transport.calls[0]["prompt"] == "ORIGINAL"
    reask = transport.calls[1]["prompt"]
    assert reask.startswith("ORIGINAL")
    assert "previous answer was rejected" in reask
    assert "not valid JSON" in reask
    assert transport.calls[1]["schema"] == transport.calls[0]["schema"]


def test_schema_invalid_output_reask_names_the_problem() -> None:
    transport = ScriptedTransport([_ok('{"name": "c"}'), _ok('{"name": "c", "count": 4}')])
    result = _service(transport, []).generate_structured(Simple, system_instruction="s", prompt="P")
    assert result.attempts == 2
    reask = transport.calls[1]["prompt"]
    assert "previous answer was rejected" in reask
    assert "count" in reask


def test_invalid_output_raises_after_invalid_output_retries() -> None:
    transport = ScriptedTransport([_ok("{bad") for _ in range(5)])
    sleeps: list[float] = []
    with pytest.raises(LLMError) as info:
        _service(transport, sleeps, invalid_output_retries=2).generate_structured(
            Simple, system_instruction="s", prompt="p"
        )
    assert info.value.code == "invalid_output"
    assert info.value.retryable is False
    assert len(transport.calls) == 3  # first try + 2 re-asks
    assert sleeps == []


def test_schema_invalid_output_raises_invalid_output_with_default_retries() -> None:
    transport = ScriptedTransport(
        [_ok('{"name": "x", "count": "many"}'), _ok('{"name": 1, "count": 2, "extra": true}')]
    )
    with pytest.raises(LLMError) as info:
        _service(transport, []).generate_structured(Simple, system_instruction="s", prompt="p")
    assert info.value.code == "invalid_output"
    assert "did not match the schema" in info.value.message
    assert len(transport.calls) == 2  # default invalid_output_retries = 1


def test_zero_invalid_output_retries_raises_without_reask() -> None:
    transport = ScriptedTransport([_ok("[]"), _ok()])
    with pytest.raises(LLMError) as info:
        _service(transport, [], invalid_output_retries=0).generate_structured(
            Simple, system_instruction="s", prompt="p"
        )
    assert info.value.code == "invalid_output"
    assert len(transport.calls) == 1


# ----- app-owned fields ------------------------------------------------------------------


def test_app_owned_fields_in_model_output_are_stripped() -> None:
    answer = {
        "technical_terminology": {
            "status": "extracted",
            "task_status": "completed",
            "terms": [
                {
                    "term": "BM25",
                    "definition": "a ranking function",
                    "support": [{"passage_id": "P01", "quote": "BM25 ranks"}],
                    "claim_ids": ["CLM_999"],
                    "evidence_ids": ["EV_999"],
                }
            ],
        }
    }
    transport = ScriptedTransport([_ok(json.dumps(answer))])
    result = _service(transport, []).generate_structured(
        TerminologyResponse, system_instruction="s", prompt="p"
    )

    assert result.attempts == 1  # stripped, not rejected
    category = result.value.technical_terminology
    assert category.task_status == "not_run"
    term = category.terms[0]
    assert term.term == "BM25"
    assert term.claim_ids == []
    assert term.evidence_ids == []
    assert term.support[0].passage_id == "P01"


def test_original_abstract_from_model_is_ignored() -> None:
    empty = {"value": None, "status": "not_found", "support": []}
    answer = {
        "abstract": {
            "status": "extracted",
            "original_abstract": {
                "value": "Invented abstract text.",
                "status": "extracted",
                "support": [],
            },
            "stated_problem": empty,
            "approach": empty,
            "principal_findings": empty,
            "conclusion": empty,
        },
        "research_problem": {"status": "not_found"},
        "objectives": {"status": "not_found"},
        "motivation": {"status": "not_found"},
        "background": {"status": "not_found"},
    }
    transport = ScriptedTransport([_ok(json.dumps(answer))])
    result = _service(transport, []).generate_structured(
        OverviewResponse, system_instruction="s", prompt="p"
    )
    assert result.value.abstract.original_abstract.value is None
    assert result.value.abstract.task_status == "not_run"


def _walk(node: Any, path: str = "") -> list[tuple[str, Any]]:
    out = [(path, node)]
    if isinstance(node, dict):
        for key, value in node.items():
            out += _walk(value, f"{path}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            out += _walk(value, f"{path}[{i}]")
    return out


@pytest.mark.parametrize("model", [OverviewResponse, TerminologyResponse])
def test_schema_passed_to_transport_has_no_refs_or_app_owned_fields(
    model: type[BaseModel],
) -> None:
    transport = ScriptedTransport([_ok("{}")])
    with pytest.raises(LLMError):
        _service(transport, [], invalid_output_retries=0).generate_structured(
            model, system_instruction="s", prompt="p"
        )
    schema = transport.calls[0]["schema"]

    assert "$defs" not in schema
    assert "$ref" not in json.dumps(schema)
    for path, node in _walk(schema):
        if isinstance(node, dict):
            assert "$ref" not in node, path
            props = node.get("properties")
            if isinstance(props, dict):
                assert not (set(props) & APP_OWNED_FIELDS), path
            required = node.get("required")
            if isinstance(required, list):
                assert not (set(required) & APP_OWNED_FIELDS), path
    # the schema is still usable: top-level fields and grounding support are present
    assert set(schema["properties"]) == set(model.model_fields)
    assert "support" in json.dumps(schema)


# ----- GeminiTransport -------------------------------------------------------------------


def test_retry_delay_seconds_parsing() -> None:
    payload = {
        "error": {
            "code": 429,
            "details": [
                {"@type": "type.googleapis.com/google.rpc.Help"},
                {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "13s"},
            ],
        }
    }
    assert _retry_delay_seconds(payload) == 13.0
    assert _retry_delay_seconds('{"retryDelay": "2.5s"}') == 2.5
    assert _retry_delay_seconds({"error": {"code": 429, "details": []}}) is None
    assert _retry_delay_seconds("") is None
    assert _retry_delay_seconds(None) is None


def _gemini_response(
    *, finish: Any = "STOP", text: str | None = '{"a": 1}', usage: Any = None
) -> SimpleNamespace:
    return SimpleNamespace(
        candidates=[SimpleNamespace(finish_reason=finish)],
        text=text,
        usage_metadata=usage,
        model_version="gemini-x-001",
    )


@pytest.mark.parametrize("finish", ["SAFETY", "FinishReason.SAFETY", "PROHIBITED_CONTENT"])
def test_to_response_safety_finish_is_blocked(finish: str) -> None:
    with pytest.raises(LLMError) as info:
        GeminiTransport._to_response(_gemini_response(finish=finish))
    assert info.value.code == "blocked"
    assert info.value.retryable is False


def test_to_response_max_tokens_is_truncated() -> None:
    with pytest.raises(LLMError) as info:
        GeminiTransport._to_response(_gemini_response(finish="MAX_TOKENS", text='{"a"'))
    assert info.value.code == "truncated"
    assert info.value.retryable is False


@pytest.mark.parametrize("text", ["", None])
def test_to_response_empty_text_is_retryable(text: str | None) -> None:
    with pytest.raises(LLMError) as info:
        GeminiTransport._to_response(_gemini_response(text=text))
    assert info.value.code == "empty_response"
    assert info.value.retryable is True


def test_to_response_normal_maps_text_and_usage() -> None:
    usage = SimpleNamespace(prompt_token_count=321, candidates_token_count=45)
    response = GeminiTransport._to_response(_gemini_response(usage=usage))
    assert response.text == '{"a": 1}'
    assert response.usage == LLMUsage(input_tokens=321, output_tokens=45)
    assert response.model_version == "gemini-x-001"


def test_to_response_without_candidates_or_usage() -> None:
    raw = SimpleNamespace(candidates=None, text='{"a": 1}', usage_metadata=None)
    response = GeminiTransport._to_response(raw)
    assert response.text == '{"a": 1}'
    assert response.usage == LLMUsage(None, None)
    assert response.model_version is None


def _transport_raising(monkeypatch: pytest.MonkeyPatch, exc: BaseException) -> GeminiTransport:
    transport = GeminiTransport(api_key=API_KEY, model_id="m", timeout_seconds=5)
    calls: list[dict[str, Any]] = []

    def fake_generate_content(**kwargs: Any) -> Any:
        calls.append(kwargs)
        raise exc

    monkeypatch.setattr(transport._client.models, "generate_content", fake_generate_content)
    transport.fake_calls = calls  # type: ignore[attr-defined]
    return transport


def _call(transport: GeminiTransport) -> LLMError:
    with pytest.raises(LLMError) as info:
        transport.generate(
            system_instruction="sys",
            prompt="prompt",
            json_schema={"type": "object", "properties": {}},
            temperature=0.1,
            max_output_tokens=100,
        )
    err = info.value
    assert API_KEY not in str(err)
    assert API_KEY not in err.message
    assert API_KEY not in repr(err)
    return err


def _error_json(code: int, status: str, details: list[Any] | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": f"failure {status} for key {API_KEY}",
            "status": status,
            "details": details or [],
        }
    }


def test_gemini_rate_limit_maps_to_retryable_with_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    details = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "13s"}]
    exc = errors.ClientError(429, _error_json(429, "RESOURCE_EXHAUSTED", details))
    transport = _transport_raising(monkeypatch, exc)
    err = _call(transport)
    assert err.code == "rate_limited"
    assert err.retryable is True
    assert err.retry_after == 13.0
    assert len(transport.fake_calls) == 1  # type: ignore[attr-defined]
    sent = transport.fake_calls[0]  # type: ignore[attr-defined]
    assert sent["model"] == "m"
    assert sent["contents"] == "prompt"


def test_gemini_rate_limit_without_hint_has_no_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exc = errors.ClientError(429, _error_json(429, "RESOURCE_EXHAUSTED"))
    err = _call(_transport_raising(monkeypatch, exc))
    assert err.code == "rate_limited"
    assert err.retry_after is None


@pytest.mark.parametrize("code", [401, 403])
def test_gemini_auth_errors_are_not_retryable(monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    exc = errors.ClientError(code, _error_json(code, "UNAUTHENTICATED"))
    err = _call(_transport_raising(monkeypatch, exc))
    assert err.code == "auth_failed"
    assert err.retryable is False


def test_gemini_404_is_model_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = errors.ClientError(404, _error_json(404, "NOT_FOUND"))
    err = _call(_transport_raising(monkeypatch, exc))
    assert err.code == "model_not_found"
    assert err.retryable is False
    assert "'m'" in err.message


def test_gemini_400_is_bad_request(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = errors.ClientError(400, _error_json(400, "INVALID_ARGUMENT"))
    err = _call(_transport_raising(monkeypatch, exc))
    assert err.code == "bad_request"
    assert err.retryable is False
    assert "400" in err.message


def test_gemini_server_error_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = errors.ServerError(500, _error_json(500, "INTERNAL"))
    err = _call(_transport_raising(monkeypatch, exc))
    assert err.code == "provider_error"
    assert err.retryable is True


def test_gemini_timeout_exception_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    class ReadTimeout(Exception):
        pass

    err = _call(_transport_raising(monkeypatch, ReadTimeout(f"timed out using {API_KEY}")))
    assert err.code == "timeout"
    assert err.retryable is True


def test_gemini_builtin_timeout_error_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    err = _call(_transport_raising(monkeypatch, TimeoutError("slow")))
    assert err.code == "timeout"
    assert err.retryable is True


def test_gemini_other_exception_is_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    err = _call(_transport_raising(monkeypatch, ConnectionError(f"boom {API_KEY}")))
    assert err.code == "transport_error"
    assert err.retryable is True
    assert "ConnectionError" in err.message


def test_gemini_success_goes_through_to_response(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = GeminiTransport(api_key=API_KEY, model_id="m", timeout_seconds=5)
    sent: list[dict[str, Any]] = []

    def fake_generate_content(**kwargs: Any) -> Any:
        sent.append(kwargs)
        usage = SimpleNamespace(prompt_token_count=7, candidates_token_count=3)
        return _gemini_response(text='{"name": "z", "count": 9}', usage=usage)

    monkeypatch.setattr(transport._client.models, "generate_content", fake_generate_content)
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    response = transport.generate(
        system_instruction="sys",
        prompt="prompt",
        json_schema=schema,
        temperature=0.3,
        max_output_tokens=77,
    )
    assert response.text == '{"name": "z", "count": 9}'
    assert response.usage == LLMUsage(7, 3)
    config = sent[0]["config"]
    assert config.system_instruction == "sys"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == schema
    assert config.temperature == 0.3
    assert config.max_output_tokens == 77


def test_gemini_transport_retries_through_service(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = GeminiTransport(api_key=API_KEY, model_id="m", timeout_seconds=5)
    outcomes: list[Any] = [
        errors.ServerError(503, _error_json(503, "UNAVAILABLE")),
        _gemini_response(
            text='{"name": "ok", "count": 1}',
            usage=SimpleNamespace(prompt_token_count=4, candidates_token_count=2),
        ),
    ]

    def fake_generate_content(**kwargs: Any) -> Any:
        outcome = outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(transport._client.models, "generate_content", fake_generate_content)
    sleeps: list[float] = []
    result = LLMService(transport, model_id="m", sleep=sleeps.append).generate_structured(
        Simple, system_instruction="s", prompt="p"
    )
    assert result.value == Simple(name="ok", count=1)
    assert result.attempts == 2
    assert sleeps == [2.0]
    assert result.model_version == "gemini-x-001"
