"""Task-aware routing: the table, the evidence rule, and the aggregated route.decision record."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from league.fast_research import ResearchRouter
from league.ledger import Ledger
from league.routing import TABLE, TaskRouter, best_profile

EVIDENCE = {"source": "fixture", "arms": {
    "pro_asap": {"samples": 10, "useful": 7, "cost_usd": "0.25", "median_seconds": 60},
    "pro_balanced": {"samples": 10, "useful": 7, "cost_usd": "0.20", "median_seconds": 90},
    "flash_asap": {"samples": 10, "useful": 6, "cost_usd": "0.02", "median_seconds": 40},
    "tiny": {"samples": 3, "useful": 3, "cost_usd": "0.001"},
}}


class Clock:
    def __init__(self):
        self.now = 1_790_000_000.0

    def __call__(self):
        return self.now


class Routing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.tmp.name) / "l.sqlite", clock=self.clock)
        self.agent = SimpleNamespace(id="a1")

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_the_table_sends_each_kind_of_work_to_its_kind_of_intelligence(self):
        self.assertEqual(TABLE["fills_and_refusals"].route, "code")
        self.assertEqual(TABLE["triage_classify"].route, "jev")
        self.assertEqual(TABLE["research_routine"].route, "research")
        self.assertEqual(TABLE["repair_patch"].route, "astra")
        router = TaskRouter(self.ledger, clock=self.clock, evidence={})
        self.assertEqual(router.route("never-heard-of-it").route, "code")  # nothing is bought by default

    def test_evidence_moves_a_profile_only_for_equal_usefulness_and_cheaper_useful_work(self):
        self.assertEqual(best_profile(EVIDENCE, "pro_asap", ["pro_balanced", "flash_asap", "tiny"])[0], "pro_balanced")
        # Flash is cheaper per token and per useful artifact, but made fewer: not economical.
        self.assertEqual(best_profile(EVIDENCE, "pro_asap", ["flash_asap"])[0], "pro_asap")
        # Too few samples never decides anything.
        self.assertEqual(best_profile(EVIDENCE, "pro_asap", ["tiny"])[0], "pro_asap")
        self.assertIn("fewer than", best_profile(EVIDENCE, "unmeasured", ["pro_balanced"])[1])
        # More samples are not more usefulness: 8 of 20 is worse than 7 of 10, however cheap.
        diluted = {"arms": {**EVIDENCE["arms"], "pro_balanced": {"samples": 20, "useful": 8, "cost_usd": "0.10"}}}
        self.assertEqual(best_profile(diluted, "pro_asap", ["pro_balanced"])[0], "pro_asap")
        # A latency bound keeps a slower window out.
        self.assertEqual(best_profile(EVIDENCE, "pro_asap", ["pro_balanced"], max_median_seconds=60)[0], "pro_asap")

    def test_sessions_are_routed_and_recorded_once_an_hour_with_counts_and_reasons(self):
        task = TaskRouter(self.ledger, clock=self.clock, evidence=EVIDENCE,
                          config={"sail_by_evidence": True, "candidates": ["pro_balanced"]})
        router = ResearchRouter(None, None, {"enabled": False}, task_router=task)
        for _ in range(3):
            self.assertEqual(router.settings_for(self.agent, {"profile": "pro_asap"})["profile"], "pro_balanced")
        self.assertEqual(list(self.ledger.iter(kinds="route.decision")), [])  # aggregated, not a row per call
        self.clock.now += 3600
        router.settings_for(self.agent, {"profile": "openai_luna"})
        rows = [e.payload for e in self.ledger.iter(kinds="route.decision")]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["task"], rows[0]["route"], rows[0]["model"], rows[0]["count"]),
                         ("research_routine", "research", "pro_balanced", 3))
        self.assertIn("useful", rows[0]["reason"])
        self.assertEqual(task.flush(), 1)
        luna = [e.payload for e in self.ledger.iter(kinds="route.decision")][-1]
        self.assertEqual((luna["model"], luna["count"], luna["partial"]), ("gpt-5.6-luna", 1, True))

    def test_without_the_evidence_switch_the_configured_profile_stands_and_is_still_recorded(self):
        task = TaskRouter(self.ledger, clock=self.clock, evidence=EVIDENCE, config={"candidates": ["pro_balanced"]})
        self.assertEqual(task.research_settings(self.agent, {"profile": "pro_asap"})["profile"], "pro_asap")
        task.flush()
        self.assertEqual([e.payload["reason"] for e in self.ledger.iter(kinds="route.decision")], ["configured Sail profile"])

    def test_a_ledger_failure_never_blocks_a_route(self):
        broken = SimpleNamespace(append=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk")))
        task = TaskRouter(broken, clock=self.clock, evidence=EVIDENCE)
        self.assertEqual(task.route("audit").model, "gpt-6-astra")
        self.assertEqual(task.flush(), 1)


from league.tests.test_researcher import ResearchCase  # noqa: E402


class ResearcherRoutes(ResearchCase):
    def test_a_paid_jev_classification_is_recorded_as_a_jev_route(self):
        researcher = self.researcher([[("classify", {"question": "Does this market resolve on a scheduled release?",
                                                      "source": "items", "items": ["CPI print", "rain"]})]])
        researcher.jev = lambda ident, body: ({"answers": {f"i{n}": {"noul": 0.8} for n in range(2)}}, "0.0001")
        researcher.routes = TaskRouter(self.ledger, clock=self.clock, evidence={})
        researcher.research(self.parent, {}, session="s-route")
        researcher.routes.flush()
        rows = [e.payload for e in self.ledger.iter(kinds="route.decision")]
        self.assertEqual([(r["task"], r["route"], r["model"], r["count"]) for r in rows], [("agent_classify", "jev", "jev-1.13.0", 1)])
