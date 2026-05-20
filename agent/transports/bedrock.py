"""Stub — bedrock transport stripped (Anthropic only in Earl)."""
from typing import Any
def __getattr__(name: str) -> Any:
    raise AttributeError(f"agent.transports.bedrock.{name} — disabled in Earl.")
