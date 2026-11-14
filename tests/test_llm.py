"""Week 11 tests: provider adapter and settings. Offline - the SDK is faked."""

from __future__ import annotations

from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from career_agent.cli import ask
from career_agent.config import ConfigError, Settings, load_settings
from career_agent.llm import ClaudeClient, LLMError

URL = "https://api.anthropic.com/v1/messages"


class FakeSDK:
    """Mimics anthropic.Anthropic().beta.messages.create(); records the request."""

    def __init__(self, result=None, error: Exception | None = None):
        self.result, self.error, self.calls = result, error, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


def message(content, stop_reason="end_turn", stop_details=None):
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        stop_details=stop_details,
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=12, output_tokens=34),
    )


def text(value):
    return SimpleNamespace(type="text", text=value)


def status_error(cls, code):
    response = httpx2.Response(code, request=httpx2.Request("POST", URL))
    return cls(f"HTTP {code}", response=response, body=None)


@pytest.fixture
def settings():
    return Settings(api_key="test-key")


@pytest.fixture
def clean_env(monkeypatch):
    for name in ("LLM_API_KEY", "ANTHROPIC_API_KEY", "LLM_MODEL", "LLM_EFFORT", "LLM_MAX_TOKENS"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_text_response_is_parsed(settings):
    sdk = FakeSDK(message([SimpleNamespace(type="thinking", thinking=""), text("Learn SQL.")]))
    response = ClaudeClient(settings, sdk=sdk).complete([{"role": "user", "content": "hi"}])

    assert response.text == "Learn SQL."
    assert response.tool_calls == []
    assert (response.input_tokens, response.output_tokens) == (12, 34)
    assert len(response.raw_content) == 2  # thinking block kept for the history


def test_request_uses_configured_model_effort_and_fallback(settings):
    sdk = FakeSDK(message([text("ok")]))
    ClaudeClient(settings, sdk=sdk).complete(
        [{"role": "user", "content": "hi"}], system="be brief", tools=[{"name": "t"}]
    )

    request = sdk.calls[0]
    assert request["model"] == "claude-opus-5-5"
    assert request["output_config"] == {"effort": "medium"}
    assert request["fallbacks"] == "default"
    assert request["system"] == "be brief"
    assert request["tools"] == [{"name": "t"}]


def test_tool_use_blocks_become_tool_calls(settings):
    block = SimpleNamespace(type="tool_use", id="tu_1", name="search_vacancies", input={"query": "analyst"})
    sdk = FakeSDK(message([text("Searching."), block], stop_reason="tool_use"))
    response = ClaudeClient(settings, sdk=sdk).complete([{"role": "user", "content": "find jobs"}])

    assert response.stop_reason == "tool_use"
    assert response.tool_calls[0].name == "search_vacancies"
    assert response.tool_calls[0].arguments == {"query": "analyst"}


def test_refusal_raises_non_retryable_error(settings):
    sdk = FakeSDK(message([], stop_reason="refusal", stop_details=SimpleNamespace(category="cyber")))
    with pytest.raises(LLMError) as err:
        ClaudeClient(settings, sdk=sdk).complete([{"role": "user", "content": "x"}])
    assert err.value.kind == "refusal" and not err.value.retryable


@pytest.mark.parametrize(
    ("error", "kind", "retryable"),
    [
        (status_error(anthropic.AuthenticationError, 401), "auth", False),
        (status_error(anthropic.RateLimitError, 429), "rate_limit", True),
        (status_error(anthropic.InternalServerError, 500), "server", True),
        (anthropic.APIConnectionError(request=httpx2.Request("POST", URL)), "network", True),
        (anthropic.APITimeoutError(request=httpx2.Request("POST", URL)), "timeout", True),
    ],
)
def test_api_failures_are_classified(settings, error, kind, retryable):
    with pytest.raises(LLMError) as err:
        ClaudeClient(settings, sdk=FakeSDK(error=error)).complete([{"role": "user", "content": "x"}])
    assert err.value.kind == kind
    assert err.value.retryable is retryable


def test_empty_messages_rejected_before_api_call(settings):
    sdk = FakeSDK(message([text("ok")]))
    with pytest.raises(ValueError):
        ClaudeClient(settings, sdk=sdk).complete([])
    assert sdk.calls == []


def test_missing_api_key_is_a_config_error(clean_env):
    with pytest.raises(ConfigError):
        load_settings(env_file=None)


def test_invalid_effort_is_rejected(clean_env):
    clean_env.setenv("LLM_API_KEY", "k")
    clean_env.setenv("LLM_EFFORT", "turbo")
    with pytest.raises(ConfigError):
        load_settings(env_file=None)


def test_settings_repr_hides_api_key(clean_env):
    clean_env.setenv("LLM_API_KEY", "secret-value-123")
    assert "secret-value-123" not in repr(load_settings(env_file=None))


def test_cli_ask_prints_answer_and_handles_errors(settings, capsys):
    ok_client = ClaudeClient(settings, sdk=FakeSDK(message([text("Python and SQL.")])))
    assert ask("What should I learn?", client=ok_client) == 0
    assert "Python and SQL." in capsys.readouterr().out

    failing = ClaudeClient(settings, sdk=FakeSDK(error=status_error(anthropic.RateLimitError, 429)))
    assert ask("What should I learn?", client=failing) == 1
    assert "rate_limit" in capsys.readouterr().err

    assert ask("   ", client=ok_client) == 2
