"""OpenRouter transport: request shape, response parsing and error mapping (no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.services.llm_service import LLMError, OpenRouterTransport, build_transport


class _Client:
    def __init__(self, status: int, payload: dict, headers: dict | None = None) -> None:
        self.status, self.payload, self.headers = status, payload, headers or {}
        self.sent: dict = {}

    def post(self, url, headers, json):
        self.sent = {"url": url, "headers": headers, "json": json}
        return SimpleNamespace(
            status_code=self.status, json=lambda: self.payload, headers=self.headers
        )


def _transport(client: _Client) -> OpenRouterTransport:
    return OpenRouterTransport(
        api_key="sk-or-test-not-real",
        model_id="google/gemini-3.8-flash",
        timeout_seconds=5,
        thinking_level="low",
        client=client,
    )


def _call(transport: OpenRouterTransport):
    return transport.generate(
        system_instruction="sys",
        prompt="p",
        json_schema={"type": "object"},
        temperature=0.1,
        max_output_tokens=100,
    )


def test_request_uses_strict_schema_low_reasoning_and_required_parameters() -> None:
    client = _Client(
        200,
        {
            "model": "google/gemini-3.8-flash",
            "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4},
        },
    )
    response = _call(_transport(client))
    body = client.sent["json"]
    assert body["model"] == "google/gemini-3.8-flash"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["reasoning"] == {"effort": "low"}
    assert body["provider"] == {"require_parameters": True}
    assert response.text == "{}"
    assert (response.usage.input_tokens, response.usage.output_tokens) == (10, 4)


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (401, "auth_failed", False),
        (402, "quota_exhausted", False),
        (404, "model_not_found", False),
        (503, "provider_error", True),
        (400, "bad_request", False),
    ],
)
def test_http_errors_are_mapped(status: int, code: str, retryable: bool) -> None:
    with pytest.raises(LLMError) as info:
        _call(_transport(_Client(status, {"error": {"code": status, "message": "x"}})))
    assert info.value.code == code
    assert info.value.retryable is retryable
    assert "sk-or-test-not-real" not in str(info.value)


def test_length_finish_is_truncated() -> None:
    client = _Client(200, {"choices": [{"finish_reason": "length", "message": {"content": "{"}}]})
    with pytest.raises(LLMError) as info:
        _call(_transport(client))
    assert info.value.code == "truncated"


def test_openrouter_key_in_gemini_slot_selects_openrouter() -> None:
    settings = Settings(_env_file=None, gemini_api_key="sk-or-test-not-real")
    assert settings.resolved_llm_provider == "openrouter"
    assert settings.llm_model_id == "google/gemini-3.8-flash"
    assert isinstance(build_transport(settings), OpenRouterTransport)
    google = Settings(_env_file=None, gemini_api_key="AQ.test-not-real")
    assert google.resolved_llm_provider == "gemini"
    assert google.llm_model_id == "gemini-3.8-flash"
