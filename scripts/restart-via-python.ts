/**
 * Upload restart_gateway.py to a running sandbox and execute it. Avoids the
 * shell-escaping nightmare of doing /proc/<pid>/environ parsing via bash.
 *
 * Usage: tsx scripts/restart-via-python.ts <sandboxId>
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
    console.error("Usage: restart-via-python.ts <sandboxId>");
    process.exit(2);
  }
  const sb = await Sandbox.connect(sandboxId, { apiKey: process.env.E2B_API_KEY });

  const script = readFileSync("scripts/restart_gateway.py", "utf-8");
  await sb.files.write("/tmp/restart_gateway.py", script);
  console.log(`✓ uploaded restart_gateway.py`);

  const result = await sb.commands.run(
    "python3 /tmp/restart_gateway.py",
    { timeoutMs: 60_000 },
  );
  console.log(result.stdout);
  if (result.stderr) console.error(result.stderr);
  process.exit(result.exitCode);
}

main().catch((err) => {
  console.error(err);
  process.exit(99);
});
