"""Stub — Bedrock provider stripped (Earl ships Anthropic via direct API)."""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    raise AttributeError(
        f"agent.bedrock_adapter.{name} — Bedrock is not enabled in Earl."
    )
