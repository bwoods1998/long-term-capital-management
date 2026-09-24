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

These tests hold the fix at that site.
"""

from __future__ import annotations

import hashlib
import json
from unittest.mock import patch

from league.history import HistoryStore
from league.lab import LabError, static_literal
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


if __name__ == "__main__":
    import unittest

    unittest.main()
