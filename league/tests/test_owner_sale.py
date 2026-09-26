"""The owner's own trades on a real Kalshi account (Sept 26, 2026).

At 02:07:08-02:07:30Z the owner sold three positions of meriwether-h2d625d by hand on Kalshi (AZ-SD NO 11, LAD-SF NO 13,
NYM-WSH NO 16; $15.4802 net of $0.3998 of fees), and from 02:16:19Z the real book froze on "cash differs by 15.4796;
positions differ: ... -11, ... -13, ... -16". At 02:34:14Z the House settled AZ-SD's 11 NO for the agent, units the
venue no longer held. These tests replay that night with the venue's own fill rows as Kalshi reported them: each sale of
NO as a YES bought at the complement (`outcome_side: yes`, `book_side: bid`), by an order the House never sent.
"""
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

from league.book import HOUSE, OWNER_FILL, OWNER_SALE, OWNER_TRANSFER, SETTLEMENT_GRACE_SECONDS, Book
from league.evaluator import Evaluator, closed_trade_rows
from league.families import TradeTape, risked_at_close
from league.fees import Fees
from league.ledger import Ledger
from league.tests.fakes import Clock, FakeBroker
from ltcm.broker import Fill, Instrument

AGENT = "meriwether-h2d625d"
AZSD = "KXMLBTOTAL-26SEP252140AZSD-8"
LADSF = "KXMLBTOTAL-26SEP252215LADSF-8"
NYMWSH = "KXMLBTOTAL-26SEP261605NYMWSH-8"
CINTOR = "KXMLBTOTAL-26SEP261507CINTOR-8"
#: What the book paid for each NO position, fees in (NYM-WSH and CIN-TOR are the ledger's own rows of that night).
COST = {AZSD: D("5.9257"), LADSF: D("7.1334"), NYMWSH: D("7.1776"), CINTOR: D("7.3305")}
UNITS = {AZSD: 11, LADSF: 13, NYMWSH: 16, CINTOR: 15}
OPENED = {AZSD: "2026-09-25T02:24:43.836Z", LADSF: "2026-09-25T23:10:00.000Z", NYMWSH: "2026-09-26T01:45:26.393Z",
          CINTOR: "2026-09-26T02:15:57.047Z"}
#: Kalshi's receipts (GET /portfolio/fills), as the adapter parses them: the YES leg bought, at the YES price.
OWNER_FILLS = [
    ("0723b771-5ad9-a0c7-0da1-a9e8f81cb471", "01a0db77-5ce0-75c5-ad20-684b02786dd3", LADSF, 13, "0.53", "0.1134", "2026-09-26T02:07:08Z"),
    ("0723b6e8-54a9-bd66-a9cc-fb179b1d6862", "01a0db77-7068-718a-8aa0-d1118fd7b42b", NYMWSH, 16, "0.57", "0.1373", "2026-09-26T02:07:13Z"),
    ("0723b6ab-9f59-bdb1-f785-95fadec740e4", "01a0db77-9778-7353-9de2-6a33297a9072", AZSD, 4, "0.75", "0.0525", "2026-09-26T02:07:23Z"),
    ("0723b6a9-5021-ba3b-e7e1-efc33bcfe8c8", "01a0db77-b2d0-718b-9508-62a9c60a2989", AZSD, 7, "0.73", "0.0966", "2026-09-26T02:07:30Z"),
]
NET = D("15.4802")  # what the four sales paid, net of their fees
CINTOR_VENUE_FEE = D("0.1311")  # the venue's fee on the House's CIN-TOR buy; the book booked 0.1305: -0.0006


def no(ticker):
    return Instrument("event", ticker, "kalshi", market_id=ticker, right="no")


def epoch(stamp):
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


class Venue(FakeBroker):
    """Kalshi as the House reads it: positions, cash, and the account's fills."""

    def __init__(self, cash):
        super().__init__("kalshi", cash=cash, family="kalshi")
        self.venue_fills: list[Fill] = []
        self.fill_reads: list[str | None] = []

    def fills(self, since=None):
        self.fill_reads.append(since)
        return [f for f in self.venue_fills if since is None or epoch(f.at) >= epoch(since[:19] + "Z")]


class OwnerSale(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = Clock(epoch("2026-09-26T02:40:00Z"))
        self.ledger = Ledger(Path(self.tmp.name) / "ledger.sqlite", clock=self.clock)
        self.addCleanup(self.ledger.close)
        self.ledger.append("book.baseline", {"book": "kalshi", "cash": "500", "positions": {}}, at="2026-09-24T00:00:00.000Z")
        self.ledger.append("book.stake", {"book": "kalshi", "usd": "60", "real_money": True}, agent=AGENT, at="2026-09-24T00:00:01.000Z")
        for ticker in (AZSD, LADSF, NYMWSH, CINTOR):
            self.buy(ticker)
        self.ledger.append("book.reconciled", {"book": "kalshi", "ok": True, "detail": "", "holds": "cent", "cash_diff": "0"},
                           at="2026-09-26T02:05:00.000Z")  # the last clean reading before the owner's sales

    def buy(self, ticker):
        units, cost = UNITS[ticker], COST[ticker]
        order = f"ord-{ticker[-12:]}"
        inst = no(ticker)
        self.ledger.append("book.order", {"book": "kalshi", "order_id": order, "broker_order_id": f"venue-{ticker}",
                                          "instrument": inst.to_dict(), "side": "buy", "quantity": str(units), "order_type": "limit",
                                          "limit_price": "0.5", "status": "filled", "submitted_at": OPENED[ticker],
                                          "shares": [{"intent_id": f"in-{order}", "agent": AGENT, "quantity": str(units)}]},
                           at=OPENED[ticker])
        self.ledger.append("book.fill", {"book": "kalshi", "source": "venue", "order_id": order, "intent_id": f"in-{order}",
                                         "instrument": inst.to_dict(), "side": "buy", "quantity": str(units), "price": "0.5",
                                         "cash_delta": str(-cost), "position_delta": str(units), "fee_usd": "0", "fee_quantity": "0",
                                         "venue_fee": "0", "realized": None, "venue_accounting_version": 2, "real_money": True},
                           agent=AGENT, at=OPENED[ticker])

    def venue(self, *, sold=(AZSD, LADSF, NYMWSH), extra_cash=D(0), fills=None, extra_positions=()):
        """The account after the owner's sales: what it holds, its cash, its fills (the House's own buys among them)."""
        held = [t for t in (AZSD, LADSF, NYMWSH, CINTOR) if t not in sold]
        cash = D(500) - sum(COST.values()) - (CINTOR_VENUE_FEE - D("0.1305")) + extra_cash
        chosen = OWNER_FILLS if fills is None else fills
        for _, _, ticker, units, yes_price, fee, _ in chosen:
            cash += units * (1 - D(yes_price)) - D(fee)
        broker = Venue(str(cash))
        for ticker in held:
            broker.held[no(ticker).key] = (no(ticker), D(UNITS[ticker]))
        for inst, units in extra_positions:
            broker.held[inst.key] = (inst, D(units))
        # The House's own buys are on the tape too, by orders it sent: never the owner's.
        for ticker in (AZSD, LADSF, NYMWSH, CINTOR):
            broker.venue_fills.append(Fill(f"own-{ticker}", f"venue-{ticker}", "", no(ticker), "buy", D(UNITS[ticker]), D("0.5"),
                                           D(0), OPENED[ticker][:19] + "Z"))
        for fill_id, order_id, ticker, units, yes_price, fee, at in chosen:
            yes = Instrument("event", ticker, "kalshi", market_id=ticker, right="yes")
            broker.venue_fills.append(Fill(fill_id, order_id, "", yes, "buy", D(units), D(yes_price), D(fee), at))
        return broker

    def book(self, broker, *, real=True, name="kalshi"):
        return Book(name, broker, self.ledger, fees=Fees("kalshi"), real_money=real, clock=self.clock)

    def rows(self, source):
        return [e for e in self.ledger.iter(kinds="book.fill") if e.payload.get("source") == source]

    def alerts(self):
        return [e.payload for e in self.ledger.iter(kinds="ops.alert") if e.payload.get("level") == "error"]

    def closed(self):
        return closed_trade_rows(self.ledger.iter(kinds=("book.fill", "book.settle"), agent=AGENT), "kalshi")

    def settle_azsd_for_the_agent(self):
        """What the House did at 02:34:14Z, before the fix: it settled 11 NO the venue no longer held (result yes)."""
        inst = no(AZSD)
        self.ledger.append("book.settle", {"book": "kalshi", "instrument": inst.to_dict(), "result": "yes", "quantity": "11",
                                           "cost": "5.92570000", "payout": "0.00000000", "pnl": "-5.92570000", "reason": "",
                                           "opened_at": OPENED[AZSD], "real_money": True},
                           agent=AGENT, id=f"settle:kalshi:{AGENT}:{inst.key}", at="2026-09-26T02:34:14.815Z")

    def through_the_grace(self, book):
        first = book.reconcile()  # the sold positions look like settlements for SETTLEMENT_GRACE_SECONDS
        self.clock.advance(SETTLEMENT_GRACE_SECONDS + 1)
        return first, book.reconcile()

    # ----------------------------------------------------------------------------------------------- the night
    def test_tonights_three_sales_explain_the_difference_and_are_booked_not_frozen(self):
        before = self.closed()
        book = self.book(self.venue())
        first, result = self.through_the_grace(book)
        self.assertIn("awaiting settlement", first.detail)
        self.assertTrue(result.ok, result.detail)
        self.assertIsNone(book.frozen)
        # Each position moved to the House row at the agent's cost, then the owner's fills were booked there.
        transfers = [e for e in self.rows(OWNER_TRANSFER) if e.agent == AGENT]
        self.assertEqual(sorted(e.payload["instrument"]["market_id"] for e in transfers), sorted([AZSD, LADSF, NYMWSH]))
        for e in transfers:
            ticker = e.payload["instrument"]["market_id"]
            self.assertIsNone(e.payload["realized"])
            self.assertEqual(D(e.payload["cash_delta"]), COST[ticker])
            self.assertEqual(D(e.payload["position_delta"]), -UNITS[ticker])
            self.assertTrue(e.payload["closes_position"])
        owner = self.rows(OWNER_FILL)
        self.assertEqual({e.payload["venue_fill_id"] for e in owner}, {f[0] for f in OWNER_FILLS})
        self.assertTrue(all(e.agent == HOUSE and e.payload["side"] == "sell" for e in owner))
        ladsf = next(e.payload for e in owner if e.payload["instrument"]["market_id"] == LADSF)
        self.assertEqual((ladsf["instrument"]["right"], D(ladsf["price"]), D(ladsf["cash_delta"])), ("no", D("0.47"), D("5.9966")))
        self.assertEqual(ladsf["reported"], {"leg": "yes", "side": "buy", "price": "0.53"})
        # The agent: its cost back, no result, only the position the owner left it.
        account = book.account(AGENT)
        self.assertEqual(account.realized, D(0))
        self.assertEqual(set(account.holdings), {no(CINTOR).key})
        self.assertEqual(account.cash, D(60) - COST[CINTOR])
        # The House: the owner's result, and none of the units.
        house_pnl = NET - COST[AZSD] - COST[LADSF] - COST[NYMWSH]
        self.assertEqual(sum(D(e.payload["realized"]) for e in owner), house_pnl)
        self.assertEqual(book.account(HOUSE).holdings, {})
        # The CIN-TOR fee's rounding, beside them, as dust.
        self.assertEqual(result.cash_diff, D(0))
        alerts = [a for a in self.alerts() if "owner" in a["text"]]
        self.assertEqual(len(alerts), 1)
        self.assertTrue(alerts[0]["text"].startswith("kalshi: "))
        for word in (AZSD, LADSF, NYMWSH, AGENT, "0.47", f"{house_pnl:+.4f}"):
            self.assertIn(word, alerts[0]["text"])
        self.assertEqual(alerts[0]["began_at"], "2026-09-26T02:07:08Z")
        # Evidence: no closed trade, no settlement, nothing at risk closed: the family record is as it was.
        self.assertEqual(self.closed(), before)
        self.assertEqual(self.closed()[0], [])
        tape = TradeTape()
        tape.refresh(self.ledger)
        rows = tape.rows[AGENT]
        self.assertEqual(closed_trade_rows([r for r in rows if r.kind != "book.stake"], "kalshi")[0], [])
        self.assertEqual(risked_at_close(rows, "kalshi", tape.cursor), {})
        # Every later reading stays reconciled (a first reading after a restart can pass while awaiting settlement).
        for _ in range(3):
            self.clock.advance(300)
            self.assertTrue(book.reconcile().ok)
        self.assertEqual(len(self.rows(OWNER_FILL)), 4)

    def test_a_restart_reads_the_booked_rows_and_stays_reconciled(self):
        broker = self.venue()
        self.through_the_grace(self.book(broker))
        booked = len(list(self.ledger.iter(kinds="book.fill")))
        again = self.book(broker)
        self.assertEqual(again.frozen, "awaiting startup reconciliation")
        for _ in range(3):
            result = again.reconcile()
            self.assertTrue(result.ok, result.detail)
            self.assertNotIn("awaiting", result.detail)
            self.clock.advance(SETTLEMENT_GRACE_SECONDS + 1)
        self.assertIsNone(again.frozen)
        self.assertEqual(len(list(self.ledger.iter(kinds="book.fill"))), booked)  # nothing booked twice
        self.assertEqual(again.account(AGENT).realized, D(0))

    # ---------------------------------------------------------------- the settlement booked before the fix
    def test_units_the_house_already_settled_keep_their_settlement_and_the_house_takes_the_proceeds(self):
        self.settle_azsd_for_the_agent()
        before = self.closed()
        self.assertEqual([round(r["made"], 4) for r in before[0]], [-5.9257])  # the settlement, as the House booked it
        book = self.book(self.venue())
        _, result = self.through_the_grace(book)
        self.assertTrue(result.ok, result.detail)
        self.assertIsNone(book.frozen)
        sale = self.ledger.get(f"owner-sale:kalshi:{AZSD}")
        self.assertIsNotNone(sale)
        self.assertEqual((sale.agent, sale.payload["source"], sale.payload["instrument"]), (HOUSE, OWNER_SALE, None))
        self.assertEqual(D(sale.payload["cash_delta"]), D("2.7409"))  # 4 @ 0.25 + 7 @ 0.27 less 0.1491 of fees; the payout was 0
        self.assertEqual(sorted(sale.payload["receipts"]), sorted(f[0] for f in OWNER_FILLS if f[2] == AZSD))
        # The settlement stands, unchanged: the agent's record is exactly what it was.
        self.assertEqual(self.closed(), before)
        self.assertEqual(book.account(AGENT).realized, D("-5.9257"))
        self.assertEqual(sorted(e.payload["instrument"]["market_id"] for e in self.rows(OWNER_TRANSFER) if e.agent == AGENT),
                         [LADSF, NYMWSH])

    def test_owner_sold_then_the_market_settled_the_house_settles_no_units_the_venue_did_not_hold(self):
        broker = self.venue()
        book = self.book(broker)
        # AZ-SD settles YES. The venue's row counts both legs traded: 11 NO bought, 11 YES (the owner's sale).
        settled = book.settle(AZSD, "yes", venue_row={"ticker": AZSD, "result": "yes", "yes_count": D("11.00"),
                                                      "no_count": D("11.00"), "revenue": D(0)})
        self.assertEqual(settled, 0)
        self.assertEqual(list(self.ledger.iter(kinds="book.settle")), [])
        self.assertIn(no(AZSD).key, book.account(AGENT).holdings)
        self.assertTrue(any(AZSD in a["text"] and "did not settle" in a["text"] for a in self.alerts()))
        _, result = self.through_the_grace(book)
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(self.closed()[0], [])  # no phantom settlement in the agent's record
        self.assertIsNone(self.ledger.get(f"owner-sale:kalshi:{AZSD}"))
        self.assertEqual(book.account(AGENT).realized, D(0))

    def test_a_settlement_the_venue_held_is_booked_as_before(self):
        book = self.book(self.venue(sold=(), fills=[]))
        self.assertTrue(book.reconcile().ok)
        self.assertEqual(book.settle(CINTOR, "no", venue_row={"yes_count": D(0), "no_count": D("15.00")}), 1)
        self.assertEqual(book.settle(AZSD, "yes", venue_row={}), 1)  # a row without counts: as before

    # --------------------------------------------------------------------------------- what stays frozen
    def test_fills_that_explain_only_two_of_three_positions_leave_the_book_frozen(self):
        fills = [f for f in OWNER_FILLS if f[2] != NYMWSH]
        broker = self.venue(fills=fills)
        broker.cash += D(16) * D("0.43") - D("0.1373")  # the venue sold NYM-WSH too, but shows no receipt for it
        _, result = self.through_the_grace(self.book(broker))
        self.assertFalse(result.ok)
        self.assertIn(NYMWSH, result.detail)
        self.assertEqual(self.rows(OWNER_TRANSFER) + self.rows(OWNER_FILL), [])

    def test_an_owner_buy_the_book_does_not_know_leaves_the_book_frozen(self):
        other = Instrument("event", "KXMLBTOTAL-26SEP261900SEAHOU-8", "kalshi", market_id="KXMLBTOTAL-26SEP261900SEAHOU-8", right="yes")
        broker = self.venue(extra_positions=[(other, 5)], extra_cash=D("-2.60"))
        broker.venue_fills.append(Fill("owner-buy", "01a0-owner-buy", "", other, "buy", D(5), D("0.52"), D(0), "2026-09-26T02:08:00Z"))
        _, result = self.through_the_grace(self.book(broker))
        self.assertFalse(result.ok)
        self.assertEqual(self.rows(OWNER_TRANSFER) + self.rows(OWNER_FILL), [])

    def test_an_owner_buy_of_more_of_a_held_leg_leaves_the_book_frozen(self):
        yes = Instrument("event", NYMWSH, "kalshi", market_id=NYMWSH, right="yes")
        fills = OWNER_FILLS + [("owner-more", "01a0-owner-more", NYMWSH, 2, "0.43", "0", "2026-09-26T02:09:00Z")]
        broker = self.venue(fills=fills)
        # Read on the NO leg a YES bought is a NO sold; a YES SOLD would be NO bought, which the book never held.
        broker.venue_fills[-1] = Fill("owner-more", "01a0-owner-more", "", yes, "sell", D(2), D("0.43"), D(0), "2026-09-26T02:09:00Z")
        _, result = self.through_the_grace(self.book(broker))
        self.assertFalse(result.ok)
        self.assertEqual(self.rows(OWNER_FILL), [])

    def test_a_cash_difference_the_fills_do_not_explain_leaves_the_book_frozen(self):
        _, result = self.through_the_grace(self.book(self.venue(extra_cash=D("2.00"))))
        self.assertFalse(result.ok)
        self.assertIn("cash differs", result.detail)
        self.assertEqual(self.rows(OWNER_TRANSFER) + self.rows(OWNER_FILL), [])

    def test_a_practice_book_is_unchanged(self):
        broker = self.venue()
        book = Book("kalshi", broker, self.ledger, fees=Fees("kalshi"), real_money=False, clock=self.clock)
        self.through_the_grace(book)
        self.assertEqual(broker.fill_reads, [])
        self.assertEqual(self.rows(OWNER_TRANSFER) + self.rows(OWNER_FILL) + self.rows(OWNER_SALE), [])
        self.assertEqual(book.settle(AZSD, "yes", venue_row={"yes_count": D(11), "no_count": D(11)}), 1)

    # ------------------------------------------------------------------------------ the agent's evidence
    def test_the_transfer_is_no_observation_of_the_agents_growth_nor_a_closed_trade_anywhere(self):
        from league.allocator import closed_trades
        from league.episodes import completed

        broker = self.venue()
        for ticker in (LADSF, NYMWSH, AZSD, CINTOR):
            broker.set_quote(no(ticker), "0.40", "0.45")
        book = self.book(broker)
        book.reconcile()
        book.mark()  # 02:40: the sold positions still marked at the bid
        self.clock.advance(3600)
        book.reconcile()  # 03:40: past the grace, booked
        self.assertEqual(len(self.rows(OWNER_FILL)), 4)
        book.mark()
        self.clock.advance(3600)
        book.mark()  # 04:40 finishes the 03 block
        evaluator = Evaluator(self.ledger, clock=self.clock)
        evaluator.observe(AGENT, "kalshi", "hour")
        blocks = {b["key"]: b for b in evaluator.blocks(AGENT, book="kalshi")}
        block = blocks["2026-09-26T03"]
        # Equity jumped by cost less the marks (the units left at cost), and the flow takes exactly that out.
        moved = sum(COST[t] - UNITS[t] * D("0.40") for t in (AZSD, LADSF, NYMWSH))
        self.assertAlmostEqual(block["end_equity"] - block["start_equity"], float(moved), places=6)
        self.assertAlmostEqual(block["flow"], float(moved), places=6)
        self.assertAlmostEqual(block["log_growth"], 0.0, places=9)
        self.assertEqual(closed_trades(SimpleNamespace(ledger=self.ledger), AGENT, "kalshi"), (0, 0))
        self.assertEqual(evaluator.independent_closed(AGENT, "kalshi"), 0)
        self.assertEqual(completed(self.ledger, AGENT, "kalshi"), [])


if __name__ == "__main__":
    unittest.main()
