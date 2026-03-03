from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Sequence

from zellij_presence.collectors.base import Collector
from zellij_presence.models import Presence
from zellij_presence.normalizer import PresenceNormalizer
from zellij_presence.publishers.base import Publisher
from zellij_presence.sanitizer import PresenceSanitizer


class PresenceService:
    def __init__(
        self,
        collector: Collector,
        normalizer: PresenceNormalizer,
        sanitizer: PresenceSanitizer,
        publishers: Sequence[Publisher],
        dry_run: bool = False,
        idle_timeout_seconds: float = 0.0,
        clock: Callable[[], float] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.collector = collector
        self.normalizer = normalizer
        self.sanitizer = sanitizer
        self.publishers = list(publishers)
        self.dry_run = dry_run
        self.idle_timeout_seconds = max(0.0, idle_timeout_seconds)
        self._clock = clock or time.monotonic
        self.logger = logger or logging.getLogger(__name__)
        self._stop_event = threading.Event()
        self._last_payload: str | None = None
        self._last_activity_key: tuple[str, str, str | None, str | None, str | None] | None = None
        self._last_activity_at: float | None = None
        self.latest: Presence | None = None

    def run_forever(self, poll_interval_seconds: float) -> None:
        while not self._stop_event.is_set():
            started_at = time.monotonic()
            try:
                snapshot = self.collect_once()
                payload = json.dumps(snapshot.to_dict(), sort_keys=True, ensure_ascii=True)
                if payload != self._last_payload:
                    self._last_payload = payload
                    if self.dry_run:
                        print(payload, flush=True)
                    for publisher in self.publishers:
                        publisher.publish(snapshot)
            except Exception:
                self.logger.exception("Presence update failed; continuing loop.")

            elapsed = time.monotonic() - started_at
            sleep_for = max(0.05, poll_interval_seconds - elapsed)
            self._stop_event.wait(timeout=sleep_for)

    def collect_once(self) -> Presence:
        raw = self.collector.collect()
        normalized = self.normalizer.normalize(raw)
        sanitized = self.sanitizer.sanitize(normalized)
        self._apply_idle_state(normalized, sanitized)
        self.latest = sanitized
        return sanitized

    def stop(self) -> None:
        self._stop_event.set()

    def _apply_idle_state(self, normalized: Presence, sanitized: Presence) -> None:
        if self.idle_timeout_seconds < 0.1:
            return

        activity_key = (
            normalized.session_name,
            normalized.tab_name,
            normalized.pane_title,
            normalized.command,
            normalized.cwd,
        )
        now = self._clock()

        if self._last_activity_key != activity_key:
            self._last_activity_key = activity_key
            self._last_activity_at = now
            return

        if self._last_activity_at is None:
            self._last_activity_at = now
            return

        if (now - self._last_activity_at) >= self.idle_timeout_seconds:
            sanitized.status = "idle"
            sanitized.command = None
