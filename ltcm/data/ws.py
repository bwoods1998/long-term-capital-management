"""A standard-library WebSocket client (RFC 6455), the client half only.

Both venues put the things the recursive loop most needs -- instant fills, instant settlement,
live prices -- behind WebSockets, and Python's standard library ships no client for them. This
is the smallest correct one: a TLS socket, the HTTP upgrade handshake with any extra headers a
venue wants (Kalshi authenticates in the handshake), masked frames out, unmasked frames in,
control frames answered (ping, close), fragmentation reassembled, and a read deadline on every
receive so a quiet socket can never hang a thread.

Deliberately not here: `permessage-deflate`, sending fragmented messages, proxies, and the
server side. A socket factory can be injected so the whole protocol is testable on a
`socketpair()`; nothing in this module needs the network to be exercised.
"""

from __future__ import annotations

import base64
import hashlib
import os
import random
import socket
import ssl
import struct
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Mapping

GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"  # RFC 6455 §1.3, verified against its own example

OP_CONTINUATION = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA
CONTROL_OPCODES = (OP_CLOSE, OP_PING, OP_PONG)

#: A single message larger than this is a protocol problem, not a market data problem.
MAX_MESSAGE_BYTES = 4 * 1024 * 1024
MAX_HEADER_BYTES = 16 * 1024


class WebSocketError(RuntimeError):
    """The socket or the protocol failed. The connection is unusable afterwards."""


class HandshakeError(WebSocketError):
    """The server did not agree to upgrade, or agreed with the wrong accept key."""


class Closed(WebSocketError):
    """The peer closed the connection. `code` and `reason` are what it said."""

    def __init__(self, code: int = 1005, reason: str = ""):
        super().__init__(f"websocket closed ({code}) {reason}".rstrip())
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class Message:
    """One complete data message. `text` is None for a binary message."""

    opcode: int
    data: bytes

    @property
    def text(self) -> str | None:
        return self.data.decode("utf-8") if self.opcode == OP_TEXT else None


def backoff_seconds(attempt: int, *, base: float = 1.0, cap: float = 60.0, jitter: float = 0.25) -> float:
    """Exponential backoff with jitter: 1, 2, 4 ... capped, so a reconnect storm never forms."""
    attempt = max(0, int(attempt))
    delay = min(float(cap), float(base) * (2 ** attempt))
    spread = delay * float(jitter)
    return max(0.0, delay + random.uniform(-spread, spread))


def split_url(url: str) -> tuple[str, int, str, bool]:
    """`(host, port, path_with_query, tls)` for a `ws://` or `wss://` URL."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("ws", "wss"):
        raise WebSocketError(f"not a websocket url: {url!r}")
    if not parts.hostname:
        raise WebSocketError(f"websocket url has no host: {url!r}")
    tls = parts.scheme == "wss"
    port = parts.port or (443 if tls else 80)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return parts.hostname, port, path, tls


def handshake_request(host: str, port: int, path: str, key: bytes, headers: Mapping[str, str] | None) -> bytes:
    """The HTTP/1.1 upgrade request, extra headers included (a venue's auth goes here)."""
    authority = host if port in (80, 443) else f"{host}:{port}"
    lines = [
        f"GET {path} HTTP/1.1",
        f"Host: {authority}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {key.decode('ascii')}",
        "Sec-WebSocket-Version: 13",
        "User-Agent: ltcm-floor/1.0",
    ]
    for name, value in (headers or {}).items():
        if "\r" in name or "\n" in name or "\r" in str(value) or "\n" in str(value):
            raise WebSocketError("a header may not contain a line break")
        lines.append(f"{name}: {value}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8")


def accept_key(key: bytes) -> str:
    """What the server must answer for `key`: base64(sha1(key + GUID))."""
    return base64.b64encode(hashlib.sha1(key + GUID).digest()).decode("ascii")


def encode_frame(opcode: int, payload: bytes, *, masked: bool, fin: bool = True) -> bytes:
    """One frame. A client masks every frame it sends; a server never does."""
    if opcode in CONTROL_OPCODES and len(payload) > 125:
        raise WebSocketError("a control frame carries at most 125 bytes")
    head = bytearray([(0x80 if fin else 0x00) | (opcode & 0x0F)])
    length = len(payload)
    mask_bit = 0x80 if masked else 0x00
    if length < 126:
        head.append(mask_bit | length)
    elif length < 65536:
        head.append(mask_bit | 126)
        head += struct.pack("!H", length)
    else:
        head.append(mask_bit | 127)
        head += struct.pack("!Q", length)
    if not masked:
        return bytes(head) + payload
    mask = os.urandom(4)
    return bytes(head) + mask + _apply_mask(payload, mask)


def _apply_mask(payload: bytes, mask: bytes) -> bytes:
    if not payload:
        return b""
    # Extend the mask to the payload length and XOR in one step; fast enough for market data.
    repeated = (mask * (len(payload) // 4 + 1))[: len(payload)]
    return bytes(a ^ b for a, b in zip(payload, repeated))


def default_connector(host: str, port: int, tls: bool, timeout: float, context: Any = None) -> Any:
    """A connected socket, TLS-wrapped for `wss://`, with the server's name verified."""
    raw = socket.create_connection((host, port), timeout=timeout)
    if not tls:
        return raw
    ctx = context or ssl.create_default_context()
    return ctx.wrap_socket(raw, server_hostname=host)


class WebSocket:
    """One open connection. Not thread-safe for sending; one reader thread per socket."""

    def __init__(
        self, sock: Any, *, url: str = "", max_message_bytes: int = MAX_MESSAGE_BYTES, prefetched: bytes = b""
    ):
        self._sock = sock
        self.url = url
        self.max_message_bytes = int(max_message_bytes)
        # Frames the server sent right behind its handshake belong to the stream, not the bin.
        self._buffer = bytearray(prefetched)
        self.closed = False
        self.close_code: int | None = None
        self.close_reason: str = ""
        self.pings_answered = 0
        self.pongs_received = 0
        self.last_received_at = time.monotonic()

    # ------------------------------------------------------------------ sending
    def send(self, text: str) -> None:
        self._write(encode_frame(OP_TEXT, text.encode("utf-8"), masked=True))

    def send_bytes(self, data: bytes) -> None:
        self._write(encode_frame(OP_BINARY, bytes(data), masked=True))

    def ping(self, data: bytes = b"") -> None:
        self._write(encode_frame(OP_PING, bytes(data), masked=True))

    def pong(self, data: bytes = b"") -> None:
        self._write(encode_frame(OP_PONG, bytes(data), masked=True))

    def close(self, code: int = 1000, reason: str = "") -> None:
        """Send a close frame (once) and shut the socket. Never raises."""
        if not self.closed:
            self.closed = True
            try:
                payload = struct.pack("!H", int(code)) + reason.encode("utf-8")[:120]
                self._sock.sendall(encode_frame(OP_CLOSE, payload, masked=True))
            except Exception:
                pass
        try:
            self._sock.close()
        except Exception:
            pass

    def _write(self, data: bytes) -> None:
        if self.closed:
            raise Closed(self.close_code or 1006, self.close_reason or "already closed")
        try:
            self._sock.sendall(data)
        except (OSError, ssl.SSLError) as exc:
            self.closed = True
            raise WebSocketError(f"send failed: {type(exc).__name__}") from exc

    # ---------------------------------------------------------------- receiving
    def _read_exact(self, count: int, timeout: float | None) -> bytes:
        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        while len(self._buffer) < count:
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("websocket read timed out")
                self._sock.settimeout(remaining)
            else:
                self._sock.settimeout(None)
            try:
                chunk = self._sock.recv(65536)
            except (socket.timeout, TimeoutError) as exc:
                raise TimeoutError("websocket read timed out") from exc
            except (OSError, ssl.SSLError) as exc:
                self.closed = True
                raise WebSocketError(f"recv failed: {type(exc).__name__}") from exc
            if not chunk:
                self.closed = True
                raise Closed(1006, "connection lost")
            self._buffer += chunk
        out = bytes(self._buffer[:count])
        del self._buffer[:count]
        return out

    def _read_frame(self, timeout: float | None) -> tuple[bool, int, bytes]:
        """`(fin, opcode, payload)` for the next frame, unmasking if the peer masked it."""
        first, second = self._read_exact(2, timeout)
        fin = bool(first & 0x80)
        if first & 0x70:
            raise WebSocketError("reserved bits set: an extension was negotiated that this client does not speak")
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            (length,) = struct.unpack("!H", self._read_exact(2, timeout))
        elif length == 127:
            (length,) = struct.unpack("!Q", self._read_exact(8, timeout))
        if opcode in CONTROL_OPCODES and (length > 125 or not fin):
            raise WebSocketError("malformed control frame")
        if length > self.max_message_bytes:
            raise WebSocketError(f"frame of {length} bytes exceeds the {self.max_message_bytes} byte limit")
        mask = self._read_exact(4, timeout) if masked else b""
        payload = self._read_exact(length, timeout) if length else b""
        if masked:
            payload = _apply_mask(payload, mask)
        self.last_received_at = time.monotonic()
        return fin, opcode, payload

    def recv(self, timeout: float | None = None) -> Message:
        """The next complete data message. Control frames are handled on the way.

        Raises `TimeoutError` when nothing complete arrived in time, `Closed` when the peer
        closed (after answering its close frame), `WebSocketError` on any protocol failure.
        """
        if self.closed:
            raise Closed(self.close_code or 1006, self.close_reason or "closed")
        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        message_opcode: int | None = None
        parts: list[bytes] = []
        size = 0
        while True:
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                raise TimeoutError("websocket read timed out")
            fin, opcode, payload = self._read_frame(remaining)
            if opcode == OP_PING:
                self.pings_answered += 1
                self.pong(payload)
                continue
            if opcode == OP_PONG:
                self.pongs_received += 1
                continue
            if opcode == OP_CLOSE:
                code, reason = 1005, ""
                if len(payload) >= 2:
                    (code,) = struct.unpack("!H", payload[:2])
                    reason = payload[2:].decode("utf-8", "replace")
                self.close_code, self.close_reason = code, reason
                self.close(code if 1000 <= code < 5000 else 1000)
                raise Closed(code, reason)
            if opcode in (OP_TEXT, OP_BINARY):
                if message_opcode is not None:
                    raise WebSocketError("a new message started inside a fragmented one")
                message_opcode = opcode
            elif opcode == OP_CONTINUATION:
                if message_opcode is None:
                    raise WebSocketError("a continuation frame with nothing to continue")
            else:
                raise WebSocketError(f"unknown opcode {opcode:#x}")
            parts.append(payload)
            size += len(payload)
            if size > self.max_message_bytes:
                raise WebSocketError("message exceeds the size limit")
            if fin:
                data = b"".join(parts)
                if message_opcode == OP_TEXT:
                    try:
                        data.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise WebSocketError("text frame is not UTF-8") from exc
                return Message(message_opcode, data)

    def messages(self, *, idle_timeout: float | None = None, deadline: float | None = None) -> Iterator[Message]:
        """Yield messages until the peer closes, the deadline passes or a read stays idle too long.

        `idle_timeout` is the longest silence tolerated between messages: a feed whose server
        pings every ten seconds and then falls silent is dead, not quiet. `deadline` is a
        `time.monotonic()` value after which the generator returns.
        """
        while True:
            timeout = idle_timeout
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                timeout = remaining if timeout is None else min(timeout, remaining)
            try:
                yield self.recv(timeout)
            except Closed:
                return


def connect(
    url: str,
    headers: Mapping[str, str] | None = None,
    *,
    timeout: float = 30.0,
    context: Any = None,
    connector: Callable[..., Any] | None = None,
    max_message_bytes: int = MAX_MESSAGE_BYTES,
) -> WebSocket:
    """Open a WebSocket to `url`. `connector(host, port, tls, timeout, context)` may be injected."""
    host, port, path, tls = split_url(url)
    key = base64.b64encode(os.urandom(16))
    sock = (connector or default_connector)(host, port, tls, timeout, context)
    try:
        sock.settimeout(timeout)
        sock.sendall(handshake_request(host, port, path, key, headers))
        status, fields, prefetched = _read_handshake(sock)
        if status != 101:
            raise HandshakeError(f"server answered {status}, not 101")
        if fields.get("upgrade", "").lower() != "websocket":
            raise HandshakeError("server did not upgrade to websocket")
        if fields.get("sec-websocket-accept") != accept_key(key):
            raise HandshakeError("sec-websocket-accept mismatch")
    except Exception:
        try:
            sock.close()
        except Exception:
            pass
        raise
    return WebSocket(sock, url=url, max_message_bytes=max_message_bytes, prefetched=prefetched)


def _read_handshake(sock: Any) -> tuple[int, dict[str, str], bytes]:
    """The status line, the headers and any bytes the server sent behind the blank line."""
    data = bytearray()
    while b"\r\n\r\n" not in data:
        if len(data) > MAX_HEADER_BYTES:
            raise HandshakeError("handshake response too large")
        try:
            chunk = sock.recv(4096)
        except (socket.timeout, TimeoutError) as exc:
            raise HandshakeError("handshake timed out") from exc
        except (OSError, ssl.SSLError) as exc:
            raise HandshakeError(f"handshake failed: {type(exc).__name__}") from exc
        if not chunk:
            raise HandshakeError("connection closed during handshake")
        data += chunk
    head, _, rest = bytes(data).partition(b"\r\n\r\n")
    lines = head.decode("iso-8859-1").split("\r\n")
    try:
        status = int(lines[0].split(" ", 2)[1])
    except (IndexError, ValueError) as exc:
        raise HandshakeError(f"malformed status line: {lines[0]!r}") from exc
    fields: dict[str, str] = {}
    for line in lines[1:]:
        name, sep, value = line.partition(":")
        if sep:
            fields[name.strip().lower()] = value.strip()
    return status, fields, rest


__all__ = [
    "Closed",
    "HandshakeError",
    "MAX_MESSAGE_BYTES",
    "Message",
    "WebSocket",
    "WebSocketError",
    "accept_key",
    "backoff_seconds",
    "connect",
    "encode_frame",
    "handshake_request",
    "split_url",
]
