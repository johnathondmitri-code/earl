"""Stub — feishu_comment platform stripped from Earl (Telegram only)."""
from typing import Any
def __getattr__(name: str) -> Any:
    raise AttributeError(
        f"gateway.platforms.feishu_comment.{name} — this platform is disabled in Earl."
    )
