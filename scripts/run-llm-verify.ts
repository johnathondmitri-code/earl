/** Upload + run verify-llm-sees-pipedream.py inside the sandbox. */
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
    console.error("Usage: run-llm-verify.ts <sandboxId>");
    process.exit(2);
  }
  const sb = await Sandbox.connect(sandboxId, { apiKey: process.env.E2B_API_KEY });

  const script = readFileSync("scripts/verify-llm-sees-pipedream.py", "utf-8");
  await sb.files.write("/tmp/verify-llm.py", script);

  const r = await sb.commands.run(
    "cd $HOME/earl/repo && source $HOME/earl/venv/bin/activate && python3 /tmp/verify-llm.py",
    { timeoutMs: 90_000 },
  );
  console.log(r.stdout);
  if (r.stderr) console.error(r.stderr);
  process.exit(r.exitCode);
}

main().catch((err) => {
  console.error(err);
  process.exit(99);
});
