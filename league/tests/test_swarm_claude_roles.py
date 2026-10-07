"""More roles on Claude (Sept 29, 2026, the owner's decision: Sail and Claude are the only lines topped up). Every role's
call asks for Claude, so `claude.roles` alone decides who gets it: the defaults change nothing, "rewrite" or "review" in
`claude.roles` routes the researcher's stall rewrite or the gate's review to Claude, a role's own daily line
(`claude.role_usd_day`) sends it to its next route once reached, and the architect without an OpenAI model is Claude's
alone while Claude is up and Sail's when Claude is down or capped. A call counts against a line on the day its hold was
booked (a call across midnight, or a hold trued up a day later, gives nothing back to the next day), a role may have its
own Claude model (`claude.role_model`), and a review Claude answered is the plan's reviewer (no false warning) unless
the audit was the same model. The real router, the real Claude and Frontier clients over fake openers, the real
Researcher, Gate, Tournament, Architect and Diagnostician."""

from __future__ import annotations

import copy
import io
import json
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
from league.tests.swarm_fakes import Clock, FakeMonth, unbound_budget
from league.tests.test_claude import message
from league.swarm.tournament import Tournament
from league.tests.test_frontier import GATEWAY, FakeOpener, FakeResponse, ok
from league.tests.test_swarm_claude_routing import FakeClaudeMeter
from league.tests.test_swarm_diagnostician import DiagnosticianCase
from league.tests.test_swarm_researcher import ResearcherCase
from league.tests.test_swarm_rounds import RoundCase

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
        # THE BUDGET is not what these tests judge: a line well above every role's own (no block is the floor).
        self.settings["budget"] = unbound_budget(self)
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
        # Sept 29, 2026 (swarm/sonnet-researchers): the top band's research cycles joined the roles, on a $100 daily line;
        # the strategist (league/swarm/strategist.py) joined with its own $4 line.
        # LTCM v3: the House's weekly post-mortem (league/ops/postmortem.py) on Claude Opus 5.5 within $1 a day.
        self.assertEqual(DEFAULTS["claude"]["roles"], ["architect", "audit", "diagnostician", "postmortem", "researcher",
                                                       "strategist"])
        self.assertEqual(DEFAULTS["claude"]["role_usd_day"], {"postmortem": 1.0, "researcher": 100.0, "strategist": 4.0})
        self.assertEqual(DEFAULTS["claude"]["role_model"], {"postmortem": "claude-opus-5-5", "researcher": "claude-sonnet-5-5"})
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
        # THE BUDGET is not what these tests judge: a line well above the rewrite's hold (no block is the floor, whose $2
        # of Claude less the holds it keeps for the gate's review and audit leaves a rewrite no room).
        self.settings["budget"] = unbound_budget(self)
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


DAY = 86400


class CountedOnTheHoldsDay(RouterCase):
    """A call is counted against a line on the day its hold was booked: the row that settles it lands when the bill does,
    and a bill that lands after 00:00 UTC (or a hold trued up a day later) is the earlier day's, not a credit to today."""

    def setUp(self):
        super().setUp()
        self.settings["claude"]["roles"].append("rewrite")
        self.settings["claude"]["role_usd_day"] = {"rewrite": 1.0}

    def today(self):
        return self.clock.t - self.clock.t % DAY

    def admitted_at_worst_case(self, ceiling):
        """Calls billed at their full worst case until the line refuses one: how many it admitted."""
        n = 0
        while True:
            self.claude = lambda request, timeout=None: message("```python\nPARAMS = {}\n```", cost=f"{ceiling:.6f}")
            if self.ask(self.router(), key=f"today-{n}")["route"] != "claude":
                return n
            n += 1

    def test_a_call_across_midnight_gives_the_next_day_no_room(self):
        self.clock.t = self.today() + DAY - 30  # 23:59:30 UTC
        clock = self.clock
        ceiling = self.router().claude_request("THE RULES", "the packet")[1]

        def slow(request, timeout=None):
            clock.advance(120)  # the answer lands at 00:01:30, a cent against its worst-case hold
            return message("```python\nPARAMS = {}\n```", cost="0.010000")

        self.claude = slow
        self.assertEqual(self.ask(self.router(), key="late")["route"], "claude")
        start = self.today()
        release = self.store._all("SELECT usd, epoch FROM spend WHERE kind='claude' ORDER BY seq")[-1]
        self.assertGreaterEqual(release["epoch"], start, "the release is booked after midnight")
        self.assertLess(release["usd"], 0)
        self.assertEqual(self.router().claude_role_room("rewrite"), 1.0, "the late call is yesterday's: no credit today")
        n = self.admitted_at_worst_case(ceiling)
        self.assertEqual(n, int(1.0 // ceiling), "today admits what fits in its own line, no more")
        rows = [(r["usd"], json.loads(r["detail"])) for r in self.store._all(
            "SELECT usd, detail FROM spend WHERE kind='claude' AND epoch>=?", (start,))]
        today = {d["request"] for _, d in rows if "hold" in d}
        real = sum(usd for usd, d in rows if (d.get("settles_hold") or d.get("request")) in today)
        self.assertLessEqual(real, 1.0 + 1e-9, "today's calls stay inside today's line")

    def test_a_hold_trued_up_a_day_later_gives_nothing_back_to_today(self):
        self.claude = FakeOpener(refused(502, "bad gateway"))  # the bill is unknown: the worst case stays held
        self.assertEqual(self.ask(self.router(), key="lost")["route"], "sail")
        [request_id] = self.store.get("claude_unsettled")
        self.clock.t = self.today() + DAY + 3600  # 01:00 UTC the next day
        self.claude = FakeOpener(message("```python\nPARAMS = {}\n```", cost="0.300000"))
        self.assertEqual(self.ask(self.router(), key="today")["route"], "claude")
        self.assertAlmostEqual(self.router().claude_role_room("rewrite"), 0.70, places=6)
        self.claude = FakeOpener(FakeResponse({"state": "released", "cost_usd": "0.000000"}))
        self.assertEqual(self.router().settle_claude_holds(), 1, "yesterday's hold is released today")
        self.assertNotIn(request_id, self.store.get("claude_unsettled") or {})
        self.assertAlmostEqual(self.router().claude_role_room("rewrite"), 0.70, places=6,
                               msg="yesterday's release is not a credit against today's calls")
        self.assertAlmostEqual(self.router().claude_spent(role="rewrite"), 0.30, places=6, msg="the lifetime total is exact")

    def test_the_diagnosticians_rolling_day_counts_a_call_at_its_hold(self):
        # The diagnostician's own `usd_day` reads a rolling 24 hours (`claude_spent(since=now - 86400)`).
        self.claude = FakeOpener(refused(502, "bad gateway"))
        self.ask(self.router(), role="diagnostician", key="lost", sail_profile="pro_asap")
        self.clock.advance(DAY + 3600)
        self.claude = FakeOpener(message('{"decision": "retire"}', cost="0.400000"))
        self.assertEqual(self.ask(self.router(), role="diagnostician", key="today")["route"], "claude")
        self.claude = FakeOpener(FakeResponse({"state": "released", "cost_usd": "0.000000"}))
        self.assertEqual(self.router().settle_claude_holds(), 1)
        self.assertAlmostEqual(self.router().claude_spent(role="diagnostician", since=self.clock.t - DAY), 0.40, places=6,
                               msg="the release of a hold booked 25 hours ago is not in the window")

    def test_a_call_settled_the_same_day_counts_at_its_cost(self):
        self.claude = FakeOpener(message("```python\nPARAMS = {}\n```", cost="0.120000"))
        self.assertEqual(self.ask(self.router())["route"], "claude")
        self.clock.advance(60)
        self.assertAlmostEqual(self.router().claude_role_room("rewrite"), 0.88, places=6)


class RoleModel(RouterCase):
    def test_no_entry_is_the_claude_model(self):
        router = self.router()
        for value in ({}, None, {"review": None}, {"review": ""}, {"review": 5}, ["review"]):
            with self.subTest(role_model=value):
                self.settings["claude"]["role_model"] = value
                self.assertEqual(router.claude_model("review"), "claude-opus-5-5")
        self.assertEqual(router.claude_model(), "claude-opus-5-5")

    def test_a_roles_model_asks_and_is_held_at_that_models_price(self):
        self.settings["claude"]["roles"].append("rewrite")
        self.settings["claude"]["role_model"] = {"rewrite": "claude-sonnet-5"}
        router = self.router()
        _, opus = router.claude_request("THE RULES", "the packet", role="architect")
        _, sonnet = router.claude_request("THE RULES", "the packet", role="rewrite")
        self.assertLess(sonnet, opus, "Sonnet's worst case is below Opus's")
        self.claude.script = [message("```python\nPARAMS = {}\n```", model="claude-sonnet-5", cost="0.040000")]
        result = self.ask(router)
        self.assertEqual((result["route"], result["model"], result["cost_usd"]), ("claude", "claude-sonnet-5", 0.04))
        self.assertEqual(self.claude.body()["model"], "claude-sonnet-5")
        hold = json.loads(self.store._all("SELECT detail FROM spend WHERE kind='claude' ORDER BY seq")[0]["detail"])
        self.assertEqual(hold["model"], "claude-sonnet-5")
        self.assertAlmostEqual(self.store._all("SELECT usd FROM spend WHERE kind='claude' ORDER BY seq")[0]["usd"], sonnet, places=6)

    def test_an_unpriced_roles_model_is_never_sent(self):
        self.settings["claude"]["roles"].append("rewrite")
        self.settings["claude"]["role_model"] = {"rewrite": "claude-unpriced-9"}
        result = self.ask(self.router())
        self.assertEqual((result["route"], self.sail_calls), ("sail", ["pro_asap"]))
        self.assertIn("no verified price", "; ".join(result["fallback_reasons"]))
        self.assertEqual((self.claude.calls, self.store.spent(["claude"])), ([], 0))


class GateRoundWithTheReviewOnClaude(RoundCase):
    """A whole gate round with "review" in `claude.roles`: the review is Claude's, the audit (a default role) too."""

    def setUp(self):
        super().setUp()
        self.claude = FakeOpener()
        self.router.claude_factory = lambda model: Claude(GATEWAY, lambda: "synthetic", model=model, opener=self.claude)
        self.router.claude_meter = FakeClaudeMeter(100)
        self.settings["claude"]["roles"].append("review")

    def round(self, review_model="claude-opus-5-5"):
        self.family("a")
        Tournament(self.store, self.pool, self.settings).validate(self.store.families(alive=True))
        passed = json.dumps({"verdict": "pass", "reasons": []})
        self.claude.script = [message(passed, model=review_model, cost="0.050000"), message(passed, cost="0.050000")]
        Gate(self.store, self.pool, self.router, self.settings).run()
        events = [e for e in self.store.events_after(0)]
        alerts = [e["payload"] for e in events if e["kind"] == "swarm.status" and e["payload"].get("action") == "not_the_plans_reviewer"]
        flags = [e["payload"].get("not_the_plans_reviewer") for e in events
                 if e["kind"] == "swarm.gate" and e["payload"].get("action") == "review"]
        return self.store.family("a")["state"]["review"], alerts, flags

    def test_a_review_claude_answered_on_its_own_model_is_the_plans_and_no_warning_is_sent(self):
        self.settings["claude"]["role_model"] = {"review": "claude-sonnet-5"}
        review, alerts, flags = self.round(review_model="claude-sonnet-5")
        self.assertEqual((review["route"], review["model"]), ("claude", "claude-sonnet-5"))
        self.assertEqual((review["audit"]["route"], review["audit"]["model"]), ("claude", "claude-opus-5-5"))
        self.assertEqual([json.loads(r.data)["model"] for r, _ in self.claude.calls], ["claude-sonnet-5", "claude-opus-5-5"])
        self.assertEqual(alerts, [], "Claude is one of the plan's reviewers: no Sail stood in")
        self.assertEqual(flags, [False])
        self.assertEqual(len(self.store.looks()), 1, "two different readers passed it: the look is taken")
        self.assertEqual(self.sail.bodies, [])

    def test_one_claude_model_reading_twice_is_told_as_that_not_as_sail(self):
        review, alerts, flags = self.round()
        self.assertEqual((review["route"], review["audit"]["route"]), ("claude", "claude"))
        self.assertEqual(review["model"], review["audit"]["model"])
        [alert] = alerts
        self.assertTrue(alert["alert"])
        self.assertTrue(alert["same_reader"])
        self.assertIn("both claude-opus-5-5: one model read the program twice", alert["text"])
        self.assertNotIn("Sail", alert["text"])
        self.assertEqual(flags, [False], "the review itself is the plan's")


def tearDownModule():
    for error in ERRORS:
        error.close()


if __name__ == "__main__":
    unittest.main()
