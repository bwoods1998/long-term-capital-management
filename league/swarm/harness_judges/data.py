"""data-retry-v1: Gym result downloads under injected network faults, through the tree's real Sailbox transport and the
Gym driver's retry (`GymDriver._retry("download", client.download, ..., retry_transport=True)`, as `GymDriver.run`
fetches a batch's results). Only the HTTP opener is fake; there is no network and no credential.

A scenario is the fault each attempt meets, then success. A TRANSIENT fault (a timeout, a reset or refused connection,
a temporary DNS failure, HTTP 408/425/429/5xx, a timeout, reset or truncation while the body is read) followed by
success within the driver's three attempts should end in the downloaded bytes. A PERMANENT fault (HTTP 4xx other than
408/425/429, a TLS failure, a permanent DNS failure, a permission error) must fail at once: retrying it is a wrong
retry. Labels are fixed by construction.

dev: the House's Sept 29-30, 2026 failures (a timeout or refused connection on the download, a 503) and permanent
controls. heldout: one or two faults drawn from a wider pool (read-phase faults included), permanent faults alone or
after a transient one, drawn from the seed. Answer: failed_transient, retried_permanent, requests (the lane's cost),
backoff_seconds.
"""
from __future__ import annotations

import errno
import http.client
import io
import socket
import ssl
import sys
from typing import Any
from urllib.error import HTTPError, URLError

import _common

PROTOCOL = "data-retry-v1"
BOX = "sb_0123456789abcdef"
PATH = "/workspace/gym/jobs/synthetic/results.json"
PAYLOAD = b'{"synthetic": true}'


def fault(kind: str, url: str) -> BaseException:
    if kind.startswith("http"):
        return HTTPError(url, int(kind[4:]), "synthetic", {}, io.BytesIO(b'{"message": "synthetic"}'))
    return {
        "timeout": lambda: TimeoutError("synthetic"),
        "sock_timeout": lambda: socket.timeout("synthetic"),
        "conn_reset": lambda: ConnectionResetError(errno.ECONNRESET, "synthetic"),
        "conn_refused": lambda: ConnectionRefusedError(errno.ECONNREFUSED, "synthetic"),
        "remote_disc": lambda: http.client.RemoteDisconnected("synthetic"),
        "url_timeout": lambda: URLError(TimeoutError("synthetic")),
        "url_refused": lambda: URLError(ConnectionRefusedError(errno.ECONNREFUSED, "synthetic")),
        "dns_again": lambda: URLError(socket.gaierror(socket.EAI_AGAIN, "synthetic")),
        "read_timeout": lambda: TimeoutError("synthetic"),
        "read_reset": lambda: ConnectionResetError(errno.ECONNRESET, "synthetic"),
        "incomplete": lambda: http.client.IncompleteRead(b"par", 16),
        "tls": lambda: URLError(ssl.SSLCertVerificationError(1, "synthetic")),
        "dns_perm": lambda: URLError(socket.gaierror(socket.EAI_NONAME, "synthetic")),
        "permission": lambda: PermissionError(errno.EACCES, "synthetic"),
    }[kind]()


TRANSIENT = ("timeout", "sock_timeout", "conn_reset", "conn_refused", "remote_disc", "url_timeout", "url_refused",
             "dns_again", "http408", "http425", "http429", "http500", "http502", "http503", "http504",
             "read_timeout", "read_reset", "incomplete")
PERMANENT = ("http400", "http401", "http403", "http404", "http409", "http422", "tls", "dns_perm", "permission")
READ_PHASE = ("read_timeout", "read_reset", "incomplete")
DEV = [["timeout"], ["url_refused"], ["http503"], ["timeout", "timeout"], ["url_timeout"], ["http404"], ["http400"],
       ["http503", "http403"]]


class Response:
    def __init__(self, error: BaseException | None):
        self.error, self.done = error, False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size: int = -1) -> bytes:
        if self.error is not None:
            raise self.error
        if self.done:
            return b""
        self.done = True
        return PAYLOAD


class Opener:
    def __init__(self, script: list[str]):
        self.script, self.calls = list(script), 0

    def open(self, request: Any, timeout: float | None = None) -> Response:
        self.calls += 1
        kind = self.script[self.calls - 1] if self.calls <= len(self.script) else None
        if kind is None:
            return Response(None)
        if kind in READ_PHASE:
            return Response(fault(kind, request.full_url))
        raise fault(kind, request.full_url)


def expected(script: list[str], retries: int = 3) -> tuple[bool, int | None]:
    """(should succeed, the request at which a permanent fault must stop it)."""
    for n, kind in enumerate(script, 1):
        if kind in PERMANENT:
            return False, n
    return len(script) < retries, None


def cases(split: str, seed: str) -> list[list[str]]:
    if split == "dev":
        return [list(c) for c in DEV]
    r = _common.rng(seed, PROTOCOL)
    out = []
    for _ in range(24):
        roll = r.random()
        if roll < 0.55:
            out.append([r.choice(TRANSIENT) for _ in range(r.choice((1, 1, 2)))])
        elif roll < 0.75:
            out.append([r.choice(PERMANENT)])
        else:
            out.append([r.choice(TRANSIENT), r.choice(PERMANENT)])
    return out


def main() -> None:
    opts = _common.args()

    def body() -> dict[str, Any]:
        from league.gym.driver import GymDriver, GymError
        from league.sailbox import SailboxClient, Transport

        socket.socket = None  # type: ignore[assignment,misc]  # no real connection can be opened from here on
        failed = wrong = requests = 0
        backoff = 0.0
        missed: dict[str, int] = {}
        scenarios = cases(opts.split, opts.seed)
        for script in scenarios:
            opener, delays = Opener(script), []
            client = SailboxClient(Transport(key_source=lambda: "synthetic-no-credential", opener=opener))
            driver = GymDriver(client, BOX, retries=3, backoff=0.01, sleep=delays.append)
            try:
                ok = driver._retry("download", client.download, BOX, PATH, retry_transport=True) == PAYLOAD
            except (GymError, Exception):  # noqa: BLE001 - any escape is a failed download
                ok = False
            should, stop = expected(script)
            requests += opener.calls
            backoff += sum(delays)
            if should and not ok:
                failed += 1
                key = "+".join(script)
                missed[key] = missed.get(key, 0) + 1
            if stop is not None and opener.calls > stop:
                wrong += 1
        return {"failed_transient": failed, "retried_permanent": wrong, "requests": requests,
                "backoff_seconds": round(backoff, 6), "missed": missed, "cases": len(scenarios)}

    _common.answer(PROTOCOL, opts.split, opts.seed, body)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
