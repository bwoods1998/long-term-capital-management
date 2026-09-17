import unittest
from types import SimpleNamespace as Row
from ltcm.arena import execution_pulse


class ArenaPulseTests(unittest.TestCase):
    def test_shadow_activity_is_not_presented_as_real_trading(self):
        fill = lambda **p: Row(at="2026-09-17T05:30:00Z", payload={"instrument": {"venue": "coinbase"}, "side": "sell", **p})
        rows = [fill(), fill(shadow=True), fill(repair=True)]
        log = Row(read=lambda **kw: rows if kw["kind"] == "broker.fill" else [])
        desks = {"live": Row(id="live", live=True, market_venue="coinbase"), "shadow": Row(id="shadow", live=False, market_venue="coinbase")}
        store = Row(for_desk=lambda desk: {"test": {"enabled": desk == "shadow"}})
        pulse = execution_pulse(log, desks, store, "2026-09-17T06:00:00Z")
        row = pulse["venues"]["coinbase"]
        self.assertEqual((row["fills"], row["sells"], row["live_paused"], row["shadow_enabled"]), (1, 1, 1, 1))
        self.assertIn("1 real fills", pulse["message"])
