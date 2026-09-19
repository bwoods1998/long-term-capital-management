import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.broker import Balance

from league.publish import Publisher, clean, clean_text, event_id, money, to_events
from league.tests.fakes import Clock
from league.tests.test_house import BUYER, HouseCase

D = Decimal


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status = status
        self._body = json.dumps(body or {"stored": 1, "replayed": 0}).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeSite:
    def __init__(self):
        self.posts = []

    def __call__(self, request, timeout=None):
        body = json.loads(request.data)
        self.posts.append((request.full_url, dict(request.header_items()), body))
        return FakeResponse()


class RealAccount:
    def __init__(self, venue, equity, clock=None):
        self.venue, self.equity, self.clock = venue, D(equity), clock

    def balance(self):
        if self.clock is not None:
            self.clock.advance(0.4)  # a real venue read takes time: the checkpoint must be stamped after it
        return Balance(self.venue, self.equity, self.equity, self.equity, "2026-09-10T00:00:00.000Z")


class CleaningTest(unittest.TestCase):
    def test_text_the_site_would_refuse_is_made_safe(self):
        self.assertEqual(clean_text("see https://www.reuters.com/x and https://kalshi.com/fees"), "see [link removed] and https://kalshi.com/fees")
        self.assertNotIn("<", clean_text("<script>"))
        self.assertNotIn("sk-", clean_text("key sk-abc123"))
        self.assertEqual(clean_text("the data:5 rows"), "the data: 5 rows")
        self.assertEqual(clean_text("a\x00b"), "a b")

    def test_payload_keys_and_private_keys(self):
        self.assertEqual(clean({"ok": 1, "_code": "x", "BTC/USD": 2, "nested": {"_p": 1, "q": "<"}}), {"ok": 1, "nested": {"q": "‹"}})

    def test_money_is_plain_digits(self):
        self.assertEqual(money(D("1E+2")), "100.00")
        self.assertEqual(money(D("-0.004"), 2, signed=True), "0.00")
        self.assertEqual(money(D("-1.239"), 2, signed=True), "-1.24")
        self.assertEqual(money(D("-5")), "0.00")
        self.assertEqual(event_id("settle:kalshi:a1:crypto:BTC-USD:alpaca:BTC/USD"), "settle:kalshi:a1:crypto:BTC-USD:alpaca:BTC_USD")


class PublisherTest(HouseCase):
    def publisher(self, site, tape="test"):
        return Publisher(
            "https://blakewoods.us", lambda: "t" * 40, Path(self.dir.name) / "publish.json", tape=tape, opener=site, clock=self.clock,
            performance={"start_at": "2026-09-09T00:00:00.000Z", "start_equity": "1000"},
            real_brokers={"alpaca": RealAccount("alpaca", "500.10", self.clock), "kalshi": RealAccount("kalshi", "521.93", self.clock)},
        )

    def test_a_tick_becomes_a_tape_the_site_accepts(self):
        agent = self.seated()
        site = FakeSite()
        self.house.publisher = self.publisher(site)
        self.house.tick()
        urls = [u for u, _, _ in site.posts]
        self.assertTrue(all(u.startswith("https://blakewoods.us/api/capital/t/test/") for u in urls))
        self.assertEqual(urls[-1], "https://blakewoods.us/api/capital/t/test/checkpoint")
        events = [e for u, _, b in site.posts if u.endswith("/events") for e in b["events"]]
        kinds = {e["kind"] for e in events}
        self.assertLessEqual({"desk.thought", "broker.fill", "lab.progress", "floor.mark"}, kinds)
        for event in events:
            self.assertEqual(set(event), {"id", "stream", "kind", "at", "payload", "digest"})
            self.assertRegex(event["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
            self.assertRegex(event["id"], r"^[A-Za-z0-9:_.-]{1,200}$")
            self.assertRegex(event["digest"], r"^[a-f0-9]{64}$")
            family = event["stream"].split(":")[0]
            self.assertTrue(event["kind"].startswith(family + ".") or (event["kind"], event["stream"]) == ("floor.mark", "ops"))
        fill = next(e for e in events if e["kind"] == "broker.fill")
        self.assertEqual(fill["stream"], "broker:alpaca-paper")
        self.assertEqual(fill["payload"]["desk_id"], agent.id)
        self.assertIs(fill["payload"]["real_money"], False)
        mark = next(e for e in events if e["kind"] == "floor.mark")
        self.assertEqual(mark["payload"]["account_equity"], "1022.0300")  # the REAL accounts, never practice money
        checkpoint = site.posts[-1][2]
        self.assertEqual(checkpoint["floor"]["account_equity"], "1022.0300")
        for row in checkpoint["floor"]["venues"]:
            self.assertLessEqual(row["as_of"], checkpoint["published_at"])
        for desk in checkpoint["desks"]:
            self.assertLessEqual(desk["updated_at"], checkpoint["published_at"])
        desk = checkpoint["desks"][0]
        self.assertEqual((desk["id"], desk["mode"], desk["status"]), (agent.id, "shadow", "active"))
        self.assertEqual(desk["positions"][0]["thesis"], "test buy")
        self.assertEqual(checkpoint["lab"]["curve"][0]["generation"], 1)
        self.assertEqual(checkpoint["run"]["started_at"], self.house.ledger.read(kinds="ops.started", limit=1)[0].at)

    def test_a_closed_trade_is_published_with_its_reason(self):
        self.seated()
        self.house.tick()
        self.clock.advance(301)
        site = FakeSite()
        self.house.publisher = self.publisher(site)
        self.house.tick()
        outcomes = [e for u, _, b in site.posts if u.endswith("/events") for e in b["events"] if e["kind"] == "desk.outcome"]
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["payload"]["result"], "sold")
        self.assertEqual(outcomes[0]["payload"]["rationale_excerpt"], "test buy")
        self.assertIs(outcomes[0]["payload"]["real_money"], False)

    def test_nothing_is_sent_twice_and_private_rows_never_leave(self):
        self.seated()
        site = FakeSite()
        self.house.publisher = self.publisher(site)
        self.house.ledger.append("provider.request", {"cost": "0.01", "_prompt": "secret"}, agent="buyer")
        self.house.tick()
        first = [e["id"] for u, _, b in site.posts if u.endswith("/events") for e in b["events"]]
        site.posts.clear()
        self.house.publisher = self.publisher(site)  # a restart reads its cursor back
        self.house.tick()
        second = [e["id"] for u, _, b in site.posts if u.endswith("/events") for e in b["events"]]
        self.assertFalse(set(first) & set(second))
        self.assertNotIn("secret", json.dumps([b for _, _, b in site.posts]))
        self.assertFalse(any("provider" in i for i in first))

    def test_production_has_no_tape_prefix(self):
        site = FakeSite()
        publisher = self.publisher(site, tape=None)
        publisher.post("/events", {"schema_version": 1, "events": []})
        self.assertEqual(site.posts[0][0], "https://blakewoods.us/api/capital/events")
        self.assertEqual(site.posts[0][1]["Authorization"], "Bearer " + "t" * 40)


if __name__ == "__main__":
    unittest.main()
