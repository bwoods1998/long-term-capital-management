"""WHAT THE REHEARSAL ON REAL DATA FOUND (release E1, Oct 11, 2026): the data job, its audit, the store, the three
seeds' Train runs and the screen's floor were run once on the House box against real SIP bars before the first deploy,
and an independent check read the result. The data job's own two defects are held in league/tests/test_equity_data.py;
this file holds the rest, by the rehearsal's finding:

- `TheVendorsCents`, `TheEngineOnCentRoundedPrices` (rehearsal-3, rehearsal-10): the vendor rounds its adjustment=all
  prices to the cent, so the all/raw ratio jitters from bar to bar with no event. The engine read that jitter as
  dividends and anomalies, and read a split whose step the rounding had pushed above its factor as a neighbouring
  fraction with a dividend;
- `TheMorningAfterAnExDate` (rehearsal-4): the book's morning audit read every ex-dividend morning as a price mismatch,
  which cancels the decision's buys and counts a failed decide. One bound serves both (`config.rounding_bound`);
- `TheNextDaysFetch` (rehearsal-9, with the review's evidence-1): the volume is no part of a day's audit mark either;
- `TheSeedsDeclaredOrder` (rehearsal-5): the two overnight seeds are one lineage, and which of them spends its one
  look is the declared order of `seeds.EQUITY_SEEDS`, never the clock;
- `TheEventTablesCoverage` (rehearsal-8): `ctx.events` says nothing before the tables' first year or after a table's
  last row, the same live and in the Gym;
- `TheCtxOfALaterStore` (rehearsal-6): a live ctx does not reproduce byte for byte from a later store once an event
  has restated the series, and by how much it may differ.

Every price here is invented (round numbers and a few cents), never a market's."""

from __future__ import annotations

import datetime as dt
import inspect
import random
import unittest
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from unittest import mock

import numpy as np

from league.equity import BETA, config, engine
from league.equity import live as L
from league.equity import screen as S
from league.equity.engine import run, split_factor
from league.equity.runner import RunFailed
from league.swarm import elane, seeds
from league.swarm.gate import run_sha
from league.tests import test_equity_book as T
from league.tests import test_equity_engine as E
from league.tests import test_equity_fx_swarm as FS
from league.tests.test_elane import CODE, ON
from league.tests.test_elane_gate import screen

REPO = Path(__file__).resolve().parents[2]
QQQ, REVERSAL, SPY = "seed-overnight-qqq", "seed-reversal-index", "seed-overnight-spy"

D = Decimal
MONDAY, TUESDAY = T.MONDAY, T.TUESDAY


def cents(value: float) -> float:
    """A price as the vendor publishes its adjusted series: rounded to the cent."""
    return round(value, 2)


# ------------------------------------------------------------------------------------------- the one shared bound
class TheVendorsCents(unittest.TestCase):
    def test_the_bound_is_half_a_cent_over_each_price_with_its_guard(self):
        self.assertEqual((config.ADJUSTED_HALF_STEP, config.ROUNDING_GUARD), (0.005, 1.5))
        self.assertAlmostEqual(config.rounding_bound(100.0, 100.0), 1.5 * 0.005 * 0.02, places=15)
        self.assertAlmostEqual(config.rounding_bound(600.0, 600.0, 600.0, 600.0), 5e-5, places=15)
        self.assertGreater(config.rounding_bound(20.0, 20.0), config.rounding_bound(200.0, 200.0),
                           "a cent is more of a low price")
        for bad in ((), (0.0, 100.0), (-1.0,), (float("nan"), 100.0), (float("inf"),), ("x",)):
            with self.subTest(bad=bad), self.assertRaises((TypeError, ValueError)):
                config.rounding_bound(*bad)

    def test_the_engines_tolerance_is_that_bound_never_under_its_floor(self):
        self.assertAlmostEqual(engine.ratio_tolerance(100.0, 100.0), 1.5e-4, places=15)
        self.assertEqual(engine.ratio_tolerance(1e6, 1e6), engine.RATIO_TOLERANCE, "the floor, for a price in the millions")
        self.assertEqual(engine.ratio_tolerance(float("nan"), 100.0), engine.RATIO_TOLERANCE,
                         "a close that is no price has no rounding to allow for: the step is judged as before")

    def test_a_split_is_read_exactly_on_cent_rounded_prices(self):
        """rehearsal-10: with the fixed bound the search refused the true factor whenever the rounding had pushed its
        residual above 1, and took the nearest smaller fraction with the rest as a dividend (39:2 for a 20-for-1)."""
        rng = random.Random(20261011)
        wrong_before = 0
        for factor in (Fraction(20), Fraction(4), Fraction(10), Fraction(2), Fraction(3, 2), Fraction(1, 10)):
            for dividend in (0.0, 0.004):                      # none, or one on the split's own day
                for _ in range(250):
                    before = cents(rng.uniform(40.0, 900.0))    # the raw close before the split
                    after = cents(before / float(factor) * (1.0 + rng.uniform(-0.03, 0.03)))
                    level = rng.choice((1.0, 0.97, 0.88))       # later events' factor on both adjusted closes
                    adj_before = cents(before / float(factor) * level * (1.0 - dividend))
                    adj_after = cents(after * level)
                    step = (adj_before / before) / (adj_after / after)
                    tolerance = engine.ratio_tolerance(adj_before, adj_after)
                    self.assertEqual(split_factor(step, tolerance), factor, (factor, dividend, before, after, level))
                    wrong_before += split_factor(step) != factor
        self.assertGreater(wrong_before, 100, "the fixed bound alone misread many of the same steps")

    def test_the_exact_steps_read_as_before(self):
        for step, want in ((0.5, 2), (0.05, 20), (10.0, Fraction(1, 10)), (2 / 3, Fraction(3, 2)), (0.5 * 0.99, 2)):
            self.assertEqual(split_factor(step, 1.5e-4), want)
        self.assertIsNone(split_factor(0.98, 1.5e-4), "a dividend is not a split")
        self.assertIsNone(split_factor(1.0, 1.5e-4))


# -------------------------------------------------------------------------------------------------- the engine
HOLD = """
if STATE['n'] == 1:
    return [{'buy': 'SPY', 'usd': 300, 'at': 'close'}]
return []
"""


def rows(raw_closes, adjusted):
    """`hand_store` rows (raw open, raw close, all open, all close) of flat bars."""
    return [(r, r, a, a) for r, a in zip(raw_closes, adjusted)]


class TheEngineOnCentRoundedPrices(E.Case):
    RAW = [100.37, 101.12, 99.81, 100.05, 102.33, 101.47, 100.91, 99.64, 100.88, 101.73, 100.19, 99.95]

    def held(self, raw, adjusted):
        bars, days = E.hand_store(self.tmp / "s", {"SPY": rows(raw, adjusted)})
        return run(E.program(HOLD, max_hold=40), bars), days

    def test_the_rounding_of_the_adjusted_series_is_no_dividend_and_no_anomaly(self):
        """rehearsal-3: an earlier dividend left the adjusted series a constant factor under the raw one, and the vendor
        rounds each adjusted price to the cent. Nothing happens in these twelve sessions; the engine read some of the
        ratio's jitter as dividends (cash credited to the lot) and some as anomalies, one-sided."""
        adjusted = [cents(r * 0.9731) for r in self.RAW]
        steps = [(adjusted[i - 1] / self.RAW[i - 1]) / (adjusted[i] / self.RAW[i]) - 1.0 for i in range(1, len(self.RAW))]
        self.assertGreater(sum(abs(s) > engine.RATIO_TOLERANCE for s in steps), 3, "the jitter is past the fixed bound")
        result, _ = self.held(self.RAW, adjusted)
        self.assertEqual(result["actions"], [])
        (lot,) = result["lots"]
        self.assertEqual((lot["div"], lot["reason"]), (0.0, "open"))
        self.assertEqual(result["summary"]["dividends"], 0.0)

    def test_a_real_dividend_is_still_credited_within_a_cent_a_share_of_its_rounding(self):
        ex, paid = 6, 0.50                                         # ex-dividend at session 6: $0.50 a share
        level = 1.0 - paid / self.RAW[ex - 1]
        adjusted = [cents(r * level) if i < ex else r for i, r in enumerate(self.RAW)]
        result, days = self.held(self.RAW, adjusted)
        (action,) = result["actions"]
        self.assertEqual((action["symbol"], action["day"], action["kind"]), ("SPY", days[ex].isoformat(), "dividend"))
        self.assertAlmostEqual(action["per_share"], paid, delta=0.011)
        (lot,) = result["lots"]
        self.assertAlmostEqual(lot["div"], lot["qty"] * paid, delta=0.04)

    def test_a_split_and_a_dividend_on_neighbouring_days(self):
        """rehearsal-10 in the engine: a 20-for-1 split at session 3 and a $0.40 dividend at session 4. With the fixed
        bound these very prices read as a 39-for-2 split with a dividend of a fortieth of the price."""
        raw = [2003.37, 2011.90, 1998.44, 101.33, 100.87, 101.10, 100.64, 101.02]
        level = 1.0 - 0.40 / raw[3]
        adjusted = [cents(raw[0] / 20 * level), cents(raw[1] / 20 * level), cents(raw[2] / 20 * level),
                    cents(raw[3] * level), *raw[4:]]
        step = (adjusted[2] / raw[2]) / (adjusted[3] / raw[3])
        self.assertEqual(split_factor(step), Fraction(39, 2), "what the fixed bound made of it")
        result, days = self.held(raw, adjusted)
        split, dividend = result["actions"]
        self.assertEqual(split, {"symbol": "SPY", "day": days[3].isoformat(), "kind": "split", "factor": "20:1"})
        self.assertEqual((dividend["day"], dividend["kind"]), (days[4].isoformat(), "dividend"))
        self.assertAlmostEqual(dividend["per_share"], 0.40, delta=0.011)
        (lot,) = result["lots"]
        bought = (D(300) / D(str(engine.fill_price(raw[1], "buy", config.half_spread("SPY"), 1.0)))).quantize(
            D("0.000001"), rounding="ROUND_DOWN")
        self.assertEqual(D(str(lot["qty"])), (bought * 20).quantize(D("0.000001")), "twenty shares for each one bought")
        self.assertAlmostEqual(lot["div"], float(bought * 20) * 0.40, delta=0.05)


# ------------------------------------------------------------------------------------------- the morning's audit
def readings(price: float, level: float, restated: float, *, n: int = 6):
    """Two readings of one symbol's bars: the 16:20 one (raw, and the adjusted series a factor `level` under it) and
    the next morning's, after an ex-date restated every adjusted price by `restated`; each adjusted price to the cent.
    -> (old_raw, old_all, fresh_raw, fresh_all, day) as `live._bars_verdict` takes them."""
    days = [f"2026-10-{d:02d}" for d in range(1, 1 + n)]
    raw = {d: tuple(cents(price + 0.37 * i + x) for x in (-0.20, 0.55, -0.61, 0.0)) + (1000 + i,)
           for i, d in enumerate(days)}
    old_all = {d: tuple(cents(x * level) for x in raw[d][:4]) for d in days}
    fresh_raw = {d: dict(zip("ohlcv", raw[d])) for d in days}
    fresh_all = {d: dict(zip("ohlc", (cents(x * level * restated) for x in raw[d][:4]))) for d in days}
    return raw, old_all, fresh_raw, fresh_all, days[-1]


class TheMorningAfterAnExDate(T.BookTest):
    """rehearsal-4: on an ex-dividend morning the vendor has restated the whole adjusted series by the event's factor,
    each price rounded to the cent again. The as-of prices a program saw are the same; compared to a millionth they
    never were, so every ex-date (monthly for one of the four index ETFs) cancelled the decision's buys and counted a
    failed decide."""

    LEVELS = (600.0, 450.0, 220.0, 100.0)
    EX_DATES = (0.9987, 0.9971, 0.9925)           # a monthly, a quarterly and a large dividend's factor

    def test_a_series_an_ex_date_restated_gives_the_same_as_of_prices(self):
        differ_before = 0
        for price in self.LEVELS:
            for restated in self.EX_DATES:
                raw, old_all, fresh_raw, fresh_all, day = readings(price, 0.9731, restated)
                self.assertTrue(L._as_of_equal(raw, old_all, fresh_raw, fresh_all, day), (price, restated))
                self.assertEqual(L._bars_verdict(raw, old_all, fresh_raw, fresh_all, day), "ok")
                differ_before += any(
                    abs(old_all[d][i] * raw[day][3] / old_all[day][3] - fresh_all[d][k] * raw[day][3] / fresh_all[day]["c"])
                    > 1e-6 * old_all[d][i] for d in old_all for i, k in enumerate("ohlc"))
        self.assertEqual(differ_before, len(self.LEVELS) * len(self.EX_DATES), "to a millionth every one of them differs")

    def test_a_price_that_really_moved_is_still_a_mismatch(self):
        for price, moved in ((600.0, 0.0005), (220.0, 0.0005), (100.0, 0.002), (41.07, 0.002)):
            raw, old_all, fresh_raw, fresh_all, day = readings(price, 0.9731, 0.9971)
            first = sorted(fresh_all)[0]
            fresh_all[first]["c"] = fresh_all[first]["c"] * (1.0 + moved)
            self.assertFalse(L._as_of_equal(raw, old_all, fresh_raw, fresh_all, day), (price, moved))
            self.assertEqual(L._bars_verdict(raw, old_all, fresh_raw, fresh_all, day), "mismatch")

    def test_a_raw_price_is_exact_and_an_unreadable_one_is_a_difference(self):
        raw, old_all, fresh_raw, fresh_all, day = readings(600.0, 0.9731, 0.9971)
        fresh_raw[day]["l"] = cents(fresh_raw[day]["l"] - 0.01)     # the raw series is the tape's own: a cent is a cent
        self.assertEqual(L._bars_verdict(raw, old_all, fresh_raw, fresh_all, day), "mismatch")
        raw, old_all, fresh_raw, fresh_all, day = readings(600.0, 0.9731, 0.9971)
        fresh_all[sorted(fresh_all)[1]]["h"] = 0.0
        self.assertFalse(L._as_of_equal(raw, old_all, fresh_raw, fresh_all, day), "never read as all rounding")
        fresh_all[sorted(fresh_all)[1]]["h"] = None
        self.assertFalse(L._as_of_equal(raw, old_all, fresh_raw, fresh_all, day))

    def decided(self) -> tuple[T.Harness, L.Intent]:
        h = self.harness()
        inst = h.instance()
        h.decider.needs[inst.id] = {"symbols": ["SPY"], "history": 5, "max_hold_sessions": 20}
        h.decider.plans[inst.id] = [{"buy": "SPY", "share": 0.5}]
        h.decide_setup(MONDAY)
        for row, source in zip(h.market.bar_rows["all"]["SPY"], h.market.bar_rows["raw"]["SPY"]):
            row.update({k: cents(source[k] * 0.9731) for k in "ohlc"})  # the vendor's cents
        h.tick(16, 31)
        (buy,) = h.intents(kind="buy")
        return h, buy

    def restate(self, h: T.Harness, factor: float) -> None:
        for row, source in zip(h.market.bar_rows["all"]["SPY"], h.market.bar_rows["raw"]["SPY"]):
            row.update({k: cents(source[k] * 0.9731 * factor) for k in "ohlc"})

    def test_the_books_audit_on_an_ex_dividend_morning_cancels_nothing(self):
        h, buy = self.decided()
        self.restate(h, 0.9971)                                      # Tuesday is the ex-date
        h.tick(8, 31, day=TUESDAY)
        decision = h.state.get("eq_decision")
        self.assertEqual((decision["audit"], decision["mismatch"]), ("ok", []))
        self.assertEqual(h.get_intent(buy.iid).status, "planned")
        (inst,) = h.book._instances(alive=True)
        self.assertEqual(inst.failed_decides, 0)
        self.assertEqual([a for a in h.alerts if a[0] == "error"], [])
        self.assertEqual({r["audit"] for r in h.state.rows("SELECT audit FROM eq_bars WHERE day=?", (MONDAY.isoformat(),))},
                         {"ok"})

    def test_and_a_moved_close_on_that_morning_still_cancels_the_buy(self):
        h, buy = self.decided()
        self.restate(h, 0.9971)
        h.market.bar_rows["all"]["SPY"][-3]["c"] *= 1.0005           # five basis points on one adjusted close
        h.tick(8, 31, day=TUESDAY)
        decision = h.state.get("eq_decision")
        self.assertEqual((decision["audit"], decision["mismatch"]), ("mismatch", ["SPY"]))
        self.assertEqual(h.get_intent(buy.iid).status, "canceled")
        (inst,) = h.book._instances(alive=True)
        self.assertEqual(inst.failed_decides, 1)


class TheNextDaysFetch(T.BookTest):
    """rehearsal-9 (the review's evidence-1 and ops-4 hold the audit itself): the vendor's 1Day volume of a session is
    not final at the 16:20 fetch, so the NEXT day's fetch always reads another volume for it. The store's upsert took
    that for a changed row and cleared the day's morning audit mark, which the twins then report as never audited."""

    def audited(self) -> T.Harness:
        h = self.harness()
        inst = h.instance()
        h.decider.needs[inst.id] = {"symbols": ["SPY"], "history": 5, "max_hold_sessions": 20}
        h.decider.plans[inst.id] = []
        h.decide_setup(MONDAY)
        h.tick(16, 31)
        h.tick(8, 31, day=TUESDAY)
        self.assertEqual(self.mark(h), {"ok"})
        for name in ("raw", "all"):                                   # Tuesday's bar, as the 16:20 fetch reads it
            last = h.market.bar_rows[name]["SPY"][-1]
            h.market.bar_rows[name]["SPY"].append({**last, "t": f"{TUESDAY.isoformat()}T04:00:00Z"})
        return h

    def mark(self, h: T.Harness) -> set:
        return {r["audit"] for r in h.state.rows("SELECT audit FROM eq_bars WHERE day=? AND symbol='SPY'",
                                                 (MONDAY.isoformat(),))}

    def monday(self, h: T.Harness, name: str = "raw") -> dict:
        return h.market.bar_rows[name]["SPY"][-2]

    def test_a_volume_that_grew_keeps_the_days_audit_mark(self):
        h = self.audited()
        before = self.monday(h)["v"]
        self.monday(h)["v"] = before + 250_000                        # the after-hours prints, counted by Tuesday
        h.tick(16, 31, day=TUESDAY)
        self.assertEqual(h.state.get("eq_decision")["day"], TUESDAY.isoformat(), "Tuesday's bars were stored")
        self.assertEqual(self.mark(h), {"ok"}, "its prices are the audited ones")
        [stored] = h.state.rows("SELECT v FROM eq_bars WHERE day=? AND symbol='SPY' AND adjustment='raw'",
                                (MONDAY.isoformat(),))
        self.assertEqual(D(stored["v"]), D(str(before + 250_000)), "the store holds the later volume")

    def test_a_price_that_changed_is_unaudited_again(self):
        h = self.audited()
        self.monday(h)["c"] += 0.25
        h.tick(16, 31, day=TUESDAY)
        marks = {(r["adjustment"], r["audit"]) for r in h.state.rows(
            "SELECT adjustment, audit FROM eq_bars WHERE day=? AND symbol='SPY'", (MONDAY.isoformat(),))}
        self.assertEqual(marks, {("raw", None), ("all", "ok")})


# ------------------------------------------------------------------------------------- the seeds' declared order
class NamedRunner(FS.PickyRunner):
    """`PickyRunner` whose runs say whose they are (so each family can have its own Train series), and whose sealed
    look the House cannot make for the families in `unmade` (no look is spent: it is owed again)."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.unmade: set[str] = set()

    def _run(self, name, window, k):
        made = super()._run(name, window, k)
        made.bars.name = name
        return made

    def look(self, code, params, *, name, gate, k=1.0):
        if name in self.unmade:
            self.calls.append(("look", name, gate))
            raise RunFailed("the decider child could not be started")
        return super().look(code, params, name=name, gate=gate, k=k)


def own_series(lots, bars, *, universe, capital, first=None, last=None):
    """The gate harness's `series`, with the reversal seed on a Train series of its own, and so a family named
    "own..." (the two overnight seeds, and any other family, share one: one lineage, as the two overnight seeds are
    declared)."""
    days = {"segment-1": np.arange(0, 5), "segment-2": np.arange(10, 15)}.get(bars.window, np.arange(100, 105))
    r = np.linspace(-0.01, 0.01, len(days))
    if "reversal" in str(getattr(bars, "name", "")):
        r = np.asarray([0.01, -0.01, 0.012, -0.008, 0.0])[:len(days)]
    elif str(getattr(bars, "name", "")).startswith("own"):
        r = np.asarray([0.0, 0.01, -0.01, 0.0, 0.0])[:len(days)]
    return S.Series(days=days.astype(np.int32), r=r, w=np.ones(len(days)), b=np.zeros(len(days)),
                    exits=np.zeros(len(days), dtype=int), invested=np.ones(len(days), dtype=bool))


class TheSeedsDeclaredOrder(FS.FixCase):
    """rehearsal-5: the two overnight seeds are one lineage, so D3 gives only one of them a look, and which one was
    left to the store's order. The captain decided it before any Validation or look (amendment A18): the declared
    order of `seeds.EQUITY_SEEDS` is the order of the looks, and it is seed-overnight-qqq, seed-reversal-index,
    seed-overnight-spy.

    verify-evidence-1: WITHIN A LINEAGE THE ORDER IS STRICT. The first fix held the later seed for 30 minutes at
    most, once, on a clock that ran even while no look could be taken at all; after it ran out, one run of the earlier
    seed the House could not make handed the lineage's one sealed look to the later seed for good. There is no
    timeout now: the later seed's look waits until the earlier seed of its lineage has been looked at, has failed its
    Validation pre-check with no retry owed, or is retired, and a long wait is one House warning."""

    def setUp(self):
        super().setUp()
        self.runner = NamedRunner()
        self.tournament.equity_runner = self.gate.equity_runner = self.runner

    def seeded(self):
        born = elane.birth_seeds(self.store, ON)
        with screen():
            self.tournament.equity_round()
        return born

    def round(self, **kw):
        """One equity round of the gate: D3 by the screen's real rule, each family on its own Train series."""
        out = {"looked": [], "refused": [], "waiting": [], "held": [], "look_held": []}
        with screen(**kw), mock.patch.object(S, "same_lineage", FS.REAL_SAME_LINEAGE), \
                mock.patch.object(S, "series", side_effect=own_series):
            self.gate.equity_round(out)
        return out

    def rounds(self, seconds, **kw):
        """The gate's rounds over `seconds`, one every `elane.ROUND_SECONDS`; the last round's answer."""
        out = None
        for _ in range(int(seconds // elane.ROUND_SECONDS)):
            self.clock.advance(elane.ROUND_SECONDS)
            out = self.round(**kw)
        return out

    def looks_asked(self):
        return [c[1] for c in self.runner.calls if c[0] == "look"]

    def said(self, action="equity_seed_waits"):
        return [e for e in self.store.events_after(0, limit=100_000)
                if e["kind"] == "swarm.status" and e["payload"].get("action") == action]

    def waiting(self, fid=SPY):
        return self.store.family(fid)["state"].get(elane.SEED_WAIT_KEY)

    def test_the_declared_order_and_whose_decision_it_was_are_written_down(self):
        """The order, that it is one lineage, and whose decision it was and when (amendment A18). What it was decided
        ON stays off a public file: no Train-era figure, and no finding about the seeds on real data
        (`ThePublicWording`)."""
        self.assertEqual([spec["id"] for spec in seeds.EQUITY_SEEDS], [QQQ, REVERSAL, SPY])
        source = inspect.getsource(seeds)
        said = source[source.index("#: THE ORDER OF THIS LIST"):source.index("EQUITY_SEEDS: list")]
        for words in ("ONE LINEAGE", "seed-overnight-qqq goes first", "the captain's", "before any Validation or look",
                      "from Train-era figures only", "amendment A18", "retired with that reason"):
            self.assertIn(words, " ".join(said.replace("#:", " ").split()))
        self.assertNotRegex(said, r"\d\.\d", "no Train-era figure in a public file")
        for finding in ThePublicWording.FINDINGS:
            self.assertNotRegex(said, finding)
        page = " ".join((REPO / "docs" / "operations.md").read_text().split())
        self.assertIn("seed-overnight-qqq, seed-reversal-index, seed-overnight-spy", page)

    def test_the_lineages_are_declared_beside_the_order(self):
        lineage = {spec["id"]: spec["lineage"] for spec in seeds.EQUITY_SEEDS}
        self.assertEqual(lineage[QQQ], lineage[SPY], "the two overnight seeds are ONE lineage (A18)")
        self.assertNotEqual(lineage[REVERSAL], lineage[QQQ], "the reversal seed is a lineage of its own")
        self.seeded()
        self.assertEqual(elane._seed_lineages(self.store), lineage)
        # The declaration is the wait's alone: it is no part of a family's record, so no family's spec moves.
        self.assertNotIn("lineage", seeds.equity_family_spec(seeds.EQUITY_SEEDS[0]))

    def test_the_declared_order_is_the_look_order(self):
        self.assertEqual(self.seeded(), [QQQ, REVERSAL, SPY])
        self.runner.calls.clear()
        out = self.round()
        self.assertEqual(out["looked"], [{"family": QQQ, "passed": True, "lane": BETA},
                                         {"family": REVERSAL, "passed": True, "lane": BETA}])
        self.assertEqual(self.looks_asked(), [QQQ, REVERSAL], "the second overnight seed is never looked at")
        (refusal,) = self.store.refusals(SPY)
        self.assertEqual(refusal["stage"], "same lineage")
        self.assertIn(QQQ, refusal["reason"])
        self.assertEqual(self.store.refusals(REVERSAL), [], "a lineage of its own")
        self.assertNotIn("waits", out)
        with screen():
            self.assertEqual(self.tournament.equity_round()["retired"], [SPY])
        fam = self.store.family(SPY)
        self.assertEqual(fam["retire_reason"], elane.SAME_LINEAGE, "retired with that reason, plainly")
        self.assertEqual({self.store.family(f)["band"] for f in (QQQ, REVERSAL)}, {"candidate"})

    def test_the_seconds_they_were_born_in_do_not_change_it(self):
        self.seeded()
        # The store's own order would now put SPY's seed first: born a second before the others.
        self.store.update_family(SPY, born_at="2026-10-11T00:00:00Z")
        self.store.update_family(REVERSAL, born_at="2026-10-11T00:00:01Z")
        self.store.update_family(QQQ, born_at="2026-10-11T00:00:02Z")
        fams = self.store.families(alive=True, lanes=elane.LANES)
        self.assertEqual([f["id"] for f in fams], [SPY, REVERSAL, QQQ])
        self.assertEqual([f["id"] for f in elane.round_order(self.store, fams)], [QQQ, REVERSAL, SPY])
        self.round()
        self.assertEqual(self.looks_asked()[:1], [QQQ])
        self.assertEqual(self.store.refusals(SPY)[0]["stage"], "same lineage")

    def test_a_look_owed_again_never_hands_the_lineage_to_the_later_seed(self):
        self.seeded()
        self.runner.calls.clear()
        self.runner.unmade = {QQQ}                    # the House cannot make its sealed run in this round
        out = self.round()
        self.assertEqual([row["family"] for row in out["looked"]], [REVERSAL], "a lineage of its own waits for nobody")
        self.assertEqual(out["waits"], {SPY: QQQ})
        self.assertEqual(self.looks_asked(), [QQQ, REVERSAL], "nothing sealed was run for the later seed of the lineage")
        self.assertEqual(([row["family"] for row in self.looks()], self.store.refusals()), ([REVERSAL], []),
                         "a wait: no look and no try is spent")
        for fid in (QQQ, SPY):
            state = self.store.family(fid)["state"]
            self.assertEqual((state["gate_ready"], state.get("look_inflight")), (True, None), fid)
        state = self.store.family(SPY)["state"]
        self.assertEqual(state["gate_outcome"]["result"], "waiting")
        self.assertIn(QQQ, state["gate"])
        self.assertEqual((self.waiting()["for"], self.waiting()["waited"]), (QQQ, 0.0))
        self.runner.unmade = set()
        self.clock.advance(elane.ROUND_SECONDS)
        out = self.round()
        self.assertEqual([row["family"] for row in out["looked"]], [QQQ], "the next round, as declared")
        self.assertIn(QQQ, self.store.refusals(SPY)[0]["reason"])
        self.assertNotIn("waits", out)
        self.assertIsNone(self.waiting(), "the wait ended with the earlier seed's verdict")
        self.assertEqual(self.said() + self.said("equity_seed_wait_over"), [], "a short wait is no news")

    def test_the_wait_has_no_timeout_and_its_warning_is_said_once(self):
        """verify-evidence-1: past the old bound the later seed was looked at whatever the earlier one's state."""
        self.seeded()
        self.runner.unmade = {QQQ}
        self.assertEqual(self.round()["waits"], {SPY: QQQ})
        out = self.rounds(elane.SEED_WAIT_SECONDS - elane.ROUND_SECONDS)
        self.assertEqual((out["waits"], self.said()), ({SPY: QQQ}, []), "inside the line: a wait, and nothing said")
        out = self.rounds(elane.ROUND_SECONDS)
        self.assertEqual((out["waits"], out["looked"]), ({SPY: QQQ}, []), "past the line it still waits")
        (warned,) = self.said()
        payload = warned["payload"]
        self.assertEqual((warned["family"], payload["ahead"], payload["alert"], payload["repeat"]), (SPY, QQQ, True, False))
        self.assertIn(SPY, payload["text"][:300])
        self.assertIn(QQQ, payload["text"][:300])
        self.assertIn("its one sealed look is still owed", payload["text"][:300], "why the earlier one has no verdict")
        self.assertIn("no timeout", payload["text"])
        out = self.rounds(2 * 3600)
        self.assertEqual((out["waits"], len(self.said())), ({SPY: QQQ}, 1), "hours later: still waiting, said once")
        self.assertNotIn(SPY, self.looks_asked(), "the later seed's sealed run was never made")
        self.assertEqual([row["family"] for row in self.looks()], [REVERSAL])
        # A day after the warning it is said again, once.
        self.store.set_state(SPY, **{elane.SEED_WAIT_KEY: {
            **self.waiting(), "alerted": self.clock() - elane.SEED_WAIT_REPEAT_SECONDS + 2 * elane.ROUND_SECONDS}})
        self.rounds(elane.ROUND_SECONDS)
        self.assertEqual(len(self.said()), 1, "not yet a day")
        self.rounds(2 * elane.ROUND_SECONDS)
        self.assertEqual([e["payload"]["repeat"] for e in self.said()], [False, True], "at most daily")
        # The earlier seed's run is made: it is judged, the later one is refused as its lineage, the warning clears.
        self.runner.unmade = set()
        out = self.rounds(elane.ROUND_SECONDS)
        self.assertEqual([row["family"] for row in out["looked"]], [QQQ])
        self.assertEqual(self.store.refusals(SPY)[0]["stage"], "same lineage")
        self.assertEqual(self.store.refusals(QQQ), [], "the seed A18 names spent the lineage's look")
        (over,) = self.said("equity_seed_wait_over")
        self.assertEqual((over["family"], over["payload"]["alert"], over["payload"]["ahead"]), (SPY, False, QQQ))
        self.assertIsNone(self.waiting())
        self.assertNotIn(SPY, self.looks_asked())

    def test_rounds_in_which_no_look_could_be_taken_do_not_run_the_clock(self):
        """verify-evidence-1's own scenario: all three seeds wait for the data job for longer than the old bound, the
        store lands, and in that round the House cannot make the earlier seed's sealed run once."""
        self.seeded()
        gap = "the daily store ends before the look's holdout: the sealed look waits for the data job"
        for _ in range(8):
            out = self.round(gap=gap)
            self.assertEqual((out["looked"], out.get("waits")), ([], None))
            self.clock.advance(elane.ROUND_SECONDS)
        self.assertEqual(self.said(), [], "nothing was looked at and no order was broken")
        self.assertIsNone(self.waiting(), "the wait was never asked: its own look was not ready")
        self.runner.unmade = {QQQ}
        out = self.round()
        self.assertEqual(([row["family"] for row in out["looked"]], out["waits"]), ([REVERSAL], {SPY: QQQ}))
        self.runner.unmade = set()
        out = self.rounds(elane.ROUND_SECONDS)
        self.assertEqual([row["family"] for row in out["looked"]], [QQQ])
        self.assertEqual((self.store.refusals(SPY)[0]["stage"], self.store.refusals(QQQ)), ("same lineage", []))

    def test_the_clock_counts_only_the_rounds_its_own_look_was_ready(self):
        self.seeded()
        self.runner.unmade = {QQQ}
        self.assertEqual(self.round()["waits"], {SPY: QQQ})
        out = self.rounds(8 * elane.ROUND_SECONDS, gap="the daily store ends before the look's holdout")
        self.assertNotIn("waits", out, "its own look waits for the data job: the order is not asked")
        self.assertEqual(self.rounds(elane.ROUND_SECONDS)["waits"], {SPY: QQQ})
        self.assertEqual((self.said(), self.waiting()["waited"]), ([], 0.0), "45 minutes on the wall, none of them counted")
        self.rounds(elane.SEED_WAIT_SECONDS - elane.ROUND_SECONDS)
        self.assertEqual(self.said(), [])
        self.rounds(elane.ROUND_SECONDS)
        self.assertEqual(len(self.said()), 1, "30 minutes of rounds in which only the order held it")

    def test_the_operators_hold_on_the_earlier_seed_holds_its_lineage_and_no_other(self):
        self.seeded()
        self.store.set_state(QQQ, gate_hold=True)
        out = self.round()
        self.assertEqual((out["held"], [row["family"] for row in out["looked"]], out["waits"]),
                         ([QQQ], [REVERSAL], {SPY: QQQ}))
        self.assertIn("gate_hold", elane.seed_owed(self.store, self.store.family(QQQ), ON))
        self.rounds(elane.SEED_WAIT_SECONDS)
        (warned,) = self.said()
        self.assertIn("gate_hold", warned["payload"]["text"][:300], "the warning says why")
        # The operator gives the lineage's look to the later seed by retiring the earlier one.
        self.store.retire(QQQ, "retired by hand")
        out = self.rounds(elane.ROUND_SECONDS)
        self.assertEqual([row["family"] for row in out["looked"]], [SPY])
        self.assertEqual(len(self.said("equity_seed_wait_over")), 1)
        self.assertIsNone(self.waiting())

    def test_a_seed_that_failed_its_pre_check_or_is_retired_holds_nobody_back(self):
        self.seeded()
        self.store.set_state(QQQ, gate_ready=False, **{elane.TRY_KEY: {"version": 1, "precheck": False,
                                                                        "entered": False}})
        self.assertEqual(elane.lineage_spent(self.store, self.store.family(QQQ), ON), elane.SPENT_TRY)
        self.assertIsNone(elane.seed_owed(self.store, self.store.family(QQQ), ON), "FAILED, and no retry owed")
        self.assertIsNone(elane.seed_ahead(self.store, self.store.family(SPY), ON))
        self.store.retire(REVERSAL, "retired by hand")
        out = self.round()
        self.assertEqual([row["family"] for row in out["looked"]], [SPY], "the lineage's look is the next seed's")
        self.assertNotIn("waits", out)

    def test_a_retired_earlier_seed_holds_nobody_back(self):
        self.seeded()
        self.store.retire(QQQ, "retired by hand")
        self.assertIsNone(elane.seed_owed(self.store, self.store.family(QQQ), ON))
        out = self.round()
        self.assertEqual([row["family"] for row in out["looked"]], [REVERSAL, SPY])
        self.assertNotIn("waits", out)

    def test_an_earlier_seed_owed_its_validation_or_its_retry_has_no_verdict(self):
        born = elane.birth_seeds(self.store, ON)
        self.assertEqual(born, [QQQ, REVERSAL, SPY])
        self.assertIn("Validation is still owed", elane.seed_owed(self.store, self.store.family(QQQ), ON))
        self.assertEqual(elane.seed_ahead(self.store, self.store.family(SPY), ON), QQQ, "before any Validation")
        with screen():
            self.tournament.equity_round()
        # Its first try FAILED the pre-check and its pre-registered retry (R3) is open: still no verdict.
        retry = self.store.add_version(QQQ, self.store.version(QQQ, 1)["code"], {"share": 0.4}, author="test")
        self.store.set_state(QQQ, gate_ready=False, **{elane.TRY_KEY: {"version": 1, "precheck": False, "entered": False,
                                                                        "retry_sha": run_sha(retry)}})
        with screen(), mock.patch.object(S, "retry_permitted", return_value=True):
            self.assertIsNone(elane.lineage_spent(self.store, self.store.family(QQQ), ON))
            self.assertIn("retry", elane.seed_owed(self.store, self.store.family(QQQ), ON))
            self.assertEqual(elane.seed_ahead(self.store, self.store.family(SPY), ON), QQQ)
        with screen():  # the receipt permits no retry: the failed pre-check is its verdict
            self.assertIsNone(elane.seed_ahead(self.store, self.store.family(SPY), ON))

    def test_an_earlier_seed_refused_before_its_look_holds_until_it_is_retired(self):
        """The gate is done with it without a look (here: no eligible floor), and the tournament's next step retires
        it. Until then it is alive without a verdict, so the later seed of its lineage waits that one round."""
        self.seeded()
        elane._refuse(self.gate, QQQ, 1, run_sha(self.store.version(QQQ, 1)), "screen floor", "no eligible floor",
                      screen="S1")
        self.assertEqual(elane.lineage_spent(self.store, self.store.family(QQQ), ON), elane.FLOOR_INELIGIBLE)
        self.assertIn("retires", elane.seed_owed(self.store, self.store.family(QQQ), ON))
        out = self.round()
        self.assertEqual(([row["family"] for row in out["looked"]], out["waits"]), ([REVERSAL], {SPY: QQQ}))
        with screen():
            self.assertEqual(self.tournament.equity_round()["retired"], [QQQ])
        self.assertEqual(self.store.family(QQQ)["retire_reason"], elane.FLOOR_INELIGIBLE)
        out = self.rounds(elane.ROUND_SECONDS)
        self.assertEqual([row["family"] for row in out["looked"]], [SPY])
        self.assertIsNone(self.waiting())

    def test_seeds_of_different_lineages_never_wait_on_each_other(self):
        self.seeded()
        self.runner.unmade = {REVERSAL}
        out = self.round()
        self.assertEqual([row["family"] for row in out["looked"]], [QQQ])
        self.assertNotIn("waits", out)
        self.assertEqual(self.store.refusals(SPY)[0]["stage"], "same lineage", "refused by D3: it waited for nobody")
        self.assertIsNone(elane.seed_ahead(self.store, self.store.family(REVERSAL), ON))
        self.assertIsNone(self.waiting(REVERSAL))

    def test_a_family_that_is_no_seed_waits_for_no_seed(self):
        self.seeded()
        self.ready("b1", code=CODE + "# not a seed\n")
        self.runner.unmade = {QQQ}
        out = self.round()
        self.assertEqual(sorted(row["family"] for row in out["looked"]), sorted(["b1", REVERSAL]))
        self.assertEqual(out["waits"], {SPY: QQQ})
        self.assertIsNone(elane.seed_ahead(self.store, self.store.family("b1"), ON))
        self.assertIsNone(elane.seed_wait(self.store, self.store.family("b1"), ON))
        self.assertIsNone(self.waiting("b1"))

    def test_an_order_that_cannot_be_read_takes_no_seeds_look(self):
        """STRICT, so it fails closed: a wait spends nothing, a look taken out of order is spent for good."""
        self.seeded()
        version, sha = self.ready("own1", seeded=False, code=CODE + "# not a seed\n")
        self.store.set_state("own1", review={"sha": sha, "verdict": "pass", "audit": {"verdict": "pass"}})
        self.runner.calls.clear()
        with mock.patch.object(elane, "_seed_places", side_effect=RuntimeError("unreadable")):
            with self.assertRaises(RuntimeError):
                elane.seed_wait(self.store, self.store.family(SPY), ON)
            out = self.round()
        self.assertEqual([row["family"] for row in out["looked"]], ["own1"], "a family that is no seed is untouched")
        self.assertEqual(self.looks_asked(), ["own1"], "no seed's sealed run was made")
        self.assertNotIn("waits", out)
        for fid in (QQQ, REVERSAL, SPY):
            state = self.store.family(fid)["state"]
            self.assertEqual((state["gate_ready"], state.get("look_inflight")), (True, None), fid)
            failed = [e["payload"] for e in self.store.events_after(0, limit=100_000)
                      if e["kind"] == "swarm.gate" and e.get("family") == fid and e["payload"].get("action") == "look_failed"]
            self.assertEqual([p["stage"] for p in failed], ["seed order"], fid)
        self.assertEqual((self.store.refusals(), [row["family"] for row in self.looks()]), ([], ["own1"]))
        out = self.rounds(elane.ROUND_SECONDS)
        self.assertEqual([row["family"] for row in out["looked"]], [QQQ, REVERSAL], "readable again: as declared")


# ------------------------------------------------------------------------------------------- the public wording
class ThePublicWording(unittest.TestCase):
    """verify-evidence-3: the repository is public and the rehearsal read REAL vendor data. Its commits wrote counts
    read from that data, and two findings about the seeds on real Train data (which of the two overnight seeds has
    the lower bar at its look, and how their Train returns correlate), into public text. A public file says what a
    rule IS and why (the daily bar's close is the closing cross; a flat bar of volume 0 is a session without a trade;
    the vendor rounds its adjusted prices to the cent; the seeds' declared order is the captain's decision, made
    before any Validation or look from Train-era figures only, amendment A18; the two overnight seeds share a
    template and are one lineage). It never carries a count read from the vendor's data, nor either finding."""

    #: The public texts the rehearsal's commits wrote in (the CHANGELOG: what is not yet deployed).
    FILES = ("CHANGELOG.md", "docs/operations.md", "league/equity/INTERFACES.md", "league/equity/EQUITY.md",
             "league/equity/config.py", "league/equity/engine.py", "league/equity/live.py", "league/ops/equity_data.py",
             "league/swarm/seeds.py", "league/swarm/elane.py", "league/swarm/gate.py",
             "league/tests/test_equity_data.py", "league/tests/test_equity_i6.py", "league/tests/test_equity_fx_daily.py",
             "league/tests/test_equity_fx_swarm.py", "league/tests/test_equity_e2e.py", "league/tests/test_elane_seeds.py",
             "league/tests/test_equity_rehearsal.py")
    #: The two findings about the seeds on real Train data, as they were worded.
    FINDINGS = (r"lower\s+bar", r"higher\s+power", r"correlate\s+at\s+or\s+above", r"one\s+lineage\s+on\s+real",
                r"real\s+bars\s+found\s+(?:\*\*)?the\s+two", r"On\s+real\s+Train\s+series", r"as\s+the\s+rehearsal\s+found\s+the\s+two")
    #: The counts read from the vendor's data, as they were worded (sessions, windows, symbols, ratio steps, events,
    #: ex-dividend days, decision days, zero-volume bars).
    COUNTS = (r"252\s+sessions", r"\b(?:all|on|the)\s+252\b", r"\b233\s+rolling", r"\b190\s+extended", r"\b43\s+unverified",
              r"\b12\s+unverified", r"\b221\s+regular", r"\bon\s+13\b", r"\b18\s+of\s+them", r"\b103\s+of\b", r"\bon\s+67\b",
              r"\b205\s+of\s+205", r"\b0\s+of\s+205", r"\b35\s+symbols", r"78,586", r"1,312\s+real", r"21,440", r"21,420",
              r"1,185", r"2,190", r"\b0\s+to\s+2\s+of\b", r"two\s+(?:flat\s+)?bars\s+of\s+volume", r"two\s+such\s+bars",
              r"two\s+sessions\s+of\s+2016", r"one\s+symbol,\s+two\s+sessions", r"\"count\s+2\"",
              r"essentially\s+every\s+decision\s+day")

    def texts(self):
        """{file: its public text}: the whole file, but the CHANGELOG from "Not yet deployed" to the first deployed
        entry, and this file without this class (it names the wordings it bars)."""
        out = {}
        for name in self.FILES:
            text = (REPO / name).read_text()
            if name == "CHANGELOG.md":
                start = text.index("## Not yet deployed")
                text = text[start:text.index("\n## ", start + 1)]
            if name == "league/tests/test_equity_rehearsal.py":
                text = text.replace(inspect.getsource(ThePublicWording), "")
            out[name] = text
        return out

    def test_no_count_read_from_the_vendors_data_is_in_a_public_text(self):
        for name, text in self.texts().items():
            for pattern in self.COUNTS:
                with self.subTest(file=name, pattern=pattern):
                    self.assertNotRegex(text, pattern)

    def test_neither_finding_about_the_seeds_on_real_data_is_in_a_public_text(self):
        for name, text in self.texts().items():
            for pattern in self.FINDINGS:
                with self.subTest(file=name, pattern=pattern):
                    self.assertNotRegex(text, pattern)

    def test_what_a_rule_is_and_why_stays_said(self):
        job = " ".join((REPO / "league" / "ops" / "equity_data.py").read_text().split())
        for words in ("where the closing cross prints", "a session without a trade", "THE VOLUME IS NOT COMPARED"):
            self.assertIn(words, job)
        self.assertIn("rounded to the cent", " ".join((REPO / "league" / "equity" / "config.py").read_text().split()))
        page = " ".join((REPO / "docs" / "operations.md").read_text().split())
        for words in ("before any Validation or look, from Train-era figures only", "amendment A18",
                      "The two overnight seeds share a template and are one lineage"):
            self.assertIn(words, page)
        log = " ".join(self.texts()["CHANGELOG.md"].split())
        for words in ("The vendor rounds its adjusted prices to the cent", "a session without a trade",
                      "where the closing cross prints", "from Train-era figures only"):
            self.assertIn(words, log)


# ------------------------------------------------------------------------------------------- the event tables
EVENTS_PROGRAM = ("NEEDS = {'symbols': ['SPY'], 'history': 5, 'max_hold_sessions': 5}\nPARAMS = {}\n\n\n"
                  "def decide(ctx):\n    return []\n")
MONEY = dict(cash=1000.0, equity=1000.0, budget=1000.0, caps={"SPY": 500.0})


class TheEventTablesCoverage(unittest.TestCase):
    """rehearsal-8: the FOMC, CPI and jobs tables (league/gym/events.py) start in 2017, and the CPI and jobs tables
    end before the first live session, while the equity Train window starts in 2016. Outside a table's coverage its
    flag is False on every session, which says nothing about the day. Stated in the program contract; the same in the
    Gym and live (one constructor); the tables are extended, with verified dates, before any program that reads them
    is born (events.py is in the equity identity, so not after a look)."""

    @classmethod
    def setUpClass(cls):
        import tempfile

        from league.equity import program as P
        from league.equity import store as ST
        from league.equity import synth

        cls.dir = tempfile.TemporaryDirectory()
        cls.program = P.load_program(EVENTS_PROGRAM, name="events")
        early = synth.synthetic_store(Path(cls.dir.name) / "early", symbols=("SPY",), start=dt.date(2016, 1, 4),
                                      end=dt.date(2016, 12, 30), seed=3)
        cls.early = ST.EquityStore(early).bars(["SPY"], "train", history=5)
        late = synth.synthetic_store(Path(cls.dir.name) / "late", symbols=("SPY",), start=dt.date(2026, 8, 3),
                                     end=dt.date(2026, 10, 9), seed=3, gate=True)
        cap = ST.mint_equity_gate_capability(late, reason="a synthetic store: the tables' coverage after their last rows")
        cls.late = ST.EquityStore(late, gate=cap).bars(["SPY"], ST.LOOK, history=5)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def both(self, bars, t):
        """The session's events from the Gym's inputs and from the live fetch's: (day, gym ctx, live ctx)."""
        from league.equity import ctx as C
        from league.gym.day import from_ordinal
        from league.tests.test_equity_i6 import fetched

        common = dict(needs=self.program.needs, params=self.program.params, **MONEY)
        day = from_ordinal(int(bars.days[t]))
        raw_rows, all_rows = fetched(bars, t)
        gym = C.build(C.inputs_from_bars(bars, t, **common))
        live = C.build(C.inputs_from_fetch(raw_rows, all_rows, day=day.isoformat(), **common))
        return day, gym, live

    def test_the_coverage_is_what_the_contract_says(self):
        from league.gym import events

        spans = {name: (min(table), max(table)) for name, table in
                 (("fomc", events.FOMC), ("cpi", events.CPI), ("jobs", events.JOBS))}
        self.assertEqual({first.year for first, _ in spans.values()}, {2017}, "no table has a 2016 row")
        self.assertLess(spans["cpi"][1], dt.date(2026, 10, 12), "the CPI table ends before the first live session")
        self.assertLess(spans["jobs"][1], dt.date(2026, 10, 12))
        contract = " ".join((REPO / "league" / "equity" / "EQUITY.md").read_text().split())
        page = " ".join((REPO / "docs" / "operations.md").read_text().split())
        for name, (first, last) in spans.items():
            for text in (contract, page):
                self.assertIn(f"{name} {first.isoformat()} through {last.isoformat()}", text,
                              "the tables' own first and last rows, said where a program's author reads")

    def test_before_the_tables_and_after_their_last_rows_the_flags_are_false_live_as_in_the_gym(self):
        from league.equity import ctx as C
        from league.gym import events

        seen = {"quarter_end": 0, "monthly_opex": 0, "half_day": 0}
        for bars in (self.early, self.late):
            # From the first session with a whole history in the slice (a synthetic store starts where it starts).
            for t in range(max(bars.first, self.program.needs.history), bars.n):
                day, gym, live = self.both(bars, t)
                self.assertEqual(C.ctx_bytes(gym), C.ctx_bytes(live), day)
                self.assertEqual((gym.events, gym.events_next), (live.events, live.events_next), day)
                covered = {"fomc": day in events.FOMC, "cpi": day in events.CPI, "jobs": day in events.JOBS}
                self.assertEqual({k: gym.events[k] for k in covered}, covered)
                if day.year == 2016:
                    self.assertEqual(set(covered.values()), {False}, f"{day}: before every table")
                if day > max(events.CPI):
                    self.assertFalse(gym.events["cpi"] or gym.events["jobs"], f"{day}: after both tables' last rows")
                for name in seen:
                    seen[name] += bool(gym.events[name])
        self.assertTrue(all(seen.values()), f"the calendar's own flags hold everywhere: {seen}")


# ------------------------------------------------------------------------------------- a later store's as-of prices
class TheCtxOfALaterStore(unittest.TestCase):
    """rehearsal-6: I6 (league/tests/test_equity_i6.py) holds byte for byte between the two BUILDERS fed the same
    bars. It does not hold between a live decision's ctx and the same session read later from the store once an event
    has restated the adjusted series: the vendor rounds each adjusted price to the cent again, so the as-of prices move
    by up to the rounding of the prices they are built from (`config.rounding_bound`). A live `ctx_sha` therefore does
    not reproduce from a later store; A14's intent-agreement reading (95% of counted sessions) polices what that does
    to decisions. Building as-of prices from raw bars and per-event factors is owed before E2's births depend on it."""

    RAW = (100.37, 101.12, 99.81, 100.05, 102.33, 101.47)

    def ctx(self, level: float):
        from league.equity import ctx as C
        from league.equity import program as P
        from league.tests.test_equity_i6 import stamp

        program = P.load_program(EVENTS_PROGRAM, name="later")
        days = [dt.date(2025, 3, d) for d in (3, 4, 5, 6, 7, 10)]
        raw_rows = {"SPY": [{"t": stamp(d), "o": c, "h": c, "l": c, "c": c, "v": 1000.0} for d, c in zip(days, self.RAW)]}
        all_rows = {"SPY": [{**r, **{k: cents(r[k] * level) for k in "ohlc"}} for r in raw_rows["SPY"]]}
        inputs = C.inputs_from_fetch(raw_rows, all_rows, day=days[-1].isoformat(), needs=program.needs,
                                     params=program.params, **MONEY)
        return C, C.build(inputs), [row["c"] for row in all_rows["SPY"]]

    def test_a_restated_series_gives_other_bytes_within_the_rounding_bound(self):
        C, live, live_all = self.ctx(0.9731)                 # the 16:20 fetch of session t
        _, later, later_all = self.ctx(0.9731 * 0.9971)      # the store, after a later ex-date restated the series
        self.assertNotEqual(C.ctx_bytes(live), C.ctx_bytes(later), "not byte for byte")
        a, b = live.bars["SPY"].close, later.bars["SPY"].close
        self.assertEqual(float(a[-1]), float(b[-1]), "session t's own close is the raw close in both")
        moved = 0
        for i in range(len(self.RAW) - 1):
            bound = config.rounding_bound(live_all[i], live_all[-1], later_all[i], later_all[-1])
            self.assertLessEqual(abs(float(a[i]) - float(b[i])), bound * float(a[i]) + 1e-4, i)
            moved += float(a[i]) != float(b[i])
        self.assertGreater(moved, 0, "some as-of price moved")


if __name__ == "__main__":
    unittest.main()
