"""THE RELEASE'S FIRST START, END TO END (the Monday scenario; Oct 3, 2026): what this release must do in production with
the state the release before it left.

Release V3-A part 1 went live on Saturday, Oct 3, 2026 at 08:50:34Z. It changed league/live alone, and by the rules it
ran:

- the swarm's evaluator adoption archived and cleared every alive family's research selection
  (`previous_evaluator_selection`, and its `evaluator_adopted` event), so every best was empty and the practice league
  was offered no program;
- the House ended every active practice cohort in place, whatever its window, with the words "evaluator changed; a new
  version needs fresh practice".

This release's first start is on that weekend, and its first session is Monday, Oct 5. One test walks it:

1. the swarm's start (`Swarm.run`'s own calls, in its order) adopts this release's identity, a league/live-only adoption:
   every alive family is given back the selection that adoption archived, by the adoption itself, with no researcher
   cycle, no Gym job and no model call;
2. `bands.observe` offers the same programs again;
3. the House's families pass in Monday's session freezes each INTERRUPTED program again as a NEW forward-ladder cohort:
   its own entrant, no judged p-value (the ladder counts it at 1), a sixty-session window from Monday, and an empty
   record that holds none of the old cohort's closes and none of its account's;
4. and it freezes nothing else: not the family that retired itself over the weekend, not the cohort that had completed
   normally, not the one whose window had already run out when that release ended it.

A second test walks what the first leaves out, on the same state: a family that set a best of its own after that
release's adoption (nothing is given back to it, and its own best practises), and a second start (the swarm adopts
nothing; a House that restarts on Monday and again on Tuesday freezes no cohort twice and writes no second entrant).

The swarm's store is built by the real writers (the tournament's validation; that release's own adoption, held
statement for statement in `evaluator_fakes.adopt_as_v3a`). The practice record is written in that release's own file
format (`V3A_SCHEMA`: no cohort evaluator, no ladder state, no entrants, no archive), row by row as its code wrote
them. The House is the real `OptionsLive` on the swarm's real store."""

from __future__ import annotations

import ast
import copy
import datetime as dt
import json
import math
import sqlite3
import unittest
from unittest.mock import patch

from league.tests.test_live_practice import PracticeCase
from league.tests.test_live_step import HAVE

if HAVE:
    from league.gym import fills as F
    from league.live import ladder as L
    from league.live import observe as O
    from league.live.families import SwarmFamilies
    from league.live.observe import practice_record
    from league.live.shadow import SHADOW_FILE, ShadowAccount, ShadowBook, needs_of
    from league.swarm import bands
    from league.swarm import settings as S
    from league.swarm.evaluator import ARCHIVE_KEY, KEY, adopt, adoption_words, identity
    from league.swarm.gate import run_sha
    from league.swarm.incubator import backfill
    from league.swarm.researcher import migrate_objective
    from league.swarm.store import SwarmStore
    from league.swarm.tournament import Tournament
    from league.tests.evaluator_fakes import adopt_as_v3a, seed_current_run
    from league.tests.live_fakes import VERTICAL, at
    from league.tests.swarm_fakes import Clock as SwarmClock
    from league.tests.test_swarm_evaluator import adoptions
    from league.tests.test_swarm_rounds import FakeGymPool, strong

IMAGE = "synthetic-image"
FRIDAY, SATURDAY, SUNDAY, MONDAY, TUESDAY = (dt.date(2026, 10, d) for d in (2, 3, 4, 5, 6))
#: Release V3-A part 1's adoption, to the second.
ADOPTED_AT = "2026-10-03T08:50:34Z"
#: What that release's `cohort_candidates` wrote on every active cohort of another evaluator, byte for byte.
BEFORE = "evaluator changed; a new version needs fresh practice"
#: That release's practice record (`league/live/observe.py` at main b7d19009), byte for byte: its SCHEMA ...
V3A_SCHEMA = """
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
    snapshot TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', completed_day TEXT, reason TEXT,
    PRIMARY KEY (family, version));
CREATE TABLE IF NOT EXISTS events (
    instance TEXT NOT NULL, account TEXT NOT NULL, event_id INTEGER NOT NULL, family TEXT NOT NULL,
    version INTEGER NOT NULL, day TEXT, minute INTEGER, kind TEXT NOT NULL, body TEXT NOT NULL,
    recorded_at REAL NOT NULL, PRIMARY KEY(instance, account, event_id));
CREATE INDEX IF NOT EXISTS events_family_day ON events(family, day);
CREATE INDEX IF NOT EXISTS events_day ON events(day);
"""
#: ... and the columns its `_migrate` adds to `trades` on first open.
V3A_TRADE_COLUMNS = (("exit_day", "TEXT"), ("reason", "TEXT"), ("forced", "INTEGER"), ("evaluator", "TEXT"))
PARAMS = {"hold": 3, "opens": 3}


def epoch(text: str) -> float:
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


@unittest.skipUnless(HAVE, "numpy not installed")
class TheFirstStart(PracticeCase):
    #: The practice cohorts as that release left them: {family: (its first day, the reason it ended with, the day)}.
    #: `open-v` and `open-t` were inside their window (three and two sessions behind them); `quit` too, and its family
    #: then retired itself; `done` had completed normally on Thursday; `over` had ten sessions behind it (the old
    #: rule's whole window) when that release ended it on Saturday with the same words as the others.
    COHORTS = {"open-v": ("2026-09-30", BEFORE, "2026-10-03"),
               "open-t": ("2026-10-01", BEFORE, "2026-10-03"),
               "quit": ("2026-09-30", BEFORE, "2026-10-03"),
               "done": ("2026-09-24", "observation target reached", "2026-10-01"),
               "over": ("2026-09-21", BEFORE, "2026-10-03")}
    VALIDATED, TRAINED = ("open-v", "quit", "done"), ("open-t", "over")

    def setUp(self):
        super().setUp()
        self.market.day = MONDAY                       # the fake market lists its expiries from Monday, Oct 5
        self.bundle = bands._bundle()
        fills = F.FillModel.load().version
        #: The release before V3-A part 1, that release, and this one: league/live alone differs.
        self.before = {"image": IMAGE, "bundle": self.bundle, "execution": "the league/live before V3-A part 1"}
        self.v3a = {**self.before, "execution": "release V3-A part 1's league/live"}
        self.this = identity(IMAGE, self.bundle)
        self.practice_before = f"{self.bundle}:{fills}:{self.before['execution']}"
        self.swarm_clock = SwarmClock(epoch("2026-09-21T14:00:00Z"))
        self.swarm = SwarmStore(self.root, clock=self.swarm_clock)
        self.addCleanup(self.swarm.close)
        self.settings = copy.deepcopy(S.DEFAULTS)
        self.settings["tournament"].update(require_robustness=False, drift_screen=False)
        self.pool = FakeGymPool(lambda job: {**strong(job), "gym_image": IMAGE, "gym_bundle": self.bundle})
        self.pool.image, self.pool.bundle = (lambda kind="gym": IMAGE), (lambda: self.bundle)
        self.tournament = Tournament(self.swarm, self.pool, self.settings, clock=self.swarm_clock)

    # ------------------------------------------------------------------ the swarm, as it stood before that release
    def swarm_start(self, evaluator: dict) -> dict:
        """A swarm's start, as `Swarm.run` makes it before any researcher or tournament thread exists: Train's objective
        (`migrate_objective`), the incubator's backfill, then the evaluator adoption. What the adoption returned."""
        migrate_objective(self.swarm, settings=self.settings)
        backfill(self.swarm)
        return adopt(self.swarm, evaluator)

    def family(self, fid: str) -> None:
        """A family whose version 1 is its best by Train score, on an eligible Train run of the Gym in force."""
        self.swarm.add_family({"id": fid, "mechanism": "An invented mechanism.", "structure": "debit_vertical",
                               "roots": ["SPY"], "dte": [0, 3]}, origin="test")
        self.swarm.add_version(fid, f"# {fid}\n" + VERTICAL, PARAMS, author="test")
        row = seed_current_run(self.swarm, fid, 1, window="train")
        self.swarm.update_family(fid, best_train=1.2)
        self.swarm.set_state(fid, best_train_run=row["run_id"], best_train_version=1)

    def before_that_release(self) -> list[dict]:
        """The swarm under the release before V3-A part 1: three families the tournament validated (the line met) and
        two with a Train best. The practice league's rows then, in its order."""
        self.assertEqual(self.swarm_start(self.before)["gym_changed"], True, "the store's first identity")
        for fid in (*self.VALIDATED, *self.TRAINED):
            self.family(fid)
        judged = self.tournament.validate([self.swarm.family(fid) for fid in self.VALIDATED])["judged"]
        self.assertEqual({fid: row["passed"] for fid, row in judged.items()}, {fid: True for fid in self.VALIDATED})
        rows = bands.observe(self.root)
        self.assertEqual([(r["family"], r["tier"]) for r in rows],
                         [("done", "validated"), ("open-v", "validated"), ("quit", "validated"), ("open-t", "train"),
                          ("over", "train")])
        return rows

    # ------------------------------------------------------------------ the practice record, as that release left it
    def account(self, fid: str) -> str:
        return f"account-of-{fid}-before"

    def practice_file(self, rows: list[dict]) -> None:
        """`observe.sqlite` in release V3-A part 1's own format, row by row as its code wrote them: each cohort's
        snapshot as its `freeze` made it (the program's row, `practice_frozen`, the practice evaluator it was frozen
        under, its DTE horizon), its ending as its `cohort_candidates` wrote it, its practice row and its closes."""
        behind = {fid: len(L.sessions_between(first, FRIDAY.isoformat())) for fid, (first, _, _) in self.COHORTS.items()}
        self.assertEqual(behind, {"open-v": 3, "open-t": 2, "quit": 3, "done": 7, "over": 10}, "the sessions behind each")
        db = sqlite3.connect(str(self.root / O.FILE))
        db.executescript(V3A_SCHEMA)
        for name, kind in V3A_TRADE_COLUMNS:
            db.execute(f"ALTER TABLE trades ADD COLUMN {name} {kind}")
        by = {r["family"]: r for r in rows}

        def minute(day: str, hh: int, mm: int) -> float:
            return at(dt.date.fromisoformat(day), hh, mm)

        for fid, (first, reason, ended) in self.COHORTS.items():
            snapshot = {**by[fid], "practice_frozen": True, "practice_evaluator": self.practice_before}
            for node in ast.parse(by[fid]["code"]).body:
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "NEEDS" for t in node.targets):
                    needs = ast.literal_eval(node.value)
                    snapshot["practice_max_sessions"] = min(60, math.ceil(float(needs["dte"][1]) * 5 / 7) + 3)
            self.assertEqual(snapshot["practice_max_sessions"], 6)
            db.execute("INSERT INTO cohorts(family, version, admitted_at, first_day, snapshot, status, completed_day, reason) "
                       "VALUES(?,?,?,?,?,?,?,?)", (fid, 1, minute(first, 9, 31), first,
                                                   json.dumps(snapshot, sort_keys=True, allow_nan=False),
                                                   "complete", ended, reason))
            practised = L.sessions_between(first, min(ended, FRIDAY.isoformat()))
            for j, day in enumerate(practised):               # two program closes a session, winners: +$30 a day
                for k in range(2):
                    trade = {"id": f"{j}-{k}", "day": day, "pnl": 15.0, "max_loss": 100.0, "exit_day": day,
                             "exit_reason": "program", "qty": 1, "fees": 1.3, "evaluator": self.practice_before}
                    db.execute("INSERT INTO trades(instance, account, family, version, trade_id, day, pnl, max_loss, "
                               "recorded_at, body, exit_day, reason, forced, evaluator) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (f"{fid}@1:o", self.account(fid), fid, 1, trade["id"], day, 15.0, 100.0, minute(day, 10 + k, 0),
                                json.dumps(trade, sort_keys=True), day, "program", 0, self.practice_before))
            db.execute("INSERT INTO practice(family, version, tier, lineage, structure, roots, capital, first_at, first_day, "
                       "last_at, last_day, sessions, minutes, account, base_pnl, pnl_marked, peak_marked, status) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (fid, 1, by[fid]["tier"], fid, "debit_vertical", '["SPY"]', 10000.0, minute(first, 9, 31), first,
                        minute(practised[-1], 15, 59), practised[-1], len(practised), 390 * len(practised),
                        self.account(fid), 0.0, 30.0 * len(practised), 30.0 * len(practised), "wound_down"))
        db.commit()
        db.close()

    def practice_rows(self, *fids: str) -> list[tuple]:
        marks = ",".join("?" for _ in fids)
        return self.live.observe_store._connect().execute(
            "SELECT family, first_day, last_day, sessions, account, pnl_marked FROM practice WHERE family IN "
            f"({marks}) ORDER BY family", fids).fetchall()

    def cohorts(self) -> dict:
        db = self.live.observe_store._connect()
        return {f: rest for f, *rest in db.execute("SELECT family, status, reason, first_day, completed_day FROM cohorts")}

    def test_the_selection_comes_back_and_the_interrupted_programs_practise_again_as_new_ladder_cohorts(self):
        # ============================ the state the running release left ============================================
        rows = self.before_that_release()
        was = {fid: self.swarm.family(fid) for fid in self.COHORTS}
        self.practice_file(rows)
        # Saturday 08:50:34Z: release V3-A part 1's swarm adopts its league/live. Every selection is archived and cleared.
        self.swarm_clock.t = epoch(ADOPTED_AT)
        self.assertEqual(adopt_as_v3a(self.swarm, self.v3a)["families"], 5)
        for fid in self.COHORTS:
            fam = self.swarm.family(fid)
            self.assertEqual([fam[column] for column in ("best_train", "best_version", "best_validation", "validated_version")],
                             [None] * 4, f"{fid}: its bests are empty")
            self.assertEqual(fam["state"][ARCHIVE_KEY]["best_train_version"], 1)
            [event] = adoptions(self.swarm, fid)
            self.assertEqual((event["at"], event["from"], event["to"], event["_previous_selection"]),
                             (ADOPTED_AT, self.before, self.v3a, fam["state"][ARCHIVE_KEY]))
            self.assertEqual(set(event), {"action", "from", "to", "_previous_selection", "incubator_barred", "at"},
                             "that release's event, in its own shape")
        self.assertEqual(bands.observe(self.root), [], "the practice league was offered no program")
        # Later that Saturday, one validated family's researcher retired it (the note said its evidence was owed again).
        self.swarm_clock.advance(6 * 3600)
        self.assertTrue(self.swarm.retire("quit", "its researcher retired it"))
        trials, jobs = self.swarm.totals(), len(self.pool.jobs)

        # ============================ this release's first start: the swarm (Sunday) ================================
        self.swarm_clock.t = epoch("2026-10-04T16:00:00Z")
        alive = ("done", "open-t", "open-v", "over")
        out = self.swarm_start(self.this)
        self.assertEqual((out["adopted"], out["gym_changed"], out["families"], out["bests"], out["returned"]),
                         (True, False, 4, 4, []), "a league/live-only adoption of the four alive families")
        self.assertEqual(out["restored"], {fid: ADOPTED_AT for fid in alive}, "each is given its selection back")
        self.assertEqual(adoption_words(out),
                         "evaluator adopted (league/live only, the Gym did not change): 4 families keep their research "
                         f"selection, 4 with a best; 4 given back the selection the league/live-only adoption of {ADOPTED_AT} "
                         "archived")
        for fid in alive:
            fam = self.swarm.family(fid)
            for column in ("best_train", "best_version", "best_validation", "validated_version"):
                self.assertEqual(fam[column], was[fid][column], (fid, column))
            for key in ("best_train_version", "best_train_run", "validation_version", "validation_line", "validation_image",
                        "validation_bundle"):
                self.assertEqual(fam["state"].get(key), was[fid]["state"].get(key), (fid, key))
            self.assertEqual(bool(fam["state"].get("gate_ready")), bool(was[fid]["state"].get("gate_ready")), fid)
            self.assertEqual(adoptions(self.swarm, fid)[-1]["restored"]["adopted_at"], ADOPTED_AT)
        self.assertEqual((self.swarm.totals(), len(self.pool.jobs)), (trials, jobs),
                         "by the adoption itself: no researcher cycle, no Gym job, no trial")
        quit_ = self.swarm.family("quit")
        self.assertEqual((bool(quit_["retired_at"]), quit_["best_version"], len(adoptions(self.swarm, "quit"))),
                         (True, None, 1), "the retired family is not adopted and is given nothing back")
        # `bands.observe` offers the programs again: the same rows as before that release, less the retired family's.
        offered = bands.observe(self.root)
        self.assertEqual(offered, [r for r in rows if r["family"] != "quit"])
        self.assertEqual([(r["family"], r["tier"], r["version"]) for r in offered],
                         [("done", "validated", 1), ("open-v", "validated", 1), ("open-t", "train", 1), ("over", "train", 1)])
        current = self.swarm.get(KEY)
        for fid in ("done", "open-v"):
            self.assertIs(bands.validation_passed(self.swarm.family(fid)["state"], 1, current), True,
                          "and the Validation line it was given back meets the ladder's L0")

        # ============================ this release's first start: the House (Sunday) ================================
        # The House's shadow book still holds one ended cohort's practice account, flat, as that release saved it.
        book = ShadowBook(self.root / SHADOW_FILE, fill_model=F.FillModel.load())
        needs = next(ast.literal_eval(n.value) for n in ast.parse(VERTICAL).body
                     if isinstance(n, ast.Assign) and n.targets[0].id == "NEEDS")
        old = ShadowAccount(instance="open-v@1:o", family="open-v", needs=needs_of(needs), params=PARAMS, capital=10000.0,
                            fill_model=book.fill_model)
        old.nonce, old.practice_evaluator = self.account("open-v"), self.practice_before
        book.accounts[old.instance] = old
        book.save()
        self.clock.set(at(SUNDAY, 12, 0))
        families = SwarmFamilies(self.root)
        self.addCleanup(lambda: families._store.close() if families._store is not None else None)
        live = self.build(families=families, real_money=True)
        store = live.observe_store
        two = store.evaluator
        self.assertEqual(two, f"{self.bundle}:{F.FillModel.load().version}:{self.this['execution']}")
        self.assertNotEqual(two, self.practice_before)
        # Friday's pins, as that release's House left them in the live state.
        live.state.put("observe_pins", {"day": FRIDAY.isoformat(), "order": ["open-v", "quit", "open-t", "over"],
                                        "versions": {f: 1 for f in ("open-v", "quit", "open-t", "over")},
                                        "tiers": {"open-v": "validated", "quit": "validated", "open-t": "train",
                                                  "over": "train"},
                                        "roots": {f: ["SPY"] for f in ("open-v", "quit", "open-t", "over")}})
        left = {fid: ["complete", reason, first, ended] for fid, (first, reason, ended) in self.COHORTS.items()}
        records = self.practice_rows(*self.COHORTS)
        self.assertEqual([r[0] for r in records], sorted(self.COHORTS))
        live.sync_families(self.clock(), force=True)                 # a families pass outside the session
        db = store._connect()
        self.assertEqual(self.cohorts(), left, "outside the session nothing is frozen, and no row is touched")
        self.assertEqual(self.practice_rows(*self.COHORTS), records)
        self.assertEqual((store.entrants(since="2026-01-01"), db.execute("SELECT COUNT(*) FROM cohort_archive").fetchone()),
                         ([], (0,)))
        self.assertEqual(db.execute("SELECT DISTINCT evaluator FROM cohorts").fetchall(), [(self.practice_before,)],
                         "the older file gained each cohort's evaluator, from its own snapshot")

        # ============================ Monday, Oct 5: the first session's families pass ===============================
        self.clock.set(at(MONDAY, 9, 31))
        live.minute()
        today = MONDAY.isoformat()
        now = self.cohorts()
        for fid, tier in (("open-v", "validated"), ("open-t", "train")):
            with self.subTest(frozen_again=fid):
                self.assertEqual(now[fid], ["active", None, today, None], "a NEW cohort, from Monday")
                snapshot, evaluator, state, entrant = db.execute(
                    "SELECT snapshot, evaluator, ladder_state, entrant FROM cohorts WHERE family=?", (fid,)).fetchone()
                snap = json.loads(snapshot)
                self.assertEqual((evaluator, snap["practice_evaluator"], snap["ladder"], snap["practice_max_sessions"], state),
                                 (two, two, L.LADDER_VERSION, 60, None),
                                 "a forward-ladder cohort under this release's practice evaluator, unjudged, sixty sessions")
                self.assertEqual((snap["code"], snap["params"], snap["run_sha"], snap["tier"]),
                                 (f"# {fid}\n" + VERTICAL, PARAMS, run_sha(self.swarm.version(fid, 1)), tier),
                                 "the very program the swarm holds")
                [mine] = [e for e in store.entrants(since="2026-01-01") if e["family"] == fid]
                self.assertEqual((mine["id"], mine["version"], mine["evaluator"], mine["entered_day"], mine["tier"],
                                  mine["run_sha"]), (entrant, 1, two, today, tier, snap["run_sha"]), "its own entrants row")
                self.assertEqual((mine["p_value"], mine["p_day"], mine["p_checkpoint"]), (None, None, None),
                                 "no judged p-value: the ladder counts it at 1")
                # AN EMPTY RECORD: none of the old cohort's closes, in any read of it.
                old_closes = db.execute("SELECT COUNT(*) FROM trades WHERE family=? AND evaluator=?",
                                        (fid, self.practice_before)).fetchone()[0]
                self.assertGreater(old_closes, 0, "the old cohort's closes are still on file")
                for evaluator in (two, self.practice_before):
                    self.assertEqual(store.ladder_rows(fid, 1, evaluator=evaluator, first_day=self.COHORTS[fid][0],
                                                       through=today)[1], [], "the ladder's record: empty, whatever is asked")
                record = practice_record(self.root, fid, 1, before="2026-10-06", evaluator=two)
                self.assertEqual((record["closes_program"], record["closes_all"], record["pnl_all"]), (0, 0, 0.0))
                self.assertTrue(store.earlier_account(fid, 1, self.account(fid)), "the old account is barred for good")
                # The old cohort, as that release ended it, is in the archive with its practice row and its account.
                [(evaluator, first, reason, ended, practice, accounts, old_entrant)] = db.execute(
                    "SELECT evaluator, first_day, reason, completed_day, practice, accounts, entrant FROM cohort_archive "
                    "WHERE family=?", (fid,)).fetchall()
                self.assertEqual((evaluator, first, reason, ended, json.loads(accounts), old_entrant),
                                 (self.practice_before, self.COHORTS[fid][0], BEFORE, SATURDAY.isoformat(),
                                  [self.account(fid)], None))
                self.assertEqual(json.loads(practice)["account"], self.account(fid))
        self.assertEqual(sorted(e["family"] for e in store.entrants(since="2026-01-01")), ["open-t", "open-v"],
                         "two cohorts, two entrants, and no other")
        for fid, why in (("quit", "its family retired itself"), ("done", "its cohort had completed normally"),
                         ("over", "its window had run out when that release ended it")):
            with self.subTest(never_frozen=fid):
                self.assertEqual(now[fid], left[fid], f"{why}: its row is as that release left it")
                self.assertEqual(db.execute("SELECT COUNT(*) FROM cohort_archive WHERE family=?", (fid,)).fetchone(), (0,))
                self.assertEqual(self.practice_rows(fid), [r for r in records if r[0] == fid], "and so is its practice row")
        self.assertEqual(bands.observe(self.root, family="quit"), [], "the retired family is offered no row at all")
        for fid in ("done", "over"):
            with self.assertRaises(ValueError, msg=f"{fid}: it may never practise again under this version"):
                store.freeze(bands.observe(self.root, family=fid)[0], day=today)
        self.assertEqual(self.observing(), ["open-t@1:o", "open-v@1:o"])
        self.assertEqual(live.state.get("observe_pins")["order"], ["open-v", "open-t"])

        # ============================ the session: they practise, each on an account of its own =====================
        self.run_to(9, 50)
        for fid in ("open-v", "open-t"):
            with self.subTest(practising=fid):
                account = live.shadow.accounts[f"{fid}@1:o"]
                self.assertEqual((account.practice_evaluator, account.winding_down), (two, False))
                self.assertNotEqual(account.nonce, self.account(fid), "never the old cohort's account")
                first, base, sessions, name = db.execute("SELECT first_day, base_pnl, sessions, account FROM practice WHERE "
                                                         "family=?", (fid,)).fetchone()
                self.assertEqual((first, base, sessions, name), (today, 0.0, 1, account.nonce),
                                 "its practice row is its own account's, from Monday and from zero")
                _, closes = store.ladder_rows(fid, 1, evaluator=two, first_day=today, through=today)
                mine = {seq for (seq,) in db.execute("SELECT seq FROM trades WHERE account=?", (account.nonce,))}
                self.assertTrue(closes, "it closed trades this morning")
                self.assertTrue({c["seq"] for c in closes} <= mine, "its record is its own account's closes alone")
        # ============================ the session's end: the ladder counts each at p = 1 and judges nothing =========
        self.clock.set(at(MONDAY, 15, 55))
        with patch.object(L, "benjamini_hochberg", wraps=L.benjamini_hochberg) as family_of:
            out = self.run_to(16, 0)
        ladder = out["ladder"]
        self.assertEqual((out["ended"], ladder["day"], ladder["binding"]), (today, today, False))
        self.assertEqual((ladder["entrants"], ladder["bh_size"], ladder["practising"], ladder["judged"], ladder["verdicts"]),
                         (2, 2, 2, 0, {}), "its first session's end is no checkpoint")
        self.assertEqual(sorted(family_of.call_args.args[0]), [1.0, 1.0], "each entrant at p = 1")
        self.assertEqual(db.execute("SELECT COUNT(*) FROM ladder_decisions").fetchone(), (0,))
        # ============================ and no money moved =============================================================
        self.assertEqual(self.practice_rows("done", "over", "quit"), [r for r in records if r[0] in ("done", "over", "quit")])
        self.assertEqual(self.cohorts(), {**left, **{fid: ["active", None, today, None] for fid in ("open-v", "open-t")}})
        self.assertEqual(self.venue.sent, [], "no real order")
        self.assertEqual((bands.read(self.root), [f["band"] for f in self.swarm.families(alive=True)]), ([], ["gym"] * 4))
        self.assertEqual([text for level, text in self.alerts if level == "error"], [])

    def test_a_best_of_its_own_since_is_kept_and_a_second_start_freezes_nothing_twice(self):
        """What the first test leaves out, on the same state.

        A BEST OF ITS OWN SINCE. After that release's adoption cleared every selection, two researchers ran their old
        best again on Saturday (under that release the practice league was offered a program again only so). Such a
        family holds a best of its own: the restoration gives it nothing back (`not_restored`), and what the practice
        league is offered is its own best, at the Train tier even where the archive held a validation. Its interrupted cohort is frozen again all
        the same, a new cohort and a new entrant, and the tournament's record of its verdict still meets the ladder's
        L0 on the Gym in force.

        A SECOND START. The swarm's next start on the same release adopts nothing and writes no event. A House that
        restarts in Monday's session after its first families pass, and again on Tuesday, freezes no second cohort,
        writes no second entrant and archives nothing more."""
        # ============================ the state the running release left, and Saturday's two researcher cycles ======
        rows = self.before_that_release()
        was = {fid: self.swarm.family(fid) for fid in self.COHORTS}
        self.practice_file(rows)
        self.swarm_clock.t = epoch(ADOPTED_AT)
        self.assertEqual(adopt_as_v3a(self.swarm, self.v3a)["families"], 5)
        own = ("open-t", "open-v")
        self.swarm_clock.advance(3 * 3600)
        for fid in own:  # its old program run again on Train under that release: a best of its own
            row = seed_current_run(self.swarm, fid, 1, window="train")
            self.swarm.update_family(fid, best_train=1.1)
            self.swarm.set_state(fid, best_train_run=row["run_id"], best_train_version=1)
        self.swarm_clock.advance(3 * 3600)
        self.assertTrue(self.swarm.retire("quit", "its researcher retired it"))
        self.assertEqual([(r["family"], r["tier"]) for r in bands.observe(self.root)], [("open-t", "train"), ("open-v", "train")],
                         "under that release practice was offered only what a researcher ran again")

        # ============================ this release's first start: the swarm (Sunday) ================================
        self.swarm_clock.t = epoch("2026-10-04T16:00:00Z")
        out = self.swarm_start(self.this)
        self.assertEqual((out["adopted"], out["gym_changed"], out["families"], out["bests"], out["returned"]),
                         (True, False, 4, 4, []))
        self.assertEqual(out["restored"], {"done": ADOPTED_AT, "over": ADOPTED_AT}, "only the families with no best since")
        for fid in own:
            fam, event = self.swarm.family(fid), adoptions(self.swarm, fid)[-1]
            self.assertEqual((event["restored"], event["not_restored"]),
                             (None, "it holds a best or a validation of its own since"), fid)
            self.assertEqual((fam["best_train"], fam["state"]["best_train_version"], fam["validated_version"],
                              fam["state"].get("validation_line")), (1.1, 1, None, None),
                             f"{fid}: its own best stands, and nothing of the archive is laid over it")
            self.assertEqual(fam["state"][ARCHIVE_KEY]["best_train_version"], 1, "the archive stays where it was")
        for fid in ("done", "over"):
            for column in ("best_train", "best_version", "best_validation", "validated_version"):
                self.assertEqual(self.swarm.family(fid)[column], was[fid][column], (fid, column))
        offered = bands.observe(self.root)
        self.assertEqual([(r["family"], r["tier"], r["version"]) for r in offered],
                         [("done", "validated", 1), ("over", "train", 1), ("open-t", "train", 1), ("open-v", "train", 1)],
                         "each family's own standing: the validated family that ran its best again practises it at the Train tier")
        current = self.swarm.get(KEY)
        self.assertIs(bands.validation_passed(self.swarm.family("open-v")["state"], 1, current), True,
                      "its verdict's record was judged on the Gym in force: L0 is met without the line")
        self.assertIsNone(bands.validation_passed(self.swarm.family("open-t")["state"], 1, current), "never validated")

        # ============================ the House: Sunday, then Monday's first families pass ===========================
        self.clock.set(at(SUNDAY, 12, 0))
        families = SwarmFamilies(self.root)
        self.addCleanup(lambda: families._store.close() if families._store is not None else None)
        live = self.build(families=families, real_money=True)
        two = live.observe_store.evaluator
        left = {fid: ["complete", reason, first, ended] for fid, (first, reason, ended) in self.COHORTS.items()}
        live.sync_families(self.clock(), force=True)
        self.assertEqual(self.cohorts(), left, "outside the session nothing is frozen")
        self.clock.set(at(MONDAY, 9, 31))
        live.minute()
        today = MONDAY.isoformat()
        monday = self.cohorts()
        self.assertEqual(monday, {**left, **{fid: ["active", None, today, None] for fid in own}},
                         "the two interrupted programs are frozen again; nothing else is")

        def entrants():
            return [(e["id"], e["family"], e["version"], e["tier"], e["evaluator"], e["entered_day"], e["p_value"])
                    for e in self.live.observe_store.entrants(since="2026-01-01")]

        def archived():
            return self.live.observe_store._connect().execute(
                "SELECT family, reason, completed_day FROM cohort_archive ORDER BY family").fetchall()

        first = entrants()
        self.assertEqual([e[1:] for e in first], [(fid, 1, "train", two, today, None) for fid in own],
                         "one entrant each, at the tier its own best practises in")
        self.assertEqual(archived(), [(fid, BEFORE, SATURDAY.isoformat()) for fid in own])
        for fid in own:
            snap = json.loads(self.live.observe_store._connect().execute(
                "SELECT snapshot FROM cohorts WHERE family=?", (fid,)).fetchone()[0])
            self.assertEqual((snap["run_sha"], snap["tier"], snap["ladder"], snap["practice_evaluator"]),
                             (run_sha(self.swarm.version(fid, 1)), "train", L.LADDER_VERSION, two))
        self.assertEqual(self.observing(), ["open-t@1:o", "open-v@1:o"])

        # ============================ a second start, the same Monday ================================================
        events = len(adoptions(self.swarm))
        self.assertEqual(self.swarm_start(self.this), {"adopted": False, "families": 0}, "the swarm adopts nothing twice")
        self.assertEqual(len(adoptions(self.swarm)), events, "and writes no event")
        self.assertEqual([(r["family"], r["tier"]) for r in bands.observe(self.root)], [(r["family"], r["tier"]) for r in offered])
        self.clock.set(at(MONDAY, 9, 33))
        live = self.restart()
        self.assertEqual(live.observe_store.evaluator, two)
        live.minute()
        self.clock.set(at(MONDAY, 9, 40))
        live.sync_families(self.clock(), force=True)
        self.assertEqual((self.cohorts(), entrants(), archived()),
                         (monday, first, [(fid, BEFORE, SATURDAY.isoformat()) for fid in own]),
                         "a restart in the session: no second cohort, no second entrant, nothing more archived")
        self.assertEqual(self.observing(), ["open-t@1:o", "open-v@1:o"])

        # ============================ the session's end, then Tuesday after another restart ==========================
        self.run_to(9, 55)
        self.clock.set(at(MONDAY, 15, 55))
        ladder = self.run_to(16, 0)["ladder"]
        self.assertEqual((ladder["entrants"], ladder["bh_size"], ladder["practising"], ladder["judged"], ladder["verdicts"]),
                         (2, 2, 2, 0, {}))
        self.market.day = TUESDAY
        self.clock.set(at(TUESDAY, 9, 31))
        live = self.restart()
        live.minute()
        self.assertEqual((self.cohorts(), entrants(), archived()),
                         (monday, first, [(fid, BEFORE, SATURDAY.isoformat()) for fid in own]),
                         "nor on the next day: a cohort is frozen once")
        self.assertEqual(self.observing(), ["open-t@1:o", "open-v@1:o"])
        self.assertEqual(self.live.observe_store._connect().execute("SELECT COUNT(*) FROM ladder_decisions").fetchone(), (0,))
        self.assertEqual(self.venue.sent, [], "no real order")
        self.assertEqual((bands.read(self.root), [f["band"] for f in self.swarm.families(alive=True)]), ([], ["gym"] * 4))
        self.assertEqual([text for level, text in self.alerts if level == "error"], [])


if __name__ == "__main__":
    unittest.main()
