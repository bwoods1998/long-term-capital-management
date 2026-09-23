import json
import os
import shutil
import subprocess
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.broker import Balance

from league import publish
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


SITE = Path(os.environ.get("LTCM_SITE") or Path(__file__).resolve().parents[3] / "personal-site")


@unittest.skipUnless(shutil.which("node") and (SITE / "capital" / "schema.js").exists(), "the site's validators are not checked out beside this repository (set LTCM_SITE)")
class SiteAcceptsTheBoardTest(BoardCase):
    """The site's own validators (personal-site/capital/schema.js), run on what this publisher posts."""

    def valid(self, body):
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

    def test_the_page_reads_every_band_move_the_tape_carries(self):
        agent = self.seated()
        rows = [{"decision": "promote", "from_rung": 1, "to_rung": 2, "band_from": "paper", "band_to": "bunt", "stake_usd": "10", "reason": "E 1.041"},
                {"decision": "promote", "from_rung": 3, "to_rung": 3, "band_from": "swing", "band_to": "star", "stake_usd": "1240.5", "reason": "top P&L"},
                {"decision": "demote", "from_rung": 3, "to_rung": 1, "band_from": "swing", "band_to": "paper", "reason": "a 35% drawdown"},
                {"decision": "size", "rung": 2, "band": "bunt", "stake_usd": "14.2", "reason": "E 1.42"}]
        events = [e for row in rows for e in to_events(self.house.ledger.append("eval.verdict", row, agent=agent.id))]
        script = ("import(process.argv[1]).then(m => { let s = ''; process.stdin.on('data', d => s += d); process.stdin.on('end', () => "
                  "console.log(JSON.stringify(JSON.parse(s).map(e => { const move = m.ladderMove(e); return move && [move.kind, move.fromBand, move.toBand, move.stake]; })))); })")
        out = subprocess.run(["node", "-e", script, (SITE / "capital" / "capital.js").as_uri()], input=json.dumps(events), capture_output=True, text=True, timeout=60)
        self.assertEqual(json.loads(out.stdout), [["up", "paper", "bunt", "10.00"], ["up", "swing", "star", "1240.50"], ["down", "swing", "paper", None], ["size", None, "bunt", "14.20"]])


if __name__ == "__main__":
    unittest.main()
