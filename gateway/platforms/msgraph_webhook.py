"""Stub — msgraph_webhook platform stripped from Earl (Telegram only)."""
from typing import Any
def __getattr__(name: str) -> Any:
    raise AttributeError(
        f"gateway.platforms.msgraph_webhook.{name} — this platform is disabled in Earl."
    )
