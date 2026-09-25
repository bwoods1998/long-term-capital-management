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


class TheHousesDailyRefresh(StructureHouseCase):
    """`House._refresh_options_history` ingests every expiry of SPY, QQQ and IWM for the options desk's replay, and
    backfills a symbol the store holds only weekly across the window once."""

    def test_spy_is_backfilled_with_every_expiry_once_and_the_rest_are_kept_current(self):
        from league import options_history as oh

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
#: chain of ten showed it -- and closes it at 16:30Z on the second.
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


class TheStructureTapesReach(unittest.TestCase):
    """A structure tape keeps only the contracts its chain could reach (`OptionsHistory._structure_reach`): a strategy
    trading what it is shown replays on it exactly as on every bar (measured Sept 25, 2026 on the local copy too:
    options-strangle-cheap over SPY, QQQ and IWM, 314,650 bars kept of 463,277, 11 trades and every fill identical)."""

    DAYS = ("2026-03-02", "2026-03-03", "2026-03-04")  # Monday to Wednesday, EST: the session is 14:30-21:00Z
    EXPIRIES = ("2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06")

    def setUp(self):
        import tempfile
        from league import options_history as oh

        self.oh = oh
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = oh.OptionsHistory(Path(folder.name) / "s.sqlite")
        self.addCleanup(self.store.close)
        self.closes = []  # (stamp, SPY) every 15 minutes, drifting from 100 to 104 over the three days
        for d, day in enumerate(self.DAYS):
            for k in range(26):
                stamp = datetime(int(day[:4]), int(day[5:7]), int(day[8:]), 14, 45, tzinfo=timezone.utc) + timedelta(minutes=15 * k)
                self.closes.append((stamp, round(100.0 + (d * 26 + k) * 4.0 / 77, 4)))
        rows, bars = [], []
        for expiry in self.EXPIRIES:
            for strike in range(90, 111):
                for right in ("C", "P"):
                    occ = f"SPY{expiry[2:4]}{expiry[5:7]}{expiry[8:]}{right}{strike * 1000:08d}"
                    rows.append((occ, "SPY", expiry, float(strike), "call" if right == "C" else "put", 100, "inactive", "x"))
                    for n, (stamp, spot) in enumerate(self.closes):
                        if stamp.strftime("%Y-%m-%d") > expiry or (strike + n) % 4 == 0:
                            continue  # expired; or a quiet interval with no print
                        inside = max(0.0, spot - strike) if right == "C" else max(0.0, strike - spot)
                        days = (datetime.fromisoformat(expiry + "T21:00:00+00:00") - stamp).total_seconds() / 86400
                        price = round(inside + 0.6 * (days + 0.2) ** 0.5 * 2.718 ** (-abs(strike - spot) / 3), 2) + 0.01
                        bars.append((occ, "15Min", stamp.strftime("%Y-%m-%dT%H:%M:%SZ"), price, price + 0.02, price - 0.01, price, 20.0, 4, price))
        self.store.db.executemany("INSERT INTO contracts VALUES (?,?,?,?,?,?,?,?)", rows)
        self.store.db.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?,?)", bars)
        self.store.db.commit()

    def underlier(self, symbol, timeframe, start, end):
        if timeframe == "1Day":
            return [{"t": f"{day}T05:00:00Z", "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.0, "v": 1e6} for day in ("2026-02-26", "2026-02-27")]
        return [{"t": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": spot, "h": spot, "l": spot, "c": spot, "v": 1e5}
                for stamp, spot in self.closes if start <= stamp.strftime("%Y-%m-%dT%H:%M:%SZ") <= end]

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


if __name__ == "__main__":
    unittest.main()
