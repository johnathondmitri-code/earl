"""Stub — WhatsApp identity stripped from Earl (Telegram only)."""
from typing import Any
def __getattr__(name: str) -> Any:
    raise AttributeError(f"gateway.whatsapp_identity.{name} — disabled in Earl.")
