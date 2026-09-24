"""The watch shows the seat market by evidence (S1-S4 of the close-the-gaps run, Sept 24, 2026).

`scripts/floor_watch.py` runs a read-only snippet on the House box and prints what the owner's plan asks to
be watched. The review of #245 found the seat line carried only the waiters and the displaceable count: the
seats holding no evidence (`seats_holding_none`), the desks' evidence clocks the grace follows, why a class
of waiter (the retained candidates too) was last refused a seat, and the House-sent sales stopped after three
identical refusals reached no operator. The snippet runs here against a state directory built for the test.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from league.ledger import Ledger

ROOT = Path(__file__).resolve().parents[2]


class SeatMarketLine(unittest.TestCase):
    def test_the_watch_shows_the_seats_holding_none_the_clocks_the_refusals_and_the_stopped_sales(self):
        from scripts import floor_watch

        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            ledger = Ledger(state / "ledger.sqlite")
            ledger.append("agent.born", {"venue": "kalshi", "founder": "house", "family": "weather-favorites"}, agent="mullins-30")
            ledger.close()
            seats = {"at": "2026-09-24T08:00:00Z", "waiters": {"graduates": 2, "retained": 1, "cards": 0, "strategies": 0},
                     "waiters_by_desk": {"kalshi-weather": 2}, "displaceable": 3, "never_traded_past_grace": 1,
                     "waiting_over_an_hour": True,
                     "seats_holding_none": {"count": 2, "ids": ["mullins-30", "hawkins-9"]},
                     "evidence_clocks": {"at": "2026-09-24T05:37:00Z", "hours": {"kalshi-weather": 31.8, "kalshi-attention": None}},
                     "last_refused_birth": {"retained": {"count": 1, "why": "none could be seated: their desks are full", "at": "t"}}}
            (state / "health.json").write_text(json.dumps({"at": "2026-09-24T08:00:00Z", "release": "r", "seats": seats}))
            refusal = {"why": "HTTP # order qty must be >= minimal qty", "quantity": "0.5", "count": 3, "order": "o-1",
                       "detail": "HTTP 403 order qty must be >= minimal qty of order 1", "at": "t", "epoch": 0}
            (state / "house.json").write_text(json.dumps({"wind_down_refusals": {"haghani-9": {"alpaca-paper": {"crypto:LINKUSD": refusal}}}}))
            run = subprocess.run([sys.executable, "-c", floor_watch.BOX_SNIPPET, "2026-09-24T00:00:00", str(state)],
                                 capture_output=True, text=True, timeout=120, cwd=ROOT)
            self.assertEqual(run.returncode, 0, run.stderr[-2000:])
            box = json.loads(run.stdout.strip().splitlines()[-1])
        block = box["blocks"]["seats"]
        self.assertEqual(block["seats_holding_none"], {"count": 2, "ids": ["mullins-30", "hawkins-9"]})
        self.assertEqual(block["evidence_clocks"], {"kalshi-weather": 31.8, "kalshi-attention": None})
        self.assertEqual(block["waiters"]["retained"], 1)
        self.assertIn("none could be seated", block["refused"]["retained"])
        self.assertEqual(len(box["blocks"]["wind_down_stopped"]), 1)
        text = floor_watch.render(box, {}, {})
        self.assertIn("holding none 2 ['mullins-30', 'hawkins-9']", text)
        self.assertIn("kalshi-weather", text)
        self.assertIn("haghani-9 alpaca-paper crypto:LINKUSD refused 3x", text)


if __name__ == "__main__":
    unittest.main()
