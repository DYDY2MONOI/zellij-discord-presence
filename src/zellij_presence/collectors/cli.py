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
        env_pane_title = os.getenv("ZELLIJ_PANE_TITLE")
        command = None
        env_cwd = os.getenv("PWD") if session_name else None
        pane_title = env_pane_title
        cwd = env_cwd

        if not session_name:
            session_name = self._latest_session_name()

        tab_name = self._query_tab_name()
        layout = self._dump_layout()
        if layout:
            parsed_layout = self._parse_layout(layout)
            session_name = session_name or parsed_layout.session_name
            tab_name = tab_name or parsed_layout.tab_name
            pane_title = parsed_layout.pane_title or env_pane_title
            command = parsed_layout.command
            cwd = parsed_layout.cwd or env_cwd

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
        if len(lines) == 1:
            return self._normalize_tab_name(lines[0])
        return None

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

        active_tab_from_flag: str | None = None
        active_tab_from_focus: str | None = None
        fallback_tab: str | None = None

        active_pane_title: str | None = None
        active_command: str | None = None
        active_cwd: str | None = None
        active_pid: int | None = None

        fallback_pane_title: str | None = None
        fallback_command: str | None = None
        fallback_cwd: str | None = None
        fallback_pid: int | None = None

        brace_depth = 0
        current_tab_name: str | None = None
        current_tab_depth: int | None = None

        for line in layout.splitlines():
            stripped = line.strip()
            if not stripped:
                brace_depth += line.count("{") - line.count("}")
                continue

            tab_name = self._extract_attr(stripped, "name") if "tab" in stripped else None
            if tab_name and stripped.startswith("tab"):
                current_tab_name = tab_name
                current_tab_depth = brace_depth + max(1, line.count("{"))
                if fallback_tab is None:
                    fallback_tab = tab_name
                if "active=true" in stripped or "focus=true" in stripped:
                    active_tab_from_flag = tab_name

            if stripped.startswith("pane"):
                pane_title = self._extract_attr(stripped, "name")
                command = self._extract_attr(stripped, "command")
                cwd = self._extract_attr(stripped, "cwd")
                pid = self._extract_pid(stripped)
                pane_is_active = "active=true" in stripped or "focus=true" in stripped

                if fallback_pane_title is None and pane_title:
                    fallback_pane_title = pane_title
                if fallback_command is None and command:
                    fallback_command = command
                if fallback_cwd is None and cwd:
                    fallback_cwd = cwd
                if fallback_pid is None and pid is not None:
                    fallback_pid = pid

                if pane_is_active:
                    if current_tab_name:
                        active_tab_from_focus = current_tab_name
                    if pane_title:
                        active_pane_title = pane_title
                    if command:
                        active_command = command
                    if cwd:
                        active_cwd = cwd
                    if pid is not None:
                        active_pid = pid

            brace_depth += line.count("{") - line.count("}")
            if current_tab_depth is not None and brace_depth < current_tab_depth:
                current_tab_name = None
                current_tab_depth = None

        parsed.tab_name = active_tab_from_focus or active_tab_from_flag or fallback_tab
        parsed.pane_title = active_pane_title or fallback_pane_title
        parsed.command = active_command or fallback_command
        parsed.cwd = active_cwd or fallback_cwd

        selected_pid = active_pid or fallback_pid
        if selected_pid is not None:
            live_cwd = self._cwd_from_pid(selected_pid)
            if live_cwd:
                parsed.cwd = live_cwd
        return parsed

    def _extract_attr(self, line: str, key: str) -> str | None:
        match = re.search(rf'{re.escape(key)}="([^"]+)"', line)
        if match:
            return match.group(1)
        return None

    def _extract_pid(self, line: str) -> int | None:
        match = re.search(r'\bpid="?(\d+)"?', line)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    def _cwd_from_pid(self, pid: int) -> str | None:
        try:
            return os.readlink(f"/proc/{pid}/cwd")
        except OSError:
            return None
