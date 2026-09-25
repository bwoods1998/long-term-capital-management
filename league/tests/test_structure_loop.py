"""The learning loop for structures (G-LOOP of the options-desk run's Wave 2, Sept 25, 2026).

Evidence (the run record, docs/runs/2026-09-25-options-desk.md). An in-place edit was replayed at half
notional ($37.50 order cap), where a $1-wide condor cannot be opened (row S3). At 15:34:48Z krasker-22
"rewrote itself: its own rules had not fired in 11 wakes ... this file at least trades", adopting a
program whose replay had FAILED at 15:34:26Z, and at 15:42:56Z opened a CCL condor whose stop then tried
to buy it back at 1.46 on $0.50 wings (watch 16:31Z). `Lab._desk` returned None for the options desk, so
the lab never bred a structure program (row S3's note for after 20:05Z).
"""

from __future__ import annotations

import ast
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from league import parameters
from league.tests.test_options import STRUCTURE_AGENT, StructureHouseCase

#: A structure program whose width and deltas are bounded knobs (as the founders declare them).
BOUNDED = STRUCTURE_AGENT.replace(
    '"style": "test-structures"}',
    '"style": "test-structures", "parameter_rules": {"bounds": {"width": [1, 5], "entry_delta": [0.05, 0.35]}}}').replace(
    'PARAMS = {"structure": "iron_condor", "width": 1.0}', 'PARAMS = {"structure": "iron_condor", "width": 1.0, "entry_delta": 0.15}')
#: What a replay that opened nothing returns (the edit's replay is judged by the gate as any other).
NOTHING = {"ok": True, "trades": 0, "blocks": [], "return_pct": 0.0, "max_drawdown": 0.0, "fees_usd": 0.0}


class TheEditReplay(StructureHouseCase):
    """X1's `edit_params` replays a structure agent's edit at the full practice caps: the program as it trades."""

    def setUp(self):
        super().setUp()
        self.replays = []

        def replay(agent, code, params, tape, *, stake, limits, timeout=600):
            self.replays.append({"params": dict(params), "stake": stake, "limits": dict(limits)})
            return SimpleNamespace(result=dict(NOTHING), seconds=0.5, created=False)

        for patcher in (mock.patch.object(self.house.sandbox, "replay", side_effect=replay),
                        mock.patch.object(self.house, "tape_for", return_value=("options:test", {"venue": "alpaca", "asset_class": "option", "steps": []})),
                        mock.patch.object(self.house, "_replayable", return_value=True)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_a_structure_agents_edit_is_replayed_at_the_full_practice_caps(self):
        agent = self.house.spawn("krasker", "options-structures-test", BOUNDED, reason="test", specialty="alpaca-options")
        self.house.evaluator.seat(agent.id, 1, "practising on the structure book")  # as a founder is seated
        self.assertTrue(self.house.is_structure_agent(agent))
        result = self.house._edit_replay(self.house.registry.get(agent.id), {"width": 2.0})
        self.assertNotIn("error", result)
        (replay,) = self.replays
        # $200 stake, $100 a position, $75 an order: a $1 condor held at 0.62 ($62) fits, as it does on its book.
        self.assertEqual((replay["params"]["width"], replay["stake"], replay["limits"]),
                         (2.0, 200.0, {"max_position_usd": 100.0, "max_order_usd": 75.0}))
        self.assertEqual((result["numbers"]["stake_usd"], result["numbers"]["max_order_usd"]), (200.0, 75.0))
        look = self.house.ledger.last("agent.research", agent=agent.id).payload
        self.assertEqual((look["tool"], look["stake_usd"], look["max_order_usd"]), ("edit_replay", 200.0, 75.0))
        self.assertIn("the full practice caps", self.house._entries_standing(agent)["tools"])

    def test_any_other_agent_is_still_replayed_at_half_notional(self):
        from league.tests.test_entry_controls import SIZED

        agent = self.seated("sized", SIZED)
        self.assertFalse(self.house.is_structure_agent(agent))
        result = self.house._edit_replay(self.house.registry.get(agent.id), {"notional_usd": 20})
        self.assertNotIn("error", result)
        (replay,) = self.replays
        self.assertEqual((replay["stake"], replay["limits"]), (100.0, {"max_position_usd": 50.0, "max_order_usd": 37.5}))
        self.assertEqual((result["numbers"]["stake_usd"], result["numbers"]["max_order_usd"]), (100.0, 37.5))
        self.assertIn("half notional", self.house._entries_standing(agent)["tools"])


#: What krasker-22 took at 15:34:48Z: another structure program, whose replay traded (17 trades) and failed.
REWRITE = STRUCTURE_AGENT.replace("test-structures", "test-credit-spread").replace('"iron_condor"', '"credit_vertical"')


class TheStuckRewrite(StructureHouseCase):
    """The stuck-agent rule (`House._commit_research`) never puts a structure program that failed its replay to work."""

    def commit(self, agent, code, *, passed, barren=11, trades=17):
        needs = dict(agent.needs, style="test-credit-spread", structures=True)
        candidate = {"code": code, "needs": needs, "params": {"structure": "credit_vertical", "width": 1.0}, "passed": passed,
                     "purpose": "a short-dated defined-risk credit spread: this file at least trades", "numbers": {"trades": trades}}
        with mock.patch.object(self.house, "idle_run", return_value={"barren": barren}):
            return self.house._commit_research(agent.id, self.house._generation(agent.id), SimpleNamespace(candidate=candidate, consulted=""))

    def test_a_stuck_structure_agent_keeps_its_rules_when_the_new_programs_replay_failed(self):
        agent = self.structure_agent()
        was = agent.code_sha256
        self.assertIsNone(self.commit(agent, REWRITE, passed=False))
        self.assertEqual(self.house.registry.get(agent.id).code_sha256, was)
        self.assertEqual(self.house.ledger.count(kinds="agent.strategy", agent=agent.id), 0)
        row = self.house.ledger.last("agent.research", agent=agent.id).payload
        self.assertEqual((row["tool"], row["status"]), ("candidate", "not_adopted"))
        self.assertIn("had not fired in 11 wakes, but a structure program trades only once its replay passes", row["reason"])

    def test_a_single_leg_agent_is_not_rewritten_into_a_failed_structure_program_either(self):
        from league.tests.test_options_desk import SINGLE_LEG

        agent = self.house.spawn("krasker", "options-single-test", SINGLE_LEG, reason="test", specialty="alpaca-options")
        self.assertFalse(self.house.is_structure_agent(agent))
        was = agent.code_sha256
        self.assertIsNone(self.commit(agent, REWRITE, passed=False))
        self.assertEqual(self.house.registry.get(agent.id).code_sha256, was)
        self.assertEqual(self.house.ledger.last("agent.research", agent=agent.id).payload["status"], "not_adopted")

    def test_a_structure_program_that_passed_its_replay_is_adopted_as_before(self):
        agent = self.structure_agent()
        self.assertIsNone(self.commit(agent, REWRITE, passed=True))
        current = self.house.registry.get(agent.id)
        self.assertEqual(current.code, REWRITE)
        row = self.house.ledger.last("agent.strategy", agent=agent.id).payload
        self.assertIs(row["passed_replay"], True)

    def test_a_failed_structure_program_that_is_not_stuck_is_dropped_silently_as_any_other(self):
        agent = self.structure_agent()
        was = agent.code_sha256
        self.assertIsNone(self.commit(agent, REWRITE, passed=False, barren=3))
        self.assertEqual(self.house.registry.get(agent.id).code_sha256, was)
        self.assertEqual([e.payload.get("status") for e in self.house.ledger.iter(kinds="agent.research", agent=agent.id)], [])



def literal(code, name):
    for node in ast.parse(code).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name:
            return ast.literal_eval(node.value)
    return None


#: A structure program that declares no bounds of its own: the standard ranges are all it has.
UNDECLARED = {"structure": "iron_condor", "width": 1.0, "dte_min": 0, "dte_max": 2, "entry_delta": 0.15, "profit_target": 0.5,
              "stop_loss": 2.0, "exit_minutes_before_close": 30, "risk_usd": 75.0}
STRUCTURAL = {"venue": "alpaca", "horizon": "day", "asset_class": "option", "structures": True, "symbols": ["SPY"]}


class StructureKnobs(unittest.TestCase):
    """`league/parameters.py` STRUCTURE_BOUNDS: the lab breeds structures, not only signals."""

    def test_every_founder_stays_valid_and_its_type_is_frozen(self):
        seeds = sorted(Path(__file__).resolve().parents[1].joinpath("seeds").glob("options_*.py"))
        founders = [path for path in seeds if (literal(path.read_text(encoding="utf-8"), "NEEDS") or {}).get("structures") is True]
        self.assertEqual(len(founders), 12)
        for path in founders:
            code = path.read_text(encoding="utf-8")
            report = parameters.inspect(literal(code, "PARAMS"), literal(code, "NEEDS"))
            with self.subTest(founder=path):
                self.assertTrue(report["valid"], report["errors"])
                self.assertIn("structure", report["frozen"])
                self.assertNotIn("structure", report["mutable"])

    def test_a_program_that_declares_nothing_can_still_be_searched_inside_the_standard_ranges(self):
        report = parameters.inspect(UNDECLARED, STRUCTURAL)
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual({k: report["bounds"][k] for k in parameters.STRUCTURE_BOUNDS},
                         {"width": [0.5, 10], "dte_min": [0, 45], "dte_max": [0, 45], "entry_delta": [0.01, 0.99],
                          "profit_target": [0.05, 1], "stop_loss": [0.1, 10], "exit_minutes_before_close": [0, 390]})
        self.assertEqual(sorted(report["mutable"]), sorted(parameters.STRUCTURE_BOUNDS))  # risk_usd declares nothing
        self.assertIn(["dte_min", "dte_max"], report["ordered"])
        changed = set()
        for seed in range(400):
            child = parameters.mutate(UNDECLARED, seed=f"structure:{seed}", needs=STRUCTURAL)
            self.assertEqual(child["structure"], "iron_condor")  # another type is another family
            self.assertEqual(sum(child[k] != UNDECLARED[k] for k in UNDECLARED), 1)
            for key, (low, high) in parameters.STRUCTURE_BOUNDS.items():
                self.assertTrue(low <= child[key] <= high, (key, child[key]))
            self.assertIs(type(child["dte_min"]), int)
            self.assertIs(type(child["dte_max"]), int)
            self.assertLessEqual(child["dte_min"], child["dte_max"])
            changed |= {k for k in UNDECLARED if child[k] != UNDECLARED[k]}
        self.assertEqual(changed, set(parameters.STRUCTURE_BOUNDS))

    def test_what_is_not_a_structure_program_s_knob(self):
        for bad, words in (({"dte_min": 0.5}, "dte_min must be an integer"), ({"dte_min": 3, "dte_max": 1}, "dte_min=3 must be <= dte_max=1"),
                           ({"width": 20.0}, "width=20.0 outside [0.5, 10]"), ({"entry_delta": 1.2}, "entry_delta=1.2 outside"),
                           ({"profit_target": 1.5}, "profit_target=1.5 outside"), ({"stop_loss": 0.0}, "stop_loss=0.0 outside"),
                           ({"exit_minutes_before_close": 400}, "outside [0, 390]"), ({"dte_max": 46}, "dte_max=46 outside [0, 45]")):
            with self.subTest(bad=bad):
                errors = parameters.inspect({**UNDECLARED, **bad}, STRUCTURAL)["errors"]
                self.assertTrue(any(words in e for e in errors), errors)
        # A declared bound narrows the standard range; one wider than it is held to it.
        narrowed = parameters.inspect(UNDECLARED, {**STRUCTURAL, "parameter_rules": {"bounds": {"width": [1, 20]}}})
        self.assertEqual(narrowed["bounds"]["width"], [1, 10])

    def test_a_same_strike_structures_width_of_zero_is_its_type_not_a_knob(self):
        calendar = {**UNDECLARED, "structure": "calendar", "width": 0}
        report = parameters.inspect(calendar, {**STRUCTURAL, "parameter_rules": {"bounds": {"width": [0, 0]}}})
        self.assertTrue(report["valid"], report["errors"])
        self.assertIn("width", report["frozen"])
        for seed in range(50):
            self.assertEqual(parameters.mutate(calendar, seed=str(seed), needs=STRUCTURAL)["width"], 0)

    def test_the_same_names_on_a_program_that_is_not_a_structure_one_are_unbounded_as_before(self):
        report = parameters.inspect(UNDECLARED, {"venue": "alpaca", "horizon": "day", "asset_class": "option", "symbols": ["F"]})
        self.assertTrue(report["valid"])
        self.assertEqual(report["mutable"], [])  # no standard domain, nothing declared: nothing to search



HOLDOUT_END = "2026-05-15"  # `deep_replay.HOLDOUT`'s end


def _epoch(text):
    return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()


def _iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class OptionsStore:
    """An options history that covers everything asked of it; its tapes carry what the House's do that touches the sealed
    holdout -- warm-up bars and options-feature rows from before it ends -- and a step every six hours over the window."""

    def __init__(self):
        self.windows = []

    def covers(self, symbols, timeframe, start, end, **kw):
        return [str(s).upper() for s in symbols]

    def tape(self, needs, start, end, **kw):
        self.windows.append((start, end))
        steps, t = [], _epoch(start)
        while t <= _epoch(end):
            steps.append({"t": _iso(t), "bars": {}, "execution_bars": {}, "options": {},
                          "history_bars": {"SPY": [{"t": _iso(t), "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}]}})
            t += 6 * 3600
        return {"venue": "alpaca", "asset_class": "option", "horizon": kw["horizon"], "steps": steps, "contracts": {},
                "warmup_bars": {"SPY": [{"t": "2026-05-12T19:45:00Z", "c": 1.0}, {"t": "2026-05-15T19:45:00Z", "c": 1.0}]},
                "options_features": {"SPY": [{"t": "2026-05-14T04:00:00Z", "atm_iv": 0.2}, {"t": "2026-05-16T04:00:00Z", "atm_iv": 0.2}]}}

    def features_at(self, symbols, now_ts):
        return {}

    def feature_series(self, symbols, start="", end="9999"):
        return {}


class Box:
    """The lab box's contract, recording what each batch asked of it (`LabBox.evaluate`, `LabBox.forget`)."""

    def __init__(self):
        self.calls, self.forgot = [], []

    def evaluate(self, candidates, tape_id, tape, *, stake, limits, timeout=600, candidate_seconds=None):
        self.calls.append({"tape_id": tape_id, "ids": [c["id"] for c in candidates], "candidate_seconds": candidate_seconds,
                           "options": tape.get("asset_class") == "option"})
        return [{"ok": False, "error": "a test result", "id": c["id"]} for c in candidates]

    def forget(self, tape_id):
        self.forgot.append(tape_id)


def program(width=1.0, symbols=("SPY",)):
    """A structure program of the options desk (a different width is a different program for the lab)."""
    return STRUCTURE_AGENT.replace('"symbols": ["SPY"]', f'"symbols": {json.dumps(list(symbols))}').replace(
        '"width": 1.0}', f'"width": {width}}}')


class StructureLab(StructureHouseCase):
    """The lab searches the options desk for structure programs (`Lab._desk`), on development data only, one options
    tape in memory at a time, with a structure replay's own batch budget."""

    def setUp(self):
        super().setUp()
        from league.lab import Lab
        from league.tests.test_lab import FakeModel

        self.house.pacer.may_spend = lambda kind: True
        self.house.game["lab"] = {**(self.house.game.get("lab") or {}), "enabled": True, "step_seconds": 600,
                                  "stats_every_minutes": 0, "leap_every": 1000}
        self.store = self.house.options_history = OptionsStore()
        self.box = Box()
        self.lab = Lab(self.house, box=self.box, mutator=FakeModel("gpt-6-luna", []), leaper=FakeModel("gpt-6-sol", []))
        self.house.lab = self.lab
        self.addCleanup(self.lab.close)
        self.desk = self.house.niches["alpaca-options"]

    def queue(self, code, lineage="founder:test"):
        return self.lab.admit(code, niche=self.desk, origin="seed", author="house", lineage=lineage)

    def test_the_options_desk_is_searched_for_structure_programs_only(self):
        from league.lab import LabError
        from league.tests.test_options_desk import SINGLE_LEG

        self.assertIs(self.lab._desk("alpaca-options", literal(STRUCTURE_AGENT, "NEEDS")), self.desk)
        self.assertIsNone(self.lab._desk("alpaca-options", literal(SINGLE_LEG, "NEEDS")))
        self.assertIs(self.lab._desk("alpaca-options"), self.desk)  # a row already admitted
        self.queue(program())
        with self.assertRaisesRegex(LabError, "structure programs only"):
            self.queue(SINGLE_LEG)
        self.house.options_history = None  # no options history, no options replay: not searched
        self.assertIsNone(self.lab._desk("alpaca-options", literal(STRUCTURE_AGENT, "NEEDS")))

    def test_it_is_seeded_with_the_structure_founders_and_structure_agents_never_a_single_leg_one(self):
        from league import options_desk
        from league.tests.test_options_desk import SINGLE_LEG

        agent = self.structure_agent()
        single = self.house.spawn("krasker", "options-single", SINGLE_LEG, reason="test", specialty="alpaca-options")
        self.lab.seed(force=True)
        lineages = {r["lineage"] for r in self.lab._q("SELECT lineage FROM candidates WHERE niche='alpaca-options'")}
        founders = {f"founder:{f['key']}" for f in options_desk.structure_founders(self.house)}
        self.assertEqual(len(founders), 12)
        self.assertEqual(lineages, founders | {f"agent:{agent.id}"})
        self.assertNotIn(f"agent:{single.id}", lineages)
        self.assertTrue(self.lab.can_score(agent))
        self.assertFalse(self.lab.can_score(single))

    def test_a_structure_search_tape_is_development_data_only(self):
        from league.lab import check_dev_only
        from league.sandbox import holdout_problem

        ident, cut = self.lab._search_tape(literal(STRUCTURE_AGENT, "NEEDS"))
        self.assertEqual([r["t"] for r in cut["warmup_bars"]["SPY"]], ["2026-05-15T19:45:00Z"])
        self.assertEqual([r["t"] for r in cut["options_features"]["SPY"]], ["2026-05-16T04:00:00Z"])
        check_dev_only(cut, self.house.holdout_window)
        self.assertIsNone(holdout_problem(cut, self.house.holdout_window))  # the lab box's own seal lets it in
        # The House's tape as built reached into the holdout: the box would have refused it whole.
        _, whole = self.house.tape_for(literal(STRUCTURE_AGENT, "NEEDS"))
        self.assertIn("sealed holdout", holdout_problem(whole, self.house.holdout_window))

    def test_one_options_tape_is_held_and_one_is_built_every_twenty_minutes(self):
        first, _ = self.lab._search_tape(literal(STRUCTURE_AGENT, "NEEDS"))
        other = literal(program(symbols=("QQQ",)), "NEEDS")
        self.lab._tapes_built = 0
        with self.assertRaisesRegex(TimeoutError, "one options tape every 20 minutes"):
            self.lab._search_tape(other)
        self.clock.advance(21 * 60)
        self.lab._tapes_built = 0
        second, _ = self.lab._search_tape(other)
        options = [hit[1] for hit in self.lab._tapes.values() if hit[2].get("asset_class") == "option"]
        self.assertEqual(options, [second])
        self.assertEqual(self.box.forgot, [first])  # the box's memo let the first go too
        self.assertEqual(self.lab._search_tape(other)[0], second)  # held: no build, no wait

    def test_a_batch_on_a_structure_tape_is_held_to_its_size_and_each_replay_to_its_own_seconds(self):
        for n in range(20):
            self.queue(program(width=1.0 + n / 10))
        self.lab.evaluate_batch()
        (call,) = self.box.calls
        self.assertEqual((len(call["ids"]), call["candidate_seconds"], call["options"]), (16, 120.0, True))

    def test_a_structure_programs_forward_window_is_the_options_tape_of_its_last_week(self):
        from league.lab import LabError
        from league.tests.test_options_desk import SINGLE_LEG

        needs = {**literal(STRUCTURE_AGENT, "NEEDS"), "options_features": True}
        ident, tape = self.lab._forward_tape(needs)
        start, end = self.store.windows[-1]
        self.assertEqual(_epoch(end) - _epoch(start), 7 * 86400)
        self.assertEqual([r["t"] for r in tape["options_features"]["SPY"]], ["2026-05-16T04:00:00Z"])  # carried, never refused
        self.assertEqual(self.lab._forward_tape(needs)[0], ident)  # one build a run
        self.assertEqual(len(self.store.windows), 1)
        with self.assertRaisesRegex(LabError, "structure programs only"):
            self.lab._forward_tape(literal(SINGLE_LEG, "NEEDS"))

    def test_a_structure_resident_is_scored_on_a_forward_window_and_the_box_lets_its_tape_go(self):
        agent = self.structure_agent()
        self.house.evaluator.seat(agent.id, 1, "practising on the structure book")
        self.lab.seed(force=True)
        self.clock.advance(3 * 86400)
        out = self.lab.forward_windows(force=True)
        self.assertGreaterEqual(out["scored"], 1, out)
        (call,) = [c for c in self.box.calls if c["tape_id"].startswith("fwd:")]
        self.assertEqual((call["candidate_seconds"], call["options"]), (120.0, True))
        self.assertIn(call["tape_id"], self.box.forgot)

    def test_a_forward_cut_of_an_options_tape_hands_the_earlier_signal_bars_on_as_warm_up(self):
        from league.lab import forward_cut

        tape = self.store.tape({}, "2026-09-01T14:00:00Z", "2026-09-02T14:00:00Z", horizon="day")
        cut = forward_cut(tape, _epoch("2026-09-02T01:00:00Z"))
        self.assertEqual([r["t"] for r in cut["warmup_bars"]["SPY"]],
                         ["2026-05-12T19:45:00Z", "2026-05-15T19:45:00Z", "2026-09-01T14:00:00Z", "2026-09-01T20:00:00Z"])
        self.assertEqual(cut["steps"][0]["t"], "2026-09-02T02:00:00Z")


if __name__ == "__main__":
    unittest.main()
