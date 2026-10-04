"""Claude in the swarm's routing (league/swarm/models.py), with the real Claude and Frontier clients over fake openers:
Claude first for its roles, the architect alternating with Astra, the audit falling back to Astra, the durable hold
booked before dispatch and settled from the gateway's cost, and every existing route intact when Claude is capped,
erring or unconfigured."""

from __future__ import annotations

import copy
import io
import socket
import tempfile
import unittest
import urllib.error
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from league.claude import Claude
from league.frontier import Frontier
from league.swarm.gate import Gate
from league.swarm.models import ModelError, ModelRouter
from league.swarm.settings import DEFAULTS
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock, FakeMonth, unbound_budget
from league.tests.test_claude import FakeStream, events, message
from league.tests.test_frontier import GATEWAY, FakeOpener, FakeResponse, ok


class FakeClaudeMeter:
    def __init__(self, remaining):
        self.value = remaining

    def remaining(self):
        return None if self.value is None else Decimal(str(self.value))


ERRORS = []


def refused(code, detail="refused", cost=None):
    error = urllib.error.HTTPError(GATEWAY, code, "error", {} if cost is None else {"X-LTCM-Cost-USD": cost}, io.BytesIO(detail.encode()))
    ERRORS.append(error)
    return error


class ClaudeRouting(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clock = Clock()
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = copy.deepcopy(DEFAULTS)
        # THE BUDGET is not what these tests judge: a paid-model line well above the holds asked here (no block is the
        # floor, and a call that falls from Claude to OpenAI is admitted under that line too).
        self.settings["budget"] = unbound_budget(self)
        self.month = FakeMonth(1000)
        self.meter = FakeClaudeMeter(100)
        self.sail_calls = []
        self.openai = FakeOpener(*[ok(cost="0.05") for _ in range(8)])

    def router(self, claude_opener=None, *, configured=True, store=None):
        router = ModelRouter(store or self.store, None, settings=self.settings, month=self.month,
                             frontier_factory=lambda model: Frontier(GATEWAY, lambda: "synthetic", model=model, opener=self.openai),
                             claude_factory=(lambda model: Claude(GATEWAY, lambda: "synthetic", model=model, opener=claude_opener))
                             if configured else None,
                             claude_meter=self.meter if configured else None)

        def sail(profile, *args, **kwargs):
            self.sail_calls.append(profile)
            return SimpleNamespace(output_text='{"fallback": true}', cost_usd=Decimal("0.02"))

        router.sail = sail
        return router

    def ask(self, router, **kw):
        args = dict(role="architect", system="THE RULES", user="the packet", family=None, key="call-1", openai_model="gpt-6-astra",
                    sail_profile="k3_balanced", max_output=12000, effort="high", need_usd=0.01, claude=True)
        args.update(kw)
        return router.ask(**args)

    def claude_spent(self):
        return Decimal(str(self.store.spent(["claude"]))).quantize(Decimal("0.000001"))

    def test_claude_answers_first_and_its_hold_settles_at_the_gateways_cost(self):
        opener = FakeOpener(message('{"families": []}', cost="0.184000"))
        result = self.ask(self.router(opener))
        self.assertEqual((result["route"], result["model"], result["json"]), ("claude", "claude-opus-5-5", {"families": []}))
        self.assertEqual((result["cost_usd"], result["cost_verified"], result["held_usd"]), (0.184, True, 0.0))
        self.assertEqual(self.claude_spent(), Decimal("0.184000"))
        self.assertEqual(self.store.spent(["openai"]), 0)
        self.assertEqual(self.openai.calls, [])
        body, headers = opener.body(), opener.headers()
        self.assertEqual((body["model"], body["max_tokens"], body["output_config"], body["thinking"], body["stream"]),
                         ("claude-opus-5-5", 16000, {"effort": "high"}, {"type": "adaptive", "display": "summarized"}, True),
                         "streamed by default: no hop waits 100 s in silence")
        self.assertEqual(body["system"][0]["cache_control"], {"type": "ephemeral"}, "the stable prefix is cached")
        self.assertEqual((headers["x-ltcm-role"], headers["x-ltcm-agent"]), ("architect", "swarm-architect"))
        rows = self.store._all("SELECT usd, detail FROM spend WHERE kind='claude' ORDER BY seq")
        self.assertEqual(len(rows), 2, "the hold, then its settlement")
        self.assertGreater(rows[0]["usd"], 0.32, "held at the worst case: 16,000 output tokens alone are $0.32")
        self.assertAlmostEqual(self.router(opener).claude_spent(role="architect"), 0.184)

    def test_a_streamed_answer_settles_at_the_gateways_tail_and_a_broken_stream_falls_through(self):
        result = self.ask(self.router(FakeOpener(FakeStream(events('{"families": []}', cost="0.184000")))))
        self.assertEqual((result["route"], result["json"], result["cost_usd"]), ("claude", {"families": []}, 0.184))
        self.assertEqual(self.claude_spent(), Decimal("0.184000"))
        self.assertFalse(self.store.get("claude_unsettled"))
        broken = self.ask(self.router(FakeOpener(FakeStream(events(), fail=socket.timeout("quiet"), fail_after=5))), key="quiet")
        self.assertEqual(broken["route"], "openai", "a stalled stream falls through to Astra")
        self.assertEqual(len(self.store.get("claude_unsettled")), 1, "its bill is unknown: trued up from the gateway later")

    def test_the_hold_is_durable_before_dispatch_and_an_unknown_bill_keeps_it(self):
        seen = []

        def opener(request, timeout=None):
            other = SwarmStore(self.root, clock=self.clock)
            try:
                seen.append(other.spent(["claude"]))
            finally:
                other.close()
            raise socket.timeout("the answer never came")

        result = self.ask(self.router(opener))
        self.assertEqual(result["route"], "openai", "an unknown Claude failure falls through to Astra")
        self.assertGreater(seen[0], 0.32, "another connection saw the committed hold while the call was out")
        reopened = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(reopened.close)
        self.assertAlmostEqual(reopened.spent(["claude"]), seen[0], msg="unknown is not free: the hold stays across a restart")

    def test_a_refusal_or_truncation_is_billed_at_its_usage_and_falls_through(self):
        for stop in ("refusal", "max_tokens"):
            with self.subTest(stop=stop):
                before = self.claude_spent()
                result = self.ask(self.router(FakeOpener(message("", stop=stop, cost="0.020400"))), key=stop)
                self.assertEqual(result["route"], "openai")
                self.assertEqual(self.claude_spent() - before, Decimal("0.020400"))

    def test_gateway_refusals_release_the_hold_and_its_zero_settlements_are_booked_at_zero(self):
        for error in (refused(402, '{"cap": "claude_funded"}'), refused(423, '{"cap": "kill_switch"}'), refused(400),
                      refused(529, "overloaded", cost="0.000000"), refused(502, "no answer", cost="0.000000")):
            with self.subTest(code=error.code):
                result = self.ask(self.router(FakeOpener(error)), key=f"k{error.code}")
                self.assertEqual(result["route"], "openai")
                self.assertEqual(self.claude_spent(), Decimal("0"))

    def test_a_refusal_naming_its_cap_releases_the_hold_and_an_empty_answer_falls_through(self):
        result = self.ask(self.router(FakeOpener(refused(503, '{"error": "Claude is not configured.", "cap": "setup"}'))), key="setup")
        self.assertEqual(result["route"], "openai")
        self.assertEqual(self.claude_spent(), Decimal("0"), "the gateway refused before reserving: no phantom hold")
        self.assertFalse(self.store.get("claude_unsettled"), "released: nothing left to true up")
        empty = self.ask(self.router(FakeOpener(message("", cost="0.030000"))), key="empty", role="audit")
        self.assertEqual(empty["route"], "openai", "an empty answer is not an audit: Astra reads it instead")
        self.assertEqual(self.claude_spent(), Decimal("0.030000"), "billed at its usage")

    def test_an_unknown_bill_is_trued_up_from_the_gateways_record_of_the_call(self):
        opener = FakeOpener(refused(502, "bad gateway"), refused(504, "timeout"), refused(500, "worker"), socket.timeout("slow"))
        router = self.router(opener)
        for key in ("a", "b", "c", "d"):
            self.assertEqual(self.ask(router, key=key)["route"], "openai")
        holds = self.store.get("claude_unsettled")
        self.assertEqual(len(holds), 4)
        sent = [dict(r.header_items()).get("X-ltcm-request") for r, _ in opener.calls]
        self.assertEqual(sorted(sent), sorted(holds), "each call carried the id its hold is filed under")
        self.assertEqual(len(set(sent)), 4)
        held = Decimal(str(self.store.spent(["claude"])))
        self.assertGreater(held, Decimal("1.2"), "four worst cases are held")
        self.assertEqual(router.settle_claude_holds(), 0, "not before a minute has passed")
        self.clock.advance(61)
        ids = sorted(holds)  # the order the holds are read in
        records = {sent[0]: {"state": "settled", "cost_usd": "0.120000"}, sent[1]: {"state": "released", "cost_usd": "0.000000"},
                   sent[2]: {"state": "absent"}, sent[3]: {"state": "held"}}
        opener.script = [FakeResponse(records[rid]) for rid in ids]
        self.assertEqual(router.settle_claude_holds(), 2, "the settled and the released; the absent and the held wait")
        left = self.store.get("claude_unsettled")
        self.assertEqual(sorted(left), sorted([sent[2], sent[3]]))
        self.clock.advance(1800)
        opener.script = [FakeResponse(records[rid]) for rid in sorted(left)]
        self.assertEqual(router.settle_holds(), 1, "a call the gateway never recorded is released after half an hour")
        self.assertEqual(list(self.store.get("claude_unsettled")), [sent[3]])
        still = Decimal(str(left[sent[3]]["usd"]))
        self.assertAlmostEqual(float(self.claude_spent()), float(Decimal("0.12") + still), places=5)

    def test_a_restart_mid_call_is_still_trued_up_from_the_gateway(self):
        def crash(request, timeout=None):
            filed = SwarmStore(self.root, clock=self.clock)
            try:
                self.assertEqual(len(filed.get("claude_unsettled")), 1, "filed in the hold's own transaction, before dispatch")
            finally:
                filed.close()
            raise SystemExit("the swarm restarted mid-call")

        with self.assertRaises(SystemExit):
            self.ask(self.router(crash))
        restarted = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(restarted.close)
        [request_id] = restarted.get("claude_unsettled")
        self.clock.advance(61)
        router = self.router(FakeOpener(FakeResponse({"state": "settled", "cost_usd": "0.210000"})), store=restarted)
        self.assertEqual(router.settle_claude_holds(), 1)
        self.assertFalse(restarted.get("claude_unsettled"))
        self.assertAlmostEqual(restarted.spent(["claude"]), 0.21)

    def test_a_true_up_that_lands_while_the_call_is_out_is_not_booked_twice(self):
        box = {}

        def gateway(request, timeout=None):
            if request.get_method() == "GET":
                return FakeResponse({"state": "settled", "cost_usd": "0.184000"})
            self.clock.advance(61)
            self.assertEqual(box["router"].settle_claude_holds(), 1, "the gateway settled first; the true-up books it")
            return message('{"families": []}', cost="0.184000")

        box["router"] = self.router(gateway)
        self.assertEqual(self.ask(box["router"])["route"], "claude")
        self.assertEqual(self.claude_spent(), Decimal("0.184000"), "booked once")
        self.assertFalse(self.store.get("claude_unsettled"))

    def test_the_true_up_pass_stops_at_a_gateway_it_cannot_read(self):
        router = self.router(FakeOpener(*[socket.timeout("slow") for _ in range(3)]))
        for key in ("a", "b", "c"):
            self.ask(router, key=key)
        self.clock.advance(61)
        reads = FakeOpener(urllib.error.URLError("hung"), FakeResponse({"state": "released"}), FakeResponse({"state": "released"}))
        self.assertEqual(self.router(reads).settle_claude_holds(), 0)
        self.assertEqual(len(reads.calls), 1, "one failed read ends the pass: the heartbeat is never held")
        self.assertEqual(len(self.store.get("claude_unsettled")), 3)
        self.assertEqual(self.router(reads).settle_claude_holds(budget_seconds=0), 0)
        self.assertEqual(len(reads.calls), 1, "no time left: no read")

    def test_capped_unconfigured_or_unreadable_claude_leaves_the_existing_routes_exactly_as_they_were(self):
        cases = {
            "unconfigured": dict(configured=False),
            "funded total at its reserve": dict(meter=5.0),
            "funded total unreadable": dict(meter=None),
            "no model": dict(settings={"model": None}),
            "role not Claude's": dict(settings={"roles": ["audit"]}),
            "nonfinite swarm cap": dict(settings={"usd_cap": "NaN"}),
            "negative reserve": dict(settings={"reserve_usd": -1}),
            "swarm's own line spent": dict(spent=100.0),
        }
        for name, case in cases.items():
            with self.subTest(case=name):
                self.setUp()
                self.meter.value = case.get("meter", 100)
                self.settings["claude"].update(case.get("settings", {}))
                if case.get("spent"):
                    self.store.add_spend("claude", case["spent"], detail={"role": "earlier"})
                opener = FakeOpener(message())
                result = self.ask(self.router(opener, configured=case.get("configured", True)))
                self.assertEqual(result["route"], "openai", name)
                self.assertEqual(opener.calls, [], f"{name}: Claude was never asked")
                self.assertEqual(self.store.spent(["claude"]), case.get("spent", 0.0))
        # Neither paid route: Sail's profile, as before.
        self.setUp()
        self.month.value = None
        self.meter.value = 1.0
        result = self.ask(self.router(FakeOpener()))
        self.assertEqual((result["route"], self.sail_calls), ("sail", ["k3_balanced"]))

    def test_the_architect_alternates_to_astra_every_other_pass_while_openai_has_room(self):
        replies = FakeOpener(*[message('{"families": []}', cost="0.1") for _ in range(6)])
        routes = [self.ask(self.router(replies), key=f"pass-{i}", rotate=True)["route"] for i in range(4)]
        self.assertEqual(routes, ["claude", "openai", "claude", "openai"])
        self.month.value = None  # the OpenAI month cannot be read: Astra's turn goes to Claude
        self.assertEqual(self.ask(self.router(replies), key="pass-4", rotate=True)["route"], "claude")
        self.assertEqual(self.ask(self.router(replies), key="pass-5", rotate=True)["route"], "claude")
        # Without rotation Claude is always first.
        self.month.value = 1000
        self.assertEqual(self.ask(self.router(FakeOpener(message())), key="plain")["route"], "claude")

    def test_no_sail_fallback_is_an_error_not_a_sail_call(self):
        with self.assertRaises(ModelError):
            self.ask(self.router(FakeOpener(), configured=False), role="diagnostician", openai_model=None, sail_profile=None)
        self.assertEqual(self.sail_calls, [])

    def test_the_gate_audits_on_claude_with_astra_behind_it_and_the_review_stays_on_openai(self):
        fam = {"id": "condor", "mechanism": "sell the variance premium", "structure": "iron_condor", "roots": ["SPY"]}
        version = {"n": 3, "code": "NEEDS = {}\nPARAMS = {}\n\ndef decide(ctx):\n    return []\n", "params": {}}
        claude = FakeOpener(message('{"verdict": "pass", "reasons": []}'), refused(529, "overloaded", cost="0.000000"))
        self.openai = FakeOpener(ok(cost="0.05", model="gpt-6-sol"), ok(cost="0.05"))
        gate = Gate(self.store, None, self.router(claude), self.settings, clock=self.clock)
        self.assertEqual(gate.review(fam, version)["route"], "openai", "the program review is unchanged: GPT-6 Sol")
        self.assertEqual(self.openai.body()["model"], "gpt-6-sol")
        audit = gate.audit(fam, version)
        self.assertEqual((audit["route"], audit["model"], audit["verdict"]), ("claude", "claude-opus-5-5", "pass"))
        self.assertEqual(claude.headers()["x-ltcm-role"], "audit")
        fallback = gate.audit(fam, version, attempt=1)
        self.assertEqual((fallback["route"], fallback["model"]), ("openai", "gpt-6-astra"))
        self.assertEqual(self.openai.body()["service_tier"], "default", "the audit is latency-sensitive: standard tier")


def tearDownModule():
    for error in ERRORS:
        error.close()


if __name__ == "__main__":
    unittest.main()
