from __future__ import annotations

from typing import Protocol

from zellij_presence.models import RawPresence


class Collector(Protocol):
    def collect(self) -> RawPresence:
        """Collect raw presence data from an upstream source."""
