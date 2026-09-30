"""THE COHORT KEEP (L1, release B, Sept 30; `Tournament.incubator_keep`, `practice.cohort_status`): a Gym family whose
active practice cohort's record is not negative is spared the revision, evaluation and idle retirement rules until its
cohort completes, fails or reaches its session window; the deflated-Sharpe rule, its researcher's own retire and the
population floor still apply; at most `tournament.incubator_keep_max` (12) families, 0 turning it off. Research attention
only: the keep reads the House's practice record read-only and writes nothing but its one private round event."""

from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import os
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from league.live.observe import ObserveStore
from league.swarm import practice
from league.swarm import settings as S
from league.swarm.hook import PUBLIC_KINDS
from league.swarm.researcher import idle_limit
from league.swarm.store import SwarmStore
from league.swarm.tournament import (KEEP_MAX, KEEP_STALE_SECONDS, Tournament, keep_order)
from league.tests.swarm_fakes import Clock
from league.tests.test_swarm_researcher import ResearcherCase
from league.tests.test_swarm_rounds import FakeGymPool

REPO = Path(__file__).resolve().parents[2]
NEW_YORK = ZoneInfo("America/New_York")
HAVE_NUMPY = importlib.util.find_spec("numpy") is not None
EVAL = "bundle-b:fill-1:exec-b"          # a stand-in for the House's practice evaluator (bundle, fill model, fingerprint)
FIRST = "2026-10-01"                      # a Thursday: sessions Oct 1, 2 and 5 before Tue Oct 6
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
               validation_t: float | None = None, dte: int = 3) -> dict:
        return self.ledger.freeze({"family": fid, "version": version, "observe": True, "band": "gym", "tier": tier,
                                   "code": CODE.replace("[0, 3]", f"[0, {dte}]"), "params": {"hold": 3},
                                   "structure": "debit_vertical", "roots": ["SPY"], "run_sha": f"sha-{fid}-{version}",
                                   "best_train": best_train, "validation_t": validation_t}, day=day)

    def practised(self, fid: str, days=(FIRST, "2026-10-02", "2026-10-05"), *, version: int = 1, open_mark: float = 0.0,
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

    def test_a_negative_record_is_not_kept_and_zero_is(self):
        cases = {
            "fresh": ([], 0.0),                                                     # no close yet: kept
            "flat": ([(FIRST, 5.0, 50.0, False), ("2026-10-02", -5.0, 50.0, False)], 0.0),   # exactly zero: kept
            "lost": ([(FIRST, -0.01, 50.0, False)], 0.0),                          # program P&L below zero
            "forced": ([(FIRST, 4.0, 50.0, False), (FIRST, -4.01, 50.0, True)], 0.0),   # program >= 0, all < 0
            "marked": ([(FIRST, 4.0, 50.0, False)], -4.01),                        # all + the open mark < 0
            "carried": ([(FIRST, 4.0, 50.0, False)], -4.0),                        # all + the open mark = 0: kept
        }
        for fid, (trades, mark) in cases.items():
            self.family(fid)
            self.cohort(fid)
            self.practised(fid, open_mark=mark)
            if trades:
                self.closed(fid, trades)
        self.assertEqual(self.tournament().incubator_keep(), frozenset({"fresh", "flat", "carried"}))

    def test_only_the_cohorts_own_evaluator_counts(self):
        self.family("old-loss")
        self.cohort("old-loss")
        self.closed("old-loss", [(FIRST, -40.0, 50.0, False)], evaluator="an-older-evaluator")
        self.family("old-win")
        self.cohort("old-win")
        self.closed("old-win", [(FIRST, 90.0, 50.0, False)], evaluator="an-older-evaluator")
        self.closed("old-win", [(FIRST, -1.0, 50.0, False)])
        self.assertTrue(self.keeps("old-loss"), "another evaluator's loss is not this cohort's record")
        self.assertFalse(self.keeps("old-win"), "nor does another evaluator's gain rescue it")

    def test_the_keep_ends_when_the_cohort_fails_or_its_window_runs_out(self):
        self.family("failed")
        self.cohort("failed")
        self.ledger.fail_cohort("failed", 1, day="2026-10-05", reason="refused")
        self.family("windowed")
        self.cohort("windowed")                             # a 0-3 DTE program: a 10-session window
        self.family("long")
        self.cohort("long", dte=45)                         # ceil(45 x 5 / 7) + 3 = 36 sessions
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
        self.practised("target")
        self.closed("target", [(d, 1.0, 50.0, False) for d in (FIRST, "2026-10-02", "2026-10-05") for _ in range(4)])
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

    def test_the_cohort_status_reads_without_writing_and_never_raises(self):
        self.family("a")
        self.cohort("a")
        self.practised("a", days=(FIRST, "2026-10-02", "2026-10-05", "2026-10-06"), open_mark=-3.0)
        self.closed("a", [(FIRST, 12.0, 60.0, False), ("2026-10-06", -2.0, 40.0, False), ("2026-10-02", -1.0, 20.0, True)])
        self.closed("a", [(FIRST, -99.0, 60.0, False)], evaluator="an-older-evaluator")
        self.ledger.close()
        db = self.root / "observe.sqlite"
        before = (db.stat().st_mtime_ns, db.read_bytes())
        [row] = practice.cohort_status(self.root, today="2026-10-06")
        self.assertEqual((db.stat().st_mtime_ns, db.read_bytes()), before, "read-only (SQLite's WAL reader may add its "
                                                                           "empty -shm/-wal sidecars, as practice_summary's)")
        self.assertEqual({k: row[k] for k in ("family", "version", "first_day", "evaluator", "tier", "best_train", "run_sha",
                                              "window", "elapsed", "sessions", "coverage", "closes_program",
                                              "closes_program_before", "pnl_program", "closes_all", "pnl_all",
                                              "max_loss_all", "open_mark", "return_on_risk")},
                         {"family": "a", "version": 1, "first_day": FIRST, "evaluator": EVAL, "tier": "train",
                          "best_train": 1.0, "run_sha": "sha-a-1", "window": 10, "elapsed": 3, "sessions": 3,
                          "coverage": 1.0, "closes_program": 2, "closes_program_before": 1, "pnl_program": 10.0,
                          "closes_all": 3, "pnl_all": 9.0, "max_loss_all": 120.0, "open_mark": -3.0,
                          "return_on_risk": 0.075})
        self.assertEqual(practice.cohort_status(self.root / "nowhere"), [])
        self.assertEqual(practice.cohort_status(None), [])
        (self.root / "observe.sqlite").write_bytes(b"not a database at all" * 100)
        for suffix in ("-wal", "-shm"):
            if (self.root / f"observe.sqlite{suffix}").exists():
                os.unlink(self.root / f"observe.sqlite{suffix}")
        self.assertIsNone(practice.cohort_status(self.root, today="2026-10-06"), "unreadable is None, never []")

    def test_a_practice_row_older_than_its_cohort_has_no_session_count(self):
        self.family("a")
        self.practised("a", days=("2026-09-30",))
        self.cohort("a")
        self.practised("a", days=(FIRST, "2026-10-02"))
        [row] = practice.cohort_status(self.root, today="2026-10-06")
        self.assertIsNone(row["sessions"])
        self.assertTrue(self.keeps("a"), "the keep still holds it (its record is not negative)")


# ------------------------------------------------------------------------------------------------ the cap and its order
class Cap(KeepCase):
    def test_at_most_twelve_the_sample_first_by_return_on_risk_then_the_practice_leagues_order(self):
        self.assertEqual(KEEP_MAX, 12)
        for i in range(12):                                          # Train tier by best Train score: t00 the best
            self.family(f"t{i:02d}")
            self.cohort(f"t{i:02d}", best_train=float(20 - i))
        self.family("val")
        self.cohort("val", tier="validated", validation_t=0.5)       # the validated tier before any Train one
        for fid, pnl in (("s-low", 1.0), ("s-high", 3.0)):           # the sample met: 3 sessions, 10 program closes
            self.family(fid)
            self.cohort(fid, best_train=-5.0)
            self.practised(fid)
            self.closed(fid, [(d, pnl, 50.0, False) for d in (FIRST, "2026-10-02", "2026-10-05", "2026-10-05", "2026-10-05")
                              for _ in range(2)])
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

    def test_zero_turns_it_off_and_a_malformed_cap_reads_as_twelve(self):
        self.family("a")
        self.dead("a")
        self.cohort("a")
        t = self.tournament()
        for raw, want in ((5, 5), (96, 96), (True, 12), ("12", 12), (-1, 12), (97, 12), (12.5, 12), (None, 12), (0, 0)):
            self.settings["tournament"]["incubator_keep_max"] = raw
            self.assertEqual(t.keep_max(), want, raw)
        self.assertEqual(t.incubator_keep(), frozenset())
        self.assertEqual((t.keep_read, t.keep_event()), ("off", None))
        self.assertEqual([r["family"] for r in t.retirements(self.store.families(alive=True))], ["a"], "main's rules")


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
            self.assertEqual(t.keep_event()["read"], "stale")
            self.clock.advance(1)
            self.assertEqual((t.incubator_keep(), t.keep_read), (frozenset(), "failed"))
            first, second = t.keep_event(), t.keep_event()
            self.assertTrue(first["alert"])
            self.assertNotIn("alert", second, "said once until it reads again")
            self.assertEqual([r["family"] for r in t.retirements(self.store.families(alive=True))], ["a"])
        self.assertEqual(t.incubator_keep(), frozenset())

    def test_a_fresh_process_that_cannot_read_keeps_nothing(self):
        self.family("a")
        self.cohort("a")
        with mock.patch.object(practice, "cohort_status", side_effect=RuntimeError("boom")):
            t = self.tournament()
            self.assertEqual((t.incubator_keep(), t.keep_read), (frozenset(), "failed"))

    def test_the_round_records_the_keep_once_privately_and_writes_nothing_else(self):
        self.family("kept")
        self.dead("kept")
        self.cohort("kept")
        self.family("other")
        t = self.tournament()
        families = self.store.families()
        t.incubator_keep()
        self.assertEqual((self.store.events_after(0), self.store.families()), ([], families), "the keep is read-only")
        t.run()
        [event] = [e for e in self.store.events_after(0)
                   if e["kind"] == "swarm.status" and e["payload"].get("action") == "incubator_keep"]
        self.assertEqual(event["payload"]["kept"], [{"family": "kept", "version": 1, "sample": False, "sessions": 0,
                                                     "closes": 0}])
        self.assertEqual((event["payload"]["spared"], event["payload"]["cap"], event["payload"]["read"]),
                         ({"kept": "idle"}, 12, "ok"))
        self.assertNotIn("swarm.status", PUBLIC_KINDS, "private")
        self.assertNotIn("alert", event["payload"])
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


# ------------------------------------------------------------------------------------------------ its researcher's retire
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


if __name__ == "__main__":
    unittest.main()
