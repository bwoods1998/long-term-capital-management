"""RELEASE 1019h, DONE SPEED (the captain's A97; brief goal-2026-10-19/speed/KEPT-1019h.md), items S2 and PL-2, through
the REAL book (league/equity/live.py), the REAL `size_entry`, the money table in force and the lane's REAL store
(league/tests/test_events_book.py's harness). Every figure is invented; none is a market's.

S2 (= SUP-1's sizing, one mechanism): PROBE AND SIZED BUYS AT DONE'S SIZE. Done counts a Probe+ buy only when the
dollars its send asked reach 0.8 of its band target (league/events/done.py `at_size`, the judge, read and never
edited). Whole-share flooring left about a third of Probe buys under that bar. A Probe or Sized buy that flooring took
under it now buys the fewest whole shares that reach it, only when those are at most the band's frozen PREREG-EVL-1
section 8 target (the loose end of its `position_share` bounds row: Probe 5%, Sized 10%) of the walls' equity, only when
rounding (not a cap) caused the shortfall, and only when `size_entry` asked again for them gives every share (the name
wall, the 100% book, cash, the loss budget). The count is never above floor(5% E / limit), PREREG-EVL-1 section 8's
own, so it stays inside the frozen envelope (A86 REVISED's doctrine). The bar is a money row of its own, as the design,
its check (condition 4) and the captain's A100 require: `equity_money.event.reach_bar.probe` and `.sized`, 0.8 (pinned
equal to the Done reader's `PROBE_SIZE_SHARE`), bound 0-0.8, 0 being release 1019f's floor rounding (the tighten-only
switch); both digests move once with those two rows and nothing else. The check's worked cases at E = $1,898 (target $66.43, bar $53.144, envelope $94.90): $40 -> 2 shares, $47 -> 2
($94), $50 -> 1 (2 would be $100 > $94.90: under size, shown beside), $90 -> 1 (one share), $96 -> skipped; a cash
case that refuses the round-up. The target stays the band's (`target_usd`); learning never rounds up.

PL-2 (the captain's A97; R3-SPEC section 4 as A97 amends it): a birth at Probe or Sized takes its band's ROOM tier
after that band's PREREG rows and before every learning row; a birth at learning stays at BIRTH_ROOM. Proved here on an
invented week: while no birth is promoted, no PREREG program's real-money pick (the decision's allocation and the
sends' order) changes."""

from __future__ import annotations

import contextlib
import dataclasses
import json
import random
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

from league.tests.evl6_fakes import on_1019h
from league import constitution as K
from league.constitution import EQUITY_MONEY_BOUNDS, equity_money_problems
from league.events import births as BI
from league.equity import live as L
from league.events import book as EB
from league.events import done as DN
from league.events import programs as P
from league.events import store as S
from league.tests import equity_design as X
from league.tests import test_events_a85 as A85
from league.tests import test_events_book as TB
from league.tests.test_events_book import CIK, CIK2, CIK3, DAY, earnings
from league.tests.test_events_births import spec

PROBE = "EVL-8K-READ-O1"        # an open-entry PREREG program reading 8-K item 8.01
LEARN = "EVL-ERN-READ-O1"       # an open-entry PREREG program reading earnings 8-Ks (item 2.02)
E1898 = D("1898")


def limit_of(prev_close: str) -> D:
    return EB.limit_price(D(prev_close), D("1.25"))


# ================================================================================================== S2, the rule (pure)
class TheRule(unittest.TestCase):
    """`book.round_up` and `book.at_size`, the arithmetic, at E = $1,898 (the check's worked cases)."""

    target = D("0.035") * E1898          # $66.43: the Probe band's target (A86 REVISED)

    def n(self, limit: str, band: str = "probe", E: D = E1898, walls: D | None = None) -> D | None:
        target = EB.settings().share(band) * E
        whole = (target / D(limit)).to_integral_value(rounding="ROUND_DOWN")
        return EB.round_up(band, target, D(limit), whole, E if walls is None else walls)

    def test_the_bar_is_the_judges_own_and_its_share_is_done_probe_size_share(self):
        self.assertEqual(DN.PROBE_SIZE_SHARE, 0.8, "the judge's line (read here, never edited)")
        for target, usd in ((66.43, 53.14), (66.43, 53.15), (54.25, 43.40), (70.0, 56.0), (100, 80), (0, 1), (66.43, 0)):
            self.assertIs(EB.at_size(D(str(target)), D(str(usd))), DN.at_size(target, usd), (target, usd))
        self.assertIs(EB.at_size(D("54.25"), D("43.40")), False, "an exact equality the judge's floats count under")

    def test_the_worked_cases_at_1898(self):
        self.assertEqual(self.target, D("66.430"))
        self.assertEqual(EB.envelope_share("probe") * E1898, D("94.90"))
        self.assertEqual(self.n("40"), 2, "$40: 1 share is $40 < $53.144; 2 shares are $80 <= $94.90")
        self.assertEqual(self.n("47"), 2, "$47: 2 shares are $94 <= $94.90")
        self.assertIsNone(self.n("50"), "$50: 2 shares are $100 > $94.90 (5% of E): under size, never past the envelope")
        self.assertIsNone(self.n("90"), "$90: no whole share at the target; the one-share rule buys 1 ($90 >= the bar)")
        self.assertIsNone(self.n("96"), "$96: the one-share rule skips it (above 5% of E)")
        self.assertIsNone(self.n("30"), "$30: 2 shares are $60, at Done's size already")
        self.assertIsNone(self.n("40", band="learning"), "learning never rounds up")
        self.assertIsNone(EB.envelope_share("learning"))
        # the price band where 1 share is under the bar and 2 are above the envelope stays under size (the design's)
        for cents in range(4746, 5315):            # ($47.46-53.14: 2 shares above $94.90, 1 share under $53.144)
            L = D(cents) / 100
            self.assertIsNone(self.n(str(L)), L)
        self.assertEqual(self.n("47.45"), 2, "2 x $47.45 is exactly the envelope: inside it")
        self.assertIsNone(self.n("53.15"), "one share reaches the bar")

    def test_never_above_prereg_evl_1_section_8s_own_count(self):
        """n x limit <= 5% x E means n <= floor(5% E / limit): the frozen rule's shares at its 5% Probe target; at Sized
        the envelope is the target itself, so no Sized buy ever rounds up."""
        for E in (D("1500"), D("1898"), D("2100")):
            for cents in range(500, 12000, 7):
                L = D(cents) / 100
                n = self.n(str(L), E=E)
                if n is not None:
                    self.assertLessEqual(n, (D("0.05") * E / L).to_integral_value(rounding="ROUND_DOWN"), (E, L))
                    self.assertLessEqual(n * L, D("0.05") * E)
                    self.assertTrue(DN.at_size(float(D("0.035") * E), float(n * L)), (E, L))
                self.assertIsNone(self.n(str(L), band="sized", E=E), (E, L))

    def test_the_envelope_is_the_bounds_rows_loose_end_on_the_walls_equity(self):
        self.assertEqual(EB.envelope_share("probe"), D(EQUITY_MONEY_BOUNDS["event.position_share.probe"][1]))
        self.assertEqual(EB.envelope_share("sized"), D(EQUITY_MONEY_BOUNDS["event.position_share.sized"][1]))
        with mock.patch.dict(EQUITY_MONEY_BOUNDS, {"event.position_share.probe": ("0", "0.04")}):
            self.assertIsNone(self.n("47"), "read from the bounds row, not a literal: 4% of E is $75.92 < $94")
            self.assertEqual(self.n("37"), 2)
        self.assertIsNone(self.n("47", walls=D("1850")), "on the walls' equity: 5% of $1,850 is $92.50 < $94")
        self.assertEqual(self.n("40", walls=D("1850")), 2)

    def test_an_exact_equality_the_judges_floats_count_under_is_rounded_up(self):
        # E $1,550: target $54.25, bar $43.40; at $21.70 two shares are exactly $43.40, which Done's float comparison
        # (0.8 x 54.25 = 43.400000000000006) counts UNDER size: three shares ($65.10 <= $77.50) reach it.
        self.assertEqual(self.n("21.70", E=D("1550")), 3)

    def test_the_bar_is_a_row_and_the_row_sets_it(self):
        """`round_up` reads the band's `reach_bar` row (the one in force when `bar` is None): 0 is no round-up; a lower
        bar rounds up less (0.7 x $66.43 = $46.50: $47 reaches it at one share), and at or under 0.5 never (a floored
        buy of one share or more is always above half its target)."""
        target = EB.settings().share("probe") * E1898
        self.assertEqual(EB.round_up("probe", target, D("40"), D(1), E1898), 2, "the row in force, 0.8")
        self.assertIsNone(EB.round_up("probe", target, D("40"), D(1), E1898, bar=D(0)), "0: release 1019f's floor")
        self.assertEqual(EB.round_up("probe", target, D("40"), D(1), E1898, bar=D("0.7")), 2)
        self.assertIsNone(EB.round_up("probe", target, D("47"), D(1), E1898, bar=D("0.7")), "$47 >= $46.50 already")
        self.assertEqual(EB.round_up("probe", target, D("47"), D(1), E1898, bar=D("0.8")), 2)
        for cents in range(500, 12000, 3):
            L = D(cents) / 100
            whole = (target / L).to_integral_value(rounding="ROUND_DOWN")
            if whole >= 1:
                self.assertIsNone(EB.round_up("probe", target, L, whole, E1898, bar=D("0.5")), L)
        off = dataclasses.replace(EB.settings(), reach_bars={"probe": D(0), "sized": D(0)})
        with mock.patch.object(EB, "settings", lambda *a, **k: off):
            self.assertIsNone(EB.round_up("probe", target, D("40"), D(1), E1898), "the row in force read at 0")
        self.assertEqual(EB.most_ask(EB.settings(), "probe", D(2000)), D("100.00"), "5% of E while the round-up is on")
        self.assertEqual(EB.most_ask(off, "probe", D(2000)), D("70.000"), "the target with it off")
        self.assertEqual(EB.most_ask(EB.settings(), "learning", D(2000)), D("40.00"), "learning: its target")


@on_1019h
class TheRows(unittest.TestCase):
    """S2's money rows (the design's `at_size.probe` as the captain's A100 names them, `event.reach_bar.probe` and
    `.sized`) and the digests they move: the design's check, condition (4): "Ship the new row and its bound in one
    commit, with a test that settings() != FALLBACK"."""

    def test_the_rows_are_dones_line_inside_their_bounds_and_in_force(self):
        event = K.CONSTITUTION["equity_money"]["event"]
        self.assertEqual(event["reach_bar"], {"probe": "0.8", "sized": "0.8"})
        for band in ("probe", "sized"):
            self.assertEqual(D(event["reach_bar"][band]), D(str(DN.PROBE_SIZE_SHARE)),
                             "the bar is the Done reader's own line (league/events/done.py, never edited)")
            self.assertEqual(EQUITY_MONEY_BOUNDS[f"event.reach_bar.{band}"], ("0", "0.8"))
            self.assertEqual(D(EQUITY_MONEY_BOUNDS[f"event.reach_bar.{band}"][1]), D(str(DN.PROBE_SIZE_SHARE)),
                             "the loose end is the judge's line: a row may only round up less")
        self.assertNotIn("event.reach_bar.learning", EQUITY_MONEY_BOUNDS, "learning never rounds up")
        self.assertEqual(equity_money_problems(), [])
        s = EB.settings()
        self.assertIsNot(s, EB.FALLBACK, "the event block in force is read")
        self.assertNotEqual(s, EB.FALLBACK)
        self.assertEqual((s.reach_bar("probe"), s.reach_bar("sized"), s.reach_bar("learning")), (D("0.8"), D("0.8"), 0))
        self.assertEqual(EB.FALLBACK.reach_bar("probe"), 0, "unread: no round-up")

    def test_a_row_outside_its_bound_or_missing_opens_nothing_and_zero_is_the_switch(self):
        for band in ("probe", "sized"):
            for value, why in (("0.81", "is outside [0, 0.8]"), ("-0.1", "is outside [0, 0.8]"),
                               ("x", "is not a number")):
                bad = json.loads(json.dumps(K.CONSTITUTION))
                bad["equity_money"]["event"]["reach_bar"][band] = value
                self.assertIn(f"equity_money.event.reach_bar.{band} = {value!r} {why}",
                              " ".join(equity_money_problems(bad)), (band, value))
                self.assertIs(EB.settings(bad), EB.FALLBACK, (band, value))
            missing = json.loads(json.dumps(K.CONSTITUTION))
            del missing["equity_money"]["event"]["reach_bar"][band]
            self.assertIn(f"equity_money.event.reach_bar.{band} is missing", " ".join(equity_money_problems(missing)))
            self.assertIs(EB.settings(missing), EB.FALLBACK)
        off = json.loads(json.dumps(K.CONSTITUTION))
        off["equity_money"]["event"]["reach_bar"] = {"probe": "0", "sized": "0"}
        self.assertEqual(equity_money_problems(off), [], "0 is inside the bound: the tighten-only switch")
        self.assertEqual(EB.settings(off).reach_bar("probe"), 0)
        self.assertEqual((K.money_digest(off)[:8], K.digest(off)[:8]), X.S2_OFF_1019I, "one money-digest move")
        self.assertEqual((K.money_digest(X.before_1019i(off))[:8], K.digest(X.before_1019i(off))[:8]), X.S2_OFF,
                         "release 1019h's switch pair, with release 1019i's row left out")

    def test_the_digests_moved_once_with_the_two_rows_and_nothing_else(self):
        pair = X.in_force()
        self.assertEqual((K.money_digest(), K.digest()), X.DIGESTS[pair])
        self.assertEqual(K.digest(), K.PINNED_DIGEST)
        # (release 1019i's row moved them once more, `event.max_open_v6.probe`: release 1019h's table is the one in force
        # with that row left out, `before_1019i`; league/tests/test_events_evl6.py holds that move)
        at_1019h = X.before_1019i()
        self.assertEqual((K.money_digest(at_1019h)[:8], K.digest(at_1019h)[:8]), ("8e63ce64", "c3026eba"))
        self.assertEqual((K.money_digest(at_1019h), K.digest(at_1019h)), X.DIGESTS_1019H[pair])
        before = X.before_1019h()
        self.assertEqual((K.money_digest(before), K.digest(before)), X.DIGESTS_A86[pair], "release 1019g's pair")
        self.assertEqual((K.money_digest(before)[:8], K.digest(before)[:8]), ("c2f0a478", "24f73f18"))
        moved = {k for k, v in flat(at_1019h).items() if flat(before).get(k, "absent") != v}
        self.assertEqual(moved, {"equity_money.event.reach_bar.probe", "equity_money.event.reach_bar.sized"})
        self.assertEqual(set(flat(before)) - set(flat(at_1019h)), set(), "no row left out")
        for candidate in X.CANDIDATES:
            at = X.constitution_at(*candidate)
            self.assertEqual((K.money_digest(at), K.digest(at)), X.DIGESTS[candidate], candidate)
            back = X.before_1019h(at)
            self.assertEqual((K.money_digest(back), K.digest(back)), X.DIGESTS_A86[candidate], candidate)
        self.assertEqual(set(X.DIGESTS.values()) & set(X.DIGESTS_A86.values()), set())
        off = X.before_1019i()
        off["equity_money"]["event"]["enabled"] = False
        self.assertEqual((K.money_digest(off)[:8], K.digest(off)[:8]), X.S2_ROLLBACK,
                         "release 1019h's rollback: every event buy stopped, the rows kept")
        self.assertEqual((K.money_digest(X.before_1019h(off))[:8], K.digest(X.before_1019h(off))[:8]),
                         X.A86_ROLLBACK, "release 1019g's rollback pair, with the rows left out")


def flat(c, prefix: str = "") -> dict:
    out = {}
    for k, v in c.items():
        if isinstance(v, dict):
            out.update(flat(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


# ======================================================================================== S2, through the real book
@on_1019h
class AtDonesSize(TB.EventTest):
    """E $1,898 and cash $1,898 (the reserve $50); EVL-8K-READ-O1 at Probe on 8.01 filings, the limit 1.25 x the
    previous close."""

    def probe(self, h: TB.Harness, names: dict[str, tuple[str, str]], band: str = "probe", program: str = PROBE) -> None:
        for i, (symbol, (cik, prev)) in enumerate(names.items()):
            earnings(h.lane, f"o-{i}", cik, symbol, prev_close=float(prev),
                     items=("8.01",) if program == PROBE else ("2.02",))
        h.lane.band(program, band)
        self.ready(h)
        for symbol in names:
            h.symbol(symbol, last=17.0)

    def sent(self, h: TB.Harness) -> dict[str, str]:
        return {b["symbol"]: b["qty"] for b in h.bodies()}

    def rows(self, h: TB.Harness) -> dict[str, dict]:
        return {r["symbol"]: r for r in h.event_intents("buy")}

    def order_why(self, h: TB.Harness, symbol: str) -> str:
        """The words of the buy order the book sent for `symbol` (its sizing reason inside them)."""
        [row] = h.state.rows("SELECT o.why FROM eq_orders o JOIN eq_event_intents e ON e.iid=o.iid WHERE e.side='buy' AND "
                             "e.symbol=?", (symbol,))
        return str(row["why"] or "")

    def test_the_worked_cases_at_1898(self):
        h = self.harness(cash="1898", E="1898")
        names = {"FRTY": (CIK, "32"), "FRSV": (CIK2, "37.6"), "FFTY": (CIK3, "40"), "NNTY": ("0000000004", "72"),
                 "NNSX": ("0000000005", "76.8")}
        self.assertEqual([limit_of(p) for _, p in names.values()], [D("40"), D("47"), D("50"), D("90"), D("96")])
        self.probe(h, names)
        h.tick(9, 15)
        h.tick(9, 16)
        self.assertEqual(self.sent(h), {"FRTY": "2", "FRSV": "2", "FFTY": "1", "NNTY": "1"},
                         "$40 -> 2, $47 -> 2, $50 -> 1 (under size), $90 -> 1; $96 skipped")
        rows = self.rows(h)
        self.assertNotIn("NNSX", rows, "one share at $96 is above 5% of E: skipped at the decision (the shadow keeps it)")
        for symbol, sized, counted in (("FRTY", "80", True), ("FRSV", "94", True), ("FFTY", "50", False),
                                       ("NNTY", "90", True)):
            row = rows[symbol]
            self.assertEqual(D(row["target_usd"]), D("66.430"), f"{symbol}: the target stays the band's, never the ask")
            self.assertEqual(D(row["sized_usd"]), D(sized), symbol)
            self.assertIs(DN.at_size(float(D(row["target_usd"])), float(D(row["sized_usd"]))), counted, symbol)
        self.assertIn("rounded up to 2 shares ($80.00) to reach Done's size bar", self.order_why(h, "FRTY"))
        self.assertEqual(rows["FFTY"]["binding"], "whole_shares", "$50: under size by whole shares, as before")
        self.assertIsNone(rows["FRTY"]["binding"], "$80 is above the target: nothing cut it")

    def test_the_houses_health_line_names_the_rows(self):
        h = self.harness(cash="1898", E="1898")
        self.assertEqual(h.book.health()["events"]["reach_bar"], {"sized": "0.8", "probe": "0.8"},
                         "the deploy's check reads the bar in force")

    def test_a_row_of_zero_is_release_1019fs_floor_rounding(self):
        """`equity_money.event.reach_bar.probe` 0 (the tighten-only switch): the $40 and $47 buys go at one share, as
        release 1019f sent them, the target the band's."""
        with mock.patch.dict(K.CONSTITUTION["equity_money"]["event"]["reach_bar"], {"probe": "0"}):
            self.assertEqual(equity_money_problems(), [])
            h = self.harness(cash="1898", E="1898")
            self.probe(h, {"FRTY": (CIK, "32"), "FRSV": (CIK2, "37.6")})
            h.tick(9, 15)
            h.tick(9, 16)
        self.assertEqual(self.sent(h), {"FRTY": "1", "FRSV": "1"})
        for symbol, sized in (("FRTY", "40"), ("FRSV", "47")):
            row = self.rows(h)[symbol]
            self.assertEqual((D(row["target_usd"]), D(row["sized_usd"]), row["binding"]),
                             (D("66.430"), D(sized), "whole_shares"))
            self.assertNotIn("rounded up", self.order_why(h, symbol))

    def test_cash_refuses_the_round_up_and_is_named_its_binding(self):
        h = self.harness(cash="1898", E="1898")
        h.options.reserved_usd = 1778.0          # available: $1,898 - $1,778 - the $50 reserve = $70
        self.probe(h, {"FRTY": (CIK, "32")})
        h.tick(9, 15)
        h.tick(9, 16)
        self.assertEqual(self.sent(h), {"FRTY": "1"}, "two shares ($80) are above the $70 of cash: one share, as before")
        row = self.rows(h)["FRTY"]
        self.assertEqual((D(row["target_usd"]), D(row["sized_usd"]), row["binding"]), (D("66.430"), D("40"), "cash"))
        why = self.order_why(h, "FRTY")
        self.assertIn("1 shares at probe (sleeve_cash)", why, "the order's words name the cap: the report counts it")
        from league.ops import evl_health as EV

        self.assertEqual(EV.sent_binding(why), "cash", "the report's reading of the sent buy's binding")
        self.assertIn("not rounded up to 2 shares, Done's size bar", why)

    def test_a_cap_that_left_the_dollars_under_the_bar_is_never_rounded_past(self):
        h = self.harness(cash="1898", E="1898")
        h.options.reserved_usd = 1798.0          # available $50: the cap, not rounding, leaves the buy under $53.144
        self.probe(h, {"FRTY": (CIK, "32")})
        h.tick(9, 15)
        h.tick(9, 16)
        self.assertEqual(self.sent(h), {"FRTY": "1"})
        row = self.rows(h)["FRTY"]
        self.assertEqual((D(row["sized_usd"]), row["binding"]), (D("40"), "cash"))
        self.assertNotIn("rounded up", self.order_why(h, "FRTY"), "no round-up is even asked: the cap caused it")

    def test_the_walls_equity_bounds_the_round_up(self):
        h = self.harness(cash="1898", E="1898")
        base = h.venue.account
        h.venue.account = lambda: {**base(), "equity": "1850"}      # the current equity under the previous close's
        self.probe(h, {"FRSV": (CIK2, "37.6"), "FRTY": (CIK, "32")})
        h.tick(9, 15)
        h.tick(9, 16)
        self.assertEqual(self.sent(h), {"FRSV": "1", "FRTY": "2"},
                         "$47 x 2 = $94 is above 5% of the walls' $1,850 ($92.50); $80 is not")
        self.assertEqual(D(self.rows(h)["FRSV"]["target_usd"]), D("66.430"), "the target stays on E")

    def test_learning_and_sized_do_not_move(self):
        h = self.harness(cash="1898", E="1898")
        self.probe(h, {"TWFV": (CIK, "20")}, band="learning", program=LEARN)     # limit $25: target $37.96
        h.tick(9, 15)
        h.tick(9, 16)
        self.assertEqual(self.sent(h), {"TWFV": "1"}, "learning: 1 share ($25 < 0.8 x $37.96), never rounded up")
        self.assertNotIn("rounded up", self.order_why(h, "TWFV"))

    def test_sized_never_rounds_up(self):
        h = self.harness(cash="1898", E="1898")
        self.probe(h, {"HNDR": (CIK, "80")}, band="sized")                       # limit $100: target $189.80
        h.tick(9, 15)
        h.tick(9, 16)
        self.assertEqual(self.sent(h), {"HNDR": "1"}, "Sized: 2 shares are $200 > 10% of E ($189.80), the name's wall")

    def test_the_exact_equality_through_the_book(self):
        h = self.harness(cash="1550", E="1550")
        self.probe(h, {"EDGE": (CIK, "17.36")})                                  # limit $21.70
        h.tick(9, 15)
        h.tick(9, 16)
        self.assertEqual(self.sent(h), {"EDGE": "3"}, "2 shares are exactly the bar, which the judge counts under")
        row = self.rows(h)["EDGE"]
        self.assertTrue(DN.at_size(float(D(row["target_usd"])), float(D(row["sized_usd"]))))


@on_1019h
class TheWaitingBuysAhead(TB.EventTest):
    """PREREG-EVL-5 section 1.3's ROOM while a buy waits for the lane's close decision (release 1019g's `HeldAhead`,
    feat/evl-5's): `_event_keep_room` keeps, from every buy after the waiting one in ROOM's order, what `_size_event`
    would give it in a DRY sizing (nothing written), so S2's round-up, which sits inside `_size_event` (on `record`, the
    side row written only when not dry), is what a waiting PREREG-EVL-5 Probe buy keeps: E $2,000 (target $70, bar $56,
    envelope $100) and EVL-ERN-DROP-ON at Probe with a $40.00 limit keep $80 (two shares), never the floor's $40.

    $100 above the $50 reserve. DROP's Probe buy waits at 15:47; EVL-NEWS-READ-ON's learning buy after it ($20.00 limit,
    learning's $40 target) is left $20: one share. Once the lane's decision names DROP, its buy sends the two shares it
    kept. With S2 off (`book.round_up` None), DROP keeps $40, the learning buy sends two shares and DROP's own buy, the
    $60 left, one (the shortfall then a cap's: no round-up)."""

    def to_close(self, h: TB.Harness) -> str:
        from league.tests.test_events_1019g import fall, DROP as DROP5

        h.lane.band(DROP5, "probe", version=1)
        fall(h, "ACME", CIK, "e-1", prev=32.0, close_px="40.00", next_open="40.00")         # (the limit 1.25 x $32)
        [news] = A85.day_articles(h, 1)
        h.venue.prints[(news, TB.DAY.isoformat(), "close")] = D("20.00")
        h.lane.decided(TB.DAY, "open")
        for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47)):
            h.tick(hh, mm)
        return news

    def kept(self, h: TB.Harness) -> L.HeldAhead:
        """`_event_keep_room` of the waiting DROP buy on a fresh `HeldAhead`, as `_event_send` makes each minute."""
        from league.tests.test_events_1019g import DROP as DROP5, buys_of

        [drop] = buys_of(h, DROP5)
        ahead = L.HeldAhead()
        intent = L.Intent.of(h.state.rows("SELECT * FROM eq_intents WHERE iid=?", (drop["iid"],))[0])
        inst = h.book._instance(intent.instance)
        h.book._event_keep_room(intent, inst, h.book._event_row(drop["iid"]), TB.DAY.isoformat(), EB.settings(), ahead)
        return ahead

    def test_a_waiting_probe_buy_keeps_its_round_up(self):
        from league.tests.test_events_1019g import DROP as DROP5, LEARN_ON, buys_of, lane_close, sent

        for off in (False, True):
            with self.subTest(s2_off=off), contextlib.ExitStack() as stack:
                self.setUp()
                if off:
                    stack.enter_context(mock.patch.object(EB, "round_up", lambda *a, **k: None))
                h = A85.short_of_cash(self.harness(cash="150"), "150")
                news = self.to_close(h)
                [drop] = buys_of(h, DROP5)
                self.assertEqual((drop["band"], drop["status"]), ("probe", "planned"))
                self.assertIn(EB.PART_WAIT, drop["why"])
                ahead = self.kept(h)
                self.assertEqual((ahead.usd, ahead.orders, ahead.names), (D(40 if off else 80), 1,
                                                                           {"ACME": D(40 if off else 80)}),
                                 "the waiting Probe buy keeps its round-up's two shares ($80), never the floor's $40")
                self.assertEqual(ahead.risk, ahead.usd * L._event_weight_of(h.book._event_row(drop["iid"]).get("weight")))
                self.assertEqual(sent(h), [(news, "2" if off else "1")],
                                 "the learning buy after it is left $20 ($100 less the $80 kept): one share")
                [on] = buys_of(h, LEARN_ON)
                order = h.state.rows("SELECT why FROM eq_orders WHERE iid=?", (on["iid"],))[0]["why"]
                if not off:
                    self.assertIn("the sleeve has $20.00 of free cash", order)
                lane_close(h, DROP5, f"{LEARN_ON}@v2")
                h.tick(15, 48)
                self.assertEqual(sent(h), [(news, "2" if off else "1"), ("ACME", "1" if off else "2")],
                                 "once named, DROP sends the two shares it kept")
                [drop] = buys_of(h, DROP5)
                row = h.book._event_row(drop["iid"])
                self.assertEqual(D(row["target_usd"]), D(70), "the target stays the band's")
                self.assertEqual(D(row["sized_usd"]), D(40 if off else 80))
                self.assertEqual(DN.at_size(float(D(row["target_usd"])), float(D(row["sized_usd"]))), not off)

    def test_an_unread_figure_keeps_the_most_the_round_up_may_ask(self):
        """When a sizing figure cannot be read this minute, `_event_keep_room` keeps the most the band may ask
        (`book.most_ask`): with the round-up on, the Probe band's frozen envelope, 5% of $2,000 = $100, not the target's
        $70 (release 1019g's keep, which a round-up can exceed: $80 here); with the row at 0, the target."""
        for bar, kept in (("0.8", D("100.00")), ("0", D("70.000"))):
            with self.subTest(bar=bar), mock.patch.dict(K.CONSTITUTION["equity_money"]["event"]["reach_bar"],
                                                        {"probe": bar}):
                self.setUp()
                h = A85.short_of_cash(self.harness(cash="150"), "150")
                self.to_close(h)
                with mock.patch.object(L.EquityBook, "_read_account", lambda self: None):
                    self.assertEqual(self.kept(h).usd, kept)

    def test_the_dry_sizing_of_a_round_up_writes_no_record(self):
        """Release 1019g: a dry sizing (`_event_keep_room`'s) writes nothing on the side row, the round-up's included."""
        from league.tests.test_events_1019g import DROP as DROP5, buys_of

        h = A85.short_of_cash(self.harness(cash="150"), "150")
        self.to_close(h)
        [drop] = buys_of(h, DROP5)
        self.assertEqual(self.kept(h).usd, D(80))
        row = h.state.rows("SELECT target_usd, binding, sized_usd FROM eq_event_intents WHERE iid=?", (drop["iid"],))[0]
        self.assertEqual((row["target_usd"], row["binding"], row["sized_usd"]), (None, None, None))


# ================================================================================================ PL-2, an invented week
BIRTH_OPEN = "EVL-B-8K-502"
BIRTH_CLOSE = "EVL-B-NEWSDAY-HI"


def old_room_key(program: str, band: str | None) -> tuple[int, int]:
    """Release 1019g's `room_key` (a frozen copy): a birth after every PREREG program, whatever its band."""
    found = next((p for p in EB.seatable() if p.id == program), None)
    if found is not None and found.spec is not None:
        return (EB.BIRTH_ROOM, EB.order_of(program))
    return (EB.PRIORITY.get(str(band), 9), EB.order_of(program))


class PromotedBirths(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(P.load_births, None)
        st = S.Store(Path(tmp.name) / "events")
        self.addCleanup(st.close)
        for seq, sp in enumerate((spec(BIRTH_OPEN, "8k", {"items": ["5.02"]}),
                                  spec(BIRTH_CLOSE, "news-day", {"score_min": 2}, exit_="open"))):
            st.db.execute("INSERT INTO births(id, version, sha, spec, seatable, registered_at, committed_at, received_at, "
                          "path, commit_sha, seq, line, why, by, night) VALUES(?, 1, ?, ?, 1, ?, ?, ?, "
                          "'docs/births/x.jsonl', ?, ?, '{}', 'x', 'captain', '2026-11-02')",
                          (sp["id"], BI.sha(sp), BI.canonical(sp), "2026-11-03T01:00:00Z", "2026-11-03T01:00:00Z",
                           "2026-11-03T01:00:00Z", "c" * 40, seq))
        P.load_births(st)
        self.prereg = [p.id for p in EB.seatable() if p.spec is None]
        self.births = [p.id for p in EB.seatable() if p.spec is not None]
        self.assertEqual((len(self.prereg), self.births), (15, [BIRTH_OPEN, BIRTH_CLOSE]))

    def week(self, birth_band: str):
        """An invented week: 5 sessions x 2 auctions; each auction, every PREREG program at an invented band (some at
        Sized and Probe) and each birth wanting invented ranked picks from one shared pool of 14 names (so names
        collide), with invented rooms. Yields (auction, wanted, rooms, bands)."""
        rng = random.Random(1019)
        pool = [f"N{i:02d}" for i in range(14)]
        prereg_band = {p: rng.choice(("learning", "learning", "probe", "sized")) for p in self.prereg}
        for session in range(5):
            for at in ("open", "close"):
                wanted, rooms, bands = {}, {}, {}
                for program in self.prereg + self.births:
                    k = rng.randint(0, 6)
                    picks = [EB.Pick(program, 2, f"e:{program}:{session}:{at}:{j}", sym, f"c-{sym}", float(rng.randint(1, 3)),
                                     1e6, D("16"), "t") for j, sym in enumerate(rng.sample(pool, k))]
                    wanted[program] = picks
                    rooms[program] = rng.randint(0, 6)
                    bands[program] = birth_band if program in self.births else prereg_band[program]
                yield f"{session}:{at}", wanted, rooms, bands

    def run_week(self, birth_band: str, key) -> dict:
        out = {}
        with mock.patch.object(EB, "room_key", key):
            for auction, wanted, rooms, bands in self.week(birth_band):
                given, passed = EB.allocate(wanted, rooms, bands)
                sends = []
                for program, picks in given.items():
                    sends += [(EB.send_key(program, bands[program], n), program, p.symbol) for n, p in enumerate(picks)]
                out[auction] = ({k: [p.symbol for p in v] for k, v in given.items()},
                                [s[1:] for s in sorted(sends)], {k: dict(v) for k, v in passed.items()},
                                {p: (EB.reserved_for(p, bands[p]), EB.leaves_room(p, bands[p])) for p in wanted})
        return out

    def test_while_no_birth_is_promoted_no_prereg_programs_real_money_pick_changes(self):
        before, after = self.run_week("learning", old_room_key), self.run_week("learning", EB.room_key)
        self.assertEqual(after, before, "the allocation, the sends' order, the passed-over picks and A85's reads, "
                                        "every auction of the week: identical")
        given = sum(len(v) for g, _, _, _ in after.values() for k, v in g.items() if k in self.prereg)
        self.assertGreater(given, 60, "the week gives the PREREG programs real picks")
        collided = sum(v.get("name_given", 0) for _, _, passed, _ in after.values() for k, v in passed.items()
                       if k in self.births)
        self.assertGreater(collided, 5, "and the births want names the PREREG programs take")
        for program in self.prereg:
            for band in ("learning", "probe", "sized"):
                self.assertEqual(EB.room_key(program, band), old_room_key(program, band), (program, band))
        for program in self.births:
            self.assertEqual(EB.room_key(program, "learning"), old_room_key(program, "learning"), program)

    def test_a_promoted_birth_takes_its_bands_tier_and_the_week_changes(self):
        before, after = self.run_week("probe", old_room_key), self.run_week("probe", EB.room_key)
        self.assertNotEqual(after, before, "a promoted birth moves ahead of every learning row: picks change")
        bands = {auction: b for auction, _, _, b in self.week("probe")}
        for auction, (given, sends, _, reads) in after.items():
            for program in self.births:
                self.assertEqual(reads[program], (True, False), "A85 reserves for it; its buys leave no room")
            order = [program for program, _ in sends]
            births_at = [i for i, p in enumerate(order) if p in self.births]
            learning_at = [i for i, p in enumerate(order) if bands[auction][p] == "learning"]
            sized_at = [i for i, p in enumerate(order) if bands[auction][p] == "sized"]
            if births_at and learning_at:
                self.assertLess(max(births_at), min(learning_at), f"{auction}: every birth buy before every learning buy")
            if births_at and sized_at:
                self.assertLess(max(sized_at), min(births_at), f"{auction}: every Sized buy before a Probe birth's")
        for program in self.births:
            for prog in self.prereg:
                self.assertLess(EB.room_key(prog, "probe"), EB.room_key(program, "probe"), "after the band's PREREG rows")
                self.assertLess(EB.room_key(program, "probe"), EB.room_key(prog, "learning"), "before every learning row")

if __name__ == "__main__":
    unittest.main()
