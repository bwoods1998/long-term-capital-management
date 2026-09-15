"""The night desk: triggers, one cheap verdict, a wake or a published ignore (leap: watch)."""

from __future__ import annotations

import threading
import unittest
from decimal import Decimal
from types import SimpleNamespace

from ltcm.broker import OrderIntent
from ltcm.tests.test_desk import DeskCase, FakeProvider as DeskFakeProvider
from ltcm.tests.test_service import AAPL, DESK, FakeProvider, ServiceCase, moment
from ltcm.watch import NightWatch, Trigger, parse_decision


class WatchProvider(FakeProvider):
    """Answers the watch's question the way a flash model would, and remembers the ask."""

    def __init__(self, decision="wake"):
        super().__init__()
        self.decision = decision
        self.packets = []

    def respond(self, profile, items, **kwargs):
        self.calls.append(kwargs.get("request_key"))
        key = kwargs.get("request_key") or ""
        if key.startswith("watch:"):
            self.packets.append((profile, items[1]["content"], kwargs))
            return SimpleNamespace(
                output_text='{"decision": "%s", "reason": "a position moved against the thesis"}' % self.decision,
                cost_usd=Decimal("0.0004"),
            )
        return SimpleNamespace(output_text="memo body", cost_usd=Decimal("0.01"))


class ParseTests(unittest.TestCase):
    def test_a_json_line_is_read_and_prose_is_tolerated(self):
        self.assertEqual(parse_decision('{"decision": "wake", "reason": "it moved"}'), ("wake", "it moved"))
        self.assertEqual(parse_decision('Sure.\n{"decision":"IGNORE","reason":""}'), ("ignore", "no reason given"))
        self.assertEqual(parse_decision("I would ignore this"), ("ignore", "I would ignore this"))
        self.assertIsNone(parse_decision("wake or ignore, hard to say"))
        self.assertIsNone(parse_decision(""))
        self.assertIsNone(parse_decision(None))


class WatchCase(ServiceCase):
    def setUp(self):
        super().setUp()
        self.service.close()
        self.provider = WatchProvider("wake")
        self.service = self.build()
        self.watch = self.service.watch

    def broker_factory(self, venue, *, manifest=None, path=None, settings=None, service=None):
        from ltcm.tests.test_exits import ClockedBroker

        if manifest is None:
            return self.venues.get(venue)
        broker = self.brokers.get(manifest.id)
        if broker is None:
            broker = self.brokers[manifest.id] = ClockedBroker()
        return broker

    def buy(self, at=None, quantity="1"):
        if at is not None:
            self.clock.set(at)
        stamp = self.service.now()
        intent = OrderIntent.new(
            desk_id=DESK, instrument=AAPL, side="buy", quantity=quantity, rationale="a documented beat",
            created_at=stamp, session_id="s", nonce=stamp,
        )
        result = self.service.gateway.propose(intent, stamp)
        self.assertTrue(result["approved"], result["reasons"])
        self.assertEqual(result["status"], "filled", result)
        return intent

    def watch_events(self):
        return [e.payload for e in self.service.log.read(kind="desk.watch")]


class WakeTests(WatchCase):
    def test_a_fill_wakes_the_desk_once_and_the_session_says_why(self):
        self.fund()
        self.tick()  # the scheduled slot runs; the watch sees no fill yet
        self.buy(moment(2026, 9, 14, 13, 51))
        result = self.tick(moment(2026, 9, 14, 13, 52))
        self.assertEqual([d["trigger"] for d in result["watch"]], ["fill"])
        events = self.watch_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["decision"], "wake")
        self.assertIn("fill: buy 1 AAPL", events[0]["detail"])
        self.assertEqual(events[0]["cost_usd"], "0.0004")
        self.assertTrue(events[0]["session_id"].startswith(f"{DESK}:"))
        self.assertIn("watch:fill", self.sessions_started())
        profile, packet, kwargs = self.provider.packets[0]
        self.assertEqual(profile, "flash_asap")
        self.assertIn("Mandate:", packet)
        self.assertIn("Event (fill)", packet)
        self.assertEqual(kwargs["desk_id"], DESK)
        # Another fill inside the cooldown does not wake it again.
        self.buy(moment(2026, 9, 14, 13, 53), quantity="1")
        result = self.tick(moment(2026, 9, 14, 13, 55))
        self.assertEqual(result["watch"], [])
        self.assertEqual(len(self.watch_events()), 1)
        self.assertEqual(self.service.log.read(kind="desk.session_started")[-1].payload["trigger"], "watch:fill")

    def test_an_ignore_is_published_and_wakes_nothing(self):
        self.provider.decision = "ignore"
        self.fund()
        self.tick()
        self.buy(moment(2026, 9, 14, 13, 51))
        result = self.tick(moment(2026, 9, 14, 13, 52))
        self.assertEqual([d["decision"] for d in result["watch"]], ["ignore"])
        self.assertEqual(self.watch_events()[0]["decision"], "ignore")
        self.assertIsNone(self.watch_events()[0]["session_id"])
        self.assertNotIn("watch:fill", self.sessions_started())
        # The ignore leaves the desk eligible: the next trigger is judged again.
        self.provider.decision = "wake"
        self.buy(moment(2026, 9, 14, 13, 53), quantity="1")
        self.tick(moment(2026, 9, 14, 13, 55))
        self.assertIn("watch:fill", self.sessions_started())

    def test_a_held_price_moving_more_than_the_threshold_is_a_trigger(self):
        self.provider.decision = "ignore"
        self.fund()
        self.buy()
        self.tick()  # marks the book at 100 and judges the fill (ignored)
        self.service.market_data.price = Decimal("105")  # five percent, over the three percent line
        self.provider.decision = "wake"
        result = self.tick(moment(2026, 9, 14, 14, 55))  # an hour and five minutes on
        kinds = [d["trigger"] for d in result["watch"]]
        self.assertEqual(kinds, ["price_move"])
        self.assertIn("AAPL moved 5.00%", self.watch_events()[-1]["detail"])
        self.assertIn("watch:price_move", self.sessions_started())

    def test_a_small_move_is_not_a_trigger(self):
        self.provider.decision = "ignore"
        self.fund()
        self.buy()
        self.tick()
        self.service.market_data.price = Decimal("101")
        self.assertEqual(self.tick(moment(2026, 9, 14, 14, 55))["watch"], [])

    def test_the_watch_is_quiet_while_the_desk_is_in_session(self):
        self.fund()
        self.tick()
        self.buy(moment(2026, 9, 14, 13, 51))
        release = threading.Event()
        worker = threading.Thread(target=release.wait, name=f"session-{DESK}-cadence:15:30", daemon=True)
        worker.start()
        self.addCleanup(release.set)
        self.service._sessions.append(worker)
        self.assertEqual(self.tick(moment(2026, 9, 14, 13, 52))["watch"], [])
        self.assertEqual(self.watch_events(), [])

    def test_a_live_desk_on_a_venue_the_floor_cannot_trade_is_left_asleep(self):
        from ltcm.tests.test_exits import ClockedBroker

        self.write_manifest(DESK, capital={"mode": "live", "usd": "1000"})
        self.venues["alpaca"] = ClockedBroker()
        self.provider.decision = "ignore"
        self.service.close()
        self.service = self.build(live_venues=["alpaca"])
        self.fund()
        self.buy()
        self.tick()  # marks the position at 100; the fill is judged and ignored
        # The venue is switched off. The same position moves five percent: no wake.
        self.service.close()
        self.service = self.build(live_venues=[])
        self.service.market_data.price = Decimal("105")
        self.venues["alpaca"].price = Decimal("105")  # the venue's own quote answers first
        self.provider.decision = "wake"
        self.assertEqual(self.tick(moment(2026, 9, 14, 14, 55))["watch"], [])
        self.assertEqual(len(self.watch_events()), 1)
        # Switched back on, the move wakes it.
        self.service.close()
        self.service = self.build(live_venues=["alpaca"])
        self.service.market_data.price = Decimal("105")
        result = self.tick(moment(2026, 9, 14, 14, 58))
        self.assertEqual([(d["trigger"], d["decision"]) for d in result["watch"]], [("price_move", "wake")])

    def test_the_watch_can_be_switched_off_and_never_asks_the_model_without_a_trigger(self):
        self.service.close()
        self.service = self.build(watch={"enabled": False})
        self.assertIsNone(self.service.watch)
        self.fund()
        result = self.tick()
        self.assertEqual(result["watch"], [])
        self.assertNotIn("watch", self.publisher.checkpoints[-1])

    def test_the_checkpoint_counts_the_days_work(self):
        self.fund()
        self.tick()
        self.buy(moment(2026, 9, 14, 13, 51))
        self.tick(moment(2026, 9, 14, 13, 52))
        block = self.publisher.checkpoints[-1]["watch"]
        self.assertEqual(block["triggers_today"], 1)
        self.assertEqual(block["wakes_today"], 1)
        self.assertEqual(str(block["cost_today_usd"]), "0.0004")
        self.assertIsNotNone(block["last_trigger_at"])
        self.assertEqual(self.service.status()["watch"]["wakes_today"], 1)

    def test_the_cooldown_survives_a_restart(self):
        self.fund()
        self.tick()
        self.buy(moment(2026, 9, 14, 13, 51))
        self.tick(moment(2026, 9, 14, 13, 52))
        self.service.close()
        self.service = self.build()
        self.buy(moment(2026, 9, 14, 13, 56), quantity="1")
        self.assertEqual(self.tick(moment(2026, 9, 14, 13, 57))["watch"], [])
        self.assertEqual(len(self.watch_events()), 1)


class TriggerTests(WatchCase):
    def test_a_trigger_names_its_kind_and_what_it_concerns(self):
        trigger = Trigger("fill", "fill: buy 2 AAPL at 100", AAPL.key)
        self.assertEqual(trigger.kind, "fill")
        self.assertEqual(trigger.key, "equity:AAPL:alpaca")

    def test_without_a_provider_the_watch_publishes_an_ignore_it_can_defend(self):
        self.fund()
        self.tick()
        self.buy(moment(2026, 9, 14, 13, 51))
        self.service.provider = None
        result = self.tick(moment(2026, 9, 14, 13, 52))
        self.assertEqual(result["watch"][0]["decision"], "ignore")
        self.assertIn("no model provider", result["watch"][0]["reason"])


class DeskPromptTests(DeskCase):
    def test_a_watch_session_is_told_why_it_was_woken(self):
        self.log.append(
            "desk:earnings-01",
            "desk.watch",
            {"trigger": "price_move", "detail": "AAPL moved 5.00% in the last hour",
             "decision": "wake", "reason": "the move is past the stated invalidation", "cost_usd": "0.0004",
             "session_id": None},
        )
        desk = self.desk(DeskFakeProvider())
        prompt = desk.build_prompt("earnings-01:20260910-0026:watch:price_move", "watch:price_move")
        state = prompt[1]["content"]
        self.assertIn("# Why you were woken", state)
        self.assertIn("AAPL moved 5.00%", state)
        self.assertIn("past the stated invalidation", state)
        scheduled = desk.build_prompt("earnings-01:20260910-0026:cadence:09:35", "cadence:09:35")
        self.assertNotIn("Why you were woken", scheduled[1]["content"])


if __name__ == "__main__":
    unittest.main()
