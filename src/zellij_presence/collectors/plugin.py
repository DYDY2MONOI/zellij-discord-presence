from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from zellij_presence.collectors.base import Collector
from zellij_presence.models import RawPresence


class PluginStateCollector:
    """
    Collector that reads snapshots emitted by a Zellij plugin bridge.

    The plugin writes structured JSON to a state file. This collector consumes
    that snapshot and optionally falls back to another collector.
    """

    def __init__(
        self,
        state_file: str | Path,
        max_age_seconds: float = 2.0,
        fallback_collector: Collector | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.state_file = Path(state_file).expanduser()
        self.max_age_seconds = max(0.1, float(max_age_seconds))
        self.fallback_collector = fallback_collector
        self.logger = logger or logging.getLogger(__name__)

    def collect(self) -> RawPresence:
        snapshot = self._read_snapshot()
        if snapshot is not None:
            return snapshot
        if self.fallback_collector is not None:
            return self.fallback_collector.collect()
        return RawPresence(collected_at=int(time.time()), source="zellij-plugin")

    def _read_snapshot(self) -> RawPresence | None:
        if not self.state_file.exists():
            return None
        try:
            payload = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.logger.debug("Failed to read plugin state file: %s", self.state_file, exc_info=True)
            return None

        if not isinstance(payload, dict):
            return None

        collected_at = payload.get("collected_at", payload.get("timestamp", int(time.time())))
        try:
            collected_at_int = int(collected_at)
        except (TypeError, ValueError):
            collected_at_int = int(time.time())

        age = time.time() - collected_at_int
        if age > self.max_age_seconds:
            return None

        return RawPresence(
            session_name=self._as_text(payload.get("session_name")),
            tab_name=self._as_text(payload.get("tab_name")),
            pane_title=self._as_text(payload.get("pane_title")),
            command=self._as_text(payload.get("command")),
            cwd=self._as_text(payload.get("cwd")),
            collected_at=collected_at_int,
            source="zellij-plugin",
        )

    def _as_text(self, value: object) -> str | None:
        if value is None:
            return None
        rendered = str(value).strip()
        return rendered or None
