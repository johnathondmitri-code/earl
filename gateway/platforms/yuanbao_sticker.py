"""Stub — yuanbao_sticker platform stripped from Earl (Telegram only)."""
from typing import Any
def __getattr__(name: str) -> Any:
    raise AttributeError(
        f"gateway.platforms.yuanbao_sticker.{name} — this platform is disabled in Earl."
    )
