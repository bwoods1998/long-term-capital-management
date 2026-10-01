"""data-retry-v3: Gym result downloads under injected network faults, through the tree's real Sailbox transport and the
Gym driver's retry (`GymDriver._retry("download", client.download, ..., retry_transport=True)`, as `GymDriver.run`
fetches a batch's results). Only the HTTP opener is fake; there is no network and no credential.

A scenario is the fault each attempt meets, then success. A TRANSIENT fault (the network or the server failing for the
moment) followed by success within the driver's three attempts should end in the downloaded bytes. A PERMANENT fault
(a refusal no retry changes: a client error, a TLS or certificate failure, a permanent DNS failure, a permission error)
must fail at once: retrying it is a wrong retry. Labels are fixed by construction.

dev (this file): the House's Sept 29-30, 2026 failures (a timeout or refused connection on the download, a 503), the
truncated read the Sept 30 judge found unretried (`IncompleteRead`), and permanent controls, plus the faults of the
first public protocol. heldout: PRIVATE faults the dev split never uses, from the lane's pool, which lives outside this
public repo and reaches the judge only on standard input (`_common.args`, `--pool-stdin`), each named by a declarative
spec (`fault_of`): every held-out transient fault alone, then before and after another held-out transient twice each;
every held-out permanent fault alone and after a transient one (stratified), from a seed that exists only once the
candidate is committed. Answer: failed_transient, retried_permanent, requests (the lane's cost), backoff_seconds.
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

PROTOCOL = "data-retry-v3"
BOX = "sb_0123456789abcdef"
PATH = "/workspace/gym/jobs/synthetic/results.json"
PAYLOAD = b'{"synthetic": true}'

#: The exception classes a fault spec may name (a fixed vocabulary: the pool only picks and labels them).
CLASSES = {
    "TimeoutError": TimeoutError, "ConnectionError": ConnectionError, "ConnectionResetError": ConnectionResetError,
    "ConnectionAbortedError": ConnectionAbortedError, "ConnectionRefusedError": ConnectionRefusedError,
    "BrokenPipeError": BrokenPipeError, "PermissionError": PermissionError, "FileNotFoundError": FileNotFoundError,
    "IsADirectoryError": IsADirectoryError, "InterruptedError": InterruptedError, "OSError": OSError,
    "ValueError": ValueError, "EOFError": EOFError, "socket.timeout": socket.timeout,
    "http.client.HTTPException": http.client.HTTPException, "http.client.BadStatusLine": http.client.BadStatusLine,
    "http.client.RemoteDisconnected": http.client.RemoteDisconnected,
    "http.client.IncompleteRead": http.client.IncompleteRead, "http.client.LineTooLong": http.client.LineTooLong,
    "http.client.ResponseNotReady": http.client.ResponseNotReady,
    "ssl.SSLError": ssl.SSLError, "ssl.SSLEOFError": ssl.SSLEOFError, "ssl.SSLZeroReturnError": ssl.SSLZeroReturnError,
    "ssl.SSLCertVerificationError": ssl.SSLCertVerificationError, "ssl.SSLWantReadError": ssl.SSLWantReadError,
}


def _errno(name: Any) -> int:
    value = getattr(errno, str(name), None) if not isinstance(name, int) else name
    if not isinstance(value, int):
        value = getattr(socket, str(name), None)
    if not isinstance(value, int):
        raise ValueError(f"unknown errno {name!r}")
    return value


def fault_of(spec: dict[str, Any], url: str) -> BaseException:
    """An exception from a declarative spec (the dev split's own shapes, e.g.): {"type": "http", "code": 503};
    {"type": "os", "errno": "ECONNRESET"}; {"type": "gai", "errno": "EAI_AGAIN"}; {"type": "exc", "cls": "<a CLASSES
    name>", "args": [...]}; each optionally `"wrap": "url"` (urllib's URLError around it)."""
    kind = spec["type"]
    if kind == "http":
        return HTTPError(url, int(spec["code"]), "synthetic", {}, io.BytesIO(b'{"message": "synthetic"}'))
    if kind == "os":
        cause: BaseException = OSError(_errno(spec["errno"]), "synthetic")
    elif kind == "gai":
        cause = socket.gaierror(_errno(spec["errno"]), "synthetic")
    elif kind == "exc":
        cls = CLASSES[spec["cls"]]
        args = list(spec.get("args") or ["synthetic"])
        if cls is http.client.IncompleteRead:
            cause = cls(str(args[0]).encode(), *(int(a) for a in args[1:2]))
        elif cls is ssl.SSLCertVerificationError:
            cause = cls(1, "synthetic")
        else:
            cause = cls(*args)
    else:
        raise ValueError(f"unknown fault type {kind!r}")
    return URLError(cause) if spec.get("wrap") == "url" else cause


#: The dev split's faults (public): the House's shapes and the first public protocol's.
FAULTS = {
    "timeout": {"type": "exc", "cls": "TimeoutError"},
    "sock_timeout": {"type": "exc", "cls": "socket.timeout"},
    "conn_reset": {"type": "os", "errno": "ECONNRESET"},
    "conn_refused": {"type": "exc", "cls": "ConnectionRefusedError", "args": [errno.ECONNREFUSED, "synthetic"]},
    "remote_disc": {"type": "exc", "cls": "http.client.RemoteDisconnected"},
    "url_timeout": {"type": "exc", "cls": "TimeoutError", "wrap": "url"},
    "url_refused": {"type": "exc", "cls": "ConnectionRefusedError", "args": [errno.ECONNREFUSED, "synthetic"], "wrap": "url"},
    "dns_again": {"type": "gai", "errno": "EAI_AGAIN", "wrap": "url"},
    "http408": {"type": "http", "code": 408}, "http425": {"type": "http", "code": 425}, "http429": {"type": "http", "code": 429},
    "http500": {"type": "http", "code": 500}, "http502": {"type": "http", "code": 502}, "http503": {"type": "http", "code": 503},
    "http504": {"type": "http", "code": 504},
    "read_timeout": {"type": "exc", "cls": "TimeoutError", "at": "read"},
    "read_reset": {"type": "os", "errno": "ECONNRESET", "at": "read"},
    "incomplete": {"type": "exc", "cls": "http.client.IncompleteRead", "args": ["par", 16], "at": "read"},
    "http400": {"type": "http", "code": 400}, "http401": {"type": "http", "code": 401}, "http403": {"type": "http", "code": 403},
    "http404": {"type": "http", "code": 404}, "http409": {"type": "http", "code": 409}, "http422": {"type": "http", "code": 422},
    "tls": {"type": "exc", "cls": "ssl.SSLCertVerificationError", "wrap": "url"},
    "dns_perm": {"type": "gai", "errno": "EAI_NONAME", "wrap": "url"},
    "permission": {"type": "exc", "cls": "PermissionError", "args": [errno.EACCES, "synthetic"]},
}
TRANSIENT = ("timeout", "sock_timeout", "conn_reset", "conn_refused", "remote_disc", "url_timeout", "url_refused",
             "dns_again", "http408", "http425", "http429", "http500", "http502", "http503", "http504",
             "read_timeout", "read_reset", "incomplete")
PERMANENT = ("http400", "http401", "http403", "http404", "http409", "http422", "tls", "dns_perm", "permission")
DEV = [["timeout"], ["url_refused"], ["http503"], ["timeout", "timeout"], ["url_timeout"], ["http404"], ["http400"],
       ["http503", "http403"], ["incomplete"], ["read_reset"], ["dns_again"], ["tls"], ["permission"]]


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
    def __init__(self, script: list[str], faults: dict[str, dict[str, Any]]):
        self.script, self.faults, self.calls = list(script), faults, 0

    def open(self, request: Any, timeout: float | None = None) -> Response:
        self.calls += 1
        kind = self.script[self.calls - 1] if self.calls <= len(self.script) else None
        if kind is None:
            return Response(None)
        spec = self.faults[kind]
        if spec.get("at") == "read":
            return Response(fault_of(spec, request.full_url))
        raise fault_of(spec, request.full_url)


def expected(script: list[str], permanent: set[str], retries: int = 3) -> tuple[bool, int | None]:
    """(should succeed, the request at which a permanent fault must stop it)."""
    for n, kind in enumerate(script, 1):
        if kind in permanent:
            return False, n
    return len(script) < retries, None


def cases(split: str, seed: str, pool: dict | None = None) -> tuple[list[list[str]], dict[str, dict[str, Any]], set[str]]:
    """(scenarios, the faults they name, which of those are permanent)."""
    if split == "dev":
        return [list(c) for c in DEV], dict(FAULTS), set(PERMANENT)
    if not pool:
        raise ValueError("the held-out split is drawn from the lane's private pool")
    transient, permanent = dict(pool["transient"]), dict(pool["permanent"])
    held_t, held_p = sorted(transient), sorted(permanent)
    r = _common.rng(seed, PROTOCOL)
    out = []
    for kind in held_t:
        out.append([kind])
        for _ in range(2):
            out.append([kind, r.choice(held_t)])
            out.append([r.choice(held_t), kind])
    for kind in held_p:
        out.append([kind])
        out.append([r.choice(held_t), kind])
    r.shuffle(out)
    return out, {**transient, **permanent}, set(held_p)


def main() -> None:
    opts = _common.args()
    # The cases are drawn before the tree's code loads; the pool is not kept past this point.
    scenarios, faults, permanent = cases(opts.split, opts.seed, opts.pool)
    opts.pool = None

    def body() -> dict[str, Any]:
        from league.gym.driver import GymDriver, GymError
        from league.sailbox import SailboxClient, Transport

        socket.socket = None  # type: ignore[assignment,misc]  # no real connection can be opened from here on
        failed = wrong = requests = 0
        backoff = 0.0
        missed: dict[str, int] = {}
        for script in scenarios:
            opener, delays = Opener(script, faults), []
            client = SailboxClient(Transport(key_source=lambda: "synthetic-no-credential", opener=opener))
            driver = GymDriver(client, BOX, retries=3, backoff=0.01, sleep=delays.append)
            try:
                ok = driver._retry("download", client.download, BOX, PATH, retry_transport=True) == PAYLOAD
            except (GymError, Exception):  # noqa: BLE001 - any escape is a failed download
                ok = False
            should, stop = expected(script, permanent)
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

    _common.answer(PROTOCOL, opts, body)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
