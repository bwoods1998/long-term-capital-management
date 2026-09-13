"""Frozen Sail request accounting with durable intent and same-key recovery."""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
import hashlib
import json
import math
import re
import sqlite3
import time
import uuid
from .accounting import estimate_cost

# Official published rates captured 2026-09-13. USD / million tokens.
PROFILES = {
    "pro_flex": ("deepseek-ai/DeepSeek-V4-Pro-0813", "flex", "0.66", "0.022", "1.98"),
    "pro_asap": ("deepseek-ai/DeepSeek-V4-Pro-0813", "asap", "1.32", "0.044", "3.96"),
    "kimi_flex": ("moonshotai/Kimi-K2.6", "flex", "0.35", "0.10", "2.00"),
    "kimi_balanced": ("moonshotai/Kimi-K2.6", "balanced", "0.45", "0.20", "3.00"),
    "kimi_asap": ("moonshotai/Kimi-K2.6", "asap", "1.00", "0.20", "4.00"),
    "k3": ("moonshotai/Kimi-K3", "asap", "3.00", "0.30", "15.00"),
    "glm_flex": ("zai-org/GLM-5.3", "flex", "0.40", "0.08", "1.80"),
    "glm_balanced": ("zai-org/GLM-5.3", "balanced", "0.50", "0.12", "2.50"),
    "flash": ("deepseek-ai/DeepSeek-V4-Flash-0731", "asap", "0.09", "0.02", "0.18"),
}
MODEL_ALIASES = {
    "deepseek-ai/DeepSeek-V4-Pro-0813": "deepseek/deepseek-v4-pro-0813",
    "deepseek-ai/DeepSeek-V4-Flash-0731": "deepseek/deepseek-v4-flash-0731",
}
TERMINAL = {"completed", "failed", "cancelled", "incomplete"}


class AdmissionClosed(RuntimeError):
    pass


class SubmissionRejected(RuntimeError):
    """Explicit pre-admission provider rejection, with no accepted response."""
    def __init__(self, code):
        if code not in {"unsupported_asap_request"}:
            raise ValueError("Unrecognized rejection")
        self.code = code
        super().__init__(code)


class ClosingConnection(sqlite3.Connection):
    """Commit/rollback and close context-owned connections; long runs must not leak FDs."""

    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class Transport:
    def __init__(
        self, *, injected=False, key_fingerprint=None, headers=None, voyage_id=None
    ):
        self.injected = injected
        self.fingerprint = key_fingerprint
        self.headers = headers or {}
        self.voyage_id = voyage_id
        if voyage_id is not None and (
            not isinstance(voyage_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", voyage_id)
        ):
            raise ValueError("Invalid frozen Voyage identity")
        if any(
            k.lower() in ("authorization", "cookie", "proxy-authorization")
            for k in self.headers
        ):
            raise ValueError("Caller headers cannot carry credentials")
        if not isinstance(key_fingerprint, str) or not re.fullmatch(
            r"[0-9a-f]{64}", key_fingerprint
        ):
            raise ValueError("A frozen credential fingerprint is required")

    def __call__(self, method, route, body=None, request_id=None):
        if not (
            (route == "/v1/responses" and method == "POST")
            or (
                re.fullmatch(r"/v1/responses/resp_[A-Za-z0-9_-]+", route)
                and method == "GET"
            )
            or (route == "/v2/usage/summary" and method == "GET")
            or (
                self.voyage_id
                and route == "/v1/voyages/" + self.voyage_id + "/events"
                and method == "POST"
            )
        ):
            raise ValueError("Unexpected provider route")
        headers = {"Content-Type": "application/json", **self.headers}
        if not self.injected:
            from .credentials import load_api_key

            key = load_api_key()
            if (
                self.fingerprint
                and hashlib.sha256(key.encode()).hexdigest() != self.fingerprint
            ):
                raise ValueError("Credential identity changed")
            headers["Authorization"] = "Bearer " + key
        if request_id:
            headers["Idempotency-Key"] = request_id
        request = Request(
            "https://api.sailresearch.com" + route,
            data=json.dumps(body, sort_keys=True).encode()
            if body is not None
            else None,
            headers=headers,
            method=method,
        )
        try:
            # Foreground Responses wait for generation to finish. Match Sail's
            # bounded SDK default; background acknowledgements/GETs stay short.
            timeout = 600 if method == "POST" and route == "/v1/responses" and not (body or {}).get("background", False) else 45
            with build_opener(NoRedirect).open(request, timeout=timeout) as response:
                raw = response.read(8_000_001)
                if len(raw) > 8_000_000:
                    raise ValueError("Oversized provider response")
                return json.loads(raw)
        except HTTPError as error:
            # Never log provider bodies, credentials or arbitrary exception text.
            code = error.code
            rejected = None
            if code == 400 and method == "POST" and route == "/v1/responses":
                try:
                    detail = json.loads(error.read(32000)).get("error", {})
                    if detail.get("type") == "invalid_request_error" and detail.get("code") == "unsupported_asap_request":
                        rejected = detail["code"]
                except (ValueError, TypeError, AttributeError):
                    pass
            error.close()
            if rejected:
                raise SubmissionRejected(rejected) from None
            raise RuntimeError(f"provider_http_{code}") from None
        except TimeoutError:
            raise RuntimeError("provider_transport_timeout") from None
        except URLError as error:
            code = "provider_transport_timeout" if isinstance(error.reason, TimeoutError) else "provider_transport_unconfirmed"
            raise RuntimeError(code) from None
        except Exception:
            raise RuntimeError("provider_transport_unconfirmed") from None


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def output_text(response):
    if not isinstance(response, dict) or not isinstance(response.get("output"), list):
        return ""
    parts = []
    for item in response["output"]:
        if (
            not isinstance(item, dict)
            or item.get("type") != "message"
            or not isinstance(item.get("content"), list)
        ):
            continue
        for content in item["content"]:
            if (
                isinstance(content, dict)
                and content.get("type") == "output_text"
                and isinstance(content.get("text"), str)
            ):
                parts.append(content["text"])
    return "\n".join(parts)


def answer_json(response):
    text = output_text(response).strip()
    if len(text) > 200000:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate result key")
            result[key] = value
        return result

    try:
        return json.loads(
            text,
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (ValueError, TypeError, RecursionError):
        return None


def body_for(
    profile, prefix, question, *, max_output=8192, cache="ordinary", cache_key=None
):
    model, window, *_ = PROFILES[profile]
    if not 16 <= max_output <= 32768 or cache not in ("ordinary", "write", "read"):
        raise ValueError("Invalid request limits")
    metadata = {"completion_window": window}
    if cache == "write":
        metadata["supercache_write"] = "24h"
    body = {
        "model": model,
        "input": [
            {"role": "system", "content": prefix},
            {"role": "user", "content": question},
        ],
        "reasoning": {"effort": "medium"},
        "max_output_tokens": max_output,
        "background": window != "asap",
        "metadata": metadata,
    }
    if cache_key:
        body["prompt_cache_key"] = cache_key
    return body


class Client:
    def __init__(self, path, config, *, transport=None, clock=time.time):
        config = json.loads(canonical(config))
        budget = Decimal(str(config["inference_budget_usd"]))
        mode = config.get("spending_mode", "capped")
        if mode not in ("capped", "available_credit"):
            raise ValueError("Unknown spending authority")
        if not budget.is_finite() or budget <= 0 or (mode == "capped" and budget > 100):
            raise ValueError("Invalid frozen inference allowance")
        if (
            any(
                type(config[k]) not in (int, float) or not math.isfinite(config[k])
                for k in ("started_epoch", "ends_epoch")
            )
            or config["ends_epoch"] <= config["started_epoch"]
        ):
            raise ValueError("Invalid run window")
        if (
            type(config.get("drain_seconds", 300)) is not int
            or not 0
            <= config.get("drain_seconds", 300)
            < config["ends_epoch"] - config["started_epoch"]
        ):
            raise ValueError("Invalid drain window")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.config = config
        self.clock = clock
        self.transport = transport or Transport(
            injected=config.get("injected_auth", False),
            key_fingerprint=config.get("key_fingerprint"),
            headers=config.get("voyage_headers"),
        )
        db = self.connect()
        db.executescript("""CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY,task_id TEXT UNIQUE NOT NULL,profile TEXT NOT NULL,body TEXT NOT NULL,reserved TEXT NOT NULL,cost TEXT,response_id TEXT,response TEXT,status TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,error TEXT,cache TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS allocations (id TEXT PRIMARY KEY,reserved TEXT NOT NULL,cost TEXT,receipt TEXT);
""")
        frozen = {
            k: config[k]
            for k in (
                "run_id",
                "inference_budget_usd",
                "started_epoch",
                "ends_epoch",
                "key_fingerprint",
            )
        }
        frozen.update(
            {
                k: config.get(k)
                for k in (
                    "injected_auth",
                    "drain_seconds",
                    "research_only",
                    "assigned_task_ids",
                )
            }
        )
        if "spending_mode" in config:
            frozen["spending_mode"] = config["spending_mode"]
        with db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT value FROM metadata WHERE key='contract'"
            ).fetchone()
            if existing and existing[0] != canonical(frozen):
                raise ValueError("Frozen provider contract changed")
            db.execute(
                "INSERT OR IGNORE INTO metadata VALUES ('contract',?)",
                (canonical(frozen),),
            )
            db.execute(
                "INSERT OR IGNORE INTO metadata VALUES ('profiles',?)",
                (canonical(PROFILES),),
            )
            self.profiles = json.loads(
                db.execute(
                    "SELECT value FROM metadata WHERE key='profiles'"
                ).fetchone()[0]
            )
        db = self.connect()
        db.executescript("""
CREATE TRIGGER IF NOT EXISTS metadata_frozen_update BEFORE UPDATE ON metadata WHEN OLD.key IN ('contract','profiles') BEGIN SELECT RAISE(ABORT,'immutable provider contract'); END;
CREATE TRIGGER IF NOT EXISTS metadata_frozen_delete BEFORE DELETE ON metadata WHEN OLD.key IN ('contract','profiles') BEGIN SELECT RAISE(ABORT,'immutable provider contract'); END;
CREATE TRIGGER IF NOT EXISTS request_identity_immutable BEFORE UPDATE OF id,task_id,profile,body,reserved,created,cache ON requests BEGIN SELECT RAISE(ABORT,'immutable request intent'); END;
CREATE TRIGGER IF NOT EXISTS request_no_delete BEFORE DELETE ON requests BEGIN SELECT RAISE(ABORT,'immutable request history'); END;
CREATE TRIGGER IF NOT EXISTS response_identity_immutable BEFORE UPDATE OF response_id ON requests WHEN OLD.response_id IS NOT NULL AND NEW.response_id IS NOT OLD.response_id BEGIN SELECT RAISE(ABORT,'immutable accepted response'); END;
CREATE TRIGGER IF NOT EXISTS terminal_immutable BEFORE UPDATE ON requests WHEN OLD.status IN ('completed','incomplete','failed','cancelled') BEGIN SELECT RAISE(ABORT,'immutable terminal response'); END;
CREATE TRIGGER IF NOT EXISTS allocation_identity_immutable BEFORE UPDATE OF id,reserved ON allocations BEGIN SELECT RAISE(ABORT,'immutable branch reservation'); END;
CREATE TRIGGER IF NOT EXISTS allocation_no_delete BEFORE DELETE ON allocations BEGIN SELECT RAISE(ABORT,'immutable branch reservation'); END;
CREATE TRIGGER IF NOT EXISTS allocation_receipt_immutable BEFORE UPDATE ON allocations WHEN OLD.receipt IS NOT NULL BEGIN SELECT RAISE(ABORT,'immutable branch settlement'); END;
""")
        db.close()
        self.path.chmod(0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30, factory=ClosingConnection)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def totals(self, db=None):
        own = db is None
        db = db or self.connect()
        rows = db.execute("SELECT reserved,cost,status FROM requests").fetchall()
        alloc = db.execute("SELECT reserved,cost FROM allocations").fetchall()
        result = {
            "known_cost_usd": format(
                sum(
                    (
                        Decimal(r["cost"])
                        for r in [*rows, *alloc]
                        if r["cost"] is not None
                    ),
                    Decimal(0),
                ),
                "f",
            ),
            "committed_usd": format(
                sum(
                    (
                        Decimal(r["cost"] if r["cost"] is not None else r["reserved"])
                        for r in [*rows, *alloc]
                    ),
                    Decimal(0),
                ),
                "f",
            ),
            "unsettled_allocations": sum(r["cost"] is None for r in alloc),
            "branch_committed_usd": format(
                sum(
                    (
                        Decimal(r["cost"] if r["cost"] is not None else r["reserved"])
                        for r in alloc
                    ),
                    Decimal(0),
                ),
                "f",
            ),
            "unsettled_requests": sum(r["cost"] is None for r in rows),
            "requests": len(rows),
            "completed": sum(r["status"] == "completed" for r in rows),
        }
        if own:
            db.close()
        return result

    def allowance(self, at=None):
        at = self.clock() if at is None else at
        c = self.config
        if c.get("spending_mode") == "available_credit":
            # The frozen snapshot is an audit receipt, not an hourly cap.
            # Every reservation and first dispatch requires live authority.
            return None
        fraction = max(
            Decimal(0),
            min(
                Decimal(1),
                (Decimal(str(at)) - Decimal(str(c["started_epoch"])))
                / (Decimal(str(c["ends_epoch"])) - Decimal(str(c["started_epoch"]))),
            ),
        )
        # A rolling allowance leaves most spending capacity available for later evidence.
        return Decimal(c["inference_budget_usd"]) * min(
            Decimal(1), Decimal(".15") + Decimal(".85") * fraction
        )

    def allocate(self, identity, amount):
        amount = Decimal(amount)
        if not amount.is_finite() or amount <= 0:
            raise ValueError("Allocation must be positive")
        if not isinstance(identity, str) or not 1 <= len(identity) <= 200:
            raise ValueError("Invalid allocation identity")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT reserved FROM allocations WHERE id=?", (identity,)
            ).fetchone()
            if old:
                if Decimal(old[0]) != amount:
                    raise ValueError("Allocation changed")
                return
            self._admission_open(db)
            allowance = self.allowance()
            if allowance is not None and Decimal(self.totals(db)["committed_usd"]) + amount > allowance:
                raise AdmissionClosed("Run budget unavailable")
            if self.config.get("spending_mode") == "available_credit":
                guard = getattr(self, "reservation_guard", None)
                if guard is None or guard(amount) is not True:
                    raise AdmissionClosed("External spending authority unavailable")
            db.execute(
                "INSERT INTO allocations(id,reserved) VALUES (?,?)",
                (identity, str(amount)),
            )

    def _admission_open(self, db):
        at = self.clock()
        if at < self.config["started_epoch"] or at >= self.config[
            "ends_epoch"
        ] - self.config.get("drain_seconds", 300):
            raise AdmissionClosed("Admission window closed")
        if db.execute(
            "SELECT 1 FROM requests WHERE error='cost_exceeds_reservation' LIMIT 1"
        ).fetchone():
            raise AdmissionClosed("Observed cost exceeded its conservative hold")

    def submit_intent(self, task_id, profile, body, *, cache="ordinary"):
        if not isinstance(task_id, str) or not 1 <= len(task_id) <= 200:
            raise ValueError("Invalid task identity")
        if self.config.get("research_only") and task_id not in self.config.get(
            "assigned_task_ids", []
        ):
            raise ValueError("Task outside frozen branch assignment")
        if profile not in self.profiles or cache not in ("ordinary", "write", "read"):
            raise ValueError("Unknown frozen request profile")
        try:
            if set(body) - {
                "model",
                "input",
                "max_output_tokens",
                "background",
                "metadata",
                "prompt_cache_key",
                "reasoning",
            }:
                raise ValueError("Unreserved request fields")
            if body["model"] != self.profiles[profile][0] or body["metadata"] != {
                "completion_window": self.profiles[profile][1],
                **({"supercache_write": "24h"} if cache == "write" else {}),
            }:
                raise ValueError("Request differs from frozen profile")
            if body.get("reasoning") != {"effort": "medium"}:
                raise ValueError("Unfrozen reasoning effort")
            if body["background"] is not (self.profiles[profile][1] != "asap"):
                raise ValueError("Unsupported completion mode")
            if (
                type(body["max_output_tokens"]) is not int
                or not 16 <= body["max_output_tokens"] <= 32768
            ):
                raise ValueError("Invalid output ceiling")
            if not isinstance(body["input"], list) or not 1 <= len(body["input"]) <= 4:
                raise ValueError("Invalid input messages")
            if any(
                not isinstance(v, dict)
                or set(v) != {"role", "content"}
                or v["role"] not in ("system", "user")
                or not isinstance(v["content"], str)
                for v in body["input"]
            ):
                raise ValueError("Only plain frozen text messages are admitted")
            if len(canonical(body).encode()) > 500000:
                raise ValueError("Request exceeds bounded input envelope")
            if "prompt_cache_key" in body and (
                not isinstance(body["prompt_cache_key"], str)
                or not 1 <= len(body["prompt_cache_key"]) <= 128
            ):
                raise ValueError("Invalid cache identity")
        except (KeyError, TypeError):
            raise ValueError("Malformed request envelope") from None
        encoded = canonical(body)
        rates = self.profiles[profile][2:]
        # UTF-8 byte bound is deliberately conservative; includes framing/token overhead.
        input_bound = sum(len(v["content"].encode()) for v in body["input"]) + 4096
        reserve = (
            Decimal(input_bound) * Decimal(rates[0]) * (100 if cache == "write" else 1)
            + Decimal(body["max_output_tokens"]) * Decimal(rates[2])
        ) / 1_000_000
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT * FROM requests WHERE task_id=?", (task_id,)
            ).fetchone()
            if old:
                if (
                    old["body"] != encoded
                    or old["profile"] != profile
                    or old["cache"] != cache
                ):
                    raise ValueError("Immutable request intent changed")
                return old["id"]
            at = self.clock()
            self._admission_open(db)
            allowance = self.allowance(at)
            if allowance is not None and Decimal(self.totals(db)["committed_usd"]) + reserve > allowance:
                raise AdmissionClosed("Paced allowance unavailable")
            guard = getattr(self, "reservation_guard", None)
            if (self.config.get("spending_mode") == "available_credit" and guard is None) or (guard is not None and guard(reserve) is not True):
                raise AdmissionClosed("External spending authority unavailable")
            identity = "pa-" + str(uuid.uuid4())
            db.execute(
                "INSERT INTO requests(id,task_id,profile,body,reserved,status,created,updated,cache) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    identity,
                    task_id,
                    profile,
                    encoded,
                    str(reserve),
                    "prepared",
                    at,
                    at,
                    cache,
                ),
            )
            return identity

    def step(self, identity):
        # The coordinator owns dispatch; recovery serializes each ID with a file lock.
        import fcntl

        if not isinstance(identity, str) or not re.fullmatch(
            r"pa-[0-9a-f-]{36}", identity
        ):
            raise ValueError("Invalid durable request identity")
        lockpath = self.path.parent / (identity + ".lock")
        with lockpath.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with self.connect() as db:
                found = db.execute(
                    "SELECT * FROM requests WHERE id=?", (identity,)
                ).fetchone()
                if found is None:
                    raise ValueError("Unknown durable request identity")
                row = dict(found)
            if row["status"] in TERMINAL:
                return row
            if (
                not row["response_id"]
                and row["attempts"] == 0
                and self.clock()
                >= self.config["ends_epoch"] - self.config.get("drain_seconds", 300)
            ):
                with self.connect() as db:
                    db.execute("UPDATE requests SET status='cancelled',cost='0',updated=?,error='never_dispatched_before_deadline' WHERE id=? AND response_id IS NULL AND attempts=0",
                               (self.clock(), identity))
                    return dict(db.execute("SELECT * FROM requests WHERE id=?", (identity,)).fetchone())
            if self.config.get("spending_mode") == "available_credit" and not row["response_id"] and row["attempts"] == 0:
                # A crash may separate reservation from the first paid POST.
                # This existing hold already counts toward global commitments;
                # recheck authority without reserving or counting it twice.
                guard = getattr(self, "reservation_guard", None)
                if guard is None or guard(Decimal(0)) is not True:
                    return row
            if not row["response_id"] and (
                self.clock() - row["created"] > 23 * 3600 or row["attempts"] >= 10
            ):
                return row
            with self.connect() as db:
                db.execute(
                    "UPDATE requests SET attempts=attempts+1,updated=? WHERE id=?",
                    (self.clock(), identity),
                )
            try:
                response = (
                    self.transport("GET", "/v1/responses/" + row["response_id"])
                    if row["response_id"]
                    else self.transport(
                        "POST", "/v1/responses", json.loads(row["body"]), identity
                    )
                )
                rid = response.get("id")
                status = response.get("status")
                if (
                    not isinstance(rid, str)
                    or not re.fullmatch(r"resp_[A-Za-z0-9_-]+", rid)
                    or status not in TERMINAL | {"queued", "in_progress"}
                ):
                    raise ValueError("Unconfirmed provider state")
                if row["response_id"] and rid != row["response_id"]:
                    raise ValueError("Response identity changed")
                # Save a valid accepted ID before any model/usage validation can park it.
                with self.connect() as db:
                    db.execute(
                        "UPDATE requests SET response_id=? WHERE id=?", (rid, identity)
                    )
                expected = self.profiles[row["profile"]][0]
                if response.get("model") not in {
                    expected,
                    MODEL_ALIASES.get(expected, expected),
                }:
                    raise ValueError("Response model changed")
                cost = None
                error = None
                if status in TERMINAL:
                    try:
                        rates = dict(
                            zip(
                                ("input", "cached", "output"),
                                self.profiles[row["profile"]][2:],
                            )
                        )
                        contract = {"write": "write-24h-v1", "read": "read-24h-v1"}.get(
                            row["cache"]
                        )
                        cost = str(
                            estimate_cost(
                                response.get("usage"),
                                rates,
                                response.get("metadata"),
                                supercache_contract=contract,
                            )
                        )
                        if Decimal(cost) > Decimal(row["reserved"]):
                            error = "cost_exceeds_reservation"
                    except (ValueError, TypeError, KeyError):
                        error = "terminal_usage_unsettled"
                with self.connect() as db:
                    db.execute(
                        "UPDATE requests SET response_id=?,response=?,status=?,cost=?,updated=?,error=? WHERE id=?",
                        (
                            rid,
                            canonical(response),
                            status,
                            cost,
                            self.clock(),
                            error,
                            identity,
                        ),
                    )
            except Exception as error:
                if isinstance(error, SubmissionRejected) and not row["response_id"]:
                    with self.connect() as db:
                        db.execute("UPDATE requests SET status='failed',cost='0',updated=?,error=? WHERE id=? AND response_id IS NULL",
                                   (self.clock(), error.code, identity))
                    with self.connect() as db:
                        return dict(db.execute("SELECT * FROM requests WHERE id=?", (identity,)).fetchone())
                category = (
                    str(error)
                    if re.fullmatch(
                        r"provider_http_\d{3}|provider_transport_(?:unconfirmed|timeout)",
                        str(error),
                    )
                    else type(error).__name__
                )
                with self.connect() as db:
                    db.execute(
                        "UPDATE requests SET error=?,updated=? WHERE id=?",
                        (category, self.clock(), identity),
                    )
            with self.connect() as db:
                return dict(
                    db.execute(
                        "SELECT * FROM requests WHERE id=?", (identity,)
                    ).fetchone()
                )

    def rows(self):
        """Compatibility view; runtime scheduling uses compact observations instead."""
        return list(self.iter_rows())

    def iter_rows(self):
        """Stream exact durable intents for recovery without retaining all prompts."""
        with self.connect() as db:
            for row in db.execute("SELECT * FROM requests ORDER BY created"):
                yield dict(row)

    def observations(self):
        """Scheduling/accounting view excluding frozen prompts and model output."""
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute("""
SELECT id,task_id,profile,reserved,cost,response_id,status,created,updated,
       attempts,error,cache,
       CASE WHEN json_valid(response) THEN json_object(
         'usage',json_extract(response,'$.usage'),
         'metadata',json_extract(response,'$.metadata'))
       ELSE NULL END AS response
FROM requests ORDER BY created""")
            ]
