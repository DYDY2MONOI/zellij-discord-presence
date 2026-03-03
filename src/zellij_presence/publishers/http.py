from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from zellij_presence.models import Presence


class _PresenceStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._payload: dict[str, Any] = {}

    def set(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._payload = payload

    def get(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._payload)


class HTTPPresencePublisher:
    def __init__(self, host: str = "127.0.0.1", port: int = 4765):
        self.host = host
        self.port = port
        self._store = _PresenceStore()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server:
            return

        store = self._store

        class PresenceHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/presence":
                    self.send_response(HTTPStatus.NOT_FOUND)
                    self.end_headers()
                    return
                payload = json.dumps(store.get(), ensure_ascii=True).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self._server = ThreadingHTTPServer((self.host, self.port), PresenceHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def publish(self, presence: Presence) -> None:
        if not self._server:
            self.start()
        self._store.set(presence.to_dict())

    def close(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
