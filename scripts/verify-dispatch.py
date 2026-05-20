"""Call registry.dispatch() with the exact (args, task_id) shape the gateway uses.

Confirms the handler signature fix actually works end-to-end through the
registry, not just in isolation.
"""
import os
import sys
import json
from pathlib import Path

# Load env from gateway
pid = (Path.home() / "earl" / "gateway.pid").read_text().strip()
with open(f"/proc/{pid}/environ", "rb") as f:
    for entry in f.read().split(b"\x00"):
        if entry and b"=" in entry:
            k, _, v = entry.partition(b"=")
            os.environ[k.decode()] = v.decode()

import tools.pipedream_tool  # noqa: register the tools
from tools.registry import registry

print("=== dispatching pipedream_list_accounts via registry.dispatch ===")
result = registry.dispatch("pipedream_list_accounts", {}, task_id="test-task-001", user_task="test")
print(f"raw result type: {type(result).__name__}")
print(f"raw result preview: {str(result)[:300]}")

try:
    parsed = json.loads(result) if isinstance(result, str) else result
    if isinstance(parsed, dict) and "error" in parsed:
        print(f"❌ FAIL: dispatch returned error: {parsed['error']}")
        sys.exit(1)
    accounts = parsed if isinstance(parsed, list) else parsed.get("data", [])
    print(f"\n✅ SUCCESS: dispatch returned {len(accounts)} connected accounts")
    for a in accounts[:5]:
        if isinstance(a, dict):
            app = a.get("app", {})
            print(f"  - {app.get('name', '?')} ({app.get('name_slug', '?')})  external_id={a.get('external_id')}")
    sys.exit(0)
except Exception as e:
    print(f"❌ FAIL parsing result: {type(e).__name__}: {e}")
    sys.exit(1)
