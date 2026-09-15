"""The WebSocket client, exercised end to end on a socketpair: no network, real bytes."""

from __future__ import annotations

import base64
import hashlib
import socket
import struct
import threading
import unittest

from ltcm.data import ws


def server_frame(opcode: int, payload: bytes, *, fin: bool = True) -> bytes:
    """A frame the way a server sends it: never masked."""
    return ws.encode_frame(opcode, payload, masked=False, fin=fin)


def parse_client_frame(data: bytes) -> tuple[int, bytes, bytes]:
    """`(opcode, payload, rest)` of one masked client frame, the way a server would read it."""
    first, second = data[0], data[1]
    opcode = first & 0x0F
    assert second & 0x80, "a client frame must be masked"
    length = second & 0x7F
    offset = 2
    if length == 126:
        (length,) = struct.unpack("!H", data[2:4])
        offset = 4
    elif length == 127:
        (length,) = struct.unpack("!Q", data[2:10])
        offset = 10
    mask = data[offset : offset + 4]
    body = data[offset + 4 : offset + 4 + length]
    payload = bytes(b ^ mask[i % 4] for i, b in enumerate(body))
    return opcode, payload, data[offset + 4 + length :]


class AcceptKeyTests(unittest.TestCase):
    def test_the_rfc_6455_example_key_produces_the_rfc_6455_example_accept(self):
        # RFC 6455 §1.3: a wrong GUID passes a self-consistent fake server and fails every
        # real one with "sec-websocket-accept mismatch", which is how this vector earned a test.
        from ltcm.data.ws import accept_key

        self.assertEqual(accept_key(b"dGhlIHNhbXBsZSBub25jZQ=="), "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")


class FakeServer:
    """The server end of a socketpair: answers the handshake, then plays a script."""

    def __init__(self, *, status: int = 101, accept: str | None = None, script: bytes = b"", close_after: bool = False):
        self.client_end, self.server_end = socket.socketpair()
        self.status = status
        self.accept = accept
        self.script = script
        self.close_after = close_after
        self.request: bytes = b""
        self.received: list[tuple[int, bytes]] = []
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def connector(self, host, port, tls, timeout, context=None):
        assert host == "feed.example" and port == 443 and tls
        return self.client_end

    def _serve(self) -> None:
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = self.server_end.recv(4096)
            if not chunk:
                return
            data += chunk
        self.request = data
        key = None
        for line in data.decode().split("\r\n"):
            if line.lower().startswith("sec-websocket-key:"):
                key = line.split(":", 1)[1].strip().encode()
        accept = self.accept
        if accept is None and key is not None:
            accept = base64.b64encode(hashlib.sha1(key + ws.GUID).digest()).decode()
        reply = (
            f"HTTP/1.1 {self.status} {'Switching Protocols' if self.status == 101 else 'Nope'}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
        ).encode()
        self.server_end.sendall(reply + self.script)
        if self.close_after:
            self.server_end.close()
            return
        # Then read whatever the client sends, so pongs and closes are observable.
        buffer = b""
        self.server_end.settimeout(2.0)
        try:
            while True:
                chunk = self.server_end.recv(65536)
                if not chunk:
                    break
                buffer += chunk
                while len(buffer) >= 2:
                    try:
                        opcode, payload, buffer = parse_client_frame(buffer)
                    except (IndexError, struct.error):
                        break
                    self.received.append((opcode, payload))
                    if opcode == ws.OP_CLOSE:
                        self.server_end.sendall(server_frame(ws.OP_CLOSE, payload))
                        return
        except (socket.timeout, OSError):
            pass


class FrameTests(unittest.TestCase):
    def test_client_frames_are_masked_and_server_frames_are_not(self):
        masked = ws.encode_frame(ws.OP_TEXT, b"hello", masked=True)
        self.assertEqual(masked[1] & 0x80, 0x80)
        opcode, payload, rest = parse_client_frame(masked)
        self.assertEqual((opcode, payload, rest), (ws.OP_TEXT, b"hello", b""))
        plain = server_frame(ws.OP_TEXT, b"hello")
        self.assertEqual(plain, b"\x81\x05hello")

    def test_every_length_encoding_round_trips(self):
        for size in (0, 1, 125, 126, 65535, 65536, 70000):
            with self.subTest(size=size):
                payload = bytes(range(256)) * (size // 256 + 1)
                payload = payload[:size]
                frame = ws.encode_frame(ws.OP_BINARY, payload, masked=True)
                opcode, decoded, rest = parse_client_frame(frame)
                self.assertEqual(opcode, ws.OP_BINARY)
                self.assertEqual(decoded, payload)
                self.assertEqual(rest, b"")

    def test_a_control_frame_over_125_bytes_is_refused(self):
        with self.assertRaises(ws.WebSocketError):
            ws.encode_frame(ws.OP_PING, b"x" * 126, masked=True)

    def test_the_accept_key_is_base64_of_sha1_over_key_and_guid(self):
        key = b"dGhlIHNhbXBsZSBub25jZQ=="
        expected = base64.b64encode(hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest()).decode()
        self.assertEqual(ws.accept_key(key), expected)
        self.assertEqual(expected, "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")  # the RFC's own worked example
        self.assertEqual(len(base64.b64decode(ws.accept_key(key))), 20)

    def test_urls_split_into_host_port_path_and_tls(self):
        self.assertEqual(ws.split_url("wss://feed.example/trade-api/ws/v2"), ("feed.example", 443, "/trade-api/ws/v2", True))
        self.assertEqual(ws.split_url("ws://feed.example:8080/x?y=1"), ("feed.example", 8080, "/x?y=1", False))
        with self.assertRaises(ws.WebSocketError):
            ws.split_url("https://feed.example/")

    def test_the_handshake_carries_the_extra_headers_and_refuses_line_breaks(self):
        request = ws.handshake_request("feed.example", 443, "/ws", b"a2V5", {"KALSHI-ACCESS-KEY": "k1"})
        self.assertIn(b"GET /ws HTTP/1.1\r\n", request)
        self.assertIn(b"Host: feed.example\r\n", request)
        self.assertIn(b"KALSHI-ACCESS-KEY: k1\r\n", request)
        self.assertIn(b"Sec-WebSocket-Version: 13\r\n", request)
        with self.assertRaises(ws.WebSocketError):
            ws.handshake_request("feed.example", 443, "/ws", b"a2V5", {"X": "a\r\nInjected: yes"})

    def test_backoff_grows_and_is_capped(self):
        self.assertLessEqual(ws.backoff_seconds(0, jitter=0), 1.0)
        self.assertEqual(ws.backoff_seconds(3, jitter=0), 8.0)
        self.assertEqual(ws.backoff_seconds(20, jitter=0), 60.0)
        self.assertGreaterEqual(ws.backoff_seconds(2), 0.0)


class ConnectionTests(unittest.TestCase):
    def open(self, **kw) -> tuple[FakeServer, ws.WebSocket]:
        server = FakeServer(**kw)
        sock = ws.connect("wss://feed.example/trade-api/ws/v2", {"X-Auth": "1"}, timeout=2.0, connector=server.connector)
        return server, sock

    def test_a_handshake_is_verified_and_the_extra_headers_are_sent(self):
        server, sock = self.open()
        self.assertIn(b"X-Auth: 1\r\n", server.request)
        sock.close()
        server.thread.join(timeout=2)

    def test_a_wrong_accept_key_or_status_is_refused(self):
        with self.assertRaises(ws.HandshakeError):
            self.open(accept="bogus=")
        with self.assertRaises(ws.HandshakeError):
            self.open(status=403)

    def test_messages_arrive_in_order_and_frames_behind_the_handshake_are_not_lost(self):
        script = server_frame(ws.OP_TEXT, b'{"a":1}') + server_frame(ws.OP_TEXT, b'{"b":2}')
        server, sock = self.open(script=script)
        self.assertEqual(sock.recv(timeout=2).text, '{"a":1}')
        self.assertEqual(sock.recv(timeout=2).text, '{"b":2}')
        sock.close()

    def test_a_ping_is_answered_with_a_pong_carrying_the_same_body(self):
        script = server_frame(ws.OP_PING, b"heartbeat") + server_frame(ws.OP_TEXT, b"after")
        server, sock = self.open(script=script)
        self.assertEqual(sock.recv(timeout=2).text, "after")
        self.assertEqual(sock.pings_answered, 1)
        sock.close()
        server.thread.join(timeout=2)
        self.assertIn((ws.OP_PONG, b"heartbeat"), server.received)

    def test_a_fragmented_message_is_reassembled(self):
        script = (
            server_frame(ws.OP_TEXT, b"hel", fin=False)
            + server_frame(ws.OP_PING, b"")  # a control frame may interleave
            + server_frame(ws.OP_CONTINUATION, b"lo ", fin=False)
            + server_frame(ws.OP_CONTINUATION, b"world", fin=True)
        )
        server, sock = self.open(script=script)
        self.assertEqual(sock.recv(timeout=2).text, "hello world")
        sock.close()

    def test_a_close_frame_is_answered_and_reported(self):
        script = server_frame(ws.OP_CLOSE, struct.pack("!H", 1001) + b"going away")
        server, sock = self.open(script=script)
        with self.assertRaises(ws.Closed) as caught:
            sock.recv(timeout=2)
        self.assertEqual((caught.exception.code, caught.exception.reason), (1001, "going away"))
        self.assertTrue(sock.closed)
        server.thread.join(timeout=2)
        self.assertEqual(server.received[0][0], ws.OP_CLOSE)

    def test_a_dropped_connection_is_a_close_not_a_hang(self):
        server, sock = self.open(script=b"", close_after=True)
        with self.assertRaises(ws.Closed):
            sock.recv(timeout=2)

    def test_silence_times_out_instead_of_blocking(self):
        server, sock = self.open()
        with self.assertRaises(TimeoutError):
            sock.recv(timeout=0.2)
        sock.close()

    def test_messages_generator_stops_on_idle_timeout_and_on_close(self):
        script = server_frame(ws.OP_TEXT, b"one")
        server, sock = self.open(script=script)
        seen = []
        with self.assertRaises(TimeoutError):
            for message in sock.messages(idle_timeout=0.2):
                seen.append(message.text)
        self.assertEqual(seen, ["one"])
        sock.close()

    def test_an_oversized_frame_is_refused(self):
        script = server_frame(ws.OP_BINARY, b"x" * 300)
        server = FakeServer(script=script)
        sock = ws.connect(
            "wss://feed.example/ws", timeout=2.0, connector=server.connector, max_message_bytes=200
        )
        with self.assertRaises(ws.WebSocketError):
            sock.recv(timeout=2)

    def test_reserved_bits_are_a_protocol_error(self):
        server, sock = self.open(script=b"\xc1\x01a")  # RSV1 set: a compressed frame we never negotiated
        with self.assertRaises(ws.WebSocketError):
            sock.recv(timeout=2)

    def test_sends_are_masked_text_frames(self):
        server, sock = self.open()
        sock.send('{"cmd":"subscribe"}')
        sock.close()
        server.thread.join(timeout=2)
        self.assertEqual(server.received[0], (ws.OP_TEXT, b'{"cmd":"subscribe"}'))


if __name__ == "__main__":
    unittest.main()
