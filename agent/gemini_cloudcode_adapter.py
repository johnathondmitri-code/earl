"""Stub — Gemini Cloud Code provider stripped (Earl ships Anthropic only)."""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    raise AttributeError(
        f"agent.gemini_cloudcode_adapter.{name} — Gemini Cloud Code is not enabled in Earl."
    )
