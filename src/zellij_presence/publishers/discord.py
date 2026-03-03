from __future__ import annotations

import json
import logging
import os
import socket
import struct
import time
import uuid
from pathlib import Path

from zellij_presence.models import Presence

OPCODE_HANDSHAKE = 0
OPCODE_FRAME = 1
RECONNECT_BACKOFF_MIN_SECONDS = 0.5
RECONNECT_BACKOFF_MAX_SECONDS = 8.0


class DiscordRPCPublisher:
    def __init__(
        self,
        client_id: str,
        socket_path: str | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.client_id = client_id.strip()
        self.socket_path = socket_path.strip() if socket_path else None
        self.logger = logger or logging.getLogger(__name__)
        self._socket: socket.socket | None = None
        self._next_connect_at = 0.0
        self._reconnect_backoff_seconds = RECONNECT_BACKOFF_MIN_SECONDS

    def publish(self, presence: Presence) -> None:
        if not self.client_id:
            return
        now = time.monotonic()
        try:
            if self._socket is None:
                if now < self._next_connect_at:
                    return
                self._connect_and_handshake()
                self._on_connected()
            payload = self._build_set_activity_payload(presence)
            self._write_frame(OPCODE_FRAME, payload)
        except Exception:
            self.logger.debug("Discord RPC publish failed; will retry with backoff.", exc_info=True)
            self.close(clear_activity=False)
            self._schedule_reconnect(now)

    def close(self, clear_activity: bool = True) -> None:
        if clear_activity and self._socket is None and self.client_id:
            # Best-effort reconnect so we can clear a previously published activity.
            try:
                self._connect_and_handshake()
            except Exception:
                self.logger.debug("Discord RPC reconnect for clear failed during close.", exc_info=True)

        if self._socket:
            if clear_activity:
                try:
                    self._write_frame(OPCODE_FRAME, self._build_clear_activity_payload())
                except Exception:
                    self.logger.debug("Discord RPC clear activity failed during close.", exc_info=True)
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def _connect_and_handshake(self) -> None:
        path = self._resolve_socket_path()
        if path is None:
            raise FileNotFoundError("Discord IPC socket not found")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(0.4)
        sock.connect(path)
        self._socket = sock
        self._write_frame(
            OPCODE_HANDSHAKE,
            {
                "v": 1,
                "client_id": self.client_id,
            },
        )

    def _on_connected(self) -> None:
        self._next_connect_at = 0.0
        self._reconnect_backoff_seconds = RECONNECT_BACKOFF_MIN_SECONDS

    def _schedule_reconnect(self, now: float) -> None:
        self._next_connect_at = now + self._reconnect_backoff_seconds
        self._reconnect_backoff_seconds = min(
            RECONNECT_BACKOFF_MAX_SECONDS,
            self._reconnect_backoff_seconds * 2,
        )

    def _resolve_socket_path(self) -> str | None:
        if self.socket_path:
            return self.socket_path

        candidates: list[Path] = []
        runtime_dir = os.getenv("XDG_RUNTIME_DIR")
        if runtime_dir:
            for index in range(10):
                candidates.append(Path(runtime_dir) / f"discord-ipc-{index}")

        uid = os.getuid() if hasattr(os, "getuid") else None
        if uid is not None:
            for index in range(10):
                candidates.append(Path(f"/run/user/{uid}") / f"discord-ipc-{index}")

        for index in range(10):
            candidates.append(Path("/tmp") / f"discord-ipc-{index}")

        for path in candidates:
            if path.exists():
                return str(path)
        return None

    def _write_frame(self, opcode: int, payload: dict[str, object]) -> None:
        if self._socket is None:
            raise RuntimeError("Discord IPC socket is not connected")
        encoded = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        header = struct.pack("<II", opcode, len(encoded))
        self._socket.sendall(header + encoded)

    def _build_set_activity_payload(self, presence: Presence) -> dict[str, object]:
        details = f"{presence.session_name} / {presence.tab_name}"
        state = presence.status
        if presence.command:
            state = f"{presence.status}: {presence.command[:60]}"

        activity: dict[str, object] = {
            "details": details[:128],
            "state": state[:128],
            "timestamps": {"start": int(presence.start_timestamp)},
        }
        if presence.pane_title:
            activity["assets"] = {
                "large_text": presence.pane_title[:128],
            }

        return {
            "cmd": "SET_ACTIVITY",
            "args": {
                "pid": os.getpid(),
                "activity": activity,
            },
            "nonce": str(uuid.uuid4()),
            "ts": int(time.time()),
        }

    def _build_clear_activity_payload(self) -> dict[str, object]:
        return {
            "cmd": "SET_ACTIVITY",
            "args": {
                "pid": os.getpid(),
            },
            "nonce": str(uuid.uuid4()),
            "ts": int(time.time()),
        }
