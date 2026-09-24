"""A dust wind-down that never ended (Sept 24, 2026, the close-the-gaps run).

Since 15:44Z Sept 23 the House's wind-down of the dead agent haghani-h426990's practice account tried
every ~5 minutes to sell 0.000000001 LINK/USD ("the House is closing this account at the ask (a market
sell would meet the House's own bid)"), and Alpaca refused every one: "HTTP 403 order qty must be >=
minimal qty of order 0.000000002" (107 rejections by 03:08Z Sept 24). A holding the venue will not trade
is booked as dust, as the reconciliation books position dust, and the account closes. The invariant: the
same refusal of a House-sent order three times in a row stops its retries with one warning naming it."""

from __future__ import annotations

from decimal import Decimal

from league.tests.test_seat_market import SeatCase, alerts
from league.venues import instrument_for
from ltcm.broker import RejectedOrder


class DustWindDown(SeatCase):
    LINK = instrument_for("alpaca-paper", {"symbol": "LINK/USD"})

    def hold(self, agent, quantity, price="12.27"):
        """A position on the practice book as its fill left it (and the venue with it)."""
        book = self.house.books["alpaca-paper"]
        self.house.seat(agent)
        with book._lock:
            entry = self.house.ledger.append("book.fill", {
                "book": "alpaca-paper", "source": "venue", "instrument": self.LINK.to_dict(), "side": "buy", "quantity": quantity,
                "price": price, "fee_usd": "0", "cash_delta": str(-(Decimal(quantity) * Decimal(price))), "position_delta": quantity,
                "real_money": False}, agent=agent.id)
            book._apply(entry.kind, agent.id, entry.payload, entry.at)
        self.broker.held[self.LINK.key] = (self.LINK, Decimal(quantity))
        self.broker.set_quote(self.LINK, "12.26", "12.28")
        return book

    def test_a_holding_worth_under_a_cent_is_booked_as_dust_and_the_account_closes(self):
        """haghani-h426990's 0.000000001 LINK/USD: 107 refused sells by 03:08Z Sept 24."""
        agent = self.seated("haghani")
        book = self.hold(agent, "0.000000001")
        self.house.kill(agent, "displaced", "test")
        self.assertEqual(self.broker.submitted, [], "a holding the venue will not trade is never sent")
        account = book.account(agent.id)
        self.assertEqual((account.holdings, account.swept), ({}, True))
        dust = [(e.agent, e.payload["position_delta"]) for e in self.house.ledger.iter(kinds="book.fill") if e.payload.get("source") == "dust"]
        self.assertEqual(dust, [(agent.id, "-0.000000001"), ("house", "0.000000001")])
        self.assertEqual(len(alerts(self.house, "info", "dust")), 1)
        self.house._retry_wind_down(self.house.registry.get(agent.id), book)
        self.assertEqual(len(alerts(self.house, "info", "dust")), 1, "said once")
        self.assertTrue(book.reconcile().ok)

    def test_the_same_venue_refusal_three_times_in_a_row_stops_the_retries_and_warns_once(self):
        agent = self.seated("haghani")
        book = self.hold(agent, "0.5")  # six dollars of LINK: not dust
        self.broker.raise_on_submit = RejectedOrder("alpaca submit: HTTP 403 order qty must be >= minimal qty of order 0.000000002")
        self.house.registry.died(agent.id, "displaced", "test")
        dead = self.house.registry.get(agent.id)
        for _ in range(4):
            self.clock.advance(300)  # the mark pass retries every five minutes
            self.house._retry_wind_down(dead, book)
        self.assertEqual(len(self.broker.submitted), 3, "three refusals in a row, then no more retries")
        told = alerts(self.house, "warning", "refused", "LINK")
        self.assertEqual(len(told), 1)
        self.house._retry_wind_down(dead, book)  # the same second again: a duplicate intent is not a new refusal
        self.clock.advance(300)
        self.house._retry_wind_down(dead, book)
        self.assertEqual(len(alerts(self.house, "warning", "refused", "LINK")), 1)
        self.assertEqual(len(self.broker.submitted), 3)
        self.broker.raise_on_submit = None
        self.hold(dead, "0.1")  # the holding changed: tried again
        self.clock.advance(300)
        self.house._retry_wind_down(dead, book)
        self.assertEqual(len(self.broker.submitted), 4)


    # The review of #245 (Sept 24, 2026). Each failed on the branch as built.
    def test_a_stub_bid_does_not_make_a_sellable_holding_dust(self):
        """The mark is the last quote's bid: under a $12.28 ask a stub $0.01 bid valued half a LINK at half a cent,
        and six dollars the venue would buy were booked off the account as dust."""
        agent = self.seated("haghani")
        book = self.hold(agent, "0.5")
        self.broker.set_quote(self.LINK, "0.01", "12.28")
        book.marks.pop(self.LINK.key, None)
        self.house.kill(agent, "displaced", "test")
        self.assertEqual([e for e in self.house.ledger.iter(kinds="book.fill") if e.payload.get("source") == "dust"], [])
        self.assertEqual(len(self.broker.submitted), 1, "it is sold")
        self.assertIsNone(self.house._dust_reason(book, self.LINK, Decimal("0.5")))
        self.assertIsNotNone(self.house._dust_reason(book, self.LINK, Decimal("0.000000001")), "a real crumb is still dust")

    def test_a_stopped_sale_is_tried_again_once_a_day(self):
        """A dead agent's holding never changes: a refusal that is transient but identical three times in a row (an
        outage) stopped its sale for good. It is tried again a day after the last refusal."""
        agent = self.seated("haghani")
        book = self.hold(agent, "0.5")
        self.broker.raise_on_submit = RejectedOrder("alpaca submit: HTTP 503 service unavailable")
        self.house.registry.died(agent.id, "displaced", "test")
        dead = self.house.registry.get(agent.id)
        for _ in range(4):
            self.clock.advance(300)
            self.house._retry_wind_down(dead, book)
        self.assertEqual(len(self.broker.submitted), 3)
        self.clock.advance(86400)
        self.house._retry_wind_down(dead, book)
        self.assertEqual(len(self.broker.submitted), 4, "a day after the last refusal: tried again")
        self.clock.advance(300)
        self.house._retry_wind_down(dead, book)
        self.assertEqual(len(self.broker.submitted), 4, "refused again: stopped for another day")
        self.assertEqual(len(alerts(self.house, "warning", "refused", "LINK")), 1, "and told once")
        self.broker.raise_on_submit = None
        self.clock.advance(86400)
        self.house._retry_wind_down(dead, book)
        self.assertEqual(len(self.broker.submitted), 5)
        self.assertNotIn(self.LINK.key, ((self.house._state.get("wind_down_refusals") or {}).get(agent.id) or {}).get(book.name, {}))

    def test_a_crash_between_the_two_dust_rows_leaves_the_book_consistent(self):
        """The review of #245 (Sept 24, 2026): the agent's dust row and the House's were two appends, so a crash
        between them left the book short of the venue by the holding. Under a cent the reconciliation re-books the
        crumb; dust by the venue's minimal quantity can be worth more, and that difference freezes the book's
        entries. Both rows are one ledger group now: both or neither, in the process and after a restart."""
        from unittest.mock import patch

        from league.ledger import HOUSE, Ledger

        agent = self.seated("haghani")
        book = self.hold(agent, "0.5")  # six dollars of LINK ...
        self.broker.cash -= Decimal("0.5") * Decimal("12.27")  # (the venue paid for it too)
        self.assertTrue(book.reconcile().ok)
        self.broker.asset = lambda symbol: {"min_order_size": Decimal("1")}  # ... under the venue's minimal quantity
        real = Ledger._append_one

        def crash(ledger, kind, payload, *, agent=HOUSE, **kw):
            if kind == "book.fill" and payload.get("source") == "dust" and agent == HOUSE:
                raise RuntimeError("the House stopped between the two dust rows")
            return real(ledger, kind, payload, agent=agent, **kw)

        with patch.object(Ledger, "_append_one", crash):
            self.house.kill(agent, "displaced", "test")
        self.assertTrue(book.reconcile().ok, "in the same process")
        self.house.close(wait=None)
        self.house = self.new_house()  # a restart on the same ledger and venue
        restarted = self.house.books["alpaca-paper"]
        self.assertTrue(restarted.reconcile().ok, "after a restart")
        self.house._retry_wind_down(self.house.registry.get(agent.id), restarted)  # the next pass books it whole
        dust = [(e.agent, e.payload["position_delta"]) for e in self.house.ledger.iter(kinds="book.fill") if e.payload.get("source") == "dust"]
        self.assertEqual(dust, [(agent.id, "-0.5"), ("house", "0.5")])
        self.assertTrue(restarted.reconcile().ok)

if __name__ == "__main__":
    import unittest

    unittest.main()
