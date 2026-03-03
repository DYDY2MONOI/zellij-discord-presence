from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import tomllib

from zellij_presence.config import init_config


class ConfigTests(unittest.TestCase):
    def test_init_config_writes_valid_toml(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.toml"
            init_config(path, force=True)
            raw = path.read_text(encoding="utf-8")
            parsed = tomllib.loads(raw)
            self.assertTrue(parsed["safe_mode"])
            self.assertIn("collector", parsed)
            self.assertIn("publish", parsed)
            self.assertIn("filters", parsed)


if __name__ == "__main__":
    unittest.main()
