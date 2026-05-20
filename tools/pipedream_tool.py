"""Pipedream Connect tool — single tool for all third-party app integrations.

Why one tool instead of one-per-app:
    The owner connects their accounts (GHL, Jobber, HCP, Stripe, QBO, Calendar,
    Gmail, ...) once on the Earl SaaS dashboard via Pipedream Connect. Pipedream
    stores OAuth tokens for us, keyed by `external_user_id` (= our workspace_id).
    From inside the sandbox, Earl issues HTTP calls to Pipedream's runtime,
    and Pipedream executes the actual API call on behalf of the workspace.

    This means:
        - No per-integration OAuth code in this repo
        - No per-integration tool wrappers
        - New integrations available the moment the owner connects them
        - Pipedream handles token refresh, rate limits, OAuth dances

Usage from the model:
    pipedream_action(
        app="gohighlevel",
        action_id="ghl-create-contact-v1",
        params={"firstName": "Maria", "phone": "+15125550101"},
    )

Reference: https://pipedream.com/docs/connect
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

try:
    from tools.registry import registry
except Exception:  # pragma: no cover — registry import bootstrap order
    registry = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

PIPEDREAM_API_BASE = "https://api.pipedream.com/v1"

TOOL_SCHEMA = {
    "name": "pipedream_action",
    "description": (
        "Call any third-party app via Pipedream Connect — GoHighLevel, Jobber, "
        "Housecall Pro, Stripe, QuickBooks Online, Google Calendar, Gmail, "
        "Outlook, Twilio, and 3000+ others. The owner connects their accounts "
        "on the Earl dashboard; Pipedream handles OAuth + token refresh. "
        "Use `list_connected_apps` first if you don't know which apps are "
        "connected for this workspace."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "app": {
                "type": "string",
                "description": (
                    "Pipedream app slug, e.g. 'gohighlevel', 'jobber', 'housecall_pro', "
                    "'stripe', 'quickbooks', 'google_calendar', 'gmail', 'outlook'."
                ),
            },
            "action_id": {
                "type": "string",
                "description": (
                    "Pipedream action identifier — usually in the form "
                    "'<app>-<action-name>-v1'. Look these up via "
                    "list_pipedream_actions if unknown."
                ),
            },
            "params": {
                "type": "object",
                "description": "Action parameters. Schema depends on the action.",
            },
        },
        "required": ["app", "action_id", "params"],
    },
}


async def _call_pipedream(
    path: str,
    method: str = "GET",
    *,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    api_key = os.environ.get("EARL_PIPEDREAM_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "Pipedream not configured for this workspace — "
            "EARL_PIPEDREAM_API_KEY missing."
        )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.request(
            method,
            f"{PIPEDREAM_API_BASE}{path}",
            headers=headers,
            json=json_body,
        )
        resp.raise_for_status()
        return resp.json()


async def pipedream_action(*, app: str, action_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """Execute a Pipedream Connect action on behalf of the current workspace."""
    workspace_id = os.environ.get("EARL_WORKSPACE_ID", "")
    project_id = os.environ.get("EARL_PIPEDREAM_PROJECT_ID", "")
    external_user_id = (
        os.environ.get("EARL_PIPEDREAM_EXTERNAL_USER_ID", "") or workspace_id
    )

    if not workspace_id:
        raise RuntimeError("EARL_WORKSPACE_ID not set — cannot scope Pipedream call")
    if not project_id:
        raise RuntimeError("EARL_PIPEDREAM_PROJECT_ID not set")

    payload = {
        "external_user_id": external_user_id,
        "app": app,
        "params": params,
    }
    logger.info(
        "[pipedream] app=%s action=%s workspace=%s",
        app,
        action_id,
        workspace_id,
    )
    return await _call_pipedream(
        f"/connect/{project_id}/actions/{action_id}/run",
        method="POST",
        json_body=payload,
    )


async def list_connected_apps() -> list[dict[str, Any]]:
    """List the Pipedream apps the current workspace has connected."""
    project_id = os.environ.get("EARL_PIPEDREAM_PROJECT_ID", "")
    external_user_id = os.environ.get(
        "EARL_PIPEDREAM_EXTERNAL_USER_ID", ""
    ) or os.environ.get("EARL_WORKSPACE_ID", "")
    if not project_id or not external_user_id:
        return []
    data = await _call_pipedream(
        f"/connect/{project_id}/accounts"
        f"?external_user_id={external_user_id}"
    )
    return data.get("data", [])


# -- Tool registry binding (runs at import time) --
if registry is not None:
    try:
        registry.register(
            schema=TOOL_SCHEMA,
            handler=pipedream_action,
            toolset="earl-pipedream",
            availability=lambda: bool(os.environ.get("EARL_PIPEDREAM_API_KEY")),
        )
    except Exception as e:  # pragma: no cover
        logger.warning("Could not register pipedream_action with registry: %s", e)
