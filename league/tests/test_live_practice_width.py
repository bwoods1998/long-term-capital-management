"""The practice league at width (v3): THE STORE CLAMP (observe reads only what the Gym's store holds of a root, read
narrower rather than lost when a clamped read is over the page cap), THE READ BUDGET (24 roots' reads fit the minute,
measured through the real `MarketData` on store-shaped listings), the honest shed (a read skipped for the minute's time is
not pressure) and THE PRACTICE CAPS (a practice account holds what a Probe may, scaled to its shadow capital). With the
fakes of `live_fakes` (the venue's shapes, invented numbers), a store-shaped market-data gateway below, the in-process
decider and the observe store."""

import datetime as dt
import json
import math
import sqlite3
import sys
import time
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from league.tests.test_live_step import HAVE
from league.tests.test_live_practice import PracticeCase, code_on, trained, validated

if HAVE:
    import numpy as np

    from league.live import shadow as S
    from league.live import step as ST
    from league.live.decider import InlineDecider
    from league.live.families import MemoryFamilies
    from league.live.step import OptionsLive
    from league.live.venue import MarketData, Rate, VenueError, occ_parts, occ_symbol
    from league.tests.live_fakes import MONDAY, Clock, Market, at, iso

TUESDAY = MONDAY + dt.timedelta(days=1)


def wide(code: str, *, dte: int = 30, band: float = 0.3) -> str:
    """A program whose own window is wider than the store's: `dte` days and `band` of spot."""
    return code.replace('"dte": [0, 3], "band": 0.03', f'"dte": [0, {dte}], "band": {band}')


def wide_row(name: str, root: str, **kw) -> dict:
    return dict(validated(name, roots=(root,)), code=wide(code_on(root), **kw))


class Recording(Market if HAVE else object):
    """The fake market with every chain read's window recorded and, with `page_size`, the venue's paging: each page one
    market-data call, and past the read's `max_pages` the read refused as `MarketData.chain` refuses it."""

    def __init__(self, clock, *args, page_size: int | None = None, **kwargs):
        super().__init__(clock, *args, **kwargs)
        self.page_size = page_size
        self.paged: set[str] | None = None        # the roots paged (None: every root)
        self.windows: list[dict] = []
        self.minute_calls = Rate(100000, clock=clock)                       # the test's minutes, not the wall's

    def chain(self, underlying, *, expiry_from, expiry_to, strike_from=None, strike_to=None, max_pages=None, timeout=None):
        self.windows.append({"root": underlying, "expiry_to": expiry_to, "strike_from": strike_from, "strike_to": strike_to,
                             "max_pages": max_pages})
        out = super().chain(underlying, expiry_from=expiry_from, expiry_to=expiry_to, strike_from=strike_from,
                            strike_to=strike_to, max_pages=max_pages, timeout=timeout)
        if self.page_size and max_pages is not None and (self.paged is None or underlying in self.paged):
            pages = max(1, math.ceil(len(out) / self.page_size))
            for _ in range(min(pages, max_pages) - 1):
                self.minute_calls.take(force=True)
            if pages > max_pages:
                raise VenueError(f"chain {underlying}: more than {max_pages} pages")
        return out

    def observe_reads(self, root):
        return [w for w in self.windows if w["root"] == root and w["max_pages"] is not None]


class WidthCase(PracticeCase):
    def setUp(self):
        super().setUp()
        self.market = Recording(self.clock, width=60, expiries=(0, 1, 2, 3, 4, 7, 14, 15, 21, 30))
        self.venue.market = self.paper.market = self.market

    def strikes_by_expiry(self, root):
        chain = self.live.day.chains[root]
        out: dict[int, set[float]] = {}
        for k, d in zip(chain.strike.tolist(), chain.dte.tolist()):
            out.setdefault(int(d), set()).add(float(k))
        return out


# ---------------------------------------------------------------------------------------------------- the store clamp
@unittest.skipUnless(HAVE, "numpy not installed")
class StoreClamp(WidthCase):
    def test_constants_are_the_stores(self):
        from league.swarm import preflight as P

        data = Path(__file__).resolve().parents[2] / "scripts" / "data"
        if str(data) not in sys.path:
            sys.path.insert(0, str(data))
        import storelib as sl

        self.assertEqual(ST.STORE_STRIKES, sl.STRIKE_RANGE)
        self.assertEqual(ST.STORE_STRIKES, P.STORE_STRIKES)
        self.assertEqual(ST.STORE_DEFAULT_STRIKES, sl.DEFAULT_STRIKE_RANGE)
        self.assertEqual(ST.STORE_DEFAULT_STRIKES, P.STORE_DEFAULT_STRIKES)
        self.assertEqual((ST.STORE_FRONT_DTE, ST.STORE_BACK_DTE), (sl.MAX_DTE, sl.BACK_MONTH_DTE))
        self.assertEqual((ST.STORE_FRONT_DTE, ST.STORE_BACK_DTE), (P.FRONT_DTE, P.BACK_MONTH_DTE))
        self.assertEqual(ST.STORE_BACK_ROOTS, frozenset(sl.BACK_MONTH_ROOTS))
        self.assertEqual(ST.STORE_BACK_ROOTS, P.BACK_MONTH_ROOTS)
        self.assertEqual(ST.STORE_STEPS, {root: row[1] for root, row in P.LISTING.items()})
        self.assertEqual((ST.STORE_FIXED_STEP, ST.STORE_WIDER), (P.FIXED_STEP, P.WIDER))
        for price in (5.0, 40.0, 74.99, 75.0, 120.0, 149.9, 150.0, 300.0, 499.0, 500.0, 900.0):
            self.assertEqual(ST._store_strikes("NVDA", price), (25, P.equity_step(price)))
        self.assertEqual(ST._store_strikes("spxw", 6000.0), (40, 5.0))
        self.assertEqual([ST._store_dte(r) for r in ("SPY", "QQQ", "SPXW", "IWM", "AAPL")], [45, 45, 14, 14, 14])

    def test_observe_reads_hold_to_the_stores_strikes_and_days_inside_the_programs_window(self):
        self.build(observed=[wide_row("i", "IWM"), wide_row("x", "SPXW"), wide_row("s", "SPY")])
        self.run_to(9, 33)
        day = self.live.day
        spot = self.market.level("IWM")
        [read, *_] = self.market.observe_reads("IWM")
        self.assertEqual(read["expiry_to"], (day.day + dt.timedelta(days=14)).isoformat(), "its 30 days held to 14")
        self.assertAlmostEqual(read["strike_from"], spot - 25.5)
        self.assertAlmostEqual(read["strike_to"], spot + 25.5)
        iwm = self.strikes_by_expiry("IWM")
        self.assertEqual(sorted(iwm), [0, 1, 2, 3, 4, 7, 14])
        self.assertEqual({len(ks) for ks in iwm.values()}, {51}, "25 listed strikes a side of the money")
        self.assertEqual(min(min(ks) for ks in iwm.values()), round(spot) - 25)
        spxw = self.strikes_by_expiry("SPXW")
        self.assertEqual(max(spxw), 14)
        self.assertEqual({len(ks) for ks in spxw.values()}, {81}, "SPXW keeps 40 a side, on $5")
        [spy, *_] = self.market.observe_reads("SPY")
        self.assertEqual(spy["expiry_to"], (day.day + dt.timedelta(days=32)).isoformat(),
                         "SPY's back months are the store's: the program's own 30 (and margin) stand")

    def test_a_program_window_narrower_than_the_store_is_its_own(self):
        self.build(observed=[validated("q", roots=("QQQ",))])                 # 0-3 days, 3% of spot
        self.run_to(9, 33)
        [read, *_] = self.market.observe_reads("QQQ")
        spot = self.market.level("QQQ")
        self.assertEqual(read["expiry_to"], (self.live.day.day + dt.timedelta(days=5)).isoformat())
        self.assertAlmostEqual(read["strike_from"], spot * (1 - 0.04))
        self.assertEqual(read["max_pages"], 3)

    def test_nearest_strikes_keep_each_expiry_to_its_side_about_the_money(self):
        rows = {occ_symbol("TSLA", e, c, k): {} for e in ("2026-09-28", "2026-10-02") for c in (True, False)
                for k in [400 + 0.5 * i for i in range(-40, 41)]}
        rows["NOT-AN-OCC"] = {}
        kept = ST._nearest_strikes(rows, 401.2, 3)
        strikes = {occ_parts(s)[3] for s in kept}
        self.assertEqual(sorted(strikes), [399.5, 400.0, 400.5, 401.0, 401.5, 402.0, 402.5])
        self.assertEqual(len(kept), 7 * 2 * 2)


@unittest.skipUnless(HAVE, "numpy not installed")
class ClampWindow(unittest.TestCase):
    """`OptionsLive._observe_chain`'s window on a market that records it (and lists nothing)."""

    def read(self, root, spot, *, lo=0, hi=14, band=0.9):
        calls = []
        market = mock.Mock()
        market.chain.side_effect = lambda *a, **kw: calls.append(kw) or {}
        live = mock.Mock(market=market, _observe_narrow={})
        day = mock.Mock(day=MONDAY)
        rows = ST.OptionsLive._observe_chain(live, day, root, lo, hi, band, spot, {"max_pages": 3}, {})
        return rows, calls

    def test_a_coarsening_listing_is_drawn_on_the_next_wider_step(self):
        _, [slv] = self.read("SLV", 40.0)                                   # $0.50 near the money, $1 further out
        self.assertEqual((slv["strike_from"], slv["strike_to"]), (40.0 - 25.5, 40.0 + 25.5))
        _, [aapl] = self.read("AAPL", 250.0)                                # $2.50 near, $5 further out
        self.assertEqual((aapl["strike_from"], aapl["strike_to"]), (250.0 - 127.5, 250.0 + 127.5))
        _, [gld] = self.read("GLD", 300.0)
        self.assertEqual((gld["strike_from"], gld["strike_to"]), (300.0 - 63.75, 300.0 + 63.75))
        _, [iwm] = self.read("IWM", 220.0)                                  # a fixed $1 step: its own
        self.assertEqual((iwm["strike_from"], iwm["strike_to"]), (220.0 - 25.5, 220.0 + 25.5))
        _, [spxw] = self.read("SPXW", 6000.0)
        self.assertEqual((spxw["strike_from"], spxw["strike_to"]), (6000.0 - 202.5, 6000.0 + 202.5))

    def test_the_programs_band_still_bounds_the_window(self):
        _, [slv] = self.read("SLV", 40.0, band=0.1)
        self.assertEqual((slv["strike_from"], slv["strike_to"]), (36.0, 44.0))

    def test_an_emptied_window_reads_nothing_spot_or_none(self):
        for spot in (40.0, float("nan")):
            self.assertEqual(self.read("IWM", spot, lo=20, hi=14), ({}, []), spot)
        _, [read] = self.read("IWM", float("nan"), lo=0, hi=14)             # no spot: the first two days, as before
        self.assertEqual(read["expiry_to"], (MONDAY + dt.timedelta(days=1)).isoformat())


@unittest.skipUnless(HAVE, "numpy not installed")
class PageCap(WidthCase):
    def setUp(self):
        super().setUp()
        self.market.expiries = (0, 1, 2, 3, 4, 7, 8, 9, 10, 14)            # ten in IWM's 14 days

    def test_a_read_over_the_page_cap_is_read_again_narrower_and_kept_so_for_the_day(self):
        self.market.page_size = 300                                         # 1,020 contracts: four pages; 500 fit
        self.build(observed=[wide_row("i", "IWM")])
        out = self.run_to(9, 33)
        self.assertEqual(out.get("observe_reads_narrowed"), 1)
        self.assertNotIn("data_errors", out)
        self.assertEqual(self.live.health()["observe"]["narrowed"], {"IWM": 1})
        self.assertEqual({len(ks) for ks in self.strikes_by_expiry("IWM").values()}, {25}, "12 a side")
        self.assertTrue(np.isfinite(self.live.day.chains["IWM"].bid[3]).any(), "the minute's quotes are read")
        del self.market.windows[:]
        out = self.run_to(9, 34)
        [read] = self.market.observe_reads("IWM")
        self.assertAlmostEqual(read["strike_to"] - read["strike_from"], 25.0, msg="straight to the narrower window")
        self.assertEqual(out.get("observe_reads_narrowed"), 1)
        self.clock.set(at(TUESDAY, 9, 33))
        del self.market.windows[:]
        self.live.minute()
        reads = self.market.observe_reads("IWM")
        self.assertAlmostEqual(reads[0]["strike_to"] - reads[0]["strike_from"], 51.0, msg="a new day tries the store's")

    def test_the_narrowest_halves_the_expiries_too(self):
        self.market.page_size = 120                                         # only 25 strikes over 6 expiries fit
        self.build(observed=[wide_row("i", "IWM")])
        self.run_to(9, 33)
        self.assertEqual(self.live.health()["observe"]["narrowed"], {"IWM": 2})
        self.assertEqual(max(self.strikes_by_expiry("IWM")), 7, "days 0-14 halved to 0-7")

    def test_a_root_still_over_the_cap_is_a_data_error_and_costs_no_other_root(self):
        self.market.page_size, self.market.paged = 20, {"IWM"}
        self.build(observed=[wide_row("i", "IWM"), validated("q", roots=("QQQ",))])
        out = self.run_to(9, 32)
        self.assertTrue([e for e in out.get("data_errors") or [] if e.startswith("IWM") and "more than 3 pages" in e])
        self.assertTrue(np.isfinite(self.live.day.chains["QQQ"].bid[2]).any())
        self.assertEqual(len(self.market.observe_reads("IWM")), 3, "the store's window, then two narrower, then no more")
        del self.market.windows[:]
        self.run_to(9, 33)
        self.assertEqual(len(self.market.observe_reads("IWM")), 1, "later minutes try the narrowest alone")

    def test_no_retry_once_the_read_budget_is_spent(self):
        self.market.page_size = 300
        self.switches(observe_read_calls=10)
        self.build(observed=[wide_row("i", "IWM")])
        self.run_to(9, 31)                                                  # pinned and loaded: it reads from 9:32
        self.clock.set(at(MONDAY, 9, 32))
        for _ in range(7):
            self.market.minute_calls.take(force=True)
        del self.market.windows[:]
        out = self.live.minute()                                            # 7 + the real phase's 1, then IWM's 3
        self.assertEqual(len(self.market.observe_reads("IWM")), 1)
        self.assertTrue([e for e in out.get("data_errors") or [] if "more than 3 pages" in e])
        self.assertEqual(self.live.health()["observe"]["narrowed"], {})


# ---------------------------------------------------------------------------------------------------- the read budget
class StoreGateway:
    """The market-data gateway as `MarketData` calls it, answering from a store-shaped listing: each root's strikes on
    its own step across the asked range, its expiries by its schedule (SPY, QQQ, SPXW and XSP every weekday, IWM Monday,
    Wednesday and Friday, the rest Fridays), the venue's pages (`limit` a page, or exactly `pages` pages a chain read).
    Every request is one market-data call (`MarketData.minute_calls`)."""

    DAILY = {"SPY", "QQQ", "SPXW", "XSP"}
    STEPS = {"SPXW": 5.0}

    def __init__(self, clock, prices, *, pages=None):
        self.clock, self.prices, self.pages = clock, dict(prices), pages
        self.timeout = 10.0
        self.requests: list[str] = []

    def price(self, root):
        return self.prices[root]

    def request(self, method, url, what=""):
        parts = urllib.parse.urlsplit(url)
        q = dict(urllib.parse.parse_qsl(parts.query))
        self.requests.append(parts.path)
        t = self.clock()
        if parts.path.startswith("/v1beta1/options/snapshots/"):
            return 200, self.chain(urllib.parse.unquote(parts.path.rsplit("/", 1)[1]), q)
        if parts.path == "/v1beta1/options/snapshots":
            return 200, {"snapshots": {s: self.quote() for s in q["symbols"].split(",")}}
        if parts.path == "/v2/stocks/snapshots":
            return 200, {s: {"latestTrade": {"p": self.price(s), "t": iso(t - 2)}} for s in q["symbols"].split(",")}
        if parts.path == "/v2/stocks/bars":
            return 200, {"bars": {s: [{"o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "t": f"2026-09-{i + 1:02d}T04:00:00Z"}
                                      for i in range(10)] for s in q["symbols"].split(",")}, "next_page_token": None}
        return 404, {"message": "not listed"}

    def quote(self):
        return {"latestQuote": {"bp": 1.0, "ap": 1.1, "bs": 10, "as": 10, "t": iso(self.clock() - 1)}}

    def step(self, root, spot):
        return self.STEPS.get(root) or (1.0 if root in self.DAILY or root in ("IWM", "DIA", "GLD")
                                        else 0.5 if spot < 75 else 1.0 if spot < 150 else 2.5 if spot < 500 else 5.0)

    def chain(self, root, q):
        today = dt.datetime.fromtimestamp(self.clock(), dt.timezone.utc).astimezone(ST.NEW_YORK).date()
        lo, hi = dt.date.fromisoformat(q["expiration_date_gte"]), dt.date.fromisoformat(q["expiration_date_lte"])
        days = {"IWM": (0, 2, 4)}.get(root, (0, 1, 2, 3, 4) if root in self.DAILY else (4,))
        expiries = [lo + dt.timedelta(days=i) for i in range((hi - lo).days + 1)
                    if (lo + dt.timedelta(days=i)).weekday() in days and lo + dt.timedelta(days=i) >= today]
        spot = self.price("SPY") * (10.0 if root == "SPXW" else 1.0) if root in ("SPXW", "XSP") else self.price(root)
        step = self.step(root, spot)
        low = float(q.get("strike_price_gte") or spot * 0.5)
        high = float(q.get("strike_price_lte") or spot * 1.5)
        strikes = [k * step for k in range(math.ceil(low / step - 1e-9), math.floor(high / step + 1e-9) + 1)]
        symbols = [occ_symbol(root, e.isoformat(), c, k) for e in expiries for k in strikes for c in (True, False)]
        size = int(q.get("limit") or 1000) if not self.pages else max(1, math.ceil(len(symbols) / self.pages))
        start = int(q.get("page_token") or 0)
        page = symbols[start:start + size]
        token = str(start + size) if start + size < len(symbols) else None
        return {"snapshots": {s: self.quote() for s in page}, "next_page_token": token}


#: Twenty-four roots of the Gym's universe, at invented prices.
PRICES = {"SPY": 600.0, "QQQ": 500.0, "SPXW": 6000.0, "XSP": 600.0, "IWM": 220.0, "DIA": 450.0, "GLD": 300.0,
          "SLV": 40.0, "TLT": 90.0, "SMH": 250.0, "NVDA": 180.0, "MSFT": 500.0, "AMZN": 220.0, "AMD": 160.0,
          "GOOGL": 240.0, "TSM": 280.0, "TSLA": 420.0, "PLTR": 180.0, "META": 700.0, "AAPL": 250.0, "MU": 160.0,
          "BABA": 170.0, "SOXL": 30.0, "TQQQ": 90.0}


@unittest.skipUnless(HAVE, "numpy not installed")
class ReadBudget(unittest.TestCase):
    """THE READ BUDGET (`step.DEFAULTS` "observe_read_calls"): 24 roots, each read over the widest window a program can
    ask (the store's whole reach, 30% of spot), after a real phase that took `OBSERVE_REAL_CALLS` of the minute."""

    def setUp(self):
        import tempfile

        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.clock = Clock(at(MONDAY, 9, 40))
        self.ticks = [0.0]
        self.alerts = []

    def tearDown(self):
        self.live.state.close()
        self.live.observe_store.close()
        self.dir.cleanup()

    def make(self, *, pages=None, budget=None):
        (self.root / "swarm.json").write_text(json.dumps({"live": {"calibration": False, **(
            {"observe_read_calls": budget} if budget else {})}}))
        self.gateway = StoreGateway(self.clock, PRICES, pages=pages)
        market = MarketData(self.gateway)
        market.minute_calls = Rate(100000, clock=lambda: self.ticks[0])
        self.live = OptionsLive(self.root, market=market, real=None, paper=None, families=MemoryFamilies(),
                                decider=InlineDecider(), observe_decider=InlineDecider(), clock=self.clock,
                                alert=lambda lvl, text: self.alerts.append((lvl, text)))
        self.day = self.live._ensure_day(MONDAY, 570, 960)
        return self.live

    def minute(self, mi):
        """One minute's observe reads after a real phase of `OBSERVE_REAL_CALLS`: (calls the observe band took, out)."""
        self.ticks[0] += 61.0                                               # a new minute of market-data calls
        self.clock.set(at(MONDAY, 9, 30) + 60 * mi + 3)
        live, market = self.live, self.live.market
        live._decision_end = time.monotonic() + 1000.0                      # the minute's time is not this test's
        for _ in range(ST.OBSERVE_REAL_CALLS):
            market.minute_calls.take(force=True)
        windows = {r: (0, int(min(60, ST._store_dte(r))), 0.30) for r in PRICES}
        out: dict = {}
        live._read(self.day, mi, windows, out, phase="observe")
        return market.minute_calls.used() - ST.OBSERVE_REAL_CALLS, out

    def read_all(self, out, mi):
        self.assertNotIn("observe_reads_skipped", out)
        self.assertNotIn("data_errors", out)
        unread = [r for r in PRICES if not np.isfinite(self.day.chains[r].bid[mi]).any()]
        self.assertEqual(unread, [], "every root's chain read this minute")

    def test_twenty_four_roots_fit_the_minute_on_store_shaped_listings(self):
        self.make()
        calls, out = self.minute(10)
        self.read_all(out, 10)
        self.assertLessEqual(ST.OBSERVE_REAL_CALLS + calls, ST.DEFAULTS["observe_read_calls"])
        # Every-weekday SPY and QQQ out to 45 days are over three pages at the store's 25 a side: read narrower (and
        # their first read's three pages spent) rather than lost.
        self.assertEqual(self.live.health()["observe"]["narrowed"], {"SPY": 1, "QQQ": 1})
        first = calls
        calls, out = self.minute(11)
        self.read_all(out, 11)
        self.assertLess(calls, first, "no daily history and no narrowing retry after the first minute")
        self.assertLessEqual(calls, 1 + 2 * len(PRICES), "about one page a root, two for the dailies")

    def test_twenty_four_roots_fit_at_the_page_cap_with_room_for_a_held_read_each(self):
        self.make(pages=3)                                                  # every chain read exactly three pages
        self.minute(10)
        calls, out = self.minute(11)
        self.read_all(out, 11)
        self.assertEqual(calls, 1 + 3 * len(PRICES), "the stocks read and three pages a root")
        self.assertLessEqual(ST.OBSERVE_REAL_CALLS + calls + len(PRICES), ST.DEFAULTS["observe_read_calls"])

    def test_the_old_budget_did_not_fit_them(self):
        self.make(budget=40)
        calls, out = self.minute(10)
        self.assertGreater(out.get("observe_reads_skipped_budget", 0), 0)
        self.assertEqual(out.get("observe_reads_skipped_time"), None)


@unittest.skipUnless(HAVE, "numpy not installed")
class ReadBudgetDefault(unittest.TestCase):
    def test_the_swarm_settings_default_is_the_steps(self):
        from league.swarm import settings as SS

        self.assertEqual(SS.DEFAULTS["live"]["observe_read_calls"], ST.DEFAULTS["observe_read_calls"])


# ---------------------------------------------------------------------------------------------------- the honest shed
@unittest.skipUnless(HAVE, "numpy not installed")
class HonestShed(PracticeCase):
    def setUp(self):
        super().setUp()
        self.build(observed=[validated("v"), trained("t1", best=2.0), trained("t2", best=1.0)])
        self.run_to(9, 34)
        self.assertEqual(len(self.observing()), 3)

    def test_reads_skipped_for_the_minutes_time_are_not_pressure(self):
        now = self.clock()
        for i in range(ST.PRESSURE_MINUTES):
            self.live._observe_shed(now + 60 * i, {"observe_reads_skipped": 5, "observe_reads_skipped_time": 5})
        self.assertFalse(self.ledger.of("live.observe"))
        self.assertIsNone(self.live.state.get("observe_shed"))

    def test_reads_skipped_for_the_read_budget_are(self):
        now = self.clock()
        for i in range(ST.PRESSED_MINUTES):
            self.live._observe_shed(now + 60 * i, {"observe_reads_skipped": 1, "observe_reads_skipped_budget": 1})
        [(record, _)] = self.ledger.of("live.observe")
        self.assertEqual(record["shed"], ["t2"])
        self.assertIn("for the read budget", record["why"])

    def test_the_read_says_which_budget_stopped_it(self):
        live = self.live
        live._decision_budget = lambda: 2.0                                 # under the ten-second floor
        out = {}
        live._read(live.day, 5, {"QQQ": (0, 5, 0.04)}, out, phase="observe")
        self.assertEqual((out.get("observe_reads_skipped_time"), out.get("observe_reads_skipped_budget")), (1, None))
        del live._decision_budget
        live.settings["observe_read_calls"] = 0
        live._switches = None
        out = {}
        live._read(live.day, 5, {"QQQ": (0, 5, 0.04)}, out, phase="observe")
        self.assertEqual((out.get("observe_reads_skipped_budget"), out.get("observe_reads_skipped_time")), (1, None))


# ---------------------------------------------------------------------------------------------------- the practice caps
#: Asks for `qty` verticals `width` wide at every decision while no order of its own works, and holds them.
OPENER = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 0, "start": 571, "end": 958}
PARAMS = {"qty": 1, "width": 1.0}

def decide(ctx):
    if ctx.orders:
        return []
    return [{"open": "debit_vertical", "root": "SPY", "qty": ctx.params["qty"], "limit": "natural",
             "legs": [{"side": "long", "right": "C", "dte": 1, "atm": 0},
                      {"side": "short", "right": "C", "rel": 0, "offset": ctx.params["width"]}]}]
'''


def opener(name, **params):
    return dict(validated(name, params={"qty": 1, "width": 1.0, **params}), code=OPENER)


@unittest.skipUnless(HAVE, "numpy not installed")
class PracticeCaps(PracticeCase):
    def rejected(self, family):
        db = sqlite3.connect(self.root / "observe.sqlite")
        try:
            return [json.loads(b)["reason"] for (b,) in db.execute(
                "SELECT body FROM events WHERE family=? AND kind='rejected' ORDER BY event_id", (family,))]
        finally:
            db.close()

    def decisions_in_error(self, family):
        db = sqlite3.connect(self.root / "observe.sqlite")
        try:
            return [json.loads(b)["error"] for (b,) in db.execute(
                "SELECT body FROM events WHERE family=? AND kind='decision'", (family,))]
        finally:
            db.close()

    def test_a_practice_account_holds_at_most_three_structures(self):
        self.build(observed=[opener("many")])
        self.run_to(9, 45)
        acc = self.live.shadow.accounts["many@1:o"]
        self.assertEqual(len(acc.positions), 3)
        self.assertEqual(acc.counts["opens"], 3, "a refused open was never an order")
        reasons = self.rejected("many")
        self.assertTrue(reasons and all(r.startswith("practice cap: 3 structures open or working") for r in reasons), reasons)
        self.assertEqual(acc.reject_reasons.get("practice cap"), len(reasons))
        self.assertTrue(self.decisions_in_error("many"))
        self.assertFalse(any(self.decisions_in_error("many")), "a cap's refusal is never the program's error")

    def orders(self, family):
        db = sqlite3.connect(self.root / "observe.sqlite")
        try:
            return [json.loads(b) for (b,) in db.execute(
                "SELECT body FROM events WHERE family=? AND kind='order' ORDER BY event_id", (family,))]
        finally:
            db.close()

    def test_an_open_over_the_probes_share_of_capital_is_sized_down_as_a_probes(self):
        self.build(observed=[opener("big", qty=40)])                        # about $2,000 of maximum loss
        self.run_to(9, 36)
        acc = self.live.shadow.accounts["big@1:o"]
        reasons = self.rejected("big")
        # Since THE FAST LANE (Oct 7, 2026) the practice caps read the Probe's 10% ($1,000 of the $10,000 notional) and the
        # family's 15% ($1,500): later opens stop at the count or at the family's room, never at their own size.
        self.assertTrue(all(r.startswith(("practice cap: 3 structures open or working", "practice cap: "))
                            and "over the Probe's" not in r for r in reasons),
                        ("sized smaller: never refused for its size", reasons))
        [first, *_] = self.orders("big")
        order = first["order"]["order"]
        self.assertEqual(first["practice_sized"], {"asked": 40, "qty": order["qty"]})
        qty, unit = order["qty"], order["max_loss_share"] * 100 + 2 * order["fees"] / order["qty"]
        self.assertTrue(1 <= qty < 40 and qty * unit <= 1000.0 + 1e-6 < (qty + 1) * unit, (qty, unit))
        self.assertGreaterEqual(acc.counts["opens"], 1)

    def test_an_open_whose_one_structure_is_over_the_probes_cap_is_refused(self):
        self.build(observed=[opener("wide", width=10.0)])
        self.live.settings["shadow_capital"] = 1000.0                       # $100 a structure (10%), no floor
        self.run_to(9, 36)
        acc = self.live.shadow.accounts["wide@1:o"]
        self.assertEqual((len(acc.positions), acc.counts["opens"], acc.orders_today), (0, 0, 0))
        [first, *_] = self.rejected("wide")
        self.assertRegex(first, r"^practice cap: one structure risks [0-9.]+ with fees, over the Probe's 100\.00 a "
                                r"structure and its 0\.00 floor$")
        self.assertFalse(any(self.decisions_in_error("wide")), "a cap's refusal is never the program's error")

    def test_a_candidate_shadow_keeps_the_engines_rules(self):
        from league.tests.live_fakes import family

        self.build([family("cand", OPENER, band="candidate", params={"qty": 1, "width": 1.0})])
        self.run_to(9, 45)
        acc = self.live.shadow.accounts["cand@1:s"]
        self.assertGreater(len(acc.positions), 3)
        self.assertNotIn("practice cap", acc.reject_reasons)


@unittest.skipUnless(HAVE, "numpy not installed")
class CapArithmetic(unittest.TestCase):
    """`ShadowAccount._practice_cap` on held structures and working opens (shadow capital $10,000: $1,000 an open (THE FAST
    LANE's 10%, Oct 7, 2026; $500 before it), three structures, $1,500 at risk at the constitution's Probe rows). The
    practice caps size by the share (several structures an open), as the Probe did before the fast lane: practice returns
    are per dollar of maximum loss, so scale-free; the real Probe is one structure (`money.plan_open`)."""

    def account(self, instance="fam@1:o", capital=10000.0):
        needs = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 0, "start": 571, "end": 958}
        return S.ShadowAccount(instance=instance, family="fam", needs=S.needs_of(needs), params={}, capital=capital)

    def position(self, pid, share, qty=1):
        return S._position_from({"pid": pid, "type": "debit_vertical", "root": "SPY", "legs": [], "keys": [],
                                 "expirations": [], "qty": qty, "opened_qty": qty, "entry": share, "max_loss_share": share,
                                 "collateral": 0.0, "opened_day": 1, "opened_mi": 0, "opened_session": 0, "cash": 0.0,
                                 "fees": 0.0, "exit_value_qty": 0.0, "exit_day": 0, "exit_mi": 0})

    def working(self, oid, share, qty=1, fees=0.0, pid=0):
        return S._working_from({"oid": oid, "remaining": qty, "placed_mi": 0, "arrival_mi": 1, "expires_mi": None,
                                "reserve_left": 0.0, "pid": pid, "forced": False, "filled": 0, "seen": False,
                                "aggressive": False, "order": {"action": "open", "type": "debit_vertical", "root": "SPY",
                                "legs": [], "qty": qty, "limit": share, "natural": share, "mid": share,
                                "max_loss_share": share, "collateral": 0.0, "fees": fees, "reserve": 0.0, "tif": None}})

    def test_the_caps_follow_the_constitutions_probe_rows(self):
        from league.constitution import CONSTITUTION

        probe = CONSTITUTION["options_money"]["probe"]
        (share, floor), open_max, family = S._probe_caps()
        self.assertEqual((share, floor, open_max, family), (float(probe["max_loss_share"]), float(probe["floor_usd"]),
                                                           int(probe["open_per_family"]), float(probe["family_share"])))

    def test_per_open_with_fees(self):
        acc = self.account()
        self.assertEqual(acc._practice_cap([self.working(9, 9.90, fees=5.0)]), ({9: 1}, None), "990, 10 of fees: 1,000")
        sizes, why = acc._practice_cap([self.working(9, 9.90, fees=5.01)])
        self.assertEqual(sizes, {})
        self.assertEqual(why, "practice cap: one structure risks 1000.02 with fees, over the Probe's 1000.00 a structure "
                              "and its 0.00 floor")

    def test_an_open_is_sized_by_the_probes_share(self):
        acc = self.account()
        # 12 asked of a $99 + $1 structure: floor(1,000 / 100) = 10 (the share; the real Probe sends one structure).
        self.assertEqual(acc._practice_cap([self.working(9, 0.99, qty=12, fees=6.0)]), ({9: 10}, None))
        # Never more than the program asked.
        self.assertEqual(acc._practice_cap([self.working(9, 0.99, qty=2, fees=1.0)]), ({9: 2}, None))
        # The unit's fees are one structure's at the decision's quotes, never the whole order's: 49 + 2 x 0.50 = 50.
        self.assertEqual(acc._practice_cap([self.working(9, 0.49, qty=40, fees=20.0)]), ({9: 20}, None))

    def test_the_floor_buys_one_structure_over_the_share(self):
        acc = self.account(capital=1000.0)                                  # $100 a structure (10%); no floor
        self.assertEqual(acc._practice_cap([self.working(9, 0.90, qty=3, fees=15.0)]), ({9: 1}, None), "90 + 10: one")
        sizes, why = acc._practice_cap([self.working(9, 0.91, qty=3, fees=15.0)])
        self.assertTrue(why.startswith("practice cap: one structure risks 101.00"), why)

    def test_structures_held_and_working_count_once_each(self):
        acc = self.account()
        acc.positions = {1: self.position(1, 1.0), 2: self.position(2, 1.0)}
        acc.orders = {5: self.working(5, 1.0, pid=2)}                        # the rest of a partly filled open: held
        self.assertEqual(acc._practice_cap([self.working(9, 1.0)]), ({9: 1}, None))
        acc.orders[6] = self.working(6, 1.0)                                 # a third structure, working
        self.assertEqual(acc._practice_cap([self.working(9, 1.0)]),
                         ({}, "practice cap: 3 structures open or working, the most a Probe holds is 3"))

    def test_the_familys_maximum_loss_at_risk(self):
        acc = self.account()
        acc.positions = {1: self.position(1, 7.0)}                           # 700 held from before the caps
        acc.orders = {5: self.working(5, 6.0)}                               # 600 working
        self.assertEqual(acc._practice_cap([self.working(9, 2.0)]), ({9: 1}, None), "1,500 exactly")
        # The family's room sizes it down: 200 of room is two $100 structures of the three asked.
        self.assertEqual(acc._practice_cap([self.working(9, 1.0, qty=3)]), ({9: 2}, None))
        self.assertEqual(acc._practice_cap([self.working(9, 2.01)]),
                         ({}, "practice cap: 1300.00 of maximum loss at risk leaves no room for one structure's 201.00 "
                              "under the Probe's 1500.00 a family"))

    def test_caps_that_cannot_be_read_refuse(self):
        acc = self.account()
        with mock.patch.object(S, "_probe_caps", side_effect=ValueError("the options money table is refused")):
            self.assertEqual(acc._practice_cap([self.working(9, 0.5)]),
                             ({}, "practice cap: the Probe's caps could not be read (ValueError)"))

    def test_a_withdrawn_open_leaves_no_trace_in_the_engines_counts(self):
        acc = self.account()
        work = self.working(9, 1.0)
        acc.orders = {9: work}
        acc.orders_today, acc.counts["orders"], acc.counts["opens"] = 4, 4, 3
        acc._withdraw(work)
        self.assertEqual((acc.orders, acc.orders_today, acc.counts["orders"], acc.counts["opens"]), ({}, 3, 3, 2))


if __name__ == "__main__":
    unittest.main()
