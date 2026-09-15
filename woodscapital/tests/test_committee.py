import copy
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from woodscapital.broker import Instrument
from woodscapital.committee import Committee, capital_mode, iso_week, promoted_desks, retired_desks
from woodscapital.events import EventLog
from woodscapital.ledger import DeskLedger
from woodscapital.manifest import DeskManifest
from woodscapital.tests.test_manifest import SAMPLE

AAPL = Instrument("equity", "AAPL", "paper")
ALPACA_AAPL = Instrument("equity", "AAPL", "alpaca")


def manifest(desk_id="earnings-01", **overrides):
    data = copy.deepcopy(SAMPLE)
    data["id"] = desk_id
    data.update(overrides)
    return DeskManifest.from_dict(data)


def live_manifest(desk_id, capital="1000"):
    return manifest(
        desk_id,
        venues=["alpaca"],
        capital={"mode": "live", "usd": capital},
        playbook=f"playbooks/{desk_id}.md",
    )


class FakeProvider:
    def __init__(self, text="The week in one paragraph."):
        self.text = text
        self.calls = []

    def respond(self, profile, items, **kwargs):
        self.calls.append({"profile": profile, "items": items, **kwargs})
        return SimpleNamespace(output_text=self.text, cost_usd=Decimal("0.02"))

    def spent_today(self, desk_id=None):
        return Decimal("0")


class CommitteeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = EventLog(Path(self.tmp.name) / "events.sqlite")
        self.provider = FakeProvider()
        self.ledgers = {}
        self.manifests = {}

    def tearDown(self):
        self.log.close()
        self.tmp.cleanup()

    def add(self, desk_manifest):
        self.manifests[desk_manifest.id] = desk_manifest
        self.ledgers[desk_manifest.id] = DeskLedger(self.log, desk_manifest.id)
        return desk_manifest

    def committee(self, **config):
        return Committee(
            self.log, self.manifests, self.ledgers, self.provider, config=config
        )

    def allocate_event(self, allocations, at):
        self.log.append(
            "committee",
            "committee.allocation",
            {"allocations": {k: str(v) for k, v in allocations.items()}, "reasons": {}},
            at=at,
        )

    def fill(self, desk, side, quantity, price, at, *, instrument=AAPL, fee="0"):
        seq = self.log.latest_seq() + 1
        self.log.append(
            "broker:paper",
            "broker.fill",
            {
                "fill_id": f"f{seq}",
                "order_id": f"o{seq}",
                "desk_id": desk,
                "instrument": instrument.to_dict(),
                "side": side,
                "quantity": str(quantity),
                "price": str(price),
                "fee": str(fee),
                "at": at,
            },
            at=at,
        )

    def mark(self, desk, price, at, *, instrument=AAPL, equity=None, cash=None):
        ledger = self.ledgers[desk]
        ledger.mark({instrument.key: Decimal(str(price))}, at)


class GateTests(CommitteeCase):
    def test_a_new_desk_fails_every_gate_it_has_no_evidence_for(self):
        self.add(manifest())
        report = self.committee().gates("earnings-01", "2026-09-14T20:00:00.000Z")
        self.assertEqual(report["gate"], "A")
        self.assertFalse(report["passed"])
        self.assertEqual(
            report["failed"], ["cost_adjusted_return", "days_live", "decisions"]
        )
        self.assertEqual(report["evidence"]["mode"], "paper")
        self.assertEqual(report["evidence"]["decisions"], 0)

    def test_gate_a_passes_on_days_decisions_and_cost_adjusted_return(self):
        self.add(manifest())
        self.allocate_event({"earnings-01": "1000"}, "2026-09-01T13:00:00.000Z")
        for n in range(10):
            day = f"2026-09-{2 + n:02d}"
            self.fill("earnings-01", "buy", "1", "100", f"{day}T14:00:00.000Z")
            self.fill("earnings-01", "sell", "1", "101", f"{day}T15:00:00.000Z")
        self.mark("earnings-01", "101", "2026-09-21T20:00:00.000Z")
        report = self.committee().gates("earnings-01", "2026-09-21T20:00:00.000Z")
        self.assertTrue(report["passed"], report["failed"])
        self.assertEqual(report["evidence"]["decisions"], 20)
        self.assertEqual(report["evidence"]["days_live"], 20)
        self.assertEqual(report["evidence"]["return_pct"], "1.0000")
        self.assertEqual(report["evidence"]["cost_adjusted_excess_pct"], "1.0000")
        self.assertTrue(report["evidence"]["reconciliation_clean"])

    def test_inference_cost_and_a_benchmark_are_subtracted(self):
        self.add(manifest())
        self.allocate_event({"earnings-01": "1000"}, "2026-09-01T13:00:00.000Z")
        for n in range(10):
            day = f"2026-09-{2 + n:02d}"
            self.fill("earnings-01", "buy", "1", "100", f"{day}T14:00:00.000Z")
            self.fill("earnings-01", "sell", "1", "101", f"{day}T15:00:00.000Z")
        self.mark("earnings-01", "101", "2026-09-21T20:00:00.000Z")
        self.log.append(
            "ops",
            "ops.budget",
            {"scope": "floor", "spent_usd": "1", "cap_usd": "15"},
            at="2026-09-10T00:00:00.000Z",
        )
        self.log.append(
            "ops",
            "provider.request",
            {"request_id": "r1", "desk_id": "earnings-01", "profile": "pro_flex",
             "cost_usd": "6.00", "usage": {}},
            at="2026-09-10T00:00:00.000Z",
        )
        committee = self.committee(benchmark=lambda start, end: Decimal("0.2"))
        report = committee.gates("earnings-01", "2026-09-21T20:00:00.000Z")
        self.assertEqual(report["evidence"]["cost_usd"], "6.00")
        self.assertEqual(report["evidence"]["cost_pct"], "0.6000")
        self.assertEqual(report["evidence"]["benchmark_pct"], "0.2")
        self.assertEqual(report["evidence"]["cost_adjusted_excess_pct"], "0.2000")
        self.assertTrue(report["passed"], report["failed"])
        # The same desk with a more expensive brain no longer clears the gate.
        self.log.append(
            "ops",
            "provider.request",
            {"request_id": "r2", "desk_id": "earnings-01", "profile": "pro_flex",
             "cost_usd": "3.00", "usage": {}},
            at="2026-09-11T00:00:00.000Z",
        )
        harder = self.committee(benchmark=lambda start, end: Decimal("0.2")).gates(
            "earnings-01", "2026-09-21T20:00:00.000Z"
        )
        self.assertFalse(harder["passed"])
        self.assertEqual(harder["failed"], ["cost_adjusted_return"])

    def test_breakers_and_dirty_reconciliation_fail_the_gate(self):
        self.add(manifest())
        self.allocate_event({"earnings-01": "1000"}, "2026-09-01T13:00:00.000Z")
        self.log.append(
            "risk",
            "risk.breaker",
            {"scope": "desk:earnings-01", "rule": "daily_loss", "detail": "9%",
             "action": "halt_new_orders"},
            at="2026-09-05T20:00:00.000Z",
        )
        self.log.append(
            "broker:paper",
            "broker.reconciled",
            {"venue": "paper", "matches": 0,
             "mismatches": [{"instrument": AAPL.key, "ledger": "1", "venue": "2"}]},
            at="2026-09-06T20:00:00.000Z",
        )
        report = self.committee().gates("earnings-01", "2026-09-21T20:00:00.000Z")
        self.assertIn("breakers", report["failed"])
        self.assertIn("reconciliation", report["failed"])
        self.assertEqual(report["evidence"]["breakers"], 1)


class AllocationTests(CommitteeCase):
    def test_paper_sleeves_sit_at_manifest_capital_and_publish_gates(self):
        self.add(manifest("earnings-01"))
        self.add(manifest("kalshi-01", family="kalshi", playbook="playbooks/kalshi-01.md"))
        targets = self.committee().allocate("2026-09-14T22:00:00.000Z")
        self.assertEqual(
            targets, {"earnings-01": Decimal("1000.00"), "kalshi-01": Decimal("1000.00")}
        )
        event = self.log.last("committee", "committee.allocation")
        self.assertEqual(event.payload["allocations"], {"earnings-01": "1000.00", "kalshi-01": "1000.00"})
        self.assertTrue(event.public)
        gates = self.log.read(kind="committee.gate")
        self.assertEqual([g.payload["desk_id"] for g in gates], ["earnings-01", "kalshi-01"])
        # The ledgers fold the allocation as a deposit.
        self.assertEqual(
            self.ledgers["earnings-01"].state("2026-09-14T22:00:00.000Z").cash, Decimal("1000.00")
        )

    def test_an_unchanged_allocation_is_not_republished(self):
        self.add(manifest())
        committee = self.committee()
        committee.allocate("2026-09-14T22:00:00.000Z")
        count = len(self.log.read(kind="committee.allocation"))
        committee.allocate("2026-09-15T22:00:00.000Z")
        self.assertEqual(len(self.log.read(kind="committee.allocation")), count)

    def test_live_sleeves_resize_by_score_within_half_and_double(self):
        self.add(live_manifest("earnings-01"))
        self.add(live_manifest("earnings-02"))
        self.allocate_event(
            {"earnings-01": "1000", "earnings-02": "1000"}, "2026-09-01T13:00:00.000Z"
        )
        for desk, price in (("earnings-01", "120"), ("earnings-02", "105")):
            self.fill(desk, "buy", "10", "100", "2026-09-01T14:00:00.000Z", instrument=ALPACA_AAPL)
            self.ledgers[desk].mark(
                {ALPACA_AAPL.key: Decimal(price)}, "2026-09-09T20:00:00.000Z"
            )
        committee = self.committee()
        self.assertEqual(committee.score("earnings-01", "2026-09-09T20:00:00.000Z"), Decimal("20"))
        self.assertEqual(committee.score("earnings-02", "2026-09-09T20:00:00.000Z"), Decimal("5"))
        targets = committee.allocate("2026-09-09T20:00:00.000Z")
        self.assertEqual(targets["earnings-01"], Decimal("2000.00"))
        self.assertEqual(targets["earnings-02"], Decimal("500.00"))
        reasons = self.log.last("committee", "committee.allocation").payload["reasons"]
        self.assertIn("2.00x manifest capital", reasons["earnings-01"])

    def test_live_sleeves_hold_between_weekly_resizes(self):
        self.add(live_manifest("earnings-01"))
        self.add(manifest("kalshi-01", family="kalshi", playbook="playbooks/kalshi-01.md"))
        self.allocate_event({"earnings-01": "1750"}, "2026-09-08T13:00:00.000Z")
        targets = self.committee().allocate("2026-09-10T22:00:00.000Z")
        self.assertEqual(targets["earnings-01"], Decimal("1750.00"))
        self.assertEqual(targets["kalshi-01"], Decimal("1000.00"))
        self.assertIn(
            "held between weekly resizes",
            self.log.last("committee", "committee.allocation").payload["reasons"]["earnings-01"],
        )

    def test_total_never_exceeds_the_floor_capital(self):
        self.add(live_manifest("earnings-01"))
        self.add(live_manifest("earnings-02"))
        self.allocate_event(
            {"earnings-01": "1000", "earnings-02": "1000"}, "2026-09-01T13:00:00.000Z"
        )
        for desk, price in (("earnings-01", "120"), ("earnings-02", "105")):
            self.fill(desk, "buy", "10", "100", "2026-09-01T14:00:00.000Z", instrument=ALPACA_AAPL)
            self.ledgers[desk].mark({ALPACA_AAPL.key: Decimal(price)}, "2026-09-09T20:00:00.000Z")
        targets = self.committee(floor_capital_usd="1000").allocate("2026-09-09T20:00:00.000Z")
        self.assertEqual(targets["earnings-01"], Decimal("800.00"))
        self.assertEqual(targets["earnings-02"], Decimal("200.00"))
        self.assertLessEqual(sum(targets.values()), Decimal("1000"))

    def test_a_bankrupt_desk_goes_to_zero(self):
        self.add(manifest())
        self.allocate_event({"earnings-01": "1000"}, "2026-09-01T13:00:00.000Z")
        self.fill("earnings-01", "buy", "10", "100", "2026-09-01T14:00:00.000Z")
        self.ledgers["earnings-01"].mark({}, "2026-09-09T20:00:00.000Z")
        self.log.append(
            "ledger:earnings-01",
            "ledger.mark",
            {
                "equity": "0",
                "cash": "0",
                "positions": [{"instrument": AAPL.to_dict(), "mark": "0"}],
                "daily_pnl": "-1000",
                "as_of": "2026-09-10T20:00:00.000Z",
            },
            at="2026-09-10T20:00:00.000Z",
        )
        targets = self.committee().allocate("2026-09-10T20:00:00.000Z")
        self.assertEqual(targets["earnings-01"], Decimal("0"))
        reasons = self.log.last("committee", "committee.allocation").payload["reasons"]
        self.assertIn("bankrupt", reasons["earnings-01"])

    def test_a_mandate_breach_goes_to_zero(self):
        self.add(manifest())
        self.allocate_event({"earnings-01": "1000"}, "2026-09-01T13:00:00.000Z")
        self.fill("earnings-01", "buy", "10", "100", "2026-09-01T14:00:00.000Z")
        self.ledgers["earnings-01"].mark({AAPL.key: Decimal("120")}, "2026-09-02T20:00:00.000Z")
        self.ledgers["earnings-01"].mark({AAPL.key: Decimal("90")}, "2026-09-03T20:00:00.000Z")
        state = self.ledgers["earnings-01"].state("2026-09-03T20:00:00.000Z")
        self.assertEqual(state.max_drawdown_pct, Decimal("0.250000"))
        targets = self.committee().allocate("2026-09-03T20:00:00.000Z")
        self.assertEqual(targets["earnings-01"], Decimal("0"))
        self.assertIn(
            "mandate breach",
            self.log.last("committee", "committee.allocation").payload["reasons"]["earnings-01"],
        )

    def test_a_paused_desk_goes_to_zero(self):
        self.add(manifest())
        self.log.append(
            "risk",
            "risk.breaker",
            {"scope": "desk:earnings-01", "rule": "bankrupt", "detail": "no equity",
             "action": "pause_desk"},
            at="2026-09-05T20:00:00.000Z",
        )
        targets = self.committee().allocate("2026-09-14T22:00:00.000Z")
        self.assertEqual(targets["earnings-01"], Decimal("0"))

    def test_a_retired_desk_is_wound_down(self):
        self.add(manifest())
        self.allocate_event({"earnings-01": "1000"}, "2026-09-01T13:00:00.000Z")
        self.log.append(
            "evolution",
            "evolution.retired",
            {"desk_id": "earnings-01", "reason": "below family median", "score": {}},
            at="2026-09-10T20:00:00.000Z",
        )
        targets = self.committee().allocate("2026-09-14T22:00:00.000Z")
        self.assertEqual(targets["earnings-01"], Decimal("0"))
        self.assertEqual(retired_desks(self.log), {"earnings-01"})


class BudgetTests(CommitteeCase):
    def profit(self, amount, at_buy, at_sell):
        self.fill("earnings-01", "buy", "10", "100", at_buy)
        self.fill("earnings-01", "sell", "10", str(100 + Decimal(amount) / 10), at_sell)

    def test_the_cap_is_the_base_plus_a_share_of_realized_profit(self):
        self.add(manifest())
        self.allocate_event({"earnings-01": "2000"}, "2026-09-01T13:00:00.000Z")
        self.profit("400", "2026-09-10T14:00:00.000Z", "2026-09-10T15:00:00.000Z")
        budget = self.committee().compute_budget("2026-09-12T20:00:00.000Z")
        self.assertEqual(budget["trailing_realized_usd"], Decimal("400.00"))
        self.assertEqual(budget["cap_usd"], Decimal("115.00").min(Decimal("60")))
        self.assertEqual(budget["cap_usd"], Decimal("60"))

    def test_a_modest_week_raises_the_cap_a_modest_amount(self):
        self.add(manifest())
        self.allocate_event({"earnings-01": "2000"}, "2026-09-01T13:00:00.000Z")
        self.profit("100", "2026-09-10T14:00:00.000Z", "2026-09-10T15:00:00.000Z")
        budget = self.committee().compute_budget("2026-09-12T20:00:00.000Z")
        self.assertEqual(budget["cap_usd"], Decimal("40.00"))
        self.assertEqual(budget["base_usd"], Decimal("15"))
        self.assertEqual(budget["profit_share"], Decimal("0.25"))

    def test_profit_outside_the_window_does_not_pay_for_compute(self):
        self.add(manifest())
        self.allocate_event({"earnings-01": "2000"}, "2026-08-01T13:00:00.000Z")
        self.profit("400", "2026-08-02T14:00:00.000Z", "2026-08-02T15:00:00.000Z")
        budget = self.committee().compute_budget("2026-09-12T20:00:00.000Z")
        self.assertEqual(budget["trailing_realized_usd"], Decimal("0.00"))
        self.assertEqual(budget["cap_usd"], Decimal("15.00"))

    def test_a_losing_week_never_lowers_the_base(self):
        self.add(manifest())
        self.allocate_event({"earnings-01": "2000"}, "2026-09-01T13:00:00.000Z")
        self.profit("-300", "2026-09-10T14:00:00.000Z", "2026-09-10T15:00:00.000Z")
        budget = self.committee().compute_budget("2026-09-12T20:00:00.000Z")
        self.assertEqual(budget["trailing_realized_usd"], Decimal("-300.00"))
        self.assertEqual(budget["cap_usd"], Decimal("15.00"))


class MemoTests(CommitteeCase):
    def test_memo_is_written_once_per_week_and_published(self):
        self.add(manifest())
        self.allocate_event({"earnings-01": "1000"}, "2026-09-01T13:00:00.000Z")
        committee = self.committee()
        text = committee.memo("2026-09-13T22:00:00.000Z")
        self.assertEqual(text, "The week in one paragraph.")
        event = self.log.last("committee", "committee.memo")
        self.assertEqual(event.payload["period"], iso_week("2026-09-13T22:00:00.000Z"))
        self.assertTrue(event.public)
        self.assertEqual(len(self.provider.calls), 1)
        call = self.provider.calls[0]
        self.assertEqual(call["profile"], "pro_flex")
        self.assertIsNone(call["tools"])
        self.assertEqual(call["desk_id"], "committee")
        self.assertIn("earnings-01", call["items"][1]["content"])
        # A second run in the same week reads the log instead of paying again.
        self.assertEqual(committee.memo("2026-09-13T23:00:00.000Z"), text)
        self.assertEqual(len(self.provider.calls), 1)

    def test_memo_is_capped_at_three_thousand_characters(self):
        self.add(manifest())
        self.provider.text = "x" * 5000
        body = self.committee().memo("2026-09-13T22:00:00.000Z")
        self.assertEqual(len(body), 3000)

    def test_a_provider_failure_is_an_alert_not_a_crash(self):
        self.add(manifest())

        class Broken(FakeProvider):
            def respond(self, *args, **kwargs):
                raise RuntimeError("budget_exceeded")

        self.provider = Broken()
        self.assertIsNone(self.committee().memo("2026-09-13T22:00:00.000Z"))
        alert = self.log.last("ops", "ops.alert")
        self.assertIn("not written", alert.payload["text"])
        self.assertIsNone(self.log.last("committee", "committee.memo"))


class LineageTests(CommitteeCase):
    def test_promotion_changes_the_mode_without_touching_the_manifest(self):
        desk = self.add(manifest())
        self.assertEqual(capital_mode(desk, promoted_desks(self.log)), "paper")
        self.log.append(
            "evolution",
            "evolution.promoted",
            {"desk_id": "earnings-01", "from": "paper", "to": "live", "score": {}},
            at="2026-09-10T20:00:00.000Z",
        )
        self.assertEqual(capital_mode(desk, promoted_desks(self.log)), "live")
        self.assertEqual(desk.capital_mode, "paper")  # the file on disk is untouched
        report = self.committee().gates("earnings-01", "2026-09-14T20:00:00.000Z")
        self.assertEqual(report["gate"], "B")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
