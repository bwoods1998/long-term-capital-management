"""RELEASE 1019f: THE PROBE SIZE'S RECORD AND THE NAME WALL'S EQUITY (the read-only audit of the live House, its capacity
and probe lenses), through the REAL book, the REAL `size_entry`, the real money table in force and the lane's REAL store
(league/tests/test_events_book.py's harness). Every figure here is invented; none is a market's.

(a) A Probe or Sized buy that cash, the loss budget or a wall cuts below its band's target was labelled "probe" in the
lane's `real_fills` with no record of the target, so the Done reader could not tell a full Probe event from a cut one.
Held here: the buy's side row in `eq_event_intents` and its row in `real_fills` keep `target_usd` (the band's
`position_share` x E at the previous close) and `binding` (league/events/bands.py `BINDINGS`: cash, budget, invested,
name_wall, gateway, whole_shares, venue; NULL when none cut it), for every event buy from the release on; a sale and an
older row hold NULL; both tables gain the columns in place (idempotent), and an older release's writes still go.

(b) The House sized the 10% name wall on `last_equity` while the gateway judges the CURRENT equity, so a one-share buy
near 10% met the gateway's final refusal. Held here: the decision's name-wall skip and the send's instrument, sleeve and
book caps read `wall_equity`, the lower of E and the account's current equity as the House last read it; the band's
target stays on E at the previous close."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import sqlite3
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

from league.equity import live as L
from league.events import bands as BA
from league.events import book as EB
from league.events import store as LS
from league.live.state import LiveState
from league.tests import test_equity_book as T
from league.tests import test_events_book as TB
from league.tests.test_events_book import CIK, DAY, earnings

#: Release 1019d's `eq_event_intents`, as a House state from before release 1019f holds it (a frozen copy).
OLD_EVENT_INTENTS = """
CREATE TABLE eq_event_intents (
    iid INTEGER PRIMARY KEY, program TEXT NOT NULL, version INTEGER NOT NULL, event TEXT NOT NULL,
    side TEXT NOT NULL, band TEXT, tif TEXT NOT NULL, otype TEXT NOT NULL,
    symbol TEXT NOT NULL, cik TEXT, day TEXT NOT NULL, at TEXT NOT NULL,
    rank_key REAL, adv20 REAL, prev_close TEXT, limit_px TEXT, sigma REAL, hold INTEGER, weight TEXT NOT NULL,
    exit_day TEXT, exit_at TEXT, lid INTEGER, rung INTEGER NOT NULL DEFAULT 0,
    decided_at TEXT NOT NULL, why TEXT, created_at REAL NOT NULL)
"""
#: Release 1019d's `real_fills`, as a lane store from before release 1019f holds it (a frozen copy).
OLD_REAL_FILLS = """
CREATE TABLE real_fills(program TEXT NOT NULL, version INTEGER NOT NULL, event TEXT NOT NULL,
  side TEXT NOT NULL, qty REAL NOT NULL, price REAL NOT NULL, fee REAL NOT NULL DEFAULT 0, filled_at TEXT NOT NULL,
  band TEXT NOT NULL, PRIMARY KEY(program, version, event, side))
"""
#: An older release's write of a fill (league/events/bands.py `record_fill` before release 1019f).
OLD_INSERT = ("INSERT OR IGNORE INTO real_fills(program, version, event, side, qty, price, fee, filled_at, band) "
              "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)")
PROBE = "EVL-8K-READ-O1"


def columns(db, table: str) -> set[str]:
    return {str(r[1]) for r in db.execute(f"PRAGMA table_info({table})")}


class PartialVenue(TB.AuctionVenue):
    """The auction venue whose cross fills `short` fewer shares than a BUY asks (the rest ends with the cross)."""

    short = D(2)

    def _try_fill(self, o: dict) -> None:
        if o.get("time_in_force") not in ("opg", "cls") or o["side"] != "buy":
            return super()._try_fill(o)
        asked = D(o["qty"])
        o["qty"] = str(asked - self.short)
        super()._try_fill(o)
        o["qty"] = str(asked)
        if o["status"] == "filled":
            o["status"] = "canceled"            # (the rest of the order ended unfilled at the cross)
            o["canceled_at"] = o["filled_at"]


class Base(TB.EventTest):
    def probe_buy(self, h: TB.Harness, *, prev_close: float = 16.0, band: str = "probe") -> None:
        """One 8.01 filing of PROBE's (EVL-8K-READ-O1) at `band`, its issuer's universe row with `prev_close` (the limit
        1.25 x it), quotes and sigma, and a print of 17.00 at DAY's open."""
        earnings(h.lane, "o-1", CIK, "OTHR", prev_close=prev_close, items=("8.01",))
        h.lane.band(PROBE, band)
        self.ready(h)
        h.symbol("OTHR", last=17.0)
        h.venue.prints[("OTHR", DAY.isoformat(), "open")] = D("17.00")

    def through_the_open(self, h: TB.Harness) -> None:
        for hh, mm in ((9, 15), (9, 16), (9, 31), (9, 33), (9, 35)):
            h.tick(hh, mm)

    def buy_row(self, h: TB.Harness) -> dict:
        [row] = h.event_intents("buy")
        return row

    def fill(self, h: TB.Harness, side: str = "buy") -> dict | None:
        rows = [f for f in h.lane.fills() if f["side"] == side]
        return rows[0] if rows else None

    def current_equity(self, h: TB.Harness, equity: str) -> None:
        """The account's CURRENT equity reads `equity`, its `last_equity` (the previous close) as before."""
        base = h.venue.account
        h.venue.account = lambda: {**base(), "equity": equity}


# ------------------------------------------------------------------------------------------------------- (a) the record
class TheProbeSizeRecord(Base):
    def test_a_probe_buy_at_its_target_keeps_the_target_and_no_binding_on_both_rows(self):
        h = self.harness()
        self.probe_buy(h)                                    # limit $20.00: 5% of E=$2,000 is five whole shares
        self.through_the_open(h)
        side = self.buy_row(h)
        self.assertEqual((side["status"], D(side["target_usd"]), side["binding"]), ("done", D("100"), None))
        self.assertEqual(h.bodies()[0]["qty"], "5")
        buy = self.fill(h)
        self.assertEqual((buy["band"], buy["qty"], buy["target_usd"], buy["binding"]), ("probe", 5.0, 100.0, None),
                         "the lane's row says the Probe buy was sized at its whole target")
        h.venue.prints[("OTHR", DAY.isoformat(), "close")] = D("17.50")
        for hh, mm in ((15, 46), (15, 47), (16, 1), (16, 3)):
            h.tick(hh, mm)
        sell = self.fill(h, "sell")
        self.assertEqual((sell["target_usd"], sell["binding"]), (None, None), "a sale has no target")

    def test_each_constraint_that_cuts_a_probe_buy_is_named_beside_its_target(self):
        cases = {
            # the House-wide cash: $2,000 less the options book's $1,890 reserved and the $50 reserve = $60: 3 shares
            "cash": (lambda h: setattr(h.options, "reserved_usd", 1890.0), 16.0, "3"),
            # the loss budget: $5 of room at the lot's weight 0.10 = $50: 2 shares
            "budget": (lambda h: setattr(h.book, "table", dataclasses.replace(h.book.table, probe_loss_budget=D("5"))),
                       16.0, "2"),
            # the 100% book: the options book's $1,950 of open maximum loss leaves $50: 2 shares
            "invested": (lambda h: setattr(h.options, "book_loss", D("1950")), 16.0, "2"),
            # no cap: the $100 target at a $30.00 limit floors to 3 whole shares ($90)
            "whole_shares": (lambda h: None, 24.0, "3"),
        }
        for binding, (setup, prev_close, qty) in cases.items():
            with self.subTest(binding=binding):
                self.tmp = tempfile.TemporaryDirectory()
                self.addCleanup(self.tmp.cleanup)
                self.root = Path(self.tmp.name)
                h = self.harness()
                self.probe_buy(h, prev_close=prev_close)
                setup(h)
                self.through_the_open(h)
                [body] = h.bodies()
                self.assertEqual(body["qty"], qty)
                side = self.buy_row(h)
                self.assertEqual((D(side["target_usd"]), side["binding"]), (D("100"), binding))
                buy = self.fill(h)
                self.assertEqual((buy["band"], buy["qty"], buy["target_usd"], buy["binding"]),
                                 ("probe", float(qty), 100.0, binding),
                                 "still labelled probe, and now the record says what cut it and from what")

    def test_the_gateways_final_refusal_is_its_binding_and_no_fill_is_written(self):
        h = self.harness()
        self.probe_buy(h)
        h.venue.gateway_refuses = "stock_position"           # (the gateway's 10% a name, its final answer)
        self.through_the_open(h)
        side = self.buy_row(h)
        self.assertEqual((side["status"], D(side["target_usd"]), side["binding"]), ("refused", D("100"), "gateway"))
        self.assertIsNone(self.fill(h))

    def test_a_gateway_refusal_of_a_reading_it_could_not_make_is_no_binding(self):
        h = self.harness()
        self.probe_buy(h)
        h.venue.gateway_refuses = "equity"                   # (a reading: sent again next minute, never final)
        h.tick(9, 15)
        h.tick(9, 16)
        side = self.buy_row(h)
        self.assertEqual((side["status"], side["binding"]), ("sent", None))

    def test_a_partial_fill_at_the_cross_is_the_venues(self):
        h = self.harness()
        h.venue = PartialVenue(h.market, h.clock, cash="2000")
        h.book = h.new_book()
        self.probe_buy(h)
        self.through_the_open(h)
        side = self.buy_row(h)
        self.assertEqual(side["binding"], None, "the sizing cut nothing")
        buy = self.fill(h)
        self.assertEqual((buy["qty"], buy["target_usd"], buy["binding"]), (3.0, 100.0, "venue"),
                         "five asked, three filled: the venue")

    def test_a_learning_buy_keeps_its_target_and_one_share_above_it_is_no_cut(self):
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME", prev_close=60.0)   # learning: a $40 target, one share at the $75 limit
        self.ready(h)
        h.symbol("ACME", last=50.0)
        h.venue.prints[("ACME", DAY.isoformat(), "open")] = D("60.00")
        self.through_the_open(h)
        side = self.buy_row(h)
        self.assertEqual((side["band"], D(side["target_usd"]), side["binding"]), ("learning", D("40"), None))
        buy = self.fill(h)
        self.assertEqual((buy["qty"], buy["target_usd"], buy["binding"]), (1.0, 40.0, None))

    def test_a_buy_the_sizing_refuses_records_what_refused_it(self):
        h = self.harness()
        self.probe_buy(h)
        h.options.reserved_usd = 1940.0                     # $10 of cash: no whole share at $20.00
        self.through_the_open(h)
        side = self.buy_row(h)
        self.assertEqual((side["status"], D(side["target_usd"]), side["binding"]), ("refused", D("100"), "cash"))
        self.assertIn("sizing", side["why"])
        self.assertEqual(h.bodies(), [])


# ---------------------------------------------------------------------------------- the dollars the send asked
class TheSentDollars(Base):
    """RELEASE 1019f's INTEGRATION (the honesty branch's independent check, its major): the record's `target_usd` is the
    dollars the sizing asked AT THE LIMIT (1.25 x the previous close) while `real_fills.price` is the fill's, so a full,
    uncut Probe buy that fills near the previous close costs about 0.8 x its target and the Done reader could not tell
    it from a cut one by the fill. Held here: `sized_usd`, the shares the send asked x the limit (0 when it sends none),
    on the buy's side row and its `real_fills` row, beside `target_usd`; the Done reader counts a Probe+ event only
    when `sized_usd` >= 0.8 x `target_usd`. Every expectation reads the money table in force (A86's Probe share)."""

    E = D("2000")
    LIMIT = D("20.00")                       # (probe_buy's previous close $16.00 x 1.25)

    def target(self, band: str = "probe") -> D:
        return EB.settings().share(band) * self.E

    def test_a_full_buy_records_the_shares_sent_x_the_limit_whatever_its_fill(self):
        h = self.harness()
        self.probe_buy(h)
        self.through_the_open(h)
        whole = (self.target() / self.LIMIT).to_integral_value(rounding="ROUND_DOWN")
        self.assertEqual(h.bodies()[0]["qty"], str(whole))
        side = self.buy_row(h)
        self.assertEqual((D(side["target_usd"]), D(side["sized_usd"]), side["binding"]),
                         (self.target(), whole * self.LIMIT, None))
        buy = self.fill(h)
        self.assertEqual((buy["target_usd"], buy["sized_usd"]), (float(self.target()), float(whole * self.LIMIT)))
        self.assertLess(buy["qty"] * buy["price"], 0.9 * buy["target_usd"], "its fill at $17.00 costs well under target")
        self.assertGreaterEqual(buy["sized_usd"], 0.8 * buy["target_usd"], "and it is a full Probe buy all the same")
        h.venue.prints[("OTHR", DAY.isoformat(), "close")] = D("17.50")
        for hh, mm in ((15, 46), (15, 47), (16, 1), (16, 3)):
            h.tick(hh, mm)
        self.assertIsNone(self.fill(h, "sell")["sized_usd"], "a sale has none")

    def test_a_buy_cash_cuts_records_what_it_sent_and_falls_under_the_line(self):
        h = self.harness()
        self.probe_buy(h)
        h.options.reserved_usd = 1925.0                     # $25 of cash: one share at $20.00
        self.through_the_open(h)
        side = self.buy_row(h)
        self.assertEqual((D(side["sized_usd"]), side["binding"]), (self.LIMIT, "cash"))
        buy = self.fill(h)
        self.assertEqual((buy["qty"], buy["sized_usd"], buy["binding"]), (1.0, 20.0, "cash"))
        self.assertLess(buy["sized_usd"], 0.8 * buy["target_usd"])

    def test_a_partial_fill_keeps_the_dollars_the_send_asked(self):
        h = self.harness()
        h.venue = PartialVenue(h.market, h.clock, cash="2000")
        h.book = h.new_book()
        self.probe_buy(h)
        self.through_the_open(h)
        whole = (self.target() / self.LIMIT).to_integral_value(rounding="ROUND_DOWN")
        buy = self.fill(h)
        self.assertEqual((buy["qty"], buy["sized_usd"], buy["binding"]),
                         (float(whole - PartialVenue.short), float(whole * self.LIMIT), "venue"))

    def test_one_share_above_a_learning_target_and_a_refused_buy(self):
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME", prev_close=60.0)   # learning: one share at the $75 limit, over its target
        self.ready(h)
        h.symbol("ACME", last=50.0)
        h.venue.prints[("ACME", DAY.isoformat(), "open")] = D("60.00")
        self.through_the_open(h)
        side = self.buy_row(h)
        self.assertEqual((D(side["target_usd"]), D(side["sized_usd"])), (self.target("learning"), D("75.00")))
        self.assertEqual(self.fill(h)["sized_usd"], 75.0)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        h = self.harness()
        self.probe_buy(h)
        h.options.reserved_usd = 1940.0                     # $10 of cash: no whole share at $20.00
        self.through_the_open(h)
        side = self.buy_row(h)
        self.assertEqual((side["status"], D(side["sized_usd"]), side["binding"]), ("refused", D("0"), "cash"))

    def test_older_states_gain_the_column_and_record_fill_checks_it(self):
        st = LiveState(self.root / "live.sqlite")
        st.execute(OLD_EVENT_INTENTS)
        st.close()
        h = self.harness()
        self.assertIn("sized_usd", columns(h.state.db, "eq_event_intents"))
        root = self.root / "lane"
        root.mkdir()
        db = sqlite3.connect(str(root / LS.DB_NAME))
        db.execute(OLD_REAL_FILLS)
        db.commit()
        db.close()
        with LS.Store(root) as st:
            self.assertIn("sized_usd", columns(st.db, "real_fills"))
            kw = dict(program=PROBE, version=2, event="e-1", qty=3, price=17.0, filled_at="z", band="probe")
            self.assertTrue(BA.record_fill(st, side="buy", fee=0.0, target_usd=70.0, binding=None, sized_usd=60.0, **kw))
            self.assertFalse(BA.record_fill(st, side="buy", fee=0.0, target_usd=70.0, binding=None, sized_usd=1.0, **kw),
                             "written once")
            self.assertEqual(st.db.execute("SELECT sized_usd FROM real_fills").fetchone()[0], 60.0)
            for bad in (dict(side="buy", sized_usd=-1.0), dict(side="buy", sized_usd=float("inf")),
                        dict(side="sell", sized_usd=60.0)):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    BA.record_fill(st, fee=0.0, **{**kw, "event": "e-bad", **bad})


# ------------------------------------------------------------------------------------------------------- the schemas
class TheColumns(Base):
    def test_a_house_state_from_before_gains_the_columns_in_place_and_again_is_nothing(self):
        st = LiveState(self.root / "live.sqlite")
        st.execute(OLD_EVENT_INTENTS)
        st.execute("INSERT INTO eq_event_intents(iid, program, version, event, side, band, tif, otype, symbol, day, at, "
                   "weight, decided_at, created_at) VALUES(1, ?, 2, 'e', 'buy', 'probe', 'opg', 'limit', 'OLDS', ?, "
                   "'open', '0.10', 'x', 0)", (PROBE, DAY.isoformat()))
        st.close()
        h = self.harness()
        self.assertTrue({"target_usd", "binding"} <= columns(h.state.db, "eq_event_intents"))
        old = h.state.rows("SELECT target_usd, binding FROM eq_event_intents WHERE iid=1")[0]
        self.assertEqual(old, {"target_usd": None, "binding": None}, "an older row reads NULL")
        h.book = h.new_book()                               # a second open: nothing to add, nothing raised
        self.assertEqual(sorted(c for c in columns(h.state.db, "eq_event_intents") if c in ("target_usd", "binding")),
                         ["binding", "target_usd"])

    def test_another_processs_add_between_the_look_and_the_alter_is_read_as_done(self):
        h = self.harness()
        real = h.state.rows
        hidden = {"n": 0}

        def rows(sql, params=()):
            out = real(sql, params)
            if sql.startswith("PRAGMA table_info(eq_event_intents)") and hidden["n"] == 0:
                hidden["n"] += 1
                return [r for r in out if r["name"] != "binding"]      # (the look saw it missing)
            return out
        with mock.patch.object(h.state, "rows", side_effect=rows):
            h.book._add_columns({"eq_event_intents": EB.SCHEMA_COLUMNS["eq_event_intents"]})   # duplicate: done
        with self.assertRaises(sqlite3.OperationalError):
            h.book._add_columns({"eq_event_intents": {"nope": "ALTER TABLE no_such_table ADD COLUMN nope TEXT"}})

    def test_a_lane_store_from_before_gains_the_columns_at_its_open_and_an_older_write_still_goes(self):
        root = self.root / "lane"
        root.mkdir()
        db = sqlite3.connect(str(root / LS.DB_NAME))
        db.execute(OLD_REAL_FILLS)
        db.execute(OLD_INSERT, (PROBE, 2, "e-old", "buy", 3, 10.0, 0.0, "2026-11-03T14:30:00Z", "probe"))
        db.commit()
        db.close()
        with LS.Store(root) as st:
            self.assertTrue({"target_usd", "binding"} <= columns(st.db, "real_fills"))
            row = dict(st.db.execute("SELECT * FROM real_fills WHERE event='e-old'").fetchone())
            self.assertEqual((row["qty"], row["target_usd"], row["binding"]), (3.0, None, None))
        with LS.Store(root) as st:                          # again: nothing to add
            self.assertEqual(LS.migrate_fills(st.db), [])
            st.db.execute(OLD_INSERT, (PROBE, 2, "e-roll", "buy", 1, 10.0, 0.0, "2026-11-03T14:30:00Z", "probe"))
            row = dict(st.db.execute("SELECT * FROM real_fills WHERE event='e-roll'").fetchone())
            self.assertEqual((row["target_usd"], row["binding"]), (None, None), "a rolled-back release's write goes")
            empty = sqlite3.connect(":memory:")
            self.addCleanup(empty.close)
            self.assertEqual(LS.migrate_fills(empty), [], "no real_fills table: nothing")

    def test_the_books_write_back_migrates_a_store_the_lane_has_not_opened_since(self):
        lane = self.root / EB.LANE_DIR
        lane.mkdir()
        db = sqlite3.connect(str(lane / LS.DB_NAME))
        db.execute(OLD_REAL_FILLS)
        db.commit()
        db.close()
        row = {"program": PROBE, "version": 2, "event": "e-1", "side": "buy", "qty": 3.0, "price": 17.0, "fee": 0.0,
               "filled_at": "2026-11-04T14:30:00Z", "band": "probe", "target_usd": 100.0, "binding": "cash"}
        self.assertEqual(EB.write_fills(self.root, [row]), 1)
        db = sqlite3.connect(str(lane / LS.DB_NAME))
        db.row_factory = sqlite3.Row
        got = dict(db.execute("SELECT * FROM real_fills").fetchone())
        db.close()
        self.assertEqual((got["target_usd"], got["binding"], got["band"]), (100.0, "cash", "probe"))

    def test_record_fill_writes_the_target_once_and_refuses_what_is_not_a_binding(self):
        with LS.Store(self.root / "lane") as st:
            kw = dict(program=PROBE, version=2, event="e-1", qty=3, price=17.0, filled_at="z", band="probe")
            self.assertTrue(BA.record_fill(st, side="buy", fee=0.0, target_usd=100.0, binding="budget", **kw))
            self.assertFalse(BA.record_fill(st, side="buy", fee=0.0, target_usd=50.0, binding=None, **kw),
                             "a write again changes nothing but the fee")
            row = dict(st.db.execute("SELECT * FROM real_fills").fetchone())
            self.assertEqual((row["target_usd"], row["binding"]), (100.0, "budget"))
            for bad in (dict(side="buy", binding="margin"), dict(side="buy", target_usd=-1.0),
                        dict(side="buy", target_usd=float("nan")), dict(side="sell", target_usd=100.0),
                        dict(side="sell", binding="cash")):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    BA.record_fill(st, fee=0.0, **{**kw, "event": "e-bad", **bad})
            self.assertTrue(BA.record_fill(st, side="sell", fee=0.01, **kw), "a sale with neither goes")
            self.assertEqual(BA.real_events(st, PROBE, 2)[0]["band"], "probe", "the band rules read as before")

    def test_the_vocabulary_is_the_lanes_and_every_sizing_cap_has_its_name(self):
        from league.equity import sizing as Z

        self.assertEqual(EB.BINDINGS, BA.BINDINGS)
        self.assertEqual(BA.BINDINGS, ("cash", "budget", "invested", "name_wall", "gateway", "whole_shares", "venue"))
        self.assertEqual({EB.binding_of(cap) for cap in Z.CAPS}, {"name_wall", "cash", "invested", "budget"})
        self.assertTrue(set(EB.SIZING_BINDINGS.values()) <= set(BA.BINDINGS))
        self.assertEqual([EB.binding_of(x) for x in ("intent", "short_held", "min_order", None)], [None] * 4)


# ------------------------------------------------------------------------------------------------------- (b) the equity
class TheWallsEquity(Base):
    def test_wall_equity_is_the_lower_of_e_and_the_current_equity(self):
        E = D("2000")
        self.assertEqual(L.wall_equity(E, {"equity": "1800.50"}), D("1800.50"))
        self.assertEqual(L.wall_equity(E, {"equity": "2500"}), E, "never above E")
        self.assertEqual(L.wall_equity(E, {"equity": "0"}), D(0), "an account at zero fits nothing")
        for unread in ({}, {"equity": None}, {"equity": "n/a"}, {"equity": "NaN"}, None):
            with self.subTest(unread=unread):
                self.assertEqual(L.wall_equity(E, unread), E)

    def test_the_decisions_name_wall_reads_the_current_equity(self):
        for equity, bought in (("2000", True), ("1800", False)):
            with self.subTest(equity=equity):
                self.tmp = tempfile.TemporaryDirectory()
                self.addCleanup(self.tmp.cleanup)
                self.root = Path(self.tmp.name)
                h = self.harness()
                self.probe_buy(h, prev_close=150.0)          # one share at the $187.50 limit: under 10% of $2,000
                self.current_equity(h, equity)
                h.tick(9, 15)
                h.tick(9, 16)
                summary = json.loads(h.state.rows("SELECT summary FROM eq_event_decisions WHERE at='open'")[0]["summary"])
                if bought:
                    self.assertEqual([(b["symbol"], b["qty"]) for b in h.bodies()], [("OTHR", "1")])
                else:
                    self.assertEqual(h.bodies(), [], "over 10% of the $1,800 the gateway judges: never sent")
                    self.assertEqual(h.event_intents("buy"), [])
                    self.assertEqual(summary["programs"][PROBE]["skipped"], {"name_wall": 1})

    def test_the_sends_caps_read_the_current_equity_and_the_target_stays_on_the_previous_close(self):
        h = self.harness()
        self.probe_buy(h, band="sized")                      # Sized: 10% of the previous close's $2,000 = $200
        self.current_equity(h, "1500")                       # the gateway's 10% a name is now $150
        self.through_the_open(h)
        [body] = h.bodies()
        self.assertEqual(body["qty"], "7", "$150 at the $20.00 limit: 7 whole shares, never the 10 the gateway refuses")
        side = self.buy_row(h)
        self.assertEqual((D(side["target_usd"]), side["binding"]), (D("200"), "name_wall"))
        buy = self.fill(h)
        self.assertEqual((buy["band"], buy["qty"], buy["target_usd"], buy["binding"]), ("sized", 7.0, 200.0, "name_wall"))

    def test_a_current_equity_above_the_previous_close_moves_nothing(self):
        h = self.harness()
        self.probe_buy(h, band="sized")
        self.current_equity(h, "2600")
        self.through_the_open(h)
        [body] = h.bodies()
        self.assertEqual(body["qty"], "10", "the walls never rise above E at the previous close")
        self.assertEqual((D(self.buy_row(h)["target_usd"]), self.buy_row(h)["binding"]), (D("200"), None))


if __name__ == "__main__":
    unittest.main()
