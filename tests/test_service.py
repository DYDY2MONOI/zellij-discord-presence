from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

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
        self.assertEqual(first.workspace_folder, "project")

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

    def test_session_diff_stats_track_net_since_service_start(self) -> None:
        collector = _MutableCollector(
            RawPresence(
                session_name="dev",
                tab_name="editor",
                pane_title="main.py",
                command="python main.py",
                cwd="/tmp/project",
                collected_at=1234,
                source="zellij-cli",
            )
        )
        service = PresenceService(
            collector=collector,
            normalizer=PresenceNormalizer(),
            sanitizer=PresenceSanitizer(PresenceConfig(safe_mode=False)),
            publishers=[],
        )

        totals = iter([(10, 3), (15, 8), (12, 4)])
        service._resolve_git_repo_root = lambda _cwd: "/repo"  # type: ignore[method-assign]
        service._read_git_diff_totals = lambda _repo: next(totals)  # type: ignore[method-assign]

        first = service.collect_once()
        self.assertEqual(first.session_lines_added, 0)
        self.assertEqual(first.session_lines_deleted, 0)

        second = service.collect_once()
        self.assertEqual(second.session_lines_added, 5)
        self.assertEqual(second.session_lines_deleted, 5)

        third = service.collect_once()
        self.assertEqual(third.session_lines_added, 2)
        self.assertEqual(third.session_lines_deleted, 1)

    def test_session_diff_stats_are_kept_in_safe_mode(self) -> None:
        collector = _MutableCollector(
            RawPresence(
                session_name="dev",
                tab_name="editor",
                pane_title="main.py",
                command="python main.py",
                cwd="/tmp/project",
                collected_at=1234,
                source="zellij-cli",
            )
        )
        service = PresenceService(
            collector=collector,
            normalizer=PresenceNormalizer(),
            sanitizer=PresenceSanitizer(PresenceConfig(safe_mode=True)),
            publishers=[],
        )

        totals = iter([(2, 1), (6, 4)])
        service._resolve_git_repo_root = lambda _cwd: "/repo"  # type: ignore[method-assign]
        service._read_git_diff_totals = lambda _repo: next(totals)  # type: ignore[method-assign]

        first = service.collect_once()
        self.assertEqual(first.session_lines_added, 0)
        self.assertEqual(first.session_lines_deleted, 0)
        self.assertIsNone(first.command)

        second = service.collect_once()
        self.assertEqual(second.session_lines_added, 4)
        self.assertEqual(second.session_lines_deleted, 3)
        self.assertIsNone(second.command)

    def test_repo_lookup_retries_after_transient_failure(self) -> None:
        collector = _MutableCollector(
            RawPresence(
                session_name="dev",
                tab_name="editor",
                pane_title="main.py",
                command="python main.py",
                cwd="/tmp/project",
                collected_at=1234,
                source="zellij-cli",
            )
        )
        service = PresenceService(
            collector=collector,
            normalizer=PresenceNormalizer(),
            sanitizer=PresenceSanitizer(PresenceConfig(safe_mode=False)),
            publishers=[],
        )

        with patch(
            "zellij_presence.service.subprocess.run",
            side_effect=[
                subprocess.TimeoutExpired(cmd="git", timeout=0.1),
                subprocess.CompletedProcess(
                    args=["git", "-C", "/tmp/project", "rev-parse", "--show-toplevel"],
                    returncode=0,
                    stdout="/tmp/project\n",
                    stderr="",
                ),
            ],
        ):
            first = service._resolve_git_repo_root("/tmp/project")
            second = service._resolve_git_repo_root("/tmp/project")

        self.assertIsNone(first)
        self.assertEqual(second, "/tmp/project")


if __name__ == "__main__":
    unittest.main()
