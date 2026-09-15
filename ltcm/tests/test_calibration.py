"""The forecast record: stated probabilities, resolutions from three sources, Brier and deciles."""

import copy
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.calibration import (
    CalibrationError,
    CalibrationLedger,
    Resolution,
    bin_label,
    bin_of,
    normalize_probability,
    venue_of_instrument_key,
)
from ltcm.events import EventLog
from ltcm.manifest import DeskManifest
from ltcm.tests.test_manifest import SAMPLE

AT = "2026-09-15T18:30:00.000Z"
LATER = "2026-09-16T19:00:00.000Z"


def manifest(desk_id, family="kalshi", generation=1, parent=None):
    data = copy.deepcopy(SAMPLE)
    data.update(
        {
            "id": desk_id,
            "family": family,
            "generation": generation,
            "parent_id": parent,
            "playbook": f"playbooks/{desk_id}.md",
        }
    )
    return DeskManifest.from_dict(data)


class CalibrationCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = EventLog(Path(self.tmp.name) / "events.sqlite")
        self.manifests = {
            "mullins": manifest("mullins"),
            "mullins-2": manifest("mullins-2", generation=2, parent="mullins"),
            "hilibrand": manifest("hilibrand", family="crypto"),
        }
        self.ledger = CalibrationLedger(self.log, self.manifests)

    def tearDown(self):
        self.log.close()
        self.tmp.cleanup()

    def forecast(self, desk, market, p, at=AT, **extra):
        return self.ledger.record_forecast(
            desk_id=desk,
            stream=f"desk:{desk}",
            session_id=f"{desk}:20260915-1830:cadence:13:30",
            market=market,
            venue="kalshi",
            probability=p,
            reasoning="Base rate plus the dated evidence.",
            at=at,
            **extra,
        )

    def outcome(self, desk, market, result, at=LATER):
        self.log.append(
            f"desk:{desk}",
            "desk.outcome",
            {
                "instrument": f"event:{market}:kalshi:yes:{market}",
                "market_id": market,
                "result": result,
                "entry_price": "0.40",
                "exit_price": "1" if result == "yes" else "0",
                "quantity": "10",
                "pnl": "6.00",
                "held_for_hours": 24,
                "rationale_excerpt": "",
            },
            at=at,
        )


class RecordingTests(CalibrationCase):
    def test_a_forecast_is_a_public_event_with_the_contract_shape(self):
        event = self.forecast("mullins", "kxfed-26sep-h25", "0.93", market_price="0.89", side="yes",
                              resolves_at="2026-09-16T18:00:00Z")
        self.assertEqual(event.kind, "desk.forecast")
        self.assertTrue(event.public)
        self.assertEqual(event.id, "forecast:mullins:KXFED-26SEP-H25:2026-09-15T18:30:00.000Z")
        self.assertEqual(
            sorted(event.payload),
            ["market", "market_price", "probability", "reasoning", "resolves_at", "session_id", "side", "venue"],
        )
        self.assertEqual(event.payload["market"], "KXFED-26SEP-H25")
        self.assertEqual(event.payload["probability"], "0.9300")
        self.assertEqual(event.payload["market_price"], "0.8900")
        self.assertEqual(event.payload["resolves_at"], "2026-09-16T18:00:00.000Z")

    def test_percentages_are_probabilities_and_nonsense_is_refused(self):
        self.assertEqual(normalize_probability("62%"), Decimal("0.6200"))
        self.assertEqual(normalize_probability(1), Decimal("1.0000"))
        for bad in ("1.4", "-0.1", "soon", None, True):
            with self.subTest(bad=bad):
                with self.assertRaises(CalibrationError):
                    normalize_probability(bad)
        with self.assertRaises(CalibrationError):
            self.forecast("mullins", "X", "0.5", side="maybe")
        with self.assertRaises(CalibrationError):
            self.forecast("mullins", "", "0.5")

    def test_the_same_moment_and_market_is_one_forecast(self):
        first = self.forecast("mullins", "M1", "0.6")
        second = self.forecast("mullins", "M1", "0.6")
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(self.ledger.forecasts()), 1)


class ScoringTests(CalibrationCase):
    def test_a_desk_outcome_resolves_the_market_and_scores_every_forecast_on_it(self):
        self.forecast("mullins", "M1", "0.9")
        self.forecast("mullins-2", "M1", "0.4", at="2026-09-15T18:31:00.000Z")
        self.outcome("mullins", "M1", "yes")
        scored = self.ledger.scored("2026-09-17T00:00:00.000Z")
        self.assertEqual([(s.forecast.desk_id, str(s.brier)) for s in scored],
                         [("mullins", "0.0100"), ("mullins-2", "0.3600")])
        self.assertEqual(scored[0].resolution.source, "outcome")

    def test_a_settlement_fill_resolves_too_and_a_no_result_scores_against_the_yes_probability(self):
        self.forecast("mullins", "M2", "0.8")
        self.log.append(
            "broker:kalshi",
            "broker.fill",
            {
                "fill_id": "settlement:M2:2026-09-16T12:00:00.000Z",
                "order_id": "",
                "desk_id": "mullins",
                "instrument": {"asset_class": "event", "symbol": "M2", "venue": "kalshi", "market_id": "M2", "right": "yes"},
                "side": "sell",
                "quantity": "10",
                "price": "0",
                "fee": "0",
                "at": "2026-09-16T12:00:00.000Z",
                "venue": "kalshi",
                "settlement": True,
                "result": "no",
            },
            at="2026-09-16T12:00:00.000Z",
        )
        scored = self.ledger.scored("2026-09-17T00:00:00.000Z")
        self.assertEqual(len(scored), 1)
        self.assertEqual(scored[0].resolution.result, "no")
        self.assertEqual(scored[0].brier, Decimal("0.6400"))

    def test_a_forecast_made_after_the_resolution_is_not_a_forecast(self):
        self.outcome("mullins", "M3", "yes", at="2026-09-15T10:00:00.000Z")
        self.forecast("mullins", "M3", "0.99", at="2026-09-15T12:00:00.000Z")
        self.assertEqual(self.ledger.scored("2026-09-16T00:00:00.000Z"), [])

    def test_the_venue_is_asked_about_due_markets_once_and_the_answer_is_kept(self):
        self.forecast("mullins", "SOON", "0.7", resolves_at="2026-09-16T00:00:00Z")
        self.forecast("mullins", "LATER", "0.7", resolves_at="2026-09-20T00:00:00Z")
        self.forecast("mullins", "UNDATED", "0.7")
        asked = []

        def resolver(venue, market):
            asked.append((venue, market))
            if market == "SOON":
                return {"result": "yes", "settled_at": "2026-09-16T00:05:00Z", "source": "kalshi"}
            return None

        # Nothing is due an hour after the forecasts were made.
        self.assertEqual(self.ledger.resolve("2026-09-15T19:30:00.000Z", resolver), [])
        self.assertEqual(asked, [])
        # A day later the dated one and the undated one are due; the far one is not.
        recorded = self.ledger.resolve("2026-09-16T19:00:00.000Z", resolver)
        self.assertEqual(sorted(asked), [("kalshi", "SOON"), ("kalshi", "UNDATED")])
        self.assertEqual([(r.market, r.result, r.source) for r in recorded], [("SOON", "yes", "kalshi")])
        private = self.log.read(kind="lab.resolution")
        self.assertEqual(len(private), 1)
        self.assertFalse(private[0].public)
        self.assertEqual(private[0].payload["settled_at"], "2026-09-16T00:05:00.000Z")
        # Asked again, the resolved market is not asked about twice.
        asked.clear()
        self.ledger.resolve("2026-09-17T19:00:00.000Z", resolver)
        self.assertEqual(asked, [("kalshi", "UNDATED")])
        self.assertEqual(len(self.ledger.scored("2026-09-17T19:00:00.000Z")), 1)

    def test_a_resolver_that_breaks_on_one_market_still_answers_the_rest(self):
        self.forecast("mullins", "A", "0.5", resolves_at="2026-09-16T00:00:00Z")
        self.forecast("mullins", "B", "0.5", resolves_at="2026-09-16T00:00:00Z")

        def resolver(venue, market):
            if market == "A":
                raise RuntimeError("venue down")
            return Resolution(market, venue, "no", "2026-09-16T01:00:00.000Z", "kalshi")

        recorded = self.ledger.resolve("2026-09-16T19:00:00.000Z", resolver)
        self.assertEqual([r.market for r in recorded], ["B"])


class SummaryTests(CalibrationCase):
    def seed(self):
        # Two founders' worth of calls: mullins is sharp, its child is not.
        calls = [
            ("mullins", "M1", "0.9", "yes"), ("mullins", "M2", "0.85", "yes"),
            ("mullins", "M3", "0.2", "no"), ("mullins", "M4", "0.15", "no"),
            ("mullins-2", "M1", "0.4", "yes"), ("mullins-2", "M3", "0.7", "no"),
            ("hilibrand", "M2", "0.5", "yes"),
        ]
        markets = {}
        for desk, market, p, result in calls:
            self.forecast(desk, market, p)
            markets[market] = result
        for market, result in markets.items():
            self.outcome("mullins", market, result)

    def test_brier_and_deciles_by_desk_family_generation_and_floor(self):
        self.seed()
        at = "2026-09-17T00:00:00.000Z"
        desk = self.ledger.summary("desk", desk_id="mullins", at=at)
        # (0.1^2 + 0.15^2 + 0.2^2 + 0.15^2) / 4 = (0.01 + 0.0225 + 0.04 + 0.0225) / 4
        self.assertEqual(desk["n"], 4)
        self.assertEqual(desk["brier"], "0.0238")
        self.assertEqual([r["bin"] for r in desk["reliability"]], ["0.1-0.2", "0.2-0.3", "0.8-0.9", "0.9-1.0"])
        self.assertEqual(desk["reliability"][0], {"bin": "0.1-0.2", "forecast_mean": "0.1500", "outcome_rate": "0.0000", "n": 1})
        child = self.ledger.summary("desk", desk_id="mullins-2", at=at)
        self.assertEqual(child["brier"], "0.4250")  # (0.36 + 0.49) / 2
        self.assertEqual(child["worst_bin"]["bin"], "0.7-0.8")
        family = self.ledger.summary("family", family="kalshi", at=at)
        self.assertEqual(family["n"], 6)
        founders = self.ledger.summary("generation", family="kalshi", generation=1, at=at)
        self.assertEqual(founders["n"], 4)
        second = self.ledger.summary("generation", family="kalshi", generation=2, at=at)
        self.assertEqual(second["n"], 2)
        floor = self.ledger.summary("floor", at=at)
        self.assertEqual(floor["n"], 7)
        self.assertEqual(floor["scope"], "floor")

    def test_summaries_cover_every_scope_with_evidence_and_nothing_else(self):
        self.seed()
        rows = self.ledger.summaries("2026-09-17T00:00:00.000Z")
        keys = [(r["scope"], r["desk_id"] or r["family"], r["generation"]) for r in rows]
        self.assertEqual(
            keys,
            [
                ("desk", "hilibrand", None), ("desk", "mullins", None), ("desk", "mullins-2", None),
                ("family", "crypto", None), ("generation", "crypto", 1),
                ("family", "kalshi", None), ("generation", "kalshi", 1), ("generation", "kalshi", 2),
                ("floor", None, None),
            ],
        )
        self.assertEqual(self.ledger.summaries(AT), [], "nothing resolved yet, nothing to say")

    def test_the_daily_publication_is_one_event_per_scope_and_idempotent(self):
        self.seed()
        first = self.ledger.publish_daily("2026-09-18T00:10:00.000Z")
        self.assertEqual(len(first), 9)
        self.assertEqual(first[0].kind, "lab.calibration")
        self.assertEqual(first[0].at, "2026-09-17T23:59:59.999Z")
        ids = {e.id for e in first}
        self.assertIn("calibration:2026-09-17:desk:mullins", ids)
        self.assertIn("calibration:2026-09-17:generation:kalshi:g2", ids)
        self.assertIn("calibration:2026-09-17:floor:floor", ids)
        payload = [e for e in first if e.id.endswith("desk:mullins")][0].payload
        self.assertEqual(
            sorted(payload), ["as_of", "brier", "desk_id", "family", "generation", "n", "reliability", "scope", "since"]
        )
        again = self.ledger.publish_daily("2026-09-18T12:00:00.000Z")
        self.assertEqual({e.id for e in again}, ids)
        self.assertEqual(len(self.log.read(kind="lab.calibration")), 9)

    def test_the_brief_reads_like_a_sentence_and_is_silent_without_evidence(self):
        self.assertEqual(self.ledger.brief("mullins", AT), "")
        self.forecast("mullins", "OPEN", "0.6")
        self.assertEqual(self.ledger.brief("mullins", LATER), "Calibration: 1 forecast recorded, none resolved yet.")
        self.seed()
        brief = self.ledger.brief("mullins-2", "2026-09-17T00:00:00.000Z")
        self.assertIn("2 forecasts scored, Brier 0.4250", brief)
        self.assertIn("Worst decile 0.7-0.8: you said 0.7000 on average and 0.0000 resolved yes (n=1).", brief)


class HelperTests(unittest.TestCase):
    def test_bins_are_deciles_with_certainty_in_the_top_one(self):
        self.assertEqual(bin_of(Decimal("0")), 0)
        self.assertEqual(bin_of(Decimal("0.09")), 0)
        self.assertEqual(bin_of(Decimal("0.5")), 5)
        self.assertEqual(bin_of(Decimal("1")), 9)
        self.assertEqual(bin_label(9), "0.9-1.0")

    def test_the_venue_is_read_from_an_instrument_key(self):
        self.assertEqual(venue_of_instrument_key("event:CPI:kalshi:yes:CPI-26SEP"), "kalshi")
        self.assertEqual(venue_of_instrument_key("nonsense"), "kalshi")


if __name__ == "__main__":
    unittest.main()
