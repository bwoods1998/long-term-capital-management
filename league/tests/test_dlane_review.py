"""THE REVIEW OF RELEASE D-1 (Oct 9, 2026): one test class a finding the fixer kept, each failing on the integrated tree
before its fix (`bc576589`) and passing after it.

1. The rollback's leakage alarm (`evidence.leakage_alarms` with `dlane.mode` "off") counts the looks the alpha lane's
   line judged, never a direction look judged on S-C: correlated direction passes must not stop the alpha lane.
2. A direction family never takes its LINEAGE's kept game arm (`game._arm_of` asks `_sits_out` first): born into a
   game-arm or control-arm lineage, or left in a direction lineage an alpha family was later given an arm in, it is legacy.
3. and 7. K5's clear is durable and honest: the `dlane` job records the operator's clear (`dlane.k5_rearm`) and re-arms
   K5 at -$600 below the net at clearing; `k5_clear` true disarms K5 while it stays (a loosening, reported every run).
4. The direction quota's reservation never exceeds the room left under the architect's class cap, and a direction card
   the class cap refused is named apart from card errors.
5. No agent-facing text (a view, a status line, a score's `why`, a sweep row, a run row's summary, the architect's
   request) carries a figure priced at today's closes or the account's equity: E5 is its verdict alone.
6. The brief states the vertical guidance as a lane rule, with no Train provenance it does not have.

Every family, figure and date here is invented."""

from __future__ import annotations

import copy
import json
import tempfile
import types
import unittest
from pathlib import Path

from league.ops import dlane_report as R
from league.swarm import dlane, evidence, game
from league.swarm.architect import LANE_LAST_KEY, Architect
from league.swarm.gate import Gate
from league.swarm.researcher import lane_cells
from league.swarm.tournament import Tournament
from league.tests.test_dlane import always_in
from league.tests.test_dlane import run as train_run
from league.tests.test_dlane_births import DIR, DMECH, LaneCase
from league.tests.swarm_fakes import result
from league.tests.test_dlane_report import Fixture as ReportFixture
from league.tests.test_game import GameCase
from league.tests.test_swarm_cards import proposal
from league.tests.test_swarm_dlane_selection import HOLDOUT_DAILY, PASS, VALIDATION_SHARPE
from league.tests.test_swarm_rounds import RoundCase

# The fixtures are imported as bases with no test of their own, so discovery runs nothing twice here.

GATE = {"dlane": {"mode": "gate"}}


def lane(settings, **block):
    out = copy.deepcopy(settings)
    out["dlane"] = {"mode": "gate", **block}
    return out


# ------------------------------------------------------------------------------------------------ 1. the rollback's alarm
class RollbackAlarm(RoundCase):
    """Finding 1: with the lane off, the one alarm counts the alpha line's looks only."""

    def setUp(self):
        super().setUp()
        self.settings["dlane"] = {"mode": "gate"}
        self.answer = self.holdout_answer

    @staticmethod
    def holdout_answer(job):
        if job.window == "holdout":
            return result(job.name, daily=HOLDOUT_DAILY, window="holdout")
        return result(job.name, window=job.window, sharpe_daily=VALIDATION_SHARPE)

    def ready(self, *fids):
        for fid in fids:
            self.family(fid)
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        for fid in fids:
            self.assertTrue(self.store.family(fid)["state"]["gate_ready"], fid)

    def gate(self):
        return Gate(self.store, self.pool, self.router, self.settings)

    def events(self, action):
        return [e["payload"] for e in self.store.events_after(0)
                if e["kind"] == "swarm.gate" and e["payload"].get("action") == action]

    def test_correlated_direction_passes_do_not_stop_the_alpha_lane_after_the_rollback(self):
        for i in range(5):  # production today: five alpha looks, none passed
            self.store.add_look("old-a", 1, f"asha{i}", passed=False, p_value=0.6, detail={})
        for i in range(5):  # the lane in gate made five direction looks, four passed (a rising market)
            self.store.add_look("old-d", 1, f"dsha{i}", passed=i < 4, p_value=0.05,
                                detail={"lane": "direction", "screen": "S-C", "receipt": None})
        looks = self.store.looks()
        self.assertEqual(evidence.leakage_alarms(looks, GATE), {"alpha": False, "direction": False})
        off = {"dlane": {"mode": "off"}}
        self.assertEqual(evidence.leakage_alarms(looks, off), {"alpha": False, "direction": False},
                         "the rollback: 0 of the alpha line's 5 looks passed")
        self.settings["dlane"] = {"mode": "off"}
        self.ready("a")
        self.replies = [PASS] * 2
        out = self.gate().run()
        self.assertNotIn("alarm", out, "the gate runs: the alpha family is reviewed and looked at")
        self.assertEqual([x["family"] for x in out["looked"]], ["a"])
        self.assertIsNone(self.store.get("leakage_alarm"), "no permanent kv is left behind")
        self.assertEqual([e for e in self.events("leakage_alarm")], [])

    def test_a_store_with_no_direction_look_reads_exactly_as_the_release_before(self):
        import random

        rng = random.Random(9)
        off = {"dlane": {"mode": "off"}}
        for _ in range(300):
            rows = [{"passed": rng.random() < 0.35, "detail": rng.choice([{}, {"lane": "alpha"}, None])}
                    for _ in range(rng.randint(0, 25))]
            before = evidence.leakage_alarm(len(rows), sum(1 for x in rows if x["passed"]))  # ccfa48d5's count
            self.assertEqual(evidence.leakage_alarms(rows, off), {"alpha": before, "direction": before})
            self.assertEqual(evidence.leakage_alarms(rows, None), {"alpha": before, "direction": before})


# ------------------------------------------------------------------------------------------------ 2. the game's arms
class DirectionInAnArmedLineage(GameCase):
    """Finding 2: decision 5 holds whatever lineage a direction family is born into."""

    def test_a_direction_family_born_into_a_game_arm_lineage_sits_the_game_out(self):
        s = lane(self.settings)
        alpha = self.family("alpha-0")
        self.assertEqual(game.arm(self.store, alpha, s), "game")
        child = self.family("dir-new", parent="alpha-0", lane="direction")
        self.assertEqual(child["lineage"], alpha["lineage"], "it joined the game-arm lineage")
        self.assertIsNone(game.arm(self.store, child, s))
        self.assertFalse(Tournament(self.store, self.pool, s, clock=self.clock).played(child))
        kept = {r["family"] for r in self.store._all("SELECT family FROM game_arms")}
        self.assertNotIn("dir-new", kept, "nothing is kept for it")
        n = self.best("dir-new", 2.0)
        player = types.SimpleNamespace(store=self.store, settings=s, pool=self.pool, clock=self.clock)
        self.assertIsNone(game.maybe_look(player, "dir-new", n, game_seen_run()), "no hidden look is opened")
        self.assertEqual([j for j in self.pool.jobs if j.family == "dir-new"], [])
        self.assertEqual(game.arm(self.store, alpha, s), "game", "the lineage's alpha member still plays")

    def test_a_direction_family_born_into_a_control_lineage_runs_no_control_look(self):
        s = lane(self.settings)
        s["game"]["arm_fraction"] = 0.0  # every alpha lineage in control
        alpha = self.family("alpha-c")
        self.assertEqual(game.arm(self.store, alpha, s), "control")
        child = self.family("dir-c", parent="alpha-c", lane="direction")
        self.assertIsNone(game.arm(self.store, child, s))

    def test_an_alpha_family_given_an_arm_in_a_direction_lineage_moves_no_direction_member(self):
        s = lane(self.settings)
        direction = self.family("dir-root", lane="direction")
        self.assertIsNone(game.arm(self.store, direction, s))
        alpha = self.family("alpha-in", parent="dir-root")
        self.assertEqual(game.arm(self.store, alpha, s), "game", "the alpha member takes the lineage's arm")
        self.assertIsNone(game.arm(self.store, direction, s), "the direction member stays legacy")
        self.assertFalse(Tournament(self.store, self.pool, s, clock=self.clock).played(direction))
        hidden = game._hidden(self.store, s)[1]
        self.assertIn("alpha-in", hidden)
        self.assertNotIn("dir-root", hidden)

    def test_the_rollback_reads_the_lineages_arm_as_before(self):
        self.family("alpha-0")
        self.assertEqual(game.arm(self.store, self.store.family("alpha-0"), lane(self.settings, mode="off")), "game")
        child = self.family("dir-off", parent="alpha-0", lane="direction")
        self.assertEqual(game.arm(self.store, child, lane(self.settings, mode="off")), "game", "no lane is read")


def game_seen_run():
    from league.tests.test_game import seen_run

    return seen_run()


class ArchitectParentInAnArmedLineage(LaneCase):
    """Finding 2 through the architect: a direction card whose declared parent is a control-arm family (which the
    architect may read) is born into its lineage and still sits the game out."""

    def setUp(self):
        super().setUp()
        self.settings["game"] = {"enabled": True, "mode": "gate", "arm_fraction": 0.0}
        game.t0(self.store, self.settings)
        self.clock.advance(60)

    def test_a_direction_birth_under_a_control_parent_is_legacy(self):
        parent = self.store.add_family({"id": "alpha-ctl", "mechanism": "An alpha call program on the index after calm "
                                        "weeks, an invented one.", "structure": "long_single", "roots": ["SPY"]},
                                       origin="architect")
        self.assertEqual(game.arm(self.store, parent, self.settings), "control")
        self.assertIn("alpha-ctl", {f["id"] for f in self.arch().visible(alive=True)}, "the architect reads it")
        born = self.arch().admit([proposal("dir-under", card=DIR, structure="long_single", roots=["SPY"],
                                           mechanism=DMECH, parent="alpha-ctl")])
        self.assertEqual(born, ["dir-under"])
        fam = self.store.family("dir-under")
        self.assertEqual((fam["lineage"], fam["spec"]["lane"]), (parent["lineage"], "direction"))
        self.assertIsNone(game.arm(self.store, fam, self.settings), "decision 5: no hidden look, no control look")


# ------------------------------------------------------------------------------------------------ 3, 7. K5's clear
class K5Clear(unittest.TestCase):
    """Findings 3 and 7 at the module: a clear is recorded and re-arms K5 from the net at clearing."""

    def setUp(self):
        from league.swarm.store import SwarmStore

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = SwarmStore(Path(self.tmp.name))
        self.addCleanup(self.store.close)

    def test_deleting_the_kv_is_a_durable_clear(self):
        self.assertTrue(dlane.k5_trip(self.store, GATE, -650.0))
        self.assertEqual(dlane.mode_effective(self.store, GATE), "shadow")
        self.store._exec("DELETE FROM kv WHERE key=?", (dlane.K5_KEY,))  # the operator's clear by hand
        self.assertEqual(dlane.mode_effective(self.store, GATE), "gate", "the lane opens at once")
        self.assertFalse(dlane.k5_trip(self.store, GATE, -650.0), "an unrecorded clear is never undone by a trip")
        record = dlane.k5_rearm(self.store, GATE, -660.0)
        self.assertEqual((record["net"], record["cleared"]["how"], record["cleared"]["trip"]["net"]),
                         (-660.0, "the kv deleted", -650.0))
        self.assertEqual(dlane.k5_line(self.store, GATE), -1260.0, "-$600 below the net at clearing")
        self.assertIsNone(dlane.k5_rearm(self.store, GATE, -700.0), "recorded once")
        self.assertFalse(dlane.k5_trip(self.store, GATE, -1259.99))
        self.assertEqual(dlane.mode_effective(self.store, GATE), "gate", "the clear holds")
        self.assertTrue(dlane.k5_trip(self.store, GATE, -1260.0), "and K5 is armed again")
        self.assertEqual(dlane.mode_effective(self.store, GATE), "shadow")

    def test_k5_clear_then_taking_it_out_keeps_the_clear(self):
        self.assertTrue(dlane.k5_trip(self.store, GATE, -650.0))
        cleared = {"dlane": {"mode": "gate", "k5_clear": True}}
        self.assertEqual(dlane.mode_effective(self.store, cleared), "gate")
        self.assertFalse(dlane.k5_trip(self.store, cleared, -5000.0), "disarmed while k5_clear is true")
        record = dlane.k5_rearm(self.store, cleared, -700.0)
        self.assertEqual(record["cleared"]["how"], "dlane.k5_clear")
        self.assertIsNone(self.store.get(dlane.K5_KEY), "the trip is gone, so taking k5_clear out brings nothing back")
        # The operator takes k5_clear out: the same losses trip nothing, a further -$600 does.
        self.assertFalse(dlane.k5_trip(self.store, GATE, -700.0))
        self.assertEqual(dlane.mode_effective(self.store, GATE), "gate")
        self.assertTrue(dlane.k5_trip(self.store, GATE, -1300.0))

    def test_an_unknown_net_rebases_at_the_trips_net(self):
        self.assertTrue(dlane.k5_trip(self.store, GATE, -620.0))
        self.store._exec("DELETE FROM kv WHERE key=?", (dlane.K5_KEY,))
        self.assertEqual(dlane.k5_rearm(self.store, GATE, None)["net"], -620.0)

    def test_the_report_no_longer_says_k5_only_tightens_and_lists_the_clear_with_its_cost(self):
        text = " ".join(R.TIGHTENED)
        self.assertNotIn("the screen, the leakage alarm and K5 can only be tightened", text)
        self.assertIn("disarms it while it is true", text)
        [row] = [r for r in R.LOOSENED if r["rule"].startswith("K5's clear")]
        self.assertIn("can lose past any line with no K5", row["cost"])


class K5ClearThroughTheJob(ReportFixture):
    """Findings 3 and 7 through the `dlane` job, as docs/operations.md's K5 runbook does it."""

    def ctx(self):
        self.alerts: list[tuple[str, str]] = []
        return types.SimpleNamespace(root=self.root, now=lambda: self.now, config={},
                                     alert=lambda level, text: self.alerts.append((level, text)))

    def gate(self, **extra) -> None:
        (self.root / "swarm.json").write_text(json.dumps({"dlane": {"mode": "gate", **extra}}))

    def k5(self):
        return json.loads((self.root / R.FILE).read_text())["k5"]

    def trip(self):
        self.gate()
        self.fam("dir-a", lane="direction")
        self.close("dir-a", route=":i", pnl=-650.0)
        out = R.run(self.ctx())
        self.assertEqual((out["k5_tripped"], out["k5_new"]), (True, True))

    def test_the_runbooks_k5_clear_then_taking_it_out(self):
        self.trip()
        self.gate(k5_clear=True)  # step 1: the lane opens at once
        out = R.run(self.ctx())   # the job's next run records the clear
        self.assertTrue(out["k5_rearmed"])
        self.assertIsNone(self.store.get(dlane.K5_KEY))
        self.assertEqual(self.k5()["line"], -1250.0)
        self.assertTrue(any("K5 is disarmed" in text for _, text in self.alerts), "the loosening is said every run")
        R.run(self.ctx())
        self.assertTrue(any("K5 is disarmed" in text for _, text in self.alerts))
        self.gate()  # step 2: take k5_clear out
        out = R.run(self.ctx())
        self.assertEqual((out["k5_tripped"], out["k5_new"]), (False, False), "the cleared losses trip nothing again")
        self.assertEqual(dlane.mode_effective(self.store, GATE), "gate")
        self.assertFalse(any(level == "warning" and "K5" in text for level, text in self.alerts))
        self.close("dir-a", route=":r", pnl=-599.0)
        self.assertFalse(R.run(self.ctx())["k5_tripped"])
        self.close("dir-a", route=":r", pnl=-1.0)
        out = R.run(self.ctx())
        self.assertEqual((out["k5_tripped"], out["k5_new"]), (True, True), "armed again, -$600 below the clear")

    def test_deleting_the_kv_is_recorded_by_the_next_run(self):
        self.trip()
        self.store._exec("DELETE FROM kv WHERE key=?", (dlane.K5_KEY,))
        out = R.run(self.ctx())
        self.assertEqual((out["k5_tripped"], out["k5_rearmed"]), (False, True))
        self.assertTrue(any("K5 cleared (the kv deleted) and re-armed" in text for _, text in self.alerts))
        self.assertEqual(dlane.mode_effective(self.store, GATE), "gate")
        self.assertFalse(R.run(self.ctx())["k5_tripped"], "it stays cleared")


# ------------------------------------------------------------------------------------------------ 4. the class cap
class ClassCapAndTheQuota(LaneCase):
    """Finding 4: the reservation follows the room under `architect.max_alive_per_class`."""

    def fill(self, structure: str, n: int = 12, roots=("SPY",)):
        for i in range(n):
            self.store.add_family({"id": f"{structure}-{i}", "mechanism": f"An invented alpha program {structure} {i}.",
                                   "structure": structure, "roots": list(roots)}, origin="architect")

    def alpha_rows(self):
        return [proposal(f"alpha-x-{i}", roots=["XSP"], structure=structure,
                         mechanism=f"An invented alpha index program, variant {i}, that trades a calm open.")
                for i, structure in enumerate(("debit_vertical", "debit_vertical", "long_single", "long_single"))]

    def test_full_lane_classes_reserve_nothing_and_never_block_alpha(self):
        self.fill("long_single")
        self.fill("debit_vertical")
        a = self.arch()
        self.assertEqual(a.want(), 6)
        self.assertEqual(a.lane_classes(), ["debit_vertical x etf", "long_single x etf"])
        a.pass_lane_quota = quota = a.lane_quota()
        self.assertEqual((quota.floor, quota.reserved()), (0, 0), "no direction card could fill a reservation")
        self.assertIn("class cap", quota.why_not(dlane.DIRECTION))
        self.assertIsNone(quota.why_not(dlane.ALPHA))
        self.assertIn("every class a direction card can be in is full", quota.text())
        born = a.admit(self.direction(1)[:2] + self.alpha_rows())
        self.assertEqual([f for f in born if f.startswith("dir-")], [])
        self.assertEqual(len([f for f in born if f.startswith("alpha-x-")]), 4, "alpha keeps every place")
        event = quota.event()
        self.assertEqual(event["lane_short"], 0)
        self.assertEqual(event["lane_class_capped"], {"cards": 2, "full": ["debit_vertical x etf", "long_single x etf"]})
        self.assertIsNone(a.lane_only(), "no direction-only pass while the lane's classes are full")

    def test_a_short_pass_names_the_full_class_not_the_cards_form(self):
        self.fill("long_single")
        self.fill("debit_vertical", 11)  # one place left in debit_vertical x etf
        a = self.arch()
        a.pass_lane_quota = quota = a.lane_quota()
        self.assertEqual(quota.floor, 1, "the reservation is the room: 1, not ceil(0.5 x 6) = 3")
        a.admit(self.direction(2)[:2] + self.alpha_rows())  # two direction long_singles: capped
        self.assertEqual(quota.short(), 1)
        self.assertIn("Full under the class cap", quota.text())
        self.store.put(LANE_LAST_KEY, {"at": "2026-10-09T06:00:00Z", **quota.event(), "lane_only": None})
        lead = self.arch().lane_lead()
        self.assertIn("The class cap refused 2 of its direction cards (full: long_single x etf)", lead)
        self.assertNotIn("no well-formed direction card", lead)
        self.assertIn("Direction cards refused by the class cap: 2 (full: long_single x etf).", self.arch().lanes_block())

    def test_with_no_cap_the_quota_is_as_before(self):
        self.settings["architect"]["max_alive_per_class"] = 0
        self.fill("long_single", 14)
        quota = self.arch().lane_quota()
        self.assertIsNone(quota.class_room)
        self.assertEqual(quota.reserved(), quota.floor)
        self.assertNotIn("lane_class_capped", quota.event())


# ------------------------------------------------------------------------------------------------ 5. today's figures
class NoFigurePricedToday(unittest.TestCase):
    """Finding 5: what agents read of E5 is its verdict; the scale and the cap stay in the family state and the report."""

    #: Invented live context with figures no Train fact can produce: SPY's last close and the account's equity.
    CLOSE, SOD = 777.77, "1289.37"

    def context(self, root: Path) -> dict:
        (root / dlane.CLOSES_FILE).write_text(json.dumps({"schema": 1, "closes": {"SPY": {"2099-01-03": self.CLOSE}}}))
        (root / dlane.HEALTH_FILE).write_text(json.dumps({"options_live": {"stops": {"sod_equity": self.SOD}}}))
        return dlane.unit_context(root, GATE)

    def forbidden(self, unit: dict, priced: dict) -> list[str]:
        scale = unit["scale"]["SPY"]
        # Each at the precision a text would print it (two decimals for dollars; a scale to 2-4 places).
        return [f"{self.CLOSE:.2f}", self.SOD, "1,289", f"{unit['cap_usd']:.2f}", f"${unit['cap_usd']:.0f}",
                f"{scale:.2f}", f"{scale:.3f}", f"{scale:.4f}", f"{priced['scaled_usd']:.2f}",
                f"${priced['scaled_usd']:.0f}"]

    def score(self, root: Path, max_loss: float) -> tuple[dict, dict]:
        unit = self.context(root)
        r = always_in()
        r["trades"] = [{"day": f"2024-03-{d:02d}", "max_loss": max_loss, "fees": 0.65, "qty": 1, "root": "SPY"}
                       for d in range(4, 14)]
        return dlane.train_score(r, first_year=2022, unit=unit, settings=GATE), unit

    def test_no_view_status_why_row_or_summary_carries_a_figure_priced_today(self):
        for max_loss in (41.11, 141.11):  # a pass and a fail
            with tempfile.TemporaryDirectory() as d:
                score, unit = self.score(Path(d), max_loss)
            priced = score["unit"]
            self.assertEqual(priced["verdict"], "pass" if max_loss < 100 else "fail")
            robust = dlane.robust_verdict(score, train_run({"2022": (-1400.0, -3.5, {}), "2023": (2500.0, 2.0, {}),
                                                            "2024": (2300.0, 1.8, {})}), settings=GATE)
            shown = {
                "view": dlane.view(score, robust),
                "status": dlane.status_text(score, robust, version=3, settings=GATE),
                "why": score.get("why"),
                "row": lane_cells(score),
                "summary": dlane.compact(score),
                "row_from_summary": lane_cells(dlane.compact(score)),
            }
            text = json.dumps(shown)
            for figure in self.forbidden(unit, priced):
                self.assertNotIn(figure, text, f"{figure} (max loss {max_loss})")
            for key in ("scale", "scaled_usd", "cap_usd"):
                self.assertNotIn(key, shown["view"]["unit"])
                self.assertNotIn(key, shown["summary"]["unit"])
            if priced["verdict"] == "fail":
                self.assertEqual(shown["view"]["unit"], {"verdict": "fail", "hint": dlane.UNIT_HINT})
                self.assertIn("over the unit cap", shown["why"])
            # The family state keeps today's figures for the operator's report (A7), and the summary re-prices today.
            self.assertEqual(dlane.compact(score, priced=True)["unit"]["scaled_usd"], priced["scaled_usd"])
            with tempfile.TemporaryDirectory() as d:
                again = dlane._score_from_compact(dlane.compact(score), self.context(Path(d)), GATE)
            self.assertEqual(again["unit"]["verdict"], priced["verdict"])

    def test_a_pruned_runs_read_run_summary_has_no_figure_priced_today(self):
        """`read_run` of a pruned run hands the researcher its row's summary: the compact score kept there."""
        with tempfile.TemporaryDirectory() as d:
            score, unit = self.score(Path(d), 141.11)
        summary = {"train_score": score["score"], dlane.STATE_KEY: dlane.compact(score)}
        text = json.dumps(summary)
        for figure in self.forbidden(unit, score["unit"]):
            self.assertNotIn(figure, text)


class NoCapInTheArchitectsRequest(LaneCase):
    """Finding 5 in the architect's LANES block: the unit's rule, never today's dollar cap (a share of equity)."""

    def test_the_lanes_block_states_the_rule_only(self):
        fam = self.store.add_family({"id": "dir-old", "mechanism": DMECH, "structure": "long_single", "roots": ["SPY"],
                                     "lane": "direction"}, origin="architect")
        self.store.set_state(fam["id"], **{dlane.STATE_KEY: {"objective": dlane.OBJECTIVE, "versions": {
            "1": {"at": self.store.now(), "train": {"fails": ["E5"], "eligible": False}}}}})
        root = Path(self.store.root)
        (root / dlane.HEALTH_FILE).write_text(json.dumps({"options_live": {"stops": {"sod_equity": "1289.37"}}}))
        (root / dlane.CLOSES_FILE).write_text(json.dumps({"schema": 1, "closes": {"SPY": {"2099-01-03": 777.77}}}))
        block = self.arch().lanes_block()
        self.assertIn("THE UNIT (E5): one lot's maximum loss with fees at today's index prices within the unit cap", block)
        for figure in ("128.94", "$129", "1289", "777.77"):
            self.assertNotIn(figure, block)


# ------------------------------------------------------------------------------------------------ 6. the brief
class BriefProvenance(unittest.TestCase):
    """Finding 6: the vertical guidance is a lane rule; the brief claims no Train result for it."""

    def test_the_brief_names_no_train_provenance_for_the_vertical_guidance(self):
        brief = dlane.brief_text(GATE, ["SPY"])
        self.assertNotIn("lost to cost on Train", brief)
        self.assertNotIn("1-3 point", brief)
        self.assertIn("the lane steers to single calls; narrow verticals rarely fit after costs", brief)


if __name__ == "__main__":
    unittest.main()
