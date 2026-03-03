# Zellij Presence

Discord Rich Presence for Zellij, focused on background usage.

## WSL + Windows Discord

Install deps:

```bash
sudo apt-get update
sudo apt-get install -y python3 socat
```

Make sure these are available:
- `zellij` in WSL
- Discord desktop app on Windows
- `npiperelay.exe` installed on Windows (winget/scoop is fine)

Start in background:

```bash
make bg-start
```

Manage:

```bash
make bg-status   # show daemon status
make bg-logs     # tail logs
make bg-stop     # stop daemon
```

## Linux/macOS

Install deps:

```bash
# Linux
sudo apt-get update && sudo apt-get install -y python3

# macOS
brew install python
```

Make sure `zellij` is installed.

Start in background (local mode):

```bash
make bg-start-local
```

Stop:

```bash
make bg-stop
```

## If Stop Does Not Clear

```bash
make bg-stop
ps -ef | grep -Ei "zellij_presence|run-wsl-discord|npiperelay\.exe -ep -s //\./pipe/discord-ipc-" | grep -v grep || true
```
