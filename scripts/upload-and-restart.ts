/**
 * Upload a local file into a running sandbox via the E2B file API,
 * then optionally restart the gateway.
 *
 * Run:
 *   tsx scripts/upload-and-restart.ts <sandboxId> <localPath> <remotePath> [--restart-gateway]
 */
import { Sandbox } from "e2b";
import { readFileSync } from "node:fs";
import { join } from "node:path";

function loadDotenv(path: string) {
  try {
    for (const line of readFileSync(path, "utf-8").split("\n")) {
      const m = line.trim().match(/^([A-Z_][A-Z0-9_]*)\s*=\s*"?([^"\n]*)"?\s*$/);
      if (m && m[1] && !process.env[m[1]]) process.env[m[1]] = m[2];
    }
  } catch {}
}
loadDotenv(join(process.cwd(), ".env.local"));

async function main() {
  const sandboxId = process.argv[2];
  const localPath = process.argv[3];
  const remotePath = process.argv[4];
  const restart = process.argv.includes("--restart-gateway");
  if (!sandboxId || !localPath || !remotePath) {
    console.error(
      "Usage: upload-and-restart.ts <sandboxId> <localPath> <remotePath> [--restart-gateway]",
    );
    process.exit(2);
  }

  const sb = await Sandbox.connect(sandboxId, { apiKey: process.env.E2B_API_KEY });
  const content = readFileSync(localPath, "utf-8");
  await sb.files.write(remotePath, content);
  console.log(`✓ uploaded ${localPath} → ${remotePath}  (${content.length} bytes)`);

  if (restart) {
    console.log("Restarting gateway…");
    // Strategy: use Python to parse /proc/<pid>/environ (NUL-separated, which
    // tr handles inconsistently across shells), write it to a sourcable env
    // file, kill the gateway, start a fresh one with the captured env.
    const restartScript = `
set -e
OLD_PID=$(pgrep -f "python -m gateway.run" | head -1)
if [ -z "$OLD_PID" ]; then
  echo "no running gateway found; will start fresh"
  OLD_PID=""
fi

ENV_FILE=$(mktemp)
if [ -n "$OLD_PID" ]; then
  echo "old gateway pid=$OLD_PID"
  python3 -c "
import sys
with open('/proc/$OLD_PID/environ', 'rb') as f:
    for entry in f.read().split(b'\\x00'):
        if not entry or b'=' not in entry: continue
        k, _, v = entry.partition(b'=')
        ks = k.decode('utf-8','replace')
        if ks.startswith('EARL_') or ks in ('TELEGRAM_BOT_TOKEN','ANTHROPIC_API_KEY','GATEWAY_ALLOW_ALL_USERS','PATH','HOME','VIRTUAL_ENV'):
            print(f\\"export {ks}={chr(39)}{v.decode('utf-8','replace').replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}{chr(39)}\\")
" > "$ENV_FILE"
  echo "captured $(wc -l < $ENV_FILE) env vars"
else
  exit 4
fi

# Kill old gateway
kill -TERM $OLD_PID 2>/dev/null || true
sleep 1
kill -9 $OLD_PID 2>/dev/null || true
# Also kill any wrappers
pkill -f "python -m gateway.run" 2>/dev/null || true
sleep 1
echo "killed old gateway"

# Start new gateway with captured env + venv
cd $HOME/earl/repo
bash -c "
source $ENV_FILE
source \\$HOME/earl/venv/bin/activate
cd \\$HOME/earl/repo
nohup python -m gateway.run > \\$HOME/earl/logs/gateway.log 2>&1 &
echo \\$!
" > /tmp/wrapper_pid
sleep 5

if pgrep -f "python -m gateway.run" >/dev/null 2>&1; then
  ACTUAL_PID=$(pgrep -f "python -m gateway.run" | head -1)
  echo "$ACTUAL_PID" > $HOME/earl/gateway.pid
  echo "✓ gateway alive — pid=$ACTUAL_PID"
  echo
  echo "--- EARL_* env in new gateway (first 10 vars) ---"
  tr '\\0' '\\n' < /proc/$ACTUAL_PID/environ | grep ^EARL_ | head -10 | sed -E 's/=(.{8}).*/=\\1.../'
  echo
  echo "--- last 15 gateway.log lines ---"
  tail -15 $HOME/earl/logs/gateway.log
else
  echo "✗ gateway crashed during restart"
  tail -50 $HOME/earl/logs/gateway.log
  exit 3
fi
rm -f "$ENV_FILE"
`;
    const result = await sb.commands.run(restartScript, { timeoutMs: 60_000 });
    console.log(result.stdout);
    if (result.stderr) console.error(result.stderr);
    if (result.exitCode !== 0) process.exit(result.exitCode);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(99);
});
