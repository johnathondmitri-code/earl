"""Stub — qqbot platform stripped from Earl (Telegram only)."""
from typing import Any
def __getattr__(name: str) -> Any:
    raise AttributeError(f"gateway.platforms.qqbot.{name} — disabled in Earl.")
