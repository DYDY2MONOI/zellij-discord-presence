from __future__ import annotations

import json
from pathlib import Path

from zellij_presence.models import Presence


class JSONFilePublisher:
    def __init__(self, output_path: str | Path):
        self.output_path = Path(output_path).expanduser()
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def publish(self, presence: Presence) -> None:
        payload = json.dumps(presence.to_dict(), sort_keys=True, ensure_ascii=True)
        temp_path = self.output_path.with_suffix(self.output_path.suffix + ".tmp")
        temp_path.write_text(payload + "\n", encoding="utf-8")
        temp_path.replace(self.output_path)
