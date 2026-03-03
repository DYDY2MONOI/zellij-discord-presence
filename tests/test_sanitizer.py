from __future__ import annotations

import unittest

from zellij_presence.config import FilterConfig, PresenceConfig, PublishConfig
from zellij_presence.models import Presence
from zellij_presence.sanitizer import PresenceSanitizer


class PresenceSanitizerTests(unittest.TestCase):
    def test_safe_mode_hides_command_and_cwd(self) -> None:
        config = PresenceConfig(safe_mode=True)
        sanitizer = PresenceSanitizer(config)
        input_presence = Presence(
            app="zellij",
            session_name="dev",
            tab_name="backend",
            pane_title="nvim main.py",
            command="python app.py token=abc123",
            cwd="/tmp/project",
            status="coding",
            start_timestamp=1234,
        )

        output = sanitizer.sanitize(input_presence)
        self.assertIsNone(output.command)
        self.assertIsNone(output.cwd)
        self.assertIsNone(output.pane_title)

    def test_command_allowlist_blocks_unsafe_command(self) -> None:
        config = PresenceConfig(
            safe_mode=False,
            publish=PublishConfig(),
            filters=FilterConfig(
                allow_commands=["nvim"],
                deny_paths=[],
                redact_patterns=[r"(?i)token=\S+"],
            ),
        )
        sanitizer = PresenceSanitizer(config)
        input_presence = Presence(
            app="zellij",
            session_name="dev",
            tab_name="shell",
            pane_title="shell",
            command="bash -lc 'echo hello'",
            cwd="/tmp/project",
            status="active",
            start_timestamp=1234,
        )

        output = sanitizer.sanitize(input_presence)
        self.assertIsNone(output.command)

    def test_redacts_secret_patterns_when_command_allowed(self) -> None:
        config = PresenceConfig(
            safe_mode=False,
            publish=PublishConfig(),
            filters=FilterConfig(
                allow_commands=["python"],
                deny_paths=[],
                redact_patterns=[r"(?i)token=\S+", r"(?i)password=\S+"],
            ),
        )
        sanitizer = PresenceSanitizer(config)
        input_presence = Presence(
            app="zellij",
            session_name="dev",
            tab_name="api",
            pane_title="server",
            command="python script.py token=abc password=def",
            cwd="/tmp/project",
            status="coding",
            start_timestamp=1234,
        )

        output = sanitizer.sanitize(input_presence)
        assert output.command is not None
        self.assertNotIn("abc", output.command)
        self.assertNotIn("def", output.command)
        self.assertIn("[REDACTED]", output.command)

    def test_denylist_hides_sensitive_path(self) -> None:
        config = PresenceConfig(
            safe_mode=False,
            publish=PublishConfig(),
            filters=FilterConfig(
                allow_commands=[],
                deny_paths=["/tmp/project/secret"],
                redact_patterns=[],
            ),
        )
        sanitizer = PresenceSanitizer(config)
        input_presence = Presence(
            app="zellij",
            session_name="dev",
            tab_name="api",
            pane_title="server",
            command="python app.py",
            cwd="/tmp/project/secret/docs",
            status="coding",
            start_timestamp=1234,
        )

        output = sanitizer.sanitize(input_presence)
        self.assertIsNone(output.cwd)


if __name__ == "__main__":
    unittest.main()
