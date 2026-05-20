import { Sandbox } from "e2b";
import { readFileSync } from "node:fs";
import { join } from "node:path";
function loadDotenv(p: string) {
  try {
    for (const line of readFileSync(p, "utf-8").split("\n")) {
      const m = line.match(/^([A-Z_][A-Z0-9_]*)\s*=\s*"?([^"\n]*)"?\s*$/);
      if (m && m[1] && !process.env[m[1]]) process.env[m[1]] = m[2];
    }
  } catch {}
}
loadDotenv(join(process.cwd(), ".env.local"));

async function main() {
  const id = process.argv[2];
  const cmd = process.argv.slice(3).join(" ") || "uname -a; git --version 2>&1 || echo NO_GIT; ls /opt/earl 2>&1 || echo NO_DIR";
  if (!id) {
    console.error("Usage: tsx scripts/debug-sandbox.ts <sandbox-id> [cmd]");
    process.exit(2);
  }
  const sandbox = await Sandbox.connect(id, { apiKey: process.env.E2B_API_KEY! });
  console.log(`Running on ${id}: ${cmd}`);
  console.log("---");
  const r = await sandbox.commands.run(cmd, {
    timeoutMs: 120_000,
    onStdout: (d) => process.stdout.write(d),
    onStderr: (d) => process.stderr.write(d),
  });
  console.log("\n--- exit", r.exitCode);
}
main().catch((e) => {
  console.error(e);
  process.exit(1);
});
