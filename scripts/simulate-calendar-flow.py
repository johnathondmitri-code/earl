"""Simulate the LLM's calendar-create flow against the gateway's exact tool set.

Runs locally in the gateway venv, calls Anthropic with the actual tool list,
and dispatches whatever tools Claude calls through registry.dispatch (with
task_id kwarg) until the agent loop terminates or hits ~4 turns.

Surfaces the same crash/error path the bot would hit on Telegram, without
needing a real Telegram message.
"""
import json
import os
import sys
from pathlib import Path

# Load env from running gateway
pid = (Path.home() / "earl" / "gateway.pid").read_text().strip()
with open(f"/proc/{pid}/environ", "rb") as f:
    for e in f.read().split(b"\x00"):
        if e and b"=" in e:
            k, _, v = e.partition(b"=")
            os.environ[k.decode()] = v.decode()

# Setup
import yaml
from earl_cli.config import get_config_path
cfg = yaml.safe_load(get_config_path().read_text()) if get_config_path().exists() else {}

from earl_cli.tools_config import _get_platform_tools
enabled_toolsets = sorted(_get_platform_tools(cfg, "telegram"))

import tools.pipedream_tool  # noqa
from model_tools import get_tool_definitions
from tools.registry import registry

defs = get_tool_definitions(enabled_toolsets=enabled_toolsets)
anthropic_tools = [
    {
        "name": d["function"]["name"],
        "description": d["function"].get("description", "")[:1024],
        "input_schema": d["function"].get("parameters") or {"type": "object", "properties": {}},
    }
    for d in defs
]
print(f"[setup] {len(anthropic_tools)} tools available to Claude")
print(f"[setup] pipedream tools: {[t['name'] for t in anthropic_tools if 'pipedream' in t['name']]}")

import anthropic
client = anthropic.Anthropic(api_key=os.environ.get("EARL_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))

messages = [{
    "role": "user",
    "content": "Add a calendar event to my Google Calendar today at 11 AM that says 'test'.",
}]

MAX_TURNS = 6
for turn in range(MAX_TURNS):
    print(f"\n=== TURN {turn + 1} ===")
    resp = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2048,
        system="You are Earl, an AI assistant. The user is on Telegram. Use the available tools to help them. When the user wants to add a calendar event, first call pipedream_list_actions(app='google_calendar') to discover available actions, then call pipedream_action with the right action_id and configured_props.",
        tools=anthropic_tools,
        messages=messages,
    )
    print(f"[stop_reason] {resp.stop_reason}")

    tool_uses = []
    for block in resp.content:
        if block.type == "text":
            print(f"[text] {block.text[:500]}")
        elif block.type == "tool_use":
            print(f"[tool_use] {block.name}  input={json.dumps(block.input)[:300]}")
            tool_uses.append(block)

    messages.append({"role": "assistant", "content": resp.content})

    if resp.stop_reason != "tool_use" or not tool_uses:
        print("\n[end] no tool_use — conversation ended")
        break

    # Dispatch tools and feed results back (mimicking the gateway)
    tool_results = []
    for tu in tool_uses:
        try:
            result = registry.dispatch(tu.name, tu.input, task_id=f"sim-{turn}", user_task="add calendar event")
            # Coerce result to string for the message history
            if isinstance(result, (dict, list)):
                content_str = json.dumps(result, default=str)[:4000]
            elif result is None:
                content_str = "(tool returned None)"
            else:
                content_str = str(result)[:4000]
            print(f"[result {tu.name}] type={type(result).__name__} preview={content_str[:200]}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": content_str,
            })
        except Exception as ex:
            print(f"[ERROR dispatching {tu.name}] {type(ex).__name__}: {ex}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": f"Dispatch error: {ex}",
                "is_error": True,
            })

    messages.append({"role": "user", "content": tool_results})

print("\n[done]")
