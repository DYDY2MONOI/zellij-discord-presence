from __future__ import annotations

import os
import re
import shlex
from copy import deepcopy
from pathlib import Path

from zellij_presence.config import PresenceConfig
from zellij_presence.models import Presence


class PresenceSanitizer:
    def __init__(self, config: PresenceConfig) -> None:
        self.config = config
        self._compiled_redact_patterns = self._compile_patterns(config.filters.redact_patterns)
        self._allow_commands = {item.lower() for item in config.filters.allow_commands}
        self._deny_paths = [self._normalize_path(item) for item in config.filters.deny_paths]

    def sanitize(self, presence: Presence) -> Presence:
        sanitized = deepcopy(presence)

        sanitized.session_name = self._redact_text(sanitized.session_name)
        sanitized.tab_name = self._redact_text(sanitized.tab_name)
        sanitized.pane_title = self._redact_text(sanitized.pane_title)
        sanitized.workspace_folder = self._redact_text(sanitized.workspace_folder)

        if self.config.safe_mode:
            sanitized.pane_title = None
            sanitized.command = None
            sanitized.cwd = None
            return sanitized

        sanitized.command = self._sanitize_command(sanitized.command)
        sanitized.cwd = self._sanitize_cwd(sanitized.cwd)
        return sanitized

    def _sanitize_command(self, command: str | None) -> str | None:
        if not command:
            return None
        if self._allow_commands and not self._is_command_allowed(command):
            return None
        return self._redact_text(command)

    def _sanitize_cwd(self, cwd: str | None) -> str | None:
        if not cwd:
            return None
        if self._is_path_denied(cwd):
            return None
        return self._redact_text(cwd)

    def _compile_patterns(self, patterns: list[str]) -> list[re.Pattern[str]]:
        compiled: list[re.Pattern[str]] = []
        for pattern in patterns:
            try:
                compiled.append(re.compile(pattern))
            except re.error:
                continue
        return compiled

    def _redact_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        redacted = value
        for pattern in self._compiled_redact_patterns:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted

    def _is_command_allowed(self, command: str) -> bool:
        executable = self._extract_executable(command)
        if executable is None:
            return False
        return executable in self._allow_commands

    def _extract_executable(self, command: str) -> str | None:
        try:
            tokens = shlex.split(command)
        except ValueError:
            tokens = command.split()
        if not tokens:
            return None
        return os.path.basename(tokens[0]).lower()

    def _normalize_path(self, value: str) -> str:
        return str(Path(value).expanduser().resolve(strict=False))

    def _is_path_denied(self, cwd: str) -> bool:
        normalized_cwd = self._normalize_path(cwd)
        for denied in self._deny_paths:
            if normalized_cwd == denied or normalized_cwd.startswith(f"{denied}{os.sep}"):
                return True
        return False
