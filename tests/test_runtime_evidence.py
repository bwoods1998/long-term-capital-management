import json
import tempfile
from pathlib import Path
import unittest
from portfolio_runtime.evidence import compact_facts, Constituents


class EvidenceTests(unittest.TestCase):
    def test_future_filings_are_excluded_and_periods_remain_distinct(self):
        values = [
            {
                "val": 100,
                "start": "2025-01-01",
                "end": "2025-12-31",
                "filed": "2026-02-01",
                "form": "10-K",
                "accn": "annual",
            },
            {
                "val": 40,
                "start": "2026-01-01",
                "end": "2026-06-30",
                "filed": "2026-07-20",
                "form": "10-Q",
                "accn": "ytd",
            },
            {
                "val": 22,
                "start": "2026-04-01",
                "end": "2026-06-30",
                "filed": "2026-07-20",
                "form": "10-Q",
                "accn": "quarter",
            },
            {
                "val": 1000,
                "start": "2026-01-01",
                "end": "2026-06-30",
                "filed": "2026-09-14",
                "form": "10-Q",
                "accn": "future-restatement",
            },
        ]
        raw = json.dumps(
            {
                "facts": {
                    "us-gaap": {
                        "NetCashProvidedByUsedInOperatingActivities": {
                            "units": {"USD": values}
                        }
                    }
                }
            }
        ).encode()
        result = compact_facts(
            raw,
            {"symbol": "TEST", "cik": "0000000001"},
            "2026-09-13T12:00:00Z",
            "2026-09-13",
        )
        observations = result["facts"]["operating_cash"][0]["observations"]
        self.assertEqual(
            {o["accn"] for o in observations}, {"annual", "ytd", "quarter"}
        )
        self.assertEqual(
            {o["period_kind"] for o in observations},
            {"annual", "quarter", "year_to_date_or_other"},
        )
        self.assertEqual(len(result["sha256"]), 64)

    def test_missing_metrics_are_not_filled_with_zero(self):
        result = compact_facts(
            b'{"facts":{}}',
            {"symbol": "TEST", "cik": "0000000001"},
            "2026-09-13T12:00:00Z",
            "2026-09-13",
        )
        self.assertEqual(result["facts"], {})

    def test_frozen_full_universe_carries_provenance_and_eligibility(self):
        p = Path(__file__).resolve().parents[1] / "data/sp500-evidence.json"
        data = json.loads(p.read_text())
        self.assertEqual(len(data["universe"]["companies"]), 503)
        self.assertEqual(
            {c["symbol"] for c in data["companies"]},
            {c["symbol"] for c in data["universe"]["companies"]},
        )
        for c in data["companies"]:
            self.assertTrue(
                c["source"].startswith("https://data.sec.gov/api/xbrl/companyfacts/CIK")
            )
            self.assertEqual(len(c["sha256"]), 64)
            self.assertLessEqual(c["research_price"]["as_of"], c["captured_at"])


if __name__ == "__main__":
    unittest.main()
