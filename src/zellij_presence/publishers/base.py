from __future__ import annotations

from typing import Protocol

from zellij_presence.models import Presence


class Publisher(Protocol):
    def publish(self, presence: Presence) -> None:
        """Publish a sanitized presence snapshot."""
