"""Stub — wecom_callback platform stripped from Earl (Telegram only)."""
from typing import Any
def __getattr__(name: str) -> Any:
    raise AttributeError(
        f"gateway.platforms.wecom_callback.{name} — this platform is disabled in Earl."
    )
