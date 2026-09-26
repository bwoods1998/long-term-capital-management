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

    def test_the_forward_windows_of_one_tape_key_run_together(self):
        """The review of G-LOOP (Sept 25, 2026): the lab holds one options forward tape at a time, so windows of one key
        that sat apart in `forward_due` order had it built twice a run, under the House's tape lock."""
        from league.lab import LabError, tape_key

        spy, qqq = literal(program(), "NEEDS"), literal(program(symbols=("QQQ",)), "NEEDS")
        now = self.clock.now
        rows = [{"id": f"cand-{n}", "needs": json.dumps(needs), "code": "x", "evaluated": now - hours * 3600, "created": now - hours * 3600}
                for n, (needs, hours) in enumerate(((spy, 5), (qqq, 5), (spy, 9)))]
        asked = []

        def tape(needs):
            asked.append(tape_key(needs))
            raise LabError("a test's: no window")

        with mock.patch.object(self.lab, "forward_due", return_value=rows), mock.patch.object(self.lab, "_forward_tape", side_effect=tape):
            self.lab.forward_windows(force=True)
        self.assertEqual(asked, [tape_key(spy), tape_key(spy), tape_key(qqq)])

    def test_a_forward_cut_of_an_options_tape_hands_the_earlier_signal_bars_on_as_warm_up(self):
        from league.lab import forward_cut

        tape = self.store.tape({}, "2026-09-01T14:00:00Z", "2026-09-02T14:00:00Z", horizon="day")
        cut = forward_cut(tape, _epoch("2026-09-02T01:00:00Z"))
        self.assertEqual([r["t"] for r in cut["warmup_bars"]["SPY"]],
                         ["2026-05-12T19:45:00Z", "2026-05-15T19:45:00Z", "2026-09-01T14:00:00Z", "2026-09-01T20:00:00Z"])
        self.assertEqual(cut["steps"][0]["t"], "2026-09-02T02:00:00Z")



class DailyVenue:
    """The listing and bars endpoints for SPY with three expiries in one week (a Monday, a Wednesday and the Friday),
    a bar a weekday for every contract until its expiry; it records what it was asked."""

    DAYS = ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06", "2026-03-09", "2026-03-10", "2026-03-11",
            "2026-03-12", "2026-03-13"]
    EXPIRIES = ("2026-03-09", "2026-03-11", "2026-03-13")

    def __init__(self):
        self.bars = []  # (expiry, start, end) of every bars request

    def get(self, path, params):
        if path == "/v2/options/contracts":
            if params["status"] != "inactive" or params.get("page_token"):
                return {"option_contracts": []}
            return {"option_contracts": [{"symbol": f"SPY{e[2:4]}{e[5:7]}{e[8:]}{r}{k * 1000:08d}", "size": "100", "status": "inactive"}
                                         for e in self.EXPIRIES for k in (99, 100, 101) for r in "CP"]}
        symbols = params["symbols"].split(",")
        expiry = f"20{symbols[0][3:5]}-{symbols[0][5:7]}-{symbols[0][7:9]}"
        self.bars.append((expiry, params["start"][:10], params["end"][:10]))
        return {"bars": {occ: [{"t": f"{d}T15:00:00Z", "o": 1.0, "h": 1.1, "l": 0.9, "c": 1.0, "v": 10, "n": 3, "vw": 1.0}
                               for d in self.DAYS if params["start"][:10] <= d <= min(params["end"][:10], expiry)] for occ in symbols}}


class TheDailyExpiries(unittest.TestCase):
    """SPY, QQQ and IWM list an expiry every weekday; the store ingested only the last of each week (`weekly_only`)."""

    def setUp(self):
        import tempfile
        from league import options_history as oh

        self.oh = oh
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.venue = DailyVenue()
        self.store = oh.OptionsHistory(Path(folder.name) / "o.sqlite", self.venue.get,
                                       clock=lambda: datetime(2026, 9, 22, tzinfo=timezone.utc).timestamp())
        self.addCleanup(self.store.close)
        self.underlier = lambda symbol, timeframe, start, end: [
            {"t": oh.close_stamp(f"{d}T05:00:00Z", "1Day"), "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.0, "v": 1e6}
            for d in ["2026-01-20"] + DailyVenue.DAYS if start[:10] <= d <= end[:10]]

    def ingest(self, **kw):
        return self.store.ingest(["SPY"], "2026-03-02", "2026-03-13", underlier_bars=self.underlier, band=0.05, max_days=10, **kw)

    def test_every_expiry_is_ingested_its_weekdays_from_their_own_reach_and_the_friday_is_never_fetched_again(self):
        (weekly,) = self.ingest()
        self.assertEqual(self.venue.bars, [("2026-03-13", "2026-03-03", "2026-03-13")])  # the Friday alone, 10 days back
        self.assertTrue(weekly["weekly_only"])
        self.assertEqual(self.store.covers(["SPY"], "1Day", "2026-03-02T00:00:00Z", "2026-03-13T00:00:00Z", every_expiry=True), [])
        self.venue.bars.clear()
        (every,) = self.ingest(all_expiries=self.oh.DAILY_EXPIRIES, daily_max_days=3)
        # The Monday and the Wednesday, each from three days before it; the Friday's chunk is done already.
        self.assertEqual(self.venue.bars, [("2026-03-09", "2026-03-06", "2026-03-09"), ("2026-03-11", "2026-03-08", "2026-03-11")])
        self.assertEqual((every["weekly_only"], every["daily_max_days"], every["expiries"]), (False, 3, 3))
        self.assertEqual(self.store.covers(["SPY"], "1Day", "2026-03-02T00:00:00Z", "2026-03-13T00:00:00Z", every_expiry=True), ["SPY"])
        self.assertEqual(self.store.covers(["SPY"], "1Day", "2026-03-02T00:00:00Z", "2026-03-13T00:00:00Z"), ["SPY"])

    def test_an_underlying_not_listed_keeps_its_weekly_expiries(self):
        (row,) = self.ingest(all_expiries=("QQQ",), daily_max_days=3)
        self.assertEqual([b[0] for b in self.venue.bars], ["2026-03-13"])
        self.assertTrue(row["weekly_only"])

    def test_the_features_read_the_weekly_expiries_alone_before_and_after_every_expiry_is_ingested(self):
        """The adversarial review of Deploy G (Sept 25, 2026): once the weekdays are ingested, a new day's features would
        sum three expiries where every stored day summed one (`compute_features` never remakes a day): a step in
        `option_volume`, `contracts_printed` and `put_call_volume_ratio` between replay and live."""
        self.ingest()
        weekly = self.store.features_for_day("SPY", "2026-03-05", 100.0)
        self.assertEqual((weekly["contracts_printed"], weekly["option_volume"]), (6, 60))  # the Friday's six contracts
        self.ingest(all_expiries=self.oh.DAILY_EXPIRIES, daily_max_days=10)
        printed = self.store.db.execute("SELECT COUNT(DISTINCT b.occ) FROM bars b JOIN contracts c ON c.occ = b.occ WHERE b.timeframe = '1Day' "
                                        "AND b.t = ?", (self.oh.close_stamp("2026-03-05T12:00:00Z", "1Day"),)).fetchone()[0]
        self.assertEqual(printed, 18)  # the Monday's, the Wednesday's and the Friday's contracts all printed that day
        every = self.store.features_for_day("SPY", "2026-03-05", 100.0)
        self.assertEqual(every, weekly)
        # Another underlying is read on every expiry it holds, as before.
        self.store.db.execute("UPDATE contracts SET underlying = 'F' WHERE underlying = 'SPY'")
        self.assertEqual(self.store.features_for_day("F", "2026-03-05", 100.0)["contracts_printed"], 18)


class TheHousesDailyRefresh(StructureHouseCase):
    """`House._refresh_options_history` ingests every expiry of SPY, QQQ and IWM for the options desk's replay, and
    backfills a symbol the store holds only weekly across the window once -- while `league/config.json`
    `options_history_daily_expiries` is on (the review of Deploy G, Sept 25, 2026: Deploy G ships it off)."""

    def refreshed(self, every=()):
        """What `_refresh_options_history` asks `refresh` for, the store covering every symbol weekly and `every` with
        every expiry: (symbols, days, all_expiries, daily_max_days) a call."""
        asked, calls = [], []

        class Store(OptionsStore):
            def covers(self, symbols, timeframe, start, end, every_expiry=False, **kw):
                asked.append((sorted(symbols), timeframe, every_expiry))
                return [str(s).upper() for s in symbols if not every_expiry or str(s).upper() in every]

        self.house.options_history = Store()

        def refresh(store_, symbols, underlier, **kw):
            calls.append((sorted(symbols), kw["days"], kw.get("all_expiries"), kw.get("daily_max_days")))
            return {"features": {}, "coverage": []}

        with mock.patch("league.options_history.refresh", refresh):
            self.house._refresh_options_history()
        return calls, asked

    def test_off_every_symbol_is_refreshed_weekly_as_before_and_nothing_is_backfilled(self):
        self.structure_agent()  # trades SPY
        self.assertIs(self.house._options_history_daily_expiries(), False)  # the repository's config.json
        calls, asked = self.refreshed()
        self.assertEqual(calls, [(["SPY"], 10, None, None), (["IWM", "QQQ"], 10, None, None)])
        self.assertNotIn(True, [every for _, _, every in asked])

    def test_the_switch_is_on_only_when_the_config_says_true_and_the_repository_ships_it_off(self):
        from league import house as house_module

        for config, on in (({}, False), ({"options_history_daily_expiries": "true"}, False), ({"options_history_daily_expiries": 1}, False),
                           ({"options_history_daily_expiries": True}, True)):
            with self.subTest(config=config):
                self.house.options_history_daily_expiries = None
                with mock.patch.object(house_module.json, "loads", return_value=config):
                    self.assertIs(self.house._options_history_daily_expiries(), on)
        self.house.options_history_daily_expiries = None
        with mock.patch.object(house_module.Path, "read_text", side_effect=OSError("unreadable")):
            self.assertIs(self.house._options_history_daily_expiries(), False)
        config = json.loads((Path(__file__).resolve().parents[1] / "config.json").read_text(encoding="utf-8"))
        self.assertIs(config["options_history_daily_expiries"], False)

    def test_spy_is_backfilled_with_every_expiry_once_and_the_rest_are_kept_current(self):
        from league import options_history as oh

        self.house.options_history_daily_expiries = True  # a later release turns it on
        agent = self.structure_agent()  # trades SPY
        single = self.house.spawn("krasker", "options-single", STRUCTURE_AGENT.replace('"structures": True, "symbols": ["SPY"]', '"symbols": ["F"]'),
                                  reason="test", specialty="alpaca-options")
        asked = []

        class Store(OptionsStore):
            every = set()

            def covers(self, symbols, timeframe, start, end, every_expiry=False, **kw):
                asked.append((sorted(symbols), timeframe, every_expiry))
                return [str(s).upper() for s in symbols if not every_expiry or str(s).upper() in self.every]

        store = self.house.options_history = Store()
        calls = []

        def refresh(store_, symbols, underlier, **kw):
            calls.append((sorted(symbols), kw["days"], kw.get("all_expiries"), kw.get("daily_max_days")))
            return {"features": {}, "coverage": []}

        span = self.house.settings.replay_days * 6 + 5
        with mock.patch("league.options_history.refresh", refresh):
            self.house._refresh_options_history()
            self.assertIn((["SPY"], "15Min", True), asked)
            self.assertEqual(calls[:2], [(["F"], 10, oh.DAILY_EXPIRIES, oh.DAILY_MAX_DAYS), (["SPY"], span, oh.DAILY_EXPIRIES, oh.DAILY_MAX_DAYS)])
            self.assertEqual(calls[2], (["IWM", "QQQ"], 10, None, None))  # the features' weekly 1Day, as before
            store.every = {"SPY"}
            calls.clear()
            self.house._refresh_options_history()
            self.assertEqual(calls[0], (["F", "SPY"], 10, oh.DAILY_EXPIRIES, oh.DAILY_MAX_DAYS))
        self.assertTrue(agent.alive and single.alive)



#: Keeps a checksum of the chain it is shown at every step (its memory holds 8 KB), opens a $1 call vertical on the chain's
#: nearest call of a later expiry at 15:00Z on the first day -- its short wing named a strike past it, whether or not the
#: chain of ten showed it (it is within the reach of twenty, so the open stands) -- and closes it at 16:30Z on the second.
CHAIN_WATCHER = '''
NEEDS = {"venue": "alpaca", "horizon": "day", "style": "chain-watcher", "asset_class": "option", "structures": True,
         "symbols": ["SPY"], "bars": {"timeframe": "1Day", "limit": 5}, "max_days_to_expiry": 3}
PARAMS = {}

def decide(ctx):
    mem = dict(ctx.get("memory") or {})
    chain = sorted(ctx.get("chain") or [], key=lambda r: r["occ"])
    text = ctx["now"] + ":" + ",".join(r["occ"] for r in chain)
    sig = int(mem.get("sig") or 7)
    for ch in text:
        sig = (sig * 131 + ord(ch)) % 2305843009213693951
    mem["sig"], mem["steps"], mem["shown"] = sig, int(mem.get("steps") or 0) + 1, int(mem.get("shown") or 0) + len(chain)
    out = []
    calls = [r for r in ctx.get("chain") or [] if r["right"] == "call" and r["expiry"] > ctx["now"][:10]]
    if ctx["now"] == "2026-03-02T15:00:00Z" and calls:
        near = min(calls, key=lambda r: (abs(r["strike"] - r["underlying_price"]), r["expiry"]))
        wing = near["occ"][:-8] + str(int(near["occ"][-8:]) + 1000).zfill(8)
        mem["legs"] = [{"occ": near["occ"], "role": "long"}, {"occ": wing, "role": "short"}]
        out.append({"structure": "debit_vertical", "action": "open", "quantity": 1, "legs": mem["legs"], "limit_price": 0.74, "reason": "t"})
    if ctx["now"] == "2026-03-03T16:30:00Z" and mem.get("legs"):
        out.append({"structure": "debit_vertical", "action": "close", "quantity": 1, "legs": mem["legs"], "limit_price": 0.01, "reason": "t"})
    return {"intents": out, "memory": mem}
'''


EXPIRIES = ("2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06")  # Monday to Friday, EST


def closes_of(path):
    """(stamp, SPY) every 15 minutes, 14:45-21:00Z, on March 2, 3 and 4, 2026: `path(n)` the n-th close."""
    out = []
    for d, day in enumerate(("2026-03-02", "2026-03-03", "2026-03-04")):
        for k in range(26):
            stamp = datetime(int(day[:4]), int(day[5:7]), int(day[8:]), 14, 45, tzinfo=timezone.utc) + timedelta(minutes=15 * k)
            out.append((stamp, round(path(d * 26 + k), 4)))
    return out


def reach_store(case, closes):
    """An options history of SPY around `closes`: strikes 90-110 a dollar apart, calls and puts, the five expiries of the
    week, a 15-minute bar of every contract at three steps of every four until its expiry, priced from the underlying."""
    import tempfile
    from league import options_history as oh

    folder = tempfile.TemporaryDirectory()
    case.addCleanup(folder.cleanup)
    store = oh.OptionsHistory(Path(folder.name) / "s.sqlite")
    case.addCleanup(store.close)
    rows, bars = [], []
    for expiry in EXPIRIES:
        for strike in range(90, 111):
            for right in ("C", "P"):
                occ = f"SPY{expiry[2:4]}{expiry[5:7]}{expiry[8:]}{right}{strike * 1000:08d}"
                rows.append((occ, "SPY", expiry, float(strike), "call" if right == "C" else "put", 100, "inactive", "x"))
                for n, (stamp, spot) in enumerate(closes):
                    if stamp.strftime("%Y-%m-%d") > expiry or (strike + n) % 4 == 0:
                        continue  # expired; or a quiet interval with no print
                    inside = max(0.0, spot - strike) if right == "C" else max(0.0, strike - spot)
                    days = (datetime.fromisoformat(expiry + "T21:00:00+00:00") - stamp).total_seconds() / 86400
                    price = round(inside + 0.6 * (days + 0.2) ** 0.5 * 2.718 ** (-abs(strike - spot) / 3), 2) + 0.01
                    bars.append((occ, "15Min", stamp.strftime("%Y-%m-%dT%H:%M:%SZ"), price, price + 0.02, price - 0.01, price, 20.0, 4, price))
    store.db.executemany("INSERT INTO contracts VALUES (?,?,?,?,?,?,?,?)", rows)
    store.db.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?,?)", bars)
    store.db.commit()
    return store


def underlier_of(closes):
    def underlier(symbol, timeframe, start, end):
        if timeframe == "1Day":
            return [{"t": f"{day}T05:00:00Z", "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.0, "v": 1e6} for day in ("2026-02-26", "2026-02-27")]
        return [{"t": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": spot, "h": spot, "l": spot, "c": spot, "v": 1e5}
                for stamp, spot in closes if start <= stamp.strftime("%Y-%m-%dT%H:%M:%SZ") <= end]
    return underlier


def two_tapes(store, closes, needs, *, whole=True, **kw):
    """The tape a structure program is replayed on (only what its chain could reach, `_structure_reach`) and the whole one
    (every bar; None when `whole` is False), with a chain of 10 and a reach of 20: the House's 80 and 160, scaled to the
    fixture's 210 contracts."""
    from league import options_history as oh, options_replay

    with mock.patch.object(options_replay, "STRUCTURE_CHAIN_PER_UNDERLYING", 10), mock.patch.object(oh, "STRUCTURE_REACH", 20):
        build = lambda: store.tape(needs, "2026-03-02T00:00:00Z", "2026-03-04T23:00:00Z", horizon="day",  # noqa: E731
                                   underlier_bars=underlier_of(closes), warmup=5, execution="15Min", max_order_usd=75.0, **kw)
        kept = build()
        if not whole:
            return kept, None
        with mock.patch.object(oh.OptionsHistory, "_structure_reach", return_value=None):
            return kept, build()


def replayed(code, tape, params=None):
    from league import options_replay
    from league.replay import run_replay

    with mock.patch.object(options_replay, "STRUCTURE_CHAIN_PER_UNDERLYING", 10):
        return run_replay(code, dict(params or {}), tape, stake=200.0, limits={"max_position_usd": 100.0, "max_order_usd": 75.0}, audit=True)


class TheStructureTapesReach(unittest.TestCase):
    """A structure tape keeps only the contracts its chain could reach (`OptionsHistory._structure_reach`): a strategy
    trading what it is shown replays on it exactly as on every bar (measured Sept 25, 2026 on the local copy too:
    options-strangle-cheap over SPY, QQQ and IWM, 314,650 bars kept of 463,277, 11 trades and every fill identical)."""

    def setUp(self):
        from league import options_history as oh

        self.oh = oh
        self.closes = closes_of(lambda n: 100.0 + n * 4.0 / 77)  # drifting from 100 to 104 over the three days
        self.store = reach_store(self, self.closes)

    def underlier(self, symbol, timeframe, start, end):
        return underlier_of(self.closes)(symbol, timeframe, start, end)

    def tape(self):
        needs = literal(CHAIN_WATCHER, "NEEDS")
        return self.store.tape(needs, "2026-03-02T00:00:00Z", "2026-03-04T23:00:00Z", horizon="day", underlier_bars=self.underlier,
                               warmup=5, execution="15Min", max_order_usd=75.0)

    def test_a_strategy_trading_what_it_is_shown_replays_on_the_kept_bars_exactly_as_on_all_of_them(self):
        from league import options_replay
        from league.replay import run_replay

        # A chain of 10 and a reach of 20 (the House's 80 and 160, scaled to 210 contracts): the reach is what binds.
        with mock.patch.object(options_replay, "STRUCTURE_CHAIN_PER_UNDERLYING", 10), mock.patch.object(self.oh, "STRUCTURE_REACH", 20):
            kept = self.tape()
            with mock.patch.object(self.oh.OptionsHistory, "_structure_reach", return_value=None):
                whole = self.tape()
            runs = [run_replay(CHAIN_WATCHER, {}, tape, stake=200.0, limits={"max_position_usd": 100.0, "max_order_usd": 75.0}, audit=True)
                    for tape in (kept, whole)]
        count = lambda tape: sum(len(step["options"]) for step in tape["steps"])  # noqa: E731
        self.assertLess(count(kept), 0.75 * count(whole))  # most contracts are never among the 20 nearest
        self.assertLess(len(kept["contracts"]), len(whole["contracts"]))
        self.assertEqual(kept["reached"]["contracts"], len(kept["contracts"]))
        first, second = runs
        self.assertTrue(first["ok"], first)
        self.assertEqual(first["final_memory"]["steps"], 78)
        self.assertGreater(first["final_memory"]["shown"], 0)
        self.assertEqual(first["options"]["structures"]["opened"], 1)
        self.assertEqual(first["options"]["structures"]["closed"], 1)
        for key in ("final_memory", "fill_log", "blocks", "trades", "return_pct", "fees_usd"):
            self.assertEqual(first[key], second[key], key)
        self.assertEqual((first["options"].pop("contracts_on_tape"), second["options"].pop("contracts_on_tape")),
                         (len(kept["contracts"]), len(whole["contracts"])))
        self.assertEqual(first["options"], second["options"])  # every count, the chain rows shown and the structures

    def test_every_price_on_a_tape_is_one_shared_object_and_the_same_number(self):
        tape = self.tape()
        prices = [bar[3] for step in tape["steps"] for bar in step["options"].values()]
        self.assertEqual(len({id(p) for p in prices}), len(set(prices)))
        self.assertTrue(all(type(bar[5]) is int and type(bar[4]) is float for step in tape["steps"] for bar in step["options"].values()))

    def test_the_bar_cap_drops_the_oldest_steps_before_any_of_their_bars_is_read(self):
        """The review of G-LOOP (Sept 25, 2026): applied after the build, a 150,000-bar cap still peaked at the uncapped
        tape's 184 MB. Now the reach counts what each step keeps, and the store is never asked for a bar the cap drops."""
        needs = literal(CHAIN_WATCHER, "NEEDS")
        whole, _ = two_tapes(self.store, self.closes, needs, whole=False)  # every bar the reach keeps: none capped
        total = sum(len(step["options"]) for step in whole["steps"])
        self.assertNotIn("bounded", whole)

        class Counting:  # the store's connection, noting the stamp of every option bar it hands the tape
            def __init__(self, db):
                self.db, self.read = db, []

            def execute(self, sql, *args):
                cursor = self.db.execute(sql, *args)
                return self.tee(cursor) if sql.startswith("SELECT occ, t, o, h, l, c, v, n FROM bars") else cursor

            def tee(self, cursor):
                for row in cursor:
                    self.read.append(row[1])
                    yield row

            def __getattr__(self, name):
                return getattr(self.db, name)

        counting = self.store._local.conn = Counting(self.store.db)  # this thread's connection (`OptionsHistory.db`)
        try:
            capped, _ = two_tapes(self.store, self.closes, needs, whole=False, max_option_bars=total // 2)
        finally:
            self.store._local.conn = counting.db
        bounded = capped["bounded"]
        kept = sum(len(step["options"]) for step in capped["steps"])
        self.assertEqual((bounded["option_bars"], bounded["kept"], bounded["max_option_bars"]), (total, kept, total // 2))
        self.assertLessEqual(kept, total // 2)
        self.assertEqual(capped["steps"][0]["t"], bounded["from"])
        self.assertTrue(counting.read and min(counting.read) >= bounded["from"], "a dropped step's bar was read")
        # The same tape the cap after the build gave: the newest steps, whole, and the older signal bars as warm-up.
        after = [step for step in whole["steps"] if step["t"] >= bounded["from"]]
        self.assertEqual([(step["t"], step["options"], step.get("quotes")) for step in capped["steps"]],
                         [(step["t"], step["options"], step.get("quotes")) for step in after])
        dropped = [bar for step in whole["steps"] if step["t"] < bounded["from"] for bar in (step.get("history_bars") or {}).get("SPY", [])]
        self.assertEqual(capped["warmup_bars"]["SPY"], (whole["warmup_bars"]["SPY"] + dropped)[-5:])
        self.assertEqual(set(capped["contracts"]), {occ for step in after for occ in step["options"]})

    def test_spy_carries_its_fridays_alone_until_every_expiry_is_ingested_across_the_window(self):
        """The review of G-LOOP (Sept 25, 2026): while the every-expiry backfill runs, a tape would show SPY's weekday
        expiries for part of its window and not the rest. Until `covers(every_expiry=True)`, the Fridays alone."""
        expiries = lambda tape: sorted({row["expiry"] for row in tape["contracts"].values()})  # noqa: E731
        self.assertEqual(expiries(self.tape()), list(EXPIRIES))  # a store with no coverage rows: taken as it is
        row = {"underlying": "SPY", "timeframe": "15Min", "start": "2026-03-01", "end": "2026-03-13", "status": "complete", "bars": 1}
        self.store.record_coverage({**row, "weekly_only": True})
        weekly = self.tape()
        self.assertEqual((expiries(weekly), weekly["every_expiry"]), (["2026-03-06"], {"SPY": False}))
        self.store.record_coverage({**row, "end": "2026-03-12", "weekly_only": False})
        every = self.tape()
        self.assertEqual((expiries(every), every["every_expiry"]), (list(EXPIRIES), {"SPY": True}))


#: The review of G-LOOP's demonstration (Sept 25, 2026), with a checksum of the chain it is shown at every step and the step
#: each contract in PARAMS["watch"] is first shown. At 15:00Z on March 2 (SPY at 100) it tries a 102/103 call debit vertical
#: and a 98/97 put debit vertical, 2% out of the money each side: legs it computed, as a width knob would, past the chain of
#: ten and the reach of twenty. At 15:00Z on March 3, after the move, it opens the chain's nearest March 4 call and the
#: strike past it, and sells that at 18:00Z.
FAR_LEGS = '''
NEEDS = {"venue": "alpaca", "horizon": "day", "style": "far-legs", "asset_class": "option", "structures": True,
         "symbols": ["SPY"], "bars": {"timeframe": "1Day", "limit": 5}, "max_days_to_expiry": 3}
PARAMS = {"watch": []}
CALL = [{"occ": "SPY260304C00102000", "role": "long"}, {"occ": "SPY260304C00103000", "role": "short"}]
PUT = [{"occ": "SPY260304P00098000", "role": "long"}, {"occ": "SPY260304P00097000", "role": "short"}]

def decide(ctx):
    mem = dict(ctx.get("memory") or {})
    shown = sorted(r["occ"] for r in ctx.get("chain") or [])
    sig = int(mem.get("sig") or 7)
    for ch in ctx["now"] + ":" + ",".join(shown):
        sig = (sig * 131 + ord(ch)) % 2305843009213693951
    first = dict(mem.get("first") or {})
    for occ in ctx["params"]["watch"]:
        if occ in shown and occ not in first:
            first[occ] = ctx["now"]
    mem["sig"], mem["first"] = sig, first
    out = []
    if ctx["now"] == "2026-03-02T15:00:00Z":
        for legs in (CALL, PUT):
            out.append({"structure": "debit_vertical", "action": "open", "quantity": 1, "legs": legs, "limit_price": 0.74, "reason": "far"})
    calls = [r for r in ctx.get("chain") or [] if r["right"] == "call" and r["expiry"] == "2026-03-04"]
    if ctx["now"] == "2026-03-03T15:00:00Z" and calls:
        near = min(calls, key=lambda r: (abs(r["strike"] - r["underlying_price"]), r["strike"]))
        wing = near["occ"][:-8] + str(int(near["occ"][-8:]) + 1000).zfill(8)
        mem["legs"] = [{"occ": near["occ"], "role": "long"}, {"occ": wing, "role": "short"}]
        out.append({"structure": "debit_vertical", "action": "open", "quantity": 1, "legs": mem["legs"], "limit_price": 0.74, "reason": "near"})
    if ctx["now"] == "2026-03-03T18:00:00Z" and mem.get("legs"):
        out.append({"structure": "debit_vertical", "action": "close", "quantity": 1, "legs": mem["legs"], "limit_price": 0.01, "reason": "t"})
    return {"intents": out, "memory": mem}
'''
FAR = ("SPY260304C00102000", "SPY260304C00103000", "SPY260304P00098000", "SPY260304P00097000")
OUTSIDE = ("outside the chain's reach: every leg of an open must be among the 20 contracts of its underlying nearest the money "
           "that the chain holds at this step (the House's rule live)")


class AFarLegIsJudgedByThePastAlone(unittest.TestCase):
    """The review of G-LOOP (Sept 25, 2026), its BLOCKER: a reach-filtered tape kept a far leg's bars only if the underlying
    LATER came near it, so the replay priced the winning side of two far verticals and refused the losing one, whichever
    way SPY went (reach tape 1 trade at +26%, whole tape 2 at +19%). Now an open's legs must be among the reach AT ITS STEP,
    live and in replay, and a contract is listed only from the step it first was: both tapes give the same replay, and
    nothing a strategy sees or may open at a step depends on where the market went after it."""

    def run_both(self, direction, code=FAR_LEGS):
        # Flat at 100 until 15:00Z on March 2, then 3 points in `direction` by that day's close, then flat.
        closes = closes_of(lambda n: 100.0 + (0.0 if n <= 1 else min(1.0, (n - 1) / 24.0) * 3.0 * direction))
        store = reach_store(self, closes)
        kept, whole = two_tapes(store, closes, literal(code, "NEEDS"))
        return kept, whole, replayed(code, kept, {"watch": list(FAR)}), replayed(code, whole, {"watch": list(FAR)})

    def test_both_far_verticals_are_refused_at_their_step_whichever_way_the_market_goes_after(self):
        for direction, came_near in ((1, FAR[:2]), (-1, FAR[2:])):
            with self.subTest(direction=direction):
                kept, whole, on_kept, on_whole = self.run_both(direction)
                self.assertTrue(on_kept["ok"], on_kept)
                for key in ("trades", "return_pct", "fill_log", "final_memory", "refusal_reasons", "blocks", "fees_usd"):
                    self.assertEqual(on_kept[key], on_whole[key], key)
                structures = on_kept["options"]["structures"]
                self.assertEqual(on_kept["refusal_reasons"].get(OUTSIDE), 2)
                self.assertEqual((structures["outside_reach_refusals"], structures["unseen_leg_refusals"]), (2, 0))
                self.assertEqual((structures["opened"], structures["closed"], on_kept["trades"]), (1, 1, 1))  # the near vertical
                self.assertEqual(structures, on_whole["options"]["structures"])
                # The legs the market came to were kept for their later reach, with bars from before it: never listed
                # before it, and first shown at the step they are on the whole tape.
                for occ in came_near:
                    reached = kept["contracts"][occ]["reached"]
                    first_bar = min(step["t"] for step in kept["steps"] if occ in step["options"])
                    self.assertLess(first_bar, "2026-03-02T15:00:01Z")  # it had a market when the far vertical was tried
                    self.assertGreater(reached, "2026-03-02T15:00:00Z")
                    self.assertGreaterEqual(on_kept["final_memory"]["first"][occ], reached)
                self.assertEqual(on_kept["final_memory"]["first"], on_whole["final_memory"]["first"])
                for occ in set(FAR) - set(came_near):
                    self.assertNotIn(occ, kept["contracts"])  # never among the reach: no bar kept

    def test_structures_is_read_as_the_house_reads_it_true_alone(self):
        """The review of G-LOOP (Sept 25, 2026): `"structures": 1` was a structure program in replay and a single-contract
        one live (`House.is_structure_agent`). Both read `True` alone now."""
        code = FAR_LEGS.replace('"structures": True', '"structures": 1')
        kept, _, on_kept, _ = self.run_both(1, code)
        self.assertNotIn("reached", kept)
        self.assertNotIn("structures", kept["chain_rules"])
        # the two far opens, the near one and its close: every structure intent, as the House refuses them live
        self.assertEqual(on_kept["refusal_reasons"].get('a structure intent is for a structure agent: its NEEDS carry "structures": true'), 4)
        self.assertNotIn("structures", on_kept["options"])


class TheStructureDays(StructureHouseCase):
    """A weekday expiry of SPY, QQQ or IWM is ingested from 14 days before it (`DAILY_MAX_DAYS`), so a structure program
    trading one of them is shown 10 days at most, live and in replay (the review of G-LOOP, Sept 25, 2026)."""

    def test_the_days_a_structure_program_is_shown(self):
        from league.options_history import DAILY_SHOWN_DAYS, structure_days

        self.assertEqual(DAILY_SHOWN_DAYS, 10)
        for asked, symbols, days in ((30, ["SPY"], 10), (30, ["F", "iwm"], 10), (30, ["F"], 30), (None, ["QQQ"], 7), (0, ["SPY"], 0),
                                     (60, ["F"], 45), (10, ["SPY"], 10), (30, ["F"] * 8 + ["SPY"], 30)):
            with self.subTest(asked=asked, symbols=symbols):
                self.assertEqual(structure_days(asked, symbols), days)

    def test_the_houses_chain_and_the_replays_hold_spy_to_ten_days(self):
        from decimal import Decimal
        from league.tests.test_options_replay import STRUCTURE_STRATEGY, socc, srun, sstep

        agent = self.house.spawn("krasker", "options-structures-test", STRUCTURE_AGENT.replace('"max_days_to_expiry": 7', '"max_days_to_expiry": 30'),
                                 reason="test", specialty="alpaca-options")
        asked = []
        with mock.patch.object(self.house, "_chain", side_effect=lambda symbols, days, *a, **k: asked.append(days) or []):
            self.house._structure_context(agent, {"quotes": {}}, ["SPY"], Decimal("75"), Decimal("100"))
        self.assertEqual(set(asked), {10})
        ten, seventeen = socc(585, "C", "261002"), socc(585, "C", "261009")  # 10 and 17 days after Sept 22
        prices = {ten: 1.0, seventeen: 1.5}
        strategy = STRUCTURE_STRATEGY.replace('"max_days_to_expiry": 7', '"max_days_to_expiry": 30')
        r = srun([sstep("2026-09-22T13:45:00Z", prices), sstep("2026-09-22T14:00:00Z", prices)], [ten, seventeen], strategy=strategy, open_at="never")
        self.assertEqual(r["final_memory"]["2026-09-22T14:00:00Z"]["chain"], [ten])


class TheLiveReach(StructureHouseCase):
    """The House refuses a structure OPEN whose legs are not all among the 160 nearest of the chain its wake read, as the
    replay does at its step (`House._structure_reach_refusal`; the review of G-LOOP, Sept 25, 2026)."""

    def test_an_open_past_the_reach_is_refused_and_a_close_never_is(self):
        from decimal import Decimal
        from league.tests.test_options import condor_row, fake_chain, occ

        self.broker.option_chain = fake_chain()  # SPY at 585.5: strikes 560-610 of three expiries, 306 contracts
        agent = self.structure_agent()
        book = self.house.book_of(agent)
        ctx = {"quotes": {"SPY": {"bid": 585.45, "ask": 585.55}}}
        self.house._structure_context(agent, ctx, ["SPY"], Decimal("75"), Decimal("100"))
        reach = self.house._structure_reach_seen[agent.id]
        self.assertEqual((len(ctx["chain"]), len(reach)), (80, 160))
        self.assertTrue({row["occ"] for row in ctx["chain"]} <= reach)
        legs = [{"occ": occ("2026-09-11", "put", 560), "role": "long"}, {"occ": occ("2026-09-11", "put", 561), "role": "short"},
                {"occ": occ("2026-09-11", "call", 609), "role": "short"}, {"occ": occ("2026-09-11", "call", 610), "role": "long"}]
        far = {**condor_row(), "legs": legs, "limit_price": 0.05}
        intents, dropped = self.house._intents(agent, book, [condor_row(), far, {**far, "action": "close", "limit_price": 0.90}])
        self.assertEqual(dropped, [])
        self.assertEqual([intent.side for intent in intents], ["buy", "sell"])  # the near condor's open and the far one's close
        (refusal,) = self.refusals(agent)
        self.assertTrue(refusal.startswith("outside the chain's reach: every leg of a structure you open must be among the 160"), refusal)
        self.assertIn(occ("2026-09-11", "put", 560), refusal)


if __name__ == "__main__":
    unittest.main()
