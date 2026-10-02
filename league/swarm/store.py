"""The swarm's store: one SQLite file in the state root, and the programs beside it.

    <root>/swarm.sqlite            families, versions, runs, notebooks, graveyard, looks, forward,
                                   events, spend, boxes, conversations, key-values
    <root>/programs/<family>/      v<n>-<sha12>.py (and .json: its PARAMS overrides), one per version
                                   (a sweep's variants share one .py: `add_versions`)
    <root>/swarm-runs/<id>.json.gz every Gym result in full (trades and daily series: licensed-data
                                   derivatives, so never in git and never on the site)

Nothing here is ever committed: the repository is public and programs are fitted to licensed data.

TRIALS. Every Gym evaluation is a trial (`add_run` counts the result's own `trials`), per family and in
total. An evaluation the family already made (its `eval_key` on a completed Train run: `evaluated`) is never asked of
the Gym again: the researcher answers it from here, so it is no trial (R3, `researcher.py`'s NO DUPLICATE RUNS). A
family's LINEAGE trial count is the sum over every family of its lineage (ancestors, siblings, descendants, alive or
retired) and over any lineage its root was born on the slice of (`prior_lineage`: an
architect's new idea on a dead family's slice): `lineage_trials`, the same set `lineage_trial_sharpes` reads. Since the
owner's decision D2 (Sept 26) the deflated Sharpe's N is that set's VALIDATED versions (`lineage_validated`), not its trials.
Holdout LOOKS are a ration, counted live across the whole connected lineage (`lineage_looks`), including
ancestors, siblings and descendants on every root, before or after a fork. Reusing identical program code
on the same structure and roots connects lineages permanently; changing a label or parameters cannot buy
new looks (a `long_single` and the `long_call` or `long_put` it sends are one structure here: `same_slice`, so
relabeling a single-option program two-sided buys none either). A `long_single` that continues a call or put twin
also joins the other twin's lineage (`link_lineages`, the architect's `admit`), so merging a twin pair buys no trials or
looks; and a new lineage on a singles' slice counts the newest dead lineage of each type there (`slice_priors`). Each
look once. Nothing ever lowers a count.

EVENTS. `event(kind, family, payload)` appends a row the House mirrors into its ledger (`hook.py`),
all of kind `swarm.*`: the public ones the site's tape reads (`swarm.born`, `swarm.retired`, `swarm.band`,
`swarm.note`) and private ones (cycles, tournaments, the gate, the pool, the guard). Never the House's own
`agent.*` or `eval.*` kinds: its roster and evaluator read those. The table is append-only.

One connection under one lock, WAL, so the House can read (and write the forward records of shadow and
real trades, `add_forward`) from its own process. Standard library only.
"""

from __future__ import annotations

import gzip
from contextlib import contextmanager
import hashlib
import json
import math
import re
import sqlite3
import threading
import time
import zlib
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import DB_NAME, PROGRAMS_DIR, RUNS_DIR
from .evidence import drift_numbers

SCHEMA = """
CREATE TABLE IF NOT EXISTS families (
    id TEXT PRIMARY KEY,
    lineage TEXT NOT NULL,
    parent TEXT,
    origin TEXT NOT NULL,
    mechanism TEXT NOT NULL,
    structure TEXT NOT NULL,
    roots TEXT NOT NULL,
    spec TEXT NOT NULL,
    born_at TEXT NOT NULL,
    retired_at TEXT,
    retire_reason TEXT,
    band TEXT NOT NULL DEFAULT 'gym',
    band_since TEXT,
    best_version INTEGER,
    best_train REAL,
    validated_version INTEGER,
    best_validation REAL,
    trials INTEGER NOT NULL DEFAULT 0,
    inherited_trials INTEGER NOT NULL DEFAULT 0,
    inherited_looks INTEGER NOT NULL DEFAULT 0,
    revisions INTEGER NOT NULL DEFAULT 0,
    cycles INTEGER NOT NULL DEFAULT 0,
    stall INTEGER NOT NULL DEFAULT 0,
    rewrites INTEGER NOT NULL DEFAULT 0,
    since_val_revisions INTEGER NOT NULL DEFAULT 0,
    since_val_trials INTEGER NOT NULL DEFAULT 0,
    validations INTEGER NOT NULL DEFAULT 0,
    weight REAL,
    spent_usd REAL NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS versions (
    family TEXT NOT NULL,
    n INTEGER NOT NULL,
    sha TEXT NOT NULL,
    params TEXT NOT NULL,
    path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    author TEXT NOT NULL,
    note TEXT,
    PRIMARY KEY (family, n)
);
CREATE INDEX IF NOT EXISTS versions_sha ON versions(sha);
CREATE TABLE IF NOT EXISTS lineage_links (
    a TEXT NOT NULL,
    b TEXT NOT NULL,
    PRIMARY KEY (a, b)
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    family TEXT NOT NULL,
    version INTEGER,
    window TEXT NOT NULL,
    stress REAL NOT NULL,
    purpose TEXT NOT NULL,
    at TEXT NOT NULL,
    status TEXT NOT NULL,
    trials INTEGER NOT NULL,
    program_years REAL NOT NULL DEFAULT 0,
    summary TEXT,
    path TEXT
);
CREATE INDEX IF NOT EXISTS runs_family ON runs(family, at);
CREATE TABLE IF NOT EXISTS notebook (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    family TEXT NOT NULL,
    at TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS notebook_family ON notebook(family, seq);
CREATE TABLE IF NOT EXISTS graveyard (
    family TEXT PRIMARY KEY,
    at TEXT NOT NULL,
    mechanism TEXT NOT NULL,
    structure TEXT NOT NULL,
    roots TEXT NOT NULL,
    lesson TEXT NOT NULL,
    best TEXT
);
CREATE TABLE IF NOT EXISTS looks (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    family TEXT NOT NULL,
    lineage TEXT NOT NULL,
    version INTEGER NOT NULL,
    run_sha TEXT NOT NULL UNIQUE,
    at TEXT NOT NULL,
    passed INTEGER NOT NULL,
    p_value REAL,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS refusals (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    family TEXT NOT NULL,
    version INTEGER,
    at TEXT NOT NULL,
    stage TEXT NOT NULL,
    reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS look_holds (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    family TEXT NOT NULL,
    version INTEGER,
    run_sha TEXT NOT NULL,
    at TEXT NOT NULL,
    stage TEXT NOT NULL,
    reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS forward (
    family TEXT NOT NULL,
    source TEXT NOT NULL,
    trade_id TEXT NOT NULL,
    day TEXT NOT NULL,
    pnl REAL NOT NULL,
    max_loss REAL NOT NULL,
    at TEXT NOT NULL,
    version INTEGER,
    PRIMARY KEY (family, source, trade_id)
);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    family TEXT,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_kind ON events(kind, at);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
    BEGIN SELECT RAISE(ABORT, 'swarm events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
    BEGIN SELECT RAISE(ABORT, 'swarm events are append-only'); END;
CREATE TABLE IF NOT EXISTS spend (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    epoch REAL NOT NULL,
    kind TEXT NOT NULL,
    family TEXT,
    usd REAL NOT NULL,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS spend_kind ON spend(kind, epoch);
CREATE TABLE IF NOT EXISTS model_costs (
    request_key TEXT PRIMARY KEY,
    booked_usd REAL NOT NULL,
    settled INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS boxes (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    version TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used REAL NOT NULL,
    busy_seconds REAL NOT NULL DEFAULT 0,
    jobs INTEGER NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS convo (
    family TEXT PRIMARY KEY,
    items TEXT NOT NULL,
    pending TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

ALIVE = ("gym", "candidate", "probe", "sized")
BANDS = ("gym", "candidate", "probe", "sized", "retired")
STRUCTURES = ("long_call", "long_put", "long_single", "debit_vertical", "credit_vertical", "iron_condor", "iron_butterfly",
              "long_butterfly", "long_straddle", "long_strangle", "calendar", "diagonal")
#: The two-sided single-option family (Sept 29, 2026): ONE program whose every open is one long call or one long put (one
#: leg, long), the side chosen by its rule, in place of a call/put twin pair (two one-sided families that each carried the
#: market's drift and doubled the births). It is only as drift-neutral as its side rule: the drift screen charges whatever
#: net exposure it holds, as for any family. It is a family's DECLARED structure only: each of its orders carries its own
#: type (`league.live.money.order_types`), and the money table, the real book and the gateway check that type as for any
#: other family; the live path also refuses a real open of any other type from it (`money.DECLARED_TYPES`).
LONG_SINGLE = "long_single"
SINGLE_SIDES = ("long_call", "long_put")
#: The five types that close in one order (the venue refuses one-order closes of the others).
CLOSEABLE = ("debit_vertical", "credit_vertical", "iron_condor", "iron_butterfly", "long_butterfly")
_SLUG = re.compile(r"^[a-z0-9-]{1,40}$")


def iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def same_slice(a: Any, b: Any) -> bool:
    """Whether families that declared structures `a` and `b` search the same slice: the same type, or a `long_single` and
    a single it sends (its programs cover theirs, so its lineage matching and trial counts must see them)."""
    return a == b or (LONG_SINGLE in (a, b) and {a, b} <= {LONG_SINGLE, *SINGLE_SIDES})


def slice_priors(dead: Sequence[Mapping[str, Any]], structure: Any) -> list[str]:
    """The prior lineages of a new lineage born on a dead slice (`add_family`'s `prior_lineage`): the newest dead lineage
    of EACH declared type on the slice, the proposal's own type first, then the others newest first. `dead` is the slice's
    dead families (`same_slice`), oldest first. For every structure but the three singles the slice holds one type, so this
    is `[dead[-1]["lineage"]]` exactly, as before; a single's slice holds up to three, and following one chain would drop
    the others (review of #425: a new long_call after a dead long_single missed the dead long_call before it)."""
    newest: dict[str, str] = {}
    for f in dead:
        newest[str(f["structure"])] = str(f["lineage"])
    types = [str(structure)] + [str(f["structure"]) for f in reversed(dead)]
    return list(dict.fromkeys(newest[t] for t in types if t in newest))


def priors_of(spec: Any) -> list[str]:
    """The lineages a family's root was born on the slice of: `prior_lineage` (the first, and the only one a store before
    #425 wrote), then any others in `prior_lineages` (`slice_priors`)."""
    if not isinstance(spec, Mapping):
        return []
    many = spec.get("prior_lineages")
    out = [str(x) for x in many if x] if isinstance(many, list) else []
    one = spec.get("prior_lineage")
    if one and str(one) not in out:
        out.insert(0, str(one))
    return list(dict.fromkeys(out))


def structure_text(structure: Any) -> str:
    """A declared structure in a model's words: its name, and for `long_single` what its orders are. Every other type is
    its name exactly (so no other family's prompt changes)."""
    if structure == LONG_SINGLE:
        return ("long_single (ONE program that buys calls or puts by its rule: every open is one long_call or one long_put, "
                "one leg, long, and names that type, never \"long_single\"; state the side rule and why its calls and puts "
                "balance: the drift screen charges whatever net exposure it holds)")
    return str(structure)


def structure_query(structure: Any) -> str:
    """A graveyard query's structure words: a `long_single` reads the lessons of the singles it sends too."""
    return " ".join((LONG_SINGLE, *SINGLE_SIDES)) if structure == LONG_SINGLE else str(structure)


def slugify(text: Any, *, limit: int = 36) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    out = re.sub(r"-{2,}", "-", out)[:limit].strip("-")
    return out or "family"


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def loads(text: Any, default: Any = None) -> Any:
    if text is None or text == "":
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


# BM25's standard constants for ranking the graveyard. K1: how fast repeats of a word saturate (a word said many
# times counts at most 2.2 times one mention). B: how much a row's length against the average discounts it (0 none,
# 1 in full proportion). The raw occurrence count they replace let the longest quarter of the graveyard take 447 of
# the architect's 450 top-3 slots in the Sept 28 replay.
GRAVEYARD_K1, GRAVEYARD_B = 1.2, 0.75


def graveyard_words(query: str) -> list[str]:
    """A graveyard query's distinct words longer than two letters, plus each underscore compound whole (`long_call`
    as itself as well as `long` and `call`), so a structure's name counts as one specific word. A compound is kept
    only beside a part long enough to count, so it never admits a row its parts would not."""
    q = str(query or "").lower()
    compounds = [c.strip("_") for c in re.findall(r"[a-z0-9_]+", q)]
    compounds = [c for c in compounds if "_" in c and any(len(p) > 2 for p in c.split("_"))]
    return sorted({w for w in re.findall(r"[a-z0-9]+", q) + compounds if len(w) > 2})


def rank_graveyard(rows: Sequence[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Graveyard rows (newest first) ranked by relevance to `query`; with no query words, all of them as given.

    A row's text is its mechanism, structure, roots and lesson; a query word is in it as a substring. Relevance is
    BM25: each query word the row contains is weighted by its inverse document frequency across the graveyard (a word
    nearly every row has adds almost nothing); its repeats saturate (`GRAVEYARD_K1`), faster in a row longer than the
    average (`GRAVEYARD_B`), so a long, repetitive lesson does not outrank a short one about the query. Exact ties
    keep the order given. A row with no query word is left out (the same rows as before, only in a new order).
    Standard library only.
    """
    words = graveyard_words(query)
    if not words or not rows:
        return list(rows)
    texts = [f"{r['mechanism']} {r['structure']} {r['roots']} {r['lesson']}".lower() for r in rows]
    counts = [{w: n for w in words if (n := t.count(w))} for t in texts]
    total = len(rows)
    df = {w: sum(1 for c in counts if w in c) for w in words}
    idf = {w: math.log(1 + (total - df[w] + 0.5) / (df[w] + 0.5)) for w in words}
    average = sum(len(t) for t in texts) / total
    ranked = []
    for i, (t, c) in enumerate(zip(texts, counts)):
        if c:
            k = GRAVEYARD_K1 * (1 - GRAVEYARD_B + GRAVEYARD_B * len(t) / average)
            ranked.append((-sum(idf[w] * n * (GRAVEYARD_K1 + 1) / (n + k) for w, n in c.items()), i))
    return [rows[i] for _, i in sorted(ranked)]


def code_sha(code: str) -> str:
    return hashlib.sha256(str(code).encode("utf-8")).hexdigest()


class SwarmStore:
    """The swarm's durable state (the module docstring)."""

    def __init__(self, root: str | Path, *, clock: Any = time.time, readonly: bool = False):
        self.root = Path(root)
        self.clock = clock
        self.readonly = readonly
        self.path = self.root / DB_NAME
        self.programs = self.root / PROGRAMS_DIR
        self.runs_dir = self.root / RUNS_DIR
        self._lock = threading.RLock()
        if readonly:
            self._db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, check_same_thread=False, timeout=5,
                                       isolation_level=None)
        else:
            self.root.mkdir(parents=True, exist_ok=True)
            self.programs.mkdir(exist_ok=True)
            self.runs_dir.mkdir(exist_ok=True)
            self._db = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30, isolation_level=None)
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.executescript(SCHEMA)
            columns = {r[1] for r in self._db.execute("PRAGMA table_info(forward)")}
            if "version" not in columns:  # a store made before forward rows carried their program version
                self._db.execute("ALTER TABLE forward ADD COLUMN version INTEGER")
        self._db.row_factory = sqlite3.Row
        if not readonly and not self.get("program_lineages_indexed"):
            with self.atomic():
                self._exec("INSERT OR IGNORE INTO lineage_links(a,b) SELECT DISTINCT f.lineage,g.lineage "
                           "FROM versions v JOIN versions w ON v.sha=w.sha "
                           "JOIN families f ON f.id=v.family JOIN families g ON g.id=w.family "
                           "WHERE f.lineage<g.lineage AND f.structure=g.structure AND f.roots=g.roots")
                self.put("program_lineages_indexed", True)

    # ------------------------------------------------------------------ plumbing
    def now(self) -> str:
        return iso(self.clock())

    def _all(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, tuple(params)).fetchall()]

    def _one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(sql, tuple(params)).fetchone()
        return dict(row) if row is not None else None

    def _exec(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._db.execute(sql, tuple(params))

    def close(self) -> None:
        with self._lock:
            self._db.close()

    @contextmanager
    def atomic(self):
        """One durable read/write operation, also excluding the House's other SQLite connection."""
        with self._lock:
            outer = not self._db.in_transaction
            if outer:
                self._db.execute("BEGIN IMMEDIATE")
            try:
                yield
                if outer:
                    self._db.commit()
            except BaseException:
                if outer:
                    try:
                        self._db.rollback()
                    except BaseException:
                        # An unusable transaction must never become a later caller's successful commit.
                        self._db.close()
                raise

    # ------------------------------------------------------------------ key-values
    def get(self, key: str, default: Any = None) -> Any:
        row = self._one("SELECT value FROM kv WHERE key=?", (key,))
        return loads(row["value"], default) if row else default

    def put(self, key: str, value: Any) -> None:
        self._exec("INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (key, dumps(value)))

    # ------------------------------------------------------------------ families
    @staticmethod
    def _family(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        row["roots"] = loads(row["roots"], [])
        row["spec"] = loads(row["spec"], {})
        row["state"] = loads(row["state"], {})
        return row

    def unique_id(self, base: str) -> str:
        stem = slugify(base)
        candidate, n = stem, 1
        while self._one("SELECT 1 FROM families WHERE id=?", (candidate,)) is not None:
            n += 1
            candidate = f"{stem[:36 - len(str(n)) - 1]}-{n}"
        return candidate

    def add_family(self, spec: Mapping[str, Any], *, origin: str, parent: str | None = None,
                   prior_lineage: str | Sequence[str] | None = None) -> dict[str, Any]:
        """A new family from `spec` (id or slug, mechanism, structure, roots, dte, rejection, ...). A fork
        (`parent`) joins its parent's lineage: its trials (`lineage_trials`) and its looks (`lineage_looks`). A new
        lineage born on a dead one's slice names it as `prior_lineage`: its trials count, its looks do not. It may name
        several (`slice_priors`, a singles' slice): the first is kept as `prior_lineage`, all of them as `prior_lineages`.
        `inherited_trials` and `inherited_looks` record the counts at birth; the live counts are the methods'."""
        if spec.get("structure") not in STRUCTURES:
            raise ValueError(f"unknown structure {spec.get('structure')!r}")
        roots = [str(r).upper() for r in (spec.get("roots") or []) if str(r).strip()]
        if not roots:
            raise ValueError("a family names at least one root")
        mechanism = " ".join(str(spec.get("mechanism") or "").split())
        if len(mechanism) < 20:
            raise ValueError("a family's mechanism is a sentence saying why it should make money")
        with self._lock:
            fid = self.unique_id(spec.get("id") or spec.get("slug") or mechanism)
            lineage, inherited_trials, inherited_looks = fid, 0, 0
            if parent:
                mother = self.family(parent)
                if mother is None:
                    raise ValueError(f"no parent family {parent}")
                lineage = mother["lineage"]
                inherited_trials = self.lineage_trials(parent)
            body = {k: v for k, v in dict(spec).items() if k not in ("id", "slug", "prior_lineage", "prior_lineages")}
            body["roots"] = roots
            named = [prior_lineage] if isinstance(prior_lineage, str) else list(prior_lineage or [])
            priors = [p for p in dict.fromkeys(str(x) for x in named if x)
                      if self._one("SELECT 1 FROM families WHERE lineage=?", (p,))]
            if priors and not parent:
                body["prior_lineage"] = priors[0]
                if len(priors) > 1:
                    body["prior_lineages"] = priors
                inherited_trials = self._trials_of(sorted({line for p in priors for line in self.lineages(p)}))
            now = self.now()
            self._exec(
                "INSERT INTO families(id, lineage, parent, origin, mechanism, structure, roots, spec, born_at, band, band_since,"
                " inherited_trials, inherited_looks) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fid, lineage, parent, origin, mechanism, spec["structure"], dumps(roots), dumps(body), now, "gym", now,
                 inherited_trials, inherited_looks))
            if parent:
                self._exec("UPDATE families SET inherited_looks=? WHERE id=?", (self.lineage_looks(fid), fid))
        return self.family(fid)  # type: ignore[return-value]

    def family(self, fid: str) -> dict[str, Any] | None:
        return self._family(self._one("SELECT * FROM families WHERE id=?", (fid,)))

    def families(self, *, alive: bool | None = None) -> list[dict[str, Any]]:
        if alive is None:
            rows = self._all("SELECT * FROM families ORDER BY born_at, id")
        elif alive:
            rows = self._all("SELECT * FROM families WHERE retired_at IS NULL ORDER BY born_at, id")
        else:
            rows = self._all("SELECT * FROM families WHERE retired_at IS NOT NULL ORDER BY retired_at, id")
        return [self._family(r) for r in rows]  # type: ignore[misc]

    def update_family(self, fid: str, **fields: Any) -> None:
        if not fields:
            return
        cols = []
        values = []
        for key, value in fields.items():
            if key in ("roots", "spec", "state"):
                value = dumps(value)
            cols.append(f"{key}=?")
            values.append(value)
        self._exec(f"UPDATE families SET {', '.join(cols)} WHERE id=?", (*values, fid))

    def bump(self, fid: str, **deltas: float) -> None:
        """Add to counters (never lowers one unless the delta says so)."""
        if deltas:
            self._exec(f"UPDATE families SET {', '.join(f'{k}={k}+?' for k in deltas)} WHERE id=?", (*deltas.values(), fid))

    def set_state(self, fid: str, **values: Any) -> dict[str, Any]:
        with self._lock:
            while True:
                row = self._one("SELECT state FROM families WHERE id=?", (fid,))
                state = dict(loads(row["state"], {}) or {}) if row else {}
                state.update(values)
                if row is None or self._exec("UPDATE families SET state=? WHERE id=? AND state=?",
                                              (dumps(state), fid, row["state"])).rowcount:
                    return state

    def compare_and_set_state(self, fid: str, expect: Mapping[str, Any], **values: Any) -> bool:
        """Set only while `expect` holds, retrying unrelated writes from the House's separate connection."""
        with self._lock:
            while True:
                row = self._one("SELECT state FROM families WHERE id=?", (fid,))
                if row is None:
                    return False
                state = dict(loads(row["state"], {}) or {})
                if any(state.get(k) != v for k, v in expect.items()):
                    return False
                state.update(values)
                if self._exec("UPDATE families SET state=? WHERE id=? AND state=?", (dumps(state), fid, row["state"])).rowcount:
                    return True

    def hold_gate(self, fid: str, hold: bool = True, *, reason: str = "") -> bool:
        """THE OPERATOR'S GATE HOLD: while a family's state has `gate_hold` true the gate (`gate.Gate.run`) looks at nothing
        of it (no review, audit or holdout look), and leaves its `gate_ready` as it is, so it is looked at once the hold is
        cleared (`hold=False`). While it is held with `gate_ready` no rule retires it (`retire_gym` refuses: the researcher's,
        the tournament's and the diagnostician's); its clocks keep running, so a family past a retirement rule may retire
        at the first round after the hold is cleared, before the gate looks. One private `swarm.gate` event says who held or
        released it and why. False when there is no such family. The operator's call on the box (a second connection is safe):
        `python -m league.swarm hold-gate --family <id> [--clear] [--reason ...]`."""
        with self.atomic():
            if self.family(fid) is None:
                return False
            self.set_state(fid, gate_hold=bool(hold))
            self.event("swarm.gate", fid, {"action": "gate_hold" if hold else "gate_hold_cleared", "by": "operator",
                                           "reason": str(reason or "")[:300]})
        return True

    def set_band(self, fid: str, band: str, *, reason: str) -> str | None:
        """Move a family's band; the move is a `swarm.band` event (the site's news). Returns the old band."""
        if band not in BANDS:
            raise ValueError(band)
        with self._lock:
            fam = self.family(fid)
            if fam is None or fam["retired_at"] or fam["band"] == band:
                return None
            if not self._exec("UPDATE families SET band=?, band_since=? WHERE id=? AND band=? AND retired_at IS NULL",
                               (band, self.now(), fid, fam["band"])).rowcount:
                return None
            self.event("swarm.band", fid, {"band_from": fam["band"], "band_to": band, "reason": reason})
            return fam["band"]

    def retire(self, fid: str, reason: str, *, public_reason: str | None = None) -> bool:
        with self.atomic():
            fam = self.family(fid)
            if fam is None or fam["retired_at"]:
                return False
            self.update_family(fid, retired_at=self.now(), retire_reason=reason, band="retired", band_since=self.now())
            self.set_state(fid, rewrite_ready=None, gate_ready=False)
            self._exec("UPDATE convo SET pending=NULL, updated_at=? WHERE family=?", (self.now(), fid))
            self.event("swarm.retired", fid, {"cause": reason if public_reason is None else public_reason, "band_from": fam["band"]})
            return True

    def retire_gym(self, fid: str, reason: Any, *, floor: int, source: str) -> dict[str, Any]:
        """One Gym retirement across researcher/tournament connections; evidence and look reservations survive."""
        if not isinstance(reason, str) or not reason.strip():
            return {"status": "refused", "reason": "retirement needs a nonempty reason string"}
        reason = reason.strip()[:2000]
        from . import public
        from .diagnostics import validation_words

        with self.atomic():
            fam = self.family(fid)
            if fam is None:
                return {"status": "refused", "reason": "no such family"}
            if fam["retired_at"]:
                return {"status": "retired", "already_retired": True}
            if fam["band"] != "gym":
                return {"status": "refused", "reason": "only a Gym family can retire through research"}
            held = fam.get("state") or {}
            if held.get("gate_hold") and held.get("gate_ready"):
                # THE OPERATOR'S GATE HOLD (`hold_gate`): the look the operator is holding must still happen, so no rule
                # (the researcher's, the tournament's or the diagnostician's) retires the family until the hold is cleared.
                return {"status": "refused", "deferred": "gate_hold",
                        "reason": "the operator holds this family's validated version at the gate; it retires only once the "
                                  "hold is cleared"}
            alive = self._one("SELECT COUNT(*) AS n FROM families WHERE retired_at IS NULL")["n"]
            if int(alive) <= max(0, int(floor)):
                return {"status": "refused", "deferred": "population_floor",
                        "reason": "the population is at its minimum; retirement was not applied"}
            state = fam.get("state") or {}
            notes = self.notebook(fid, limit=4)
            # Validation as a verdict and a count only (D2a): the graveyard is read by researchers and the architect.
            validation = validation_words(state.get("validation_line")) if state.get("validation_line") else "never validated"
            lesson = (f"{fam['structure']} on {', '.join(fam['roots'])}: {reason}. Tried {fam.get('revisions')} versions over "
                      f"{self.lineage_trials(fid)} lineage trials; best Train score {fam.get('best_train')}; best validation: "
                      f"{validation}. Last notes: " + " | ".join(n["text"][:240] for n in notes))
            self.note(fid, f"Retired by {source}: {reason}")
            self.bury(fid, lesson, {"validation": state.get("validation_view"), "best_train": fam.get("best_train"),
                                   "best_version": fam.get("best_version")})
            latest = self.latest_version(fid) or {}
            names = public.param_names_of(latest.get("code")) + list((latest.get("params") or {}).keys())
            cause = public.note_text(reason, param_names=names) or "the family left the Gym after review"
            self.retire(fid, reason, public_reason=cause)
            return {"status": "retired", "already_retired": False}

    def _lineages_from(self, line: str | None) -> list[str]:
        """`line` first, then every lineage its root's priors reach (`priors_of`: each one's own priors too)."""
        out: list[str] = []
        pending = [line]
        while pending:
            line = pending.pop(0)
            if not line or line in out:
                continue
            out.append(line)
            root = self._one("SELECT spec FROM families WHERE id=?", (line,))
            pending.extend(priors_of(loads(root["spec"], {}) or {}) if root else [])
        return out

    def lineages(self, fid: str) -> list[str]:
        """The family's lineage and every lineage its root was born on the slice of: the set its trials count over."""
        fam = self._one("SELECT lineage FROM families WHERE id=?", (fid,))
        if fam is None:
            return []
        out, pending = set(), [fam["lineage"]]
        while pending:
            line = pending.pop()
            if line in out:
                continue
            connected = self._connected_lineages(line)
            out.update(connected)
            for linked in connected:
                pending.extend(prior for prior in self._lineages_from(linked)[1:] if prior not in out)
        return sorted(out)

    def _connected_lineages(self, line: str) -> list[str]:
        graph: dict[str, set[str]] = {}
        for row in self._all("SELECT a,b FROM lineage_links"):
            graph.setdefault(row["a"], set()).add(row["b"])
            graph.setdefault(row["b"], set()).add(row["a"])
        seen, pending = set(), [line]
        while pending:
            node = pending.pop()
            if node in seen:
                continue
            seen.add(node)
            pending.extend(graph.get(node, set()) - seen)
        return sorted(seen)

    def _trials_of(self, lines: Sequence[str]) -> int:
        if not lines:
            return 0
        row = self._one(f"SELECT COALESCE(SUM(trials), 0) AS n FROM families WHERE lineage IN ({','.join('?' * len(lines))})",
                        tuple(lines))
        return int(row["n"]) if row else 0

    @property
    def lock(self) -> Any:
        """The store's own (re-entrant) lock, for a read-then-write that must not interleave with another thread's."""
        return self._lock

    def lineage_trials(self, fid: str) -> int:
        """Every trial of every family in the lineage set (`lineages`): the N the deflated Sharpe divides by."""
        return self._trials_of(self.lineages(fid))

    def ancestors(self, fid: str) -> list[str]:
        """The family and its parents up to the lineage's root."""
        out: list[str] = []
        cur: str | None = fid
        while cur and cur not in out:
            out.append(cur)
            row = self._one("SELECT parent FROM families WHERE id=?", (cur,))
            cur = row["parent"] if row else None
        return out

    def lineage_looks(self, fid: str, *, include_inflight: bool = False) -> int:
        """Every connected lineage's look, across all roots and all fork dates; optionally reserve pending looks."""
        fam = self._one("SELECT lineage FROM families WHERE id=?", (fid,))
        if fam is None:
            return 0
        lines = self._connected_lineages(fam["lineage"])
        slots = ",".join("?" * len(lines))
        seen = {row["run_sha"] for row in self._all(f"SELECT run_sha FROM looks WHERE lineage IN ({slots})", lines)}
        if include_inflight:
            for row in self._all(f"SELECT state FROM families WHERE lineage IN ({slots})", lines):
                marker = (loads(row["state"], {}) or {}).get("look_inflight") or {}
                if marker.get("sha"):
                    seen.add(marker["sha"])
        return len(seen)

    def lineage_validated(self, fid: str) -> tuple[int, list[float]]:
        """(N, Sharpes) for the deflated Sharpe (the owner's decision D2b, Sept 26): N = the distinct program versions
        validated across the family's lineage set (`lineages`: ancestors, siblings, descendants and prior slices, so
        inherited ones count), and each one's traded-day Sharpe (`t_daily / sqrt(days_traded)`) from its latest
        validation at the normal spread."""
        from .evidence import traded_sharpe

        lines = self.lineages(fid)
        if not lines:
            return 0, []
        rows = self._all(f"SELECT r.family, r.version, r.summary FROM runs r JOIN families f ON f.id=r.family "
                         f"WHERE f.lineage IN ({','.join('?' * len(lines))}) AND r.window='validation' AND r.stress=1.0 "
                         "AND r.trials>0 AND r.version IS NOT NULL ORDER BY r.at DESC, r.rowid DESC", tuple(lines))
        seen: set[tuple[str, int]] = set()
        sharpes = []
        for r in rows:
            key = (r["family"], int(r["version"]))
            if key in seen:
                continue
            seen.add(key)
            value = traded_sharpe(loads(r["summary"], {}) or {})
            if value is not None:
                sharpes.append(value)
        return len(seen), sharpes

    def lineage_trial_sharpes(self, fid: str, *, window: str = "train", limit: int = 5000) -> list[float]:
        """Daily Sharpe of every recorded trial in the family's lineage (for the deflated Sharpe)."""
        fam = self.family(fid)
        if fam is None:
            return []
        lines = self.lineages(fid)
        rows = self._all(f"SELECT r.summary FROM runs r JOIN families f ON f.id=r.family WHERE f.lineage IN ({','.join('?' * len(lines))})"
                         " AND r.window=? AND r.trials>0 ORDER BY r.at DESC LIMIT ?", (*lines, window, limit))
        out = []
        for r in rows:
            s = loads(r["summary"], {}) or {}
            v = s.get("sharpe_daily")
            if isinstance(v, (int, float)):
                out.append(float(v))
        return out

    # ------------------------------------------------------------------ programs
    def add_version(self, fid: str, code: str, params: Mapping[str, Any] | None, *, author: str, note: str = "") -> dict[str, Any]:
        """Store a program version (or return the existing one with the same code and parameters)."""
        sha = code_sha(code)
        params = dict(params or {})
        with self._lock:
            self._link_code(fid, sha)
            for v in self._all("SELECT * FROM versions WHERE family=? AND sha=?", (fid, sha)):
                if loads(v["params"], {}) == params:
                    return self.version(fid, v["n"])  # type: ignore[return-value]
            last = self._one("SELECT MAX(n) AS n FROM versions WHERE family=?", (fid,))
            n = int((last or {}).get("n") or 0) + 1
            folder = self.programs / fid
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"v{n}-{sha[:12]}.py"
            path.write_text(code)
            (folder / f"v{n}-{sha[:12]}.json").write_text(dumps(params))
            self._exec("INSERT INTO versions(family, n, sha, params, path, created_at, author, note) VALUES(?,?,?,?,?,?,?,?)",
                       (fid, n, sha, dumps(params), str(path.relative_to(self.root)), self.now(), author, str(note or "")[:500]))
            self.bump(fid, revisions=1, stall=1, since_val_revisions=1)
        return self.version(fid, n)  # type: ignore[return-value]

    def _link_code(self, fid: str, sha: str) -> None:
        """Identical code on the same structure and roots joins the lineages (the module docstring)."""
        fam = self.family(fid)
        if fam is None:
            return
        for other in self._all("SELECT DISTINCT f.lineage,f.structure,f.roots FROM versions v JOIN families f "
                               "ON f.id=v.family WHERE v.sha=? AND f.lineage!=?", (sha, fam["lineage"])):
            if same_slice(other["structure"], fam["structure"]) and sorted(loads(other["roots"], [])) == sorted(fam["roots"]):
                a, b = sorted((fam["lineage"], other["lineage"]))
                self._exec("INSERT OR IGNORE INTO lineage_links(a,b) VALUES(?,?)", (a, b))

    def link_lineages(self, a: str, b: str) -> bool:
        """Join two lineages for good, as identical code does (`_link_code`): their trials, looks and validated versions
        count together from now on. The architect joins a `long_single` that continues one call or put twin to the other
        twin's lineage (review of #425). True when a new link was made; never a lineage to itself or to one that does not
        exist."""
        if not a or not b or a == b:
            return False
        with self._lock:
            if not (self._one("SELECT 1 FROM families WHERE lineage=?", (a,)) and self._one("SELECT 1 FROM families WHERE lineage=?", (b,))):
                return False
            a, b = sorted((a, b))
            return self._exec("INSERT OR IGNORE INTO lineage_links(a,b) VALUES(?,?)", (a, b)).rowcount > 0

    def add_versions(self, fid: str, code: str, params_list: Sequence[Mapping[str, Any] | None], *, author: str,
                     note: str = "") -> list[dict[str, Any]]:
        """The versions of ONE program under several PARAMS overrides (a sweep's variants, `researcher.py`), in order.
        Each variant is a version of its own, because the tournament, the gate and the live path read a version's params;
        the code is stored once (new rows share one file of it), and the whole sweep counts as ONE revision when it adds
        any version. A variant whose code and params a version of the family already has is that version."""
        sha = code_sha(code)
        numbers: list[int] = []
        with self._lock:
            self._link_code(fid, sha)
            same = self._all("SELECT n, params, path FROM versions WHERE family=? AND sha=? ORDER BY n DESC", (fid, sha))
            known = [(loads(v["params"], {}), int(v["n"])) for v in same]
            shared = next((v["path"] for v in same if (self.root / v["path"]).is_file()), None)
            last = self._one("SELECT MAX(n) AS n FROM versions WHERE family=?", (fid,))
            n = int((last or {}).get("n") or 0)
            folder = self.programs / fid
            added = 0
            for params in params_list:
                params = dict(params or {})
                match = next((k for p, k in known if p == params), None)
                if match is not None:
                    numbers.append(match)
                    continue
                n += 1
                folder.mkdir(parents=True, exist_ok=True)
                if shared is None:
                    path = folder / f"v{n}-{sha[:12]}.py"
                    path.write_text(code)
                    shared = str(path.relative_to(self.root))
                (folder / f"v{n}-{sha[:12]}.json").write_text(dumps(params))
                self._exec("INSERT INTO versions(family, n, sha, params, path, created_at, author, note) VALUES(?,?,?,?,?,?,?,?)",
                           (fid, n, sha, dumps(params), shared, self.now(), author, str(note or "")[:500]))
                known.append((params, n))
                numbers.append(n)
                added += 1
            if added:
                self.bump(fid, revisions=1, stall=1, since_val_revisions=1)
        return [self.version(fid, k) for k in numbers]  # type: ignore[misc]

    def version(self, fid: str, n: int | None) -> dict[str, Any] | None:
        if n is None:
            return None
        row = self._one("SELECT * FROM versions WHERE family=? AND n=?", (fid, int(n)))
        if row is None:
            return None
        row["params"] = loads(row["params"], {})
        try:
            row["code"] = (self.root / row["path"]).read_text()
        except OSError:
            row["code"] = None
        return row

    def latest_version(self, fid: str) -> dict[str, Any] | None:
        row = self._one("SELECT MAX(n) AS n FROM versions WHERE family=?", (fid,))
        return self.version(fid, row["n"]) if row and row["n"] else None

    def versions(self, fid: str) -> list[dict[str, Any]]:
        rows = self._all("SELECT family, n, sha, params, created_at, author, note FROM versions WHERE family=? ORDER BY n", (fid,))
        for r in rows:
            r["params"] = loads(r["params"], {})
        return rows

    # ------------------------------------------------------------------ runs
    def add_run(self, fid: str, version: int | None, result: Mapping[str, Any], *, window: str, stress: float, purpose: str,
                program_years: float = 0.0, prune: bool = True, key: str | None = None) -> dict[str, Any]:
        """Record one Gym result (every result is a trial when its `trials` says so) and keep it in full. The same
        evaluation run again (same code, parameters, data and settings: the same `run_id`) is stored once and still
        counted: every evaluation the Gym makes is a trial. `prune=False` (a sweep's variants) leaves the pruning of full
        Train results to the caller (`prune_runs(keep=...)` once the sweep is recorded). `key` is the researcher's
        evaluation key (`researcher.Researcher.eval_key`), kept in the row's summary as `eval_key` so the same evaluation
        asked again is answered from the store (`evaluated`), with the result's `fill_model` beside it (a stored result on
        another fill model is not reused); a row recorded before keys existed takes both on its next identical evaluation,
        and its Train score and eligibility when it had none."""
        run_id = str(result.get("run_id") or code_sha(dumps(result))[:24])
        trials = int(result.get("trials", 0) or 0)
        status = str(result.get("status") or "unknown")
        summary = dict(result.get("summary") or {})
        # Evaluator identity survives pruning of full Train results. It is stamped by the actual
        # worker result, never inferred from the process recording a possibly late result.
        summary.update({name: result[name] for name in ("gym_image", "gym_bundle") if name in result})
        if status == "refused":
            summary = {"reason": result.get("reason")}
        elif window == "train" and drift_numbers(result.get("drift")) is not None:
            # A Train run's drift figures stay with its row after its full result is pruned: the drift screen reads them.
            summary["drift"] = drift_numbers(result.get("drift"))
        if key:
            summary["eval_key"] = str(key)
            if result.get("fill_model"):
                summary["fill_model"] = str(result["fill_model"])
        with self._lock:
            mine = f"{run_id}-{fid}"[:64]
            existing = self._one("SELECT * FROM runs WHERE (run_id=? OR run_id=?) AND family=?", (run_id, mine, fid))
            if existing is not None:
                # The worker's standalone run hash includes ENGINE_VERSION, not the full deployed
                # bundle. A source-only upgrade (or a forgotten version bump) can therefore reuse
                # it for different results. Never relabel the old metrics/path with the new bundle.
                names = ("gym_image", "gym_bundle")
                current_identity = tuple(result.get(name) for name in names)
                previous = loads(existing["summary"], {}) or {}
                if not any(previous.get(name) for name in names) and any(current_identity):
                    previous = self.run_result(existing["run_id"]) or previous
                previous_identity = tuple(previous.get(name) for name in names)
                if current_identity != previous_identity and (any(current_identity) or any(previous_identity)):
                    scope = code_sha(dumps({"worker_run_id": run_id, "family": fid, "evaluator": current_identity}))
                    run_id = f"{run_id[:31]}-{scope[:32]}"
                    existing = self._one("SELECT * FROM runs WHERE run_id=? AND family=?", (run_id, fid))
            if existing is not None:
                if trials:
                    self._exec("UPDATE runs SET trials=trials+?, program_years=program_years+? WHERE run_id=?",
                               (trials, float(program_years), existing["run_id"]))
                    self.bump(fid, trials=trials, since_val_trials=trials)
                old = loads(existing["summary"], {}) or {}
                if key:
                    new = {**old, **{k: summary[k] for k in ("train_score", "train_eligible") if k in summary and k not in old},
                           **{k: summary[k] for k in ("eval_key", "fill_model", "gym_image", "gym_bundle") if k in summary}}
                    if "train_kill" in summary and "train_kill" not in old:
                        # THE TRAIN KILL TESTS (league/swarm/killtests.py): a row scored before them takes the new score,
                        # eligibility and verdict when the same evaluation is made again (its stale flag is never kept).
                        new.update({k: summary[k] for k in ("train_score", "train_eligible", "train_kill", "train_why")
                                    if k in summary})
                    if new != old:
                        self._exec("UPDATE runs SET summary=? WHERE run_id=?", (dumps(new), existing["run_id"]))
                return self._one("SELECT * FROM runs WHERE run_id=?", (existing["run_id"],))  # type: ignore[return-value]
            if self._one("SELECT 1 FROM runs WHERE run_id=?", (run_id,)) is not None:
                run_id = mine
            path = self.runs_dir / f"{run_id}.json.gz"
            path.write_bytes(gzip.compress(dumps(result).encode("utf-8"), compresslevel=5))
            self._exec("INSERT INTO runs(run_id, family, version, window, stress, purpose, at, status, trials, program_years, summary, path)"
                       " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                       (run_id, fid, version, window, float(stress), purpose, self.now(), status, trials, float(program_years),
                        dumps(summary), str(path.relative_to(self.root))))
            if trials:
                self.bump(fid, trials=trials, since_val_trials=trials)
            if window == "train" and prune:
                self.prune_runs(fid)
        return self._one("SELECT * FROM runs WHERE run_id=?", (run_id,))  # type: ignore[return-value]

    #: Full Train results kept per family (the newest, plus its best and submitted runs): a three-year result is ~100-400 KB
    #: compressed and a researcher makes one a minute, which would fill the House box's disk in days. The summary row stays.
    KEEP_FULL_TRAIN_RUNS = 6

    #: Full robustness results kept per family (their compact figures live in the family's state).
    KEEP_FULL_ROBUSTNESS_RUNS = 2

    def prune_runs(self, fid: str, keep: Iterable[str] = ()) -> int:
        """Drop the full results beyond the newest few (the constants above), never the best, the submitted run or `keep`
        (a sweep's rows, which its researcher reads next)."""
        fam = self.family(fid) or {}
        state = fam.get("state") or {}
        protected = {state.get("best_train_run"), state.get("submitted_run"), *keep}
        rows = self._all("SELECT run_id, path, purpose FROM runs WHERE family=? AND window='train' AND path IS NOT NULL "
                         "ORDER BY at DESC, rowid DESC", (fid,))
        # The researcher's own runs and the robustness runs are kept apart, so robustness never pushes out a run it reads.
        research = [r for r in rows if r["purpose"] != "robustness"][self.KEEP_FULL_TRAIN_RUNS:]
        robustness = [r for r in rows if r["purpose"] == "robustness"][self.KEEP_FULL_ROBUSTNESS_RUNS:]
        n = 0
        for row in research + robustness:
            if row["run_id"] in protected:
                continue
            try:
                (self.root / row["path"]).unlink()
            except OSError:
                pass
            self._exec("UPDATE runs SET path=NULL WHERE run_id=?", (row["run_id"],))
            n += 1
        return n

    def run(self, run_id: str) -> dict[str, Any] | None:
        row = self._one("SELECT * FROM runs WHERE run_id=?", (run_id,))
        if row is not None:
            row["summary"] = loads(row["summary"], {})
        return row

    def evaluated(self, fid: str, key: str | None) -> dict[str, Any] | None:
        """The family's completed ("ok") Train run of this evaluation (its `eval_key`: the program, its merged params, the
        stress, window and roots, the Gym's image and engine), the latest, or None. A researcher asking for it again is
        answered from here: no Gym job, no trial, no version (`researcher.py`, NO DUPLICATE RUNS)."""
        if not key:
            return None
        key = str(key)
        for row in self._all("SELECT * FROM runs WHERE family=? AND window='train' AND status='ok' AND version IS NOT NULL "
                             "AND summary LIKE ? ORDER BY at DESC, rowid DESC", (fid, f'%"eval_key":"{key}"%')):
            row["summary"] = loads(row["summary"], {})
            if (row["summary"] or {}).get("eval_key") == key:
                return row
        return None

    def run_result(self, run_id: str) -> dict[str, Any] | None:
        row = self._one("SELECT path FROM runs WHERE run_id=?", (run_id,))
        if row is None or not row["path"]:
            return None
        try:
            return json.loads(gzip.decompress((self.root / row["path"]).read_bytes()))
        except (OSError, ValueError, EOFError, zlib.error):  # a missing, truncated or corrupt file is unreadable, never a crash
            return None

    def runs(self, fid: str, *, window: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if window:
            rows = self._all("SELECT * FROM runs WHERE family=? AND window=? ORDER BY at DESC, rowid DESC LIMIT ?", (fid, window, limit))
        else:
            rows = self._all("SELECT * FROM runs WHERE family=? ORDER BY at DESC, rowid DESC LIMIT ?", (fid, limit))
        for r in rows:
            r["summary"] = loads(r["summary"], {})
        return rows

    def version_runs(self, fid: str, version: int, *, window: str = "train", stress: float | None = None,
                     limit: int = 20) -> list[dict[str, Any]]:
        """One version's run rows, newest first (optionally at one `stress`): a lookup by version in SQL, so a family's
        thousands of other rows are never decoded."""
        sql, args = "SELECT * FROM runs WHERE family=? AND version=? AND window=?", [fid, int(version), window]
        if stress is not None:
            sql, args = sql + " AND stress=?", args + [float(stress)]
        rows = self._all(sql + " ORDER BY at DESC, rowid DESC LIMIT ?", (*args, int(limit)))
        for r in rows:
            r["summary"] = loads(r["summary"], {})
        return rows

    def totals(self) -> dict[str, Any]:
        row = self._one("SELECT COALESCE(SUM(trials),0) AS trials, COALESCE(SUM(program_years),0) AS years, COUNT(*) AS runs FROM runs")
        alive = self._one("SELECT COUNT(*) AS n FROM families WHERE retired_at IS NULL")
        dead = self._one("SELECT COUNT(*) AS n FROM families WHERE retired_at IS NOT NULL")
        looks = self._one("SELECT COUNT(*) AS n, COALESCE(SUM(passed),0) AS passed FROM looks")
        return {"trials": int(row["trials"]), "market_years": float(row["years"]), "runs": int(row["runs"]),
                "families_alive": int(alive["n"]), "families_retired": int(dead["n"]),
                "holdout_looks": int(looks["n"]), "holdout_passes": int(looks["passed"])}

    # ------------------------------------------------------------------ notebook and graveyard
    def note(self, fid: str, text: str) -> int:
        text = str(text or "").strip()[:4000]
        if not text:
            return 0
        cur = self._exec("INSERT INTO notebook(family, at, text) VALUES(?,?,?)", (fid, self.now(), text))
        return int(cur.lastrowid or 0)

    def notebook(self, fid: str, *, limit: int = 30) -> list[dict[str, Any]]:
        rows = self._all("SELECT seq, at, text FROM notebook WHERE family=? ORDER BY seq DESC LIMIT ?", (fid, limit))
        return list(reversed(rows))

    def bury(self, fid: str, lesson: str, best: Mapping[str, Any] | None = None) -> None:
        fam = self.family(fid)
        if fam is None:
            return
        self._exec("INSERT OR REPLACE INTO graveyard(family, at, mechanism, structure, roots, lesson, best) VALUES(?,?,?,?,?,?,?)",
                   (fid, self.now(), fam["mechanism"], fam["structure"], dumps(fam["roots"]), str(lesson)[:3000], dumps(best or {})))

    def graveyard(self, query: str = "", *, limit: int = 8) -> list[dict[str, Any]]:
        """The lessons most relevant to `query` (`rank_graveyard`), or with no query the newest first (ties by id)."""
        rows = rank_graveyard(self._all("SELECT * FROM graveyard ORDER BY at DESC, family"), query)
        out = []
        for r in rows[:limit]:
            r["roots"] = loads(r["roots"], [])
            r["best"] = loads(r["best"], {})
            out.append(r)
        return out

    # ------------------------------------------------------------------ the gate's records
    def add_look(self, fid: str, version: int, run_sha: str, *, passed: bool, p_value: float | None, detail: Mapping[str, Any]) -> int:
        fam = self.family(fid)
        cur = self._exec("INSERT INTO looks(family, lineage, version, run_sha, at, passed, p_value, detail) VALUES(?,?,?,?,?,?,?,?)",
                         (fid, fam["lineage"] if fam else fid, int(version), run_sha, self.now(), 1 if passed else 0, p_value, dumps(detail)))
        return int(cur.lastrowid or 0)

    def looks(self) -> list[dict[str, Any]]:
        rows = self._all("SELECT * FROM looks ORDER BY seq")
        for r in rows:
            r["detail"] = loads(r["detail"], {})
        return rows

    def looked(self, run_sha: str) -> bool:
        return self._one("SELECT 1 FROM looks WHERE run_sha=?", (run_sha,)) is not None

    def looks_inflight(self) -> list[tuple[str, dict[str, Any]]]:
        """Every family's holdout look in flight: [(family, its `look_inflight` marker)], alive or retired, by family id.
        Only the states that name a marker at all are decoded (THE DUPLICATE LOOK, `gate.Gate.duplicate_look`)."""
        out = []
        for row in self._all("SELECT id, state FROM families WHERE state LIKE '%look_inflight%' ORDER BY id"):
            marker = (loads(row["state"], {}) or {}).get("look_inflight")
            if isinstance(marker, Mapping) and marker.get("sha"):
                out.append((str(row["id"]), dict(marker)))
        return out

    def refuse(self, fid: str, version: int | None, stage: str, reason: str) -> None:
        self._exec("INSERT INTO refusals(family, version, at, stage, reason) VALUES(?,?,?,?,?)",
                   (fid, version, self.now(), stage, str(reason)[:2000]))

    def refusals(self, fid: str | None = None) -> list[dict[str, Any]]:
        if fid:
            return self._all("SELECT * FROM refusals WHERE family=? ORDER BY seq", (fid,))
        return self._all("SELECT * FROM refusals ORDER BY seq")

    def hold_look(self, fid: str, version: int | None, run_sha: str, stage: str, reason: str) -> None:
        """THE LOOK HOLDS' record (`gate.Gate.look_hold`): a refusal-style row of its own, never a `refusals` row (a hold
        judges no evidence and no program; it says the holdout could not judge it). Its money-path effect is the gate's
        outcome "held" (`bands.BAD_OUTCOMES`: no execution tuition, no incubator) and the program's incubator bar, which
        the gate records with the row. `reason` is the researcher's words (no figure); the figures are in the private
        `swarm.gate` event."""
        self._exec("INSERT INTO look_holds(family, version, run_sha, at, stage, reason) VALUES(?,?,?,?,?,?)",
                   (fid, version, run_sha, self.now(), stage, str(reason)[:2000]))

    def look_holds(self, fid: str | None = None) -> list[dict[str, Any]]:
        if fid:
            return self._all("SELECT * FROM look_holds WHERE family=? ORDER BY seq", (fid,))
        return self._all("SELECT * FROM look_holds ORDER BY seq")

    # ------------------------------------------------------------------ forward records
    def add_forward(self, fid: str, source: str, trades: Iterable[Mapping[str, Any]], *, version: int | None = None) -> int:
        """Forward trades (nightly replays here; shadow and real from the live path), each once by id, each with the
        program VERSION that made it (a trade's own `version`, else `version`): a new version starts its own record."""
        if source not in ("nightly", "shadow", "real"):
            raise ValueError(source)
        n = 0
        with self._lock:
            for t in trades:
                v = t.get("version", version)
                cur = self._exec("INSERT OR IGNORE INTO forward(family, source, trade_id, day, pnl, max_loss, at, version)"
                                 " VALUES(?,?,?,?,?,?,?,?)",
                                 (fid, source, str(t["id"]), str(t.get("day") or ""), float(t["pnl"]), float(t.get("max_loss") or 0.0),
                                  self.now(), None if v is None else int(v)))
                n += cur.rowcount or 0
        return n

    def replace_forward(self, fid: str, source: str, trades: Iterable[Mapping[str, Any]], *, version: int) -> int:
        """One version's record from one source anew (the nightly replay reruns every forward day: its latest good run
        is the record). Other versions' and sources' rows are untouched."""
        with self.atomic():
            self._exec("DELETE FROM forward WHERE family=? AND source=? AND version=?", (fid, source, int(version)))
            return self.add_forward(fid, source, trades, version=version)

    def forward(self, fid: str, *, version: int | None = None) -> list[dict[str, Any]]:
        if version is None:
            return self._all("SELECT * FROM forward WHERE family=? ORDER BY day, trade_id", (fid,))
        return self._all("SELECT * FROM forward WHERE family=? AND version=? ORDER BY day, trade_id", (fid, int(version)))

    # ------------------------------------------------------------------ events and spend
    def event(self, kind: str, family: str | None, payload: Mapping[str, Any]) -> int:
        cur = self._exec("INSERT INTO events(at, kind, family, payload) VALUES(?,?,?,?)", (self.now(), kind, family, dumps(payload)))
        return int(cur.lastrowid or 0)

    def events_after(self, seq: int, *, limit: int = 500) -> list[dict[str, Any]]:
        rows = self._all("SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT ?", (int(seq), int(limit)))
        for r in rows:
            r["payload"] = loads(r["payload"], {})
        return rows

    def add_spend(self, kind: str, usd: float, *, family: str | None = None, detail: Mapping[str, Any] | None = None) -> None:
        if not usd:
            return
        now = self.clock()
        self._exec("INSERT INTO spend(at, epoch, kind, family, usd, detail) VALUES(?,?,?,?,?,?)",
                   (iso(now), now, kind, family, float(usd), dumps(detail or {})))
        if family:
            self.bump(family, spent_usd=float(usd))

    def spent(self, kinds: Sequence[str] | None = None, *, since: float | None = None) -> float:
        sql, params = "SELECT COALESCE(SUM(usd),0) AS usd FROM spend WHERE 1=1", []
        if kinds:
            sql += f" AND kind IN ({','.join('?' * len(kinds))})"
            params += list(kinds)
        if since is not None:
            sql += " AND epoch>=?"
            params.append(float(since))
        row = self._one(sql, params)
        return float(row["usd"]) if row else 0.0

    # ------------------------------------------------------------------ boxes
    def upsert_box(self, box: str, *, kind: str, version: str, state: str, detail: Mapping[str, Any] | None = None) -> None:
        now = self.clock()
        self._exec("INSERT INTO boxes(id, kind, version, state, created_at, last_used, detail) VALUES(?,?,?,?,?,?,?)"
                   " ON CONFLICT(id) DO UPDATE SET state=excluded.state, version=excluded.version, detail=excluded.detail",
                   (box, kind, version, state, iso(now), now, dumps(detail or {})))

    def box_used(self, box: str, seconds: float, *, jobs: int = 1) -> None:
        self._exec("UPDATE boxes SET last_used=?, busy_seconds=busy_seconds+?, jobs=jobs+? WHERE id=?", (self.clock(), float(seconds), int(jobs), box))

    def set_box_state(self, box: str, state: str) -> None:
        self._exec("UPDATE boxes SET state=? WHERE id=?", (state, box))

    def boxes(self, *, kind: str | None = None, live: bool = True) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM boxes WHERE 1=1", []
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        if live:
            sql += " AND state NOT IN ('terminated','failed')"
        rows = self._all(sql + " ORDER BY created_at, id", params)
        for r in rows:
            r["detail"] = loads(r["detail"], {})
        return rows

    # ------------------------------------------------------------------ conversations
    def convo(self, fid: str) -> tuple[list[dict[str, Any]], Any]:
        row = self._one("SELECT items, pending FROM convo WHERE family=?", (fid,))
        if row is None:
            return [], None
        return loads(row["items"], []), loads(row["pending"], None)

    def save_convo(self, fid: str, items: list[dict[str, Any]], pending: Any = None) -> None:
        with self.atomic():
            fam = self.family(fid)
            if fam is None or fam["retired_at"]:
                pending = None
            self._exec("INSERT INTO convo(family, items, pending, updated_at) VALUES(?,?,?,?) ON CONFLICT(family) DO UPDATE SET"
                       " items=excluded.items, pending=excluded.pending, updated_at=excluded.updated_at",
                       (fid, dumps(items), dumps(pending) if pending is not None else None, self.now()))


__all__ = ["SwarmStore", "ALIVE", "BANDS", "STRUCTURES", "LONG_SINGLE", "SINGLE_SIDES", "same_slice", "slice_priors",
           "priors_of", "structure_text", "structure_query", "CLOSEABLE", "slugify", "code_sha", "dumps", "loads", "iso"]
