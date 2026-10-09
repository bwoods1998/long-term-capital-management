"""THE DIRECTION LANE in the researcher (league/swarm/researcher.py, release D-1, PLAN D3, HARNESS C5 and 6.4 item 7).

A direction family climbs direction-v2 (S_D, the pooled t of daily P&L over Train at 1.0x, under E1, E3, E4 and E5) in
place of the worst-year score; its 1.5x run is judged by P1, R2 and R3 in place of the profit alone, and the game's look
follows only a pass; its brief, status, run views and sweep table carry the lane's text and Train-year figures only; the
graveyard tool labels DRIFT deaths as not binding for it; the ROLE is lane-aware while the lane is on. The alpha lane's
CODE PATHS are golden: an alpha family runs the same with the lane on as with it off, and with it off the role is
ccfa48d5's byte for byte (the role's text is the one shared change the lane makes to an alpha researcher, PLAN D3 and the
operator's decision 1).

Every figure is invented (`league.tests.test_dlane`'s fixtures): none is read from the operator's studies.
"""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from league.swarm import cards, dlane, evidence, game
from league.swarm import settings as S
from league.swarm.researcher import (CORE_SPAN, ROLE, ROLE_DRIFT_LANES, ROLE_LANES, ROLE_SCORE_LANES, SCREENED, VERDICT_WORDS,
                                     Researcher, lane_cells, migrate_objective)
from league.swarm.seeds import SEEDS, family_spec, program_for
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock
from league.tests.swarm_fakes import result as fake_result
from league.tests.test_dlane import LEAK, always_in, unit_ctx
from league.tests.test_dlane import run as shaped_run

GATE = {"mode": "gate"}
#: sha256 of `researcher.ROLE` at ccfa48d5 (the release before D-1): with the lane off the prompt is exactly it.
ROLE_CCFA48D5 = "a75bbbaa8c9ee1084bea67bc5e964b78540bdc551d240318617dd6cd298cd458"
SEED = next(s for s in SEEDS if s["id"] == "condor-vrp")
DIRECTION_SPEC = {"id": "spy-drift-gate", "mechanism": "One out-of-the-money SPY call rents the equity premium while a trend "
                  "gate says the index's drift is reliable, and stands aside when it is not.",
                  "structure": "long_single", "roots": ["SPY"], "dte": [7, 21],
                  "rejection": "no better than the same call entered every session", "lane": "direction"}
#: An invented Train year set an alpha score and S_D order differently: steady (every year up, the alpha score's
#: favourite) against always-in (the pooled t's, with an in-market losing year).
STEADY = {"2022": (900.0, 1.0, {}), "2023": (1000.0, 1.1, {}), "2024": (1100.0, 1.2, {})}
#: The founder's program with its one open made a long call (release D-1b, the review's finding 3): a direction program
#: names no other open, no put and no short leg (`dlane.calls_only_code`), so the direction cases run this one.
_CONDOR_LEGS = '''    return "iron_condor", [
        {"side": "long", "right": "P", "rel": 1, "offset": -p["width"]},
        {"side": "short", "right": "P", "dte": dte, "delta": p["short_delta"]},
        {"side": "short", "right": "C", "dte": dte, "delta": p["short_delta"]},
        {"side": "long", "right": "C", "rel": 2, "offset": p["width"]}]'''
assert _CONDOR_LEGS in program_for(SEED)[0]
CALLS_CODE = program_for(SEED)[0].replace(
    _CONDOR_LEGS, '''    return "long_call", [{"side": "long", "right": "C", "dte": dte, "delta": p["short_delta"]}]''')
ALWAYS_IN = {"2022": (-1500.0, -3.9, {}), "2023": (2600.0, 2.1, {}), "2024": (2400.0, 1.9, {})}


def train(name: str, years: dict, *, pnl: float | None = None, stress: float = 1.0, stats: bool = False, **extra: Any) -> dict:
    """A Gym-shaped Train result (`swarm_fakes.result`) with direction-shaped per-year rows and drift figures
    (`test_dlane.run`; `stats` adds the drift statistics the same-exposure buy-and-hold reads): a deterministic run id, a
    summary P&L that is the years' sum unless given."""
    base = fake_result(name)
    shaped = shaped_run(years, pnl=pnl, stats=stats)
    base.update(run_id=f"run-{name}", by_year=shaped["by_year"], drift=shaped["drift"], trades=shaped["trades"], stress=stress)
    base["summary"].update(pnl=shaped["summary"]["pnl"], quarters_positive="9/12")
    base.update(extra)
    return base


class ScriptPool:
    """A Gym that answers each Train job from `answer(job)` (no `submit`: no robustness job is queued)."""

    def __init__(self, answer):
        self.answer = answer
        self.jobs: list = []

    def run(self, job, timeout=None, late=None):
        self.jobs.append(job)
        return self.answer(job)


def by_params(table: dict, *, stats: bool = False) -> Any:
    """A pool answer keyed by the job's `vrp_min` (a variant's identity): `table[vrp_min] -> (name, years)`."""
    def answer(job):
        name, years = table[float((job.params or {}).get("vrp_min", 0.0))]
        return train(f"{name}-{job.version}", years, stats=stats)
    return answer


class Case(unittest.TestCase):
    def make(self, mode: str | None, answer=None, *, drift_screen: bool = False) -> tuple[SwarmStore, Researcher, dict]:
        """A store, a researcher over it and its environment. The tournament's drift screen is off, as the committed
        policy has it since fast lane v2 (Oct 7); `drift_screen` True is the code's default (a brake an operator may set)."""
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        root = Path(d.name)
        clock = Clock()
        store = SwarmStore(root, clock=clock)
        self.addCleanup(store.close)
        settings = copy.deepcopy(S.DEFAULTS)
        settings["tournament"]["drift_screen"] = drift_screen
        if mode is not None:
            settings["dlane"] = {"mode": mode}
        pool = ScriptPool(answer or (lambda job: train(f"x-{job.version}", ALWAYS_IN)))
        researcher = Researcher(store, None, pool, settings, clock=clock, starter=program_for, background=False)
        return store, researcher, {"root": root, "clock": clock, "settings": settings, "pool": pool}

    def gym_run(self, researcher: Researcher, fid: str, params: dict, code: str | None = None) -> dict:
        out: dict = {}
        fam = researcher.store.family(fid)
        code = code or (CALLS_CODE if (fam.get("spec") or {}).get("lane") == "direction" else program_for(SEED)[0])
        return researcher._gym_run(fam, {"code": code, "params": params}, out, author="synthetic")


# ------------------------------------------------------------------------------------------------ the role
class Role(Case):
    def test_the_role_is_ccfa48d5s_byte_for_byte_and_the_prompt_with_the_lane_off_is_it(self):
        self.assertEqual(hashlib.sha256(ROLE.encode("utf-8")).hexdigest(), ROLE_CCFA48D5)
        for mode in (None, "off"):
            _, researcher, _ = self.make(mode)
            self.assertIs(researcher.prompt(), researcher.system, "the same string: the cached prefix is untouched")
            self.assertEqual(researcher.prompt(), ROLE + researcher.contract)

    def test_the_lane_on_makes_the_role_lane_aware_for_every_researcher_and_a_switch_needs_no_restart(self):
        _, researcher, env = self.make("gate")
        self.assertIs(researcher.prompt(), researcher.system_lanes)
        self.assertEqual(researcher.prompt(), ROLE_LANES + researcher.contract)
        self.assertNotIn("DRIFT IS NOT AN EDGE", ROLE_LANES)
        self.assertIn("never your best and is never validated", ROLE, "the old, unconditional claim")
        self.assertIn(ROLE_SCORE_LANES + ROLE_DRIFT_LANES, ROLE_LANES)
        self.assertIn("ALPHA lane: drift is not alpha", ROLE_LANES)
        self.assertIn("DIRECTION lane: profit from drift counts", ROLE_LANES)
        self.assertIn("reported beside the same-risk buy-and-hold", ROLE_LANES)
        self.assertIn("While the\ndrift screen is on", ROLE_LANES, "the screen's rule is stated as conditional, as the code is")
        # Only the two paragraphs change: what comes before and after is ROLE's.
        head, tail = ROLE.index("THE TRAIN SCORE you climb"), ROLE.index("Your family trades one to five")
        self.assertTrue(ROLE_LANES.startswith(ROLE[:head]))
        self.assertTrue(ROLE_LANES.endswith(ROLE[tail:]))
        self.assertIsNone(LEAK.search(ROLE_LANES))
        self.assertTrue(ROLE_LANES.isascii())
        env["settings"]["dlane"]["mode"] = "off"  # the loop updates the dict in place (THE ROLLBACK, no restart)
        self.assertIs(researcher.prompt(), researcher.system)
        shadow = {**env["settings"], "dlane": {"mode": "shadow"}}
        researcher.settings = shadow
        self.assertIs(researcher.prompt(), researcher.system_lanes, "shadow runs the lane's research: its role too")


# ------------------------------------------------------------------------------------------------ alpha golden
def alpha_scenario(store: SwarmStore, researcher: Any, clock: Clock, root: Path) -> dict:
    """Every researcher path the lane touches, on an ALPHA family: two runs, a stored run, a sweep, a 1.5x run that
    profits and one that loses, the status, the brief, the graveyard (with a DRIFT death in it), `submit` and
    `eligible_run`; then the store as it stands. Paths and timestamps come from the case's own root and clock."""
    fam = store.add_family(family_spec(SEED), origin="seed")
    fid = fam["id"]
    code, _ = program_for(SEED)
    dead = store.add_family({**family_spec(SEED), "id": "dead-drift"}, origin="seed")
    store.retire(dead["id"], f"{SCREENED}. {VERDICT_WORDS['drift']}.")
    store.bury(dead["id"], "Calls held into a rising tape earned the drift and nothing else.")
    views: list = []

    def run(params: dict) -> dict:
        out: dict = {}
        view = researcher._gym_run(store.family(fid), {"code": code, "params": params}, out, author="synthetic")
        clock.advance(60)
        return {"view": view, "out": out}

    views.append(run({"vrp_min": 1.3}))
    views.append(run({"vrp_min": 1.5}))
    views.append(run({"vrp_min": 1.3}))  # NO DUPLICATE RUNS: the stored result
    out: dict = {}
    views.append({"sweep": researcher._gym_sweep(store.family(fid), {"variants": [{"vrp_min": 1.1}, {"vrp_min": 1.7}]}, out,
                                                 author="synthetic"), "out": out})
    clock.advance(60)
    best = store.family(fid)["state"].get("best_train_version") or 1
    with mock.patch.object(game, "maybe_look") as look:
        researcher.robust_landed(fid, int(best), "stress_1.5", 1.5,
                                 train("alpha-15-win", {"2022": (300.0, 0.4, {}), "2023": (200.0, 0.3, {}),
                                                        "2024": (100.0, 0.2, {})}, stress=1.5))
        researcher.robust_landed(fid, 2, "stress_1.5", 1.5,
                                 train("alpha-15-loss", {"2022": (-300.0, -0.4, {}), "2023": (100.0, 0.1, {}),
                                                         "2024": (100.0, 0.1, {})}, stress=1.5))
    views.append({"looks": [list(c.args[1:3]) for c in look.call_args_list]})
    clock.advance(60)
    fam = store.family(fid)
    views.append({"status": researcher.status(fam), "brief": researcher.brief(fam)})
    views.append({"graveyard": researcher._local_tool(fam, "graveyard", {"query": ""}, {})})
    runs = store.runs(fid, window="train", limit=100)
    views.append({"eligible": [researcher.eligible_run(fam, r) for r in runs]})
    views.append({"submit": researcher._local_tool(fam, "submit", {"run_id": runs[-1]["run_id"]}, {})})
    fam = store.family(fid)
    keep = ("best_train", "best_version", "stall", "trials", "revisions", "since_val_trials", "roots", "spec", "state")
    rows = [{k: v for k, v in r.items() if k != "path"} for r in store.runs(fid, window="train", limit=100)]
    events = [{"kind": e["kind"], "family": e.get("family"), "payload": e.get("payload")} for e in store.events_after(0)]
    text = json.dumps({"views": views, "family": {k: fam.get(k) for k in keep}, "runs": rows, "events": events},
                      sort_keys=True, default=str)
    return json.loads(text.replace(str(root), "<root>"))


class AlphaGolden(Case):
    def test_an_alpha_family_runs_every_path_the_same_with_the_lane_on_as_off(self):
        """The alpha lane's code paths are golden: off is ccfa48d5's (every existing test runs it, the policy layer being
        empty in tests), and gate and shadow change nothing an alpha family does, records or reads but the role."""
        for screen in (False, True):  # the committed policy's drift screen (off), and the code's default (on)
            dumps = {}
            for mode in (None, "off", "shadow", "gate"):
                answer = by_params({1.3: ("a", STEADY), 1.5: ("b", ALWAYS_IN), 1.1: ("c", STEADY), 1.7: ("d", ALWAYS_IN)})
                store, researcher, env = self.make(mode, answer, drift_screen=screen)
                dumps[mode] = alpha_scenario(store, researcher, env["clock"], env["root"])
            if not screen:
                self.assertIsNotNone(dumps[None]["family"]["best_train"], "the scenario scored an alpha best")
            else:
                self.assertTrue(dumps[None]["family"]["state"].get("drift_failed"), "and the screen marked its versions")
            for mode in ("off", "shadow", "gate"):
                self.assertEqual(dumps[mode], dumps[None], (screen, mode))
            text = json.dumps(dumps["gate"])
            for word in ("direction-v2", '"' + dlane.STATE_KEY + '"', "YOUR LANE", "not binding for the direction lane",
                         "DIRECTION OBJECTIVE"):
                self.assertNotIn(word, text, (screen, word))


# ------------------------------------------------------------------------------------------------ the direction score
class DirectionScore(Case):
    def setUp(self):
        answer = by_params({1.3: ("steady", STEADY), 1.5: ("always", ALWAYS_IN),
                            1.7: ("one-year", {"2022": (0.0, 0.0, {"held": 10, "trades": 5, "days_traded": 5}),
                                               "2023": (0.0, 0.0, {"held": 10, "trades": 5, "days_traded": 5}),
                                               "2024": (2400.0, 1.9, {})})})
        self.store, self.researcher, self.env = self.make("gate", answer)
        self.fid = self.store.add_family(DIRECTION_SPEC, origin="architect")["id"]

    def s_d(self, years: dict) -> float:
        return dlane.train_score(train("probe", years), first_year=2022, settings={"dlane": GATE})["score"]

    def test_a_direction_family_climbs_s_d_and_its_best_is_the_highest_s_d(self):
        steady = self.gym_run(self.researcher, self.fid, {"vrp_min": 1.3})
        always = self.gym_run(self.researcher, self.fid, {"vrp_min": 1.5})
        # The alpha score orders these two the other way: the always-in program's worst year is deep in the red.
        alpha = {k: evidence.train_score(train(k, y), first_year=2022)["score"] for k, y in (("s", STEADY), ("a", ALWAYS_IN))}
        self.assertGreater(alpha["s"], 0)
        self.assertLess(alpha["a"], 0)
        self.assertGreater(self.s_d(ALWAYS_IN), self.s_d(STEADY))
        fam = self.store.family(self.fid)
        self.assertEqual(fam["state"]["best_train_version"], 2)
        self.assertAlmostEqual(fam["best_train"], self.s_d(ALWAYS_IN), places=6)
        self.assertEqual(always["new_best_train_score"], round(self.s_d(ALWAYS_IN), 3))
        # The view: S_D as its Train score, the lane block (Train years only) with the plain statement.
        self.assertAlmostEqual(always["train_score"]["score"], self.s_d(ALWAYS_IN), places=6)
        self.assertTrue(always["train_score"]["eligible"])
        lane = always["lane"]
        self.assertEqual((lane["lane"], lane["objective"], lane["verdict"]), ("direction", "direction-v2", "eligible"))
        self.assertEqual(lane["note"], dlane.ALWAYS_IN_NOTE)
        self.assertEqual(sorted(lane["years"]), ["2022", "2023", "2024"])
        self.assertIs(lane["reported"]["E2"], False, "reported, never a bar")
        self.assertIn("lane", steady)
        # Its row keeps S_D, eligibility and the compact score (a pruned run is still judged).
        row = self.store.run(always["run_id"])
        self.assertAlmostEqual(row["summary"]["train_score"], self.s_d(ALWAYS_IN), places=6)
        self.assertTrue(row["summary"]["train_eligible"])
        self.assertEqual(row["summary"][dlane.STATE_KEY]["objective"], "direction-v2")
        self.assertEqual(row["summary"][dlane.STATE_KEY]["active"], ["2022", "2023", "2024"])
        # And the family's state keeps the verdicts the architect's counts read.
        kept = fam["state"][dlane.STATE_KEY]["versions"]
        self.assertEqual(sorted(kept), ["1", "2"])
        counts = dlane.failure_counts(self.store, 48.0, now=self.env["clock"]())
        self.assertEqual((counts["versions"], counts["eligible"], counts["reported_misses"]["E2"]), (2, 2, 1))

    def test_a_version_failing_a_bar_is_never_the_best_and_the_view_names_the_bar(self):
        view = self.gym_run(self.researcher, self.fid, {"vrp_min": 1.7})
        self.assertFalse(view["train_score"]["eligible"])
        self.assertTrue(view["train_score"]["why_not_eligible"].startswith("fails E1:"), view["train_score"])
        self.assertEqual(view["lane"]["fails"], ["E1"])
        fam = self.store.family(self.fid)
        self.assertIsNone(fam["best_train"])
        self.assertFalse(fam["state"].get("train_candidates"))
        ok, why = self.researcher.eligible_run(fam, self.store.run(view["run_id"]))
        self.assertFalse(ok)
        self.assertIn("direction objective: fails E1", why)
        self.assertEqual(dlane.failure_counts(self.store, 48.0, now=self.env["clock"]())["fails"]["E1"], 1)

    def test_the_unit_is_priced_at_the_live_context_and_unknown_passes(self):
        unit_ctx(self.env["root"])  # SPY up a fifth on its 2024 mean, a $1,000 account: one lot is over the cap
        over = self.gym_run(self.researcher, self.fid, {"vrp_min": 1.5})
        self.assertFalse(over["train_score"]["eligible"])
        self.assertEqual(over["lane"]["fails"], ["E5"])
        self.assertEqual(over["lane"]["unit"]["verdict"], "fail")
        unit_ctx(self.env["root"], sod="2000.00", last="2000.00")  # the account doubled: it fits
        fits = self.gym_run(self.researcher, self.fid, {"vrp_min": 1.3})
        self.assertEqual(fits["lane"]["unit"]["verdict"], "pass")
        for name in (dlane.CLOSES_FILE, dlane.HEALTH_FILE):
            (self.env["root"] / name).unlink()
        again = self.gym_run(self.researcher, self.fid, {"vrp_min": 1.5})  # stored: scored again, the unit unknown today
        self.assertEqual(again["lane"]["unit"]["verdict"], "unknown")
        self.assertTrue(again["train_score"]["eligible"], "E5 unknown passes: the live path prices every open again")

    def test_an_operators_drift_screen_still_binds_a_direction_version(self):
        """A judgment call of the wiring, said here: the tournament's drift screen is a brake (off in the committed policy
        since Oct 7). Switched back on, it binds a direction version as any other: the lane does not lift it."""
        store, researcher, _ = self.make("gate", by_params({1.5: ("always", ALWAYS_IN)}), drift_screen=True)
        fid = store.add_family(DIRECTION_SPEC, origin="architect")["id"]
        view = self.gym_run(researcher, fid, {"vrp_min": 1.5})
        self.assertEqual(view["lane"]["verdict"], "eligible", "the lane's own bar holds")
        self.assertFalse(view["train_score"]["eligible"])
        self.assertIn("fails the drift screen", view["train_score"]["why_not_eligible"])
        self.assertIsNone(store.family(fid)["best_train"])

    def test_the_lane_off_is_the_rollback_for_a_direction_family(self):
        store, researcher, _ = self.make("off", by_params({1.5: ("always", ALWAYS_IN)}))
        fid = store.add_family(DIRECTION_SPEC, origin="architect")["id"]
        view = self.gym_run(researcher, fid, {"vrp_min": 1.5})
        self.assertNotIn("lane", view)
        self.assertAlmostEqual(view["train_score"]["score"], evidence.train_score(train("a", ALWAYS_IN), first_year=2022)["score"])
        row = store.run(view["run_id"])
        self.assertNotIn(dlane.STATE_KEY, row["summary"])
        fam = store.family(fid)
        self.assertNotIn(dlane.STATE_KEY, fam["state"])
        self.assertNotIn("YOUR LANE", researcher.brief(fam))
        self.assertNotIn("DIRECTION OBJECTIVE", researcher.status(fam))

    def test_migrate_objective_chooses_a_direction_best_by_s_d(self):
        self.gym_run(self.researcher, self.fid, {"vrp_min": 1.3})
        self.gym_run(self.researcher, self.fid, {"vrp_min": 1.5})
        for mode, version in (("gate", 2), ("off", 1)):
            self.store.put("train_objective", None)
            self.store.set_state(self.fid, objective_migrated=None, legacy_best=None)
            state = {k: v for k, v in self.store.family(self.fid)["state"].items() if k != "legacy_best"}
            self.store.update_family(self.fid, best_train=None)
            with self.store.atomic():
                self.store._exec("UPDATE families SET state=? WHERE id=?", (json.dumps(state), self.fid))
            migrate_objective(self.store, settings={**self.env["settings"], "dlane": {"mode": mode}})
            self.assertEqual(self.store.family(self.fid)["best_version"], version, mode)


# ------------------------------------------------------------------------------------------------ the 1.5x rules
class Demotion(Case):
    BASE = {"2022": (-100.0, -0.5, {"held": 50}), "2023": (2600.0, 2.1, {}), "2024": (2400.0, 1.9, {})}

    def setUp(self):
        self.store, self.researcher, self.env = self.make("gate", by_params({1.5: ("always", ALWAYS_IN),
                                                                              1.3: ("out", self.BASE)}))
        self.fid = self.store.add_family(DIRECTION_SPEC, origin="architect")["id"]

    def land(self, n: int, years: dict, *, pnl: float | None = None, fid: str | None = None):
        with mock.patch.object(game, "maybe_look") as look:
            self.researcher.robust_landed(fid or self.fid, n, "stress_1.5", 1.5,
                                          train(f"r15-{n}-{len(self.store.runs(fid or self.fid, limit=100))}", years,
                                                pnl=pnl, stress=1.5))
        fam = self.store.family(fid or self.fid)
        return fam, look

    def best(self, params: dict) -> int:
        view = self.gym_run(self.researcher, self.fid, params)
        self.assertTrue(view["train_score"]["eligible"], view)
        return int(view["version"])

    def test_p1_a_loss_at_one_and_a_half_demotes(self):
        n = self.best({"vrp_min": 1.5})
        fam, look = self.land(n, {"2022": (-2500.0, -4.5, {}), "2023": (1200.0, 1.0, {}), "2024": (1100.0, 0.9, {})})
        self.assertIn(n, fam["state"]["robust_failed"])
        self.assertTrue(fam["state"]["robust_why"][str(n)].startswith("fails P1:"), fam["state"]["robust_why"])
        self.assertIsNone(fam["best_train"])
        look.assert_not_called()

    def test_r2_an_out_year_that_falls_through_its_floor_at_one_and_a_half_demotes(self):
        n = self.best({"vrp_min": 1.3})
        fam, look = self.land(n, {"2022": (-300.0, -1.5, {"held": 50}), "2023": (2000.0, 1.8, {}), "2024": (1900.0, 1.6, {})})
        self.assertIn(n, fam["state"]["robust_failed"])
        self.assertTrue(fam["state"]["robust_why"][str(n)].startswith("fails R2:"), fam["state"]["robust_why"])
        look.assert_not_called()
        self.assertIn(f"version {n} fails R2:", self.researcher.status(fam), "the status names the rule")

    def test_r3_a_profit_under_half_the_one_x_profit_demotes_where_the_alpha_rule_would_not(self):
        n = self.best({"vrp_min": 1.5})
        thin = {"2022": (-1200.0, -3.5, {}), "2023": (1300.0, 1.2, {}), "2024": (1100.0, 1.0, {})}
        fam, look = self.land(n, thin)
        self.assertIn(n, fam["state"]["robust_failed"])
        self.assertTrue(fam["state"]["robust_why"][str(n)].startswith("fails R3:"), fam["state"]["robust_why"])
        look.assert_not_called()
        kept = fam["state"][dlane.STATE_KEY]["versions"][str(n)]["robust"]
        self.assertEqual((kept["known"], kept["passed"], kept["fails"]), (True, False, ["R3"]))
        self.assertEqual(dlane.failure_counts(self.store, 48.0, now=self.env["clock"]())["robust"]["R3"], 1)
        # The alpha twin: the same 1.5x run made a profit, so the alpha lane's rule keeps its version, and looks.
        seed = self.store.add_family(family_spec(SEED), origin="seed")["id"]
        alpha = self.gym_run(self.researcher, seed, {"vrp_min": 1.5})
        self.assertNotIn("lane", alpha)
        fam, look = self.land(int(alpha["version"]), thin, fid=seed)
        self.assertFalse(fam["state"].get("robust_failed"))
        look.assert_called_once()

    def test_a_pass_keeps_the_version_and_only_then_the_game_may_look(self):
        n = self.best({"vrp_min": 1.5})
        fam, look = self.land(n, {"2022": (-1700.0, -4.1, {}), "2023": (2300.0, 1.9, {}), "2024": (2100.0, 1.7, {})})
        self.assertFalse(fam["state"].get("robust_failed"))
        self.assertEqual(fam["state"]["best_train_version"], n)
        look.assert_called_once()
        self.assertEqual(look.call_args.args[1:3], (self.fid, n))
        kept = fam["state"][dlane.STATE_KEY]["versions"][str(n)]["robust"]
        self.assertEqual((kept["known"], kept["passed"]), (True, True))
        status = self.researcher.status(fam)
        self.assertIn("(P1 yes)", status)
        self.assertIn("(R2 yes)", status)

    def test_an_unknown_verdict_demotes_nothing_of_its_own_and_never_looks(self):
        """No 1.0x score of the version (here: a version with no Train run): the House's profit rule stands alone."""
        version = self.store.add_version(self.fid, program_for(SEED)[0], {"vrp_min": 9.0}, author="synthetic")
        n = int(version["n"])
        fam, look = self.land(n, {"2022": (-100.0, -0.1, {}), "2023": (50.0, 0.1, {}), "2024": (60.0, 0.1, {})})
        self.assertFalse(fam["state"].get("robust_failed"))
        look.assert_not_called()
        self.assertNotIn(str(n), (fam["state"].get(dlane.STATE_KEY) or {}).get("versions") or {})
        fam, _ = self.land(n, {"2022": (-500.0, -0.5, {}), "2023": (50.0, 0.1, {}), "2024": (60.0, 0.1, {})})
        self.assertEqual(fam["state"]["robust_why"][str(n)], "lost money on Train at 1.5x the half-spread")


# ------------------------------------------------------------------------------------------------ what agents read
class WhatAgentsRead(Case):
    def setUp(self):
        hidden = {**ALWAYS_IN, "2020": (5000.0, 4.0, {}), "2021": (4000.0, 3.5, {})}
        self.store, self.researcher, self.env = self.make("gate", by_params({1.5: ("hidden", hidden)}, stats=True))
        self.fid = self.store.add_family(DIRECTION_SPEC, origin="architect")["id"]
        unit_ctx(self.env["root"], sod="2000.00", last="2000.00")

    def test_the_brief_status_and_views_carry_the_lanes_text_and_no_hidden_year(self):
        view = self.gym_run(self.researcher, self.fid, {"vrp_min": 1.5})
        fam = self.store.family(self.fid)
        brief, status = self.researcher.brief(fam), self.researcher.status(fam)
        self.assertIn("YOUR LANE: DIRECTION", brief)
        self.assertIn(dlane.ALWAYS_IN_NOTE, brief)
        self.assertIn("DIRECTION OBJECTIVE (direction-v2), version 1", status)
        self.assertIn(dlane.ALWAYS_IN_NOTE, status)
        self.assertIn("the same exposure held every session", status, "beside it: the buy-and-hold of its exposure")
        for name, text in (("brief", brief), ("status", status), ("lane", json.dumps(view["lane"])),
                           ("train_score", json.dumps(view["train_score"]))):
            self.assertIsNone(LEAK.search(text), f"{name}: {LEAK.search(text)}")
        self.assertEqual(sorted(view["lane"]["years"]), ["2022", "2023", "2024"])
        self.assertEqual(sorted(view["train_score"]["by_year"]), ["2022", "2023", "2024"])
        # The S_D the score reports is over the Train years alone: the older years the run carried never enter it.
        self.assertAlmostEqual(view["train_score"]["score"],
                               dlane.train_score(train("t", ALWAYS_IN), first_year=2022, settings={"dlane": GATE})["score"])

    def test_an_alpha_familys_brief_and_status_carry_no_lane_text_with_the_lane_on(self):
        seed = self.store.add_family(family_spec(SEED), origin="seed")["id"]
        self.gym_run(self.researcher, seed, {"vrp_min": 1.5})
        fam = self.store.family(seed)
        self.assertNotIn("YOUR LANE", self.researcher.brief(fam))
        self.assertNotIn("DIRECTION OBJECTIVE", self.researcher.status(fam))

    def test_the_mechanism_verdict_reaches_the_view_in_gate_mode_only(self):
        """The card's gate against its every-session twin is the mechanism test: its verdict is shown in the test's GATE
        mode only (SHADOW IS BLIND, mechanism.py MODES), and "not tested" otherwise."""
        fam = self.store.family(self.fid)
        with mock.patch.object(Researcher, "mechanism_lineage", return_value={"passed": True, "broad": False}), \
                mock.patch.object(cards, "card_of", return_value={"card": {}, "sha": "x"}):
            for mode, word in (("shadow", None), ("gate", "passed")):
                self.researcher.settings["researcher"]["mechanism_test"] = {"mode": mode}
                self.assertEqual(self.researcher._dlane_mechanism(fam), word, mode)
        with mock.patch.object(Researcher, "mechanism_lineage", return_value={"passed": False, "broad": True}), \
                mock.patch.object(cards, "card_of", return_value={"card": {}, "sha": "x"}):
            self.assertIsNone(self.researcher._dlane_mechanism(fam), "a broad replay before the gate is no pass")
        self.researcher.settings["researcher"]["mechanism_test"] = {"mode": "shadow"}
        self.assertEqual(self.gym_run(self.researcher, self.fid, {"vrp_min": 1.5})["lane"]["reported"]["mechanism"],
                         "not tested")
        with mock.patch.object(Researcher, "_dlane_mechanism", return_value="failed"):
            view = self.researcher._stored_run(self.store.family(self.fid), self.store.runs(self.fid, limit=1)[0], {},
                                               code=program_for(SEED)[0], stress=1.0)
        self.assertEqual(view["lane"]["reported"]["mechanism"], "failed")

    def test_the_graveyard_tool_labels_drift_deaths_for_the_direction_lane_only(self):
        dead = self.store.add_family({**family_spec(SEED), "id": "dead-drift"}, origin="seed")["id"]
        self.store.retire(dead, f"{SCREENED}. {VERDICT_WORDS['drift']}.")
        self.store.bury(dead, "Calls held into a rising tape earned the drift and nothing else.")
        other = self.store.add_family({**family_spec(SEED), "id": "dead-stress"}, origin="seed")["id"]
        self.store.retire(other, f"{SCREENED}. {VERDICT_WORDS['stress']}.")
        self.store.bury(other, "It lost at the wider spread.")
        seed = self.store.add_family(family_spec(SEED), origin="seed")["id"]
        lessons = {r["family"]: r for r in self.researcher._local_tool(self.store.family(self.fid), "graveyard", {}, {})["lessons"]}
        self.assertIn("not binding for the direction lane", lessons[dead]["lane"])
        self.assertNotIn("lane", lessons[other])
        alpha = self.researcher._local_tool(self.store.family(seed), "graveyard", {}, {})["lessons"]
        self.assertFalse(any("lane" in r for r in alpha))


# ------------------------------------------------------------------------------------------------ the sweep
class CallsOnlyCode(Case):
    """THE CALLS-ONLY CODE CHECK (release D-1b, the review's finding 3; `dlane.calls_only_code`): a direction family's run
    or sweep whose program names a put, a short leg or any open but `long_call` is refused before any version, job or
    trial. An alpha family's, and every family's while the lane is off, runs as before."""

    def test_a_direction_run_or_sweep_naming_another_open_is_refused_before_any_version(self):
        store, researcher, env = self.make("gate")
        fid = store.add_family(DIRECTION_SPEC, origin="architect")["id"]
        condor = program_for(SEED)[0]
        for view in (self.gym_run(researcher, fid, {"vrp_min": 1.5}, code=condor),
                     researcher._gym_sweep(store.family(fid), {"code": condor,
                                                               "variants": [{"vrp_min": 1.3}, {"vrp_min": 1.5}]},
                                           {}, author="synthetic"),
                     self.gym_run(researcher, fid, {"vrp_min": 1.5}, code=CALLS_CODE.replace('"long_call"', '"long_put"'))):
            self.assertEqual(view["status"], "refused")
            self.assertTrue(view["reason"].startswith(dlane.CALLS_ONLY_CODE_WHY), view["reason"])
            self.assertIn("long_call only", view["hint"])
        self.assertEqual((store.versions(fid), env["pool"].jobs), ([], []), "no version, no job, no trial")
        self.assertEqual(self.gym_run(researcher, fid, {"vrp_min": 1.5})["status"], "ok", "a calls-only program runs")

    def test_an_alpha_family_and_the_rollback_run_as_before(self):
        store, researcher, env = self.make("gate")
        alpha = store.add_family(family_spec(SEED), origin="seed")["id"]
        self.assertEqual(self.gym_run(researcher, alpha, {"vrp_min": 1.5})["status"], "ok")
        store, researcher, env = self.make("off")
        fid = store.add_family(DIRECTION_SPEC, origin="architect")["id"]
        self.assertEqual(self.gym_run(researcher, fid, {"vrp_min": 1.5}, code=program_for(SEED)[0])["status"], "ok")


class Sweep(Case):
    def test_a_direction_sweep_is_sorted_by_s_d_with_the_lanes_cells(self):
        table = {1.1: ("steady", STEADY), 1.3: ("always", ALWAYS_IN),
                 1.5: ("milder", {"2022": (-400.0, -1.2, {}), "2023": (1900.0, 1.8, {}), "2024": (1700.0, 1.6, {})}),
                 1.7: ("one-year", {"2022": (0.0, 0.0, {"held": 10, "trades": 5, "days_traded": 5}),
                                    "2023": (0.0, 0.0, {"held": 10, "trades": 5, "days_traded": 5}),
                                    "2024": (2400.0, 1.9, {})})}
        store, researcher, env = self.make("gate", by_params(table))
        fid = store.add_family(DIRECTION_SPEC, origin="architect")["id"]
        out: dict = {}
        view = researcher._gym_sweep(store.family(fid), {"code": CALLS_CODE,
                                                         "variants": [{"vrp_min": v} for v in (1.1, 1.3, 1.5, 1.7)]},
                                     out, author="synthetic")
        s_d = {v: dlane.train_score(train(n, y), first_year=2022, settings={"dlane": GATE})["score"] for v, (n, y) in table.items()}
        rows = view["table"]
        eligible = [r for r in rows if r["eligible"]]
        self.assertEqual([r["params"]["vrp_min"] for r in eligible], sorted((1.1, 1.3, 1.5), key=lambda v: -s_d[v]),
                         "by S_D, not by the worst year")
        alpha = {v: evidence.train_score(train(n, y), first_year=2022)["score"] for v, (n, y) in table.items() if v != 1.7}
        self.assertEqual(max(alpha, key=alpha.get), 1.1, "the worst-year score's favourite is the steady program")
        self.assertEqual(eligible[-1]["params"]["vrp_min"], 1.1, "which S_D puts last of the eligible")
        self.assertFalse(rows[-1]["eligible"])
        self.assertEqual(rows[-1]["lane"]["fails"], ["E1"])
        cells = {r["params"]["vrp_min"]: r["lane"] for r in eligible}
        self.assertEqual((cells[1.3]["years_in"], cells[1.3]["verdict"], cells[1.3]["unit"]), ("3/3", "eligible", "unknown"))
        self.assertAlmostEqual(cells[1.3]["t_pool"], round(s_d[1.3], 2))
        self.assertEqual((cells[1.3]["worst_in_t"], cells[1.3]["out_t"]), (-3.9, None))
        self.assertEqual(view["lane"]["note"], dlane.ALWAYS_IN_NOTE)
        fam = store.family(fid)
        self.assertAlmostEqual(fam["best_train"], max(s_d[v] for v in (1.1, 1.3, 1.5)), places=6)
        self.assertEqual(sorted(fam["state"][dlane.STATE_KEY]["versions"]), ["1", "2", "3", "4"])
        self.assertTrue(all(dlane.STATE_KEY in store.run(r["run_id"])["summary"] for r in rows))
        self.assertIsNone(LEAK.search(json.dumps(view)))

    def test_lane_cells_read_a_compact_score_and_nothing_else(self):
        score = dlane.train_score(train("c", {**ALWAYS_IN, "2022": (-80.0, -0.6, {"held": 30, "trades": 12, "days_traded": 12})}),
                                  first_year=2022, settings={"dlane": GATE})
        full, compact = lane_cells(score), lane_cells(dlane.compact(score))
        self.assertEqual(full, compact, "a pruned row's cells are the same")
        self.assertEqual((full["years_in"], full["out_t"]), ("2/3", -0.6))
        self.assertIsNone(lane_cells(evidence.train_score(train("a", STEADY), first_year=2022)))
        self.assertIsNone(lane_cells(None))


if __name__ == "__main__":
    unittest.main()
