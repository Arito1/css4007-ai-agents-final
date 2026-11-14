"""Provider adapter: the only module that talks to the Claude API.

The rest of the agent depends on `LLMClient.complete()` and the small
`LLMResponse` / `LLMError` types below, never on the SDK directly. That keeps
the agent testable with a scripted fake client and makes failures explicit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic

from .config import Settings

# Server-side refusal fallback: if the main model declines a request for a policy
# reason, the API re-runs it on a suitable fallback model inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMResponse:
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    # Unmodified content blocks: the agent loop appends these to the message
    # history as the assistant turn (thinking blocks must be passed back as-is).
    raw_content: list[Any] = field(default_factory=list, repr=False)

    @property
    def truncated(self) -> bool:
        return self.stop_reason == "max_tokens"


class LLMError(Exception):
    """A failed model call, classified so the agent can decide: retry or stop."""

    def __init__(self, kind: str, message: str, *, retryable: bool, status: int | None = None):
        super().__init__(f"[{kind}] {message}")
        self.kind = kind
        self.retryable = retryable
        self.status = status


class LLMClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse: ...


class ClaudeClient:
    """LLMClient implementation backed by the Anthropic Messages API."""

    def __init__(self, settings: Settings, sdk: Any | None = None):
        self.settings = settings
        self._sdk = sdk or anthropic.Anthropic(
            api_key=settings.api_key,
            timeout=settings.timeout_seconds,
            max_retries=settings.max_retries,  # SDK retries 408/409/429/5xx/network itself
        )

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        if not messages:
            raise ValueError("messages must not be empty")

        request: dict[str, Any] = {
            "model": self.settings.model,
            "max_tokens": self.settings.max_tokens,
            "messages": messages,
            "output_config": {"effort": self.settings.effort},
            "betas": [FALLBACK_BETA],
            "fallbacks": "default",
        }
        if system:
            request["system"] = system
        if tools:
            request["tools"] = tools

        try:
            response = self._sdk.beta.messages.create(**request)
        except anthropic.AuthenticationError as exc:
            raise LLMError("auth", "invalid or missing API key", retryable=False, status=401) from exc
        except anthropic.PermissionDeniedError as exc:
            raise LLMError("permission", "API key lacks access", retryable=False, status=403) from exc
        except anthropic.NotFoundError as exc:
            raise LLMError("not_found", f"unknown model {self.settings.model!r}", retryable=False, status=404) from exc
        except anthropic.BadRequestError as exc:
            raise LLMError("bad_request", exc.message, retryable=False, status=400) from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("rate_limit", "rate limited", retryable=True, status=429) from exc
        except anthropic.APIStatusError as exc:
            retryable = exc.status_code >= 500
            kind = "server" if retryable else "api"
            raise LLMError(kind, exc.message, retryable=retryable, status=exc.status_code) from exc
        except anthropic.APITimeoutError as exc:
            raise LLMError("timeout", "request timed out", retryable=True) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("network", "cannot reach the API", retryable=True) from exc

        return parse_response(response)


def parse_response(response: Any) -> LLMResponse:
    """Convert an SDK message into LLMResponse. Refusals become LLMError."""
    stop_reason = response.stop_reason or "unknown"
    if stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        category = getattr(details, "category", None) if details else None
        raise LLMError("refusal", f"model declined the request (category={category})", retryable=False)

    texts: list[str] = []
    calls: list[ToolCall] = []
    for block in response.content:
        if block.type == "text":
            texts.append(block.text)
        elif block.type == "tool_use":
            arguments = block.input if isinstance(block.input, dict) else {}
            calls.append(ToolCall(id=block.id, name=block.name, arguments=arguments))
        # thinking / fallback blocks are kept only in raw_content

    usage = getattr(response, "usage", None)
    return LLMResponse(
        text="\n".join(texts).strip(),
        tool_calls=calls,
        stop_reason=stop_reason,
        model=getattr(response, "model", ""),
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        raw_content=list(response.content),
    )
