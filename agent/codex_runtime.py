"""Stub for the stripped Codex runtime.

We ship Anthropic-only. These functions are no-op shims so that legacy
deferred imports inside ``run_agent.py`` resolve. The control flow in
the agent loop selects Anthropic transport and never reaches Codex.
"""

from __future__ import annotations

from typing import Any


def run_codex_stream(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("Codex provider is not enabled in Earl — Anthropic only.")


def run_codex_create_stream_fallback(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("Codex provider is not enabled in Earl — Anthropic only.")


def run_codex_app_server_turn(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("Codex provider is not enabled in Earl — Anthropic only.")
