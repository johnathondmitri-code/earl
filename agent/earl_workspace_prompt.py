"""Earl: render per-workspace context as a system-prompt section.

This module is the bridge between :mod:`earl_workspace` (which parses
SaaS-provisioned env vars + the on-disk ``memory.json``) and the agent's
system-prompt assembly in :mod:`agent.system_prompt`.

Why it exists: before this, ``earl_workspace`` was orphaned code — the Hermes
prompt builder loaded ``SOUL.md`` (Earl's identity) but had no notion of
*which company* Earl is working for on this particular sandbox. So every
workspace's agent ran with the same generic persona, ignoring brand voice,
escalation rules, pricing rules, business hours, etc.

The rendered section sits in the **stable** tier of the system prompt so
prompt caching stays warm across turns. Audience-specific context (this
message is from the owner / a customer / a crew member) is injected
per-turn elsewhere — see :mod:`gateway.platforms.telegram`.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Day-of-week names matching the integers stored in CompanyMemory (1=Mon … 7=Sun)
# Earl SaaS uses the same convention as ISO 8601, matching JS getDay()-1.
_DAY_NAMES = ["", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def build_workspace_prompt_section() -> str:
    """Return a markdown section describing the workspace, or empty string.

    Empty string means we couldn't build the section (workspace env not set,
    memory file missing, etc.) — the agent then falls back to identity-only.

    The returned content is appended to the stable system-prompt parts. It
    starts with ``## Working for:`` so it's easy to spot when debugging a
    prompt dump.
    """
    try:
        from earl_workspace import get_workspace
        ws = get_workspace()
    except Exception as e:
        logger.debug("Workspace config unavailable, skipping section: %s", e)
        return ""

    try:
        memory = ws.load_memory()
    except Exception as e:
        logger.warning("Failed to load company memory: %s", e)
        memory = {}

    lines: list[str] = []
    lines.append(f"## Working for: {_company_display(ws, memory)}")
    lines.append("")
    lines.append(
        "This section describes the company you (Earl) work for on this "
        "particular workspace. Read it carefully — the brand voice, escalation "
        "rules, and pricing rules below override your defaults."
    )
    lines.append("")

    # ── Identity ─────────────────────────────────────────────────────────
    lines.extend(_section_identity(ws, memory))

    # ── Brand voice ──────────────────────────────────────────────────────
    voice = _section_brand_voice(memory)
    if voice:
        lines.extend(voice)

    # ── Service area + hours ─────────────────────────────────────────────
    ops = _section_operations(memory)
    if ops:
        lines.extend(ops)

    # ── Payment terms + pricing ──────────────────────────────────────────
    pay = _section_payment(memory)
    if pay:
        lines.extend(pay)

    # ── Escalation rules — these are HARD STOPS ──────────────────────────
    esc = _section_escalation(memory)
    if esc:
        lines.extend(esc)

    # ── Team roster ──────────────────────────────────────────────────────
    team = _section_team(memory)
    if team:
        lines.extend(team)

    return "\n".join(lines).rstrip() + "\n"


# ── Helpers ──────────────────────────────────────────────────────────────


def _company_display(ws, memory: dict[str, Any]) -> str:
    """Human-readable company name for the section header."""
    legal = (memory.get("legalName") or "").strip()
    dba = (memory.get("doingBusinessAs") or "").strip()
    if dba and legal and dba != legal:
        return f"{dba} ({legal})"
    return legal or ws.company_name or ws.company_slug or "this workspace"


def _section_identity(ws, memory: dict[str, Any]) -> list[str]:
    out = ["### Company"]
    legal = (memory.get("legalName") or ws.company_name or "").strip()
    dba = (memory.get("doingBusinessAs") or "").strip()
    if legal:
        out.append(f"- **Legal name:** {legal}")
    if dba and dba != legal:
        out.append(f"- **Doing business as:** {dba}")
    vertical = (memory.get("vertical") or ws.vertical or "").strip()
    if vertical:
        out.append(f"- **Trade:** {vertical}")
    if ws.locale and ws.locale != "en":
        out.append(f"- **Default locale:** {ws.locale}")
    out.append("")
    return out


def _section_brand_voice(memory: dict[str, Any]) -> list[str]:
    voice = memory.get("brandVoice") or {}
    if not isinstance(voice, dict) or not voice:
        return []
    out = ["### Brand voice"]
    tone = voice.get("tone")
    if tone:
        tone_label = {
            "warm_professional": "Warm + professional (the default — friendly, competent, no fluff)",
            "no_nonsense": "No-nonsense, direct (skip pleasantries, get to the point)",
            "friendly_casual": "Friendly + casual (conversational, can use light humor)",
            "formal": "Formal (full sentences, no contractions, respectful titles)",
        }.get(tone, tone)
        out.append(f"- **Tone:** {tone_label}")
    sign_off = voice.get("signOff")
    if sign_off:
        out.append(f"- **Sign off outbound messages with:** {sign_off}")
    forbidden = voice.get("forbiddenPhrases") or []
    if forbidden:
        out.append(
            f"- **Never use these phrases:** {', '.join(str(p) for p in forbidden)}"
        )
    required = voice.get("requiredDisclosures") or []
    if required:
        out.append("- **Required disclosures:**")
        for d in required:
            out.append(f"  - {d}")
    out.append("")
    return out


def _section_operations(memory: dict[str, Any]) -> list[str]:
    out: list[str] = []
    area = memory.get("serviceArea") or {}
    if isinstance(area, dict) and area:
        out.append("### Service area")
        base = area.get("base") or {}
        addr = base.get("address") if isinstance(base, dict) else None
        if area.get("type") == "radius" and area.get("radiusMiles") and addr:
            out.append(
                f"- {area['radiusMiles']} miles around {addr}"
            )
        elif area.get("type") == "radius" and area.get("radiusMiles"):
            out.append(f"- {area['radiusMiles']} mile radius (base address not set)")
        elif area.get("states"):
            out.append(f"- States: {', '.join(area['states'])}")
        elif area.get("counties"):
            out.append(f"- Counties: {', '.join(area['counties'])}")
        elif area.get("zipCodes"):
            out.append(f"- ZIPs: {', '.join(area['zipCodes'])}")
        out.append(
            "- If a job is OUTSIDE this service area, escalate to the owner "
            "and offer to refer the customer to a partner."
        )
        out.append("")

    hours = memory.get("businessHours") or []
    if isinstance(hours, list) and hours:
        out.append("### Business hours")
        for h in hours:
            if not isinstance(h, dict):
                continue
            day = h.get("day")
            day_name = _DAY_NAMES[day] if isinstance(day, int) and 1 <= day <= 7 else f"day {day}"
            open_t = h.get("open") or "—"
            close_t = h.get("close") or "—"
            policy = h.get("after_hours_policy") or ""
            policy_suffix = f" ({policy.replace('_', ' ')} after hours)" if policy else ""
            out.append(f"- {day_name}: {open_t}–{close_t}{policy_suffix}")
        out.append("")
    return out


def _section_payment(memory: dict[str, Any]) -> list[str]:
    pay = memory.get("paymentTerms") or {}
    rules = memory.get("pricingRules") or []
    if not (isinstance(pay, dict) and pay) and not (isinstance(rules, list) and rules):
        return []
    out = ["### Payment + pricing"]
    if isinstance(pay, dict):
        std = pay.get("standard")
        if std:
            out.append(f"- **Standard terms:** {std}")
        deposit = pay.get("deposit")
        if deposit:
            out.append(f"- **Deposit:** {deposit}")
        if pay.get("financingOffered"):
            partner = pay.get("financingPartner") or "(partner not specified)"
            out.append(f"- **Financing:** offered via {partner}")
        else:
            out.append("- **Financing:** not offered")
    if isinstance(rules, list) and rules:
        out.append("- **Pricing rules:**")
        for r in rules:
            out.append(f"  - {r}")
    else:
        out.append(
            "- **No pricing rules configured.** If a customer asks for a price, "
            "DO NOT QUOTE. Escalate to the owner with the request."
        )
    out.append("")
    return out


def _section_escalation(memory: dict[str, Any]) -> list[str]:
    rules = memory.get("escalationRules") or []
    if not (isinstance(rules, list) and rules):
        return []
    out = ["### Hard escalation rules (always escalate to owner — never engage)"]
    for r in rules:
        out.append(f"- {r}")
    out.append("")
    return out


def _section_team(memory: dict[str, Any]) -> list[str]:
    team = memory.get("team") or []
    if not (isinstance(team, list) and team):
        return []
    out = ["### Team"]
    for member in team:
        if not isinstance(member, dict):
            continue
        name = member.get("name") or "(unnamed)"
        role = member.get("role") or ""
        handle = member.get("telegramHandle") or ""
        parts = [name]
        if role:
            parts.append(f"({role})")
        if handle:
            parts.append(f"— Telegram @{handle}")
        out.append(f"- {' '.join(parts)}")
    out.append("")
    return out
