#!/bin/bash
# ============================================================================
# Earl Sandbox Install (E2B-flavored, headless)
# ============================================================================
# Runs inside a per-workspace E2B sandbox at provision time. NOT user-facing.
# The Earl SaaS provisioner sets env vars (EARL_WORKSPACE_ID, EARL_COMPANY_NAME,
# EARL_ANTHROPIC_API_KEY, EARL_TELEGRAM_BOT_TOKEN, EARL_PIPEDREAM_*, etc.) before
# invoking this script.
#
# What it does:
#   1. Install uv (Python project manager)
#   2. Create venv at /opt/earl/venv (or $EARL_HOME/venv)
#   3. uv pip install -e .  (this repo, mounted into the sandbox)
#   4. Validate required env vars + write a sentinel file
#   5. Start the gateway via earl-gateway (Telegram only)
#
# Logs go to $EARL_HOME/logs/install.log and $EARL_HOME/logs/gateway.log.
# Exit non-zero on any failure so the SaaS provisioner sees the error.
# ============================================================================

set -euo pipefail

EARL_HOME="${EARL_HOME:-/opt/earl}"
EARL_REPO_DIR="${EARL_REPO_DIR:-/opt/earl/repo}"
LOGS="$EARL_HOME/logs"
mkdir -p "$EARL_HOME" "$LOGS"
exec > >(tee -a "$LOGS/install.log") 2>&1

echo "==> Earl sandbox install starting at $(date -Iseconds)"
echo "EARL_HOME=$EARL_HOME"
echo "EARL_REPO_DIR=$EARL_REPO_DIR"

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

# ----------------------------------------------------------------------------
# 2. Install uv if not present
# ----------------------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  echo "==> Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # shellcheck source=/dev/null
  source "$HOME/.local/bin/env" || true
  export PATH="$HOME/.local/bin:$PATH"
fi

# ----------------------------------------------------------------------------
# 3. Create venv + install Earl
# ----------------------------------------------------------------------------
cd "$EARL_REPO_DIR"
if [ ! -d "$EARL_HOME/venv" ]; then
  echo "==> Creating venv at $EARL_HOME/venv"
  uv venv "$EARL_HOME/venv" --python 3.11
fi
# shellcheck source=/dev/null
source "$EARL_HOME/venv/bin/activate"

echo "==> Installing Earl + dependencies"
# Use the [all] extra so Telegram + Anthropic + tool deps are present
uv pip install -e ".[all]"

# ----------------------------------------------------------------------------
# 4. Write workspace state files
# ----------------------------------------------------------------------------
mkdir -p /var/earl
echo "$EARL_WORKSPACE_ID" > /var/earl/workspace_id
date -Iseconds > "$EARL_HOME/installed_at"

# Write memory file if SaaS passed one inline (via EARL_MEMORY_JSON env var,
# convenient for E2B which doesn't easily mount files). Otherwise the SaaS
# provisioner is expected to write /var/earl/memory.json directly.
if [ -n "${EARL_MEMORY_JSON:-}" ]; then
  echo "==> Writing /var/earl/memory.json from EARL_MEMORY_JSON"
  printf '%s' "$EARL_MEMORY_JSON" > /var/earl/memory.json
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
python -c "import earl_workspace; cfg = earl_workspace.get_workspace(); print(f'OK — workspace={cfg.workspace_id} company={cfg.company_name}')"

# ----------------------------------------------------------------------------
# 6. Start the gateway (Telegram). Background, log to file.
# ----------------------------------------------------------------------------
echo "==> Starting Telegram gateway"
nohup python -m gateway.run > "$LOGS/gateway.log" 2>&1 &
echo $! > "$EARL_HOME/gateway.pid"

# Wait a moment + verify the process is alive
sleep 3
if kill -0 "$(cat "$EARL_HOME/gateway.pid")" 2>/dev/null; then
  echo "==> Earl gateway running (pid $(cat "$EARL_HOME/gateway.pid"))"
  echo "==> Earl install complete at $(date -Iseconds)"
  exit 0
else
  echo "ERROR: gateway crashed during startup. Tail of gateway.log:" >&2
  tail -30 "$LOGS/gateway.log" >&2
  exit 3
fi
