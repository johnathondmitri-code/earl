"""Stub — codex transport stripped (Anthropic only in Earl)."""
from typing import Any
def __getattr__(name: str) -> Any:
    raise AttributeError(f"agent.transports.codex.{name} — disabled in Earl.")
