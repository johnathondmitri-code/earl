"""Stub — WhatsApp identity stripped from Earl (Telegram only in v1).

Provides no-op implementations of the symbols ``gateway/session.py`` and
``gateway/run.py`` import so the Telegram gateway can boot. Real
implementations would normalize WhatsApp phone ids, expand aliases, and
detect identifier formats — none of which matter for Telegram-only Earl.
"""

from __future__ import annotations

from typing import Iterable


def canonical_whatsapp_identifier(identifier: str | None) -> str | None:
    """No-op for Earl — Telegram-only. Returns the input unchanged."""
    return identifier


def normalize_whatsapp_identifier(identifier: str | None) -> str | None:
    """No-op for Earl — Telegram-only. Returns the input unchanged."""
    return identifier


def expand_whatsapp_aliases(
    identifiers: Iterable[str] | str | None,
) -> list[str]:
    """No-op for Earl — Telegram-only. Returns the input as a list (or empty)."""
    if identifiers is None:
        return []
    if isinstance(identifiers, str):
        return [identifiers]
    return list(identifiers)
