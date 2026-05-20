"""Verify the LLM-facing tool schema for pipedream_* actually has properties.

Reproduces the gateway's exact resolution path. Prints the input_schema
that gets sent to Anthropic for each Pipedream tool.
"""
import json
import os
import sys
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

defs = get_tool_definitions(enabled_toolsets=enabled)
for d in defs:
    fn = d["function"]
    if "pipedream" not in fn["name"]:
        continue
    params = fn.get("parameters") or {}
    props = params.get("properties") or {}
    required = params.get("required") or []
    print(f"\n=== {fn['name']} ===")
    print(f"  description (first 200 chars): {fn.get('description', '')[:200]}")
    print(f"  properties: {list(props.keys())}")
    print(f"  required:   {required}")
    print(f"  full params: {json.dumps(params, indent=2)[:600]}")

print("\n=== Now invoke Anthropic with the EXACT tool list the gateway would send ===")
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
resp = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    tools=anthropic_tools,
    messages=[{"role": "user", "content": "List the Pipedream actions available for google_calendar."}],
)
for block in resp.content:
    if block.type == "tool_use":
        print(f"\n[tool_use] {block.name}")
        print(f"  input: {json.dumps(block.input)}")
        if "pipedream" in block.name:
            if block.input:
                print("  ✅ LLM sent real args — parameters are visible")
            else:
                print("  ❌ LLM sent empty args — schema still broken")
    elif block.type == "text":
        print(f"[text] {block.text[:300]}")
