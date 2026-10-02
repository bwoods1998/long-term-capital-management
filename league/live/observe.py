"""The practice league's record: `<state>/observe.sqlite` (mode 0600), the House's private file.

The sprint (B4, Sept 26, 2026) made the observe band: an observe instance (`<family>@<version>:o`, `league/live/step.py`)
trades the shadow book on live quotes under the Gym's own fill rules, and its trades are never a forward row (no
evidence, no band). The practice league (Sept 29, 2026) keeps a record of it here:

- `trades`: one row a closed practice trade (the engine's own row in `body`; `exit_day` the session it closed, whose
  P&L is realized then; `reason` its exit reason; `forced` 1 when the House closed it winding the instance down);
- `practice`: one row per (family, version) from its first live minute, kept after the family retires (families live
  hours; the record outlives them): its tier, lineage, structure and roots at its first pin, the session days and
  minutes it was live, its decision coverage (due, made, missed for want of quotes, missed for want of the minute's
  budget), its marked P&L path (per minute, across a remade account) and its open positions at the engine's mark; and
  (`prior_*`) its coverage and open mark as its last session before the current one left them, rolled at the current
  session day's first minute (`prior_day`: that day, the roll's) (the incubator reads the record before today, never
  today's values).
- `cohorts`: immutable admitted program snapshots, retained through research revision (and, before the ladder,
  retirement) until the observation target or bounded session window completes; shadow-only entry authority. A FORWARD
  LADDER cohort (evidence v3, Oct 2, 2026: every cohort frozen from that release on; its snapshot's `ladder`) has no
  observation target: it practises until the ladder promotes it (`promoted`) or fails it (`failed`: its family retired
  among the reasons), or its practice window ends (the constitution's `options_money.ladder.max_sessions`); a promoted
  cohort whose Probe goes back to the Gym is `demoted`. Each row names the practice evaluator it was frozen under (`evaluator`). A program whose
  cohort completed under ANOTHER evaluator (a release moved it: the plan's "practice cohorts restart on the new
  fingerprint") is frozen again as a new cohort: the old row, with its practice row, moves to `cohort_archive`, and its
  practice row starts again, so its sessions are the new cohort's. A cohort that failed, was promoted or was demoted
  never re-enters, under any evaluator; nor does one completed under the running evaluator.
- `events`: private decision, coverage, intent, rejection, order, quote and fill/slippage receipts, idempotent across
  restarts. Unwritten receipts live in the saved shadow account and retry; the bounded outage buffer reports drops.
- `entrants`: one row per ladder cohort (family, version and its evaluator: a program frozen again under another
  evaluator is another trial), written with its admission: every entrant is a trial of its lineage and of the desk (the
  ladder's Benjamini-Hochberg counts every entrant of its trailing window), with its latest one-sided p-value.
- `ladder_decisions`: the ladder's receipts, one per cohort a day it judged (`league/live/ladder.py`).
- `cohort_archive`: cohorts that completed under an earlier evaluator and were frozen again, each with its practice row
  as it stood (JSON), kept for good.

WHO READS IT. THE FORWARD LADDER (evidence v3, the owner's D2 of Oct 2, 2026; `league/live/ladder.py`) reads a ladder
cohort's own program closes under its own evaluator as the promotion evidence to Probe; nothing else that promotes reads
it (not the gate, the verifier, the bands' reads, the money table's forward record or Profit). The swarm reads `practice_summary` (read-only) as a RESEARCH signal (`league/swarm/practice.py`: the strategist's
table, the architect's lines, the bandit's capped bonus), and the publisher shows its aggregates (the site's practice
block: never a price, strike, leg, expiry, minute, trade date, version or code). THE INCUBATOR (release B, Oct 1, 2026;
`league/live/incubator.py`) reads one cohort's record (`practice_record`, read-only) as a pre-registered sign test of
positive live practice: its eligibility for one-lot real money within the owner's caps. That is money, and never a
promotion, a band, a forward row or evidence of any kind. While the incubator is on, a cohort whose first look passed
keeps practising past its observation target to its bounded window (`cohort_candidates(keep=)`, at most eight).

HONEST ACCOUNTING. The fills are the engine's (`ShadowAccount`, the House's shadow fill model, the Candidates' own); a
trade's P&L is the engine's after fees. The headline is REALIZED P&L; open positions are reported apart, at the engine's
mark (a mid inside the package's bounds), and never added to it. Forced (wind-down) closes stay in the headline, because
they happened, and are counted apart; the feedback's statistics use program-closed trades only.

Bounded: at most `MAX_ROWS` trades (the oldest go first, but never a trade of an active or promoted ladder cohort under
its own evaluator: the ladder judges and receipts that record whole, so the table may then hold more); practice rows
unseen for `KEEP_DAYS` days are pruned. Each write
is one transaction; a failure is caught, alerted once, and never stops the minute (trades stay in the shadow account and
are offered again; a practice row is repaired by the next minute's upsert).
"""

from __future__ import annotations

import ast
import functools
import json
import math
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

FILE = "observe.sqlite"
MAX_ROWS = 50_000
KEEP_DAYS = 120
PRUNE_EVERY = 3600.0


class Hold(frozenset):
    """`cohort_candidates(keep=HOLD)`: this pass completes no cohort at its observation target."""


#: The incubator's keep could not be taken this pass (the cohorts unread, or `keep` raised): fail open for practising
#: only, for that pass (its window, an evaluator change or a failure still end a cohort; pins still need `_passing`).
HOLD = Hold()

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, instance TEXT NOT NULL, account TEXT NOT NULL, family TEXT NOT NULL,
    version INTEGER, trade_id TEXT NOT NULL, day TEXT, pnl REAL, max_loss REAL, recorded_at REAL NOT NULL,
    body TEXT NOT NULL, UNIQUE(instance, account, trade_id));
CREATE INDEX IF NOT EXISTS trades_family ON trades(family, day);
CREATE TABLE IF NOT EXISTS practice (
    family TEXT NOT NULL, version INTEGER NOT NULL,
    tier TEXT NOT NULL, lineage TEXT, structure TEXT, roots TEXT,
    capital REAL NOT NULL,
    first_at REAL NOT NULL, first_day TEXT NOT NULL,
    last_at REAL NOT NULL, last_day TEXT NOT NULL,
    sessions INTEGER NOT NULL DEFAULT 0,
    minutes INTEGER NOT NULL DEFAULT 0,
    decisions_due INTEGER NOT NULL DEFAULT 0, decisions_made INTEGER NOT NULL DEFAULT 0,
    missed_quotes INTEGER NOT NULL DEFAULT 0, missed_budget INTEGER NOT NULL DEFAULT 0,
    missed_errors INTEGER NOT NULL DEFAULT 0,
    account TEXT, base_pnl REAL NOT NULL DEFAULT 0,
    pnl_marked REAL NOT NULL DEFAULT 0, peak_marked REAL NOT NULL DEFAULT 0, drawdown_marked REAL NOT NULL DEFAULT 0,
    open_positions INTEGER NOT NULL DEFAULT 0, open_mark_pnl REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'live',
    prior_day TEXT, prior_due INTEGER, prior_made INTEGER, prior_open_mark REAL,
    PRIMARY KEY (family, version));
CREATE TABLE IF NOT EXISTS cohorts (
    family TEXT NOT NULL, version INTEGER NOT NULL, admitted_at REAL NOT NULL, first_day TEXT NOT NULL,
    snapshot TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', completed_day TEXT, reason TEXT, evaluator TEXT,
    PRIMARY KEY (family, version));
CREATE TABLE IF NOT EXISTS cohort_archive (
    family TEXT NOT NULL, version INTEGER NOT NULL, evaluator TEXT, admitted_at REAL NOT NULL, first_day TEXT NOT NULL,
    snapshot TEXT NOT NULL, status TEXT NOT NULL, completed_day TEXT, reason TEXT, practice TEXT,
    archived_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS cohort_archive_program ON cohort_archive(family, version);
CREATE TABLE IF NOT EXISTS events (
    instance TEXT NOT NULL, account TEXT NOT NULL, event_id INTEGER NOT NULL, family TEXT NOT NULL,
    version INTEGER NOT NULL, day TEXT, minute INTEGER, kind TEXT NOT NULL, body TEXT NOT NULL,
    recorded_at REAL NOT NULL, PRIMARY KEY(instance, account, event_id));
CREATE INDEX IF NOT EXISTS events_family_day ON events(family, day);
CREATE INDEX IF NOT EXISTS events_day ON events(day);
CREATE TABLE IF NOT EXISTS entrants (
    family TEXT NOT NULL, version INTEGER NOT NULL, run_sha TEXT, lineage TEXT, tier TEXT, evaluator TEXT NOT NULL,
    entered_at REAL NOT NULL, entered_day TEXT NOT NULL, p_value REAL, p_day TEXT,
    PRIMARY KEY (family, version, evaluator));
CREATE INDEX IF NOT EXISTS entrants_day ON entrants(entered_day);
CREATE TABLE IF NOT EXISTS ladder_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, family TEXT NOT NULL, version INTEGER NOT NULL,
    run_sha TEXT, inputs TEXT NOT NULL, stats TEXT NOT NULL, p_value REAL, bh_rank INTEGER, bh_size INTEGER,
    bh_threshold REAL, verdict TEXT NOT NULL, reasons TEXT, binding INTEGER NOT NULL, at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ladder_decisions_cohort ON ladder_decisions(family, version, day);
"""
#: Columns the practice league added to `trades` (Sept 29, 2026), backfilled from `body` on first open.
TRADE_COLUMNS = (("exit_day", "TEXT"), ("reason", "TEXT"), ("forced", "INTEGER"), ("evaluator", "TEXT"))
#: Columns release B added to `practice` (Oct 1, 2026): the row's decision coverage and open mark as its last session
#: before `last_day` left them, copied at the first minute of each new session day, with `prior_day` THAT day (the
#: roll's, never the day the values came from), so the incubator's record before today never reads today's values
#: (`practice_record` takes them only when `prior_day` is today: a row a release without these columns stepped today,
#: release A after a rollback, has an older `prior_day`, and its record is `intraday`). NULL until the row's next new
#: session day.
PRIOR_COLUMNS = (("prior_day", "TEXT"), ("prior_due", "INTEGER"), ("prior_made", "INTEGER"), ("prior_open_mark", "REAL"))


@functools.lru_cache(maxsize=1)
def evaluator_bundle() -> str:
    from ..gym.driver import build_bundle

    return build_bundle()[1]


class ObserveStore:
    """`<state>/observe.sqlite` (the module docstring)."""

    def __init__(self, root: str | Path, *, alert: Callable[[str, str], Any] | None = None,
                 clock: Callable[[], float] = time.time, max_rows: int = MAX_ROWS):
        self.path = Path(root) / FILE
        self.alert, self.clock, self.max_rows = alert, clock, int(max_rows)
        self.db: sqlite3.Connection | None = None
        self.told = False
        self.practice_told = False
        self._pruned_at = float("-inf")
        from ..gym import ENGINE_VERSION

        self.evaluator = ENGINE_VERSION

    def _connect(self) -> sqlite3.Connection:
        if self.db is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(fd)
            os.chmod(self.path, 0o600)
            db = sqlite3.connect(str(self.path), timeout=0.05, isolation_level=None, check_same_thread=False)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
            db.executescript(SCHEMA)
            _migrate(db)
            self.db = db
        return self.db

    def add(self, instance: str, family: str, version: int | None, trades: Iterable[Mapping[str, Any]], *,
            account: str = "") -> bool:
        """The trades of one observe instance's shadow account (`account`: its nonce, as trade ids restart when an account
        is made again under the same key), each once by (instance, account, trade id), in one transaction. False when not
        written."""
        rows = [(str(instance), str(account), str(family), version, str(t.get("id")), str(t.get("day") or ""),
                 _num(t.get("pnl")), _num(t.get("max_loss")), self.clock(), json.dumps(dict(t), sort_keys=True, default=str),
                 _day_of(t.get("exit_day")), str(t.get("exit_reason") or "") or None, 1 if t.get("forced") is True else 0,
                 t.get("evaluator"))
                for t in trades]
        if not rows:
            return True
        try:
            db = self._connect()
            with db:
                db.execute("BEGIN IMMEDIATE")
                db.executemany("INSERT OR IGNORE INTO trades(instance, account, family, version, trade_id, day, pnl, "
                               "max_loss, recorded_at, body, exit_day, reason, forced, evaluator) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
                over = int(db.execute("SELECT count(*) FROM trades").fetchone()[0]) - self.max_rows
                if over > 0:
                    # The oldest go first, never a trade of an active or promoted ladder cohort under its own evaluator:
                    # the ladder judges (and its receipts hash) that record whole.
                    db.execute("DELETE FROM trades WHERE seq IN (SELECT t.seq FROM trades t WHERE NOT EXISTS ("
                               "SELECT 1 FROM cohorts c WHERE c.family=t.family AND c.version=t.version AND "
                               "c.status IN ('active', 'promoted') AND c.evaluator=t.evaluator) ORDER BY t.seq LIMIT ?)",
                               (over,))
            return True
        except Exception as exc:  # noqa: BLE001 - the practice record never stops the minute
            if not self.told and self.alert is not None:
                self.told = True
                try:
                    self.alert("warning", f"live: the observe band's trades could not be recorded ({type(exc).__name__}); "
                                          "they are offered again next minute")
                except Exception:  # noqa: BLE001
                    pass
            return False

    def cohort_candidates(self, current: Iterable[Mapping[str, Any]], *, day: str, in_session: bool,
                          min_sessions: int = 3, min_trades: int = 10, max_sessions: int = 10,
                          keep: Iterable[tuple[str, int]] = frozenset()) -> list[dict]:
        """Keep admitted immutable snapshots across research revisions and retirement. Completed snapshots never
        re-enter under the evaluator they completed under: one that completed under another (an active one whose
        evaluator changed is completed here) is offered again from `current`, and `freeze` makes it a new cohort (the
        module docstring). A failed, promoted or demoted cohort never re-enters. A cohort finishes between sessions
        after enough observed days and program closes, or its bounded
        calendar-session window; capacity/pressure switches still apply in the caller. This is shadow authority only.
        `keep` (L2', the incubator's: (family, version) of cohorts whose first look passed, while `live.incubator` is on):
        such a cohort is not completed at its observation target; its window, an evaluator change or a failure still
        end it. Empty, this is exactly the league's own rule. `HOLD`: no cohort is completed at its target this pass."""
        hold = keep is HOLD
        keep = {(str(f), int(n)) for f, n in keep}
        from datetime import date, timedelta
        from .chains import session_minutes
        from ..swarm.bands import priority

        db = self._connect()
        frozen, seen = [], set()
        rows = db.execute("SELECT family, version, first_day, snapshot, status, evaluator FROM cohorts "
                          "ORDER BY admitted_at, family")
        for family, version, first, snapshot, status, evaluator in rows.fetchall():
            if status != "active":
                if status != "complete" or _evaluator_of(evaluator, snapshot) == self.evaluator:
                    seen.add((family, version))  # never again; a completed one under another evaluator may re-enter
                continue
            row = json.loads(snapshot)
            if row.get("practice_evaluator") != self.evaluator:
                db.execute("UPDATE cohorts SET status='complete', completed_day=?, reason=? WHERE family=? AND version=?",
                           (day, "evaluator changed; its practice starts again under the new one", family, version))
                continue  # not seen: offered again from `current`, frozen as a new cohort under this evaluator
            seen.add((family, version))
            # THE FORWARD LADDER's cohorts (evidence v3, `league/live/ladder.py`): no observation target ends one; it runs
            # until the ladder promotes it or fails it, or its own practice window (`practice_max_sessions`, at most 60).
            ladder = bool(row.get("ladder"))
            horizon = max(max_sessions, int(row.get("practice_max_sessions") or max_sessions))
            if ladder:
                horizon = int(row.get("practice_max_sessions") or 60)
            reason = None
            if in_session and first < day:
                elapsed, cursor, end = 0, date.fromisoformat(first), date.fromisoformat(day)
                while cursor < end:
                    elapsed += session_minutes(cursor) is not None
                    cursor += timedelta(days=1)
                if ladder:
                    if elapsed >= max(1, min(60, horizon)):
                        reason = "ladder: its practice window ended"
                else:
                    evidence = db.execute("SELECT sessions, last_day, open_positions FROM practice WHERE family=? "
                                          "AND version=?", (family, version)).fetchone()
                    completed = int(evidence[0]) - int(evidence[1] == day) if evidence else 0
                    trades = db.execute("SELECT COUNT(*) FROM trades WHERE family=? AND version=? AND forced=0 "
                                        "AND evaluator=? AND exit_day<?", (family, version, self.evaluator, day)).fetchone()[0]
                    if (completed >= max(1, min_sessions) and trades >= max(1, min_trades) and evidence and evidence[2] == 0
                            and not hold and (family, int(version)) not in keep):
                        reason = "observation target reached"
                    elif elapsed >= max(min_sessions, min(60, horizon)):
                        reason = "maximum session window reached"
            if reason:
                db.execute("UPDATE cohorts SET status='complete', completed_day=?, reason=? WHERE family=? AND version=?",
                           (day, reason, family, version))
                continue
            row["practice_frozen"] = True
            frozen.append(row)
        held = {r["family"] for r in frozen}
        frozen.sort(key=priority)
        return frozen + [dict(r) for r in current if r["family"] not in held
                         and (r["family"], int(r["version"])) not in seen]

    def freeze(self, row: Mapping[str, Any], *, day: str) -> dict:
        """Persist the exact admitted program before its first decision; never update a snapshot in place."""
        if row.get("observe") is not True or row.get("band") != "gym" or not row.get("code"):
            raise ValueError("only an eligible practice program can be frozen")
        db = self._connect()
        snapshot = {**dict(row), "practice_frozen": True, "practice_evaluator": self.evaluator}
        # A 45-DTE strategy cannot be fairly observed in a ten-session cohort. Honor the declared expiry horizon
        # plus three sessions, bounded at sixty sessions; malformed code is still rejected by the decider itself.
        try:
            for node in ast.parse(str(row["code"])).body:
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "NEEDS" for t in node.targets):
                    needs = ast.literal_eval(node.value)
                    snapshot["practice_max_sessions"] = min(60, math.ceil(float(needs["dte"][1]) * 5 / 7) + 3)
        except (SyntaxError, TypeError, ValueError, KeyError, IndexError):
            pass
        # EVIDENCE V3 (the owner's D2, Oct 2, 2026): every cohort frozen from this release on is a FORWARD LADDER cohort
        # (`league/live/ladder.py`): it practises its whole window (the constitution's `options_money.ladder.
        # max_sessions`, whatever its DTE), and it is an ENTRANT, a trial of its lineage and of the desk, recorded once
        # with its admission (the ladder's Benjamini-Hochberg counts every entrant of its trailing window).
        from .ladder import LADDER_VERSION, Rules

        snapshot["ladder"] = LADDER_VERSION
        snapshot["practice_max_sessions"] = Rules.from_constitution().max_sessions
        family, version = str(row["family"]), int(row["version"])
        with db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT admitted_at, first_day, snapshot, status, completed_day, reason, evaluator "
                             "FROM cohorts WHERE family=? AND version=?", (family, version)).fetchone()
            if old is not None and old[3] in ("active", "complete") and _evaluator_of(old[6], old[2]) != self.evaluator:
                # PRACTICE STARTS AGAIN ON A NEW EVALUATOR (the module docstring): the earlier cohort and its practice
                # row go to the archive, so this program's cohort, sessions and record are the new evaluator's alone.
                practice = _dicts(db.execute("SELECT * FROM practice WHERE family=? AND version=?", (family, version)))
                db.execute("INSERT INTO cohort_archive(family, version, evaluator, admitted_at, first_day, snapshot, "
                           "status, completed_day, reason, practice, archived_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                           (family, version, _evaluator_of(old[6], old[2]), old[0], old[1], old[2], "complete",
                            old[4] or day, old[5] if old[3] == "complete" else
                            "evaluator changed; its practice starts again under the new one",
                            json.dumps(practice[0], sort_keys=True, default=str) if practice else None, self.clock()))
                db.execute("DELETE FROM cohorts WHERE family=? AND version=?", (family, version))
                db.execute("DELETE FROM practice WHERE family=? AND version=?", (family, version))
            db.execute("INSERT OR IGNORE INTO cohorts(family, version, admitted_at, first_day, snapshot, evaluator) "
                       "VALUES(?,?,?,?,?,?)", (family, version, self.clock(), day,
                                               json.dumps(snapshot, sort_keys=True, allow_nan=False), self.evaluator))
            stored = db.execute("SELECT snapshot, status, admitted_at, first_day FROM cohorts WHERE family=? AND version=?",
                                (family, version)).fetchone()
            kept = json.loads(stored[0])
            if stored[1] == "active" and kept.get("ladder"):
                db.execute("INSERT OR IGNORE INTO entrants(family, version, run_sha, lineage, tier, evaluator, entered_at, "
                           "entered_day) VALUES(?,?,?,?,?,?,?,?)",
                           (family, version, kept.get("run_sha"), kept.get("lineage"), kept.get("tier") or "validated",
                            str(kept.get("practice_evaluator") or ""), float(stored[2]), str(stored[3])))
        if stored[1] != "active":
            raise ValueError("this practice snapshot has completed")
        return kept

    def cohort_allowed(self, expected: Mapping[str, Any]) -> bool:
        """Shadow-only identity check against an admitted snapshot, independent of the mutable research population."""
        if expected.get("observe") is not True or expected.get("tuition") or expected.get("band") != "gym":
            return False
        row = self._connect().execute("SELECT snapshot FROM cohorts WHERE family=? AND version=? AND status='active'",
                                     (str(expected["family"]), int(expected["version"]))).fetchone()
        if row is None:
            return False
        frozen = json.loads(row[0])
        return (frozen.get("practice_evaluator") == self.evaluator and frozen["code"] == expected.get("code")
                and frozen.get("params", {}) == expected.get("params", {}))

    def cohort_snapshot(self, family: str, version: int) -> dict | None:
        """The ACTIVE cohort's snapshot of (family, version) under the running evaluator, or None (the incubator's
        identity check: its real program is exactly this one)."""
        row = self._connect().execute("SELECT snapshot FROM cohorts WHERE family=? AND version=? AND status='active'",
                                     (str(family), int(version))).fetchone()
        if row is None:
            return None
        frozen = json.loads(row[0])
        return frozen if frozen.get("practice_evaluator") == self.evaluator else None

    def fail_cohort(self, family: str, version: int, *, day: str, reason: str) -> None:
        """A refused/disqualified program cannot benefit from more practice; preserve the reason and free its slot."""
        self._connect().execute("UPDATE cohorts SET status='failed', completed_day=?, reason=? WHERE family=? AND version=?",
                                (day, reason[:1000], family, version))

    # ------------------------------------------------------------------ the forward ladder's rows (`ladder.py`)
    def close_cohort(self, family: str, version: int, *, status: str, day: str, reason: str,
                     was: tuple[str, ...] = ("active",)) -> bool:
        """THE FORWARD LADDER's ending of a cohort: `status` "promoted" (its program trades real money at Probe),
        "failed" (it cannot be promoted) or "demoted" (its Probe went back to the Gym), from one of `was`. True when it
        moved."""
        if status not in ("promoted", "failed", "demoted"):
            raise ValueError(status)
        marks = ",".join("?" for _ in was)
        cur = self._connect().execute(f"UPDATE cohorts SET status=?, completed_day=?, reason=? WHERE family=? AND version=? "
                                      f"AND status IN ({marks})", (status, day, reason[:1000], str(family), int(version), *was))
        return cur.rowcount > 0

    def ladder_cohorts(self, *, statuses: tuple[str, ...] = ("active",)) -> list[dict[str, Any]]:
        """The forward ladder's cohorts in `statuses` (its snapshot marked `ladder`): [{family, version, first_day, status,
        snapshot}], the oldest admitted first."""
        marks = ",".join("?" for _ in statuses)
        out = []
        for family, version, first, status, snapshot in self._connect().execute(
                f"SELECT family, version, first_day, status, snapshot FROM cohorts WHERE status IN ({marks}) "
                "ORDER BY admitted_at, family, version", statuses).fetchall():
            snap = json.loads(snapshot)
            if isinstance(snap, dict) and snap.get("ladder"):
                out.append({"family": str(family), "version": int(version), "first_day": str(first), "status": str(status),
                            "snapshot": snap})
        return out

    def ladder_rows(self, family: str, version: int, *, evaluator: str, first_day: str,
                    through: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """One ladder cohort's record through the session day `through` (inclusive): (its practice row, or None; its
        PROGRAM closes under `evaluator` exited from `first_day` to `through`, forced (wind-down) closes left out, in
        record order: {seq, trade_id, pnl, max_loss, exit_day, body})."""
        db = self._connect()
        live = _dicts(db.execute("SELECT * FROM practice WHERE family=? AND version=?", (str(family), int(version))))
        trades = _dicts(db.execute(
            "SELECT seq, trade_id, pnl, max_loss, exit_day, body FROM trades WHERE family=? AND version=? AND evaluator=? "
            "AND COALESCE(forced, 0)=0 AND exit_day IS NOT NULL AND exit_day>=? AND exit_day<=? ORDER BY seq",
            (str(family), int(version), str(evaluator), str(first_day), str(through))))
        return (live[0] if live else None), trades

    def entrants(self, *, since: str) -> list[dict[str, Any]]:
        """Every ladder entrant that entered on or after the day `since`: [{family, version, run_sha, lineage, tier,
        evaluator, entered_day, p_value, p_day}]."""
        return _dicts(self._connect().execute(
            "SELECT family, version, run_sha, lineage, tier, evaluator, entered_day, p_value, p_day FROM entrants "
            "WHERE entered_day>=? ORDER BY entered_at, family, version", (str(since),)))

    def set_entrant_p(self, family: str, version: int, p: float, *, day: str, evaluator: str | None = None) -> None:
        """An entrant's latest one-sided p-value (the ladder's bootstrap; 1.0 without a full record), as of `day`: the
        entrant under `evaluator` (default: the running one)."""
        self._connect().execute("UPDATE entrants SET p_value=?, p_day=? WHERE family=? AND version=? AND evaluator=?",
                                (float(p), str(day), str(family), int(version), str(evaluator or self.evaluator)))

    def add_decision(self, row: Mapping[str, Any]) -> int:
        """One `ladder_decisions` row (the ladder's receipt): its id."""
        cur = self._connect().execute(
            "INSERT INTO ladder_decisions(day, family, version, run_sha, inputs, stats, p_value, bh_rank, bh_size, "
            "bh_threshold, verdict, reasons, binding, at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(row["day"]), str(row["family"]), int(row["version"]), row.get("run_sha"), str(row["inputs"]),
             json.dumps(row.get("stats") or {}, sort_keys=True, default=str), row.get("p_value"), row.get("bh_rank"),
             row.get("bh_size"), row.get("bh_threshold"), str(row["verdict"]),
             json.dumps(list(row.get("reasons") or []), default=str), int(bool(row.get("binding"))), self.clock()))
        return int(cur.lastrowid)

    def decision(self, receipt: int) -> dict[str, Any] | None:
        """One `ladder_decisions` row by its id (a receipt), or None."""
        rows = _dicts(self._connect().execute("SELECT id, day, family, version, run_sha, verdict, binding FROM "
                                              "ladder_decisions WHERE id=?", (int(receipt),)))
        return rows[0] if rows else None

    def set_verdict(self, receipt: int, verdict: str, reasons: Iterable[str]) -> None:
        """The verdict a receipt ends with (a promotion the swarm's store refused, say)."""
        self._connect().execute("UPDATE ladder_decisions SET verdict=?, reasons=? WHERE id=?",
                                (str(verdict), json.dumps(list(reasons), default=str), int(receipt)))

    def events(self, instance: str, family: str, version: int, account: str,
               rows: Iterable[Mapping[str, Any]]) -> bool:
        """Durable private decision/order/fill receipts. Retries after a restart are idempotent by account/event id."""
        rows = list(rows)
        if not rows:
            return True
        try:
            db = self._connect()
            with db:
                db.execute("BEGIN IMMEDIATE")
                db.executemany("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?,?,?,?)", [
                    (instance, account, int(r["id"]), family, version, r.get("day"), r.get("minute"), r["kind"],
                     json.dumps(dict(r, evaluator=self.evaluator), sort_keys=True, default=str), self.clock()) for r in rows])
            return True
        except Exception as exc:  # noqa: BLE001 - the account retains unexported receipts for retry
            if not self.practice_told and self.alert is not None:
                self.practice_told = True
                self.alert("warning", f"live: practice receipts could not be recorded ({type(exc).__name__}); retrying")
            return False

    def practice(self, rows: Iterable[Mapping[str, Any]]) -> bool:
        """One minute of the practice league: an upsert per practice account, all in one transaction. Each row:
        {family, version, tier, lineage, structure, roots, capital, account (the account's nonce), at, day (the session),
        equity (the account's, at the engine's mark), open_positions, open_mark_pnl, due, made, missed_quotes,
        missed_budget (0 or 1 each), status ("live" | "wound_down")}. A (family, version) seen for the first time starts
        its record (`first_at`: this minute). A remade account (a new nonce) continues it: its marked P&L restarts from the
        realized P&L of the earlier accounts. False when not written (alerted once; the next minute repairs it)."""
        rows = [dict(r) for r in rows]
        if not rows:
            return True
        try:
            db = self._connect()
            with db:
                db.execute("BEGIN IMMEDIATE")
                for r in rows:
                    self._upsert(db, r)
                now = self.clock()
                if now - self._pruned_at >= PRUNE_EVERY:
                    self._pruned_at = now
                    db.execute("DELETE FROM practice WHERE last_at < ?", (now - KEEP_DAYS * 86400.0,))
                    db.execute("DELETE FROM events WHERE recorded_at < ?", (now - KEEP_DAYS * 86400.0,))
            return True
        except Exception as exc:  # noqa: BLE001 - the practice record never stops the minute
            if not self.practice_told and self.alert is not None:
                self.practice_told = True
                try:
                    self.alert("warning", f"live: the practice league's record could not be written ({type(exc).__name__}); "
                                          "the next minute writes it again")
                except Exception:  # noqa: BLE001
                    pass
            return False

    @staticmethod
    def _upsert(db: sqlite3.Connection, r: Mapping[str, Any]) -> None:
        family, version = str(r["family"]), int(r["version"])
        at, day = float(r["at"]), str(r["day"])
        capital = float(r.get("capital") or 0.0)
        account = str(r.get("account") or "")
        counts = [int(bool(r.get(k))) for k in ("due", "made", "missed_quotes", "missed_budget", "missed_errors")]
        old = db.execute("SELECT sessions, minutes, last_day, account, base_pnl, peak_marked, drawdown_marked, tier, last_at, "
                         "decisions_due, decisions_made, open_mark_pnl, prior_day, prior_due, prior_made, prior_open_mark "
                         "FROM practice WHERE family=? AND version=?", (family, version)).fetchone()
        if old is not None and old[3] == account and int(float(old[8]) // 60) == int(at // 60):
            return  # a repeated minute/retry must not inflate session coverage
        if old is None or old[3] != account:
            # A new record, or a remade account: its equity starts at `capital` again, so the marked path carries on from
            # the realized P&L of the (family, version)'s other accounts.
            base = db.execute("SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE family=? AND version=? AND account != ?",
                              (family, version, account)).fetchone()[0]
        else:
            base = old[4]
        equity = _num(r.get("equity"))
        marked = float(base or 0.0) + ((equity - capital) if equity is not None else 0.0)
        tier = "validated" if r.get("tier") == "validated" else "train"
        if old is None:
            db.execute("INSERT INTO practice(family, version, tier, lineage, structure, roots, capital, first_at, first_day, "
                       "last_at, last_day, sessions, minutes, decisions_due, decisions_made, missed_quotes, missed_budget, missed_errors, "
                       "account, base_pnl, pnl_marked, peak_marked, drawdown_marked, open_positions, open_mark_pnl, status) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?,?,1,1,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (family, version, tier, r.get("lineage"), r.get("structure"),
                        json.dumps([str(x) for x in r.get("roots") or []]), capital, at, day, at, day, *counts, account,
                        float(base or 0.0), marked, max(0.0, marked), max(0.0, -marked),
                        int(r.get("open_positions") or 0), float(_num(r.get("open_mark_pnl")) or 0.0),
                        str(r.get("status") or "live")))
            return
        peak = max(float(old[5]), marked)
        drawdown = max(float(old[6]), peak - marked)
        # A new session day: the coverage and open mark its last session left, before this minute adds to them, stamped
        # with THIS day, the roll's (the incubator's record before today, `practice_record`, takes them only when the
        # roll is today's; a release that never rolls them leaves an older stamp, and the record says `intraday`).
        prior = (day, old[9], old[10], old[11]) if day != old[2] else tuple(old[12:16])
        db.execute("UPDATE practice SET last_at=?, last_day=?, sessions=sessions+?, minutes=minutes+1, "
                   "decisions_due=decisions_due+?, decisions_made=decisions_made+?, missed_quotes=missed_quotes+?, "
                   "missed_budget=missed_budget+?, missed_errors=missed_errors+?, account=?, base_pnl=?, pnl_marked=?, peak_marked=?, drawdown_marked=?, "
                   "open_positions=?, open_mark_pnl=?, status=?, tier=?, prior_day=?, prior_due=?, prior_made=?, "
                   "prior_open_mark=? WHERE family=? AND version=?",
                   (at, day, int(day != old[2]), *counts, account, float(base or 0.0), marked, peak, drawdown,
                    int(r.get("open_positions") or 0), float(_num(r.get("open_mark_pnl")) or 0.0),
                    str(r.get("status") or "live"), "validated" if "validated" in (tier, old[7]) else "train",
                    *prior, family, version))

    def close(self) -> None:
        try:
            if self.db is not None:
                self.db.close()
        except Exception:  # noqa: BLE001
            pass
        self.db = None


def _dicts(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    """A cursor's rows as dicts (the House's connection keeps plain tuples: no row factory is switched on it)."""
    names = [c[0] for c in cursor.description or ()]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _evaluator_of(column: Any, snapshot: Any) -> str | None:
    """A cohort row's practice evaluator: its `evaluator` column, else its snapshot's (a row written before the column,
    or by hand)."""
    if column is not None:
        return str(column)
    try:
        value = json.loads(snapshot).get("practice_evaluator")
    except (TypeError, ValueError, AttributeError):
        return None
    return None if value is None else str(value)


def _migrate(db: sqlite3.Connection) -> None:
    """The practice league's trade columns on a file written before them, filled from each trade's own row; and the
    cohorts' evaluator column (evidence v3), filled from each snapshot."""
    if "evaluator" not in {row[1] for row in db.execute("PRAGMA table_info(cohorts)")}:
        with db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("ALTER TABLE cohorts ADD COLUMN evaluator TEXT")
            for family, version, snapshot in db.execute("SELECT family, version, snapshot FROM cohorts").fetchall():
                db.execute("UPDATE cohorts SET evaluator=? WHERE family=? AND version=?",
                           (_evaluator_of(None, snapshot), family, version))
    columns = {row[1] for row in db.execute("PRAGMA table_info(practice)")}
    if "missed_errors" not in columns:
        db.execute("ALTER TABLE practice ADD COLUMN missed_errors INTEGER NOT NULL DEFAULT 0")
    for name, kind in PRIOR_COLUMNS:
        if name not in columns:
            db.execute(f"ALTER TABLE practice ADD COLUMN {name} {kind}")
    have = {row[1] for row in db.execute("PRAGMA table_info(trades)")}
    missing = [(name, kind) for name, kind in TRADE_COLUMNS if name not in have]
    if not missing:
        return
    with db:
        db.execute("BEGIN IMMEDIATE")
        for name, kind in missing:
            db.execute(f"ALTER TABLE trades ADD COLUMN {name} {kind}")
        for seq, body in db.execute("SELECT seq, body FROM trades").fetchall():
            try:
                t = json.loads(body)
            except (TypeError, ValueError):
                t = {}
            db.execute("UPDATE trades SET exit_day=?, reason=?, forced=?, evaluator=? WHERE seq=?",
                       (_day_of(t.get("exit_day")), str(t.get("exit_reason") or "") or None,
                        1 if t.get("forced") is True else 0, t.get("evaluator"), seq))


# ------------------------------------------------------------------------------------------------ the incubator's reads
def _read_only(root: str | Path) -> sqlite3.Connection | None:
    path = Path(root) / FILE
    if not path.exists():
        return None
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
    db.row_factory = sqlite3.Row
    return db


def cohort_rows(root: str | Path, *, since: str | None = None) -> list[dict[str, Any]] | None:
    """Every practice cohort, read-only (`mode=ro`, a one-second timeout), standard library only, never raising: [{family,
    version, first_day, status, reason, completed_day, snapshot (its immutable program row)}], oldest first; `since`: only
    the active ones and those completed on or after that day. [] without a record; None when it cannot be read."""
    try:
        db = _read_only(root)
        if db is None:
            return []
        try:
            if "cohorts" not in {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
                return []
            out = []
            where = "" if since is None else "WHERE status='active' OR completed_day>=? "
            for r in db.execute("SELECT family, version, first_day, status, reason, completed_day, snapshot FROM cohorts "
                                f"{where}ORDER BY admitted_at, family, version", () if since is None else (str(since),)):
                snapshot = json.loads(r["snapshot"])
                out.append({"family": str(r["family"]), "version": int(r["version"]), "first_day": str(r["first_day"]),
                            "status": str(r["status"]), "reason": r["reason"], "completed_day": r["completed_day"],
                            "snapshot": snapshot if isinstance(snapshot, dict) else {}})
            return out
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - the incubator takes no new pin on an unreadable record
        return None


def practice_record(root: str | Path, family: str, version: int, *, before: str, evaluator: str,
                    unit_cap: float = 50.0) -> dict[str, Any] | None:
    """One practice cohort's record for the incubator's first look and its re-checks (`money.practice_ok`): read-only
    (`mode=ro`, a one-second timeout), standard library only, NEVER raising (None on any error, or without the cohort).
    Everything is before `before` (a session day, ISO): today's closes and today's session are left out, and so are
    today's decisions and today's mark, whenever in the session it is read.

        sessions        the practice row's completed sessions (less today's); None (ineligible) when the practice row
                        began before the cohort did
        coverage        decisions made / due over the practice row before today (None before any was due);
                        decisions_due, _made
        closes_program  closed trades under `evaluator`, program-closed (not forced), exited before `before`
        pnl_program     their P&L (the engine's, after its fees and the House's shadow fill model)
        closes_all, pnl_all   the same with forced (wind-down) closes included
        open_mark       the practice row's open positions' P&L at the engine's mark at its last stepped minute before
                        today (a row stepped today: as its last session before today left it, `prior_*`, only when
                        they were rolled TODAY, `prior_day == before`)
        intraday        True when the row was stepped today and what it held before today is not known: no `prior_*`
                        (a row last rolled before release B's columns), or `prior_*` rolled on an earlier day (a
                        release without these columns, release A after a rollback, stepped it today: its `prior_*`
                        are an older session's); its coverage and open mark are then TODAY's, and no check may be
                        decided on them (the incubator's `_judge`: fail closed, deferred); False otherwise
        return_on_risk  pnl_all over the same trades' maximum loss (None without one)
        feasible        program closes whose one-lot unit (maximum loss a lot plus twice the fees a lot) is at most
                        `unit_cap`: whether it could ever open at the incubator's size
        first_day, status, reason, tier, structure, run_sha   the cohort's (and its snapshot's)

    The P&L is from the evaluator-filtered trades, never `practice.pnl_marked` (which rebases on any evaluator's)."""
    try:
        db = _read_only(root)
        if db is None:
            return None
        try:
            cohort = db.execute("SELECT first_day, status, reason, snapshot FROM cohorts WHERE family=? AND version=?",
                                (str(family), int(version))).fetchone()
            if cohort is None:
                return None
            snapshot = json.loads(cohort["snapshot"]) or {}
            live = db.execute("SELECT * FROM practice WHERE family=? AND version=?", (str(family), int(version))).fetchone()
            live = dict(live) if live is not None else None
            if live is None:
                sessions: int | None = 0
            elif str(live["first_day"]) < str(cohort["first_day"]):
                sessions = None
            else:
                sessions = int(live["sessions"]) - int(str(live["last_day"]) == str(before))
            due, made, mark, intraday = _before(live, str(before))
            trades = [dict(r) for r in db.execute(
                "SELECT pnl, max_loss, forced, body FROM trades WHERE family=? AND version=? AND evaluator=? "
                "AND exit_day IS NOT NULL AND exit_day<? ORDER BY seq", (str(family), int(version), str(evaluator), str(before)))]
        finally:
            db.close()
        program = [t for t in trades if not t["forced"]]

        def total(rows: list[dict]) -> float:
            return round(sum(float(t["pnl"] or 0.0) for t in rows), 6)

        losses = sum(float(t["max_loss"] or 0.0) for t in trades)
        feasible = 0
        for t in program:
            body = _body(t)
            qty = int(body.get("qty") or 0)
            if qty < 1:
                continue
            unit = float(t["max_loss"] or 0.0) / qty + 2 * float(body.get("fees") or 0.0) / qty
            if math.isfinite(unit) and 0 < unit <= float(unit_cap) + 1e-9:
                feasible += 1
        pnl_all = total(trades)
        return {"family": str(family), "version": int(version), "before": str(before), "evaluator": str(evaluator),
                "first_day": str(cohort["first_day"]), "status": str(cohort["status"]), "reason": cohort["reason"],
                "tier": snapshot.get("tier") or (live or {}).get("tier"),
                "structure": snapshot.get("structure") or (live or {}).get("structure"),
                "run_sha": snapshot.get("run_sha"), "practice_evaluator": snapshot.get("practice_evaluator"),
                "sessions": sessions, "decisions_due": due, "decisions_made": made,
                "coverage": round(made / due, 4) if due else None,
                "closes_program": len(program), "pnl_program": total(program),
                "closes_all": len(trades), "pnl_all": pnl_all,
                "open_mark": round(mark, 6), "intraday": intraday,
                "return_on_risk": round(pnl_all / losses, 6) if losses > 0 else None, "feasible": feasible}
    except Exception:  # noqa: BLE001 - no record is no eligibility
        return None


def _before(live: Mapping[str, Any] | None, before: str) -> tuple[int, int, float, bool]:
    """(decisions due, made, open mark, intraday) of a practice row as they stood before the session day `before`."""
    if live is None:
        return 0, 0, 0.0, False
    last = str(live["last_day"])
    if last < before:                                       # not stepped since: its values are all before today
        return (int(live["decisions_due"] or 0), int(live["decisions_made"] or 0),
                float(live.get("open_mark_pnl") or 0.0), False)
    if last == before and str(live["first_day"]) == before:
        return 0, 0, 0.0, False                             # first stepped today: nothing before it
    prior = live.get("prior_day")
    if last == before and prior is not None and str(prior) == before:
        # Rolled today, at today's first minute: its last session before today, whatever day that was.
        return (int(live.get("prior_due") or 0), int(live.get("prior_made") or 0),
                float(live.get("prior_open_mark") or 0.0), False)
    # Stepped today (or after `before`) with no value from before it, or with `prior_*` rolled on an earlier day (a
    # release that never rolls them stepped it today: they are an older session's): today's, said so.
    return (int(live["decisions_due"] or 0), int(live["decisions_made"] or 0), float(live.get("open_mark_pnl") or 0.0),
            True)


# ------------------------------------------------------------------------------------------------ the summary
def practice_summary(root: str | Path, *, sessions: int | None = 10) -> dict[str, Any]:
    """The practice league as research and the site read it: read-only (`mode=ro`, a one-second timeout), standard library
    only, NEVER raising ({} on any error, a missing file or a file from before the practice table).

    The window is the last `sessions` session days on record (None: all of them). One row per (family, version) with a
    closed trade or a live minute in it:

        family, version, tier, lineage, structure, roots, status ("live" | "wound_down"), first_day, last_day
        sessions, minutes, coverage (decisions made / due; None before any was due)   its whole record
        trades, forced, pnl_usd, max_loss_usd, return_on_risk (P&L / maximum loss)      closed in the window, forced
                                                                                         (wind-down) closes included
        drawdown_realized_usd   the largest drop of cumulative realized P&L, in close order, in the window
        drawdown_marked_usd     the largest drop of its per-minute marked P&L from its peak, its whole record
        open_positions, open_mark_pnl_usd                                               now, at the engine's mark
        program {trades, wins, pnl_usd, days, t_trade, t_daily, returns, daily}         program-closed trades only
                                                                                         (the feedback's statistics)

    `t_trade` is the t of the per-trade return on maximum loss (None below 3 trades); `t_daily` the t of the daily return
    (the day's per-trade returns summed per exit day; None below 2 days). A trade recorded before the practice table
    (no practice row) is listed under its own family and version as tier "validated" (the only tier then)."""
    path = Path(root) / FILE
    if not path.exists():
        return {}
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        try:
            return _summary(db, sessions)
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - research and the site go without it
        return {}


def _summary(db: sqlite3.Connection, sessions: int | None) -> dict[str, Any]:
    db.row_factory = sqlite3.Row
    live = {(str(r["family"]), int(r["version"])): dict(r) for r in db.execute("SELECT * FROM practice")}
    # A trade's session is its exit day (every trade since the practice table has one; the migration filled the rest);
    # its entry day only when neither says. The trades' bodies are read only for a (family, version) with no practice row.
    close = "COALESCE(exit_day, day, '')"
    days = sorted({str(r["last_day"]) for r in live.values()} | {str(r["first_day"]) for r in live.values()}
                  | {str(r[0]) for r in db.execute(f"SELECT DISTINCT {close} FROM trades") if r[0]})
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "events" in tables:
        days = sorted(set(days) | {str(r[0]) for r in db.execute("SELECT DISTINCT day FROM events") if r[0]})
    if sessions is not None and int(sessions) > 0 and len(days) > int(sessions):
        since = days[-int(sessions)]
    else:
        since = days[0] if days else ""
    keyed: dict[tuple[str, int], dict[str, Any]] = {}
    for key, r in live.items():
        if str(r["last_day"]) >= since:
            keyed[key] = {"live": r, "trades": []}
    evaluator = "evaluator" if "evaluator" in {r[1] for r in db.execute("PRAGMA table_info(trades)")} else "NULL"
    for t in db.execute(f"SELECT seq, family, version, pnl, max_loss, forced, {evaluator} AS evaluator, {close} AS close_day FROM trades "
                        f"WHERE {close} >= ? ORDER BY seq", (since,)):
        t = dict(t)
        key = (str(t["family"]), int(t["version"] or 0))
        if key not in keyed:
            keyed[key] = {"live": live.get(key), "trades": []}
        keyed[key]["trades"].append(t)
    for key, part in keyed.items():
        if part["live"] is None:
            part["bodies"] = [_body(dict(r)) for r in db.execute(
                "SELECT body FROM trades WHERE family=? AND version IS ? ORDER BY seq", (key[0], key[1] or None))]
    # Old shadow trades remain in the realized headline, but cannot become feedback for a new evaluator's cohort.
    if "cohorts" in tables:
        for cohort in db.execute("SELECT family, version, snapshot FROM cohorts"):
            key = (str(cohort["family"]), int(cohort["version"]))
            if key in keyed:
                keyed[key]["evaluator"] = json.loads(cohort["snapshot"]).get("practice_evaluator")
    rows = [_row(key, part) for key, part in keyed.items()]
    rows.sort(key=lambda r: (-r["trades"], r["family"], r["version"]))
    return {"sessions": len([d for d in days if d >= since]), "since": since or None, "rows": rows}


def _row(key: tuple[str, int], part: Mapping[str, Any]) -> dict[str, Any]:
    fam, version = key
    live, trades = part["live"], part["trades"]
    bodies = part.get("bodies") or []
    body0 = bodies[0] if bodies else {}
    closes = sorted(trades, key=lambda t: (t["close_day"], t["seq"]))
    pnl = [float(t["pnl"] or 0.0) for t in closes]
    losses = [float(t["max_loss"] or 0.0) for t in closes]
    cum = peak = drawdown = 0.0
    for p in pnl:
        cum += p
        peak = max(peak, cum)
        drawdown = max(drawdown, peak - cum)
    eligible_evaluator = part.get("evaluator")
    program = [t for t in closes if not t.get("forced") and
               (eligible_evaluator is None or t.get("evaluator") == eligible_evaluator)]
    returns = [float(t["pnl"] or 0.0) / float(t["max_loss"]) for t in program if (t["max_loss"] or 0) > 0]
    daily: dict[str, list[float]] = {}
    for t in program:
        if (t["max_loss"] or 0) > 0:
            d = daily.setdefault(t["close_day"], [0.0, 0.0])
            d[0] += float(t["pnl"] or 0.0) / float(t["max_loss"])
            d[1] += float(t["pnl"] or 0.0)
    due = int(live["decisions_due"]) if live else 0
    return {
        "family": fam, "version": version,
        "tier": (live or {}).get("tier") or "validated", "lineage": (live or {}).get("lineage"),
        "structure": (live or {}).get("structure") or body0.get("type"),
        "roots": _roots(live) if live else sorted({str(b.get("root") or "") for b in bodies} - {""}),
        "status": (live or {}).get("status") or "wound_down",
        "first_day": (live or {}).get("first_day") or (closes[0]["close_day"] if closes else None),
        "last_day": max([str((live or {}).get("last_day") or "")] + [t["close_day"] for t in closes]) or None,
        "sessions": int(live["sessions"]) if live else len({t["close_day"] for t in closes}),
        "minutes": int(live["minutes"]) if live else 0,
        "coverage": round(int(live["decisions_made"]) / due, 4) if live and due else None,
        "decisions_due": due, "decisions_made": int(live["decisions_made"]) if live else 0,
        "missed_quotes": int(live["missed_quotes"]) if live else 0, "missed_budget": int(live["missed_budget"]) if live else 0,
        "missed_errors": int(live.get("missed_errors") or 0) if live else 0,
        "trades": len(closes), "forced": sum(1 for t in closes if t.get("forced")),
        "unmatched_evaluator": sum(1 for t in closes if not t.get("forced") and eligible_evaluator is not None
                                   and t.get("evaluator") != eligible_evaluator),
        "pnl_usd": round(sum(pnl), 2), "max_loss_usd": round(sum(losses), 2),
        "return_on_risk": round(sum(pnl) / sum(losses), 4) if sum(losses) > 0 else None,
        "drawdown_realized_usd": round(drawdown, 2),
        "drawdown_marked_usd": round(float(live["drawdown_marked"]), 2) if live else round(drawdown, 2),
        "open_positions": int(live["open_positions"]) if live else 0,
        "open_mark_pnl_usd": round(float(live["open_mark_pnl"]), 2) if live else 0.0,
        "program": {
            "trades": len(program), "wins": sum(1 for t in program if float(t["pnl"] or 0.0) > 0),
            "pnl_usd": round(sum(float(t["pnl"] or 0.0) for t in program), 2), "days": len(daily),
            "t_trade": t_stat(returns, 3), "t_daily": t_stat([v[0] for _, v in sorted(daily.items())], 2),
            "returns": [round(x, 6) for x in returns],
            "daily": [[d, round(v[0], 6), round(v[1], 2)] for d, v in sorted(daily.items())],
        },
    }


def t_stat(values: list[float], minimum: int) -> float | None:
    """The t of the mean of `values` (None below `minimum` values or with no spread)."""
    n = len(values)
    if n < max(2, int(minimum)):
        return None
    mean = sum(values) / n
    var = sum((x - mean) ** 2 for x in values) / (n - 1)
    if not var > 0 or not math.isfinite(var):
        return None
    return round(mean / math.sqrt(var / n), 4)


def _roots(live: Mapping[str, Any]) -> list[str]:
    try:
        value = json.loads(live.get("roots") or "[]")
    except (TypeError, ValueError):
        return []
    return [str(x) for x in value] if isinstance(value, list) else []


def _body(t: Mapping[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(t.get("body") or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _day_of(value: Any) -> str | None:
    text = str(value or "")
    return text[:10] if len(text) >= 10 and text[4] == "-" and text[7] == "-" else None


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


__all__ = ["ObserveStore", "practice_summary", "practice_record", "cohort_rows", "t_stat", "FILE", "MAX_ROWS", "KEEP_DAYS",
           "HOLD"]
