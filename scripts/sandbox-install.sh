#!/bin/bash
# ============================================================================
# Earl Sandbox Install (E2B-flavored, headless, non-root)
# ============================================================================
# Runs inside a per-workspace E2B sandbox at provision time. NOT user-facing.
# The Earl SaaS provisioner sets env vars (EARL_WORKSPACE_ID, EARL_COMPANY_NAME,
# EARL_ANTHROPIC_API_KEY, EARL_TELEGRAM_BOT_TOKEN, EARL_PIPEDREAM_*, etc.) before
# invoking this script.
#
# E2B note: sandboxes run as `user` (non-root) — all paths must be under $HOME.
#
# What it does:
#   1. Install uv (Python project manager)
#   2. Create venv at $EARL_HOME/venv
#   3. uv pip install -e .  (this repo, mounted into the sandbox)
#   4. Validate required env vars + write state files
#   5. Start the gateway via `python -m gateway.run` (Telegram only)
#
# Logs go to $EARL_HOME/logs/install.log and $EARL_HOME/logs/gateway.log.
# Exit non-zero on any failure so the SaaS provisioner sees the error.
# ============================================================================

set -euo pipefail

EARL_HOME="${EARL_HOME:-$HOME/earl}"
EARL_REPO_DIR="${EARL_REPO_DIR:-$HOME/earl/repo}"
EARL_STATE_DIR="${EARL_STATE_DIR:-$HOME/earl/state}"
LOGS="$EARL_HOME/logs"
mkdir -p "$EARL_HOME" "$LOGS" "$EARL_STATE_DIR"
exec > >(tee -a "$LOGS/install.log") 2>&1

echo "==> Earl sandbox install starting at $(date -Iseconds)"
echo "EARL_HOME=$EARL_HOME"
echo "EARL_REPO_DIR=$EARL_REPO_DIR"
echo "EARL_STATE_DIR=$EARL_STATE_DIR"
echo "USER=$(whoami)"

# ----------------------------------------------------------------------------
# 1. Required env validation (fail loud, fast)
# ----------------------------------------------------------------------------
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

# Earl's workspace config defaults memory_path to /var/earl/memory.json. Since
# we run as non-root, override that to under $EARL_STATE_DIR.
export EARL_MEMORY_PATH="${EARL_MEMORY_PATH:-$EARL_STATE_DIR/memory.json}"

# ----------------------------------------------------------------------------
# 2. Install uv if not present
# ----------------------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  echo "==> Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
echo "uv: $(command -v uv) — $(uv --version 2>&1)"

# ----------------------------------------------------------------------------
# 3. Create venv + install Earl
# ----------------------------------------------------------------------------
cd "$EARL_REPO_DIR"
if [ ! -d "$EARL_HOME/venv" ]; then
  echo "==> Creating venv at $EARL_HOME/venv (Python 3.11 via uv)"
  uv venv "$EARL_HOME/venv" --python 3.11
fi
# shellcheck source=/dev/null
source "$EARL_HOME/venv/bin/activate"

echo "==> Installing Earl + dependencies (this takes 60-90s)"
# Use the [all] extra so Telegram + Anthropic + tool deps are present
uv pip install -e ".[all]"

# ----------------------------------------------------------------------------
# 4. Write workspace state files
# ----------------------------------------------------------------------------
echo "$EARL_WORKSPACE_ID" > "$EARL_STATE_DIR/workspace_id"
date -Iseconds > "$EARL_HOME/installed_at"

# Write memory file if SaaS passed one inline (via EARL_MEMORY_JSON env var,
# convenient for E2B which doesn't easily mount files). Otherwise the SaaS
# provisioner is expected to write $EARL_MEMORY_PATH directly.
if [ -n "${EARL_MEMORY_JSON:-}" ]; then
  echo "==> Writing $EARL_MEMORY_PATH from EARL_MEMORY_JSON"
  printf '%s' "$EARL_MEMORY_JSON" > "$EARL_MEMORY_PATH"
fi

# Write the persona overlay (overwrites docker/SOUL.md, the soul file Earl reads)
if [ -n "${EARL_PERSONA_OVERLAY:-}" ]; then
  echo "==> Applying persona overlay to docker/SOUL.md"
  printf '%s' "$EARL_PERSONA_OVERLAY" > "$EARL_REPO_DIR/docker/SOUL.md"
fi

# ----------------------------------------------------------------------------
# 5. Smoke test the install
# ----------------------------------------------------------------------------
echo "==> Smoke test"
cd "$EARL_REPO_DIR"
python -c "import earl_workspace; cfg = earl_workspace.get_workspace(); print(f'OK — workspace={cfg.workspace_id} company={cfg.company_name}')"

# ----------------------------------------------------------------------------
# 6. Bridge EARL_* env vars → the names the Hermes-derived gateway expects
# ----------------------------------------------------------------------------
# Earl SaaS sets EARL_* env vars; the gateway code reads vendor-native names.
export TELEGRAM_BOT_TOKEN="$EARL_TELEGRAM_BOT_TOKEN"
export ANTHROPIC_API_KEY="$EARL_ANTHROPIC_API_KEY"
# Allow any user to talk to the bot — the owner identity check is enforced at
# the workspace level via the Earl SaaS (only the owner has the bot's chat id).
# For a multi-user workspace, set TELEGRAM_ALLOWED_USERS in the per-workspace config.
export GATEWAY_ALLOW_ALL_USERS="${GATEWAY_ALLOW_ALL_USERS:-true}"

# ----------------------------------------------------------------------------
# 7. Start the gateway (Telegram). Background, log to file.
# ----------------------------------------------------------------------------
echo "==> Starting Telegram gateway"
cd "$EARL_REPO_DIR"
nohup python -m gateway.run > "$LOGS/gateway.log" 2>&1 &
WRAPPER_PID=$!
echo $WRAPPER_PID > "$EARL_HOME/gateway.pid"

# Give it a moment to boot. The gateway connects to Telegram and starts
# polling; that connection happens ~3-5s in. Wait + verify by looking for
# the "Connected to Telegram" log line OR a running `python -m gateway.run`
# process (since nohup spawns a child the wrapper pid doesn't always match).
sleep 5
if pgrep -f "python -m gateway.run" >/dev/null 2>&1 || grep -q "Connected to Telegram" "$LOGS/gateway.log" 2>/dev/null; then
  ACTUAL_PID=$(pgrep -f "python -m gateway.run" | head -1)
  if [ -n "$ACTUAL_PID" ]; then
    echo "$ACTUAL_PID" > "$EARL_HOME/gateway.pid"
  fi
  echo "==> Earl gateway running (pid $(cat "$EARL_HOME/gateway.pid"))"
  echo "==> Earl install complete at $(date -Iseconds)"
  exit 0
else
  echo "ERROR: gateway crashed during startup. Tail of gateway.log:" >&2
  tail -50 "$LOGS/gateway.log" >&2
  exit 3
fi
