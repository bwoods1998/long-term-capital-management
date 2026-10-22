"""The event lane's two network clients: the LTCM gateway (Alpaca data and Claude, keyed there) and SEC EDGAR.

The gateway token never appears in an error or a log line. On the House the token comes from the House's own
environment; on blake-desktop (phase 1) from `LTCM_GATEWAY_TOKEN` or the deploy tree's `.env` (`GATEWAY_TOKEN`).

A STREAMED CLAUDE CALL (`Gateway.post_stream`, release 1019h's fix round: R3's births call on Claude Opus 5.5,
league/events/births.py `propose`). An unstreamed answer comes back only when Anthropic has finished it (the gateway
awaits the whole body, gateway/lib/router.mjs `claudeCall`), so the House's socket hears nothing for the whole
generation: a thinking Opus answer can outlast this client's 45-second read and Cloudflare's 100-second wait in front of
api.anthropic.com (HTTP 524). Streamed, the gateway relays Anthropic's events as they are made (`claudeStream`) and ends
with its own `ltcm.cost` event (what its meter booked, and whether it read the usage: `known`); the socket waits at most
`gap` seconds for each read and the whole answer at most `limit`. A stream lost after it began (it broke, went quiet,
ran past its limit, or Anthropic's stream failed) raises `StreamLost`, carrying the gateway's cost when its last event
came: the call went out and may be billed. A failure before the gateway had the whole request is urllib's `URLError`
(urllib raises it only when sending the request fails; a failure while waiting for the answer is any other `OSError`).
`NotSent` is a call refused before it went out (league/events/house.py `LaneCut`): nothing was billed.
"""

from __future__ import annotations

import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping

GATEWAY_URL = "https://ltcm-gateway.blake-woods-personal-site.workers.dev"
ENV_FILE = Path.home() / "Work" / "ltcm-deploy" / ".env"


#: The gateway's cost of a call (`X-LTCM-Cost-USD`), and its mark of one it could not read (`X-LTCM-Cost-Known: false`),
#: as `last_headers` holds them (lower case).
COST_HEADER = "x-ltcm-cost-usd"
COST_KNOWN_HEADER = "x-ltcm-cost-known"


class NotSent(OSError):
    """A call refused before it went out (league/events/house.py `LaneCut`, the lane's own refusal): nothing was billed."""


class StreamLost(OSError):
    """A streamed answer lost after the call went out (`Gateway.post_stream`): it may still be billed. `cost` is the
    gateway's `ltcm.cost` when that last event came (`known`: the gateway read the usage), else None."""

    def __init__(self, message: str, *, cost: float | None = None, known: bool = False):
        super().__init__(message)
        self.cost = cost
        self.known = bool(known)


class GatewayError(Exception):
    """A gateway answer that is not 2xx (status and the gateway's own message, never the token)."""

    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message[:300]}")
        self.status = status


def token_from_env(env_file: Path = ENV_FILE) -> str:
    token = os.environ.get("LTCM_GATEWAY_TOKEN")
    if token:
        return token.strip()
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("GATEWAY_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("no gateway token: set LTCM_GATEWAY_TOKEN or GATEWAY_TOKEN in the deploy tree's .env")


class Gateway:
    def __init__(self, token: str | Callable[[], str], *, url: str = GATEWAY_URL, timeout: float = 45.0,
                 opener: Any = None, min_interval: float = 0.0, sleep: Callable[[float], None] = time.sleep):
        self._token = token
        self.url = url.rstrip("/")
        self.timeout = float(timeout)
        self._open = opener or urllib.request.build_opener().open
        self.min_interval = float(min_interval)
        self._last = 0.0
        self._sleep = sleep
        self.last_headers: dict[str, str] = {}

    def token(self) -> str:
        return self._token() if callable(self._token) else self._token

    def _space(self) -> None:
        if self.min_interval:
            wait = self._last + self.min_interval - time.monotonic()
            if wait > 0:
                self._sleep(wait)
            self._last = time.monotonic()

    def _prepare(self, method: str, path: str, *, params: Mapping[str, Any] | None = None, body: Any = None,
                 headers: Mapping[str, str] | None = None, accept: str = "application/json") -> urllib.request.Request:
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{self.url}{path}" + (f"?{query}" if query else "")
        data = None if body is None else json.dumps(body).encode("utf-8")
        sent = {"Authorization": f"Bearer {self.token()}", "Accept": accept, "User-Agent": "ltcm-evl/1"}
        if data is not None:
            sent["Content-Type"] = "application/json"
        sent.update(headers or {})
        return urllib.request.Request(url, data=data, headers=sent, method=method)

    @staticmethod
    def _payload(raw: bytes) -> Any:
        try:
            return json.loads(raw.decode("utf-8")) if raw else None
        except ValueError:
            return raw.decode("utf-8", "replace")

    def _request(self, method: str, path: str, *, params: Mapping[str, Any] | None = None, body: Any = None,
                 headers: Mapping[str, str] | None = None) -> tuple[int, Any]:
        self._space()
        req = self._prepare(method, path, params=params, body=body, headers=headers)
        try:
            with self._open(req, timeout=self.timeout) as resp:
                status, raw, hdrs = int(resp.status), resp.read(), dict(resp.headers.items())
        except urllib.error.HTTPError as err:
            status, raw, hdrs = int(err.code), err.read(), dict(err.headers.items()) if err.headers else {}
        payload = self._payload(raw)
        self.last_headers = {k.lower(): v for k, v in hdrs.items()}
        return status, payload

    def get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        status, payload = self._request("GET", path, params=params)
        if not 200 <= status < 300:
            message = payload.get("message") or payload.get("error") if isinstance(payload, dict) else payload
            raise GatewayError(status, str(message or ""))
        return payload

    def post_json(self, path: str, body: Any, headers: Mapping[str, str] | None = None) -> tuple[int, Any]:
        return self._request("POST", path, body=body, headers=headers)

    def post_stream(self, path: str, body: Any, headers: Mapping[str, str] | None = None, *, limit: float,
                    gap: float | None = None, clock: Callable[[], float] = time.monotonic) -> tuple[int, Any]:
        """POST a streamed Claude call (`body` carries `"stream": true`; the module docstring): (status, the answer's
        message rebuilt from its events: its blocks with their text, its stop reason, its usage and model). The socket
        waits at most `gap` seconds (this client's timeout when None) for each read, and the whole answer at most `limit`
        seconds. The gateway's `ltcm.cost` is put in `last_headers` as an unstreamed answer's `X-LTCM-Cost-USD`, with
        `X-LTCM-Cost-Known: false` when the gateway could not read the usage. An answer that is not a stream (a refusal
        before the call was forwarded, or Anthropic's error before its stream began) is read as `post_json` reads one.
        Raises `StreamLost` for a stream lost after it began, and as urllib does for a failure before the answer came."""
        self._space()
        req = self._prepare("POST", path, body=body, headers=headers, accept="text/event-stream")
        until = clock() + float(limit)
        try:
            opened = self._open(req, timeout=self.timeout if gap is None else float(gap))
        except urllib.error.HTTPError as err:
            with err:
                raw, hdrs = err.read(), dict(err.headers.items()) if err.headers else {}
            self.last_headers = {k.lower(): v for k, v in hdrs.items()}
            return int(err.code), self._payload(raw)
        with opened as resp:
            status = int(resp.status)
            hdrs = {k.lower(): v for k, v in dict(resp.headers.items()).items()}
            if not str(hdrs.get("content-type") or "").startswith("text/event-stream"):
                self.last_headers = hdrs
                return status, self._payload(resp.read())
            self.last_headers = {k: v for k, v in hdrs.items() if k not in (COST_HEADER, COST_KNOWN_HEADER)}
            message, cost, known = read_stream(resp, until=until, limit=float(limit), clock=clock)
        if cost is not None:
            self.last_headers[COST_HEADER] = f"{cost:.6f}"
        if cost is None or not known:
            self.last_headers[COST_KNOWN_HEADER] = "false"
        return status, message


def read_stream(resp: Any, *, until: float, limit: float,
                clock: Callable[[], float] = time.monotonic) -> tuple[dict[str, Any], float | None, bool]:
    """A relayed Claude stream read to its end (gateway/lib/router.mjs `claudeStream`): (the message rebuilt from its
    events, the gateway's `ltcm.cost` or None, whether that cost is known). Text blocks are rebuilt from their
    `text_delta`s; any other block (a thinking block's summary) keeps only its type. Raises `StreamLost` when the stream
    breaks or goes quiet (a read that fails or times out), runs past `until` before Anthropic's `message_stop`, carries
    Anthropic's `error` event, or ends before `message_stop`; the gateway's cost goes with it when its last event came.
    After `message_stop` the answer is whole: the clock no longer cuts it (only the gateway's last event is waited for)."""
    message: dict[str, Any] = {}
    blocks: dict[int, dict[str, Any]] = {}
    usage: dict[str, Any] = {}
    state: dict[str, Any] = {"stopped": False, "error": None, "cost": None, "known": False}
    data: list[str] = []

    def dispatch() -> None:
        if not data:
            return
        try:
            event = json.loads("\n".join(data))
        except ValueError:
            event = None
        data.clear()
        if not isinstance(event, dict):
            return
        kind = event.get("type")
        index = event.get("index") if type(event.get("index")) is int else 0
        if kind == "message_start" and isinstance(event.get("message"), dict):
            message.update({k: v for k, v in event["message"].items() if k != "content"})
            usage.update({k: v for k, v in (event["message"].get("usage") or {}).items() if v is not None})
        elif kind == "content_block_start" and isinstance(event.get("content_block"), dict):
            block = event["content_block"]
            blocks[index] = {"type": block.get("type")} | ({"text": str(block.get("text") or "")}
                                                            if block.get("type") == "text" else {})
        elif kind == "content_block_delta" and isinstance(event.get("delta"), dict):
            delta = event["delta"]
            if delta.get("type") == "text_delta":
                block = blocks.setdefault(index, {"type": "text", "text": ""})
                block["text"] = str(block.get("text") or "") + str(delta.get("text") or "")
        elif kind == "message_delta":
            if isinstance(event.get("delta"), dict) and event["delta"].get("stop_reason") is not None:
                message["stop_reason"] = event["delta"]["stop_reason"]
            usage.update({k: v for k, v in (event.get("usage") or {}).items() if v is not None})
        elif kind == "message_stop":
            state["stopped"] = True
        elif kind == "error":
            state["error"] = str((event.get("error") or {}).get("type") or "error")
        elif kind == "ltcm.cost":
            try:
                amount = float(event.get("cost_usd")) if event.get("cost_usd") is not None else None
            except (TypeError, ValueError):
                amount = None
            if amount is not None and amount == amount and 0 <= amount < float("inf"):
                state["cost"], state["known"] = amount, event.get("known") is True

    def lost(why: str) -> StreamLost:
        return StreamLost(why, cost=state["cost"], known=state["known"])

    try:
        while True:
            if not state["stopped"] and clock() > until:
                raise lost(f"the Claude stream ran past its {limit:.0f}-second limit")
            line = resp.readline()
            if not line:
                break
            text = line.decode("utf-8", "replace").rstrip("\r\n")
            if not text:
                dispatch()
            elif text.startswith("data:"):
                data.append(text[5:][1:] if text[5:].startswith(" ") else text[5:])
        dispatch()
    except StreamLost:
        raise
    except (http.client.HTTPException, OSError, ValueError) as exc:     # a quiet or cut stream (a timeout, IncompleteRead)
        if not state["stopped"]:
            raise lost(f"the Claude stream went quiet or broke: {type(exc).__name__}") from None
    if state["error"]:
        raise lost(f"Anthropic's stream failed: {state['error']}")
    if not state["stopped"]:
        raise lost("the Claude stream ended before the answer did")
    message["content"] = [blocks[i] for i in sorted(blocks)]
    message["usage"] = usage
    return message, state["cost"], state["known"]


#: EDGAR's answers that are tried again (rate limit, server busy), and the waits between the tries: one 503 from
#: browse-edgar failed Monday Oct 19's first live open decision. A read still failing after them raises as before.
SEC_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
SEC_RETRY_WAITS = (1.0, 2.0, 4.0)


def sec_getter(transport: Any = None, *, sleep: Callable[[float], Any] | None = None) -> Callable[[str], bytes]:
    """`get(url) -> bytes` for www.sec.gov with the House's contact User-Agent and the SEC's rate (ltcm.data)."""
    from ltcm.data import CONTACT_USER_AGENT, HttpTransport
    from ltcm.data.edgar import MIN_INTERVAL

    # 30 MB, not the transport's 4 MB default: an 8-K's exhibit can be a large HTML file, and dropping those would make
    # the event set depend on document size (PREREG TEXT reads only the first 16,000 characters of it).
    pause = sleep or time.sleep
    transport = transport or HttpTransport(user_agent=CONTACT_USER_AGENT, min_interval=MIN_INTERVAL,
                                           max_bytes=30 * 1024 * 1024)

    def get(url: str) -> bytes:
        if not url.startswith("https://www.sec.gov/"):
            raise ValueError(f"not an SEC URL: {url[:80]}")
        for wait in SEC_RETRY_WAITS + (None,):
            status, _, body = transport.get(url, {"Accept": "*/*"}, 45.0)
            if status == 200:
                return body
            if status not in SEC_RETRY_STATUS or wait is None:
                break
            pause(wait)
        raise GatewayError(status, f"SEC {url[:120]}")
    return get


__all__ = ["Gateway", "GatewayError", "NotSent", "StreamLost", "read_stream", "token_from_env", "sec_getter",
           "GATEWAY_URL", "COST_HEADER", "COST_KNOWN_HEADER"]
