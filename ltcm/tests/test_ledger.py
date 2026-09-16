import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.broker import Instrument
from ltcm.events import EventLog
from ltcm.ledger import DeskLedger, floor_totals, position_walk, quote_prices

AAPL = Instrument("equity", "AAPL", "alpaca")
MSFT = Instrument("equity", "MSFT", "alpaca")
DESK = "earnings-01"


class LedgerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = EventLog(Path(self.tmp.name) / "events.sqlite")
        self.ledger = DeskLedger(self.log, DESK)

    def tearDown(self):
        self.log.close()
        self.tmp.cleanup()

    # -- helpers ---------------------------------------------------------
    def allocate(self, amount, at, desk=DESK):
        return self.log.append(
            "committee",
            "committee.allocation",
            {"allocations": {desk: str(amount)}, "reasons": {}},
            at=at,
        )

    def fill(self, side, quantity, price, at, *, fee="0", instrument=AAPL, desk=DESK, fill_id=None):
        fill_id = fill_id or f"f-{self.log.latest_seq() + 1}"
        return self.log.append(
            "broker:shadow",
            "broker.fill",
            {
                "fill_id": fill_id,
                "order_id": "ord-" + fill_id,
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


class FoldTests(LedgerCase):
    def test_allocation_is_an_external_flow(self):
        self.allocate("1000", "2026-09-01T13:00:00.000Z")
        state = self.ledger.state("2026-09-01T13:00:00.000Z")
        self.assertEqual(state.cash, Decimal("1000"))
        self.assertEqual(state.equity, Decimal("1000"))
        self.assertEqual(state.net_deposits, Decimal("1000"))
        self.assertEqual(state.allocation, Decimal("1000"))
        self.assertEqual(state.time_weighted_return_pct, Decimal("0.0000"))
        self.assertEqual(state.daily_pnl, Decimal("0"))

    def test_fill_moves_cash_positions_and_fees(self):
        self.allocate("1000", "2026-09-01T13:00:00.000Z")
        self.fill("buy", "5", "100", "2026-09-01T14:00:00.000Z", fee="1")
        state = self.ledger.state("2026-09-01T14:30:00.000Z")
        self.assertEqual(state.cash, Decimal("499"))
        self.assertEqual(state.fees, Decimal("1"))
        self.assertEqual(state.decisions, 1)
        position = state.positions[AAPL.key]
        self.assertEqual(position.quantity, Decimal("5"))
        self.assertEqual(position.average_cost, Decimal("100"))
        self.assertEqual(state.equity, Decimal("999"))

    def test_average_cost_and_realized_pnl(self):
        self.allocate("10000", "2026-09-01T13:00:00.000Z")
        self.fill("buy", "10", "100", "2026-09-01T14:00:00.000Z")
        self.fill("buy", "10", "120", "2026-09-01T15:00:00.000Z")
        state = self.ledger.state("2026-09-01T15:30:00.000Z")
        self.assertEqual(state.positions[AAPL.key].average_cost, Decimal("110"))
        self.fill("sell", "12", "130", "2026-09-02T14:00:00.000Z", fee="2")
        state = self.ledger.state("2026-09-02T14:30:00.000Z")
        self.assertEqual(state.realized_pnl, Decimal("240"))  # 12 * (130 - 110)
        self.assertEqual(state.fees, Decimal("2"))
        self.assertEqual(state.positions[AAPL.key].quantity, Decimal("8"))
        self.assertEqual(state.positions[AAPL.key].average_cost, Decimal("110"))
        # 10000 - 1000 - 1200 + 1560 - 2
        self.assertEqual(state.cash, Decimal("9358"))

    def test_closing_a_position_removes_it(self):
        self.allocate("1000", "2026-09-01T13:00:00.000Z")
        self.fill("buy", "5", "100", "2026-09-01T14:00:00.000Z")
        self.fill("sell", "5", "110", "2026-09-01T15:00:00.000Z")
        state = self.ledger.state("2026-09-01T16:00:00.000Z")
        self.assertEqual(state.positions, {})
        self.assertEqual(state.realized_pnl, Decimal("50"))
        self.assertEqual(state.equity, Decimal("1050"))

    def test_duplicate_fill_ids_are_absorbed_once(self):
        self.allocate("1000", "2026-09-01T13:00:00.000Z")
        self.fill("buy", "2", "100", "2026-09-01T14:00:00.000Z", fill_id="dup")
        self.log.append(
            "broker:shadow",
            "broker.fill",
            {
                "fill_id": "dup",
                "order_id": "ord-dup",
                "desk_id": DESK,
                "instrument": AAPL.to_dict(),
                "side": "buy",
                "quantity": "2",
                "price": "100",
                "fee": "0",
                "at": "2026-09-01T14:00:00.000Z",
                "note": "a replay with a different event id",
            },
            at="2026-09-01T14:00:00.000Z",
        )
        state = self.ledger.state("2026-09-01T15:00:00.000Z")
        self.assertEqual(state.positions[AAPL.key].quantity, Decimal("2"))
        self.assertEqual(state.decisions, 1)

    def test_other_desks_are_ignored(self):
        self.allocate("1000", "2026-09-01T13:00:00.000Z")
        self.allocate("5000", "2026-09-01T13:00:00.000Z", desk="kalshi-01")
        self.fill("buy", "5", "100", "2026-09-01T14:00:00.000Z", desk="kalshi-01")
        state = self.ledger.state("2026-09-01T15:00:00.000Z")
        self.assertEqual(state.cash, Decimal("1000"))
        self.assertEqual(state.positions, {})

    def test_malformed_fill_is_skipped_not_absorbed(self):
        self.allocate("1000", "2026-09-01T13:00:00.000Z")
        self.log.append(
            "broker:shadow",
            "broker.fill",
            {"fill_id": "bad", "desk_id": DESK, "side": "buy", "quantity": "1"},
            at="2026-09-01T14:00:00.000Z",
        )
        state = self.ledger.state("2026-09-01T15:00:00.000Z")
        self.assertEqual(state.cash, Decimal("1000"))
        self.assertEqual(state.decisions, 0)

    def test_incremental_fold_is_cached_by_seq(self):
        self.allocate("1000", "2026-09-01T13:00:00.000Z")
        first = self.ledger.state("2026-09-01T13:00:00.000Z")
        self.assertEqual(first.seq, self.log.latest_seq())
        self.fill("buy", "1", "100", "2026-09-01T14:00:00.000Z")
        second = self.ledger.state("2026-09-01T14:00:00.000Z")
        self.assertEqual(second.seq, self.log.latest_seq())
        self.assertGreater(second.seq, first.seq)
        self.assertEqual(second.cash, Decimal("900"))


class MarkTests(LedgerCase):
    def test_mark_writes_a_valuation_and_is_idempotent(self):
        self.allocate("1000", "2026-09-01T13:00:00.000Z")
        self.fill("buy", "5", "100", "2026-09-01T14:00:00.000Z")
        event = self.ledger.mark({AAPL.key: Decimal("110")}, "2026-09-01T20:00:00.000Z")
        self.assertEqual(event.id, "mark:earnings-01:2026-09-01T20:00:00.000Z")
        self.assertEqual(event.kind, "ledger.mark")
        self.assertEqual(event.stream, "ledger:earnings-01")
        self.assertTrue(event.public)
        self.assertEqual(event.payload["equity"], "1050")
        self.assertEqual(event.payload["cash"], "500")
        self.assertEqual(event.payload["daily_pnl"], "50")
        self.assertEqual(event.payload["as_of"], "2026-09-01T20:00:00.000Z")
        self.assertEqual(len(event.payload["positions"]), 1)
        again = self.ledger.mark({AAPL.key: Decimal("110")}, "2026-09-01T20:00:00.000Z")
        self.assertEqual(again.seq, event.seq)
        self.assertEqual(self.log.count("ledger:earnings-01"), 1)

    def test_marks_drive_equity_and_daily_pnl_across_a_day(self):
        self.allocate("1000", "2026-09-01T13:00:00.000Z")
        self.fill("buy", "10", "100", "2026-09-01T13:30:00.000Z")
        self.ledger.mark({AAPL.key: Decimal("110")}, "2026-09-01T20:00:00.000Z")
        state = self.ledger.state("2026-09-01T20:00:00.000Z")
        self.assertEqual(state.equity, Decimal("1100"))
        self.assertEqual(state.daily_pnl, Decimal("100"))
        self.ledger.mark({AAPL.key: Decimal("105")}, "2026-09-02T20:00:00.000Z")
        state = self.ledger.state("2026-09-02T20:00:00.000Z")
        self.assertEqual(state.equity, Decimal("1050"))
        self.assertEqual(state.start_of_day_equity, Decimal("1100"))
        self.assertEqual(state.daily_pnl, Decimal("-50"))

    def test_quote_prices_accepts_quotes_and_mappings(self):
        from ltcm.broker import Quote

        quote = Quote(AAPL, Decimal("99"), Decimal("101"), Decimal("100"), "now", "sim")
        self.assertEqual(quote_prices([quote]), {AAPL.key: Decimal("100")})
        self.assertEqual(quote_prices({AAPL: "12"}), {AAPL.key: Decimal("12")})
        self.assertEqual(quote_prices({AAPL.key: {"bid": "2", "ask": "4"}}), {AAPL.key: Decimal("3")})
        self.assertEqual(quote_prices(None), {})


class ReturnTests(LedgerCase):
    def test_twr_chains_across_a_deposit(self):
        self.allocate("1000", "2026-09-01T13:00:00.000Z")
        self.fill("buy", "10", "100", "2026-09-01T13:30:00.000Z")
        self.ledger.mark({AAPL.key: Decimal("110")}, "2026-09-01T20:00:00.000Z")
        self.assertEqual(
            self.ledger.state("2026-09-01T20:00:00.000Z").time_weighted_return_pct,
            Decimal("10.0000"),
        )
        # The committee doubles the sleeve: a deposit, not a gain.
        self.allocate("2000", "2026-09-02T13:00:00.000Z")
        after = self.ledger.state("2026-09-02T13:00:00.000Z")
        self.assertEqual(after.net_deposits, Decimal("2000"))
        self.assertEqual(after.cash, Decimal("1000"))
        self.assertEqual(after.equity, Decimal("2100"))
        self.assertEqual(after.time_weighted_return_pct, Decimal("10.0000"))
        # Second sub-period: 2210 / 2100.
        self.ledger.mark({AAPL.key: Decimal("121")}, "2026-09-02T20:00:00.000Z")
        end = self.ledger.state("2026-09-02T20:00:00.000Z")
        self.assertEqual(end.equity, Decimal("2210"))
        self.assertEqual(end.time_weighted_return_pct, Decimal("15.7619"))
        # The money-weighted number a naive ledger would report is materially different.
        self.assertNotEqual(end.time_weighted_return_pct, Decimal("10.5000"))

    def test_withdrawal_does_not_look_like_a_loss(self):
        self.allocate("1000", "2026-09-01T13:00:00.000Z")
        self.fill("buy", "5", "100", "2026-09-01T13:30:00.000Z")
        self.ledger.mark({AAPL.key: Decimal("120")}, "2026-09-01T20:00:00.000Z")
        self.assertEqual(
            self.ledger.state("2026-09-01T20:00:00.000Z").time_weighted_return_pct,
            Decimal("10.0000"),
        )
        self.allocate("400", "2026-09-02T13:00:00.000Z")
        state = self.ledger.state("2026-09-02T13:00:00.000Z")
        self.assertEqual(state.net_deposits, Decimal("400"))
        self.assertEqual(state.cash, Decimal("-100"))
        self.assertEqual(state.time_weighted_return_pct, Decimal("10.0000"))

    def test_drawdown_is_measured_on_the_growth_index(self):
        self.allocate("1000", "2026-09-01T13:00:00.000Z")
        self.fill("buy", "10", "100", "2026-09-01T13:30:00.000Z")
        self.ledger.mark({AAPL.key: Decimal("110")}, "2026-09-01T20:00:00.000Z")
        self.ledger.mark({AAPL.key: Decimal("90")}, "2026-09-02T20:00:00.000Z")
        state = self.ledger.state("2026-09-02T20:00:00.000Z")
        self.assertEqual(state.equity, Decimal("900"))
        self.assertEqual(state.time_weighted_return_pct, Decimal("-10.0000"))
        self.assertEqual(state.max_drawdown_pct, Decimal("0.181818"))
        # Recovering does not shrink the recorded worst case.
        self.ledger.mark({AAPL.key: Decimal("115")}, "2026-09-03T20:00:00.000Z")
        self.assertEqual(
            self.ledger.state("2026-09-03T20:00:00.000Z").max_drawdown_pct, Decimal("0.181818")
        )

    def test_history_and_days_live(self):
        self.allocate("1000", "2026-09-01T13:00:00.000Z")
        self.fill("buy", "10", "100", "2026-09-01T13:30:00.000Z")
        self.ledger.mark({AAPL.key: Decimal("110")}, "2026-09-01T20:00:00.000Z")
        self.ledger.mark({AAPL.key: Decimal("120")}, "2026-09-08T20:00:00.000Z")
        state = self.ledger.state("2026-09-08T20:00:00.000Z")
        self.assertEqual(state.started_at, "2026-09-01T13:00:00.000Z")
        self.assertEqual(state.days_live, 7)
        self.assertEqual([p["at"] for p in state.history][-1], "2026-09-08T20:00:00.000Z")
        self.assertEqual(state.history[-1]["equity"], "1200")
        self.assertEqual(state.to_dict()["time_weighted_return_pct"], "20.0000")


class FloorTests(LedgerCase):
    def test_floor_totals_sum_every_sleeve(self):
        other = DeskLedger(self.log, "kalshi-01")
        self.allocate("1000", "2026-09-01T13:00:00.000Z")
        self.allocate("500", "2026-09-01T13:00:00.000Z", desk="kalshi-01")
        self.fill("buy", "5", "100", "2026-09-01T14:00:00.000Z")
        self.ledger.mark({AAPL.key: Decimal("110")}, "2026-09-01T20:00:00.000Z")
        totals = floor_totals(
            {DESK: self.ledger, "kalshi-01": other}, "2026-09-01T20:00:00.000Z"
        )
        self.assertEqual(totals["equity"], Decimal("1550"))
        self.assertEqual(totals["cash"], Decimal("1000"))
        self.assertEqual(totals["net_deposits"], Decimal("1500"))
        self.assertEqual(totals["daily_pnl"], Decimal("50"))

    def test_floor_totals_can_be_narrowed_to_the_live_sleeves(self):
        """The floor's equity is real money. A scored book is counted, never added."""
        other = DeskLedger(self.log, "kalshi-01")
        self.allocate("1000", "2026-09-01T13:00:00.000Z")
        self.allocate("500", "2026-09-01T13:00:00.000Z", desk="kalshi-01")
        ledgers = {DESK: self.ledger, "kalshi-01": other}
        live = floor_totals(ledgers, "2026-09-01T20:00:00.000Z", include={"kalshi-01"})
        self.assertEqual(live["equity"], Decimal("500"))
        self.assertEqual(live["net_deposits"], Decimal("500"))
        self.assertEqual(
            floor_totals(ledgers, "2026-09-01T20:00:00.000Z", include=set())["equity"],
            Decimal("0"),
        )

    def test_a_shadow_mark_says_so_in_its_payload(self):
        self.allocate("1000", "2026-09-01T13:00:00.000Z")
        self.ledger.mark({}, "2026-09-01T20:00:00.000Z", shadow=True)
        event = self.log.read(stream=f"ledger:{DESK}", kind="ledger.mark")[-1]
        self.assertTrue(event.payload["shadow"])
        self.ledger.mark({}, "2026-09-01T21:00:00.000Z")
        self.assertNotIn("shadow", self.log.read(stream=f"ledger:{DESK}", kind="ledger.mark")[-1].payload)

    def test_gross_exposure_uses_marks_then_cost(self):
        self.allocate("10000", "2026-09-01T13:00:00.000Z")
        self.fill("buy", "10", "100", "2026-09-01T14:00:00.000Z")
        self.fill("buy", "4", "50", "2026-09-01T14:05:00.000Z", instrument=MSFT)
        state = self.ledger.state("2026-09-01T15:00:00.000Z")
        self.assertEqual(state.gross_exposure, Decimal("1200"))


class UnfundedBookTests(unittest.TestCase):
    def test_a_book_cut_to_zero_does_not_turn_leftover_pennies_into_drawdowns(self):
        import tempfile
        from pathlib import Path
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        log = EventLog(Path(tmp.name) / "events.sqlite")
        self.addCleanup(log.close)
        mark = lambda equity, at: log.append("ledger:d1", "ledger.mark", {"equity": equity, "cash": equity, "positions": [], "daily_pnl": "0", "as_of": at}, at=at)
        log.append("committee", "committee.allocation", {"allocations": {"d1": "150"}, "reasons": {}}, at="2026-09-16T10:00:00.000Z")
        mark("156.50", "2026-09-16T11:00:00.000Z")
        log.append("committee", "committee.allocation", {"allocations": {"d1": "0"}, "reasons": {}}, at="2026-09-16T12:00:00.000Z")
        at_cut = DeskLedger(log, "d1").state("2026-09-16T12:00:00.000Z").max_drawdown_pct
        mark("4.00", "2026-09-16T13:00:00.000Z")
        mark("6.90", "2026-09-16T14:00:00.000Z")
        mark("2.10", "2026-09-16T15:00:00.000Z")
        state = DeskLedger(log, "d1").state("2026-09-16T15:00:00.000Z")
        self.assertEqual(state.max_drawdown_pct, at_cut, "no drawdown from a book with no capital")
        log.append("committee", "committee.allocation", {"allocations": {"d1": "150"}, "reasons": {}}, at="2026-09-16T16:00:00.000Z")
        mark("120.00", "2026-09-16T17:00:00.000Z")
        funded = DeskLedger(log, "d1").state("2026-09-16T17:00:00.000Z")
        self.assertGreater(funded.max_drawdown_pct, Decimal("0.15"), "a funded book's real loss still counts")


class ConcurrentFoldTests(unittest.TestCase):
    def test_threads_folding_one_ledger_agree_with_a_single_fold(self):
        import tempfile, threading
        from pathlib import Path
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        log = EventLog(Path(tmp.name) / "events.sqlite")
        self.addCleanup(log.close)
        ledger = DeskLedger(log, "d1")
        log.append("committee", "committee.allocation", {"allocations": {"d1": "1000"}, "reasons": {}}, at="2026-09-16T10:00:00.000Z")
        errors = []

        def reader():
            try:
                for _ in range(200):
                    ledger.state("2026-09-16T12:00:00.000Z")
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(6)]
        for thread in threads:
            thread.start()
        for n in range(150):
            target = "1000" if n % 2 else "500"
            log.append("committee", "committee.allocation", {"allocations": {"d1": target}, "reasons": {}}, at=f"2026-09-16T11:{n // 60:02d}:{n % 60:02d}.000Z")
            log.append("ledger:d1", "ledger.mark", {"equity": target, "cash": target, "positions": [], "daily_pnl": "0", "as_of": f"2026-09-16T11:{n // 60:02d}:{n % 60:02d}.500Z"}, at=f"2026-09-16T11:{n // 60:02d}:{n % 60:02d}.500Z")
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        fresh = DeskLedger(log, "d1").state("2026-09-16T12:00:00.000Z")
        shared = ledger.state("2026-09-16T12:00:00.000Z")
        self.assertEqual(shared.max_drawdown_pct, fresh.max_drawdown_pct)
        self.assertEqual(shared.cash, fresh.cash)
        self.assertEqual(shared.max_drawdown_pct, Decimal("0"), "capital moves are never drawdowns")


class PositionWalkTests(unittest.TestCase):
    """When a position opened and what its entry paid, fill by fill (the outcome's record)."""

    def walk(self, *fills, shorts=False):
        rows = [
            {"fill_id": f"f{i}", "side": side, "quantity": quantity, "fee": fee, "at": at}
            for i, (side, quantity, fee, at) in enumerate(fills)
        ]
        return list(position_walk(rows, shorts=shorts))

    def test_adds_and_partial_sells_pool_the_fees_at_average_cost(self):
        rows = self.walk(
            ("buy", "10", "0.30", "t1"), ("sell", "5", "0.01", "t2"), ("buy", "5", "0.20", "t3"),
            ("sell", "10", "0.02", "t4"), ("buy", "4", "0.08", "t5"), ("sell", "4", "0", "t6"),
        )
        self.assertEqual([r["closed"] for r in rows], [0, 5, 0, 10, 0, 4])
        self.assertEqual(rows[1]["entry_fees"], Decimal("0.15"))
        self.assertEqual(rows[3]["entry_fees"], Decimal("0.35"))  # what is left of the pool: all of it
        self.assertEqual([r["opened_at"] for r in rows], ["t1", "t1", "t1", "t1", "t5", "t5"])
        self.assertEqual(rows[5]["entry_fees"], Decimal("0.08"))
        self.assertEqual(rows[-1]["held"], 0)

    def test_a_sell_with_nothing_held_is_passed_over_unless_shorts_are_allowed(self):
        rows = self.walk(("sell", "3", "0.01", "t1"), ("buy", "3", "0.03", "t2"), ("sell", "5", "0", "t3"))
        self.assertEqual([r["closed"] for r in rows], [0, 0, 3])
        self.assertEqual((rows[2]["held"], rows[2]["opened_at"]), (0, "t2"))
        flipped = self.walk(("buy", "3", "0.03", "t1"), ("sell", "5", "0.05", "t2"), ("buy", "2", "0", "t3"), shorts=True)
        self.assertEqual((flipped[1]["closed"], flipped[1]["held"], flipped[1]["opened_at"]), (3, -2, "t1"))
        self.assertEqual((flipped[2]["closed"], flipped[2]["entry_fees"], flipped[2]["opened_at"]), (2, Decimal("0.02"), "t2"))
        self.assertEqual(self.walk(("buy", "x", "0", "t1"), ("hold", "1", "0", "t2")), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
