"""Public progress is a bounded projection, independent of model-generated prose."""

from pathlib import Path
import tempfile
import unittest

from portfolio_runtime.research import Research
from portfolio_runtime.runner import public_activity


class ActivityTests(unittest.TestCase):
    def test_private_content_and_unknown_enums_never_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            research = Research(
                Path(directory) / "research.sqlite",
                {
                    "companies": [{"symbol": "AAPL"}],
                    "overview": [],
                    "universe": {"id": "test"},
                },
            )
            for i in range(5):
                research.add(
                    "review-" + str(i),
                    0,
                    "company",
                    "AAPL",
                    "pro_flex",
                    "PRIVATE PROMPT",
                    "PRIVATE QUESTION",
                )
            research.add(
                "unreviewed", 0, "unexpected", None, "pro_flex", "PRIVATE", "PRIVATE"
            )
            research.attach("review-0", "pa-example")
            totals = {
                "completed": 0,
                "requests": 1,
                "known_cost_usd": "0.20",
                "committed_usd": "4.50",
            }
            result = public_activity(research, totals, "2026-09-13T16:00:00Z")
            self.assertEqual(len(result["tasks"]), 3)
            self.assertEqual(result["tasks"][0]["status"], "running")
            self.assertEqual(result["reserved_cost_usd"], "4.30")
            self.assertNotIn("PRIVATE", str(result))
            self.assertNotIn("pa-example", str(result))
            self.assertTrue(all(t["kind"] == "company" for t in result["tasks"]))
            self.assertEqual(
                public_activity(
                    research, totals, "2026-09-13T16:00:00Z", running=False
                )["tasks"],
                [],
            )


if __name__ == "__main__":
    unittest.main()
