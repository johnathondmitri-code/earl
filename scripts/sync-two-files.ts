/**
 * Upload run_agent.py + toolsets.py into the live sandbox so a gateway
 * restart picks up both fixes without depending on a git pull race.
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
  if (!sandboxId) {
    console.error("Usage: sync-two-files.ts <sandboxId>");
    process.exit(2);
  }
  const sb = await Sandbox.connect(sandboxId, { apiKey: process.env.E2B_API_KEY });
  for (const [local, remote] of [
    ["run_agent.py", "/home/user/earl/repo/run_agent.py"],
    ["toolsets.py", "/home/user/earl/repo/toolsets.py"],
  ]) {
    const c = readFileSync(local, "utf-8");
    await sb.files.write(remote, c);
    console.log(`✓ ${local} → ${remote}  (${c.length} bytes)`);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
