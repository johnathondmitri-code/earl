import { Sandbox } from "e2b";
import { readFileSync } from "node:fs";
import { join } from "node:path";

function loadDotenv(path: string) {
  try { for (const line of readFileSync(path, "utf-8").split("\n")) {
    const m = line.trim().match(/^([A-Z_][A-Z0-9_]*)\s*=\s*"?([^"\n]*)"?\s*$/);
    if (m && m[1] && !process.env[m[1]]) process.env[m[1]] = m[2];
  }} catch {}
}
loadDotenv(join(process.cwd(), ".env.local"));

async function main() {
  const sb = await Sandbox.connect("isuvx6tkuu40l32tctnxq", { apiKey: process.env.E2B_API_KEY });
  const script = readFileSync("/tmp/check_telegram_toolset.py", "utf-8");
  await sb.files.write("/tmp/check_telegram_toolset.py", script);
  const r = await sb.commands.run(
    "cd $HOME/earl/repo && source $HOME/earl/venv/bin/activate && python3 /tmp/check_telegram_toolset.py",
    { timeoutMs: 60_000 },
  );
  console.log(r.stdout);
  if (r.stderr) console.error(r.stderr);
}
main().catch((e) => { console.error(e); process.exit(1); });
