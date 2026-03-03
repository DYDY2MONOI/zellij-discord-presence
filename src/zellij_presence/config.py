from __future__ import annotations

import os
import platform
import textwrap
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_REDACT_PATTERNS = [
    r"(?i)(token|secret|password|passwd|api[_-]?key)\s*[:=]\s*([^\s]+)",
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
    r"\b(?:ghp|gho|ghu|ghs|glpat|xox[baprs]-|sk_(?:live|test))[A-Za-z0-9_-]{8,}\b",
]

DEFAULT_ALLOW_COMMANDS = ["nvim", "vim", "git", "python", "cargo", "make"]
DEFAULT_DENY_PATHS = ["~/Documents/secret", "~/.ssh", "~/.gnupg"]


def default_presence_file_path() -> Path:
    runtime_dir = os.getenv("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "zellij-presence.json"
    return Path("/tmp/zellij-presence.json")


def default_config_path() -> Path:
    home = Path.home()
    if platform.system() == "Darwin":
        return home / "Library" / "Application Support" / "zellij-presence" / "config.toml"
    return home / ".config" / "zellij-presence" / "config.toml"


@dataclass(slots=True)
class PublishConfig:
    file_path: str = field(default_factory=lambda: str(default_presence_file_path()))
    http_enabled: bool = False
    http_host: str = "127.0.0.1"
    http_port: int = 4765
    discord_enabled: bool = False
    discord_client_id: str = ""
    discord_socket_path: str = ""


@dataclass(slots=True)
class FilterConfig:
    allow_commands: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOW_COMMANDS))
    deny_paths: list[str] = field(default_factory=lambda: list(DEFAULT_DENY_PATHS))
    redact_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_REDACT_PATTERNS))


@dataclass(slots=True)
class CollectorConfig:
    strategy: str = "auto"
    plugin_state_file: str = "/tmp/zellij-presence-plugin-state.json"
    plugin_max_age_seconds: float = 2.0


@dataclass(slots=True)
class PresenceConfig:
    safe_mode: bool = True
    poll_interval_seconds: float = 0.5
    collector: CollectorConfig = field(default_factory=CollectorConfig)
    publish: PublishConfig = field(default_factory=PublishConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)


def _update_from_dict(config: PresenceConfig, data: dict[str, Any]) -> None:
    if "safe_mode" in data:
        config.safe_mode = bool(data["safe_mode"])
    if "poll_interval_seconds" in data:
        try:
            config.poll_interval_seconds = max(0.1, float(data["poll_interval_seconds"]))
        except (TypeError, ValueError):
            pass

    publish = data.get("publish", {})
    if isinstance(publish, dict):
        if "file_path" in publish:
            config.publish.file_path = str(publish["file_path"])
        if "http_enabled" in publish:
            config.publish.http_enabled = bool(publish["http_enabled"])
        if "http_host" in publish:
            config.publish.http_host = str(publish["http_host"])
        if "http_port" in publish:
            try:
                config.publish.http_port = int(publish["http_port"])
            except (TypeError, ValueError):
                pass
        discord = publish.get("discord", {})
        if isinstance(discord, dict):
            if "enabled" in discord:
                config.publish.discord_enabled = bool(discord["enabled"])
            if "client_id" in discord:
                config.publish.discord_client_id = str(discord["client_id"])
            if "socket_path" in discord:
                config.publish.discord_socket_path = str(discord["socket_path"])

    collector = data.get("collector", {})
    if isinstance(collector, dict):
        if "strategy" in collector:
            strategy = str(collector["strategy"]).strip().lower()
            if strategy in {"auto", "plugin", "cli"}:
                config.collector.strategy = strategy
        if "plugin_state_file" in collector:
            config.collector.plugin_state_file = str(collector["plugin_state_file"])
        if "plugin_max_age_seconds" in collector:
            try:
                config.collector.plugin_max_age_seconds = max(
                    0.1, float(collector["plugin_max_age_seconds"])
                )
            except (TypeError, ValueError):
                pass

    filters = data.get("filters", {})
    if isinstance(filters, dict):
        if "allow_commands" in filters and isinstance(filters["allow_commands"], list):
            config.filters.allow_commands = [str(item) for item in filters["allow_commands"]]
        if "deny_paths" in filters and isinstance(filters["deny_paths"], list):
            config.filters.deny_paths = [str(item) for item in filters["deny_paths"]]
        if "redact_patterns" in filters and isinstance(filters["redact_patterns"], list):
            config.filters.redact_patterns = [str(item) for item in filters["redact_patterns"]]


def _update_from_env(config: PresenceConfig) -> None:
    safe_mode = os.getenv("ZELLIJ_PRESENCE_SAFE_MODE")
    if safe_mode is not None:
        config.safe_mode = safe_mode.lower() not in {"0", "false", "no", "off"}

    file_path = os.getenv("ZELLIJ_PRESENCE_FILE_PATH")
    if file_path:
        config.publish.file_path = file_path

    http_enabled = os.getenv("ZELLIJ_PRESENCE_HTTP_ENABLED")
    if http_enabled is not None:
        config.publish.http_enabled = http_enabled.lower() in {"1", "true", "yes", "on"}

    http_port = os.getenv("ZELLIJ_PRESENCE_HTTP_PORT")
    if http_port:
        try:
            config.publish.http_port = int(http_port)
        except ValueError:
            pass
    discord_enabled = os.getenv("ZELLIJ_PRESENCE_DISCORD_ENABLED")
    if discord_enabled is not None:
        config.publish.discord_enabled = discord_enabled.lower() in {"1", "true", "yes", "on"}
    discord_client_id = os.getenv("ZELLIJ_PRESENCE_DISCORD_CLIENT_ID")
    if discord_client_id:
        config.publish.discord_client_id = discord_client_id
    discord_socket_path = os.getenv("ZELLIJ_PRESENCE_DISCORD_SOCKET_PATH")
    if discord_socket_path:
        config.publish.discord_socket_path = discord_socket_path

    interval = os.getenv("ZELLIJ_PRESENCE_POLL_INTERVAL_SECONDS")
    if interval:
        try:
            config.poll_interval_seconds = max(0.1, float(interval))
        except ValueError:
            pass
    collector_strategy = os.getenv("ZELLIJ_PRESENCE_COLLECTOR_STRATEGY")
    if collector_strategy:
        strategy = collector_strategy.strip().lower()
        if strategy in {"auto", "plugin", "cli"}:
            config.collector.strategy = strategy
    plugin_state_file = os.getenv("ZELLIJ_PRESENCE_PLUGIN_STATE_FILE")
    if plugin_state_file:
        config.collector.plugin_state_file = plugin_state_file
    plugin_max_age = os.getenv("ZELLIJ_PRESENCE_PLUGIN_MAX_AGE_SECONDS")
    if plugin_max_age:
        try:
            config.collector.plugin_max_age_seconds = max(0.1, float(plugin_max_age))
        except ValueError:
            pass


def load_config(config_path: str | Path | None = None) -> PresenceConfig:
    config = PresenceConfig()
    path = Path(config_path).expanduser() if config_path else default_config_path()
    if path.exists():
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            _update_from_dict(config, parsed)
    _update_from_env(config)
    return config


def render_default_config() -> str:
    return textwrap.dedent(
        f"""\
        safe_mode = true
        poll_interval_seconds = 0.5

        [collector]
        strategy = "auto"
        plugin_state_file = "/tmp/zellij-presence-plugin-state.json"
        plugin_max_age_seconds = 2.0

        [publish]
        file_path = "{default_presence_file_path()}"
        http_enabled = false
        http_host = "127.0.0.1"
        http_port = 4765

        [publish.discord]
        enabled = false
        client_id = ""
        socket_path = ""

        [filters]
        allow_commands = ["nvim", "vim", "git", "python", "cargo", "make"]
        deny_paths = ["~/Documents/secret", "~/.ssh", "~/.gnupg"]
        redact_patterns = [
          "(?i)(token|secret|password|passwd|api[_-]?key)\\\\s*[:=]\\\\s*([^\\\\s]+)",
          "\\\\beyJ[A-Za-z0-9_-]{{10,}}\\\\.[A-Za-z0-9_-]{{10,}}\\\\.[A-Za-z0-9_-]{{10,}}\\\\b",
          "\\\\b(?:ghp|gho|ghu|ghs|glpat|xox[baprs]-|sk_(?:live|test))[A-Za-z0-9_-]{{8,}}\\\\b",
        ]
        """
    )


def init_config(path: str | Path | None = None, force: bool = False) -> Path:
    config_path = Path(path).expanduser() if path else default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists() and not force:
        raise FileExistsError(f"Config already exists at {config_path}")
    config_path.write_text(render_default_config(), encoding="utf-8")
    return config_path
