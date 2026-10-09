"""THE DIRECTION LANE wired into selection (release D-1, Oct 9, 2026; PLAN D4 to D7 and the operator's decisions 4 to 7 and
9): the learning game (a direction lineage sits it out, the legacy route with no hidden look; its looks are kept out of
the operator's R1(b) and R2), the gate's screen per lane (the alpha lane's S-B byte for byte, S-C for direction, D2 only
with a receipt pinned in the repository's policy; every look records its lane, screen and receipt), the leakage alarm
per lane, the gate and the incubator while the lane is in "shadow" or K5 holds it, the incubator's direction mark from
the lane's bar (the alpha mark unchanged; the House's reader accepting it only while the lane takes marks), and the
sigma writer release L-D's DM1 reads. With `dlane.mode` "off" (THE ROLLBACK) every path is the release before it's.

HARNESS 6.4 items 8 to 10, adapted to PLAN D4 (no hidden look for direction: no tier, CONFIRM or direction ladder to
test). Invented stores and results only: no figure here is from the operator's studies."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from league import stats
from league.swarm import bands, cards, dlane, evidence, game
from league.swarm import incubator as I
from league.swarm import settings as S
from league.swarm.gate import Gate, gate_contract, run_sha
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament
from league.tests import REAL_POLICY_PATH, game_golden
from league.tests.swarm_fakes import Clock, result
from league.tests.test_dlane import always_in
from league.tests.test_dlane import run as train_result
from league.tests.test_game import GameCase, seen_run
from league.tests.test_swarm_incubator import EVALUATOR, OBJECTIVE
from league.tests.test_swarm_incubator import Case as IncubatorCase
from league.tests.test_swarm_rounds import RoundCase

PASS = {"text": json.dumps({"verdict": "pass", "reasons": []})}
#: A holdout whose daily P&L alternates 12 and 0: p is tiny, its daily Sharpe about 1. With Validation's daily Sharpe at
#: 3, the alpha lane's line needs 1.5 (fails) and the direction lane's S-C 0.75 (passes).
HOLDOUT_DAILY = [12.0 if i % 2 else 0.0 for i in range(250)]
VALIDATION_SHARPE = 3.0
LANE_KEYS = ("lane", "screen", "receipt")


def lane_on(settings, **dl):
    """`settings` with the direction lane switched on ("gate" unless `mode` says otherwise)."""
    out = copy.deepcopy(settings)
    out["dlane"] = {"mode": "gate", **dl}
    return out


# ------------------------------------------------------------------------------------------------ D4: the game
class GameLane(GameCase):
    """HARNESS 6.4 item 8 adapted: a direction lineage sits the game out (decision 5, `dlane.arm_fraction` 0)."""

    def test_a_direction_lineage_sits_the_game_out_and_the_alpha_lane_still_plays(self):
        s = lane_on(self.settings)
        alpha = self.family("alpha-one")
        direction = self.family("dir-one", lane="direction")
        carded = self.family("dir-card")
        cards.put(self.store, carded["id"], {"lane": "direction", "mechanism_class": "equity_premium"}, "debit_vertical")
        self.assertEqual(game.arm(self.store, alpha, s), "game", "the alpha lane's game is unchanged")
        self.assertIsNone(game.arm(self.store, direction, s), "the legacy route: no hidden look")
        self.assertIsNone(game.arm(self.store, carded, s), "a lane read from the card")
        n = self.best("dir-one", 2.0)
        player = types.SimpleNamespace(store=self.store, settings=s, pool=self.pool, clock=self.clock)
        self.assertIsNone(game.maybe_look(player, "dir-one", n, seen_run()), "it does not play: no look is opened")
        self.assertEqual(game.recheck(self.store, s, self.pool), [])
        self.assertEqual([j for j in self.pool.jobs if j.family == "dir-one"], [], "no private job")
        child = self.family("dir-child", parent="dir-one", lane="direction")
        self.assertIsNone(game.arm(self.store, child, s))
        kept = {r["family"] for r in self.store._all("SELECT family FROM game_arms")}
        self.assertIn("alpha-one", kept)
        self.assertFalse(kept & {"dir-one", "dir-card", "dir-child"}, "nothing is kept for a lineage that sits out")
        visible = {f["id"] for f in game.visible_families(self.store, settings=s)}
        self.assertTrue({"dir-one", "dir-card", "dir-child"} <= visible, "legacy: the architect and strategist see it")
        self.assertNotIn("alpha-one", visible, "the game arm stays hidden")
        self.assertEqual(game.status_text(self.store, direction, s), "")
        self.assertIsNone(game.retire_rule(self.store, direction, s))
        self.assertFalse(Tournament(self.store, self.pool, s, clock=self.clock).played(direction), "today's rules")

    def test_a_non_zero_arm_fraction_admits_that_share_of_direction_lineages_to_the_games_own_split(self):
        c = game.cfg(self.settings)
        fams = [{"id": f"d-{i}", "lineage": f"d-{i}", "born_at": self.store.now(), "roots": ["SPY"],
                 "spec": {"lane": "direction"}} for i in range(4000)]
        for fraction in (0.0, 0.3, 1.0):
            s = lane_on(self.settings, arm_fraction=fraction)
            playing = [f for f in fams if game._arm_of(f, c, self.t0, sits_out=lambda f=f: game._sits_out(self.store, f, s, c))]
            self.assertAlmostEqual(len(playing) / len(fams), fraction, delta=0.03)
            self.assertTrue(all(game._arm_of(f, c, self.t0) in game.ARMS for f in playing[:20]))
        self.assertEqual(dlane.cfg(json.loads((Path(game_golden.__file__).parents[2] / "league" / "swarm" / "policy.json")
                                              .read_text())).get("arm_fraction"), 0.0, "decision 5: none plays")

    def test_a_kept_arm_is_kept(self):
        """A direction lineage given an arm while the lane was off (the rollback) keeps it: the game's comparison is never
        moved by a setting."""
        fam = self.family("dir-kept", lane="direction")
        self.assertEqual(game.arm(self.store, fam, lane_on(self.settings, mode="off")), "game")
        self.assertEqual(game.arm(self.store, fam, lane_on(self.settings)), "game")

    def test_the_rollback_every_game_path_reads_no_lane(self):
        """With `dlane.mode` "off" (or no block) a direction-declared family plays exactly as an alpha one: its arm, its
        look, its visibility and the metrics, the same as the same store with no lane written at all."""
        outs = []
        for lane in ("direction", None):
            with tempfile.TemporaryDirectory() as d:
                clock = Clock()
                store = SwarmStore(Path(d), clock=clock)
                try:
                    settings = lane_on(self.settings, mode="off") if lane else copy.deepcopy(self.settings)
                    game.t0(store, settings)
                    clock.advance(60)
                    spec = {"id": "fam-x", "mechanism": "Index calls after a low close rebound, a debit vertical.",
                            "structure": "debit_vertical", "roots": ["SPY"]}
                    if lane:
                        spec["lane"] = lane
                    fam = store.add_family(spec, origin="architect")
                    v = store.add_version("fam-x", "NEEDS = {'roots': ['SPY']}\nTAG = 1\n", {"k": 1}, author="test")
                    row = store.add_run("fam-x", v["n"], {"run_id": "r-x", "status": "ok", "trials": 1,
                                                          "summary": {"train_score": 2.0, "train_eligible": True,
                                                                      "train_from": game.SEEN_FROM}},
                                        window="train", stress=1.0, purpose="train")
                    store.update_family("fam-x", best_train=2.0)
                    store.set_state("fam-x", best_train_version=v["n"], best_train_run=row["run_id"])
                    pool = type(self.pool)()
                    player = types.SimpleNamespace(store=store, settings=settings, pool=pool, clock=clock)
                    look = game.maybe_look(player, "fam-x", v["n"], seen_run())
                    outs.append({"arm": game.arm(store, fam, settings), "look": look,
                                 "jobs": [(j.family, j.version, j.purpose) for j in pool.jobs],
                                 "visible": [f["id"] for f in game.visible_families(store, settings=settings)],
                                 "metrics": {k: v for k, v in game.metrics(store, settings=settings, draws=0).items()
                                             if k != "at"}})
                finally:
                    store.close()
        self.assertEqual(outs[0], outs[1])
        self.assertEqual(outs[0]["arm"], "game")
        self.assertNotIn("dlane", outs[0]["metrics"])

    def test_direction_looks_are_kept_out_of_r1b_and_r2(self):
        """HARNESS 6.4 item 8's R1(b) and R2: a direction look (a kept arm, or a non-zero `arm_fraction`) is no draw of D1
        and no pair of the selection carry; the metrics say the birth quota's and the role text's costs."""
        s = lane_on(self.settings)
        rng = random.Random(9)
        alphas = [self.family(f"met-a-{i}") for i in range(8)]
        directions = [self.family(f"met-d-{i}", lane="direction") for i in range(4)]
        for fam in alphas + directions:
            for _ in range(2):
                f = rng.uniform(-1, 3)
                self.plant(fam, f, 0.5 * f + rng.uniform(-0.5, 0.5), side="game")
        self.store.event("swarm.born", "met-d-0", {"family": "met-d-0", "lane": "direction"})
        self.store.event("swarm.born", "met-a-0", {"family": "met-a-0"})
        on = game.metrics(self.store, settings=s, draws=0)
        off = game.metrics(self.store, settings=self.settings, draws=0)
        self.assertEqual(off["R1"]["d1_founders"]["n"], 24, "the rollback counts every look")
        self.assertEqual(on["R1"]["d1_founders"]["n"], 16, "only the alpha lane's founders")
        self.assertEqual(on["R2"]["n"], 16)
        self.assertEqual(off["R2"]["n"], 24)
        self.assertEqual(on["dlane"]["excluded_from"], ["R1.d1_founders", "R2"])
        self.assertEqual((on["dlane"]["excluded_families"], on["dlane"]["excluded_looks"]), (4, 8))
        self.assertEqual(on["dlane"]["births_24h"], {"alpha": 1, "direction": 1}, "a born payload without a lane is alpha")
        text = " ".join(on["dlane"]["notes"])
        self.assertIn("about 73 to about 36 a day", text, "decision 1: the quota's cost")
        self.assertIn("code paths only", text, "decision 1: the shared prompt changed")
        self.assertNotIn("dlane", off)
        both = [game._operator_years(r) for r in game._rows(self.store, operator=True)
                if r["status"] == "ok" and r["family"].startswith("met-a-")]
        self.assertAlmostEqual(on["R2"]["rho_hidden"], game.spearman([x for x, _ in both], [y for _, y in both]), places=12)

    def test_the_alpha_lanes_round_is_mains_byte_for_byte(self):
        """The game's golden round (control and legacy families) with the lane switched off, and switched on: the alpha
        lane's round is unchanged; the one addition while the lane is on is the sigma writer's keys (decision 4)."""
        golden = json.loads(game_golden.GOLDEN.read_text(encoding="utf-8"))
        base = game_golden.settings

        def strip(snap):
            for fam in snap["families"]:
                for key in ("validation_r_sd", "validation_r_sd_by_version"):
                    (fam.get("state") or {}).pop(key, None)
            return snap

        for mode in ("off", "shadow", "gate"):
            with self.subTest(mode), tempfile.TemporaryDirectory() as d, \
                    mock.patch.object(game_golden, "settings", lambda g=None, m=mode: {**base(g), "dlane": {"mode": m}}):
                snap = json.loads(json.dumps(game_golden.play(d, {"enabled": True, "mode": "gate", "arm_fraction": 0.5}),
                                             default=str))
                if mode == "off":
                    self.assertEqual(snap, golden)
                else:
                    sd = [f["id"] for f in snap["families"] if "validation_r_sd_by_version" in (f.get("state") or {})]
                    self.assertTrue(sd, "the sigma writer wrote beside typical_max_loss_usd")
                    self.assertEqual(strip(snap), golden)


# ------------------------------------------------------------------------------------------------ D6, D7: the gate
class GateLane(RoundCase):
    """HARNESS 6.4's screen and alarm items for the gate (PLAN D6, D7; decisions 6, 7, 9)."""

    def setUp(self):
        super().setUp()
        self.settings["dlane"] = {"mode": "gate"}
        self.answer = self.holdout_answer

    @staticmethod
    def holdout_answer(job):
        if job.window == "holdout":
            return result(job.name, daily=HOLDOUT_DAILY, window="holdout")
        return result(job.name, window=job.window, sharpe_daily=VALIDATION_SHARPE)

    def ready(self, *fids, lane=None):
        for fid in fids:
            self.family(fid, **({"lane": lane} if lane else {}))
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        for fid in fids:
            self.assertTrue(self.store.family(fid)["state"]["gate_ready"], fid)

    def gate(self):
        return Gate(self.store, self.pool, self.router, self.settings)

    def looks(self):
        return {x["family"]: x for x in self.store.looks()}

    def events(self, action):
        return [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.gate" and e["payload"].get("action") == action]

    def test_sc_is_the_direction_lanes_screen_and_the_alpha_look_is_s_b_byte_for_byte(self):
        self.ready("a")
        self.ready("d", lane="direction")
        self.replies = [PASS] * 4
        out = self.gate().run()
        self.assertEqual(sorted((x["family"], x["passed"]) for x in out["looked"]), [("a", False), ("d", True)],
                         "the same holdout: half Validation's Sharpe fails, a quarter passes")
        looks = self.looks()
        a, d = looks["a"]["detail"], looks["d"]["detail"]
        self.assertEqual({k: a[k] for k in LANE_KEYS}, {"lane": "alpha", "screen": "S-B", "receipt": None})
        self.assertEqual({k: d[k] for k in LANE_KEYS}, {"lane": "direction", "screen": "S-C", "receipt": None})
        self.assertEqual((d["numbers"]["level"], d["numbers"]["sharpe_share"]), (0.2, 0.25))
        self.assertFalse(a["checks"]["sharpe"])
        self.assertNotIn("sharpe_share", a["numbers"], "the alpha line's numbers are the release before it's")
        # The alpha look is the evidence line of the release before D-1, byte for byte, beside its three record keys.
        holdout = self.holdout_answer(types.SimpleNamespace(window="holdout", name="a"))
        sha = run_sha(self.store.version("a", 1))
        before = evidence.holdout_line(holdout, validation_sharpe=VALIDATION_SHARPE, previous_ps=[], seed=sha)
        self.assertEqual({k: v for k, v in a.items() if k not in LANE_KEYS}, json.loads(json.dumps(before)))
        self.assertAlmostEqual(stats.sharpe(HOLDOUT_DAILY), 1.0, delta=0.01)
        events = {e["version"]: e for e in self.events("look")}
        recorded = [{k: e[k] for k in LANE_KEYS} for e in self.events("look")]
        self.assertIn({"lane": "direction", "screen": "S-C", "receipt": None}, recorded, "each look event records them")
        self.assertTrue(events)
        self.assertEqual(self.store.family("d")["band"], "candidate")
        self.assertEqual(self.store.family("a")["band"], "gym")

    def test_the_rollback_judges_every_look_by_the_alpha_line_and_records_nothing_new(self):
        self.settings["dlane"] = {"mode": "off"}
        self.ready("a")
        self.ready("d", lane="direction")
        self.replies = [PASS] * 4
        out = self.gate().run()
        self.assertEqual(sorted((x["family"], x["passed"]) for x in out["looked"]), [("a", False), ("d", False)])
        for look in self.store.looks():
            self.assertFalse(set(LANE_KEYS) & set(look["detail"]))
        for e in self.events("look"):
            self.assertFalse(set(LANE_KEYS) & set(e))

    def test_shadow_and_k5_hold_a_direction_look_before_anything_is_paid(self):
        self.settings["dlane"] = {"mode": "shadow"}
        self.ready("d", lane="direction")
        out = self.gate().run()
        self.assertEqual((out["looked"], out["waiting"]), ([], ["d"]))
        self.assertEqual(self.sail.bodies, [], "no review is paid")
        state = self.store.family("d")["state"]
        self.assertTrue(state["gate_ready"], "its place is kept")
        self.assertIn("shadow", state["gate"])
        self.assertFalse(any(ch.isdigit() for ch in state["gate"]), "no figure")
        # K5 holds a "gate" lane in shadow until the operator clears it.
        self.settings["dlane"] = {"mode": "gate"}
        self.store.put(dlane.K5_KEY, {"at": "x", "net": -612.0})
        self.assertEqual(self.gate().run()["waiting"], ["d"])
        self.assertEqual(self.sail.bodies, [])
        self.settings["dlane"] = {"mode": "gate", "k5_clear": True}
        self.replies = [PASS] * 2
        self.assertEqual(self.gate().run()["looked"], [{"family": "d", "passed": True}])

    def test_a_direction_look_that_lands_in_shadow_makes_no_candidate(self):
        self.ready("d", lane="direction")
        fam, version = self.store.family("d"), self.store.version("d", 1)
        sha = run_sha(version)
        self.store.put(dlane.K5_KEY, {"at": "x", "net": -700.0})
        holdout = self.holdout_answer(types.SimpleNamespace(window="holdout", name="d"))
        passed = self.gate().finish("d", version, sha, holdout, validation_sharpe=VALIDATION_SHARPE)
        self.assertTrue(passed, "judged and recorded")
        self.assertEqual(self.store.family("d")["band"], "gym", "no Candidate while K5 holds")
        self.assertEqual(len(self.events("candidate_withheld")), 1)
        self.assertEqual(fam["band"], "gym")

    def test_d2_is_refused_without_a_pinned_receipt_and_judges_by_its_pooled_test_with_one(self):
        """D2 behind `dlane.screen` "D2": refused (S-C, the coded Validation line) unless the repository's policy pins a
        receipt and its `c`; with one, a direction version that missed the line but passes the pre-check reaches the gate
        WITHOUT opening tuition, and its look is judged by the pooled test and records the receipt."""
        self.settings["dlane"] = {"mode": "gate", "screen": "D2"}
        weak = lambda job: (result(job.name, window=job.window, t=0.5, mean=0.01, quarters="1/4")  # noqa: E731
                            if job.window == "validation" else result(job.name, daily=HOLDOUT_DAILY, window=job.window))
        self.answer = weak
        self.family("d", lane="direction")
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        state = self.store.family("d")["state"]
        self.assertFalse(state["validation_line"]["passed"])
        self.assertFalse(state["gate_ready"], "no receipt pinned: D2 refused, the line as coded")
        sha = hashlib.sha256(b"an invented receipt").hexdigest()
        pinned = ({"dlane": {"screens": {"D2": {"receipt_sha256": sha, "c": 1.0}}}}, {"state": "ok"})
        with mock.patch.object(S, "read_policy", lambda path=None: copy.deepcopy(pinned)):
            fam = self.store.family("d")
            Tournament(self.store, self.pool, self.settings).judge("d", 1, weak(types.SimpleNamespace(
                window="validation", name="d")), record=True)
            state = self.store.family("d")["state"]
            self.assertTrue(state["gate_ready"], "the pre-check opens the gate")
            self.assertFalse(state["validation_line"]["passed"], "the line is left as judged: no tuition")
            self.assertEqual([r["family"] for r in bands.read(self.root) if r["family"] == "d"], [])
            self.replies = [PASS] * 2
            out = self.gate().run()
        self.assertEqual(out["looked"], [{"family": "d", "passed": True}])
        detail = self.looks()["d"]["detail"]
        self.assertEqual({k: detail[k] for k in LANE_KEYS}, {"lane": "direction", "screen": "D2", "receipt": sha})
        self.assertEqual(detail["numbers"]["rule"], "D2")
        self.assertEqual(set(detail["checks"]), {"status_ok", "pnl", "pooled"})
        self.assertGreaterEqual(detail["numbers"]["pooled_t"], 1.0)
        self.assertEqual((fam["band"], self.store.family("d")["band"]), ("gym", "candidate"))
        # Pinned while the operator later moves the screen back to S-C: a pre-check entry waits for the coded line.
        self.store.set_state("d", gate_ready=True, gated_sha=None)
        self.settings["dlane"] = {"mode": "gate"}
        self.assertIn("pre-check", self.gate().lane_closed(self.store.family("d"), self.store.family("d")["state"]))

    def test_the_leakage_alarm_counts_each_lane_alone(self):
        self.ready("a")
        self.ready("d", lane="direction")
        for i in range(10):  # ten direction looks, seven passed: over 60%
            self.store.add_look("old-d", 1, f"dsha{i}", passed=i < 7, p_value=0.01, detail={"lane": "direction"})
        self.replies = [PASS] * 4
        out = self.gate().run()
        self.assertEqual(out["alarm_lanes"], ["direction"])
        self.assertEqual([x["family"] for x in out["looked"]], ["a"], "the alpha lane's looks go on")
        self.assertEqual(out["alarm_held"], ["d"])
        self.assertTrue(self.store.family("d")["state"]["gate_ready"])
        self.assertIsNone(self.store.get("leakage_alarm"), "the alpha lane's alarm does not hold")
        self.assertEqual(self.store.get("leakage_alarm_direction")["lane"], "direction")
        [event] = self.events("leakage_alarm")
        self.assertEqual((event["lane"], event["looks"], event["passes"]), ("direction", 10, 7))

    def test_sixty_percent_is_no_direction_alarm_and_the_rollback_counts_the_alpha_lines_looks_as_before(self):
        self.ready("d", lane="direction")
        for i in range(10):
            self.store.add_look("old-d", 1, f"dsha{i}", passed=i < 6, p_value=0.01, detail={"lane": "direction"})
        self.assertEqual(self.gate().alarms(), {"alpha": False, "direction": False})
        self.settings["dlane"] = {"mode": "off"}
        # THE ROLLBACK (the review of Oct 9): the direction lane's looks were judged on S-C, so they are left out of the
        # one count; 6 of its 10 passing must not stop the alpha lane.
        self.assertEqual(self.gate().alarms(), {"alpha": False, "direction": False}, "no look the alpha line judged")
        for i in range(10):  # ten looks the alpha line judged (no lane recorded), four passed: the one count, as before
            self.store.add_look("old-a", 1, f"asha{i}", passed=i < 4, p_value=0.01, detail={})
        self.assertEqual(self.gate().alarms(), {"alpha": True, "direction": True}, "one count: 4 of the alpha line's 10")
        out = self.gate().run()
        self.assertTrue(out["alarm"])
        self.assertEqual(self.store.get("leakage_alarm")["looks"], 10)
        self.assertNotIn("lane", self.store.get("leakage_alarm"))
        [event] = self.events("leakage_alarm")
        self.assertEqual((event["looks"], event["passes"]), (10, 4), "the alpha line's looks, not the direction lane's")

    def test_the_alpha_lanes_alarm_is_unchanged_over_its_own_looks(self):
        self.ready("d", lane="direction")
        for i in range(10):  # ten alpha looks (made before D-1: no lane recorded), four passed: over 30%
            self.store.add_look("old-a", 1, f"asha{i}", passed=i < 4, p_value=0.01, detail={})
        for i in range(5):
            self.store.add_look("old-d", 1, f"dsha{i}", passed=False, p_value=0.5, detail={"lane": "direction"})
        self.assertEqual(self.gate().alarms(), {"alpha": True, "direction": False})
        self.assertEqual(evidence.leakage_alarms(self.store.looks(), {}), {"alpha": True, "direction": True},
                         "the rollback: the one count over the alpha line's looks (4 of 10), the direction looks left out")
        self.replies = [PASS] * 2
        out = self.gate().run()
        self.assertEqual(out["alarm_lanes"], ["alpha"])
        self.assertEqual(out["looked"], [{"family": "d", "passed": True}])
        self.assertEqual(self.store.get("leakage_alarm")["lane"], "alpha")

    def test_the_incubator_reads_no_family_of_a_stopped_or_shadowed_lane(self):
        self.family("a")
        self.family("d", lane="direction")
        due = [{"family": "a", "version": 1, "sha": "sha-a"}, {"family": "d", "version": 1, "sha": "sha-d"}]
        read = []
        with mock.patch.object(I, "due_reviews", lambda *a, **k: list(due)), \
                mock.patch.object(Gate, "_incubator_review", lambda gate, fid, n, sha: read.append(fid) or "pass"):
            self.gate().incubator_reviews()
            self.assertEqual(read, ["a", "d"])
            read.clear()
            self.gate().incubator_reviews(stopped=frozenset({"direction"}))
            self.assertEqual(read, ["a"], "the direction lane's alarm stops its reads")
            read.clear()
            self.gate().incubator_reviews(stopped=frozenset({"alpha"}))
            self.assertEqual(read, ["d"])
            read.clear()
            self.settings["dlane"] = {"mode": "shadow"}
            self.gate().incubator_reviews()
            self.assertEqual(read, ["a"], "no direction read in shadow")
            read.clear()
            self.settings["dlane"] = {"mode": "off"}
            self.gate().incubator_reviews(stopped=frozenset())
            self.assertEqual(read, ["a", "d"], "the rollback: every family is alpha")


# ------------------------------------------------------------------------------------------------ decision 4: the sigma
class SigmaWriter(RoundCase):
    def test_the_validation_sd_is_kept_beside_typical_max_loss_for_ld(self):
        """Decision 4 (release L-D's DM1 reads it in league/live/families.py `validation_r_sd`): the sd of per-trade P&L
        per dollar of maximum loss of the Validation run, `validation_r_sd_by_version[str(n)]` and `validation_r_sd`
        (validation_version's), finite and above zero, else omitted; nothing while the lane is off."""
        self.family("a")
        tour = Tournament(self.store, self.pool, self.settings)
        tour.validate(self.store.families(alive=True))
        state = self.store.family("a")["state"]
        self.assertIn("typical_max_loss_usd", state)
        self.assertFalse({"validation_r_sd", "validation_r_sd_by_version"} & set(state), "the rollback writes nothing")
        self.settings["dlane"] = {"mode": "gate"}
        tour = Tournament(self.store, self.pool, self.settings)
        tour.judge("a", 1, self.answer(types.SimpleNamespace(window="validation", name="a", family="a", stress=1.0)),
                   record=True)
        state = self.store.family("a")["state"]
        summary = self.store.version_runs("a", 1, window="validation", stress=1.0, limit=1)[0]["summary"]
        want = abs(summary["mean_return_on_max_loss"]) * math.sqrt(summary["trades"]) / abs(summary["t_stat"])
        self.assertAlmostEqual(state["validation_r_sd"], want, places=5)
        self.assertEqual(state["validation_r_sd_by_version"], {"1": state["validation_r_sd"]})

        def ld_reader(st, version):  # league/live/families.py `validation_r_sd` on release L-D, its two keys' shape
            by = st.get("validation_r_sd_by_version") or {}
            return by.get(str(version), st.get("validation_r_sd") if st.get("validation_version") == version else None)

        self.assertEqual(ld_reader(state, 1), state["validation_r_sd"])
        # A newer version whose figure is not finite and above zero: omitted, and the banded version's kept.
        v2 = self.store.add_version("a", "# a v2\nNEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n", {},
                                    author="seed")
        self.store.update_family("a", best_version=v2["n"])
        bad = result("a-v2", window="validation", t=-1.0)
        self.assertIsNone(dlane.validation_r_sd(bad["summary"]))
        tour.judge("a", v2["n"], bad, record=True)
        state = self.store.family("a")["state"]
        self.assertEqual(state["validation_version"], v2["n"])
        self.assertIsNone(state["validation_r_sd"], "an older version's scalar is never read as the new one's")
        self.assertNotIn(str(v2["n"]), state["validation_r_sd_by_version"])
        self.assertIsNone(ld_reader(state, v2["n"]))
        self.assertAlmostEqual(ld_reader(state, 1), want, places=5, msg="the banded version's figure survives")


# ------------------------------------------------------------------------------------------------ D5: the incubator mark
class DirectionMark(IncubatorCase):
    """HARNESS 6.4 item 9: the direction mark from the lane verdict; the alpha mark unchanged; `bands.incubator` accepts
    the mark (its belt unchanged) only while the lane takes marks."""

    def setUp(self):
        super().setUp()
        self.on = lane_on(self.settings)

    def direction(self, fid, *, train=None, robust_pnl=40.0, r15=None):
        self.store.add_family({"id": fid, "mechanism": "Index calls held while implied vol is calm against its year.",
                               "structure": "long_single", "roots": ["SPY"], "lane": "direction"}, origin="test")
        v = self.store.add_version(fid, f"# {fid}\nNEEDS = {{'roots': ['SPY']}}\nPARAMS = {{}}\ndef decide(ctx):\n    return []\n",
                                   {}, author="test")
        n = int(v["n"])
        r = copy.deepcopy(train if train is not None else always_in())
        r.update(run_id=f"{fid}-train", gym_image=EVALUATOR["image"], gym_bundle=EVALUATOR["bundle"])
        r["summary"] = {**r["summary"], "train_eligible": True}
        self.store.add_run(fid, n, r, window="train", stress=1.0, purpose="train")
        r15 = copy.deepcopy(r15 if r15 is not None else train_result(
            {"2022": (-1800.0, -4.2, {}), "2023": (2100.0, 1.4, {}), "2024": (1900.0, 1.3, {})}))
        r15.update(run_id=f"{fid}-r15", gym_image=EVALUATOR["image"], gym_bundle=EVALUATOR["bundle"])
        self.store.add_run(fid, n, r15, window="train", stress=1.5, purpose="robustness")
        self.robust(fid, n, pnl=robust_pnl)
        return n

    def mark(self, fid, n, settings=None):
        return I.mark_of(self.store, self.store.family(fid), n, self.on if settings is None else settings,
                         evaluator=EVALUATOR, objective=OBJECTIVE, clock=self.clock)

    def test_the_direction_mark_is_the_lanes_bar_not_the_drift_screen_alone(self):
        n = self.direction("d")
        mark, why, drop = self.mark("d", n)
        self.assertIsNotNone(mark, why)
        self.assertEqual((mark["lane"], mark["bar"], mark["objective"]), ("direction", dlane.OBJECTIVE, OBJECTIVE))
        self.assertEqual((mark["evaluator"], mark["robust_pnl"]), (EVALUATOR, 40.0))
        self.assertIsInstance(mark["drift"], dict)
        self.assertTrue(mark["drift"]["reported"])
        self.assertEqual(mark["direction"]["unit"]["verdict"], "unknown", "no closes or equity here: E5 unknown passes")
        self.assertEqual(sorted(mark["direction"]["active"]), ["2022", "2023", "2024"])
        # Under the rollback the same family is alpha's: the drift screen alone, which an always-in program fails.
        alpha, why, drop = self.mark("d", n, self.settings)
        self.assertIsNone(alpha)
        self.assertIn("drift screen", why)

    def test_a_known_bar_failure_drops_figures_owed_never_do_and_shadow_marks_nothing(self):
        short = self.direction("short", train=always_in(**{"2023": (2600.0, 2.1, {"days_traded": 59})}))
        mark, why, drop = self.mark("short", short)
        self.assertEqual((mark, drop), (None, True))
        self.assertIn("fails E4", why)
        weak = self.direction("weak15", r15=train_result({"2022": (-1800.0, -4.2, {}), "2023": (1000.0, 1.4, {}),
                                                          "2024": (900.0, 1.3, {})}))
        mark, why, drop = self.mark("weak15", weak)
        self.assertEqual((mark, drop), (None, True))
        self.assertIn("R3", why)
        pruned = self.direction("pruned")
        self.store._exec("UPDATE runs SET path=NULL WHERE family='pruned'")
        mark, why, drop = self.mark("pruned", pruned)
        self.assertEqual((mark, drop), (None, False))
        self.assertIn("owed", why)
        good = self.direction("good")
        for mode in ({"mode": "shadow"}, {"mode": "gate", "k5": True}):
            with self.subTest(**mode):
                if mode.get("k5"):
                    self.store.put(dlane.K5_KEY, {"at": "x", "net": -650.0})
                mark, why, drop = self.mark("good", good, lane_on(self.settings, mode=mode["mode"]))
                self.assertEqual((mark, drop), (None, False), "a mark already made stays")
                self.assertIn("shadow", why)

    def test_the_alpha_mark_is_unchanged_with_the_lane_on(self):
        n = self.eligible("a")
        on = self.mark("a", n)
        off = self.mark("a", n, self.settings)
        self.assertEqual(on, off)
        self.assertNotIn("lane", on[0])

    def test_owed_runs_never_read_the_drift_screen_for_a_direction_version(self):
        n = self.direction("d")
        self.store._exec("DELETE FROM runs WHERE family='d' AND stress=1.5")
        state = dict(self.state("d"))
        state.pop("robustness", None)
        self.store.set_state("d", robustness={})
        self.cohort("d", n)
        owed = I.owed_runs(self.store, self.on, self.root, clock=self.clock)
        self.assertEqual([(r["family"], r["next"]) for r in owed], [("d", "stress_1.5")],
                         "its 1.5x run is asked for although the drift screen (not its bar) fails")
        self.assertEqual(I.owed_runs(self.store, self.settings, self.root, clock=self.clock), [],
                         "the rollback: the drift screen's verdict, as before")

    def test_the_houses_reader_accepts_a_direction_mark_only_while_the_lane_takes_marks(self):
        n = self.direction("d")
        self.cohort("d", n)
        self.practised("d", n, [("2026-10-01", 3.0, False)] * 5)
        out = I.facts(self.store, self.on, self.root, clock=self.clock)
        self.assertEqual(out["written"], ["d@1"])
        sha = run_sha(self.store.version("d", n))
        contract = gate_contract()["sha256"]
        self.store.set_state("d", review={"sha": sha, "verdict": "pass", "contract_sha": contract,
                                          "audit": {"verdict": "pass", "contract_sha": contract}})
        self.assertEqual(bands.incubator(self.root, family="d", version=n), [], "the tests' empty policy: the lane off")
        with mock.patch.object(S, "POLICY_PATH", REAL_POLICY_PATH):  # the committed policy.json runs the lane in "gate"
            self.assertEqual([r["family"] for r in bands.incubator(self.root, family="d", version=n)], ["d"])
            swarm_json = self.root / "swarm.json"
            for local, accepted in (({"dlane": {"mode": "shadow"}}, False), ({"dlane": {"mode": "off"}}, False),
                                    ({}, True)):
                swarm_json.write_text(json.dumps(local))
                self.assertEqual(bool(bands.incubator(self.root, family="d", version=n)), accepted, local)
            self.store.put(dlane.K5_KEY, {"at": "x", "net": -601.0})
            self.assertEqual(bands.incubator(self.root, family="d", version=n), [], "K5 refuses direction marks")
            swarm_json.write_text(json.dumps({"dlane": {"k5_clear": True}}))
            self.assertTrue(bands.incubator(self.root, family="d", version=n), "only the operator clears it")
            swarm_json.write_text("{not json")
            self.assertEqual(bands.incubator(self.root, family="d", version=n), [],
                             "an unreadable swarm.json is no layer (as the swarm reads it): the policy's gate, K5 holds")
        alpha = self.eligible("a")
        self.practised("a", alpha, [("2026-10-01", 3.0, False)] * 5)
        I.facts(self.store, self.on, self.root, clock=self.clock)
        sha = run_sha(self.store.version("a", alpha))
        self.store.set_state("a", review={"sha": sha, "verdict": "pass", "contract_sha": contract,
                                          "audit": {"verdict": "pass", "contract_sha": contract}})
        self.assertEqual([r["family"] for r in bands.incubator(self.root, family="a", version=alpha)], ["a"],
                         "an alpha mark reads no lane setting: K5 and an unreadable swarm.json leave it as it was")


if __name__ == "__main__":
    unittest.main()
