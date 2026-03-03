.PHONY: test-all
.PHONY: run-now
.PHONY: run-wsl-discord
.PHONY: bg-start
.PHONY: bg-start-local
.PHONY: bg-stop
.PHONY: bg-status
.PHONY: bg-logs

test-all:
	bash scripts/test-all.sh

run-now:
	bash scripts/run-now.sh

run-wsl-discord:
	bash scripts/run-wsl-discord.sh

bg-start:
	bash scripts/presence-daemon.sh start --mode wsl-discord

bg-start-local:
	bash scripts/presence-daemon.sh start --mode local

bg-stop:
	bash scripts/presence-daemon.sh stop

bg-status:
	bash scripts/presence-daemon.sh status

bg-logs:
	bash scripts/presence-daemon.sh logs
