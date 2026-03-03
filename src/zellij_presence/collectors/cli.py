from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass

from zellij_presence.models import RawPresence

ANSI_ESCAPE_RE = re.compile(r"\x1B[@-_][0-?]*[ -/]*[@-~]")
ACTIVE_HINT_RE = re.compile(r"(^\*|\(active\)|\[active\]|active=true|focus=true)", re.IGNORECASE)


def _strip_ansi(value: str) -> str:
    return ANSI_ESCAPE_RE.sub("", value)


@dataclass(slots=True)
class ParsedLayout:
    session_name: str | None = None
    tab_name: str | None = None
    pane_title: str | None = None
    command: str | None = None
    cwd: str | None = None


class CLICollector:
    """
    Best-effort CLI collector.

    Zellij's CLI can only query active tab/pane details when running from inside
    an active session. This collector handles partial data and degrades safely.
    """

    def __init__(self, timeout_seconds: float = 0.8):
        self.timeout_seconds = timeout_seconds

    def collect(self) -> RawPresence:
        now = int(time.time())
        session_name = os.getenv("ZELLIJ_SESSION_NAME")
        tab_name = None
        pane_title = os.getenv("ZELLIJ_PANE_TITLE")
        command = None
        cwd = os.getenv("PWD") if session_name else None

        if not session_name:
            session_name = self._latest_session_name()

        tab_name = self._query_tab_name()
        layout = self._dump_layout()
        if layout:
            parsed_layout = self._parse_layout(layout)
            session_name = session_name or parsed_layout.session_name
            tab_name = tab_name or parsed_layout.tab_name
            pane_title = pane_title or parsed_layout.pane_title
            command = parsed_layout.command
            cwd = cwd or parsed_layout.cwd

        return RawPresence(
            session_name=session_name,
            tab_name=tab_name,
            pane_title=pane_title,
            command=command,
            cwd=cwd,
            collected_at=now,
            source="zellij-cli",
        )

    def _run(self, args: list[str]) -> str | None:
        proc = subprocess.run(
            ["zellij", *args],
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        output = _strip_ansi((proc.stdout or "").strip())
        if not output:
            output = _strip_ansi((proc.stderr or "").strip())
        if "There is no active session!" in output:
            return None
        return output or None

    def _latest_session_name(self) -> str | None:
        output = self._run(["list-sessions", "--short", "--no-formatting", "--reverse"])
        if not output:
            return None
        for line in output.splitlines():
            candidate = line.strip()
            if candidate:
                return candidate
        return None

    def _query_tab_name(self) -> str | None:
        output = self._run(["action", "query-tab-names"])
        if not output:
            return None

        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if not lines:
            return None

        for line in lines:
            if ACTIVE_HINT_RE.search(line):
                return self._normalize_tab_name(line)
        return self._normalize_tab_name(lines[0])

    def _dump_layout(self) -> str | None:
        return self._run(["action", "dump-layout"])

    def _normalize_tab_name(self, value: str) -> str:
        cleaned = value
        cleaned = cleaned.replace("*", "").replace("[active]", "")
        cleaned = re.sub(r"\(active\)", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^\d+\s*[:\-]\s*", "", cleaned)
        return cleaned.strip() or value.strip()

    def _parse_layout(self, layout: str) -> ParsedLayout:
        parsed = ParsedLayout()

        session_match = re.search(r'session\s+name="([^"]+)"', layout)
        if session_match:
            parsed.session_name = session_match.group(1)

        active_tab_match = re.search(
            r'tab\b[^\n]*name="([^"]+)"[^\n]*(?:active=true|focus=true)', layout
        )
        fallback_tab_match = re.search(r'tab\b[^\n]*name="([^"]+)"', layout)
        if active_tab_match:
            parsed.tab_name = active_tab_match.group(1)
        elif fallback_tab_match:
            parsed.tab_name = fallback_tab_match.group(1)

        active_pane_match = re.search(
            r'pane\b[^\n]*name="([^"]+)"[^\n]*(?:active=true|focus=true)', layout
        )
        fallback_pane_match = re.search(r'pane\b[^\n]*name="([^"]+)"', layout)
        if active_pane_match:
            parsed.pane_title = active_pane_match.group(1)
        elif fallback_pane_match:
            parsed.pane_title = fallback_pane_match.group(1)

        active_command_match = re.search(
            r'pane\b[^\n]*command="([^"]+)"[^\n]*(?:active=true|focus=true)', layout
        )
        fallback_command_match = re.search(r'pane\b[^\n]*command="([^"]+)"', layout)
        if active_command_match:
            parsed.command = active_command_match.group(1)
        elif fallback_command_match:
            parsed.command = fallback_command_match.group(1)

        active_cwd_match = re.search(
            r'pane\b[^\n]*cwd="([^"]+)"[^\n]*(?:active=true|focus=true)', layout
        )
        fallback_cwd_match = re.search(r'pane\b[^\n]*cwd="([^"]+)"', layout)
        if active_cwd_match:
            parsed.cwd = active_cwd_match.group(1)
        elif fallback_cwd_match:
            parsed.cwd = fallback_cwd_match.group(1)

        return parsed
