from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from zellij_presence.collectors.cli import CLICollector
from zellij_presence.collectors.plugin import PluginStateCollector
from zellij_presence.models import RawPresence


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class FixtureCLICollector(CLICollector):
    def __init__(self, fixtures: dict[tuple[str, ...], str]):
        super().__init__(timeout_seconds=0.01)
        self._fixtures = fixtures

    def _run(self, args: list[str]) -> str | None:
        return self._fixtures.get(tuple(args))


class StaticCollector:
    def __init__(self, snapshot: RawPresence):
        self.snapshot = snapshot

    def collect(self) -> RawPresence:
        return self.snapshot


class CollectorIntegrationTests(unittest.TestCase):
    def test_cli_collector_parses_fixture_outputs(self) -> None:
        fixtures = {
            ("list-sessions", "--short", "--no-formatting", "--reverse"): (
                FIXTURES_DIR / "zellij_list_sessions.txt"
            ).read_text(encoding="utf-8"),
            ("action", "query-tab-names"): (
                FIXTURES_DIR / "zellij_query_tab_names.txt"
            ).read_text(encoding="utf-8"),
            ("action", "dump-layout"): (FIXTURES_DIR / "zellij_dump_layout.kdl").read_text(
                encoding="utf-8"
            ),
        }
        collector = FixtureCLICollector(fixtures)

        with patch.dict("os.environ", {"ZELLIJ_SESSION_NAME": "", "ZELLIJ_PANE_TITLE": ""}, clear=False):
            raw = collector.collect()
        self.assertEqual(raw.session_name, "beta-session")
        self.assertEqual(raw.tab_name, "editor")
        self.assertEqual(raw.pane_title, "nvim src/main.py")
        self.assertEqual(raw.command, "nvim src/main.py")
        self.assertEqual(raw.cwd, "/home/alice/project")
        self.assertEqual(raw.source, "zellij-cli")

    def test_plugin_collector_reads_snapshot_fixture(self) -> None:
        fixture_payload = json.loads((FIXTURES_DIR / "plugin_snapshot.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "plugin-state.json"
            state_file.write_text(json.dumps(fixture_payload), encoding="utf-8")
            collector = PluginStateCollector(state_file=state_file, max_age_seconds=60.0)

            raw = collector.collect()
            self.assertEqual(raw.session_name, "plugin-session")
            self.assertEqual(raw.tab_name, "plugin-tab")
            self.assertEqual(raw.command, "nvim src/lib.rs")
            self.assertEqual(raw.source, "zellij-plugin")

    def test_plugin_collector_falls_back_when_snapshot_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "plugin-state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "session_name": "stale-session",
                        "tab_name": "stale-tab",
                        "collected_at": int(time.time()) - 120,
                    }
                ),
                encoding="utf-8",
            )
            fallback = StaticCollector(
                RawPresence(
                    session_name="fallback-session",
                    tab_name="fallback-tab",
                    collected_at=int(time.time()),
                    source="zellij-cli",
                )
            )
            collector = PluginStateCollector(
                state_file=state_file,
                max_age_seconds=1.0,
                fallback_collector=fallback,
            )
            raw = collector.collect()
            self.assertEqual(raw.session_name, "fallback-session")
            self.assertEqual(raw.tab_name, "fallback-tab")
            self.assertEqual(raw.source, "zellij-cli")

    def test_layout_focus_pane_selects_active_tab_without_tab_flag(self) -> None:
        collector = FixtureCLICollector({})
        layout = """
session name="dev-session" {
    tab name="Tab #1" {
        pane name="bash" command="bash" cwd="/tmp/a"
    }
    tab name="Tab #2" {
        pane name="nvim main.py" command="nvim main.py" cwd="/tmp/b" focus=true
    }
}
"""
        parsed = collector._parse_layout(layout)
        self.assertEqual(parsed.tab_name, "Tab #2")
        self.assertEqual(parsed.pane_title, "nvim main.py")
        self.assertEqual(parsed.command, "nvim main.py")
        self.assertEqual(parsed.cwd, "/tmp/b")

    def test_query_tab_names_without_active_hint_returns_none(self) -> None:
        fixtures = {
            ("action", "query-tab-names"): "1: Tab #1\n2: Tab #2\n",
        }
        collector = FixtureCLICollector(fixtures)
        self.assertIsNone(collector._query_tab_name())


if __name__ == "__main__":
    unittest.main()
