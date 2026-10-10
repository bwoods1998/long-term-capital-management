"""THE EQUITY LANES' Validation and sealed look (release E1; league/swarm/elane.py `validate` and `look`, dispatched by
league/swarm/tournament.py `Tournament.equity_round` and league/swarm/gate.py `Gate.equity_round`): Validation on the
House at k 1.0 and 1.5 with the S1 pre-check as its entry, one try a lineage; the one sealed look with the gate's
capability, refused with no look spent when no receipt is pinned, when the program floor is ineligible or when it is
the same lineage (A9 D3); a pass makes a Candidate proven on the equity identity; the options leakage alarm never counts
an equity look. The runner and the screen are other packages' (core's, screen's): faked here at their interfaces."""

from __future__ import annotations

import contextlib
import itertools
from types import SimpleNamespace
from unittest import mock

import numpy as np

from league.equity import BETA, EQUITY_ENGINE_VERSION
from league.equity import screen as S
from league.equity.runner import Run
from league.swarm import elane
from league.swarm.gate import Gate, run_sha
from league.swarm.tournament import Tournament
from league.tests.test_elane import CODE, ON, SHA, equity_spec, pinned_block
from league.tests.test_swarm_store import StoreCase

EQUITY_SHA = "f" * 64
_N = itertools.count(1)


class FakeRunner:
    """`league.equity.runner.Isolated` at its interface: Validation, the Train-era segments and the sealed look."""

    def __init__(self, *, status="ok", result_sha="validation-sha", sd=0.012, look_error=None, fail=False):
        self.status, self.result_sha, self.sd, self.look_error, self.fail = status, result_sha, sd, look_error, fail
        self.calls: list[tuple] = []

    def _run(self, name, window, k):
        result = {"run_id": f"{name}-{window}-{k}-{next(_N)}", "status": self.status, "trials": 1, "window": window,
                  "symbols": ["SPY"], "capital": "1000", "lots": [{"lid": 1}],
                  "summary": {"days": 250, "sd_net_return": self.sd, "pnl": 1.0},
                  "result_sha": self.result_sha if window == "validation" else f"{window}-sha"}
        return Run(result, SimpleNamespace(window=window))

    def validation(self, code, params, *, name, k=1.0):
        self.calls.append(("validation", name, k))
        if self.fail:
            raise RuntimeError("the child failed")
        return self._run(name, "validation", k)

    def segments(self, code, params, *, name):
        self.calls.append(("segments", name))
        return [self._run(name, "segment-1", 1.0), self._run(name, "segment-2", 1.0)]

    def look(self, code, params, *, name, gate, k=1.0):
        self.calls.append(("look", name, gate))
        if self.look_error is not None:
            raise self.look_error
        return self._run(name, "holdout", k)


def receipt():
    return S.Receipt(receipt_sha256=SHA, c_R=1.5, c_X=0.9, fp_cap=0.12, owner_wall=0.15, retry=False, r4={},
                     beside="c_used {c_used}", fp={})


def series(lots, bars, *, universe, capital, first=None, last=None):
    days = {"segment-1": np.arange(0, 5), "segment-2": np.arange(10, 15)}.get(bars.window, np.arange(100, 105))
    return S.Series(days=days.astype(np.int32), r=np.linspace(-0.01, 0.01, len(days)), w=np.ones(len(days)),
                    b=np.zeros(len(days)), exits=np.zeros(len(days), dtype=int), invested=np.ones(len(days), dtype=bool))


@contextlib.contextmanager
def screen(*, precheck=True, eligible=True, passed=True, same=False, pinned=True):
    """The screen package's functions at their interfaces, the receipt pinned in the repository's policy (or not), the
    gate's capability and the equity identity (core's)."""
    with contextlib.ExitStack() as stack:
        enter = stack.enter_context
        enter(mock.patch.object(elane, "_policy_block", return_value=pinned_block() if pinned else {}))
        enter(mock.patch.object(S, "pinned_receipt", return_value=receipt()))
        enter(mock.patch.object(S, "series", side_effect=series))
        enter(mock.patch.object(S, "precheck", return_value={"passed": precheck, "checks": {"activity": precheck}}))
        floor = {"eligible": eligible, "why": None if eligible else "no 300-session pool", "c_p": 1.2, "c_H": 0.4}
        floored = enter(mock.patch.object(S, "floor", return_value=floor))
        enter(mock.patch.object(S, "verdict", return_value={"passed": passed, "c_used": 1.5, "c_H": 0.4, "t": 2.0,
                                                          "label": "beta"}))
        enter(mock.patch.object(S, "beside_line", return_value="c_used 1.5"))
        enter(mock.patch.object(S, "same_lineage", return_value=same))
        enter(mock.patch.object(S, "retry_permitted", return_value=False))
        mint = enter(mock.patch("league.equity.store.mint_equity_gate_capability", return_value="CAPABILITY"))
        enter(mock.patch("league.swarm.evaluator.equity_fingerprint", return_value=EQUITY_SHA))
        mint.floor = floored
        yield mint


class EquityCase(StoreCase):
    def setUp(self):
        super().setUp()
        self.runner = FakeRunner()
        self.tournament = Tournament(self.store, None, ON, clock=self.clock)
        self.tournament.equity_runner = self.runner
        self.gate = Gate(self.store, None, None, ON, clock=self.clock)
        self.gate.equity_runner = self.runner

    def born(self, fid="b1", *, seeded=True, code=CODE, lane=BETA):
        self.store.add_family(equity_spec(fid, lane=lane, seeded=seeded), origin="seed")
        return self.store.add_version(fid, code, {}, author=elane.SEED_AUTHOR)

    def validated(self, fid="b1", **kw):
        with screen(**kw):
            return elane.validate(self.tournament, self.store.family(fid), self.store.version(fid, 1))

    def looks(self):
        return self.store.looks()


class Validation(EquityCase):
    def test_validation_runs_on_the_house_at_both_ks_and_its_precheck_is_the_entry(self):
        v1 = self.born()
        v2 = self.store.add_version("b1", CODE, {"share": 0.4}, author="test")  # written before the first try: R3's
        verdict = self.validated()
        self.assertEqual((verdict["passed"], verdict["entered"], verdict["first"], verdict["screen"]), (True, True, True, "S1"))
        self.assertEqual(self.runner.calls, [("validation", "b1", 1.0), ("validation", "b1", 1.5)])
        runs = sorted((r["stress"], r["trials"]) for r in self.store.runs("b1", window="validation"))
        self.assertEqual(runs, [(1.0, 1), (1.5, 1)], "both runs are trials")
        fam = self.store.family("b1")
        state = fam["state"]
        self.assertEqual((fam["validated_version"], state["validation_version"], state["gate_ready"]), (1, 1, True))
        self.assertEqual(state[elane.SIGMA_KEY], {"1": 0.012}, "EDM1's sigma: the per-trade net-return sd")
        self.assertEqual(state[elane.TRY_KEY]["retry_sha"], run_sha(v2), "the retry's version hashed at the first try")
        self.assertTrue(state[elane.TRY_KEY]["first"] and state[elane.TRY_KEY]["entered"])
        self.assertEqual(state[elane.VALIDATION_KEY]["result_sha"], "validation-sha")
        with screen():
            self.assertEqual(elane.validate(self.tournament, self.store.family("b1"), v2)["refused"], elane.SPENT_TRY)
        self.assertEqual(run_sha(v1), run_sha(self.store.version("b1", 1)))

    def test_a_failed_precheck_enters_nothing_and_spends_the_try(self):
        self.born()
        verdict = self.validated(precheck=False)
        self.assertEqual((verdict["passed"], verdict["entered"]), (False, False))
        state = self.store.family("b1")["state"]
        self.assertEqual((state["gate_ready"], state[elane.TRY_KEY]["precheck"]), (False, False))
        self.assertEqual(elane.lineage_spent(self.store, self.store.family("b1"), ON), elane.SPENT_TRY)

    def test_no_result_is_no_try_and_the_lanes_off_validate_nothing(self):
        self.born()
        self.runner.fail = True
        self.assertEqual(self.validated()["error"], "RuntimeError")
        self.assertEqual(self.store.runs("b1", window="validation"), [])
        self.assertEqual(elane.lineage_tries(self.store, "b1"), [])
        self.tournament.settings = {}
        self.assertIn("off", self.validated()["refused"])
        self.assertIn("not an equity", elane.validate(self.tournament, {"id": "x", "spec": {}}, {"n": 1})["refused"])

    def test_the_tournament_dispatches_validation_by_lane_and_retires_a_spent_lineage(self):
        elane.birth_seeds(self.store, ON)
        with screen():
            out = self.tournament.equity_round()
        self.assertEqual(sorted(out["validated"]), ["seed-overnight-qqq", "seed-overnight-spy", "seed-reversal-index"])
        self.assertTrue(all(v["entered"] for v in out["validated"].values()))
        with screen():
            self.assertEqual(self.tournament.equity_round()["validated"], {}, "a current verdict is not asked again")
        self.store.set_state("seed-overnight-qqq", **{elane.TRY_KEY: {"version": 1, "precheck": False, "entered": False}})
        with screen():
            out = self.tournament.equity_round()
        self.assertEqual(out["retired"], ["seed-overnight-qqq"])
        fam = self.store.family("seed-overnight-qqq")
        self.assertEqual((fam["band"], fam["retire_reason"]), ("retired", elane.SPENT_TRY))
        self.assertEqual(self.store.graveyard(), [], "no graveyard row: no look outcome reaches a generator (A9 D3)")
        self.assertFalse(self.tournament.lane_forks(self.store.family("seed-overnight-spy")), "never forks")
        self.store.set_band("seed-overnight-spy", "candidate", reason="passed")
        self.store.set_band("seed-overnight-spy", "probe", reason="the EquityBook")
        self.store.add_forward("seed-overnight-spy", "real", [{"id": "eq-1", "day": "2026-10-13", "pnl": -200.0,
                                                               "max_loss": 600.0}])
        self.assertEqual(self.tournament.equity_round()["retired"], [])
        self.store.add_forward("seed-overnight-spy", "real", [{"id": "eq-2", "day": "2026-10-14", "pnl": -100.0,
                                                               "max_loss": 600.0}])
        self.assertEqual(self.tournament.equity_round()["retired"], ["seed-overnight-spy"], "the program loss line")
        self.assertEqual(self.store.family("seed-overnight-spy")["retire_reason"], elane.LOSS_LINE)
        self.assertEqual([f["id"] for f in self.store.families(alive=True)], [], "the options round never sees them")


class Look(EquityCase):
    def ready(self, fid="b1", **kw):
        version = self.born(fid, **kw)
        self.validated(fid)
        return version, run_sha(version)

    def test_a_screen_with_no_pinned_receipt_refuses_and_spends_no_look(self):
        version, sha = self.ready()
        out = {"looked": [], "held": []}
        with screen(pinned=False) as mint:
            self.gate.equity_round(out)
        self.assertEqual((out["looked"], self.looks(), mint.call_count), ([], [], 0))
        state = self.store.family("b1")["state"]
        self.assertEqual((state["gate_ready"], state["gate_outcome"]["result"]), (True, "waiting"))
        self.assertNotIn("look", [c[0] for c in self.runner.calls])
        self.assertIsNone(elane.lineage_spent(self.store, self.store.family("b1"), ON))

    def test_a_pass_spends_the_one_look_and_makes_a_candidate_proven_on_the_equity_identity(self):
        version, sha = self.ready()
        out = {"looked": [], "held": []}
        with screen() as mint:
            self.gate.equity_round(out)
        self.assertEqual(out["looked"], [{"family": "b1", "passed": True, "lane": BETA}])
        mint.assert_called_once()
        self.assertEqual(mint.call_args.args[0], self.store.root / "equity-daily")
        self.assertIn(("look", "b1", "CAPABILITY"), self.runner.calls)
        (look,) = self.looks()
        self.assertEqual((look["run_sha"], look["passed"], look["detail"]["lane"], look["detail"]["screen"],
                          look["detail"]["receipt"], look["detail"]["c_used"], look["detail"]["beside"]),
                         (sha, 1, BETA, "S1", SHA, 1.5, "c_used 1.5"))
        fam = self.store.family("b1")
        state = fam["state"]
        self.assertEqual((fam["band"], state["banded_version"], state["gated_sha"], state["gate_ready"]),
                         ("candidate", 1, sha, False))
        self.assertEqual(state["banded_evaluator"], {"engine": EQUITY_ENGINE_VERSION, "equity_sha256": EQUITY_SHA,
                                                     "run_sha": sha})
        self.assertEqual((state[elane.LOOK_KEY]["beside"], state[elane.TRAIN_R_KEY]["days"][:2]), ("c_used 1.5", [0, 1]))
        self.assertIsNone(state.get("look_inflight"))
        with screen():
            self.gate.equity_round(out)
        self.assertEqual(len(self.looks()), 1, "one look, ever")

    def test_a_failed_look_is_spent_and_the_lineage_retires(self):
        self.ready()
        with screen(passed=False):
            self.assertFalse(self.gate.look(self.store.family("b1"), self.store.version("b1", 1),
                                            run_sha(self.store.version("b1", 1))))
        self.assertEqual(self.store.family("b1")["band"], "gym")
        self.assertEqual(elane.lineage_spent(self.store, self.store.family("b1"), ON), elane.SPENT_LOOK)
        with screen():
            self.assertEqual(self.tournament.equity_round()["retired"], ["b1"])

    def test_an_ineligible_floor_refuses_before_the_look(self):
        version, sha = self.ready()
        with screen(eligible=False) as mint:
            self.assertIsNone(self.gate.look(self.store.family("b1"), version, sha))
        self.assertEqual((self.looks(), mint.call_count), ([], 0))
        (refusal,) = self.store.refusals("b1")
        self.assertEqual(refusal["stage"], "screen floor")
        state = self.store.family("b1")["state"]
        self.assertEqual((state["gated_sha"], state["gate_ready"]), (sha, False))

    def test_the_same_lineage_takes_no_second_look(self):
        self.ready("b1")
        with screen():
            self.assertTrue(self.gate.look(self.store.family("b1"), self.store.version("b1", 1),
                                           run_sha(self.store.version("b1", 1))))
        version, sha = self.ready("b2", code=CODE + "# another program\n")
        with screen(same=True) as mint:
            self.assertIsNone(self.gate.look(self.store.family("b2"), version, sha))
        self.assertEqual((len(self.looks()), mint.call_count), (1, 0))
        self.assertEqual(self.store.refusals("b2")[0]["stage"], "same lineage")
        self.assertIn("b1", self.store.refusals("b2")[0]["reason"])
        version, sha = self.ready("b3", code=CODE + "# a third program\n")
        self.store.set_state("b3", **{elane.TEMPLATE_KEY: self.store.family("b1")["state"][elane.TEMPLATE_KEY]})
        self.store.set_state("b1", **{elane.TEMPLATE_KEY: elane.lineage_key(BETA, version["sha"])})
        with screen(same=False) as mint:
            self.assertIsNone(self.gate.look(self.store.family("b3"), version, sha))
        self.assertEqual(self.store.refusals("b3")[0]["stage"], "same lineage", "the same template in its own lane")

    def test_a_validation_that_does_not_reproduce_goes_back_to_the_tournament(self):
        version, sha = self.ready()
        self.runner.result_sha = "another-sha"
        with screen() as mint:
            self.assertIsNone(self.gate.look(self.store.family("b1"), version, sha))
        self.assertEqual((self.looks(), mint.call_count), ([], 0))
        state = self.store.family("b1")["state"]
        self.assertEqual((state["gate_ready"], state[elane.VALIDATION_KEY]["stale"]), (False, True))
        self.assertEqual(elane.next_try(self.store, self.store.family("b1"), ON), 1, "validated again: the same try")

    def test_a_program_the_captain_did_not_seed_waits_for_the_equity_review(self):
        version, sha = self.ready(seeded=False)
        with screen() as mint:
            self.assertIsNone(self.gate.look(self.store.family("b1"), version, sha))
        self.assertEqual((self.looks(), mint.call_count), ([], 0))
        self.assertEqual(self.store.family("b1")["state"]["gate_outcome"]["result"], "waiting")
        self.store.set_state("b1", review={"sha": sha, "verdict": "pass", "audit": {"verdict": "pass"}})
        with screen():
            self.assertTrue(self.gate.look(self.store.family("b1"), version, sha))

    def test_a_look_that_does_not_land_is_owed_again(self):
        version, sha = self.ready()
        self.runner.look_error = RuntimeError("the child died")
        with screen():
            self.assertIsNone(self.gate.look(self.store.family("b1"), version, sha))
        state = self.store.family("b1")["state"]
        self.assertEqual((self.looks(), state.get("look_inflight"), state["gate_ready"]), ([], None, True))
        self.store.set_state("b1", gate_ready=False, look_inflight={"sha": sha, "n": 1, "at": self.gate.started_at - 1})
        self.runner.look_error = None
        out = {"looked": [], "held": []}
        with screen() as mint:
            self.gate.equity_round(out)
        self.assertEqual(out["looked"], [{"family": "b1", "passed": True, "lane": BETA}],
                         "a look in flight from a dead process is owed again")
        self.assertEqual(mint.floor.call_count, 0, "the program floor is computed once a version")

    def test_the_operators_hold_and_the_lanes_off(self):
        version, sha = self.ready()
        self.store.hold_gate("b1", reason="checking")
        out = {"looked": [], "held": []}
        with screen():
            self.gate.equity_round(out)
        self.assertEqual((out["held"], self.looks()), (["b1"], []))
        self.gate.settings = {}
        with screen():
            self.assertIsNone(self.gate.look(self.store.family("b1"), version, sha))

    def test_the_options_leakage_alarm_never_counts_an_equity_look(self):
        for i in range(12):
            self.store.add_look(f"eq{i}", 1, f"sha-{i}", passed=True, p_value=None, detail={"lane": BETA, "screen": "S1"})
        self.assertFalse(self.gate.alarm())
        self.assertEqual(self.gate.options_looks(), [])
        for i in range(10):
            self.store.add_look(f"opt{i}", 1, f"osha-{i}", passed=True, p_value=0.01, detail={})
        self.assertTrue(self.gate.alarm(), "the options looks alone still raise it")
