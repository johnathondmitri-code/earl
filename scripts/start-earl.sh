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

# 3. Persona overlay
if [ -n "${EARL_PERSONA_OVERLAY:-}" ]; then
  echo "==> Applying persona overlay to docker/SOUL.md"
  printf '%s' "$EARL_PERSONA_OVERLAY" > "$EARL_REPO_DIR/docker/SOUL.md"
fi

# 4. Verify Earl import works (template-build verified this too, but cheap to recheck)
echo "==> Verifying Earl import"
cd "$EARL_REPO_DIR"
/home/user/earl/venv/bin/python -c "import earl_workspace; cfg = earl_workspace.get_workspace(); print(f'OK — workspace={cfg.workspace_id} company={cfg.company_name}')"

# 5. Bridge env vars to vendor-native names
export TELEGRAM_BOT_TOKEN="$EARL_TELEGRAM_BOT_TOKEN"
export ANTHROPIC_API_KEY="$EARL_ANTHROPIC_API_KEY"
export GATEWAY_ALLOW_ALL_USERS="${GATEWAY_ALLOW_ALL_USERS:-true}"

# 6. Start gateway in background
echo "==> Starting Telegram gateway"
nohup /home/user/earl/venv/bin/python -m gateway.run > "$LOGS/gateway.log" 2>&1 &
sleep 3

# 7. Verify it's alive
if pgrep -f "python -m gateway.run" >/dev/null 2>&1; then
  ACTUAL_PID=$(pgrep -f "python -m gateway.run" | head -1)
  echo "$ACTUAL_PID" > "$EARL_HOME/gateway.pid"
  echo "==> Earl gateway running (pid $ACTUAL_PID)"
  echo "==> Earl ready at $(date -Iseconds)"
  exit 0
else
  echo "ERROR: gateway did not start. Tail of gateway.log:" >&2
  tail -50 "$LOGS/gateway.log" >&2
  exit 3
fi
