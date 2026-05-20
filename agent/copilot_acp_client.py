"""Stub — Copilot ACP client stripped (Earl ships Anthropic only)."""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    raise AttributeError(
        f"agent.copilot_acp_client.{name} — Copilot ACP is not enabled in Earl."
    )
