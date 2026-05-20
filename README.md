# Earl

**Earl is the AI employee that runs in your sandbox.**

Earl is the agent runtime that powers Earl-the-product — the AI coworker SaaS for blue-collar service businesses. It's a fork of [Nous Research's Hermes Agent](https://github.com/NousResearch/hermes-agent) (MIT-licensed), stripped down for one specific use case:

- **One channel:** Telegram (SMS / WhatsApp wired in via Pipedream later)
- **One LLM:** Anthropic Claude (Opus/Sonnet/Haiku, picked per-task)
- **One backend:** runs inside an E2B sandbox, one sandbox per workspace
- **Zero user-facing CLI:** the owner never sees a terminal. They DM their Telegram bot and Earl works.
- **All integrations via Pipedream:** owner connects their apps (GHL, QBO, Calendar) once on the Earl SaaS dashboard; Earl calls them through Pipedream Connect.

## Architecture (where Earl fits)

```
                          EARL SaaS (Next.js)
              owner-facing: signup, billing, dashboard
                              │
                              │ provisions per workspace
                              ↓
                       E2B sandbox (per workspace)
                              │
                              │ runs
                              ↓
                          EARL (this repo)
              ┌───────────────┴───────────────┐
              ↓               ↓               ↓
        agent loop      Telegram gateway   Pipedream tool
        (Anthropic)     (one bot/workspace) (3000+ apps)
                              │
                              ↓
                         Owner's Telegram
                         (DMs the bot, Earl does the work)
```

The SaaS layer + provisioning live in [../earl/](../earl/) (the TypeScript monorepo). This Python repo is the agent runtime that gets installed inside each workspace's E2B sandbox.

## What Earl is (when an owner DMs the bot)

- An AI **employee**, not a chatbot. Acts on behalf of the company, in first person.
- Reads the company's memory (services, pricing rules, brand voice, escalation rules) on every action.
- Takes action by default (autopilot): updates CRM, drafts customer messages, books appointments. Only escalates when uncertain.
- Can be dispatched into roles ("you're the intake person from now on") via the persona system.
- Persistent memory across sessions. Searches its own past conversations. Builds a model of the company over time.
- Autonomously creates new skills from experience.

## What we kept from Hermes

- The agent loop (`agent/conversation_loop.py`, `run_agent.py`) — Hermes's battle-tested tool-use loop
- Memory + auto-curation system
- Subagent system (for persona dispatch and parallel work)
- Skills system + autonomous skill creation
- Cron scheduler
- Telegram gateway adapter
- MCP integration (lets Pipedream + other MCP servers plug in)
- Tools: code execution, file ops, terminal, browser, vision, web search, transcription
- Defensive code patterns (UTF-8 bootstrap, exact-pinned deps, supply-chain protection)

## What we stripped

- All non-Telegram gateway platforms (Discord, Slack, WhatsApp, Signal, Email, etc.)
- All non-Anthropic LLM providers (Bedrock, Gemini, Codex, Azure, Copilot)
- The interactive TUI (`ui-tui/`, `tui_gateway/`) — owner never sees a terminal
- Hermes's web dashboard (`web/`) — Earl SaaS has its own
- Agent Communication Protocol (`acp_*`) — not v1
- Training-data utilities (`batch_runner.py`, `trajectory_compressor.py`) — Nous-only
- OpenClaw migration code — not our path
- Community skills library (`skills/apple`, `creative`, `devops`, `email`, etc.) — replaced with vertical packs in `skills/earl/`
- All non-Telegram tool platforms (Discord tool, Feishu, Microsoft Graph, etc.)

## What we added

- `skills/earl/` — vertical skill packs (restoration, roofing, HVAC, plumbing)
- A Pipedream tool (single tool, calls any of 3000+ apps via the workspace's Connect token)
- Env-driven config (no interactive setup; the Earl SaaS provisioning script sets `EARL_WORKSPACE_ID`, `EARL_COMPANY_NAME`, `EARL_ANTHROPIC_API_KEY`, etc.)
- Headless install script designed for E2B (`scripts/sandbox-install.sh`)

## Install (for the sandbox)

This isn't a user-facing install. The Earl SaaS provisioning code runs this inside each workspace's E2B sandbox:

```bash
curl -fsSL https://raw.githubusercontent.com/johnathondmitri-code/earl/main/scripts/sandbox-install.sh | bash
```

The script reads its config from env vars (set by SaaS provisioner) and starts the gateway. No prompts, no interaction.

## Develop

```bash
git clone https://github.com/johnathondmitri-code/earl.git
cd earl
./setup-earl.sh    # creates venv, installs .[all,dev]
./earl --help
```

## License

MIT — same as upstream Hermes. See [LICENSE](LICENSE).

## Credit

Built on top of [Hermes Agent](https://github.com/NousResearch/hermes-agent) by Nous Research. We track upstream — `git fetch upstream && git merge upstream/main` periodically.
