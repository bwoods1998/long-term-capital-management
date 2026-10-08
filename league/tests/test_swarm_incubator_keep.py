"""THE COHORT KEEP (L1, release B, Sept 30; `Tournament.incubator_keep`, `practice.cohort_status`): a Gym family with an
active practice cohort is spared the revision, evaluation and idle retirement rules until its cohort completes, fails or
reaches its session window, on the cohort's realized record before today (the incubator's own basis): whatever that record
before the incubator's sample, and only while it is not negative once the sample is met. The deflated-Sharpe rule, its
researcher's own retire and the population floor still apply; a cohort the House is not practising is not kept; at most
`tournament.incubator_keep_max` (12) families, 0 turning it off. Research attention only: the keep reads the House's
practice record read-only and writes nothing but its saved keep (`practice.KEEP_KV`, read by the researchers' status) and
its one private round event."""

from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import os
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from league.live.observe import ObserveStore
from league.swarm import bands, practice
from league.swarm import settings as S
from league.swarm.hook import PUBLIC_KINDS
from league.swarm.researcher import idle_limit
from league.swarm.store import SwarmStore
from league.swarm.tournament import (KEEP_MAX, KEEP_SAMPLE_SESSIONS, KEEP_SAMPLE_TRADES, KEEP_STALE_SECONDS,
                                    KEEP_UNPRACTICED, Tournament, incubator_held, keep_order)
from league.tests.swarm_fakes import Clock
from league.tests.test_swarm_researcher import ResearcherCase
from league.tests.test_swarm_rounds import FakeGymPool

REPO = Path(__file__).resolve().parents[2]
NEW_YORK = ZoneInfo("America/New_York")
HAVE_NUMPY = importlib.util.find_spec("numpy") is not None
EVAL = "bundle-b:fill-1:exec-b"          # a stand-in for the House's practice evaluator (bundle, fill model, fingerprint)
FIRST = "2026-10-01"                      # a Thursday: sessions Oct 1, 2 and 5 before Tue Oct 6
PRACTISED = (FIRST, "2026-10-02", "2026-10-05")
CODE = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 2, "start": 571, "end": 958}
PARAMS = {"hold": 3}

def decide(ctx):
    return []
'''


def at(day: str, hour: int = 12, minute: int = 0) -> float:
    return dt.datetime.combine(dt.date.fromisoformat(day), dt.time(hour, minute), NEW_YORK).timestamp()


class KeepCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clock = Clock(at("2026-10-06", 8, 0))    # Tuesday before the open
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = copy.deepcopy(S.DEFAULTS)
        self.settings["population"].update(floor=0, start=0)
        self.ledger = ObserveStore(self.root, clock=self.clock)
        self.ledger.evaluator = EVAL
        self.addCleanup(self.ledger.close)
        self.pool = FakeGymPool(lambda job: None)
        self.minute = 0

    def tournament(self) -> Tournament:
        return Tournament(self.store, self.pool, self.settings, clock=self.clock, rng=random.Random(1))

    def family(self, fid: str, **fields) -> None:
        self.store.add_family({"id": fid, "mechanism": "An invented mechanism.", "structure": "debit_vertical",
                               "roots": ["SPY"], "dte": [0, 5]}, origin="test")
        self.store.add_version(fid, f"# {fid}\n{CODE}", {"hold": 3}, author="test")
        self.store.update_family(fid, best_version=1, **fields)

    def dead(self, fid: str) -> None:
        """Dead by the idle rule: no eligible Train version in `retire_idle_evaluations` Gym evaluations."""
        self.store.update_family(fid, since_val_trials=idle_limit(self.settings), trials=idle_limit(self.settings))

    def cohort(self, fid: str, *, version: int = 1, day: str = FIRST, tier: str = "train", best_train: float | None = 1.0,
               validation_t: float | None = None, dte: int = 3, practised: bool = True, run_sha: str | None = None) -> dict:
        """A cohort frozen on `day`, practised by the House on each session from Oct 1 to Oct 5 unless `practised` is
        False. Its snapshot's program is `run_sha` (default: one no version of the swarm's holds)."""
        snap = self.ledger.freeze({"family": fid, "version": version, "observe": True, "band": "gym", "tier": tier,
                                   "code": CODE.replace("[0, 3]", f"[0, {dte}]"), "params": {"hold": 3},
                                   "structure": "debit_vertical", "roots": ["SPY"],
                                   "run_sha": run_sha or f"sha-{fid}-{version}",
                                   "best_train": best_train, "validation_t": validation_t}, day=day)
        if practised:
            self.practised(fid, version=version)
        return snap

    def sampled(self, fid: str, total: float, *, version: int = 1) -> None:
        """The incubator's sample before Oct 6: ten program closes over Oct 1, 2 and 5 summing to `total`."""
        days = [d for d in PRACTISED for _ in range(3)] + ["2026-10-05"]
        self.closed(fid, [(d, 1.0, 50.0, False) for d in days[:9]] + [(days[9], total - 9.0, 50.0, False)], version=version)

    def practised(self, fid: str, days=PRACTISED, *, version: int = 1, open_mark: float = 0.0,
                  due: bool = True, made: bool = True) -> None:
        for day in days:
            self.minute += 1
            self.ledger.practice([{"family": fid, "version": version, "tier": "train", "lineage": fid,
                                   "structure": "debit_vertical", "roots": ["SPY"], "capital": 10000.0, "account": "a",
                                   "at": at(day, 10) + 60 * self.minute, "day": day, "equity": 10000.0 + open_mark,
                                   "open_positions": int(open_mark != 0), "open_mark_pnl": open_mark, "due": due,
                                   "made": made, "status": "live"}])

    def closed(self, fid: str, trades, *, version: int = 1, evaluator: str = EVAL) -> None:
        """Closed practice trades [(exit day, pnl, max loss, forced)]."""
        self.minute += 1
        self.ledger.add(f"{fid}@{version}:o", fid, version,
                        [{"id": f"{evaluator}-{self.minute}-{i}", "day": d, "exit_day": d, "pnl": p, "max_loss": m,
                          "exit_reason": "forced" if f else "program", "forced": f, "evaluator": evaluator}
                         for i, (d, p, m, f) in enumerate(trades, 1)], account="a")

    def alive(self) -> list[str]:
        return sorted(f["id"] for f in self.store.families(alive=True))


# ------------------------------------------------------------------------------------------------ the rules it spares
class Spares(KeepCase):
    def test_a_kept_family_is_spared_revisions_evaluations_and_the_idle_rule_but_not_the_deflated_sharpe_rule(self):
        for prefix in ("k", "c"):                      # k: an active cohort with a fresh record; c: no cohort
            self.family(f"{prefix}1", since_val_revisions=int(self.settings["tournament"]["retire_revisions"]))
            self.family(f"{prefix}2", since_val_trials=int(self.settings["tournament"]["retire_evaluations"]))
            self.family(f"{prefix}3")
            self.dead(f"{prefix}3")
            self.family(f"{prefix}4", validations=6)
            self.store.set_state(f"{prefix}4", validation_line={"numbers": {"dsr": 0.01}})
        for fid in ("k1", "k2", "k3", "k4"):
            self.cohort(fid)
        t = self.tournament()
        out = {r["family"]: r["why"] for r in t.retirements(self.store.families(alive=True))}
        self.assertEqual(sorted(out), ["c1", "c2", "c3", "c4", "k4"])
        self.assertEqual(out["k4"], out["c4"], "the deflated-Sharpe rule is evidence: the keep never spares it")
        self.assertIn("deflated Sharpe", out["k4"])
        self.assertEqual(self.alive(), ["k1", "k2", "k3"])
        self.assertEqual(t.keep_spared, {"k1": "revisions", "k2": "evaluations", "k3": "idle"})

    def test_the_idle_pass_spares_a_kept_family_and_retires_the_rest(self):
        for fid in ("kept", "dead"):
            self.family(fid)
            self.dead(fid)
        self.cohort("kept")
        t = self.tournament()
        out = t.idle_pass()
        self.assertEqual([r["family"] for r in out["retired"]], ["dead"])
        self.assertEqual(self.alive(), ["kept"])
        self.assertEqual(t.keep_spared, {"kept": "idle"})
        self.assertIsNone(t.idle_why(self.store.family("kept")), "idle_why reads the keep itself when not given one")
        self.assertIsNotNone(t.idle_why(self.store.family("kept"), kept=frozenset()), "and the rule is only spared")

    def test_the_floor_and_the_gate_hold_still_apply(self):
        self.family("a", validations=6)
        self.store.set_state("a", validation_line={"numbers": {"dsr": 0.01}})
        self.cohort("a")
        self.settings["population"]["floor"] = 1
        self.assertEqual(self.tournament().retirements(self.store.families(alive=True)), [], "the floor holds the DSR retiree")
        self.family("held")
        self.dead("held")
        self.cohort("held")
        self.store.set_state("held", gate_ready=True)
        t = self.tournament()
        self.assertIsNone(t._why(self.store.family("held"), (None, None)))
        self.assertEqual(t.keep_spared, {}, "a gate hold spares it before the keep is asked")

    def test_a_kept_family_outside_the_gym_band_or_retired_takes_no_place(self):
        self.settings["tournament"]["incubator_keep_max"] = 1
        for fid, t in (("promoted", 3.0), ("gone", 2.5), ("next", 1.0)):
            self.family(fid)
            self.cohort(fid, tier="validated", validation_t=t)
        self.store.set_band("promoted", "candidate", reason="synthetic")
        self.store.retire_gym("gone", "The mechanism failed.", floor=0, source="researcher")
        self.assertEqual(self.tournament().incubator_keep(), frozenset({"next"}))


# ------------------------------------------------------------------------------------------------ the record it reads
class Record(KeepCase):
    def keeps(self, fid: str) -> bool:
        return fid in self.tournament().incubator_keep()

    def test_a_fresh_cohorts_first_open_marked_below_zero_keeps_its_family(self):
        # Review of Sept 30: the engine books an open's fees and spread against it, so the open mark is below zero from
        # the minute a position opens. The keep reads realized closes only: the family is still kept and the idle pass
        # does not retire it.
        self.family("f")
        self.dead("f")
        self.cohort("f")
        self.practised("f", days=("2026-10-05",), open_mark=-1.30)
        t = self.tournament()
        self.assertEqual(t.idle_pass()["retired"], [])
        self.assertEqual(self.alive(), ["f"])
        self.assertEqual(t.keep_spared, {"f": "idle"})

    def test_before_the_sample_any_record_is_kept_and_the_negative_ones_last(self):
        # Review of Sept 30: a record judged before the incubator's sample drops a third or more of the cohorts whose
        # first look would pass; the first look is the one pre-registered P&L test.
        self.family("early-loss")
        self.dead("early-loss")
        self.cohort("early-loss", best_train=9.0)
        self.closed("early-loss", [(FIRST, -0.40, 50.0, False)])
        self.family("level")
        self.cohort("level", best_train=1.0)
        t = self.tournament()
        self.assertEqual(t.incubator_keep(), frozenset({"early-loss", "level"}))
        self.assertEqual([(r["family"], r["sample"], r["negative"]) for r in t.kept_rows],
                         [("level", False, False), ("early-loss", False, True)], "not negative first, whatever the order")
        self.assertEqual(t.retirements(self.store.families(alive=True)), [])
        self.settings["tournament"]["incubator_keep_max"] = 1
        self.assertEqual(self.tournament().incubator_keep(), frozenset({"level"}))

    def test_once_the_sample_is_met_a_negative_record_is_not_kept_and_zero_is(self):
        cases = {"flat": 0.0, "won": 12.0, "lost": -0.01}
        for fid, total in cases.items():
            self.family(fid)
            self.cohort(fid)
            self.sampled(fid, total)
        self.family("forced")                                   # program >= 0, all closes < 0
        self.cohort("forced")
        self.sampled("forced", 1.0)
        self.closed("forced", [("2026-10-02", -1.01, 50.0, True)])
        self.family("marked")                                   # a realized gain and an open mark far below it
        self.cohort("marked")
        self.sampled("marked", 2.0)
        self.practised("marked", days=("2026-10-05",), open_mark=-40.0)
        t = self.tournament()
        self.assertEqual(t.incubator_keep(), frozenset({"flat", "won", "marked"}))
        self.assertTrue(all(r["sample"] for r in t.kept_rows))
        self.assertEqual([r["family"] for r in t.kept_rows][0], "won", "the sample met, by return on risk")

    def test_todays_closes_do_not_move_the_keep(self):
        self.family("down-today")
        self.cohort("down-today")
        self.sampled("down-today", 5.0)
        self.closed("down-today", [("2026-10-06", -50.0, 50.0, False)])
        self.family("up-today")
        self.cohort("up-today")
        self.sampled("up-today", -5.0)
        self.closed("up-today", [("2026-10-06", 50.0, 50.0, False)])
        self.clock.t = at("2026-10-06", 15, 0)
        self.assertEqual(self.tournament().incubator_keep(), frozenset({"down-today"}))
        self.clock.t = at("2026-10-07", 8, 0)                    # the next session day: yesterday's closes count
        self.assertEqual(self.tournament().incubator_keep(), frozenset({"up-today"}))

    def test_only_the_cohorts_own_evaluator_counts(self):
        self.family("old-loss")
        self.cohort("old-loss")
        self.sampled("old-loss", 1.0)
        self.closed("old-loss", [(FIRST, -400.0, 500.0, False)], evaluator="an-older-evaluator")
        self.family("old-win")
        self.cohort("old-win")
        self.sampled("old-win", -1.0)
        self.closed("old-win", [(FIRST, 900.0, 500.0, False)], evaluator="an-older-evaluator")
        self.assertTrue(self.keeps("old-loss"), "another evaluator's loss is not this cohort's record")
        self.assertFalse(self.keeps("old-win"), "nor does another evaluator's gain rescue it")

    def test_a_cohort_the_house_is_not_practising_is_not_kept(self):
        self.family("never")                                    # admitted Oct 1, never practised: 3 sessions
        self.cohort("never", practised=False)
        self.family("stopped")                                  # practised Oct 1 only: Oct 2 and 5 missed
        self.cohort("stopped", practised=False)
        self.practised("stopped", days=(FIRST,))
        self.family("missed-one")                               # practised Oct 1 and 2: Oct 5 missed
        self.cohort("missed-one", practised=False)
        self.practised("missed-one", days=(FIRST, "2026-10-02"))
        self.family("admitted-friday")                          # admitted Oct 5, not yet practised: one session
        self.cohort("admitted-friday", day="2026-10-05", practised=False)
        self.family("admitted-today")
        self.cohort("admitted-today", day="2026-10-06", practised=False)
        self.assertEqual(KEEP_UNPRACTICED, 2)
        rows = {r["family"]: r["unpracticed"] for r in practice.cohort_status(self.root, today="2026-10-06")}
        self.assertEqual(rows, {"never": 3, "stopped": 2, "missed-one": 1, "admitted-friday": 1, "admitted-today": 0})
        self.assertEqual(self.tournament().incubator_keep(),
                         frozenset({"missed-one", "admitted-friday", "admitted-today"}))

    def test_a_house_that_practises_no_cohort_is_an_outage_not_a_cohort_left_out(self):
        for fid in ("a", "b"):
            self.family(fid)
            self.dead(fid)
            self.cohort(fid)                                    # practised Oct 1, 2 and 5
        self.clock.t = at("2026-10-08", 8, 0)                   # the House down Oct 6 and 7
        self.assertEqual([r["unpracticed"] for r in practice.cohort_status(self.root, today="2026-10-08")], [2, 2])
        self.assertEqual(self.tournament().incubator_keep(), frozenset({"a", "b"}))
        self.practised("b", days=("2026-10-08",))               # back, practising b only: a is left out
        self.assertEqual(self.tournament().incubator_keep(), frozenset({"b"}))

    def test_the_keep_ends_when_the_cohort_fails_or_its_window_runs_out(self):
        sessions = ("2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09",
                    "2026-10-12", "2026-10-13", "2026-10-14")
        self.family("failed")
        self.cohort("failed")
        self.ledger.fail_cohort("failed", 1, day="2026-10-05", reason="refused")
        self.family("windowed")
        self.cohort("windowed", practised=False)            # a 0-3 DTE program: a 10-session window
        self.practised("windowed", days=sessions)
        self.family("long")
        self.cohort("long", dte=45, practised=False)        # ceil(45 x 5 / 7) + 3 = 36 sessions
        self.practised("long", days=sessions)
        self.clock.t = at("2026-10-14", 16, 30)             # nine sessions since Oct 1 (Oct 12 is a session)
        self.assertEqual(self.tournament().incubator_keep(), frozenset({"windowed", "long"}))
        self.clock.t = at("2026-10-15", 8, 0)               # ten: the House completes it at this session's first sync
        self.assertEqual(self.tournament().incubator_keep(), frozenset({"long"}))
        for fid in ("failed", "windowed", "long"):
            self.dead(fid)
        self.tournament().retirements(self.store.families(alive=True))
        self.assertEqual(self.alive(), ["long"])

    @unittest.skipUnless(HAVE_NUMPY, "the House's cohort rule needs numpy (league.live.chains)")
    def test_the_keep_ends_where_the_house_completes_the_cohort(self):
        # The observation target: three sessions, ten program closes and no open position; the House completes it at the
        # next session's first sync, and the keep ends with it.
        self.family("target")
        self.cohort("target")
        self.closed("target", [(d, 1.0, 50.0, False) for d in PRACTISED for _ in range(4)])
        self.family("window")
        self.cohort("window")
        self.assertEqual(self.tournament().incubator_keep(), frozenset({"target", "window"}))
        self.ledger.cohort_candidates([], day="2026-10-06", in_session=True)
        self.assertEqual(self.tournament().incubator_keep(), frozenset({"window"}))
        # The window: the research side's count says it has run out on exactly the session the House completes it.
        day = dt.date(2026, 10, 7)
        while day < dt.date(2026, 11, 30):
            iso = day.isoformat()
            [row] = [r for r in practice.cohort_status(self.root, today=iso) if r["family"] == "window"] or [None]
            expired = row is None or row["elapsed"] >= row["window"]
            if day.weekday() < 5:
                self.ledger.cohort_candidates([], day=iso, in_session=True)
                done = not [r for r in practice.cohort_status(self.root, today=iso) if r["family"] == "window"]
                self.assertEqual(done, expired, iso)
                if done:
                    break
            day += dt.timedelta(days=1)
        self.assertEqual(iso, "2026-10-15")

    @unittest.skipUnless(HAVE_NUMPY, "the House's step defaults import numpy")
    def test_the_sample_and_the_window_are_the_houses_and_the_money_rows(self):
        from league.constitution import CONSTITUTION
        from league.live.step import DEFAULTS

        self.assertEqual((KEEP_SAMPLE_SESSIONS, KEEP_SAMPLE_TRADES),
                         (DEFAULTS["observe_min_sessions"], DEFAULTS["observe_min_trades"]))
        self.assertEqual((practice.COHORT_WINDOW, practice.COHORT_WINDOW_MIN),
                         (DEFAULTS["observe_max_sessions"], DEFAULTS["observe_min_sessions"]))
        row = CONSTITUTION["options_money"].get("incubator")
        if row is not None:                                  # the incubator's money row (B1)
            self.assertEqual((KEEP_SAMPLE_SESSIONS, KEEP_SAMPLE_TRADES), (row["min_sessions"], row["min_trades"]))

    def test_the_cohort_status_reads_before_today_without_writing_and_never_raises(self):
        self.family("a")
        self.cohort("a", practised=False)
        self.practised("a", days=(FIRST, "2026-10-02", "2026-10-05", "2026-10-06"), open_mark=-3.0)
        self.closed("a", [(FIRST, 12.0, 60.0, False), ("2026-10-06", -2.0, 40.0, False), ("2026-10-02", -1.0, 20.0, True)])
        self.closed("a", [(FIRST, -99.0, 60.0, False)], evaluator="an-older-evaluator")
        self.ledger.close()
        db = self.root / "observe.sqlite"
        before = (db.stat().st_mtime_ns, db.read_bytes())
        [row] = practice.cohort_status(self.root, today="2026-10-06")
        self.assertEqual((db.stat().st_mtime_ns, db.read_bytes()), before, "read-only (SQLite's WAL reader may add its "
                                                                           "empty -shm/-wal sidecars, as practice_summary's)")
        self.assertEqual(row, {"family": "a", "version": 1, "first_day": FIRST, "evaluator": EVAL, "tier": "train",
                               "validation_t": None, "best_train": 1.0, "structure": "debit_vertical", "run_sha": "sha-a-1",
                               "window": 10, "elapsed": 3, "sessions": 3, "unpracticed": 0, "coverage": 1.0,
                               "closes_program": 1, "pnl_program": 12.0, "closes_all": 2, "pnl_all": 11.0,
                               "max_loss_all": 80.0, "return_on_risk": 0.1375})
        self.assertNotIn("open_mark", row, "the open mark is the first look's, never the keep's")
        self.assertEqual(practice.cohort_status(self.root / "nowhere"), [])
        self.assertEqual(practice.cohort_status(None), [])
        with mock.patch.dict("sys.modules", {"league.live.observe": None}):
            self.assertIsNone(practice.cohort_status(self.root, today="2026-10-06"), "a broken import is None too")
        (self.root / "observe.sqlite").write_bytes(b"not a database at all" * 100)
        for suffix in ("-wal", "-shm"):
            if (self.root / f"observe.sqlite{suffix}").exists():
                os.unlink(self.root / f"observe.sqlite{suffix}")
        self.assertIsNone(practice.cohort_status(self.root, today="2026-10-06"), "unreadable is None, never []")

    def test_a_cohort_whose_practice_row_began_before_it_is_not_kept(self):
        # The incubator never takes a first look at it (`observe.practice_record` gives it no session count).
        self.family("a")
        self.practised("a", days=("2026-09-30",))
        self.cohort("a", practised=False)
        self.practised("a", days=(FIRST, "2026-10-02", "2026-10-05"))
        [row] = practice.cohort_status(self.root, today="2026-10-06")
        self.assertIsNone(row["sessions"])
        self.assertFalse(self.keeps("a"))


# ------------------------------------------------------------------------------------------------ the cap and its order
class Cap(KeepCase):
    def test_at_most_twelve_the_sample_first_by_return_on_risk_then_the_practice_leagues_order(self):
        self.assertEqual(KEEP_MAX, 12)
        for i in range(12):                                          # Train tier by best Train score: t00 the best
            self.family(f"t{i:02d}")
            self.cohort(f"t{i:02d}", best_train=float(20 - i))
        self.family("val")
        self.cohort("val", tier="validated", validation_t=0.5)       # the validated tier before any Train one
        for fid, pnl in (("s-low", 10.0), ("s-high", 30.0)):         # the sample met: 3 sessions, 10 program closes
            self.family(fid)
            self.cohort(fid, best_train=-5.0)
            self.sampled(fid, pnl)
        t = self.tournament()
        kept = t.incubator_keep()
        self.assertEqual([r["family"] for r in t.kept_rows],
                         ["s-high", "s-low", "val"] + [f"t{i:02d}" for i in range(9)])
        self.assertEqual(len(kept), 12)
        self.assertTrue(t.kept_rows[0]["sample"])
        self.assertFalse(t.kept_rows[2]["sample"])
        for fam in self.store.families(alive=True):
            self.dead(fam["id"])
        out = t.retirements(self.store.families(alive=True))
        self.assertEqual(sorted(r["family"] for r in out), ["t09", "t10", "t11"])

    def test_one_place_a_family_whatever_its_cohorts(self):
        self.family("a")
        self.cohort("a", version=1, best_train=2.0)
        self.store.add_version("a", f"# a2\n{CODE}", {"hold": 4}, author="test")
        self.cohort("a", version=2, best_train=3.0)
        self.family("b")
        self.cohort("b", best_train=1.0)
        rows = practice.cohort_status(self.root, today="2026-10-06")
        self.assertEqual([(r["family"], r["version"]) for r in keep_order(rows, {"a", "b"}, 2)], [("a", 2), ("b", 1)])
        self.assertEqual([r["family"] for r in keep_order(rows, {"a", "b"}, 1)], ["a"])
        self.assertEqual(keep_order(rows, {"a", "b"}, 0), [])

    def test_zero_or_anything_not_a_number_turns_it_off(self):
        self.family("a")
        self.dead("a")
        self.cohort("a")
        t = self.tournament()
        self.assertNotIn("incubator_keep_max", self.settings["tournament"], "settings.py is untouched: absent is 12")
        self.assertEqual(t.keep_max(), 12)
        for raw, want in ((5, 5), (96, 96), (97, 96), (12.5, 12), (0, 0), (-1, 0), (None, 0), (False, 0), (True, 0),
                          ("12", 0), ("0", 0), (float("nan"), 0), (float("inf"), 0)):
            self.settings["tournament"]["incubator_keep_max"] = raw
            self.assertEqual(t.keep_max(), want, raw)
        self.settings["tournament"]["incubator_keep_max"] = False
        self.assertEqual(t.incubator_keep(), frozenset())
        self.assertEqual((t.keep_read, t.keep_event()), ("off", None))
        self.assertEqual(self.store.get(practice.KEEP_KV)["families"], {}, "the researchers see no keep")
        self.assertEqual([r["family"] for r in t.retirements(self.store.families(alive=True))], ["a"], "main's rules")


class IncubatorsCohorts(KeepCase):
    """The final integrated check of release B (swarm nit 2): the L1 keep did not know which cohorts the House's
    incubator pinned (L2', at most `MAX_PINS`), so on a day with more than `incubator_keep_max` cohorts past the sample a
    pinned family with a lower return on risk left the keep for a round, was retired by the revision rule, and its
    incubation went to exits only. The swarm never reads the House's live state; it holds every cohort the incubator can
    pin (`incubator_held`: the sample met, a record not negative, and the swarm's own facts admitting the program), first
    and never cut by the cap."""

    EVALUATOR = {"image": "img-b", "bundle": "bundle-b", "execution": "exec-b"}
    OBJECTIVE = "worst-train-year-v1"

    def incubated(self, fid: str, total: float | None, *, version: int = 1, practises: str | None = None) -> str:
        """The swarm's incubator facts admit `fid`'s program (B2's mark under the current evaluator and Train objective,
        the gate's passed review and audit), and its cohort met the sample with `total` (None: not yet): one the House
        can pin. The cohort practises `practises` (default: that program). Returns the program's run sha."""
        from league.swarm.gate import gate_contract as review_contract
        from league.swarm.gate import run_sha

        self.store.put("research_evaluator", self.EVALUATOR)
        self.store.put("train_objective", self.OBJECTIVE)
        sha = run_sha(self.store.version(fid, version))
        contract = review_contract()["sha256"]
        self.store.set_state(fid, train_passed={str(version): {
            "evaluator": self.EVALUATOR, "objective": self.OBJECTIVE, "run": "r", "robust_pnl": 5.0,
            "drift": {"t": 1.0, "positive": 4, "years": 5}, "at": 1.0}}, review={
            "sha": sha, "version": version, "verdict": "pass", "contract_sha": contract,
            "audit": {"verdict": "pass", "contract_sha": contract}})
        self.cohort(fid, version=version, run_sha=practises or sha)
        if total is not None:
            self.sampled(fid, total, version=version)
        self.assertEqual(len(bands.incubator(self.root, family=fid, version=version)), 1, "the reader the House pins by")
        return sha

    def test_a_pinned_family_is_never_dropped_for_a_higher_return_and_the_cap_never_holds_fewer(self):
        self.family("pinned")
        self.incubated("pinned", 5.0)                           # return on risk 0.01
        for fid, total in (("high", 30.0), ("higher", 40.0)):   # more return, nothing the incubator can pin
            self.family(fid)
            self.cohort(fid)
            self.sampled(fid, total)
        self.settings["tournament"]["incubator_keep_max"] = 1
        t = self.tournament()
        self.assertEqual(t.incubator_keep(), frozenset({"pinned"}), "before both higher returns")
        self.assertEqual([(r["family"], r["sample"], r["held"]) for r in t.kept_rows], [("pinned", True, True)])
        self.family("second")                                   # a second cohort the incubator can pin, the cap still 1
        self.incubated("second", 4.0)
        self.assertEqual(t.incubator_keep(), frozenset({"pinned", "second"}), "the cap is never below them")
        self.assertEqual([r["family"] for r in t.kept_rows], ["pinned", "second"], "by return on risk")
        self.settings["tournament"]["incubator_keep_max"] = 3
        t.incubator_keep()
        self.assertEqual([r["family"] for r in t.kept_rows], ["pinned", "second", "higher"],
                         "then the rest that met the sample, by return on risk")
        self.settings["tournament"]["incubator_keep_max"] = 1
        t.incubator_keep()
        for fid in self.alive():
            self.store.update_family(fid, since_val_revisions=int(self.settings["tournament"]["retire_revisions"]))
        out = t.retirements(self.store.families(alive=True))
        self.assertEqual(sorted(r["family"] for r in out), ["high", "higher"])
        self.assertEqual(self.alive(), ["pinned", "second"], "never retired mid-incubation for a higher return")
        self.assertEqual(t.keep_spared, {"pinned": "revisions", "second": "revisions"})
        self.assertEqual(t.keep_event()["held"], ["pinned", "second"])
        self.assertEqual(self.store.get(practice.KEEP_KV)["held"], ["pinned", "second"])
        self.settings["tournament"]["incubator_keep_max"] = 0
        self.assertEqual(self.tournament().incubator_keep(), frozenset(), "0 still turns the keep off")

    def test_only_a_cohort_whose_program_the_swarms_facts_admit_comes_first(self):
        self.family("held")
        self.incubated("held", 5.0)
        self.family("other-program")                            # facts for its version; its cohort practises another
        self.incubated("other-program", 6.0, practises="another program")
        self.family("barred")                                   # facts, then a bar on its program
        sha = self.incubated("barred", 7.0)
        self.store.set_state("barred", incubator_barred={sha: {"why": "the gate's audit failed it"}})
        self.family("early")                                    # facts, the sample not met yet
        self.incubated("early", None)
        self.family("plain")                                    # no facts, the highest return
        self.cohort("plain")
        self.sampled("plain", 50.0)
        rows = practice.cohort_status(self.root, today="2026-10-06")
        alive = set(self.alive())
        held = incubator_held(self.root, rows, alive)
        self.assertEqual(held, frozenset({("held", 1)}))
        self.assertEqual([(r["family"], r["held"]) for r in keep_order(rows, alive, 12, held=held)][:2],
                         [("held", True), ("plain", False)])
        self.assertEqual(incubator_held(self.root, rows, alive - {"held"}), frozenset(), "a family not alive")
        with mock.patch.object(bands, "incubator", side_effect=sqlite3.OperationalError("database is locked")):
            self.assertEqual(incubator_held(self.root, rows, alive),
                             frozenset({("held", 1), ("other-program", 1), ("barred", 1), ("plain", 1)}),
                             "facts that cannot be read: every cohort past the sample is held (fail open for keeping)")
            t = self.tournament()
            self.assertEqual(t.keep_read, "off")
            t.incubator_keep()
            self.assertEqual(t.keep_read, "ok", "never raises")
        self.assertEqual(incubator_held(None, rows, alive), frozenset())

    def test_a_fresh_process_keeps_the_saved_incubators_cohorts_beyond_the_cap(self):
        for fid, total in (("p1", 5.0), ("p2", 4.0)):
            self.family(fid)
            self.incubated(fid, total)
        self.family("high")
        self.cohort("high")
        self.sampled("high", 40.0)
        self.settings["tournament"]["incubator_keep_max"] = 1
        self.assertEqual(self.tournament().incubator_keep(), frozenset({"p1", "p2"}))
        saved = self.store.get(practice.KEEP_KV)
        self.assertEqual(saved, {"at": self.clock(), "families": {"p1": 1, "p2": 1}, "held": ["p1", "p2"]})
        self.store.put(practice.KEEP_KV, {**saved, "families": {**saved["families"], "aaa": 1}})
        self.clock.advance(60)
        t = self.tournament()
        with mock.patch.object(practice, "cohort_status", return_value=None):
            self.assertEqual((t.incubator_keep(), t.keep_read), (frozenset({"p1", "p2"}), "stale"),
                             "the incubator's first, beyond the cap (by name alone it would have been aaa)")
            self.assertEqual([r["held"] for r in t.kept_rows], [True, True])

    def test_the_order_is_pure_and_the_incubators_cohorts_need_the_sample(self):
        for fid, total in (("a", 30.0), ("b", 5.0), ("c", None)):
            self.family(fid)
            self.cohort(fid)
            if total is not None:
                self.sampled(fid, total)
        rows = practice.cohort_status(self.root, today="2026-10-06")
        alive = {"a", "b", "c"}
        self.assertEqual([r["family"] for r in keep_order(rows, alive, 2)], ["a", "b"])
        self.assertEqual([r["family"] for r in keep_order(rows, alive, 1, held={("b", 1)})], ["b"])
        self.assertEqual([r["family"] for r in keep_order(rows, alive, 1, held={("b", 1), ("a", 1)})], ["a", "b"])
        self.assertEqual([(r["family"], r["held"]) for r in keep_order(rows, alive, 3, held={("c", 1)})],
                         [("a", False), ("b", False), ("c", False)], "a cohort before the sample is never the incubator's")
        self.assertEqual(keep_order(rows, alive, 0, held={("b", 1)}), [])


# ------------------------------------------------------------------------------------------------ reads, events, reach
class Reads(KeepCase):
    def test_an_unreadable_record_keeps_the_last_keep_for_an_hour_then_none_with_one_alert(self):
        self.family("a")
        self.dead("a")
        self.cohort("a")
        t = self.tournament()
        self.assertEqual(t.incubator_keep(), frozenset({"a"}))
        with mock.patch.object(practice, "cohort_status", return_value=None):
            self.clock.advance(KEEP_STALE_SECONDS)
            self.assertEqual((t.incubator_keep(), t.keep_read), (frozenset({"a"}), "stale"))
            self.assertEqual(t.retirements(self.store.families(alive=True)), [])
            event = t.keep_event()
            self.assertEqual((event["read"], event["error"]), ("stale", "the practice record (observe.sqlite) could not "
                                                                        "be read"))
            self.clock.advance(1)
            self.assertEqual((t.incubator_keep(), t.keep_read), (frozenset(), "failed"))
            self.assertEqual(self.store.get(practice.KEEP_KV)["families"], {}, "the researchers' keep ends with it")
            first, second = t.keep_event(), t.keep_event()
            self.assertTrue(first["alert"])
            self.assertIn("observe.sqlite", first["text"])
            self.assertNotIn("alert", second, "said once until it reads again")
            self.assertEqual([r["family"] for r in t.retirements(self.store.families(alive=True))], ["a"])
        self.assertEqual(t.incubator_keep(), frozenset())

    def test_a_fresh_process_that_cannot_read_keeps_nothing(self):
        self.family("a")
        self.cohort("a")
        with mock.patch.object(practice, "cohort_status", side_effect=RuntimeError("boom")):
            t = self.tournament()
            self.assertEqual((t.incubator_keep(), t.keep_read), (frozenset(), "failed"), "no keep was saved")
            self.assertIn("RuntimeError", t.keep_event()["error"])

    def test_a_fresh_process_that_cannot_read_takes_the_keep_the_last_process_saved_until_its_hour_ends(self):
        # The review of release B (Sept 30): a restarted swarm (a deploy, the induced-failure kill) runs its idle pass at
        # once; one failed first read retired the kept families and overwrote the saved keep with {}.
        for fid in ("kept", "dead"):
            self.family(fid)
            self.dead(fid)
        self.cohort("kept")
        self.assertEqual(self.tournament().incubator_keep(), frozenset({"kept"}))
        saved = self.store.get(practice.KEEP_KV)
        self.clock.advance(60)                              # the swarm restarts a minute later
        t = self.tournament()                               # a fresh process: no read of its own
        with mock.patch.object(practice, "cohort_status", return_value=None):
            out = t.idle_pass()
            self.assertEqual([r["family"] for r in out["retired"]], ["dead"], "the saved keep spares its family")
            self.assertEqual((t.kept, t.keep_read), (frozenset({"kept"}), "stale"))
            self.assertEqual(t.keep_spared, {"kept": "idle"})
            self.assertEqual(self.store.get(practice.KEEP_KV), saved, "not overwritten while it stands")
            event = t.keep_event()
            self.assertEqual((event["read"], event["error"]),
                             ("stale", "the practice record (observe.sqlite) could not be read"))
            self.assertEqual(event["kept"], [{"family": "kept", "version": 1, "sample": None, "negative": None,
                                              "sessions": None, "closes": None}], "this process has not read the record")
            self.assertNotIn("alert", event)
            self.clock.advance(KEEP_STALE_SECONDS - 60)     # an hour after the last good read: it still stands
            self.assertEqual(t.idle_pass()["retired"], [])
            self.assertEqual((t.keep_read, self.store.get(practice.KEEP_KV)), ("stale", saved))
            self.clock.advance(1)                           # then none does, with one alert
            self.assertEqual([r["family"] for r in t.idle_pass()["retired"]], ["kept"])
            self.assertEqual((t.kept, t.keep_read), (frozenset(), "failed"))
            self.assertEqual(self.store.get(practice.KEEP_KV), {"at": self.clock(), "families": {}})
            self.assertTrue(t.keep_event()["alert"])

    def test_a_saved_keep_older_than_the_hour_or_malformed_is_not_used(self):
        self.family("kept")
        self.dead("kept")
        self.cohort("kept")
        self.tournament().incubator_keep()
        self.clock.advance(KEEP_STALE_SECONDS + 1)
        t = self.tournament()
        with mock.patch.object(practice, "cohort_status", return_value=None):
            self.assertEqual((t.incubator_keep(), t.keep_read), (frozenset(), "failed"), "a stale saved keep")
            self.assertEqual(self.store.get(practice.KEEP_KV), {"at": self.clock(), "families": {}})
            now = self.clock()
            for value in ("not a keep", [1], {"at": True, "families": {"kept": 1}}, {"at": now + 60, "families": {"kept": 1}},
                          {"at": now, "families": ["kept"]}, {"at": now, "families": {"kept": True}},
                          {"at": now, "families": {"kept": "1"}}, {"at": now, "families": {}}, {"families": {"kept": 1}}):
                self.store.put(practice.KEEP_KV, value)
                t = self.tournament()
                self.assertEqual((t.incubator_keep(), t.keep_read), (frozenset(), "failed"), value)
            with mock.patch.object(self.store, "get", side_effect=RuntimeError("locked")):
                t = self.tournament()
                self.assertEqual((t.incubator_keep(), t.keep_read), (frozenset(), "failed"), "never raises")

    def test_a_saved_keep_stands_only_until_a_read_of_its_own_and_at_most_the_cap(self):
        for fid in ("a", "b", "c"):
            self.family(fid)
            self.cohort(fid)
        self.store.put(practice.KEEP_KV, {"at": self.clock() - 60, "families": {"gone": 4, "b": 1, "a": 1}})
        t = self.tournament()
        self.assertEqual((t.incubator_keep(), t.keep_read), (frozenset({"a", "b", "c"}), "ok"), "a good read")
        self.assertEqual(self.store.get(practice.KEEP_KV),
                         {"at": self.clock(), "families": {"a": 1, "b": 1, "c": 1}}, "the good read overwrites it")
        self.store.put(practice.KEEP_KV, {"at": self.clock() - 60, "families": {"gone": 4, "b": 1, "a": 1}})
        self.settings["tournament"]["incubator_keep_max"] = 3
        t = self.tournament()
        with mock.patch.object(practice, "cohort_status", return_value=None):
            self.assertEqual((t.incubator_keep(), t.keep_read), (frozenset({"gone", "a", "b"}), "stale"), "the saved keep")
        self.settings["tournament"]["incubator_keep_max"] = 2
        t = self.tournament()
        with mock.patch.object(practice, "cohort_status", return_value=None):
            self.assertEqual((t.incubator_keep(), t.keep_read), (frozenset({"a", "b"}), "stale"), "the cap, by name")
        self.assertEqual((t.incubator_keep(), t.keep_read), (frozenset({"a", "b"}), "ok"), "then its own read")
        self.assertEqual(self.store.get(practice.KEEP_KV), {"at": self.clock(), "families": {"a": 1, "b": 1}})

    def test_a_swarm_store_error_is_not_blamed_on_the_practice_record(self):
        self.family("a")
        self.cohort("a")
        t = self.tournament()
        with mock.patch.object(self.store, "families", side_effect=RuntimeError("locked")):
            self.assertEqual((t.incubator_keep(), t.keep_read), (frozenset(), "failed"))
        event = t.keep_event()
        self.assertEqual(event["error"], "the swarm's families could not be read or ordered (RuntimeError)")
        self.assertNotIn("observe.sqlite", event["text"])

    def test_the_round_records_the_keep_once_privately_and_saves_it_for_the_researchers(self):
        self.family("kept")
        self.dead("kept")
        self.cohort("kept")
        self.family("other")
        t = self.tournament()
        families = self.store.families()
        t.incubator_keep()
        self.assertEqual((self.store.events_after(0), self.store.families()), ([], families), "no event, no family write")
        self.assertEqual(self.store.get(practice.KEEP_KV), {"at": self.clock(), "families": {"kept": 1}})
        self.assertEqual(practice.kept_version(self.store, "kept", now=self.clock()), 1)
        self.assertIsNone(practice.kept_version(self.store, "other", now=self.clock()))
        self.assertIsNone(practice.kept_version(self.store, "kept", now=self.clock() + practice.KEEP_KV_SECONDS + 1),
                          "a saved keep that is not refreshed lapses")
        t.run()
        [event] = [e for e in self.store.events_after(0)
                   if e["kind"] == "swarm.status" and e["payload"].get("action") == "incubator_keep"]
        self.assertEqual(event["payload"]["kept"], [{"family": "kept", "version": 1, "sample": False, "negative": False,
                                                     "sessions": 3, "closes": 0}])
        self.assertEqual((event["payload"]["spared"], event["payload"]["cap"], event["payload"]["read"]),
                         ({"kept": "idle"}, 12, "ok"))
        self.assertNotIn("swarm.status", PUBLIC_KINDS, "private")
        self.assertNotIn("alert", event["payload"])
        self.assertNotIn("error", event["payload"])
        self.assertEqual(t.keep_spared, {}, "the round's event takes what was spared")
        self.assertEqual(self.alive(), ["kept", "other"])

    def test_with_no_cohort_the_round_says_nothing(self):
        self.family("a")
        self.tournament().run()
        self.assertFalse([e for e in self.store.events_after(0) if e["payload"].get("action") == "incubator_keep"])

    def test_the_keep_reads_no_real_money_record(self):
        for name in ("tournament.py", "practice.py"):
            text = (REPO / "league" / "swarm" / name).read_text(encoding="utf-8")
            for word in ("live.sqlite", "RealBook", "incubator_tally", '":i"'):
                self.assertNotIn(word, text, f"{name}: {word}")


# ------------------------------------------------------------------------------------------------ its researcher
class OwnRetire(ResearcherCase):
    def test_a_researchers_own_retire_still_retires_a_kept_family(self):
        self.settings["population"].update(floor=0, start=0)
        self.store.update_family(self.fam["id"], validations=2)
        self.store.add_version(self.fam["id"], CODE, {}, author="seed")
        ledger = ObserveStore(self.root, clock=self.clock)
        self.addCleanup(ledger.close)
        ledger.freeze({"family": self.fam["id"], "version": 1, "observe": True, "band": "gym", "tier": "train",
                       "code": CODE, "params": {}, "best_train": 1.0}, day=practice.session_day(self.clock()))
        t = Tournament(self.store, self.pool, self.settings, clock=self.clock)
        self.assertEqual(t.incubator_keep(), frozenset({self.fam["id"]}))
        self.pool.cancel_family = lambda fid: None
        out: dict = {}
        result = self.researcher()._execute(self.store.family(self.fam["id"]), "retire",
                                            {"reason": "Costs defeated the mechanism."}, out, author="test")
        self.assertEqual(result["status"], "retired")
        self.assertIsNotNone(self.store.family(self.fam["id"])["retired_at"])

    def test_a_kept_familys_researcher_is_not_urged_to_retire_it_and_may_still(self):
        # Review of Sept 30: the status line urged a kept, idle family's researcher to retire it every cycle.
        self.settings["population"].update(floor=0, start=0)
        fid = self.fam["id"]
        self.store.update_family(fid, since_val_trials=idle_limit(self.settings), trials=idle_limit(self.settings))
        r = self.researcher()
        fam = self.store.family(fid)
        self.assertTrue(r.dead(fam))
        self.assertIn("If its mechanism is dead, call retire", r.status(fam))
        self.store.put(practice.KEEP_KV, {"at": self.clock(), "families": {fid: 1}})
        text = r.status(self.store.family(fid))
        self.assertNotIn("If its mechanism is dead", text)
        self.assertIn("Your family is in a live practice cohort", text)
        self.assertTrue(r.can_retire(self.store.family(fid)), "the retire tool stays offered")
        self.assertIn("If you abandon the entire mechanism, call retire with your reason.", text)
        self.clock.advance(practice.KEEP_KV_SECONDS + 1)
        self.assertIn("If its mechanism is dead, call retire", r.status(self.store.family(fid)), "a lapsed keep")
        self.store.put(practice.KEEP_KV, "not a keep")
        self.assertIn("If its mechanism is dead, call retire", r.status(self.store.family(fid)), "never raises")


if __name__ == "__main__":
    unittest.main()
