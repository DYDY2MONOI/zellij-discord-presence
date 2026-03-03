from __future__ import annotations

import os
import time

from zellij_presence.models import Presence, RawPresence

EDITORS = {"vim", "nvim", "vi", "emacs", "nano", "hx", "helix"}
TESTING = {"pytest", "go", "ctest", "cargo", "jest", "vitest", "unittest"}
CODING = {"python", "node", "ruby", "bash", "zsh", "fish", "cargo", "go", "git", "make"}


class PresenceNormalizer:
    def __init__(self) -> None:
        self._session_starts: dict[str, int] = {}

    def normalize(self, raw: RawPresence) -> Presence:
        collected_at = raw.collected_at or int(time.time())
        session_name = raw.session_name or "unknown-session"
        tab_name = raw.tab_name or "unknown-tab"

        if session_name not in self._session_starts:
            self._session_starts[session_name] = collected_at

        return Presence(
            app="zellij",
            session_name=session_name,
            tab_name=tab_name,
            pane_title=raw.pane_title,
            command=raw.command,
            cwd=raw.cwd,
            status=self._derive_status(raw.command, raw.pane_title),
            start_timestamp=self._session_starts[session_name],
        )

    def _derive_status(self, command: str | None, pane_title: str | None) -> str:
        verb = self._leading_executable(command)
        if verb:
            if verb in EDITORS:
                return "editing"
            if verb in TESTING:
                return "testing"
            if verb in CODING:
                return "coding"

        if pane_title:
            lowered = pane_title.lower()
            if "test" in lowered:
                return "testing"
            if any(marker in lowered for marker in ("vim", "nvim", "emacs")):
                return "editing"
        return "active"

    def _leading_executable(self, command: str | None) -> str | None:
        if not command:
            return None
        primary = command.strip().split(maxsplit=1)[0]
        if not primary:
            return None
        return os.path.basename(primary).lower()
