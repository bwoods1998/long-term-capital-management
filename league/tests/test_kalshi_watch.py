"""The Kalshi-scale run's watch (`scripts/kalshi_watch.py`) reads what it says it reads.

docs/goals/LTCM_KALSHI_SCALE.md, workstreams W, K3 and K4 (Sept 25, 2026). The snippet runs here against
a throwaway state directory built for the test: real and practice fills and settlements by family and
league, the House's dust rows kept out of the trades (five of them on the real Kalshi book between 18:00Z
Sept 24 and 06:20Z Sept 25, `source: dust`, no instrument), refusals by class, the hours with and without a
live desk, the model-versus-market founders, capacity and the data requests.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from league.ledger import Ledger
from league.tests.fakes import Clock
from scripts import kalshi_watch


def _instrument(market, right="no", venue="kalshi"):
    return {"asset_class": "event", "market_id": market, "symbol": market, "right": right, "venue": venue}


class TheBoxSnippet(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.clock = Clock()
        self.ledger = Ledger(self.root / "ledger.sqlite", clock=self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def run_snippet(self, since, until="", board=None, health=None):
        (self.root / "health.json").write_text(json.dumps(health or {"at": "t", "release": "r"}), encoding="utf-8")
        (self.root / "allocator-board.json").write_text(json.dumps(board or {}), encoding="utf-8")
        done = subprocess.run([sys.executable, "-c", kalshi_watch.BOX_SNIPPET, since, until, str(self.root)],
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        return json.loads(done.stdout.strip().splitlines()[-1])

    def test_money_by_family_and_league_with_dust_kept_out(self):
        self.ledger.append("agent.born", {"venue": "kalshi", "family": "sports-central-run-under"}, agent="meriwether-h2d625d")
        self.ledger.append("agent.born", {"venue": "kalshi", "family": "sports-consensus-ncaaf", "founder": "consensus-ncaaf"},
                           agent="meriwether-70")
        since = kalshi_watch.parser().parse_args(["--since", self.ledger.append("ops.started", {}).at]).since
        self.clock.advance(60)
        market = "KXMLBTOTAL-26SEP251805CHCBOSG2-9"
        self.ledger.append("book.order", {"book": "kalshi", "order_id": "o1", "instrument": _instrument(market), "post_only": False,
                                          "shares": [{"agent": "meriwether-h2d625d", "quantity": "10"}]}, agent="house")
        self.ledger.append("book.fill", {"book": "kalshi", "cash_delta": "-5.10", "liquidity": "taker", "instrument": _instrument(market),
                                         "real_money": True}, agent="meriwether-h2d625d")
        self.ledger.append("book.fill", {"book": "kalshi", "cash_delta": "-0.0003", "instrument": None, "source": "dust",
                                         "real_money": True}, agent="house")
        self.ledger.append("book.settle", {"book": "kalshi", "pnl": "4.90", "instrument": _instrument(market), "real_money": True},
                           agent="meriwether-h2d625d")
        game = "KXNCAAFGAME-26SEP26TEXTENN-TEX"
        self.ledger.append("book.fill", {"book": "kalshi-shadow", "cash_delta": "-6.30", "liquidity": "maker",
                                         "instrument": _instrument(game, "yes", "kalshi-shadow")}, agent="meriwether-70")
        self.ledger.append("agent.woke", {"book": "kalshi-shadow", "offered": 42, "intents": 2}, agent="meriwether-70")
        self.ledger.append("agent.thought", {"thought": "NCAAF: 42 markets priced off the consensus; best edge 5c."}, agent="meriwether-70")
        out = self.run_snippet(since)
        real = dict(out["real"]["family"])
        self.assertEqual(real["sports-central-run-under"]["orders"], 1)
        self.assertEqual(real["sports-central-run-under"]["taking"], 1)
        self.assertEqual(real["sports-central-run-under"]["fills"], 1)
        self.assertEqual(real["sports-central-run-under"]["settled"], 1)
        self.assertEqual(real["sports-central-run-under"]["pnl"], 4.9)
        self.assertNotIn("?", real, "a dust row is not a trade")
        self.assertAlmostEqual(out["dust_usd"], -0.0003)
        self.assertEqual(dict(out["real"]["league"])["mlb"]["events"], 1)
        self.assertEqual(dict(out["practice"]["league"])["ncaaf"]["maker_fills"], 1)
        founder = out["founders"]["meriwether-70"]
        self.assertEqual((founder["founder"], founder["wakes"], founder["offered_max"], founder["intents"]), ("consensus-ncaaf", 1, 42, 2))
        self.assertIn("best edge", founder["thought"][1])
        text = kalshi_watch.render(out)
        self.assertIn("## real by league", text)
        self.assertIn("consensus-ncaaf", text)

    def test_refusals_by_class_and_hours_without_a_live_desk(self):
        from scripts.floor_watch import normalize_since

        since = normalize_since(self.ledger.append("ops.started", {}).at)
        self.clock.advance(30)
        self.ledger.append("book.refused", {"book": "kalshi", "instrument": _instrument("KXBTCD-26SEP2503-T84499.99"),
                                            "reasons": ["one event may hold at most 25% of the stake: ... (constitution allocator.max_event_share)"]},
                           agent="hilibrand-lc04657")
        self.ledger.append("book.refused", {"book": "kalshi", "instrument": _instrument("KXMLBTOTAL-26SEP251805CHCBOSG2-7"),
                                            "reasons": ["a real entry on x must be a post-only limit until the family's pooled taker record is positive"]},
                           agent="meriwether-h7d7702")
        self.ledger.append("book.refused", {"book": "kalshi", "instrument": _instrument("KXRAIN-26SEP25-CMH"),
                                            "reasons": ["this market is expected to resolve in 52 hours, by its scheduled expiration"]},
                           agent="mullins-6")
        self.ledger.append("agent.woke", {"book": "kalshi", "offered": 3, "intents": 1}, agent="hilibrand-lc04657")
        self.clock.advance(2 * 3600)
        self.ledger.append("agent.woke", {"book": "kalshi", "offered": 0, "intents": 0}, agent="mullins-6")
        self.clock.advance(5)
        until = normalize_since(self.ledger.append("ops.started", {}).at)
        out = self.run_snippet(since, until)
        self.assertEqual(dict(out["refusals"]["real"]), {"per-event cap": 1, "maker-only": 1, "horizon": 1})
        hours = [row[0] for row in out["coverage"]]
        self.assertEqual(len(hours), 3)
        self.assertEqual(out["coverage"][0][2], 1, "the first hour had a real agent offered a market")
        self.assertEqual(out["hours_without_live_desk"], hours[1:], "no wake, and a wake with nothing offered, are hours with no live desk")

    def test_capacity_counts_the_proven_families_and_the_envelope(self):
        since = "2026-01-01T00:00:00"
        board = {"at": "2026-09-25T06:03:51Z", "envelope": {"kalshi": {"capital_usd": "546.83", "committed_usd": "109.23"}},
                 "agents": {"meriwether-h2d625d": {"venue": "kalshi", "band": "bunt", "family": "sports-central-run-under",
                                                   "stake_usd": "16.62", "equity_usd": "38.78"}},
                 "families": {"kalshi": {
                     "sports-central-run-under": {"state": "proven", "proven": True, "n": 26, "bound": 0.092, "mean_log": 0.27,
                                                  "real": {"n": 12, "bound": 0.093}, "capacity": {"size_usd": 6.0, "fill_rate_at_size": 1.0,
                                                  "markets_per_day": 19.3, "usd_per_day": 31.7}, "stake_usd": "30"},
                     "sports-central-over-under": {"state": "unproven", "proven": False, "n": 8, "mean_log": 1.0,
                                                   "capacity": {"usd_per_day": 22.8}},
                     "crypto-15m-lab-335592": {"state": "unproven", "proven": False, "n": 64, "mean_log": -0.01,
                                               "capacity": {"usd_per_day": -0.4}}}}}
        out = self.run_snippet(since, board=board, health={"at": "t", "shards": {"balances": {"0": "346.52", "3": "76.98"}}})
        self.assertEqual([row[0] for row in out["capacity"]], ["sports-central-run-under", "sports-central-over-under"])
        self.assertEqual(out["proven_capacity_usd_day"], 31.7)
        self.assertEqual(out["envelope"]["committed"], "109.23")
        self.assertEqual(out["real_agents"], [["meriwether-h2d625d", "bunt", "sports-central-run-under", "16.62", "38.78"]])
        self.assertEqual(out["shards"]["balances"]["3"], "76.98")


if __name__ == "__main__":
    unittest.main()
