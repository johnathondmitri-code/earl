/** Sync run_agent.py + gateway/run.py + tools/pipedream_tool.py to a sandbox. */
import { Sandbox } from "e2b";
import { readFileSync } from "node:fs";
import { join } from "node:path";

function ld(p: string) {
  try {
    for (const l of readFileSync(p, "utf-8").split("\n")) {
      const m = l.trim().match(/^([A-Z_][A-Z0-9_]*)\s*=\s*"?([^"\n]*)"?\s*$/);
      if (m && m[1] && !process.env[m[1]]) process.env[m[1]] = m[2];
    }
  } catch {}
}
ld(join(process.cwd(), ".env.local"));

async function main() {
  const sb = await Sandbox.connect(process.argv[2]!, { apiKey: process.env.E2B_API_KEY });
  for (const [local, remote] of [
    ["run_agent.py", "/home/user/earl/repo/run_agent.py"],
    ["gateway/run.py", "/home/user/earl/repo/gateway/run.py"],
    ["tools/pipedream_tool.py", "/home/user/earl/repo/tools/pipedream_tool.py"],
  ]) {
    const c = readFileSync(local, "utf-8");
    await sb.files.write(remote, c);
    console.log(`✓ ${local} → ${remote}  (${c.length} bytes)`);
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
