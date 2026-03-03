# Zellij Presence

Privacy-first Discord-like presence for Zellij.

It collects your active Zellij session/tab/pane, sanitizes sensitive data, and publishes structured presence to JSON, optional HTTP, and optional Discord Rich Presence.

## Requirements
- Python 3.11+
- Zellij installed
- Discord desktop app (only if using Discord publisher)

## Quick Start: Linux/macOS
Run this from the repo root:

```bash
bash scripts/run-now.sh
```

What this does:
- creates `/tmp/zellij-presence.toml`
- forces `collector.strategy = "cli"`
- writes presence to `/tmp/zellij-presence.json` when not in dry-run
- starts in `--dry-run` mode by default

Run with file output:

```bash
bash scripts/run-now.sh --no-dry-run
cat /tmp/zellij-presence.json
```

Shortcut:

```bash
make run-now
```

Background mode (no second terminal):

```bash
bash scripts/presence-daemon.sh start --mode local
bash scripts/presence-daemon.sh status
bash scripts/presence-daemon.sh logs
bash scripts/presence-daemon.sh stop
```

## Quick Start: WSL + Windows Discord
1. Open Discord desktop app on Windows.
2. Install dependencies in WSL:

```bash
sudo apt-get install socat
```

3. Run:

```bash
bash scripts/run-wsl-discord.sh
```

The script auto-detects `npiperelay.exe` (winget/scoop common locations), creates a WSL relay socket, enables Discord publishing, and starts the service.
It uses default Discord app ID `1478178019074904085`.

If auto-detect fails, pass explicit path:

```bash
bash scripts/run-wsl-discord.sh --npiperelay "C:\\path\\to\\npiperelay.exe"
```

If you need a different app ID:

```bash
bash scripts/run-wsl-discord.sh --client-id YOUR_DISCORD_APP_ID
```

Background mode (recommended for daily use):

```bash
bash scripts/presence-daemon.sh start --mode wsl-discord
bash scripts/presence-daemon.sh status
bash scripts/presence-daemon.sh logs
bash scripts/presence-daemon.sh stop
```

Makefile shortcuts:

```bash
make bg-start      # WSL Discord mode
make bg-start-local
make bg-status
make bg-logs
make bg-stop
```

## Verify It Is Working
In another terminal:

```bash
cat /tmp/zellij-presence.json
PYTHONPATH=src python3 -m zellij_presence.cli --config /tmp/zellij-presence.toml status
```

For WSL Discord relay issues:

```bash
cat /tmp/zp-discord-relay.log
```

## CLI Commands
If not installed as a package, run with `PYTHONPATH=src`:

```bash
PYTHONPATH=src python3 -m zellij_presence.cli run --config /tmp/zellij-presence.toml --verbose
PYTHONPATH=src python3 -m zellij_presence.cli status --config /tmp/zellij-presence.toml
PYTHONPATH=src python3 -m zellij_presence.cli config init --path /tmp/zellij-presence.toml --force
```

## Config Overview
Default generated config includes:
- `safe_mode = true` by default
- `collector.strategy = "auto" | "plugin" | "cli"`
- `[publish]` JSON file + optional HTTP
- `[publish.discord]` optional Rich Presence
- `[filters]` allowlist/denylist/redaction regex

## Data Safety Defaults
- `safe_mode=true` means only session + tab are published
- `cwd`, `command`, `pane_title` are suppressed in safe mode
- redaction patterns remove likely secrets (tokens/passwords/JWT/API keys)

## Development
Run tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Run full local checks:

```bash
make test-all
```
