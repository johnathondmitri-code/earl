"""Stub — Gemini schema helpers stripped (Earl ships Anthropic only)."""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    raise AttributeError(f"agent.gemini_schema.{name} — Gemini is not enabled in Earl.")
