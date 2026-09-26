"""The live path's reads and writes through the gateway (`league/live/venue.py`), against answers in the shapes the
gateway returned on Sept 26, 2026 (numbers invented: the data licence forbids committing real quotes)."""

import json
import unittest
from decimal import Decimal

from league.live.venue import Account, MarketData, Rate, RateLimited, occ_parts, parse_time, quote_of, stock_price
from ltcm.adapters import GatewaySigner, VenueClient
from ltcm.data import TransportError

GATEWAY = "https://gateway.example"


class Transport:
    def __init__(self):
        self.routes = []   # (method, fragment, status, body)
        self.seen = []

    def route(self, method, fragment, status, body):
        self.routes.insert(0, (method, fragment, status, body))

    def request(self, method, url, *, headers=None, body=None, timeout=None):
        self.seen.append((method, url, dict(headers or {}), body))
        for m, fragment, status, answer in self.routes:
            if m == method and fragment in url:
                if isinstance(answer, Exception):
                    raise answer
                return status, {}, json.dumps(answer).encode() if answer is not None else b""
        return 404, {}, b'{"message": "not found"}'


def account(transport, venue="alpaca"):
    client = VenueClient(transport, gateway_url=GATEWAY, gateway=GatewaySigner("t" * 40), venue=venue)
    return Account(client, venue=venue)


class Orders(unittest.TestCase):
    def setUp(self):
        self.t = Transport()
        self.a = account(self.t)
        self.body = {"order_class": "mleg", "qty": "1", "type": "limit", "limit_price": "0.55", "time_in_force": "day",
                     "legs": [], "client_order_id": "lv-0000001-f"}

    def test_every_call_goes_to_the_gateway_with_the_bearer_token_only(self):
        self.t.route("GET", "/v2/account", 200, {"equity": "481.63", "last_equity": "482.01858051001", "options_buying_power": "481.6"})
        self.a.account()
        method, url, headers, _ = self.t.seen[0]
        self.assertEqual(url, f"{GATEWAY}/v1/alpaca/v2/account")
        self.assertEqual(headers["Authorization"], "Bearer " + "t" * 40)
        self.assertFalse(any(k.lower().startswith("apca") for k in headers))
        paper = account(self.t, "alpaca-paper")
        self.t.route("GET", "/v2/positions", 200, [])
        paper.positions()
        self.assertEqual(self.t.seen[-1][1], f"{GATEWAY}/v1/alpaca-paper/v2/positions")

    def test_a_submit_is_classified_by_who_answered(self):
        self.t.route("POST", "/v2/orders", 200, {"id": "abc", "status": "accepted", "client_order_id": "lv-0000001-f"})
        ok = self.a.submit(self.body, exit=False)
        self.assertTrue(ok.ok)
        self.assertEqual(self.t.seen[-1][2]["X-LTCM-Purpose"], "entry")
        # The venue refused: it reached the venue (the gateway counted it).
        self.t.route("POST", "/v2/orders", 403, {"code": 40310000, "message": "potential wash trade detected"})
        venue = self.a.submit(self.body, exit=True)
        self.assertEqual((venue.ok, venue.unknown, venue.sent), (False, False, True))
        self.assertIn("wash trade", venue.error)
        self.assertEqual(self.t.seen[-1][2]["X-LTCM-Purpose"], "exit")
        # The gateway refused before forwarding: `cap` names why, and even a 503 is then not an unknown outcome.
        self.t.route("POST", "/v2/orders", 503, {"error": "The real account's equity has not been read", "cap": "equity"})
        refused = self.a.submit(self.body, exit=False)
        self.assertEqual((refused.ok, refused.unknown), (False, False))
        self.assertEqual(refused.order, {"error": "The real account's equity has not been read", "cap": "equity"})
        # A 502 from the gateway ("did not answer") or no answer at all: unknown, looked up by client id.
        self.t.route("POST", "/v2/orders", 502, {"error": "The alpaca API did not answer."})
        self.assertTrue(self.a.submit(self.body, exit=False).unknown)
        self.t.route("POST", "/v2/orders", 0, TransportError("timed out"))
        self.assertTrue(self.a.submit(self.body, exit=False).unknown)

    def test_a_missing_order_is_none_and_a_found_one_is_its_row(self):
        self.assertIsNone(self.a.order_by_client_id("lv-0000009-f"))
        self.t.route("GET", "orders:by_client_order_id", 200, {"id": "abc", "client_order_id": "lv-0000009-f", "legs": []})
        self.assertEqual(self.a.order_by_client_id("lv-0000009-f")["id"], "abc")
        self.assertIn("nested=true", self.t.seen[-1][1])

    def test_the_request_budget_holds_entries_but_never_an_exit(self):
        a = account(self.t)
        a.rate = Rate(2)
        self.t.route("GET", "/v2/positions", 200, [])
        a.positions()
        a.positions()
        with self.assertRaises(RateLimited):
            a.positions()
        self.assertFalse(a.submit(self.body, exit=False).sent)
        self.t.route("DELETE", "/v2/orders/", 204, None)
        self.assertEqual(a.cancel("abc"), (True, ""))                    # a cancel takes risk off: always sent
        self.t.route("POST", "/v2/orders", 200, {"id": "x", "status": "new"})
        self.assertTrue(a.submit(self.body, exit=True).ok)               # so does an exit

    def test_activities_are_read_to_the_last_page(self):
        first = [{"id": f"2026092{i:02d}::a", "activity_type": "CSD", "net_amount": "1"} for i in range(100)]
        self.t.route("GET", "page_token=20260929", 200, [])
        self.t.route("GET", "/v2/account/activities", 200, first)
        rows = self.a.activities(["CSD", "CSW"], after="2026-09-26T06:25:30.000Z")
        self.assertEqual(len(rows), 100)
        self.assertIn("activity_types=CSD%2CCSW", self.t.seen[0][1])
        self.assertIn("direction=asc", self.t.seen[0][1])


class MarketReads(unittest.TestCase):
    def test_the_chain_is_read_to_its_last_page_and_parsed(self):
        t = Transport()
        client = VenueClient(t, gateway_url=GATEWAY, gateway=GatewaySigner("t" * 40), venue="alpaca")
        m = MarketData(client)
        page2 = {"snapshots": {"XSP260928C00765000": {"latestQuote": {"ap": 2.2, "as": 7, "bp": 2, "bs": 5, "t": "2026-09-28T13:45:00.123456789Z"}}},
                 "next_page_token": None}
        page1 = {"snapshots": {"XSP260928P00760000": {"latestQuote": {"ap": 1.5, "as": 4, "bp": 0, "bs": 0, "t": "2026-09-28T13:45:00Z"}}},
                 "next_page_token": "WFNQ"}
        t.route("GET", "/v1beta1/options/snapshots/XSP", 200, page1)
        t.route("GET", "page_token=WFNQ", 200, page2)          # checked first: the later route wins
        rows = m.chain("XSP", expiry_from="2026-09-28", expiry_to="2026-09-28", strike_from=760.0, strike_to=770.0)
        self.assertEqual(sorted(rows), ["XSP260928C00765000", "XSP260928P00760000"])
        url = t.seen[0][1]
        self.assertTrue(url.startswith(f"{GATEWAY}/v1/alpaca/v1beta1/options/snapshots/XSP?"))
        for part in ("feed=opra", "limit=1000", "expiration_date_gte=2026-09-28", "strike_price_gte=760.000"):
            self.assertIn(part, url)
        bid, ask, bs, as_, t_ = quote_of(rows["XSP260928P00760000"])
        self.assertEqual((bid, ask, bs, as_), (0.0, 1.5, 0, 4))
        self.assertEqual(t_, parse_time("2026-09-28T13:45:00+00:00"))

    def test_the_underlying_is_this_sessions_trade_else_its_quote(self):
        row = {"latestTrade": {"p": "771.35", "t": "2026-09-28T13:31:00.001700549Z"}, "latestQuote": {"ap": "772.04", "bp": 772, "t": "2026-09-28T13:31:01Z"}}
        opened = parse_time("2026-09-28T13:30:00Z")
        self.assertEqual(stock_price(row, not_before=opened), 771.35)
        stale = {"latestTrade": {"p": "771.35", "t": "2026-09-26T00:00:00Z"}, "latestQuote": {"ap": "772.04", "bp": 772, "t": "2026-09-28T13:31:01Z"}}
        self.assertAlmostEqual(stock_price(stale, not_before=opened), 772.02)
        self.assertNotEqual(stock_price({"latestTrade": {"p": 1, "t": "2026-09-25T00:00:00Z"}}, not_before=opened),
                            stock_price({"latestTrade": {"p": 1, "t": "2026-09-25T00:00:00Z"}}, not_before=opened))  # NaN

    def test_times_and_symbols(self):
        self.assertEqual(parse_time("2026-09-25T19:59:59.991425952Z"), parse_time("2026-09-25T19:59:59.991425Z"))
        self.assertIsNone(parse_time("2026-09-25T19:59:59"))            # no zone: never this machine's local time
        self.assertEqual(occ_parts("SPXW260928C07700000"), ("SPXW", "2026-09-28", True, 7700.0))
        self.assertIsNone(occ_parts("SPY"))
        self.assertIsNone(occ_parts("XYZ1261016P00005000"))


if __name__ == "__main__":
    unittest.main()
