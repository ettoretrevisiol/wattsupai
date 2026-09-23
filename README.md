# WattsUpAI — Personal Training Coach Agent

Chat-based training assistant that reads your Garmin data + your current goals/schedule
and suggests what to train today.

## How it works

- **Kiro custom agent**: `wattsupai` (config at `~/.kiro/agents/wattsupai.json`)
- **Garmin data**: via the [garmin_mcp](https://github.com/taxuspt/garmin_mcp) MCP server
  (activities, sleep, HRV, training load/status, recovery, etc.)
- **Your context**: this folder (`goals.md`, `schedule.md`) — plain markdown, edit anytime
- **Training log**: `training-log/` — optional place to jot notes after sessions if you want
  the coach to remember how a workout actually felt

## Usage

From a terminal:

```
kiro-cli chat --agent wattsupai
```

Then just talk to it: "what should I train today?", "I only have 30 minutes",
"I feel wrecked, what do you suggest instead?", etc.

## Updating goals/schedule

Just edit `goals.md` / `schedule.md` directly, or tell the agent in chat and ask it to
update the files for you.

## Garmin auth

Tokens live in `~/.garminconnect` (not in this folder — keep credentials out of anything
synced/shared). Tokens last ~6 months. To re-authenticate:

```
uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth
```

## Notes on scope

The Garmin MCP server exposes 110+ tools including write/upload tools (creating and
scheduling workouts directly on your watch). By default this setup only enables
read-only-ish tools (activities, health metrics, training status/load, sleep, HRV, goals)
via `GARMIN_ENABLED_TOOLS` in `~/.kiro/settings/mcp.json`. If you want the coach to be able
to push a planned workout to your watch automatically, ask to expand the tool list.
# wattsupai
