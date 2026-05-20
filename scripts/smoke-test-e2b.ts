/**
 * Earl Agent E2B smoke test.
 *
 * Boots a sandbox from the pre-baked `earl-agent` template (built via
 * `e2b template create earl-agent` from e2b.Dockerfile), configures it
 * with workspace env vars, starts the Telegram gateway, and verifies it's
 * alive. With the pre-baked template this takes ~10s instead of ~90s.
 *
 * Run:
 *   pnpm tsx scripts/smoke-test-e2b.ts
 *
 * Required env:
 *   E2B_API_KEY
 *   EARL_ANTHROPIC_API_KEY     — sk-ant-...
 *   EARL_TELEGRAM_BOT_TOKEN    — from @BotFather
 *
 * Optional env:
 *   EARL_WORKSPACE_ID          — defaults to a stable UUID for smoke testing
 *   EARL_COMPANY_NAME          — defaults to "Smoke Test Co"
 *   EARL_COMPANY_SLUG          — defaults to "smoke-test"
 *   EARL_VERTICAL              — defaults to "restoration"
 *   EARL_MEMORY_JSON           — JSON memory blob (if you want Earl to know
 *                                about the workspace's contacts/estimates/etc.)
 *   PIPEDREAM_*                — pass through from local env
 *   KEEP_ALIVE                 — if "1", leave the sandbox running so you can DM the bot.
 *   USE_TEMPLATE               — if "0", boot from default Ubuntu + install from scratch
 *                                (slow path; use only if the template is broken).
 */

import { Sandbox } from "e2b";
import { readFileSync } from "node:fs";
import { join } from "node:path";

function loadDotenv(path: string) {
  try {
    const contents = readFileSync(path, "utf-8");
    for (const line of contents.split("\n")) {
      const m = line.match(/^([A-Z_][A-Z0-9_]*)\s*=\s*"?([^"\n]*)"?\s*$/);
      if (m && m[1] && !process.env[m[1]]) process.env[m[1]] = m[2];
    }
  } catch {
    /* */
  }
}
loadDotenv(join(process.cwd(), ".env.local"));
loadDotenv(join(process.cwd(), "../earl/apps/web/.env.local"));

const E2B_API_KEY = process.env.E2B_API_KEY ?? "";
const ANTHROPIC_KEY =
  process.env.EARL_ANTHROPIC_API_KEY ?? process.env.ANTHROPIC_API_KEY ?? "";
const TELEGRAM_TOKEN =
  process.env.EARL_TELEGRAM_BOT_TOKEN ?? process.env.TELEGRAM_BOT_TOKEN ?? "";

const WORKSPACE_ID =
  process.env.EARL_WORKSPACE_ID ?? "00000000-0000-0000-0000-000000000001";
const COMPANY_NAME = process.env.EARL_COMPANY_NAME ?? "Smoke Test Co";
const COMPANY_SLUG = process.env.EARL_COMPANY_SLUG ?? "smoke-test";
const VERTICAL = process.env.EARL_VERTICAL ?? "restoration";
const MEMORY_JSON = process.env.EARL_MEMORY_JSON ?? "";

const KEEP_ALIVE = process.env.KEEP_ALIVE === "1";
const USE_TEMPLATE = process.env.USE_TEMPLATE !== "0";
const TEMPLATE_NAME = process.env.EARL_TEMPLATE_NAME ?? "earl-agent";

const missing: string[] = [];
if (!E2B_API_KEY) missing.push("E2B_API_KEY");
if (!ANTHROPIC_KEY) missing.push("EARL_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY)");
if (!TELEGRAM_TOKEN) missing.push("EARL_TELEGRAM_BOT_TOKEN (or TELEGRAM_BOT_TOKEN)");
if (missing.length) {
  console.error("✗ Missing required env vars:", missing.join(", "));
  process.exit(2);
}

function fmt(msec: number) {
  return `${(msec / 1000).toFixed(1)}s`;
}

async function main() {
  const t0 = Date.now();
  console.log("Earl E2B smoke test — starting");
  console.log("  workspace_id =", WORKSPACE_ID);
  console.log("  company      =", COMPANY_NAME, `(${COMPANY_SLUG})`);
  console.log("  vertical     =", VERTICAL);
  console.log("  template     =", USE_TEMPLATE ? TEMPLATE_NAME : "default Ubuntu (slow path)");
  console.log("  memory       =", MEMORY_JSON ? `${MEMORY_JSON.length} chars` : "(empty)");
  console.log("  keep_alive   =", KEEP_ALIVE);
  console.log("");

  // ----------------------------------------------------------------------------
  // 1. Provision sandbox
  // ----------------------------------------------------------------------------
  console.log("[1/3] Creating E2B sandbox…");
  const sandbox = USE_TEMPLATE
    ? await Sandbox.create(TEMPLATE_NAME, {
        apiKey: E2B_API_KEY,
        timeoutMs: KEEP_ALIVE ? 60 * 60 * 1000 : 15 * 60 * 1000,
      })
    : await Sandbox.create({
        apiKey: E2B_API_KEY,
        timeoutMs: KEEP_ALIVE ? 60 * 60 * 1000 : 15 * 60 * 1000,
      });
  console.log(`      ✓ sandbox ${sandbox.sandboxId} ready in ${fmt(Date.now() - t0)}`);

  try {
    // ----------------------------------------------------------------------------
    // 2. Start Earl (fast path uses pre-baked template; slow path installs)
    // ----------------------------------------------------------------------------
    const startT = Date.now();
    const pipedreamProjectId = process.env.PIPEDREAM_PROJECT_ID ?? "";
    const pipedreamClientId = process.env.PIPEDREAM_CLIENT_ID ?? "";
    const pipedreamClientSecret = process.env.PIPEDREAM_CLIENT_SECRET ?? "";
    const pipedreamEnv = process.env.PIPEDREAM_ENVIRONMENT ?? "production";

    const envLines = [
      `export EARL_HOME=$HOME/earl`,
      `export EARL_REPO_DIR=$HOME/earl/repo`,
      `export EARL_STATE_DIR=$HOME/earl/state`,
      `export EARL_MEMORY_PATH=$HOME/earl/state/memory.json`,
      `export EARL_WORKSPACE_ID="${WORKSPACE_ID}"`,
      `export EARL_COMPANY_NAME="${COMPANY_NAME.replace(/"/g, '\\"')}"`,
      `export EARL_COMPANY_SLUG="${COMPANY_SLUG}"`,
      `export EARL_VERTICAL="${VERTICAL}"`,
      `export EARL_ANTHROPIC_API_KEY="${ANTHROPIC_KEY}"`,
      `export EARL_TELEGRAM_BOT_TOKEN="${TELEGRAM_TOKEN}"`,
      `export EARL_LOCALE=en`,
      `export EARL_PIPEDREAM_PROJECT_ID="${pipedreamProjectId}"`,
      `export EARL_PIPEDREAM_CLIENT_ID="${pipedreamClientId}"`,
      `export EARL_PIPEDREAM_CLIENT_SECRET="${pipedreamClientSecret}"`,
      `export EARL_PIPEDREAM_ENVIRONMENT="${pipedreamEnv}"`,
      `export EARL_PIPEDREAM_EXTERNAL_USER_ID="${WORKSPACE_ID}"`,
      `export PATH=$HOME/.local/bin:$PATH`,
    ];

    if (MEMORY_JSON) {
      // base64-encode to dodge shell-escape issues with arbitrary JSON
      const b64 = Buffer.from(MEMORY_JSON, "utf-8").toString("base64");
      envLines.push(`export EARL_MEMORY_JSON="$(echo ${b64} | base64 -d)"`);
    }

    const envExports = envLines.join("\n");

    const scriptToRun = USE_TEMPLATE
      ? "$EARL_REPO_DIR/scripts/start-earl.sh"
      : "$EARL_REPO_DIR/scripts/sandbox-install.sh";

    console.log(`[2/3] Running ${USE_TEMPLATE ? "start-earl.sh (fast)" : "sandbox-install.sh (slow)"}…`);

    // Pull (or freshly clone) the Earl repo. The template ships with it
    // pre-cloned at $EARL_REPO_DIR; the slow path needs to clone from scratch.
    // Either way we pull on top to ensure we run the freshest scripts.
    const start = await sandbox.commands.run(
      `set -e
${envExports}
mkdir -p "$EARL_HOME"
if [ -d "$EARL_REPO_DIR/.git" ]; then
  ( cd "$EARL_REPO_DIR" && git pull --rebase --autostash --quiet 2>&1 ) || echo "git pull skipped/failed"
else
  echo "==> Cloning Earl Agent repo into $EARL_REPO_DIR"
  git clone --depth 1 https://github.com/johnathondmitri-code/earl.git "$EARL_REPO_DIR" 2>&1
fi
if [ ! -f "${scriptToRun}" ]; then
  echo "ERROR: script not found at ${scriptToRun}" >&2
  ls -la "$EARL_REPO_DIR/scripts/" 2>&1 >&2 || true
  exit 4
fi
chmod +x ${scriptToRun}
bash ${scriptToRun} 2>&1
echo "EXIT_CODE=$?"`,
      { timeoutMs: USE_TEMPLATE ? 90_000 : 600_000 },
    );

    console.log("      ----- output (last 30 lines) -----");
    console.log(start.stdout.split("\n").slice(-30).join("\n"));
    if (start.stderr) {
      console.log("      ----- stderr -----");
      console.log(start.stderr.split("\n").slice(-15).join("\n"));
    }
    if (start.exitCode !== 0) {
      console.error(`      ✗ start script failed (exit ${start.exitCode})`);
      throw new Error("start failed");
    }
    console.log(`      ✓ Earl up in ${fmt(Date.now() - startT)}`);

    // ----------------------------------------------------------------------------
    // 3. Verify Earl is alive
    // ----------------------------------------------------------------------------
    console.log("[3/3] Verifying gateway…");
    await new Promise((r) => setTimeout(r, 3_000));
    const check = await sandbox.commands.run(
      `if pgrep -f "python -m gateway.run" >/dev/null 2>&1; then
  PID=$(pgrep -f "python -m gateway.run" | head -1)
  echo "ALIVE pid=$PID"
  ps -p $PID -o pid,etime,command 2>/dev/null || true
  echo
  echo '--- last 10 gateway.log lines ---'
  tail -10 $HOME/earl/logs/gateway.log 2>/dev/null
else
  echo "DEAD"
  tail -50 $HOME/earl/logs/gateway.log 2>/dev/null
fi`,
      { timeoutMs: 30_000 },
    );
    console.log(check.stdout);
    if (!check.stdout.includes("ALIVE")) {
      throw new Error("gateway not alive");
    }

    console.log("");
    console.log(`✓ SMOKE TEST PASSED in ${fmt(Date.now() - t0)}`);
    console.log("");
    if (KEEP_ALIVE) {
      console.log(`Sandbox is still running: ${sandbox.sandboxId}`);
      console.log("DM your Telegram bot now — Earl should reply.");
      console.log(`To stop: pnpm exec tsx scripts/kill-sandbox.ts ${sandbox.sandboxId}`);
    } else {
      console.log("Killing sandbox (set KEEP_ALIVE=1 to leave it running).");
    }
  } catch (err) {
    console.error("");
    console.error("✗ SMOKE TEST FAILED:", err instanceof Error ? err.message : String(err));
    if (KEEP_ALIVE) {
      console.error(`Sandbox ${sandbox.sandboxId} still up for debug.`);
    }
    process.exit(1);
  } finally {
    if (!KEEP_ALIVE) {
      await sandbox.kill();
    }
  }
}

main().catch((err) => {
  console.error("Unexpected error:", err);
  process.exit(99);
});
