"""A thin Sailbox client: the floor's own hosting layer, standard library only.

The floor runs on a Sail Sailbox, not on the owner's laptop. This module is the whole client
surface that `scripts/floor_box.py` drives: create a box with an egress allowlist, upload code,
run commands with streamed output, checkpoint, fork from a checkpoint, sleep, resume, pause,
terminate, and read status and spend.

Ported from the first generation's `sail_host.py` / `control.py`, with three rules kept:

- **The key never leaves this module.** It is fetched through `ltcm.provider.default_key_source`
  at the moment of the request, put in one `Authorization` header, and never logged, printed,
  returned or placed in an exception. Redirects are refused, so a credentialed request can never
  be pointed somewhere else.
- **Routes are allowlisted.** `Transport.allowed` is the complete list of what this client may
  call. A typo fails locally instead of reaching the API.
- **Policies are verified by live readback.** `create` asks for an egress allowlist and then reads
  the Sailbox back and compares the *stored* document against what was asked for, because Sail
  normalizes what it saves.

API basis, 2026-09-15: `https://sailbox-api.sailresearch.com/v1` (the apps endpoints live on
`https://api.sailresearch.com/v1`; the same key works on both). The published OpenAPI document,
version `2026-09-07`, names the create-time network field `egress_policy`; the older contract this
repository's cached docs describe called it `network_policy`. `create` speaks the current one and
falls back to the older name when the API rejects it, so the client survives either.

Nothing here is imported by `ltcm.service`: the floor does not operate its own box.
"""

from __future__ import annotations

import base64
import json
import re
import time
import uuid
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_HOST = "sailbox-api.sailresearch.com"
API_BASE = f"https://{API_HOST}/v1"
APPS_HOST = "api.sailresearch.com"
APPS_BASE = f"https://{APPS_HOST}/v1"

#: Where the floor's code, logs and data live on the box.
REMOTE_ROOT = "/workspace"

#: Every host the floor is allowed to open a connection to, and nothing else.
#:
#: `api.sailresearch.com` is the model provider; `api.elections.kalshi.com` and `api.coinbase.com`
#: are the live venues; `blakewoods.us` is the public site the publisher pushes to; the three
#: `sec.gov` hosts are EDGAR; the two Yahoo hosts and `news.google.com` are research sources;
#: `docs.sailresearch.com` serves the rate card the provider diffs its frozen prices against; and
#: `pypi.org` with `files.pythonhosted.org` are needed once, to install `cryptography`.
FLOOR_HOSTS: tuple[str, ...] = (
    "api.sailresearch.com",
    "api.elections.kalshi.com",
    "api.coinbase.com",
    "blakewoods.us",
    "www.sec.gov",
    "data.sec.gov",
    "efts.sec.gov",
    "query2.finance.yahoo.com",
    "feeds.finance.yahoo.com",
    "news.google.com",
    "docs.sailresearch.com",
    "pypi.org",
    "files.pythonhosted.org",
)

#: The owner's publish gateway. Sail's allowlist accepts a `*.` wildcard covering exactly one
#: extra name part, so the concrete Worker subdomain does not have to be written down here. If a
#: future API rejects wildcards, `floor_policy(gateway_host=...)` takes the exact host instead.
GATEWAY_HOST = "*.workers.dev"

_BOX_ID = re.compile(r"^sb_[0-9a-fA-F-]{8,64}$")
_APP_ID = re.compile(r"^app_[0-9a-fA-F-]{8,64}$")
_CHECKPOINT_ID = re.compile(r"^sbcp_[0-9a-fA-F-]{8,64}$")
_POLICY_ID = re.compile(r"^(?:ep|hp)_[0-9a-fA-F-]{8,64}$")
_HOST = re.compile(r"^(?:\*\.)?[a-z0-9]+(?:[.-][a-z0-9]+)*$")
_REMOTE_PATH = re.compile(r"^/[A-Za-z0-9._/-]{1,512}$")

#: Statuses a Sailbox never comes back from.
TERMINAL = ("terminated", "terminating", "failed", "create_failed", "interrupted_unsafe_to_retry")


class SailboxError(RuntimeError):
    """A Sailbox API call that did not succeed. Carries a status, never a credential."""

    def __init__(self, message: str, *, status: int | None = None, kind: str | None = None):
        super().__init__(message)
        self.status = status
        self.kind = kind


def box_id(value: Any) -> str:
    if not isinstance(value, str) or not _BOX_ID.match(value):
        raise SailboxError("not a Sailbox id")
    return value


def app_id(value: Any) -> str:
    if not isinstance(value, str) or not _APP_ID.match(value):
        raise SailboxError("not an app id")
    return value


def checkpoint_id(value: Any) -> str:
    if not isinstance(value, str) or not _CHECKPOINT_ID.match(value):
        raise SailboxError("not a checkpoint id")
    return value


def remote_path(value: str) -> str:
    """A guest path this client will touch: absolute, no traversal, no shell metacharacters."""
    if not isinstance(value, str) or not _REMOTE_PATH.match(value) or ".." in value:
        raise SailboxError(f"unsafe guest path: {value!r}")
    return value


def normalize_hosts(hosts: Iterable[str]) -> list[str]:
    """Lowercase, de-duplicate and sort an allowlist the way Sail stores it."""
    out: set[str] = set()
    for host in hosts:
        if not isinstance(host, str):
            raise SailboxError("an allowlist entry must be text")
        entry = host.strip().rstrip(".").lower()
        if not entry or not _HOST.match(entry):
            raise SailboxError(f"not an allowlist host: {host!r}")
        out.add(entry)
    if not out:
        raise SailboxError("an allowlist needs at least one host")
    if len(out) > 128:
        raise SailboxError("an allowlist holds at most 128 entries")
    return sorted(out)


def floor_policy(
    hosts: Sequence[str] = FLOOR_HOSTS, *, gateway_host: str | None = GATEWAY_HOST
) -> dict[str, Any]:
    """The egress document the floor runs under: an allowlist and nothing else.

    No `rules` block, so no credential injection: the floor's venue keys are files on the box that
    only the owner puts there, not Sail secrets, and every request leaves signed by the adapter
    that built it. `blocked` is left out because an allowlist already denies everything else.
    """
    entries = list(hosts)
    if gateway_host:
        entries.append(gateway_host)
    return {"allowlist": normalize_hosts(entries)}


def policy_allowlist(value: Any) -> list[str]:
    """The allowlist stored on a box, from either the current or the older readback shape."""
    if not isinstance(value, Mapping):
        return []
    document = value.get("document") if isinstance(value.get("document"), Mapping) else value
    if not isinstance(document, Mapping):
        return []
    hosts = document.get("allowlist")
    if hosts is None:
        hosts = document.get("allowed_hosts")
    if not isinstance(hosts, (list, tuple)):
        return []
    return sorted({str(h).strip().rstrip(".").lower() for h in hosts if isinstance(h, str)})


def check_egress(row: Mapping[str, Any], expected: Mapping[str, Any]) -> dict[str, Any]:
    """Compare a live Sailbox row against the policy that was asked for.

    Sail normalizes what it stores, so the comparison is on the allowlist as a set, plus a hard
    refusal of `no_network`. Returns a report; `ok` is the only thing a caller has to read.
    """
    policy = row.get("egress_policy")
    if policy is None:
        policy = row.get("network_policy")
    wanted = sorted(set(expected.get("allowlist") or ()))
    found = policy_allowlist(policy)
    document = policy.get("document") if isinstance(policy, Mapping) else None
    cut_off = bool(isinstance(document, Mapping) and document.get("no_network"))
    mode = policy.get("mode") if isinstance(policy, Mapping) else None
    return {
        "ok": bool(found) and found == wanted and not cut_off and mode != "no_network",
        "allowlist": found,
        "expected": wanted,
        "missing": [h for h in wanted if h not in found],
        "extra": [h for h in found if h not in wanted],
        "policy_id": policy.get("policy_id") if isinstance(policy, Mapping) else None,
        "no_network": cut_off,
    }


# --------------------------------------------------------------------------- transport


class _NoRedirect(HTTPRedirectHandler):
    """Refuse every redirect: a credentialed request must not follow the server elsewhere."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def _default_key_source() -> str:
    """The Sail key, through the floor's one key path. Never returned to a caller of this module."""
    from .provider import default_key_source

    return default_key_source()


def _error(status: int, raw: bytes) -> SailboxError:
    """Turn an API error body into an exception. The body is Sail's, never the request's."""
    message, kind = "", None
    try:
        payload = json.loads(raw.decode("utf-8", "replace"))
        error = payload.get("error") if isinstance(payload, Mapping) else None
        if isinstance(error, Mapping):
            message = str(error.get("message") or "")[:400]
            kind = error.get("type")
    except (ValueError, AttributeError):
        message = ""
    return SailboxError(f"sailbox api {status}: {message or 'no detail'}", status=status, kind=kind)


class Transport:
    """Allowlisted HTTPS calls to the Sail Sailbox API. Callable, so tests inject a function.

    One call shape covers everything the client needs:

        transport(method, path, body=None, data=None, query=None, idempotency_key=None,
                  stream=False, raw=False, timeout=None)

    and it returns a parsed JSON object, or raw `bytes` for a file download, or an iterator of
    decoded NDJSON events for a streamed exec.
    """

    def __init__(
        self,
        *,
        key_source: Callable[[], str] = _default_key_source,
        base_url: str = API_BASE,
        apps_url: str = APPS_BASE,
        opener: Any = None,
        user_agent: str = "ltcm-floor/1",
    ):
        for url, host in ((base_url, API_HOST), (apps_url, APPS_HOST)):
            if not url.startswith(f"https://{host}/v1"):
                raise ValueError(f"the Sailbox transport only speaks https to {host}")
        self.base_url = base_url.rstrip("/")
        self.apps_url = apps_url.rstrip("/")
        self.key_source = key_source
        self.user_agent = user_agent
        self._opener = opener or build_opener(_NoRedirect)

    # The complete set of routes this client may reach.
    def allowed(self, method: str, path: str) -> bool:
        if path == "/apps/find":
            return method == "POST"
        if path == "/whoami":
            return method == "GET"
        if path == "/sailboxes":
            return method in ("POST", "GET")
        if path in ("/sailboxes/from_checkpoint", "/sailboxes/spend"):
            return method == ("POST" if path.endswith("from_checkpoint") else "GET")
        if not path.startswith("/sailboxes/sb_"):
            return False
        rest = path[len("/sailboxes/") :]
        head, _, tail = rest.partition("/")
        if not _BOX_ID.match(head):
            return False
        if tail == "":
            return method == "GET"
        if tail in ("checkpoint", "sleep", "resume", "pause", "terminate", "auto_sleep", "wake_at"):
            return method == "POST"
        if tail == "exec":
            return method == "POST"
        if tail.startswith("exec/") and tail.endswith("/wait"):
            return method == "POST"
        if tail == "files":
            return method in ("PUT", "GET")
        if tail in ("egress-policy", "http-policy"):
            return method in ("GET", "PUT")
        if tail in ("metrics", "ingress-auth"):
            return method == "GET"
        return False

    def __call__(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        data: bytes | None = None,
        query: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
        stream: bool = False,
        raw: bool = False,
        timeout: float = 60.0,
    ) -> Any:
        if not self.allowed(method, path):
            raise SailboxError(f"route not on this client's allowlist: {method} {path}")
        base = self.apps_url if path.startswith("/apps/") else self.base_url
        url = base + path
        if query:
            clean = {k: v for k, v in query.items() if v is not None}
            if clean:
                url += "?" + urlencode(clean)
        headers = {
            "Authorization": "Bearer " + self.key_source(),
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        payload = data
        if body is not None:
            payload = json.dumps(body, sort_keys=True).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif data is not None:
            headers["Content-Type"] = "application/octet-stream"
        request = Request(url, data=payload, headers=headers, method=method)
        try:
            response = self._opener.open(request, timeout=timeout)
        except HTTPError as error:
            raise _error(error.code, error.read(200_000)) from None
        except (URLError, TimeoutError, OSError) as error:
            raise SailboxError(f"sailbox transport failed: {type(error).__name__}") from None
        if stream:
            return _ndjson(response)
        with response:
            if raw:
                return response.read(256_000_000)
            body_bytes = response.read(20_000_000)
        if not body_bytes:
            return {}
        try:
            return json.loads(body_bytes)
        except ValueError:
            raise SailboxError("sailbox api returned a body that is not JSON") from None


def _ndjson(response: Any) -> Iterator[dict[str, Any]]:
    """Decode a newline-delimited JSON stream, one event at a time, closing when it ends."""
    try:
        for line in response:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                yield event
    finally:
        try:
            response.close()
        except Exception:
            pass


# --------------------------------------------------------------------------- exec result


class ExecResult:
    """What one command on the box did. `output` interleaves stdout and stderr as they arrived."""

    def __init__(self, command: Any):
        self.command = command
        self.exec_id: str | None = None
        self.status: str = "unknown"
        self.return_code: int | None = None
        self.stdout: str = ""
        self.stderr: str = ""
        self.output: str = ""
        self.error_code: str | None = None

    @property
    def ok(self) -> bool:
        return self.return_code == 0 and self.status in ("succeeded", "unknown")

    def check(self) -> "ExecResult":
        if not self.ok:
            tail = (self.stderr or self.output or "")[-800:]
            raise SailboxError(
                f"command failed on the box (status {self.status}, code {self.return_code}): {tail}"
            )
        return self

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<ExecResult {self.status} code={self.return_code} bytes={len(self.output)}>"


# --------------------------------------------------------------------------- client


class SailboxClient:
    """Everything `scripts/floor_box.py` needs, and nothing that could spend money by surprise."""

    def __init__(self, transport: Any = None, *, clock: Callable[[], float] = time.time):
        self.transport = transport if transport is not None else Transport()
        self.clock = clock

    # ------------------------------------------------------------------ identity
    def whoami(self) -> dict[str, Any]:
        """Which organization and member this key belongs to. Returns ids, never the key.

        `user_id` is null for an organization key, and a `private` Sailbox needs a key that
        carries a user, so `create` asks this before it chooses a visibility.
        """
        return self.transport("GET", "/whoami")

    # ------------------------------------------------------------------ apps
    def find_app(self, name: str, *, mint_if_missing: bool = True) -> dict[str, Any]:
        row = self.transport("POST", "/apps/find", {"name": name, "mint_if_missing": mint_if_missing})
        app_id(row.get("id"))
        return row

    # ------------------------------------------------------------------ lifecycle
    def create(
        self,
        *,
        app: str,
        name: str,
        size: str = "s",
        image: Mapping[str, Any] | None = None,
        egress: Mapping[str, Any] | None = None,
        auto_sleep: Mapping[str, Any] | None = None,
        visibility: str = "private",
        memory_limit_gib: int | None = None,
        state_disk_limit_gib: int | None = None,
        idempotency_key: str | None = None,
        timeout: float = 900.0,
        policy_field: str = "auto",
    ) -> dict[str, Any]:
        """Create one Sailbox. Blocks until it is up, which can take minutes.

        `policy_field` is `auto` (send `egress_policy`, retry as `network_policy` when the API
        does not know that name), or either field name to pin the contract.
        """
        if size not in ("s", "m", "l"):
            raise SailboxError("size is one of s, m, l")
        if visibility not in ("org", "private"):
            raise SailboxError("visibility is org or private")
        body: dict[str, Any] = {
            "app_id": app_id(app),
            "name": name,
            "size": size,
            "image": dict(image or {"base": "BASE_IMAGE_DEBIAN"}),
            "visibility": visibility,
        }
        if memory_limit_gib:
            body["memory_limit_gib"] = int(memory_limit_gib)
        if state_disk_limit_gib:
            body["state_disk_limit_gib"] = int(state_disk_limit_gib)
        if auto_sleep is not None:
            body["auto_sleep"] = dict(auto_sleep)
        first = "egress_policy" if policy_field in ("auto", "egress_policy") else "network_policy"
        if egress is not None:
            body[first] = self._policy_value(first, egress)
        key = idempotency_key or f"ltcm-create-{uuid.uuid4()}"
        try:
            row = self.transport("POST", "/sailboxes", body, idempotency_key=key, timeout=timeout)
        except SailboxError as error:
            if not (
                policy_field == "auto"
                and egress is not None
                and error.status == 400
                and "egress_policy" in str(error)
            ):
                raise
            body.pop("egress_policy")
            body["network_policy"] = self._policy_value("network_policy", egress)
            row = self.transport(
                "POST",
                "/sailboxes",
                body,
                idempotency_key=f"ltcm-create-{uuid.uuid4()}",
                timeout=timeout,
            )
        box_id(row.get("sailbox_id"))
        if row.get("status") in TERMINAL:
            raise SailboxError(
                f"sailbox did not start ({row.get('status')}): {row.get('error_message') or ''}"[:300]
            )
        return row

    @staticmethod
    def _policy_value(field: str, egress: Mapping[str, Any]) -> Any:
        """The same allowlist in whichever shape the create endpoint is asking for."""
        if field == "egress_policy":
            return dict(egress)
        return {"mode": "allowlist", "allowed_hosts": list(egress.get("allowlist") or ())}

    def get(self, sailbox: str) -> dict[str, Any]:
        return self.transport("GET", f"/sailboxes/{box_id(sailbox)}")

    def list_boxes(
        self, *, app: str | None = None, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self.transport(
                "GET",
                "/sailboxes",
                query={"app": app, "status": status, "limit": min(100, limit), "offset": offset},
            )
            items = page.get("sailboxes") or page.get("data") or []
            rows.extend(item for item in items if isinstance(item, dict))
            if not page.get("has_more") or len(rows) >= limit or not items:
                return rows[:limit]
            offset += len(items)

    def egress(self, sailbox: str) -> dict[str, Any]:
        """The policy the box is actually running under, read from the box itself."""
        try:
            return self.transport("GET", f"/sailboxes/{box_id(sailbox)}/egress-policy")
        except SailboxError as error:
            if error.status != 404:
                raise
            return self.transport("GET", f"/sailboxes/{box_id(sailbox)}/http-policy") or {}

    def set_egress(self, sailbox: str, allowlist: Sequence[str]) -> dict[str, Any]:
        """Replace the box's egress allowlist with an inline document.

        `PUT /sailboxes/{id}/egress-policy` takes either a saved `policy_id` or an inline
        `document` (https://docs.sailresearch.com/api-reference/egress-policies/set-a-sailboxs-egress-policy.md);
        the floor sends a document with an allowlist and nothing else. Returns the live readback.
        """
        document = {"allowlist": normalize_hosts(list(allowlist))}
        self.transport("PUT", f"/sailboxes/{box_id(sailbox)}/egress-policy", {"document": document})
        return self.egress(sailbox)

    def verify_egress(self, sailbox: str, expected: Mapping[str, Any]) -> dict[str, Any]:
        """Read the policy back from the live API and compare it with what was asked for."""
        row = self.get(sailbox)
        report = check_egress(row, expected)
        if not report["ok"]:
            report = check_egress({"egress_policy": self.egress(sailbox)}, expected)
        return report

    def set_auto_sleep(
        self, sailbox: str, *, automatic: bool, min_seconds_before_sleep: int | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"automatic": bool(automatic)}
        if min_seconds_before_sleep is not None:
            if not automatic:
                raise SailboxError("an idle window cannot be sent with automatic sleep turned off")
            body["min_seconds_before_sleep"] = int(min_seconds_before_sleep)
        return self.transport("POST", f"/sailboxes/{box_id(sailbox)}/auto_sleep", body)

    def sleep(self, sailbox: str, *, wake_at: str | None = None) -> dict[str, Any]:
        body = {"wake_at": wake_at} if wake_at else {}
        return self.transport(
            "POST",
            f"/sailboxes/{box_id(sailbox)}/sleep",
            body,
            idempotency_key=f"ltcm-sleep-{uuid.uuid4()}",
        )

    def resume(self, sailbox: str, *, timeout: float = 300.0) -> dict[str, Any]:
        row = self.transport(
            "POST",
            f"/sailboxes/{box_id(sailbox)}/resume",
            {},
            idempotency_key=f"ltcm-resume-{uuid.uuid4()}",
            timeout=timeout,
        )
        if row.get("resume_state") == "terminal_unavailable":
            raise SailboxError(f"sailbox cannot resume: {row.get('error_message') or ''}"[:300])
        return row

    def pause(self, sailbox: str) -> dict[str, Any]:
        return self.transport(
            "POST",
            f"/sailboxes/{box_id(sailbox)}/pause",
            {},
            idempotency_key=f"ltcm-pause-{uuid.uuid4()}",
        )

    def terminate(self, sailbox: str) -> dict[str, Any]:
        return self.transport(
            "POST",
            f"/sailboxes/{box_id(sailbox)}/terminate",
            {},
            idempotency_key=f"ltcm-terminate-{uuid.uuid4()}",
        )

    # ------------------------------------------------------------------ checkpoints
    def checkpoint(
        self,
        sailbox: str,
        *,
        name: str | None = None,
        ttl_seconds: int | None = None,
        idempotency_key: str | None = None,
        timeout: float = 600.0,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if name:
            body["name"] = name
        if ttl_seconds:
            body["ttl_seconds"] = int(ttl_seconds)
        row = self.transport(
            "POST",
            f"/sailboxes/{box_id(sailbox)}/checkpoint",
            body,
            idempotency_key=idempotency_key or f"ltcm-checkpoint-{uuid.uuid4()}",
            timeout=timeout,
        )
        checkpoint_id(row.get("checkpoint_id"))
        if row.get("sailbox_id") not in (None, sailbox):
            raise SailboxError("checkpoint came back against a different Sailbox")
        return row

    def checkpoints(self, sailbox: str, *, recorded: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
        """What is known about this box's checkpoints.

        The API has no list endpoint -- `POST /sailboxes/{id}/checkpoint` and
        `POST /sailboxes/from_checkpoint` are the whole surface -- so the ids come from the
        operator's own record (`.data/ltcm/box.json`) and the counters come from the live row.
        """
        row = self.get(sailbox)
        return {
            "sailbox_id": sailbox,
            "checkpoint_generation": row.get("checkpoint_generation"),
            "last_checkpointed_at": row.get("last_checkpointed_at"),
            "recorded": [dict(entry) for entry in recorded],
        }

    def from_checkpoint(
        self, checkpoint: str, *, name: str, timeout: float = 900.0
    ) -> dict[str, Any]:
        """Start a second Sailbox from a checkpoint. It inherits the disk, memory and policy."""
        row = self.transport(
            "POST",
            "/sailboxes/from_checkpoint",
            {"checkpoint_id": checkpoint_id(checkpoint), "name": name},
            idempotency_key=f"ltcm-fork-{uuid.uuid4()}",
            timeout=timeout,
        )
        box_id(row.get("sailbox_id"))
        if row.get("checkpoint_id") != checkpoint:
            raise SailboxError("fork came back from a different checkpoint")
        if row.get("status") in TERMINAL:
            raise SailboxError(f"fork did not start ({row.get('status')})")
        return row

    # ------------------------------------------------------------------ files
    def upload(
        self,
        sailbox: str,
        path: str,
        content: bytes,
        *,
        mode: int = 0o600,
        create_parents: bool = True,
        timeout: float = 300.0,
    ) -> dict[str, Any]:
        if not isinstance(content, (bytes, bytearray)):
            raise SailboxError("upload takes bytes")
        if not 0 <= mode <= 0o777:
            raise SailboxError("mode is 0 through 511")
        return self.transport(
            "PUT",
            f"/sailboxes/{box_id(sailbox)}/files",
            data=bytes(content),
            query={
                "path": remote_path(path),
                "mode": mode,
                "create_parents": "true" if create_parents else "false",
            },
            timeout=timeout,
        )

    def download(self, sailbox: str, path: str, *, timeout: float = 300.0) -> bytes:
        return self.transport(
            "GET",
            f"/sailboxes/{box_id(sailbox)}/files",
            query={"path": remote_path(path)},
            raw=True,
            timeout=timeout,
        )

    # ------------------------------------------------------------------ exec
    def exec(
        self,
        sailbox: str,
        command: str | Sequence[str],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout: int = 600,
        background: bool = False,
        on_output: Callable[[str, str], None] | None = None,
        idempotency_key: str | None = None,
    ) -> ExecResult:
        """Run one command and stream its output. `on_output(stream, text)` sees it as it lands."""
        body: dict[str, Any] = {"command": list(command) if not isinstance(command, str) else command}
        if timeout:
            body["timeout"] = int(timeout)
        if cwd is not None:
            if not isinstance(command, str):
                raise SailboxError("cwd applies to a shell command string")
            body["cwd"] = cwd
        if background:
            if not isinstance(command, str):
                raise SailboxError("background applies to a shell command string")
            body["background"] = True
        if env:
            body["env"] = {str(k): str(v) for k, v in env.items()}
        if idempotency_key:
            body["idempotency_key"] = idempotency_key
        result = ExecResult(command)
        events = self.transport(
            "POST",
            f"/sailboxes/{box_id(sailbox)}/exec",
            body,
            stream=True,
            timeout=float(timeout or 600) + 120.0,
        )
        chunks: list[str] = []
        for event in events:
            kind = event.get("type")
            if kind == "started":
                result.exec_id = event.get("exec_request_id")
            elif kind in ("stdout", "stderr"):
                text = _decode(event.get("data"))
                if kind == "stdout":
                    result.stdout += text
                else:
                    result.stderr += text
                chunks.append(text)
                if on_output is not None:
                    on_output(kind, text)
            elif kind == "exit":
                result.status = str(event.get("status") or "unknown")
                code = event.get("return_code")
                result.return_code = int(code) if isinstance(code, int) else None
            elif kind == "error":
                result.status = "failed"
                result.error_code = str(event.get("error_code") or "error")
        result.output = "".join(chunks)
        if result.return_code is None and result.exec_id and not background:
            self._reconcile(sailbox, result)
        if background and result.return_code is None:
            result.status, result.return_code = "background", 0
        return result

    def _reconcile(self, sailbox: str, result: ExecResult) -> None:
        """The stream ended without an exit event: ask the API how the command finished.

        `POST /sailboxes/{id}/exec/{exec_id}/wait` returns the result and a bounded tail of the
        output. An exec id that will not sit in a URL segment goes in the query instead, with `-`
        in the path, which is what the HTTP API guide says to do.
        """
        exec_id = result.exec_id or ""
        segment, query = quote(exec_id, safe=""), None
        if not exec_id or len(exec_id) > 200 or "/" in exec_id:
            segment, query = "-", {"exec_request_id": exec_id}
        try:
            row = self.transport(
                "POST",
                f"/sailboxes/{box_id(sailbox)}/exec/{segment}/wait",
                {},
                query=query,
                timeout=120.0,
            )
        except SailboxError:
            result.status = "unconfirmed" if result.status == "unknown" else result.status
            return
        result.status = str(row.get("status") or result.status)
        code = row.get("return_code")
        result.return_code = int(code) if isinstance(code, int) else result.return_code
        for name in ("stdout", "stderr"):
            tail = row.get(name)
            if isinstance(tail, str) and tail and not getattr(result, name):
                setattr(result, name, tail)

    # ------------------------------------------------------------------ usage
    def spend(
        self,
        *,
        sailbox: str | None = None,
        app: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> dict[str, Any]:
        return self.transport(
            "GET",
            "/sailboxes/spend",
            query={
                "sailbox_id": box_id(sailbox) if sailbox else None,
                "app_id": app,
                "from": since,
                "to": until,
            },
        )

    def status(self, sailbox: str, *, expected_egress: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """One projection of a box: identity, size, state, policy and spend."""
        row = self.get(sailbox)
        report: dict[str, Any] = {
            "sailbox_id": row.get("sailbox_id"),
            "name": row.get("name"),
            "app_id": row.get("app_id"),
            "status": row.get("status"),
            "vcpu_count": row.get("vcpu_count"),
            "memory_mib": row.get("memory_mib"),
            "state_disk_size_gib": row.get("state_disk_size_gib"),
            "cpu_used_vcpu": row.get("cpu_used_vcpu"),
            "memory_used_bytes": row.get("memory_used_bytes"),
            "disk_used_bytes": row.get("disk_used_bytes"),
            "auto_sleep": row.get("auto_sleep"),
            "visibility": row.get("visibility"),
            "created_at": row.get("created_at"),
            "started_at": row.get("started_at"),
            "checkpoint_generation": row.get("checkpoint_generation"),
            "last_checkpointed_at": row.get("last_checkpointed_at"),
            "egress": policy_allowlist(row.get("egress_policy") or row.get("network_policy")),
        }
        if expected_egress is not None:
            report["egress_ok"] = check_egress(row, expected_egress)["ok"]
        try:
            report["spend"] = usd(self.spend(sailbox=sailbox))
        except SailboxError as error:
            report["spend_error"] = str(error)
        return report


def _decode(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    try:
        return base64.b64decode(value, validate=False).decode("utf-8", "replace")
    except (ValueError, TypeError):
        return ""


def usd(spend: Mapping[str, Any]) -> dict[str, Any]:
    """The spend response reduced to dollars. Sail counts in billionths."""

    rates = spend.get("rates") if isinstance(spend.get("rates"), Mapping) else {}

    def dollars(key: str) -> float:
        try:
            return round(int(spend.get(key) or 0) / 1_000_000_000, 6)
        except (TypeError, ValueError):
            return 0.0

    def rate(key: str, per_hour: bool = True) -> float:
        try:
            value = int(rates.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0
        return round(value * (3600 if per_hour else 1) / 1e9, 6)

    return {
        "from": spend.get("start_at"),
        "to": spend.get("end_at"),
        "finalized_usd": dollars("finalized_cost_usd_nanos"),
        "active_usd": dollars("estimated_active_cost_usd_nanos"),
        "total_usd": dollars("estimated_total_cost_usd_nanos"),
        "running_seconds": spend.get("duration_seconds"),
        "vcpu_seconds": spend.get("vcpu_seconds"),
        "rates_usd_per_hour": {
            "vcpu": rate("vcpu_second_usd_nanos"),
            "memory_gib": rate("memory_gib_second_usd_nanos"),
            "disk_gib": rate("state_disk_gib_second_usd_nanos"),
        },
        "s_creation_usd": rate("s_creation_usd_nanos", per_hour=False),
    }


def hourly_cost(status: Mapping[str, Any], spend: Mapping[str, Any]) -> float:
    """What this box costs per hour at its observed usage. Sail bills what is used, not reserved."""
    rates = spend.get("rates_usd_per_hour") if isinstance(spend, Mapping) else None
    rates = rates or {"vcpu": 0.015, "memory_gib": 0.008, "disk_gib": 0.0007}
    vcpu = float(status.get("cpu_used_vcpu") or 0.0)
    memory = float(status.get("memory_used_bytes") or 0) / (1024**3)
    disk = float(status.get("disk_used_bytes") or 0) / (1024**3)
    return round(
        vcpu * float(rates["vcpu"])
        + memory * float(rates["memory_gib"])
        + disk * float(rates["disk_gib"]),
        6,
    )
