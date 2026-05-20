"""SaaS event callback — Earl Agent → SaaS Postgres.

Every meaningful agent action (inbound message, outbound reply, tool call,
LLM call) gets POSTed to the Earl SaaS at EARL_SAAS_CALLBACK_URL so the
dashboard, audit log, usage meter, and (later) eval harness can see what
actually happened inside the sandbox.

Architecture:

  Sandbox (Earl Agent)                          SaaS (Next.js)
  ──────────────────────                        ──────────────
  emit("inbound_message", {...}) ─────HMAC──>   POST /api/v1/agent/events
                                                  ├─ verify HMAC
                                                  ├─ withBusinessContext()
                                                  └─ INSERT into messages /
                                                     conversations / audit_logs /
                                                     usage_meter

Auth: each request includes
    X-Earl-Workspace-Id: <businessId>
    X-Earl-Signature:    sha256=<hex hmac of raw body>
The HMAC secret is the workspace's `businesses.callback_token`, plumbed into
the sandbox as EARL_SAAS_CALLBACK_TOKEN by the SaaS provisioner.

Resilience:
  - Async, fire-and-forget. Agent code never blocks on the callback.
  - Failures are logged at WARNING and dropped — losing a single event is
    preferable to blocking a tool call.
  - 3-attempt retry with exponential backoff (1s, 2s, 4s) inside the
    background task. Beyond that, give up — Phase 2 doesn't aim for
    durable delivery; that's a later refinement.

Configuration:
    EARL_SAAS_CALLBACK_URL    — Full URL of /api/v1/agent/events.
                                Empty/unset disables callbacks entirely.
    EARL_SAAS_CALLBACK_TOKEN  — HMAC secret (hex). Empty disables callbacks.
    EARL_WORKSPACE_ID         — businessId, used in the workspace_id header.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT_SEC = 10.0
_RETRY_DELAYS_SEC = (1.0, 2.0, 4.0)


def _is_configured() -> bool:
    return bool(
        os.environ.get("EARL_SAAS_CALLBACK_URL")
        and os.environ.get("EARL_SAAS_CALLBACK_TOKEN")
        and os.environ.get("EARL_WORKSPACE_ID")
    )


def _sign(body_bytes: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _post_once(url: str, body_bytes: bytes, headers: dict[str, str]) -> bool:
    """Single POST attempt. Returns True on 2xx, False otherwise."""
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SEC) as client:
            resp = await client.post(url, content=body_bytes, headers=headers)
            if 200 <= resp.status_code < 300:
                return True
            logger.warning(
                "[saas_callback] non-2xx: %d %s",
                resp.status_code,
                resp.text[:200],
            )
            return False
    except Exception as e:
        logger.warning("[saas_callback] POST failed: %s", e)
        return False


async def _emit_with_retry(envelope: dict[str, Any]) -> None:
    """Send the event envelope to SaaS with retries."""
    if not _is_configured():
        return  # no-op when SaaS isn't wired up (e.g. local agent dev)

    url = os.environ["EARL_SAAS_CALLBACK_URL"]
    token = os.environ["EARL_SAAS_CALLBACK_TOKEN"]
    workspace_id = os.environ["EARL_WORKSPACE_ID"]

    body_bytes = json.dumps(envelope, default=str).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Earl-Workspace-Id": workspace_id,
        "X-Earl-Signature": _sign(body_bytes, token),
    }

    # First attempt, then up to 3 retries.
    if await _post_once(url, body_bytes, headers):
        return
    for delay in _RETRY_DELAYS_SEC:
        await asyncio.sleep(delay)
        if await _post_once(url, body_bytes, headers):
            return
    logger.warning("[saas_callback] giving up on event %s", envelope.get("event_id"))


def emit(event_type: str, payload: dict[str, Any]) -> None:
    """Fire-and-forget event emit.

    Schedules the actual POST as a background task on the current event
    loop. Never raises into caller — if there's no loop running yet, log
    and drop (we're probably in startup).
    """
    if not _is_configured():
        return

    envelope = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "workspace_id": os.environ.get("EARL_WORKSPACE_ID", ""),
        "occurred_at": _now_iso(),
        "payload": payload,
    }

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    if loop is None or not loop.is_running():
        # Run synchronously in a fresh loop (rare path — module init etc.)
        try:
            asyncio.run(_emit_with_retry(envelope))
        except Exception as e:
            logger.debug("[saas_callback] sync emit failed: %s", e)
        return

    # Normal path: schedule as background task on the active loop.
    loop.create_task(_emit_with_retry(envelope))


# ── Typed helpers — easier to call from hook sites ─────────────────────

def emit_inbound_message(
    *,
    channel: str,
    external_chat_id: str | int,
    external_message_id: str | int | None,
    sender_external_id: str | int | None,
    sender_handle: str | None,
    sender_name: str | None,
    text: str | None,
    attachments: list[dict[str, Any]] | None = None,
    sender_type: str = "owner",
) -> None:
    emit("inbound_message", {
        "channel": channel,
        "external_chat_id": str(external_chat_id),
        "external_message_id": str(external_message_id) if external_message_id is not None else None,
        "sender_external_id": str(sender_external_id) if sender_external_id is not None else None,
        "sender_handle": sender_handle,
        "sender_name": sender_name,
        "sender_type": sender_type,
        "text": text,
        "attachments": attachments or [],
    })


def emit_outbound_message(
    *,
    channel: str,
    external_chat_id: str | int,
    external_message_id: str | int | None,
    text: str,
    in_reply_to_external_message_id: str | int | None = None,
) -> None:
    emit("outbound_message", {
        "channel": channel,
        "external_chat_id": str(external_chat_id),
        "external_message_id": str(external_message_id) if external_message_id is not None else None,
        "text": text,
        "in_reply_to_external_message_id":
            str(in_reply_to_external_message_id) if in_reply_to_external_message_id is not None else None,
    })


def emit_tool_call(
    *,
    tool_name: str,
    status: str,  # success | error | blocked | skipped
    latency_ms: int = 0,
    input_summary: Any = None,
    output_summary: Any = None,
    skill_id: str | None = None,
    error_message: str | None = None,
    trace_id: str | None = None,
    action_type: str = "tool_call",
) -> None:
    emit("tool_call", {
        "tool_name": tool_name,
        "status": status,
        "latency_ms": int(latency_ms),
        "input_summary": input_summary,
        "output_summary": output_summary,
        "skill_id": skill_id,
        "error_message": error_message,
        "trace_id": trace_id,
        "action_type": action_type,
    })


def emit_llm_call(
    *,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_input_tokens: int = 0,
    cost_cents: int = 0,
    latency_ms: int = 0,
    trace_id: str | None = None,
) -> None:
    emit("llm_call", {
        "model": model,
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "cached_input_tokens": int(cached_input_tokens),
        "cost_cents": int(cost_cents),
        "latency_ms": int(latency_ms),
        "trace_id": trace_id,
    })
