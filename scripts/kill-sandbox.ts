/**
 * Kill an E2B sandbox by id.
 *
 * Usage:
 *   pnpm tsx scripts/kill-sandbox.ts <sandbox-id>
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
  const id = process.argv[2];
  if (!id) {
    console.error("Usage: pnpm tsx scripts/kill-sandbox.ts <sandbox-id>");
    process.exit(2);
  }
  if (!process.env.E2B_API_KEY) {
    console.error("E2B_API_KEY not set");
    process.exit(2);
  }
  const sandbox = await Sandbox.connect(id, { apiKey: process.env.E2B_API_KEY });
  await sandbox.kill();
  console.log(`✓ killed ${id}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
