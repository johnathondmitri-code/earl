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
        "Call a third-party app via Pipedream Connect — Google Calendar, Gmail, "
        "Google Drive, GoHighLevel, Jobber, Housecall Pro, Stripe, QuickBooks "
        "Online, Outlook, Twilio, and 3000+ others. The owner connected their "
        "accounts on the Earl dashboard; Pipedream handles OAuth + token "
        "refresh. Call `pipedream_list_accounts` first to find connected "
        "account ids. Call `pipedream_list_actions` to discover action keys. "
        "\n\nEXAMPLE (Google Calendar quick add):\n"
        "  action_id: 'google_calendar-quick-add-event'\n"
        "  account_id: 'apn_jEhK4e4'  (from pipedream_list_accounts)\n"
        "  configured_props: {'calendarId': 'primary', 'text': 'lunch at noon'}"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action_id": {
                "type": "string",
                "description": (
                    "Pipedream action key, format '<app_slug>-<action-name>'. "
                    "Examples: 'google_calendar-quick-add-event', "
                    "'gmail-send-email', 'stripe-create-customer'. "
                    "Use pipedream_list_actions to discover keys."
                ),
            },
            "account_id": {
                "type": "string",
                "description": (
                    "The connected account id (e.g. 'apn_jEhK4e4') from "
                    "pipedream_list_accounts. The handler auto-injects this "
                    "into configured_props under the app's auth key — you "
                    "don't need to nest it yourself."
                ),
            },
            "configured_props": {
                "type": "object",
                "description": (
                    "Action parameters as a flat dict. Do NOT include the "
                    "auth account here — pass it via `account_id` instead. "
                    "Examples: {'text': 'lunch at noon'}, {'to': '+15555551212', "
                    "'body': 'Running 10 min late'}, {'calendarId': 'primary', "
                    "'summary': 'Team standup', 'start': {'dateTime': "
                    "'2026-05-20T11:00:00-07:00'}}."
                ),
            },
        },
        "required": ["action_id", "account_id", "configured_props"],
    },
}

TOOL_SCHEMA_LIST_ACCOUNTS = {
    "name": "pipedream_list_accounts",
    "description": (
        "List the third-party app accounts the workspace owner has connected. "
        "Use this to discover what's available before calling pipedream_action."
    ),
    "parameters": {"type": "object", "properties": {}},
}

TOOL_SCHEMA_LIST_ACTIONS = {
    "name": "pipedream_list_actions",
    "description": (
        "List the available actions Pipedream exposes for a given app slug."
    ),
    "parameters": {
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
# IMPORTANT: every handler takes (args: dict, **kwargs). The registry's
# dispatch() calls `entry.handler(args, **kwargs)` where:
#   - `args` is the LLM-provided input dict (matches the schema's properties)
#   - `**kwargs` carries dispatch-context like `task_id`, `user_task` that the
#     registry adds for every call.
# Handlers MUST absorb the kwargs (or raise TypeError: unexpected kwarg task_id).
# Cache for component schemas — keyed by action_id. We use the schema to find
# the app-typed prop name (e.g. "googleCalendar"), which is NOT the same as
# the snake_case app slug used in action_ids. Pipedream's authProvisionId
# must be nested under the schema's prop name, not the slug — that's the
# difference between "Cannot read oauth_access_token" and a working call.
_component_schema_cache: dict[str, dict[str, Any]] = {}


async def _get_action_app_prop_name(action_id: str) -> str | None:
    """Fetch action schema and return the name of its app-typed prop.

    For 'google_calendar-quick-add-event' this returns 'googleCalendar' —
    that's the key Pipedream's runtime expects in configured_props for the
    OAuth resolution to succeed.
    """
    cached = _component_schema_cache.get(action_id)
    if cached is None:
        headers = await _headers()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{PIPEDREAM_API_BASE}{_project_path()}/components/{action_id}",
                headers=headers,
            )
            if resp.status_code >= 400:
                logger.warning(
                    "[pipedream] component schema fetch failed: %s %s",
                    resp.status_code, resp.text[:200],
                )
                return None
            payload = resp.json()
            cached = payload.get("data") if isinstance(payload, dict) else payload
            if not isinstance(cached, dict):
                return None
            _component_schema_cache[action_id] = cached

    for prop in cached.get("configurable_props") or []:
        if prop.get("type") == "app":
            return prop.get("name")
    return None


async def pipedream_action(
    args: dict[str, Any], **_kwargs: Any
) -> dict[str, Any]:
    """Execute a Pipedream Connect action on behalf of the current workspace.

    Pipedream's action runtime expects the OAuth account to be nested under
    the component's *app-typed prop name* — which is usually camelCase
    (`googleCalendar`, `microsoftOutlook`) and NOT the snake_case app slug
    that appears in the action_id (`google_calendar`, `microsoft_outlook`).
    The mismatch was producing
        TypeError: Cannot read properties of undefined (reading
                   'oauth_access_token')
    from inside the Pipedream component runtime. We look up the component
    schema once per action_id, find the app-typed prop name, and inject the
    auth there.

    LLM-facing args (in `args` dict):
        action_id (required):  e.g. "google_calendar-quick-add-event"
        account_id (required): e.g. "apn_jEhK4e4" (from pipedream_list_accounts)
        configured_props:      flat dict of action params (text, calendarId, etc.)
    """
    action_id = args.get("action_id", "")
    account_id = args.get("account_id") or args.get("auth_account_id") or ""
    configured_props = dict(args.get("configured_props") or {})

    if not action_id:
        return {
            "error": (
                "pipedream_action requires `action_id`. Use pipedream_list_actions("
                "app=<slug>) to find one — e.g. 'google_calendar-quick-add-event'."
            ),
        }

    # Inject the auth account under the schema-defined app prop name.
    # (Falls back to the snake_case slug if we can't fetch the schema —
    # better to try than fail outright; some apps may use slug as prop name.)
    if account_id:
        app_prop_name = await _get_action_app_prop_name(action_id)
        if app_prop_name is None:
            app_prop_name = action_id.split("-", 1)[0] if "-" in action_id else action_id
            logger.warning(
                "[pipedream] could not resolve app prop name for %s; falling "
                "back to slug %r",
                action_id, app_prop_name,
            )
        existing = configured_props.get(app_prop_name)
        if not isinstance(existing, dict) or "authProvisionId" not in existing:
            configured_props[app_prop_name] = {"authProvisionId": account_id}
        app_slug = app_prop_name
    else:
        app_slug = "(no account_id)"

    logger.info(
        "[pipedream] running action=%s app_prop=%s account=%s for workspace=%s",
        action_id,
        app_slug,
        account_id or "(none)",
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


async def pipedream_list_accounts(
    args: dict[str, Any] | None = None, **_kwargs: Any
) -> list[dict[str, Any]]:
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


async def pipedream_list_actions(
    args: dict[str, Any], **_kwargs: Any
) -> list[dict[str, Any]]:
    """List actions for a given app slug (does not require a connected account).

    Returns a slim summary (key + name + description) — the raw schemas can
    be 5–10KB each and overwhelm the LLM context. The model can call
    pipedream_action directly once it has the action key.
    """
    app = args.get("app", "")
    if not app:
        return [{"error": "pipedream_list_actions requires `app` slug, e.g. 'google_calendar'."}]
    headers = await _headers()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{PIPEDREAM_API_BASE}{_project_path()}/actions",
            headers=headers,
            params={"app": app},
        )
        resp.raise_for_status()
        raw = resp.json().get("data", [])
    # Slim each entry to the fields the LLM actually needs to pick an action.
    return [
        {
            "key": a.get("key"),
            "name": a.get("name"),
            "description": (a.get("description") or "")[:200],
        }
        for a in raw
    ]


def _is_configured() -> bool:
    return bool(
        os.environ.get("EARL_PIPEDREAM_CLIENT_ID")
        and os.environ.get("EARL_PIPEDREAM_CLIENT_SECRET")
        and os.environ.get("EARL_PIPEDREAM_PROJECT_ID")
    )


# ----- Tool registry binding -----
# NOTE: the registry's `register()` signature requires `name=` and uses
# `check_fn=` (not `availability=`). All three calls below must match that.
if registry is not None:
    try:
        registry.register(
            name=TOOL_SCHEMA_ACTION["name"],
            toolset="earl-pipedream",
            schema=TOOL_SCHEMA_ACTION,
            handler=pipedream_action,
            check_fn=_is_configured,
            is_async=True,
        )
        registry.register(
            name=TOOL_SCHEMA_LIST_ACCOUNTS["name"],
            toolset="earl-pipedream",
            schema=TOOL_SCHEMA_LIST_ACCOUNTS,
            handler=pipedream_list_accounts,
            check_fn=_is_configured,
            is_async=True,
        )
        registry.register(
            name=TOOL_SCHEMA_LIST_ACTIONS["name"],
            toolset="earl-pipedream",
            schema=TOOL_SCHEMA_LIST_ACTIONS,
            handler=pipedream_list_actions,
            check_fn=_is_configured,
            is_async=True,
        )
    except Exception as e:  # pragma: no cover
        logger.warning("Could not register Pipedream tools with registry: %s", e)
