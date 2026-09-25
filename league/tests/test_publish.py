import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import urllib.error
from decimal import Decimal
from pathlib import Path

from ltcm.broker import Balance

from league import publish
from league.publish import Publisher, clean, clean_text, event_id, money, to_events
from league.ledger import HOUSE, now_iso
from league.pacer import Pacer
from league.tests.fakes import Clock
from league.tests.test_house import BUYER, HouseCase
from league.tests.test_lab import KNOB, LOSER, LabCase

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

    def test_limits_count_as_the_site_counts_so_an_emoji_never_pushes_text_past_them(self):
        # The site measures JavaScript length (UTF-16 units): an emoji is two there, one in Python.
        self.assertEqual(publish.js_length("📉"), 2)
        self.assertEqual(publish.js_length("a‹é"), 3)
        cut = clean_text("📉" * 400, 300)
        self.assertEqual((len(cut), publish.js_length(cut)), (150, 300))
        odd = clean_text("a" + "📉" * 400, 300)
        self.assertEqual(odd, "a" + "📉" * 149, "a character is never split: 299 units, not a lone half of a pair")
        mixed = clean_text(("drawdown 📉 after the veto; " * 40), 240)
        self.assertLessEqual(publish.js_length(mixed), 240)
        self.assertTrue(("drawdown 📉 after the veto; " * 40).startswith(mixed))
        self.assertEqual(publish.js_length(clean_text("🚀" * 9000)), 8000, "payload strings: the site's 8000 is units too")
        self.assertEqual(clean_text("plain text", 300), "plain text")
        self.assertEqual(clean_text("x" * 301, 300), "x" * 300)

    def test_payload_keys_and_private_keys(self):
        self.assertEqual(clean({"ok": 1, "_code": "x", "BTC/USD": 2, "nested": {"_p": 1, "q": "<"}}), {"ok": 1, "nested": {"q": "‹"}})

    def test_money_is_plain_digits(self):
        self.assertEqual(money(D("1E+2")), "100.00")
        self.assertEqual(money(D("-0.004"), 2, signed=True), "0.00")
        self.assertEqual(money(D("-1.239"), 2, signed=True), "-1.24")
        self.assertEqual(money(D("-5")), "0.00")
        self.assertEqual(event_id("settle:kalshi:a1:crypto:BTC-USD:alpaca:BTC/USD"), "settle:kalshi:a1:crypto:BTC-USD:alpaca:BTC_USD")


class PublisherTest(HouseCase):
    def test_ladder_checkpoint_has_recorded_moves_and_does_not_endorse_tainted_pnl(self):
        from unittest.mock import patch

        agent = self.seated()
        self.house.tick()
        publisher = self.publisher(FakeSite())
        row = publisher.checkpoint(self.house)["desks"][0]
        self.assertIsNone(row["gate"]["evidence"]["lifecycle"]["last_move"], "initial seating is not a performance promotion")
        self.assertTrue(row["gate"]["evidence"]["accounting_ok"])
        # This fixture has only fake brokers. It tests the public projection, not eligibility.
        self.house.evaluator.promote(agent.id, 2, "fixture evidence")
        self.house.evaluator.demote(agent.id, "fixture drift")
        book = self.house.book_of(agent)
        with patch.object(book, "evidence_integrity", return_value={"ok": False}):
            row = publisher.checkpoint(self.house)["desks"][0]
        evidence = row["gate"]["evidence"]
        self.assertFalse(evidence["accounting_ok"])
        self.assertEqual(evidence["lifecycle"]["born_at"], agent.born_at)
        self.assertEqual(evidence["lifecycle"]["last_move"]["decision"], "demote")
        self.assertEqual(evidence["lifecycle"]["last_move"]["from_rung"], 2)
        self.assertEqual(evidence["lifecycle"]["last_move"]["to_rung"], 1)
        self.house.registry.died(agent.id, "fixture death")
        row = publisher.checkpoint(self.house)["desks"][0]
        self.assertEqual(row["gate"]["evidence"]["lifecycle"]["died_at"], agent.died_at)
        self.assertEqual(row["gate"]["evidence"]["lifecycle"]["cause"], "fixture death")

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
        self.clock.advance(float(self.house.settings.publish_seconds))  # the site is checkpointed once a minute (H5)
        self.house.tick()
        self.assertTrue(site.posts)
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

    def test_the_roster_never_exceeds_the_sites_desk_limit(self):
        # Sept 23, 2026: 96 living + the last 8 dead = 104 rows, and the site refused every checkpoint.
        from league import publish

        for index in range(6):
            agent = self.house.registry.born(name=f"gone-{index}", family="test-family", code=BUYER,
                                              needs={"venue": "alpaca", "horizon": "hour", "style": "test"})
            self.house.registry.died(agent.id, "test")
        living = [self.house.registry.born(name=f"alive-{index}", family="test-family", code=BUYER,
                                           needs={"venue": "alpaca", "horizon": "hour", "style": "test"}) for index in range(5)]
        old_max, old_dead = publish.MAX_DESKS, publish.MAX_DEAD_SHOWN
        try:
            publish.MAX_DESKS, publish.MAX_DEAD_SHOWN = 7, 8
            body = self.publisher(FakeSite()).checkpoint(self.house)
            ids = [d["id"] for d in body["desks"]]
            self.assertEqual(len(ids), 7)
            self.assertTrue({a.id for a in living} <= set(ids), "the living are shown before the dead")
            self.assertEqual(len(set(ids)), len(ids))
            publish.MAX_DESKS = 4
            body = self.publisher(FakeSite()).checkpoint(self.house)
            self.assertEqual(len(body["desks"]), 4)
            self.assertTrue(all(d["status"] == "active" for d in body["desks"]))
            # the generation curve still counts every agent ever born, up to the site's own counter bound
            # (its MAX_DESKS, simulated at 4 here; `BoardTest` checks the whole count at the real 160)
            self.assertEqual(sum(row["desks"] for row in body["lab"]["curve"]), min(11, publish.MAX_DESKS))
        finally:
            publish.MAX_DESKS, publish.MAX_DEAD_SHOWN = old_max, old_dead

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


class CheckpointFoldsTest(HouseCase):
    """Sept 24, 2026 (R6-perf): the checkpoint summed the whole ledger on every tick (every charge twice,
    every model request, each agent's every verdict, the newest 10,000 wakes: about 250,000 rows a tick on
    a copy of the 17:27Z snapshot). It folds them once and then reads only the new rows; the body is the
    one a publisher reading the whole ledger afresh draws."""

    FOLDED = ("credit.charge", "ops.budget", "provider.request", "merton.pass", "audit.verdict", "agent.woke",
              "agent.intent", "eval.verdict")

    def rows(self, agents):
        ledger = self.house.ledger
        today, yesterday = now_iso(self.clock)[:10], now_iso(lambda: self.clock() - 86400)[:10]
        for i, agent in enumerate(agents):
            for what, usd in (("tokens: research", "0.0123"), ("sandbox seconds", "0.004"), ("web search", "0.01"), ("merton", "0.25")):
                ledger.append("credit.charge", {"usd": str(D(usd) * (i + 1)), "what": what}, agent=agent.id)
            ledger.append("credit.charge", {"usd": "0.5", "what": "tokens: yesterday"}, agent=agent.id, at=yesterday + "T10:00:00.000Z")
            ledger.append("agent.intent", {"book": "alpaca-paper"}, agent=agent.id)
            ledger.append("agent.woke", {"ok": True, "book": "alpaca-paper"}, agent=agent.id)
            ledger.append("eval.verdict", {"decision": "look", "look": i + 1, "active_blocks": 3, "mean": 0.01, "lcb": -0.01,
                                           "ucb": 0.03, "alpha_spent": 0.001, "drawdown": 0.02 * (i + 1)}, agent=agent.id)
        ledger.append("agent.woke", {"ok": True}, agent=agents[0].id, at=yesterday + "T23:59:00.000Z")
        ledger.append("ops.budget", {"what": "sail", "spent_usd": "0.31", "balance_usd": 100}, at=today + "T00:10:00.000Z")
        ledger.append("ops.budget", {"what": "sail", "spent_usd": "1.20"}, at=yesterday + "T12:00:00.000Z")
        ledger.append("ops.budget", {"what": "expedition", "spent_usd": "9.99"})  # not the Sail meter: not in the sums
        ledger.append("provider.request", {"profile": "flash_flex", "_body": "private"})
        ledger.append("merton.pass", {"role": "teacher", "cost_usd": "0"})

    def publisher(self, name):
        return Publisher("https://blakewoods.us", lambda: "t" * 40, Path(self.dir.name) / f"{name}.json", tape="test",
                         opener=FakeSite(), clock=self.clock)

    def body(self, publisher):
        return json.loads(json.dumps(publisher.checkpoint(self.house), default=str))

    def test_new_rows_are_folded_onto_the_old_sums_and_the_body_is_a_fresh_read_s(self):
        from unittest.mock import patch

        first, second = self.seated("first"), self.seated("second", code=BUYER.replace("test-buyer", "test-second"))
        self.rows([first, second])
        standing = self.publisher("standing")
        before = self.body(standing)
        self.assertEqual(before, self.body(self.publisher("fresh-before")))
        self.house.tick()
        self.rows([second, first])  # every folded kind again, after the standing publisher's cursor
        self.house.evaluator.promote(first.id, 2, "fixture evidence")
        self.house.evaluator.demote(first.id, "fixture drift")
        self.house.ledger.append("provider.request", {"profile": "pro_flex"})
        self.house.ledger.append("audit.verdict", {"agent": second.id, "cost_usd": "0.42"})
        with patch.object(self.house.ledger, "read", wraps=self.house.ledger.read) as read:
            after = self.body(standing)
        whole = [c.kwargs for c in read.call_args_list if c.kwargs.get("after", 0) == 0 and not c.kwargs.get("newest")
                 and set([c.kwargs["kinds"]] if isinstance(c.kwargs.get("kinds"), str) else c.kwargs.get("kinds") or ()) & set(self.FOLDED)]
        self.assertEqual(whole, [], "a checkpoint after the first reads none of the folded kinds from the start")
        self.assertEqual(after, self.body(self.publisher("fresh-after")))
        # And the sums are the whole ledger's, as the full read made them.
        ledger, today = self.house.ledger, now_iso(self.clock)[:10]
        charges = list(ledger.iter(kinds="credit.charge"))
        desk = {row["id"]: row for row in after["desks"]}[first.id]
        self.assertEqual(desk["cost_usd"], money(sum((D(e.payload["usd"]) for e in charges if e.agent == first.id), D(0)), 4))
        self.assertEqual(desk["orders"], ledger.count(kinds="agent.intent", agent=first.id))
        self.assertEqual(desk["gate"]["evidence"]["lifecycle"]["last_move"]["decision"], "demote")
        self.assertEqual(desk["max_drawdown_pct"], money(D("0.04") * 100, 4))  # its latest look's drawdown
        self.assertEqual(after["run"]["sail_model_spend_total_usd"],
                         money(sum((D(e.payload["usd"]) for e in charges if "token" in e.payload["what"]), D(0)), 4))
        self.assertEqual(after["run"]["sail_model_spend_today_usd"],
                         money(sum((D(e.payload["usd"]) for e in charges if "token" in e.payload["what"] and e.at[:10] == today), D(0)), 4))
        self.assertEqual(after["run"]["sail_spend_total_usd"], money(D("0.31") + D("1.20") + D("0.31") + D("1.20"), 4))
        self.assertEqual(after["run"]["sessions_today"], sum(1 for e in ledger.iter(kinds="agent.woke") if e.at[:10] == today))
        self.assertIn(before["run"]["models_used"][0], after["run"]["models_used"])
        self.assertGreater(len(after["run"]["models_used"]), len(before["run"]["models_used"]))


class FakeAllocator:
    """The allocator's published contract (Workstream A): `board()` and nothing else."""

    def __init__(self, board=None, error=None):
        self._board, self.error, self.calls = board, error, 0

    def board(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self._board


# The site's copy rule: the House's word for the practice band never reaches the page.
NEVER_ON_THE_PAGE = "paper"


class BoardCase(HouseCase):
    def publisher(self, site=None):
        return Publisher("https://blakewoods.us", lambda: "t" * 40, Path(self.dir.name) / "publish.json", tape="test", opener=site or FakeSite(), clock=self.clock)

    def board(self, agent, **overrides):
        at = now_iso(self.clock)
        board = {
            "enabled": True,
            "agents": {agent.id: {
                "band": "bunt", "stake_usd": D("10"),
                "evidence": {"W_paper": 1.08345123456, "W_real": D("1"), "E": D("1.040890"), "trades": 6, "real_trades": 0},
                "last_move": {"at": at, "from_band": "paper", "to_band": "bunt", "reason": "E crossed 1.03 after 6 trades"},
            }},
            "moves": [{"id": "le-move-1", "at": at, "agent": agent.id, "venue": "alpaca", "from_band": "paper", "to_band": "bunt",
                       "stake_usd": "10.00", "reason": "E crossed 1.03 after 6 trades"}],
            "bands": {"alpaca": {"bunt": {"count": 1, "capital_usd": D("10")}, "paper": {"count": 40, "capital_usd": D("0")}},
                      "kalshi": {"swing": {"count": 1, "capital_usd": D("42.5")}}},
            "throttle": {"active": False, "floor_pnl_usd": D("-12.4"), "envelope_usd": D("1017.75")},
        }
        board.update(overrides)
        return board


class BoardTest(BoardCase):
    def test_the_board_publishes_the_allocators_band_stake_evidence_and_moves(self):
        agent = self.seated()
        self.house.allocator = FakeAllocator(self.board(agent))
        self.clock.advance(5)
        body = self.publisher().checkpoint(self.house)
        row = body["desks"][0]
        self.assertEqual(row["band"], "bunt")
        self.assertEqual(row["stake_usd"], "10.00")
        self.assertEqual(row["evidence"], {"W_paper": "1.083451", "W_real": "1.000000", "E": "1.040890", "trades": 6, "real_trades": 0})
        self.assertEqual(row["last_move"], {"at": self.house.allocator._board["agents"][agent.id]["last_move"]["at"], "from_band": "paper", "to_band": "bunt",
                                            "reason": "E crossed 1.03 after 6 trades"})
        self.assertEqual(body["board"], {
            "enabled": True,
            "bands": {"alpaca": {"bunt": {"count": 1, "capital_usd": "10.00"}, "paper": {"count": 40, "capital_usd": "0.00"}},
                      "kalshi": {"swing": {"count": 1, "capital_usd": "42.50"}}},
            "moves": [{"id": "le-move-1", "at": row["last_move"]["at"], "agent": agent.id, "venue": "alpaca", "from_band": "paper", "to_band": "bunt",
                       "stake_usd": "10.00", "reason": "E crossed 1.03 after 6 trades"}],
            "throttle": {"active": False, "floor_pnl_usd": "-12.40", "envelope_usd": "1017.75"},
        })
        self.assertEqual(self.house.allocator.calls, 1, "one board per checkpoint")

    def test_without_an_allocator_or_when_it_fails_the_band_follows_the_rung_and_nothing_else_is_claimed(self):
        agent = self.seated()
        for allocator in (None, FakeAllocator(error=RuntimeError("the allocator is down")), FakeAllocator(board="not a board")):
            self.house.allocator = allocator
            site = FakeSite()
            self.house.publisher = self.publisher(site)
            self.clock.advance(float(self.house.settings.publish_seconds))  # the site is checkpointed once a minute (H5)
            self.house.tick()
            self.assertTrue(site.posts[-1][0].endswith("/checkpoint"), "the checkpoint is published whatever the board did")
            body = site.posts[-1][2]
            row = next(d for d in body["desks"] if d["id"] == agent.id)
            self.assertEqual(row["band"], "paper")
            for key in ("stake_usd", "evidence", "last_move"):
                self.assertNotIn(key, row)
            self.assertEqual(body["board"]["enabled"], False)
            self.assertEqual(body["board"]["bands"], {"alpaca": {"paper": {"count": 1, "capital_usd": "0.00"}}})
            self.assertEqual(body["board"]["moves"], [])
        # The ledger's own promotions and demotions are the trail, as bands, with their venue.
        self.house.evaluator.promote(agent.id, 2, "fixture evidence")
        self.house.allocator = None
        body = self.publisher().checkpoint(self.house)
        self.assertEqual(body["desks"][0]["band"], "bunt")
        move = body["board"]["moves"][-1]
        self.assertEqual({k: move[k] for k in ("agent", "venue", "from_band", "to_band", "reason")},
                         {"agent": agent.id, "venue": "alpaca", "from_band": "paper", "to_band": "bunt", "reason": "fixture evidence"})
        self.assertEqual(move["id"], event_id(self.house.ledger.last("eval.verdict", agent=agent.id).id), "the trail and the tape share the move's id")

    def test_the_real_allocators_placeholder_is_not_a_board_but_its_first_pass_is(self):
        # The House's own allocator (league/allocator.py) holds an empty placeholder until its first
        # rebalance: every restart until the first mark pass, and always while it is switched off.
        agent = self.seated()
        self.house.evaluator.promote(agent.id, 2, "fixture evidence")
        self.assertEqual(self.house.allocator.board()["agents"], {})
        self.clock.advance(5)
        body = self.publisher().checkpoint(self.house)
        self.assertEqual(body["desks"][0]["band"], "bunt")
        self.assertEqual(body["board"]["enabled"], False, "no board drawn yet: the roster and the ledger stand in")
        self.assertEqual(set(body["board"]["bands"]["alpaca"]), {"bunt"})
        self.assertEqual([(m["agent"], m["from_band"], m["to_band"]) for m in body["board"]["moves"]], [(agent.id, "paper", "bunt")])
        self.house.allocator.rebalance()
        self.assertIn(agent.id, self.house.allocator.board()["agents"])
        self.clock.advance(5)
        body = self.publisher().checkpoint(self.house)
        self.assertEqual(body["board"]["enabled"], True, "the allocator's own board, once it has drawn one")
        self.assertEqual(body["desks"][0]["band"], self.house.allocator.board()["agents"][agent.id]["band"])
        self.assertEqual(sum(row["count"] for per in body["board"]["bands"].values() for row in per.values()), 1)

    def test_an_agent_the_allocator_does_not_list_keeps_its_rung_band(self):
        agent = self.seated()
        other = self.seated("other")
        self.house.allocator = FakeAllocator(self.board(agent))
        self.clock.advance(5)
        rows = {d["id"]: d for d in self.publisher().checkpoint(self.house)["desks"]}
        self.assertEqual(rows[other.id]["band"], "paper")
        self.assertNotIn("evidence", rows[other.id])
        self.assertEqual(rows[agent.id]["band"], "bunt")

    def test_whatever_the_allocator_returns_the_site_gets_only_what_it_accepts(self):
        agent = self.seated()
        at = now_iso(self.clock)
        later = now_iso(lambda: self.clock() + 3600)
        good = {"id": "le-ok", "at": at, "agent": agent.id, "from_band": "paper", "to_band": "bunt", "reason": "ok"}
        board = self.board(agent, agents={agent.id: {
            "band": "bunt", "stake_usd": "ten dollars",
            "evidence": {"W_paper": float("nan"), "W_real": 1, "E": 1, "trades": 3},
            "last_move": {"at": at, "from_band": "paper", "to_band": "dead", "reason": "x"},
        }}, moves=[
            {**good, "id": "le-future", "at": later},                       # dated after the checkpoint
            {**good, "id": "le-dead", "to_band": "dead"},                     # a band the site does not know
            {**good, "id": "le-name", "agent": "Not An Id"},                  # not an agent id
            {**good, "id": "le-venue", "venue": "BTC/USD", "stake_usd": -3},  # a venue and a stake the site refuses
            {**good, "id": "le-iso", "at": "2026-09-09T00:00:00+00:00"},     # Python's isoformat, normalised
            good, good,                                                        # the same move twice
            *({**good, "id": f"le-{n}", "reason": "<b>" + "x" * 400} for n in range(80)),
        ], bands={"alpaca": {"bunt": {"count": "1", "capital_usd": "x"}, "dead": {"count": 1, "capital_usd": 1}}, "BTC/USD": {}},
            throttle={"active": "yes", "floor_pnl_usd": 1, "envelope_usd": 1}, enabled="yes")
        self.house.allocator = FakeAllocator(board)
        self.clock.advance(5)
        body = self.publisher().checkpoint(self.house)
        row = body["desks"][0]
        self.assertEqual(row["band"], "bunt")
        self.assertIsNone(row["stake_usd"])
        self.assertIsNone(row["evidence"])
        self.assertIsNone(row["last_move"])
        out = body["board"]
        self.assertEqual(out["enabled"], False)
        self.assertNotIn("throttle", out)
        self.assertEqual(out["bands"], {"alpaca": {}})
        self.assertEqual(len(out["moves"]), 50)
        ids = [m["id"] for m in out["moves"]]
        self.assertEqual(len(set(ids)), 50)
        self.assertNotIn("le-future", ids)
        self.assertNotIn("le-dead", ids)
        self.assertNotIn("le-name", ids)
        self.assertEqual(ids[-1], "le-79", "the newest fifty, oldest first")
        for move in out["moves"]:
            self.assertLessEqual(publish.js_length(move["reason"]), 300)
            self.assertNotIn("<", move["reason"])
            self.assertRegex(move["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
        stamp = now_iso(self.clock)
        venue = publish.site_board_move({**good, "venue": "BTC/USD", "stake_usd": -3}, stamp)
        self.assertNotIn("venue", venue)
        self.assertIsNone(venue["stake_usd"])
        self.assertEqual(publish.site_board_move({**good, "at": "2026-09-09T00:00:00+00:00"}, stamp)["at"], "2026-09-09T00:00:00.000Z")
        self.assertIsNone(publish.site_board_move({**good, "at": later}, stamp))

    def test_an_emoji_heavy_reason_stays_inside_the_sites_300_on_every_path(self):
        # A frontier audit veto: up to 300 characters of model text behind the House's own words.
        agent = self.seated()
        veto = "the frontier audit after promotion vetoed it: " + "the edge 📉 is noise 🎲 and the fills 🚫 are optimistic; " * 12
        self.assertGreater(len(veto), 300)
        at = now_iso(self.clock)
        cut = veto[:300]  # what the allocator's own trail keeps: 300 of Python's characters
        self.assertGreater(publish.js_length(cut), 300)
        self.house.allocator = FakeAllocator(self.board(agent, agents={agent.id: {
            "band": "paper", "stake_usd": None, "evidence": None,
            "last_move": {"at": at, "from_band": "bunt", "to_band": "paper", "reason": cut}}},
            moves=[{"id": "le-veto", "at": at, "agent": agent.id, "venue": "alpaca", "from_band": "bunt", "to_band": "paper", "reason": cut}]))
        self.clock.advance(5)
        body = self.publisher().checkpoint(self.house)
        reasons = [body["desks"][0]["last_move"]["reason"], body["board"]["moves"][-1]["reason"]]
        # Without the allocator: the ledger's demote row is the trail.
        self.house.evaluator.promote(agent.id, 2, "fixture evidence")
        self.clock.advance(5)
        self.house.evaluator.demote(agent.id, veto)
        self.house.allocator = None
        self.clock.advance(5)
        trail = self.publisher().checkpoint(self.house)["board"]["moves"][-1]
        self.assertEqual((trail["from_band"], trail["to_band"]), ("bunt", "paper"))
        reasons.append(trail["reason"])
        for reason in reasons:
            self.assertLessEqual(publish.js_length(reason), 300)
            self.assertGreaterEqual(publish.js_length(reason), 299, "cut at the limit, not far short of it")
            self.assertTrue(veto.startswith(reason), "a clean prefix: no character split")

    def test_band_moves_and_stake_changes_reach_the_tape_in_the_sites_templates_and_never_say_paper(self):
        agent = self.seated()
        rows = [
            ({"decision": "promote", "from_rung": 1, "to_rung": 2, "band_from": "paper", "band_to": "bunt", "stake_usd": "10", "via": "allocator",
              "reason": "E 1.041 after 6 trades."}, f"{agent.id} climbs from Practice to Bunt with a $10.00 real stake: E 1.041 after 6 trades."),
            ({"decision": "promote", "from_rung": 3, "to_rung": 3, "band_from": "swing", "band_to": "star", "stake_usd": "1240.5", "via": "allocator",
              "reason": "the top real P&L"}, f"{agent.id} climbs from Swing to Star with a $1240.50 real stake: the top real P&L."),
            ({"decision": "demote", "from_rung": 3, "to_rung": 1, "band_from": "swing", "band_to": "paper", "stake_usd": None, "via": "allocator",
              "reason": "it lost 35% of its real stake"}, f"{agent.id} drops from Swing to Practice: it lost 35% of its real stake."),
            ({"decision": "size", "rung": 2, "band": "bunt", "stake_usd": "14.2", "via": "allocator", "reason": "E 1.42"},
             f"{agent.id}'s real stake is now $14.20 (Bunt): E 1.42."),
            ({"decision": "size", "rung": 3, "stake_usd": "61.07", "moved_usd": "6", "reason": "kelly"}, f"{agent.id}'s real stake is now $61.07 (Swing): kelly."),
            ({"decision": "promote", "from_rung": 1, "to_rung": 2, "reason": "it cleared the screen"}, f"{agent.id} climbs from rung 1 to rung 2: it cleared the screen."),
            ({"decision": "promote", "from_rung": 1, "to_rung": 2, "band_from": "paper", "band_to": "bunt", "reason": ""},
             f"{agent.id} climbs from Practice to Bunt: the allocator's evidence."),
            # A probe (Sept 24, 2026): an unproven family's first real stake, and its climb to a bunt.
            ({"decision": "promote", "from_rung": 1, "to_rung": 2, "band_from": "paper", "band_to": "probe", "stake_usd": "10", "via": "allocator",
              "reason": "E 1.02 on 5 settlements."}, f"{agent.id} climbs from Practice to Probe with a $10.00 real stake: E 1.02 on 5 settlements."),
            ({"decision": "size", "rung": 2, "band": "probe", "stake_usd": "10.4", "via": "allocator", "reason": "E 1.04"},
             f"{agent.id}'s real stake is now $10.40 (Probe): E 1.04."),
        ]
        for payload, message in rows:
            entry = self.house.ledger.append("eval.verdict", payload, agent=agent.id)
            events = to_events(entry)
            self.assertEqual([e["payload"]["message"] for e in events], [message])
            self.assertEqual(events[0]["id"], event_id(entry.id))
            self.assertEqual((events[0]["stream"], events[0]["kind"], events[0]["payload"]["component"]), ("lab", "lab.progress", "league"))
        for payload in ({"decision": "size", "rung": 2, "stake_usd": "0"}, {"decision": "size", "rung": 1, "stake_usd": "x"}, {"decision": "look", "rung": 1}):
            self.assertEqual(to_events(self.house.ledger.append("eval.verdict", payload, agent=agent.id)), [])
        for payload, message in rows:
            if "band_from" in payload or "band" in payload:
                self.assertNotIn(NEVER_ON_THE_PAGE, message.lower())

    def test_the_roster_and_the_body_stay_inside_the_sites_limits(self):
        self.assertEqual(publish.MAX_DESKS, 160, "the site accepts 160 rows since personal-site #4")
        self.assertEqual(publish.MAX_CHECKPOINT_BYTES, 512 * 1024)
        agents = [self.seated(f"agent-{n}") for n in range(6)]
        for n in range(3):
            gone = self.house.registry.born(name=f"gone-{n}", family="test-family", code=BUYER, needs={"venue": "alpaca", "horizon": "hour", "style": "test"})
            self.house.registry.died(gone.id, "test")
        self.house.evaluator.promote(agents[2].id, 2, "fixture evidence")
        full = self.publisher().checkpoint(self.house)
        self.assertEqual(len(full["desks"]), 9)
        rows = sorted(len(json.dumps(d, separators=(",", ":"))) for d in full["desks"])
        old = publish.MAX_CHECKPOINT_BYTES
        try:
            # Room for about five rows: the dead go first, then the youngest of the lowest band.
            publish.MAX_CHECKPOINT_BYTES = len(json.dumps(full, separators=(",", ":"), ensure_ascii=False).encode()) - sum(rows[-4:])
            body = self.publisher().checkpoint(self.house)
            size = len(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
            self.assertLessEqual(size, publish.MAX_CHECKPOINT_BYTES)
            ids = {d["id"] for d in body["desks"]}
            self.assertIn(agents[2].id, ids, "real money is the last thing left out")
            self.assertTrue(all(d["status"] == "active" for d in body["desks"]), "the dead are left out first")
            self.assertEqual(set(body["committee"]["allocations"]), ids)
            self.assertEqual(body["floor"]["live_desks"] + body["floor"]["shadow_desks"], len(ids))
            self.assertEqual(sum(g["desks"] for g in body["lab"]["curve"]), 9, "the totals still count every agent")
            self.assertEqual(body["board"]["bands"], {"alpaca": {"bunt": {"count": 1, "capital_usd": full["board"]["bands"]["alpaca"]["bunt"]["capital_usd"]},
                                                                  "paper": {"count": 5, "capital_usd": "0.00"}}}, "the board counts every living agent")
        finally:
            publish.MAX_CHECKPOINT_BYTES = old


class FamiliesCase(BoardCase):
    """The mechanism ledger on the board (C1 and C4, the close-the-gaps run, Sept 24, 2026): the House's
    `families` block (per venue, per family: `families.row_of`) and each agent row's family fields."""

    def family_row(self, state="proven", **overrides):
        at = now_iso(self.clock)
        row = {"unit": "at_risk", "state": state, "since": at, "n": 11, "n_eff": 9.9, "mean_log": 0.2371, "bound": 0.1423, "loss_gate": None,
               "proven": state != "unproven", "edge_per_dollar": 0.2104,
               "real": {"n": 2, "mean_log": 0.31, "bound": None, "loss_gate": None, "honest_bound": None,
                        "entry": {"checkpoint": None, "next_checkpoint": 15, "confidence": 0.9, "honest_bound": None, "ready": False}},
               "maker": {"n": 0, "bound": None, "positive": False}, "taker": {"n": 11, "bound": 0.0981, "positive": True},
               "blocks": {"practice": 6, "real": 2, "growth": 0.0123}, "members": 3, "members_living": 2, "members_real": 1, "stake_usd": "30",
               "capacity": {"usd_per_day": 56.6512, "markets_per_day": 12.31, "fill_rate_at_size": 0.6, "size_usd": 6.0, "settlements_per_day": 5.1,
                            "binds": False},
               "swing": None}
        row.update(overrides)
        return row

    def families(self):
        swing = self.family_row("swing", n=40, bound=0.031, real={"n": 32, "honest_bound": 0.02}, stake_usd="120.00", members_real=2,
                                capacity={"usd_per_day": 14.2, "binds": True},
                                swing={"stake_usd": Decimal("120.00"), "limit": "capacity", "level": 1, "entered_seq": 88})
        return {"kalshi": {"sports-central-run-under": self.family_row(), "weather-favorites": swing,
                           "crypto-15m-favorites": self.family_row("unproven", n=106, bound=-0.0064, stake_usd="10")},
                "alpaca": {"crypto-alts-reversion": self.family_row("unproven", n=156, bound=-0.0016, stake_usd="25"),
                           "equity-trend": self.family_row("unproven", n=0, bound=None)}}

    def ledger_board(self, agent, **overrides):
        board = self.board(agent, **{"families": self.families(), **overrides})
        board["agents"][agent.id].update(family="sports-central-run-under", family_state="proven", family_bound=0.1423, family_n=11,
                                         capacity={"usd_per_day": 56.6512, "binds": False}, stake_limit=None)
        return board

    def lab_stats(self, **overrides):
        """A `lab.stats` row as `Lab.publish` writes it (`Lab.stats`: the last hour's batches, what they evaluated, the
        graduates waiting for a seat), with the fields the site reads and a few it does not."""
        stats = {"window_seconds": 3600.0, "batches": 63, "evaluated": 84, "per_hour": 84.0, "queued": 12, "born_total": 20,
                 "waiting_seat": {"count": 3, "longest_hours": 1.5}, "failing_since": None, "failures_in_a_row": 0, "error": None}
        stats.update(overrides)
        return self.house.ledger.append("lab.stats", stats, agent=HOUSE)


class FamiliesTest(FamiliesCase):
    def test_a_desk_carries_its_familys_state_and_settlements_and_nothing_else_of_its_record(self):
        agent = self.seated()
        self.house.allocator = FakeAllocator(self.ledger_board(agent))
        self.clock.advance(5)
        row = self.publisher().checkpoint(self.house)["desks"][0]
        self.assertEqual((row["family_state"], row["family_n"]), ("proven", 11))
        for key in ("family_bound", "capacity", "stake_limit", "target_usd"):
            self.assertNotIn(key, row, "the family's bound and capacity ride the board's families, once a family")
        self.assertEqual(row["family"], "test-family", "the desk's own family field is unchanged")

    def test_a_family_field_the_site_would_refuse_is_left_out_with_its_pair(self):
        agent = self.seated()
        for state, n in (("lucky", 11), ("Proven", 11), (None, 11), ("proven", -1), ("proven", 1.5), ("proven", True), ("proven", None), ("proven", "x")):
            board = self.ledger_board(agent)
            board["agents"][agent.id].update(family_state=state, family_n=n)
            self.house.allocator = FakeAllocator(board)
            self.clock.advance(5)
            row = self.publisher().checkpoint(self.house)["desks"][0]
            self.assertNotIn("family_state", row, (state, n))
            self.assertNotIn("family_n", row, (state, n))
            self.assertEqual(row["band"], "bunt", "the rest of the row stands")
        board = self.ledger_board(agent)
        board["agents"][agent.id].update(family_state="swing", family_n=10 ** 12)
        self.house.allocator = FakeAllocator(board)
        self.clock.advance(5)
        row = self.publisher().checkpoint(self.house)["desks"][0]
        self.assertEqual((row["family_state"], row["family_n"]), ("swing", publish.MAX_SETTLEMENTS), "the site's bound on a count")
        # Without the allocator, or an agent it does not list: no family is claimed.
        self.house.allocator = None
        self.clock.advance(5)
        self.assertNotIn("family_state", self.publisher().checkpoint(self.house)["desks"][0])

    def test_the_board_carries_the_proven_families_strongest_first_and_the_unproven_count(self):
        agent = self.seated()
        self.house.allocator = FakeAllocator(self.ledger_board(agent))
        self.clock.advance(5)
        families = self.publisher().checkpoint(self.house)["board"]["families"]
        self.assertEqual(families, {"unproven": 3, "rows": [
            {"family": "weather-favorites", "venue": "kalshi", "state": "swing", "n": 40, "real_n": 32, "bound": "0.031000", "stake_usd": "120.00",
             "members_real": 2, "capacity_usd_per_day": "14.20"},
            {"family": "sports-central-run-under", "venue": "kalshi", "state": "proven", "n": 11, "real_n": 2, "bound": "0.142300", "stake_usd": "30.00",
             "members_real": 1, "capacity_usd_per_day": "56.65"},
        ]})

    def test_a_proven_familys_bound_is_its_honest_one(self):
        # A lopsided record (favourites) is also held to the House's loss-rate bound: the proof is the smaller of the two.
        self.assertEqual(publish.honest_bound({"bound": 0.05, "loss_gate": 0.012}), Decimal("0.012"))
        self.assertEqual(publish.honest_bound({"bound": 0.05, "loss_gate": None}), Decimal("0.05"))
        self.assertIsNone(publish.honest_bound({"bound": None, "loss_gate": 0.3}))
        families = {"kalshi": {"weather-favorites": self.family_row(bound=0.05, loss_gate=0.012)}}
        self.assertEqual(publish.site_families(families)["rows"][0]["bound"], "0.012000")

    def test_whatever_the_families_block_holds_the_site_gets_only_what_it_accepts(self):
        row = self.family_row
        eight = {f"family-{n}": row(n=20 + n) for n in range(10)}
        raw = {
            "kalshi": {
                **eight,
                "Sports Central!": row(n=5),                                   # normalised as a desk's family is
                "sports-central": row(n=4),                                    # ... and then the same name: one row
                "no-bound": row(bound=None),                                   # proven with no bound: not a proof to show
                "nan-bound": row(bound=float("nan")),
                "no-count": row(n="many"),
                "lucky": row("lucky"),                                         # a state the site does not know: neither row nor count
                "huge": row(n=10 ** 9, real={"n": 10 ** 9}, bound=1e12, stake_usd="1e3", members_real=10 ** 6,
                            capacity={"usd_per_day": 1e30}),
                "odd": row(real="nope", stake_usd="thirty", members_real=-2, capacity="none"),
                "not-a-row": "proven",
            },
            "BTC/USD": {"x": row()},                                           # not a venue
            "alpaca": "not a mapping",
            "coinbase": {"u": row("unproven"), "v": row("unproven")},
        }
        out = publish.site_families(raw)
        self.assertEqual(out["unproven"], 2)
        self.assertEqual(len(out["rows"]), publish.MAX_FAMILY_ROWS)
        self.assertEqual(len({(r["venue"], r["family"]) for r in out["rows"]}), len(out["rows"]))
        self.assertEqual([r["n"] for r in out["rows"]][:2], [publish.MAX_SETTLEMENTS, 29], "the most settlements first, counts bounded")
        huge = out["rows"][0]
        self.assertEqual((huge["family"], huge["real_n"], huge["bound"], huge["stake_usd"], huge["members_real"], huge["capacity_usd_per_day"]),
                         ("huge", publish.MAX_SETTLEMENTS, "999999.000000", "1000.00", publish.MAX_DESKS, "999999999.00"))
        everything = publish.site_families({"kalshi": {k: v for k, v in raw["kalshi"].items() if k not in eight}})
        names = [r["family"] for r in everything["rows"]]
        self.assertEqual(names.count("sports-central"), 1)
        for gone in ("no-bound", "nan-bound", "no-count", "lucky", "not-a-row"):
            self.assertNotIn(gone, names)
        odd = next(r for r in everything["rows"] if r["family"] == "odd")
        self.assertEqual((odd["real_n"], odd["stake_usd"], odd["members_real"], odd["capacity_usd_per_day"]), (0, None, 0, None))
        for bad in (None, "families", [row()], {}):
            self.assertEqual(publish.site_families(bad), None if bad != {} else {"unproven": 0, "rows": []})

    def test_the_lab_reading_is_the_labs_own_hourly_stats_while_it_is_fresh(self):
        agent = self.seated()
        self.house.allocator = FakeAllocator(self.ledger_board(agent))
        publisher = self.publisher()
        self.clock.advance(5)
        self.assertNotIn("lab", publisher.checkpoint(self.house)["board"], "no reading yet: no line")
        entry = self.lab_stats()
        self.clock.advance(60)
        board = publisher.checkpoint(self.house)["board"]
        self.assertEqual(board["lab"], {"at": entry.at, "tested_last_hour": 84, "graduates_waiting": 3})
        self.clock.advance(publish.LAB_READING_MAX_AGE)
        self.assertNotIn("lab", publisher.checkpoint(self.house)["board"], "a reading older than half an hour says nothing of the last hour")
        # The newest reading is the one read, and one the site would refuse is not sent.
        for stats, expected in (({}, {"tested_last_hour": 84, "graduates_waiting": 3}),
                                ({"evaluated": 0, "waiting_seat": {"count": 0}}, {"tested_last_hour": 0, "graduates_waiting": 0}),
                                ({"evaluated": 10 ** 9}, {"tested_last_hour": publish.MAX_TESTED, "graduates_waiting": 3}),
                                ({"window_seconds": 600.0}, None), ({"evaluated": -1}, None), ({"evaluated": 1.5}, None),
                                ({"waiting_seat": None}, None), ({"waiting_seat": {"count": "3"}}, {"tested_last_hour": 84, "graduates_waiting": 3}),
                                ({"evaluated": None}, None)):
            entry = self.lab_stats(**stats)
            self.clock.advance(5)
            lab = publisher.checkpoint(self.house)["board"].get("lab")
            self.assertEqual(lab, None if expected is None else {"at": entry.at, **expected}, stats)

    def test_the_lab_line_needs_no_allocator(self):
        self.seated()
        self.house.allocator = None
        entry = self.lab_stats()
        self.clock.advance(5)
        board = self.publisher().checkpoint(self.house)["board"]
        self.assertEqual(board["enabled"], False)
        self.assertEqual(board["lab"], {"at": entry.at, "tested_last_hour": 84, "graduates_waiting": 3})
        self.assertNotIn("families", board, "the families come with the allocator's board only")

    def test_a_lab_reading_that_cannot_be_read_costs_the_checkpoint_nothing(self):
        from unittest.mock import patch

        agent = self.seated()
        self.house.allocator = FakeAllocator(self.ledger_board(agent))
        self.lab_stats()
        self.clock.advance(5)
        with patch.object(self.house.ledger, "last", side_effect=RuntimeError("the ledger is busy")):
            body = self.publisher().checkpoint(self.house)
        self.assertNotIn("lab", body["board"])
        self.assertIn("families", body["board"])


class FlywheelCase(FamiliesCase):
    """The capital page's flywheel (W of the forward-first run, Sept 25, 2026): the checkpoint's `flywheel` from
    health.json, the board and the hourly yield rows, and a proven family's clock and capacity curve."""

    def swing_clock(self, **needs):
        """The board's `swing_clock` as `families.swing_clock` draws it (the T0 snapshot's sports family, Sept 25, 2026)."""
        return {"real_n": 11, "real_since": "2026-09-23T04:52:20Z", "real_days": 1.98, "real_per_day": 5.556,
                "needs": {"real_settlements": 4, "look_at": 15, "confidence": 0.9, "proof": False, "audit": True, "grant": False, **needs},
                "days_to_swing": 0.72}

    def curve(self):
        """C6's `capacity.curve` as `families.row_of` writes it (c/family, Sept 25, 2026): 1x and 2x measured on the real
        book, 4x never bid enough."""
        return [{"multiple": 1, "size_usd": 5.39, "fill_rate": 0.6, "basis": "real", "usd_per_day": 32.3312},
                {"multiple": 2, "size_usd": 10.78, "fill_rate": 0.6, "basis": "real", "usd_per_day": 64.6624},
                {"multiple": 4, "size_usd": 21.56, "fill_rate": None, "basis": None, "usd_per_day": None}]

    def sports(self, **overrides):
        row = self.family_row(swing_clock=self.swing_clock(),
                              capacity={"usd_per_day": 32.3312, "markets_per_day": 19.07, "fill_rate_at_size": 0.6, "size_usd": 5.39,
                                        "settlements_per_day": 4.77, "fill_rate_basis": "real", "curve": self.curve(), "binds": False})
        row.update(overrides)
        return row

    def health(self, **fields):
        """health.json as `House._health` writes it at the end of a tick, with the fields the strip reads and some it does not."""
        body = {"at": now_iso(self.clock), "living": 128, "restarts_24h": 24, "restarts_24h_in_session": 7,
                "last_start": {"at": now_iso(self.clock), "release": "main-47c52e860764", "seq": 700000},
                "research_economy": {"sail_cap": {"calls": 198}, "merton": {"roles": ["architect"], "paused": [], "real_pnl_24h_usd": "19.38124",
                                                                            "settlements": 66, "measure": "realized"}},
                "tick_duration_seconds": 72.4}
        body.update(fields)
        self.house.root.mkdir(parents=True, exist_ok=True)
        (self.house.root / "health.json").write_text(json.dumps(body), encoding="utf-8")
        return body

    def yield_row(self, blocks=(("research", 5), ("lab", 3)), graduates=2):
        """One hourly yield row (`yield_ledger.fold`), as `YieldLedger.tick` appends it."""
        evidence = {line: {"positive_blocks": n, "active_blocks": 2 * n} for line, n in blocks}
        evidence.setdefault("lab", {})["graduates"] = graduates
        return self.house.ledger.append("ops.budget", {"what": "yield", "since": now_iso(lambda: self.clock() - 3600), "until": now_iso(self.clock),
                                                       "spend_usd": {"research": "2.1"}, "evidence": evidence, "usd_per": {}, "total_usd": "2.1",
                                                       "hours": 1.0}, agent=HOUSE)


class FlywheelTest(FlywheelCase):
    def test_a_proven_familys_row_carries_its_clock_and_capacity_curve_in_the_sites_shape(self):
        agent = self.seated()
        families = self.families()
        families["kalshi"]["sports-central-run-under"] = self.sports()
        families["kalshi"]["weather-favorites"]["swing_clock"] = self.swing_clock()  # a compounding family: no clock goes
        self.house.allocator = FakeAllocator(self.ledger_board(agent, families=families))
        self.clock.advance(5)
        rows = {r["family"]: r for r in self.publisher().checkpoint(self.house)["board"]["families"]["rows"]}
        self.assertEqual(rows["sports-central-run-under"]["swing_clock"], {"look_at": 15, "to_go": 4, "per_day": "5.556", "days": "0.72"})
        self.assertEqual(rows["sports-central-run-under"]["capacity_curve"], [
            {"multiple": 1, "size_usd": "5.39", "fill_rate": "0.6000", "usd_per_day": "32.33", "basis": "real"},
            {"multiple": 2, "size_usd": "10.78", "fill_rate": "0.6000", "usd_per_day": "64.66", "basis": "real"},
            {"multiple": 4, "size_usd": "21.56", "fill_rate": None, "usd_per_day": None, "basis": None}])
        self.assertNotIn("swing_clock", rows["weather-favorites"], "the site refuses a clock on a compounding family")
        # The board as a/integration draws it today (no C6 curve, no M1 dates): nothing the board lacks is sent.
        self.house.allocator = FakeAllocator(self.ledger_board(agent))
        self.clock.advance(5)
        for row in self.publisher().checkpoint(self.house)["board"]["families"]["rows"]:
            self.assertNotIn("swing_clock", row)
            self.assertNotIn("capacity_curve", row)

    def test_whatever_the_clock_and_the_curve_hold_the_site_gets_only_what_it_accepts(self):
        clock = publish.site_swing_clock
        self.assertEqual(clock(self.swing_clock(distinct_dates=2, grant=True)),
                         {"look_at": 15, "to_go": 4, "per_day": "5.556", "days": "0.72", "dates_to_go": 2, "grant_holds": True})
        self.assertEqual(clock({**self.swing_clock(real_settlements=0), "days_to_swing": 0.0}), {"look_at": 15, "to_go": 0, "per_day": "5.556", "days": "0.00"})
        self.assertEqual(clock({**self.swing_clock(look_at=None), "real_per_day": None, "days_to_swing": None}),
                         {"look_at": None, "to_go": 4, "per_day": None, "days": None})
        self.assertEqual(clock({**self.swing_clock(real_settlements=10 ** 9, look_at=10 ** 9, distinct_dates=10 ** 6), "real_per_day": 1e12, "days_to_swing": -3}),
                         {"look_at": publish.MAX_SETTLEMENTS, "to_go": publish.MAX_SETTLEMENTS, "per_day": "100000.000", "days": None, "dates_to_go": 366})
        self.assertEqual(clock(self.swing_clock(grant=None))["look_at"], 15)
        self.assertNotIn("grant_holds", clock(self.swing_clock(grant=None)), "an unknown grant claims nothing")
        for bad in (None, "0.72", {}, {"needs": "four"}, {"needs": {"look_at": 15}}, {"needs": {"real_settlements": -1}},
                    {"needs": {"real_settlements": 4, "look_at": "fifteen"}}, {"needs": {"real_settlements": 1.5}}):
            self.assertIsNone(clock(bad), bad)
        curve = publish.site_capacity_curve
        self.assertIsNone(curve({"usd_per_day": 32.33}), "before C6: no curve")
        self.assertIsNone(curve(None))
        self.assertIsNone(curve({"curve": []}))
        odd = curve({"curve": [
            {"multiple": 4, "size_usd": 20, "fill_rate": 0.5, "basis": "real", "usd_per_day": 1e30},   # out of order, bounded
            {"multiple": 1, "size_usd": 5, "fill_rate": 0.5, "basis": "practice", "usd_per_day": 3},    # a basis the site does not know: unmeasured
            {"multiple": 2, "size_usd": 10, "fill_rate": 1.5, "basis": "real", "usd_per_day": 3},       # a rate above one: unmeasured
            {"multiple": 2, "size_usd": 99, "fill_rate": 0.1, "basis": "all", "usd_per_day": 3},        # the same multiple twice: the first stands
            {"multiple": 0, "size_usd": 1}, {"multiple": 8, "size_usd": -1}, {"multiple": 1.5, "size_usd": 1}, "a point",
            {"multiple": 16, "size_usd": 80, "fill_rate": 0.25, "basis": "all", "usd_per_day": -0.4001},
            {"multiple": 8, "size_usd": 40, "fill_rate": 0.25, "basis": "all", "usd_per_day": None},
        ]})
        self.assertEqual(odd, [
            {"multiple": 1, "size_usd": "5.00", "fill_rate": None, "usd_per_day": None, "basis": None},
            {"multiple": 2, "size_usd": "10.00", "fill_rate": None, "usd_per_day": None, "basis": None},
            {"multiple": 4, "size_usd": "20.00", "fill_rate": "0.5000", "usd_per_day": "999999999.00", "basis": "real"},
            {"multiple": 8, "size_usd": "40.00", "fill_rate": "0.2500", "usd_per_day": None, "basis": "all"}])

    def test_the_flywheel_is_health_the_board_and_the_yield_rows_of_the_last_day(self):
        agent = self.seated()
        families = self.families()
        families["kalshi"]["sports-central-run-under"]["since"] = now_iso(lambda: self.clock() - 3600)      # proven an hour ago
        families["kalshi"]["weather-favorites"]["since"] = now_iso(lambda: self.clock() - 3 * 86400)        # compounding for three days
        families["alpaca"]["equity-trend"]["since"] = now_iso(self.clock)                                   # unproven: not a proof
        self.house.allocator = FakeAllocator(self.ledger_board(agent, families=families))
        old = self.yield_row(graduates=40)                     # a day and more ago: not in the day
        self.clock.advance(86400 + 60)
        for _ in range(3):
            self.yield_row()
            self.clock.advance(3600)
        families["kalshi"]["sports-central-run-under"]["since"] = now_iso(lambda: self.clock() - 3600)
        health = self.health()
        self.clock.advance(60)
        body = self.publisher().checkpoint(self.house)
        self.assertEqual(body["flywheel"], {"at": health["at"], "restarts_per_day": 24, "real_profit_usd_per_day": "19.38", "proofs_per_day": 1,
                                            "positive_blocks_per_day": 24, "graduates_per_day": 6})
        self.assertLessEqual(body["flywheel"]["at"], body["published_at"])
        self.assertTrue(old.at < now_iso(lambda: self.clock() - 86400))
        # health.json older than half an hour says nothing of the last day: the board and the yield rows still do.
        self.clock.advance(publish.FLYWHEEL_MAX_AGE)
        body = self.publisher().checkpoint(self.house)
        self.assertEqual(body["flywheel"], {"at": body["published_at"], "proofs_per_day": 1, "positive_blocks_per_day": 24, "graduates_per_day": 6})
        # Nothing known: no block at all.
        self.house.allocator = None
        (self.house.root / "health.json").unlink()
        self.clock.advance(2 * 86400)
        self.assertNotIn("flywheel", self.publisher().checkpoint(self.house))

    def test_health_fields_the_site_would_refuse_are_left_out(self):
        self.seated()
        self.house.allocator = None
        for fields, expected in (({"restarts_24h": None}, {"real_profit_usd_per_day": "19.38"}),
                                 ({"restarts_24h": -1, "research_economy": None}, None),
                                 ({"restarts_24h": 1.5, "research_economy": {"merton": None}}, None),
                                 ({"restarts_24h": 10 ** 9, "research_economy": {"merton": {"real_pnl_24h_usd": "-1e40"}}},
                                  {"restarts_per_day": 100000, "real_profit_usd_per_day": "-999999999.00"}),
                                 ({"restarts_24h": 0, "research_economy": {"merton": {"real_pnl_24h_usd": "nan"}}}, {"restarts_per_day": 0}),
                                 ({"at": "yesterday"}, None), ({"at": "2099-01-01T00:00:00.000Z"}, None)):
            health = self.health(**fields)
            self.clock.advance(5)
            flywheel = self.publisher().checkpoint(self.house).get("flywheel")
            self.assertEqual(flywheel, None if expected is None else {"at": health["at"], **expected}, fields)
        (self.house.root / "health.json").write_text("{not json", encoding="utf-8")
        self.assertNotIn("flywheel", self.publisher().checkpoint(self.house))
        (self.house.root / "health.json").write_text("[1, 2]", encoding="utf-8")
        self.assertNotIn("flywheel", self.publisher().checkpoint(self.house))

    def test_y2s_unit_economics_reaches_the_strip_through_its_hook_and_nothing_else_of_it(self):
        self.seated()
        self.house.allocator = None
        # The scoreboard's `unit_economics` row (scripts/gap_scoreboard.py) at the 10:36Z reading, Sept 25, 2026.
        health = self.health(unit_economics={"fn": "unit_economics", "profit_per_day_usd": 19.38, "compute_per_day_usd": 122.31,
                                             "compute_over_profit": 6.31, "family_swings": False, "meets_target": False})
        self.clock.advance(5)
        flywheel = self.publisher().checkpoint(self.house)["flywheel"]
        self.assertEqual(flywheel, {"at": health["at"], "restarts_per_day": 24, "compute_usd_per_day": "122.31", "real_profit_usd_per_day": "19.38"})
        self.assertEqual(publish.site_unit_economics({"compute_per_day_usd": -3, "profit_per_day_usd": None}), {})
        self.assertEqual(publish.site_unit_economics({"compute_per_day_usd": "12.5", "profit_per_day_usd": "-4.2"}),
                         {"compute_usd_per_day": "12.50", "real_profit_usd_per_day": "-4.20"})
        self.assertEqual(publish.site_unit_economics(None), {})
        self.assertEqual(publish.UNIT_ECONOMICS, "unit_economics", "the one key Y2's builder writes")

    def test_a_flywheel_that_cannot_be_read_costs_the_checkpoint_nothing(self):
        from unittest.mock import patch

        self.seated()
        self.health()
        self.clock.advance(5)
        with patch.object(publish, "site_flywheel", side_effect=RuntimeError("odd health")):
            body = self.publisher().checkpoint(self.house)
        self.assertNotIn("flywheel", body)
        self.assertIn("board", body)

    def test_a_site_that_predates_the_flywheel_still_gets_its_checkpoint_without_it(self):
        agent = self.seated()
        families = self.families()
        families["kalshi"]["sports-central-run-under"] = self.sports()
        self.house.allocator = FakeAllocator(self.ledger_board(agent, families=families))
        self.health()

        class OlderSite(FakeSite):
            """The site before personal-site #8: a checkpoint with a field it does not know is a 400."""
            knows = False

            def __call__(self, request, timeout=None):
                body = json.loads(request.data)
                self.posts.append((request.full_url, dict(request.header_items()), body))
                rows = ((body.get("board") or {}).get("families") or {}).get("rows") or []
                new = "flywheel" in body or any("swing_clock" in r or "capacity_curve" in r for r in rows)
                if request.full_url.endswith("/checkpoint") and new and not self.knows:
                    raise urllib.error.HTTPError(request.full_url, 400, "invalid checkpoint", {}, io.BytesIO(b'{"error":"invalid checkpoint"}'))
                return FakeResponse()

        site = OlderSite()
        publisher = self.publisher(site)
        self.clock.advance(5)
        out = publisher.publish(self.house)
        checkpoints = [body for url, _, body in site.posts if url.endswith("/checkpoint")]
        self.assertEqual(len(checkpoints), 2)
        self.assertIn("flywheel", checkpoints[0])
        self.assertNotIn("flywheel", checkpoints[1])
        self.assertFalse(any("swing_clock" in r or "capacity_curve" in r for r in checkpoints[1]["board"]["families"]["rows"]))
        self.assertEqual(checkpoints[1], publish.without_flywheel(checkpoints[0]))
        self.assertEqual((out["checkpoint"], out["without_flywheel"]), (200, True))
        self.assertEqual(json.loads((Path(self.dir.name) / "publish.json").read_text())["flywheel_refused"], checkpoints[0]["published_at"])
        # Once the site knows the fields, the whole checkpoint is taken and the note is cleared.
        site.knows = True
        self.clock.advance(60)
        out = publisher.publish(self.house)
        self.assertNotIn("without_flywheel", out)
        self.assertNotIn("flywheel_refused", json.loads((Path(self.dir.name) / "publish.json").read_text()))
        self.assertIn("flywheel", [body for url, _, body in site.posts if url.endswith("/checkpoint")][-1])
        # A site that refuses the checkpoint for another reason still refuses it: the fallback hides nothing.
        self.assertIsNone(publish.without_flywheel({"board": {"families": {"unproven": 0, "rows": [{"family": "x"}]}}}))

        class Refusing(FakeSite):
            def __call__(self, request, timeout=None):
                self.posts.append((request.full_url, dict(request.header_items()), json.loads(request.data)))
                if request.full_url.endswith("/checkpoint"):
                    raise urllib.error.HTTPError(request.full_url, 400, "invalid checkpoint", {}, io.BytesIO(b'{"error":"invalid checkpoint"}'))
                return FakeResponse()

        refusing = self.publisher(Refusing())
        self.clock.advance(60)
        with self.assertRaises(publish.PublishError):
            refusing.publish(self.house)  # the body without the flywheel is refused as well
        self.house.allocator = None
        (self.house.root / "health.json").unlink()
        self.clock.advance(60)
        with self.assertRaises(publish.PublishError):
            refusing.publish(self.house)  # nothing new in the body: nothing to fall back to


class LabLineTest(LabCase):
    """The board's lab line reads what the lab itself writes (`Lab.publish`), not a copy of its shape."""

    def test_the_lab_line_is_the_labs_own_last_hour(self):
        self.queue(KNOB)
        self.queue(LOSER)
        self.lab.evaluate_batch()
        self.lab.publish(force=True)
        row = self.house.ledger.last("lab.stats")
        publisher = Publisher("https://blakewoods.us", lambda: "t" * 40, Path(self.dir.name) / "publish.json", tape="test", opener=FakeSite(),
                              clock=self.clock)
        self.assertEqual(publisher.lab_reading(self.house), {"at": row.at, "tested_last_hour": 2, "graduates_waiting": 0})
        self.clock.advance(publish.LAB_READING_MAX_AGE + 1)
        self.assertIsNone(publisher.lab_reading(self.house), "the lab has not written a reading in half an hour")


SITE = Path(os.environ.get("LTCM_SITE") or Path(__file__).resolve().parents[3] / "personal-site")


#: Whether the checked-out site knows the flywheel's fields (personal-site #8, Sept 25, 2026). A site from before
#: it is sent the body `Publisher.publish` falls back to (`publish.without_flywheel`), and is checked on that.
FLYWHEEL_SITE = (SITE / "capital" / "schema.js").exists() and "validFlywheel" in (SITE / "capital" / "schema.js").read_text(encoding="utf-8", errors="replace")


@unittest.skipUnless(shutil.which("node") and (SITE / "capital" / "schema.js").exists(), "the site's validators are not checked out beside this repository (set LTCM_SITE)")
class SiteAcceptsTheBoardTest(FlywheelCase):
    """The site's own validators (personal-site/capital/schema.js), run on what this publisher posts."""

    def valid(self, body):
        if not FLYWHEEL_SITE:
            body = publish.without_flywheel(body) or body
        script = "import(process.argv[1]).then(m => { let s = ''; process.stdin.on('data', d => s += d); process.stdin.on('end', () => console.log(m.validCheckpoint(JSON.parse(s)))); })"
        out = subprocess.run(["node", "-e", script, (SITE / "capital" / "schema.js").as_uri()], input=json.dumps(body), capture_output=True, text=True, timeout=60)
        return out.stdout.strip()

    def test_the_site_accepts_the_board_with_and_without_the_allocator(self):
        agent = self.seated()
        self.house.evaluator.promote(agent.id, 2, "fixture evidence")
        self.clock.advance(5)
        self.assertEqual(self.valid(self.publisher().checkpoint(self.house)), "true")
        self.house.allocator = FakeAllocator(self.board(agent))
        self.clock.advance(5)
        self.assertEqual(self.valid(self.publisher().checkpoint(self.house)), "true")

    def test_the_site_accepts_a_probe_on_the_board(self):
        # Sept 24, 2026 (the close-the-gaps run, P1): an unproven family's first real stake is a
        # probe. The publisher sends the band as the allocator names it, with its stake, and the
        # site's validators (personal-site #6) accept it on the desk row, the counts and the moves.
        agent = self.seated()
        self.house.evaluator.promote(agent.id, 2, "fixture evidence")
        at = now_iso(self.clock)
        board = self.board(agent, bands={"alpaca": {"probe": {"count": 1, "capital_usd": D("25")}}},
                           moves=[{"id": "le-move-1", "at": at, "agent": agent.id, "venue": "alpaca", "from_band": "paper",
                                   "to_band": "probe", "stake_usd": "25.00", "reason": "E 1.02 on 5 closed trades"}])
        board["agents"][agent.id].update(band="probe", stake_usd=D("25"),
                                         last_move={"at": at, "from_band": "paper", "to_band": "probe", "reason": "E 1.02 on 5 closed trades"})
        self.house.allocator = FakeAllocator(board)
        self.clock.advance(5)
        body = self.publisher().checkpoint(self.house)
        row = body["desks"][0]
        self.assertEqual((row["band"], row["stake_usd"]), ("probe", "25.00"))
        self.assertEqual(body["board"]["bands"], {"alpaca": {"probe": {"count": 1, "capital_usd": "25.00"}}})
        self.assertEqual(body["board"]["moves"][0]["to_band"], "probe")
        self.assertEqual(self.valid(body), "true")

    def test_the_site_accepts_the_real_allocators_board_before_and_after_its_first_pass(self):
        agent = self.seated()
        self.seated("other")
        self.house.evaluator.promote(agent.id, 2, "fixture evidence")
        self.clock.advance(5)
        self.assertEqual(self.valid(self.publisher().checkpoint(self.house)), "true")
        self.house.allocator.rebalance()
        self.clock.advance(5)
        body = self.publisher().checkpoint(self.house)
        self.assertTrue(body["board"]["enabled"])
        self.assertEqual(self.valid(body), "true")

    def test_the_site_accepts_a_move_whose_reason_is_full_of_emoji(self):
        agent = self.seated()
        veto = "the frontier audit after promotion vetoed it: " + "📉🎲🚫 noise " * 60
        at = now_iso(self.clock)
        self.house.allocator = FakeAllocator(self.board(agent, agents={agent.id: {
            "band": "paper", "stake_usd": None, "evidence": None,
            "last_move": {"at": at, "from_band": "bunt", "to_band": "paper", "reason": veto[:300]}}},
            moves=[{"id": "le-veto", "at": at, "agent": agent.id, "venue": "alpaca", "from_band": "bunt", "to_band": "paper", "reason": veto[:300]}]))
        self.clock.advance(5)
        self.assertEqual(self.valid(self.publisher().checkpoint(self.house)), "true")
        self.house.evaluator.promote(agent.id, 2, "fixture evidence")
        self.clock.advance(5)
        self.house.evaluator.demote(agent.id, veto)
        self.house.allocator = None
        self.clock.advance(5)
        self.assertEqual(self.valid(self.publisher().checkpoint(self.house)), "true")

    def page(self, body):
        """What the site's page (capital/capital.js `boardSnapshot`) reads from a checkpoint: the proven families
        and their words, the lab's line, and each agent's family."""
        script = ("import(process.argv[1]).then(m => { let s = ''; process.stdin.on('data', d => s += d); process.stdin.on('end', () => { "
                  "const body = JSON.parse(s); const model = m.boardSnapshot(body, [], Date.parse(body.published_at)); "
                  "console.log(JSON.stringify({ rows: model.families && model.families.rows.map(m.familyWords), "
                  "unproven: model.families && m.unprovenWords(model.families), lab: model.lab && m.labWords(model.lab), "
                  "agents: model.agents.map(a => [a.id, a.familyState, a.familyN]) })); }); })")
        out = subprocess.run(["node", "-e", script, (SITE / "capital" / "capital.js").as_uri()], input=json.dumps(body), capture_output=True, text=True, timeout=60)
        return json.loads(out.stdout)

    def test_the_site_accepts_the_mechanism_ledger_and_its_page_draws_it(self):
        # Sept 24, 2026 (C4, the close-the-gaps run): each desk's family, the proven families and the lab's hourly
        # reading, published in the site's shapes, pass its validators (personal-site's schema after this run's site
        # change: deployed before the floor publishes them) and read on its page in its own words.
        agent = self.seated()
        self.house.evaluator.promote(agent.id, 2, "fixture evidence")
        self.house.allocator = FakeAllocator(self.ledger_board(agent))
        self.lab_stats()
        self.clock.advance(5)
        body = self.publisher().checkpoint(self.house)
        self.assertEqual(self.valid(body), "true")
        self.assertEqual(self.page(body), {
            "rows": ["compounding · 40 settlements, 32 real · lower bound +3.1% · 2 agents at $120 · capacity $14/day",
                     "proven · 11 settlements, 2 real · lower bound +14.2% · 1 agent at $30 · capacity $57/day"],
            "unproven": "3 strategies still unproven", "lab": "84 strategies tested in the last hour · 3 graduates waiting for a seat",
            "agents": [[agent.id, "proven", 11]]})
        # Nothing proven, a lab that tested nothing: still what the site accepts, in its words.
        board = self.ledger_board(agent, families={"kalshi": {"weather-favorites": self.family_row("unproven", bound=-0.2112)}})
        self.house.allocator = FakeAllocator(board)
        self.lab_stats(evaluated=0, waiting_seat={"count": 0})
        self.clock.advance(5)
        body = self.publisher().checkpoint(self.house)
        self.assertEqual(body["board"]["families"], {"unproven": 1, "rows": []})
        self.assertEqual(self.valid(body), "true")
        page = self.page(body)
        self.assertEqual((page["rows"], page["unproven"], page["lab"]), ([], "No proven edge yet · 1 strategy unproven", "No strategy tested in the last hour"))
        # The most the publisher sends of everything is still what the site accepts.
        many = {"kalshi": {f"family-{n}": self.family_row("swing" if n % 2 else "proven", n=10 ** 9, real={"n": 10 ** 9}, bound=1e12,
                                                          stake_usd="1e20", members_real=10 ** 6, capacity={"usd_per_day": -1e30})
                           for n in range(12)}}
        self.house.allocator = FakeAllocator(self.ledger_board(agent, families=many))
        self.lab_stats(evaluated=10 ** 12, waiting_seat={"count": 10 ** 12})
        self.clock.advance(5)
        body = self.publisher().checkpoint(self.house)
        self.assertEqual(len(body["board"]["families"]["rows"]), publish.MAX_FAMILY_ROWS)
        self.assertEqual(self.valid(body), "true")

    def test_the_site_accepts_the_real_allocators_mechanism_ledger(self):
        # The House's own allocator (Deploy B): its board's families and each agent's family fields, as it draws them.
        agent = self.seated()
        self.seated("other")
        self.house.evaluator.promote(agent.id, 2, "fixture evidence")
        self.house.allocator.rebalance()
        self.assertIn("families", self.house.allocator.board())
        self.lab_stats()
        self.clock.advance(5)
        body = self.publisher().checkpoint(self.house)
        self.assertEqual(body["board"]["families"], {"unproven": 1, "rows": []})
        self.assertEqual({(d["id"], d["family_state"], d["family_n"]) for d in body["desks"]}, {(agent.id, "unproven", 0), ("other", "unproven", 0)})
        self.assertEqual(self.valid(body), "true")

    def test_the_page_says_why_each_agent_was_born_and_retired(self):
        # Sept 24, 2026: the House's birth reasons and causes of death (league/house.py `kill`), as its ledger rows
        # reach the tape, read on the page in its own fixed words: a cause renamed on the House side says nothing
        # there, and this test says so first.
        parent = self.seated()
        needs = {"venue": "alpaca", "horizon": "hour", "style": "test"}
        births = [("an Alpha Lab graduate (param, by house, lineage agent:buyer): a parameter mutation of 0a77b052", "lab graduate"),
                  ("a parameter mutation of its parent", "tweak of Buyer"), ("Test a narrower entry window.", "child of Buyer")]
        rows = [self.house.registry.born(name=f"child-{n}", family="test-family", code=BUYER, needs=needs, parent=parent.id, reason=reason)
                for n, (reason, _) in enumerate(births)]
        causes = [("displaced", "lost its seat"), ("evidence", "lost too much"), ("superseded", "replaced by its fix"), ("redundant", "a duplicate"),
                  ("credits", "out of credits"), ("never qualified", "never passed its history test"), ("stuck", "idle too long")]
        for (cause, _), child in zip(causes, rows + [self.seated(f"gone-{n}") for n in range(len(causes) - len(rows))]):
            self.house.kill(child, cause, f"{child.id} died of {cause} in a test")
        events = [e for entry in self.house.ledger.read(kinds=("agent.born", "agent.died"), limit=100) for e in to_events(entry)
                  if entry.kind == "agent.died" or entry.agent.startswith("child-")]
        script = ("import(process.argv[1]).then(m => { let s = ''; process.stdin.on('data', d => s += d); process.stdin.on('end', () => "
                  "console.log(JSON.stringify(JSON.parse(s).map(e => { const move = m.ladderMove(e); return move && [move.kind, m.reasonWords(move)]; })))); })")
        out = subprocess.run(["node", "-e", script, (SITE / "capital" / "capital.js").as_uri()], input=json.dumps(events), capture_output=True, text=True, timeout=60)
        said = json.loads(out.stdout)
        self.assertEqual([w for kind, w in said if kind == "born"], [words for _, words in births])
        self.assertEqual(sorted(w for kind, w in said if kind == "out"), sorted(words for _, words in causes))

    def test_the_page_reads_every_band_move_the_tape_carries(self):
        agent = self.seated()
        rows = [{"decision": "promote", "from_rung": 1, "to_rung": 2, "band_from": "paper", "band_to": "bunt", "stake_usd": "10", "reason": "E 1.041"},
                {"decision": "promote", "from_rung": 3, "to_rung": 3, "band_from": "swing", "band_to": "star", "stake_usd": "1240.5", "reason": "top P&L"},
                {"decision": "demote", "from_rung": 3, "to_rung": 1, "band_from": "swing", "band_to": "paper", "reason": "a 35% drawdown"},
                {"decision": "size", "rung": 2, "band": "bunt", "stake_usd": "14.2", "reason": "E 1.42"},
                {"decision": "promote", "from_rung": 1, "to_rung": 2, "band_from": "paper", "band_to": "probe", "stake_usd": "10", "reason": "E 1.02"}]
        events = [e for row in rows for e in to_events(self.house.ledger.append("eval.verdict", row, agent=agent.id))]
        script = ("import(process.argv[1]).then(m => { let s = ''; process.stdin.on('data', d => s += d); process.stdin.on('end', () => "
                  "console.log(JSON.stringify(JSON.parse(s).map(e => { const move = m.ladderMove(e); return move && [move.kind, move.fromBand, move.toBand, move.stake]; })))); })")
        out = subprocess.run(["node", "-e", script, (SITE / "capital" / "capital.js").as_uri()], input=json.dumps(events), capture_output=True, text=True, timeout=60)
        self.assertEqual(json.loads(out.stdout), [["up", "paper", "bunt", "10.00"], ["up", "swing", "star", "1240.50"], ["down", "swing", "paper", None], ["size", None, "bunt", "14.20"],
                                                    ["up", "paper", "probe", "10.00"]])

    @unittest.skipUnless(FLYWHEEL_SITE, "the checked-out site predates the flywheel (personal-site #8)")
    def test_the_site_accepts_the_flywheel_and_its_page_draws_it(self):
        # Sept 25, 2026 (W of the forward-first run): the checkpoint's flywheel from health.json (with Y2's unit
        # economics), the board and an hourly yield row, and the sports family's clock and C6 curve, pass the site's
        # validators and read on its page in its own words.
        agent = self.seated()
        self.house.evaluator.promote(agent.id, 2, "fixture evidence")
        families = self.families()
        families["kalshi"]["sports-central-run-under"] = self.sports()
        self.house.allocator = FakeAllocator(self.ledger_board(agent, families=families))
        self.yield_row()
        self.health(unit_economics={"compute_per_day_usd": 122.31, "profit_per_day_usd": 19.38})
        self.clock.advance(5)
        body = self.publisher().checkpoint(self.house)
        self.assertEqual(self.valid(body), "true")
        script = ("import(process.argv[1]).then(m => { let s = ''; process.stdin.on('data', d => s += d); process.stdin.on('end', () => { "
                  "const body = JSON.parse(s); const model = m.boardSnapshot(body, [], Date.parse(body.published_at)); "
                  "console.log(JSON.stringify({ cells: m.flywheelCells(model.flywheel).map(c => [c.name, c.value]), "
                  "rows: model.families.rows.map(r => [m.familyWords(r), m.clockWords(r.clock), m.capacityWords(r.curve)]) })); }); })")
        out = subprocess.run(["node", "-e", script, (SITE / "capital" / "capital.js").as_uri()], input=json.dumps(body), capture_output=True, text=True, timeout=60)
        page = json.loads(out.stdout)
        self.assertEqual(page["cells"], [["Compute", "$122 · 6.3× real profit"], ["Evidence", "8 winning blocks · 2 graduates · 2 edges proven"],
                                         ["Real profit", "+$19.38"], ["Restarts", "24"]])
        self.assertEqual(page["rows"], [
            ["compounding · 40 settlements, 32 real · lower bound +3.1% · 2 agents at $120 · capacity $14/day", "", ""],
            ["proven · 11 settlements, 2 real · lower bound +14.2% · 1 agent at $30", "Compounding review at 15 real settlements · 4 to go at 5.6 a day · about 17 hours",
             "Capacity $32/day at $5.39 · $65/day at $11 · not measured at $22"]])
        # The most the publisher sends of everything is still what the site accepts.
        families["kalshi"]["sports-central-run-under"] = self.sports(swing_clock={**self.swing_clock(real_settlements=10 ** 9, look_at=10 ** 9, distinct_dates=10 ** 6, grant=True),
                                                                                   "real_per_day": 1e12, "days_to_swing": 1e12})
        families["kalshi"]["sports-central-run-under"]["capacity"]["curve"] = [
            {"multiple": k, "size_usd": 1e20, "fill_rate": 1.0, "basis": "all", "usd_per_day": -1e30} for k in (1, 2, 4, 8, 16)]
        for _ in range(60):
            self.yield_row(blocks=(("research", 10 ** 8),), graduates=10 ** 8)
        self.health(restarts_24h=10 ** 12, unit_economics={"compute_per_day_usd": 1e30, "profit_per_day_usd": -1e30})
        self.clock.advance(5)
        body = self.publisher().checkpoint(self.house)
        self.assertEqual(len(body["board"]["families"]["rows"][1]["capacity_curve"]), publish.MAX_CURVE_POINTS)
        self.assertEqual(self.valid(body), "true")


if __name__ == "__main__":
    unittest.main()
