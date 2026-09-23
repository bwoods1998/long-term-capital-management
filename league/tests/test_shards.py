"""The Kalshi shard funder (league/shards.py, Sept 23, 2026): collateral follows the desks."""

from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from ltcm.broker import Instrument

from league import shards
from league.ledger import Ledger, now_iso
from league.tests.fakes import Clock

D = Decimal


class FakeShardBroker:
    """The two shard calls of `KalshiBroker`, over an in-memory account."""

    def __init__(self, balances):
        self.balances = {int(k): D(str(v)) for k, v in balances.items()}
        self.transfers = []
        self.fail_next = None
        self.reads = 0

    def shard_balances(self):
        self.reads += 1
        return dict(self.balances)

    def transfer_between_shards(self, usd, source, destination):
        if self.fail_next is not None:
            exc, self.fail_next = self.fail_next, None
            raise exc
        usd = D(str(usd))
        self.transfers.append((usd, int(source), int(destination)))
        self.balances[int(source)] = self.balances.get(int(source), D(0)) - usd
        self.balances[int(destination)] = self.balances.get(int(destination), D(0)) + usd
        return f"tr-{len(self.transfers)}"


class FakeBook:
    def __init__(self, broker):
        self.name = "kalshi"
        self.real_money = True
        self.frozen = None
        self.broker = broker
        self.stakes = {}
        self.holdings = {}  # agent -> [tickers]
        self.resting = []  # tickers

    def agents(self):
        return sorted(set(self.stakes) | set(self.holdings))

    def account(self, agent):
        held = {t: SimpleNamespace(instrument=Instrument("event", t, "kalshi", market_id=t), quantity=D(1)) for t in self.holdings.get(agent, [])}
        return SimpleNamespace(staked=self.stakes.get(agent, D(0)), holdings=held)

    def open_orders(self, agent=None):
        return [SimpleNamespace(instrument=Instrument("event", t, "kalshi", market_id=t)) for t in self.resting]


class FakeHouse:
    """What the funder reads of the House: the ledger, the real book, the guards, the desks and
    the shared listing. `_background` runs the job inline and records it."""

    def __init__(self, root, clock, broker):
        self.root = Path(root)
        self.clock = clock
        self.ledger = Ledger(self.root / "ledger.sqlite", clock=clock)
        self.books = {"kalshi": FakeBook(broker)}
        self.killed = False
        self.kill_switch = lambda: self.killed
        self.grant = {"active": True, "revoked": None}
        self.campaigns = SimpleNamespace(live_authorization=lambda: self.grant)
        self.pause = None
        self.agents = []
        self.registry = SimpleNamespace(living=lambda: list(self.agents), get=lambda i: next((a for a in self.agents if a.id == i), None))
        self.listings = {}  # series -> rows
        self.listing_calls = []
        self.jobs = []

    def paused(self):
        return self.pause

    def alert(self, level, text):
        self.ledger.append("ops.alert", {"level": level, "text": text})

    def _markets(self, series, hours, max_age):
        self.listing_calls.append((tuple(series), hours, max_age))
        rows = []
        for name in series:
            if isinstance(self.listings.get(name), Exception):
                raise self.listings[name]
            rows.extend(self.listings.get(name) or [])
        return rows

    def _background(self, key, work, *args):
        self.jobs.append(key)
        work(*args)
        return True

    def desk(self, ident, *series):
        agent = SimpleNamespace(id=ident, venue="kalshi", needs={"series": list(series)})
        self.agents.append(agent)
        return agent

    def alerts(self, level=None):
        return [e for e in self.ledger.read(kinds="ops.alert", limit=1000) if level is None or e.payload["level"] == level]

    def moves(self):
        return [e.payload["shard_move"] for e in self.alerts() if "shard_move" in e.payload]


def market(ticker, shard):
    return {"market": ticker, "series": shards.series_of(ticker), "exchange_index": shard}


class FunderCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.broker = FakeShardBroker({0: "372.81", 2: "36.60"})
        self.house = FakeHouse(self.dir.name, self.clock, self.broker)
        self.house.listings["KXMLBTOTAL"] = [market("KXMLBTOTAL-26SEP231840STLPIT-8", 3)]
        self.house.listings["KXBTC15M"] = [market("KXBTC15M-26SEP231700-1", 2)]
        self.house.listings["KXHIGHNY"] = [market("KXHIGHNY-26SEP23-B80", 0)]
        self.funder = shards.ShardFunder(self.house, self.dir.name, clock=self.clock)

    def tearDown(self):
        self.house.ledger.close()
        self.dir.cleanup()


class WantedShards(FunderCase):
    def test_the_wanted_shards_follow_the_listings_the_desks_are_offered(self):
        self.house.desk("sports-1", "KXMLBTOTAL")
        self.house.desk("weather-1", "KXHIGHNY")
        wanted, unmapped, errors = self.funder.wanted()
        self.assertEqual(wanted, {0, 3})
        self.assertEqual((unmapped, errors), (set(), []))
        # The listing is read through the House's shared cache, an hour old at most.
        self.assertEqual(self.house.listing_calls[0][2], shards.LISTING_MAX_AGE)
        # And the series -> shard map is learned and kept, so a refusal can name its shard.
        self.assertEqual(self.funder.shard_of("KXMLBTOTAL-26SEP231840STLPIT-8"), 3)
        self.assertEqual(self.funder.shard_of("KXNFLGAME-X"), None)

    def test_a_shard_holding_a_position_or_a_resting_order_is_wanted_too(self):
        self.house.desk("crypto-1", "KXBTC15M")
        self.funder.wanted()  # learns crypto -> 2
        book = self.house.books["kalshi"]
        book.holdings["sports-old"] = ["KXMLBTOTAL-26SEP231840STLPIT-8"]
        book.resting = ["KXHIGHNY-26SEP23-B80"]
        self.house.listings["KXHIGHNY"] = [market("KXHIGHNY-26SEP23-B80", 0)]
        self.house.desk("weather-1", "KXHIGHNY")
        wanted, unmapped, _ = self.funder.wanted()
        self.assertIn(2, wanted)
        self.assertIn(0, wanted)
        # The sports position's series was never listed to a living desk: its shard is unknown and said so.
        self.assertEqual(unmapped, {"KXMLBTOTAL-26SEP231840STLPIT-8"})

    def test_a_listing_without_the_shard_field_maps_nothing_and_says_so(self):
        self.house.listings["KXMLBTOTAL"] = [{"market": "KXMLBTOTAL-1", "series": "KXMLBTOTAL"}]
        self.house.desk("sports-1", "KXMLBTOTAL")
        wanted, unmapped, _ = self.funder.wanted()
        self.assertEqual((wanted, unmapped), (set(), {"KXMLBTOTAL"}))

    def test_a_listing_that_is_down_is_an_error_not_a_stop(self):
        self.house.listings["KXMLBTOTAL"] = RuntimeError("429")
        self.house.desk("sports-1", "KXMLBTOTAL")
        self.house.desk("weather-1", "KXHIGHNY")
        wanted, _, errors = self.funder.wanted()
        self.assertEqual(wanted, {0})
        self.assertEqual(errors, ["KXMLBTOTAL: RuntimeError"])


class Funding(FunderCase):
    def test_a_wanted_shard_under_the_floor_is_funded_from_the_richest_donor(self):
        self.house.desk("sports-1", "KXMLBTOTAL")
        report = self.funder.run()
        self.assertEqual(self.broker.transfers, [(D("30"), 0, 3)])
        self.assertEqual(self.broker.balances[3], D("30"))
        self.assertEqual(self.broker.balances[0], D("342.81"))
        move = self.house.moves()[0]
        self.assertTrue(move["ok"])
        self.assertEqual((move["source"], move["destination"], move["usd"], move["transfer_id"]), (0, 3, "30.00", "tr-1"))
        self.assertEqual(move["before"], {"0": "372.81", "2": "36.60"})
        self.assertEqual(move["after"], {"0": "342.81", "2": "36.60", "3": "30.00"})
        self.assertEqual(self.house.alerts("info")[0].payload["level"], "info")
        self.assertEqual(report["blocked"], None)
        self.assertEqual(self.funder.health()["balances"]["3"], "30.00")
        self.assertEqual(self.funder.health()["moved_24h_usd"], "30.00")

    def test_a_shard_at_or_above_the_floor_is_left_alone(self):
        self.broker.balances[3] = D("22.77")
        self.house.desk("sports-1", "KXMLBTOTAL")
        self.funder.run()
        self.assertEqual(self.broker.transfers, [])

    def test_the_home_shard_is_never_drawn_below_the_stakes_of_the_desks_on_it(self):
        self.broker.balances[0] = D("100")
        self.house.desk("sports-1", "KXMLBTOTAL")
        self.house.desk("weather-1", "KXHIGHNY")
        book = self.house.books["kalshi"]
        book.stakes = {"weather-1": D("50"), "sports-1": D("10"), "gone-agent": D("30")}
        # Shard 0 must keep max($60, $50 weather + $30 of an agent whose shard cannot be told) = $80.
        self.funder.run()
        self.assertEqual(self.broker.transfers, [(D("20"), 0, 3)])
        self.assertEqual(self.broker.balances[0], D("80"))

    def test_a_funded_shard_may_donate_down_to_its_own_floor(self):
        self.broker.balances[0] = D("62")  # the home shard can spare only $2 above its $60 keep
        self.house.desk("sports-1", "KXMLBTOTAL")
        self.funder.run()
        self.assertEqual(self.broker.transfers, [(D("16.60"), 2, 3)])
        self.assertEqual(self.broker.balances[2], shards.FLOOR_USD)

    def test_no_donor_can_spare_the_minimum_so_nothing_moves_and_it_is_said(self):
        self.broker.balances[0] = D("62")
        self.broker.balances[2] = D("22")
        self.house.desk("sports-1", "KXMLBTOTAL")
        self.funder.run()
        self.assertEqual(self.broker.transfers, [])
        warnings = [e.payload["text"] for e in self.house.alerts("warning")]
        self.assertTrue(any("shard 3 holds $0.00" in w and "no other shard can spare" in w for w in warnings), warnings)
        # Said once an hour, not once a pass.
        self.funder.run()
        self.assertEqual(len(self.house.alerts("warning")), 1)

    def test_one_move_is_capped_at_the_plan_bound(self):
        self.house.desk("sports-1", "KXMLBTOTAL")
        with unittest.mock.patch.object(shards, "TOP_UP_USD", D("500")):
            self.funder.run()
        self.assertEqual(self.broker.transfers, [(shards.MAX_MOVE_USD, 0, 3)])

    def test_the_rolling_day_is_capped_and_counted_from_the_ledger(self):
        self.broker.balances[0] = D("2000")
        self.house.desk("sports-1", "KXMLBTOTAL")
        with unittest.mock.patch.object(shards, "TOP_UP_USD", D("100")):
            for _ in range(3):
                self.broker.balances[3] = D("0")  # spent between passes
                self.funder.run()
                self.clock.advance(3600)
        self.assertEqual([t[0] for t in self.broker.transfers], [D("100"), D("100")])
        self.assertTrue(any("the day's $200 is spent" in e.payload["text"] for e in self.house.alerts("warning")))
        # A restart does not reset the day: a new funder over the same ledger sees the $200.
        again = shards.ShardFunder(self.house, self.dir.name, clock=self.clock)
        self.assertEqual(again.moved_in_day(), D("200"))
        # And a day later the window has rolled on.
        self.clock.advance(shards.DAY_SECONDS)
        self.assertEqual(again.moved_in_day(), D("0"))

    def test_a_refusal_requested_shard_is_funded_even_before_a_listing_names_it(self):
        self.funder.request(3)
        self.assertTrue(self.funder.due())
        self.funder.run()
        self.assertEqual(self.broker.transfers, [(D("30"), 0, 3)])
        self.assertFalse(self.funder.due())


class Guards(FunderCase):
    def test_nothing_moves_under_the_kill_switch(self):
        self.house.desk("sports-1", "KXMLBTOTAL")
        self.house.killed = True
        report = self.funder.run()
        self.assertEqual(self.broker.transfers, [])
        self.assertEqual(report["blocked"], "the kill switch is engaged")
        self.assertTrue(any("kill switch" in e.payload["text"] for e in self.house.alerts("warning")))

    def test_nothing_moves_without_an_active_grant(self):
        self.house.desk("sports-1", "KXMLBTOTAL")
        for grant in (None, {"active": False}, {"active": True, "revoked": 1.0}):
            self.house.grant = grant
            self.assertEqual(self.funder.run()["blocked"], "no live grant is active")
        self.assertEqual(self.broker.transfers, [])

    def test_nothing_moves_while_paused_or_frozen(self):
        self.house.desk("sports-1", "KXMLBTOTAL")
        self.house.pause = {"reason": "maintenance"}
        self.assertEqual(self.funder.run()["blocked"], "the House is paused")
        self.house.pause = None
        self.house.books["kalshi"].frozen = "does not reconcile"
        self.assertIn("frozen", self.funder.run()["blocked"])
        self.assertEqual(self.broker.transfers, [])

    def test_the_balances_are_read_but_not_moved_while_blocked(self):
        self.house.killed = True
        self.funder.run()
        self.assertEqual(self.broker.reads, 1)
        self.assertEqual(self.funder.health()["balances"], {"0": "372.81", "2": "36.60"})


class Failures(FunderCase):
    def test_a_failed_transfer_is_recorded_re_read_and_backed_off(self):
        self.house.desk("sports-1", "KXMLBTOTAL")
        self.broker.fail_next = RuntimeError("kalshi shard transfer: HTTP 500")
        self.funder.run()
        move = self.house.moves()[0]
        self.assertFalse(move["ok"])
        self.assertIn("HTTP 500", move["error"])
        self.assertEqual(move["after"], {"0": "372.81", "2": "36.60"})  # read again after the failure
        self.assertEqual(self.broker.reads, 2)
        self.assertEqual(self.house.alerts("warning")[0].payload["level"], "warning")
        self.assertIn("3", self.funder.health()["backoff"])
        # Not tried again within the hour, even by a refusal's request; tried after it.
        self.funder.request(3)
        self.funder.run()
        self.assertEqual(self.broker.transfers, [])
        self.clock.advance(shards.BACKOFF_SECONDS + 1)
        self.funder.run()
        self.assertEqual(self.broker.transfers, [(D("30"), 0, 3)])

    def test_a_broker_that_cannot_read_shards_does_nothing_and_says_nothing_false(self):
        self.house.books["kalshi"].broker = object()
        self.assertIn("cannot read", self.funder.run()["blocked"])

    def test_a_reader_that_raises_is_a_warning_not_a_crash(self):
        self.house.books["kalshi"].broker.shard_balances = lambda: (_ for _ in ()).throw(RuntimeError("gateway 502"))
        report = self.funder.run()
        self.assertIn("gateway 502", report["error"])
        self.assertIn("gateway 502", self.funder.health()["last_error"])


class Refusals(FunderCase):
    def refuse(self, agent, ticker, reason="kalshi order: HTTP 404 insufficient_shard_balance Exchange user not found"):
        return self.house.ledger.append("book.order", {
            "book": "kalshi", "order_id": f"o-{ticker}-{agent}", "status": "rejected", "reason": reason,
            "instrument": Instrument("event", ticker, "kalshi", market_id=ticker).to_dict(),
            "shares": [{"intent_id": "i-1", "agent": agent, "quantity": "5", "reason": "test"}], "real_money": True})

    def test_a_shard_refusal_is_told_at_once_and_funded_before_the_hour(self):
        self.house.desk("sports-1", "KXMLBTOTAL")
        self.funder.run()  # the hourly pass: learns sports -> 3 and funds it
        self.broker.balances[3] = D("0")  # then the collateral is gone (positions took it)
        self.assertFalse(self.funder.due())
        self.refuse("sports-1", "KXMLBTOTAL-26SEP231840STLPIT-8")
        self.assertTrue(self.funder.tick())
        warning = next(e.payload["text"] for e in self.house.alerts("warning"))
        self.assertIn("sports-1", warning)
        self.assertIn("KXMLBTOTAL-26SEP231840STLPIT-8", warning)
        self.assertIn("shard 3", warning)
        self.assertEqual(self.house.jobs, [shards.JOB])
        self.assertEqual(self.broker.transfers[-1], (D("30"), 0, 3))

    def test_the_scan_is_incremental_and_ignores_other_refusals(self):
        self.house.desk("sports-1", "KXMLBTOTAL")
        self.refuse("sports-1", "KXMLBTOTAL-26SEP231840STLPIT-8")  # before the funder first existed: handled by hand
        self.funder = shards.ShardFunder(self.house, Path(self.dir.name) / "fresh-root", clock=self.clock)
        self.assertEqual(self.funder.scan_refusals(), [])
        self.refuse("sports-1", "KXMLBTOTAL-26SEP231840STLPIT-9", reason="kalshi order: HTTP 400 order too small")
        self.house.ledger.append("book.order", {"book": "kalshi-shadow", "order_id": "x", "status": "rejected",
                                                "reason": "insufficient_shard_balance", "instrument": {}, "shares": []})
        self.assertEqual(self.funder.scan_refusals(), [])
        first = self.refuse("sports-1", "KXMLBTOTAL-26SEP231840STLPIT-7")
        found = self.funder.scan_refusals()
        self.assertEqual([(f["market"], f["seq"]) for f in found], [("KXMLBTOTAL-26SEP231840STLPIT-7", first.seq)])
        self.assertEqual(self.funder.scan_refusals(), [])  # the cursor moved past it
        self.assertEqual(self.funder.state["cursor"], first.seq)

    def test_a_refusal_on_an_unlisted_series_still_schedules_a_pass(self):
        self.refuse("props-1", "KXNBAPTS-26OCT01-LAL-30")
        self.assertTrue(self.funder.tick())
        warning = next(e.payload["text"] for e in self.house.alerts("warning"))
        self.assertIn("no listing has named", warning)
        self.assertEqual(self.house.jobs, [shards.JOB])

    def test_the_cursor_survives_a_restart(self):
        self.funder.scan_refusals()
        self.refuse("sports-1", "KXMLBTOTAL-26SEP231840STLPIT-8")
        again = shards.ShardFunder(self.house, self.dir.name, clock=self.clock)
        self.assertEqual(len(again.scan_refusals()), 1)


class Schedule(FunderCase):
    def test_the_hourly_pass_is_scheduled_on_the_ops_lane_once_an_hour(self):
        self.assertTrue(self.funder.tick())
        self.assertEqual(self.house.jobs, [shards.JOB])
        self.assertFalse(self.funder.tick())
        self.clock.advance(shards.INTERVAL_SECONDS)
        self.assertTrue(self.funder.tick())
        self.assertEqual(self.house.jobs, [shards.JOB, shards.JOB])

    def test_health_shows_the_check_the_balances_and_the_day(self):
        self.house.desk("sports-1", "KXMLBTOTAL")
        self.funder.run()
        health = self.funder.health()
        self.assertEqual(health["last_check"], now_iso(self.clock))
        self.assertEqual(health["wanted"], [3])
        self.assertEqual(health["series"], {"KXMLBTOTAL": 3})
        self.assertEqual((health["moved_24h_usd"], health["day_cap_usd"]), ("30.00", "200.00"))

    def test_state_is_persisted_under_the_root(self):
        self.house.desk("sports-1", "KXMLBTOTAL")
        self.funder.run()
        again = shards.ShardFunder(self.house, self.dir.name, clock=self.clock)
        self.assertEqual(again.state["series"], {"KXMLBTOTAL": 3})
        self.assertFalse(again.due())


class TheHouseHook(unittest.TestCase):
    """The House builds the funder with its real Kalshi book, ticks it, and shows it in health."""

    def setUp(self):
        from unittest.mock import patch

        strategies = patch("league.strategies.all_strategies", return_value=[])
        strategies.start()
        self.addCleanup(strategies.stop)
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def test_a_house_with_a_real_kalshi_book_funds_shards_off_the_tick_and_reports_them(self):
        import json

        from league.economy import load_game
        from league.house import House, Settings
        from league.tests.fakes import FakeBroker
        from league.tests.test_ladder import InProcessSandbox

        class KalshiWithShards(FakeBroker):
            def __init__(self):
                super().__init__("kalshi", cash="400", family="kalshi")
                self.shards = FakeShardBroker({0: "372.81", 2: "36.60"})

            def shard_balances(self):
                return self.shards.shard_balances()

            def transfer_between_shards(self, usd, source, destination):
                return self.shards.transfer_between_shards(usd, source, destination)

        game = load_game()
        game["economy"]["min_population"] = 0
        game["economy"]["newcomer_seconds"] = 10 ** 9
        clock = Clock()
        broker = KalshiWithShards()
        house = House(Path(self.dir.name) / "house", brokers={"kalshi": broker}, sandbox=InProcessSandbox(), clock=clock,
                      settings=Settings(mark_every_seconds=0, research=False, real_money=True), game=game)
        self.addCleanup(lambda: house.close(wait=None))
        self.assertIsNotNone(house.shards)
        house.tick()
        house.wait(10)  # the pass ran on the ops lane, not on the tick: a finished job leaves its `ops.job` row
        self.assertIn(shards.JOB, [e.payload.get("key") for e in house.ledger.read(kinds="ops.job", limit=100)])
        clock.advance(60)
        house.tick()  # not due again: the second tick writes the health the first pass left
        health = json.loads((Path(self.dir.name) / "house" / "health.json").read_text(encoding="utf-8"))["shards"]
        self.assertEqual(health["balances"], {"0": "372.81", "2": "36.60"})
        self.assertEqual(health["blocked"], "no live grant is active")  # a test House holds no grant: read, never moved
        self.assertEqual(broker.shards.transfers, [])
        self.assertTrue((Path(self.dir.name) / "house" / "shards.json").exists())

    def test_a_house_without_a_real_kalshi_book_has_no_funder(self):
        from league.economy import load_game
        from league.house import House, Settings
        from league.sandbox import LocalSandbox
        from league.tests.fakes import FakeBroker

        game = load_game()
        game["economy"]["min_population"] = 0
        house = House(Path(self.dir.name) / "house", brokers={"alpaca-paper": FakeBroker("alpaca-paper")}, sandbox=LocalSandbox(),
                      clock=Clock(), settings=Settings(mark_every_seconds=0, research=False), game=game)
        self.addCleanup(lambda: house.close(wait=None))
        self.assertIsNone(house.shards)


import unittest.mock  # noqa: E402 - used by the cap tests above through `unittest.mock.patch`


if __name__ == "__main__":
    unittest.main()
