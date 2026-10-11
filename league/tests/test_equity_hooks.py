"""The equity lane's thin hooks in league/live (release E1; league/equity/INTERFACES.md section 6; amendments A1, A8):
the one door (`league/live/equity_hook.py`), the account's shares (`OptionsLive._close_shares`, A8.2: unattributed
shorts covered at once, unattributed longs sold after two readings, owned lots never touched), the share-event ledger,
`real_block` on the equity freeze and a negative cash balance, the one `equity.tick` a minute, and in the real book:
`ingest` leaving `lq-` orders alone, `reconcile` with lots and assignment shares as Decimal, THE PROBE LOSS BUDGET's
union of both lanes, the options reservation under the House-wide cash rule (A8.1) and the one day order count (A8.3).

The equity book itself (league/equity/live.py, the book package) is a fake here (`FakeBook`), mocked at the interface
INTERFACES.md fixes; the one test that reads its real row functions says so."""

import dataclasses
import datetime as dt
import sqlite3
import tempfile
import types
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

try:
    import numpy  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.live import equity_hook as H
    from league.live import money as M
    from league.live import real as R
    from league.live.real import RealBook
    from league.live.state import LiveState
    from league.live.venue import MarketData
    from league.tests.live_fakes import MONDAY, VERTICAL, Clock, Market, Venue, at, family
    from league.tests.test_live_step import LiveCase


class FakeBook:
    """The equity book as the hooks see it (league/equity/live.py `EquityBook`'s reading surface)."""

    def __init__(self, owned=None, *, frozen="", busy=()):
        self.owned = {k: D(str(v)) for k, v in dict(owned or {}).items()}
        self.frozen = frozen
        self.working = set(busy)
        self.fail = None
        self.ticks = []
        self.tick_error = None
        self.taken = []

    def expected_shares(self):
        if self.fail:
            raise RuntimeError(self.fail)
        return dict(self.owned)

    def busy(self):
        return set(self.working)

    def shares_taken(self, symbol, qty, px, *, why):
        taken = min(self.owned.get(symbol, D(0)), qty)
        self.taken.append((symbol, taken, px))
        self.owned = {k: v for k, v in {**self.owned, symbol: self.owned.get(symbol, D(0)) - taken}.items() if v}
        return taken

    def tick(self, now, **kw):
        self.ticks.append((now, kw))
        if self.tick_error:
            raise self.tick_error
        return {"ticked": now}

    def health(self):
        return {"frozen": self.frozen, "lots": len(self.owned)}


def equity_table(table=None, **kw):
    """The money table in force with an equity block's reading surface (money's `EquityTable` attributes the hooks read)."""
    block = types.SimpleNamespace(cash_reserve=D("50"), open_risk_weight={"etf": D("0.20"), "stock": D("0.40")}, **kw)
    return dataclasses.replace(table or M.Table.from_constitution(), equity=block)


def available_cash(account, *, working_buys_worst, reserved, reserve_usd):
    """money's `available_cash` as its docstring fixes it (A8.1), for the hooks' wiring tests only."""
    return (D(str(account["cash"])) - abs(D(str(account.get("short_market_value") or 0))) - working_buys_worst - reserved
            - reserve_usd)


def lot_tables(state):
    """The equity book's two row tables, columns as league/equity/live.py `SCHEMA` (enough for the hooks' existence
    checks and raw reads; the book creates the real ones)."""
    state.execute("CREATE TABLE IF NOT EXISTS eq_lots (lid INTEGER PRIMARY KEY, instance TEXT, symbol TEXT, class TEXT, "
                  "qty TEXT, status TEXT)")
    state.execute("CREATE TABLE IF NOT EXISTS eq_orders (eid INTEGER PRIMARY KEY, client_id TEXT, status TEXT)")


# ------------------------------------------------------------------------------------------------ the one door
@unittest.skipUnless(HAVE, "numpy not installed")
class TheDoor(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.state = LiveState(Path(self.dir.name) / "live.sqlite", clock=Clock(at(MONDAY, 10, 0)))

    def tearDown(self):
        self.state.close()
        self.dir.cleanup()

    def test_the_names(self):
        self.assertTrue(H.is_equity_client_id("lq-7-seed-overnight-spy"))
        self.assertFalse(H.is_equity_client_id("lv-a1b2-0000001-f"))
        self.assertFalse(H.is_equity_client_id(None))
        self.assertTrue(H.is_equity_row({"family": "f", "lane": "beta"}))
        self.assertTrue(H.is_equity_row({"family": "f", "lane": "equity"}))
        self.assertFalse(H.is_equity_row({"family": "f"}))
        self.assertFalse(H.is_equity_row(None))
        from league.equity import live as B

        self.assertEqual(H.SHARE_TOLERANCE, B.SHARE_TOLERANCE)
        self.assertEqual(H.CLIENT_PREFIX, B.CLIENT_PREFIX)

    def test_no_book_is_nothing_owned_and_an_unreadable_one_fails_closed(self):
        self.assertEqual(H.expected_shares(None), {})
        self.assertEqual(H.frozen(None), "")
        self.assertEqual(H.busy(None), set())
        self.assertIsNone(H.health(None))
        book = FakeBook({"spy": "2.5"}, frozen="")
        self.assertEqual(H.expected_shares(book), {"SPY": D("2.5")})
        book.fail = "sqlite is locked"
        with self.assertRaises(RuntimeError):
            H.expected_shares(book)
        broken = H.Unreadable("the equity book cannot be read: it could not be built")
        self.assertTrue(H.frozen(broken).startswith(H.UNREADABLE))
        with self.assertRaises(RuntimeError):
            H.expected_shares(broken)

        class Raising:
            @property
            def frozen(self):
                raise OSError("disk")

        self.assertTrue(H.frozen(Raising()).startswith(H.UNREADABLE))

    def test_a_state_from_before_e1_never_reaches_the_equity_book(self):
        from league.equity import live as B

        with mock.patch.object(B, "probe_figures", side_effect=AssertionError("not called")), \
                mock.patch.object(B, "working_buys_worst", side_effect=AssertionError("not called")), \
                mock.patch.object(B, "orders_today", side_effect=AssertionError("not called")), \
                mock.patch.object(B, "invested", side_effect=AssertionError("not called")):
            figures = H.probe_figures(self.state.rows, table=None)
            self.assertEqual((figures.programs, figures.closes, figures.open_risk), (0, (), D(0)))
            self.assertEqual(H.working_buys_worst(self.state.rows), D(0))
            self.assertEqual(H.orders_today(self.state.rows, "2026-09-28"), 0)
            self.assertEqual(H.invested(self.state.rows), D(0))
            self.assertEqual(H.open_risk(self.state.rows, table=None), D(0))

    def test_the_rows_go_to_the_book_with_the_tables_equity_weights(self):
        from league.equity import live as B

        lot_tables(self.state)
        seen = []

        def figures(rows, *, weights):
            seen.append(weights)
            return B.ProbeFigures(programs=1, closes=(("2026-09-28", D("-3.10")),), open_risk=D("12.50"))

        with mock.patch.object(B, "probe_figures", side_effect=figures), \
                mock.patch.object(B, "working_buys_worst", return_value=D("99.50")), \
                mock.patch.object(B, "orders_today", return_value=7), mock.patch.object(B, "invested", return_value=D("400")):
            self.assertEqual(H.open_risk(self.state.rows, table=equity_table()), D("12.50"))
            self.assertEqual(seen[-1], {"etf": D("0.20"), "stock": D("0.40")})
            # A table without the equity block: every class weighs its whole value (fail closed).
            H.probe_figures(self.state.rows, table=dataclasses.replace(M.Table.from_constitution(), equity=None))
            self.assertEqual(seen[-1], {"etf": D(1), "stock": D(1)})
            self.assertEqual(H.working_buys_worst(self.state.rows), D("99.50"))
            self.assertEqual(H.orders_today(self.state.rows, "2026-09-28"), 7)
            self.assertEqual(H.invested(self.state.rows), D("400"))

    def test_band_for_is_the_equity_bands(self):
        from league.equity import bands as EB

        with mock.patch.object(EB, "band_for_row", return_value=("probe", "seated")) as band:
            self.assertEqual(H.band_for({"family": "f", "lane": "beta"}), ("probe", "seated"))
        band.assert_called_once()


@unittest.skipUnless(HAVE, "numpy not installed")
class BuildingTheBook(unittest.TestCase):
    """`build_book`: None without a real account or an equity block (nothing held); fail closed when the state holds
    equity shares it cannot account for."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.alerts = []
        self.state = LiveState(Path(self.dir.name) / "live.sqlite", clock=Clock(at(MONDAY, 10, 0)))
        from league.live.families import MemoryFamilies

        self.live = types.SimpleNamespace(
            real=object(), paper=object(), market=object(), state=self.state, table=equity_table(), decider=object(),
            book=object(), root=Path(self.dir.name), clock=Clock(at(MONDAY, 10, 0)), families=MemoryFamilies(),
            record=lambda *a, **k: None, alert=lambda level, text: self.alerts.append((level, text)),
            sizing_equity=lambda: D("2229"))

    def tearDown(self):
        self.state.close()
        self.dir.cleanup()

    def test_no_real_account_no_book(self):
        self.live.real = None
        self.assertIsNone(H.build_book(self.live))

    def test_no_equity_block_and_nothing_held_no_book(self):
        self.live.table = dataclasses.replace(self.live.table, equity=None)
        self.assertIsNone(H.build_book(self.live))
        self.assertEqual(self.alerts, [])

    def test_no_equity_block_while_lots_are_held_fails_closed(self):
        self.live.table = dataclasses.replace(self.live.table, equity=None)
        lot_tables(self.state)
        self.state.execute("INSERT INTO eq_lots (lid, instance, symbol, class, qty, status) VALUES (1, 'f@1:r', 'SPY', "
                           "'etf', '0.5', 'open')")
        book = H.build_book(self.live)
        self.assertIsInstance(book, H.Unreadable)
        self.assertTrue(H.frozen(book))
        self.assertEqual([lvl for lvl, _ in self.alerts], ["error"])

    def test_the_book_is_built_with_the_houses_parts(self):
        from league.equity import families as EF
        from league.equity import live as B
        from league.live import paper as P

        made = {}

        class Book:
            def __init__(self, *args, **kw):
                made["args"], made["kw"] = args, kw

        with mock.patch.object(B, "EquityBook", Book), mock.patch.object(EF, "MemoryEquityFamilies", lambda: "memory"):
            book = H.build_book(self.live)
        self.assertIsInstance(book, Book)
        state, real, market, table, families = made["args"]
        self.assertEqual((state, real, market, table, families), (self.state, self.live.real, self.live.market,
                                                                  self.live.table, "memory"))
        kw = made["kw"]
        self.assertIs(kw["decider"], self.live.decider)
        self.assertIs(kw["options_book"], self.live.book)
        self.assertIsInstance(kw["stock_proof"], P.StockPaperProof)
        self.assertEqual(kw["stock_proof"].key, "paper_proof_stock")
        self.assertEqual(kw["sizing_equity"](), D("2229"))
        # One proof at a time on the practice account: the stock proof starts once the options route's have passed.
        self.assertTrue(kw["stock_proof"].after(), "no options proof on this House")
        self.live.proof = types.SimpleNamespace(passed=lambda: True)
        self.live.proof_single = types.SimpleNamespace(passed=lambda: False)
        with mock.patch.object(B, "EquityBook", Book), mock.patch.object(EF, "MemoryEquityFamilies", lambda: "memory"):
            H.build_book(self.live)
        self.assertFalse(made["kw"]["stock_proof"].after())

    def test_a_book_that_cannot_be_built(self):
        from league.equity import live as B

        with mock.patch.object(B, "EquityBook", side_effect=RuntimeError("bad release")), \
                mock.patch("league.equity.families.MemoryEquityFamilies", lambda: None):
            self.assertIsNone(H.build_book(self.live), "nothing held: the lane does not run")
            lot_tables(self.state)
            self.state.execute("INSERT INTO eq_orders (eid, client_id, status) VALUES (1, 'lq-1-f', 'working')")
            self.assertIsInstance(H.build_book(self.live), H.Unreadable, "a working order: fail closed")
        self.assertEqual([lvl for lvl, _ in self.alerts], ["error", "error"])


# ------------------------------------------------------------------------------------------------ league/live/step.py
@unittest.skipUnless(HAVE, "numpy not installed")
class TheAccountsShares(LiveCase):
    """A8.2: `_close_shares` sells or covers only what no program owns; a lot the equity book owns is never touched (the
    review's cases, the gateway's cover rule among them, are league/tests/test_equity_fx_hooks.py's)."""

    def start(self, owned=None, **kw):
        live = self.make([])
        live.equity = FakeBook(owned, **kw)
        self.run_to(9, 31)
        return live

    def stock(self):
        return [b for b in self.venue.sent if b.get("symbol") == "SPY"]

    def test_owned_lots_are_never_touched(self):
        live = self.start({"SPY": "2.5"})
        self.venue.held["SPY"] = D("2.5")
        for _ in range(3):
            live._close_shares()
        self.assertEqual(self.stock(), [])
        self.assertFalse(live._stock_held, "held equity lots never hold the assignment latch")

    def test_a_long_excess_is_sold_after_two_readings_and_only_the_excess(self):
        live = self.start({"SPY": "2.5"})
        live._book_shares("OPEXC", "SPY261016C00600000", 1)          # a long call exercised: 100 shares received
        self.venue.held["SPY"] = D("102.5")
        live._close_shares()
        self.assertEqual(self.stock(), [], "the first reading only remembers it")
        self.assertEqual({k: D(v) for k, v in live.state.get("unattributed_seen").items()}, {"SPY": D("100")})
        self.assertTrue(live._stock_held)
        live._close_shares()
        [sale] = self.stock()
        self.assertEqual((sale["side"], sale["type"], sale["qty"]), ("sell", "market", "100"))
        self.assertTrue(sale["client_order_id"].startswith("lv-shares-spy-"))
        self.assertEqual(self.venue.held["SPY"], D("2.5"), "the lots are still held")
        self.assertTrue(any("SPY" in text for level, text in self.alerts if level == "error"))
        live._close_shares()
        self.assertEqual(len(self.stock()), 1)
        self.assertEqual(live.state.get("unattributed_seen"), {})

    def test_an_excess_gone_by_the_second_reading_is_never_sold(self):
        live = self.start({"SPY": "1"})
        self.venue.held["SPY"] = D("2")
        live._close_shares()
        live.equity.owned["SPY"] = D("2")         # the book's fill booked in between: the shares were its own
        live._close_shares()
        live._close_shares()
        self.assertEqual(self.stock(), [])

    def test_a_short_is_covered_at_once_by_exactly_the_accounts_short(self):
        live = self.start({"SPY": "2"})
        self.venue.held["SPY"] = D("-98")                              # an assignment's -100 netted with the 2-share lot
        live._close_shares()
        [cover] = self.stock()
        self.assertEqual((cover["side"], cover["type"], cover["qty"]), ("buy", "market", "98"),
                         "the gateway admits a cover of at most the short: never the lot's 2 shares with it")
        self.assertEqual(self.venue.held["SPY"], D("0"), "the account is flat")
        live._close_shares()
        self.assertEqual(live.equity.taken, [("SPY", D("2"), D("600.0"))], "the lot the assignment took: closed in the book")
        self.venue.held["SPY"] = D("-5")
        live._close_shares()
        self.assertEqual([b["qty"] for b in self.stock()], ["98", "5"], "nothing owned: covered to flat")
        self.assertEqual(len(live.equity.taken), 1)

    def test_an_account_below_the_lots_is_a_mismatch_never_an_order(self):
        live = self.start({"SPY": "5"})
        self.venue.held["SPY"] = D("3")
        live._close_shares()
        live._close_shares()
        self.assertEqual(self.stock(), [])
        problems = live.book.reconcile(self.venue.positions(), [], day=MONDAY, after_close=False,
                                       equity_shares=live._owned_shares())
        self.assertIn("SPY: 3 shares held, 5 expected", " ".join(problems))

    def test_a_symbol_with_a_working_order_in_either_book_waits(self):
        live = self.start({}, busy={"SPY"})
        self.venue.held["SPY"] = D("4")
        for _ in range(3):
            live._close_shares()
        self.assertEqual(self.stock(), [], "the equity book's working order")
        self.assertEqual(live.state.get("unattributed_seen"), {}, "a skipped reading is not a reading")
        live.equity.working = set()
        live._close_shares()
        live._close_shares()
        self.assertEqual([b["qty"] for b in self.stock()], ["4"])

    def test_an_unreadable_book_sells_no_long_share_and_still_covers_a_short(self):
        live = self.start({"SPY": "1"})
        live.equity.fail = "the book's rows are locked"
        self.venue.held["SPY"] = D("4")
        self.venue.held["QQQ"] = D("-3")
        for _ in range(3):
            live._close_shares()
        self.assertEqual(self.stock(), [])
        self.assertEqual([(b["symbol"], b["side"], b["qty"]) for b in self.venue.sent if b.get("symbol") == "QQQ"],
                         [("QQQ", "buy", "3")])
        self.assertTrue(live._stock_held, "not known to be clear")


@unittest.skipUnless(HAVE, "numpy not installed")
class TheShareLedger(LiveCase):
    """A8.2: each assignment and exercise books 100 shares a contract on its underlying; the House's share orders move
    it back toward zero as they fill; reconciliation expects it beside the equity lots."""

    def test_the_sign_of_each_event(self):
        live = self.make([])
        live._book_shares("OPASN", "SPY261016C00600000", 2)          # a short call assigned: shares delivered
        self.assertEqual(live.state.get("shares"), {"SPY": "-200"})
        live._book_shares("OPASN", "QQQ261016P00500000", 1)          # a short put assigned: shares received
        live._book_shares("OPEXC", "SPY261016C00600000", 1)          # a long call exercised: received
        live._book_shares("OPEXC", "IWM261016P00200000", 3)          # a long put exercised: delivered
        live._book_shares("OPASN", "SPXW261016C06000000", 1)         # an index option settles in cash
        self.assertEqual(live.state.get("shares"), {"SPY": "-100", "QQQ": "100", "IWM": "-300"})

    def test_an_assignment_netted_against_a_lot_is_covered_the_lot_closed_and_the_latch_lifts(self):
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 600})])
        live.equity = FakeBook()
        self.run_to(9, 31)
        live.equity.owned["SPY"] = D("0.5")                            # a program's ETF lot on the same symbol
        [pos] = live.book.positions.values()
        short_leg = next(leg for leg in pos.legs if leg.side < 0)
        contracts = self.venue.held[short_leg.symbol]
        self.venue.held[short_leg.symbol] = D(0)
        self.venue.held["SPY"] = contracts * 100 + D("0.5")
        self.venue.activity_rows.append({"id": "asn1", "activity_type": "OPASN", "symbol": short_leg.symbol,
                                         "qty": str(-contracts), "date": "2026-09-28"})
        live._activities_at = float("-inf")
        self.run_to(9, 33)
        short = -contracts * 100 - D("0.5")                            # what the account shows: 99.5 short
        [cover] = [b for b in self.venue.sent if b.get("symbol") == "SPY"]
        self.assertEqual((cover["side"], cover["qty"]), ("buy", str(int(short))),
                         "the account's short and never more (the gateway refuses a buy that covers and opens): its "
                         "whole shares at once")
        self.assertEqual(self.venue.held["SPY"], D("-0.5"))
        self.assertEqual(live.equity.taken, [("SPY", D("0.5"), D("600.0"))], "the lot went with the assignment: closed")
        self.assertEqual(live.state.get("shares"), {"SPY": "-0.5"}, "what is left of the delivery is the fraction")
        self.assertFalse([p for p in live.book.mismatch if p.startswith("SPY")])
        live._activities_at = float("-inf")
        self.run_to(9, 34)
        self.assertEqual([b["qty"] for b in self.venue.sent if b.get("symbol") == "SPY"], [str(int(short)), "0.5"],
                         "the fraction of a share at the next reading")
        self.assertEqual(self.venue.held["SPY"], D("0"), "flat")
        self.assertEqual(live.state.get("shares"), {}, "the covers filled: the ledger is back at zero")
        self.assertEqual(live.state.get("shares_orders"), {})
        self.assertFalse([p for p in live.book.mismatch if p.startswith("SPY")])
        live._activities_at = float("-inf")
        self.run_to(9, 37)
        self.assertIsNone(live.state.get("assignment_latch"), "resolved: the short covered, the lot closed")

    def test_the_owners_clear_resets_the_ledger(self):
        live = self.make([])
        live._book_shares("OPASN", "SPY261016P00600000", 1)
        live.state.put("assignment_latch", {"why": "an assignment on SPY261016P00600000 (1 contracts)", "at": 0})
        live.state.put("owner_clear_assignment", {"by": "the owner"})
        live.owner_actions()
        self.assertIsNone(live.state.get("assignment_latch"))
        self.assertIsNone(live.state.get("shares"), "the owner says the shares are resolved")

    def test_reconciliation_expects_the_ledger_beside_the_lots_until_the_shares_are_sold(self):
        live = self.make([])
        self.run_to(9, 31)
        live.equity = FakeBook({"SPY": "0.25"})
        live._book_shares("OPASN", "SPY261016P00600000", 1)          # +100 received
        self.venue.held["SPY"] = D("100.25")
        problems = live.book.reconcile(self.venue.positions(), [], day=MONDAY, after_close=False,
                                       shares=live.state.get("shares"), equity_shares=live._owned_shares())
        self.assertEqual(problems, [])
        live._close_shares()
        live._close_shares()                                          # two readings: the 100 are sold, the lot is not
        [sale] = [b for b in self.venue.sent if b.get("symbol") == "SPY"]
        self.assertEqual((sale["side"], sale["qty"]), ("sell", "100"))
        self.assertEqual(live.state.get("shares"), {"SPY": "100"}, "not yet read back")
        live._close_shares()
        self.assertEqual(live.state.get("shares"), {}, "its fill moved the ledger to zero")
        self.assertEqual(live.book.reconcile(self.venue.positions(), [], day=MONDAY, after_close=False,
                                             shares=live.state.get("shares"), equity_shares=live._owned_shares()), [])


@unittest.skipUnless(HAVE, "numpy not installed")
class TheMinute(LiveCase):
    def test_one_tick_a_minute_on_every_branch_after_the_options_reads(self):
        live = self.make([])
        live.equity = book = FakeBook()
        sunday = dt.date(2026, 9, 27)
        for t, state in ((at(sunday, 12, 0), "closed"), (at(MONDAY, 9, 0), "before the open"),
                         (at(MONDAY, 9, 31), "session"), (at(MONDAY, 16, 5), "after the close")):
            self.clock.set(t)
            out = live.minute()
            self.assertEqual(out["state"], state)
            self.assertEqual(out["equity"], {"ticked": t})
        self.assertEqual([now for now, _ in book.ticks], [at(sunday, 12, 0), at(MONDAY, 9, 0), at(MONDAY, 9, 31),
                                                          at(MONDAY, 16, 5)])
        session = book.ticks[2][1]
        self.assertEqual(session["real_block"], live.real_block)
        self.assertEqual(session["killed"], live._killed)
        self.assertEqual(session["account_row"]["equity"], "5481.65")
        self.assertIsNotNone(session["positions"], "the session minute's own positions read")
        self.assertIsInstance(session["open_orders"], list)

    def test_an_equity_failure_never_ends_the_options_minute(self):
        live = self.make([family("vert", VERTICAL, band="probe")])
        live.equity = FakeBook()
        live.equity.tick_error = RuntimeError("the book broke")
        out = self.run_to(9, 31)
        self.assertEqual(out["state"], "session")
        self.assertIn("the book broke", out["equity"]["error"])
        self.assertEqual(len(live.book.positions), 1, "the options path traded")
        self.assertTrue(any("equity book's minute failed" in text for _, text in self.alerts))
        self.assertEqual(live.health()["equity"], {"frozen": "", "lots": 0})


@unittest.skipUnless(HAVE, "numpy not installed")
class TheBlock(LiveCase):
    def test_the_equity_freeze_blocks_options_opens(self):
        live = self.make([])
        live.equity = FakeBook()
        self.run_to(9, 31)
        self.assertIsNone(live.real_block())
        live.equity = FakeBook(frozen="SPY: 3 shares held, 5 expected")
        self.assertEqual(live.real_block(), "equity reconciliation: SPY: 3 shares held, 5 expected")
        live.equity = H.Unreadable("the equity book cannot be read: it could not be built")
        self.assertIn("equity reconciliation: the equity book cannot be read", live.real_block())

    def test_a_negative_cash_balance_refuses_every_open_and_alarms_once(self):
        live = self.make([])
        live.equity = FakeBook()
        self.run_to(9, 31)
        live.account_row = dict(live.account_row, cash="-12.40")
        for _ in range(3):
            self.assertIn("cash is below zero", live.real_block())
        self.assertEqual(sum(1 for _, text in self.alerts if "cash is below zero" in text), 1)
        live.account_row = dict(live.account_row, cash="10.00")
        self.assertIsNone(live.real_block())


# ------------------------------------------------------------------------------------------------ league/live/real.py
@unittest.skipUnless(HAVE, "numpy not installed")
class TheRealBook(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock(at(MONDAY, 10, 0))
        self.market = Market(self.clock)
        self.venue = Venue(self.market)
        self.state = LiveState(Path(self.dir.name) / "live.sqlite", clock=self.clock)
        self.book = RealBook(self.state, self.venue, M.Table.from_constitution(), clock=self.clock)

    def tearDown(self):
        self.state.close()
        self.dir.cleanup()

    def recon(self, **kw):
        return self.book.reconcile(self.venue.positions(), [], day=MONDAY, after_close=False, **kw)

    def test_ingest_never_takes_an_equity_order_for_a_foreign_one(self):
        rows = [{"id": "e1", "client_order_id": "lq-12-seed-overnight-spy", "status": "new", "symbol": "SPY", "legs": None},
                {"id": "p1", "client_order_id": "lq-pp-20261012-ab12-1-b", "status": "partially_filled", "symbol": "SPY"}]
        self.assertEqual(self.book.ingest(rows), [])
        self.assertEqual([r["id"] for r in self.book.ingest(rows + [{"id": "m1", "client_order_id": "manual", "status": "new"}])],
                         ["m1"])

    def test_reconcile_holds_lots_and_assignment_shares_as_decimal(self):
        self.venue.held["SPY"] = D("102.5")
        self.assertEqual(self.recon(shares={"SPY": "100"}, equity_shares={"SPY": D("2.5")}), [])
        self.venue.held["SPY"] = D("102.5000000005")                          # inside the venue's nine places
        self.assertEqual(self.recon(shares={"SPY": "100"}, equity_shares={"SPY": D("2.5")}), [])
        self.venue.held["SPY"] = D("102.500001")
        self.assertIn("SPY: 102.500001 shares held, 102.5 expected (equity lots 2.5, assignment shares 100)",
                      " ".join(self.recon(shares={"SPY": "100"}, equity_shares={"SPY": D("2.5")})))
        self.venue.held["SPY"] = D("-100")
        self.assertEqual(self.recon(shares={"SPY": "-100"}), [], "a short call's assignment, as the ledger says")
        del self.venue.held["SPY"]
        self.assertIn("QQQ: no shares held, 1.5 expected", " ".join(self.recon(equity_shares={"QQQ": D("1.5")})))
        self.assertEqual(self.recon(shares={"SPY": "0"}, equity_shares={"QQQ": D("0")}), [])

    def test_two_mismatched_readings_freeze_and_two_clean_ones_lift(self):
        self.venue.held["SPY"] = D("1")
        self.recon(equity_shares={"SPY": D("2")})
        self.recon(equity_shares={"SPY": D("2")})
        self.assertIn("SPY", self.book.frozen)
        self.recon(equity_shares={"SPY": D("1")})
        self.recon(equity_shares={"SPY": D("1")})
        self.assertEqual(self.book.frozen, "")

    def test_the_day_order_count_is_both_books(self):
        day = "2026-09-28"
        self.book._count(day, 236)
        legs = [R.RLeg("SPY260929C00600000", 1, 1, True, 600.0, "2026-09-29", 1),
                R.RLeg("SPY260929C00601000", -1, 1, True, 601.0, "2026-09-29", 2)]
        self.assertIsNone(self.book.path_refusal(legs, opening=True, day=day))
        self.assertIsNone(self.book.count_refusal(2, day=day))
        with mock.patch.object(H, "orders_today", return_value=13):
            self.assertEqual(self.book.house_count(day), 249)
            self.assertIn("the day's order count: 249 legs sent of 250", self.book.path_refusal(legs, opening=True, day=day))
            self.assertIn("the day's order count: 249 legs sent", self.book.count_refusal(2, day=day))
        self.assertEqual(self.book.count_today(day), 236, "the options book's own count is unchanged (the equity book reads it)")

    def test_the_options_reservation_obeys_the_house_wide_cash_rule(self):
        account = {"options_buying_power": "1000", "cash": "600", "short_market_value": "0", "equity": "600"}
        free, bound = self.book.free_to_reserve(account)
        if self.book.table.equity is None:
            self.assertEqual((free, bound), (1000.0, "options buying power"), "a table without the equity block")
        self.book.table = equity_table(self.book.table)
        with mock.patch.object(M, "available_cash", side_effect=available_cash) as cash, \
                mock.patch.object(H, "working_buys_worst", return_value=D("120")):
            free, bound = self.book.free_to_reserve(account)
            self.assertEqual((free, bound), (430.0, "the House-wide cash"), "600 - 120 of equity buys - the $50 reserve")
            kw = cash.call_args.kwargs
            self.assertEqual((kw["working_buys_worst"], kw["reserved"], kw["reserve_usd"]), (D("120"), D("0"), D("50")))
            free, bound = self.book.free_to_reserve(dict(account, cash="5000"))
            self.assertEqual((free, bound), (1000.0, "options buying power"))
            free, bound = self.book.free_to_reserve(dict(account, cash="-40"))
            self.assertLess(free, 0, "a negative balance leaves nothing free")
        with mock.patch.object(M, "available_cash", side_effect=ValueError("no cash")):
            self.assertEqual(self.book.free_to_reserve(account)[0], 0.0, "unreadable cash: nothing free")

    def test_exposure_carries_the_equity_figures(self):
        self.book.table = equity_table(self.book.table)
        with mock.patch.object(H, "open_risk", return_value=D("33.40")), mock.patch.object(H, "invested", return_value=D("167")):
            exposure = self.book.exposure("f", day="2026-09-28", week_start="2026-09-28")
        self.assertEqual((exposure.equity_open_risk, exposure.equity_invested), (D("33.40"), D("167")))


@unittest.skipUnless(HAVE, "numpy not installed")
class TheSharedBudget(unittest.TestCase):
    """A8.6: the equity rows join THE PROBE LOSS BUDGET: one slot a program, the weighted open risk, and each Probe
    lot's net cash in the window's worst stretch and the total, by its New York close day."""

    DAY = "2026-10-09"

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.state = LiveState(Path(self.dir.name) / "live.sqlite", clock=Clock(at(MONDAY, 10, 0)))
        lot_tables(self.state)

    def tearDown(self):
        self.state.close()
        self.dir.cleanup()

    def figures(self, programs=2, closes=(), open_risk="40"):
        from league.equity import live as B

        return mock.patch.object(B, "probe_figures", return_value=B.ProbeFigures(programs=programs, closes=tuple(
            (day, D(cash)) for day, cash in closes), open_risk=D(open_risk)))

    def test_the_tally_counts_programs_risk_and_closes(self):
        with self.figures(closes=(("2026-10-02", "-30"), ("2026-10-05", "12"))):
            self.assertEqual(R.probe_tally(self.state.rows, day=self.DAY, basis="gross", table=equity_table()),
                             (2, D("30"), D("40")))
            self.assertEqual(R.probe_tally(self.state.rows, day=self.DAY, basis="net", table=equity_table()),
                             (2, D("18"), D("40")))

    def test_the_window_reads_both_lanes_by_close_day(self):
        with self.figures(closes=(("2026-10-02", "-30"), ("2026-10-05", "12"), ("2026-10-07", "-25"), (None, "-5"))):
            self.assertEqual(R.probe_realized(self.state.rows, basis="gross", since="2026-10-05", table=equity_table()),
                             D("30"), "the 10-07 loss and the undated one; the 10-02 loss is before the window")
            self.assertEqual(R.probe_realized(self.state.rows, basis="net", since=None, table=equity_table()), D("48"))
            table = equity_table()
            open_n, window, total, at_risk, since = R.probe_figures(self.state.rows, day=self.DAY, table=table)
            self.assertEqual((open_n, at_risk), (2, D("40")))
            self.assertEqual(total, {"net": D("48"), "gross": D("60")}[table.probe_loss_basis], "from inception")

    def test_the_options_rows_are_unchanged_without_equity_rows(self):
        bare = LiveState(Path(self.dir.name) / "bare.sqlite", clock=Clock(at(MONDAY, 10, 0)))
        try:
            self.assertEqual(R.probe_tally(bare.rows, day=self.DAY, basis="gross"), (0, D(0), D(0)))
        finally:
            bare.close()

    def test_one_slot_a_program_and_the_class_weights_with_the_books_own_rows(self):
        """Cross-package (book): `league.equity.live.probe_figures` over real eq_lots rows."""
        from league.equity import live as B

        state = LiveState(Path(self.dir.name) / "book.sqlite", clock=Clock(at(MONDAY, 10, 0)))
        try:
            for statement in B.SCHEMA.split(";"):
                if statement.strip():
                    state.execute(statement)
            lot = ("INSERT INTO eq_lots (lid, instance, family, version, lane, symbol, class, qty, opened_qty, entry_px, "
                   "entry_notional, entry_at, mark, opened_at, opened_day, status, cash, probe, closed_at, exit_day) "
                   "VALUES (?, ?, ?, 1, 'beta', ?, ?, ?, ?, ?, ?, 'open', ?, 1.0, '2026-10-05', ?, ?, 1, ?, ?)")
            state.execute(lot, (1, "a@1:r", "a", "SPY", "etf", "0.5", "0.5", "100", "50", "110", "open", "-50", None, None))
            state.execute(lot, (2, "a@1:r", "a", "QQQ", "etf", "1", "1", "200", "200", "200", "open", "-200", None, None))
            state.execute(lot, (3, "b@1:r", "b", "AAPL", "stock", "2", "2", "100", "200", "90", "open", "-200", None, None))
            closed_at = dt.datetime(2026, 10, 7, 16, 0, tzinfo=dt.timezone.utc).timestamp()
            state.execute(lot, (4, "c@1:r", "c", "DIA", "etf", "0", "1", "400", "400", None, "closed", "-7.25", closed_at,
                                "2026-10-07"))
            open_n, realized, at_risk = R.probe_tally(state.rows, day=self.DAY, basis="gross", table=equity_table())
            self.assertEqual(open_n, 2, "programs a and b: one slot each, not one a lot")
            self.assertEqual(at_risk, D("0.20") * D("55") + D("0.20") * D("200") + D("0.40") * D("180"))
            self.assertEqual(realized, D("7.25"))
        finally:
            state.close()


# ------------------------------------------------------------------------------------------------ league/live/venue.py
@unittest.skipUnless(HAVE, "numpy not installed")
class TheBars(unittest.TestCase):
    def test_the_adjustment_is_sent_and_only_raw_or_all(self):
        urls = []

        class Client:
            def request(self, method, url, **kw):
                urls.append(url)
                return 200, {"bars": {"SPY": [{"t": "2026-10-09T04:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}]}}

        market = MarketData(Client())
        self.assertEqual(len(market.bars(["SPY"], timeframe="1Day", start="2026-10-01")["SPY"]), 1)
        self.assertIn("adjustment=raw", urls[-1])
        market.bars(["SPY"], timeframe="1Day", start="2026-10-01", adjustment="all")
        self.assertIn("adjustment=all", urls[-1])
        with self.assertRaises(ValueError):
            market.bars(["SPY"], timeframe="1Day", start="2026-10-01", adjustment="split")
        self.assertEqual(len(urls), 2, "refused before any request")


if __name__ == "__main__":
    unittest.main()
