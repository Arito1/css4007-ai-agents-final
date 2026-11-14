"""Settings loaded from environment variables (and an optional local .env file).

Secrets never live in code. `.env` is git-ignored; `.env.example` documents the keys.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Haiku 5.5: cheapest current Claude model ($0.10 / $0.50 per 1M tokens) with tool use.
DEFAULT_MODEL = "claude-haiku-5-5"
ALLOWED_EFFORT = ("low", "medium", "high", "xhigh", "max")


class ConfigError(ValueError):
    """Raised when required settings are missing or invalid."""


@dataclass(frozen=True)
class Settings:
    api_key: str
    model: str = DEFAULT_MODEL
    max_tokens: int = 16000
    effort: str = "medium"
    timeout_seconds: float = 60.0
    max_retries: int = 2

    def __repr__(self) -> str:  # never print the key, even in debug output
        return (
            f"Settings(api_key='***', model={self.model!r}, max_tokens={self.max_tokens}, "
            f"effort={self.effort!r}, timeout_seconds={self.timeout_seconds}, "
            f"max_retries={self.max_retries})"
        )


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env reader: KEY=VALUE lines, '#' comments. Existing env vars win."""
    file = Path(path)
    if not file.is_file():
        return
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _int(name: str, default: int, low: int, high: int) -> int:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if not low <= value <= high:
        raise ConfigError(f"{name} must be between {low} and {high}, got {value}")
    return value


def load_settings(env_file: str | Path | None = ".env") -> Settings:
    """Build Settings from the environment. Raises ConfigError on bad values."""
    if env_file is not None:
        load_dotenv(env_file)

    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or ""
    if not api_key.strip():
        raise ConfigError(
            "No API key: set LLM_API_KEY in .env (see .env.example) or ANTHROPIC_API_KEY."
        )

    effort = os.environ.get("LLM_EFFORT") or "medium"
    if effort not in ALLOWED_EFFORT:
        raise ConfigError(f"LLM_EFFORT must be one of {ALLOWED_EFFORT}, got {effort!r}")

    timeout_raw = os.environ.get("LLM_TIMEOUT_SECONDS") or "60"
    try:
        timeout = float(timeout_raw)
    except ValueError as exc:
        raise ConfigError(f"LLM_TIMEOUT_SECONDS must be a number, got {timeout_raw!r}") from exc
    if not 1 <= timeout <= 600:
        raise ConfigError("LLM_TIMEOUT_SECONDS must be between 1 and 600")

    return Settings(
        api_key=api_key.strip(),
        model=os.environ.get("LLM_MODEL") or DEFAULT_MODEL,
        max_tokens=_int("LLM_MAX_TOKENS", 16000, 256, 64000),
        effort=effort,
        timeout_seconds=timeout,
        max_retries=_int("LLM_MAX_RETRIES", 2, 0, 5),
    )
