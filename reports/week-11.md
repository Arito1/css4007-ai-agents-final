# Semester Week 11 Progress Report

## Completed Work

- Committed the project proposal and the Week 10 report.
- Set up the Python project: `pyproject.toml` (package `career_agent`, `src/` layout), a virtual environment and `pytest` configuration.
- **Settings module** (`src/career_agent/config.py`):
  - reads the API key, model, effort, max tokens, timeout and retries from environment variables or a local `.env`;
  - validates every value: allowed effort levels, numeric ranges;
  - never prints the API key, even through `repr()`.
- **Claude API adapter** (`src/career_agent/llm.py`). `ClaudeClient.complete(messages, system, tools)` returns a small `LLMResponse`: text, tool calls, stop reason, token usage, and the raw content blocks kept for the later agent loop. API failures become one `LLMError` type, classified by kind (`auth`, `rate_limit`, `server`, `network`, `timeout`, `refusal`, ...) with a `retryable` flag. The agent will use this flag to decide whether to retry or stop.
- **First working request.** The CLI command `python -m career_agent ask "<question>"` sends one question with a career-assistant system prompt and prints the answer and its token usage. It validates input first (rejects an empty question or one over 2000 characters). Model and configuration errors produce clear messages and non-zero exit codes.
- **15 offline tests** (`tests/test_llm.py`): they cover text and tool-call parsing, the request parameters, the per-model refusal fallback, the refusal path, classification of five failure types, rejected empty input, config validation and hiding the key. The Claude SDK is replaced by a fake client, so the tests need no key or network.
- Added a project section to the README (setup, run, test, code layout) and documented every setting in `.env.example`.
- Revised the model choice in the proposal. The default is now `claude-haiku-5-5`, the cheapest current Claude model with tool use, and it stays configurable through `LLM_MODEL`. I first used `claude-opus-5-5`, but it costs too much for development and evaluation runs. The server-side refusal fallback is enabled only for models that support it (Opus, Sonnet and Fable, not Haiku).

## Important Commits

- Commit hash: `a7c6658`
- Description: project proposal (JumysAI Career Agent, level A) and Week 10 report.
- Link: https://github.com/Arito1/css4007-ai-agents-final/commit/a7c6658
- Commit hash: see the commit "Week 11: Claude API adapter, settings, CLI and tests" in the history.
- Description: Python project setup, `ClaudeClient` adapter, settings validation, the `ask` CLI and 14 tests.
- Link: https://github.com/Arito1/css4007-ai-agents-final/commit/013b9d3
- Commit hash: see the commit "Switch default model to Claude Haiku 5.5" in the history.
- Description: the default model becomes Haiku 5.5 because of cost, the refusal fallback is enabled only for models that support it, and a test for that is added.
- Link: https://github.com/Arito1/css4007-ai-agents-final/commits/main

## Current Functionality

- `python -m career_agent ask "What skills does a Junior Data Analyst need in Almaty?"` sends one request to Claude and prints the answer. A live run needs my own API key in a local `.env`.
- Without a key, the app stops with a configuration error before any network call.
- `pytest` runs 15 offline tests, and all of them pass. `npm test` still passes the instructor starter checks.
- There are no tools or agent loop yet. The adapter already accepts tool definitions and returns parsed tool calls, ready for Week 12–13.

## Problems Encountered

- The Anthropic Python SDK 2.x is built on `httpx2`, not `httpx`. Test code that builds SDK exceptions must create `httpx2.Request` / `httpx2.Response` objects.
- On current Claude models some request options behave differently from older tutorials. Current models think adaptively by default, newer ones reject forced `tool_choice`, and the refusal fallback exists only for some models. The adapter must not depend on either.
- Tests must not need a real API key, but they must still exercise the real error classes.

## Solutions

- The adapter is the only module that imports the SDK. Everything else uses `LLMClient.complete()`, so tests inject a fake SDK object while still raising real `anthropic` exception types.
- The adapter uses only stable options: `output_config.effort` controls how deep the model thinks, and tool choice will stay on the default `auto`. Raw content blocks (including thinking) are kept unchanged so they can be passed back in the conversation history.
- Errors are classified once, in the adapter, into retryable and non-retryable. The SDK already retries 429/5xx/network errors (`max_retries`). The agent will add its own limit on top in Week 15.

## What I Learned

- How the Messages API is structured: `system`, `messages`, `tools`, content blocks (`text`, `tool_use`, `thinking`) and `stop_reason` (`end_turn`, `tool_use`, `max_tokens`, `refusal`).
- Why to keep the provider behind a thin adapter: the code becomes testable, swappable and has a single place for error handling.
- The difference between retryable failures (rate limit, 5xx, timeout, network) and permanent ones (bad key, bad request, refusal).
- Keeping secrets out of the repository and out of logs.

## Next Week

- Create the mock dataset: a fictional profile, about 30 fictional vacancies in Kazakhstan cities, and skill relations (*close* skills).
- Implement `get_profile`, `search_vacancies` and `analyze_match` with argument validation and deterministic match scoring.
- Add tests for each function: normal cases, invalid arguments, missing data.
