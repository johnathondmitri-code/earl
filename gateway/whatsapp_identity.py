"""Stub — WhatsApp identity stripped from Earl (Telegram only in v1).

Provides no-op implementations of the symbols ``gateway/session.py`` imports
so the gateway can boot. Real implementations would normalize WhatsApp phone
ids and detect identifier format — none of which matter for Telegram.
"""

from __future__ import annotations


def canonical_whatsapp_identifier(identifier: str | None) -> str | None:
    """No-op for Earl — Telegram-only. Returns the input unchanged."""
    return identifier


def normalize_whatsapp_identifier(identifier: str | None) -> str | None:
    """No-op for Earl — Telegram-only. Returns the input unchanged."""
    return identifier
