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
  await sb.files.write("/tmp/sim-remove.py", readFileSync("scripts/sim-remove-event.py", "utf-8"));
  const r = await sb.commands.run(
    "cd $HOME/earl/repo && $HOME/earl/venv/bin/python3 /tmp/sim-remove.py",
    { timeoutMs: 240_000 },
  );
  console.log(r.stdout);
  if (r.stderr) console.error("STDERR:", r.stderr.slice(0, 3000));
  process.exit(r.exitCode);
}

main().catch((e) => { console.error(e); process.exit(99); });
