"""Research quote relevance and durability, with no network or inference."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from portfolio_runtime.contracts import timestamp
from portfolio_runtime.evidence import save
from portfolio_runtime.market import chart_url
from portfolio_runtime.provider import canonical
from portfolio_runtime.research import Research, grade_result
from portfolio_runtime.service import Service, stamp
from test_runtime_runner import answer, evidence


AT = "2026-09-14T04:00:00Z"


def quote(symbol, **changes):
    return {"schema_version": 1, "symbol": symbol, "currency": "USD", "price": "100",
            "price_kind": "daily_close", "as_of": "2026-09-11T20:00:00Z",
            "captured_at": AT, "source": chart_url(symbol), "source_sha256": "a"*64,
            "provider": "Yahoo Finance", "adjusted": False, **changes}


class PriceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.at = timestamp(AT).timestamp()
        self.calls, self.failures, self.responses = [], set(), {}
        self.config = {"schema_version": 1, "kind": "weekday_service",
                       "service_id": "quote-test", "state_dir": str(self.root / "state"),
                       "week_starts_at": AT, "week_ends_at": "2026-09-19T04:00:00Z",
                       "weekly_inference_budget_usd": "100", "session_inference_budget_usd": "10",
                       "session_seconds": 3600, "wave_size": 12,
                       "account_created_at": "2026-09-13T15:00:00Z", "key_fingerprint": "a"*64,
                       "initial_evidence_path": str(self.root / "initial.json"),
                       "admission_path": str(self.root / "admission.json"), "injected_auth": True}
        save(self.root / "initial.json", evidence())
        owner = self

        class Market:
            def __init__(self, directory):
                pass
            def snapshot_price(self, symbol):
                owner.calls.append(symbol)
                if symbol in owner.failures:
                    raise OSError("source unavailable")
                return owner.responses.get(symbol, quote(symbol, captured_at=stamp(owner.at)))

        self.market = Market
        self.service = self.make_service()
        self.paper = patch("portfolio_runtime.service.PortfolioLedger")
        self.mock_ledger = self.paper.start()
        self.mock_ledger.return_value.__enter__.return_value.public_state.return_value = {
            "holdings": [], "pending_decisions": []}

    def tearDown(self):
        self.paper.stop()
        self.tmp.cleanup()

    def make_service(self):
        return Service(self.config, clock=lambda: self.at, market_factory=self.market)

    def expanded(self, count=130):
        data = evidence()
        template = data["companies"][0]
        symbols = ["Z"+chr(65+i//26)+chr(65+i%26) for i in range(count)]
        data["companies"] = [{**deepcopy(template), "symbol": symbol, "cik": str(i+1).zfill(10)}
                             for i, symbol in enumerate(symbols)]
        return data

    def test_next_research_and_allocation_names_precede_rotating_sample(self):
        data = self.expanded()
        ordered = sorted((c["symbol"] for c in data["companies"]), key=lambda s: hashlib.sha256(s.encode()).hexdigest())
        selected, candidates = ordered[-12:], ordered[60:96]
        overview = canonical(data["overview"])
        with patch.object(self.service, "_research_price_priority", return_value=(selected, candidates)):
            result = self.service._enrich_prices(data)
        self.assertTrue(set(selected+candidates) <= set(self.calls))
        self.assertLessEqual(len(self.calls), 64)
        self.assertEqual(len(self.calls), len(set(self.calls)))
        self.assertEqual(canonical(result["overview"]), overview)
        health = json.loads((self.service.root / "research-price-health.json").read_text())
        self.assertEqual(health["next_wave_symbols"], health["next_wave_with_prices"])

    def test_every_pending_name_is_refreshed_even_above_thirty_two(self):
        data = self.expanded()
        held = [c["symbol"] for c in data["companies"][:40]]
        pending = [c["symbol"] for c in data["companies"][40:80]]
        self.mock_ledger.return_value.__enter__.return_value.public_state.return_value = {
            "holdings": [{"symbol": s} for s in held],
            "pending_decisions": [{"targets": [{"symbol": s} for s in pending]}]}
        with patch.object(self.service, "_research_price_priority", return_value=([], [])):
            self.service._enrich_prices(data)
        self.assertTrue(set(held+pending) <= set(self.calls))
        self.assertLessEqual(len(self.calls), len(held+pending)+64)

    def test_restart_retains_exact_quote_after_failure_without_restamping(self):
        before = self.service._enrich_prices(evidence())
        old_quote = deepcopy(before["companies"][0]["research_price"])
        self.at += 3600
        self.failures.add("AAPL")
        restarted = self.make_service()
        after = restarted._enrich_prices(evidence())
        self.assertEqual(after["companies"][0]["research_price"], old_quote)
        self.assertEqual(after["companies"][1]["research_price"]["captured_at"], stamp(self.at))
        self.assertEqual(json.loads((restarted.root / "research-prices.json").read_text())["prices"]["AAPL"]["quote"], old_quote)

    def test_existing_epoch_quotes_seed_cache_without_modifying_frozen_packet(self):
        old = evidence()
        old["companies"][0]["research_price"] = quote("AAPL")
        path = self.service.root / "epochs" / "2026-09-13-00" / "evidence.json"
        save(path, old)
        original = path.read_bytes()
        self.failures.add("AAPL")
        result = self.service._enrich_prices(evidence())
        self.assertEqual(result["companies"][0]["research_price"], quote("AAPL"))
        self.assertEqual(path.read_bytes(), original)

    def test_new_capture_of_older_observation_cannot_replace_newer_quote(self):
        self.service._enrich_prices(evidence())
        self.at += 3600
        self.responses["AAPL"] = quote("AAPL", as_of="2026-09-10T20:00:00Z", captured_at=stamp(self.at))
        result = self.service._enrich_prices(evidence())
        self.assertEqual(result["companies"][0]["research_price"], quote("AAPL"))

    def test_invalid_future_expired_wrong_identity_prices_stay_missing(self):
        invalid = [quote("AAPL", captured_at="2026-09-15T04:00:00Z"),
                   quote("AAPL", as_of="2026-09-15T04:00:00Z"),
                   quote("AAPL", as_of="2026-09-01T20:00:00Z"),
                   quote("AAPL", source="https://example.com/price"),
                   quote("AAPL", price="NaN"), quote("MSFT"),
                   quote("AAPL", source_sha256="not-a-hash")]
        for wrong in invalid:
            with self.subTest(quote=wrong):
                self.responses["AAPL"] = wrong
                data = evidence()
                data["companies"][0]["research_price"] = wrong
                result = self.service._enrich_prices(data)
                self.assertNotIn("research_price", result["companies"][0])

    def test_ticker_reused_for_different_cik_cannot_inherit_quote(self):
        self.service._enrich_prices(evidence())
        self.failures.add("AAPL")
        changed = evidence()
        changed["companies"][0]["cik"] = "9999999999"
        result = self.service._enrich_prices(changed)
        self.assertNotIn("research_price", result["companies"][0])

    def test_real_preview_uses_retained_selector_and_keeps_source_journal_unchanged(self):
        previous = Research(self.service.root / "epochs" / "2026-09-13-01" / "research.sqlite", evidence())
        previous.add("company-AAPL", 0, "company", "AAPL", "pro_flex", "context", canonical({
            "question": "Assess the business economics, cash generation, balance-sheet resilience and missing valuation evidence. Identify what would change an investment decision.",
            "evidence": evidence()["companies"][0]}))
        result = answer()
        with previous.connect() as db:
            db.execute("UPDATE tasks SET status='complete',result=?,grade=? WHERE id='company-AAPL'",
                       (canonical(result), canonical(grade_result(result, previous.companies))))
            original = tuple(db.execute("SELECT * FROM tasks").fetchone())
        selected, candidates = self.service._research_price_priority(evidence())
        self.assertEqual(selected[0], "MSFT")
        self.assertEqual(candidates, ["AAPL"])
        with previous.connect() as db:
            self.assertEqual(tuple(db.execute("SELECT * FROM tasks").fetchone()), original)
            self.assertEqual(db.execute("SELECT count(*) FROM tasks").fetchone()[0], 1)
        self.assertEqual(list(self.service.root.glob("*preview*")), [])


if __name__ == "__main__":
    unittest.main()
