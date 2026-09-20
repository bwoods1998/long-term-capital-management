import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.broker import Balance

from league.publish import Publisher, clean, clean_text, event_id, money, to_events
from league.ledger import now_iso
from league.pacer import Pacer
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
        self.assertEqual(mark["payload"]["account_equity"], "1000.0000")  # the league's basis: never practice money, and flat until the league trades real money
        checkpoint = site.posts[-1][2]
        self.assertEqual(checkpoint["floor"]["account_equity"], "1000.0000")
        for row in checkpoint["floor"]["venues"]:
            self.assertLessEqual(row["as_of"], checkpoint["published_at"])
        for desk in checkpoint["desks"]:
            self.assertLessEqual(desk["updated_at"], checkpoint["published_at"])
        desk = checkpoint["desks"][0]
        self.assertEqual((desk["id"], desk["mode"], desk["status"]), (agent.id, "shadow", "active"))
        self.assertEqual(desk["positions"][0]["thesis"], "test buy")
        self.assertEqual(checkpoint["lab"]["curve"][0]["generation"], 1)
        self.assertEqual(checkpoint["run"]["started_at"], self.house.ledger.read(kinds="ops.started", limit=1)[0].at)

    def test_total_profit_is_the_leagues_own_real_money_result_and_nothing_else(self):
        # Found on the first production day (Sept 19, 2026): the page showed -$4.57 of "profit" before
        # any real trade, because the contracts the first run left in the Kalshi account are marked
        # to market. What is not the league's doing is a flow, whatever it is.
        from league.publish import league_real_pnl

        class Flows:
            def read(self, accounts, at):
                return {"start_at": "2026-09-09T00:00:00.000Z", "start_equity": "1000", "net_flows": "0", "verified_at": at}

        self.seated()
        site = FakeSite()
        self.house.publisher = self.publisher(site)
        self.house.publisher._flows = Flows()
        self.house.tick()
        floor = site.posts[-1][2]["floor"]
        # The accounts are up $22.03 on the start and none of it is the league's: the chart's number does not move.
        self.assertEqual(floor["account_equity"], "1000.0000")
        self.assertNotIn("real_account_equity", floor)  # the site's schema is exact; the raw balance is on the ledger
        self.assertEqual(self.house.ledger.last("floor.mark").payload["real_account_equity"], "1022.0300")
        self.assertEqual(league_real_pnl(self.house), D(0))  # practice money is not profit either
        self.assertEqual(floor["performance"], {"start_at": "2026-09-09T00:00:00.000Z", "start_equity": "1000", "net_flows": "0", "verified_at": floor["performance"]["verified_at"]})
        self.assertEqual(D(floor["since_inception_pct"]), D(0))
        marks = [e for u, _, b in site.posts if u.endswith("/events") for e in b["events"] if e["kind"] == "floor.mark"]
        self.assertEqual({m["payload"]["account_equity"] for m in marks}, {"1000.0000"})  # a flat line
        # And with a real book that has made a dollar, a dollar is what is published.
        real = type("RealBook", (), {"real_money": True, "accounts": {"a1": type("A", (), {"staked": D(25)})(), "house": type("A", (), {"staked": D(0)})()},
                                     "equity": lambda self, name: {"a1": D("26.10"), "house": D("-0.10")}[name]})()
        self.house.books["alpaca"] = real
        try:
            self.assertEqual(league_real_pnl(self.house), D("1.00"))
        finally:
            del self.house.books["alpaca"]

    def test_a_mark_of_the_raw_balance_from_before_the_leagues_basis_is_not_published(self):
        from league.publish import to_events

        old = self.house.ledger.append("floor.mark", {"account_equity": "1021.9251", "account_cash": "997.76", "as_of": "2026-09-19T18:05:00.000Z", "venues": []})
        new = self.house.ledger.append("floor.mark", {"account_equity": "1017.3551", "real_account_equity": "1015.10", "account_cash": "997.76", "as_of": "2026-09-19T19:05:00.000Z", "venues": []})
        self.assertEqual(to_events(old), [])
        self.assertEqual([e["payload"]["account_equity"] for e in to_events(new)], ["1017.3551"])

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

    def test_the_generation_curve_keeps_losses_and_costs_after_the_ninth_death(self):
        oldest = self.seated("oldest")
        self.house.tick()
        self.clock.advance(301)
        self.house.tick()
        self.house.kill(oldest, "test")
        loss = self.house.books["alpaca-paper"].account(oldest.id).realized
        self.assertLess(loss, 0)
        for index in range(8):
            agent = self.house.registry.born(name=f"retired-{index}", family="test-family", code=BUYER,
                                              needs={"venue": "alpaca", "horizon": "hour", "style": "test"})
            self.house.economy.charge(agent.id, "1", "research tokens")
            self.house.registry.died(agent.id, "test")
        total_cost = sum((D(e.payload["usd"]) for e in self.house.ledger.iter(kinds="credit.charge")), D(0))
        body = self.publisher(FakeSite()).checkpoint(self.house)
        self.assertEqual(len(body["desks"]), 8)
        self.assertNotIn(oldest.id, {d["id"] for d in body["desks"]})
        row = body["lab"]["curve"][0]
        self.assertEqual(row["desks"], 9)
        self.assertEqual(row["pnl_usd"], money(loss, 4, signed=True))
        self.assertEqual(row["cost_usd"], money(total_cost, 4))
        self.assertGreater(row["decisions"], 0)

    def test_model_costs_exclude_other_compute_and_the_budget_uses_the_sail_meter(self):
        agent = self.seated()
        self.house.pacer = Pacer(self.house.ledger, clock=self.clock, expedition={
            "start": now_iso(self.clock)[:10], "days": 10, "sail_usd": "100", "openai_usd": "100", "front_load": "2",
        })
        self.house.economy.charge(agent.id, "1", "research tokens")
        self.house.ledger.append("ops.budget", {"what": "sail", "spent_usd": "5"})
        self.clock.advance(86400)
        for amount, what in (("2", "research tokens"), ("0.6", "sandbox seconds"), ("0.01", "web search"),
                             ("4", "frontier audit"), ("5", "merton's time")):
            self.house.economy.charge(agent.id, amount, what)
        self.house.ledger.append("ops.budget", {"what": "sail", "spent_usd": "3"})
        body = self.publisher(FakeSite()).checkpoint(self.house)
        run = body["run"]
        self.assertEqual(run["sail_model_spend_today_usd"], "2.0000")
        self.assertEqual(run["sail_model_spend_total_usd"], "3.0000")
        self.assertEqual(run["sail_spend_total_usd"], "8.0000")
        self.assertLess(D(run["sail_infra_spend_total_usd"]), D("0.7"))
        self.assertEqual(body["budget"]["spent_today_usd"], "3.0000")
        self.assertEqual(body["budget"]["cap_usd"], "21.11")

    def test_sail_cost_estimates_do_not_include_frontier_calls_without_a_balance_meter(self):
        for amount, what in (("2", "research tokens"), ("0.6", "sandbox seconds"),
                             ("0.01", "web search"), ("4", "frontier audit"), ("5", "merton's time")):
            self.house.economy.charge("test", amount, what)
        body = self.publisher(FakeSite()).checkpoint(self.house)
        self.assertEqual(body["run"]["sail_spend_total_usd"], "2.6100")
        self.assertEqual(body["budget"]["spent_today_usd"], "2.6100")

    def test_the_model_list_follows_recorded_or_configured_profiles(self):
        publisher = self.publisher(FakeSite())
        self.assertEqual(publisher.checkpoint(self.house)["run"]["models_used"], [])
        self.house.economy.charge("test", "0.1", "research tokens")
        self.assertEqual(publisher.checkpoint(self.house)["run"]["models_used"], ["DeepSeek V4 Pro"])
        self.house.ledger.append("provider.request", {"profile": "flash_flex", "cost_usd": "0.02"})
        self.house.ledger.append("merton.pass", {"role": "architect", "cost_usd": "0.5"})
        self.assertEqual(publisher.checkpoint(self.house)["run"]["models_used"], ["DeepSeek V4 Flash", "gpt-6-astra"])


if __name__ == "__main__":
    unittest.main()
