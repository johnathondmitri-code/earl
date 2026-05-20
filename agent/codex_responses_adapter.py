"""Stub for the stripped Codex Responses adapter.

The OpenAI Codex Responses provider was removed from this Earl fork; we
only ship Anthropic. The functions below are no-op shims so that legacy
imports from ``run_agent.py`` keep working. If anything actually invokes
these, the agent loop should never call them in practice because the
model selection is Anthropic-only.
"""

from __future__ import annotations

from typing import Any


def _derive_responses_function_call_id(*args: Any, **kwargs: Any) -> str | None:
    return None


def _deterministic_call_id(*args: Any, **kwargs: Any) -> str | None:
    return None


def _split_responses_tool_id(tool_id: str) -> tuple[str, str | None]:
    return tool_id, None


def _summarize_user_message_for_log(*args: Any, **kwargs: Any) -> str:
    return ""
