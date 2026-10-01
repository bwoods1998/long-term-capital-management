"""The incubator's swarm facts (release B2, league/swarm/incubator.py): the Train and drift mark the tournament writes for
a practised version, and the incubator review and audit the gate makes. Neither resets evidence, reads the House's real
rows, spends a holdout look or touches the gate's own review state. Invented stores, practice records and model answers
only."""

from __future__ import annotations

import copy
import datetime as dt
import json
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from league.gym.review_contract import review_contract
from league.gym.safety import CodeRefused
from league.live.observe import ObserveStore
from league.swarm import bands
from league.swarm import evaluator as E
from league.swarm import incubator as I
from league.swarm.bands import demoted
from league.swarm.gate import Gate, incubator_stage, run_sha
from league.swarm.researcher import demote_version, screen_best
from league.swarm.settings import DEFAULTS
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import Clock, drift_block, result
from league.tests.test_swarm_rounds import FakeGymPool, RoundCase, review_failure, strong

REPO = Path(__file__).resolve().parents[2]
EVALUATOR = {"image": "sbcp_gym_b", "bundle": "gym-engine-4-aaaaaaaaaaaa", "execution": "e" * 64}
PRACTICE = f"{EVALUATOR['bundle']}:fill-v1:{EVALUATOR['execution']}"
OBJECTIVE = "worst-train-year-v1"
#: Oct 6, 2026, 10:00 in New York: the cohorts below practised Oct 1, 2 and 5.
TODAY = "2026-10-06"
AT = dt.datetime(2026, 10, 6, 14, 0, tzinfo=dt.timezone.utc).timestamp()
SESSIONS = ("2026-10-01", "2026-10-02", "2026-10-05")
CODE = '''# {fid}
NEEDS = {{"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 2, "start": 571, "end": 958}}
PARAMS = {{"hold": 3}}

def decide(ctx):
    return []
'''
FAILING = drift_block(t=0.4, alpha_usd=30.0, drift_usd=900.0)  # the profit is the market's drift
PASS = {"text": json.dumps({"verdict": "pass", "reasons": []})}
UNCLEAR = {"text": "{}"}


def fail_reply(reason: str = "a synthetic finding") -> dict:
    return {"text": json.dumps(review_failure(reason))}


def live_rows(root: Path, fid: str, n: int) -> list | None:
    """Release B1's own reader (`bands.incubator`) on this store, once B1 is merged with B2 (release B); None before."""
    reader = getattr(bands, "incubator", None)
    return None if reader is None else reader(root, family=fid, version=n)


def accepts(state: dict, n: int, sha: str, kv: dict) -> bool:
    """SPEC-B §3.1's conditions 2 to 5, word for word, as `bands.incubator` (release B1) applies them to these facts: the
    field names B2 writes are the ones B1 reads."""
    if demoted(state, n):
        return False
    mark = (state.get("train_passed") or {}).get(str(n))
    if not mark or mark.get("evaluator") != kv["research_evaluator"] or mark.get("objective") != kv["train_objective"]:
        return False
    contract = review_contract()["sha256"]

    def passed(record):
        return (isinstance(record, dict) and record.get("sha") == sha and record.get("verdict") == "pass"
                and (record.get("audit") or {}).get("verdict") == "pass" and record.get("contract_sha") == contract
                and (record.get("audit") or {}).get("contract_sha") == contract)

    if not (passed(state.get("review")) or passed((state.get("incubator_reviews") or {}).get(sha))):
        return False
    outcome = state.get("gate_outcome") or {}
    return not (outcome.get("sha") == sha and outcome.get("result") in ("refused", "failed", "demoted"))


class Fixture:
    """A swarm store and the House's practice record on one root, the clock on Oct 6, the current evaluator adopted."""

    def fixture(self, store: SwarmStore, root: Path, clock: Clock) -> None:
        self.store, self.root, self.clock = store, root, clock
        clock.t = AT
        store.put(E.KEY, EVALUATOR)
        store.put("train_objective", OBJECTIVE)
        self.ledger = ObserveStore(root, clock=clock)
        self.ledger.evaluator = PRACTICE
        self.addCleanup(self.ledger.close)
        self.minute = AT - 7 * 86400

    def family(self, fid: str, **state) -> int:
        self.store.add_family({"id": fid, "mechanism": "An invented mechanism for the incubator's facts.",
                               "structure": "debit_vertical", "roots": ["SPY"], "dte": [0, 5]}, origin="test")
        v = self.store.add_version(fid, CODE.format(fid=fid), {"hold": 3}, author="test")
        if state:
            self.store.set_state(fid, **state)
        return int(v["n"])

    def train(self, fid: str, n: int, *, eligible: bool = True, identity: dict | None = EVALUATOR, drift="default") -> dict:
        r = result(f"{fid}-v{n}")
        r["summary"]["train_eligible"] = eligible
        if identity is not None:
            r.update(gym_image=identity["image"], gym_bundle=identity["bundle"])
        if drift is None:
            r.pop("drift", None)
        elif drift != "default":
            r["drift"] = copy.deepcopy(drift)
        return self.store.add_run(fid, n, r, window="train", stress=1.0, purpose="train")

    def robust(self, fid: str, n: int, pnl: float = 40.0, *, status: str = "ok") -> None:
        rows = dict((self.store.family(fid)["state"].get("robustness") or {}))
        rows[str(n)] = {"stress_1.5": {"status": status, "pnl": pnl, "gym_image": EVALUATOR["image"],
                                       "gym_bundle": EVALUATOR["bundle"]}}
        self.store.set_state(fid, robustness=rows)

    def cohort(self, fid: str, n: int, *, day: str = SESSIONS[0]) -> dict:
        version = self.store.version(fid, n)
        return self.ledger.freeze({"family": fid, "version": n, "observe": True, "band": "gym", "tier": "train",
                                   "structure": "debit_vertical", "roots": ["SPY"], "code": version["code"],
                                   "params": version["params"], "run_sha": run_sha(version)}, day=day)

    def practised(self, fid: str, n: int, trades, *, days=SESSIONS, evaluator: str = PRACTICE) -> None:
        """A live minute on each of `days`, then the closed trades [(exit day, pnl, forced)]."""
        for day in days:
            self.minute += 60
            self.ledger.practice([{"family": fid, "version": n, "tier": "train", "lineage": fid, "structure": "debit_vertical",
                                   "roots": ["SPY"], "capital": 10000.0, "account": "a", "at": self.minute, "day": day,
                                   "equity": 10000.0, "open_positions": 0, "open_mark_pnl": 0.0, "due": True, "made": True,
                                   "status": "live"}])
        start = len(self.ledger._connect().execute("SELECT 1 FROM trades").fetchall())
        self.ledger.add(f"{fid}@{n}:o", fid, n, [
            {"id": start + i, "day": d, "exit_day": d, "pnl": p, "max_loss": 50.0, "exit_reason": "program", "forced": f,
             "evaluator": evaluator} for i, (d, p, f) in enumerate(trades, 1)], account="a")

    def eligible(self, fid: str) -> int:
        """A version that meets every condition of the mark, practising in an active, current cohort."""
        n = self.family(fid)
        self.train(fid, n)
        self.robust(fid, n)
        self.cohort(fid, n)
        return n

    def state(self, fid: str) -> dict:
        return self.store.family(fid)["state"]

    def sha(self, fid: str, n: int) -> str:
        return run_sha(self.store.version(fid, n))

    def kv(self) -> dict:
        return {"research_evaluator": self.store.get(E.KEY), "train_objective": self.store.get("train_objective")}


class Case(Fixture, unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        clock = Clock()
        store = SwarmStore(root, clock=clock)
        self.addCleanup(store.close)
        self.settings = copy.deepcopy(DEFAULTS)
        self.fixture(store, root, clock)

    def facts(self) -> dict:
        return I.facts(self.store, self.settings, self.root, clock=self.clock)


# ---------------------------------------------------------------------------------------------------- the mark
class Mark(Case):
    def test_a_practised_version_that_passes_train_and_the_drift_screen_is_marked_under_the_current_evaluator(self):
        n = self.eligible("a")
        out = self.facts()
        self.assertEqual((out["cohorts"], out["marked"], out["written"]), (1, 1, ["a@1"]))
        mark = self.state("a")["train_passed"][str(n)]
        run = self.store.version_runs("a", n, window="train")[0]
        self.assertEqual(mark["evaluator"], EVALUATOR)
        self.assertEqual(mark["objective"], OBJECTIVE)
        self.assertEqual(mark["run"], run["run_id"])
        self.assertEqual(mark["robust_pnl"], 40.0)
        self.assertEqual(mark["drift"], {"t": 2.0, "positive": 3, "years": 3})
        self.assertEqual(mark["at"], AT)
        again = self.facts()
        self.assertEqual((again["marked"], again["written"]), (1, []), "a current mark is not written again")
        self.assertEqual(self.state("a")["train_passed"][str(n)], mark)

    def test_each_condition_removed_alone_writes_no_mark(self):
        cases = {  # why: (arrange, the refusal's words, drop: an existing mark goes)
            "no eligible Train run": (lambda f, n: self.train(f, n, eligible=False), "no eligible Train run", False),
            "a Train run of another evaluator": (lambda f, n: self.train(f, n, identity={**EVALUATOR, "bundle": "gym-engine-4-old"}),
                                                 "no eligible Train run", False),
            "its 1.5x run has not landed": (lambda f, n: (self.train(f, n), self.robust(f, n, status="failed")), "not landed", False),
            "its 1.5x run lost": (lambda f, n: (self.train(f, n), self.robust(f, n, pnl=-3.0)), "lost money", True),
            "its 1.5x run broke even": (lambda f, n: (self.train(f, n), self.robust(f, n, pnl=0.0)), "lost money", True),
            "demoted at 1.5x": (lambda f, n: (self.train(f, n), self.store.set_state(f, robust_failed=[n])), "demoted", True),
            "demoted by the drift screen": (lambda f, n: (self.train(f, n), self.store.set_state(f, drift_failed={str(n): "x"})),
                                            "demoted", True),
            "drift figures owed": (lambda f, n: self.train(f, n, drift=None), "owed", False),
            "a failed drift screen": (lambda f, n: self.train(f, n, drift=FAILING), "fails the drift screen", True),
            "the gate refused it": (lambda f, n: (self.train(f, n), self.store.refuse(f, n, "review", "x")),
                                    "barred by the gate: the gate refused it (the review)", True),
            "the gate refused it for rations": (lambda f, n: (self.train(f, n), self.store.refuse(f, n, "rations", "x")),
                                                "the gate refused it (the rations)", True),
            "its holdout look failed": (lambda f, n: (self.train(f, n), self.store.add_look(f, n, self.sha(f, n), passed=False,
                                                                                            p_value=0.9, detail={})),
                                        "its holdout look failed", True),
            "the gate demoted it": (lambda f, n: (self.train(f, n), self.store.set_state(
                f, gate_outcome={"sha": self.sha(f, n), "result": "demoted"})), "the gate's outcome for it is demoted", True),
            "a demotion recorded earlier": (lambda f, n: (self.train(f, n), self.store.set_state(
                f, incubator_barred={self.sha(f, n): {"why": "the gate's outcome for it was demoted", "at": 1.0}})),
                "was demoted", True),
            "the gate's reviewer failed it (no refusal row)": (lambda f, n: (self.train(f, n), self.store.set_state(
                f, review={"sha": self.sha(f, n), "verdict": "fail"})), "barred by the gate: the gate's reviewer failed it", True),
            "the gate's audit failed it (no refusal row)": (lambda f, n: (self.train(f, n), self.store.set_state(
                f, review={"sha": self.sha(f, n), "verdict": "fail", "stage": "audit", "audit": {"verdict": "fail"}})),
                "the gate's audit failed it", True),
            "the gate's review of it cannot be read": (lambda f, n: (self.train(f, n), self.store.set_state(
                f, review={"sha": self.sha(f, n), "verdict": None})), "the gate's review of it cannot be read", True),
            "the gate's review record cannot be read": (lambda f, n: (self.train(f, n), self.store.set_state(
                f, review="garbage")), "the gate's review record cannot be read", True),
            "the incubator's reviewer failed it": (lambda f, n: (self.train(f, n), self.store.set_state(
                f, incubator_reviews={self.sha(f, n): {"sha": self.sha(f, n), "verdict": "fail",
                                                       "contract_sha": review_contract()["sha256"]}})),
                "the incubator's reviewer failed it", True),
            "a gate bar recorded earlier that cannot be read": (lambda f, n: (self.train(f, n), self.store.set_state(
                f, incubator_barred={self.sha(f, n): "garbage"})), "the gate barred it", True),
        }
        for i, (why, (arrange, words, final)) in enumerate(cases.items()):
            fid = f"case-{i}"  # a family id (the store's slug is at most 36 characters)
            n = self.family(fid)
            self.robust(fid, n)
            arrange(fid, n)
            self.cohort(fid, n)
            mark, reason, is_final = I.mark_of(self.store, self.store.family(fid), n, self.settings, evaluator=EVALUATOR,
                                               objective=OBJECTIVE, clock=self.clock)
            self.assertIsNone(mark, why)
            self.assertIn(words, reason, why)
            self.assertEqual(is_final, final, why)
        out = self.facts()
        self.assertEqual(out["cohorts"], len(cases))
        self.assertEqual(out["written"], [])
        for fam in self.store.families():
            self.assertNotIn("train_passed", fam["state"], fam["id"])

    def test_no_mark_outside_an_active_current_cohort_of_an_alive_gym_family(self):
        n = self.eligible("retired")
        self.store.retire_gym("retired", "finished", floor=0, source="test")
        n = self.eligible("candidate")
        self.store.set_band("candidate", "candidate", reason="test")
        n = self.eligible("complete")
        self.ledger._connect().execute("UPDATE cohorts SET status='complete' WHERE family='complete'")
        n = self.eligible("failed")
        self.ledger.fail_cohort("failed", n, day=TODAY, reason="refused")
        self.ledger.evaluator = f"{EVALUATOR['bundle']}:fill-v1:{'f' * 64}"
        n = self.eligible("stale")  # frozen under another execution fingerprint
        self.ledger.evaluator = PRACTICE
        n = self.family("unpractised")
        self.train("unpractised", n)
        self.robust("unpractised", n)
        out = self.facts()
        self.assertEqual((out["cohorts"], out["written"]), (2, []), "the retired and the Candidate's cohorts are read, not marked")
        for fam in self.store.families():
            self.assertNotIn("train_passed", fam["state"], fam["id"])

    def test_an_off_drift_screen_writes_nothing_and_takes_existing_marks_until_it_is_on_again(self):
        self.eligible("a")
        self.settings["tournament"]["drift_screen"] = False
        out = self.facts()
        self.assertEqual((out["written"], out["waiting"]), ([], 1))
        self.assertNotIn("train_passed", self.state("a"))
        self.settings["tournament"]["drift_screen"] = True
        self.assertEqual(self.facts()["written"], ["a@1"])
        n = self.eligible("b")
        self.store.set_state("b", train_passed={str(n): self.state("a")["train_passed"]["1"]})  # e.g. an ended cohort
        self.ledger._connect().execute("UPDATE cohorts SET status='complete' WHERE family='b'")
        self.settings["tournament"]["drift_screen"] = False  # an off screen never passes: every mark goes
        out = self.facts()
        self.assertEqual(sorted(out["removed"]), ["a@1", "b@1"])
        self.assertEqual((self.state("a")["train_passed"], self.state("b")["train_passed"]), ({}, {}))
        self.settings["tournament"]["drift_screen"] = True
        self.assertEqual(self.facts()["written"], ["a@1"], "not final: marked again once the screen is on and passes")

    def test_without_a_research_evaluator_or_an_objective_or_a_readable_record_nothing_is_written(self):
        self.eligible("a")
        self.store.put(E.KEY, None)
        self.assertEqual(self.facts()["written"], [])
        self.store.put(E.KEY, EVALUATOR)
        self.store.put("train_objective", None)
        self.assertEqual(self.facts()["written"], [])
        self.store.put("train_objective", OBJECTIVE)
        with patch.object(I, "OBSERVE_FILE", "missing.sqlite"):
            self.assertEqual(self.facts()["cohorts"], 0)
        self.assertNotIn("train_passed", self.state("a"))
        self.assertEqual(self.facts()["written"], ["a@1"])

    def test_a_stale_mark_is_replaced_and_a_mark_whose_version_fails_for_good_is_removed(self):
        n = self.eligible("a")
        self.store.set_state("a", train_passed={str(n): {"evaluator": {**EVALUATOR, "bundle": "old"}, "objective": OBJECTIVE}})
        self.assertEqual(self.facts()["written"], ["a@1"])
        self.assertEqual(self.state("a")["train_passed"][str(n)]["evaluator"], EVALUATOR)
        self.store.set_state("a", drift_failed={str(n): "fails the drift screen"})  # e.g. screened by the tournament
        out = self.facts()
        self.assertEqual(out["removed"], ["a@1"])
        self.assertEqual(self.state("a")["train_passed"], {})

    def test_a_mark_is_not_removed_while_its_figures_are_only_owed(self):
        n = self.eligible("a")
        self.facts()
        self.store.set_state("a", robustness={})  # its 1.5x figure is owed again: nothing is final
        out = self.facts()
        self.assertEqual((out["removed"], out["waiting"]), ([], 1))
        self.assertIn(str(n), self.state("a")["train_passed"])

    def test_a_demotion_landing_while_the_mark_is_made_wins(self):
        n = self.eligible("a")
        real = I.mark_of

        def racing(store, fam, n, settings, **kw):
            answer = real(store, fam, n, settings, **kw)
            demote_version(store, store.family(fam["id"]), n, why="lost money on Train at 1.5x the half-spread")
            return answer

        with patch.object(I, "mark_of", racing):
            out = self.facts()
        self.assertEqual(out["written"], [])
        self.assertNotIn(str(n), self.state("a").get("train_passed") or {})

    def test_the_newest_marks_are_kept(self):
        self.family("a")
        marks = {str(k): {"evaluator": EVALUATOR, "objective": OBJECTIVE} for k in range(2, 2 + I.MARKS_KEPT)}
        self.store.set_state("a", train_passed=marks)
        for _ in range(1 + I.MARKS_KEPT):
            self.store.add_version("a", CODE.format(fid="a") + f"# v{_}\n", {"hold": 3}, author="test")
        n = 1 + I.MARKS_KEPT + 1
        self.train("a", n)
        self.robust("a", n)
        self.cohort("a", n)
        self.facts()
        kept = self.state("a")["train_passed"]
        self.assertEqual(len(kept), I.MARKS_KEPT)
        self.assertIn(str(n), kept)
        self.assertNotIn("2", kept, "the oldest version's mark goes")

    def test_demote_version_pops_the_mark_and_the_drift_screen_does_too(self):
        n = self.eligible("a")
        self.facts()
        demote_version(self.store, self.store.family("a"), n)
        self.assertEqual(self.state("a")["train_passed"], {})
        self.assertTrue(demoted(self.state("a"), n))
        b = self.eligible("b")
        self.facts()
        self.assertIn(str(b), self.state("b")["train_passed"])
        self.store.update_family("b", best_version=b)
        self.train("b", b, drift=FAILING)  # its newest Train run's figures fail the screen
        self.assertEqual([d["version"] for d in screen_best(self.store, "b", self.settings, clock=self.clock)], [b])
        self.assertEqual(self.state("b")["train_passed"], {})
        demote_version(self.store, self.store.family("b"), b)  # a version without a mark: nothing to pop
        self.assertEqual(self.state("b")["train_passed"], {})

    def test_adoption_of_a_new_evaluator_clears_marks_and_reviews_but_never_a_bar_or_the_gates_rows(self):
        n = self.eligible("a")
        self.facts()
        bars = {"y": {"why": "the gate's outcome for it was demoted", "at": 1.0}}
        self.store.set_state("a", incubator_reviews={"x": {"sha": "x", "verdict": "pass"}}, incubator_barred=bars)
        E.adopt(self.store, {**EVALUATOR, "bundle": "gym-engine-4-bbbbbbbbbbbb"})
        state = self.state("a")
        self.assertEqual((state["train_passed"], state["incubator_reviews"]), ({}, {}))
        self.assertEqual(state["incubator_barred"], bars, "a bar is as durable as a refusal row (the owner's term)")
        self.assertIn(str(n), state["previous_evaluator_selection"]["train_passed"], "archived, privately")
        for key in ("train_passed", "incubator_reviews"):
            self.assertIn(key, E.SELECTION_KEYS)
        self.assertNotIn("incubator_barred", E.SELECTION_KEYS)
        self.assertNotIn("incubator_barred", state["previous_evaluator_selection"], "never cleared, so never archived")
        self.store.refuse("a", n, "review", "a synthetic refusal")  # a refusal row outlives any adoption
        mark, why, drop = I.mark_of(self.store, self.store.family("a"), n, self.settings, evaluator=EVALUATOR,
                                    objective=OBJECTIVE, clock=self.clock)
        self.assertEqual((mark, drop), (None, True))
        self.assertIn("refused", why)

    def test_a_mark_moves_no_band_and_changes_nothing_else(self):
        n = self.eligible("a")
        self.practised("a", n, [(SESSIONS[i % 3], 9.0, False) for i in range(30)])
        before = self.store.family("a")
        self.facts()
        after = self.store.family("a")
        self.assertEqual({k: v for k, v in after["state"].items() if k != "train_passed"}, before["state"])
        self.assertEqual({k: v for k, v in after.items() if k != "state"}, {k: v for k, v in before.items() if k != "state"})
        self.assertEqual((self.store.looks(), self.store.forward("a"), self.store.refusals("a")), ([], [], []))

    def test_the_tournaments_round_marks_after_validation_and_reports_it(self):
        self.eligible("a")
        row = Tournament(self.store, FakeGymPool(strong), self.settings, clock=self.clock).run()
        self.assertEqual(row["incubator"]["written"], ["a@1"])
        self.assertIn("1", self.state("a")["train_passed"])
        with patch.object(I, "facts", side_effect=RuntimeError("boom")):
            row = Tournament(self.store, FakeGymPool(strong), self.settings, clock=self.clock).run()
        self.assertEqual(row["incubator"], {"error": "RuntimeError"}, "an error never fails the round")
        errors = [e for e in self.store.events_after(0) if e["payload"].get("action") == "incubator_facts_error"]
        self.assertEqual(len(errors), 1)


# ---------------------------------------------------------------------------------------------------- the practice record
class Record(Case):
    def test_the_cohort_reader_counts_completed_sessions_and_program_closes_before_today_under_the_cohorts_evaluator(self):
        n = self.eligible("a")
        self.practised("a", n, [(SESSIONS[0], 5.0, False), (SESSIONS[1], -2.0, False), (SESSIONS[2], 4.0, True),
                                (TODAY, 100.0, False)], days=SESSIONS + (TODAY,))
        self.practised("a", n, [(SESSIONS[2], 50.0, False)], days=(), evaluator="gym-engine-4-old:fill-v1:" + "e" * 64)
        [row] = I.practice_cohorts(self.root, research=EVALUATOR, before=TODAY)
        self.assertEqual((row["family"], row["version"], row["first_day"]), ("a", n, SESSIONS[0]))
        self.assertEqual(row["sessions"], 3, "today's session is not complete")
        self.assertEqual((row["closes_program"], row["pnl_program"]), (2, 3.0), "no forced close, no other evaluator, not today")
        self.assertEqual(row["run_sha"], run_sha(self.store.version("a", n)))

    def test_a_practice_record_older_than_its_cohort_is_not_the_cohorts(self):
        n = self.family("a")
        self.practised("a", n, [], days=(SESSIONS[0],))
        self.cohort("a", n, day=SESSIONS[1])
        [row] = I.practice_cohorts(self.root, research=EVALUATOR, before=TODAY)
        self.assertIsNone(row["sessions"])

    def test_the_reader_is_read_only_and_never_raises(self):
        self.eligible("a")
        path = self.root / I.OBSERVE_FILE
        self.ledger.close()
        before = (path.stat().st_mtime_ns, path.read_bytes())
        self.assertEqual(len(I.practice_cohorts(self.root, research=EVALUATOR, before=TODAY)), 1)
        self.assertEqual((path.stat().st_mtime_ns, path.read_bytes()), before)
        self.assertEqual(I.practice_cohorts(self.root, research=None, before=TODAY), [])
        with tempfile.TemporaryDirectory() as other:
            self.assertEqual(I.practice_cohorts(other, research=EVALUATOR, before=TODAY), [])
            Path(other, I.OBSERVE_FILE).write_bytes(b"not a database")
            self.assertEqual(I.practice_cohorts(other, research=EVALUATOR, before=TODAY), [])

    def test_a_current_practice_evaluator_is_the_research_evaluators_bundle_and_fingerprint(self):
        self.assertTrue(I.practice_current(PRACTICE, EVALUATOR))
        for bad in (f"{EVALUATOR['bundle']}::{EVALUATOR['execution']}", f"x:fill:{EVALUATOR['execution']}",
                    f"{EVALUATOR['bundle']}:fill:x", EVALUATOR["bundle"], None, 7):
            self.assertFalse(I.practice_current(bad, EVALUATOR), bad)
        self.assertFalse(I.practice_current(PRACTICE, None))
        self.assertFalse(I.practice_current(PRACTICE, {**EVALUATOR, "execution": None}))

    def test_the_session_day_is_new_yorks(self):
        self.assertEqual(I.session_day(lambda: AT), TODAY)
        self.assertEqual(I.session_day(lambda: dt.datetime(2026, 10, 7, 3, 0, tzinfo=dt.timezone.utc).timestamp()), TODAY)


# ---------------------------------------------------------------------------------------------------- due reviews
class Due(Case):
    def marked(self, fid: str, trades, *, days=SESSIONS) -> int:
        n = self.eligible(fid)
        self.practised(fid, n, trades, days=days)
        self.facts()
        self.assertIn(str(n), self.state(fid)["train_passed"])
        return n

    def ready(self, fid: str = "a") -> int:
        return self.marked(fid, [(SESSIONS[i % 2], 3.0, False) for i in range(5)], days=SESSIONS[:2])

    def due(self) -> list[str]:
        return [f"{r['family']}@{r['version']}" for r in I.due_reviews(self.store, self.settings, self.root, clock=self.clock)]

    def test_a_marked_positive_version_is_due_at_two_sessions_and_five_closes(self):
        n = self.ready()
        [row] = I.due_reviews(self.store, self.settings, self.root, clock=self.clock)
        self.assertEqual((row["family"], row["version"], row["sessions"], row["closes"]), ("a", n, 2, 5))
        self.assertEqual(row["sha"], run_sha(self.store.version("a", n)))

    def test_the_practice_boundaries(self):
        self.marked("one-session", [(SESSIONS[0], 3.0, False)] * 5, days=SESSIONS[:1])
        self.marked("four-closes", [(SESSIONS[0], 3.0, False)] * 4, days=SESSIONS[:2])
        self.marked("forced-fifth", [(SESSIONS[0], 3.0, False)] * 4 + [(SESSIONS[1], 3.0, True)], days=SESSIONS[:2])
        self.marked("flat", [(SESSIONS[0], 3.0, False)] * 4 + [(SESSIONS[1], -12.0, False)], days=SESSIONS[:2])
        self.marked("today", [(SESSIONS[0], 3.0, False)] * 4 + [(TODAY, 3.0, False)], days=SESSIONS[:2])
        self.marked("cent", [(SESSIONS[0], 3.0, False)] * 4 + [(SESSIONS[1], -11.99, False)], days=SESSIONS[:2])
        self.assertEqual(self.due(), ["cent@1"])

    def test_nothing_is_due_without_a_current_mark(self):
        n = self.ready()
        marks = self.state("a")["train_passed"]
        self.store.set_state("a", train_passed={})
        self.assertEqual(self.due(), [])
        self.store.set_state("a", train_passed={str(n): {**marks[str(n)], "objective": "another"}})
        self.assertEqual(self.due(), [])
        self.store.set_state("a", train_passed=marks)
        self.assertEqual(self.due(), ["a@1"])

    def test_a_final_review_or_the_gates_refusal_of_the_program_ends_it(self):
        n = self.ready()
        sha = run_sha(self.store.version("a", n))
        contract = review_contract()["sha256"]
        self.store.set_state("a", incubator_reviews={sha: {"sha": sha, "verdict": "pass", "contract_sha": contract}})
        self.assertEqual(self.due(), ["a@1"], "a review whose audit is owed is not final")
        self.store.set_state("a", incubator_reviews={sha: {"sha": sha, "verdict": "fail", "contract_sha": contract}})
        self.assertEqual(self.due(), [])
        self.store.set_state("a", incubator_reviews={sha: {"sha": sha, "verdict": "fail", "contract_sha": "old"}})
        self.assertEqual(self.due(), ["a@1"], "a review under another contract is not current")
        self.store.set_state("a", incubator_reviews={}, review={"sha": sha, "verdict": "pass", "contract_sha": contract,
                                                                "audit": {"verdict": "pass", "contract_sha": contract}})
        self.assertEqual(self.due(), [], "the gate's own review and audit serve")
        self.assertTrue(accepts(self.state("a"), n, sha, self.kv()))
        self.store.set_state("a", review=None)
        self.store.refuse("a", n, "audit", "a synthetic refusal")
        self.assertEqual(self.due(), [], "the gate's refusal of the program is final, even after its review slot moved on")

    def test_no_review_is_paid_for_a_held_demoted_gated_or_refused_version(self):
        n = self.ready()
        sha = run_sha(self.store.version("a", n))
        for state, why in (({"gate_hold": True}, "held by the operator"),
                           ({"gate_ready": True, "validation_version": n}, "the gate is reviewing it"),
                           ({"gate_outcome": {"sha": sha, "result": "failed"}}, "its holdout look failed"),
                           ({"gate_outcome": {"sha": sha, "result": "refused"}}, "the gate refused it")):
            original = copy.deepcopy(self.state("a"))
            self.store.set_state("a", **state)
            self.assertEqual(self.due(), [], why)
            self.store.update_family("a", state=original)
        self.store.set_state("a", robust_failed=[n])
        self.assertEqual(self.due(), [])

    def test_a_cohort_practising_another_program_is_not_reviewed_for_this_one(self):
        n = self.ready()
        db = self.ledger._connect()
        [snapshot] = db.execute("SELECT snapshot FROM cohorts").fetchone()
        db.execute("UPDATE cohorts SET snapshot=?", (json.dumps({**json.loads(snapshot), "run_sha": "other"}),))
        self.assertEqual(self.due(), [])

    def test_the_oldest_cohort_first(self):
        self.ready("z")
        n = self.family("b")
        self.train("b", n)
        self.robust("b", n)
        self.cohort("b", n, day="2026-09-30")
        self.practised("b", n, [(SESSIONS[0], 3.0, False)] * 5, days=("2026-09-30",) + SESSIONS[:2])
        self.facts()
        self.assertEqual(self.due(), ["b@1", "z@1"])

    def test_the_setting(self):
        self.assertEqual(DEFAULTS["gate"]["incubator_reviews"], 2)
        for raw, want in ((2, 2), (0, 0), (-3, 0), (99, I.REVIEWS_CEILING), (1.0, 1), (1.5, 2), (True, 2), ("3", 2),
                          (float("inf"), 2), (float("nan"), 2), (None, 2)):
            self.assertEqual(I.reviews_per_round({"gate": {"incubator_reviews": raw}}), want, raw)
        self.assertEqual(I.reviews_per_round({}), 2)


# ---------------------------------------------------------------------------------------------------- the gate's reads
class GateCase(Fixture, RoundCase):
    """The gate's rounds on a fixture whose version "a@1" is marked and due (`ready`); no tests of its own."""

    def setUp(self):
        super().setUp()
        self.fixture(self.store, self.root, self.clock)
        self.settings["tournament"]["drift_screen"] = True

    def ready(self, fid: str = "a") -> tuple[int, str]:
        n = self.eligible(fid)
        self.practised(fid, n, [(SESSIONS[i % 2], 3.0, False) for i in range(5)], days=SESSIONS[:2])
        I.facts(self.store, self.settings, self.root, clock=self.clock)
        self.assertIn(str(n), self.state(fid)["train_passed"])
        return n, run_sha(self.store.version(fid, n))

    def gate(self) -> Gate:
        return Gate(self.store, self.pool, self.router, self.settings, clock=self.clock)

    def actions(self, *names):
        return [e["payload"] for e in self.store.events_after(0) if e["payload"].get("action") in names]


class Reviews(GateCase):
    def test_a_due_version_is_reviewed_and_audited_and_nothing_of_the_gate_moves(self):
        n, sha = self.ready()
        before = {k: self.state("a").get(k) for k in ("review", "gate_ready", "gated_sha", "gate_outcome", "gate")}
        self.replies = [PASS, PASS]
        out = self.gate().run()
        self.assertEqual(out["incubator"], {"reviewed": ["a@1"], "failed": [], "waiting": []})
        record = self.state("a")["incubator_reviews"][sha]
        self.assertEqual((record["sha"], record["version"], record["verdict"]), (sha, n, "pass"))
        self.assertEqual(record["audit"]["verdict"], "pass")
        self.assertEqual(record["contract_sha"], review_contract()["sha256"])
        self.assertEqual(record["audit"]["contract_sha"], review_contract()["sha256"])
        self.assertEqual({k: self.state("a").get(k) for k in before}, before, "the gate's own state is untouched")
        self.assertEqual(self.store.looks(), [], "no look is spent")
        self.assertEqual([j for j in self.pool.jobs if j.window == "holdout"], [])
        self.assertEqual(len(self.actions("incubator_review")), 1)
        self.assertEqual(len(self.actions("incubator_audit")), 1)
        self.assertTrue(accepts(self.state("a"), n, sha, self.kv()), "SPEC-B §3.1 reads these facts as a passed review")
        asked = len(self.sail.bodies)
        self.assertNotIn("incubator", self.gate().run(), "a final review is never asked again")
        self.assertEqual(len(self.sail.bodies), asked)

    def test_a_failed_audit_is_final(self):
        n, sha = self.ready()
        self.replies = [PASS, fail_reply("the audit's synthetic finding")]
        out = self.gate().run()
        self.assertEqual(out["incubator"]["failed"], ["a@1"])
        record = self.state("a")["incubator_reviews"][sha]
        self.assertEqual((record["verdict"], record["stage"], record["audit"]["verdict"]), ("fail", "audit", "fail"))
        self.assertFalse(accepts(self.state("a"), n, sha, self.kv()))
        asked = len(self.sail.bodies)
        self.replies = [PASS, PASS]
        self.gate().run()
        self.assertEqual(len(self.sail.bodies), asked, "failed for good: no new read")
        self.assertEqual(self.store.refusals("a"), [], "no gate refusal is recorded")
        self.assertIsNone(self.state("a").get("gate_outcome"))

    def test_a_failed_review_is_final_and_pays_no_audit(self):
        n, sha = self.ready()
        self.replies = [fail_reply()]
        self.gate().run()
        record = self.state("a")["incubator_reviews"][sha]
        self.assertEqual(record["verdict"], "fail")
        self.assertNotIn("audit", record)
        self.assertEqual(len(self.sail.bodies), 1)
        self.assertEqual(I.due_reviews(self.store, self.settings, self.root, clock=self.clock), [])

    def test_an_unclear_review_is_asked_again_and_a_third_is_a_failure(self):
        n, sha = self.ready()
        for round_ in range(3):
            self.replies = [UNCLEAR]
            out = self.gate().run()
            if round_ < 2:
                self.assertEqual(out["incubator"]["waiting"], ["a@1"])
                self.assertNotIn(sha, self.state("a").get("incubator_reviews") or {})
        self.assertEqual(self.state("a")["incubator_reviews"][sha]["verdict"], "fail")
        self.assertEqual(len(self.sail.bodies), 3)

    def test_an_audit_asked_again_does_not_redo_the_review(self):
        n, sha = self.ready()
        self.replies = [PASS, UNCLEAR]
        out = self.gate().run()
        self.assertEqual(out["incubator"]["waiting"], ["a@1"])
        record = self.state("a")["incubator_reviews"][sha]
        self.assertEqual(record["verdict"], "pass")
        self.assertNotIn("audit", record)
        self.assertFalse(accepts(self.state("a"), n, sha, self.kv()), "no audit yet: not a passed review")
        self.replies = [PASS]
        self.gate().run()
        self.assertEqual(len(self.sail.bodies), 3, "one review, two audits")
        self.assertEqual(self.state("a")["incubator_reviews"][sha]["audit"]["verdict"], "pass")

    def test_a_program_the_experiment_contract_refuses_pays_for_no_read(self):
        n, sha = self.ready()
        with patch("league.swarm.gate.check_experiment", side_effect=CodeRefused("bad")):
            self.gate().run()
        record = self.state("a")["incubator_reviews"][sha]
        self.assertEqual((record["verdict"], record["stage"]), ("fail", "experiment contract"))
        self.assertEqual(len(self.sail.bodies), 0)

    def test_the_rounds_limit_and_off(self):
        self.ready("a")
        self.ready("b")
        self.settings["gate"]["incubator_reviews"] = 1
        self.replies = [PASS, PASS]
        out = self.gate().run()
        self.assertEqual(out["incubator"]["reviewed"], ["a@1"])
        self.settings["gate"]["incubator_reviews"] = 0
        self.replies = [PASS, PASS]
        self.assertNotIn("incubator", self.gate().run())
        self.assertEqual(len(self.sail.bodies), 2)

    def test_the_leakage_alarm_stops_them(self):
        self.ready()
        self.store.add_family({"id": "looked", "mechanism": "An invented mechanism for the alarm.", "structure": "debit_vertical",
                               "roots": ["SPY"]}, origin="test")
        for i in range(10):
            self.store.add_look("looked", i + 1, f"sha-{i}", passed=i < 4, p_value=0.01, detail={})
        self.replies = [PASS, PASS]
        out = self.gate().run()
        self.assertTrue(out["alarm"])
        self.assertNotIn("incubator", out)
        self.assertEqual(len(self.sail.bodies), 0)

    def test_a_version_no_longer_eligible_starts_no_paid_stage(self):
        n, sha = self.ready()
        with patch.object(I, "reviewable", return_value=False):
            out = self.gate().run()
        self.assertEqual(out["incubator"]["waiting"], ["a@1"])
        self.assertEqual(len(self.sail.bodies), 0)

    def test_an_error_never_fails_the_gates_round(self):
        self.ready()
        with patch.object(I, "due_reviews", side_effect=RuntimeError("boom")):
            out = self.gate().run()
        self.assertEqual(out["incubator"], {"error": "RuntimeError"})
        self.assertEqual(len(self.actions("incubator_error")), 1)

    def test_sail_readers_are_reported_to_the_owner(self):
        self.ready()
        self.replies = [PASS, PASS]
        self.gate().run()
        [alert] = [p for p in self.actions("not_the_plans_reviewer") if p.get("incubator")]
        self.assertTrue(alert["alert"])
        self.assertIn("incubator review", alert["text"])


# ---------------------------------------------------------------------------------------------------- the gate's own reads
class GateUnchanged(GateCase):
    """The incubator's reads never change the D2 gate: its own tries, its cached answers and its daily fuse."""

    def d2_ready(self, fid: str, n: int) -> None:
        self.store.set_state(fid, gate_ready=True, validation_version=n, validation_image=None, validation_bundle=None)

    def requests(self) -> list[tuple[str, str]]:
        return [(str(k), str(d)) for k, d in self.provider._db.execute("SELECT request_key, desk_id FROM requests ORDER BY rowid")]

    def test_the_gates_own_names_are_as_before(self):
        self.assertEqual(incubator_stage("review", "a"), ("review", "a:review"))
        self.assertEqual(incubator_stage("audit", "a"), ("audit", "a:review"))
        self.assertEqual(incubator_stage("review", "a", incubator=True), ("incubator_review", "a:incubator"))
        self.assertEqual(incubator_stage("audit", "a", incubator=True), ("incubator_audit", "a:incubator"))

    def test_two_unclear_incubator_reviews_leave_the_gate_its_three_tries(self):
        n, sha = self.ready()
        for _ in range(2):
            self.replies = [UNCLEAR]
            self.gate().run()
        contract = review_contract()["sha256"][:12]
        self.assertEqual(self.store.get(f"incubator_review_attempt:{contract}:a:{n}"), 2)
        self.assertIsNone(self.store.get(f"review_attempt:{contract}:a:{n}"), "the gate's own count is untouched")
        self.d2_ready("a", n)
        self.replies = [UNCLEAR]
        out = self.gate().run()
        self.assertEqual(self.store.refusals("a"), [], "one unclear answer: the gate waits, as it did without the incubator")
        self.assertIsNone(self.state("a").get("gate_outcome"))
        self.assertNotIn("incubator", out, "the gate is reviewing this very version: its own review serves")
        self.assertEqual(self.store.get(f"review_attempt:{contract}:a:{n}"), 1)
        for _ in range(2):
            self.replies = [UNCLEAR]
            self.gate().run()
        [refusal] = self.store.refusals("a")
        self.assertEqual(refusal["stage"], "review", "the gate's third unclear answer is its own refusal, as before")

    def test_the_incubators_reads_have_their_own_keys_and_fuse_and_never_answer_the_gate_from_cache(self):
        n, sha = self.ready()
        self.settings["gym"]["gate_checkpoint"] = None  # the gate reviews and waits: no look here
        self.replies = [PASS, fail_reply("the audit's synthetic finding")]
        self.gate().run()
        incubator = self.requests()
        self.assertEqual(len(incubator), 2)
        self.assertEqual([k.split(":")[3] for k, _ in incubator], ["incubator_review", "incubator_audit"])
        self.assertEqual({d for _, d in incubator}, {"a:incubator"})
        self.d2_ready("a", n)
        self.replies = [PASS, PASS]
        self.gate().run()
        gate = self.requests()[2:]
        self.assertEqual([k.split(":")[3] for k, _ in gate], ["review", "audit"], "the gate asks its own questions, paid")
        self.assertEqual({d for _, d in gate}, {"a:review"})
        self.assertEqual(len(self.sail.bodies), 4)
        review = self.state("a")["review"]
        self.assertEqual((review["verdict"], review["audit"]["verdict"]), ("pass", "pass"), "the incubator's failed audit is not the gate's")

    def test_a_version_whose_read_keeps_erring_never_holds_the_rounds_places(self):
        self.ready("a")
        self.ready("b")
        self.settings["gate"]["incubator_reviews"] = 1
        real = Gate.review

        def review(gate, fam, version, **kw):
            if fam["id"] == "a":
                raise RuntimeError("family a's fuse is spent")
            return real(gate, fam, version, **kw)

        with patch.object(Gate, "review", review):
            gate = self.gate()
            self.replies = []
            self.assertEqual(gate.run()["incubator"]["waiting"], ["a@1"])
            self.replies = [PASS, PASS]
            self.assertEqual(gate.run()["incubator"]["reviewed"], ["b@1"], "the other version is read next")
            self.assertEqual(gate.run()["incubator"]["waiting"], ["a@1"])


# ---------------------------------------------------------------------------------------------------- the gate's bar
class BarCase(GateCase):
    """A version "a@1" that passed the incubator's review and audit (`passed`), and what a bar on it must leave
    (`barred`); no tests of its own."""

    def passed(self) -> tuple[int, str]:
        n, sha = self.ready()
        self.replies = [PASS, PASS]
        self.gate().run()
        self.assertTrue(accepts(self.state("a"), n, sha, self.kv()))
        self.assertNotEqual(live_rows(self.root, "a", n), [], "B1's own reader admits it (release B)")
        return n, sha

    def moved_on(self) -> None:
        """A newer version then reaches the gate: `review` and `gate_outcome` name its program now."""
        self.store.set_state("a", review={"sha": "newer", "verdict": "pass"}, gate_outcome={"sha": "newer", "result": "waiting"})

    def barred(self, n: int, sha: str, words: str) -> None:
        state = self.state("a")
        self.assertNotIn(str(n), state.get("train_passed") or {})
        self.assertFalse(accepts(state, n, sha, self.kv()))
        self.assertIn(live_rows(self.root, "a", n), (None, []), "B1's own reader refuses it (release B)")
        record = state["incubator_reviews"][sha]
        self.assertEqual((record["verdict"], record["stage"]), ("fail", "gate"))
        self.assertIn(words, record["reasons"][0])
        self.assertEqual(record["audit"]["verdict"], "pass", "the paid audit stays on the record")
        again = I.facts(self.store, self.settings, self.root, clock=self.clock)
        self.assertEqual(again["written"], [], "never marked again")
        self.assertEqual(I.due_reviews(self.store, self.settings, self.root, clock=self.clock), [])
        self.assertFalse(I.reviewable(self.store, "a", n, sha))


class GateBar(BarCase):
    """A program the gate refused, whose holdout look failed or which it demoted loses its incubator mark for good, and
    the bar outlives the family's `gate_outcome` moving on to a newer version (which is all the live side reads)."""

    def test_the_gates_reviewer_refusing_the_program_bars_it_after_gate_outcome_moves_on(self):
        n, sha = self.passed()
        self.store.refuse("a", n, "review", "the gate's reviewer fails this program")
        self.store.set_state("a", review={"sha": sha, "verdict": "fail"}, gate_outcome={"sha": sha, "result": "refused"})
        self.moved_on()
        out = I.facts(self.store, self.settings, self.root, clock=self.clock)
        self.assertEqual((out["removed"], out["revoked"]), (["a@1"], ["a@1"]))
        self.barred(n, sha, "refused")

    def test_a_refusal_whose_gate_outcome_was_never_written_bars_it(self):
        n, sha = self.passed()
        self.store.refuse("a", n, "audit", "refused after the tournament validated a newer version")  # its CAS failed
        self.gate().run()  # the gate's own sweep, within its round
        self.barred(n, sha, "refused")

    def test_a_failed_holdout_look_bars_it_after_gate_outcome_moves_on(self):
        n, sha = self.passed()
        self.store.add_look("a", n, sha, passed=False, p_value=0.9, detail={})
        self.store.set_state("a", gate_outcome={"sha": sha, "result": "failed"})
        self.moved_on()
        self.gate().run()
        self.barred(n, sha, "holdout look failed")

    def test_a_forward_demotion_is_recorded_and_bars_it_after_gate_outcome_moves_on(self):
        n, sha = self.passed()
        self.store.set_state("a", gate_outcome={"sha": sha, "result": "demoted"})
        swept = self.gate()._incubator_sweep()
        self.assertEqual(swept["barred"], [f"a:{sha[:12]}"])
        self.assertIn(sha, self.state("a")["incubator_barred"])
        self.moved_on()
        self.gate().run()
        self.barred(n, sha, "demoted")

    def test_the_gates_own_refusal_in_a_round_takes_the_mark_with_the_verdict(self):
        n, sha = self.passed()
        self.store.set_state("a", gate_ready=True, validation_version=n, validation_image=None, validation_bundle=None)
        self.replies = [fail_reply("the gate's synthetic finding")]
        out = self.gate().run()
        self.assertEqual(out["refused"], ["a"])
        self.barred(n, sha, "the gate's reviewer failed it")
        [event] = self.actions("incubator_bar")  # THE VERDICT FIRST: the failed review, before its refusal row
        self.assertEqual((event["removed"], event["barred"], event["revoked"]), (["a@1"], [f"a:{sha[:12]}"], ["a@1"]))
        self.assertEqual(event["bar"], "the gate's reviewer failed it")
        self.assertEqual(self.actions("incubator_sweep"), [], "nothing left for the round's sweeps")
        [refusal] = self.store.refusals("a")
        self.assertEqual(refusal["stage"], "review", "the gate's own refusal, as before")

    def test_the_sweep_touches_nothing_the_gate_or_the_bands_read(self):
        n, sha = self.passed()
        self.store.refuse("a", n, "review", "x")
        before = copy.deepcopy(self.store.family("a"))
        I.sweep(self.store, self.settings, clock=self.clock)
        after = self.store.family("a")
        mine = ("train_passed", "incubator_reviews", "incubator_barred")
        self.assertEqual({k: v for k, v in after["state"].items() if k not in mine},
                         {k: v for k, v in before["state"].items() if k not in mine})
        self.assertEqual({k: v for k, v in after.items() if k != "state"}, {k: v for k, v in before.items() if k != "state"})
        self.assertEqual(I.sweep(self.store, self.settings, clock=self.clock), {"removed": [], "barred": [], "revoked": []})

    def test_a_sweep_error_never_fails_the_gates_round(self):
        self.ready()
        with patch.object(I, "sweep", side_effect=RuntimeError("boom")):
            self.replies = [PASS, PASS]
            out = self.gate().run()
        self.assertEqual(out["incubator"]["reviewed"], ["a@1"])
        self.assertEqual(len(self.actions("incubator_sweep_error")), 2, "the round's start and its end")


# ---------------------------------------------------------------------------------------------------- the reviews' bar
class ReviewBar(BarCase):
    """The gate's review and audit are required for the incubator (the owner's term): a program the gate's own reviewer or
    auditor failed is barred for good, with or without a refusal row and after `review` has moved on to a newer version;
    one whose review or audit cannot be read is barred (fail-closed); the incubator's own failed review or audit bars it
    too. `GateBar.barred` also asks B1's own reader once B1 is merged (release B)."""

    def hold_mid_read(self, stage: str):
        """The operator holds the family while the gate's own `stage` read is in flight: the gate records the verdict in
        `review` and, the version being no longer its to judge (`_review_current`), writes no refusal row."""
        real = getattr(Gate, stage)

        def read(gate, fam, version, **kw):
            answer = real(gate, fam, version, **kw)
            if not kw.get("incubator"):
                self.store.hold_gate(fam["id"], True, reason="the operator, mid-read")
            return answer

        return patch.object(Gate, stage, read)

    def d2_ready(self, n: int) -> None:
        self.store.set_state("a", gate_ready=True, validation_version=n, validation_image=None, validation_bundle=None)

    def recorded(self, sha: str) -> str:
        return self.state("a")["incubator_barred"][sha]["why"]

    def test_the_gates_failed_review_without_a_refusal_row_bars_it_and_outlives_review_moving_on(self):
        n, sha = self.passed()
        self.d2_ready(n)
        self.replies = [fail_reply("the gate's reviewer finds a flaw")]
        with self.hold_mid_read("review"):
            out = self.gate().run()
        state = self.state("a")
        self.assertEqual((state["review"]["sha"], state["review"]["verdict"]), (sha, "fail"))
        self.assertEqual((self.store.refusals("a"), out["refused"], state.get("gate_outcome")), ([], [], None),
                         "no refusal row and no outcome: the fail is in `review` alone")
        self.assertEqual(self.recorded(sha), "the gate's reviewer failed it", "recorded by the round's end")
        self.barred(n, sha, "the gate's reviewer failed it")
        # A newer version reaches the gate once the hold is cleared: `review` and `gate_outcome` name its program now.
        m = int(self.store.add_version("a", CODE.format(fid="a") + "# v2\n", {"hold": 3}, author="test")["n"])
        self.train("a", m)
        self.store.set_state("a", validation_version=m, gate_ready=True, validation_image=None, validation_bundle=None)
        self.store.hold_gate("a", False)
        self.settings["gym"]["gate_checkpoint"] = None  # the gate reviews m and waits: no look here
        self.replies = [PASS, PASS]
        self.gate().run()
        state = self.state("a")
        self.assertEqual((state["review"]["sha"], state["review"]["verdict"]), (self.sha("a", m), "pass"))
        self.assertEqual(state["gate_outcome"]["sha"], self.sha("a", m))
        self.assertEqual([r for r in self.store.refusals("a") if r["version"] == n], [], "the gate never refused n")
        self.barred(n, sha, "the gate's reviewer failed it")

    def test_the_gates_failed_audit_without_a_refusal_row_bars_it(self):
        n, sha = self.passed()
        self.d2_ready(n)
        self.replies = [PASS, fail_reply("the gate's auditor finds a flaw")]
        with self.hold_mid_read("audit"):
            self.gate().run()
        review = self.state("a")["review"]
        self.assertEqual((review["verdict"], review["stage"], review["audit"]["verdict"]), ("fail", "audit", "fail"))
        self.assertEqual(self.store.refusals("a"), [])
        self.assertEqual(self.recorded(sha), "the gate's audit failed it")
        self.moved_on()
        self.gate().run()
        self.barred(n, sha, "the gate's audit failed it")

    def test_each_reading_of_the_gates_review_record(self):
        contract = review_contract()["sha256"]
        passed_audit = {"verdict": "pass", "contract_sha": contract}
        cases = {  # the gate's `review` of this program: the bar's words, or None
            "failed": ({"verdict": "fail"}, "the gate's reviewer failed it"),
            "failed at its review stage": ({"verdict": "fail", "stage": "review"}, "the gate's reviewer failed it"),
            "its audit failed": ({"verdict": "fail", "stage": "audit", "audit": {"verdict": "fail"}}, "the gate's audit failed it"),
            "a pass whose audit failed": ({"verdict": "pass", "audit": {"verdict": "fail"}}, "the gate's audit failed it"),
            "failed under another contract": ({"verdict": "fail", "contract_sha": "old"}, "the gate's reviewer failed it"),
            "an unclear verdict": ({"verdict": "unclear"}, "the gate's review of it cannot be read"),
            "no verdict": ({}, "the gate's review of it cannot be read"),
            "a verdict that is not a word": ({"verdict": ["pass"]}, "the gate's review of it cannot be read"),
            "an audit that is not a record": ({"verdict": "pass", "audit": None}, "the gate's audit of it cannot be read"),
            "an audit without a verdict": ({"verdict": "pass", "audit": {}}, "the gate's audit of it cannot be read"),
            "an unclear audit": ({"verdict": "pass", "audit": {"verdict": "unclear"}}, "the gate's audit of it cannot be read"),
            "a pass whose audit is owed": ({"verdict": "pass", "contract_sha": contract}, None),
            "a pass and a passed audit": ({"verdict": "pass", "contract_sha": contract, "audit": passed_audit}, None),
        }
        for i, (why, (fields, words)) in enumerate(cases.items()):
            fid = f"case-{i}"
            n, sha = self.ready(fid)
            record = {"sha": sha, "version": n, **fields}
            self.assertEqual(I.gate_review_bar(record, sha), words, why)
            self.assertIsNone(I.gate_review_bar(record, "another program"), why)
            self.assertIsNone(I.gate_review_bar({**record, "sha": None}, sha), why)
            self.store.set_state(fid, review=record)
            out = I.sweep(self.store, self.settings, clock=self.clock)
            state = self.state(fid)
            if words is None:
                self.assertEqual(out["removed"], [], why)
                self.assertIn(str(n), state["train_passed"], why)
                self.assertNotIn(sha, state.get("incubator_barred") or {}, why)
                continue
            self.assertIn(f"{fid}@{n}", out["removed"], why)
            self.assertIn(f"{fid}:{sha[:12]}", out["barred"], why)
            self.assertEqual(state["incubator_barred"][sha]["why"], words, why)
            self.store.set_state(fid, review={"sha": "newer", "verdict": "pass"})  # moved on
            self.assertIn(words, I.gate_bar(self.store, self.store.family(fid), n) or "", why)
            I.facts(self.store, self.settings, self.root, clock=self.clock)
            self.assertNotIn(str(n), self.state(fid).get("train_passed") or {}, f"{why}: never marked again")

    def test_a_pass_whose_gate_audit_is_owed_keeps_the_mark_and_counts_only_with_a_passed_audit(self):
        n, sha = self.ready()
        contract = review_contract()["sha256"]
        self.store.set_state("a", review={"sha": sha, "version": n, "verdict": "pass", "contract_sha": contract})
        out = I.facts(self.store, self.settings, self.root, clock=self.clock)
        self.assertEqual((out["removed"], out["barred"]), ([], []))
        self.assertIn(str(n), self.state("a")["train_passed"])
        self.assertFalse(accepts(self.state("a"), n, sha, self.kv()), "no audit: not a passed review, so never admitted")
        self.assertIn(live_rows(self.root, "a", n), (None, []))
        self.assertEqual(self.due(), ["a@1"], "the incubator's own review and audit are still owed")

    def due(self) -> list[str]:
        return [f"{r['family']}@{r['version']}" for r in I.due_reviews(self.store, self.settings, self.root, clock=self.clock)]

    def test_a_review_record_that_cannot_be_read_bars_every_program_of_the_family_while_it_stays_so(self):
        n, sha = self.passed()
        for garbage, words in (("garbage", "the gate's review record cannot be read"),
                               (["x"], "the gate's review record cannot be read"),
                               ({"verdict": "fail"}, "the gate's review record names no program"),
                               ({"sha": 7, "verdict": "fail"}, "the gate's review record names no program")):
            self.store.set_state("a", review=garbage)
            self.assertEqual(I.family_bar(self.state("a")), words, garbage)
            self.assertEqual(I.gate_bar(self.store, self.store.family("a"), n), words, garbage)
            self.assertEqual(I.gate_bar(self.store, self.store.family("a"), n, program_only=True), None, garbage)
            out = I.facts(self.store, self.settings, self.root, clock=self.clock)
            self.assertEqual((out["removed"], out["barred"], out["revoked"]), (["a@1"], [], []), garbage)
            self.assertNotIn(str(n), self.state("a")["train_passed"], garbage)
            self.assertFalse(accepts(self.state("a"), n, sha, self.kv()), garbage)
            self.assertIn(live_rows(self.root, "a", n), (None, []), garbage)
            self.assertEqual(self.due(), [], garbage)
            self.assertFalse(I.reviewable(self.store, "a", n, sha), garbage)
            self.assertEqual(self.state("a")["incubator_reviews"][sha]["verdict"], "pass", "never revoked: it names no program")
            self.assertNotIn("incubator_barred", self.state("a"), "nothing recorded")
            self.store.set_state("a", review=None)  # the record reads again: the mark comes back, the pass still stands
            self.assertEqual(I.facts(self.store, self.settings, self.root, clock=self.clock)["written"], ["a@1"], garbage)
            self.assertTrue(accepts(self.state("a"), n, sha, self.kv()), garbage)
            self.assertNotIn(live_rows(self.root, "a", n), ([],), garbage)
        self.store.set_state("a", review={})
        self.assertIsNone(I.family_bar(self.state("a")), "an empty record is no review")

    def test_the_incubators_own_failed_review_or_audit_bars_it_even_where_the_gates_reading_passed(self):
        contract = review_contract()["sha256"]
        gate_pass = {"verdict": "pass", "contract_sha": contract, "audit": {"verdict": "pass", "contract_sha": contract}}
        cases = {  # the incubator's own record of this program: the bar's words, or None
            "its review failed": ({"verdict": "fail", "contract_sha": contract}, "the incubator's reviewer failed it"),
            "its audit failed": ({"verdict": "fail", "stage": "audit", "contract_sha": contract, "audit": {"verdict": "fail"}},
                                 "the incubator's audit failed it"),
            "a pass whose audit cannot be read": ({"verdict": "pass", "contract_sha": contract, "audit": "x"},
                                                  "the incubator's audit of it cannot be read"),
            "a pass whose audit failed": ({"verdict": "pass", "contract_sha": contract, "audit": {"verdict": "fail"}},
                                          "the incubator's audit failed it"),
            "failed under another contract": ({"verdict": "fail", "contract_sha": "old"}, None),
            "a pass whose audit is owed": ({"verdict": "pass", "contract_sha": contract}, None),
        }
        for i, (why, (fields, words)) in enumerate(cases.items()):
            fid = f"case-{i}"
            n, sha = self.ready(fid)
            self.store.set_state(fid, review={"sha": sha, "version": n, **gate_pass},
                                 incubator_reviews={sha: {"sha": sha, "version": n, **fields}})
            self.assertTrue(accepts(self.state(fid), n, sha, self.kv()), f"{why}: the gate's own passed reading counts")
            self.assertEqual(I.incubator_review_bar(self.state(fid)["incubator_reviews"][sha], sha), words, why)
            I.facts(self.store, self.settings, self.root, clock=self.clock)
            if words is None:
                self.assertIn(str(n), self.state(fid)["train_passed"], why)
                continue
            self.assertNotIn(str(n), self.state(fid).get("train_passed") or {}, why)
            self.assertFalse(accepts(self.state(fid), n, sha, self.kv()), why)
            self.assertIn(live_rows(self.root, fid, n), (None, []), why)
            if fields["verdict"] == "pass":  # a pass with a failed or unreadable audit is revoked for good
                record = self.state(fid)["incubator_reviews"][sha]
                self.assertEqual((record["verdict"], record["stage"]), ("fail", "gate"), why)

    def test_a_failed_incubator_read_takes_the_mark_within_the_gates_round(self):
        n, sha = self.ready()
        self.replies = [PASS, fail_reply("the incubator's auditor finds a flaw")]
        out = self.gate().run()
        self.assertEqual(out["incubator"]["failed"], ["a@1"])
        self.assertNotIn(str(n), self.state("a")["train_passed"])
        [event] = self.actions("incubator_bar")  # with the verdict itself (THE VERDICT FIRST)
        self.assertEqual(event["why"]["a@1"], "barred by the gate: the incubator's audit failed it")
        self.assertEqual(self.state("a")["incubator_barred"][sha]["why"], "the incubator's audit failed it")

    def test_records_that_cannot_be_read_fail_closed(self):
        n, sha = self.passed()
        family = self.store.family("a")
        for key in ("incubator_barred", "incubator_reviews"):
            self.store.update_family("a", state={**family["state"], key: "garbage"})
            self.assertIn("cannot be read", I.family_bar(self.state("a")), key)
            out = I.facts(self.store, self.settings, self.root, clock=self.clock)
            self.assertEqual(out["removed"], ["a@1"], key)
            self.assertIn(live_rows(self.root, "a", n), (None, []), key)
            self.assertEqual(self.due(), [], key)
            self.store.update_family("a", state=family["state"])
        self.store.update_family("a", state={**family["state"], "incubator_barred": {sha: None}})
        self.assertEqual(I.gate_bar(self.store, self.store.family("a"), n), "the gate barred it", "an entry that cannot be read")
        self.store.set_state("a", gate_outcome={"sha": "another", "result": "refused"})
        I.sweep(self.store, self.settings, clock=self.clock)
        self.assertEqual(set(self.state("a")["incubator_barred"]), {sha, "another"}, "kept when a new bar is recorded")
        self.assertEqual(I.gate_bar(self.store, {"id": "a", "state": {}}, 99), "its version cannot be read")

    def test_every_bar_is_kept_for_good_an_adoption_too(self):
        """The verification's probe p4: a Gym bundle change (the same review contract) keeps the gate's failed-review bar."""
        n, sha = self.passed()
        old = {f"{i:064x}": {"why": "the gate's outcome for it was refused", "at": float(i)} for i in range(60)}
        self.store.set_state("a", incubator_barred=old, review={"sha": sha, "version": n, "verdict": "fail"})
        out = I.sweep(self.store, self.settings, clock=self.clock)
        self.assertEqual(out["barred"], [f"a:{sha[:12]}"])
        self.assertEqual(set(self.state("a")["incubator_barred"]), set(old) | {sha}, "none is dropped for a newer one")
        E.adopt(self.store, {**EVALUATOR, "bundle": "gym-engine-4-bbbbbbbbbbbb"})
        state = self.state("a")
        self.assertEqual(set(state["incubator_barred"]), set(old) | {sha}, "an adoption keeps every bar")
        self.assertIsNone(state.get("review"), "the adoption cleared the gate's review: the bar alone holds the fail")
        self.assertEqual(I.gate_bar(self.store, self.store.family("a"), n), "the gate's reviewer failed it")

    def test_a_family_with_only_a_failed_gate_review_is_swept_to_record_it(self):
        n, sha = self.passed()
        self.store.set_state("a", train_passed={}, incubator_reviews={}, review={"sha": sha, "version": n, "verdict": "fail"})
        self.assertEqual(I.unrecorded_bars(self.state("a")), {sha: "the gate's reviewer failed it"})
        self.assertEqual(I.sweep(self.store, self.settings, clock=self.clock)["barred"], [f"a:{sha[:12]}"])
        self.assertEqual(I.unrecorded_bars(self.state("a")), {}, "recorded once")
        self.assertEqual(I.sweep(self.store, self.settings, clock=self.clock), {"removed": [], "barred": [], "revoked": []})


# ---------------------------------------------------------------------------------------------------- the verdict first
class VerdictFirst(BarCase):
    """THE VERDICT FIRST (the round-2 verification's should-fix, probes p1, p1b, p3 and p5): a verdict against a program
    is its incubator bar at once, and its mark goes in the same transaction, whatever the gate's own write-back then does:
    a compare-and-set on `validation_version` that a newer validation beat during the model read, an error, the trim of
    the incubator's reviews. Most rounds here run with the sweep switched off (`no_sweep`), so only the verdict itself
    can take the mark; `barred` then asks the sweep, `facts`, `due_reviews`, `reviewable` and B1's own reader."""

    def d2(self, n: int) -> None:
        """Version n validated with its line passed and at the gate (D2's route: B1 leaves it to D2's tuition)."""
        self.store.set_state("a", gate_ready=True, validation_version=n, validation_line={"passed": True},
                             validation_image=None, validation_bundle=None)

    def newer_validation_mid_read(self, stage: str, *, when=lambda: True):
        """While the gate's own `stage` read of n is in flight, the tournament validates a newer version m whose line
        failed (validation_version m, gate_ready False): the gate's compare-and-set on validation_version then fails, and
        D2's route is gone, so only B2's facts stand between the program and B1's reader."""
        real, probe = getattr(Gate, stage), self

        def read(gate, fam, version, **kw):
            answer = real(gate, fam, version, **kw)
            if not kw.get("incubator") and when():
                m = int(probe.store.add_version("a", CODE.format(fid="a") + f"# v{version['n'] + 1}\n", {"hold": 3}, author="t")["n"])
                probe.store.set_state("a", validation_version=m, validation_line={"passed": False}, gate_ready=False)
            return answer

        return patch.object(Gate, stage, read)

    def no_sweep(self):
        return patch.object(I, "sweep", return_value={"removed": [], "barred": [], "revoked": []})

    def gone(self, n: int, sha: str, words: str) -> None:
        """The mark went with the verdict (no sweep ran), the bar is recorded, and it holds for good."""
        state = self.state("a")
        self.assertNotIn(str(n), state.get("train_passed") or {}, "the mark went with the verdict")
        self.assertEqual(state["incubator_barred"][sha]["why"], words)
        self.assertIsNotNone(I.gate_bar(self.store, self.store.family("a"), n))
        self.assertFalse(accepts(state, n, sha, self.kv()))
        self.assertIn(live_rows(self.root, "a", n), (None, []), "B1's own reader refuses it (release B)")
        self.barred(n, sha, words)

    def test_p1_the_gates_failed_review_outlives_a_newer_validation_landing_during_the_read(self):
        n, sha = self.passed()
        self.d2(n)
        self.assertIn(live_rows(self.root, "a", n), (None, []), "D2's route while validated")
        self.replies = [fail_reply("the gate's reviewer finds a flaw")]
        with self.newer_validation_mid_read("review"), self.no_sweep():
            out = self.gate().run()
        state = self.state("a")
        self.assertEqual((state.get("review"), self.store.refusals("a"), state.get("gate_outcome"), out["refused"]),
                         (None, [], None, []), "the gate's own write-back lost the race: only the bar holds the fail")
        self.gone(n, sha, "the gate's reviewer failed it")

    def test_p1b_the_gates_failed_audit_outlives_a_newer_validation_landing_during_the_read(self):
        n, sha = self.passed()
        self.d2(n)
        self.replies = [PASS, fail_reply("the gate's auditor finds a flaw")]
        with self.newer_validation_mid_read("audit"), self.no_sweep():
            self.gate().run()
        review = self.state("a")["review"]
        self.assertEqual((review["sha"], review["verdict"]), (sha, "pass"))
        self.assertNotIn("audit", review, "the failed audit was never written back: the review reads as an audit owed")
        self.assertIsNone(I.gate_review_bar(review, sha))
        self.gone(n, sha, "the gate's audit failed it")

    def third_unclear(self, stage: str, first: list, words: str) -> None:
        """Three rounds of unclear answers from the gate's own `stage` read of n (`first`: the replies before it in the
        first round); the tournament validates a newer version during the third read."""
        n, sha = self.passed()
        self.d2(n)
        at = {"round": 0}
        with self.newer_validation_mid_read(stage, when=lambda: at["round"] == 2), self.no_sweep():
            for round_ in range(3):
                at["round"] = round_
                self.replies = (first if round_ == 0 else []) + [UNCLEAR]
                self.gate().run()
                if round_ < 2:
                    self.assertIn(str(n), self.state("a")["train_passed"], "an unclear answer is no verdict yet")
                    self.assertNotIn(sha, self.state("a").get("incubator_barred") or {})
        self.assertEqual((self.store.refusals("a"), self.state("a").get("gate_outcome")), ([], None))
        self.gone(n, sha, words)

    def test_a_third_unclear_review_is_a_verdict_under_the_same_race(self):
        self.third_unclear("review", [], "the gate's reviewer failed it")

    def test_a_third_unclear_audit_is_a_verdict_under_the_same_race(self):
        self.third_unclear("audit", [PASS], "the gate's audit failed it")

    def test_an_error_after_the_read_loses_nothing(self):
        n, sha = self.passed()
        self.d2(n)
        real = self.store.event

        def event(kind, family, payload):
            if payload.get("action") == "review":
                raise RuntimeError("the store's disk is full")
            return real(kind, family, payload)

        self.replies = [fail_reply("the gate's reviewer finds a flaw")]
        with patch.object(self.store, "event", event), self.no_sweep():
            with self.assertRaises(RuntimeError):
                self.gate().run()
        self.assertIsNone(self.state("a").get("review"), "nothing after the read was written")
        self.gone(n, sha, "the gate's reviewer failed it")

    def test_a_refusal_takes_the_mark_at_once(self):
        n, sha = self.passed()
        self.d2(n)
        with patch("league.swarm.gate.check_experiment", side_effect=CodeRefused("bad")), self.no_sweep():
            out = self.gate().run()
        self.assertEqual(out["refused"], ["a"])
        self.gone(n, sha, "the gate refused it (the experiment contract)")

    def outcome(self, result: str) -> None:
        n, sha = self.passed()
        with self.no_sweep():
            self.gate().outcome("a", sha, result)
        self.gone(n, sha, f"the gate's outcome for it was {result}")

    def test_a_forward_demotion_takes_the_mark_at_once(self):
        self.outcome("demoted")

    def test_a_failed_look_takes_the_mark_at_once(self):
        self.outcome("failed")

    def test_an_outcome_that_is_no_verdict_bars_nothing(self):
        n, sha = self.passed()
        for result in ("waiting", "passed"):
            self.gate().outcome("a", sha, result)
            self.assertIn(str(n), self.state("a")["train_passed"], result)
            self.assertNotIn(sha, self.state("a").get("incubator_barred") or {}, result)
        self.assertEqual(self.actions("incubator_bar"), [])

    def test_an_error_recording_the_bar_never_fails_the_gates_round_and_the_sweep_still_records_it(self):
        n, sha = self.passed()
        self.d2(n)
        self.replies = [fail_reply("the gate's reviewer finds a flaw")]
        with patch.object(I, "record_bar", side_effect=RuntimeError("boom")):
            out = self.gate().run()
        self.assertEqual(out["refused"], ["a"], "the gate's own work is as before")
        self.assertGreaterEqual(len(self.actions("incubator_bar_error")), 1)
        self.barred(n, sha, "refused")  # the round's end sweep recorded it

    def test_a_round_the_leakage_alarm_cuts_short_still_sweeps_at_its_end(self):
        self.ready()
        swept = []
        with patch.object(Gate, "alarm", side_effect=[False, True]), \
                patch.object(Gate, "_incubator_sweep", lambda gate: swept.append(1) or {}):
            out = self.gate().run()
        self.assertEqual(len(swept), 2, "the round's start and its end")
        self.assertNotIn("incubator", out, "the alarm stops every read")
        self.assertEqual(len(self.sail.bodies), 0)

    def test_p3_the_incubators_own_failed_review_is_final_after_the_trim(self):
        n, sha = self.ready()
        self.replies = [fail_reply("the incubator's reviewer finds a flaw")]
        with self.no_sweep():
            self.gate().run()
        self.assertEqual(self.state("a")["incubator_reviews"][sha]["verdict"], "fail")
        self.assertNotIn(str(n), self.state("a")["train_passed"], "the mark went with the verdict")
        for i in range(I.REVIEWS_KEPT):
            self.clock.t += 60
            I.put_review(self.store, "a", f"{i:064x}", {"sha": f"{i:064x}", "version": 99, "verdict": "pass",
                                                        "contract_sha": review_contract()["sha256"], "at": self.clock.t})
        state = self.state("a")
        self.assertNotIn(sha, state["incubator_reviews"], "trimmed from the reviews")
        self.assertEqual(state["incubator_barred"][sha]["why"], "the incubator's reviewer failed it", "never from the bars")
        self.assertIsNotNone(I.gate_bar(self.store, self.store.family("a"), n))
        self.assertEqual(I.facts(self.store, self.settings, self.root, clock=self.clock)["written"], [], "never marked again")
        self.assertEqual(I.due_reviews(self.store, self.settings, self.root, clock=self.clock), [])
        asked = len(self.sail.bodies)
        self.replies = [PASS, PASS]
        self.assertNotIn("incubator", self.gate().run(), "never read again")
        self.assertEqual(len(self.sail.bodies), asked)
        self.assertFalse(accepts(self.state("a"), n, sha, self.kv()))
        self.assertIn(live_rows(self.root, "a", n), (None, []))

    def test_p5_a_verdict_landing_while_the_mark_is_made_wins(self):
        injections = {
            "a": lambda sha, n: self.store.set_state("a", review={"sha": sha, "version": n, "verdict": "fail"}),
            "b": lambda sha, n: self.store.refuse("b", n, "review", "the gate's reviewer fails it"),
            "c": lambda sha, n: self.store.set_state("c", incubator_barred={sha: {"why": "the gate's audit failed it"}}),
        }
        for fid in injections:
            self.ready(fid)
        self.settings["gate"]["incubator_reviews"] = len(injections)
        self.replies = [PASS, PASS] * len(injections)
        self.gate().run()
        real = I.mark_of
        for fid, inject in injections.items():
            n, sha = 1, self.sha(fid, 1)
            self.assertTrue(accepts(self.state(fid), n, sha, self.kv()), fid)
            self.store.set_state(fid, train_passed={})  # the mark was taken earlier (the screen off a while): facts re-marks

            def mark_of(store, fam, n_, settings, _fid=fid, _inject=inject, _sha=sha, **kw):
                out = real(store, fam, n_, settings, **kw)
                if fam["id"] == _fid:
                    _inject(_sha, n_)  # the verdict lands between facts' read and its write
                return out

            with patch.object(I, "mark_of", mark_of):
                out = I.facts(self.store, self.settings, self.root, clock=self.clock)
            self.assertNotIn(f"{fid}@1", out["written"], fid)
            self.assertNotIn("1", self.state(fid).get("train_passed") or {}, fid)
            self.assertFalse(accepts(self.state(fid), n, sha, self.kv()), fid)
            self.assertIn(live_rows(self.root, fid, n), (None, []), fid)


# ---------------------------------------------------------------------------------------------------- durable bars, the belt
class DurableBarsAndTheBelt(BarCase):
    """The round-2 verification's findings, and the orchestrator's decisions of Sept 30 (the owner's term: a program whose
    review or audit failed never trades the incubator). (a) A bar is as durable as a refusal row: an evaluator adoption
    keeps `incubator_barred` (probes R2, R3). (b) B1's reader keeps its own belt and refuses on the verdicts themselves,
    before any sweep (probes p2, R5). A bar an error kept from the store is owed and recorded before the gate gives up
    its write-back (R1); an incubator audit in flight never writes a pass over a bar (R6)."""

    d2 = VerdictFirst.d2
    newer_validation_mid_read = VerdictFirst.newer_validation_mid_read
    no_sweep = VerdictFirst.no_sweep
    gone = VerdictFirst.gone

    def image_only_adoption(self, n: int) -> dict:
        """The operator's new `gym.image_checkpoint` alone: the House's cohort stays current (its bundle and execution are
        unchanged), the adoption clears the marks and the reviews, and the version's Train and 1.5x runs land again."""
        new = {**EVALUATOR, "image": "sbcp_gym_c"}
        E.adopt(self.store, new)
        [cohort] = I.practice_cohorts(self.root, research=new, before=I.session_day(self.clock))
        self.assertTrue(I.practice_current(cohort["evaluator"], new), "the House's cohort is still current")
        self.assertEqual((self.state("a")["train_passed"], self.state("a")["incubator_reviews"]), ({}, {}))
        self.train("a", n, identity=new)
        self.store.set_state("a", robustness={str(n): {"stress_1.5": {"status": "ok", "pnl": 40.0, "gym_image": new["image"],
                                                                      "gym_bundle": new["bundle"]}}})
        return new

    def never_again(self, n: int, sha: str, words: str) -> None:
        """After the adoption: the bar stands, the program is never marked or read again, and B1's reader refuses it."""
        self.assertEqual(self.state("a")["incubator_barred"][sha]["why"], words, "the adoption kept the bar")
        self.assertEqual(I.facts(self.store, self.settings, self.root, clock=self.clock)["written"], [], "never marked again")
        self.assertEqual(I.due_reviews(self.store, self.settings, self.root, clock=self.clock), [])
        asked = len(self.sail.bodies)
        self.replies = [PASS, PASS]
        self.assertNotIn("incubator", self.gate().run(), "never read again")
        self.assertEqual(len(self.sail.bodies), asked)
        self.assertIn(live_rows(self.root, "a", n), (None, []), "B1's own reader refuses it (release B)")

    def test_r3_an_adoption_after_the_gates_raced_audit_fail_never_lets_it_trade(self):
        n, sha = self.passed()
        self.d2(n)
        self.replies = [PASS, fail_reply("the gate's auditor finds a flaw")]
        with self.newer_validation_mid_read("audit"):
            self.gate().run()
        self.assertEqual(self.store.refusals("a"), [], "no refusal row: the bar alone holds the fail")
        self.image_only_adoption(n)
        self.never_again(n, sha, "the gate's audit failed it")

    def test_r2_an_adoption_after_the_incubators_own_failed_review_never_reads_it_again(self):
        n, sha = self.ready()
        self.replies = [fail_reply("the incubator's reviewer finds a flaw")]
        self.gate().run()
        self.image_only_adoption(n)
        self.never_again(n, sha, "the incubator's reviewer failed it")

    def test_r1_a_bar_an_error_kept_from_the_store_is_recorded_before_the_gate_gives_up_its_write_back(self):
        n, sha = self.passed()
        self.d2(n)
        real, calls = I.record_bar, {"n": 0}

        def flaky(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise sqlite3.OperationalError("database is locked")
            return real(*args, **kwargs)

        self.replies = [fail_reply("the gate's reviewer finds a flaw")]
        gate = self.gate()
        with patch.object(I, "record_bar", flaky), self.newer_validation_mid_read("review"), self.no_sweep():
            gate.run()
        self.assertEqual((calls["n"], gate.bars_owed), (2, {}), "recorded again when the compare-and-set failed")
        self.assertEqual(len(self.actions("incubator_bar_error")), 1)
        self.assertIsNone(self.state("a").get("review"), "the gate's own write-back lost the race")
        self.gone(n, sha, "the gate's reviewer failed it")

    def test_a_bar_owed_through_a_lasting_error_holds_off_every_incubator_read_and_lands_next_round(self):
        n, sha = self.ready()  # marked and due, not yet read by the incubator
        self.d2(n)
        self.replies = [fail_reply("the gate's reviewer finds a flaw")]
        gate = self.gate()
        with patch.object(I, "record_bar", side_effect=sqlite3.OperationalError("database is locked")), \
                self.newer_validation_mid_read("review"), self.no_sweep():
            out = gate.run()
        self.assertEqual(set(gate.bars_owed), {("a", sha)})
        self.assertGreaterEqual(len(self.actions("incubator_bar_error")), 2, "at the failed write-back and the round's end")
        self.assertEqual([r["version"] for r in I.due_reviews(self.store, self.settings, self.root, clock=self.clock)], [n],
                         "the store alone would have the incubator read it")
        self.assertNotIn("incubator", out, "no incubator read of a program owed a bar")
        self.assertEqual(len(self.sail.bodies), 1, "the gate's own review only")
        self.assertIn(live_rows(self.root, "a", n), (None, []))
        with self.no_sweep():
            gate.run()  # the store works again: the round's start records it
        self.assertEqual(gate.bars_owed, {})
        state = self.state("a")
        self.assertEqual(state["incubator_barred"][sha]["why"], "the gate's reviewer failed it")
        self.assertNotIn(str(n), state.get("train_passed") or {})
        self.assertEqual(I.due_reviews(self.store, self.settings, self.root, clock=self.clock), [])
        self.assertEqual(len(self.sail.bodies), 1, "never read by the incubator")

    def test_p2_a_failed_gate_review_written_straight_into_state_is_refused_before_any_sweep(self):
        n, sha = self.passed()
        self.store.set_state("a", review={"sha": sha, "version": n, "verdict": "fail", "contract_sha": review_contract()["sha256"]},
                             validation_version=n, validation_line={"passed": False}, gate_ready=False)
        self.assertIn(str(n), self.state("a")["train_passed"], "no sweep has run: the mark stands")
        self.assertNotIn(sha, self.state("a").get("incubator_barred") or {})
        self.assertIn(live_rows(self.root, "a", n), (None, []), "B1's reader refuses on the verdict itself")

    def test_r5_a_review_record_that_cannot_be_read_is_refused_before_any_sweep(self):
        n, sha = self.passed()
        self.store.set_state("a", review="garbled")
        self.assertIn(str(n), self.state("a")["train_passed"], "no sweep has run: the mark stands")
        self.assertIn(live_rows(self.root, "a", n), (None, []), "fail-closed")

    def test_a_recorded_bar_alone_is_refused_before_any_sweep(self):
        n, sha = self.passed()
        self.store.set_state("a", incubator_barred={sha: {"why": "the gate's audit failed it", "at": 1.0}})
        self.assertIn(str(n), self.state("a")["train_passed"])
        self.assertEqual(self.state("a")["incubator_reviews"][sha]["verdict"], "pass")
        self.assertIn(live_rows(self.root, "a", n), (None, []))

    def test_r6_an_incubator_audit_in_flight_never_writes_a_pass_over_a_bar(self):
        n, sha = self.ready()
        real, probe = Gate.audit, self

        def audit(gate, fam, version, **kwargs):
            answer = real(gate, fam, version, **kwargs)
            if kwargs.get("incubator"):  # the gate's fail on the same program lands during the incubator's audit
                I.record_bar(probe.store, "a", sha, "the gate's reviewer failed it", version=n, clock=probe.clock)
            return answer

        self.replies = [PASS, PASS]
        with patch.object(Gate, "audit", audit):
            out = self.gate().run()
        self.assertEqual(out["incubator"]["failed"], ["a@1"])
        record = self.state("a")["incubator_reviews"][sha]
        self.assertEqual((record["verdict"], record["stage"], record["reasons"]), ("fail", "gate", ["the gate's reviewer failed it"]))
        self.assertEqual(record["audit"]["verdict"], "pass", "the paid audit stays on the record")
        self.assertNotIn(str(n), self.state("a").get("train_passed") or {})
        self.assertIn(live_rows(self.root, "a", n), (None, []))


class TheProgramAndTheAdoption(BarCase):
    """The round-3 verification's findings (probes Q1, Q1b, Q1c, Q2 and the legacy gap): an evaluator adoption first records
    as bars the failures that only what it clears holds (the gate's `review` and `gate_outcome`, and the bars the gate
    owes, which outlive a restart beside the store); a verdict is on the PROGRAM (its run_sha) in every family; and a
    verdict that release B's gate left only in its event log is recorded at the swarm's start (`incubator.backfill`)."""

    NEW = {**EVALUATOR, "image": "sbcp_gym_c"}  # an image-only adoption: the House's cohort stays current
    d2 = VerdictFirst.d2
    newer_validation_mid_read = VerdictFirst.newer_validation_mid_read
    no_sweep = VerdictFirst.no_sweep

    def retrain(self, fid: str, n: int) -> None:
        """The new image's Train and 1.5x runs land for the version (the tournament's normal work under it)."""
        self.train(fid, n, identity=self.NEW)
        self.store.set_state(fid, robustness={str(n): {"stress_1.5": {"status": "ok", "pnl": 40.0, "gym_image": self.NEW["image"],
                                                                      "gym_bundle": self.NEW["bundle"]}}})

    def never_after_adoption(self, n: int, sha: str, words: str) -> None:
        """After the adoption and the new image's runs: the bar stands, the program is never marked or read again, and
        B1's reader refuses it."""
        self.assertEqual(self.state("a")["incubator_barred"][sha]["why"], words, "the adoption recorded the bar first")
        self.retrain("a", n)
        self.assertEqual(I.facts(self.store, self.settings, self.root, clock=self.clock)["written"], [], "never marked again")
        self.assertEqual(I.due_reviews(self.store, self.settings, self.root, clock=self.clock), [])
        asked = len(self.sail.bodies)
        self.replies = [PASS, PASS]
        self.assertNotIn("incubator", self.gate().run(), "never read again")
        self.assertEqual(len(self.sail.bodies), asked)
        self.assertEqual(live_rows(self.root, "a", n), [], "B1's own reader refuses it")

    def test_q1_an_adoption_records_a_failed_gate_review_before_it_clears_review(self):
        n, sha = self.passed()
        self.store.set_state("a", incubator_reviews={}, review={"sha": sha, "version": n, "verdict": "fail", "reasons": ["x"],
                                                              "contract_sha": review_contract()["sha256"]})
        self.assertEqual((self.store.refusals("a"), self.state("a").get("incubator_barred")), ([], None), "no row, no bar")
        out = E.adopt(self.store, self.NEW)  # the loop's start: before any gate round or sweep
        self.assertTrue(out["adopted"])
        self.assertIsNone(self.state("a")["review"], "the adoption cleared the review")
        [event] = [e["payload"] for e in self.store.events_after(0) if e["payload"].get("action") == "evaluator_adopted"]
        self.assertEqual(event["incubator_barred"], [sha[:12]])
        self.never_after_adoption(n, sha, "the gate's reviewer failed it")

    def test_q1b_an_adoption_records_a_failed_gate_audit_before_it_clears_review(self):
        n, sha = self.passed()
        contract = review_contract()["sha256"]
        self.store.set_state("a", incubator_reviews={}, review={
            "sha": sha, "version": n, "verdict": "fail", "stage": "audit", "reasons": ["x"], "contract_sha": contract,
            "audit": {"verdict": "fail", "contract_sha": contract}})
        E.adopt(self.store, self.NEW)
        self.never_after_adoption(n, sha, "the gate's audit failed it")

    def test_an_adoption_records_a_bad_outcome_and_a_failed_incubator_review_and_keeps_what_is_recorded(self):
        n, sha = self.passed()
        self.store.set_state("a", review=None, gate_outcome={"sha": "demoted-sha", "result": "demoted"},
                             incubator_reviews={sha: {**self.state("a")["incubator_reviews"][sha], "verdict": "fail",
                                                      "contract_sha": "0" * 64},
                                                "passed-sha": {"sha": "passed-sha", "verdict": "pass"}},
                             incubator_barred={"old-sha": {"why": "kept", "at": 1.0}})
        E.adopt(self.store, self.NEW)
        barred = self.state("a")["incubator_barred"]
        self.assertEqual(set(barred), {"old-sha", "demoted-sha", sha})
        self.assertEqual(barred["old-sha"], {"why": "kept", "at": 1.0}, "an entry is kept as it was")
        self.assertEqual(barred["demoted-sha"]["why"], "the gate's outcome for it was demoted")
        self.assertEqual(barred[sha]["why"], "the incubator's reviewer failed it", "whatever its contract")
        self.never_after_adoption(n, sha, "the incubator's reviewer failed it")

    def test_an_adoption_leaves_an_unreadable_incubator_barred_alone(self):
        n, sha = self.passed()
        self.store.set_state("a", incubator_barred="garbled", review={"sha": sha, "version": n, "verdict": "fail"})
        E.adopt(self.store, self.NEW)
        self.assertEqual(self.state("a")["incubator_barred"], "garbled", "never written over")
        self.assertEqual(live_rows(self.root, "a", n), [], "fail-closed")

    def test_q1c_release_bs_failed_review_under_a_hold_survives_bs_own_adoption(self):
        """The verification's probe Q1c: release B's gate (no verdict-first bar, no sweep) fails the review while the
        operator holds the family during the read, so no refusal row is written; B's deploy then adopts at its start."""
        n, sha = self.passed()
        self.store.set_state("a", gate_ready=True, validation_version=n, validation_line={"passed": True},
                             validation_image=None, validation_bundle=None, incubator_reviews={})
        real, probe = Gate.review, self

        def read(gate, fam, version, **kw):
            answer = real(gate, fam, version, **kw)
            if not kw.get("incubator"):
                probe.store.hold_gate("a", True, reason="operator")
            return answer

        self.replies = [fail_reply("the gate's reviewer finds a flaw")]
        with patch.object(Gate, "review", read), patch.object(Gate, "_incubator_bar", lambda *a, **k: None), \
                patch.object(Gate, "_incubator_sweep", lambda *a, **k: {}), patch.object(Gate, "_incubator_round", lambda *a, **k: {}):
            self.gate().run()  # release B's gate, without B2's bar and sweep
        state = self.state("a")
        self.assertEqual((state["review"]["verdict"], self.store.refusals("a"), state.get("incubator_barred")), ("fail", [], None))
        self.store.hold_gate("a", False)
        self.store.set_state("a", validation_line={"passed": False})
        E.adopt(self.store, self.NEW)  # B's swarm start
        self.never_after_adoption(n, sha, "the gate's reviewer failed it")

    def test_a_bar_owed_across_a_restart_is_recorded_by_the_adoption_and_refused_meanwhile(self):
        n, sha = self.passed()
        self.d2(n)
        self.replies = [fail_reply("the gate's reviewer finds a flaw")]
        gate = self.gate()
        with patch.object(I, "record_bar", side_effect=sqlite3.OperationalError("database is locked")), \
                self.newer_validation_mid_read("review"), self.no_sweep():
            gate.run()
        self.assertEqual(set(gate.bars_owed), {("a", sha)})
        self.assertIsNone(self.state("a").get("incubator_barred"), "the store holds nothing of the fail")
        self.assertIn(str(n), self.state("a")["train_passed"], "the mark stands: the bar never landed")
        self.assertEqual(I.load_owed(self.root), {("a", sha): (n, "the gate's reviewer failed it")}, "kept beside the store")
        self.assertEqual(live_rows(self.root, "a", n), [], "the reader refuses a program the gate owes a bar")
        # The process dies (the in-memory bar with it); B's deploy restarts the swarm into an adoption.
        E.adopt(self.store, self.NEW)
        self.assertEqual(self.state("a")["incubator_barred"][sha]["version"], n)
        restarted = self.gate()
        self.assertEqual(set(restarted.bars_owed), {("a", sha)}, "read back at the gate's start")
        self.never_after_adoption(n, sha, "the gate's reviewer failed it")
        self.assertEqual(I.load_owed(self.root), {}, "recorded by the next gate's start, then no longer owed")
        self.assertFalse((self.root / bands.BARS_OWED_FILE).exists(), "nothing owed: no file")

    def test_q2_a_program_failed_in_one_family_is_never_marked_reviewed_or_read_in_another(self):
        n, sha = self.passed()
        I.record_bar(self.store, "a", sha, "the gate's reviewer failed it", version=n, clock=self.clock)
        self.store.set_state("a", review={"sha": sha, "version": n, "verdict": "fail", "reasons": ["x"],
                                          "contract_sha": review_contract()["sha256"]})
        self.store.refuse("a", n, "review", "the gate's reviewer failed it")
        self.store.add_family({"id": "b", "mechanism": "Another invented mechanism for the incubator's facts.",
                               "structure": "debit_vertical", "roots": ["SPY"], "dte": [0, 5]}, origin="test")
        m = int(self.store.add_version("b", CODE.format(fid="a"), {"hold": 3}, author="test")["n"])
        self.assertEqual(run_sha(self.store.version("b", m)), sha, "the same program")
        self.assertEqual(I.twins(self.store, "b", m), [("a", n), ("b", m)])
        self.train("b", m)
        self.robust("b", m)
        self.cohort("b", m)
        self.practised("b", m, [(SESSIONS[i % 2], 3.0, False) for i in range(5)], days=SESSIONS[:2])
        out = I.facts(self.store, self.settings, self.root, clock=self.clock)
        self.assertNotIn(f"b@{m}", out["written"], "never marked")
        self.assertEqual(I.gate_bar(self.store, self.store.family("b"), m), f"the gate refused it in a@{n} (the review)")
        self.assertEqual(I.due_reviews(self.store, self.settings, self.root, clock=self.clock), [], "no review is paid for it")
        # Even with a mark and passed reviews written straight into b's state, the reader refuses it.
        contract = review_contract()["sha256"]
        self.store.set_state("b", train_passed={str(m): {"evaluator": EVALUATOR, "objective": OBJECTIVE, "run": "r",
                                                         "robust_pnl": 5.0, "drift": {"t": 1.0}, "at": 1.0}},
                             incubator_reviews={sha: {"sha": sha, "version": m, "verdict": "pass", "contract_sha": contract,
                                                      "audit": {"verdict": "pass", "contract_sha": contract}}})
        self.assertEqual(live_rows(self.root, "b", m), [], "a program the gate's reviewer failed (in a) never trades")
        self.assertFalse(I.reviewable(self.store, "b", m, sha))
        swept = I.sweep(self.store, self.settings, clock=self.clock)
        self.assertEqual((swept["removed"], swept["revoked"]), ([f"b@{m}"], [f"b@{m}"]), "the sweep takes them too")

    def test_q2_another_familys_failed_review_alone_refuses_the_program(self):
        """Only `review` in a names the fail (no bar, no row: release B's gate under a hold): b's program is refused."""
        n, sha = self.passed()
        self.store.add_family({"id": "b", "mechanism": "Another invented mechanism for the incubator's facts.",
                               "structure": "debit_vertical", "roots": ["SPY"], "dte": [0, 5]}, origin="test")
        m = int(self.store.add_version("b", CODE.format(fid="a"), {"hold": 3}, author="test")["n"])
        contract = review_contract()["sha256"]
        self.store.set_state("b", train_passed={str(m): {"evaluator": EVALUATOR, "objective": OBJECTIVE, "run": "r",
                                                         "robust_pnl": 5.0, "drift": {"t": 1.0}, "at": 1.0}},
                             incubator_reviews={sha: {"sha": sha, "version": m, "verdict": "pass", "contract_sha": contract,
                                                      "audit": {"verdict": "pass", "contract_sha": contract}}})
        self.assertEqual(len(live_rows(self.root, "b", m)), 1, "nothing against the program yet")
        self.store.set_state("a", review={"sha": sha, "version": n, "verdict": "fail", "contract_sha": contract})
        self.assertEqual(live_rows(self.root, "b", m), [])
        self.store.set_state("a", review=None, incubator_reviews={})
        self.assertEqual(len(live_rows(self.root, "b", m)), 1)
        self.store.update_family("a", retired_at="2026-10-06T00:00:00Z", state={**self.state("a"), "incubator_barred": {sha: {}}})
        self.assertEqual(live_rows(self.root, "b", m), [], "a retired family's bar on the program stands")

    def test_a_retired_twins_pass_whose_audit_is_owed_bars_the_program_as_the_reader_refuses_it(self):
        """The final integrated check of release B (swarm nit 1): a's gate review passed, its audit errored (every audit
        route out of budget), and a retired, so its `review` is never cleared and its audit never lands. The reader
        refuses the same program in b for good; the swarm now agrees (fail-closed) and never marks it in b nor pays for
        b's incubator review and audit. Not a verdict: nothing is recorded and no passed review is revoked."""
        contract = review_contract()["sha256"]
        n = self.family("a")
        sha = self.sha("a", n)
        owed = {"sha": sha, "version": n, "verdict": "pass", "reasons": [], "contract_sha": contract}
        self.store.set_state("a", review=owed)
        self.store.retire_gym("a", "its researcher retired it", floor=0, source="test")
        self.assertIsNotNone(self.store.family("a")["retired_at"])
        self.assertIsNotNone(bands.program_refusal(self.state("a"), sha), "the reader refuses it there")
        self.store.add_family({"id": "b", "mechanism": "Another invented mechanism for the incubator's facts.",
                               "structure": "debit_vertical", "roots": ["SPY"], "dte": [0, 5]}, origin="test")
        m = int(self.store.add_version("b", CODE.format(fid="a"), {"hold": 3}, author="test")["n"])
        self.assertEqual(self.sha("b", m), sha, "the same program")
        self.train("b", m)
        self.robust("b", m)
        self.cohort("b", m)
        self.practised("b", m, [(SESSIONS[i % 2], 3.0, False) for i in range(5)], days=SESSIONS[:2])
        out = I.facts(self.store, self.settings, self.root, clock=self.clock)
        self.assertNotIn(f"b@{m}", out["written"], "never marked")
        words = "the gate's review of it passed with its audit still owed (in a, which holds the same program)"
        self.assertEqual(I.gate_bar(self.store, self.store.family("b"), m), words)
        self.assertEqual(I.due_reviews(self.store, self.settings, self.root, clock=self.clock), [], "no review is paid")
        asked = len(self.sail.bodies)
        self.replies = [PASS, PASS]
        self.assertNotIn("incubator", self.gate().run(), "never read")
        self.assertEqual(len(self.sail.bodies), asked)
        # The reader stays strict: with a mark and passed reviews written straight into b's state, still no row.
        self.store.set_state("b", train_passed={str(m): {"evaluator": EVALUATOR, "objective": OBJECTIVE, "run": "r",
                                                         "robust_pnl": 5.0, "drift": {"t": 1.0}, "at": 1.0}},
                             incubator_reviews={sha: {"sha": sha, "version": m, "verdict": "pass", "contract_sha": contract,
                                                      "audit": {"verdict": "pass", "contract_sha": contract}}})
        self.assertEqual(live_rows(self.root, "b", m), [], "the reader refuses it while a's audit is owed")
        self.assertFalse(I.reviewable(self.store, "b", m, sha))
        # No verdict against it: the sweep takes the mark, records no bar and revokes no review (`program_only`).
        self.assertIsNone(I.gate_bar(self.store, self.store.family("b"), m, program_only=True))
        swept = I.sweep(self.store, self.settings, clock=self.clock)
        self.assertEqual((swept["removed"], swept["barred"], swept["revoked"]), ([f"b@{m}"], [], []))
        self.assertEqual(self.state("b")["incubator_reviews"][sha]["verdict"], "pass")
        self.assertNotIn(sha, self.state("b").get("incubator_barred") or {})
        self.assertNotIn("incubator_barred", self.state("a"))
        # Were a's audit to land (an alive family's would), the bar lifts and both sides admit the program in b again.
        self.store.update_family("a", state={**self.state("a"), "review": {
            **owed, "audit": {"verdict": "pass", "contract_sha": contract}}})
        self.assertIsNone(I.gate_bar(self.store, self.store.family("b"), m))
        self.assertIn(f"b@{m}", I.facts(self.store, self.settings, self.root, clock=self.clock)["written"])
        self.assertEqual(len(live_rows(self.root, "b", m)), 1)

    def test_the_backfill_records_release_bs_fails_that_only_the_event_log_holds(self):
        n, sha = self.passed()
        m = self.family("c")
        other = self.sha("c", m)
        # Release B's gate: a failed review whose compare-and-set lost to a newer validation (the event alone), a third
        # unclear audit whose write-back lost too (its attempt count alone), and an unrelated passed review.
        self.store.event("swarm.gate", "a", {"action": "review", "version": n, "verdict": "fail", "reasons": ["x"]})
        self.store.event("swarm.gate", "a", {"action": "review", "version": 99, "verdict": "fail"})  # no such version
        self.store.event("swarm.gate", "c", {"action": "review", "version": m, "verdict": "pass"})
        self.store.put(f"audit_attempt:{review_contract()['sha256'][:12]}:{other}", 3)
        self.assertEqual(len(live_rows(self.root, "a", n)), 1, "the reader never reads the event log")
        out = I.backfill(self.store, clock=self.clock)
        self.assertEqual(sorted(out["barred"]), sorted([f"a:{sha[:12]}", f"c:{other[:12]}"]))
        self.assertEqual(self.state("a")["incubator_barred"][sha], {"why": "the gate's reviewer failed it", "at": self.clock(),
                                                                    "version": n})
        self.assertEqual(self.state("c")["incubator_barred"][other]["why"], "the gate's audit could not reach a verdict three times")
        self.assertNotIn(str(n), self.state("a").get("train_passed") or {}, "its mark went with the bar")
        self.assertEqual(live_rows(self.root, "a", n), [])
        self.assertEqual(len(self.actions("incubator_backfill")), 1)
        self.assertEqual(I.backfill(self.store, clock=self.clock)["barred"], [], "idempotent: from where it stopped")
        self.assertEqual(self.store.get(I.BACKFILL_KEY), max(e["seq"] for e in self.store.events_after(0, limit=10**6)
                                                             if e["kind"] == "swarm.gate"))
        E.adopt(self.store, self.NEW)
        self.never_after_adoption(n, sha, "the gate's reviewer failed it")

    def test_the_swarm_start_backfills_before_the_adoption(self):
        text = (REPO / "league" / "swarm" / "loop.py").read_text(encoding="utf-8")
        self.assertLess(text.index("backfill(self.store)"), text.index("adopt(self.store, evaluator)"))


# ---------------------------------------------------------------------------------------------------- never evidence
class NeverEvidence(unittest.TestCase):
    TOKENS = ("live.sqlite", "RealBook", "incubator_tally", '":i"', "':i'")

    def test_the_swarm_never_reads_the_houses_real_rows(self):
        for name in ("incubator.py", "gate.py", "tournament.py", "researcher.py", "evaluator.py", "evidence.py"):
            text = (REPO / "league" / "swarm" / name).read_text(encoding="utf-8")
            for token in self.TOKENS:
                self.assertNotIn(token, text, f"{name}: {token}")
        text = (REPO / "league" / "swarm" / "incubator.py").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"from \.\.live|league\.live\b", "the facts read the practice record's file only")
        self.assertIsNone(re.search(r"\bweight\b", (REPO / "league" / "swarm" / "gate.py").read_text(encoding="utf-8")))

    def test_the_facts_are_outside_the_execution_fingerprint(self):
        """B2 changes no file the evaluator hashes, so it resets no evidence (SPEC-B §1.1)."""
        from league.gym.driver import LEAGUE_FILES

        hashed = {str(Path(p)) for p in LEAGUE_FILES}
        for name in ("incubator.py", "gate.py", "tournament.py", "researcher.py", "evaluator.py", "settings.py"):
            path = Path("league") / "swarm" / name
            self.assertNotIn(str(path), hashed)
            self.assertFalse(str(path).startswith(("league/gym", "league/live")))



if __name__ == "__main__":
    unittest.main()
