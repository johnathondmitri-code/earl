"""Stub — wecom_crypto platform stripped from Earl (Telegram only)."""
from typing import Any
def __getattr__(name: str) -> Any:
    raise AttributeError(
        f"gateway.platforms.wecom_crypto.{name} — this platform is disabled in Earl."
    )
