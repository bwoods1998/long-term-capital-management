"""More roles on Claude (Sept 29, 2026, the owner's decision: Sail and Claude are the only lines topped up). Every role's
call asks for Claude, so `claude.roles` alone decides who gets it: the defaults change nothing, "rewrite" or "review" in
`claude.roles` routes the researcher's stall rewrite or the gate's review to Claude, a role's own daily line
(`claude.role_usd_day`) sends it to its next route once reached, and the architect without an OpenAI model is Claude's
alone while Claude is up and Sail's when Claude is down or capped. The real router, the real Claude and Frontier clients
over fake openers, the real Researcher, Gate, Architect and Diagnostician."""

from __future__ import annotations

import copy
import io
import tempfile
import unittest
import urllib.error
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from league.claude import Claude, reservation_ceiling
from league.frontier import Frontier
from league.swarm.architect import Architect
from league.swarm.gate import Gate
from league.swarm.models import ModelRouter
from league.swarm.settings import DEFAULTS
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock, FakeMonth
from league.tests.test_claude import message
from league.tests.test_frontier import GATEWAY, FakeOpener, ok
from league.tests.test_swarm_claude_routing import FakeClaudeMeter
from league.tests.test_swarm_diagnostician import DiagnosticianCase
from league.tests.test_swarm_researcher import ResearcherCase

FAMILY = {"id": "condor", "mechanism": "sell the variance premium", "structure": "iron_condor", "roots": ["SPY"]}
VERSION = {"n": 3, "code": "NEEDS = {}\nPARAMS = {}\n\ndef decide(ctx):\n    return []\n", "params": {}}
ERRORS = []


def refused(code, detail="refused", cost=None):
    error = urllib.error.HTTPError(GATEWAY, code, "error", {} if cost is None else {"X-LTCM-Cost-USD": cost}, io.BytesIO(detail.encode()))
    ERRORS.append(error)
    return error


class RouterCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = Clock()
        self.store = SwarmStore(Path(self.tmp.name), clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = copy.deepcopy(DEFAULTS)
        self.month = FakeMonth(1000)
        self.meter = FakeClaudeMeter(100)
        self.sail_calls = []
        self.openai = FakeOpener(*[ok(cost="0.05", model="gpt-6-sol") for _ in range(4)])
        self.claude = FakeOpener()

    def router(self, *, configured=True):
        router = ModelRouter(self.store, None, settings=self.settings, month=self.month,
                             frontier_factory=lambda model: Frontier(GATEWAY, lambda: "synthetic", model=model, opener=self.openai),
                             claude_factory=(lambda model: Claude(GATEWAY, lambda: "synthetic", model=model, opener=self.claude))
                             if configured else None,
                             claude_meter=self.meter if configured else None)

        def sail(profile, *args, **kwargs):
            self.sail_calls.append(profile)
            return SimpleNamespace(output_text='{"families": [], "verdict": "pass"}', cost_usd=Decimal("0.02"))

        router.sail = sail
        return router

    def ask(self, router, **kw):
        args = dict(role="rewrite", system="THE RULES", user="the packet", family="condor", key="call-1", openai_model=None,
                    sail_profile="pro_asap", max_output=12000, effort="medium", need_usd=0.0, claude=True)
        args.update(kw)
        return router.ask(**args)

    def spend(self, role, usd):
        self.store.add_spend("claude", usd, family="condor", detail={"role": role})


class Defaults(RouterCase):
    def test_the_default_roles_and_lines(self):
        # Sept 29, 2026 (swarm/sonnet-researchers): the top band's research cycles joined the roles, on a $100 daily line.
        self.assertEqual(DEFAULTS["claude"]["roles"], ["architect", "audit", "diagnostician", "researcher"])
        self.assertEqual(DEFAULTS["claude"]["role_usd_day"], {"researcher": 100.0})
        router = self.router()
        for role in ("architect", "audit", "diagnostician", "rewrite", "review"):
            self.assertIsNone(router.claude_role_line(role), role)
            self.assertIsNone(router.claude_role_room(role), role)
        self.assertEqual(router.claude_role_line("researcher"), 100.0)

    def test_with_the_defaults_the_rewrite_stays_on_sail_and_the_review_on_openai(self):
        router = self.router()
        result = self.ask(router)
        self.assertEqual((result["route"], self.sail_calls), ("sail", ["pro_asap"]), "asking for Claude is not Claude's role")
        gate = Gate(self.store, None, router, self.settings, clock=self.clock)
        review = gate.review(FAMILY, VERSION)
        self.assertEqual((review["route"], review["model"]), ("openai", "gpt-6-sol"))
        self.assertEqual(self.claude.calls, [], "Claude was never asked")
        self.assertEqual(self.store.spent(["claude"]), 0)


class MoreRoles(RouterCase):
    def test_review_in_the_roles_puts_the_gates_review_on_claude(self):
        self.settings["claude"]["roles"].append("review")
        self.claude.script = [message('{"verdict": "pass", "reasons": []}', cost="0.061000")]
        review = Gate(self.store, None, self.router(), self.settings, clock=self.clock).review(FAMILY, VERSION)
        self.assertEqual((review["route"], review["model"], review["verdict"]), ("claude", "claude-opus-5-5", "pass"))
        self.assertEqual(self.claude.headers()["x-ltcm-role"], "review")
        self.assertEqual(self.openai.calls, [], "Sol is behind Claude now")

    def test_rewrite_in_the_roles_puts_the_rewrite_on_claude(self):
        self.settings["claude"]["roles"].append("rewrite")
        self.claude.script = [message("```python\nPARAMS = {}\n```\nWider wings.", cost="0.090000")]
        result = self.ask(self.router())
        self.assertEqual((result["route"], result["cost_usd"]), ("claude", 0.09))
        self.assertEqual(self.sail_calls, [])
        self.assertAlmostEqual(self.router().claude_spent(role="rewrite"), 0.09)


class RoleLines(RouterCase):
    def setUp(self):
        super().setUp()
        self.settings["claude"]["roles"].append("rewrite")
        self.settings["claude"]["role_usd_day"] = {"rewrite": 0.5}

    def test_the_role_line_reached_falls_through_to_sail_and_the_next_utc_day_has_it_again(self):
        self.spend("rewrite", 0.5)
        self.assertEqual(self.router().claude_role_room("rewrite"), 0.0)
        result = self.ask(self.router())
        self.assertEqual((result["route"], self.sail_calls), ("sail", ["pro_asap"]))
        self.assertIn("rewrite line for today has no room", "; ".join(result["fallback_reasons"]))
        self.assertEqual(self.claude.calls, [], "Claude was never asked")
        self.assertEqual(self.store.spent(["claude"]), 0.5, "no hold was booked")
        # Other roles are not on this line.
        self.spend("architect", 3.0)
        self.claude.script = [message('{"families": []}', cost="0.100000")]
        self.assertEqual(self.ask(self.router(), role="architect", key="arch")["route"], "claude")
        # The next UTC day the rewrite has its line again; yesterday's spend does not count.
        self.clock.advance(86400)
        self.claude.script = [message("```python\nPARAMS = {}\n```", cost="0.090000")]
        self.assertEqual(self.ask(self.router(), key="call-2")["route"], "claude")

    def test_a_call_that_would_pass_the_line_skips_claude_for_openai_when_the_role_has_it(self):
        self.spend("rewrite", 0.45)
        ceiling = self.router().claude_request("THE RULES", "the packet")[1]
        self.assertGreater(ceiling, 0.05, "the call's worst case does not fit in the $0.05 left")
        result = self.ask(self.router(), openai_model="gpt-6-sol", need_usd=0.01)
        self.assertEqual((result["route"], result["model"]), ("openai", "gpt-6-sol"))
        self.assertEqual((self.claude.calls, self.sail_calls), ([], []))

    def test_holds_count_against_the_line_until_they_settle(self):
        self.settings["claude"]["role_usd_day"] = {"rewrite": 1.0}
        router = self.router()
        _, ceiling = router.claude_request("THE RULES", "the packet")
        seen = []

        def opener(request, timeout=None):
            seen.append(router.claude_role_room("rewrite"))
            return message("```python\nPARAMS = {}\n```", cost="0.090000")

        self.claude = opener
        self.assertEqual(self.ask(self.router())["route"], "claude")
        self.assertAlmostEqual(seen[0], 1.0 - ceiling, places=5, msg="the in-flight hold is on the line")
        self.assertAlmostEqual(self.router().claude_role_room("rewrite"), 0.91, places=5, msg="settled at the gateway's cost")

    def test_a_malformed_line_is_a_zero_line_and_null_is_no_line(self):
        cases = {"text": ("a lot", 0.0), "negative": (-1, 0.0), "nan": ("NaN", 0.0), "infinite": ("Infinity", 0.0),
                 "boolean": (True, 0.0), "null": (None, None), "number as text": ("2.5", 2.5)}
        for name, (value, line) in cases.items():
            with self.subTest(case=name):
                self.settings["claude"]["role_usd_day"] = {"rewrite": value}
                self.assertEqual(self.router().claude_role_line("rewrite"), line)
        self.settings["claude"]["role_usd_day"] = 5
        self.assertEqual(self.router().claude_role_line("architect"), 0.0, "not an object: every role is held at zero")
        self.settings["claude"]["role_usd_day"] = {"rewrite": "a lot"}
        self.assertEqual(self.ask(self.router())["route"], "sail")
        self.assertEqual(self.claude.calls, [])


class ArchitectWithoutOpenAI(RouterCase):
    def setUp(self):
        super().setUp()
        self.settings["architect"]["openai_model"] = None  # OpenAI is no longer topped up

    def architect(self, router):
        return Architect(self.store, router, self.settings, clock=self.clock)

    def test_claude_up_answers_every_pass_alone(self):
        self.claude.script = [message('{"families": []}', cost="0.200000") for _ in range(3)]
        routes = []
        for _ in range(3):
            routes.append(self.architect(self.router()).run().get("route"))
            self.clock.advance(3600)
        self.assertEqual(routes, ["claude", "claude", "claude"], "no Astra turn without an OpenAI model")
        self.assertEqual((self.openai.calls, self.sail_calls), ([], []))
        self.assertEqual(self.claude.headers()["x-ltcm-role"], "architect")

    def test_claude_down_or_capped_falls_back_to_sail(self):
        cases = {
            "unconfigured": dict(configured=False),
            "gateway overloaded": dict(script=[refused(529, "overloaded", cost="0.000000")]),
            "gateway refuses at its funded total": dict(script=[refused(402, '{"cap": "claude_funded"}')]),
            "funded total at its reserve": dict(meter=5.0),
            "meter unreadable": dict(meter=None),
            "swarm's own Claude line spent": dict(spent=("earlier", 100.0)),
            "the architect's line reached": dict(line=2.0, spent=("architect", 2.0)),
        }
        for name, case in cases.items():
            with self.subTest(case=name):
                self.setUp()
                self.claude.script = list(case.get("script", []))
                self.meter.value = case.get("meter", 100)
                if "line" in case:
                    self.settings["claude"]["role_usd_day"] = {"architect": case["line"]}
                if "spent" in case:
                    self.spend(*case["spent"])
                out = self.architect(self.router(configured=case.get("configured", True))).run()
                self.assertEqual((out.get("route"), out.get("model")), ("sail", "k3_balanced"), name)
                self.assertEqual(self.sail_calls, ["k3_balanced"])
                self.assertEqual(self.openai.calls, [], "no OpenAI model: OpenAI is never asked")


class RewriteThroughTheResearcher(ResearcherCase):
    def setUp(self):
        super().setUp()
        self.claude = FakeOpener()
        self.router.claude_factory = lambda model: Claude(GATEWAY, lambda: "synthetic", model=model, opener=self.claude)
        self.router.claude_meter = FakeClaudeMeter(100)
        self.fid = self.fam["id"]
        self.researcher().cycle(self.fid)  # the starter: version 1 and its Train run

    def rewrite(self):
        r = self.researcher()
        r.pace = lambda: False
        self.store.update_family(self.fid, stall=5)
        out = {}
        self.assertTrue(r.request_rewrite(self.store.family(self.fid), out))
        return out, self.store.family(self.fid)["state"]

    def test_with_the_default_roles_the_rewrite_is_sails(self):
        self.steps = [{"text": "```python\n" + self.code + "\n```\nOne change."}]
        before = len(self.sail.bodies)
        out, state = self.rewrite()
        self.assertEqual(state["rewrite_ready"]["code"].strip(), self.code.strip())
        self.assertEqual(state["rewrite_ready"]["profile"], out["rewrite_asked"])
        self.assertEqual(len(self.sail.bodies), before + 1)
        self.assertEqual(self.claude.calls, [])

    def test_with_rewrite_in_the_roles_claude_writes_it_and_is_its_author(self):
        self.settings["claude"]["roles"].append("rewrite")
        self.claude.script = [message("```python\n" + self.code + "\n```\nOne change.", cost="0.090000")]
        before = len(self.sail.bodies)
        _, state = self.rewrite()
        self.assertEqual(state["rewrite_ready"]["code"].strip(), self.code.strip())
        self.assertEqual(state["rewrite_ready"]["profile"], "claude-opus-5-5", "the version's author is the model that wrote it")
        self.assertEqual(len(self.sail.bodies), before, "Sail was not asked")
        self.assertEqual(self.claude.headers()["x-ltcm-role"], "rewrite")
        self.assertAlmostEqual(self.router.claude_spent(role="rewrite"), 0.09)
        hold = self.store._all("SELECT usd FROM spend WHERE kind='claude' ORDER BY seq")[0]["usd"]
        self.assertAlmostEqual(hold, float(reservation_ceiling(self.claude.body())), places=6,
                               msg="held at the gateway's worst case alone: no OpenAI minimum on a Claude-or-Sail call")

    def test_the_rewrite_line_reached_falls_through_to_sail(self):
        self.settings["claude"]["roles"].append("rewrite")
        self.settings["claude"]["role_usd_day"] = {"rewrite": 1.0}
        self.store.add_spend("claude", 1.0, family=self.fid, detail={"role": "rewrite"})
        self.steps = [{"text": "```python\n" + self.code + "\n```"}]
        out, state = self.rewrite()
        self.assertEqual(state["rewrite_ready"]["profile"], out["rewrite_asked"])
        self.assertEqual(self.claude.calls, [])


class DiagnosticianLine(DiagnosticianCase):
    def test_the_diagnosticians_role_line_skips_its_round_before_any_call(self):
        self.settings["claude"]["role_usd_day"] = {"diagnostician": 0.0}
        out = self.diagnostician().run()
        self.assertIn("claude.role_usd_day", out["skipped"])
        self.assertEqual(self.claude.calls, [])


def tearDownModule():
    for error in ERRORS:
        error.close()


if __name__ == "__main__":
    unittest.main()
