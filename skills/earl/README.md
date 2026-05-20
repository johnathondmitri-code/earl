# Earl skill packs

This directory is where Earl's vertical skill packs live. Each subdirectory is a Earl-style skill bundle (manifest + prompts + tools) tailored to a specific trade vertical.

Planned packs:
- `restoration/` — water + fire + mold workflows
- `roofing/` — storm chasing, satellite measurement, financing
- `hvac/` — seasonal maintenance, tune-up reminders
- `plumbing/` — emergency triage, water-heater quoting

Each pack is loaded into a workspace's sandbox at provision time based on the workspace's `vertical` setting.
