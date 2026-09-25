"""The House's replay of a lab graduate is independent of the lab's forward selection (the F-lab review's open finding 2,
Sept 25, 2026).

F1 graduates a candidate only on a positive forward window: the steps of the House's own tape strictly after the hour its
code was frozen (`lab.forward_cut`). On Kalshi and the Alpaca desks not replayed on the history store the House then
replayed it on the same `tape_for` tape, whose last third -- the out-of-sample blocks the replay gate reads -- lies inside
that window once the tape is rebuilt after the freeze: the candidate was chosen on the data that was then meant to test
it. The House now cuts a lab graduate's replay tape at that hour (`House._lab_freeze_cut`, `House._tape_until`): the
replay ends where the forward window begins. A researcher's or a card's replay is never cut.
"""

from __future__ import annotations

import json
import math
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from league.house import House
from league.lab import candidate_id, forward_cut
from league.replay import run_replay
from league.tests.test_lab import KNOB, LabCase
from league.tests.test_replay import MKT, event, kalshi_tape, market, script, t_at

HOUR = 3600.0
MIDNIGHT = datetime(2026, 9, 10, tzinfo=timezone.utc).timestamp()  # the fake tape's first step


class LabGraduateReplayTest(LabCase):
    def capture(self):
        """Every tape the House hands the sandbox for a replay, in order."""
        tapes = []
        original = self.house.sandbox.replay

        def replay(agent_id, code, params, tape, **kw):
            tapes.append(tape)
            return original(agent_id, code, params, tape, **kw)

        return tapes, patch.object(self.house.sandbox, "replay", side_effect=replay)

    def test_a_graduates_replay_ends_where_its_forward_window_begins(self):
        # LabCase's clock stands `LAB_CLOCK_OFFSET` into the fake tape: frozen at 2026-09-11T11:26:40Z, the tape runs to
        # 2026-09-12T11:55Z.
        ident = self.queue(KNOB, origin="luna")
        self.lab.evaluate_batch()
        self.forward_wins(ident)
        self.clock.advance(3 * HOUR)
        cut = math.ceil(self.lab._frozen_at(self.candidate(ident)) / HOUR) * HOUR
        self.assertEqual(self.house._lab_freeze_cut(KNOB), cut)
        whole = self.house.tape_for(json.loads(self.candidate(ident)["needs"]))[1]
        tapes, replays = self.capture()
        with replays:
            out = self.lab.graduate()
        self.assertEqual(out[0]["state"], "born", out)
        (replayed,) = tapes
        self.assertEqual(replayed["steps"][-1]["t"], "2026-09-11T12:00:00Z")
        self.assertEqual(whole["steps"][-1]["t"], "2026-09-12T11:55:00Z", "the House's tape itself runs past the freeze")
        forward = forward_cut(whole, cut)
        self.assertTrue(forward and forward["steps"], "the forward window has steps")
        self.assertFalse({s["t"] for s in replayed["steps"]} & {s["t"] for s in forward["steps"]}, "no step in both")
        self.assertEqual(len(replayed["steps"]) + len(forward["steps"]), len(whole["steps"]))
        self.assertNotIn("replay_until", whole, "the cached tape is never mutated")

    def test_a_researchers_replay_and_code_the_lab_never_held_are_not_cut(self):
        agent = self.seated("sawtooth", KNOB)
        tapes, replays = self.capture()
        with replays:
            self.house._candidate_replay(agent, KNOB)  # a researcher's: no lineage
        self.assertEqual(tapes[-1]["steps"][-1]["t"], "2026-09-12T11:55:00Z")
        other = KNOB.replace("50.0", "51.0")
        self.assertEqual(self.lab._q("SELECT id FROM candidates WHERE id=?", (candidate_id(other),)), [])
        self.assertIsNone(self.house._lab_freeze_cut(other))

    def test_a_tape_with_nothing_after_the_cut_is_the_tape_itself_and_too_little_before_it_is_no_trial(self):
        tape = {"steps": [{"t": "2026-09-10T00:00:00Z"}, {"t": "2026-09-10T00:05:00Z"}, {"t": "2026-09-10T01:05:00Z"}]}
        same_id, same = self.house._tape_until("t1", tape, MIDNIGHT + 10 * HOUR)
        self.assertIs(same, tape)
        self.assertEqual(same_id, "t1")
        cut_id, cut = self.house._tape_until("t1", tape, MIDNIGHT + 10 * 60)
        self.assertEqual([s["t"] for s in cut["steps"]], ["2026-09-10T00:00:00Z", "2026-09-10T00:05:00Z"])
        self.assertTrue(cut_id.startswith("t1|until:2026-09-10T00:10:00"))
        with self.assertRaises(ValueError):
            self.house._tape_until("t1", tape, MIDNIGHT + 60)  # one step up to 00:01


class KalshiCutSettlesWhatClosedBeforeIt(unittest.TestCase):
    """The review of Deploy C (Sept 25, 2026): a Kalshi tape holds only markets that had settled when it was built, a step
    at each one's close and one at its settlement. Cut at the freeze hour, an hourly market closing at the cut and paying
    four minutes later never paid on the cut tape: a program holding it ended the replay `unresolved`, and the evaluator
    failed the graduate as a counted trial on a tape that could not show the settlement."""

    EARLY, LATER = "KXBTCD-26SEP1013-T80999.99", "KXBTCD-26SEP1015-T80999.99"

    def tape(self):
        rows = []
        for i in range(25):  # 13:00 to 15:00, a step every five minutes
            step = []
            if i * 5 < 30:
                step.append(market(.50, .51, ticker=self.EARLY, close=30))
            if i * 5 < 60:
                step.append(market(.50, .51, close=60))  # MKT closes at the cut, 14:00, and pays at 14:04
            elif i * 5 == 60:
                step.append(market(None, None, close=60, execution_only=True))  # its terminal row, as `KalshiData.tape` writes it
            step.append(market(.50, .51, ticker=self.LATER, close=120))
            rows.append(step)
        tape = kalshi_tape(rows, {MKT: "yes", self.EARLY: "yes", self.LATER: "no"})
        tape["settlements"] = {self.EARLY: t_at(32), MKT: t_at(64), self.LATER: t_at(121)}
        tape["meta"] = {"listed": 30, "scanned": 3, "kept": 3}
        for minute in (32, 64, 121):  # a settlement step, as the builder adds one
            tape["steps"].append({"t": t_at(minute), "markets": [], "execution_only": True})
        tape["steps"].sort(key=lambda s: s["t"])
        return tape

    def test_a_market_closed_by_the_cut_and_paid_after_it_is_left_off_the_cut_tape(self):
        tape = self.tape()
        until = datetime(2026, 9, 10, 14, 0, tzinfo=timezone.utc).timestamp()
        _, cut = House._tape_until("t", tape, until)
        self.assertEqual(cut["steps"][-1]["t"], "2026-09-10T14:00:00Z")
        plan = {"plan": {"0": [event("buy", 10), event("buy", 10, ticker=self.EARLY), event("buy", 10, ticker=self.LATER)]}}
        code = script(venue="kalshi")
        whole = run_replay(code, plan, tape)
        self.assertEqual((whole["ok"], whole["unresolved"], whole["trades"]), (True, 0, 3))
        short = run_replay(code, plan, cut)
        # The market that paid before the cut settles on it; the one still open at the cut is marked, never unresolved.
        self.assertEqual((short["ok"], short["unresolved"], short["trades"], short["open_positions"]), (True, 0, 1, 1))
        self.assertEqual(cut["unsettled_at_cut"], [MKT])
        self.assertFalse(any(row.get("market") == MKT for step in cut["steps"] for row in step["markets"]))
        self.assertEqual([row["market"] for row in cut["steps"][-1]["markets"]], [self.LATER], "its terminal row gone, the rest kept")
        self.assertTrue(next(s for s in cut["steps"] if s["t"] == t_at(32)).get("execution_only"), "a settlement step stays one")
        self.assertEqual((sorted(cut["results"]), cut["meta"]["kept"]), (sorted([self.EARLY, self.LATER]), 2))
        self.assertIn(MKT, tape["results"], "the cached tape is never mutated")
        self.assertTrue(any(row.get("market") == MKT for step in tape["steps"] for row in step["markets"]))

    def test_an_alpaca_tape_or_one_without_settlements_is_only_cut(self):
        tape = self.tape()
        del tape["settlements"]
        until = datetime(2026, 9, 10, 14, 0, tzinfo=timezone.utc).timestamp()
        _, cut = House._tape_until("t", tape, until)
        self.assertNotIn("unsettled_at_cut", cut)
        self.assertTrue(any(row.get("market") == MKT for step in cut["steps"] for row in step["markets"]))
