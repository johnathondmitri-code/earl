/**
 * Quick helper: connect to an existing E2B sandbox and run a one-off command.
 * Usage:
 *   tsx scripts/sandbox-exec.ts <sandboxId> "<bash command>"
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

async function main() {
  const sandboxId = process.argv[2];
  const command = process.argv[3];
  if (!sandboxId || !command) {
    console.error("Usage: sandbox-exec.ts <sandboxId> <bash-cmd>");
    process.exit(2);
  }

  const sandbox = await Sandbox.connect(sandboxId, {
    apiKey: process.env.E2B_API_KEY,
  });
  const result = await sandbox.commands.run(command, { timeoutMs: 60_000 });
  process.stdout.write(result.stdout);
  if (result.stderr) {
    process.stderr.write(result.stderr);
  }
  process.exit(result.exitCode);
}

main().catch((err) => {
  console.error(err);
  process.exit(99);
});
