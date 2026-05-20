"""Simulate the "remove that event" flow against the live gateway env.

Includes a prior turn of conversation history so we test the same code
path that crashes when session history is loaded — _hydrate_todo_store
and the MEDIA scan over agent_history.
"""
import json, os, sys
from pathlib import Path

pid = (Path.home() / "earl" / "gateway.pid").read_text().strip()
with open(f"/proc/{pid}/environ", "rb") as f:
    for e in f.read().split(b"\x00"):
        if e and b"=" in e:
            k, _, v = e.partition(b"=")
            os.environ[k.decode()] = v.decode()

import yaml
from earl_cli.config import get_config_path
cfg = yaml.safe_load(get_config_path().read_text()) if get_config_path().exists() else {}

from earl_cli.tools_config import _get_platform_tools
enabled = sorted(_get_platform_tools(cfg, "telegram"))

import tools.pipedream_tool  # noqa
from model_tools import get_tool_definitions
from tools.registry import registry

defs = get_tool_definitions(enabled_toolsets=enabled)
anthropic_tools = [
    {
        "name": d["function"]["name"],
        "description": d["function"].get("description", "")[:1024],
        "input_schema": d["function"].get("parameters") or {"type": "object", "properties": {}},
    }
    for d in defs
]

import anthropic
client = anthropic.Anthropic(api_key=os.environ.get("EARL_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))

# Bootstrap with messy prior history — same content=None pattern that crashes
# _hydrate_todo_store. This is what's in the user's actual session right now.
messages = [
    {"role": "user", "content": "What apps do I have connected through Pipedream?"},
    {"role": "assistant", "content": "Let me check.\nGmail (1 account), Google Drive (1 account), Google Calendar (3 separate connections)."},
    {"role": "user", "content": "Great add an appointment to my calendar today at 11 AM that says test"},
    # The crashed turn: assistant attempted tool calls, server errored, content ended up None
    {"role": "assistant", "content": None},
    {"role": "user", "content": "Remove that event for me"},
]

MAX_TURNS = 6
for turn in range(MAX_TURNS):
    print(f"\n=== TURN {turn + 1} ===")
    # Anthropic strict — drop messages with None content
    clean = [m for m in messages if m.get("content") is not None]
    resp = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2048,
        system="You are Earl, an AI assistant on Telegram. Use the available tools. To remove a calendar event you'll need to list events first via pipedream_action with action_id 'google_calendar-list-events' to find the event id, then call pipedream_action with action_id 'google_calendar-delete-event'.",
        tools=anthropic_tools,
        messages=clean,
    )
    print(f"[stop_reason] {resp.stop_reason}")
    tool_uses = []
    for block in resp.content:
        if block.type == "text":
            print(f"[text] {block.text[:400]}")
        elif block.type == "tool_use":
            print(f"[tool_use] {block.name}  input={json.dumps(block.input)[:300]}")
            tool_uses.append(block)
    messages.append({"role": "assistant", "content": resp.content})

    if resp.stop_reason != "tool_use" or not tool_uses:
        print("\n[end] no tool_use — conversation ended")
        break

    tool_results = []
    for tu in tool_uses:
        try:
            result = registry.dispatch(tu.name, tu.input, task_id=f"sim-{turn}", user_task="remove event")
            if isinstance(result, (dict, list)):
                content_str = json.dumps(result, default=str)[:4000]
            elif result is None:
                content_str = "(tool returned None)"
            else:
                content_str = str(result)[:4000]
            print(f"[result {tu.name}] type={type(result).__name__} preview={content_str[:200]}")
            tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": content_str})
        except Exception as ex:
            print(f"[ERROR dispatching {tu.name}] {type(ex).__name__}: {ex}")
            tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": f"Dispatch error: {ex}", "is_error": True})

    messages.append({"role": "user", "content": tool_results})

print("\n[done]")
