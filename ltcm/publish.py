"""Streaming the floor to the public site.

Two endpoints, one rule: nothing leaves the box that the publication policy has not cleared.

* `POST {site}/api/capital/events` receives the event tape in batches of at most 100, in sequence
  order, each event already stripped of private (underscore-prefixed) payload keys by
  `Event.to_public()`. Public events go immediately. Deferred events -- order intents and orders --
  are *held* until the gateway says their order is terminal, so nobody can trade ahead of a desk.
  Private kinds (the raw provider records) are never sent at all.
* `POST {site}/api/capital/checkpoint` receives the leaderboard projection: the floor, each desk
  and the committee, with every money field as a decimal string.

The site validates hard, and it is right to: a desk is a language model, and a model writing a
memo is an untrusted author of strings. `sanitize_for_site` therefore runs before anything is
sent -- angle brackets neutered, control characters removed, credential-shaped text redacted,
links outside the allowlist dropped, every string truncated -- so a single bad sentence cannot
get a whole batch rejected. Events whose *shape* is wrong (a malformed timestamp, a stream that
disagrees with its kind) are skipped with an `ops.alert` rather than retried forever, and so is
any single event the site answers 400 to.

Progress is a small JSON file: the sequence number scanned through, plus the ids of deferred events
passed over. A crash replays at most one batch, and the site's own idempotency on event id makes a
replay a no-op.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .events import KINDS, Event, EventLog, canonical, now_iso, public_view

SCHEMA_VERSION = 1
EVENTS_PATH = "/api/capital/events"
CHECKPOINT_PATH = "/api/capital/checkpoint"
RETRY_STATUSES = (408, 425, 429, 500, 502, 503, 504, 529)
MAX_BATCH = 100

# ---------------------------------------------------------------- the site's shape contract
AT_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ID_PATTERN = re.compile(r"^[A-Za-z0-9:_.\-]{1,200}$")
SUFFIX_PATTERN = re.compile(r"^[a-z0-9-]{1,40}$")
#: kind prefix -> the stream it must live on. A trailing colon means "prefix plus a suffix".
STREAM_FOR: dict[str, str] = {
    "desk": "desk:",
    "ledger": "ledger:",
    "broker": "broker:",
    "risk": "risk",
    "committee": "committee",
    "evolution": "evolution",
    "lab": "lab",
    "ops": "ops",
    # The floor's balance mark belongs to the whole floor, not to a desk, so it rides `ops`.
    "floor": "ops",
}

MAX_STRING = 8000
#: Tab, newline and carriage return survive; every other C0/C1 control character does not.
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
SECRET = re.compile(r"\bsk-\S*|\bAPCA-\S*|\bBearer[ :]\s*\S*")
URL = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s<>\"\')]+")
#: The site refuses a string carrying a script-capable URI; a colon followed by whitespace
#: ("from the data:\n") is prose and passes on both sides. Mirrors `UNSAFE_SCHEME` in the
#: site's schema.js, so a desk that writes a data URI loses the URI, not the whole thought.
UNSAFE_SCHEME = re.compile(r"\b(javascript|vbscript|data|file|blob):(?=\S)", re.IGNORECASE)
ALLOWED_HOSTS = frozenset(
    {
        "sec.gov",
        "www.sec.gov",
        "efts.sec.gov",
        "blakewoods.us",
        "github.com",
        "kalshi.com",
        "finance.yahoo.com",
    }
)
REDACTED = "[redacted]"
DROPPED_LINK = "[link removed]"


class PublishError(RuntimeError):
    """The site refused a batch, or the transport failed after every retry."""

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


PCT_PLACES = Decimal("0.000001")  # the site accepts at most six fraction digits on a percent
MONEY_PLACES = Decimal("0.00000001")  # and eight on money


def jsonable(value: Any, *, key: str = "") -> Any:
    """Decimals become strings quantized to what the site accepts; the rest is plain JSON."""
    if isinstance(value, Decimal):
        places = PCT_PLACES if key.endswith("_pct") else MONEY_PLACES
        if value.is_finite() and value.as_tuple().exponent < places.as_tuple().exponent:
            try:  # only trim what the site would refuse; never pad a short number
                value = value.quantize(places, rounding=ROUND_HALF_EVEN)
            except InvalidOperation:
                pass
        return format(value, "f")
    if isinstance(value, Mapping):
        return {str(k): jsonable(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v, key=key) for v in value]
    if isinstance(value, str) and key.endswith("_pct") and _looks_decimal(value):
        return jsonable(Decimal(value), key=key)
    if isinstance(value, str) and key in MONEY_KEYS and _looks_decimal(value):
        return jsonable(Decimal(value), key=key)
    return value


MONEY_KEYS = frozenset(
    {"equity", "cash", "daily_pnl", "capital_usd", "cost_usd", "spent_today_usd", "cap_usd",
     "trailing_realized_usd", "base_usd", "ceiling_usd", "live_equity", "live_daily_pnl",
     "spend_usd", "account_equity", "account_cash"}
)


def _looks_decimal(value: str) -> bool:
    text_value = value.strip()
    if not text_value or len(text_value) > 60:
        return False
    body = text_value[1:] if text_value[0] in "+-" else text_value
    return body.replace(".", "", 1).isdigit()


def _host_allowed(url: str) -> bool:
    if not url.lower().startswith("https://"):
        return False
    rest = url[len("https://") :]
    host = rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    host = host.split("@")[-1].split(":")[0].lower()
    return host in ALLOWED_HOSTS


#: The floor's own credential values, registered at start so that a string carrying one of
#: them, however it got there, never reaches the site. Values only; names are not secret.
_SECRET_LITERALS: list[str] = []


def register_secret_literals(values: Iterable[Any]) -> int:
    """Remember credential values to redact. Short or empty values are ignored: a four-letter
    token would redact ordinary words. Returns how many are registered."""
    found = {str(v) for v in values if isinstance(v, str) and len(v) >= 16}
    _SECRET_LITERALS[:] = sorted(found, key=len, reverse=True)
    return len(_SECRET_LITERALS)


def sanitize_string(value: str) -> str:
    """Make one model-written string safe to hand the site, without changing what it says."""
    cleaned = CONTROL.sub("", value)
    cleaned = SECRET.sub(REDACTED, cleaned)
    for literal in _SECRET_LITERALS:
        if literal in cleaned:
            cleaned = cleaned.replace(literal, REDACTED)
    cleaned = URL.sub(lambda m: m.group(0) if _host_allowed(m.group(0)) else DROPPED_LINK, cleaned)
    cleaned = cleaned.replace("<", "\u2039")
    cleaned = UNSAFE_SCHEME.sub(lambda m: m.group(1) + ": ", cleaned)
    if len(cleaned) > MAX_STRING:
        cleaned = cleaned[: MAX_STRING - 1] + "\u2026"
    return cleaned


def sanitize_for_site(payload: Any) -> Any:
    """Recursively sanitize a payload: private keys gone, strings safe, lengths bounded.

    Applied to every event before it is sent. One desk writing an angle bracket, a stray control
    character or something that looks like an API key must not cost the whole batch.
    """
    if isinstance(payload, Mapping):
        return {
            str(key): sanitize_for_site(value)
            for key, value in payload.items()
            if not (isinstance(key, str) and key.startswith("_"))
        }
    if isinstance(payload, (list, tuple)):
        return [sanitize_for_site(item) for item in payload]
    if isinstance(payload, str):
        return sanitize_string(payload)
    if isinstance(payload, Decimal):
        return format(payload, "f")
    return payload


#: The site's payload limits (capital/schema.js `safeValue` and `validPayload`), mirrored so a
#: payload the site would refuse is named here as a bug instead of discovered as a 400.
SITE_MAX_PAYLOAD_BYTES = 20 * 1024
SITE_MAX_KEYS = 100
SITE_MAX_ITEMS = 500
SITE_MAX_DEPTH = 8
SITE_MAX_STRING = 8000
SITE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")


def payload_problem(value: Any, depth: int = 0) -> str | None:
    """Why the site's `safeValue` would refuse this (already sanitized) payload, or None."""
    if depth > SITE_MAX_DEPTH:
        return f"nesting deeper than {SITE_MAX_DEPTH} levels"
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return None if math.isfinite(value) else "a number that is not finite"
    if isinstance(value, str):
        if len(value) > SITE_MAX_STRING:
            return f"a string of {len(value)} characters (the site takes {SITE_MAX_STRING})"
        return None
    if isinstance(value, (list, tuple)):
        if len(value) > SITE_MAX_ITEMS:
            return f"a list of {len(value)} items (the site takes {SITE_MAX_ITEMS})"
        for item in value:
            problem = payload_problem(item, depth + 1)
            if problem is not None:
                return problem
        return None
    if isinstance(value, Mapping):
        if len(value) > SITE_MAX_KEYS:
            return f"an object with {len(value)} keys (the site takes {SITE_MAX_KEYS})"
        for key, item in value.items():
            if not isinstance(key, str) or not SITE_KEY.match(key):
                return f"key {str(key)[:40]!r} is not publishable"
            problem = payload_problem(item, depth + 1)
            if problem is not None:
                return problem
        return None
    return f"a value of type {type(value).__name__}"


def shape_problem(event: Event) -> str | None:
    """Why the site would refuse this event's shape, or None when it would accept it.

    Checked here rather than discovered as a 400: a malformed event is a bug in this box, and it
    should be named in an alert instead of blocking the tape behind an endless retry.
    """
    kind = event.kind
    if KINDS.get(kind) == "private":
        return f"{kind} is never published"
    if not ID_PATTERN.match(event.id or ""):
        return f"event id {event.id!r} is not publishable"
    if not DIGEST_PATTERN.match(event.digest or ""):
        return "digest is not 64 lowercase hex characters"
    if not AT_PATTERN.match(event.at or ""):
        return f"timestamp {event.at!r} is not YYYY-MM-DDTHH:MM:SS.mmmZ"
    prefix = kind.split(".", 1)[0]
    expected = STREAM_FOR.get(prefix)
    if expected is None:
        return f"no stream is defined for {kind}"
    if expected.endswith(":"):
        if not event.stream.startswith(expected):
            return f"{kind} belongs on {expected}<id>, not {event.stream!r}"
        if not SUFFIX_PATTERN.match(event.stream[len(expected) :]):
            return f"stream suffix {event.stream[len(expected):]!r} is not lowercase [a-z0-9-]"
    elif event.stream != expected:
        return f"{kind} belongs on the {expected!r} stream, not {event.stream!r}"
    wire = sanitize_for_site(public_view(event.payload))
    if not isinstance(wire, Mapping):
        return "payload is not an object"
    problem = payload_problem(wire)
    if problem is not None:
        return f"payload has {problem}"
    if len(json.dumps(wire, separators=(",", ":")).encode("utf-8")) > SITE_MAX_PAYLOAD_BYTES:
        return f"payload is over {SITE_MAX_PAYLOAD_BYTES // 1024} KB"
    return None


def wire_event(event: Event) -> dict[str, Any]:
    """Exactly the keys the site accepts, with the payload sanitized."""
    return {
        "seq": event.seq,
        "id": event.id,
        "stream": event.stream,
        "kind": event.kind,
        "at": event.at,
        "digest": event.digest,
        "payload": sanitize_for_site(public_view(event.payload)),
    }


def _retry_after(headers: Mapping[str, str] | None, attempt: int) -> float:
    """Honour the server's backoff hint, else exponential with a one-second floor."""
    if headers:
        for key in ("retry-after", "Retry-After"):
            raw = headers.get(key)
            if raw:
                try:
                    return max(0.0, min(60.0, float(str(raw).strip())))
                except ValueError:
                    break
    return min(30.0, float(2**attempt))


class Publisher:
    """Batches public events and the leaderboard checkpoint to the site API."""

    def __init__(
        self,
        log: EventLog,
        site_url: str,
        token_source: Callable[[], str] | str | None,
        transport: Any,
        clock: Callable[[], float] = time.time,
        state_path: str | Path = "publish-state.json",
        *,
        batch_size: int = MAX_BATCH,
        max_attempts: int = 4,
        sleeper: Callable[[float], None] = time.sleep,
        timeout: float = 20.0,
    ):
        self.log = log
        self.site_url = site_url.rstrip("/")
        self.token_source = token_source
        self.transport = transport
        self.clock = clock
        self.state_path = Path(state_path)
        self.batch_size = max(1, min(int(batch_size), MAX_BATCH))
        self.max_attempts = max(1, int(max_attempts))
        self.sleeper = sleeper
        self.timeout = float(timeout)

    # ------------------------------------------------------------------ state
    def state(self) -> dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        held = data.get("held")
        return {
            "schema_version": SCHEMA_VERSION,
            "last_seq": int(data.get("last_seq") or 0),
            "held": [h for h in held if isinstance(h, str)] if isinstance(held, list) else [],
            "sent": int(data.get("sent") or 0),
            "updated_at": data.get("updated_at"),
        }

    def _save(self, state: Mapping[str, Any]) -> None:
        body = dict(state)
        body["schema_version"] = SCHEMA_VERSION
        body["updated_at"] = now_iso(self.clock)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_name(self.state_path.name + f".tmp-{os.getpid()}")
        tmp.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.state_path)

    # ------------------------------------------------------------------ transport
    def token(self) -> str:
        source = self.token_source
        if callable(source):
            source = source()
        if not source:
            raise PublishError("no publish token available")
        return str(source)

    def post(self, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """One POST with retries. Never logs or returns the bearer token."""
        url = f"{self.site_url}{path}"
        body = canonical(jsonable(payload)).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        last: str = "not attempted"
        for attempt in range(self.max_attempts):
            try:
                status, response_headers, raw = self.transport.request(
                    "POST", url, headers=headers, body=body, timeout=self.timeout
                )
            except Exception as exc:
                last = f"transport error: {exc}"
                if attempt + 1 >= self.max_attempts:
                    raise PublishError(f"{path}: {last}") from exc
                self.sleeper(_retry_after(None, attempt))
                continue
            if 200 <= int(status) < 300:
                try:
                    return json.loads(raw.decode("utf-8")) if raw else {}
                except (UnicodeDecodeError, json.JSONDecodeError):
                    return {}
            last = f"HTTP {status}"
            if int(status) in RETRY_STATUSES and attempt + 1 < self.max_attempts:
                self.sleeper(_retry_after(response_headers, attempt))
                continue
            raise PublishError(f"{path}: {last}", status=int(status))
        raise PublishError(f"{path}: {last}")

    # ------------------------------------------------------------------ events
    @staticmethod
    def sendable(event: Event, released: set[str]) -> str:
        """"send", "hold" or "skip" for one event under the publication policy."""
        if KINDS.get(event.kind) == "private":
            return "skip"
        if event.public:
            return "send"
        return "send" if event.id in released else "hold"

    def push_events(self, released_ids: Iterable[str] = ()) -> dict[str, Any]:
        """Send everything cleared for publication. Returns a summary of what moved."""
        released = {i for i in released_ids if isinstance(i, str)}
        state = self.state()
        last_seq: int = state["last_seq"]
        total_sent: int = state["sent"]

        # Deferred events passed over on an earlier call: send the ones now cleared.
        to_send: list[Event] = []
        held: list[tuple[int, str]] = []
        for event_id in state["held"]:
            event = self.log.get(event_id)
            if event is None:  # never happens to an append-only log, but do not crash on it
                continue
            if event.public or event_id in released:
                to_send.append(event)
            else:
                held.append((event.seq, event_id))

        # Everything appended since the last scan.
        scanned = last_seq
        while True:
            batch = self.log.read(after=scanned, limit=2000)
            if not batch:
                break
            for event in batch:
                scanned = event.seq
                verdict = self.sendable(event, released)
                if verdict == "send":
                    to_send.append(event)
                elif verdict == "hold":
                    held.append((event.seq, event.id))
            if len(batch) < 2000:
                break

        # Anything the site would refuse on shape is named in an alert and passed over, not
        # retried until the end of time.
        skipped = 0
        publishable: list[Event] = []
        seen_ids: set[str] = set()
        for event in sorted(to_send, key=lambda e: e.seq):
            problem = shape_problem(event)
            if problem is not None:
                self.alert(f"event {event.id} not published: {problem}")
                skipped += 1
                continue
            if event.id in seen_ids:  # duplicate ids in one batch are a 400
                continue
            seen_ids.add(event.id)
            publishable.append(event)

        held.sort()
        sent = batches = 0

        def commit(mark: int) -> None:
            """Everything at or below `mark` is accounted for: sent, held or skipped."""
            nonlocal last_seq
            last_seq = max(last_seq, mark)
            self._save(
                {
                    "last_seq": last_seq,
                    "held": [i for seq, i in held if seq <= last_seq],
                    "sent": total_sent,
                }
            )

        for start in range(0, len(publishable), self.batch_size):
            chunk = publishable[start : start + self.batch_size]
            delivered, dropped = self.send_batch(chunk)
            sent += delivered
            skipped += dropped
            batches += 1
            total_sent += delivered
            commit(chunk[-1].seq)

        if scanned > last_seq or [i for _, i in held] != state["held"]:
            commit(scanned)

        return {
            "sent": sent,
            "skipped": skipped,
            "batches": batches,
            "last_seq": last_seq,
            "held": len([1 for seq, _ in held if seq <= last_seq]),
        }

    def send_batch(self, chunk: Sequence[Event]) -> tuple[int, int]:
        """Post one batch. Returns (delivered, dropped).

        A 400 means the site refused something in this batch. The batch is halved until the
        offending event is alone, then that one event is alerted and dropped: the tape keeps
        moving. A 409 means the site already holds that id with a different digest, which no
        amount of resending can fix, so the batch is alerted and passed over.
        """
        if not chunk:
            return 0, 0
        try:
            self.post(
                EVENTS_PATH,
                {"schema_version": SCHEMA_VERSION, "events": [wire_event(e) for e in chunk]},
            )
            return len(chunk), 0
        except PublishError as exc:
            if exc.status not in (400, 409):
                raise
            # The site takes a batch in one transaction, so one bad id refuses all of them:
            # halve until the one is alone, then say so and move past it. A 409 is one event
            # the site holds with a different digest; the other ninety-nine still go.
            if len(chunk) == 1:
                self.alert(
                    f"site refused event {chunk[0].id}: {exc}",
                    level="critical" if exc.status == 409 else "warning",
                )
                return 0, 1
        middle = len(chunk) // 2
        first = self.send_batch(chunk[:middle])
        second = self.send_batch(chunk[middle:])
        return first[0] + second[0], first[1] + second[1]

    def alert(self, message: str, *, level: str = "warning") -> None:
        """Say so in the log. Publication problems are operational events, not silent losses."""
        at = now_iso(self.clock)
        try:
            self.log.append(
                "ops",
                "ops.alert",
                {"level": level, "text": message[:2000]},
                id=f"alert:publish:{at}:{abs(hash(message)) % 10**9}",
                at=at,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------ checkpoint
    def push_checkpoint(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Send the leaderboard projection. `body` carries floor, desks, committee and budget."""
        payload = {
            "schema_version": SCHEMA_VERSION,
            "published_at": body.get("published_at") or now_iso(self.clock),
            **{k: v for k, v in body.items() if k not in ("schema_version", "published_at")},
        }
        payload, trimmed = fit_checkpoint(payload)
        if trimmed:
            self.alert(f"checkpoint trimmed to fit the site's cap: {trimmed}", level="warning")
        return self.post(CHECKPOINT_PATH, payload)


#: The site refuses a checkpoint over 256 KB; the floor keeps a margin under it.
CHECKPOINT_CAP_BYTES = 240 * 1024


def _checkpoint_bytes(payload: Mapping[str, Any]) -> int:
    return len(canonical(jsonable(payload)).encode("utf-8"))


def fit_checkpoint(payload: Mapping[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Trim a checkpoint that would exceed the site's cap: shadow desks' positions first (they
    are scores, not money), then every thesis to a line, then the shadow desks' strategies. A
    book of sixteen desks holding fifty contracts each would otherwise refuse every checkpoint
    with nothing on the runtime side saying why (audit, Sept 16, 2026)."""
    body = dict(payload)
    if _checkpoint_bytes(body) <= CHECKPOINT_CAP_BYTES:
        return body, None
    steps: list[str] = []
    desks = [dict(d) for d in body.get("desks") or []]
    for desk in desks:
        if desk.get("mode") != "live" and desk.get("positions"):
            desk["positions"] = []
    body["desks"] = desks
    steps.append("shadow positions dropped")
    if _checkpoint_bytes(body) > CHECKPOINT_CAP_BYTES:
        for desk in desks:
            for row in desk.get("positions") or []:
                if isinstance(row, dict) and isinstance(row.get("thesis"), str):
                    row["thesis"] = row["thesis"][:80]
        steps.append("theses cut to a line")
    if _checkpoint_bytes(body) > CHECKPOINT_CAP_BYTES:
        for desk in desks:
            if desk.get("mode") != "live":
                desk.pop("strategies", None)
                desk.pop("working", None)
        steps.append("shadow strategies dropped")
    return body, ", ".join(steps)


def _site_factor(value: Any) -> Any:
    """The site accepts a budget factor in (0, 10]; the config could say otherwise."""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return max(Decimal("0.01"), min(Decimal("10"), number)).quantize(Decimal("0.01"))


def unsigned(value: Any) -> Any:
    """The site refuses a negative where only a magnitude makes sense. Clamp, do not lie:
    a desk cannot hold less than nothing, and a drawdown is reported as its own depth."""
    if value is None:
        return None
    number = value if isinstance(value, Decimal) else Decimal(str(value))
    return abs(number) if number < 0 else number


def floor_at_zero(value: Any) -> Any:
    """A balance the site treats as unsigned: a negative one is published as zero, and the real
    number stays in the ledger and the health file where an operator will see it."""
    if value is None:
        return None
    number = value if isinstance(value, Decimal) else Decimal(str(value))
    return number if number > 0 else Decimal(0)


def not_after(stamp: Any, limit: str) -> Any:
    """No row may claim to be newer than the checkpoint that carries it."""
    if not isinstance(stamp, str) or not stamp:
        return None
    return stamp if stamp <= limit else limit


#: A venue name the site will accept on a balance row.
VENUE_PATTERN = re.compile(r"^[a-z0-9-]{1,24}$")
#: `...THH:MM:SS` with an optional fraction and a UTC marker, which is what a venue answers with.
STAMP_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(?:Z|\+00:00)$")


def millis(value: Any) -> str | None:
    """A venue timestamp in the log's `YYYY-MM-DDTHH:MM:SS.mmmZ` form, or None if unreadable.

    The venue adapters stamp a balance to the second; the site accepts milliseconds and nothing
    else, so the missing digits are added here rather than invented anywhere upstream.
    """
    if not isinstance(value, str):
        return None
    found = STAMP_PATTERN.match(value.strip())
    if found is None:
        return None
    return f"{found.group(1)}.{((found.group(2) or '')[:3]).ljust(3, '0')}Z"


def venue_rows(rows: Any, published_at: str) -> list[dict[str, Any]]:
    """One row per venue account the box could read: `{venue, equity, cash, as_of}`.

    Balances are unsigned and stamped no later than the checkpoint that carries them. A row the
    box could not refresh keeps its last known numbers and says `stale: true` rather than
    disappearing, so a venue outage reads as an outage instead of as a fall in the balance.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows or ():
        if not isinstance(row, Mapping):
            continue
        venue = str(row.get("venue") or "")
        if not VENUE_PATTERN.match(venue) or venue in seen:
            continue
        seen.add(venue)
        clean: dict[str, Any] = {
            "venue": venue,
            "equity": floor_at_zero(row.get("equity")),
            "cash": floor_at_zero(row.get("cash")),
            "as_of": not_after(millis(row.get("as_of")), published_at) or published_at,
        }
        if row.get("stale"):
            clean["stale"] = True
        out.append(clean)
    return out


def account_totals(rows: Sequence[Mapping[str, Any]]) -> dict[str, Decimal]:
    """The whole portfolio: every venue balance added up, which is the number the owner asked for."""
    total_equity = Decimal(0)
    total_cash = Decimal(0)
    for row in rows:
        total_equity += Decimal(str(row.get("equity") or 0))
        total_cash += Decimal(str(row.get("cash") or 0))
    return {"equity": total_equity, "cash": total_cash}


def account_block(rows: Any, published_at: str) -> dict[str, Any]:
    """The floor's real account balances, or `{}` when no venue has answered even once.

    Absent is the honest answer for a box with no live venue: the site draws nothing rather than
    a zero that would read as a portfolio that lost everything.
    """
    venues = venue_rows(rows, published_at)
    if not venues:
        return {}
    totals = account_totals(venues)
    return {
        "account_equity": totals["equity"],
        "account_cash": totals["cash"],
        "venues": venues,
    }


def counted(value: Any) -> int | None:
    """A whole non-negative count, or None. The site types these and refuses anything else."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else 0


def runway_fields(budget: Mapping[str, Any]) -> dict[str, Any]:
    """The spend-policy fields of a budget block, in the site's shapes: money as strings,
    `balance_usd` and `runway_days` null when the balance could not be read."""
    if not budget.get("mode"):
        return {}
    out: dict[str, Any] = {"mode": str(budget["mode"])}
    for key in ("balance_usd", "runway_days"):
        value = budget.get(key)
        out[key] = None if value is None else floor_at_zero(value)
    for key in ("spendable_usd", "burn_usd_per_day", "reserve_usd", "desk_fuse_usd"):
        out[key] = floor_at_zero(budget.get(key))
    return out


def mutation_block(value: Any) -> dict[str, Any] | None:
    """leap: lab -- a bred desk's mutation in the contract's shape, or None for a founder."""
    if not isinstance(value, Mapping):
        return None
    return {
        "model_profile": str(value.get("model_profile") or "")[:80],
        "reasoning_effort": str(value.get("reasoning_effort") or "")[:20],
        "session_shift_minutes": int(value.get("session_shift_minutes") or 0),
        "memory_limit": counted(value.get("memory_limit")),
        "persona_trait": str(value.get("persona_trait") or "")[:200],
        "model_changed": bool(value.get("model_changed")),
    }


STRATEGY_NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


def _plain_params_for_site(value: Any) -> dict[str, Any]:
    """A strategy's params as the site accepts them: plain values, sanitized strings, under 1 KB."""
    out: dict[str, Any] = {}
    for key, raw in sorted(dict(value).items()):
        name = str(key)[:40]
        if not SITE_KEY.match(name) or name.startswith("_"):
            continue
        if isinstance(raw, bool) or isinstance(raw, (int, float)):
            out[name] = raw
        elif isinstance(raw, str):
            out[name] = sanitize_string(raw)[:80]
        elif isinstance(raw, (list, tuple)):
            out[name] = [sanitize_string(str(item))[:40] for item in list(raw)[:20]]
        if len(json.dumps(out)) > 900:
            out.pop(name, None)
            break
    return out


def strategy_rows(value: Any, published_at: str | None = None) -> list[dict[str, Any]]:
    """leap: strategies -- the site's shape for a desk's strategies: at most eight rows of
    `{name, house, cadence_seconds, runs, intents, approved, errors, fills, settled, wins,
    settled_pnl_usd, last_run_at, last_notes}`. Anything malformed is left out, never sent."""
    if not isinstance(value, (list, tuple)):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in value:
        if not isinstance(row, Mapping):
            continue
        name = str(row.get("name") or "")
        if not STRATEGY_NAME.match(name) or name in seen:
            continue
        seen.add(name)
        counters = {}
        for key in ("runs", "intents", "approved", "errors", "fills", "settled", "wins"):
            try:
                counters[key] = max(0, int(row.get(key) or 0))
            except (TypeError, ValueError):
                counters[key] = 0
        try:
            cadence = max(1, min(86_400, int(row.get("cadence_seconds") or 600)))
        except (TypeError, ValueError):
            cadence = 600
        pnl = row.get("settled_pnl_usd")
        try:
            pnl_text = format(Decimal(str(pnl)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN), "f") if pnl not in (None, "") else "0.00"
        except (InvalidOperation, ValueError):
            pnl_text = "0.00"
        last_run = row.get("last_run_at")
        last_run = not_after(last_run, published_at) if isinstance(last_run, str) and AT_PATTERN.match(last_run) else None
        out.append(
            {
                "name": name,
                "house": bool(row.get("house")),
                **({"enabled": bool(row["enabled"])} if "enabled" in row else {}),
                "cadence_seconds": cadence,
                **counters,
                "settled_pnl_usd": pnl_text,
                "last_run_at": last_run,
                "last_notes": sanitize_string(str(row.get("last_notes") or ""))[:240],
                # Why these settings (a promotion, a lab experiment, the house) and the settings.
                **({"note": sanitize_string(str(row["note"]))[:200]} if row.get("note") else {}),
                **({"params": _plain_params_for_site(row.get("params"))} if isinstance(row.get("params"), Mapping) and row.get("params") else {}),
            }
        )
        if len(out) >= 8:
            break
    return out


def working_rows(value: Any, published_at: str | None = None) -> list[dict[str, Any]]:
    """The desk's resting orders in the site's shape: at most twenty of `{order_id, instrument,
    side, quantity, limit_price, submitted_at, purpose, strategy, intent_id}`."""
    if not isinstance(value, (list, tuple)):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in value:
        if not isinstance(row, Mapping):
            continue
        order_id = str(row.get("order_id") or "")
        if not order_id or order_id in seen or len(order_id) > 120:
            continue
        instrument = row.get("instrument") if isinstance(row.get("instrument"), Mapping) else {}
        symbol = str(instrument.get("symbol") or "")
        asset_class = str(instrument.get("asset_class") or "")
        venue = str(instrument.get("venue") or "")
        side = str(row.get("side") or "")
        if not symbol or not asset_class or not venue or side not in ("buy", "sell"):
            continue
        try:
            quantity = floor_at_zero(row.get("quantity"))
            limit_price = None if row.get("limit_price") in (None, "") else floor_at_zero(row.get("limit_price"))
        except (InvalidOperation, ValueError, TypeError):
            continue
        if quantity is None:
            continue
        submitted = row.get("submitted_at")
        submitted = not_after(submitted, published_at) if isinstance(submitted, str) and AT_PATTERN.match(submitted) else None
        seen.add(order_id)
        wire_instrument: dict[str, Any] = {"symbol": symbol[:80], "asset_class": asset_class[:24], "venue": venue}
        for extra in ("market_id", "right"):
            if instrument.get(extra):
                wire_instrument[extra] = str(instrument[extra])[:80]
        out.append(
            {
                "order_id": order_id,
                "instrument": wire_instrument,
                "side": side,
                "quantity": quantity,
                "limit_price": limit_price,
                "submitted_at": submitted,
                "purpose": "exit" if row.get("purpose") == "exit" else "entry",
                "strategy": (str(row["strategy"])[:40] if row.get("strategy") else None),
                "intent_id": (str(row["intent_id"])[:120] if row.get("intent_id") else None),
            }
        )
        if len(out) >= 20:
            break
    return out


def calibration_block(value: Any) -> dict[str, Any] | None:
    """leap: lab -- `{n, brier, since}` when a desk has scored forecasts, else None."""
    if not isinstance(value, Mapping) or not int(value.get("n") or 0):
        return None
    brier = value.get("brier")
    return {
        "n": counted(value.get("n")),
        "brier": None if brier is None else floor_at_zero(brier),
        "since": value.get("since"),
    }


def public_change(value: Any) -> dict[str, Any]:
    """An experiment's change as the checkpoint carries it. The site caps a change at 4 KB, so
    a strategy's code (up to 6,000 characters) travels as its digest and length; the code itself
    is on the tape in the `lab.experiment` event and in the variant's toolbox."""
    change = {str(k): v for k, v in dict(value).items() if isinstance(k, str) and SITE_KEY.match(k) and not k.startswith("_")} if isinstance(value, Mapping) else {}
    spec = change.get("strategy")
    if isinstance(spec, Mapping):
        import hashlib

        code = str(spec.get("code") or "")
        change["strategy"] = {
            "name": str(spec.get("name") or "")[:40],
            "cadence_seconds": spec.get("cadence_seconds"),
            "params": _plain_params_for_site(spec.get("params") or {}) if isinstance(spec.get("params"), Mapping) else {},
            "code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest()[:16],
            "code_chars": len(code),
        }
    if isinstance(change.get("playbook_note"), str):
        change["playbook_note"] = sanitize_string(change["playbook_note"])[:600]
    # Whatever the site would still refuse is withheld rather than sent: one bad experiment on
    # the checkpoint would freeze the whole page for as long as it stayed on the list.
    if payload_problem(change) is not None:
        return {"withheld": "the change did not fit the site's shape"}
    return change


def lab_block(value: Any) -> dict[str, Any]:
    """leap: lab -- the checkpoint's lab block: experiments, the improvement curve, calibration."""
    lab = value if isinstance(value, Mapping) else {}
    experiments = []
    for row in list(lab.get("experiments") or [])[:12]:
        if not isinstance(row, Mapping):
            continue
        entry = {
            "experiment_id": str(row.get("experiment_id") or ""),
            "hypothesis": sanitize_string(str(row.get("hypothesis") or ""))[:600],
            "family": str(row.get("family") or ""),
            "parent_id": row.get("parent_id"),
            "change": public_change(row.get("change")),
            "variant_desk_id": row.get("variant_desk_id"),
            "status": str(row.get("status") or ""),
            "proposed_at": row.get("proposed_at"),
            "evaluate_after": row.get("evaluate_after"),
        }
        if row.get("verdict_reason"):
            entry["verdict_reason"] = sanitize_string(str(row["verdict_reason"]))[:600]
        experiments.append(entry)
    curve = [dict(row) for row in list(lab.get("curve") or [])[:40] if isinstance(row, Mapping)]
    calibration = lab.get("calibration") if isinstance(lab.get("calibration"), Mapping) else {}
    brier = calibration.get("brier")
    return {
        "experiments": experiments,
        "curve": curve,
        "calibration": {
            "n": counted(calibration.get("n")),
            "brier": None if brier is None else floor_at_zero(brier),
        },
    }


def checkpoint_body(
    *,
    published_at: str,
    floor: Mapping[str, Any],
    desks: Sequence[Mapping[str, Any]],
    committee: Mapping[str, Any],
    budget: Mapping[str, Any],
    infra: Mapping[str, Any] | None = None,
    watch: Mapping[str, Any] | None = None,
    lab: Mapping[str, Any] | None = None,
    run: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The exact shape the site expects. Money stays `Decimal` for `jsonable` to render.

    The desks array replaces the published roster wholesale, so it always carries every desk,
    retired ones included, rather than a delta.

    The floor block is **real money only**. `live_equity` and `live_daily_pnl` are the ledger's
    numbers, which is what attributes a gain to a desk, and `shadow_desks` counts the desks whose
    books are hypothetical. `account_equity`, `account_cash` and `venues` are the venue accounts
    themselves -- Kalshi plus Coinbase -- and are present only when a venue answered.
    A shadow desk still gets a row, with its notional equity and its hypothetical return, so the
    competition for a live sleeve is legible -- but nothing on that row is ever added to the floor.
    """
    infra = dict(infra or {})
    return {
        "schema_version": SCHEMA_VERSION,
        "published_at": published_at,
        "floor": {
            "equity": floor_at_zero(floor.get("equity")),
            "cash": floor_at_zero(floor.get("cash")),
            "daily_pnl": floor.get("daily_pnl"),
            "capital_usd": floor_at_zero(floor.get("capital_usd")),
            "since_inception_pct": floor.get("since_inception_pct"),
            "benchmark": floor.get("benchmark"),
            "live_equity": floor_at_zero(floor.get("live_equity", floor.get("equity"))),
            "live_daily_pnl": floor.get("live_daily_pnl", floor.get("daily_pnl")),
            "live_desks": counted(floor.get("live_desks")),
            "shadow_desks": counted(floor.get("shadow_desks")),
            # The owner's actual money, read from the venues themselves rather than folded from
            # the tape. `live_equity` above stays the ledger's number, which is what attributes a
            # gain to a desk; this is what the bank says the account holds.
            **account_block(floor.get("venues"), published_at),
            **({"performance": {key: floor["performance"].get(key) for key in
                ("start_at", "start_equity", "net_flows", "verified_at")}} if floor.get("performance") else {}),
        },
        "desks": [
            {
                "id": desk.get("id"),
                "name": desk.get("name"),
                "family": desk.get("family"),
                "generation": desk.get("generation"),
                "parent_id": desk.get("parent_id"),
                "mode": desk.get("mode"),
                "venues": list(desk.get("venues") or []),
                "capital_usd": floor_at_zero(desk.get("capital_usd")),
                "equity": desk.get("equity"),
                "cash": desk.get("cash"),
                "daily_pnl": desk.get("daily_pnl"),
                **({"pnl_usd": desk.get("pnl_usd")} if desk.get("pnl_usd") is not None else {}),
                "return_pct": desk.get("return_pct"),
                "max_drawdown_pct": unsigned(desk.get("max_drawdown_pct")),
                "days_live": desk.get("days_live"),
                "orders": desk.get("orders"),
                "cost_usd": floor_at_zero(desk.get("cost_usd")),
                "status": "halted" if desk.get("status") == "blocked" else desk.get("status"),
                "gate": desk.get("gate"),
                "updated_at": not_after(desk.get("updated_at"), published_at),
                **({"next_session_at": desk.get("next_session_at")} if "next_session_at" in desk else {}),
                # leap: exits and watch. Optional on the wire: an older floor omits them.
                **({"positions": [position_row(row, published_at) for row in list(desk.get("positions") or [])[:50]]}
                   if desk.get("positions") is not None else {}),
                **({"live_session": live_session_row(desk.get("live_session"), published_at)}
                   if desk.get("live_session") else {}),
                # leap: lab -- optional, absent for a founder or a desk with no scored forecast.
                **({"mutation": mutation_block(desk["mutation"])} if mutation_block(desk.get("mutation")) else {}),
                **({"calibration": calibration_block(desk["calibration"])} if calibration_block(desk.get("calibration")) else {}),
                # leap: strategies -- optional; an older floor, or a desk with none, omits it.
                **({"strategies": strategy_rows(desk["strategies"], published_at)} if strategy_rows(desk.get("strategies"), published_at) else {}),
                **({"working": working_rows(desk["working"], published_at)} if working_rows(desk.get("working"), published_at) else {}),
                **({"budget_factor": _site_factor(desk.get("budget_factor"))} if desk.get("budget_factor") not in (None, "") else {}),
            }
            for desk in desks
        ],
        "committee": {
            "last_memo_at": not_after(committee.get("last_memo_at"), published_at),
            "allocations": {
                str(k): floor_at_zero(v)
                for k, v in sorted((committee.get("allocations") or {}).items())
            },
        },
        "budget": {
            "spent_today_usd": floor_at_zero(budget.get("spent_today_usd")),
            "cap_usd": floor_at_zero(budget.get("cap_usd")),
            # The runway policy's picture, when the floor runs under it. Absent under a fixed cap.
            **runway_fields(budget),
        },
        # Where the floor runs and what the box has cost today. Absent facts stay null rather
        # than guessing: the site prints what it is given and nothing more.
        "infra": {
            "host": infra.get("host") or "local",
            "box_id": infra.get("box_id"),
            "checkpoint_count": counted(infra.get("checkpoint_count")),
            "spend_usd": floor_at_zero(infra.get("spend_usd")),
            "uptime_seconds": counted(infra.get("uptime_seconds")),
            "region": infra.get("region"),
            "requests_today": counted(infra.get("requests_today")),
        },
        # leap: watch. What the night desk did today; absent on a floor without one.
        **({"watch": watch_row(watch, published_at)} if watch is not None else {}),
        # leap: lab -- present whenever the floor runs a lab, however empty its record.
        **({"lab": lab_block(lab)} if lab is not None else {}),
        # leap: run clock -- how long the desks have worked, what it cost, what it earned.
        **({"run": run_row(run)} if run is not None else {}),
    }


def position_row(row: Mapping[str, Any], published_at: str | None = None) -> dict[str, Any]:
    """One entry of a desk's positions board, in the contract's shape (leap: exits)."""
    instrument = dict(row.get("instrument") or {})
    exits = []
    for order in list(row.get("exit_orders") or [])[:8]:
        exits.append(
            {
                "id": str(order.get("id")),
                "kind": str(order.get("kind") or "desk"),
                "price": None if order.get("price") is None else floor_at_zero(order.get("price")),
            }
        )
    return {
        "instrument": {
            "symbol": instrument.get("symbol"),
            "asset_class": instrument.get("asset_class"),
            "venue": instrument.get("venue"),
        },
        "side": row.get("side"),
        "quantity": floor_at_zero(row.get("quantity")),
        "entry_price": floor_at_zero(row.get("entry_price")),
        "mark_price": floor_at_zero(row.get("mark_price")),
        "market_value": floor_at_zero(row.get("market_value")),
        "unrealized_pnl": row.get("unrealized_pnl"),
        "opened_at": not_after(row.get("opened_at"), published_at) if published_at else row.get("opened_at"),
        # A desk writes inline math ("S<K"); the site refuses a raw "<" in prose.
        "thesis": sanitize_string(str(row.get("thesis") or ""))[:240],
        "intent_id": row.get("intent_id"),
        "session_id": row.get("session_id"),
        "target_price": None if row.get("target_price") is None else floor_at_zero(row.get("target_price")),
        "stop_price": None if row.get("stop_price") is None else floor_at_zero(row.get("stop_price")),
        "time_stop_at": row.get("time_stop_at"),
        "exit_orders": exits,
    }


def live_session_row(row: Mapping[str, Any], published_at: str | None = None) -> dict[str, Any]:
    return {
        "session_id": row.get("session_id"),
        "trigger": row.get("trigger"),
        "started_at": not_after(row.get("started_at"), published_at) if published_at else row.get("started_at"),
    }


def run_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """The contract's `run` block. Signed numbers stay signed; unknowns stay null."""
    def signed(value: Any) -> Any:
        if value is None:
            return None
        return value if isinstance(value, Decimal) else Decimal(str(value))

    return {
        "started_at": row.get("started_at"),
        "uptime_seconds": counted(row.get("uptime_seconds")),
        "availability_7d_pct": None if row.get("availability_7d_pct") is None else floor_at_zero(row.get("availability_7d_pct")),
        "sessions_total": counted(row.get("sessions_total")),
        "sessions_today": counted(row.get("sessions_today")),
        "decisions_total": counted(row.get("decisions_total")),
        "sail_model_spend_today_usd": floor_at_zero(row.get("sail_model_spend_today_usd")),
        "sail_model_spend_total_usd": floor_at_zero(row.get("sail_model_spend_total_usd")),
        "sail_infra_spend_total_usd": None if row.get("sail_infra_spend_total_usd") is None else floor_at_zero(row.get("sail_infra_spend_total_usd")),
        "sail_spend_total_usd": floor_at_zero(row.get("sail_spend_total_usd")),
        "pnl_total_usd": signed(row.get("pnl_total_usd")),
        "pnl_per_sail_dollar": signed(row.get("pnl_per_sail_dollar")),
        "models_used": [str(m)[:40] for m in list(row.get("models_used") or [])[:8]],
    }


def watch_row(row: Mapping[str, Any], published_at: str | None = None) -> dict[str, Any]:
    return {
        "triggers_today": counted(row.get("triggers_today")),
        "wakes_today": counted(row.get("wakes_today")),
        "last_trigger_at": not_after(row.get("last_trigger_at"), published_at) if published_at else row.get("last_trigger_at"),
        "cost_today_usd": floor_at_zero(row.get("cost_today_usd")),
    }
