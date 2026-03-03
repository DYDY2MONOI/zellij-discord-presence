from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from zellij_presence.models import Presence
from zellij_presence.publishers.discord import DiscordRPCPublisher


class _DummySocket:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


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
            workspace_folder="project",
        )

        payload = publisher._build_set_activity_payload(presence)
        self.assertEqual(payload["cmd"], "SET_ACTIVITY")
        args = payload["args"]
        assert isinstance(args, dict)
        activity = args["activity"]
        assert isinstance(activity, dict)
        self.assertEqual(activity["details"], "dev / editor [project]")
        self.assertIn("editing", activity["state"])
        self.assertIn("+0/-0", activity["state"])
        self.assertEqual(activity["timestamps"]["start"], 12345)

    def test_close_sends_clear_activity_when_socket_open(self) -> None:
        publisher = DiscordRPCPublisher(client_id="1234567890")
        dummy_socket = _DummySocket()
        written: list[tuple[int, dict[str, object]]] = []

        def fake_write_frame(opcode: int, payload: dict[str, object]) -> None:
            written.append((opcode, payload))

        publisher._socket = dummy_socket  # type: ignore[assignment]
        publisher._write_frame = fake_write_frame  # type: ignore[method-assign]

        publisher.close()

        self.assertEqual(len(written), 1)
        self.assertEqual(written[0][0], 1)
        self.assertEqual(written[0][1]["cmd"], "SET_ACTIVITY")
        args = written[0][1]["args"]
        assert isinstance(args, dict)
        self.assertNotIn("activity", args)
        self.assertTrue(dummy_socket.closed)
        self.assertIsNone(publisher._socket)

    def test_close_attempts_reconnect_to_clear_when_socket_missing(self) -> None:
        publisher = DiscordRPCPublisher(client_id="1234567890")
        dummy_socket = _DummySocket()
        written: list[tuple[int, dict[str, object]]] = []

        def fake_connect_and_handshake() -> None:
            publisher._socket = dummy_socket  # type: ignore[assignment]

        def fake_write_frame(opcode: int, payload: dict[str, object]) -> None:
            written.append((opcode, payload))

        publisher._connect_and_handshake = fake_connect_and_handshake  # type: ignore[method-assign]
        publisher._write_frame = fake_write_frame  # type: ignore[method-assign]

        publisher.close()

        self.assertEqual(len(written), 1)
        args = written[0][1]["args"]
        assert isinstance(args, dict)
        self.assertNotIn("activity", args)
        self.assertTrue(dummy_socket.closed)

    def test_publish_retries_with_backoff_after_connection_failures(self) -> None:
        publisher = DiscordRPCPublisher(client_id="1234567890")
        connect_mock = Mock(side_effect=RuntimeError("connect failed"))
        publisher._connect_and_handshake = connect_mock  # type: ignore[method-assign]

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

        with patch("zellij_presence.publishers.discord.time.monotonic", side_effect=[10.0, 10.1, 10.6]):
            publisher.publish(presence)
            publisher.publish(presence)
            publisher.publish(presence)

        self.assertEqual(connect_mock.call_count, 2)
        self.assertAlmostEqual(publisher._next_connect_at, 11.6)

    def test_publish_recovers_after_backoff_window(self) -> None:
        publisher = DiscordRPCPublisher(client_id="1234567890")
        dummy_socket = _DummySocket()
        attempts = {"count": 0}

        def fake_connect_and_handshake() -> None:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("connect failed")
            publisher._socket = dummy_socket  # type: ignore[assignment]

        publisher._connect_and_handshake = fake_connect_and_handshake  # type: ignore[method-assign]

        written: list[tuple[int, dict[str, object]]] = []

        def fake_write_frame(opcode: int, payload: dict[str, object]) -> None:
            written.append((opcode, payload))

        publisher._write_frame = fake_write_frame  # type: ignore[method-assign]

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

        with patch("zellij_presence.publishers.discord.time.monotonic", side_effect=[5.0, 5.2, 5.6]):
            publisher.publish(presence)
            publisher.publish(presence)
            publisher.publish(presence)

        self.assertEqual(attempts["count"], 2)
        self.assertEqual(len(written), 1)
        self.assertEqual(written[0][1]["cmd"], "SET_ACTIVITY")
        self.assertEqual(publisher._next_connect_at, 0.0)


if __name__ == "__main__":
    unittest.main()
