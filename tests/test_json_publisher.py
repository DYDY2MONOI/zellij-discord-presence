from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from zellij_presence.models import Presence
from zellij_presence.publishers.file import JSONFilePublisher


class JSONFilePublisherTests(unittest.TestCase):
    def test_publish_writes_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "presence.json"
            publisher = JSONFilePublisher(output_path)

            presence = Presence(
                app="zellij",
                session_name="dev",
                tab_name="editor",
                pane_title=None,
                command=None,
                cwd=None,
                status="editing",
                start_timestamp=1234,
            )
            publisher.publish(presence)

            raw = output_path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            self.assertEqual(parsed["app"], "zellij")
            self.assertEqual(parsed["session_name"], "dev")
            self.assertEqual(parsed["tab_name"], "editor")
            self.assertEqual(parsed["status"], "editing")
            self.assertEqual(parsed["start_timestamp"], 1234)


if __name__ == "__main__":
    unittest.main()
