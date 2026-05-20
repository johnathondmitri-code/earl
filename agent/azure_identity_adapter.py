"""Stub for the stripped Azure identity adapter.

Earl uses Anthropic with a single shared API key — no Azure / AD identity.
This module exists so legacy imports inside ``agent/anthropic_adapter.py``
and ``cli.py`` resolve.
"""

from __future__ import annotations

from typing import Any


def is_token_provider(*args: Any, **kwargs: Any) -> bool:
    return False


def build_bearer_http_client(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("Azure identity is not enabled in Earl.")
