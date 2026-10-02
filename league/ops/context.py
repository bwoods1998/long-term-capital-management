"""What a House job gets: `run(ctx) -> dict` (`league/ops/registry.py`).

    ctx.job, ctx.due_at (epoch), ctx.now() (the clock), ctx.root (<state>), ctx.base (/workspace), ctx.release
    (the running release's directory), ctx.config (its league/config.json), ctx.settings (<state>/ops.json, the
    owner's private overrides; {} when absent), ctx.gateway (a GET/POST client of the Cloudflare gateway, built on
    first use from GATEWAY_TOKEN), ctx.sail (a `league.sailbox.SailboxClient`, built on first use), ctx.alert(level,
    text) (a House alert the runner raises when the job ends), ctx.house_box() (the House box's Sail id: the config's
    `backup.box_id` pin, else the environment Sail sets).

A job's return value is its receipt (`summary_json`, a small JSON object). A job that decides it has nothing to do
returns `{"status": "skipped", "why": ...}`; one that failed without raising returns `{"status": "failed", "error": ...}`;
any exception is a `failed` receipt with its text.
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

RELEASE = Path(__file__).resolve().parents[2]
USER_AGENT = "ltcm-floor-ops/1.0"


class GatewayError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


class Gateway:
    """The gateway, bounded and without retries. The token is read at each call and never logged or returned; an
    error's text carries the gateway's answer (cut short), never the request's headers."""

    def __init__(self, url: str, token: Callable[[], str], *, timeout: float = 45.0, opener: Any = None):
        if not url:
            raise GatewayError("no gateway_url in league/config.json")
        self.url = str(url).rstrip("/")
        self.token = token
        self.timeout = float(timeout)
        self.opener = opener or urllib.request.build_opener()
        self.calls: list[str] = []

    def _call(self, method: str, path: str, params: Mapping[str, Any] | None = None, body: Any = None) -> Any:
        query = "?" + urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None}) if params else ""
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Authorization": "Bearer " + self.token(), "User-Agent": USER_AGENT}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.url + path + query, data=data, method=method, headers=headers)
        self.calls.append(f"{method} {path}")
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(8_000_000).decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read(400).decode("utf-8", "replace") if exc.fp is not None else ""
            raise GatewayError(f"{method} {path}: HTTP {exc.code} {detail[:300]}", status=exc.code) from None
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise GatewayError(f"{method} {path}: {type(exc).__name__}: {str(exc)[:200]}") from None
        try:
            return json.loads(raw) if raw else None
        except ValueError:
            raise GatewayError(f"{method} {path}: not JSON") from None

    def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        return self._call("GET", path, params)

    def post(self, path: str, body: Any) -> Any:
        return self._call("POST", path, None, body)


def token_from_env() -> str:
    value = os.environ.get("GATEWAY_TOKEN", "").strip()
    if len(value) < 16:
        raise GatewayError("GATEWAY_TOKEN is not set")
    return value


def read_json(path: str | Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: str | Path, value: Any, *, mode: int = 0o600, indent: int | None = 1) -> Path:
    """Atomic, owner-only."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True, indent=indent, default=str) + "\n")
    os.replace(tmp, path)
    return path


def write_text(path: str | Path, text: str, *, mode: int = 0o600) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(tmp, path)
    return path


def settings(root: str | Path) -> dict[str, Any]:
    """`<state>/ops.json`, the owner's private overrides (an object), or {}."""
    value = read_json(Path(root) / "ops.json", {})
    return value if isinstance(value, dict) else {}


class Context:
    def __init__(self, job: str, *, root: str | Path, due_at: float, base: str | Path | None = None,
                 release: str | Path | None = None, config: Mapping[str, Any] | None = None,
                 clock: Callable[[], float] = time.time, gateway: Any = None, sail: Any = None,
                 settings_value: Mapping[str, Any] | None = None):
        self.job = job
        self.root = Path(root)
        self.base = Path(base) if base is not None else self.root.parent
        self.release = Path(release) if release is not None else RELEASE
        self.due_at = float(due_at)
        self.clock = clock
        self._config = dict(config) if config is not None else None
        self._gateway = gateway
        self._sail = sail
        self.settings = dict(settings_value) if settings_value is not None else settings(self.root)
        self.alerts: list[dict[str, str]] = []

    def now(self) -> float:
        return float(self.clock())

    @property
    def config(self) -> dict[str, Any]:
        if self._config is None:
            self._config = read_json(self.release / "league" / "config.json", {}) or {}
        return self._config

    @property
    def gateway(self) -> Any:
        if self._gateway is None:
            self._gateway = Gateway(str(self.config.get("gateway_url") or ""), token_from_env)
        return self._gateway

    @property
    def sail(self) -> Any:
        if self._sail is None:
            from ..sailbox import SailboxClient

            self._sail = SailboxClient()
        return self._sail

    def job_settings(self) -> dict[str, Any]:
        value = self.settings.get(self.job)
        return dict(value) if isinstance(value, dict) else {}

    def house_box(self) -> str | None:
        """The House box's Sail id: `league/config.json` `backup.box_id` when pinned (the House box was forked, and Sail's
        environment can still name the box it came from: `league/backup.py`), else the id Sail's environment gives."""
        from ..backup import BOX_ID_VARS

        block = self.config.get("backup") if isinstance(self.config, Mapping) else None
        pinned = block.get("box_id") if isinstance(block, Mapping) else None
        if isinstance(pinned, str) and pinned.strip():
            return pinned.strip()
        for name in BOX_ID_VARS:
            value = os.environ.get(name, "").strip()
            if value:
                return value
        return None

    def alert(self, level: str, text: str) -> None:
        self.alerts.append({"level": str(level), "text": str(text)[:900]})
