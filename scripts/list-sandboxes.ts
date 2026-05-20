/**
 * List currently-running E2B sandboxes. Run: pnpm tsx scripts/list-sandboxes.ts
 */
import { Sandbox } from "e2b";
import { readFileSync } from "node:fs";

const env = readFileSync(
  "/Users/johnathonzamora/Documents/Claude Projects/hank/earl-agent/.env.local",
  "utf-8",
);
const m = env.match(/^E2B_API_KEY=(\S+)/m);
const apiKey = m ? m[1] : "";

async function main() {
  const raw = (await Sandbox.list({ apiKey })) as unknown;
  const arr =
    (raw as { sandboxes?: unknown[] }).sandboxes ??
    (Array.isArray(raw) ? (raw as unknown[]) : []);
  console.log(`Total running sandboxes: ${arr.length}`);
  for (const s of arr as Array<Record<string, unknown>>) {
    console.log(
      `  ${s["sandboxId"]}  template=${s["templateId"] ?? "?"}  started=${s["startedAt"]}`,
    );
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
