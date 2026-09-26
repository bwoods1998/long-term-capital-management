"""A defect of the Alpha Lab's queue (Sept 24, 2026, the close-the-gaps run).

mcentee-hddb4ae's three alpaca-megacaps submissions (12 names, 1Day, limit 260) failed every hour with
"alpaca stock bars: more than 60 pages; ask for a shorter window" and were re-queued at priority 0 for
ever (the A-lab builder's report); while they sat at the front of the queue the largest-group turn never
ran. An input the House will never fetch is unsupported input: the row is blocked. The invariant: a tape
that fails the same way hour after hour blocks its rows too, and a row that cannot be served now never
decides a batch's turn."""

from __future__ import annotations

from unittest.mock import patch

from league.lab import with_params
from league.tapes import TapeError
from league.tests.test_lab import KNOB
from league.tests.test_lab_step import StepCase

#: mcentee-hddb4ae's submissions as lab.sqlite held them at T0 (0df9a4fc..., 4e5514592..., 06fe16a9...).
MEGACAPS = "alpaca-megacaps"
TWELVE = ["AAPL", "AMD", "AMZN", "AVGO", "GOOGL", "META", "MSFT", "MU", "NVDA", "QCOM", "TSLA", "TSM"]
TOO_LONG = {"bars": {"limit": 260, "timeframe": "1Day"}, "horizon": "day", "style": "chip-demand-relay", "symbols": TWELVE,
            "venue": "alpaca", "wake_minutes": 60}


class TooLong(StepCase):
    def failing(self, message):
        real = self.house.tape_for

        def tape_for(needs):
            if needs.get("symbols") == TWELVE:
                raise TapeError(message)
            return real(needs)

        return patch.object(self.house, "tape_for", side_effect=tape_for)

    def test_a_row_asking_for_more_history_than_the_house_reads_is_blocked_not_requeued(self):
        ident = self.insert("0df9a4fc254707132cbba407", TOO_LONG, niche=MEGACAPS, origin="agent", priority=0)
        behind = self.queue(KNOB)
        with self.failing("alpaca stock bars: more than 60 pages; ask for a shorter window"):
            self.lab.step()
        row = self.candidate(ident)
        self.assertEqual(row["status"], "blocked")
        self.assertIn("unsupported input", row["error"])
        self.assertIn("shorter window", row["error"])
        self.assertEqual(self.candidate(behind)["status"], "evaluated")

    def test_a_tape_that_fails_the_same_way_for_hours_blocks_its_rows(self):
        """The invariant: an input that fails identically on every hourly build is unsupported, whatever it says;
        the count is kept in `meta`, so a restart does not start it again."""
        needs = {**TOO_LONG, "bars": {"limit": 60, "timeframe": "1Day"}}
        limit = int(self.lab.settings["tape_failures_before_block"])
        with self.failing("alpaca stock bars: HTTP 500 from the venue"):
            for n in range(limit - 1):
                with self.assertRaises(Exception) as caught:
                    self.lab._search_tape(needs)
                self.assertNotIn("unsupported input", str(caught.exception), n)
                self.clock.advance(3601)  # the failure is kept for the hour; the next build is an hour on
                if n == 2:
                    self.restart()
            with self.assertRaisesRegex(Exception, "unsupported input.*same way"):
                self.lab._search_tape(needs)
        self.assertEqual(len(self.alerts("warning", "failed the same way")), 1)

    def test_a_row_whose_tape_failed_this_hour_does_not_decide_the_batchs_turn(self):
        """While a submission that cannot be served sits at the front of the queue, the largest-group turn still runs."""
        self.house.game["lab"]["reserved_share"] = 0.5  # E1's turns: queue, reserved, largest (F1's third: test_lab_forward_first)
        self.insert("0df9a4fc254707132cbba407", {**TOO_LONG, "bars": {"limit": 30, "timeframe": "1Day"}}, niche=MEGACAPS,
                    origin="agent", priority=0)
        seed = self.queue(KNOB.replace('"symbols": ["BTC/USD"]', '"symbols": ["ETH/USD"]'), lineage="founder:seed")  # a tape of its own
        mutants = [self.lab.admit(with_params(KNOB, {"notional": 40.0 + n}), niche=self.niche, origin="param", author="house",
                                  lineage="founder:test") for n in range(4)]
        with self.failing("alpaca stock bars: HTTP 500 from the venue"):
            self.lab._batch_turn = 0
            first = self.lab._next_batch()  # queue order: the seed's tape
            self.assertEqual([r["id"] for r in first[2]], [seed])
            second = self.lab._next_batch()  # the largest group, although an agent's row fronts the queue
        self.assertEqual(sorted(r["id"] for r in second[2]), sorted(mutants))


if __name__ == "__main__":
    import unittest

    unittest.main()
