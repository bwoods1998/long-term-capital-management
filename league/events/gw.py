"""The event lane's two network clients: the LTCM gateway (Alpaca data and Claude, keyed there) and SEC EDGAR.

The gateway token never appears in an error or a log line. On the House the token comes from the House's own
environment; on blake-desktop (phase 1) from `LTCM_GATEWAY_TOKEN` or the deploy tree's `.env` (`GATEWAY_TOKEN`).
"""

from __future__ import annotations

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

    def token(self) -> str:
        return self._token() if callable(self._token) else self._token

    def _request(self, method: str, path: str, *, params: Mapping[str, Any] | None = None, body: Any = None,
                 headers: Mapping[str, str] | None = None) -> tuple[int, Any]:
        if self.min_interval:
            wait = self._last + self.min_interval - time.monotonic()
            if wait > 0:
                self._sleep(wait)
            self._last = time.monotonic()
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{self.url}{path}" + (f"?{query}" if query else "")
        data = None if body is None else json.dumps(body).encode("utf-8")
        sent = {"Authorization": f"Bearer {self.token()}", "Accept": "application/json", "User-Agent": "ltcm-evl/1"}
        if data is not None:
            sent["Content-Type"] = "application/json"
        sent.update(headers or {})
        req = urllib.request.Request(url, data=data, headers=sent, method=method)
        try:
            with self._open(req, timeout=self.timeout) as resp:
                status, raw = int(resp.status), resp.read()
        except urllib.error.HTTPError as err:
            status, raw = int(err.code), err.read()
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else None
        except ValueError:
            payload = raw.decode("utf-8", "replace")
        return status, payload

    def get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        status, payload = self._request("GET", path, params=params)
        if not 200 <= status < 300:
            message = payload.get("message") or payload.get("error") if isinstance(payload, dict) else payload
            raise GatewayError(status, str(message or ""))
        return payload

    def post_json(self, path: str, body: Any, headers: Mapping[str, str] | None = None) -> tuple[int, Any]:
        return self._request("POST", path, body=body, headers=headers)


def sec_getter(transport: Any = None) -> Callable[[str], bytes]:
    """`get(url) -> bytes` for www.sec.gov with the House's contact User-Agent and the SEC's rate (ltcm.data)."""
    from ltcm.data import CONTACT_USER_AGENT, HttpTransport
    from ltcm.data.edgar import MIN_INTERVAL

    transport = transport or HttpTransport(user_agent=CONTACT_USER_AGENT, min_interval=MIN_INTERVAL)

    def get(url: str) -> bytes:
        if not url.startswith("https://www.sec.gov/"):
            raise ValueError(f"not an SEC URL: {url[:80]}")
        status, _, body = transport.get(url, {"Accept": "*/*"}, 45.0)
        if status != 200:
            raise GatewayError(status, f"SEC {url[:120]}")
        return body
    return get


__all__ = ["Gateway", "GatewayError", "token_from_env", "sec_getter", "GATEWAY_URL"]
