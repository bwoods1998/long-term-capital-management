"""The incubator's swarm facts (release B2, league/swarm/incubator.py): the Train and drift mark the tournament writes for
a practised version, and the incubator review and audit the gate makes. Neither resets evidence, reads the House's real
rows, spends a holdout look or touches the gate's own review state. Invented stores, practice records and model answers
only."""

from __future__ import annotations

import copy
import datetime as dt
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from league.gym.review_contract import review_contract
from league.gym.safety import CodeRefused
from league.live.observe import ObserveStore
from league.swarm import evaluator as E
from league.swarm import incubator as I
from league.swarm.bands import demoted
from league.swarm.gate import Gate, run_sha
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
        cases = {
            "no eligible Train run": lambda f, n: self.train(f, n, eligible=False),
            "a Train run of another evaluator": lambda f, n: self.train(f, n, identity={**EVALUATOR, "bundle": "gym-engine-4-old"}),
            "its 1.5x run has not landed": lambda f, n: (self.train(f, n), self.robust(f, n, status="failed")),
            "its 1.5x run lost": lambda f, n: (self.train(f, n), self.robust(f, n, pnl=-3.0)),
            "its 1.5x run broke even": lambda f, n: (self.train(f, n), self.robust(f, n, pnl=0.0)),
            "demoted at 1.5x": lambda f, n: (self.train(f, n), self.store.set_state(f, robust_failed=[n])),
            "demoted by the drift screen": lambda f, n: (self.train(f, n), self.store.set_state(f, drift_failed={str(n): "x"})),
            "drift figures owed": lambda f, n: self.train(f, n, drift=None),
            "a failed drift screen": lambda f, n: self.train(f, n, drift=FAILING),
        }
        for why, arrange in cases.items():
            fid = re.sub(r"[^a-z0-9]+", "-", why)
            n = self.family(fid)
            self.robust(fid, n)
            arrange(fid, n)
            self.cohort(fid, n)
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

    def test_an_off_drift_screen_writes_nothing(self):
        self.eligible("a")
        self.settings["tournament"]["drift_screen"] = False
        out = self.facts()
        self.assertEqual((out["written"], out["waiting"]), ([], 1))
        self.assertNotIn("train_passed", self.state("a"))

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

    def test_adoption_of_a_new_evaluator_clears_marks_and_reviews(self):
        n = self.eligible("a")
        self.facts()
        self.store.set_state("a", incubator_reviews={"x": {"sha": "x", "verdict": "pass"}})
        E.adopt(self.store, {**EVALUATOR, "bundle": "gym-engine-4-bbbbbbbbbbbb"})
        state = self.state("a")
        self.assertEqual((state["train_passed"], state["incubator_reviews"]), ({}, {}))
        self.assertIn(str(n), state["previous_evaluator_selection"]["train_passed"], "archived, privately")
        self.assertIn("train_passed", E.SELECTION_KEYS)
        self.assertIn("incubator_reviews", E.SELECTION_KEYS)

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
class Reviews(Fixture, RoundCase):
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
