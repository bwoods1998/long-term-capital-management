import json
import unittest
from decimal import Decimal

from woodscapital import tools
from woodscapital.broker import Balance, Instrument, OrderIntent, Position, Quote
from woodscapital.manifest import TOOLS, DeskManifest
from woodscapital.tests.test_manifest import SAMPLE

ALL_TOOLS = list(TOOLS)


def manifest(**overrides):
    data = {**SAMPLE, "tools": ALL_TOOLS}
    data.update(overrides)
    return DeskManifest.from_dict(data)


def live_manifest():
    return manifest(
        venues=["alpaca", "kalshi"], capital={"mode": "live", "usd": "5000"}
    )


class FakeContext:
    """A ToolContext that records what it was asked and returns canned answers."""

    def __init__(self, *, decision=None, fail=None):
        self.seen = []
        self.intents = []
        self.decision = decision or {"approved": True, "reasons": []}
        self.fail = fail or set()

    def _note(self, name, *args):
        self.seen.append((name, args))
        if name in self.fail:
            raise RuntimeError("boom")

    def quote(self, instrument):
        self._note("quote", instrument)
        return Quote(
            instrument,
            Decimal("100.10"),
            Decimal("100.20"),
            Decimal("100.15"),
            "2026-09-15T13:30:00.000Z",
            "sim",
            True,
        )

    def bars(self, instrument, interval, limit):
        self._note("bars", instrument, interval, limit)
        return [{"t": "2026-09-14", "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": 10}] * 2

    def news(self, query, limit):
        self._note("news", query, limit)
        return [{"title": "Beat on revenue", "url": "https://example.com/a", "source": "wire"}]

    def filing(self, symbol, form, index):
        self._note("filing", symbol, form, index)
        return {
            "symbol": symbol,
            "form": form,
            "sha256": "a" * 64,
            "url": "https://sec.example/x",
            "excerpt": "Revenue rose 12%.",
        }

    def facts(self, symbol):
        self._note("facts", symbol)
        return {"symbol": symbol, "revenue": Decimal("1234.50")}

    def calendar(self, days):
        self._note("calendar", days)
        return [{"symbol": "AAPL", "date": "2026-09-20", "event": "earnings"}]

    def chain(self, symbol, expiry):
        self._note("chain", symbol, expiry)
        return [{"strike": "100", "right": "call"}]

    def event_markets(self, query):
        self._note("event_markets", query)
        return [{"market_id": "CPI-26SEP", "yes": "0.42"}]

    def positions(self):
        self._note("positions")
        return [
            Position(
                Instrument("equity", "AAPL", "paper"), Decimal("3"), Decimal("99"), Decimal("101")
            )
        ]

    def balance(self):
        self._note("balance")
        return Balance("paper", Decimal("500"), Decimal("803"), Decimal("500"), "2026-09-15T13:30:00.000Z")

    def outcomes(self, limit):
        self._note("outcomes", limit)
        return [{"symbol": "MSFT", "pnl": "12.50", "closed_at": "2026-09-10"}]

    def memory_read(self, query, limit):
        self._note("memory_read", query, limit)
        return [{"id": "mem-1", "at": "2026-09-01T00:00:00.000Z", "text": "NVDA beat", "kind": "fact"}]

    def memory_write(self, entry):
        self._note("memory_write", entry)
        return {"id": "mem-2", **entry}

    def memo(self, title, text):
        self._note("memo", title, text)
        return {"title": title, "chars": len(text)}

    def propose_order(self, intent):
        self._note("propose_order", intent)
        self.intents.append(intent)
        decision = {"intent_id": intent.id, "desk_id": intent.desk_id, **self.decision}
        out = {"decision": decision}
        if decision.get("approved"):
            out["order"] = {"id": "ord-" + intent.id[3:], "status": "accepted"}
        return out

    def cancel_order(self, order_id):
        self._note("cancel_order", order_id)
        return {"order_id": order_id, "status": "cancelled"}

    def playbook_read(self):
        self._note("playbook_read")
        return "# playbook\nrules"

    def playbook_write(self, text, reason):
        self._note("playbook_write", text, reason)
        return {"version": 2, "diff": "--- v1\n+++ v2", "reason": reason}

    def end_session(self, summary):
        self._note("end_session", summary)
        return {"ended": True, "summary": summary}


def session(session_id="earnings-01:20260915-1345:market_open"):
    return tools.ToolSession(
        session_id=session_id, desk_id="earnings-01", now="2026-09-15T13:45:00.000Z"
    )


def run(name, arguments, ctx=None, mf=None, sess=None):
    ctx = ctx or FakeContext()
    return json.loads(tools.execute(name, arguments, ctx, mf or manifest(), sess or session()))


class SchemaTests(unittest.TestCase):
    def test_every_manifest_tool_has_a_schema_plus_end_session(self):
        self.assertEqual(set(tools.TOOL_SCHEMAS), set(TOOLS) | {"end_session"})
        for name, schema in tools.TOOL_SCHEMAS.items():
            self.assertEqual(schema["name"], name)
            self.assertTrue(10 < len(schema["description"]) < 400, name)
            params = schema["parameters"]
            self.assertEqual(params["type"], "object")
            self.assertIs(params["additionalProperties"], False)
            for required in params["required"]:
                self.assertIn(required, params["properties"], name)
            # Must survive the JSON encoding the Responses API body uses.
            json.dumps(schema)

    def test_schemas_for_a_desk_are_its_tools_plus_end_session(self):
        mf = manifest(tools=["quote", "memo", "propose_order"])
        names = [schema["name"] for schema in tools.schemas_for(mf)]
        self.assertEqual(names, ["quote", "memo", "propose_order", "end_session"])
        self.assertEqual(tools.allowed_tools(mf), {"quote", "memo", "propose_order", "end_session"})

    def test_a_tool_the_desk_does_not_hold_is_refused(self):
        mf = manifest(tools=["quote"])
        out = run("propose_order", {}, mf=mf)
        self.assertIn("unknown tool", out["error"])
        self.assertIn("quote", out["error"])


class InstrumentTests(unittest.TestCase):
    def test_a_paper_desk_routes_to_paper(self):
        instrument = tools.instrument_from({"asset_class": "equity", "symbol": "AAPL"}, manifest())
        self.assertEqual(instrument.venue, "paper")

    def test_a_live_desk_routes_to_its_first_real_venue(self):
        instrument = tools.instrument_from({"asset_class": "equity", "symbol": "AAPL"}, live_manifest())
        self.assertEqual(instrument.venue, "alpaca")
        self.assertEqual(tools.default_venue(live_manifest()), "alpaca")

    def test_a_venue_the_desk_does_not_hold_is_replaced(self):
        instrument = tools.instrument_from(
            {"asset_class": "equity", "symbol": "AAPL", "venue": "coinbase"}, manifest()
        )
        self.assertEqual(instrument.venue, "paper")
        kept = tools.instrument_from(
            {"asset_class": "equity", "symbol": "AAPL", "venue": "alpaca"}, manifest()
        )
        self.assertEqual(kept.venue, "alpaca")

    def test_options_default_to_the_standard_multiplier(self):
        instrument = tools.instrument_from(
            {
                "asset_class": "option",
                "symbol": "AAPL",
                "expiry": "2026-10-16",
                "strike": "200",
                "right": "call",
            },
            manifest(),
        )
        self.assertEqual(instrument.multiplier, Decimal("100"))
        self.assertEqual(instrument.strike, Decimal("200"))

    def test_an_unusable_instrument_is_an_error_not_an_exception(self):
        out = run("quote", {"instrument": {"asset_class": "equity"}})
        self.assertIn("invalid instrument", out["error"])
        self.assertIn("error", run("quote", {"instrument": "AAPL"}))
        self.assertIn("error", run("quote", {}))


class ExecutionTests(unittest.TestCase):
    def test_results_are_json_with_decimals_as_strings(self):
        ctx = FakeContext()
        out = run("quote", {"instrument": {"asset_class": "equity", "symbol": "AAPL"}}, ctx)
        self.assertEqual(out["bid"], "100.10")
        self.assertEqual(out["instrument"]["symbol"], "AAPL")
        self.assertTrue(out["delayed"])
        self.assertEqual(ctx.seen[0][0], "quote")

    def test_numeric_arguments_are_clamped_and_coerced(self):
        ctx = FakeContext()
        run("bars", {"instrument": {"asset_class": "equity", "symbol": "AAPL"}, "interval": "1d", "limit": 9999}, ctx)
        self.assertEqual(ctx.seen[0][1][2], 500)
        run("news", {"query": "AAPL", "limit": "3"}, ctx)
        self.assertEqual(ctx.seen[1][1][1], 3)
        run("calendar", {}, ctx)
        self.assertEqual(ctx.seen[2][1][0], 7)

    def test_a_failing_context_becomes_an_error_object(self):
        ctx = FakeContext(fail={"facts"})
        out = run("facts", {"symbol": "AAPL"}, ctx)
        self.assertEqual(out["error"], "facts failed: RuntimeError")

    def test_memory_write_shapes_the_entry(self):
        ctx = FakeContext()
        out = run("memory_write", {"text": "Revenue beat", "kind": "fact", "symbol": "AAPL", "tags": ["earnings"]}, ctx)
        entry = ctx.seen[0][1][0]
        self.assertEqual(entry["desk_id"], "earnings-01")
        self.assertEqual(entry["kind"], "fact")
        self.assertEqual(entry["tags"], ["earnings"])
        self.assertEqual(entry["session_id"], session().session_id)
        self.assertEqual(out["id"], "mem-2")
        self.assertIn("error", run("memory_write", {"kind": "fact"}))

    def test_end_session_marks_the_session(self):
        sess = session()
        out = run("end_session", {"summary": "did the work"}, sess=sess)
        self.assertTrue(sess.ended)
        self.assertEqual(sess.end_summary, "did the work")
        self.assertTrue(out["ended"])
        self.assertIn("error", run("end_session", {"summary": ""}, sess=session()))

    def test_oversized_results_are_capped(self):
        text = tools.dumps({"payload": "x" * (tools.MAX_RESULT_CHARS + 1000)})
        self.assertLessEqual(len(text), tools.MAX_RESULT_CHARS)
        self.assertTrue(json.loads(text)["truncated"])


class ProposeOrderTests(unittest.TestCase):
    def arguments(self, **overrides):
        base = {
            "instrument": {"asset_class": "equity", "symbol": "AAPL"},
            "side": "buy",
            "quantity": "2",
            "order_type": "limit",
            "limit_price": "100.00",
            "rationale": "Beat on revenue with a small move; ten day hold, exit on the next print.",
        }
        base.update(overrides)
        return base

    def test_an_approved_proposal_returns_the_decision_and_the_order(self):
        ctx, sess = FakeContext(), session()
        out = run("propose_order", self.arguments(), ctx, sess=sess)
        self.assertTrue(out["approved"])
        self.assertEqual(out["order"]["status"], "accepted")
        intent = ctx.intents[0]
        self.assertIsInstance(intent, OrderIntent)
        self.assertEqual(intent.session_id, sess.session_id)
        self.assertEqual(intent.quantity, Decimal("2"))
        self.assertEqual(intent.limit_price, Decimal("100.00"))
        self.assertEqual(intent.created_at, "2026-09-15T13:45:00.000Z")
        self.assertEqual(out["intent_id"], intent.id)
        self.assertEqual(sess.intents, [{"intent_id": intent.id, "approved": True, "reasons": []}])
        self.assertEqual(sess.nonce, 1)

    def test_a_rejection_returns_the_risk_reasons_verbatim(self):
        reasons = [
            "order notional 900.00 exceeds 25% of desk equity",
            "insufficient desk cash: need 900.00, have 500.00",
        ]
        ctx = FakeContext(decision={"approved": False, "reasons": reasons})
        sess = session()
        out = run("propose_order", self.arguments(), ctx, sess=sess)
        self.assertFalse(out["approved"])
        self.assertEqual(out["reasons"], reasons)
        self.assertEqual(sess.intents[0]["reasons"], reasons)

    def test_replaying_a_session_derives_the_same_intent_ids(self):
        first, second = FakeContext(), FakeContext()
        one, two = session(), session()
        for ctx, sess in ((first, one), (second, two)):
            run("propose_order", self.arguments(), ctx, sess=sess)
            run("propose_order", self.arguments(instrument={"asset_class": "equity", "symbol": "MSFT"}), ctx, sess=sess)
        self.assertEqual([i.id for i in first.intents], [i.id for i in second.intents])
        # Within one session the counter keeps two identical proposals apart.
        third = FakeContext()
        sess = session()
        run("propose_order", self.arguments(), third, sess=sess)
        run("propose_order", self.arguments(), third, sess=sess)
        self.assertNotEqual(third.intents[0].id, third.intents[1].id)

    def test_bad_orders_never_raise(self):
        for arguments in (
            self.arguments(side="hold"),
            self.arguments(order_type="stop"),
            self.arguments(order_type="limit", limit_price=None),
            self.arguments(quantity="-4"),
            self.arguments(quantity="lots"),
            self.arguments(rationale=""),
        ):
            out = run("propose_order", arguments)
            self.assertIn("error", out, arguments)

    def test_a_market_order_drops_a_stray_limit_price(self):
        ctx = FakeContext()
        run("propose_order", self.arguments(order_type="market"), ctx)
        self.assertIsNone(ctx.intents[0].limit_price)


class PublicationTests(unittest.TestCase):
    def test_public_arguments_summarize_long_bodies(self):
        public = tools.public_arguments("playbook_write", {"text": "x" * 5000, "reason": "learned"})
        self.assertEqual(public, {"reason": "learned", "chars": 5000})
        memo = tools.public_arguments("memo", {"title": "Today", "text": "y" * 900})
        self.assertEqual(memo, {"title": "Today", "chars": 900})
        clipped = tools.public_arguments("news", {"query": "z" * 900, "limit": 5})
        self.assertEqual(len(clipped["query"]), tools.PUBLIC_STRING_CHARS + 1)
        self.assertEqual(clipped["limit"], 5)
        self.assertEqual(tools.public_arguments("quote", "nope"), {"_invalid": True})

    def test_public_arguments_survive_json(self):
        public = tools.public_arguments(
            "propose_order", {"quantity": Decimal("2"), "instrument": {"symbol": "AAPL"}}
        )
        self.assertEqual(json.loads(json.dumps(public))["quantity"], "2")

    def test_summaries_are_short_and_readable(self):
        ctx = FakeContext()
        for name, arguments in (
            ("quote", {"instrument": {"asset_class": "equity", "symbol": "AAPL"}}),
            ("filing", {"symbol": "AAPL", "form": "8-K", "index": 0}),
            ("news", {"query": "AAPL", "limit": 3}),
            ("positions", {}),
        ):
            raw = tools.execute(name, arguments, ctx, manifest(), session())
            summary = tools.summarize_result(name, raw)
            self.assertLessEqual(len(summary), tools.SUMMARY_CHARS)
            self.assertTrue(summary.startswith(name), summary)
        self.assertIn("bid 100.10", tools.summarize_result("quote", tools.execute(
            "quote", {"instrument": {"asset_class": "equity", "symbol": "AAPL"}}, ctx, manifest(), session()
        )))
        self.assertIn("1 item", tools.summarize_result("news", '[{"title": "Beat"}]'))
        self.assertIn("first: Beat", tools.summarize_result("news", '[{"title": "Beat"}]'))
        self.assertEqual(
            tools.summarize_result("facts", '{"error": "facts failed: RuntimeError"}'),
            "facts error: facts failed: RuntimeError",
        )
        long = tools.summarize_result("facts", json.dumps({"k" * 50: "v" * 5000}))
        self.assertLessEqual(len(long), tools.SUMMARY_CHARS)

    def test_a_filing_summary_cites_the_document_hash(self):
        raw = tools.execute(
            "filing", {"symbol": "AAPL", "form": "8-K", "index": 0}, FakeContext(), manifest(), session()
        )
        self.assertEqual(tools.document_sha256(raw), "a" * 64)
        self.assertIn("a" * 16, tools.summarize_result("filing", raw))
        self.assertIsNone(tools.document_sha256('{"no": "hash"}'))
        self.assertIsNone(tools.document_sha256("not json"))

    def test_propose_order_summary_names_the_verdict(self):
        summary = tools.summarize_result(
            "propose_order", {"intent_id": "oi-1", "approved": False, "reasons": ["no cash"]}
        )
        self.assertEqual(summary, "propose_order oi-1 rejected: no cash")


if __name__ == "__main__":
    unittest.main()
