# Earl — Agent Guidelines

You are working in **Earl**, a fork of Hermes Agent customized for the Earl SaaS product (AI employee for blue-collar service businesses).

## Identity rules

- This codebase IS Earl. It is not Hermes. User-facing strings should say "Earl" not "Hermes".
- Internal Python module names use the `earl_*` prefix (renamed from `hermes_*` during fork setup).
- Upstream is `git@github.com:NousResearch/hermes-agent.git` — pull from there periodically to get upstream fixes. Merge conflicts are expected on user-facing strings.

## Hard constraints

1. **Telegram is the only active gateway platform.** Don't add Discord, Slack, etc. tooling unless explicitly requested. SMS/WhatsApp/Email code paths may exist dormant for future Pipedream integration.
2. **Anthropic is the only LLM provider.** Claude Opus/Sonnet/Haiku. Don't bring back OpenAI / Gemini / Bedrock / Azure / OpenRouter adapters; we deleted them during fork setup.
3. **The owner never sees a terminal.** No interactive prompts. All config comes from env vars (`EARL_*`).
4. **Integrations go through Pipedream.** Don't write direct GHL/Jobber/HCP/QBO clients in this repo. There's a single `pipedream_tool.py` that proxies all third-party calls.
5. **Earl runs inside an E2B sandbox.** Per-workspace isolation comes from the sandbox boundary — don't add multi-tenant logic to Earl itself.

## How Earl talks

- First person, as an employee of the company. "I'll handle that." "Done — I followed up with Maria."
- Warm but direct. No corporate-speak. No "How may I assist you?"
- Match the company's brand voice from `EARL_BRAND_VOICE` env var / memory.
- Sign off with the company's signoff if configured.
- Never quote a price not in the configured pricing rules.
- Escalate on legal mentions, refunds, anger, anything outside service area.

## Where things live

- `agent/` — the agent loop (Hermes-derived, kept intact)
- `gateway/` — messaging gateway. `gateway/platforms/telegram.py` is the only active platform.
- `tools/` — agent tools. Each tool self-registers via `tools/registry.py`.
- `tools/pipedream_tool.py` — single tool for all third-party app integrations
- `skills/earl/` — vertical skill packs (Restoration, HVAC, etc.)
- `earl_cli/` — CLI used internally by the sandbox bootstrap; owners never invoke it
- `scripts/sandbox-install.sh` — headless install for E2B
- `earl_bootstrap.py` — Python bootstrap (Windows UTF-8 fix; safe on Linux)

## Don't do these

- Don't re-introduce interactive setup flows. Setup is via env vars.
- Don't re-introduce non-Anthropic providers.
- Don't write provider-specific tools (GHL, Stripe, QBO) when Pipedream covers it.
- Don't expose terminal/CLI commands to the owner.
- Don't add gateway platforms beyond Telegram without an explicit decision.

## What's allowed/encouraged

- Adding new vertical skill packs under `skills/earl/`
- Improving the Pipedream tool surface
- Adding new Anthropic-specific optimizations (prompt caching, batch API, etc.)
- Bumping upstream Hermes and merging in their improvements (memory, subagents, cron, etc.)
- Adding tests that exercise the Telegram → agent → tool → reply loop
