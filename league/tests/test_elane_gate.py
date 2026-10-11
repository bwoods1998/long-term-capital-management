"""THE EQUITY LANES' Validation and sealed look (release E1; league/swarm/elane.py `validate` and `look`, dispatched by
league/swarm/tournament.py `Tournament.equity_round` and league/swarm/gate.py `Gate.equity_round`): Validation on the
House at k 1.0 and 1.5 with the screen's pre-check as its entry, one try a lineage; the one sealed look with the gate's
capability, under the lane's pinned receipt (S2's floor and verdict for receipt 2, amendment A11; S1's for receipt 1),
refused or waiting with no look spent when no receipt is pinned, when a receipt file at hand is not the pin's bytes,
when the program floor is ineligible or does not fit the receipt, when the daily store ends before the calibrated
holdout (A12) or when it is the same lineage (A9 D3); a pass makes a Candidate proven on the equity identity; the options
leakage alarm never counts an equity look. The runner and the screen are other packages' (core's, screen's): faked here
at their interfaces."""

from __future__ import annotations

import contextlib
import hashlib
import itertools
import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

from league.equity import BETA, EQUITY_ENGINE_VERSION
from league.equity import screen as S
from league.equity.runner import Run
from league.swarm import elane
from league.swarm.gate import Gate, run_sha
from league.swarm.tournament import Tournament
from league.tests.test_elane import CODE, ON, SHA, equity_spec, pinned_block, pinned_block_s2
from league.tests.test_swarm_store import StoreCase

EQUITY_SHA = "f" * 64
_N = itertools.count(1)
#: A release root with no docs/ (the House box's: docs/benchmarks/ never reaches it), so no receipt file is at hand.
NO_DOCS = Path(__file__).resolve().parent / "fixtures" / "no-such-release-root"
FAKE_S2 = Path(__file__).resolve().parent / "fixtures" / "equity_screen_2_fake.json"


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


def receipt_s2():
    return S.pinned_receipt_s2(pinned_block_s2())


def floor_s1(eligible=True):
    """A floor as S1's `screen.floor` writes it (its screen and the fp_cap it ran at: `screen.floor_fits`)."""
    return {"screen": "S1", "eligible": eligible, "why": None if eligible else "no 300-session pool", "c_p": 1.2,
            "c_H": 0.4, "fp_cap": 0.12}


def floor_s2(eligible=True):
    """A floor as `screen.floor_s2` writes it under `receipt_s2()` (exact; the receipt's fp_cap, floor and margin)."""
    return {"screen": "S2", "method": "exact", "eligible": eligible, "why": None if eligible else "no eligible floor set",
            "c_pF1": 0.92, "c_H_used": 0.97, "fp_cap": 0.12, "c_H_floor": 0.9, "c_H_margin": 0.05}


def series(lots, bars, *, universe, capital, first=None, last=None):
    days = {"segment-1": np.arange(0, 5), "segment-2": np.arange(10, 15)}.get(bars.window, np.arange(100, 105))
    return S.Series(days=days.astype(np.int32), r=np.linspace(-0.01, 0.01, len(days)), w=np.ones(len(days)),
                    b=np.zeros(len(days)), exits=np.zeros(len(days), dtype=int), invested=np.ones(len(days), dtype=bool))


@contextlib.contextmanager
def screen(*, precheck=True, eligible=True, passed=True, same=False, pinned=True, s2=False, floor=None, gap=None,
           repo=NO_DOCS, s1x=None):
    """The screen package's functions at their interfaces, the receipt pinned in the repository's policy (or not; `s2`:
    receipt 2's block, else receipt 1's), the gate's capability, the equity identity (core's) and the daily store's
    last day (`gap`: why it ends before the look's holdout; core's store). `repo` is where a receipt file would be at
    hand (none by default, as on the House box); `s1x` the S1 floor measured for S1-X's rate beside an S2 verdict. The
    routing (`screen_of`, `receipt_path`, `floor_fits`) is the screen's own. The yielded mock is the capability's mint;
    its `.floor` and `.verdict` are the screen's, its `.s1x` elane's `_s1x_floor`."""
    with contextlib.ExitStack() as stack:
        enter = stack.enter_context
        block = (pinned_block_s2() if s2 else pinned_block()) if pinned else {}
        enter(mock.patch.object(elane, "_policy_block", return_value=block))
        enter(mock.patch.object(elane, "REPO", repo))
        enter(mock.patch.object(elane, "_holdout_gap", return_value=gap))
        measured = enter(mock.patch.object(elane, "_s1x_floor", return_value=s1x))
        enter(mock.patch.object(S, "pinned_receipt", return_value=receipt_s2() if s2 else receipt()))
        enter(mock.patch.object(S, "series", side_effect=series))
        enter(mock.patch.object(S, "precheck", return_value={"passed": precheck, "checks": {"activity": precheck}}))
        if floor is None:
            floor = floor_s2(eligible) if s2 else floor_s1(eligible)
        floored = enter(mock.patch.object(S, "floor", return_value=floor))
        answer = ({"screen": "S2", "passed": passed, "c_pF1": 0.92, "c_H": 0.97, "t_H": 1.4, "label": "beta"} if s2
                  else {"screen": "S1", "passed": passed, "c_used": 1.5, "c_H": 0.4, "t": 2.0, "label": "beta"})
        judged = enter(mock.patch.object(S, "verdict", return_value=answer))
        enter(mock.patch.object(S, "beside_line", return_value="c_H,used 0.97" if s2 else "c_used 1.5"))
        enter(mock.patch.object(S, "same_lineage", return_value=same))
        enter(mock.patch.object(S, "retry_permitted", return_value=False))
        mint = enter(mock.patch("league.equity.store.mint_equity_gate_capability", return_value="CAPABILITY"))
        enter(mock.patch("league.swarm.evaluator.equity_fingerprint", return_value=EQUITY_SHA))
        mint.floor, mint.verdict, mint.s1x = floored, judged, measured
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

    def test_the_floor_is_the_pinned_receipts_and_is_kept_only_while_it_fits_it(self):
        """S2-MERGE step 2: the look runs `screen.floor(segments, receipt=)` (the pinned receipt's own floor), never
        S1's `fp_cap=` floor, and a floor kept for the version under another receipt is run again BEFORE the look."""
        version, sha = self.ready()
        with screen() as mint:
            self.assertTrue(self.gate.look(self.store.family("b1"), version, sha))
        (call,) = mint.floor.call_args_list
        self.assertEqual((len(call.args), sorted(call.kwargs)), (1, ["receipt"]), "the floor is asked by the receipt")
        self.assertEqual(call.kwargs["receipt"], receipt())
        self.assertEqual(self.store.family("b1")["state"][elane.FLOOR_KEY]["1"], floor_s1())
        # The same version under receipt 2 (the pin moved, A11): S1's kept floor is not S2's, so S2's is run and kept.
        version, sha = self.ready("b2", code=CODE + "# another program\n")
        self.store.set_state("b2", **{elane.FLOOR_KEY: {"1": floor_s1()}})
        with screen(s2=True) as mint:
            self.assertTrue(self.gate.look(self.store.family("b2"), version, sha))
        (call,) = mint.floor.call_args_list
        self.assertEqual(call.kwargs, {"receipt": receipt_s2()})
        self.assertEqual(self.store.family("b2")["state"][elane.FLOOR_KEY]["1"], floor_s2())
        self.assertEqual(mint.verdict.call_args.kwargs["program_floor"], floor_s2(), "judged on the floor that fits")
        # An S2 floor run at another floor or margin than the pinned receipt's is not kept either.
        version, sha = self.ready("b3", code=CODE + "# a third program\n")
        self.store.set_state("b3", **{elane.FLOOR_KEY: {"1": {**floor_s2(), "c_H_floor": 0.95}}})
        with screen(s2=True) as mint:
            self.gate.look(self.store.family("b3"), version, sha)
        self.assertEqual(mint.floor.call_count, 1)
        version, sha = self.ready("b4", code=CODE + "# a fourth program\n")
        self.store.set_state("b4", **{elane.FLOOR_KEY: {"1": floor_s2()}})
        with screen(s2=True) as mint:
            self.gate.look(self.store.family("b4"), version, sha)
        self.assertEqual(mint.floor.call_count, 0, "a floor that fits the receipt is computed once a version")

    def test_a_floor_that_does_not_fit_the_receipt_spends_no_look(self):
        """The verdict refuses a floor of another screen or of other figures than the receipt's: were the look taken
        first it would be spent on a certain failure. It is not taken."""
        for i, bad in enumerate((floor_s1(), {**floor_s2(), "fp_cap": 0.10}, {**floor_s2(), "c_H_margin": 0.0},
                                 {**floor_s2(), "method": "worlds"}, {"c_pF1": 0.92}, "not a floor")):
            fid = f"m{i}"
            version, sha = self.ready(fid, code=CODE + f"# program {i}\n")
            with screen(s2=True, floor=bad) as mint:
                self.assertIsNone(self.gate.look(self.store.family(fid), version, sha), bad)
            self.assertEqual((mint.call_count, mint.verdict.call_count), (0, 0), bad)
            self.assertNotIn(("look", fid, "CAPABILITY"), self.runner.calls)
            state = self.store.family(fid)["state"]
            self.assertEqual((state["gate_ready"], state.get("look_inflight"), state.get(elane.FLOOR_KEY)),
                             (True, None, None), "owed again: nothing kept, nothing spent")
            self.assertIsNone(elane.lineage_spent(self.store, self.store.family(fid), ON))
        self.assertEqual(self.looks(), [])

    def test_a_look_under_receipt_2_is_recorded_as_s2s(self):
        version, sha = self.ready()
        with screen(s2=True, s1x={"eligible": True, "screen": "S1"}) as mint:
            self.assertTrue(self.gate.look(self.store.family("b1"), version, sha))
        mint.s1x.assert_called_once()
        self.assertEqual(mint.s1x.call_args.args[2], receipt_s2())
        self.assertEqual(mint.verdict.call_args.kwargs["s1_floor"], {"eligible": True, "screen": "S1"},
                         "S1-X's rate beside an S2 verdict comes from an S1 floor of the same Train-era series")
        self.assertEqual(mint.verdict.call_args.kwargs["receipt"], receipt_s2())
        (look,) = self.looks()
        detail = look["detail"]
        self.assertEqual((detail["screen"], detail["receipt"], detail["c_pF1"], detail["c_H"], detail["beside"]),
                         ("S2", SHA, 0.92, 0.97, "c_H,used 0.97"))
        self.assertNotIn("c_used", detail, "S2 has no pooled-t bar")
        fam = self.store.family("b1")
        self.assertEqual(fam["band"], "candidate")
        events = [e["payload"] for e in self.store.events_after(0)
                  if e["kind"] == "swarm.gate" and e["payload"].get("action") == "look"]
        self.assertEqual([e["screen"] for e in events], ["S2"])
        self.assertEqual(elane.view(fam, lane=BETA)["screen"], "S2", "the view names the screen that judged the look")
        self.assertIsNone(elane.view({"state": {}}, lane=BETA)["screen"])

    def test_s1xs_rate_is_measured_only_under_receipt_2_and_never_stops_a_look(self):
        segments = [S.Series(days=np.arange(5, dtype=np.int32), r=np.zeros(5), w=np.ones(5), b=np.zeros(5),
                             exits=np.zeros(5, dtype=int), invested=np.ones(5, dtype=bool))]
        with mock.patch.object(S, "floor", return_value={"screen": "S1", "eligible": True, "curves": {}}) as floored:
            self.assertIsNone(elane._s1x_floor(S, segments, receipt()), "receipt 1's own floor carries the curve")
            self.assertEqual(floored.call_count, 0)
            self.assertEqual(elane._s1x_floor(S, segments, receipt_s2()),
                             {"screen": "S1", "eligible": True, "curves": {}})
            self.assertEqual(floored.call_args.kwargs, {"fp_cap": 0.12}, "S1's floor at the receipt's cap")
        with mock.patch.object(S, "floor", return_value={"screen": "S1", "eligible": False, "why": "no pool"}):
            self.assertIsNone(elane._s1x_floor(S, segments, receipt_s2()), "an ineligible S1 floor: unmeasured")
        with mock.patch.object(S, "floor", side_effect=RuntimeError("numpy")):
            self.assertIsNone(elane._s1x_floor(S, segments, receipt_s2()))

    def test_a_receipt_file_whose_bytes_are_not_the_pinned_sha_spends_no_look(self):
        """A11's pin: where the receipt file is at hand, its bytes are the pinned sha256 or the screen refuses (the
        look waits; nothing is spent, nothing is retired)."""
        version, sha = self.ready()
        with tempfile.TemporaryDirectory(dir=self.dir.name) as root:
            path = Path(root) / S.RECEIPT_PATH_S2
            path.parent.mkdir(parents=True)
            shutil.copy(FAKE_S2, path)
            good = hashlib.sha256(path.read_bytes()).hexdigest()
            block = pinned_block_s2(receipt_sha256=good)
            doc = json.loads(path.read_text())
            doc["c_H_floor"] = 0.5                              # the file edited after it was pinned
            path.write_text(json.dumps(doc))
            with screen(s2=True, repo=Path(root)) as mint:
                with mock.patch.object(elane, "_policy_block", return_value=block), \
                        mock.patch.object(S, "pinned_receipt", return_value=S.pinned_receipt_s2(block)):
                    self.assertIsNone(self.gate.look(self.store.family("b1"), version, sha))
                    self.assertEqual((self.looks(), mint.call_count, mint.floor.call_count), ([], 0, 0))
                    state = self.store.family("b1")["state"]
                    self.assertEqual((state["gate_ready"], state["gate_outcome"]["result"]), (True, "waiting"))
                    self.assertIn("is not the pinned", state["gate"])
                    self.assertIsNone(elane.lineage_spent(self.store, self.store.family("b1"), ON))
                    # The file as it was pinned: the look goes ahead.
                    shutil.copy(FAKE_S2, path)
                    self.assertTrue(self.gate.look(self.store.family("b1"), version, sha))
        self.assertEqual(len(self.looks()), 1)

    def test_the_look_waits_while_the_store_ends_before_the_calibrated_holdout(self):
        """A12: a look reads exactly the 194 calibrated sessions; a store that ends earlier would spend the lineage's
        one look on a certain failure (the verdict's windows), so the look waits for the data job."""
        version, sha = self.ready()
        ran = len(self.runner.calls)
        with screen(gap="the daily store ends 2026-10-08") as mint:
            self.assertIsNone(self.gate.look(self.store.family("b1"), version, sha))
        self.assertEqual((self.looks(), mint.call_count, mint.floor.call_count), ([], 0, 0))
        self.assertEqual(len(self.runner.calls), ran, "it waits before any run: no segment, no Validation, no look")
        state = self.store.family("b1")["state"]
        self.assertEqual((state["gate_ready"], state["gate_outcome"]["result"], state.get("look_inflight")),
                         (True, "waiting", None))
        with screen() as mint:
            with mock.patch.object(elane, "_holdout_gap", side_effect=RuntimeError("no manifest")):
                self.assertIsNone(self.gate.look(self.store.family("b1"), version, sha), "an unreadable store: no look")
            self.assertEqual(mint.call_count, 0)
        with screen():
            self.assertTrue(self.gate.look(self.store.family("b1"), version, sha))

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


class HoldoutGap(StoreCase):
    """`elane._holdout_gap` on real (synthetic) daily stores: the look's span is the calibrated holdout, whole (A12)."""

    def test_a_store_that_ends_before_the_look_cap_makes_the_look_wait(self):
        import datetime as dt

        from league.equity import config, synth
        from league.equity.store import MissingData, StoreRefused

        root = Path(self.dir.name)
        with self.assertRaises((MissingData, StoreRefused, OSError), msg="no store: no look"):
            elane._holdout_gap(root)
        synth.synthetic_store(root / elane.STORE_DIR, symbols=("SPY",), start=dt.date(2026, 9, 1),
                              end=dt.date(2026, 10, 9), as_of=dt.date(2026, 10, 8))
        why = elane._holdout_gap(root)
        self.assertIn("ends 2026-10-08", why)
        self.assertIn(config.LOOK_CAP.isoformat(), why)
        other = Path(self.dir.name) / "whole"
        synth.synthetic_store(other / elane.STORE_DIR, symbols=("SPY",), start=dt.date(2026, 9, 1),
                              end=dt.date(2026, 10, 9))
        self.assertIsNone(elane._holdout_gap(other), "through the look cap: the 194 calibrated sessions are all there")
        later = Path(self.dir.name) / "later"
        synth.synthetic_store(later / elane.STORE_DIR, symbols=("SPY",), start=dt.date(2026, 9, 1),
                              end=dt.date(2026, 10, 14))
        self.assertIsNone(elane._holdout_gap(later), "forward days after the cap never enter a look")
