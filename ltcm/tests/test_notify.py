"""Trade notices: one per live fill and per settlement, folded from the log, never a raise."""

from __future__ import annotations

import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace

from ltcm.events import EventLog
from ltcm.notify import TradeNotifier

T0 = "2026-09-15T14:00:00.000Z"
T1 = "2026-09-15T14:05:00.000Z"
T2 = "2026-09-15T14:06:00.000Z"
INSTRUMENT = {"symbol": "KXFED-26SEP-T3.75", "asset_class": "event", "venue": "kalshi"}


class NotifierCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.log = EventLog(Path(self.temp.name) / "events.sqlite")
        self.state: dict = {}
        self.posts: list = []
        self.alerts: list = []
        self.manifests = {
            "mullins": SimpleNamespace(name="Mullins", capital_mode="live"),
            "mullins-2": SimpleNamespace(name="Mullins II", capital_mode="shadow"),
        }

    def notifier(self, poster=None, enabled=True, token="tok"):
        def post(url, tok, facts):
            self.posts.append((url, tok, facts))
            return {"sent": True}

        return TradeNotifier(
            self.log,
            self.manifests,
            gateway_url="https://gw.example.workers.dev/",
            token=token,
            state=lambda: dict(self.state),
            save_state=lambda **updates: self.state.update(updates),
            alert=lambda level, text: self.alerts.append((level, text)),
            poster=poster or post,
            enabled=enabled,
        )

    def trade(self, *, shadow=False, at=T1, order="o1", intent="oi-1"):
        self.log.append("desk:mullins", "desk.intent", {
            "intent_id": intent, "instrument": INSTRUMENT, "side": "buy", "quantity": "20", "order_type": "limit",
            "limit_price": "0.56", "rationale": "Hot CPI and a Reuters poll put a hike at 93%; the market asks 89%.",
            "target_price": "0.95", "stop_price": "0.40", "time_stop_at": "2026-09-17T18:00:00.000Z",
        }, at=at)
        self.log.append("risk", "risk.decision", {"intent_id": intent, "desk_id": "mullins", "approved": True, "reasons": []}, at=at)
        self.log.append("risk", "risk.review", {"intent_id": intent, "desk_id": "mullins", "verdict": "approve", "reason": "Sized inside the mandate.", "model": "glm"}, at=at)
        self.log.append("broker:kalshi", "broker.order", {"order_id": order, "intent_id": intent, "status": "filled", "filled_quantity": "20", "average_price": "0.56", "desk_id": "mullins", "purpose": "entry"}, at=at)
        self.log.append("desk:mullins", "desk.exit_plan", {"intent_id": intent, "instrument": INSTRUMENT, "target_price": "0.95", "stop_price": "0.40", "time_stop_at": "2026-09-17T18:00:00.000Z", "venue_native": False, "order_ids": []}, at=at)
        return self.log.append("broker:kalshi", "broker.fill", {
            "fill_id": f"f-{order}", "order_id": order, "instrument": INSTRUMENT, "side": "buy", "quantity": "20", "price": "0.56", "fee": "0.14",
            **({"shadow": True} if shadow else {}),
        }, at=at)


class NotifierTests(NotifierCase):
    def test_missing_mail_binding_retries_without_claiming_delivery(self):
        answers = iter([{"sent": False}, {"sent": True}])
        notifier = self.notifier(poster=lambda *args: next(answers))
        notifier.tick(T0)
        fill = self.trade(at=T1)
        self.assertEqual(notifier.tick(T2), [])
        self.assertLess(self.state["notify_seq"], fill.seq)
        self.assertEqual(self.state["notify_failed_seq"], fill.seq)
        self.assertEqual(self.state["notify_sent_total"], 0)
        self.assertEqual(notifier.tick(T2), [fill.id])
        self.assertIsNone(self.state["notify_failed_seq"])
        self.assertEqual(self.state["notify_sent_total"], 1)

    def test_the_first_tick_sets_the_floor_and_mails_nothing_old(self):
        self.trade(at=T0)
        notifier = self.notifier()
        self.assertEqual(notifier.tick(T1), [])
        self.assertEqual(self.posts, [])
        self.assertEqual(self.state["notify_floor"], T1)

    def test_a_live_fill_becomes_one_notice_with_the_desks_reasons(self):
        notifier = self.notifier()
        notifier.tick(T0)
        fill = self.trade(at=T1)
        sent = notifier.tick(T2)
        self.assertEqual(sent, [fill.id])
        url, token, facts = self.posts[0]
        self.assertEqual(url, "https://gw.example.workers.dev/v1/notify")
        self.assertEqual(token, "tok")
        self.assertEqual(facts["kind"], "trade")
        self.assertEqual(facts["desk_name"], "Mullins")
        self.assertEqual(facts["instrument"], "KXFED-26SEP-T3.75")
        self.assertEqual(facts["venue"], "kalshi")
        self.assertEqual((facts["side"], facts["quantity"], facts["price"], facts["fee"]), ("buy", "20", "0.56", "0.14"))
        self.assertIn("Reuters poll", facts["rationale"])
        self.assertEqual(facts["engine"], "approved")
        self.assertEqual(facts["critic"], "approve: Sized inside the mandate.")
        self.assertEqual((facts["target_price"], facts["stop_price"]), ("0.95", "0.40"))
        self.assertEqual(facts["story_url"], "https://blakewoods.us/capital/desk/?id=mullins#story-oi-1")
        # Once is enough.
        self.assertEqual(notifier.tick("2026-09-15T14:07:00.000Z"), [])
        self.assertEqual(len(self.posts), 1)

    def test_the_fills_of_one_order_in_one_tick_are_one_notice(self):
        # A 333-contract weather order filled in six pieces on Sept 16, 2026: one email, not six.
        notifier = self.notifier()
        notifier.tick(T0)
        first = self.trade(at=T1)
        second = self.log.append("broker:kalshi", "broker.fill", {
            "fill_id": "f-o1-b", "order_id": "o1", "instrument": INSTRUMENT, "side": "buy", "quantity": "10", "price": "0.59", "fee": "0.07",
        }, at="2026-09-15T14:05:30.000Z")
        other = self.trade(at="2026-09-15T14:05:40.000Z", order="o2", intent="oi-2")
        sent = notifier.tick(T2)
        self.assertEqual(sorted(sent), sorted([first.id, second.id, other.id]))
        self.assertEqual(len(self.posts), 2, "one notice per order, not per fill")
        grouped = self.posts[0][2]
        self.assertEqual((grouped["quantity"], grouped["price"], grouped["fee"]), ("30", "0.5700", "0.21"))
        self.assertEqual(grouped["at"], "2026-09-15T14:05:30.000Z")
        self.assertEqual(self.posts[1][2]["quantity"], "20")

    def test_a_shadow_fill_is_a_score_not_a_notice(self):
        notifier = self.notifier()
        notifier.tick(T0)
        self.trade(at=T1, shadow=True)
        self.assertEqual(notifier.tick(T2), [])
        self.assertEqual(self.posts, [])

    def test_a_settlement_on_a_live_desk_is_a_notice_with_the_pnl(self):
        notifier = self.notifier()
        notifier.tick(T0)
        outcome = self.log.append("desk:mullins", "desk.outcome", {
            "instrument": INSTRUMENT, "market_id": "KXFED-26SEP-T3.75", "result": "yes", "entry_price": "0.56",
            "exit_price": "1.00", "quantity": "20", "pnl": "8.66", "held_for_hours": "26", "rationale_excerpt": "Hike at 93%.",
        }, at=T1)
        shadow = self.log.append("desk:mullins-2", "desk.outcome", {
            "instrument": INSTRUMENT, "market_id": "KXFED-26SEP-T3.75", "result": "yes", "entry_price": "0.56",
            "exit_price": "1.00", "quantity": "20", "pnl": "8.66", "held_for_hours": "26", "rationale_excerpt": "Hike at 93%.",
        }, at=T1)
        sent = notifier.tick(T2)
        self.assertEqual(sent, [outcome.id])
        facts = self.posts[0][2]
        self.assertEqual(facts["kind"], "settled")
        self.assertEqual(facts["pnl"], "8.66")
        self.assertEqual(facts["desk_name"], "Mullins")
        self.assertNotIn(shadow.id, sent)

    def test_a_gateway_failure_alerts_and_the_notice_is_retried_next_tick(self):
        calls = {"n": 0}

        def flaky(url, token, facts):
            calls["n"] += 1
            if calls["n"] == 1:
                raise urllib.error.HTTPError(url, 502, "bad gateway", {}, None)
            return {"sent": True}

        notifier = self.notifier(poster=flaky)
        notifier.tick(T0)
        fill = self.trade(at=T1)
        self.assertEqual(notifier.tick(T2), [])
        self.assertTrue(any("refused: http 502" in text for _, text in self.alerts))
        self.assertEqual(notifier.tick("2026-09-15T14:07:00.000Z"), [fill.id])

    def test_a_capped_day_is_said_once_and_left_for_later(self):
        def capped(url, token, facts):
            raise urllib.error.HTTPError(url, 429, "cap", {}, None)

        notifier = self.notifier(poster=capped)
        notifier.tick(T0)
        self.trade(at=T1)
        self.assertEqual(notifier.tick(T2), [])
        self.assertTrue(any("daily notice cap" in text for _, text in self.alerts))

    def test_news_older_than_a_day_is_let_go(self):
        notifier = self.notifier()
        notifier.tick(T0)
        self.trade(at="2026-09-15T14:01:00.000Z")
        self.assertEqual(notifier.tick("2026-09-17T14:00:00.000Z"), [])
        self.assertEqual(self.posts, [])

    def test_without_a_gateway_or_a_token_it_does_nothing(self):
        notifier = self.notifier(token=None)
        self.assertFalse(notifier.enabled)
        self.trade(at=T1)
        self.assertEqual(notifier.tick(T2), [])


if __name__ == "__main__":
    unittest.main()
