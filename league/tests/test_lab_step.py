"""D1 (Sept 24, 2026): the Alpha Lab's step failed every minute and nothing escalated.

From 23:21:59Z Sept 23 the step's alert read "the lab's step failed (IndexError: list index out of
range)" every 1-3 minutes (115 of them by 01:40Z), each step ending in about 0.09 s; the last batch
ran at 23:37:17Z. Reproduced from the T0 snapshot of `lab.sqlite` (01:42Z): the Luna child
4dac144a4a1bcace0863b8f3 on alpaca-crypto-alts asks for ADA/USD alone. The history store fetched
ADA/USD's whole range and holds bars only from 2026-02-01 (the House's own `data.coverage` row:
first_day 2026-02-01, 61 empty chunks, 7 done), so the development window of an hourly tape,
[2025-09-12, 2025-11-14), is fetched and empty. `House.tape_for` returned a tape with no steps,
`search_tape` cut it to none, and `Lab._search_tape` read `steps[0]` outside its guard: an
IndexError out of `_next_batch` on every step, before any batch, for as long as the row stayed at
the front of the queue (a poison pill: nothing ever moved it).

These tests hold the fix at that site, the rule that one candidate never stops the lab, and the
step's traceback and escalation.
"""

from __future__ import annotations

import hashlib
import json
from unittest.mock import patch

from league import lab as lab_module
from league.history import HistoryStore
from league.lab import Lab, LabError, _iso, static_literal
from league.tests.test_history import FakeAlpaca, _ingestor
from league.tests.test_house import IDLE
from league.tests.test_lab import DESK, KNOB, LabCase

#: The failing row, exactly as `lab.sqlite` held it at 01:42Z Sept 24 (candidate
#: 4dac144a4a1bcace0863b8f3, a Luna child of card:9b8d01dcb85a0d26, queued since 16:09:34Z).
ADA_ROW = "4dac144a4a1bcace0863b8f3"
ADA_NEEDS = {"bars": {"limit": 100, "timeframe": "15Min"}, "horizon": "hour",
             "parameter_rules": {"bounds": {"fast": [4, 16], "hold_bars": [4, 32], "notional_usd": [10, 35],
                                            "pullback_pct": [0.003, 0.02], "slow": [18, 60]}},
             "style": "ada-trend-pullback-maker", "symbols": ["ADA/USD"], "venue": "alpaca", "wake_minutes": 15}
ALTS = "alpaca-crypto-alts"


class StepCase(LabCase):
    def setUp(self):
        super().setUp()
        # Seeding is hourly and was not due at T0 (seeded at 01:08Z): a step seeds nothing here either.
        self.lab._set_meta("seeded_at", str(self.clock()))

    def history(self, symbols, timeframe, since, until, listed=None):
        """The House's history store, ingested as the live one is (the daily pass first)."""
        store = HistoryStore.at_root(self.house.root)
        try:
            ingest = _ingestor(store, FakeAlpaca(listed=listed or {}), workers=1)
            ingest.run(ingest.plan(list(symbols), ["1Day", timeframe], since, until))
        finally:
            store.close()

    def insert(self, ident, needs, *, niche=ALTS, origin="luna", priority=1, code=IDLE, age=3600.0):
        """A queued row as the store holds one (its `needs` column is what decides its tape)."""
        text = needs if isinstance(needs, str) else json.dumps(needs, sort_keys=True)
        self.lab._x("INSERT INTO candidates(id, code, code_sha256, params, needs, niche, venue, horizon, origin, author, lineage, parents,"
                    " idea, priority, created, status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'queued')",
                    (ident, code, hashlib.sha256((code + ident).encode()).hexdigest(), "{}", text, niche, "alpaca", "hour", origin,
                     origin, "card:9b8d01dcb85a0d26", "[]", "a queued row", priority, self.clock() - age))
        return ident

    def alerts(self, level=None, words=""):
        return [e for e in self.house.ledger.iter(kinds="ops.alert")
                if (level is None or e.payload.get("level") == level) and words in str(e.payload.get("text"))]

    def restart(self):
        """What a deploy does to the lab: its process, and with it every in-memory cache, is gone."""
        self.lab.close()
        self.lab = Lab(self.house, box=self.box, mutator=self.luna, leaper=self.sol)
        self.house.lab = self.lab
        self.addCleanup(self.lab.close)
        return self.lab


class TheFailingRow(StepCase):
    def test_the_failing_row_is_blocked_and_the_batches_behind_it_run(self):
        """The regression, from the failing state: the row's own NEEDS, the history store as it stood."""
        self.history(["ADA/USD"], "15Min", "2025-08-01", "2025-11-14", listed={"ADA/USD": "2026-02-01T00:00:00Z"})
        tape_id, tape = self.house.tape_for(ADA_NEEDS)
        self.assertEqual(tape["source"]["window"], ["2025-09-12", "2025-11-14"])
        self.assertEqual(tape["steps"], [])  # fetched and empty: not a gap in the store, so no TapeError either
        self.house._tapes.clear()
        self.insert(ADA_ROW, ADA_NEEDS)
        behind = self.queue(KNOB)
        out = self.lab.step()
        self.assertNotIn("error", out)
        self.assertEqual(self.alerts("warning", "step failed"), [])
        row = self.candidate(ADA_ROW)
        self.assertEqual(row["status"], "blocked")
        self.assertIn("unsupported input", row["error"])
        self.assertIn("no steps", row["error"])
        self.assertEqual(self.candidate(behind)["status"], "evaluated")
        self.assertGreaterEqual(out["batches"], 1)
        self.assertNotIn(tape_id, self.house._tapes)  # the House still keeps no tape only the lab asked for

    def test_a_tape_with_no_steps_is_unsupported_input_and_one_step_is_searched(self):
        needs = static_literal(KNOB, "NEEDS")
        empty = {"venue": "alpaca", "horizon": "hour", "steps": []}
        with patch.object(self.house, "tape_for", return_value=("alpaca:empty", empty)) as built:
            with self.assertRaisesRegex(LabError, "unsupported input.*no steps"):
                self.lab._search_tape(needs)
            with self.assertRaisesRegex(LabError, "no steps"):  # the answer is kept for the hour: no second build
                self.lab._search_tape(needs)
        self.assertEqual(built.call_count, 1)
        one = {"venue": "alpaca", "horizon": "hour", "steps": [{"t": "2026-09-10T00:00:00Z", "bars": {}}]}
        with patch.object(self.house, "tape_for", return_value=("alpaca:one", one)):
            ident, cut = self.lab._search_tape({**needs, "symbols": ["ETH/USD"]})
        self.assertTrue(ident.startswith("lab:"))
        self.assertEqual(len(cut["steps"]), 1)


class OneRowNeverStopsTheLab(StepCase):
    def test_a_row_whose_needs_or_tape_breaks_the_lab_is_blocked_and_the_step_goes_on(self):
        corrupt = self.insert("corrupt-needs", "{not json", age=7200)
        odd_needs = {**static_literal(KNOB, "NEEDS"), "symbols": ["ETH/USD"]}
        odd = self.insert("odd-tape", odd_needs, niche=DESK, age=7000)
        behind = self.queue(KNOB)
        real_tape, real_cut = self.house.tape_for, lab_module.search_tape

        def tape_for(needs):
            if needs.get("symbols") == ["ETH/USD"]:
                return "alpaca:odd", {"venue": "alpaca", "horizon": "hour", "odd": True,
                                      "steps": [{"t": f"2026-09-10T00:0{n}:00Z", "bars": {}} for n in range(3)]}
            return real_tape(needs)

        def cut(tape, fraction):  # the lab's own handling of one tape breaks, past `_search_tape`'s guard
            if tape.get("odd"):
                raise AttributeError("'str' object has no attribute 'get'")
            return real_cut(tape, fraction)

        with patch.object(self.house, "tape_for", side_effect=tape_for), patch("league.lab.search_tape", side_effect=cut):
            out = self.lab.step()
        self.assertNotIn("error", out)
        self.assertEqual(self.candidate(corrupt)["status"], "blocked")
        self.assertIn("JSONDecodeError", self.candidate(corrupt)["error"])
        self.assertEqual(self.candidate(odd)["status"], "blocked")
        self.assertIn("AttributeError", self.candidate(odd)["error"])
        self.assertEqual(self.candidate(behind)["status"], "evaluated")
        told = self.alerts("warning", "could not evaluate")
        self.assertEqual(len(told), 1)  # one warning for the step, naming the rows, with the first traceback
        self.assertEqual(set(told[0].payload["candidates"]), {corrupt, "odd-tape"})
        self.assertIn("Traceback", told[0].payload["_traceback"])
        self.assertNotIn("_traceback", told[0].to_public()["payload"])

    def test_more_broken_rows_than_the_cap_fail_the_step_rather_than_block_the_queue(self):
        """A defect that breaks every row is the lab's, not the rows': past `row_errors_per_step` the
        step fails loudly and the rest of the queue stays as it was."""
        self.house.game["lab"]["row_errors_per_step"] = 3
        rows = [self.insert(f"corrupt-{n}", "{not json", age=7200 - n) for n in range(5)]
        out = self.lab.step()
        self.assertIn("JSONDecodeError", out["error"])
        states = [self.candidate(r)["status"] for r in rows]
        self.assertEqual(states.count("blocked"), 3)
        self.assertEqual(states.count("queued"), 2)

    def test_a_result_the_lab_cannot_score_blocks_its_row_and_the_batch_is_kept(self):
        good, bad = self.queue(KNOB), self.queue(KNOB.replace("50.0", "40.0"))
        real = lab_module.score

        def score(result, tape, rules=None):
            if result.get("id") == bad:
                raise KeyError("blocks")
            return real(result, tape, rules)

        with patch("league.lab.score", side_effect=score):
            done = self.lab.evaluate_batch()
        self.assertEqual(done["candidates"], 1)
        self.assertEqual(self.candidate(good)["status"], "evaluated")
        self.assertEqual(self.candidate(bad)["status"], "blocked")
        self.assertIn("KeyError", self.candidate(bad)["error"])
        self.assertEqual(len(self.lab._q("SELECT * FROM batches")), 1)

    def test_a_failing_phase_does_not_stop_the_others(self):
        queued = self.queue(KNOB)
        with patch.object(self.lab, "royalties", side_effect=RuntimeError("the fee cursor is gone")), \
                patch.object(self.lab, "breed", side_effect=RuntimeError("a bad elite")), \
                patch.object(self.lab, "graduate", side_effect=RuntimeError("a birth broke")), \
                patch.object(self.lab, "forward_windows", return_value={"scored": 0}) as forward:
            out = self.lab.step()
        self.assertEqual(self.candidate(queued)["status"], "evaluated")  # royalties and breeding failed; the batch ran
        forward.assert_called_once()  # graduation failed; the forward windows ran
        self.assertEqual(out["error"], "RuntimeError: the fee cursor is gone")
        phases = [e.payload["phase"] for e in self.alerts("warning", "step failed")]
        self.assertEqual(phases, ["royalties", "breed", "graduate"])


class TheStepSaysWhy(StepCase):
    def test_the_alert_carries_the_traceback_privately_and_stats_carry_the_error(self):
        def deep(n):  # two functions in turn: format_exc() folds only a frame repeated in a row
            if n == 0:
                raise IndexError("list index out of range")
            return deeper(n - 1)

        def deeper(n):
            return deep(n)

        with patch.object(self.lab, "royalties", side_effect=lambda: deep(40)):
            out = self.lab.step()
        self.assertEqual(out["error"], "IndexError: list index out of range")
        alert = self.alerts("warning", "step failed")[-1]
        self.assertEqual(alert.payload["text"], "the lab's step failed (IndexError: list index out of range)")
        self.assertEqual(alert.payload["phase"], "royalties")
        trace = alert.payload["_traceback"]
        self.assertEqual(len(trace), 2000)  # the last 2,000 characters of traceback.format_exc()
        self.assertTrue(trace.rstrip().endswith("IndexError: list index out of range"))
        self.assertIn("in deep", trace)
        self.assertNotIn("_traceback", alert.to_public()["payload"])  # private: never published
        stats = self.lab.stats()
        self.assertEqual((stats["error"], stats["failures_in_a_row"], stats["failing_since"]),
                         ("IndexError: list index out of range", 1, None))
        self.assertEqual(self.lab.health()["error"], "IndexError: list index out of range")

    def test_five_failures_in_a_row_raise_one_error_and_a_success_clears_it(self):
        def boom():  # a new exception each step, as the floor raises them
            raise IndexError("list index out of range")

        def failing(lab):
            return patch.object(lab, "royalties", side_effect=boom)

        first = self.clock()
        with failing(self.lab):
            for _ in range(4):
                self.lab.step()
                self.clock.advance(60)
            self.assertEqual(self.alerts("error"), [])
            health = self.lab.health()
            self.assertEqual((health["failures_in_a_row"], health["failing_since"]), (4, None))
            self.lab.step()  # the fifth
            self.clock.advance(60)
        errors = self.alerts("error")
        self.assertEqual(len(errors), 1)
        self.assertIn("failed 5 times in a row since " + _iso(first), errors[0].payload["text"])
        self.assertIn("IndexError: list index out of range", errors[0].payload["text"])
        self.assertIn("Traceback", errors[0].payload["_traceback"])
        self.assertEqual(self.lab.health()["failing_since"], _iso(first))
        # A restart does not reset the count or the since-when: they are in the lab's own store.
        self.restart()
        self.assertEqual((self.lab.health()["failures_in_a_row"], self.lab.health()["failing_since"]), (5, _iso(first)))
        with failing(self.lab):
            self.lab.step()
            self.clock.advance(60)
            self.lab.step()
            self.clock.advance(60)
        self.assertEqual(len(self.alerts("error")), 1)  # one error for the run of failures, not one every five
        self.assertEqual(self.lab.stats()["failures_in_a_row"], 7)
        out = self.lab.step()
        self.assertNotIn("error", out)
        again = self.alerts("info", "works again")
        self.assertEqual(len(again), 1)
        self.assertIn("7 failures in a row since " + _iso(first), again[0].payload["text"])
        health = self.lab.health()
        self.assertEqual((health["failures_in_a_row"], health["failing_since"], health["error"]), (0, None, None))
        self.assertEqual(self.lab.stats()["error"], None)

    def test_a_few_failures_then_a_success_reset_quietly(self):
        with patch.object(self.lab, "royalties", side_effect=RuntimeError("once")):
            self.lab.step()
            self.lab.step()
        self.assertEqual(self.lab.health()["failures_in_a_row"], 2)
        self.lab.step()
        self.assertEqual(self.lab.health()["failures_in_a_row"], 0)
        self.assertEqual(self.alerts("info", "works again"), [])  # never escalated, so nothing to take back
        self.assertEqual(self.alerts("error"), [])


if __name__ == "__main__":
    import unittest

    unittest.main()
