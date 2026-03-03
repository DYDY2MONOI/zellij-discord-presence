from __future__ import annotations

import unittest

from zellij_presence.models import Presence
from zellij_presence.publishers.discord import DiscordRPCPublisher


class DiscordPublisherTests(unittest.TestCase):
    def test_build_activity_payload_uses_presence_fields(self) -> None:
        publisher = DiscordRPCPublisher(client_id="1234567890")
        presence = Presence(
            app="zellij",
            session_name="dev",
            tab_name="editor",
            pane_title="nvim src/main.py",
            command="nvim src/main.py",
            cwd="/tmp/project",
            status="editing",
            start_timestamp=12345,
        )

        payload = publisher._build_set_activity_payload(presence)
        self.assertEqual(payload["cmd"], "SET_ACTIVITY")
        args = payload["args"]
        assert isinstance(args, dict)
        activity = args["activity"]
        assert isinstance(activity, dict)
        self.assertEqual(activity["details"], "dev / editor")
        self.assertIn("editing", activity["state"])
        self.assertEqual(activity["timestamps"]["start"], 12345)


if __name__ == "__main__":
    unittest.main()
