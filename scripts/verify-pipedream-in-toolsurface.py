"""Reproduce the gateway's exact tool-selection path and verify Pipedream is in.

Run inside the sandbox:
  python3 scripts/verify-pipedream-in-toolsurface.py
"""
import os
import sys
from pathlib import Path

# Step 1: Pull env from the running gateway so check_fns return True
gpid_file = Path.home() / "earl" / "gateway.pid"
if gpid_file.exists():
    pid = gpid_file.read_text().strip()
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            for entry in f.read().split(b"\x00"):
                if not entry or b"=" not in entry:
                    continue
                k, _, v = entry.partition(b"=")
                ks = k.decode("utf-8", "replace")
                if ks.startswith("EARL_") or ks in {"TELEGRAM_BOT_TOKEN", "ANTHROPIC_API_KEY"}:
                    os.environ[ks] = v.decode("utf-8", "replace")
        print(f"[setup] loaded env from running gateway pid={pid}")
    except FileNotFoundError:
        print(f"[setup] /proc/{pid}/environ not readable; using current env")

# Step 2: Nuke any cached imports
for mod in list(sys.modules):
    if mod.startswith("tools.") or mod == "tools" or mod in {"toolsets", "model_tools"} or mod.startswith("earl_cli."):
        del sys.modules[mod]

# Step 3: Load the gateway's actual user config
import yaml
from earl_cli.config import get_config_path
cfg_path = get_config_path()
print(f"[setup] config path: {cfg_path}")
if cfg_path.exists():
    with open(cfg_path) as f:
        user_config = yaml.safe_load(f) or {}
else:
    user_config = {}
print(f"[setup] platform_toolsets.telegram = {user_config.get('platform_toolsets', {}).get('telegram')}")

# Step 4: Run the same _get_platform_tools the gateway uses
from earl_cli.tools_config import _get_platform_tools

enabled_toolsets = sorted(_get_platform_tools(user_config, "telegram"))
print()
print(f"=== _get_platform_tools('telegram') returns: ===")
for ts in enabled_toolsets:
    print(f"  {ts}")
print(f"  → total: {len(enabled_toolsets)} toolsets")
print()
print(f"  Pipedream toolset enabled? {'pipedream' in enabled_toolsets}")
print()

# Step 5: Force-import pipedream_tool (mimicking run_agent.py's top-level import)
import tools.pipedream_tool  # noqa
from tools.registry import registry
pd_in_registry = [n for n in registry._tools if "pipedream" in n]
print(f"=== Registry state ===")
print(f"  Pipedream tools in registry: {pd_in_registry}")
print()

# Step 6: Run the gateway's actual get_tool_definitions
from model_tools import get_tool_definitions

defs = get_tool_definitions(enabled_toolsets=enabled_toolsets)
all_names = sorted(d["function"]["name"] for d in defs)
print(f"=== get_tool_definitions output ({len(all_names)} tools) ===")
for n in all_names:
    marker = " ← PIPEDREAM ✓" if "pipedream" in n else ""
    print(f"  {n}{marker}")
print()

pd_in_output = [n for n in all_names if "pipedream" in n]
if pd_in_output:
    print(f"✅ SUCCESS: {len(pd_in_output)} Pipedream tools in LLM tool surface")
    sys.exit(0)
else:
    print("❌ FAIL: Pipedream tools missing from LLM tool surface")
    sys.exit(1)
