#!/bin/bash
# ============================================================================
# Earl gateway launcher — fast path for pre-baked sandbox templates
# ============================================================================
# When the sandbox boots from the `earl-agent` E2B template (built via
# e2b.Dockerfile), Earl is already installed at /home/user/earl/venv and the
# repo is at /home/user/earl/repo. This script just:
#   1. Validates required EARL_* env vars
#   2. Optionally writes a fresh company memory file from EARL_MEMORY_JSON
#   3. Optionally overlays a persona from EARL_PERSONA_OVERLAY
#   4. Bridges EARL_* → TELEGRAM_BOT_TOKEN / ANTHROPIC_API_KEY
#   5. Starts `python -m gateway.run`
#
# Total: <2s from invocation to gateway-listening (vs ~90s for full install).
#
# Use sandbox-install.sh instead if booting from a vanilla E2B sandbox.
# ============================================================================

set -euo pipefail

EARL_HOME="${EARL_HOME:-/home/user/earl}"
EARL_REPO_DIR="${EARL_REPO_DIR:-/home/user/earl/repo}"
EARL_STATE_DIR="${EARL_STATE_DIR:-/home/user/earl/state}"
LOGS="$EARL_HOME/logs"
mkdir -p "$LOGS" "$EARL_STATE_DIR"
exec > >(tee -a "$LOGS/start.log") 2>&1

echo "==> Earl start at $(date -Iseconds)"

# 0. Pull latest code (template might be slightly behind main)
#    Skip if SKIP_GIT_PULL=1 (e.g., when offline or pinning versions)
if [ "${SKIP_GIT_PULL:-}" != "1" ] && [ -d "$EARL_REPO_DIR/.git" ]; then
  echo "==> Pulling latest from origin"
  ( cd "$EARL_REPO_DIR" && git pull --rebase --autostash --quiet 2>&1 ) || echo "  (git pull failed, continuing with template code)"
fi

# 1. Required env validation
required=(
  EARL_WORKSPACE_ID
  EARL_COMPANY_NAME
  EARL_COMPANY_SLUG
  EARL_VERTICAL
  EARL_ANTHROPIC_API_KEY
  EARL_TELEGRAM_BOT_TOKEN
)
missing=()
for v in "${required[@]}"; do
  if [ -z "${!v:-}" ]; then missing+=("$v"); fi
done
if [ "${#missing[@]}" -ne 0 ]; then
  echo "ERROR: Missing required env vars: ${missing[*]}" >&2
  exit 2
fi
export EARL_MEMORY_PATH="${EARL_MEMORY_PATH:-$EARL_STATE_DIR/memory.json}"

# 2. Memory file (from EARL_MEMORY_JSON env, written by SaaS provisioner)
if [ -n "${EARL_MEMORY_JSON:-}" ]; then
  echo "==> Writing $EARL_MEMORY_PATH (${#EARL_MEMORY_JSON} chars from EARL_MEMORY_JSON)"
  printf '%s' "$EARL_MEMORY_JSON" > "$EARL_MEMORY_PATH"
fi

# 3. SOUL.md composition. The agent's prompt builder reads $EARL_HOME/SOUL.md
#    (NOT the repo's docker/SOUL.md, which is a template). On every boot we
#    rewrite $EARL_HOME/SOUL.md to be: Earl's canonical identity (the repo
#    template) + an optional per-workspace persona overlay below it.
#
#    Doing this unconditionally — not just when EARL_PERSONA_OVERLAY is set —
#    also guarantees we overwrite the bootstrap-seeded default that
#    earl_cli/default_soul.py would write on first run. Without this, a
#    sandbox booted before Earl's canonical identity was wired up would keep
#    serving the old default forever.
SOUL_BASE="$EARL_REPO_DIR/docker/SOUL.md"
SOUL_TARGET="$EARL_HOME/SOUL.md"
if [ -f "$SOUL_BASE" ]; then
  cp "$SOUL_BASE" "$SOUL_TARGET"
  if [ -n "${EARL_PERSONA_OVERLAY:-}" ]; then
    echo "==> Applying workspace persona overlay to $SOUL_TARGET"
    printf '\n\n## Workspace overlay\n\n%s\n' "$EARL_PERSONA_OVERLAY" >> "$SOUL_TARGET"
  else
    echo "==> Using canonical Earl identity (no workspace overlay)"
  fi
else
  echo "WARNING: $SOUL_BASE missing — keeping whatever SOUL.md is already at $SOUL_TARGET" >&2
fi

# 3b. Earl SaaS workspace defaults (docker/earl-defaults.yaml → $EARL_HOME/config.yaml).
#     Copies our "just works for the customer" config overlays on every boot:
#       - memory.provider=holographic for real long-term memory
#       - approvals.mode=smart so dangerous-command prompts don't spam chat
#       - telegram.reactions=true for native read-receipts
#       - display.tool_progress=off (belt-and-suspenders with EARL_TOOL_PROGRESS_MODE)
#       - agent.gateway_notify_interval=300 so "still working" pings are rare
#     See docker/earl-defaults.yaml for the full list and rationale.
DEFAULTS_BASE="$EARL_REPO_DIR/docker/earl-defaults.yaml"
DEFAULTS_TARGET="$EARL_HOME/config.yaml"
if [ -f "$DEFAULTS_BASE" ]; then
  cp "$DEFAULTS_BASE" "$DEFAULTS_TARGET"
  echo "==> Wrote Earl defaults to $DEFAULTS_TARGET ($(wc -c < "$DEFAULTS_TARGET" | tr -d ' ') bytes)"
else
  echo "WARNING: $DEFAULTS_BASE missing — sandbox will run with stock Hermes defaults" >&2
fi

# 4. Verify the full Earl Agent surface imports + the workspace config loads.
#    The template build already verified imports, but the boot-time pull may
#    have introduced a regression — this catches it before the gateway tries
#    to start and dies silently.
echo "==> Verifying Earl import + workspace config"
cd "$EARL_REPO_DIR"
/home/user/earl/venv/bin/python -c "
import earl_workspace, gateway, gateway.run, gateway.platforms.telegram
import agent, tools, providers, plugins, cron
cfg = earl_workspace.get_workspace()
print(f'OK — workspace={cfg.workspace_id} company={cfg.company_name}')"

# 5. Bridge env vars to vendor-native names
export TELEGRAM_BOT_TOKEN="$EARL_TELEGRAM_BOT_TOKEN"
export ANTHROPIC_API_KEY="$EARL_ANTHROPIC_API_KEY"
export GATEWAY_ALLOW_ALL_USERS="${GATEWAY_ALLOW_ALL_USERS:-true}"

# 5b. Earl's consumer-facing display defaults. Hermes ships with developer-tool
#     defaults that leak through to chat ("⚙️ pipedream_action..." bubbles,
#     30 slash commands in the Telegram menu, /verbose hints, etc.). For Earl
#     we want the chat to feel like a person, not a CLI. These env vars
#     suppress those AI-tells. Workspaces can override by setting the var
#     before invoking start-earl.sh.
export EARL_TOOL_PROGRESS_MODE="${EARL_TOOL_PROGRESS_MODE:-off}"        # no "⚙️ tool..." bubbles
export EARL_TELEGRAM_MENU="${EARL_TELEGRAM_MENU:-hidden}"               # empty Telegram slash menu

# 6. Kill any existing gateway BEFORE starting a new one.
#    Without this, re-provisioning a live sandbox stacks gateways: the old
#    one keeps running with stale code (and a stale system prompt), the
#    new one fights for the Telegram polling slot, and pgrep|head -1 below
#    would report the OLDEST pid as "running" — masking the fact that the
#    new gateway was actually started but the stale one is what's serving.
#    This is the carbon-copy guarantee: every start-earl.sh run produces
#    a single, fresh gateway running the current code on disk.
EXISTING_PIDS=$(pgrep -f "python -m gateway.run" 2>/dev/null || true)
if [ -n "$EXISTING_PIDS" ]; then
  echo "==> Stopping stale gateway PIDs: $EXISTING_PIDS"
  # Try graceful first, then escalate
  echo "$EXISTING_PIDS" | xargs -r kill 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    REMAINING=$(pgrep -f "python -m gateway.run" 2>/dev/null || true)
    if [ -z "$REMAINING" ]; then break; fi
    sleep 1
  done
  REMAINING=$(pgrep -f "python -m gateway.run" 2>/dev/null || true)
  if [ -n "$REMAINING" ]; then
    echo "==> Gateway didn't exit gracefully, sending SIGKILL: $REMAINING"
    echo "$REMAINING" | xargs -r kill -9 2>/dev/null || true
    sleep 1
  fi
fi

# 6b. Wipe conversation/session state. Hermes persists conversation history
#     across gateway restarts via sessions/*.jsonl + memories/. If a user
#     pattern (e.g. an "asdf" signature) ends up in that history, the model
#     keeps mirroring it even after the system prompt is updated. A clean
#     restart should mean a clean conversation.
#
#     Opt-in keep via KEEP_CONVERSATION_STATE=1 if the SaaS ever wants to
#     preserve history across an upgrade-restart.
if [ "${KEEP_CONVERSATION_STATE:-}" != "1" ]; then
  if [ -d "$EARL_HOME/sessions" ] || [ -d "$EARL_HOME/memories" ]; then
    echo "==> Clearing conversation/session state (KEEP_CONVERSATION_STATE=1 to preserve)"
    rm -rf "$EARL_HOME/sessions"/* "$EARL_HOME/memories"/* 2>/dev/null || true
  fi
fi

# 7. Start the new gateway. Capture its PID directly so we don't depend on
#    pgrep returning the right one when multiple python processes exist.
echo "==> Starting Telegram gateway"
nohup /home/user/earl/venv/bin/python -m gateway.run > "$LOGS/gateway.log" 2>&1 &
LAUNCH_PID=$!
sleep 3

# 8. Verify the gateway we just launched is still alive. The captured
#    LAUNCH_PID is the actual child we started — not whatever pgrep
#    happens to find. We still cross-check pgrep to make sure no
#    duplicates leaked in.
if kill -0 "$LAUNCH_PID" 2>/dev/null; then
  PGREP_COUNT=$(pgrep -fc "python -m gateway.run" 2>/dev/null || echo 0)
  echo "$LAUNCH_PID" > "$EARL_HOME/gateway.pid"
  echo "==> Earl gateway running (pid $LAUNCH_PID, total matching procs: $PGREP_COUNT)"
  if [ "$PGREP_COUNT" -gt 1 ]; then
    echo "WARNING: $PGREP_COUNT gateway-like processes are running. Expected exactly 1." >&2
    pgrep -af "python -m gateway.run" >&2 || true
  fi
  echo "==> Earl ready at $(date -Iseconds)"
  exit 0
else
  echo "ERROR: gateway pid $LAUNCH_PID did not stay alive. Tail of gateway.log:" >&2
  tail -50 "$LOGS/gateway.log" >&2
  exit 3
fi
