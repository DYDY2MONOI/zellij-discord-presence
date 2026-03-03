from __future__ import annotations

import json
import logging
import threading
import time
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
        logger: logging.Logger | None = None,
    ) -> None:
        self.collector = collector
        self.normalizer = normalizer
        self.sanitizer = sanitizer
        self.publishers = list(publishers)
        self.dry_run = dry_run
        self.logger = logger or logging.getLogger(__name__)
        self._stop_event = threading.Event()
        self._last_payload: str | None = None
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
        self.latest = sanitized
        return sanitized

    def stop(self) -> None:
        self._stop_event.set()
