from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class RawPresence:
    session_name: str | None = None
    tab_name: str | None = None
    pane_title: str | None = None
    command: str | None = None
    cwd: str | None = None
    collected_at: int = 0
    source: str = "unknown"


@dataclass(slots=True)
class Presence:
    app: str
    session_name: str
    tab_name: str
    pane_title: str | None
    command: str | None
    cwd: str | None
    status: str
    start_timestamp: int
    workspace_folder: str | None = None
    session_lines_added: int = 0
    session_lines_deleted: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {key: value for key, value in data.items() if value is not None}
