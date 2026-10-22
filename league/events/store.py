"""The event lane's store: `events.sqlite` and the document files under one state root.

Records are appended and never rewritten; a row's `status` only moves forward. Times are ISO 8601 UTC strings ending in
`Z`; days are New York session dates (`YYYY-MM-DD`). Event ids: `8k:<accession>`, `f4:<accession>`, `news:<id>`.
Documents (the raw bytes a recorder fetched) live gzip-compressed at `<root>/docs/<sha[:2]>/<sha>.gz`, keyed by the
SHA-256 of the uncompressed bytes, so a verdict can cite exactly what it read.

The schema is pinned in goal-2026-10-19/EVL-DESIGN.md ("The store"); `SCHEMA_VERSION` moves with any change to it that
an older release could not read. A new table is additive (the older release never reads it, and a rollback opens the
store as before): PREREG-EVL-3's `bands`, `band_history` and `real_fills`, release 1019b's `eligibility` (below) and R3's
`births`, `birth_calls` and `birth_candidates` leave it at 1.

R3'S BIRTHS (goal-2026-10-19/R3-SPEC.md; league/events/births.py): `births` holds one row a REGISTERED birth, filled only
from the gateway's receipt of its registration (`POST /v1/github/docs` appending its canonical line to
`docs/births/<night>.jsonl` on main): the spec's canonical JSON and sha256, the commit, GitHub's commit time
(`committed_at`), the House's receipt of the answer (`received_at`) and the registration time, the later of the two
(`registered_at`: a birth counts only events knowable after it). Never rewritten. `birth_calls` keeps the architect's
one model call a night (its prompt sha, the facts' sha and the answer, as `verdicts` keeps a verdict); `birth_candidates`
every spec proposed a night with the validator's verdict (`accepted`, `refused`, `registered`, `unknown`) and its
outcome-free figures (its selection count over the last 20 sessions, the highest Jaccard and with whom).

ELIGIBILITY ONCE PER (ENTRY SESSION, CIK), BY THE RULE THAT MADE IT (release 1019b's second review; PREREG-EVL-1
section 2: a LIVE decision reads Alpaca's `status=active` and `tradable: true`, a BACKFILLED one `status=all` and the
previous session's closing-print exchange). `eligibility` keeps every result of the test, eligible (with its universe
row's symbol: the row's details are the `universe` row (day, symbol)) or not, with its `rule` ("live" or "backfill"),
one row a (day, cik, rule), written once (league/events/universe.py `record_result`; league/events/run.py
`eligibility` reads and writes it). A store from before the table is migrated when it is first opened (`_migrate`):
each universe row gets the result "eligible" under the rule of the decision that wrote it as the receipts tell it, the
first decision receipt of its entry session (`decide-open:<day>` or `decide-close:<day>`, the lowest id): "live" when
that run started within `LEGACY_LIVE_WITHIN` (10 minutes) of its scheduled time (09:15 ET, or the close less 14
minutes), as the House's lane and the CLI's `catchup` judge a run live, else "backfill" (no receipt: "backfill"); the
receipts do not say which of a session's runs wrote which row, so the first run's rule is every row's. BEFORE THAT,
the desktop's live refusals (amendment A67: meta `elig-no:<day>:<cik>` = "live", its hotfix's mark of a CIK the live
rule refused for that session) are kept as live results, ineligible (release 1019b's third review), so a re-decision
of either kind never admits such a CIK, and a universe row of it is not labelled. The sessions whose decisions ran
before the table kept no other ineligible result: meta `ELIGIBILITY_FROM` is the first entry session after the last
one with a decision receipt then, and league/events/universe.py `seen_live` reads a session before it that has no
markers.

THE PROBE SIZE'S RECORD (release 1019f, the audit's capacity and probe lenses): a real BUY's row in `real_fills` keeps
the dollars its band's target asked (`target_usd`: the band's `position_share` x E at the previous close, the House's
event book's own figure) and which constraint cut it below that (`binding`, one of league/events/bands.py `BINDINGS`,
NULL when none did), and the dollars its send asked (`sized_usd`: the shares sent x the limit, release 1019f's
integration), so a reader can tell a full Probe event from one that cash, the loss budget, a wall or the whole shares
cut. A sale's row, and every row written before the release, holds NULL in both. The two are NULLABLE COLUMNS,
additive like a new table (an older release names its columns and never reads them, so `SCHEMA_VERSION` stays 1):
the schema makes them in a new store, and `migrate_fills` adds them to a store from before them at every open
(`FILL_COLUMNS_DDL`; idempotent).
"""

from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping
from zoneinfo import ZoneInfo

SCHEMA_VERSION = 1
DB_NAME = "events.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS filings(accession TEXT PRIMARY KEY, form TEXT NOT NULL, cik TEXT NOT NULL, company TEXT,
  items TEXT, accepted_at TEXT NOT NULL, knowable_at TEXT NOT NULL, received_at TEXT NOT NULL, source TEXT NOT NULL,
  index_url TEXT, doc_url TEXT, doc_kind TEXT, text_sha TEXT, text_len INTEGER, raw_sha TEXT, status TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS filings_knowable ON filings(form, knowable_at);
CREATE INDEX IF NOT EXISTS filings_cik ON filings(cik, accepted_at);
CREATE TABLE IF NOT EXISTS documents(sha TEXT PRIMARY KEY, kind TEXT NOT NULL, bytes INTEGER NOT NULL,
  path TEXT NOT NULL, stored_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS form4_owners(accession TEXT NOT NULL, owner_cik TEXT NOT NULL, owner_name TEXT,
  is_director INTEGER, is_officer INTEGER, officer_title TEXT, is_ten_pct INTEGER, PRIMARY KEY(accession, owner_cik));
CREATE TABLE IF NOT EXISTS form4_tx(accession TEXT NOT NULL, seq INTEGER NOT NULL, security TEXT, tx_date TEXT,
  code TEXT, shares REAL, price REAL, acquired TEXT, owned_after REAL, PRIMARY KEY(accession, seq));
CREATE TABLE IF NOT EXISTS news(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT, received_at TEXT NOT NULL,
  knowable_at TEXT NOT NULL, source TEXT, headline TEXT, summary TEXT, symbols TEXT, live INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS news_knowable ON news(knowable_at);
CREATE TABLE IF NOT EXISTS sessions(day TEXT PRIMARY KEY, open_at TEXT NOT NULL, close_at TEXT NOT NULL,
  early INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS universe(day TEXT NOT NULL, symbol TEXT NOT NULL, cik TEXT NOT NULL, name TEXT, exchange TEXT,
  prev_close REAL, adv20 REAL, bench TEXT, sigma60 REAL, PRIMARY KEY(day, symbol));
CREATE INDEX IF NOT EXISTS universe_cik ON universe(day, cik);
CREATE TABLE IF NOT EXISTS cik_info(cik TEXT PRIMARY KEY, sic TEXT, periodic_form TEXT, periodic_at TEXT,
  operating INTEGER, checked_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS verdicts(event TEXT NOT NULL, prompt_sha TEXT NOT NULL, model TEXT NOT NULL, request_id TEXT,
  asked_at TEXT, answered_at TEXT, status TEXT NOT NULL, score INTEGER, guidance TEXT, answer TEXT, usd REAL,
  PRIMARY KEY(event, prompt_sha, model));
CREATE TABLE IF NOT EXISTS intents(program TEXT NOT NULL, version INTEGER NOT NULL, event TEXT NOT NULL,
  symbol TEXT NOT NULL, cik TEXT, decided_at TEXT NOT NULL, entry_day TEXT NOT NULL, entry_at TEXT NOT NULL,
  exit_day TEXT NOT NULL, exit_at TEXT NOT NULL, rank_key REAL, mode TEXT NOT NULL, status TEXT NOT NULL, why TEXT,
  PRIMARY KEY(program, version, event));
CREATE INDEX IF NOT EXISTS intents_entry ON intents(program, version, entry_day);
CREATE TABLE IF NOT EXISTS outcomes(program TEXT NOT NULL, version INTEGER NOT NULL, event TEXT NOT NULL, entry_px REAL,
  exit_px REAL, bench TEXT, bench_entry REAL, bench_exit REAL, cost_entry_bp REAL, cost_exit_bp REAL, r REAL, b REAL,
  a REAL, spread_entry_bp REAL, spread_exit_bp REAL, stress_r REAL, tradable INTEGER, settled_at TEXT NOT NULL,
  status TEXT NOT NULL, PRIMARY KEY(program, version, event));
CREATE TABLE IF NOT EXISTS looks(program TEXT NOT NULL, version INTEGER NOT NULL, k INTEGER NOT NULL, at TEXT NOT NULL,
  sessions INTEGER, n INTEGER, issuers INTEGER, blocks INTEGER, mean_a REAL, mean_r REAL, mean_a_tradable REAL,
  p REAL, alpha REAL, fp_check REAL, held INTEGER NOT NULL, passed INTEGER NOT NULL, why TEXT,
  PRIMARY KEY(program, version, k));
CREATE TABLE IF NOT EXISTS bars(symbol TEXT NOT NULL, day TEXT NOT NULL, adj TEXT NOT NULL, o REAL, h REAL, l REAL,
  c REAL, v REAL, fetched_at TEXT NOT NULL, PRIMARY KEY(symbol, day, adj));
CREATE TABLE IF NOT EXISTS marks(symbol TEXT NOT NULL, day TEXT NOT NULL, label TEXT NOT NULL, px REAL, t TEXT,
  source TEXT NOT NULL, fetched_at TEXT NOT NULL, PRIMARY KEY(symbol, day, label));
CREATE TABLE IF NOT EXISTS receipts(id INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT NOT NULL, started_at TEXT NOT NULL,
  finished_at TEXT, status TEXT, summary TEXT);
CREATE TABLE IF NOT EXISTS bands(program TEXT NOT NULL, version INTEGER NOT NULL, band TEXT NOT NULL, since TEXT NOT NULL,
  why TEXT, PRIMARY KEY(program, version));
CREATE TABLE IF NOT EXISTS band_history(id INTEGER PRIMARY KEY AUTOINCREMENT, program TEXT NOT NULL,
  version INTEGER NOT NULL, band TEXT NOT NULL, since TEXT NOT NULL, why TEXT, written_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS real_fills(program TEXT NOT NULL, version INTEGER NOT NULL, event TEXT NOT NULL,
  side TEXT NOT NULL, qty REAL NOT NULL, price REAL NOT NULL, fee REAL NOT NULL DEFAULT 0, filled_at TEXT NOT NULL,
  band TEXT NOT NULL, target_usd REAL, binding TEXT, sized_usd REAL, PRIMARY KEY(program, version, event, side));
CREATE TABLE IF NOT EXISTS eligibility(day TEXT NOT NULL, cik TEXT NOT NULL, rule TEXT NOT NULL, eligible INTEGER NOT NULL,
  symbol TEXT, decided_at TEXT NOT NULL, PRIMARY KEY(day, cik, rule));
CREATE TABLE IF NOT EXISTS births(id TEXT NOT NULL, version INTEGER NOT NULL, sha TEXT NOT NULL, spec TEXT NOT NULL,
  seatable INTEGER NOT NULL, registered_at TEXT NOT NULL, committed_at TEXT, received_at TEXT NOT NULL, path TEXT NOT NULL,
  commit_sha TEXT, seq INTEGER NOT NULL, line TEXT NOT NULL, why TEXT, by TEXT, night TEXT NOT NULL,
  PRIMARY KEY(id, version));
CREATE UNIQUE INDEX IF NOT EXISTS births_sha ON births(sha);
CREATE TABLE IF NOT EXISTS birth_calls(night TEXT NOT NULL, prompt_sha TEXT NOT NULL, model TEXT NOT NULL,
  request_id TEXT, asked_at TEXT, answered_at TEXT, status TEXT NOT NULL, user_sha TEXT, facts_sha TEXT, answer TEXT,
  usd REAL, PRIMARY KEY(night, prompt_sha, model));
CREATE TABLE IF NOT EXISTS birth_candidates(night TEXT NOT NULL, seq INTEGER NOT NULL, sha TEXT, id TEXT, spec TEXT,
  why TEXT, by TEXT, status TEXT NOT NULL, reasons TEXT, figures TEXT, line TEXT, at TEXT NOT NULL,
  PRIMARY KEY(night, seq));
"""

#: RELEASE 1019i'S ADDITIVE TABLE (made by `Store` beside `SCHEMA`, so `SCHEMA_VERSION` stays 1: an older release never
#: reads it, and a rollback opens the store as before): `score_parity` (PREREG-EVL-8's harness plan H1,
#: league/events/score.py `check_parity`), the batched score's parity night, one EQUALITY FLAG per sampled intent (1 when
#: the per-intent path settles it identically, else 0), never a value.
SCHEMA_1019I = """
CREATE TABLE IF NOT EXISTS score_parity(program TEXT NOT NULL, version INTEGER NOT NULL, event TEXT NOT NULL,
  night TEXT NOT NULL, equal INTEGER NOT NULL, checked_at TEXT NOT NULL, PRIMARY KEY(program, version, event));
"""

#: The two rules of PREREG-EVL-1 section 2 an eligibility result is made by (the `eligibility` table's `rule`).
LIVE_RULE = "live"
BACKFILL_RULE = "backfill"
#: meta: the first entry session whose every eligibility result is in `eligibility` (the module docstring).
ELIGIBILITY_FROM = "evl:eligibility:from"
#: A decision run this soon after its scheduled time was live (league/events/run.py LIVE_WITHIN, the House's lane and the
#: CLI's catchup take theirs from there).
LEGACY_LIVE_WITHIN = dt.timedelta(minutes=10)
#: meta `elig-no:<day>:<cik>` = "live": the desktop lane's mark of a CIK the live rule refused for entry session <day>
#: (amendment A67's hotfix, written there from Oct 19); the migration keeps each as a live refusal (`_migrate`).
MARKER_PREFIX = "elig-no:"
_NY = ZoneInfo("America/New_York")

#: The forward-only order of an intent's status (a `skipped:<why>` is terminal like `exited`).
INTENT_ORDER = {"planned": 0, "entered": 1, "exited": 2}

#: RELEASE 1019f: the nullable columns of `real_fills` a store from before them gains (`migrate_fills`), each by its
#: own statement: a buy's target dollars, the constraint that cut it and the dollars its send asked (the module
#: docstring).
FILL_COLUMNS_DDL = {"target_usd": "ALTER TABLE real_fills ADD COLUMN target_usd REAL",
                    "binding": "ALTER TABLE real_fills ADD COLUMN binding TEXT",
                    "sized_usd": "ALTER TABLE real_fills ADD COLUMN sized_usd REAL"}


def migrate_fills(db: sqlite3.Connection) -> list[str]:
    """`FILL_COLUMNS_DDL`'s columns added to the store's `real_fills` where it lacks them (PRAGMA table_info, read
    afresh): additive and idempotent; another process's first open adding one between the look and the ALTER is read
    as done ("duplicate column name"). Nothing when the store holds no `real_fills` table. Returns the columns added."""
    have = {str(r[1]) for r in db.execute("PRAGMA table_info(real_fills)")}
    if not have:
        return []
    added = []
    for column, ddl in FILL_COLUMNS_DDL.items():
        if column in have:
            continue
        try:
            db.execute(ddl)
            added.append(column)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
    return added


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(moment: dt.datetime) -> str:
    """ISO 8601 UTC with a `Z`, to the second (the store's one time format)."""
    if moment.tzinfo is None:
        raise ValueError("a naive datetime has no place in the store")
    return moment.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(text: str) -> dt.datetime:
    """The inverse of `iso` (also accepts an explicit offset)."""
    value = dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError(f"not an aware time: {text!r}")
    return value.astimezone(dt.timezone.utc)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Store:
    """One state root: `events.sqlite` plus `docs/`. Open it with `Store(root)`; close with `close()` or a `with`."""

    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "docs").mkdir(exist_ok=True)
        self.db = sqlite3.connect(str(self.root / DB_NAME), timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        self.db.executescript(SCHEMA_1019I)     # (release 1019i: `score_parity`, additive)
        have = self.meta("schema_version")
        if have is None:
            self.set_meta("schema_version", str(SCHEMA_VERSION))
        elif int(have) != SCHEMA_VERSION:
            raise RuntimeError(f"events.sqlite schema {have} is not this code's {SCHEMA_VERSION}")
        migrate_fills(self.db)      # (release 1019f: `real_fills.target_usd` and `binding` on a store from before them)
        if self.meta(ELIGIBILITY_FROM) is None:
            self._migrate()

    def _migrate(self) -> None:
        """The `eligibility` table on a store from before it (the module docstring): each universe row without a
        result gets "eligible" under its session's first decision's rule, once; then meta `ELIGIBILITY_FROM`."""
        with self.tx() as db:
            if db.execute("SELECT 1 FROM meta WHERE key=?", (ELIGIBILITY_FROM,)).fetchone() is not None:
                return
            # THE DESKTOP'S LIVE REFUSALS FIRST (amendment A67; release 1019b's third review): each meta
            # `elig-no:<day>:<cik>` = "live" is the live rule's refusal of that CIK for that entry session, kept as its
            # live result (ineligible), so no later decision of the session admits it under either rule; a universe row
            # of the same (day, cik) is then not labelled (the refusal stands: the reading that trades less).
            for row in db.execute("SELECT key FROM meta WHERE key LIKE ? AND value=?", (f"{MARKER_PREFIX}%", LIVE_RULE)
                                  ).fetchall():
                marked = _marker(str(row["key"]))
                if marked is not None:
                    db.execute("INSERT OR IGNORE INTO eligibility(day, cik, rule, eligible, symbol, decided_at) VALUES(?, ?, "
                               "?, 0, NULL, 'migrated')", (marked[0], marked[1], LIVE_RULE))
            rules: dict[str, str] = {}
            for row in db.execute("SELECT u.day, u.symbol, u.cik FROM universe u WHERE NOT EXISTS (SELECT 1 FROM "
                                  "eligibility e WHERE e.day=u.day AND e.cik=u.cik) ORDER BY u.day, u.cik, "
                                  "u.adv20 DESC").fetchall():
                day = str(row["day"])
                if day not in rules:
                    rules[day] = _legacy_rule(db, day)
                db.execute("INSERT OR IGNORE INTO eligibility(day, cik, rule, eligible, symbol, decided_at) VALUES(?, ?, ?, "
                           "1, ?, 'migrated')", (day, str(row["cik"]), rules[day], str(row["symbol"])))
            last = db.execute("SELECT MAX(substr(job, instr(job, ':') + 1)) FROM receipts WHERE job LIKE 'decide-open:%' "
                              "OR job LIKE 'decide-close:%'").fetchone()[0]
            since = (dt.date.fromisoformat(str(last)[:10]) + dt.timedelta(days=1)).isoformat() if last else "0001-01-01"
            db.execute("INSERT INTO meta(key, value) VALUES(?, ?)", (ELIGIBILITY_FROM, since))

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """One transaction (BEGIN IMMEDIATE ... COMMIT, rolled back on any exception)."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self.db
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")

    # -- meta -------------------------------------------------------------------------------------------------------
    def meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return None if row is None else str(row[0])

    def set_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, value))

    # -- documents --------------------------------------------------------------------------------------------------
    def put_document(self, data: bytes, kind: str, *, now: dt.datetime | None = None) -> str:
        """Store raw bytes once (idempotent); returns their SHA-256."""
        digest = sha256(data)
        rel = Path("docs") / digest[:2] / f"{digest}.gz"
        path = self.root / rel
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            with gzip.open(tmp, "wb") as out:
                out.write(data)
            os.replace(tmp, path)
        self.db.execute("INSERT OR IGNORE INTO documents(sha, kind, bytes, path, stored_at) VALUES(?, ?, ?, ?, ?)",
                        (digest, kind, len(data), str(rel), iso(now or utc_now())))
        return digest

    def get_document(self, digest: str) -> bytes:
        row = self.db.execute("SELECT path FROM documents WHERE sha=?", (digest,)).fetchone()
        if row is None:
            raise KeyError(digest)
        with gzip.open(self.root / row["path"], "rb") as src:
            data = src.read()
        if sha256(data) != digest:
            raise RuntimeError(f"document {digest} does not match its digest")
        return data

    # -- receipts ---------------------------------------------------------------------------------------------------
    def start_receipt(self, job: str, *, now: dt.datetime | None = None) -> int:
        cur = self.db.execute("INSERT INTO receipts(job, started_at, status) VALUES(?, ?, 'running')",
                              (job, iso(now or utc_now())))
        return int(cur.lastrowid)

    def finish_receipt(self, rid: int, status: str, summary: Mapping[str, Any] | None = None, *,
                       now: dt.datetime | None = None) -> None:
        self.db.execute("UPDATE receipts SET finished_at=?, status=?, summary=? WHERE id=?",
                        (iso(now or utc_now()), status, json.dumps(summary or {}, sort_keys=True, default=str), rid))

    # -- intents (forward-only status) ------------------------------------------------------------------------------
    def move_intent(self, program: str, version: int, event: str, status: str, why: str | None = None) -> bool:
        """Move an intent's status forward; a move backward or out of a terminal state is refused (False)."""
        row = self.db.execute("SELECT status FROM intents WHERE program=? AND version=? AND event=?",
                              (program, version, event)).fetchone()
        if row is None:
            raise KeyError((program, version, event))
        old = str(row["status"])
        if old.startswith("skipped") or old == "exited":
            return False
        if not status.startswith("skipped") and INTENT_ORDER.get(status, -1) <= INTENT_ORDER.get(old, -1):
            return False
        self.db.execute("UPDATE intents SET status=?, why=COALESCE(?, why) WHERE program=? AND version=? AND event=?",
                        (status, why, program, version, event))
        return True


def _marker(key: str) -> tuple[str, str] | None:
    """(day, cik) of a meta key `elig-no:<day>:<cik>`, or None when the key is not one (a day that is not a date)."""
    rest = key[len(MARKER_PREFIX):] if key.startswith(MARKER_PREFIX) else ""
    day, _, cik = rest.partition(":")
    try:
        dt.date.fromisoformat(day)
    except ValueError:
        return None
    return (day, cik) if cik else None


def has_markers(db: sqlite3.Connection, day: str) -> bool:
    """Whether entry session `day` has the desktop's live refusals (meta `elig-no:<day>:<cik>` = "live", A67): then
    they are that session's exact live refusals, both kinds, and the migration kept each (league/events/universe.py
    `seen_live` reads nothing more for it)."""
    return db.execute("SELECT 1 FROM meta WHERE key LIKE ? AND value=? LIMIT 1",
                      (f"{MARKER_PREFIX}{day}:%", LIVE_RULE)).fetchone() is not None


def _legacy_rule(db: sqlite3.Connection, day: str) -> str:
    """The rule a universe row of entry session `day` from before `eligibility` was made by (the module docstring):
    "live" when the session's first decision receipt started within LEGACY_LIVE_WITHIN of its scheduled time."""
    first = db.execute("SELECT job, started_at FROM receipts WHERE job IN (?, ?) ORDER BY id LIMIT 1",
                       (f"decide-open:{day}", f"decide-close:{day}")).fetchone()
    session = db.execute("SELECT close_at FROM sessions WHERE day=?", (day,)).fetchone()
    if first is None or session is None:
        return BACKFILL_RULE
    try:
        if str(first["job"]).startswith("decide-open:"):
            scheduled = dt.datetime.combine(dt.date.fromisoformat(day), dt.time(9, 15), tzinfo=_NY).astimezone(
                dt.timezone.utc)
        else:
            scheduled = parse_iso(session["close_at"]) - dt.timedelta(minutes=14)
        late = parse_iso(first["started_at"]) - scheduled
    except (TypeError, ValueError):
        return BACKFILL_RULE
    return LIVE_RULE if dt.timedelta(0) <= late <= LEGACY_LIVE_WITHIN else BACKFILL_RULE


__all__ = ["Store", "SCHEMA", "SCHEMA_VERSION", "iso", "parse_iso", "sha256", "utc_now", "INTENT_ORDER", "LIVE_RULE",
           "BACKFILL_RULE", "ELIGIBILITY_FROM", "LEGACY_LIVE_WITHIN", "MARKER_PREFIX", "has_markers", "FILL_COLUMNS_DDL",
           "migrate_fills", "SCHEMA_1019I"]
