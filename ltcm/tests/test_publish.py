import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.events import EventLog
from ltcm.publish import (
    payload_problem,
    CHECKPOINT_PATH,
    EVENTS_PATH,
    Publisher,
    PublishError,
    checkpoint_body,
    jsonable,
    sanitize_for_site,
    shape_problem,
)

TOKEN = "publish-token-not-a-real-secret"


class FakeTransport:
    """Records every request and answers from a scripted queue. Never opens a socket."""

    def __init__(self, status=200, body=b'{"ok":true}'):
        self.calls = []
        self.status = status
        self.body = body
        self.script = []  # list of (status, headers, body) consumed first
        self.fail_with = None

    def request(self, method, url, *, headers=None, body=None, timeout=None):
        payload = json.loads(body.decode("utf-8")) if body else None
        self.calls.append(
            {"method": method, "url": url, "headers": dict(headers or {}), "payload": payload}
        )
        if self.fail_with is not None:
            error, self.fail_with = self.fail_with, None
            raise error
        if self.script:
            return self.script.pop(0)
        return self.status, {}, self.body

    # -- convenience ------------------------------------------------------
    def events_sent(self):
        return [
            event
            for call in self.calls
            if call["url"].endswith(EVENTS_PATH)
            for event in call["payload"]["events"]
        ]

    def batches(self):
        return [call for call in self.calls if call["url"].endswith(EVENTS_PATH)]


class PublisherCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log = EventLog(self.root / "events.sqlite")
        self.transport = FakeTransport()
        self.slept = []
        self.publisher = Publisher(
            self.log,
            "https://blakewoods.us/",
            lambda: TOKEN,
            self.transport,
            state_path=self.root / "publish-state.json",
            sleeper=self.slept.append,
        )

    def tearDown(self):
        self.log.close()
        self.tmp.cleanup()

    def thought(self, text="reading the 8-K", desk="earnings-01", at="2026-09-14T14:00:00.000Z"):
        return self.log.append(
            f"desk:{desk}", "desk.thought", {"session_id": "s1", "text": text}, at=at
        )


class EventTests(PublisherCase):
    def test_public_events_are_sent_once_with_a_bearer_token(self):
        first = self.thought("one")
        second = self.thought("two")
        summary = self.publisher.push_events()
        self.assertEqual(summary["sent"], 2)
        self.assertEqual(summary["batches"], 1)
        call = self.transport.batches()[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["url"], "https://blakewoods.us/api/capital/events")
        self.assertEqual(call["headers"]["Authorization"], f"Bearer {TOKEN}")
        self.assertEqual(call["payload"]["schema_version"], 1)
        self.assertEqual([e["id"] for e in call["payload"]["events"]], [first.id, second.id])
        self.assertEqual(
            sorted(call["payload"]["events"][0]),
            ["at", "digest", "id", "kind", "payload", "seq", "stream"],
        )
        # A second call sends nothing: the cursor moved.
        self.assertEqual(self.publisher.push_events()["sent"], 0)
        self.assertEqual(len(self.transport.batches()), 1)

    def test_state_survives_a_new_publisher(self):
        self.thought()
        self.publisher.push_events()
        state = json.loads((self.root / "publish-state.json").read_text())
        self.assertEqual(state["last_seq"], self.log.latest_seq())
        self.assertEqual(state["sent"], 1)
        fresh = Publisher(
            self.log,
            "https://blakewoods.us",
            TOKEN,
            self.transport,
            state_path=self.root / "publish-state.json",
            sleeper=self.slept.append,
        )
        self.assertEqual(fresh.push_events()["sent"], 0)

    def test_batches_are_capped_at_one_hundred(self):
        for n in range(230):
            self.thought(f"note {n}")
        summary = self.publisher.push_events()
        self.assertEqual(summary["sent"], 230)
        self.assertEqual(summary["batches"], 3)
        self.assertEqual([len(b["payload"]["events"]) for b in self.transport.batches()],
                         [100, 100, 30])

    def test_deferred_events_wait_for_their_release(self):
        intent = self.log.append(
            "desk:earnings-01",
            "desk.intent",
            {"intent_id": "oi-1", "instrument": {}, "side": "buy", "quantity": "1",
             "order_type": "market", "rationale": "drift"},
        )
        self.thought("thinking out loud")
        self.assertFalse(intent.public)
        summary = self.publisher.push_events()
        self.assertEqual(summary["sent"], 1)
        self.assertEqual(summary["held"], 1)
        self.assertNotIn(intent.id, [e["id"] for e in self.transport.events_sent()])
        self.assertEqual(json.loads((self.root / "publish-state.json").read_text())["held"],
                         [intent.id])

        released = self.publisher.push_events([intent.id])
        self.assertEqual(released["sent"], 1)
        self.assertEqual(released["held"], 0)
        self.assertEqual(self.transport.batches()[-1]["payload"]["events"][0]["id"], intent.id)
        # Releasing twice does not send twice.
        self.assertEqual(self.publisher.push_events([intent.id])["sent"], 0)

    def test_private_kinds_are_never_sent(self):
        self.log.append(
            "ops",
            "provider.request",
            {"request_id": "r1", "desk_id": "earnings-01", "profile": "pro_flex",
             "cost_usd": "0.02", "usage": {}},
        )
        self.thought()
        summary = self.publisher.push_events()
        self.assertEqual(summary["sent"], 1)
        self.assertEqual([e["kind"] for e in self.transport.events_sent()], ["desk.thought"])

    def test_private_payload_keys_are_stripped(self):
        self.log.append(
            "desk:earnings-01",
            "desk.tool_result",
            {"session_id": "s", "call_id": "c", "tool": "filing", "summary": "10-Q read",
             "_prompt": "never publish this"},
        )
        self.publisher.push_events()
        payload = self.transport.events_sent()[0]["payload"]
        self.assertNotIn("_prompt", payload)
        self.assertEqual(payload["summary"], "10-Q read")

    def test_a_failed_batch_does_not_advance_the_cursor(self):
        self.thought("one")
        self.transport.script = [(500, {}, b"")] * 4
        with self.assertRaises(PublishError):
            self.publisher.push_events()
        self.assertEqual(json.loads((self.root / "publish-state.json").read_text() or "{}").get(
            "last_seq", 0), 0) if (self.root / "publish-state.json").exists() else None
        self.transport.script = []
        self.assertEqual(self.publisher.push_events()["sent"], 1)

    def test_backoff_honours_the_retry_after_hint(self):
        self.thought()
        self.transport.script = [(429, {"retry-after": "3"}, b""), (200, {}, b"{}")]
        self.assertEqual(self.publisher.push_events()["sent"], 1)
        self.assertEqual(self.slept, [3.0])


class SanitizerTests(PublisherCase):
    def test_angle_brackets_control_characters_and_secrets_are_neutralised(self):
        cleaned = sanitize_for_site(
            {"text": "a <script> tag\x00 and sk-live-abc123 and Bearer: xyz", "n": 3}
        )
        self.assertNotIn("<", cleaned["text"])
        self.assertIn("‹script>", cleaned["text"])  # only "<" needs neutering
        self.assertNotIn("\x00", cleaned["text"])
        self.assertNotIn("sk-live-abc123", cleaned["text"])
        self.assertNotIn("Bearer", cleaned["text"])
        self.assertNotIn("xyz", cleaned["text"])
        self.assertEqual(cleaned["n"], 3)

    def test_prose_colons_survive_but_script_capable_uris_are_defused(self):
        # The site refuses "data:text/html,..." and "javascript:..." outright, and a refused
        # thought is a hole in the public tape. Prose such as "from the data:\n" must pass.
        prose = "The dates near the end are clearly from the data:\n\nLooking at the file: it is closed."
        self.assertEqual(sanitize_for_site(prose), prose)
        defused = sanitize_for_site("then javascript:alert(1) and data:text/plain;base64,QQ== ran")
        self.assertEqual(defused, "then javascript: alert(1) and data: text/plain;base64,QQ== ran")

    def test_the_floors_own_credential_values_are_redacted_wherever_they_appear(self):
        from ltcm.publish import register_secret_literals

        self.assertEqual(register_secret_literals(["gw-token-0123456789abcdef", "short", None]), 1)
        try:
            cleaned = sanitize_for_site({"text": "sent gw-token-0123456789abcdef to the gateway", "note": "short word"})
            self.assertEqual(cleaned["text"], "sent [redacted] to the gateway")
            self.assertEqual(cleaned["note"], "short word")
        finally:
            register_secret_literals([])

    def test_tabs_and_newlines_survive(self):
        self.assertEqual(sanitize_for_site("a\tb\nc\r"), "a\tb\nc\r")

    def test_links_outside_the_allowlist_are_dropped(self):
        cleaned = sanitize_for_site(
            "see https://www.sec.gov/Archives/x.htm and http://evil.test/y and "
            "https://elsewhere.example/z"
        )
        self.assertIn("https://www.sec.gov/Archives/x.htm", cleaned)
        self.assertNotIn("evil.test", cleaned)
        self.assertNotIn("elsewhere.example", cleaned)
        self.assertEqual(cleaned.count("[link removed]"), 2)

    def test_long_strings_are_truncated(self):
        cleaned = sanitize_for_site({"text": "x" * 9000})
        self.assertEqual(len(cleaned["text"]), 8000)

    def test_nested_private_keys_are_dropped(self):
        cleaned = sanitize_for_site({"a": [{"_secret": 1, "ok": 2}], "_b": 3})
        self.assertEqual(cleaned, {"a": [{"ok": 2}]})

    def test_a_poisoned_memo_is_cleaned_before_it_is_sent(self):
        self.log.append(
            "desk:earnings-01",
            "desk.memo",
            {"session_id": "s", "title": "Read this", "text": "<b>buy</b> http://bad.test/x"},
        )
        self.publisher.push_events()
        text = self.transport.events_sent()[0]["payload"]["text"]
        self.assertNotIn("<", text)
        self.assertNotIn("bad.test", text)


class ShapeTests(PublisherCase):
    def test_a_well_formed_event_has_no_problem(self):
        self.assertIsNone(shape_problem(self.thought()))

    def test_a_live_order_review_is_publishable(self):
        event = self.log.append(
            "risk",
            "risk.review",
            {
                "intent_id": "int-0123456789ab",
                "desk_id": "rosenfeld",
                "verdict": "block",
                "reason": "The rationale argues to sell.",
                "model": "zai-org/GLM-5.3",
            },
            id="review:int-0123456789ab:0123456789ab",
        )
        self.assertIsNone(shape_problem(event))
        summary = self.publisher.push_events()
        self.assertEqual(summary["skipped"], 0)
        sent = self.transport.calls[-1]["payload"]["events"]
        review = [e for e in sent if e["kind"] == "risk.review"][0]
        self.assertEqual(
            sorted(review["payload"]), ["desk_id", "intent_id", "model", "reason", "verdict"]
        )

    def test_a_bad_timestamp_is_named_and_skipped(self):
        self.log.append(
            "desk:earnings-01", "desk.thought", {"session_id": "s", "text": "x"},
            at="2026-09-14T14:00:00Z",
        )
        self.thought("good one")
        summary = self.publisher.push_events()
        self.assertEqual(summary["sent"], 1)
        self.assertEqual(summary["skipped"], 1)
        alert = self.log.last("ops", "ops.alert")
        self.assertIn("not YYYY-MM-DDTHH:MM:SS.mmmZ", alert.payload["text"])

    def test_a_stream_that_disagrees_with_its_kind_is_skipped(self):
        event = self.log.append(
            "desk:earnings-01", "ledger.mark",
            {"equity": "1", "cash": "1", "positions": [], "daily_pnl": "0", "as_of": "x"},
        )
        self.assertIn("belongs on ledger:", shape_problem(event))
        summary = self.publisher.push_events()
        self.assertEqual(summary["sent"], 0)
        self.assertEqual(summary["skipped"], 1)

    def test_a_four_hundred_drops_one_event_not_the_batch(self):
        for n in range(4):
            self.thought(f"note {n}")
        # Two whole-batch 400s, then one per half, until the offender is alone.
        self.transport.script = [
            (400, {}, b'{"error":"bad event"}'),  # 4
            (400, {}, b'{"error":"bad event"}'),  # first 2
            (400, {}, b'{"error":"bad event"}'),  # first 1 -> dropped
            (200, {}, b"{}"),  # second 1
            (200, {}, b"{}"),  # last 2
        ]
        summary = self.publisher.push_events()
        self.assertEqual(summary["sent"], 3)
        self.assertEqual(summary["skipped"], 1)
        self.assertIn("site refused event", self.log.last("ops", "ops.alert").payload["text"])

    def test_a_conflict_is_alerted_and_passed_over(self):
        self.thought()
        self.transport.script = [(409, {}, b'{"error":"digest mismatch"}')]
        summary = self.publisher.push_events()
        self.assertEqual(summary["sent"], 0)
        self.assertEqual(summary["skipped"], 1)
        alert = self.log.last("ops", "ops.alert")
        self.assertEqual(alert.payload["level"], "critical")
        self.assertIn("already holds a different version", alert.payload["text"])


class CheckpointTests(PublisherCase):
    def body(self, **overrides):
        base = dict(
            published_at="2026-09-14T22:00:00.000Z",
            floor={
                "equity": Decimal("4980.25"),
                "cash": Decimal("1000"),
                "daily_pnl": Decimal("-19.75"),
                "capital_usd": Decimal("5000"),
                "since_inception_pct": Decimal("-0.395"),
                "benchmark": None,
                "live_equity": Decimal("4980.25"),
                "live_daily_pnl": Decimal("-19.75"),
                "live_desks": 1,
                "shadow_desks": 3,
            },
            desks=[
                {
                    "id": "earnings-01",
                    "name": "Earnings",
                    "family": "earnings",
                    "generation": 1,
                    "parent_id": None,
                    "mode": "shadow",
                    "venues": ["alpaca"],
                    "capital_usd": Decimal("1000"),
                    "equity": Decimal("-5"),
                    "cash": Decimal("-5"),
                    "daily_pnl": Decimal("-19.75"),
                    "return_pct": Decimal("-0.5"),
                    "max_drawdown_pct": Decimal("-0.12"),
                    "days_live": 13,
                    "orders": 4,
                    "cost_usd": Decimal("1.25"),
                    "status": "active",
                    "gate": {"gate": "A", "passed": False, "failed": ["days_live"]},
                    "updated_at": "2026-09-15T00:00:00.000Z",
                }
            ],
            committee={
                "last_memo_at": "2026-09-30T00:00:00.000Z",
                "allocations": {"earnings-01": Decimal("1000")},
            },
            budget={"spent_today_usd": Decimal("0.42"), "cap_usd": Decimal("40")},
            infra={
                "host": "sail",
                "box_id": "box-9f2c1ad4e7b6",
                "checkpoint_count": 118,
                "spend_usd": Decimal("0.42"),
                "uptime_seconds": 90061,
                "region": "us-east",
                "requests_today": 37,
            },
        )
        base.update(overrides)
        return checkpoint_body(**base)

    def test_key_sets_are_exact(self):
        body = self.body()
        self.assertEqual(sorted(body), ["budget", "committee", "desks", "floor", "infra",
                                        "published_at", "schema_version"])
        self.assertEqual(
            sorted(body["floor"]),
            ["benchmark", "capital_usd", "cash", "daily_pnl", "equity", "live_daily_pnl",
             "live_desks", "live_equity", "shadow_desks", "since_inception_pct"],
        )
        self.assertEqual(
            sorted(body["infra"]),
            ["box_id", "checkpoint_count", "host", "region", "requests_today", "spend_usd",
             "uptime_seconds"],
        )
        self.assertEqual(sorted(body["committee"]), ["allocations", "last_memo_at"])
        self.assertEqual(sorted(body["budget"]), ["cap_usd", "spent_today_usd"])
        self.assertEqual(
            sorted(body["desks"][0]),
            ["capital_usd", "cash", "cost_usd", "daily_pnl", "days_live", "equity", "family",
             "gate", "generation", "id", "max_drawdown_pct", "mode", "name", "orders",
             "parent_id", "return_pct", "status", "updated_at", "venues"],
        )

    def test_the_floor_block_separates_real_money_from_scored_books(self):
        floor = self.body()["floor"]
        self.assertEqual(floor["live_equity"], Decimal("4980.25"))
        self.assertEqual(floor["live_daily_pnl"], Decimal("-19.75"))
        self.assertEqual(floor["shadow_desks"], 3)
        self.assertEqual(floor["live_desks"], 1)
        # A floor block that says nothing about shadow desks still publishes: the counts are
        # optional and the live numbers fall back to the floor's own.
        bare = self.body(floor={
            "equity": Decimal("10"), "cash": Decimal("10"), "daily_pnl": Decimal("0"),
            "capital_usd": Decimal("10"), "since_inception_pct": Decimal("0"), "benchmark": None,
        })["floor"]
        self.assertEqual(bare["live_equity"], Decimal("10"))
        self.assertIsNone(bare["shadow_desks"])

    def test_infra_degrades_to_the_local_box(self):
        infra = self.body(infra=None)["infra"]
        self.assertEqual(infra["host"], "local")
        self.assertIsNone(infra["box_id"])
        self.assertIsNone(infra["region"])
        self.assertIsNone(infra["checkpoint_count"])
        self.assertIsNone(infra["spend_usd"])  # unknown is published as unknown, not as zero

    def test_infra_and_shadow_counts_travel_as_the_site_types_them(self):
        self.publisher.push_checkpoint(self.body())
        call = [c for c in self.transport.calls if c["url"].endswith(CHECKPOINT_PATH)][0]
        payload = call["payload"]
        self.assertEqual(payload["infra"]["spend_usd"], "0.42")
        self.assertEqual(payload["infra"]["uptime_seconds"], 90061)
        self.assertEqual(payload["infra"]["box_id"], "box-9f2c1ad4e7b6")
        self.assertEqual(payload["floor"]["live_equity"], "4980.25")
        self.assertEqual(payload["floor"]["live_daily_pnl"], "-19.75")
        self.assertEqual(payload["floor"]["shadow_desks"], 3)

    def test_unsigned_fields_are_clamped_and_stamps_are_bounded(self):
        desk = self.body()["desks"][0]
        self.assertEqual(desk["equity"], Decimal("0"))
        self.assertEqual(desk["cash"], Decimal("0"))
        self.assertEqual(desk["max_drawdown_pct"], Decimal("0.12"))
        self.assertEqual(desk["daily_pnl"], Decimal("-19.75"))  # signed fields keep their sign
        self.assertEqual(desk["return_pct"], Decimal("-0.5"))
        self.assertEqual(desk["updated_at"], "2026-09-14T22:00:00.000Z")
        self.assertEqual(self.body()["committee"]["last_memo_at"], "2026-09-14T22:00:00.000Z")

    def test_money_is_sent_as_decimal_strings(self):
        self.publisher.push_checkpoint(self.body())
        call = [c for c in self.transport.calls if c["url"].endswith(CHECKPOINT_PATH)][0]
        payload = call["payload"]
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["floor"]["equity"], "4980.25")
        self.assertEqual(payload["floor"]["daily_pnl"], "-19.75")
        self.assertEqual(payload["budget"]["cap_usd"], "40")
        self.assertEqual(payload["committee"]["allocations"], {"earnings-01": "1000"})
        self.assertEqual(payload["desks"][0]["max_drawdown_pct"], "0.12")

    def test_published_at_is_filled_in_when_missing(self):
        self.publisher.push_checkpoint({"floor": {}, "desks": [], "committee": {}, "budget": {}})
        call = [c for c in self.transport.calls if c["url"].endswith(CHECKPOINT_PATH)][0]
        self.assertTrue(call["payload"]["published_at"].endswith("Z"))

    def test_jsonable_renders_decimals_everywhere(self):
        self.assertEqual(
            jsonable({"a": [Decimal("1.50")], "b": {"c": Decimal("-2")}}),
            {"a": ["1.50"], "b": {"c": "-2"}},
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class SiteLimitsTests(unittest.TestCase):
    """The site's payload limits are mirrored here, so an oversized event is a named alert, not a 400."""

    def test_the_limits_match_the_sites_safe_value(self):
        self.assertIsNone(payload_problem({"a": "b", "n": 1, "list": [1, 2, {"k": None}], "t": True}))
        self.assertIn("101 keys", payload_problem({f"k{i}": "v" for i in range(101)}))
        self.assertIsNone(payload_problem({f"k{i}": "v" for i in range(100)}))
        self.assertIn("501 items", payload_problem({"rows": list(range(501))}))
        self.assertIn("8001 characters", payload_problem({"text": "x" * 8001}))
        deep: dict = {"leaf": "x"}
        for _ in range(9):
            deep = {"down": deep}
        self.assertIn("deeper", payload_problem(deep))
        self.assertIn("not publishable", payload_problem({"bad key!": "x"}))
        self.assertIn("not publishable", payload_problem({"_private": "x"}))
        self.assertIn("not finite", payload_problem({"n": float("inf")}))
        self.assertIn("type", payload_problem({"n": object()}))

    def test_an_oversized_lab_result_is_named_before_it_is_sent(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = EventLog(Path(tmp) / "events.sqlite")
            metrics = {f"desk.d{i}.net_pnl_usd": "0.0000" for i in range(269)}
            event = log.append(
                "lab", "lab.result", {"hypothesis_id": "daily-2026-09-15", "metrics": metrics, "verdict": "quiet"},
                id="lab:daily:2026-09-15", at="2026-09-15T23:59:59.999Z",
            )
            self.assertEqual(shape_problem(event), "payload has an object with 269 keys (the site takes 100)")
            fine = log.append(
                "lab", "lab.result",
                {"hypothesis_id": "daily-2026-09-16", "metrics": {"desks": {f"d{i}": {"net_pnl_usd": "0"} for i in range(100)}}, "verdict": "quiet"},
                id="lab:daily:2026-09-16", at="2026-09-16T23:59:59.999Z",
            )
            self.assertIsNone(shape_problem(fine))
            big = log.append(
                "desk:mullins", "desk.memo", {"session_id": "s", "text": "y" * 7000, "more": "z" * 7000, "rest": "w" * 7000},
                id="memo:big", at="2026-09-16T23:59:59.999Z",
            )
            self.assertEqual(shape_problem(big), "payload is over 20 KB")
            log.close()
