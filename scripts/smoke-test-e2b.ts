/**
 * Earl Agent E2B smoke test.
 *
 * Single-shot: provision a fresh E2B sandbox, clone Earl Agent into it,
 * configure env vars, run the install script, verify the gateway is alive.
 *
 * Run:
 *   cd /Users/johnathonzamora/Documents/Claude\ Projects/hank/earl-agent
 *   pnpm tsx scripts/smoke-test-e2b.ts
 *
 * Required env:
 *   E2B_API_KEY                — from e2b.dev → API keys
 *   EARL_ANTHROPIC_API_KEY     — sk-ant-...
 *   EARL_TELEGRAM_BOT_TOKEN    — from @BotFather
 *
 * Optional env:
 *   EARL_WORKSPACE_ID          — defaults to a stable UUID for smoke testing
 *   EARL_COMPANY_NAME          — defaults to "Smoke Test Co"
 *   EARL_COMPANY_SLUG          — defaults to "smoke-test"
 *   EARL_VERTICAL              — defaults to "restoration"
 *   EARL_REPO_URL              — public earl repo URL (defaults to johnathondmitri-code/earl)
 *   EARL_REPO_BRANCH           — defaults to "main"
 *   KEEP_ALIVE                 — if "1", leave the sandbox running so you can DM the bot.
 *                                Otherwise the sandbox is killed after the smoke check.
 */

import { Sandbox } from "e2b";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// --- Tiny dotenv loader (avoid extra dep) ---
function loadDotenv(path: string) {
  try {
    const contents = readFileSync(path, "utf-8");
    for (const line of contents.split("\n")) {
      const m = line.match(/^([A-Z_][A-Z0-9_]*)\s*=\s*"?([^"\n]*)"?\s*$/);
      if (m && m[1] && !process.env[m[1]]) process.env[m[1]] = m[2];
    }
  } catch {
    /* file may not exist */
  }
}
loadDotenv(join(process.cwd(), ".env.local"));
loadDotenv(join(process.cwd(), "../earl/apps/web/.env.local"));

// --- Config ---
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

const REPO_URL =
  process.env.EARL_REPO_URL ?? "https://github.com/johnathondmitri-code/earl.git";
const REPO_BRANCH = process.env.EARL_REPO_BRANCH ?? "main";

const KEEP_ALIVE = process.env.KEEP_ALIVE === "1";

// --- Sanity ---
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
  console.log("  repo         =", REPO_URL, "@", REPO_BRANCH);
  console.log("  keep_alive   =", KEEP_ALIVE);
  console.log("");

  // ----------------------------------------------------------------------------
  // 1. Provision sandbox
  // ----------------------------------------------------------------------------
  console.log("[1/6] Creating E2B sandbox (default template, ~3s)…");
  // E2B caps sandbox timeout at 1 hour. Use the max for KEEP_ALIVE so you
  // have time to DM the bot; otherwise 15 min is plenty for the install+verify.
  const sandbox = await Sandbox.create({
    apiKey: E2B_API_KEY,
    timeoutMs: KEEP_ALIVE ? 60 * 60 * 1000 : 15 * 60 * 1000,
  });
  console.log(`      ✓ sandbox ${sandbox.sandboxId} ready in ${fmt(Date.now() - t0)}`);

  try {
    // ----------------------------------------------------------------------------
    // 2. Clone Earl Agent into the sandbox
    // ----------------------------------------------------------------------------
    console.log("[2/6] Cloning Earl Agent repo into $HOME/earl…");
    const cloneT = Date.now();
    const clone = await sandbox.commands.run(
      `mkdir -p $HOME/earl && cd $HOME/earl && git clone --depth 1 --branch ${REPO_BRANCH} ${REPO_URL} repo 2>&1`,
      { timeoutMs: 120_000 },
    );
    if (clone.exitCode !== 0) {
      console.error("      ✗ git clone failed (exit", clone.exitCode + ")");
      console.error(clone.stdout);
      console.error(clone.stderr);
      throw new Error("clone failed");
    }
    console.log(`      ✓ cloned in ${fmt(Date.now() - cloneT)}`);

    // ----------------------------------------------------------------------------
    // 3. Install Python 3.11 if not present
    // ----------------------------------------------------------------------------
    console.log("[3/6] Ensuring Python 3.11 is available…");
    const pyT = Date.now();
    const pyCheck = await sandbox.commands.run(
      "command -v python3.11 || (apt-get update -y 2>&1 && apt-get install -y python3.11 python3.11-venv python3.11-dev 2>&1 | tail -3)",
      { timeoutMs: 300_000 },
    );
    if (pyCheck.exitCode !== 0) {
      console.error("      ✗ python3.11 install failed");
      console.error(pyCheck.stderr);
      throw new Error("python install failed");
    }
    console.log(`      ✓ python3.11 ready in ${fmt(Date.now() - pyT)}`);

    // ----------------------------------------------------------------------------
    // 4. Write env file + run install script
    // ----------------------------------------------------------------------------
    console.log("[4/6] Running sandbox-install.sh (~60-90s for uv + deps)…");
    const installT = Date.now();
    const pipedreamProjectId = process.env.PIPEDREAM_PROJECT_ID ?? "";
    const pipedreamClientId = process.env.PIPEDREAM_CLIENT_ID ?? "";
    const pipedreamClientSecret = process.env.PIPEDREAM_CLIENT_SECRET ?? "";
    const pipedreamEnv = process.env.PIPEDREAM_ENVIRONMENT ?? "production";

    const envExports = [
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
      // Pipedream — optional. If unset in the local env, these vars are empty
      // strings; the agent's pipedream_tool gracefully reports "not configured."
      `export EARL_PIPEDREAM_PROJECT_ID="${pipedreamProjectId}"`,
      `export EARL_PIPEDREAM_CLIENT_ID="${pipedreamClientId}"`,
      `export EARL_PIPEDREAM_CLIENT_SECRET="${pipedreamClientSecret}"`,
      `export EARL_PIPEDREAM_ENVIRONMENT="${pipedreamEnv}"`,
      `export EARL_PIPEDREAM_EXTERNAL_USER_ID="${WORKSPACE_ID}"`,
      `export PATH=$HOME/.local/bin:$PATH`,
    ].join("\n");

    const install = await sandbox.commands.run(
      `set -e
${envExports}
chmod +x $HOME/earl/repo/scripts/sandbox-install.sh
bash $HOME/earl/repo/scripts/sandbox-install.sh 2>&1
echo "EXIT_CODE=$?"`,
      { timeoutMs: 600_000 },
    );

    console.log("      ----- install output (last 40 lines) -----");
    console.log(install.stdout.split("\n").slice(-40).join("\n"));
    if (install.stderr) {
      console.log("      ----- install stderr -----");
      console.log(install.stderr.split("\n").slice(-20).join("\n"));
    }

    if (install.exitCode !== 0) {
      console.error(`      ✗ install failed (exit ${install.exitCode})`);
      throw new Error("install failed");
    }
    console.log(`      ✓ install finished in ${fmt(Date.now() - installT)}`);

    // ----------------------------------------------------------------------------
    // 5. Verify gateway process is alive
    // ----------------------------------------------------------------------------
    console.log("[5/6] Verifying Telegram gateway is running…");
    await new Promise((r) => setTimeout(r, 5_000));
    const check = await sandbox.commands.run(
      `if [ -f $HOME/earl/gateway.pid ]; then
  PID=$(cat $HOME/earl/gateway.pid)
  if kill -0 $PID 2>/dev/null; then
    echo "ALIVE pid=$PID"
    ps -p $PID -o pid,etime,command
  else
    echo "DEAD"
    tail -50 $HOME/earl/logs/gateway.log 2>/dev/null || echo "(no gateway.log)"
  fi
else
  echo "NO PID FILE"
  ls -la $HOME/earl/logs/ 2>/dev/null
fi`,
      { timeoutMs: 30_000 },
    );
    console.log(check.stdout);
    if (!check.stdout.includes("ALIVE")) {
      console.error("      ✗ gateway not running");
      const log = await sandbox.commands.run(
        "tail -100 $HOME/earl/logs/gateway.log 2>/dev/null || echo '(no log)'",
      );
      console.log("      ----- gateway.log tail -----");
      console.log(log.stdout);
      throw new Error("gateway not alive");
    }
    console.log("      ✓ gateway alive");

    // ----------------------------------------------------------------------------
    // 6. Done
    // ----------------------------------------------------------------------------
    console.log("");
    console.log(`[6/6] ✓ SMOKE TEST PASSED in ${fmt(Date.now() - t0)}`);
    console.log("");
    if (KEEP_ALIVE) {
      console.log(`Sandbox is still running: ${sandbox.sandboxId}`);
      console.log("DM your Telegram bot now — Earl should reply.");
      console.log("To stop: pnpm tsx scripts/kill-sandbox.ts " + sandbox.sandboxId);
    } else {
      console.log("Killing sandbox (set KEEP_ALIVE=1 to leave it running and DM the bot).");
    }
  } catch (err) {
    console.error("");
    console.error("✗ SMOKE TEST FAILED:", err instanceof Error ? err.message : String(err));
    if (KEEP_ALIVE) {
      console.error(
        `Sandbox ${sandbox.sandboxId} is still up so you can shell in and debug.`,
      );
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
