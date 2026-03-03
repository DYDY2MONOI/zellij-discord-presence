from __future__ import annotations

import unittest

from zellij_presence.config import PresenceConfig
from zellij_presence.models import RawPresence
from zellij_presence.normalizer import PresenceNormalizer
from zellij_presence.sanitizer import PresenceSanitizer
from zellij_presence.service import PresenceService


class _MutableCollector:
    def __init__(self, snapshot: RawPresence) -> None:
        self.snapshot = snapshot

    def collect(self) -> RawPresence:
        return self.snapshot


class _FakeClock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class PresenceServiceTests(unittest.TestCase):
    def test_collect_once_marks_idle_after_timeout(self) -> None:
        collector = _MutableCollector(
            RawPresence(
                session_name="dev",
                tab_name="editor",
                pane_title="app.py",
                command="python app.py",
                cwd="/tmp/project",
                collected_at=1234,
                source="zellij-cli",
            )
        )
        clock = _FakeClock(100.0)
        service = PresenceService(
            collector=collector,
            normalizer=PresenceNormalizer(),
            sanitizer=PresenceSanitizer(PresenceConfig(safe_mode=False)),
            publishers=[],
            idle_timeout_seconds=5.0,
            clock=clock,
        )

        first = service.collect_once()
        self.assertEqual(first.status, "coding")
        self.assertEqual(first.command, "python app.py")

        clock.advance(4.0)
        second = service.collect_once()
        self.assertEqual(second.status, "coding")

        clock.advance(2.0)
        third = service.collect_once()
        self.assertEqual(third.status, "idle")
        self.assertIsNone(third.command)

    def test_activity_change_resets_idle_state(self) -> None:
        collector = _MutableCollector(
            RawPresence(
                session_name="dev",
                tab_name="editor",
                pane_title="app.py",
                command="python app.py",
                cwd="/tmp/project",
                collected_at=1234,
                source="zellij-cli",
            )
        )
        clock = _FakeClock(100.0)
        service = PresenceService(
            collector=collector,
            normalizer=PresenceNormalizer(),
            sanitizer=PresenceSanitizer(PresenceConfig(safe_mode=False)),
            publishers=[],
            idle_timeout_seconds=5.0,
            clock=clock,
        )

        service.collect_once()
        clock.advance(6.0)
        idle = service.collect_once()
        self.assertEqual(idle.status, "idle")

        collector.snapshot = RawPresence(
            session_name="dev",
            tab_name="build",
            pane_title="Makefile",
            command="make test",
            cwd="/tmp/project",
            collected_at=1235,
            source="zellij-cli",
        )
        clock.advance(0.1)
        active = service.collect_once()
        self.assertNotEqual(active.status, "idle")
        self.assertEqual(active.command, "make test")


if __name__ == "__main__":
    unittest.main()
