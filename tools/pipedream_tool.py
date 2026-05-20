"""Pipedream Connect tool — single tool for all third-party app integrations.

Architecture:
    The Earl SaaS dashboard exposes "Connect <App>" buttons that mint a
    Connect Token scoped to the current workspace (`external_user_id = workspace_id`).
    The owner OAuths their account via Pipedream's hosted Connect Link UI.
    Pipedream stores the credentials.

    From inside the sandbox, Earl uses THIS tool to invoke actions on those
    connected accounts. Pipedream executes the actual API calls and returns
    the results, handling token refresh + rate limits.

    The agent doesn't need to know about OAuth, token refresh, or any
    integration-specific API. It just calls:
        pipedream_action(app="gohighlevel", action_id="ghl-create-contact", params={...})

Auth (server → Pipedream):
    Pipedream Connect uses OAuth2 client credentials. Earl-the-org has ONE
    client_id/client_secret pair; we exchange those for a bearer token, cache
    it, and use it on every API call.

Required env (set by the SaaS provisioner):
    EARL_PIPEDREAM_PROJECT_ID         — from Pipedream → project settings
    EARL_PIPEDREAM_CLIENT_ID          — from Pipedream → @ → Accounts → OAuth Clients
    EARL_PIPEDREAM_CLIENT_SECRET      — same place
    EARL_PIPEDREAM_ENVIRONMENT        — "production" | "development"
    EARL_PIPEDREAM_EXTERNAL_USER_ID   — usually equals EARL_WORKSPACE_ID

Reference: https://pipedream.com/docs/connect/api-reference/introduction
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx

try:
    from tools.registry import registry
except Exception:  # pragma: no cover
    registry = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

PIPEDREAM_TOKEN_URL = "https://api.pipedream.com/v1/oauth/token"
PIPEDREAM_API_BASE = "https://api.pipedream.com/v1"


# ----- OAuth access-token caching -----
class _TokenCache:
    """Holds the org-wide Pipedream access token + refresh logic."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get(self) -> str:
        # 60-second skew so we don't accidentally use a token that expired
        # while we're holding it.
        now = time.time()
        if self._token and now < self._expires_at - 60:
            return self._token

        async with self._lock:
            # Re-check inside the lock to avoid thundering herd refreshes
            now = time.time()
            if self._token and now < self._expires_at - 60:
                return self._token

            client_id = os.environ.get("EARL_PIPEDREAM_CLIENT_ID", "")
            client_secret = os.environ.get("EARL_PIPEDREAM_CLIENT_SECRET", "")
            if not client_id or not client_secret:
                raise RuntimeError(
                    "Pipedream not configured — EARL_PIPEDREAM_CLIENT_ID / "
                    "EARL_PIPEDREAM_CLIENT_SECRET missing. The Earl SaaS "
                    "provisioner sets these at sandbox boot."
                )

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    PIPEDREAM_TOKEN_URL,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                )
                resp.raise_for_status()
                payload = resp.json()
            self._token = payload["access_token"]
            self._expires_at = now + float(payload.get("expires_in", 3600))
            logger.info(
                "Pipedream OAuth token refreshed (expires in %.0fs)",
                self._expires_at - now,
            )
            return self._token


_token_cache = _TokenCache()


# ----- Headers helper -----
async def _headers() -> dict[str, str]:
    token = await _token_cache.get()
    env = os.environ.get("EARL_PIPEDREAM_ENVIRONMENT", "production").strip() or "production"
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-PD-Environment": env,
    }


def _project_path() -> str:
    project_id = os.environ.get("EARL_PIPEDREAM_PROJECT_ID", "")
    if not project_id:
        raise RuntimeError("EARL_PIPEDREAM_PROJECT_ID is not set")
    return f"/connect/{project_id}"


def _external_user_id() -> str:
    val = os.environ.get("EARL_PIPEDREAM_EXTERNAL_USER_ID", "") or os.environ.get(
        "EARL_WORKSPACE_ID", ""
    )
    if not val:
        raise RuntimeError("EARL_WORKSPACE_ID is not set; cannot scope Pipedream call")
    return val


# ----- Tool surface -----
TOOL_SCHEMA_ACTION = {
    "name": "pipedream_action",
    "description": (
        "Call a third-party app via Pipedream Connect — GoHighLevel, Jobber, "
        "Housecall Pro, Stripe, QuickBooks Online, Google Calendar, Gmail, "
        "Outlook, Twilio, and 3000+ others. The owner connected their accounts "
        "on the Earl dashboard; Pipedream handles OAuth + token refresh. "
        "Call `pipedream_list_accounts` first if you don't know which apps are "
        "connected. Call `pipedream_list_actions` to discover what actions an "
        "app supports."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action_id": {
                "type": "string",
                "description": (
                    "Pipedream action key, e.g. 'gohighlevel-create-contact', "
                    "'stripe-create-customer', 'gmail-send-email'. "
                    "Use pipedream_list_actions to discover keys."
                ),
            },
            "configured_props": {
                "type": "object",
                "description": (
                    "Action parameters. Must include the auth account id under "
                    "the app-specific auth key (e.g. {'gohighlevel': {'authProvisionId': '<id>'}, ...}). "
                    "The id comes from pipedream_list_accounts."
                ),
            },
        },
        "required": ["action_id", "configured_props"],
    },
}

TOOL_SCHEMA_LIST_ACCOUNTS = {
    "name": "pipedream_list_accounts",
    "description": (
        "List the third-party app accounts the workspace owner has connected. "
        "Use this to discover what's available before calling pipedream_action."
    ),
    "input_schema": {"type": "object", "properties": {}},
}

TOOL_SCHEMA_LIST_ACTIONS = {
    "name": "pipedream_list_actions",
    "description": (
        "List the available actions Pipedream exposes for a given app slug."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "app": {
                "type": "string",
                "description": "App slug, e.g. 'gohighlevel', 'stripe', 'gmail'.",
            },
        },
        "required": ["app"],
    },
}


# ----- Tool handlers -----
async def pipedream_action(
    *, action_id: str, configured_props: dict[str, Any]
) -> dict[str, Any]:
    """Execute a Pipedream Connect action on behalf of the current workspace."""
    logger.info(
        "[pipedream] running action=%s for workspace=%s",
        action_id,
        _external_user_id(),
    )
    headers = await _headers()
    body = {
        "id": action_id,
        "external_user_id": _external_user_id(),
        "configured_props": configured_props,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{PIPEDREAM_API_BASE}{_project_path()}/actions/run",
            headers=headers,
            json=body,
        )
        if resp.status_code >= 400:
            logger.warning(
                "Pipedream action %s returned %s: %s",
                action_id,
                resp.status_code,
                resp.text[:500],
            )
        resp.raise_for_status()
        return resp.json()


async def pipedream_list_accounts() -> list[dict[str, Any]]:
    """List connected accounts scoped to the current workspace."""
    headers = await _headers()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{PIPEDREAM_API_BASE}{_project_path()}/accounts",
            headers=headers,
            params={"external_user_id": _external_user_id()},
        )
        resp.raise_for_status()
        return resp.json().get("data", [])


async def pipedream_list_actions(*, app: str) -> list[dict[str, Any]]:
    """List actions for a given app slug (does not require a connected account)."""
    headers = await _headers()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{PIPEDREAM_API_BASE}{_project_path()}/actions",
            headers=headers,
            params={"app": app},
        )
        resp.raise_for_status()
        return resp.json().get("data", [])


def _is_configured() -> bool:
    return bool(
        os.environ.get("EARL_PIPEDREAM_CLIENT_ID")
        and os.environ.get("EARL_PIPEDREAM_CLIENT_SECRET")
        and os.environ.get("EARL_PIPEDREAM_PROJECT_ID")
    )


# ----- Tool registry binding -----
if registry is not None:
    try:
        registry.register(
            schema=TOOL_SCHEMA_ACTION,
            handler=pipedream_action,
            toolset="earl-pipedream",
            availability=_is_configured,
        )
        registry.register(
            schema=TOOL_SCHEMA_LIST_ACCOUNTS,
            handler=pipedream_list_accounts,
            toolset="earl-pipedream",
            availability=_is_configured,
        )
        registry.register(
            schema=TOOL_SCHEMA_LIST_ACTIONS,
            handler=pipedream_list_actions,
            toolset="earl-pipedream",
            availability=_is_configured,
        )
    except Exception as e:  # pragma: no cover
        logger.warning("Could not register Pipedream tools with registry: %s", e)
