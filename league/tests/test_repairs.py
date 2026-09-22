"""The repair worklist, its deterministic sources, the engineer, Merton.follow after a refusal,
the per-strategy descriptions that end registry collisions, and the synthetic drill (Sept 22, 2026)."""

import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from league import ci, strategies
from league.engineer import Engineer, NEEDS_CORE
from league.frontier import Answer, FrontierError
from league.ledger import Ledger
from league.merton import ForgeError, Merton, parse_proposal
from league.tests.fakes import Clock
from league.worklist import Sources, Worklist, normalize_reason

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import repair_drill  # noqa: E402

GOOD = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "test", "symbols": ["BTC/USD"], "wake_minutes": 15}
PARAMS = {}

def decide(ctx):
    return {"intents": [], "thought": "nothing"}
'''
TOOL = "def midpoint(bid, ask):\n    return (bid + ask) / 2\n"
TOOL_TEST = "import unittest\n\nclass T(unittest.TestCase):\n    def test_mid(self):\n        pass\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.clock = Clock()
        self.ledger = Ledger(self.root / "l.sqlite", clock=self.clock)
        self.worklist = Worklist(self.ledger, clock=self.clock)
        self.repo = self.root / "repo"
        for sub in ("league/tools", "league/strategies", "league/tests"):
            (self.repo / sub).mkdir(parents=True)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def ev(self, seq, agent, text="x"):
        return {"seq": seq, "at": f"2026-09-01T0{seq % 10}:00:00.000Z", "agent": agent, "excerpt": text}

    def deploy(self, files):
        for row in files:
            path = self.repo / row["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(row["content"])


class WorklistFold(Base):
    def test_the_same_key_merges_evidence_and_agents_and_keeps_the_original(self):
        self.worklist.report(key="k", kind="shared_defect", summary="first words", evidence=[self.ev(1, "a", "original")],
                             agents=["a"], source="audit", severity="high")
        self.worklist.report(key="k", kind="shared_defect", summary="later words", evidence=[self.ev(1, "a", "original"), self.ev(2, "b")],
                             agents=["b"], source="refusals", severity="blocker")
        job = self.worklist.get("k")
        self.assertEqual(job.summary, "first words")
        self.assertEqual(job.agents, {"a", "b"})
        self.assertEqual(job.evidence[0]["excerpt"], "original")
        self.assertEqual(len(job.evidence), 2, "a repeated evidence row is not counted twice")
        self.assertEqual(job.reports, 2)
        self.assertEqual(job.sources, {"audit", "refusals"})
        # agents 2 x recurrence 2 x severity blocker 3
        self.assertEqual(job.priority(), 12.0)

    def test_priority_orders_the_queue_and_admission_follows_the_line(self):
        self.worklist.report(key="one", kind="bug_report", summary="s", evidence=[self.ev(1, "a")], agents=["a"], source="triage", severity="low")
        self.worklist.report(key="many", kind="order_refusal", summary="s", evidence=[self.ev(i, f"a{i}") for i in range(1, 4)],
                             agents=[], source="refusals", severity="medium", occurrences=3)
        self.assertEqual([j.key for j in self.worklist.queue()], ["many", "one"])
        self.assertEqual(self.worklist.admit(threshold=2.0), ["many"])
        self.assertEqual(self.worklist.get("one").state, "proposed")
        self.worklist.report(key="op", kind="bug_report", summary="s", evidence=[], agents=[], source="operator", severity="low")
        self.assertEqual(self.worklist.admit(threshold=2.0), ["op"], "an operator's report is admitted whatever its priority")

    def test_costs_add_up_and_the_latest_row_says_the_attempt(self):
        self.worklist.report(key="k", kind="bug_report", summary="s", evidence=[], agents=[], source="operator", severity="low")
        self.worklist.transition("k", "patching", attempt=1, cost_usd="0.40")
        self.worklist.transition("k", "revising", attempt=1, cost_usd="0.10")
        self.worklist.transition("k", "admitted", attempt=0, note="refused before anything was bought")
        job = self.worklist.get("k")
        self.assertEqual((job.cost_usd, job.attempt, job.state), (Decimal("0.50"), 0, "admitted"))
        with self.assertRaises(ValueError):
            self.worklist.transition("k", "finished")


class DeterministicSources(Base):
    def scan(self, **kw):
        return Sources(self.ledger, self.worklist, **kw).scan()

    def test_an_audit_veto_is_reported_with_its_defect(self):
        self.ledger.append("audit.verdict", {"approve": True, "summary": "fine", "findings": []}, agent="good")
        self.ledger.append("audit.verdict", {"approve": False, "error": "unreachable"}, agent="failed-call")
        self.ledger.append("audit.verdict", {"approve": False, "book": "alpaca-paper", "summary": "Cent rounding defeats the minimum discount.",
                                             "findings": [{"issue": "rounding", "severity": "blocker"}]}, agent="haghani")
        self.assertEqual(self.scan(), ["audit_veto:haghani"])
        job = self.worklist.get("audit_veto:haghani")
        self.assertEqual((job.kind, job.severity, job.agents), ("audit_veto", 3.0, {"haghani"}))
        self.assertIn("Cent rounding", job.evidence[0]["excerpt"])

    def test_a_refusal_reason_is_a_repair_only_across_three_agents_or_wakes(self):
        def refuse(agent, minute):
            self.clock.now = 1789000000.0 + minute * 60
            self.ledger.append("book.refused", {"book": "kalshi-shadow", "reasons": [f"this market is expected to resolve in {minute + 30} hours; entries must resolve within 12"]}, agent=agent)
        refuse("agent-a", 0)
        refuse("agent-b", 1)
        sources = Sources(self.ledger, self.worklist)
        self.assertEqual(sources.scan(), [])
        refuse("agent-c", 2)
        reported = sources.scan()
        self.assertEqual(len(reported), 1)
        job = self.worklist.get(reported[0])
        self.assertEqual(job.agents, {"agent-a", "agent-b", "agent-c"})
        self.assertEqual(job.recurrence, 3)
        self.assertIn("<agent>", normalize_reason("x has no seat on the alpaca-paper book, x", "x"))
        # A restarted process reads everything again and reports nothing twice.
        self.assertEqual(Sources(self.ledger, self.worklist).scan(), [])
        self.assertEqual(self.ledger.count(kinds="repair.reported"), 1)
        refuse("agent-a", 5)
        self.assertEqual(sources.scan(), reported)
        self.assertEqual(self.worklist.get(reported[0]).recurrence, 4)

    def test_a_merton_pr_refused_by_ci_is_reported_but_a_repair_s_own_is_not(self):
        self.ledger.append("merton.change", {"number": 72, "status": "opened", "role": "architect", "title": "t", "paths": ["league/strategies/x.py"]})
        self.ledger.append("merton.change", {"number": 72, "status": "refused by CI", "role": "architect", "title": "t", "paths": ["league/strategies/x.py"]})
        self.ledger.append("merton.change", {"number": 90, "status": "refused by CI", "role": "toolsmith", "repair": "k", "paths": []})
        self.assertEqual(self.scan(), ["ci_failure:pr-72"])
        self.assertEqual(self.worklist.get("ci_failure:pr-72").details["paths"], ["league/strategies/x.py"])

    def test_tool_requests_merge_by_name_and_a_blocked_verdict_is_kept(self):
        first = self.ledger.append("tool.request", {"name": "attention_underlying", "description": "point-in-time counts"}, agent="leahy")
        self.ledger.append("tool.request", {"name": "Attention Underlying", "description": "the same feed"}, agent="leahy-2")
        self.ledger.append("tool.blocked", {"request": first.id, "outcome": "cannot be a pure tool: needs data", "status": "blocked"})
        self.scan()
        job = self.worklist.get("missing_data:attention_underlying")
        self.assertEqual(job.agents, {"leahy", "leahy-2"})
        self.assertTrue(job.details["blocked"])
        self.assertIn(first.id, job.details["requests"])

    def test_research_that_names_a_missing_input_twice_is_reported_and_negations_are_not(self):
        say = lambda agent, text, s: self.ledger.append("agent.research", {"tool": "summary", "summary": text, "session": s}, agent=agent)
        say("leahy-3", "No replay: the count feed is a missing feed for these series.", "s1")
        say("leahy-4", "Missing data is not the blocker here; the markets are closed.", "s2")
        sources = Sources(self.ledger, self.worklist, niche_of=lambda a: "kalshi-attention")
        self.assertEqual(sources.scan(), [])
        say("leahy-5", "Still a missing input: point-in-time counts.", "s3")
        self.assertEqual(sources.scan(), ["missing_data:research:kalshi-attention"])
        self.assertEqual(self.worklist.get("missing_data:research:kalshi-attention").agents, {"leahy-3", "leahy-5"})

    def test_a_triage_report_is_folded_like_any_other(self):
        self.ledger.append("repair.reported", {"key": "missing_data:funding_rates", "kind": "missing_data", "summary": "funding rates",
                                               "evidence": [self.ev(3, "a")], "agents": ["a"], "source": "triage", "severity": "high"})
        self.assertEqual(self.worklist.get("missing_data:funding_rates").sources, {"triage"})


class FakeFrontier:
    def __init__(self, *answers, error=None, cost="0.50"):
        self.answers, self.error, self.asked, self.cost, self.model = list(answers), error, [], Decimal(cost), "gpt-6-astra"

    def ask(self, **kw):
        self.asked.append(kw)
        if self.error:
            raise self.error
        return Answer(json.dumps(self.answers.pop(0)), self.cost, {}, "gpt-6-astra")


class FakeGitHub:
    """A forge and CI in one: every proposal opens a PR; `judge` decides what CI says of it."""

    def __init__(self, judge=None, readable=True):
        self.proposed, self.judge, self.readable, self.verdicts = [], judge or (lambda files: None), readable, {}

    def propose(self, *, role, slug, title, body, files):
        number = 100 + len(self.proposed)
        self.proposed.append({"role": role, "slug": slug, "title": title, "body": body, "files": files, "number": number})
        self.verdicts[number] = self.judge(files)
        return {"ok": True, "branch": f"merton/{role}/{slug}-{number}", "number": number, "head": f"{number:040x}"}

    def status(self, number):
        failure = self.verdicts[number]
        return {"number": number, "state": "closed" if failure is None else "open", "merged": failure is None, "head": f"{number:040x}",
                "checks": {"conclusion": "success" if failure is None else "failure"}}

    def failures(self, number):
        if not self.readable:
            raise ForgeError("HTTP 404: Not found.")
        failure = self.verdicts[number]
        return {"number": number, "failures": [] if failure is None else [{"name": "judge", "annotations": [{"message": failure}]}]}


class EngineerLoop(Base):
    def engineer(self, frontier, forge, **settings):
        base = {"min_seconds_between_calls": 0, "observe_hours": 1.0, "max_job_usd": "5.00"}
        self.merton = Merton(frontier, forge, self.ledger, evidence=lambda role: {}, clock=self.clock)
        return Engineer(frontier, forge, self.ledger, self.worklist, clock=self.clock, repo=self.repo,
                        settings={**base, **settings}, code_of=lambda a: {"family": "fam", "code": GOOD} if a == "parent" else None)

    def job(self, key="shared_defect:quote-helper", kind="shared_defect", agents=("a", "b"), severity="high"):
        self.worklist.report(key=key, kind=kind, summary="agents compute midpoints wrong", agents=list(agents), source="triage",
                             severity=severity, evidence=[self.ev(1, agents[0] if agents else "house", "original evidence")])
        return key

    def tool_answer(self, content=TOOL):
        return {"summary": "a quote helper", "role": "toolsmith", "slug": "midpoint", "title": "Add a midpoint helper", "body": "b",
                "files": [{"path": "league/tools/midpoint.py", "content": content}, {"path": "league/tests/test_tool_midpoint.py", "content": TOOL_TEST}],
                "needs_core": None}

    def states(self, key):
        return [h["state"] for h in self.worklist.get(key).history]

    def test_a_failed_check_is_revised_against_ci_s_text_and_verified_only_after_the_window(self):
        key = self.job()
        forge = FakeGitHub(judge=lambda files: None if "(bid + ask) / 2" in files[0]["content"] else "FAIL: test_mid: expected 2.0, got 1")
        frontier = FakeFrontier(self.tool_answer("def midpoint(bid, ask):\n    return bid\n"), self.tool_answer())
        engineer = self.engineer(frontier, forge)
        engineer.step()
        self.assertEqual(self.worklist.get(key).state, "testing")
        self.merton.follow()
        engineer.step()  # refused: the failure text is read back, and the revision is bought
        self.assertIn("expected 2.0", json.loads(frontier.asked[1]["user"])["previous"]["ci_failure"])
        self.assertEqual(self.worklist.get(key).state, "testing")
        self.merton.follow()
        engineer.step()
        self.assertEqual(self.worklist.get(key).state, "canary", "merged is not deployed")
        engineer.step()
        self.assertEqual(self.worklist.get(key).state, "canary")
        self.deploy(forge.proposed[-1]["files"])
        engineer.step()
        self.assertEqual(self.worklist.get(key).state, "observing")
        self.clock.advance(1800)
        engineer.step()
        self.assertEqual(self.worklist.get(key).state, "observing", "the window has not passed")
        self.clock.advance(1900)
        engineer.step()
        self.assertEqual(self.states(key), ["admitted", "reproducing", "patching", "testing", "testing", "revising", "reproducing",
                                            "patching", "testing", "testing", "canary", "observing", "verified"])
        job = self.worklist.get(key)
        self.assertEqual((job.cost_usd, job.attempt), (Decimal("1.00"), 2))
        passes = [e.payload for e in self.ledger.iter(kinds="merton.pass") if e.payload.get("role") == "engineer"]
        self.assertEqual([p["cost_usd"] for p in passes], ["0.50", "0.50"], "every paid call is a row the pacer reads")

    def test_attempts_are_bounded_and_the_costs_are_kept(self):
        key = self.job()
        forge = FakeGitHub(judge=lambda files: "FAIL: still wrong")
        engineer = self.engineer(FakeFrontier(*[self.tool_answer()] * 3), forge, max_attempts=3)
        for _ in range(3):
            engineer.step()
            self.merton.follow()
            self.clock.advance(1000)  # the follower's own cadence for refused changes
        engineer.step()
        job = self.worklist.get(key)
        self.assertEqual(job.state, "dormant")
        self.assertIn("attempt limit", job.note)
        self.assertEqual((job.attempt, job.cost_usd, len(forge.proposed)), (3, Decimal("1.50"), 3))
        engineer.step()
        self.assertEqual(len(forge.proposed), 3)

    def test_a_job_that_would_pass_its_ceiling_is_refused_before_any_call(self):
        key = self.job()
        frontier = FakeFrontier(self.tool_answer())
        engineer = self.engineer(frontier, FakeGitHub(), max_job_usd="0.10")
        engineer.step()
        job = self.worklist.get(key)
        self.assertEqual(job.state, "dormant")
        self.assertIn("per-job spend limit", job.note)
        self.assertEqual(frontier.asked, [])

    def test_a_closed_day_allowance_waits_and_a_refused_call_is_not_an_attempt(self):
        key = self.job()
        frontier = FakeFrontier(error=FrontierError("HTTP 402 over the month", status=402))
        engineer = self.engineer(frontier, FakeGitHub())
        engineer.may_spend = lambda: False
        engineer.step()
        self.assertEqual((self.worklist.get(key).state, frontier.asked), ("admitted", []))
        engineer.may_spend = lambda: True
        engineer.step()
        job = self.worklist.get(key)
        self.assertEqual((job.state, job.attempt, job.cost_usd), ("admitted", 0, Decimal(0)))

    def test_a_call_that_may_have_been_billed_is_counted_at_its_worst_case(self):
        key = self.job()
        frontier = FakeFrontier(error=FrontierError("frontier call failed: TimeoutError"))
        engineer = self.engineer(frontier, FakeGitHub())
        engineer.step()
        job = self.worklist.get(key)
        self.assertEqual((job.state, job.attempt), ("revising", 1))
        self.assertGreater(job.cost_usd, Decimal("0.5"), "the worst case, not zero")
        ambiguous = [e.payload for e in self.ledger.iter(kinds="merton.pass") if e.payload.get("ambiguous")]
        self.assertEqual(Decimal(ambiguous[0]["cost_usd"]), job.cost_usd)

    def test_a_restart_mid_call_books_the_hold_and_the_next_attempt_is_new_and_recorded(self):
        key = self.job()
        self.worklist.admit(threshold=0)
        self.worklist.transition(key, "reproducing", attempt=0)
        self.worklist.transition(key, "patching", attempt=1, extra={"request": "engineer:k:1:9", "hold_usd": "1.75"})
        forge = FakeGitHub()
        frontier = FakeFrontier(self.tool_answer())
        engineer = self.engineer(frontier, forge)  # a new process: nothing is in flight here
        engineer.step()
        job = self.worklist.get(key)
        self.assertEqual(self.states(key)[3:], ["revising", "reproducing", "patching", "testing", "testing"])
        self.assertIn("interrupted", job.history[3]["note"])
        self.assertEqual((job.attempt, job.cost_usd), (2, Decimal("2.25")))
        self.assertEqual(len(frontier.asked), 1, "one new call, recorded as attempt 2, not a silent repeat of attempt 1")
        interrupted = [e.payload for e in self.ledger.iter(kinds="merton.pass") if e.payload.get("interrupted")]
        self.assertEqual(interrupted[0]["cost_usd"], "1.75")

    def test_a_paid_patch_survives_a_forge_outage_without_being_bought_again(self):
        key = self.job()
        forge = FakeGitHub()
        real = forge.propose
        forge.propose = lambda **kw: (_ for _ in ()).throw(ForgeError("HTTP 503"))
        frontier = FakeFrontier(self.tool_answer())
        engineer = self.engineer(frontier, forge)
        engineer.step()
        self.assertEqual((self.worklist.get(key).state, self.worklist.get(key).pr), ("testing", None))
        forge.propose = real
        engineer.step()
        self.assertEqual(self.worklist.get(key).pr, 100)
        self.assertEqual(len(frontier.asked), 1)

    def test_a_fix_outside_the_allowlist_is_dormant_as_needing_core_authority(self):
        key = self.job()
        answer = {"summary": "the book must seat them", "role": "toolsmith", "files": [{"path": "league/book.py", "content": "x"}], "needs_core": None}
        engineer = self.engineer(FakeFrontier(answer), FakeGitHub())
        engineer.step()
        job = self.worklist.get(key)
        self.assertEqual(job.state, "dormant")
        self.assertTrue(job.note.startswith(NEEDS_CORE))
        other = self.job(key="k2")
        engineer.frontier = FakeFrontier({"needs_core": {"reason": "seats are House code", "paths": ["league/house.py"]}})
        engineer.step()
        self.assertTrue(self.worklist.get(other).note.startswith(NEEDS_CORE))

    def test_a_protective_refusal_is_rejected_and_a_house_one_is_dormant_without_a_call(self):
        protective = self.job(key="order_refusal:kalshi-shadow:desk daily loss #% reached limit #%; only risk-reducing orders allowed",
                              kind="order_refusal", severity="medium")
        seats = self.job(key="order_refusal:alpaca-paper:<agent> has no seat on the alpaca-paper book", kind="order_refusal", severity="medium")
        frontier = FakeFrontier()
        engineer = self.engineer(frontier, FakeGitHub())
        out = engineer.step()
        self.assertEqual(len(out["decided"]), 2, "decisions made by code do not wait for the next step")
        self.assertEqual(self.worklist.get(protective).state, "rejected")
        self.assertIn("protective rule", self.worklist.get(protective).note)
        self.assertTrue(self.worklist.get(seats).note.startswith(NEEDS_CORE))
        self.assertEqual(frontier.asked, [])

    def test_a_blocked_data_request_goes_dormant_without_a_call(self):
        first = self.ledger.append("tool.request", {"name": "feed", "description": "a feed nobody has"}, agent="a")
        self.ledger.append("tool.request", {"name": "feed", "description": "the same feed"}, agent="b")
        self.ledger.append("tool.blocked", {"request": first.id, "outcome": "cannot be a pure tool", "status": "blocked"})
        frontier = FakeFrontier()
        engineer = self.engineer(frontier, FakeGitHub())
        engineer.sources = Sources(self.ledger, self.worklist)
        engineer.step()
        self.assertTrue(self.worklist.get("missing_data:feed").note.startswith(NEEDS_CORE))
        self.assertEqual(frontier.asked, [])

    def test_ci_refusal_without_readable_text_waits_for_it_and_is_never_revised_blind(self):
        key = self.job()
        forge = FakeGitHub(judge=lambda files: None if len(forge.proposed) > 1 else "FAIL: test_mid", readable=False)
        frontier = FakeFrontier(self.tool_answer(), self.tool_answer())
        engineer = self.engineer(frontier, forge)
        engineer.step()
        self.merton.follow()
        engineer.step()
        self.assertIn("waiting for its failure text", self.worklist.get(key).note)
        rows = self.ledger.count(kinds="repair.status")
        self.clock.advance(3600)
        engineer.step()
        self.assertEqual(self.ledger.count(kinds="repair.status"), rows, "waiting writes nothing more")
        forge.readable = True  # the gateway's read is deployed within the window: the revision goes ahead
        engineer.step()
        self.assertEqual((self.worklist.get(key).state, len(frontier.asked)), ("testing", 2))

    def test_a_failure_text_that_never_arrives_ends_dormant_without_a_second_call(self):
        key = self.job()
        forge = FakeGitHub(judge=lambda files: "FAIL", readable=False)
        frontier = FakeFrontier(self.tool_answer(), self.tool_answer())
        engineer = self.engineer(frontier, forge)
        engineer.step()
        self.merton.follow()
        engineer.step()
        self.clock.advance(6 * 3600 + 1)
        engineer.step()
        job = self.worklist.get(key)
        self.assertEqual(job.state, "dormant")
        self.assertIn("failure text could not be read", job.note)
        self.assertEqual(len(frontier.asked), 1)

    def test_switched_off_it_still_reports_but_admits_and_buys_nothing(self):
        self.ledger.append("audit.verdict", {"approve": False, "summary": "broken", "findings": []}, agent="haghani")
        frontier = FakeFrontier(self.tool_answer())
        engineer = self.engineer(frontier, FakeGitHub(), enabled=False)
        engineer.sources = Sources(self.ledger, self.worklist)
        engineer.summary_path = self.root / "repairs.json"
        self.assertTrue(engineer.due())
        out = engineer.step()
        self.assertEqual((out["reported"], out["admitted"], frontier.asked), (["audit_veto:haghani"], [], []))
        self.assertEqual(self.worklist.get("audit_veto:haghani").state, "proposed")
        shown = json.loads((self.root / "repairs.json").read_text())
        self.assertEqual((shown["enabled"], shown["counts"], shown["top"][0]["key"]), (False, {"proposed": 1}, "audit_veto:haghani"))
        self.assertFalse(engineer.due(), "a step waits step_seconds")

    def test_the_pace_between_paid_calls_survives_a_restart(self):
        first, second = self.job(key="one"), self.job(key="two")
        frontier = FakeFrontier(self.tool_answer(), self.tool_answer())
        engineer = self.engineer(frontier, FakeGitHub(), min_seconds_between_calls=1800)
        engineer.step()
        self.assertEqual(len(frontier.asked), 1)
        restarted = self.engineer(frontier, FakeGitHub(), min_seconds_between_calls=1800)
        self.clock.advance(600)
        restarted.step()
        self.assertEqual(len(frontier.asked), 1, "a new process does not buy the next patch at once")
        self.clock.advance(1300)
        restarted.step()
        self.assertEqual(len(frontier.asked), 2)
        self.assertEqual({self.worklist.get(first).state, self.worklist.get(second).state}, {"testing"})

    def test_a_strategy_defect_becomes_a_new_child_that_inherits_nothing(self):
        (self.repo / "league/strategies/old.py").write_text(GOOD)
        key = self.job(key="audit_veto:parent", kind="audit_veto", agents=("parent",), severity="blocker")
        answer = {"summary": "round after checking", "role": "architect", "slug": "fixed", "title": "Corrected child", "body": "b", "needs_core": None,
                  "files": [{"path": "league/strategies/old.py", "content": GOOD},
                            {"path": "league/strategies/parent_fixed.py", "content": GOOD},
                            {"path": "league/strategies/parent_fixed.json", "content": json.dumps({"name": "parent-fixed", "family": "other", "why": "fix"})}]}
        forge = FakeGitHub()
        engineer = self.engineer(FakeFrontier(answer), forge)
        engineer.step()
        files = {f["path"]: f["content"] for f in forge.proposed[0]["files"]}
        self.assertNotIn("league/strategies/old.py", files, "an existing strategy file is never rewritten")
        described = json.loads(files["league/strategies/parent_fixed.json"])
        self.assertEqual(described["family"], "fam", "the child stays in its parent's family, so its trials count there")
        self.assertEqual(described["repair"], {"key": key, "parent": "parent"})
        self.deploy(forge.proposed[0]["files"])
        self.merton.follow()
        engineer.step()
        engineer.step()
        self.assertEqual(self.worklist.get(key).state, "observing")
        self.clock.advance(7200)
        engineer.step()
        self.assertEqual(self.worklist.get(key).state, "observing", "a corrected strategy is a fix only once it is born")
        self.ledger.append("agent.born", {"founder": "parent-fixed", "family": "fam", "parent": None}, agent="child")
        engineer.step()
        self.assertEqual(self.worklist.get(key).state, "verified")

    def test_a_recurrence_after_deployment_reopens_the_job(self):
        key = self.job()
        engineer = self.engineer(FakeFrontier(self.tool_answer(), self.tool_answer()), FakeGitHub())
        engineer.step()
        self.merton.follow()
        engineer.step()
        self.deploy(engineer.forge.proposed[0]["files"])
        engineer.step()
        self.assertEqual(self.worklist.get(key).state, "observing")
        self.clock.advance(60)
        self.worklist.report(key=key, kind="shared_defect", summary="again", agents=["c"], source="triage", severity="high",
                             evidence=[{"seq": 999, "at": "2099-01-01T00:00:00.000Z", "agent": "c", "excerpt": "still broken"}])
        engineer.step()
        job = self.worklist.get(key)
        self.assertEqual([h["state"] for h in job.history][-5:], ["revising", "reproducing", "patching", "testing", "testing"])
        self.assertIn("recurred after deployment", job.history[-5]["note"])
        self.assertEqual(job.attempt, 2, "the recurrence buys a second attempt, within the same bound")


class FollowAfterRefusal(Base):
    def test_a_refused_change_is_still_followed_and_its_merge_closes_its_requests_once_running(self):
        class Forge:
            statuses = {}

            def status(self, number):
                return self.statuses[number]

        forge = Forge()
        merton = Merton(None, forge, self.ledger, evidence=lambda role: {}, clock=self.clock)
        self.ledger.append("tool.request", {"name": "midpoint", "description": "a helper"}, agent="a", id="req-1")
        digest = __import__("hashlib").sha256(TOOL.encode()).hexdigest()
        self.ledger.append("merton.change", {"role": "toolsmith", "branch": "merton/toolsmith/mid", "number": 46, "status": "opened",
                                             "paths": ["league/tools/midpoint.py"], "file_digests": {"league/tools/midpoint.py": digest},
                                             "tool_answers": [{"request": "req-1", "outcome": "built"}]})
        forge.statuses[46] = {"state": "open", "merged": False, "head": "a" * 40, "checks": {"conclusion": "failure"}}
        self.assertEqual([r["status"] for r in merton.follow()], ["refused by CI"])
        forge.statuses[46] = {"state": "open", "merged": False, "head": "b" * 40, "checks": {"conclusion": "failure"}}
        self.assertEqual(merton.follow(), [], "a refused change is asked about on its own slower cadence")
        self.clock.advance(Merton.REFUSED_POLL_SECONDS + 1)
        self.assertEqual([r["head"] for r in merton.follow()], ["b" * 40], "a refusal of a new head is its own row")
        forge.statuses[46] = {"state": "closed", "merged": True, "head": "c" * 40, "checks": {"conclusion": "success"}}
        self.clock.advance(Merton.REFUSED_POLL_SECONDS + 1)
        with patch("league.merton.__file__", str(self.root / "league/merton.py")):
            self.assertEqual([r["status"] for r in merton.follow()], ["merged"])
            self.assertEqual(self.ledger.count(kinds="tool.fulfilled"), 0, "a merge is not a deployment")
            tool = self.root / "league/tools/midpoint.py"
            tool.parent.mkdir(parents=True)
            tool.write_text(TOOL)
            self.assertEqual([r["status"] for r in merton.follow()], ["deployed"])
        self.assertEqual(self.ledger.last("tool.fulfilled").payload["request"], "req-1")

    def test_a_stale_refusal_is_left_alone(self):
        class Forge:
            asked = 0

            def status(self, number):
                Forge.asked += 1
                return {"state": "open", "checks": {"conclusion": "failure"}}

        merton = Merton(None, Forge(), self.ledger, evidence=lambda role: {}, clock=self.clock)
        self.ledger.append("merton.change", {"number": 5, "status": "refused by CI"})
        self.clock.advance(15 * 86400)
        merton.follow()
        self.assertEqual(Forge.asked, 0)


class RegistryCollisions(Base):
    STALE = [{"name": "old-one", "family": "f", "file": "old_one.py", "why": "w"}]

    def proposal(self, name):
        stem = name.replace("-", "_")
        stale = self.STALE + [{"name": name, "family": "f", "file": f"league/strategies/{stem}.py", "why": "new"}]
        return parse_proposal("architect", {"files": [
            {"path": f"league/strategies/{stem}.py", "content": GOOD},
            {"path": "league/strategies/registry.json", "content": json.dumps(stale)}]}, Decimal(0))

    def test_two_concurrent_strategy_additions_both_survive(self):
        directory = self.repo / "league/strategies"
        (directory / "old_one.py").write_text(GOOD)
        (directory / "old_one.json").write_text(json.dumps({"name": "old-one", "family": "f", "why": "w"}))
        first, second = self.proposal("first-idea"), self.proposal("second-idea")
        for proposal in (first, second):
            self.assertNotIn("league/strategies/registry.json", [f["path"] for f in proposal.files])
            self.assertEqual(len(proposal.files), 2)
        for proposal in (first, second):  # merged one after the other, from the same stale copy
            for row in proposal.files:
                (self.repo / row["path"]).write_text(row["content"])
        self.assertEqual(sorted(r["name"] for r in strategies.registry(directory)), ["first-idea", "old-one", "second-idea"])
        self.assertEqual(strategies.problems(directory), [])
        self.assertEqual(ci.check_strategies(self.repo), [])

    def test_ci_still_refuses_an_undescribed_or_misdescribed_strategy(self):
        directory = self.repo / "league/strategies"
        (directory / "lonely.py").write_text(GOOD)
        self.assertIn("not described", " ".join(ci.check_strategies(self.repo)))
        (directory / "lonely.json").write_text(json.dumps({"name": "lonely", "family": "f", "why": "w", "file": "other.py"}))
        self.assertIn("describes lonely.py", " ".join(ci.check_strategies(self.repo)))
        (directory / "ghost.json").write_text(json.dumps({"name": "ghost", "family": "f", "why": "w"}))
        self.assertIn("does not exist", " ".join(ci.check_strategies(self.repo)))
        (directory / "Bad-Name.json").write_text("{}")
        self.assertIn("named after its strategy file", " ".join(strategies.problems(directory)))

    def test_a_merton_branch_may_not_write_the_retired_registry(self):
        with patch("league.ci.changed_paths", return_value=["league/strategies/registry.json"]), \
                patch("league.ci.check_strategies", return_value=[]), patch("league.ci.check_tools", return_value=[]), \
                patch("league.ci.check_game", return_value=[]), patch("league.ci.check_config", return_value=[]):
            problems = ci.check("origin/main", "merton/architect/x-1234abcd", tests=False)
        self.assertTrue(any("retired" in p for p in problems), problems)

    def test_refusals_become_github_annotations(self):
        import io

        out = io.StringIO()
        ci.annotate(["the test suite failed:\nFAIL: x (100%)"], out=out)
        self.assertEqual(out.getvalue(), "::error title=league.ci refused::the test suite failed:%0AFAIL: x (100%25)\n")


class TheInbox(Base):
    def test_an_operator_report_is_filed_once_and_a_bad_file_is_set_aside(self):
        inbox = self.root / "inbox"
        inbox.mkdir()
        (inbox / "seats.json").write_text(json.dumps({"key": "bug_report:seats", "summary": "agents lose their seats", "agents": ["a"]}))
        (inbox / "junk.json").write_text("[1, 2")
        engineer = Engineer(None, None, self.ledger, self.worklist, clock=self.clock, repo=self.repo, settings={"enabled": False}, inbox=inbox)
        self.assertEqual(engineer.step()["filed"], ["bug_report:seats"])
        self.assertEqual(self.worklist.get("bug_report:seats").sources, {"operator"})
        self.assertEqual(sorted(p.name for p in inbox.iterdir()), ["junk.json.refused", "junk.json.why", "seats.json.filed"])
        self.assertEqual(engineer.step()["filed"], [])
        self.assertEqual(self.ledger.count(kinds="repair.reported"), 1)


class TheDrill(Base):
    def test_the_drill_fails_once_is_revised_against_ci_s_text_and_is_verified(self):
        key = repair_drill.plant(self.root / "state", stamp="t1")
        self.assertEqual(self.ledger.count(kinds="repair.reported"), 0, "the script never writes the ledger itself")

        def ci_runs_the_drill_test(files):
            """The drill's own test, run the way CI would run it."""
            namespace = {}
            exec(next(f["content"] for f in files if f["path"] == "league/tools/repair_drill.py"), namespace)
            got = namespace["checksum"]([1, 2, 3])
            return None if got == 6 else f"the test suite failed:\nFAIL: test_checksum_adds_every_value (league.tests.test_tool_repair_drill)\nAssertionError: {got} != 6"

        forge = FakeGitHub(judge=ci_runs_the_drill_test)
        frontier = FakeFrontier()
        merton = Merton(frontier, forge, self.ledger, evidence=lambda role: {}, clock=self.clock)
        engineer = Engineer(frontier, forge, self.ledger, self.worklist, clock=self.clock, repo=self.repo,
                            settings={"synthetic_observe_minutes": 20, "min_seconds_between_calls": 1800},
                            inbox=self.root / "state" / "repairs-inbox")
        for _ in range(4):
            engineer.step()
            merton.follow()
        self.deploy(forge.proposed[-1]["files"])
        engineer.step()
        self.clock.advance(21 * 60)
        engineer.step()
        states = ["proposed"] + [h["state"] for h in self.worklist.get(key).history]
        self.assertEqual(states, ["proposed", "admitted", "reproducing", "patching", "testing", "testing", "revising", "reproducing",
                                  "patching", "testing", "testing", "canary", "observing", "verified"])
        self.assertEqual(frontier.asked, [], "a drill asks no model and spends nothing")
        self.assertEqual(len(forge.proposed), 2)
        self.assertTrue(all(p["title"].startswith("SYNTHETIC") for p in forge.proposed))
        self.assertIn("SYNTHETIC", forge.proposed[0]["body"])
        self.assertEqual(self.worklist.get(key).cost_usd, Decimal(0))
        shown = repair_drill.inspect(self.root / "l.sqlite", key)
        self.assertEqual(shown[-1]["state"], "verified")
        self.assertEqual(sorted(p.name for p in (self.root / "state" / "repairs-inbox").iterdir()), ["drill-t1.json.filed"])

    def test_a_drill_revision_is_written_only_if_ci_s_text_names_the_test(self):
        from league.engineer import drill_report

        key = drill_report(self.worklist, "t2")
        forge = FakeGitHub(judge=lambda files: "something unrelated broke")
        merton = Merton(None, forge, self.ledger, evidence=lambda role: {}, clock=self.clock)
        engineer = Engineer(None, forge, self.ledger, self.worklist, clock=self.clock, repo=self.repo, settings={})
        for _ in range(3):
            engineer.step()
            merton.follow()
        self.assertEqual(self.worklist.get(key).state, "rejected")
        self.assertEqual(len(forge.proposed), 1)


if __name__ == "__main__":
    unittest.main()


from league.tests.test_house import HouseCase  # noqa: E402


class WiredIntoTheHouse(HouseCase):
    class Worker:
        def __init__(self):
            self.steps = 0

        def due(self):
            return True

        def step(self):
            self.steps += 1

    def test_the_tick_runs_the_engineer_beside_it_and_a_pause_stops_it(self):
        worker = self.house.engineer = self.Worker()
        self.house.tick()
        self.house.wait()
        self.assertEqual(worker.steps, 1)
        (self.house.root / "PAUSE").write_text("rebuilding", encoding="utf-8")
        self.clock.advance(301)
        self.house.tick()
        self.house.wait()
        self.assertEqual(worker.steps, 1, "no paid or spending work while paused")

    def test_the_service_builds_it_on_the_house_s_own_ledger_and_frontier(self):
        from league.service import repair_engineer

        engineer = repair_engineer(self.house, frontier=object(), forge=object())
        self.assertIs(engineer.ledger, self.house.ledger)
        self.assertIs(engineer.sources.ledger, self.house.ledger)
        self.assertTrue(engineer.settings["enabled"])
        self.assertEqual(engineer.settings["max_attempts"], 3)
