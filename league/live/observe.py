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
  cohort whose Probe goes back to the Gym is `demoted`. Its `ladder_state` (JSON; empty until its first checkpoint) says
  which of the ladder's CHECKPOINTS it has been judged at (`judged`: each with its day and its receipt) and whether it
  is LATCHED (`latch`: it met L1-L5 at that checkpoint on that day, by that receipt, and waits for its Validation
  verdict or the pre-filter's answer, `waits`; once its ANSWER is read, `waits` is null and `answer` names the day,
  the receipt and the verdict; a latched cohort is never judged again). THE WINDOW HOLD (`ladder_window`): a ladder
  cohort ends `complete` at its window, but one whose latch still waits is kept active, in its slot, until the
  constitution's `answer_sessions` sessions have passed since its checkpoint's day (the ladder ends it at its answer,
  or at that limit without one), and one never judged at its last checkpoint (the House missed that session's end) is
  kept that many sessions past its window, to be judged at the first session's end it runs. Each row names the
  practice evaluator it was frozen under (`evaluator`) and its entrant (`entrant`). THE RE-ENTRY RULE (below) says
  which cohort a release may start again.
- `events`: private decision, coverage, intent, rejection, order, quote and fill/slippage receipts, idempotent across
  restarts. Unwritten receipts live in the saved shadow account and retry; the bounded outage buffer reports drops.
- `entrants`: one row per ladder COHORT (`id`; the cohort's row names it, `cohorts.entrant`, and so does its archive
  row): every cohort is its own entrant, a trial of its lineage and of the desk (the ladder's Benjamini-Hochberg counts
  every entrant of its trailing window), written with its admission and never reused: a program frozen again is
  another row, whatever evaluator it is frozen under (one that came back included). It holds its latest one-sided
  p-value. Only a CHECKPOINT's judgement writes it (`p_checkpoint`: that checkpoint), with its receipt and the cohort's
  state in one transaction (`add_decision`), at most once a checkpoint and never at an earlier one: an entrant without
  a `p_checkpoint` has no judged p-value (the ladder counts it at 1).
- `ladder_decisions`: the ladder's receipts (`league/live/ladder.py`): a checkpoint's judgement names it
  (`checkpoint`: the sessions the constitution names it by); a latched cohort's ANSWER (`add_answer`, written with
  its latch and its ending in one transaction), a pending promotion (`promote_pending`, settled once its band landed:
  `settle_answer`) and a demotion name none.
- `cohort_archive`: the cohorts THE RE-ENTRY RULE started again, each as it ended, with its practice row as it stood
  (JSON), its `ladder_state`, its entrant and `accounts` (every practice account on record for its program when it
  was archived), kept for good.

THE RE-ENTRY RULE (Oct 3, 2026; `changed_reason`, `ObserveStore.cohort_candidates`, `freeze`). A (family, version) is
frozen again, as a NEW cohort and a NEW entrant, only when its last cohort was INTERRUPTED: active, still
inside its window and not yet judged with a final verdict (not judged at its last checkpoint, and not latched: a
latched checkpoint's verdict is final) when a release changed the practice evaluator. It is decided by the cohort's
RECORDED ENDING, never by comparing evaluators:

- this release ends an active cohort of another evaluator as one of three: `EVALUATOR_CHANGED` (interrupted: it is
  offered again), `EVALUATOR_CHANGED_FINAL` (its checkpoint's verdict was final) or `EVALUATOR_CHANGED_WINDOW` (the
  calendar sessions behind it had reached its window: those from its first day to before that day, and that day's
  own once that session has closed, whether or not the cohort practised it: the House's clock says so,
  `cohort_candidates(session_over=)`, and so does a cohort that practised that day when the House is outside the
  session); the last two never re-enter;
- the rule before the ladder (release V3-A part 1 and every release before it) ends EVERY active cohort of another
  evaluator in place as `EVALUATOR_CHANGED_BEFORE`, whatever its window or its checkpoints (a rollback to that
  release writes it on this release's cohorts). Such a row is read by what it records itself: it re-enters only when
  its `ladder_state` holds no latch and no judgement at its last checkpoint and its calendar sessions from
  `first_day` through `completed_day` (the day that rule ended it: the row cannot say whether that day's session
  was still running, so it is counted) are under its window. So a rollback followed by this same release starts the
  interrupted programs again and no finished window;
- every other ending is final for that version: a window that ended (judged, unjudged or unanswered), a cohort the
  ladder failed, promoted or demoted, a failed cohort of any kind, an observation target or window of the old rule.

The interrupted row, with its practice row, moves to `cohort_archive`; the new cohort starts with no `ladder_state`,
its own first day and no practice row.

THE COHORT'S OWN RECORD (`earlier_accounts`, `own_closes`). A cohort's record is its own practice accounts' alone, from
its own first day. An account on record for the program when its earlier cohort was archived (the archive's
`accounts`) is that earlier cohort's for good: its later closes (its wind-down, a program close still in flight) and
its practice minutes are never the new cohort's, under any evaluator, so an evaluator that comes back the same day
brings nothing of the first cohort with it. The House winds such an account down (`ObserveStore.earlier_account`,
`OptionsLive._earlier_cohort`) and makes a new one once it is flat; the new cohort's practice row begins at that
account's first minute, its marked P&L from zero. `ladder_rows`, `practice_record` and the swarm's two cohort reads
(`league/swarm/practice.py`, `league/swarm/incubator.py`) read by both halves of this rule. The summary's program
statistics (`practice_summary`: a research signal over a window of sessions, never a record anything is judged on)
leave out an earlier cohort's accounts and every close under another evaluator, and hold no floor at the cohort's
first day.

WHO READS IT. THE FORWARD LADDER (evidence v3, the owner's D2 of Oct 2, 2026; `league/live/ladder.py`) reads a ladder
cohort's own program closes under its own evaluator as the promotion evidence to Probe; nothing else that promotes reads
it (not the gate, the verifier, the bands' reads, the money table's forward record or Profit). The swarm reads
`practice_summary` (read-only) as a RESEARCH signal (`league/swarm/practice.py`: the strategist's
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
    ladder_state TEXT, entrant INTEGER, PRIMARY KEY (family, version));
CREATE TABLE IF NOT EXISTS cohort_archive (
    family TEXT NOT NULL, version INTEGER NOT NULL, evaluator TEXT, admitted_at REAL NOT NULL, first_day TEXT NOT NULL,
    snapshot TEXT NOT NULL, status TEXT NOT NULL, completed_day TEXT, reason TEXT, practice TEXT,
    archived_at REAL NOT NULL, ladder_state TEXT, entrant INTEGER, accounts TEXT);
CREATE INDEX IF NOT EXISTS cohort_archive_program ON cohort_archive(family, version);
CREATE TABLE IF NOT EXISTS events (
    instance TEXT NOT NULL, account TEXT NOT NULL, event_id INTEGER NOT NULL, family TEXT NOT NULL,
    version INTEGER NOT NULL, day TEXT, minute INTEGER, kind TEXT NOT NULL, body TEXT NOT NULL,
    recorded_at REAL NOT NULL, PRIMARY KEY(instance, account, event_id));
CREATE INDEX IF NOT EXISTS events_family_day ON events(family, day);
CREATE INDEX IF NOT EXISTS events_day ON events(day);
CREATE TABLE IF NOT EXISTS entrants (
    id INTEGER PRIMARY KEY AUTOINCREMENT, family TEXT NOT NULL, version INTEGER NOT NULL, run_sha TEXT, lineage TEXT,
    tier TEXT, evaluator TEXT NOT NULL, entered_at REAL NOT NULL, entered_day TEXT NOT NULL, p_value REAL, p_day TEXT,
    p_checkpoint INTEGER);
CREATE INDEX IF NOT EXISTS entrants_day ON entrants(entered_day);
CREATE TABLE IF NOT EXISTS ladder_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, family TEXT NOT NULL, version INTEGER NOT NULL,
    run_sha TEXT, inputs TEXT NOT NULL, stats TEXT NOT NULL, p_value REAL, bh_rank INTEGER, bh_size INTEGER,
    bh_threshold REAL, verdict TEXT NOT NULL, reasons TEXT, binding INTEGER NOT NULL, at REAL NOT NULL,
    checkpoint INTEGER);
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
#: Columns the forward ladder's checkpoints added (Oct 3, 2026), NULL on every row written before them: a cohort's
#: `ladder_state` (kept in the archive too), the checkpoint an entrant's p-value is of, the checkpoint a receipt judged;
#: and those of THE RE-ENTRY RULE: a cohort's entrant (kept in the archive too) and the archive's accounts.
LADDER_COLUMNS = (("cohorts", "ladder_state", "TEXT"), ("cohort_archive", "ladder_state", "TEXT"),
                  ("entrants", "p_checkpoint", "INTEGER"), ("ladder_decisions", "checkpoint", "INTEGER"),
                  ("cohorts", "entrant", "INTEGER"), ("cohort_archive", "entrant", "INTEGER"),
                  ("cohort_archive", "accounts", "TEXT"))
#: The entrants' columns but their `id` (a file whose entrants were keyed by family, version and evaluator is rebuilt
#: with one: `_migrate`).
ENTRANT_COLUMNS = ("family", "version", "run_sha", "lineage", "tier", "evaluator", "entered_at", "entered_day", "p_value",
                   "p_day", "p_checkpoint")
#: What a latched ladder cohort waits for (`cohorts.ladder_state`'s latch), in the order it waits for them.
LATCH_WAITS = ("validation", "prefilter")
#: How a latched cohort's answer can end it (`ObserveStore.add_answer`, `settle_answer`).
ANSWER_ENDS = ("failed", "complete", "promoted")
#: A promotion's receipt until its band landed in the swarm's store (`ObserveStore.settle_answer`): never a `promote`.
PROMOTE_PENDING = "promote_pending"
#: How a ladder cohort's window ends it (`ladder_window`).
WINDOW_ENDED = "ladder: its practice window ended"
WINDOW_UNJUDGED = "ladder: its practice window ended and its last checkpoint was never judged"
WINDOW_UNANSWERED = "ladder: its latch had no answer within the sessions it may wait"
#: How an evaluator change ends an active cohort (THE RE-ENTRY RULE, `changed_reason`): interrupted, so offered again;
#: or never again under its version, its checkpoint's verdict final, or its window ended.
EVALUATOR_CHANGED = "evaluator changed; its practice starts again under the new one"
EVALUATOR_CHANGED_FINAL = "evaluator changed; its checkpoint's verdict was final: it never practises again under this version"
EVALUATOR_CHANGED_WINDOW = "evaluator changed; its practice window had ended: it never practises again under this version"
#: What the rule before the ladder (release V3-A part 1's `cohort_candidates`, and every release's before it) writes,
#: in place, on EVERY active cohort of another evaluator, byte for byte: such a row re-enters only by what it records
#: itself (`ObserveStore._reenters`).
EVALUATOR_CHANGED_BEFORE = "evaluator changed; a new version needs fresh practice"
#: The old rule's observation target and window (`cohort_candidates`' defaults), a cohort frozen before the ladder.
COHORT_MIN_SESSIONS, COHORT_MAX_SESSIONS = 3, 10


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
        # The old rule's window as the House last gave it (`cohort_candidates`): THE RE-ENTRY RULE reads a cohort frozen
        # before the ladder by it, the same in `freeze`.
        self._windows = (COHORT_MIN_SESSIONS, COHORT_MAX_SESSIONS)
        # {(family, version): the accounts of its earlier cohorts} (`_earlier`), read once and again after a `freeze`
        # that archives one: only this store writes the archive.
        self._earlier_cache: dict[tuple[str, int], frozenset[str]] = {}
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
                          session_over: bool = False, min_sessions: int = COHORT_MIN_SESSIONS, min_trades: int = 10,
                          max_sessions: int = COHORT_MAX_SESSIONS,
                          keep: Iterable[tuple[str, int]] = frozenset()) -> list[dict]:
        """Keep admitted immutable snapshots across research revisions and retirement. An ended snapshot never
        re-enters, THE RE-ENTRY RULE apart (the module docstring): an active cohort of another evaluator is ended
        here, by `changed_reason`, and only one that was INTERRUPTED (this release's `EVALUATOR_CHANGED`, or the
        earlier rule's ending on a row that itself shows the interruption: `_reenters`) is offered again from `current`,
        for `freeze` to make a new cohort and a new entrant of. `session_over`: the House's clock says `day`'s session
        has closed (outside the session only), so that session is behind every cohort an evaluator change ends here,
        practised or not. A cohort finishes between sessions after enough observed days and program closes, or its
        bounded calendar-session window; capacity/pressure switches still apply in the caller. This is shadow
        authority only.
        A FORWARD LADDER cohort has no observation target and ends at its window, THE WINDOW HOLD apart
        (`ladder_window`: a latch that still waits for its answer, or a last checkpoint not judged yet).
        `keep` (L2', the incubator's: (family, version) of cohorts whose first look passed, while `live.incubator` is on):
        such a cohort is not completed at its observation target; its window, an evaluator change or a failure still
        end it. Empty, this is exactly the league's own rule. `HOLD`: no cohort is completed at its target this pass."""
        hold = keep is HOLD
        keep = {(str(f), int(n)) for f, n in keep}
        from ..swarm.bands import priority

        db = self._connect()
        self._windows = (int(min_sessions), int(max_sessions))
        current = [dict(r) for r in current]
        offered = {(str(r["family"]), int(r["version"])) for r in current}
        frozen, seen = [], set()
        rows = db.execute("SELECT family, version, first_day, snapshot, status, ladder_state, completed_day, reason "
                          "FROM cohorts ORDER BY admitted_at, family")
        for family, version, first, snapshot, status, state, ended, ending in rows.fetchall():
            if status != "active":
                # Never again, THE RE-ENTRY RULE apart: read by its recorded ending (only where it is offered at all).
                if (family, version) in offered and not self._reenters(status, ending, first, ended, snapshot, state):
                    seen.add((family, version))
                continue
            row = json.loads(snapshot)
            if row.get("practice_evaluator") != self.evaluator:
                # Outside the session, today's session is behind a cohort once it has closed: the House's clock says so
                # (a window is calendar sessions, practised or not), and so does a cohort that practised today (it
                # cannot have before the open). The stricter of the two readings holds.
                over = not in_session and (bool(session_over) or db.execute(
                    "SELECT 1 FROM practice WHERE family=? AND version=? AND last_day=?",
                    (family, version, day)).fetchone() is not None)
                reason = changed_reason(first, day, row, state, session_over=over, min_sessions=min_sessions,
                                        max_sessions=max_sessions)
                db.execute("UPDATE cohorts SET status='complete', completed_day=?, reason=? WHERE family=? AND version=?",
                           (day, reason, family, version))
                if reason != EVALUATOR_CHANGED:
                    seen.add((family, version))  # its verdict was final, or its window had ended: never again
                continue  # interrupted: offered again from `current`, frozen as a new cohort and a new entrant
            seen.add((family, version))
            # THE FORWARD LADDER's cohorts (evidence v3, `league/live/ladder.py`): no observation target ends one; it runs
            # until the ladder promotes it or fails it, or its own practice window (`practice_max_sessions`, at most 60),
            # THE WINDOW HOLD apart (`ladder_window`).
            ladder = bool(row.get("ladder"))
            window = cohort_window(row, min_sessions=min_sessions, max_sessions=max_sessions)
            reason = None
            if in_session and first < day:
                elapsed = _sessions_before(first, day)
                if ladder:
                    if elapsed >= window:
                        window, why = ladder_window(
                            window, state, sessions_through=lambda d, first=first: _sessions_before(first, _day_after(d)),
                            answer_sessions=answer_sessions())
                        if elapsed >= window:
                            reason = why
                else:
                    evidence = db.execute("SELECT sessions, last_day, open_positions FROM practice WHERE family=? "
                                          "AND version=?", (family, version)).fetchone()
                    completed = int(evidence[0]) - int(evidence[1] == day) if evidence else 0
                    trades = db.execute("SELECT COUNT(*) FROM trades WHERE family=? AND version=? AND forced=0 "
                                        "AND evaluator=? AND exit_day<?", (family, version, self.evaluator, day)).fetchone()[0]
                    if (completed >= max(1, min_sessions) and trades >= max(1, min_trades) and evidence and evidence[2] == 0
                            and not hold and (family, int(version)) not in keep):
                        reason = "observation target reached"
                    elif elapsed >= window:
                        reason = "maximum session window reached"
            if reason:
                db.execute("UPDATE cohorts SET status='complete', completed_day=?, reason=? WHERE family=? AND version=?",
                           (day, reason, family, version))
                continue
            row["practice_frozen"] = True
            frozen.append(row)
        held = {r["family"] for r in frozen}
        frozen.sort(key=priority)
        return frozen + [r for r in current if r["family"] not in held and (r["family"], int(r["version"])) not in seen]

    def _reenters(self, status: Any, reason: Any, first_day: Any, completed_day: Any, snapshot: Any, state: Any) -> bool:
        """THE RE-ENTRY RULE (the module docstring), by an ended cohort row's RECORDED ENDING and never its evaluator:
        True only for a `complete` row an evaluator change interrupted. This release's `EVALUATOR_CHANGED` says so
        itself (`changed_reason` read the row when it was written). The earlier rule's `EVALUATOR_CHANGED_BEFORE` says
        only that the cohort was active: the row is read as `changed_reason` would have read it on the day it was ended
        (`completed_day`), by its own `first_day`, snapshot and `ladder_state`, with that day's own session counted
        behind it (the row cannot say whether the session was still running when that rule ended it: the stricter
        reading holds); a row that cannot be read never re-enters."""
        if status != "complete":
            return False
        if reason == EVALUATOR_CHANGED:
            return True
        if reason != EVALUATOR_CHANGED_BEFORE or not completed_day:
            return False
        try:
            snap = json.loads(snapshot)
            return isinstance(snap, dict) and changed_reason(
                str(first_day), str(completed_day), snap, state, session_over=True, min_sessions=self._windows[0],
                max_sessions=self._windows[1]) == EVALUATOR_CHANGED
        except (TypeError, ValueError):
            return False

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
            old = db.execute("SELECT admitted_at, first_day, snapshot, status, completed_day, reason, evaluator, "
                             "ladder_state, entrant FROM cohorts WHERE family=? AND version=?", (family, version)).fetchone()
            if old is not None and old[3] == "active" and _evaluator_of(old[6], old[2]) != self.evaluator:
                # An active cohort of another evaluator is ended here as `cohort_candidates` ends it, by the same rule (the
                # House freezes only inside the session: `day`'s own session is still running, so it is not behind it).
                ending = changed_reason(str(old[1]), day, json.loads(old[2]), old[7], min_sessions=self._windows[0],
                                        max_sessions=self._windows[1])
                db.execute("UPDATE cohorts SET status='complete', completed_day=?, reason=? WHERE family=? AND version=?",
                           (day, ending, family, version))
                old = (*old[:3], "complete", day, ending, *old[6:])
            if old is not None and self._reenters(old[3], old[5], old[1], old[4], old[2], old[7]):
                # THE RE-ENTRY RULE (the module docstring): the interrupted cohort and its practice row go to the archive,
                # with its entrant and every account on record for the program (never the new cohort's: THE COHORT'S OWN
                # RECORD), so this program's cohort, entrant, sessions and record are the new cohort's alone.
                practice = _dicts(db.execute("SELECT * FROM practice WHERE family=? AND version=?", (family, version)))
                db.execute("INSERT INTO cohort_archive(family, version, evaluator, admitted_at, first_day, snapshot, "
                           "status, completed_day, reason, practice, archived_at, ladder_state, entrant, accounts) "
                           "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (family, version, _evaluator_of(old[6], old[2]), old[0], old[1], old[2], old[3], old[4], old[5],
                            json.dumps(practice[0], sort_keys=True, default=str) if practice else None, self.clock(),
                            old[7], old[8], json.dumps(_accounts(db, family, version))))
                db.execute("DELETE FROM cohorts WHERE family=? AND version=?", (family, version))
                db.execute("DELETE FROM practice WHERE family=? AND version=?", (family, version))
                self._earlier_cache.pop((family, version), None)
            db.execute("INSERT OR IGNORE INTO cohorts(family, version, admitted_at, first_day, snapshot, evaluator) "
                       "VALUES(?,?,?,?,?,?)", (family, version, self.clock(), day,
                                               json.dumps(snapshot, sort_keys=True, allow_nan=False), self.evaluator))
            stored = db.execute("SELECT snapshot, status, admitted_at, first_day, entrant FROM cohorts WHERE family=? AND "
                                "version=?", (family, version)).fetchone()
            kept = json.loads(stored[0])
            if stored[1] == "active" and kept.get("ladder") and stored[4] is None:
                # EACH COHORT IS ITS OWN ENTRANT: a new row with its admission, named by the cohort's own row.
                entrant = db.execute(
                    "INSERT INTO entrants(family, version, run_sha, lineage, tier, evaluator, entered_at, entered_day) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (family, version, kept.get("run_sha"), kept.get("lineage"), kept.get("tier") or "validated",
                     str(kept.get("practice_evaluator") or ""), float(stored[2]), str(stored[3]))).lastrowid
                db.execute("UPDATE cohorts SET entrant=? WHERE family=? AND version=?", (int(entrant), family, version))
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

    def fail_cohort(self, family: str, version: int, *, day: str, reason: str) -> bool:
        """A refused/disqualified program cannot benefit from more practice; preserve the reason and free its slot. Only
        an ACTIVE cohort is failed (True when it moved): one the ladder promoted or demoted, or that already ended,
        keeps its own ending (a wind-down that fails, or a sweep that read it while it was active, changes nothing)."""
        cur = self._connect().execute("UPDATE cohorts SET status='failed', completed_day=?, reason=? WHERE family=? AND "
                                      "version=? AND status='active'", (day, reason[:1000], family, version))
        return cur.rowcount > 0

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
        snapshot, state (`ladder_state`), entrant (its own `entrants` row's id)}], the oldest admitted first."""
        marks = ",".join("?" for _ in statuses)
        out = []
        for family, version, first, status, snapshot, state, entrant in self._connect().execute(
                "SELECT family, version, first_day, status, snapshot, ladder_state, entrant FROM cohorts "
                f"WHERE status IN ({marks}) ORDER BY admitted_at, family, version", statuses).fetchall():
            snap = json.loads(snapshot)
            if isinstance(snap, dict) and snap.get("ladder"):
                out.append({"family": str(family), "version": int(version), "first_day": str(first), "status": str(status),
                            "snapshot": snap, "state": _ladder_state(state),
                            "entrant": None if entrant is None else int(entrant)})
        return out

    def ladder_state(self, family: str, version: int) -> dict[str, Any]:
        """A cohort's CHECKPOINT state (the module docstring): {judged: {checkpoint: {day, receipt}}, latch: {checkpoint,
        day, receipt, waits ("validation" | "prefilter" | None once its answer was read), answer} | None}. Empty for a
        cohort never judged at a checkpoint, and without a cohort."""
        row = self._connect().execute("SELECT ladder_state FROM cohorts WHERE family=? AND version=?",
                                      (str(family), int(version))).fetchone()
        return _ladder_state(row[0] if row is not None else None)

    def move_latch(self, family: str, version: int, *, waits: str | None,
                   answer: Mapping[str, Any] | None = None) -> bool:
        """A latched active cohort's wait moves on, never back: from "validation" to "prefilter" (its Validation verdict
        came), or to None with its `answer` (what was read: {day, receipt, verdict}; nothing waits any more, and it is
        still never judged again; the ladder writes that with its receipt, `add_answer`). True when it moved; False,
        nothing written, without such a cohort, without a latch, or when its latch does not wait for something
        earlier."""
        if waits is not None and waits not in LATCH_WAITS:
            raise ValueError(waits)
        db = self._connect()
        with db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT ladder_state FROM cohorts WHERE family=? AND version=? AND status='active'",
                             (str(family), int(version))).fetchone()
            state = _ladder_state(row[0] if row is not None else None)
            latch = state["latch"]
            if latch is None or latch.get("waits") not in LATCH_WAITS:
                return False
            if waits is not None and LATCH_WAITS.index(waits) <= LATCH_WAITS.index(latch["waits"]):
                return False
            latch["waits"] = waits
            if waits is None:
                latch["answer"] = dict(answer or {})
            db.execute("UPDATE cohorts SET ladder_state=? WHERE family=? AND version=?",
                       (_ladder_text(state), str(family), int(version)))
        return True

    def ladder_rows(self, family: str, version: int, *, evaluator: str, first_day: str,
                    through: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """One ladder cohort's record through the session day `through` (inclusive): (its practice row, or None; its
        PROGRAM closes under `evaluator` exited from `first_day` to `through`, forced (wind-down) closes left out, and
        only its OWN accounts' (THE COHORT'S OWN RECORD: never an earlier cohort's account), in record order: {seq,
        trade_id, pnl, max_loss, exit_day, body})."""
        db = self._connect()
        live = _dicts(db.execute("SELECT * FROM practice WHERE family=? AND version=?", (str(family), int(version))))
        own, accounts = own_closes(db, str(family), int(version))
        trades = _dicts(db.execute(
            "SELECT seq, trade_id, pnl, max_loss, exit_day, body FROM trades WHERE family=? AND version=? AND evaluator=? "
            f"AND COALESCE(forced, 0)=0 AND exit_day IS NOT NULL AND exit_day>=? AND exit_day<=?{own} ORDER BY seq",
            (str(family), int(version), str(evaluator), str(first_day), str(through), *accounts)))
        return (live[0] if live else None), trades

    def _earlier(self, db: sqlite3.Connection, family: str, version: int) -> frozenset[str]:
        key = (str(family), int(version))
        if key not in self._earlier_cache:
            self._earlier_cache[key] = frozenset(earlier_accounts(db, *key))
        return self._earlier_cache[key]

    def earlier_account(self, family: str, version: int | None, account: str) -> bool:
        """THE COHORT'S OWN RECORD: whether `account` is an EARLIER cohort's of (family, version) (the archive names it):
        never the running cohort's, whatever evaluator made it. The House winds such an account down. Never raises:
        False when it cannot be read (asked again the next minute; the record leaves the account out all the same)."""
        try:
            return version is not None and str(account) in self._earlier(self._connect(), str(family), int(version))
        except Exception:  # noqa: BLE001 - the minute goes on; the record's own reads bar the account
            return False

    def entrants(self, *, since: str) -> list[dict[str, Any]]:
        """Every ladder entrant (one a cohort) that entered on or after the day `since`: [{id, family, version, run_sha,
        lineage, tier, evaluator, entered_day, p_value, p_day, p_checkpoint}]."""
        return _dicts(self._connect().execute(
            "SELECT id, family, version, run_sha, lineage, tier, evaluator, entered_day, p_value, p_day, p_checkpoint "
            "FROM entrants WHERE entered_day>=? ORDER BY entered_at, family, version, id", (str(since),)))

    def add_decision(self, row: Mapping[str, Any], *, close: str | None = None, reason: str = "") -> int:
        """One `ladder_decisions` row (the ladder's receipt): its id.

        A receipt that names its `checkpoint` is A CHECKPOINT'S JUDGEMENT of the active ladder cohort (`family`,
        `version`) under the running evaluator, written in ONE transaction with its own entrant's p-value (the receipt's
        `p_value`, as of its `day`, and `p_checkpoint`; `cohorts.entrant`'s row) and the cohort's state (`ladder_state`:
        the checkpoint judged, with the day and this receipt; `latch` "validation" or "prefilter": it met L1-L5 there
        and waits for that) and, with `close` ("failed": the judgement ends it for good, for `reason`), the cohort's
        ending.
        ValueError, nothing written: no such active ladder cohort under the running evaluator, a latched one (its
        checkpoint's verdict is final), one already judged at that checkpoint or a later one, one with no entrant row,
        a p-value outside [0, 1], or a judgement that both latches and ends. A receipt without a checkpoint writes
        neither a p-value nor a state (a demotion, a pending promotion; a latched cohort's answer is `add_answer`'s)."""
        checkpoint, latch = row.get("checkpoint"), row.get("latch")
        db = self._connect()
        if close is not None and (close != "failed" or checkpoint is None or latch is not None):
            raise ValueError("only a checkpoint's judgement that does not latch can end its cohort, as failed")
        if checkpoint is None:
            if latch is not None:
                raise ValueError("only a checkpoint's receipt latches its cohort")
            return self._insert_decision(db, row, None)
        if isinstance(checkpoint, bool) or not isinstance(checkpoint, int) or checkpoint < 1:
            raise ValueError(f"a checkpoint is named by its sessions: {checkpoint!r}")
        if latch is not None and latch not in LATCH_WAITS:
            raise ValueError(f"a latch waits for one of {list(LATCH_WAITS)}: {latch!r}")
        p = _num(row.get("p_value")) if not isinstance(row.get("p_value"), bool) else None
        if p is None or not 0.0 <= p <= 1.0:
            raise ValueError(f"a checkpoint's receipt carries the entrant's p-value: {row.get('p_value')!r}")
        family, version, day = str(row["family"]), int(row["version"]), str(row["day"])
        with db:
            db.execute("BEGIN IMMEDIATE")
            cohort = db.execute("SELECT status, snapshot, evaluator, ladder_state, entrant FROM cohorts WHERE family=? AND "
                                "version=?", (family, version)).fetchone()
            snapshot = json.loads(cohort[1]) if cohort is not None else None
            if cohort is None or cohort[0] != "active" or not isinstance(snapshot, dict) or not snapshot.get("ladder") \
                    or _evaluator_of(cohort[2], cohort[1]) != self.evaluator:
                raise ValueError(f"{family}@{version} is no active ladder cohort under the running evaluator")
            state = _ladder_state(cohort[3])
            if state["latch"] is not None:
                raise ValueError(f"{family}@{version} is latched at checkpoint {state['latch'].get('checkpoint')}: its "
                                 "verdict is final")
            if any(k >= checkpoint for k in state["judged"]):
                raise ValueError(f"{family}@{version} was already judged at checkpoint {max(state['judged'])}")
            receipt = self._insert_decision(db, {**row, "p_value": p}, checkpoint)
            if cohort[4] is None or db.execute("UPDATE entrants SET p_value=?, p_day=?, p_checkpoint=? WHERE id=?",
                                               (p, day, checkpoint, int(cohort[4]))).rowcount != 1:
                raise ValueError(f"{family}@{version} has no entrant row of its own")
            state["judged"][checkpoint] = {"day": day, "receipt": receipt}
            if latch is not None:
                state["latch"] = {"checkpoint": checkpoint, "day": day, "receipt": receipt, "waits": latch}
            if close is None:
                db.execute("UPDATE cohorts SET ladder_state=? WHERE family=? AND version=?",
                           (_ladder_text(state), family, version))
            else:
                db.execute("UPDATE cohorts SET ladder_state=?, status=?, completed_day=?, reason=? WHERE family=? AND "
                           "version=?", (_ladder_text(state), close, day, reason[:1000], family, version))
        return receipt

    def _insert_decision(self, db: sqlite3.Connection, row: Mapping[str, Any], checkpoint: int | None) -> int:
        cur = db.execute(
            "INSERT INTO ladder_decisions(day, family, version, run_sha, inputs, stats, p_value, bh_rank, bh_size, "
            "bh_threshold, verdict, reasons, binding, at, checkpoint) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(row["day"]), str(row["family"]), int(row["version"]), row.get("run_sha"), str(row["inputs"]),
             json.dumps(row.get("stats") or {}, sort_keys=True, default=str), row.get("p_value"), row.get("bh_rank"),
             row.get("bh_size"), row.get("bh_threshold"), str(row["verdict"]),
             json.dumps(list(row.get("reasons") or []), default=str), int(bool(row.get("binding"))), self.clock(),
             checkpoint))
        return int(cur.lastrowid)

    def decision(self, receipt: int) -> dict[str, Any] | None:
        """One `ladder_decisions` row by its id (a receipt), or None: {id, day, family, version, run_sha, inputs, stats,
        p_value, bh_rank, bh_size, bh_threshold, verdict, reasons, binding, at, checkpoint}."""
        rows = _dicts(self._connect().execute(
            "SELECT id, day, family, version, run_sha, inputs, stats, p_value, bh_rank, bh_size, bh_threshold, verdict, "
            "reasons, binding, at, checkpoint FROM ladder_decisions WHERE id=?", (int(receipt),)))
        if not rows:
            return None
        row = rows[0]
        for key, empty in (("stats", {}), ("reasons", [])):
            try:
                value = json.loads(row[key] or "null")
            except (TypeError, ValueError):
                value = None
            row[key] = value if isinstance(value, type(empty)) else empty
        return row

    def pending_promotions(self) -> list[dict[str, Any]]:
        """Every PENDING promotion's receipt (`promote_pending`: its band not yet known to have landed), whatever became
        of its cohort, the oldest first: [{id, day, family, version, run_sha}]."""
        return _dicts(self._connect().execute("SELECT id, day, family, version, run_sha FROM ladder_decisions WHERE "
                                              "verdict=? ORDER BY id", (PROMOTE_PENDING,)))

    def add_answer(self, row: Mapping[str, Any], *, close: str | None = None, reason: str = "") -> int:
        """THE ANSWER of a latched cohort (`league/live/ladder.py`): its receipt (it names no checkpoint: no line is
        judged again), written in ONE transaction with its latch (`waits` null and `answer` {day, receipt, verdict}:
        nothing waits any more) and, with `close` (one of `ANSWER_ENDS`), its ending for `reason`. Without `close` the
        cohort stays active, answered. Its id. ValueError, nothing written: no such active ladder cohort under the
        running evaluator, or one whose latch does not wait (never latched, or already answered)."""
        if close is not None and close not in ANSWER_ENDS:
            raise ValueError(close)
        if row.get("checkpoint") is not None:
            raise ValueError("an answer judges no checkpoint")
        family, version = str(row["family"]), int(row["version"])
        db = self._connect()
        with db:
            db.execute("BEGIN IMMEDIATE")
            cohort = db.execute("SELECT snapshot, evaluator, ladder_state FROM cohorts WHERE family=? AND version=? AND "
                                "status='active'", (family, version)).fetchone()
            latch = _ladder_state(cohort[2])["latch"] if cohort is not None else None
            if cohort is None or _evaluator_of(cohort[1], cohort[0]) != self.evaluator or latch is None \
                    or latch.get("waits") not in LATCH_WAITS:
                raise ValueError(f"{family}@{version} is no active cohort under the running evaluator whose latch waits")
            receipt = self._insert_decision(db, row, None)
            self._answered(db, family, version, day=str(row["day"]), receipt=receipt, verdict=str(row["verdict"]),
                           close=close, reason=reason)
        return receipt

    def settle_answer(self, receipt: int, verdict: str, reasons: Iterable[str] | None = None, *, day: str, close: str,
                      reason: str, was: tuple[str, ...] = (PROMOTE_PENDING,)) -> bool:
        """A PENDING promotion's receipt takes its verdict (`promote` once its band landed in the swarm's store,
        "blocked" when that store refused it; `reasons` when given), in ONE transaction with its cohort's latch
        (answered, as `add_answer`) and its ending (`close`, one of `ANSWER_ENDS`, for `reason`). True when the cohort
        moved (it was active). ValueError, nothing written, when the receipt's verdict is not one of `was`."""
        if close not in ANSWER_ENDS:
            raise ValueError(close)
        db = self._connect()
        with db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT family, version, verdict FROM ladder_decisions WHERE id=?", (int(receipt),)).fetchone()
            if row is None or row[2] not in was:
                raise ValueError(f"receipt {receipt} is not one of {list(was)}")
            if reasons is None:
                db.execute("UPDATE ladder_decisions SET verdict=? WHERE id=?", (str(verdict), int(receipt)))
            else:
                db.execute("UPDATE ladder_decisions SET verdict=?, reasons=? WHERE id=?",
                           (str(verdict), json.dumps(list(reasons), default=str), int(receipt)))
            return self._answered(db, str(row[0]), int(row[1]), day=str(day), receipt=int(receipt), verdict=str(verdict),
                                  close=close, reason=reason)

    @staticmethod
    def _answered(db: sqlite3.Connection, family: str, version: int, *, day: str, receipt: int, verdict: str,
                  close: str | None, reason: str) -> bool:
        """Inside a transaction: an active cohort's latch (when it has one) answered and, with `close`, the cohort
        ended. False, nothing written, without an active cohort."""
        row = db.execute("SELECT ladder_state FROM cohorts WHERE family=? AND version=? AND status='active'",
                         (family, version)).fetchone()
        if row is None:
            return False
        state = _ladder_state(row[0])
        if state["latch"] is not None:
            state["latch"].update(waits=None, answer={"day": day, "receipt": receipt, "verdict": verdict})
        if close is None:
            db.execute("UPDATE cohorts SET ladder_state=? WHERE family=? AND version=?",
                       (_ladder_text(state), family, version))
        else:
            db.execute("UPDATE cohorts SET ladder_state=?, status=?, completed_day=?, reason=? WHERE family=? AND version=?",
                       (_ladder_text(state), close, day, reason[:1000], family, version))
        return True

    def latch_told(self, family: str, version: int, *, day: str) -> bool:
        """A waiting latch's ONE alert: True the first time it is asked (its `told`, the day, written with it), False
        from then on, and without an active cohort whose latch waits."""
        db = self._connect()
        with db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT ladder_state FROM cohorts WHERE family=? AND version=? AND status='active'",
                             (str(family), int(version))).fetchone()
            state = _ladder_state(row[0] if row is not None else None)
            latch = state["latch"]
            if latch is None or latch.get("waits") not in LATCH_WAITS or latch.get("told"):
                return False
            latch["told"] = str(day)
            db.execute("UPDATE cohorts SET ladder_state=? WHERE family=? AND version=?",
                       (_ladder_text(state), str(family), int(version)))
        return True

    def set_verdict(self, receipt: int, verdict: str, reasons: Iterable[str], *, was: tuple[str, ...] | None = None) -> bool:
        """The verdict a receipt ends with (a pending promotion whose band never landed is void, say), only from one of
        `was` when given. True when it was written."""
        marks = "" if was is None else f" AND verdict IN ({','.join('?' for _ in was)})"
        cur = self._connect().execute(f"UPDATE ladder_decisions SET verdict=?, reasons=? WHERE id=?{marks}",
                                      (str(verdict), json.dumps(list(reasons), default=str), int(receipt), *(was or ())))
        return cur.rowcount > 0

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
        realized P&L of the cohort's other accounts. A minute of an EARLIER cohort's account (THE COHORT'S OWN RECORD: it
        winds down beside the new cohort) is not the record's: nothing is written for it. False when not written (alerted
        once; the next minute repairs it)."""
        rows = [dict(r) for r in rows]
        if not rows:
            return True
        try:
            db = self._connect()
            with db:
                db.execute("BEGIN IMMEDIATE")
                for r in rows:
                    self._upsert(db, r, self._earlier(db, str(r["family"]), int(r["version"])))
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
    def _upsert(db: sqlite3.Connection, r: Mapping[str, Any], earlier: frozenset[str] = frozenset()) -> None:
        family, version = str(r["family"]), int(r["version"])
        at, day = float(r["at"]), str(r["day"])
        capital = float(r.get("capital") or 0.0)
        account = str(r.get("account") or "")
        if account in earlier:
            return  # an earlier cohort's account, winding down: never a minute of this cohort's record
        counts = [int(bool(r.get(k))) for k in ("due", "made", "missed_quotes", "missed_budget", "missed_errors")]
        old = db.execute("SELECT sessions, minutes, last_day, account, base_pnl, peak_marked, drawdown_marked, tier, last_at, "
                         "decisions_due, decisions_made, open_mark_pnl, prior_day, prior_due, prior_made, prior_open_mark "
                         "FROM practice WHERE family=? AND version=?", (family, version)).fetchone()
        if old is not None and old[3] == account and int(float(old[8]) // 60) == int(at // 60):
            return  # a repeated minute/retry must not inflate session coverage
        if old is None or old[3] != account:
            # A new record, or a remade account: its equity starts at `capital` again, so the marked path carries on from
            # the realized P&L of the cohort's other accounts (never an earlier cohort's: a new cohort starts from zero).
            marks = "".join(" AND account != ?" for _ in earlier)
            base = db.execute(f"SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE family=? AND version=? AND account != ?{marks}",
                              (family, version, account, *sorted(earlier))).fetchone()[0]
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


def _ladder_state(text: Any) -> dict[str, Any]:
    """A cohort's `ladder_state` column, read: {judged: {checkpoint: {day, receipt}}, latch: {...} | None}; empty for
    NULL (a cohort never judged at a checkpoint, or a row written before the column) and for anything unreadable."""
    try:
        value = json.loads(text) if text else {}
    except (TypeError, ValueError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    judged = value.get("judged") if isinstance(value.get("judged"), dict) else {}
    latch = value.get("latch") if isinstance(value.get("latch"), dict) else None
    return {"judged": {int(k): dict(v) for k, v in judged.items() if isinstance(v, dict) and str(k).isdigit()},
            "latch": dict(latch) if latch else None}


def ladder_window(window: int, state: Any, *, sessions_through: Callable[[str], int],
                  answer_sessions: int) -> tuple[int, str]:
    """THE WINDOW HOLD (the module docstring): (the calendar sessions from its first day at which a forward-ladder
    cohort of practice window `window` ends `complete`, the reason it ends with). `state`: its `ladder_state` (the
    column, or as read); `sessions_through(day)`: the calendar sessions from its first day through `day`, on the
    caller's calendar; `answer_sessions`: the constitution's. A latch that still waits holds the cohort until
    `answer_sessions` sessions have passed since its checkpoint's day; a cohort never judged at its last checkpoint
    (the one its window names), `answer_sessions` sessions past its window; any other ends at its window. One rule
    for both sides: the House (`ObserveStore.cohort_candidates`) and the swarm's cohort keep
    (`league/swarm/practice.py`)."""
    state = state if isinstance(state, Mapping) else _ladder_state(state)
    hold = max(0, int(answer_sessions))
    latch = state.get("latch")
    if latch is not None:
        if latch.get("waits") not in LATCH_WAITS:
            return window, WINDOW_ENDED                      # its answer was read: it practised on to its window
        try:
            latched = int(sessions_through(str(latch.get("day"))))
        except (TypeError, ValueError):
            return window, WINDOW_UNANSWERED                 # a latch without its day: no wait can be counted
        return max(window, latched + hold), WINDOW_UNANSWERED
    if any(int(k) >= window for k in state.get("judged") or ()):
        return window, WINDOW_ENDED
    return window + hold, WINDOW_UNJUDGED


def cohort_window(snapshot: Mapping[str, Any], *, min_sessions: int = COHORT_MIN_SESSIONS,
                  max_sessions: int = COHORT_MAX_SESSIONS) -> int:
    """A cohort's window in calendar sessions from its first day, THE WINDOW HOLD apart: a forward-ladder cohort's is its
    snapshot's `practice_max_sessions` (at most 60); one frozen before the ladder keeps the old rule's (`max_sessions`,
    extended to its declared horizon, at most 60 and at least `min_sessions`)."""
    if snapshot.get("ladder"):
        return max(1, min(60, int(snapshot.get("practice_max_sessions") or 60)))
    horizon = max(int(max_sessions), int(snapshot.get("practice_max_sessions") or max_sessions))
    return max(int(min_sessions), min(60, horizon))


def changed_reason(first_day: str, day: str, snapshot: Mapping[str, Any], state: Any, *, session_over: bool = False,
                   min_sessions: int = COHORT_MIN_SESSIONS, max_sessions: int = COHORT_MAX_SESSIONS) -> str:
    """THE RE-ENTRY RULE's reading (the module docstring) of an active cohort that an evaluator change ends on `day`:
    `EVALUATOR_CHANGED` when it was INTERRUPTED (it is offered again); `EVALUATOR_CHANGED_FINAL` when a forward-ladder
    cohort's checkpoint verdict was final (it is latched, waiting or answered, or it was judged at its last
    checkpoint); `EVALUATOR_CHANGED_WINDOW` when the calendar sessions behind it had reached its window
    (`cohort_window`: a cohort held past it by THE WINDOW HOLD reached its window's end): those from `first_day` to
    before `day`, and `day`'s own when `session_over` (that session has closed, or cannot be shown to have been
    running; a `day` that is no session day has none to count). `state`: its `ladder_state` (the column, or as read)."""
    window = cohort_window(snapshot, min_sessions=min_sessions, max_sessions=max_sessions)
    if snapshot.get("ladder"):
        state = state if isinstance(state, Mapping) else _ladder_state(state)
        if state.get("latch") is not None or any(int(k) >= window for k in state.get("judged") or ()):
            return EVALUATOR_CHANGED_FINAL
    end = _day_after(day) if session_over else day
    behind = _sessions_before(first_day, end) if first_day < end else 0
    return EVALUATOR_CHANGED_WINDOW if behind >= window else EVALUATOR_CHANGED


def earlier_accounts(db: sqlite3.Connection, family: str, version: int) -> list[str]:
    """THE COHORT'S OWN RECORD (the module docstring): the practice accounts of the EARLIER cohorts of (family, version),
    as the archive holds them. [] for a program never frozen again, and on a file without the archive or from before
    it kept them. On any connection to the record (the House's, a read-only one)."""
    if "accounts" not in {row[1] for row in db.execute("PRAGMA table_info(cohort_archive)")}:
        return []
    found: set[str] = set()
    for row in db.execute("SELECT accounts FROM cohort_archive WHERE family=? AND version=?", (str(family), int(version))):
        try:
            value = json.loads(row[0]) if row[0] else []
        except (TypeError, ValueError):
            value = []
        if isinstance(value, list):
            found.update(str(a) for a in value)
    return sorted(found)


def own_closes(db: sqlite3.Connection, family: str, version: int) -> tuple[str, list[str]]:
    """THE COHORT'S OWN RECORD as a condition on `trades`: (SQL to append to a WHERE clause on (family, version), its
    parameters): no close of an earlier cohort's account ("" and [] for a program never frozen again)."""
    earlier = earlier_accounts(db, family, version)
    return "".join(" AND account != ?" for _ in earlier), earlier


def _accounts(db: sqlite3.Connection, family: str, version: int) -> list[str]:
    """Every practice account on record for (family, version): its closes', its receipts' and its practice row's."""
    found = {row[0] for row in db.execute("SELECT DISTINCT account FROM trades WHERE family=? AND version=?",
                                          (family, version))}
    found |= {row[0] for row in db.execute("SELECT DISTINCT account FROM events WHERE family=? AND version=?",
                                           (family, version))}
    found |= {row[0] for row in db.execute("SELECT account FROM practice WHERE family=? AND version=?", (family, version))}
    return sorted(str(a) for a in found if a is not None)


def answer_sessions() -> int:
    """The constitution's `options_money.ladder.answer_sessions` (THE WINDOW HOLD's sessions); 0 on a money table that
    is refused (the ladder judges nothing on one, so nothing is held for it)."""
    from .ladder import Rules

    try:
        return Rules.from_constitution().answer_sessions
    except ValueError:
        return 0


def _sessions_before(first: str, end: str) -> int:
    """Session days on the House's calendar (`chains.session_minutes`) from `first` to before `end`."""
    from datetime import date, timedelta
    from .chains import session_minutes

    count, cursor, stop = 0, date.fromisoformat(first), date.fromisoformat(end)
    while cursor < stop:
        count += session_minutes(cursor) is not None
        cursor += timedelta(days=1)
    return count


def _day_after(day: str) -> str:
    from datetime import date, timedelta

    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def _ladder_text(state: Mapping[str, Any]) -> str:
    return json.dumps({"judged": {str(k): v for k, v in sorted(state["judged"].items())}, "latch": state["latch"]},
                      sort_keys=True, allow_nan=False)


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
    """The practice league's trade columns on a file written before them, filled from each trade's own row; the
    cohorts' evaluator column (evidence v3), filled from each snapshot; the ladder's checkpoint and re-entry columns
    (`LADDER_COLUMNS`), NULL on the rows already there; and an `entrants` table keyed by (family, version, evaluator),
    rebuilt with an `id` a row (in admission order), each cohort and archive row named its entrant by that old key."""
    if "evaluator" not in {row[1] for row in db.execute("PRAGMA table_info(cohorts)")}:
        with db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("ALTER TABLE cohorts ADD COLUMN evaluator TEXT")
            for family, version, snapshot in db.execute("SELECT family, version, snapshot FROM cohorts").fetchall():
                db.execute("UPDATE cohorts SET evaluator=? WHERE family=? AND version=?",
                           (_evaluator_of(None, snapshot), family, version))
    for table, name, kind in LADDER_COLUMNS:
        if name not in {row[1] for row in db.execute(f"PRAGMA table_info({table})")}:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
    if "id" not in {row[1] for row in db.execute("PRAGMA table_info(entrants)")}:
        names = ", ".join(ENTRANT_COLUMNS)
        with db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("ALTER TABLE entrants RENAME TO entrants_keyed")
            db.execute(SCHEMA[SCHEMA.index("CREATE TABLE IF NOT EXISTS entrants"):SCHEMA.index("CREATE INDEX IF NOT EXISTS "
                                                                                              "entrants_day")])
            db.execute(f"INSERT INTO entrants({names}) SELECT {names} FROM entrants_keyed "
                       "ORDER BY entered_at, family, version, evaluator")
            db.execute("DROP TABLE entrants_keyed")
            db.execute("CREATE INDEX IF NOT EXISTS entrants_day ON entrants(entered_day)")
            for table in ("cohorts", "cohort_archive"):
                db.execute(f"UPDATE {table} SET entrant=(SELECT e.id FROM entrants e WHERE e.family={table}.family AND "
                           f"e.version={table}.version AND e.evaluator={table}.evaluator) WHERE entrant IS NULL")
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
        closes_program  closed trades under `evaluator`, program-closed (not forced), exited before `before`; the
                        cohort's OWN closes alone (THE COHORT'S OWN RECORD: from its own first day, never an earlier
                        cohort's account), as are all the closes below
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
            own, accounts = own_closes(db, str(family), int(version))
            trades = [dict(r) for r in db.execute(
                "SELECT pnl, max_loss, forced, body FROM trades WHERE family=? AND version=? AND evaluator=? "
                f"AND exit_day IS NOT NULL AND exit_day>=? AND exit_day<?{own} ORDER BY seq",
                (str(family), int(version), str(evaluator), str(cohort["first_day"]), str(before), *accounts))]
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
    for t in db.execute(f"SELECT seq, family, version, account, pnl, max_loss, forced, {evaluator} AS evaluator, "
                        f"{close} AS close_day FROM trades WHERE {close} >= ? ORDER BY seq", (since,)):
        t = dict(t)
        key = (str(t["family"]), int(t["version"] or 0))
        if key not in keyed:
            keyed[key] = {"live": live.get(key), "trades": []}
        keyed[key]["trades"].append(t)
    for key, part in keyed.items():
        if part["live"] is None:
            part["bodies"] = [_body(dict(r)) for r in db.execute(
                "SELECT body FROM trades WHERE family=? AND version IS ? ORDER BY seq", (key[0], key[1] or None))]
    # Old shadow trades remain in the realized headline, but cannot become feedback for a new evaluator's cohort, nor an
    # earlier cohort's for the cohort that followed it (THE COHORT'S OWN RECORD).
    if "cohorts" in tables:
        for cohort in db.execute("SELECT family, version, snapshot FROM cohorts").fetchall():
            key = (str(cohort["family"]), int(cohort["version"]))
            if key in keyed:
                keyed[key]["evaluator"] = json.loads(cohort["snapshot"]).get("practice_evaluator")
                keyed[key]["earlier"] = set(earlier_accounts(db, *key))
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
    earlier = part.get("earlier") or ()
    program = [t for t in closes if not t.get("forced") and t.get("account") not in earlier and
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


__all__ = ["ObserveStore", "practice_summary", "practice_record", "cohort_rows", "t_stat", "ladder_window",
           "cohort_window", "changed_reason", "earlier_accounts", "own_closes", "answer_sessions", "FILE", "MAX_ROWS",
           "KEEP_DAYS", "HOLD", "LATCH_WAITS", "ANSWER_ENDS", "PROMOTE_PENDING", "WINDOW_ENDED", "WINDOW_UNJUDGED",
           "WINDOW_UNANSWERED", "EVALUATOR_CHANGED", "EVALUATOR_CHANGED_FINAL", "EVALUATOR_CHANGED_WINDOW",
           "EVALUATOR_CHANGED_BEFORE", "COHORT_MIN_SESSIONS", "COHORT_MAX_SESSIONS"]
