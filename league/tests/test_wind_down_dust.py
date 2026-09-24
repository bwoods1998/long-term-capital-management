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


if __name__ == "__main__":
    import unittest

    unittest.main()
