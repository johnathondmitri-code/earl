"""Earl workspace config — single source of truth for SaaS-driven settings.

When the Earl SaaS provisions a new workspace's sandbox, it sets the env vars
listed in :class:`EarlWorkspaceConfig` and writes the company-memory file. All
other Earl modules read settings from this object so the agent runs with
workspace context without any interactive setup.

Used at:
- `earl_bootstrap.py` start-up (validates required vars are present)
- `gateway/run.py` (picks the Telegram bot token + workspace id)
- `agent/conversation_loop.py` system-prompt assembly (injects company memory)
- `tools/pipedream_tool.py` (resolves which Pipedream connections this workspace owns)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EarlWorkspaceConfig:
    """Per-workspace configuration injected into the sandbox by Earl SaaS."""

    # --- Identity ---
    workspace_id: str
    """UUID of the workspace in the Earl SaaS Postgres."""

    company_name: str
    """Customer-facing company name (used in outbound messages)."""

    company_slug: str
    """URL-safe identifier, also used to namespace files inside the sandbox."""

    vertical: str
    """One of: restoration, roofing, hvac, plumbing, electrical, ..."""

    locale: str = "en"
    """Default locale for outbound messages: 'en' or 'es'."""

    # --- LLM ---
    anthropic_api_key: str = ""
    """Earl's pooled Anthropic key. Usage is metered + upcharged via the SaaS layer."""

    model_default: str = "claude-sonnet-4-6"
    model_reasoning: str = "claude-opus-4-7"
    model_light: str = "claude-haiku-4-5-20251001"

    # --- Telegram ---
    telegram_bot_token: str = ""
    """Per-workspace bot token. Set by the SaaS at provision-time."""

    telegram_owner_chat_id: int = 0
    """The owner's Telegram chat id, captured on first DM. 0 = unset."""

    # --- Pipedream ---
    pipedream_api_key: str = ""
    """Earl's Pipedream API key (single org-wide key)."""

    pipedream_project_id: str = ""
    """Pipedream project id for the Earl org."""

    pipedream_external_user_id: str = ""
    """Per-workspace external user id to scope connections. Set to workspace_id."""

    # --- Reporting back to Earl SaaS ---
    saas_callback_url: str = ""
    """HTTPS URL the agent calls to ship audit logs + usage back to the SaaS Postgres."""

    saas_callback_token: str = ""
    """Bearer token authenticating callback requests."""

    # --- Memory + behavior ---
    memory_path: str = "/var/earl/memory.json"
    """Path inside the sandbox where company memory is mounted as JSON."""

    persona_overlay: str = ""
    """Optional persona dispatch ('You're the intake coordinator'). Empty = default Earl persona."""

    # --- Limits ---
    monthly_interactions_included: int = 20_000
    monthly_interactions_used: int = 0
    overage_per_interaction_usd: float = 0.005

    # --- Diagnostics ---
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "EarlWorkspaceConfig":
        """Build the config from environment variables.

        Required:
            EARL_WORKSPACE_ID
            EARL_COMPANY_NAME
            EARL_COMPANY_SLUG
            EARL_VERTICAL
            EARL_ANTHROPIC_API_KEY
            EARL_TELEGRAM_BOT_TOKEN

        Optional (with defaults):
            EARL_LOCALE
            EARL_MODEL_DEFAULT / EARL_MODEL_REASONING / EARL_MODEL_LIGHT
            EARL_PIPEDREAM_API_KEY / EARL_PIPEDREAM_PROJECT_ID
            EARL_SAAS_CALLBACK_URL / EARL_SAAS_CALLBACK_TOKEN
            EARL_MEMORY_PATH
            EARL_PERSONA_OVERLAY
            EARL_MONTHLY_INTERACTIONS_INCLUDED
            EARL_OVERAGE_PER_INTERACTION_USD
        """
        missing: list[str] = []

        def need(key: str) -> str:
            val = os.environ.get(key, "").strip()
            if not val:
                missing.append(key)
            return val

        cfg = cls(
            workspace_id=need("EARL_WORKSPACE_ID"),
            company_name=need("EARL_COMPANY_NAME"),
            company_slug=need("EARL_COMPANY_SLUG"),
            vertical=need("EARL_VERTICAL"),
            anthropic_api_key=need("EARL_ANTHROPIC_API_KEY"),
            telegram_bot_token=need("EARL_TELEGRAM_BOT_TOKEN"),
            locale=os.environ.get("EARL_LOCALE", "en").strip() or "en",
            model_default=os.environ.get("EARL_MODEL_DEFAULT", "claude-sonnet-4-6").strip(),
            model_reasoning=os.environ.get("EARL_MODEL_REASONING", "claude-opus-4-7").strip(),
            model_light=os.environ.get(
                "EARL_MODEL_LIGHT", "claude-haiku-4-5-20251001"
            ).strip(),
            telegram_owner_chat_id=int(os.environ.get("EARL_TELEGRAM_OWNER_CHAT_ID", "0") or "0"),
            pipedream_api_key=os.environ.get("EARL_PIPEDREAM_API_KEY", "").strip(),
            pipedream_project_id=os.environ.get("EARL_PIPEDREAM_PROJECT_ID", "").strip(),
            pipedream_external_user_id=os.environ.get(
                "EARL_PIPEDREAM_EXTERNAL_USER_ID", ""
            ).strip()
            or os.environ.get("EARL_WORKSPACE_ID", "").strip(),
            saas_callback_url=os.environ.get("EARL_SAAS_CALLBACK_URL", "").strip(),
            saas_callback_token=os.environ.get("EARL_SAAS_CALLBACK_TOKEN", "").strip(),
            memory_path=os.environ.get("EARL_MEMORY_PATH", "/var/earl/memory.json").strip(),
            persona_overlay=os.environ.get("EARL_PERSONA_OVERLAY", "").strip(),
            monthly_interactions_included=int(
                os.environ.get("EARL_MONTHLY_INTERACTIONS_INCLUDED", "20000") or "20000"
            ),
            overage_per_interaction_usd=float(
                os.environ.get("EARL_OVERAGE_PER_INTERACTION_USD", "0.005") or "0.005"
            ),
        )

        if missing:
            raise SystemExit(
                "Earl bootstrap failed — missing required env vars: "
                + ", ".join(missing)
                + "\nThe Earl SaaS provisioner should set these before starting the sandbox."
            )

        return cfg

    def load_memory(self) -> dict[str, Any]:
        """Load the workspace's company-memory JSON. Returns {} if missing."""
        path = Path(self.memory_path)
        if not path.exists():
            logger.warning("Company memory file not found at %s — using empty memory", path)
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.exception("Failed to load company memory from %s: %s", path, e)
            return {}


# Lazy singleton
_workspace: EarlWorkspaceConfig | None = None


def get_workspace() -> EarlWorkspaceConfig:
    """Return the singleton workspace config, building it on first call."""
    global _workspace
    if _workspace is None:
        _workspace = EarlWorkspaceConfig.from_env()
    return _workspace


def reset_workspace_for_test() -> None:
    """Test hook — clears the singleton so tests can re-load with different env."""
    global _workspace
    _workspace = None
