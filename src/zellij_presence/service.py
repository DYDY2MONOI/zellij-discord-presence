from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from collections.abc import Callable
from typing import Sequence

from zellij_presence.collectors.base import Collector
from zellij_presence.models import Presence
from zellij_presence.normalizer import PresenceNormalizer
from zellij_presence.publishers.base import Publisher
from zellij_presence.sanitizer import PresenceSanitizer

REPO_ROOT_LOOKUP_TIMEOUT_SECONDS = 1.0
DIFF_TOTALS_LOOKUP_TIMEOUT_SECONDS = 1.5


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
        self._git_baselines: dict[str, tuple[int, int]] = {}
        self._cwd_repo_cache: dict[str, str] = {}
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
        self._apply_session_diff_stats(normalized, sanitized)
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

    def _apply_session_diff_stats(self, normalized: Presence, sanitized: Presence) -> None:
        sanitized.session_lines_added = 0
        sanitized.session_lines_deleted = 0

        if not normalized.cwd:
            return

        repo_root = self._resolve_git_repo_root(normalized.cwd)
        if not repo_root:
            return

        totals = self._read_git_diff_totals(repo_root)
        if totals is None:
            return

        baseline = self._git_baselines.get(repo_root)
        if baseline is None:
            self._git_baselines[repo_root] = totals
            return

        sanitized.session_lines_added = max(0, totals[0] - baseline[0])
        sanitized.session_lines_deleted = max(0, totals[1] - baseline[1])

    def _resolve_git_repo_root(self, cwd: str) -> str | None:
        cached = self._cwd_repo_cache.get(cwd)
        if cached:
            return cached

        try:
            proc = subprocess.run(
                ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                text=True,
                capture_output=True,
                timeout=REPO_ROOT_LOOKUP_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        if proc.returncode != 0:
            return None

        root = (proc.stdout or "").strip()
        if not root:
            return None

        self._cwd_repo_cache[cwd] = root
        return root

    def _read_git_diff_totals(self, repo_root: str) -> tuple[int, int] | None:
        try:
            unstaged = subprocess.run(
                ["git", "-C", repo_root, "diff", "--numstat", "--"],
                text=True,
                capture_output=True,
                timeout=DIFF_TOTALS_LOOKUP_TIMEOUT_SECONDS,
                check=False,
            )
            staged = subprocess.run(
                ["git", "-C", repo_root, "diff", "--numstat", "--cached", "--"],
                text=True,
                capture_output=True,
                timeout=DIFF_TOTALS_LOOKUP_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        if unstaged.returncode != 0 or staged.returncode != 0:
            return None

        add_u, del_u = self._sum_numstat(unstaged.stdout or "")
        add_s, del_s = self._sum_numstat(staged.stdout or "")
        return add_u + add_s, del_u + del_s

    def _sum_numstat(self, content: str) -> tuple[int, int]:
        added = 0
        deleted = 0
        for line in content.splitlines():
            parts = line.split("\t", 2)
            if len(parts) < 2:
                continue
            added += self._parse_numstat_value(parts[0])
            deleted += self._parse_numstat_value(parts[1])
        return added, deleted

    def _parse_numstat_value(self, raw: str) -> int:
        value = raw.strip()
        if value == "-" or value == "":
            return 0
        try:
            return int(value)
        except ValueError:
            return 0
