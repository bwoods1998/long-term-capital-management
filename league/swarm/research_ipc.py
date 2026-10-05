"""Private Unix capability transport for the separate research controller.

The credential-holding broker runs on the trusted host. The controller sees only
this socket, its reviewed code and redacted research state. Socket peer identity
and framing are enforced here; resource scope, costs and job admission belong to
ResearchBroker.handle. No arbitrary URL, provider route or command is exposed.
Neither side retries an uncertain call. Paid request keys live in broker state.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import stat
import struct
import uuid
from typing import Any, Mapping

VERSION = 1
REQUEST_LIMIT = 4 * 1024 * 1024
RESPONSE_LIMIT = 32 * 1024 * 1024
OPERATIONS = frozenset(("open_runtime", "summary", "evaluate", "run_gym",
                        "recover_gym", "sleep_gym", "stop_gym", "cached_result", "recover_evaluation"))


class ResearchIPCError(RuntimeError):
    """A refused or uncertain capability call; catching it never authorizes retry."""


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ResearchIPCError("duplicate capability field")
        result[key] = value
    return result


def _encode(value: Any, limit: int) -> bytes:
    try:
        body = json.dumps(value, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise ResearchIPCError("capability message is not finite JSON") from exc
    if not 0 < len(body) <= limit:
        raise ResearchIPCError("capability message exceeds its bound")
    return struct.pack("!I", len(body)) + body


def _read_exact(connection: socket.socket, count: int) -> bytes:
    chunks = []
    while count:
        piece = connection.recv(min(count, 65536))
        if not piece:
            raise ResearchIPCError("capability reply was lost or truncated")
        chunks.append(piece)
        count -= len(piece)
    return b"".join(chunks)


def _read(connection: socket.socket, limit: int):
    size = struct.unpack("!I", _read_exact(connection, 4))[0]
    if not 0 < size <= limit:
        raise ResearchIPCError("capability message exceeds its bound")
    try:
        return json.loads(_read_exact(connection, size), object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ResearchIPCError("nonfinite capability field")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ResearchIPCError("capability message is not valid JSON") from exc


def _peer_credentials(connection: socket.socket) -> tuple[int, int, int]:
    # This transport intentionally requires Linux's kernel identity. A caller
    # cannot substitute a claimed UID in JSON or fall back to anonymous TCP.
    if not hasattr(socket, "SO_PEERCRED"):
        raise ResearchIPCError("kernel peer authentication is unavailable")
    return struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))


def _peer_uid(connection: socket.socket) -> int:
    return _peer_credentials(connection)[1]


class BrokerServer:
    """One bounded request per authenticated connection, dispatched once."""

    def __init__(self, broker, *, controller_uid: int):
        if isinstance(controller_uid, bool) or not isinstance(controller_uid, int) or controller_uid < 0:
            raise ResearchIPCError("explicit controller peer identity is required")
        if not callable(getattr(broker, "handle", None)) or not callable(getattr(broker, "authorize_peer", None)):
            raise ResearchIPCError("a reviewed high-level capability broker is required")
        self.broker, self.controller_uid = broker, controller_uid

    def serve_connection(self, connection: socket.socket) -> None:
        # Authenticate before reading a request or calling the paid broker.
        peer = _peer_credentials(connection)
        if peer[1] != self.controller_uid:
            raise ResearchIPCError("unauthorized controller peer")
        request = _read(connection, REQUEST_LIMIT)
        if (not isinstance(request, dict) or set(request) != {"version", "request_id", "operation", "payload"}
                or type(request["version"]) is not int or request["version"] != VERSION
                or not isinstance(request["request_id"], str) or len(request["request_id"]) != 32
                or any(c not in "0123456789abcdef" for c in request["request_id"])
                or not isinstance(request["operation"], str) or request["operation"] not in OPERATIONS
                or not isinstance(request["payload"], dict)):
            raise ResearchIPCError("invalid capability request")
        response = {"version": VERSION, "request_id": request["request_id"]}
        try:
            self.broker.authorize_peer(*peer)
            result = self.broker.handle(request["operation"], request["payload"])
            response.update(ok=True, result=result)
            frame = _encode(response, RESPONSE_LIMIT)
        except Exception:  # no host credentials, exception text or raw provider body crosses this wall
            response.update(ok=False, error="broker_refused_or_uncertain")
            response.pop("result", None)
            frame = _encode(response, RESPONSE_LIMIT)
        connection.sendall(frame)

    def serve_once(self, listener: socket.socket, *, timeout: float = 1800) -> None:
        connection, _ = listener.accept()
        with connection:
            connection.settimeout(timeout)
            self.serve_connection(connection)


def create_listener(path: str | Path, *, backlog: int = 8) -> socket.socket:
    """Bind a new host-owned socket in a private directory; never remove an old path."""
    path = Path(path)
    if not path.is_absolute() or path.parent.resolve() != path.parent:
        raise ResearchIPCError("capability socket needs a plain absolute parent")
    parent = path.parent.stat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise ResearchIPCError("capability socket directory must be owned and private")
    if path.exists() or path.is_symlink():
        raise ResearchIPCError("capability socket path is already occupied")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        listener.bind(str(path))
        os.chmod(path, 0o600)
        listener.listen(backlog)
        return listener
    except Exception:
        listener.close()
        raise


class BrokerClient:
    """Controller-side client: no secrets, generic provider routes or automatic retries."""

    def __init__(self, path: str | Path, *, broker_uid: int, timeout: float = 1800):
        self.path = Path(path)
        if not self.path.is_absolute() or isinstance(broker_uid, bool) or not isinstance(broker_uid, int) or broker_uid < 0:
            raise ResearchIPCError("an absolute capability socket and host peer identity are required")
        self.broker_uid, self.timeout = broker_uid, timeout

    def request(self, operation: str, payload: Mapping[str, Any] | None = None):
        if operation not in OPERATIONS or (payload is not None and not isinstance(payload, Mapping)):
            raise ResearchIPCError("unknown capability operation")
        request_id = uuid.uuid4().hex
        frame = _encode({"version": VERSION, "request_id": request_id, "operation": operation,
                         "payload": dict(payload or {})}, REQUEST_LIMIT)
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self.timeout)
                connection.connect(str(self.path))
                if _peer_uid(connection) != self.broker_uid:
                    raise ResearchIPCError("unauthorized broker peer")
                connection.sendall(frame)
                response = _read(connection, RESPONSE_LIMIT)
        except OSError as exc:
            raise ResearchIPCError("capability call outcome is unknown; do not redispatch") from exc
        if (not isinstance(response, dict) or type(response.get("version")) is not int or response.get("version") != VERSION
                or response.get("request_id") != request_id or type(response.get("ok")) is not bool):
            raise ResearchIPCError("capability response identity differs")
        if response["ok"]:
            if set(response) != {"version", "request_id", "ok", "result"}:
                raise ResearchIPCError("invalid terminal capability response")
            return response["result"]
        if set(response) != {"version", "request_id", "ok", "error"}:
            raise ResearchIPCError("invalid refused capability response")
        raise ResearchIPCError("broker refused the request or its paid outcome is unresolved")

    def open_runtime(self):
        return self.request("open_runtime")

    def summary(self):
        return self.request("summary")

    def cached_result(self, key, *, kind):
        return self.request("cached_result", {"key": key, "kind": kind})

    def evaluate(self, profile, items, *, key, **options):
        return self.request("evaluate", {"profile": profile, "items": list(items), "key": key, **options})

    def recover_evaluation(self, profile, items, *, key, **options):
        return self.request("recover_evaluation", {"profile": profile, "items": list(items), "key": key, **options})

    def run_gym(self, job, *, key):
        return self.request("run_gym", {"job": dict(job), "key": key})

    def recover_gym(self):
        return self.request("recover_gym")

    def sleep_gym(self):
        return self.request("sleep_gym")

    def stop_gym(self):
        return self.request("stop_gym")
