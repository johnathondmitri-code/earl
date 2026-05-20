import { Sandbox } from "e2b";
import { readFileSync } from "node:fs";
import { join } from "node:path";

function loadDotenv(p: string) {
  try {
    for (const line of readFileSync(p, "utf-8").split("\n")) {
      const m = line.trim().match(/^([A-Z_][A-Z0-9_]*)\s*=\s*"?([^"\n]*)"?\s*$/);
      if (m && m[1] && !process.env[m[1]]) process.env[m[1]] = m[2];
    }
  } catch {}
}
loadDotenv(join(process.cwd(), ".env.local"));

async function main() {
  const sb = await Sandbox.connect(process.argv[2]!, { apiKey: process.env.E2B_API_KEY });
  const script = readFileSync("scripts/verify-dispatch.py", "utf-8");
  await sb.files.write("/tmp/verify-dispatch.py", script);
  await sb.commands.run('find $HOME/earl/repo -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; find $HOME/earl/repo -name "*.pyc" -delete 2>/dev/null', { timeoutMs: 30_000 });
  const r = await sb.commands.run(
    "cd $HOME/earl/repo && source $HOME/earl/venv/bin/activate && python3 /tmp/verify-dispatch.py",
    { timeoutMs: 60_000 },
  );
  console.log(r.stdout);
  if (r.stderr) console.error(r.stderr);
  process.exit(r.exitCode);
}

main().catch((e) => { console.error(e); process.exit(99); });
