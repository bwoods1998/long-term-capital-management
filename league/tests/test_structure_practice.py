"""Structures on the owner's Alpaca practice account (Wave 2 of the options desk, Sept 25, 2026).

Track P built the adapter (`ltcm/adapters/alpaca.py`: one multi-leg order, its legs read back as ONE fill
of the held structure) and the structure-aware book (`league/book.py`: the venue's legs folded into the
structures held, a broken structure closed at once). This module pins what Wave 2 adds on top and what
the owner asked to see before the switch is flipped:

- The switch, `league/config.json` `options_structures.practice_account`, and the routing it drives
  (`House._structure_target`): a structure agent trades on `alpaca-paper` only when its program's
  `PARAMS["structure"]` is a type that account opens (the five Alpaca closes as ONE covered order);
  every other structure agent stays on the options shadow book.
- The migration (`House._structure_move`): an agent holding structures on its old book keeps trading
  there until it is flat (opens through one full session, then closes only), and is then re-seated, its
  stake moved, on the new book; never positions or orders on two books.
- The whole path House -> adapter -> book over a fake of the practice account in Alpaca's documented
  shapes (`Venue`, P2's `FakeAlpaca` with the account's type, FILL activities per leg and legs filled
  one at a time): per-leg fills, a partial fill, a late leg, a restart mid-order, a broken structure,
  an unmatched short leg, the expiry-day close, and the owner's record of the venue's answers.
- Cash: every Alpaca account adds a credit to cash (Alpaca has no cash accounts; its 1x account, what the
  owner calls cash, is a limited margin account), so the book offsets the open credit structures'
  collateral on both; the real account refuses a credit structure before anything is sent unless
  `allocator.option_spread_real_types` admits it, and a venue that set the loss aside instead would be
  named to the cent, never booked.
- The review of Wave 2 (Sept 25, 2026): a break writes off only the structures short of their own leg,
  as few as cover it; a leg in flight is never adopted; an order whose legs stand uneven is cancelled;
  a moving agent keeps one full session of opens whatever day the switch is flipped.

No test order was sent anywhere: every venue here is a fake.
"""

import dataclasses
import math
import unittest
import urllib.parse
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from unittest import mock

from league import structures
from league.book import ADOPT_AFTER, Book, Intent, Limits
from league.fees import Fees
from league.ledger import HOUSE, Ledger
from league.tests.fakes import Clock, FakeBroker, iso, without_real_entry_rules
from league.tests.test_options import STRUCTURE_AGENT, THURSDAY_11_NY, StructureHouseCase, condor_row, occ
from league.tests.test_structure_book import FakeAlpaca

D = Decimal
PRACTICE = "alpaca-paper"
SHADOW = "options-shadow"
#: The condor's legs (Friday Sept 11, 2026 expiry) and their touches: opened at the ask it is held at
#: 1 + 0.11 + 0.13 - 0.29 - 0.34 = 0.61 (a 0.39 credit); its bid is 1 + 0.09 + 0.11 - 0.31 - 0.36 = 0.53.
LEGS = {occ("2026-09-11", "put", 580): ("0.09", "0.11"), occ("2026-09-11", "put", 581): ("0.29", "0.31"),
        occ("2026-09-11", "call", 590): ("0.34", "0.36"), occ("2026-09-11", "call", 591): ("0.11", "0.13")}
#: A call debit vertical on the same expiry: long 585 at 0.62 ask, short 586 at 0.20 bid, 0.42 to open.
VERTICAL_LEGS = {occ("2026-09-11", "call", 585): ("0.60", "0.62"), occ("2026-09-11", "call", 586): ("0.20", "0.22")}


def vertical_row(*, action="open", limit=0.45, quantity=1):
    legs = [{"occ": occ("2026-09-11", "call", 585), "role": "long"}, {"occ": occ("2026-09-11", "call", 586), "role": "short"}]
    return {"structure": "debit_vertical", "action": action, "quantity": quantity, "limit_price": limit, "legs": legs,
            "reason": "a test vertical"}


def agent_code(kind):
    """A structure agent whose program names `kind` (None: names no type at all)."""
    params = "{}" if kind is None else f'{{"structure": "{kind}", "width": 1.0}}'
    return STRUCTURE_AGENT.replace('PARAMS = {"structure": "iron_condor", "width": 1.0}', f"PARAMS = {params}")


class Venue(FakeAlpaca):
    """P2's fake practice account (`FakeAlpaca`: a multi-leg order fills every leg at once when its signed net
    meets the touches, a credit ADDS to cash, positions one row a contract, orders read back nested) with what
    Wave 2 needs besides: the account's `multiplier` and `options_trading_level` on `GET /v2/account`
    (https://docs.alpaca.markets/reference/getaccount-1); one FILL activity per leg, carrying the LEG's order id
    (the docs do not say which id a leg's FILL carries; the adapter reads both); legs filled one at a time
    (`fill_legs`); and a venue that sets a credit structure's maximum loss aside from cash (`sets_aside`), the
    spec's model of a cash account, which Alpaca's documentation says none of its accounts is: kept to show the
    book names that difference exactly, never books it."""

    def __init__(self, clock, *, multiplier="4", level="3", sets_aside=False):
        super().__init__(clock)
        self.multiplier, self.level, self.sets_aside = multiplier, level, sets_aside
        self.activities: list[dict] = []
        self.n_activity = 0

    def __call__(self, method, url, body):
        path = urllib.parse.urlsplit(url).path
        if path == "/v2/account":
            row = super().__call__(method, url, body)
            if self.multiplier is not None:
                row["multiplier"] = self.multiplier
            if self.level is not None:
                row["options_trading_level"] = self.level
            return row
        if path == "/v2/account/activities/FILL":
            return list(self.activities)
        if method == "DELETE" and path.startswith("/v2/orders/"):
            order = self.orders[path.rsplit("/", 1)[1]]
            if order["status"] in ("filled", "canceled"):
                return (422, {}, b'{"message": "order is not cancelable"}')
            order["status"] = "canceled"  # Alpaca cancels a multi-leg order whole: its unfilled legs with it
            for leg in order.get("legs") or []:
                if leg["status"] != "filled":
                    leg["status"] = "canceled"
            return (204, {}, b"")
        if path.startswith("/v2/account/activities"):
            return []
        return super().__call__(method, url, body)

    @staticmethod
    def collateral(legs):
        """K of a credit structure: its widest wing (a vertical's width, a condor's wider side)."""
        from ltcm.adapters.alpaca import instrument_for

        wings = {}
        for leg in legs:
            inst = instrument_for({"symbol": leg["symbol"], "asset_class": "us_option"})
            wings.setdefault(inst.right, []).append(inst.strike)
        return max((max(s) - min(s) for s in wings.values() if len(s) > 1), default=D(0))

    def place(self, body):
        cash_before = self.cash
        row = super().place(body)
        legs = row.get("legs") or []
        if row.get("status") == "filled":
            for leg in legs:
                self.activity(row, leg, D(leg["filled_qty"]), D(leg["filled_avg_price"]))
            if self.sets_aside and body.get("order_class") == "mleg":
                opening = legs[0]["position_intent"].endswith("_to_open")
                credit = (self.cash - cash_before) > 0 if opening else (self.cash - cash_before) < 0
                if credit:
                    held = self.collateral(legs) * 100 * D(body["qty"])
                    self.cash += -held if opening else held
        return row

    def activity(self, order, leg, qty, price):
        self.n_activity += 1
        self.activities.append({"id": f"20260910150000000::act-{self.n_activity}", "activity_type": "FILL", "type": "fill",
                                "order_id": leg["id"], "symbol": leg["symbol"], "side": leg["side"], "qty": str(qty),
                                "price": str(price), "cum_qty": leg["filled_qty"], "leaves_qty": str(D(leg["qty"]) - D(leg["filled_qty"])),
                                "transaction_time": iso(self.clock), "order_status": leg["status"]})

    def fill_legs(self, order_id, contracts):
        """Fill `contracts[symbol]` more contracts of the named legs of a resting multi-leg order, each at its touch."""
        order = self.orders[order_id]
        for leg in order["legs"]:
            more = D(contracts.get(leg["symbol"], 0))
            if not more:
                continue
            bid, ask = self.quotes[leg["symbol"]]
            price = ask if leg["side"] == "buy" else bid
            done = D(leg["filled_qty"]) + more
            leg.update(filled_qty=str(done), filled_avg_price=str(price), status="filled" if done >= D(leg["qty"]) else "partially_filled")
            signed = more if leg["side"] == "buy" else -more
            self.held[leg["symbol"]] = self.held.get(leg["symbol"], D(0)) + signed
            self.cash += -signed * price * 100 - self.fee(more)
            self.activity(order, leg, more, price)
        whole = min(D(leg["filled_qty"]) / D(leg["ratio_qty"]) for leg in order["legs"])
        order["filled_qty"] = str(int(whole))
        order["status"] = "filled" if all(leg["status"] == "filled" for leg in order["legs"]) else "partially_filled"


class PracticeCase(StructureHouseCase):
    """A House whose `alpaca-paper` book is the real Alpaca adapter over `Venue` (the practice account, margin,
    options level 3), beside the options shadow book, in the session on Thursday Sept 10, 2026, 11:00 New York."""

    def new_house(self, **kw):
        from league.economy import load_game
        from league.house import House, Settings
        from league.sandbox import LocalSandbox
        from ltcm.adapters import AlpacaCredentials
        from ltcm.adapters.alpaca import AlpacaBroker
        from ltcm.tests.fakes import FakeTransport

        game = load_game()
        game["economy"]["min_population"] = 0
        game["economy"]["newcomer_seconds"] = 10 ** 9
        kw.setdefault("game", game)
        if not hasattr(self, "venue"):
            self.venue = Venue(self.clock)
            for symbol, (bid, ask) in {**LEGS, **VERTICAL_LEGS}.items():
                self.venue.quotes[symbol] = (D(bid), D(ask))
        self.shadow = FakeBroker(SHADOW)
        # As `league.venues.gateway_broker` builds it: placeholder credentials, `paper` False, the venue's name.
        self.alpaca = AlpacaBroker(AlpacaCredentials("gateway", "gateway", paper=False), transport=FakeTransport(default=self.venue),
                                   venue=PRACTICE)
        house = House(
            Path(self.dir.name) / "house", brokers={PRACTICE: self.alpaca, "alpaca": FakeBroker("alpaca", cash="500"), SHADOW: self.shadow},
            sandbox=LocalSandbox(Path(self.dir.name) / "boxes"), alpaca_data=self.data, clock=self.clock,
            settings=Settings(mark_every_seconds=0, research=False), **kw,
        )
        house.structure_book_name = SHADOW
        return house

    def setUp(self):
        super().setUp()
        self._rules = without_real_entry_rules()
        self._rules.start()
        self.addCleanup(self._rules.stop)
        self.practice = self.house.books[PRACTICE]
        self.assertTrue(self.practice.reconcile().ok)

    # -- helpers
    def switch(self, on=True):
        self.house.structure_practice_account = on

    def agent(self, kind="iron_condor", name="krasker"):
        return self.house.spawn(name.replace("_", "-"), f"options-{str(kind).replace('_', '-')}-test", agent_code(kind), reason="test",
                                specialty="alpaca-options")

    def send(self, agent, rows, book=None):
        """What a wake does with the agent's decision: the House's intents, submitted on the book it trades on."""
        book = book or self.house.book_of(agent)
        intents, dropped = self.house._intents(agent, book, rows)
        self.assertEqual(dropped, [])
        outcome = {"agent": agent.id, "_generation": self.house._generation(agent.id), "intents": intents}
        return self.house._submit_wakes(book.name, [outcome])

    def fills(self, agent, book=PRACTICE):
        return [e.payload for e in self.house.ledger.iter(kinds="book.fill", agent=agent.id) if e.payload.get("book") == book]

    def alerts(self):
        return [e.payload for e in self.house.ledger.iter(kinds="ops.alert")]

    def held(self, book, agent):
        return {k: h.quantity for k, h in book.account(agent.id).holdings.items() if h.quantity}

    def mleg_posts(self):
        return [b for b in self.venue.posted if b.get("order_class") == "mleg"]


class TheSwitch(PracticeCase):
    """`options_structures.practice_account`: off unless it is a literal true; on, routing by the program's type."""

    def test_the_switch_is_off_unless_the_config_says_true(self):
        from league import house as house_module

        for config, on in (({}, False), ({"options_structures": {"book": SHADOW}}, False),
                           ({"options_structures": {"practice_account": "true"}}, False),
                           ({"options_structures": {"practice_account": 1}}, False),
                           ({"options_structures": {"practice_account": True}}, True)):
            with self.subTest(config=config):
                self.house.structure_practice_account = None
                with mock.patch.object(house_module.json, "loads", return_value=config):
                    self.assertIs(self.house._structure_practice_account(), on)
        self.house.structure_practice_account = None
        with mock.patch.object(house_module.Path, "read_text", side_effect=OSError("unreadable")):
            self.assertFalse(self.house._structure_practice_account())

    def test_the_repository_ships_it_off(self):
        import json

        config = json.loads((Path(__file__).resolve().parents[1] / "config.json").read_text(encoding="utf-8"))
        self.assertIs(config["options_structures"]["practice_account"], False)
        self.assertEqual(config["options_structures"]["book"], SHADOW)

    def test_off_every_structure_agent_trades_on_the_shadow_book(self):
        self.switch(False)
        for kind in ("iron_condor", "debit_vertical", "calendar"):
            self.assertIs(self.house.book_of(self.agent(kind, name=f"k-{kind}")), self.house.books[SHADOW])

    def test_on_the_five_types_the_practice_account_closes_as_one_order_go_there_and_the_rest_stay(self):
        self.switch(True)
        where = {}
        for kind in list(structures.TYPES) + [None]:
            agent = self.agent(kind, name=f"k-{kind or 'none'}")
            where[kind] = self.house.book_of(agent).name
        self.assertEqual({k for k, v in where.items() if v == PRACTICE},
                         {"debit_vertical", "credit_vertical", "iron_condor", "iron_butterfly", "long_butterfly"})
        self.assertEqual({k for k, v in where.items() if v == SHADOW},
                         {"calendar", "diagonal", "long_straddle", "long_strangle", None})

    def test_a_practice_account_whose_venue_holds_no_legs_is_never_the_target(self):
        """A canary's simulated account (`SimBroker`) holds no legs: the switch sends nobody there."""
        self.switch(True)
        agent = self.agent("iron_condor")
        with mock.patch.object(self.practice, "_legs_at_venue", return_value=False):
            self.assertIs(self.house.book_of(agent), self.house.books[SHADOW])

    def test_an_account_that_reads_as_cash_keeps_credit_programs_on_the_shadow_book(self):
        self.venue.multiplier = "1"
        self.alpaca._account = None
        self.practice.reconcile()
        self.assertEqual(self.alpaca.account_type(), "cash")
        self.switch(True)
        self.assertIs(self.house.book_of(self.agent("iron_condor", name="k-condor")), self.house.books[SHADOW])
        self.assertIs(self.house.book_of(self.agent("debit_vertical", name="k-vertical")), self.practice)

    def test_an_account_under_options_level_3_opens_nothing_and_keeps_every_program_on_the_shadow_book(self):
        self.venue.level = "2"
        self.alpaca._account = None
        self.practice.reconcile()
        self.assertEqual(self.alpaca.structure_types, ())
        self.switch(True)
        self.assertIs(self.house.book_of(self.agent("debit_vertical")), self.house.books[SHADOW])

    def test_the_wake_says_which_book(self):
        self.switch(True)
        agent = self.agent("iron_condor")
        self.house.seat(agent)
        ctx = self.house.snapshot(agent, self.house.book_of(agent))
        self.assertEqual(ctx["structure_rules"]["book"], PRACTICE)
        self.assertNotIn("moving_to", ctx["structure_rules"])


class TheMigration(PracticeCase):
    """An agent seated on the options shadow book when the switch turns on keeps trading there until it is flat
    (opens for a day, then closes only); then it is re-seated, its stake moved, on the practice account. Never
    positions or orders on two books at once."""

    def condor_on_the_shadow_book(self):
        self.switch(False)
        agent = self.agent("iron_condor")
        shadow = self.house.books[SHADOW]
        self.assertIs(self.house.book_of(agent), shadow)
        self.house.seat(agent)
        inst = structures.instrument(structures.parse(SHADOW, condor_row()).spec, SHADOW)
        self.shadow.set_quote(inst, "0.55", "0.62")
        self.assertEqual([o.status for o in self.send(agent, [condor_row()])], ["filled"])
        return agent, shadow, inst

    def assert_one_book(self, agent):
        """Never positions or orders on two books at once."""
        busy = [name for name, book in self.house.books.items() if self.house._structure_busy(book, agent.id)]
        self.assertLessEqual(len(busy), 1, busy)

    def test_it_closes_on_the_shadow_book_then_moves_when_flat(self):
        agent, shadow, inst = self.condor_on_the_shadow_book()
        self.switch(True)
        # 1. Holding a condor on the shadow book: it stays there, and says where it is going.
        self.assertIs(self.house.book_of(agent), shadow)
        self.house.seat(agent)
        self.assertNotIn(agent.id, self.practice.accounts)  # nothing staked on the practice account yet
        ctx = self.house.snapshot(agent, shadow)
        self.assertEqual(ctx["structure_rules"]["book"], SHADOW)
        self.assertIn("alpaca-paper", ctx["structure_rules"]["moving_to"])
        # This fake venue serves an empty chain, so the wake's reach (g/loop: a structure opens only on legs among the 160
        # nearest the money its wake was shown) would refuse the condor: this test is about the move, not the reach.
        self.house._structure_reach_seen.pop(agent.id, None)
        # 2. For a day it keeps trading there, opens included; nothing reaches the practice account.
        opens, _ = self.house._intents(agent, shadow, [condor_row(expiry="2026-09-14")])
        self.assertEqual([i.instrument.venue for i in opens], [SHADOW])
        self.assertEqual(self.venue.posted, [])
        self.assert_one_book(agent)
        # Through the close of the first full session after the first wake that found it moving (Thursday's), its
        # opens still go there: Friday 11:05 New York (`test_after_one_full_session_it_only_closes_there`).
        self.at(THURSDAY_11_NY + 86400 + 300)
        self.house.seat(agent)
        opens, _ = self.house._intents(agent, shadow, [condor_row(expiry="2026-09-14")])
        self.assertEqual([i.instrument.venue for i in opens], [SHADOW])
        self.assertEqual(self.venue.posted, [])
        # 3. A close rests there (0.60 over the 0.55 bid): still not flat, still there.
        rested = self.send(agent, [condor_row(action="close", limit=0.40)])
        self.assertEqual([o.status for o in rested], ["resting"])
        self.assertIs(self.house.book_of(agent), shadow)
        self.assert_one_book(agent)
        # 4. It fills: flat on the shadow book. The next seat (every wake seats) moves the stake.
        self.shadow.fill_resting(rested[0].order_id, "1")
        shadow.poll()
        self.assertEqual(self.held(shadow, agent), {})
        self.assertIs(self.house.book_of(agent), self.practice)
        self.house.seat(agent)
        self.assertTrue(shadow.account(agent.id).swept)
        self.assertEqual(shadow.account(agent.id).cash, 0)
        self.assertEqual(self.practice.account(agent.id).cash, D("200"))  # the rung's practice stake
        stakes = [(e.payload["book"], e.payload.get("note")) for e in self.house.ledger.iter(kinds="book.stake", agent=agent.id)]
        self.assertIn((SHADOW, "account closed"), stakes)
        self.assertEqual(stakes[-1], (PRACTICE, "rung 1 stake"))
        self.assertTrue(any("moved from options-shadow to alpaca-paper" in str(a) for a in self.alerts()))
        self.assertNotIn(agent.id, self.house._state.get("structure_moving") or {})
        # 5. Its next open goes to the practice account as ONE multi-leg order.
        self.assertEqual([o.status for o in self.send(agent, [condor_row()])], ["filled"])
        self.assertEqual(len(self.mleg_posts()), 1)
        self.assert_one_book(agent)
        self.assertEqual(shadow.account(agent.id).holdings, {})

    def test_after_one_full_session_it_only_closes_there(self):
        agent, shadow, inst = self.condor_on_the_shadow_book()
        self.switch(True)
        self.house.seat(agent)  # Thursday 11:00 New York: found moving
        self.at(THURSDAY_11_NY + 4 * 86400 - 5100)  # Monday 09:35 New York: Friday's full session has closed
        self.house.seat(agent)
        self.assertIs(self.house.book_of(agent), shadow)
        self.assertEqual(self.house._intents(agent, shadow, [condor_row(expiry="2026-09-14")])[0], [])
        refused = [e.payload["reasons"][0] for e in self.house.ledger.iter(kinds="book.refused", agent=agent.id)]
        self.assertIn("after a full session of trading on here it closes what it holds on options-shadow", refused[-1])
        closing, _ = self.house._intents(agent, shadow, [condor_row(action="close", limit=0.40)])
        self.assertEqual([i.side for i in closing], ["sell"])  # a close is never refused for the move
        self.assertEqual(self.venue.posted, [])

    def test_a_weekend_flip_leaves_a_full_session_of_opens_on_the_old_book(self):
        """The review of Wave 2 (Sept 25, 2026), its demonstration kept as the regression: Deploy G with the switch on in
        Saturday's 07:00Z slot, the agent's wakes seating it every 15 minutes all weekend. Counted as a day of wall clock
        from the first wake, its opens on the old book ran out on Sunday, and on Monday an agent still holding (krasker-22,
        a CCL condor to Oct 2) could open on neither book. Counted in sessions, Monday is its session there."""
        self.switch(False)
        agent = self.agent("iron_condor", name="k22")
        shadow = self.house.books[SHADOW]
        self.house.seat(agent)
        held = condor_row(expiry="2026-09-18")
        self.shadow.set_quote(structures.instrument(structures.parse(SHADOW, held).spec, SHADOW), "0.55", "0.62")
        self.assertEqual([o.status for o in self.send(agent, [held])], ["filled"])
        self.switch(True)
        for hours in range(40, 40 + 48, 1):  # Saturday 07:00Z onward: seated through the weekend
            self.at(THURSDAY_11_NY + hours * 3600)
            self.house.seat(agent)
        self.assertIs(self.house.book_of(agent), shadow)
        other = condor_row(expiry="2026-09-18", limit=0.40)
        other["legs"] = [{"occ": occ("2026-09-18", "put", 575), "role": "long"}, {"occ": occ("2026-09-18", "put", 576), "role": "short"},
                         {"occ": occ("2026-09-18", "call", 595), "role": "short"}, {"occ": occ("2026-09-18", "call", 596), "role": "long"}]
        self.at(THURSDAY_11_NY + 4 * 86400 - 5100)  # Monday Sept 14, 09:35 New York: the first session since the flip
        self.house.seat(agent)
        opens, _ = self.house._intents(agent, shadow, [other])
        self.assertEqual([i.instrument.venue for i in opens], [SHADOW])
        self.at(THURSDAY_11_NY + 5 * 86400 - 5100)  # Tuesday 09:35 New York: Monday's session has closed
        self.assertEqual(self.house._intents(agent, shadow, [other])[0], [])
        refused = [e.payload["reasons"][0] for e in self.house.ledger.iter(kinds="book.refused", agent=agent.id)]
        self.assertIn("after a full session of trading on here", refused[-1])
        self.assertEqual(self.venue.posted, [])

    def test_the_window_is_the_close_of_the_first_full_session_after_the_stamp(self):
        from ltcm.data import to_datetime

        until = self.house._structure_move_opens_until
        for stamp, close in (("2026-09-10T15:00:00Z", "2026-09-11T20:00:00Z"),   # Thursday in session: Friday's close
                             ("2026-09-11T19:00:00Z", "2026-09-14T20:00:00Z"),   # Friday's last hour: Monday's close
                             ("2026-09-12T07:00:00Z", "2026-09-14T20:00:00Z"),   # Saturday: Monday's close
                             ("2026-11-25T15:00:00Z", "2026-11-27T18:00:00Z")):  # before Thanksgiving: Friday's early close
            with self.subTest(stamp=stamp):
                self.assertEqual(until(to_datetime(stamp).timestamp()), to_datetime(close).timestamp())

    def test_a_decision_made_for_the_old_book_is_dropped_once_it_has_moved(self):
        agent, shadow, inst = self.condor_on_the_shadow_book()
        self.switch(True)
        closing, _ = self.house._intents(agent, shadow, [condor_row(action="close", limit=0.50)])  # decided on the shadow book
        self.shadow.set_quote(inst, "0.61", "0.66")
        own = shadow.submit(self.house._intents(agent, shadow, [condor_row(action="close", limit=0.39)])[0])  # flat meanwhile
        self.assertEqual([o.status for o in own], ["filled"])
        self.assertIs(self.house.book_of(agent), self.practice)
        late = {"agent": agent.id, "_generation": self.house._generation(agent.id), "intents": closing}
        self.assertEqual(self.house._submit_wakes(SHADOW, [late]), [])  # `_submit_wakes`: not its book any more

    def test_a_structure_order_resting_on_the_old_book_is_not_flat(self):
        self.switch(False)
        agent = self.agent("iron_condor")
        self.house.seat(agent)
        inst = structures.instrument(structures.parse(SHADOW, condor_row()).spec, SHADOW)
        self.shadow.set_quote(inst, "0.55", "0.66")
        self.assertEqual([o.status for o in self.send(agent, [condor_row()])], ["resting"])  # 0.62 under the 0.66 ask
        self.switch(True)
        self.assertIs(self.house.book_of(agent), self.house.books[SHADOW])
        self.house.books[SHADOW].cancel(agent.id, self.house.books[SHADOW].open_orders(agent.id)[0].order_id)
        self.assertIs(self.house.book_of(agent), self.practice)

    def test_turned_off_it_moves_back_the_same_way(self):
        self.switch(True)
        agent = self.agent("iron_condor")
        self.house.seat(agent)
        self.assertEqual([o.status for o in self.send(agent, [condor_row()])], ["filled"])
        self.switch(False)  # a config-only release sets it false (never a rollback past this code)
        self.assertIs(self.house.book_of(agent), self.practice)
        self.house.seat(agent)
        self.assertIn(agent.id, self.house._state["structure_moving"])
        self.assertEqual([o.status for o in self.send(agent, [condor_row(action="close", limit=0.47)])], ["filled"])
        self.assertIs(self.house.book_of(agent), self.house.books[SHADOW])
        self.house.seat(agent)
        self.assertTrue(self.practice.account(agent.id).swept)
        self.assertEqual(self.house.books[SHADOW].account(agent.id).cash, D("200"))
        self.assertTrue(self.practice.reconcile().ok)


class TheRecordAcrossTheMove(PracticeCase):
    """The adversarial review of Deploy G (Sept 25, 2026): after the move an agent's practice record stays on the book it
    left, and the House read only the book it moved to. An agent with closed structures there then had "no record to
    protect" and rewrote itself in place (the allocator pools both books, so the new program carried the old one's
    W_paper); its standing lost its blocks; and its death clock started again. Each now reads both books."""

    def closed_condor_then_moved(self):
        """A condor opened and closed (at a loss) on the options shadow book, then the switch: moved, flat, swept."""
        self.switch(False)
        agent = self.agent("iron_condor")
        shadow = self.house.books[SHADOW]
        self.house.seat(agent)
        inst = structures.instrument(structures.parse(SHADOW, condor_row()).spec, SHADOW)
        self.shadow.set_quote(inst, "0.55", "0.62")
        self.assertEqual([o.status for o in self.send(agent, [condor_row()])], ["filled"])
        self.shadow.set_quote(inst, "0.61", "0.66")
        self.assertEqual([o.status for o in self.send(agent, [condor_row(action="close", limit=0.39)])], ["filled"])
        self.assertEqual(self.held(shadow, agent), {})
        self.assertFalse(self.house.record_is_empty(agent))
        self.switch(True)
        self.assertIs(self.house.book_of(agent), self.practice)
        self.house.seat(agent)
        self.assertTrue(shadow.account(agent.id).swept)
        self.assertEqual(self.practice.account(agent.id).cash, D("200"))
        return agent

    def blocks(self, agent, book, growth, n):
        """`n` finished active day blocks of `growth` each on `book`, begun after the agent entered its rung."""
        entered = self.house.evaluator._rung_entered(agent.id)
        for _ in range(n):
            self.n_blocks = getattr(self, "n_blocks", 0) + 1
            seq = entered + self.n_blocks
            self.house.ledger.append("eval.block", {"book": book, "key": f"day-{self.n_blocks}", "horizon": "day", "start_equity": 200.0,
                                                    "end_equity": 200.0 * math.exp(growth), "flow": 0.0, "log_growth": growth, "active": True,
                                                    "exposure": 0.5, "first_mark_seq": seq, "last_mark_seq": seq},
                                     agent=agent.id, id=f"block:{agent.id}:{book}:day-{self.n_blocks}")

    def moved(self, name="krasker"):
        """A structure agent seated on the shadow book, then moved flat to the practice account."""
        self.switch(False)
        agent = self.agent("iron_condor", name=name)
        self.house.seat(agent)
        return agent

    def move(self, agent):
        self.switch(True)
        self.house.seat(agent)
        self.assertIs(self.house.book_of(agent), self.practice)
        self.assertTrue(self.house.books[SHADOW].account(agent.id).swept)

    def test_a_moved_agent_with_closed_structures_on_the_book_it_left_does_not_rewrite_in_place(self):
        agent = self.closed_condor_then_moved()
        # Before the review this was True: alpaca-paper, the book of its rung now, is empty.
        self.assertEqual(self.house.evaluator.trade_returns(agent.id, PRACTICE)[0], [])
        self.assertFalse(self.house.record_is_empty(agent))
        self.assertEqual([b.name for b in self.house._record_books(agent)], [PRACTICE, SHADOW])

    def test_a_moved_agent_with_no_record_still_rewrites_in_place(self):
        agent = self.moved()
        self.assertTrue(self.house.record_is_empty(agent))
        self.move(agent)
        self.assertTrue(self.house.record_is_empty(agent))

    def test_its_standing_reads_its_blocks_on_both_books(self):
        agent = self.moved()
        self.blocks(agent, SHADOW, 0.01, 4)
        self.move(agent)
        self.blocks(agent, PRACTICE, 0.02, 1)
        row = self.house.standing_of(agent.id)
        self.assertEqual(row["active_blocks"], 5)  # 1 on alpaca-paper alone, before the review
        self.assertAlmostEqual(row["mean_growth"], 0.012)

    def test_its_death_clock_does_not_start_again_on_the_new_book(self):
        agent = self.moved()
        self.blocks(agent, SHADOW, -0.02, 5)  # down 9.5% after 5 active blocks: paper death is 10% from 6
        self.move(agent)
        self.blocks(agent, PRACTICE, -0.02, 1)  # 6 active blocks in all, down 11.3%
        self.assertEqual(self.house.evaluator.judge(agent.id, PRACTICE).decision, "hold")  # its new book alone
        verdict = self.house.judge(agent)
        self.assertEqual(verdict.decision, "die")
        self.assertIn("down 11.3% on paper after 6 active blocks", verdict.reason)
        self.assertIn("over alpaca-paper and options-shadow", verdict.reason)
        self.assertEqual(verdict.numbers["books"], [PRACTICE, SHADOW])
        self.assertFalse(self.house.registry.get(agent.id).alive)

    def test_a_winner_that_moved_is_not_judged_on_what_it_left(self):
        agent = self.moved()
        self.blocks(agent, SHADOW, 0.01, 5)
        self.move(agent)
        self.blocks(agent, PRACTICE, -0.02, 1)
        self.assertIsNone(self.house._moved_record_death(agent, self.practice, 1))
        self.assertNotEqual(self.house.judge(agent).decision, "die")
        self.assertTrue(self.house.registry.get(agent.id).alive)

    def test_an_agent_that_never_moved_is_judged_by_the_evaluator_alone(self):
        agent = self.moved()
        self.blocks(agent, SHADOW, -0.02, 5)
        self.assertEqual([b.name for b in self.house._record_books(agent)], [SHADOW])
        self.assertIsNone(self.house._moved_record_death(agent, self.house.books[SHADOW], 1))


class TheBooksAStructureMayTradeOn(PracticeCase):
    """The review of Deploy G (Sept 25, 2026): a misnamed `options_structures.book` could put a rung-1 structure agent's
    structures on the owner's real account; and a `structure_moving` stamp outlived a promotion or a death."""

    def test_the_config_may_name_only_a_practice_book(self):
        from league import house as house_module

        for named, book in (("alpaca", SHADOW), ("kalshi-shadow", SHADOW), ("nonsense", SHADOW), (PRACTICE, PRACTICE), (SHADOW, SHADOW)):
            with self.subTest(named=named):
                self.house.structure_book_name = None
                with mock.patch.object(house_module.json, "loads", return_value={"options_structures": {"book": named}}):
                    self.assertEqual(self.house._structure_book_name(), book)
        self.assertTrue(any("options_structures.book names alpaca, which is not a practice book" in a.get("text", "")
                            for a in self.alerts()))

    def test_a_real_book_named_directly_is_the_shadow_book_too(self):
        """The review's demonstration (`structure_book_name` set to the real book's name): no rung-1 agent is staked there."""
        self.house.structure_book_name = "alpaca"
        agent = self.agent("debit_vertical")
        self.assertEqual(self.house._structure_book_name(), SHADOW)
        self.assertIs(self.house.book_of(agent), self.house.books[SHADOW])

    def test_a_moving_stamp_goes_when_it_dies(self):
        """(Its promotion: `test_real_structures.TheReviewOfDeployG`, on a House with a real book.)"""
        self.switch(False)
        agent = self.agent("iron_condor")
        self.house.seat(agent)
        inst = structures.instrument(structures.parse(SHADOW, condor_row()).spec, SHADOW)
        self.shadow.set_quote(inst, "0.55", "0.62")
        self.assertEqual([o.status for o in self.send(agent, [condor_row()])], ["filled"])
        self.switch(True)
        self.house.seat(agent)  # holding on the shadow book: moving
        self.assertIn(agent.id, self.house._state["structure_moving"])
        self.house.kill(agent, "evidence", "a test: killed while moving")
        self.assertNotIn(agent.id, self.house._state["structure_moving"])


class EndToEnd(PracticeCase):
    """House -> adapter -> book over the fake practice account (margin, level 3)."""

    def seated(self, kind="iron_condor"):
        self.switch(True)
        agent = self.agent(kind)
        self.assertIs(self.house.book_of(agent), self.practice)
        self.house.seat(agent)
        return agent

    def test_a_condor_opens_and_closes_as_one_order_each_way_and_reconciles_to_the_cent_on_margin(self):
        agent = self.seated()
        opened = self.send(agent, [condor_row()])
        self.assertEqual([o.status for o in opened], ["filled"], opened[0].detail)
        body = self.venue.posted[-1]
        self.assertEqual((body["order_class"], body["qty"], body["limit_price"], body["time_in_force"]), ("mleg", "1", "-0.38", "day"))
        self.assertEqual(sorted((l["symbol"], l["side"], l["position_intent"]) for l in body["legs"]),
                         sorted([(occ("2026-09-11", "put", 580), "buy", "buy_to_open"), (occ("2026-09-11", "put", 581), "sell", "sell_to_open"),
                                 (occ("2026-09-11", "call", 590), "sell", "sell_to_open"), (occ("2026-09-11", "call", 591), "buy", "buy_to_open")]))
        holding = self.practice.account(agent.id).holdings
        (key, held), = holding.items()
        self.assertEqual((held.quantity, held.cost), (D(1), D("61.12")))  # 0.61 x 100, four legs' $0.03 clearing fee
        # A margin account ADDS the 0.39 credit to cash; the book debited 0.61: offset by $100 of collateral, exact.
        self.assertEqual(self.alpaca.account_type(), "margin")
        reading = self.practice.reconcile()
        self.assertTrue(reading.ok, reading.detail)
        self.assertEqual(reading.cash_diff, D(0))
        # The owner's record: the account's type, the first order's answer, its fill as the order lists it, and the
        # legs' FILL activities, with which order id they carry.
        answers = {a["structure_answer"]["stage"]: a["structure_answer"] for a in self.alerts() if a.get("structure_answer")}
        self.assertEqual(set(answers), {"account", "submit", "fill", "activity"})
        self.assertEqual(answers["account"]["detail"]["multiplier"], "4")
        self.assertEqual(answers["submit"]["detail"]["sent"]["legs"], body["legs"])
        self.assertEqual(len(answers["fill"]["detail"]["legs"]), 4)
        self.assertEqual(answers["activity"]["detail"]["order_id_is"], ["leg"])
        self.assertEqual(len(answers["activity"]["detail"]["rows"]), 4)
        # The close: one order, a debit (positive) at the buy-back's most.
        closed = self.send(agent, [condor_row(action="close", limit=0.47)])
        self.assertEqual([o.status for o in closed], ["filled"])
        self.assertEqual((self.venue.posted[-1]["order_class"], self.venue.posted[-1]["limit_price"]), ("mleg", "0.47"))
        sales = [f for f in self.fills(agent) if f["side"] == "sell"]
        self.assertEqual(len(sales), 1)  # one closed trade
        self.assertEqual((D(sales[0]["realized"]), sales[0]["flat"]), (D("-8.24"), True))  # (0.53 - 0.61) x 100 - $0.24
        final = self.practice.reconcile()
        self.assertTrue(final.ok, final.detail)
        self.assertEqual(final.cash_diff, D(0))
        self.assertEqual({s: q for s, q in self.venue.held.items() if q}, {})
        # The first answers are kept once a type: the second condor records nothing new but its refusal-free fill.
        stages = [a["structure_answer"]["stage"] for a in self.alerts() if a.get("structure_answer")]
        self.assertEqual(sorted(stages), ["account", "activity", "fill", "submit"])

    def test_each_type_keeps_its_own_first_answers_once(self):
        """The owner asked whether the practice account takes each structure and how it lists per-leg fills: the first
        order of EACH type on the account is recorded (its answer, its fill, its legs' FILL activities), once."""
        condor = self.seated()
        vertical = self.agent("debit_vertical", name="kv")
        self.house.seat(vertical)
        self.assertEqual([o.status for o in self.send(condor, [condor_row()])], ["filled"])
        self.assertEqual([o.status for o in self.send(vertical, [vertical_row()])], ["filled"])
        self.assertEqual([o.status for o in self.send(vertical, [vertical_row(action="close", limit=0.38)])], ["filled"])
        self.at(self.clock() + 60)
        self.assertEqual([o.status for o in self.send(vertical, [vertical_row()])], ["filled"])  # a second order of the type
        self.practice.reconcile()
        kept = sorted((a["structure_answer"]["structure"], a["structure_answer"]["stage"]) for a in self.alerts() if a.get("structure_answer"))
        self.assertEqual(kept, [("debit_vertical", "activity"), ("debit_vertical", "fill"), ("debit_vertical", "submit"),
                                ("iron_condor", "activity"), ("iron_condor", "fill"), ("iron_condor", "submit"), ("margin", "account")])
        rows = {a["structure_answer"]["structure"]: a["structure_answer"]["detail"] for a in self.alerts()
                if (a.get("structure_answer") or {}).get("stage") == "activity"}
        self.assertEqual({len(r["rows"]) for r in rows.values()}, {2, 4})  # one FILL row a leg, each under its leg's id

    def rested(self, agent, row, held):
        orders = self.send(agent, [row])  # under the ask: it rests at the venue
        self.assertEqual([o.status for o in orders], ["resting"], orders[0].detail)
        (order_id,) = [o for o, r in self.venue.orders.items() if r.get("order_class") == "mleg" and r["status"] == "new"]
        self.assertEqual(self.venue.orders[order_id]["limit_price"], held)
        return order_id

    def test_a_partial_fill_and_a_late_leg_book_only_whole_structures_and_never_adopt_a_leg(self):
        agent = self.seated("debit_vertical")
        long_call, short_call = occ("2026-09-11", "call", 590), occ("2026-09-11", "call", 591)
        cheap = {"structure": "debit_vertical", "action": "open", "quantity": 2, "limit_price": 0.24, "reason": "two cheap verticals",
                 "legs": [{"occ": long_call, "role": "long"}, {"occ": short_call, "role": "short"}]}
        order_id = self.rested(agent, cheap, "0.24")  # 0.36 - 0.11 = 0.25 to open: $48 for two at the limit
        # The long leg fills one structure's worth; the short is late. Nothing is booked, nothing broken, and a
        # practice book never adopts the leg ahead however many readings it stands.
        self.venue.fill_legs(order_id, {long_call: 1})
        for _ in range(ADOPT_AFTER + 2):
            self.practice.poll()
            reading = self.practice.reconcile()
            self.assertEqual(self.held(self.practice, agent), {})
        self.assertFalse(reading.ok)  # frozen while the leg is late: the order's legs are in flight
        self.assertIn("positions differ", reading.detail)
        self.assertEqual(self.practice.baseline_positions, {})
        self.assertFalse([a for a in self.alerts() if a.get("structure_break")])
        # The late leg: one whole structure, booked once.
        self.venue.fill_legs(order_id, {short_call: 1})
        self.practice.poll()
        self.assertEqual(list(self.held(self.practice, agent).values()), [D(1)])
        reading = self.practice.reconcile()
        self.assertTrue(reading.ok, reading.detail)
        # The second structure's legs, both at once: two held, one order, reconciled to the cent.
        self.venue.fill_legs(order_id, {long_call: 1, short_call: 1})
        self.practice.poll()
        self.assertEqual(list(self.held(self.practice, agent).values()), [D(2)])
        final = self.practice.reconcile()
        self.assertTrue(final.ok, final.detail)
        self.assertEqual(final.cash_diff, D(0))
        buys = [f for f in self.fills(agent) if f["side"] == "buy"]
        self.assertEqual([(D(f["quantity"]), D(f["price"])) for f in buys], [(D(1), D("0.25")), (D(1), D("0.25"))])
        self.assertEqual(self.practice.open_orders(agent.id), [])

    def test_an_order_that_ends_with_its_legs_uneven_is_an_error_and_the_leg_it_left_is_closed_not_adopted(self):
        agent = self.seated("debit_vertical")
        long_call, short_call = occ("2026-09-11", "call", 590), occ("2026-09-11", "call", 591)
        one = {"structure": "debit_vertical", "action": "open", "quantity": 1, "limit_price": 0.24, "reason": "a cheap vertical",
               "legs": [{"occ": long_call, "role": "long"}, {"occ": short_call, "role": "short"}]}
        order_id = self.rested(agent, one, "0.24")
        self.venue.fill_legs(order_id, {long_call: 1})
        order = self.venue.orders[order_id]
        order["status"] = "canceled"  # the day ends: the short leg never filled
        for leg in order["legs"]:
            if leg["status"] != "filled":
                leg["status"] = "canceled"
        self.practice.poll()
        self.assertEqual(self.practice.open_orders(agent.id), [])
        self.assertEqual(self.held(self.practice, agent), {})  # no structure: never booked
        uneven = [a for a in self.alerts() if (a.get("structure_answer") or {}).get("stage") == "uneven"]
        self.assertEqual([a["level"] for a in uneven], ["error"])
        # The order's row says so (`UNEVEN_LEGS_REASON`), so a new process knows which contracts it left.
        from league.book import UNEVEN_LEGS_REASON

        ended = [e.payload for e in self.house.ledger.iter(kinds="book.order") if e.payload.get("status") == "cancelled"]
        self.assertTrue(ended[-1]["reason"].startswith(UNEVEN_LEGS_REASON), ended[-1]["reason"])
        self.house.close(wait=None)
        self.house = self.new_house()
        self.house.structure_practice_account = True
        self.practice = self.house.books[PRACTICE]
        self.assertEqual(set(self.practice._uneven_ended), {ended[-1]["order_id"]})
        for _ in range(ADOPT_AFTER + 2):
            self.practice.poll()
            final = self.practice.reconcile()
        breaks = [a for a in self.alerts() if a.get("structure_break")]
        self.assertEqual([a["level"] for a in breaks], ["error"])
        sold = [(b["symbol"], b["side"], b["position_intent"]) for b in self.venue.posted if "legs" not in b]
        self.assertEqual(sold, [(long_call, "sell", "sell_to_close")])
        self.assertEqual({s_: q for s_, q in self.venue.held.items() if q}, {})
        self.assertEqual(self.practice.baseline_positions, {})  # the leg was never adopted
        self.assertTrue(final.ok, final.detail)  # its cash, which no agent booked, is the House's, adopted on practice

    def test_a_restart_while_the_order_rests_books_its_fill_from_the_legs(self):
        agent = self.seated()
        order_id = self.rested(agent, condor_row(limit=0.42), "-0.42")  # held 0.58, under the 0.61 ask
        self.house.close(wait=None)
        self.house = self.new_house()  # a new process: a new adapter that never saw the order, the book from the ledger
        self.house.structure_practice_account = True
        self.practice = self.house.books[PRACTICE]
        self.assertEqual(len(self.practice.open_orders(agent.id)), 1)
        self.venue.fill_legs(order_id, {symbol: 1 for symbol in LEGS})  # the venue fills it while the House is away
        self.practice.poll()
        self.assertEqual(list(self.held(self.practice, agent).values()), [D(1)])
        final = self.practice.reconcile()
        self.assertTrue(final.ok, final.detail)
        self.assertEqual(final.cash_diff, D(0))
        self.assertIs(self.house.book_of(self.house.registry.get(agent.id)), self.practice)

    def test_a_broken_structure_is_closed_at_once_shorts_first_with_an_error_alert(self):
        agent = self.seated()
        self.assertEqual([o.status for o in self.send(agent, [condor_row()])], ["filled"])
        self.assertTrue(self.practice.reconcile().ok)
        self.venue.held[occ("2026-09-11", "put", 580)] = D(0)  # the long put is gone at the venue (exercised)
        self.practice.reconcile()
        self.practice.reconcile()  # BREAK_AFTER readings in a row
        breaks = [a for a in self.alerts() if a.get("structure_break")]
        self.assertEqual([a["level"] for a in breaks], ["error"])
        self.assertEqual(self.held(self.practice, agent), {})  # written off the agent at nothing
        written = [e.payload for e in self.house.ledger.iter(kinds="book.settle", agent=agent.id)]
        self.assertEqual([p["result"] for p in written], ["broken"])
        singles = [b for b in self.venue.posted if "legs" not in b]
        self.assertEqual(sorted((b["symbol"], b["side"], b["position_intent"]) for b in singles),
                         [(occ("2026-09-11", "call", 590), "buy", "buy_to_close"), (occ("2026-09-11", "put", 581), "buy", "buy_to_close")])
        for _ in range(2):  # then the long call left, sold once no short remains
            self.practice.poll()
            final = self.practice.reconcile()
        self.assertTrue(final.ok, final.detail)
        self.assertEqual({s: q for s, q in self.venue.held.items() if q}, {})
        self.assertTrue(all(q >= 0 for q in self.practice.baseline_positions.values()))

    def test_an_unmatched_short_leg_closes_the_whole_structure_at_once_with_an_error_alert(self):
        """The owner's rule: a short the venue holds that no structure explains closes the WHOLE structure it sits in,
        at once, with an error alert: every short bought back in the first pass, the longs sold once no short is left."""
        agent = self.seated()
        self.assertEqual([o.status for o in self.send(agent, [condor_row()])], ["filled"])
        stray = occ("2026-09-11", "call", 590)
        self.venue.held[stray] -= 1  # a second short call no structure explains, beside the condor's own
        self.practice.reconcile()
        self.assertFalse([a for a in self.alerts() if a.get("structure_break")])  # one reading can fall between a fill and its poll
        self.practice.reconcile()
        breaks = [a for a in self.alerts() if a.get("structure_break")]
        self.assertEqual([a["level"] for a in breaks], ["error"])
        self.assertEqual(self.held(self.practice, agent), {})
        first = [(b["symbol"], b["side"], b["position_intent"], b["qty"]) for b in self.venue.posted if "legs" not in b]
        self.assertEqual(sorted(first), [(stray, "buy", "buy_to_close", "2"), (occ("2026-09-11", "put", 581), "buy", "buy_to_close", "1")])
        for _ in range(2):
            self.practice.poll()
            final = self.practice.reconcile()
        self.assertTrue(final.ok, final.detail)
        self.assertEqual({s: q for s, q in self.venue.held.items() if q}, {})
        sold = [(b["symbol"], b["side"], b["position_intent"]) for b in self.venue.posted if "legs" not in b and b["side"] == "sell"]
        self.assertEqual(sorted(sold), [(occ("2026-09-11", "call", 591), "sell", "sell_to_close"),
                                        (occ("2026-09-11", "put", 580), "sell", "sell_to_close")])

    def test_nothing_is_held_into_expiry_the_house_sells_it_whole_from_1530(self):
        agent = self.seated()
        self.assertEqual([o.status for o in self.send(agent, [condor_row()])], ["filled"])
        self.house._state["next_wake"][agent.id] = self.clock() + 10 ** 9
        self.at(THURSDAY_11_NY + 86400 + 4.6 * 3600)  # Friday 15:36 New York, the condor's expiry day
        for symbol in LEGS:  # fresh quotes on the Friday
            self.venue.quotes[symbol] = tuple(D(x) for x in LEGS[symbol])
        self.house._enforce_horizon()
        closes = [b for b in self.mleg_posts() if b["legs"][0]["position_intent"].endswith("_to_close")]
        self.assertEqual([(b["qty"], b["limit_price"]) for b in closes], [("1", "0.47")])  # at its bid, 0.53: one order
        self.assertEqual(self.held(self.practice, agent), {})
        self.assertEqual({s: q for s, q in self.venue.held.items() if q}, {})


class TheReviewOfWave2(PracticeCase):
    """The review of Wave 2 (Sept 25, 2026): its demonstrations, kept as the regressions of what was fixed."""

    LONG, SHORT = occ("2026-09-11", "call", 590), occ("2026-09-11", "call", 591)

    def vertical(self, limit, quantity=1):
        return {"structure": "debit_vertical", "action": "open", "quantity": quantity, "limit_price": limit, "reason": "review",
                "legs": [{"occ": self.LONG, "role": "long"}, {"occ": self.SHORT, "role": "short"}]}

    def seated(self, name):
        self.switch(True)
        agent = self.agent("debit_vertical", name=name)
        self.assertIs(self.house.book_of(agent), self.practice)
        self.house.seat(agent)
        return agent

    def settles(self, agent):
        return [e.payload["result"] for e in self.house.ledger.iter(kinds="book.settle", agent=agent.id)]

    def resting_mleg(self):
        (order_id,) = [o for o, r in self.venue.orders.items() if r.get("order_class") == "mleg" and r["status"] == "new"]
        return order_id

    def held_at_venue(self):
        return {symbol: q for symbol, q in self.venue.held.items() if q}

    def test_a_leg_an_uneven_order_left_breaks_no_other_agents_whole_structure(self):
        """Before: kb's whole vertical, sharing its contracts with ka's order that filled only its long leg, was written off
        at nothing (the break took every structure with a leg on a contract with any difference)."""
        innocent = self.seated("kb")
        mover = self.seated("ka")
        self.assertEqual([o.status for o in self.send(innocent, [self.vertical(0.26)])], ["filled"])  # 0.36 - 0.11 = 0.25
        self.assertTrue(self.practice.reconcile().ok)
        self.assertEqual([o.status for o in self.send(mover, [self.vertical(0.24)])], ["resting"])
        order_id = self.resting_mleg()
        self.venue.fill_legs(order_id, {self.LONG: 1})  # the long leg only, then the order ends
        order = self.venue.orders[order_id]
        order["status"] = "canceled"
        for leg in order["legs"]:
            if leg["status"] != "filled":
                leg["status"] = "canceled"
        for _ in range(ADOPT_AFTER + 3):
            self.practice.poll()
            final = self.practice.reconcile()
        self.assertEqual(self.settles(innocent), [])
        self.assertEqual(list(self.held(self.practice, innocent).values()), [D(1)])
        breaks = [a["structure_break"] for a in self.alerts() if a.get("structure_break")]
        self.assertEqual([b["written_off"] for b in breaks], [[]])  # the House row took the spare long call, nobody's structure
        sold = [(b["symbol"], b["side"], b["position_intent"]) for b in self.venue.posted if "legs" not in b]
        self.assertEqual(sold, [(self.LONG, "sell", "sell_to_close")])
        self.assertEqual(self.held_at_venue(), {self.LONG: D(1), self.SHORT: D(-1)})  # kb's vertical, whole
        self.assertTrue(final.ok, final.detail)
        self.assertEqual(self.practice.baseline_positions, {})

    def test_one_short_assigned_of_two_identical_structures_breaks_only_the_newest(self):
        """Before: both verticals were written off when one of their two short 591 calls was assigned."""
        a, b = self.seated("ka"), self.seated("kb")
        self.assertEqual([o.status for o in self.send(a, [self.vertical(0.26)])], ["filled"])
        self.at(self.clock() + 60)
        self.assertEqual([o.status for o in self.send(b, [self.vertical(0.26)])], ["filled"])  # b's is the newer
        self.assertTrue(self.practice.reconcile().ok)
        self.venue.held[self.SHORT] += 1  # ONE of the two short 591 calls is gone
        self.practice.reconcile()
        self.practice.reconcile()  # BREAK_AFTER
        self.assertEqual((self.settles(a), self.settles(b)), ([], ["broken"]))
        self.assertEqual(list(self.held(self.practice, a).values()), [D(1)])
        (alert,) = [x["structure_break"] for x in self.alerts() if x.get("structure_break")]
        self.assertEqual(len(alert["written_off"]), 1)
        self.assertTrue(alert["written_off"][0].startswith("kb"), alert)
        # What is left of b's (its long 590 call) is sold; a's vertical is what the venue holds.
        self.practice.poll()
        self.practice.reconcile()
        self.assertEqual(self.held_at_venue(), {self.LONG: D(1), self.SHORT: D(-1)})

    def test_an_extra_long_on_a_long_leg_is_the_house_rows_to_close_and_no_structure_breaks(self):
        agent = self.seated("ka")
        self.assertEqual([o.status for o in self.send(agent, [self.vertical(0.26)])], ["filled"])
        self.venue.held[self.LONG] += 1
        self.practice.reconcile()
        self.practice.reconcile()
        self.assertEqual(self.settles(agent), [])
        self.assertEqual([(b["symbol"], b["side"]) for b in self.venue.posted if "legs" not in b], [(self.LONG, "sell")])

    def test_a_late_leg_beside_a_stray_difference_is_never_adopted_and_the_structure_stays_whole(self):
        """Before: with any other difference beside the late leg, three readings adopted the leg that filled first into the
        baseline, and when the late leg came the healthy vertical was read as broken and written off."""
        agent = self.seated("ka")
        self.assertEqual([o.status for o in self.send(agent, [self.vertical(0.24)])], ["resting"])
        order_id = self.resting_mleg()
        self.venue.fill_legs(order_id, {self.LONG: 1})  # the short leg is late
        stray = occ("2026-09-11", "put", 580)
        self.venue.held[stray] = D(1)  # beside it, a stray long no structure touches (a lost single-contract fill)
        for _ in range(ADOPT_AFTER + 2):
            self.practice.poll()
            reading = self.practice.reconcile()
        self.assertFalse(reading.ok)
        self.assertEqual(self.practice.baseline_positions, {})  # nothing adopted while a leg is in flight
        self.venue.fill_legs(order_id, {self.SHORT: 1})
        self.practice.poll()
        self.assertEqual(list(self.held(self.practice, agent).values()), [D(1)])
        for _ in range(3):
            self.practice.poll()
            reading = self.practice.reconcile()
        self.assertTrue(reading.ok, reading.detail)
        self.assertEqual(self.settles(agent), [])
        self.assertEqual(list(self.practice.baseline_positions), ["option:SPY:alpaca-paper:2026-09-11:580:put"])

    def test_legs_standing_uneven_are_cancelled_and_the_book_reconciles_again(self):
        """Before: a late leg froze alpaca-paper for every agent for as long as the order rested (five hours of readings)."""
        from league.book import UNEVEN_CANCEL_SECONDS
        from ltcm.broker import Instrument

        agent = self.seated("ka")
        self.assertEqual([o.status for o in self.send(agent, [self.vertical(0.24)])], ["resting"])
        order_id = self.resting_mleg()
        self.venue.fill_legs(order_id, {self.LONG: 1})
        self.practice.limits["stock-agent"] = Limits(D("100"), D("75"), asset_classes=("equity",))
        self.practice.stake("stock-agent", "200")
        start = self.clock()
        readings = []
        for minutes in range(0, 45, 5):  # mark passes five minutes apart
            self.at(start + minutes * 60)
            self.practice.poll()
            readings.append((minutes, self.practice.reconcile().ok))
        self.assertEqual(self.venue.orders[order_id]["status"], "canceled")
        self.assertFalse([m for m, ok in readings if m * 60 < UNEVEN_CANCEL_SECONDS and ok])  # frozen while it stood
        self.assertTrue(readings[-1][1], readings)
        self.assertEqual(self.practice.open_orders(agent.id), [])
        cancelled = [x for x in self.alerts() if x.get("uneven_cancelled")]
        self.assertEqual([x["level"] for x in cancelled], ["error"])
        self.assertEqual(self.held_at_venue(), {})  # the leg ahead was sold by the House row
        spy = Instrument("equity", "SPY", PRACTICE)
        buy = Intent.new(agent="stock-agent", instrument=spy, side="buy", quantity="0.1", order_type="limit", limit_price="580",
                         time_in_force="day", reason="r", created_at=iso(self.clock), nonce="s")
        self.assertFalse([r for r in self.practice.check(buy, None, iso(self.clock)) if "frozen" in r])

    def test_a_single_contract_on_a_contract_a_cancelled_structure_order_named_stays_a_single(self):
        """Before: every structure order ever sent kept its contracts in the break check, so a single contract's later
        difference there was an ERROR "a structure broke" and a buy-back of a short the venue never held."""
        from ltcm.broker import Instrument

        agent = self.seated("ka")
        self.assertEqual([o.status for o in self.send(agent, [self.vertical(0.24)])], ["resting"])
        order = self.venue.orders[self.resting_mleg()]
        order["status"] = "canceled"
        for leg in order["legs"]:
            leg["status"] = "canceled"
        self.practice.poll()
        self.assertTrue(self.practice.reconcile().ok)
        self.practice.limits["single"] = Limits(D("100"), D("75"), asset_classes=("option",))
        self.practice.stake("single", "200")
        call = Instrument("option", "SPY", PRACTICE, multiplier=D(100), expiry="2026-09-11", strike=D(590), right="call")
        buy = Intent.new(agent="single", instrument=call, side="buy", quantity="1", order_type="limit", limit_price="0.36",
                         time_in_force="day", reason="single", created_at=iso(self.clock), nonce="single")
        self.assertEqual(self.practice.submit([buy])[0].status, "filled")
        self.assertTrue(self.practice.reconcile().ok)
        posted = len(self.venue.posted)
        self.venue.held[self.LONG] -= 1  # the venue no longer shows it
        for _ in range(3):
            self.practice.reconcile()
        self.assertFalse([x for x in self.alerts() if x.get("structure_break")])
        self.assertEqual(len(self.venue.posted), posted)  # no buy-back of a short the venue never held
        self.assertEqual({k: h.quantity for k, h in self.practice.account("single").holdings.items()},
                         {call.key: D(1)})  # frozen for the owner as on main, never passed off as a break


class RealCashAccount(unittest.TestCase):
    """The real account (multiplier 1: Alpaca's 1x limited margin, the owner's "cash" account) through the adapter and
    a real-money book. Structures on real money are held by the House until O1 and by the gateway's
    `OPTION_STRUCTURES_REAL`; this pins the adapter's and the book's part of it. The venue adds a credit to cash as
    Alpaca documents for every account (the review of Wave 2, Sept 25, 2026); `sets_aside` is the other model, which
    the book names to the cent if the account shows it."""

    def setUp(self):
        import tempfile

        from ltcm.adapters import AlpacaCredentials
        from ltcm.adapters.alpaca import AlpacaBroker
        from ltcm.tests.fakes import FakeTransport

        self._rules = without_real_entry_rules()
        self._rules.start()
        self.addCleanup(self._rules.stop)
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock(THURSDAY_11_NY)
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)
        self.addCleanup(self.ledger.close)
        self.venue = Venue(self.clock, multiplier="1", level="3")
        self.venue.cash = D("500")
        for symbol, (bid, ask) in {**LEGS, **VERTICAL_LEGS}.items():
            self.venue.quotes[symbol] = (D(bid), D(ask))
        self.broker = AlpacaBroker(AlpacaCredentials("gateway", "gateway", paper=False), transport=FakeTransport(default=self.venue),
                                   venue="alpaca")
        self.book = Book("alpaca", self.broker, self.ledger, fees=Fees("alpaca", option_clearing=True), real_money=True, clock=self.clock)
        self.assertTrue(self.book.reconcile().ok)
        self.book.limits["a1"] = Limits(D("100"), D("75"), asset_classes=("option",))
        self.book.stake("a1", "200")

    def trade(self, row, side):
        order = structures.parse("alpaca", {**row, "action": "open" if side == "buy" else "close"})
        intent = Intent.new(agent="a1", instrument=structures.instrument(order.spec, "alpaca"), side=side, quantity="1",
                            order_type="limit", limit_price=order.held_limit, time_in_force="day", reason="real",
                            created_at=iso(self.clock), nonce=f"{side}{row['limit_price']}{len(self.venue.posted)}")
        return self.book.submit([intent])[0]

    def test_the_account_reads_as_cash_and_its_record_says_so(self):
        self.assertEqual((self.broker.account_type(), self.broker.credit_in_cash()), ("cash", True))
        self.assertFalse(self.broker.practice)
        self.assertEqual(self.broker.structure_types, ("debit_vertical", "long_butterfly"))
        rows = [e.payload for e in self.ledger.iter(kinds="ops.alert") if (e.payload.get("structure_answer") or {}).get("stage") == "account"]
        self.assertEqual(len(rows), 1)
        self.assertIn("reads as a cash account (multiplier 1", rows[0]["text"])
        self.assertIn("taken off the venue's cash before reconciling (the venue adds the credit)", rows[0]["text"])

    def test_a_debit_vertical_opens_closes_and_reconciles_with_nothing_to_offset(self):
        opened = self.trade(vertical_row(limit=0.45), "buy")
        self.assertEqual(opened.status, "filled", opened.detail)
        self.assertEqual(self.venue.posted[-1]["limit_price"], "0.45")  # a debit: positive, at its limit
        (held,) = self.book.account("a1").holdings.values()
        self.assertEqual(held.cost, D("42.06"))  # filled at the touch, 0.62 - 0.20, and two legs' $0.03
        reading = self.book.reconcile()
        self.assertTrue(reading.ok, reading.detail)
        self.assertEqual(reading.cash_diff, D(0))
        self.assertEqual((self.book._collateral_offset, self.book._collateral_not_offset), (D(0), D(0)))  # a debit has none
        closed = self.trade(vertical_row(limit=0.38), "sell")
        self.assertEqual(closed.status, "filled", closed.detail)
        final = self.book.reconcile()
        self.assertTrue(final.ok, final.detail)
        self.assertEqual(final.cash_diff, D(0))

    def test_a_credit_structure_is_refused_before_anything_is_sent_unless_the_owner_admitted_it(self):
        outcome = self.trade(condor_row(), "buy")
        self.assertEqual(outcome.status, "refused")
        self.assertIn("credit structures on the real account wait for the owner's confirmation", outcome.detail)
        self.assertEqual(self.venue.posted, [])
        from ltcm.broker import OrderIntent, RejectedOrder

        spec = structures.parse("alpaca", condor_row()).spec
        direct = OrderIntent.new(desk_id="book-alpaca", instrument=structures.instrument(spec, "alpaca"), side="buy", quantity="1",
                                 order_type="limit", limit_price="0.62", time_in_force="day", rationale="t", created_at=iso(self.clock),
                                 purpose="entry")
        with self.assertRaises(RejectedOrder):
            self.broker.submit(direct)  # the adapter refuses it itself, whatever the book asked
        self.assertEqual(self.venue.posted, [])

    def admit(self, types):
        from league.constitution import CONSTITUTION

        allocator = {**CONSTITUTION["allocator"], "option_spread_real_types": types}
        return mock.patch.dict(CONSTITUTION, {"allocator": allocator})

    def test_an_admitted_credit_type_on_the_1x_account_reconciles_exactly_with_its_collateral_offset(self):
        with self.admit(["iron_condor"]):
            self.assertIn("iron_condor", self.broker.structure_types)
            self.assertNotIn("credit_vertical", self.broker.structure_types)
            opened = self.trade(condor_row(), "buy")
            self.assertEqual(opened.status, "filled", opened.detail)
            reading = self.book.reconcile()
            self.assertTrue(reading.ok, reading.detail)
            self.assertEqual(reading.cash_diff, D(0))
            self.assertEqual(self.book._collateral_offset, D(100))
            closed = self.trade(condor_row(limit=0.47), "sell")
            self.assertEqual(closed.status, "filled", closed.detail)
            final = self.book.reconcile()
            self.assertTrue(final.ok, final.detail)
            self.assertEqual(final.cash_diff, D(0))

    def test_a_1x_account_that_set_the_loss_aside_after_all_freezes_the_real_book_and_says_so(self):
        """If the 1x account set a credit structure's maximum loss aside from cash after all (the spec's cash account,
        against Alpaca's documentation), the first admitted credit structure shows it, and the real book freezes on
        exactly its collateral, named, never booked as the venue's fees."""
        self.venue.sets_aside = True
        with self.admit("iron_condor"):
            self.assertEqual(self.trade(condor_row(), "buy").status, "filled")
            reading = self.book.reconcile()
        self.assertFalse(reading.ok)
        self.assertIn("cash differs by -100.0000 (exactly the $100.00 collateral of the credit structures held, which the book "
                      "took off the venue's cash", reading.detail)

    def test_a_venue_that_says_it_does_not_add_the_credit_is_not_offset_and_named_the_other_way(self):
        self.venue.sets_aside = False
        with self.admit("iron_condor"), mock.patch.object(self.broker, "credit_in_cash", return_value=False):
            self.assertEqual(self.trade(condor_row(), "buy").status, "filled")
            reading = self.book.reconcile()
        self.assertFalse(reading.ok)
        self.assertIn("cash differs by 100.0000 (exactly the $100.00 collateral of the credit structures held, which this "
                      "account was read not to add to cash", reading.detail)

    def break_a_long_wing(self):
        self.assertEqual(self.trade(condor_row(), "buy").status, "filled")
        self.assertTrue(self.book.reconcile().ok)
        self.venue.held[occ("2026-09-11", "put", 580)] = D(0)  # a long wing gone (exercised)
        self.book.reconcile()
        return self.book.reconcile()  # BREAK_AFTER: broken, the House row holds what is left

    def test_a_broken_credit_structure_releases_the_collateral_the_fold_took_off(self):
        with self.admit(["iron_condor"]):
            after = self.break_a_long_wing()
        self.assertEqual([p["result"] for p in (e.payload for e in self.ledger.iter(kinds="book.settle"))], ["broken"])
        self.assertNotIn("cash differs", after.detail)

    def test_a_broken_credit_structure_on_a_venue_that_sets_the_loss_aside_releases_nothing(self):
        """The review of Wave 2 (Sept 25, 2026): the break released K x 100 whatever the account's model, so on a venue
        that holds the loss aside itself the real book then stood $100 over it, frozen."""
        self.venue.sets_aside = True
        with self.admit(["iron_condor"]), mock.patch.object(self.broker, "credit_in_cash", return_value=False):
            after = self.break_a_long_wing()
        self.assertEqual([p["result"] for p in (e.payload for e in self.ledger.iter(kinds="book.settle"))], ["broken"])
        self.assertNotIn("cash differs", after.detail)

    def test_the_practice_account_offsets_the_same_condor(self):
        """The same condor on a margin practice account: the credit is added to cash and the collateral offset."""
        from ltcm.adapters import AlpacaCredentials
        from ltcm.adapters.alpaca import AlpacaBroker
        from ltcm.tests.fakes import FakeTransport

        venue = Venue(self.clock, multiplier="4")
        venue.quotes = dict(self.venue.quotes)
        broker = AlpacaBroker(AlpacaCredentials("gateway", "gateway", paper=False), transport=FakeTransport(default=venue), venue=PRACTICE)
        ledger = Ledger(Path(self.dir.name) / "practice.sqlite", clock=self.clock)
        self.addCleanup(ledger.close)
        book = Book(PRACTICE, broker, ledger, fees=Fees("alpaca", option_clearing=True), real_money=False, clock=self.clock)
        self.assertTrue(book.reconcile().ok)
        book.limits["a1"] = Limits(D("100"), D("75"), asset_classes=("option",))
        book.stake("a1", "200")
        self.assertEqual((broker.account_type(), broker.credit_in_cash()), ("margin", True))
        order = structures.parse(PRACTICE, condor_row())
        intent = Intent.new(agent="a1", instrument=structures.instrument(order.spec, PRACTICE), side="buy", quantity="1", order_type="limit",
                            limit_price=order.held_limit, time_in_force="day", reason="practice", created_at=iso(self.clock), nonce="p")
        self.assertEqual(book.submit([intent])[0].status, "filled")
        reading = book.reconcile()
        self.assertTrue(reading.ok, reading.detail)
        self.assertEqual(venue.cash - D("98000"), D("38.88"))  # the venue added the 0.39 credit less $0.12 of fees
        self.assertEqual((book._collateral_offset, book._collateral_not_offset), (D(100), D(0)))


if __name__ == "__main__":
    unittest.main()
