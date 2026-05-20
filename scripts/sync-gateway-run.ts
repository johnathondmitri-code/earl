/**
 * Upload the patched gateway/run.py into the live sandbox.
 */
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
  const sandboxId = process.argv[2];
  if (!sandboxId) {
    console.error("Usage: sync-gateway-run.ts <sandboxId>");
    process.exit(2);
  }
  const sb = await Sandbox.connect(sandboxId, { apiKey: process.env.E2B_API_KEY });

  const content = readFileSync("gateway/run.py", "utf-8");
  await sb.files.write("/home/user/earl/repo/gateway/run.py", content);
  console.log(`✓ gateway/run.py uploaded (${content.length} bytes)`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
