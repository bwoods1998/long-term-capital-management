"""Adversarial review of Track S (the options shadow book and the replay's parity with it), Sept 25, 2026.

Each test asserts the behaviour the spec asks for; the ones that FAIL on the trial merge d6bfe3a
demonstrate a defect named in the review report. The last two pass and pin what was checked and holds.
"""

import unittest
from decimal import Decimal

from league import structure_core as core
from league import structures
from league.book import Intent, Limits
from league.fees import Fees
from league.ledger import now_iso
from league.replay import run_replay
from league.tests import test_options_shadow as shadow
from league.tests.test_options_replay import SLIMITS, STRUCTURE_STRATEGY, VERTICAL, VLEGS, socc, sstep, stape
from league.tests.test_options_shadow import BUTTERFLY, CONDOR, V, VERTICAL as SHADOW_VERTICAL, epoch, occ

D = Decimal


class NoBidWing(shadow.ThroughTheBook):
    """MAJOR: a long wing quoted with no bid (0 x size / 0.01 ask, the usual state of a far 0-DTE wing late in
    the day) makes a held credit structure unsellable on the shadow account: rule 3 needs every leg two-sided
    for a CLOSE too, so neither the agent's close nor the House's 15:30 close at the bid can ever fill, and
    the structure is held into its expiry (settled only the next New York day). A real account closes it by
    buying the shorts back at their asks and leaving (or selling at 0) the worthless wing."""

    def test_a_condor_whose_long_wing_has_no_bid_can_still_be_closed_at_its_conservative_bid(self):
        self.book.limits["alice"] = Limits(D(100), D(75), asset_classes=("option",))
        self.legs.set(occ(575, "P"), "0.10", "0.12")
        self.legs.set(occ(576, "P"), "0.30", "0.32")
        self.legs.set(occ(585), "0.30", "0.32")
        self.legs.set(occ(586), "0.10", "0.12")  # ask 1 + .12 + .12 - .30 - .30 = 0.64
        condor = structures.instrument(CONDOR, V)
        [opened] = self.book.submit([Intent.new(agent="alice", instrument=condor, side="buy", quantity="1", order_type="limit",
                                                limit_price="0.64", reason="open", created_at=now_iso(self.clock), nonce="o")])
        self.assertEqual(opened.status, "resting", opened.detail)
        self.later()
        for symbol in (occ(575, "P"), occ(576, "P"), occ(585), occ(586)):
            self.legs.touch(symbol)
        self.broker.advance()
        self.book.poll()
        self.assertIn(condor.key, self.book.account("alice").holdings)
        # Late in the day SPY sits between the shorts; the far put wing has no bid (Alpaca: bp 0, bs 0).
        self.later()
        self.legs.set(occ(575, "P"), "0", "0.01", bid_size="0")
        self.legs.set(occ(576, "P"), "0.02", "0.03")
        self.legs.set(occ(585), "0.05", "0.06")
        self.legs.set(occ(586), "0.01", "0.02")
        quote = self.broker.quote(condor)
        self.assertEqual(quote.bid, D("0.92"))  # the mark: K + 0 + .01 - .03 - .06 (the wing worth nothing)
        # The House's close (`_structure_expiry_close`): a sale at the bid, re-sent each tick.
        [sale] = self.book.submit([Intent.new(agent="alice", instrument=condor, side="sell", quantity="1", order_type="limit",
                                              limit_price=quote.bid, reason="close", created_at=now_iso(self.clock), nonce="c")])
        self.assertEqual(sale.status, "resting", sale.detail)
        for _ in range(5):
            self.later()
            for symbol in (occ(575, "P"), occ(576, "P"), occ(585), occ(586)):
                self.legs.touch(symbol)
            self.broker.advance()
            self.book.poll()
        self.assertNotIn(condor.key, self.book.account("alice").holdings,
                         "the condor was never sold at its conservative bid 0.92: every close waits for a bid on the no-bid wing")


class StaleLegAtTheFill(shadow.ShadowCase):
    """MAJOR: the fill reads no quote age. The book judges the structure's quote by its stalest leg only when
    the order is CHECKED (`max_option_quote_age_seconds`, 1500 s); `advance` fills on a leg quote of any age as
    long as it is newer than the order's submission, so an order resting all afternoon fills on a wing quote
    printed hours before (the module docstring says the age rule judges the fill: it does not)."""

    def test_no_fill_on_a_leg_quote_older_than_the_books_age_rule(self):
        order = self.buy(SHADOW_VERTICAL, "1", "0.55")
        self.later(1)
        self.legs.touch(occ(580))  # 580 quoted once just after the order, then never again
        self.later(40 * 60)
        self.legs.touch(occ(581))  # 581 quoted now
        self.broker.advance()
        self.assertEqual(self.broker.get_order(order.id).filled_quantity, D(0),
                         "filled on a 2,399-second-old quote of the 580 leg (the book's rule is 1,500 s)")


class CapAtTheFill(shadow.ThroughTheBook):
    """MINOR: the order cap meters a marketable limit at the ASK it saw (`risk.notional_of`), but the shadow
    fills at a LATER ask up to the limit (10% over the ask passes `rule_limit_sanity`): a structure's maximum
    loss then exceeds the rung's $75 order cap the spec says it meters exactly."""

    def test_a_structures_maximum_loss_never_exceeds_the_order_cap(self):
        self.quote_vertical(low=("1.60", "1.70"))  # ask 0.70: $70 counted
        [outcome] = self.book.submit([self.wish("buy", "1", "0.77")])
        self.assertEqual(outcome.status, "resting", outcome.detail)
        self.requote(low=("1.66", "1.77"))  # ask 0.77, within the limit
        held = self.book.account("alice").holdings.get(self.vertical.key)
        paid = held.cost if held is not None else D(0)
        self.assertLessEqual(paid, D(75), f"a structure bought for ${paid} on a $75 order cap")


class ReplayEntryCut(unittest.TestCase):
    """MAJOR (parity): live, the House cancels a RESTING open of a structure expiring today at the 14:30 New
    York cut (`House._cancel_structure_opens_at_cut`); the replay only refuses NEW opens after it, so a 0-DTE
    open placed at 14:15 still fills at 14:45 in the replay: the replay is looser than the House."""

    def test_a_resting_zero_day_open_does_not_fill_after_the_cut(self):
        steps = [sstep("2026-09-25T18:15:00Z", {socc(585): 1.20, socc(586): 0.70}),  # 14:15 NY: rests (ask 0.576 > 0.50)
                 sstep("2026-09-25T18:30:00Z", {socc(585): 1.20, socc(586): 0.70}),  # 14:30: the cut
                 sstep("2026-09-25T18:45:00Z", {socc(585): 1.00, socc(586): 0.65})]  # 14:45: conservative ask 0.416
        r = run_replay(STRUCTURE_STRATEGY, {"legs": VLEGS, "open_at": "2026-09-25T18:15:00Z", "limit": 0.50},
                       stape(steps, VERTICAL), stake=1000.0, limits=SLIMITS, audit=True)
        self.assertTrue(r["ok"], r)
        self.assertEqual([f for f in r["fill_log"] if f["side"] == "buy"], [],
                         "the replay filled a 0-DTE open after 14:30 New York that the House would have cancelled at the cut")


class ParseParity(unittest.TestCase):
    """MINOR (parity): a leg spelled with a malformed expiry is a `RejectedOrder` (a RuntimeError) in the
    House's `structures.parse` and a `ValueError` in the box's `structure_core.parse`: the House drops the row
    (`_intents` catches Exception) while the replay counts a refusal, and `test_structure_parity`'s
    `outcome()` catches ValueError only, so it cannot pin this case."""

    def test_the_same_malformed_leg_is_the_same_error_in_both(self):
        row = {"structure": "debit_vertical", "action": "open", "quantity": 1, "limit_price": 0.3, "reason": "x",
               "legs": [{"symbol": "SPY", "expiry": "2026-9-28", "strike": "580", "right": "call", "role": "long"},
                        {"occ": "SPY260928C00581000", "role": "short"}]}
        with self.assertRaises(ValueError):
            core.parse(row, venue=V)
        with self.assertRaises(ValueError):
            structures.parse(V, row)


class HoldsAsClaimed(shadow.ShadowCase):
    """Checked and holding: the book's fee model and the account agree to the cent for four contracts a unit."""

    def test_fees_agree_for_a_condor_of_four_and_a_ratio_two_butterfly(self):
        fees = Fees("alpaca", option_clearing=True)
        for spec_, quantity, expected in ((CONDOR, "4", "0.80"), (BUTTERFLY, "3", "0.60"), (SHADOW_VERTICAL, "7", "0.70")):
            inst = structures.instrument(spec_, V)
            self.assertEqual(fees.charge(inst, "buy", D(quantity), D("0.50")).usd, D(expected))
            self.assertEqual(self.broker._fee(spec_, D(quantity)), D(expected))
        single = structures.instrument(SHADOW_VERTICAL, V)
        self.assertEqual(Fees("alpaca", option_clearing=True).charge(
            structures.spec_of(single).legs[0].instrument, "buy", D(4), D("0.5")).usd, D("0.10"))  # a single contract: as before

    def test_the_entry_cut_is_the_same_minute_in_the_book_and_the_house(self):
        from league.book import _structure_entry_refusal

        self.assertIsNone(_structure_entry_refusal("2026-09-25", "2026-09-25T18:29:59Z"))
        self.assertIsNotNone(_structure_entry_refusal("2026-09-25", "2026-09-25T18:30:00Z"))
        self.assertIsNone(_structure_entry_refusal("2026-09-28", "2026-09-25T19:59:00Z"))
        self.assertEqual(epoch("2026-09-25T18:30:00Z") - epoch("2026-09-25T18:29:59Z"), 1)


if __name__ == "__main__":
    unittest.main()
