"""Stub — Gemini Native provider stripped (Earl ships Anthropic only)."""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    raise AttributeError(
        f"agent.gemini_native_adapter.{name} — Gemini Native is not enabled in Earl."
    )
