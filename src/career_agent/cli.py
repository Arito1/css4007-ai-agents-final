"""Command-line entry point.

Week 11: a single LLM request (no tools yet), to prove the integration works:

    python -m career_agent ask "What skills does a Junior Data Analyst need in Almaty?"
"""

from __future__ import annotations

import argparse
import sys

from .config import ConfigError, load_settings
from .llm import ClaudeClient, LLMError

SYSTEM_PROMPT = (
    "You are JumysAI Career Agent, a career assistant for job seekers in Kazakhstan. "
    "Answer briefly and concretely. If you are not sure about a fact (salaries, "
    "specific companies), say so instead of guessing. Answer in the user's language."
)

MAX_QUESTION_CHARS = 2000


def ask(question: str, client=None) -> int:
    question = question.strip()
    if not question:
        print("Error: the question is empty.", file=sys.stderr)
        return 2
    if len(question) > MAX_QUESTION_CHARS:
        print(f"Error: the question is longer than {MAX_QUESTION_CHARS} characters.", file=sys.stderr)
        return 2

    try:
        client = client or ClaudeClient(load_settings())
        response = client.complete(
            [{"role": "user", "content": question}], system=SYSTEM_PROMPT
        )
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except LLMError as exc:
        hint = " (temporary, try again later)" if exc.retryable else ""
        print(f"Model error: {exc}{hint}", file=sys.stderr)
        return 1

    if not response.text:
        print("Model error: empty answer.", file=sys.stderr)
        return 1
    print(response.text)
    if response.truncated:
        print("\n[warning: the answer was cut off at max_tokens]", file=sys.stderr)
    print(
        f"\n[model={response.model} input_tokens={response.input_tokens} "
        f"output_tokens={response.output_tokens}]",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="career_agent", description="JumysAI Career Agent")
    sub = parser.add_subparsers(dest="command", required=True)
    ask_parser = sub.add_parser("ask", help="send one question to the model")
    ask_parser.add_argument("question")
    args = parser.parse_args(argv)

    if args.command == "ask":
        return ask(args.question)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
