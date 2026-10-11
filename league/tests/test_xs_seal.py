"""The panel lane's seals that package C owns (E4-SPEC 14): X1 and X2.

X1 `NoNameNoDateNoLevelReachesAProgram`: over 20 synthetic days what a run is sent (`PanelBars`) and what a decision
is built from (`Inputs`) hold no aid and no text but the run's own labels, and the ctx is exactly the registered
contract's slots: no ticker, no date, no price level, no share count, no dollar volume. AND AN ADVERSARY FAILS
(`TheLevelCannotBeSearched`): given everything a program is given over 60 consecutive ctxs of a panel whose prices
sit on the cent grid, with dividends, three searches recover no name's close within 5% and SPY's neither; the same
searches DO recover every close, exactly, when the dither is switched off in the test (so the test would see a leak).
The contract shows no price array (the pinned pre-registration's C1), so the searches read the five scale-free fields
(league/xs/E4_INTERFACES.md, open point 11).

X2 `IdsAreSaltedPerRun`: ids and sector codes are unrelated across run keys and fixed inside one, whatever joins or
leaves the index.

Every panel is synthetic (`league.xs.synth`): no market data.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import math
import pickle
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

import numpy as np

from league.equity.store import mint_equity_gate_capability, ordinal
from league.xs import config, ctx, store, synth
from league.xs.program import Needs

D = dt.date
REF = len(config.REF)
#: The fields of a `PanelBars`, an `Inputs`, a lot row and a ctx that may hold text: the run's own labels and the
#: engine's own words. Everything else that is text would be a name or a date.
TEXT_FIELDS = {"window", "data_version", "at", "tag", "reason", "rejects", "params"}


def texts(value, path: str = ""):
    """(path, text) of every str inside dataclasses, mappings and sequences (bytes are not text)."""
    if isinstance(value, str):
        yield path, value
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        for field in dataclasses.fields(value):
            yield from texts(getattr(value, field.name), f"{path}.{field.name}".lstrip("."))
    elif isinstance(value, dict):
        for key, item in value.items():           # a row's keys are the contract's own field names
            yield from texts(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from texts(item, path)
    elif isinstance(value, (ctx.XsCtx, ctx.Fields)):
        for name in value.__slots__:
            yield from texts(getattr(value, name), f"{path}.{name}".lstrip("."))


def allowed(path: str) -> bool:
    return any(part in TEXT_FIELDS for part in path.split("."))


class NoNameNoDateNoLevelReachesAProgram(unittest.TestCase):
    """SEAL X1."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = synth.synthetic_panel(Path(cls.tmp.name) / "equity-daily", n_assets=40, seed=21, gate=True,
                                         start=D(2023, 6, 1), end=D(2026, 10, 9))
        gate = mint_equity_gate_capability(cls.root, "the seal's test")
        cls.panel = store.PanelStore(cls.root, gate=gate)
        cls.universe = cls.panel.universe()
        cls.needs = Needs("sp500", 60, 10, "weekly", 0, 60)
        cls.slices = [cls.panel.bars(window, history=60, run_key=f"run-sha|{window}|first")
                      for window in ("validation", "look")]
        cls.slices.append(cls.panel.train(D(2024, 6, 3), D(2024, 12, 31), history=60, run_key="run-sha|train|first"))
        cls.tickers = sorted({row[0] for asset in cls.universe._assets.values() for row in asset.spells}
                             | set(config.REF))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def decisions(self):
        """20 decision days over the three slices, each with a held lot, a closed lot and a reject."""
        rng = np.random.default_rng(5)
        for piece in self.slices:
            bars = piece.bars
            for t in sorted(rng.choice(np.arange(bars.first, bars.n), 7, replace=False).tolist())[:7]:
                col = REF + int(rng.integers(0, bars.ids.shape[0]))
                mark = float(np.nan_to_num(bars.raw[t, col, 3], nan=50.0))
                lots = [{"lid": 4, "col": col, "qty": 1.75, "value": 1.75 * mark, "entry_value": 1.7 * mark,
                         "held_sessions": 3, "at": "open", "tag": "mine"}]
                closed = [{"lid": 2, "col": col, "net_ret": 0.01, "held_sessions": 6, "reason": "max_hold",
                           "tag": "mine"}]
                yield piece, t, ctx.inputs_from_panel(bars, t, needs=self.needs, positions=lots, closed=closed,
                                                      rejects=["order cap"], cash=500.0, equity=1000.0, budget=1000.0,
                                                      params={"style": "contrarian", "k": 5})

    def test_what_a_run_is_sent_holds_no_aid_no_symbol_and_no_text_but_its_labels(self):
        self.assertEqual([f.name for f in dataclasses.fields(store.PanelBars)],
                         ["days", "early", "first", "raw", "adj", "elig0", "ref", "ids", "exit", "hs", "sector_perm",
                          "dither_key", "window", "data_version"])
        for piece in self.slices:
            bars = piece.bars
            found = list(texts(bars))
            self.assertEqual(sorted(path for path, _ in found), ["data_version", "window"])
            self.assertIn(bars.window, store.WINDOWS)
            self.assertRegex(bars.data_version, r"^[0-9a-f]{24}$")
            aids = set(piece.aids[REF:].tolist())
            self.assertFalse(aids & set(bars.ids.tolist()), "an id is never an aid")
            for name in ("ids", "exit", "sector_perm", "days"):
                values = np.asarray(getattr(bars, name)).astype(np.int64)
                self.assertFalse(values.shape == piece.aids[REF:].shape and np.array_equal(np.sort(values),
                                                                                           np.sort(piece.aids[REF:])))
            data = pickle.dumps(bars)
            self.assertNotIn(synth.TEST_SALT, data)
            self.assertNotIn(piece.run_key.encode(), data, "the run key stays with the parent")
            self.assertNotIn(piece.aids.astype(np.int32).tobytes(), data)
            self.assertNotIn(piece.aids.astype(np.int64).tobytes(), data)
            self.assertNotIn(store.run_salt(synth.TEST_SALT, piece.run_key), data)
            for ticker in self.tickers:
                self.assertNotIn(b"\x00" + ticker.encode() + b"\x00", data)
            self.assertEqual([f.name for f in dataclasses.fields(piece)], ["bars", "aids", "run_key"],
                             "the aids and the run key are the parent's Slice")

    def test_over_twenty_days_the_inputs_hold_no_aid_and_no_text_but_their_labels(self):
        seen = 0
        for piece, t, inputs in self.decisions():
            seen += 1
            for path, text in texts(inputs):
                self.assertTrue(allowed(path), f"{path}: {text!r}")
            data = pickle.dumps(inputs)
            self.assertNotIn(synth.TEST_SALT, data)
            self.assertNotIn(piece.run_key.encode(), data)
            self.assertNotIn(piece.aids.astype(np.int32).tobytes(), data)
            for ticker in self.tickers:
                self.assertNotIn(b"\x00" + ticker.encode() + b"\x00", data)
            self.assertFalse(set(piece.aids[REF:].tolist()) & set(np.asarray(inputs.ids).tolist()))
            self.assertEqual([f.name for f in dataclasses.fields(inputs)],
                             ["days", "raw", "adj", "elig0", "ref", "ids", "dither_key", "sector_perm", "history",
                              "max_names", "trading_days", "early", "positions", "closed", "rejects", "cash",
                              "equity", "budget", "params"])
        self.assertGreaterEqual(seen, 20)

    def test_over_twenty_days_the_ctx_is_the_contracts_slots_and_nothing_names_or_dates_or_prices(self):
        seen = 0
        for piece, t, inputs in self.decisions():
            seen += 1
            c = ctx.build(inputs)
            self.assertEqual(tuple(c.__slots__), (
                "n", "ids", "ret", "oret", "iret", "range", "rel_volume", "sector", "beta", "mkt", "positions",
                "closed", "rejects", "cash", "equity", "budget", "weekday", "session_of_month",
                "sessions_left_in_month", "last_session_of_week", "max_names", "params"))
            for path, text in texts(c):
                self.assertTrue(allowed(path), f"ctx.{path}: {text!r}")
            # NO DATE: the calendar is four small counts; no number is a session's ordinal, a year or a month-day
            day = dt.date(1970, 1, 1) + dt.timedelta(days=int(inputs.days[-1]))
            self.assertEqual((c.weekday, c.max_names), (day.weekday(), 10))
            self.assertTrue(1 <= c.session_of_month <= 23 and 0 <= c.sessions_left_in_month <= 22)
            scalars = [c.n, c.weekday, c.session_of_month, c.sessions_left_in_month, c.max_names, c.cash, c.equity,
                       c.budget]
            for value in scalars:
                self.assertNotIn(value, (int(inputs.days[-1]), day.year, day.toordinal()))
            for value in (*c.ids.tolist(), *(lot["id"] for lot in c.positions), *(lot["slot"] for lot in c.positions)):
                self.assertNotIn(value, set(inputs.days.tolist()))
            self.assertFalse(any(isinstance(getattr(c, name), (dt.date, dt.datetime)) for name in c.__slots__))
            # NO LEVEL, NO SHARE COUNT, NO DOLLAR VOLUME: every field is a pure ratio, far from any price or volume
            derived = ctx.derive(inputs)
            cols = np.flatnonzero(derived.elig)
            h = self.needs.history
            raw, adj = inputs.raw[-(h + 1):, cols], inputs.adj[-(h + 1):, cols]
            series = [raw[:, :, k].T for k in range(5)] + [adj[:, :, k].T for k in range(4)]
            series.append((raw[:, :, 3] * raw[:, :, 4]).T)
            for name in ctx.FIELDS:
                values = getattr(c, name)
                finite = values[np.isfinite(values)]
                self.assertLess(float(np.abs(finite).max(initial=0.0)), 60.0, name)
                for other in series:
                    self.assertFalse(np.allclose(values, other, equal_nan=True, rtol=1e-3, atol=1e-6), name)
            for name in ("ret", "oret", "iret", "range"):
                self.assertLess(float(np.nanmax(np.abs(getattr(c, name)), initial=0.0)), 3.0, name)
            self.assertLess(float(np.nanmax(np.abs(c.beta), initial=0.0)), 20.0)
            # the ids are the salted ones, the sector the relabelled one; nothing else is an integer array
            self.assertTrue(set(c.ids.tolist()) <= set(inputs.ids.tolist()))
            self.assertTrue(set(c.sector.tolist()) <= set(range(11)))
            self.assertEqual(c.positions[0]["slot"], int(inputs.ids[inputs.positions[0]["col"] - REF]))
            self.assertEqual(sorted(c.positions[0]), ["at", "held_sessions", "id", "ret", "slot", "tag", "weight"])
            self.assertEqual(sorted(c.closed[0]), ["held_sessions", "id", "net_ret", "reason", "slot", "tag"])
        self.assertGreaterEqual(seen, 20)

    def test_the_program_reads_params_and_text_it_wrote_and_no_other(self):
        _, _, inputs = next(iter(self.decisions()))
        c = ctx.build(inputs)
        self.assertEqual(dict(texts(c)), {"positions.at": "open", "positions.tag": "mine",
                                          "closed.reason": "max_hold", "closed.tag": "mine", "rejects": "order cap",
                                          "params.style": "contrarian"})
        self.assertEqual(c.params, {"style": "contrarian", "k": 5})


# ------------------------------------------------------------------------------------------------- the adversary
def simplest_between(low: float, high: float) -> Fraction:
    """The fraction with the smallest denominator in [low, high] (0 < low <= high): continued fractions."""
    whole = math.floor(low)
    if whole + 1 <= high or whole == low:
        return Fraction(whole if whole == low else whole + 1)
    rest = simplest_between(1.0 / (high - whole), 1.0 / (low - whole))
    return whole + 1 / rest


def lattice(ret, oret, spread, *, low: int = 100, high: int = 1_000_000, slack: float = 0.0):
    """(a) THE LATTICE SEARCH. Every candidate last close from $1 to $10,000 in cents; walk back through the
    sessions: the close before (x / (1 + ret)), the open (the close before x (1 + oret)) and the day's range (range x
    the close) must each sit on a whole number of cents, to within what the fields' own 6-decimal rounding moves
    them (half a millionth of the price: above about $9,400 that is half a cent, and the rounding alone hides the
    grid). `slack`: cents more allowed, for a search that knows how far a dither moved each price. The candidates
    that survive every session, ascending."""
    candidates = np.arange(low, high + 1, dtype=np.float64)
    x = candidates.copy()
    for s in range(len(ret) - 1, 0, -1):
        if not (math.isfinite(ret[s]) and math.isfinite(oret[s]) and math.isfinite(spread[s])):
            return candidates[:0]
        tol = 0.002 + 0.53e-6 * x + slack
        wick = spread[s] * x
        before = x / (1.0 + ret[s])
        whole = np.rint(before)
        opened = whole * (1.0 + oret[s])
        keep = (np.abs(wick - np.rint(wick)) <= tol) & (np.abs(before - whole) <= tol) \
            & (np.abs(opened - np.rint(opened)) <= tol)
        candidates, x = candidates[keep], whole[keep]
        if not candidates.size:
            break
    return candidates


def told_the_neighbourhood(ret, oret, truth: float) -> float:
    """(a') THE SAME SEARCH, TOLD THE CLOSE WITHIN A FACTOR OF TWO: of every candidate from half the true close to
    twice it, the one whose implied closes and opens sit nearest whole cents (least squares)."""
    candidates = np.arange(max(1, int(truth // 2)), int(truth * 2) + 1, dtype=np.float64)
    score = np.zeros_like(candidates)
    scale = 1.0
    for s in range(len(ret) - 1, 0, -1):
        scale /= 1.0 + ret[s]                           # the close before, as a share of the last close
        before = candidates * scale
        opened = before * (1.0 + oret[s])
        score += (before - np.rint(before)) ** 2 + (opened - np.rint(opened)) ** 2
    return float(candidates[int(np.argmin(score))])


def moves(ret, oret, *, rounding: float = 0.6e-6, harmonics: int = 12, near: float = 5e-4) -> tuple[int, float]:
    """(b) CONTINUED FRACTIONS ON A RATIO OF RATIOS. ret / oret = (the close's move) / (the open's move): two SMALL
    whole numbers of cents on a grid, so the simplest fraction inside the ratio's rounding interval is the pair (up
    to a common factor g), and the close before is (the close's move) / ret. Each session's estimate, carried to the
    last close by the returns between, is then the close / g: the estimates VOTE for the level they are whole
    fractions of. (votes, level): the smallest level that nine tenths of the best vote agree on."""
    estimates = []
    carry = 1.0
    for s in range(len(ret) - 1, 0, -1):
        r, o = ret[s], oret[s]
        carry *= 1.0 + r                                 # the last close over the close before s
        if not (math.isfinite(r) and math.isfinite(o)) or abs(r) < 2e-3 or abs(o) < 3e-4:
            continue
        ratio = abs(r / o)
        slack = ratio * rounding * (1.0 / abs(r) + 1.0 / abs(o))
        if slack >= ratio:
            continue
        pair = simplest_between(ratio - slack, ratio + slack)
        if pair.numerator:
            estimates.append(pair.numerator / abs(r) * carry)
    found = np.array(estimates)
    tally = []
    for level in sorted({float(e * k) for e in estimates for k in range(1, harmonics + 1)}):
        share = level / found
        whole = np.rint(share)
        agree = (whole >= 1) & (whole <= harmonics) & (np.abs(share / np.maximum(whole, 1.0) - 1.0) <= near)
        tally.append((int(agree.sum()), level))
    best = max(votes for votes, _ in tally)
    return best, min(level for votes, level in tally if votes >= 0.9 * best)


class TheLevelCannotBeSearched(unittest.TestCase):
    """SEAL X1's adversary, on `synth.cent_panel`: 50 names on the cent grid, with dividends."""

    CTXS, HISTORY = 60, 60

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = synth.cent_panel(Path(cls.tmp.name) / "equity-daily", n_assets=50, seed=13, churn=0.0,
                                    start=D(2023, 6, 1), end=D(2025, 12, 31))
        cls.panel = store.PanelStore(cls.root)
        cls.piece = cls.panel.bars("validation", history=cls.HISTORY, run_key="adversary|validation|2025-01-02")
        cls.bars = cls.piece.bars
        cls.first = cls.bars.first + 120
        cls.needs = Needs("sp500", cls.HISTORY, 10, "weekly", 0, 60)
        cls.seen = cls.collect()
        with mock.patch.object(config, "DITHER_HALF", 0.0):
            ctx._DITHERS.clear()
            ctx._REL.clear()
            cls.bare = cls.collect()
        ctx._DITHERS.clear()
        ctx._REL.clear()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def collect(cls) -> dict:
        """EVERYTHING A PROGRAM IS GIVEN over the 60 consecutive ctxs: per slot id (and -1 for SPY) the fields of
        every session it was shown (the 60 decisions' and the 60 before them), every view of each bar kept; and a
        held lot's `ret` and `weight` with the sleeve's `cash` and `equity`, ctx by ctx."""
        span = cls.CTXS + cls.HISTORY
        views: dict[int, dict[str, list]] = {}
        book = []
        held = None
        for k in range(cls.CTXS):
            t = cls.first + k
            probe = ctx.inputs_from_panel(cls.bars, t, needs=cls.needs, cash=0.0, equity=0.0, budget=1000.0, params={})
            if held is None:
                held = int(np.flatnonzero(ctx.derive(probe).elig)[3])
                entry = float(cls.bars.raw[t, held, 3])
            lot = {"lid": 1, "col": held, "qty": 1.5, "value": 0.0, "entry_value": 1.5 * entry, "held_sessions": k,
                   "at": "open", "tag": ""}
            c = ctx.build(dataclasses.replace(probe, positions=(lot,), cash=250.0))
            book.append({"ret": c.positions[0]["ret"], "weight": c.positions[0]["weight"], "cash": c.cash,
                         "equity": c.equity, "slot": c.positions[0]["slot"]})
            for ident, row in [(-1, None), *((int(i), n) for n, i in enumerate(c.ids.tolist()))]:
                slot = views.setdefault(ident, {**{name: [[] for _ in range(span)] for name in ctx.FIELDS}, "ctxs": 0})
                slot["ctxs"] += 1
                for name in ctx.FIELDS:
                    values = getattr(c.mkt, name) if row is None else getattr(c, name)[row]
                    for j, value in enumerate(values.tolist()):
                        if j == 0 and name in ("ret", "oret"):
                            continue                # a ctx's first column has no close before it: NaN by contract
                        slot[name][k + j].append(value)      # the session's place among the 120 shown
        return {"views": views, "book": book, "held": held}

    def names(self, seen: dict) -> list[int]:
        """The ids shown at every one of the 60 decisions (SPY's -1 among them)."""
        full = [ident for ident, slot in seen["views"].items() if slot["ctxs"] == self.CTXS]
        self.assertGreaterEqual(len(full), 40)
        self.assertIn(-1, full)
        return sorted(full)

    def series(self, seen: dict, ident: int) -> tuple[list[float], list[float], list[float]]:
        slot = seen["views"][ident]
        return tuple([views[0] if views else math.nan for views in slot[name]] for name in ("ret", "oret", "range"))

    def truth(self, ident: int) -> int:
        """The name's adjusted close at the last of the 60 decisions, in cents (what its last column is a ratio of);
        on a panel with dividends it is within a few percent of its raw close."""
        col = config.MARKET_COLUMN if ident == -1 else REF + self.bars.ids.tolist().index(ident)
        t = self.first + self.CTXS - 1
        cents = float(self.bars.adj[t, col, 3]) * 100.0
        self.assertAlmostEqual(cents, round(cents), delta=1e-6, msg="the panel sits on the cent grid")
        self.assertLess(abs(float(self.bars.raw[t, col, 3]) * 100.0 / cents - 1.0), 0.04)
        return int(round(cents))

    def near(self, answer: float | None, truth: int) -> bool:
        return answer is not None and abs(answer / truth - 1.0) <= 0.05

    def test_the_panel_has_ex_dates_inside_the_60_ctxs(self):
        rows = slice(self.first - self.HISTORY, self.first + self.CTXS)
        ratio = self.bars.adj[rows, REF:, 3] / self.bars.raw[rows, REF:, 3]
        stepped = (np.abs(np.diff(ratio, axis=0)) > 5e-4).any(axis=0)
        self.assertGreaterEqual(int(stepped.sum()), 8, "names went ex-dividend between the first view and the last")
        self.assertEqual(len(self.seen["views"][-1]["ret"]), 120)

    def test_a_the_lattice_search_recovers_every_close_without_the_dither(self):
        for ident in self.names(self.bare):
            survivors = lattice(*self.series(self.bare, ident))
            self.assertTrue(survivors.size, ident)
            self.assertEqual(int(survivors[0]), self.truth(ident), f"id {ident}: the smallest survivor is the close")

    def test_a_the_lattice_search_recovers_nothing_with_it(self):
        recovered = 0
        for ident in self.names(self.seen):
            truth = self.truth(ident)
            survivors = lattice(*self.series(self.seen, ident))
            # what survives is only where the fields' own rounding is itself near half a cent (candidates of
            # several thousand dollars, which pass with the dither or without): nowhere near any close here
            self.assertFalse(survivors.size and survivors[0] < 500_000, ident)
            self.assertLess(truth, 100_000)
            self.assertFalse(self.near(float(survivors[0]) if survivors.size else None, truth))
            # a search that allows for the dither (half a cent either side) keeps every candidate: nothing to grip
            sample = np.random.default_rng(ident % 1000).integers(100, 400_000, 500).astype(np.float64)
            ret, oret, _ = self.series(self.seen, ident)
            x = sample.copy()
            for s in range(len(ret) - 1, 0, -1):
                before = x / (1.0 + ret[s])
                self.assertTrue((np.abs(before - np.rint(before)) <= 0.5).all())
                x = np.rint(before)
            recovered += self.near(told_the_neighbourhood(ret, oret, truth), truth)
        # told the close within a factor of two, the best-scoring candidate is within 5% as often as a blind guess
        # in that range would be (1 in 15): not once in a dozen names more
        self.assertLessEqual(recovered, 12)

    def test_a_told_the_neighbourhood_it_recovers_every_close_without_the_dither(self):
        for ident in self.names(self.bare):
            ret, oret, _ = self.series(self.bare, ident)
            truth = self.truth(ident)
            self.assertLessEqual(abs(told_the_neighbourhood(ret, oret, truth) - truth), 2.0, ident)

    def test_b_continued_fractions_recover_every_close_without_the_dither(self):
        for ident in self.names(self.bare):
            ret, oret, spread = self.series(self.bare, ident)
            truth = self.truth(ident)
            votes, level = moves(ret, oret)
            self.assertGreaterEqual(votes, 8, ident)
            self.assertLess(abs(level / truth - 1.0), 1e-3, f"id {ident}: the moves in cents give the level")
            exact = lattice(ret, oret, spread, low=int(level * 0.998), high=int(level * 1.002) + 1)
            self.assertEqual([int(v) for v in exact], [truth], "and the grid pins it to the cent")

    def test_b_continued_fractions_recover_nothing_with_it(self):
        """A dithered move is no ratio of two small whole numbers: the estimates agree on nothing. The level they
        vote for is a guess (it lands within 5% as often as a guess does), and the grid confirms none of them."""
        guessed = 0
        for ident in self.names(self.seen):
            ret, oret, spread = self.series(self.seen, ident)
            truth = self.truth(ident)
            votes, level = moves(ret, oret)
            self.assertLessEqual(votes, 12, f"id {ident}: no more agree than chance brings together")
            self.assertFalse(lattice(ret, oret, spread, low=max(100, int(level * 0.998)),
                                     high=int(level * 1.002) + 1).size, f"id {ident}: nothing on the grid there")
            self.assertFalse(lattice(ret, oret, spread, low=int(truth * 0.95), high=int(truth * 1.05) + 1).size,
                             f"id {ident}: and nothing within 5% of the close")
            guessed += self.near(level, truth)
        self.assertLessEqual(guessed, 8)

    def test_b_one_ratio_alone_gives_a_level_only_under_seven_dollars(self):
        """Continued fractions on `1 + ret`: a 6-decimal ratio pins p / q only while q x q is under a million, so one
        ratio alone names a close under about $7 (and the ratio of ratios above is what reaches every price)."""
        low = round(541 / 537 - 1.0, 6)
        self.assertEqual(Fraction(1.0 + low).limit_denominator(999), Fraction(541, 537))
        dithered = round((5.41 + 0.0031) / (5.37 - 0.0044) - 1.0, 6)
        self.assertNotEqual(Fraction(1.0 + dithered).limit_denominator(999), Fraction(541, 537))
        high = round(20541 / 20537 - 1.0, 6)
        self.assertNotEqual(Fraction(1.0 + high).limit_denominator(99_999), Fraction(20541, 20537))

    def test_c_two_views_of_one_bar_are_the_same_numbers(self):
        """(c) THE DITHER-RANGE BOUND ACROSS TWO VIEWS OF ONE BAR needs two views that differ. Every bar was shown in
        up to 60 ctxs, before and after ex-dividend dates: every view of it is the same number, field by field."""
        compared = 0
        for ident, slot in self.seen["views"].items():
            for name in ctx.FIELDS:
                for views in slot[name]:
                    if len(views) > 1:
                        compared += 1
                        self.assertTrue(all(v == views[0] or (math.isnan(v) and math.isnan(views[0])) for v in views))
        self.assertGreater(compared, 45 * 100 * 5)

    def test_c_the_bound_has_teeth_against_a_dither_drawn_again_for_each_view(self):
        """Why the dither is one draw a bar for the whole run: were it drawn again for each view, the two views of a
        bar would differ by about a cent over the price, and the size of that difference IS the level. This is the
        bound, run on a dither built that way here (the design the review refused): it finds the level within 5%.
        Run on the built ctx's views it has nothing to read."""
        rng = np.random.default_rng(3)
        price = 137.42 * np.exp(np.cumsum(rng.normal(0.0, 0.002, 2000)))
        views = [np.round(price, 2) + rng.uniform(-0.005, 0.005, price.shape[0]) for _ in range(2)]
        rets = [np.round(v[1:] / v[:-1] - 1.0, 6) for v in views]

        def bound(first: np.ndarray, second: np.ndarray) -> float | None:
            """A return's two views differ by (two differences of two uniforms on a cent) / the price: a spread of a
            cent / (sqrt(3) x the price)."""
            spread = float(np.std(first - second))
            return None if spread == 0.0 else 0.01 / (math.sqrt(3.0) * spread)

        level = bound(*rets)
        self.assertLess(abs(level / float(np.median(price)) - 1.0), 0.05)
        self.assertLess(float(price.max() / price.min()), 1.5)
        ident = self.names(self.seen)[5]
        slot = self.seen["views"][ident]["ret"]
        firsts = np.array([views[0] for views in slot if len(views) > 1])
        lasts = np.array([views[-1] for views in slot if len(views) > 1])
        self.assertGreater(firsts.shape[0], 100)
        self.assertIsNone(bound(firsts, lasts))

    def test_a_held_lots_marks_and_the_sleeves_dollars_recover_nothing(self):
        """`positions[].ret` and `weight` (4 decimals) and `equity` - `cash` (cents) over 60 ctxs: each is the held
        name's dithered close times a constant. No search on them finds its close, with the dither or without: at
        these precisions the grid is already below the rounding."""
        t = self.first + self.CTXS - 1
        truth = int(round(float(self.bars.raw[t, self.seen["held"], 3]) * 100.0))
        for seen in (self.seen, self.bare):
            book = seen["book"]
            marks = np.array([row["equity"] - row["cash"] for row in book])
            rets = np.array([1.0 + row["ret"] for row in book])
            self.assertTrue(np.allclose(marks / marks[0], rets / rets[0], rtol=2e-4))
            for series, rounding in ((marks, 0.005 / float(marks.min())), (rets, 0.5e-4)):
                candidates = np.arange(100, 1_000_001, dtype=np.float64)
                x = candidates.copy()
                for k in range(len(series) - 1, 0, -1):
                    before = x * series[k - 1] / series[k]
                    keep = np.abs(before - np.rint(before)) <= 0.01 + 2.0 * rounding * x
                    candidates, x = candidates[keep], np.rint(before)[keep]
                self.assertFalse(self.near(float(candidates[0]) if candidates.size else None, truth))
        self.assertEqual(len({row["slot"] for row in self.seen["book"]}), 1)

    def test_why_the_dither_sits_on_the_adjusted_grid_and_not_on_the_raw_one(self):
        """E4-SPEC D7's words move each bar's RAW price by half a raw cent. The vendor serves adjustment=all rounded
        to the cent, so after a 4-for-1 split the adjusted history is a quarter of the raw one AND on the cent grid:
        half a raw cent is an eighth of an adjusted cent, and the lattice search, allowed that much, finds the level
        to the cent or two. Moved by half a cent of the adjusted grid (what `ctx.build` does) nothing survives."""
        rng = np.random.default_rng(17)
        n = 120
        raw_close = np.round(412.0 * np.exp(np.cumsum(rng.normal(0.0, 0.012, n))), 2)
        raw_open = np.round(np.concatenate([[raw_close[0]], raw_close[:-1]]) * np.exp(rng.normal(0.0, 0.004, n)), 2)
        raw_high = np.round(np.maximum(raw_open, raw_close) * (1.0 + np.abs(rng.normal(0.0, 0.004, n))), 2)
        raw_low = np.round(np.minimum(raw_open, raw_close) * (1.0 - np.abs(rng.normal(0.0, 0.004, n))), 2)
        raw = np.stack([raw_open, raw_high, raw_low, raw_close], axis=1)
        adj = np.round(raw / 4.0, 2)                               # the vendor's cents, on a quarter of the price
        u = rng.uniform(-0.005, 0.005, raw.shape)
        truth = int(round(adj[-1, 3] * 100.0))

        def fields(prices):
            o, h, low, c = prices.T
            ret, oret = np.full(n, np.nan), np.full(n, np.nan)
            ret[1:], oret[1:] = c[1:] / c[:-1] - 1.0, o[1:] / c[:-1] - 1.0
            return np.round(ret, 6).tolist(), np.round(oret, 6).tolist(), np.round((h - low) / c, 6).tolist()

        bare = lattice(*fields(adj), high=60_000)
        self.assertEqual(int(bare[0]), truth)
        on_the_raw_grid = lattice(*fields(adj * (1.0 + u / raw)), high=60_000, slack=0.27)   # two eighths of a cent
        self.assertTrue(on_the_raw_grid.size and abs(float(on_the_raw_grid[0]) / truth - 1.0) < 0.01,
                        "half a raw cent leaves the adjusted grid in sight")
        on_its_own_grid = fields(adj + u)
        for slack in (0.0, 0.27, 0.45):
            self.assertFalse(lattice(*on_its_own_grid, high=60_000, slack=slack).size, slack)

    def test_the_dither_covers_the_adjusted_grid_whatever_a_later_dividend_or_split_made_of_it(self):
        """The grid a ratio of two history prices keeps is the ADJUSTED price's own cent grid (the vendor rounds
        adjustment=all to the cent). Every dithered price is its adjusted price moved by under half a cent, and the
        dithered prices' cents are spread evenly over the whole cell: no gap for a search to find."""
        t = self.first + self.CTXS - 1
        inputs = ctx.inputs_from_panel(self.bars, t, needs=self.needs, cash=0.0, equity=0.0, budget=0.0, params={})
        key, days = inputs.dither_key, inputs.days.tolist()
        adj = inputs.adj[:, REF:REF + 12, 3]
        self.assertTrue(np.allclose(adj * 100.0, np.rint(adj * 100.0), atol=1e-6))
        moved = np.array([[adj[r, i] + ctx.dither(key, int(inputs.ids[i]), days[r], b"c") for i in range(12)]
                          for r in range(adj.shape[0])])
        offset = (moved - adj) * 100.0
        self.assertTrue((np.abs(offset) <= 0.5).all())
        counts, _ = np.histogram(offset.ravel(), bins=10, range=(-0.5, 0.5))
        expected = offset.size / 10.0
        self.assertTrue((np.abs(counts - expected) < 5.0 * math.sqrt(expected)).all(), counts.tolist())
        shrunk = inputs.adj[0, REF:, 3] / inputs.raw[0, REF:, 3]
        self.assertTrue((shrunk < 0.999).any(), "some adjusted prices are below their raw ones: dividends since")


class IdsAreSaltedPerRun(unittest.TestCase):
    """SEAL X2."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = synth.synthetic_panel(Path(cls.tmp.name) / "equity-daily", n_assets=40, seed=8, churn=0.15,
                                         start=D(2023, 6, 1), end=D(2025, 12, 31))
        cls.panel = store.PanelStore(cls.root)
        cls.universe = cls.panel.universe()
        cls.table = cls.universe.table()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def slice(self, run_key: str, **cut):
        return self.panel.bars("validation", history=60, run_key=run_key, **cut)

    def test_two_run_keys_give_unrelated_ids_and_sector_codes(self):
        a, b = self.slice("sha-one|validation|2025-01-02"), self.slice("sha-two|validation|2025-01-02")
        self.assertEqual(sorted(a.aids.tolist()), sorted(b.aids.tolist()))
        self.assertFalse(set(a.bars.ids.tolist()) & set(b.bars.ids.tolist()))
        self.assertNotEqual(a.aids.tolist(), b.aids.tolist(), "the member columns are in another order")
        rank_a = {aid: i for i, aid in enumerate(a.aids[REF:].tolist())}
        rank_b = {aid: i for i, aid in enumerate(b.aids[REF:].tolist())}
        aids = sorted(rank_a)
        ra, rb = np.array([rank_a[x] for x in aids], dtype=float), np.array([rank_b[x] for x in aids], dtype=float)
        self.assertLess(abs(float(np.corrcoef(ra, rb)[0, 1])), 0.4, "one run's order says nothing of another's")
        self.assertLess(abs(float(np.corrcoef(ra, np.array(aids, dtype=float))[0, 1])), 0.4, "nor of the aids'")
        self.assertNotEqual(a.bars.dither_key, b.bars.dither_key)
        perms = {tuple(self.slice(f"sha-{k}|validation|2025-01-02").bars.sector_perm.tolist()) for k in range(6)}
        self.assertEqual(len(perms), 6)
        # the same program, another window or another first day: another run key, other ids
        c = self.slice("sha-one|look|2025-01-02")
        self.assertFalse(set(a.bars.ids.tolist()) & set(c.bars.ids.tolist()))

    def test_one_run_key_gives_the_same_ids_on_every_day(self):
        key = "sha-one|validation|2025-01-02"
        whole = self.slice(key)
        ids = dict(zip(whole.aids[REF:].tolist(), whole.bars.ids.tolist()))
        for cut in ({"end": D(2025, 3, 31)}, {"start": D(2025, 6, 2), "end": D(2025, 6, 30)}, {"start": D(2025, 11, 3)}):
            part = self.slice(key, **cut)
            self.assertEqual(dict(zip(part.aids[REF:].tolist(), part.bars.ids.tolist())),
                             {aid: ids[aid] for aid in part.aids[REF:].tolist()})
        needs = Needs("sp500", 20, 10, "weekly", 0, 60)
        seen: dict[int, int] = {}
        for t in range(whole.bars.first, whole.bars.n, 9):
            c = ctx.build(ctx.inputs_from_panel(whole.bars, t, needs=needs, cash=0.0, equity=0.0, budget=0.0, params={}))
            for ident in c.ids.tolist():
                aid = int(whole.aids[REF + whole.bars.ids.tolist().index(ident)])
                self.assertEqual(seen.setdefault(ident, aid), aid)
        self.assertGreater(len(seen), 40)
        self.assertTrue(all(ids[aid] == ident for ident, aid in seen.items()))

    def test_a_membership_change_inside_a_run_moves_no_id(self):
        key = "sha-one|validation|2025-01-02"
        whole = self.slice(key)
        days = [dt.date(1970, 1, 1) + dt.timedelta(days=int(d)) for d in whole.bars.days]
        ids = dict(zip(whole.aids[REF:].tolist(), whole.bars.ids.tolist()))
        joined = [aid for aid in ids if not self.universe.member(aid, days[whole.bars.first])
                  and self.universe.member(aid, days[-1])]
        left = [aid for aid in ids if self.universe.member(aid, days[whole.bars.first])
                and not self.universe.member(aid, days[-1])]
        self.assertTrue(joined and left, "names join and leave inside the run")
        # a name joins whose id is LOWER than a held name's: a rank would have moved the held name's id
        stayed = [aid for aid in ids if self.universe.member(aid, days[whole.bars.first])
                  and self.universe.member(aid, days[-1])]
        self.assertTrue(any(ids[j] < ids[s] for j in joined for s in stayed))
        for day in (days[whole.bars.first], days[whole.bars.first + 120], days[-1]):
            members = [aid for aid, _ in self.universe.members(day)]
            live = self.slice(key, start=day, end=day, aids=[*members, *left])     # a live day's columns
            self.assertEqual(dict(zip(live.aids[REF:].tolist(), live.bars.ids.tolist())),
                             {aid: ids[aid] for aid in live.aids[REF:].tolist()})
        # a held name that left the index keeps its id AND its column, with its bars, and is no candidate
        gone = left[0]
        column = whole.aids.tolist().index(gone)
        self.assertEqual(int(whole.bars.ids[column - REF]), ids[gone])
        self.assertTrue(np.isfinite(whole.bars.raw[-1, column, 3]))
        self.assertFalse(whole.bars.elig0[-1, column])

    def test_the_id_of_an_aid_is_the_same_whatever_other_aids_are_asked_with_it(self):
        run = store.run_salt(synth.TEST_SALT, "k")
        table = list(range(100, 400))
        every = dict(zip(table, store.ids_for(table, run, table=table).tolist()))
        rng = np.random.default_rng(1)
        for _ in range(20):
            asked = rng.choice(table, int(rng.integers(1, 60)), replace=False).tolist()
            self.assertEqual(store.ids_for(asked, run, table=table).tolist(), [every[a] for a in asked])
        # a new asset takes an aid above every old one: the old ids do not move
        grown = dict(zip([*table, 400, 401], store.ids_for([*table, 400, 401], run, table=[*table, 400, 401]).tolist()))
        self.assertEqual({a: grown[a] for a in table}, every)

    def test_a_forced_collision_is_settled_by_the_lower_aid_and_stays_settled(self):
        streams = {100: [7, 1, 2], 101: [7, 9, 3], 102: [9, 7, 11], 103: [7, 9, 11, 13], 104: [5]}

        def fake(run, aid):
            yield from streams[aid]

        run = store.run_salt(synth.TEST_SALT, "k")
        with mock.patch.object(store, "_id_candidates", fake):
            first = store.ids_for([100, 101, 102], run, table=[100, 101, 102])
            self.assertEqual(first.tolist(), [7, 9, 11], "the lower aid keeps the value; the higher takes its next")
            self.assertEqual(store.ids_for([102, 100], run, table=[100, 101, 102]).tolist(), [11, 7],
                             "settled over the whole table, not over the aids asked")
            self.assertEqual(store.ids_for([102], run, table=[100, 101, 102]).tolist(), [11])
            grown = store.ids_for([100, 101, 102, 103, 104], run, table=[100, 101, 102, 103, 104])
            self.assertEqual(grown.tolist(), [7, 9, 11, 13, 5], "a higher aid added later moves none of them")
        # the real stream: the 4-byte windows of the aid's digest, then of that digest's own hash
        digest = hashlib.sha256(run + b"|id|" + b"100").digest()
        stream = store._id_candidates(run, 100)
        got = [next(stream) for _ in range(10)]
        self.assertEqual(got[:8], [int.from_bytes(digest[k:k + 4], "big") >> 1 for k in range(0, 32, 4)])
        again = hashlib.sha256(digest).digest()
        self.assertEqual(got[8:], [int.from_bytes(again[k:k + 4], "big") >> 1 for k in (0, 4)])
        self.assertTrue(all(0 <= value < 2 ** 31 for value in got))

    def test_what_a_program_answers_with_is_an_id_and_only_the_parent_can_name_it(self):
        """A target is keyed by ids; the aids (and so the symbols) are in the parent's `Slice` alone, in the columns'
        order: the child plans by id, the parent names the symbols."""
        piece = self.slice("sha-one|validation|2025-01-02")
        day = D(2025, 6, 2)
        row = piece.bars.days.tolist().index(ordinal(day))
        needs = Needs("sp500", 20, 10, "weekly", 0, 60)
        c = ctx.build(ctx.inputs_from_panel(piece.bars, row, needs=needs, cash=0.0, equity=0.0, budget=0.0, params={}))
        members = dict(self.universe.members(day))
        for ident in c.ids.tolist():
            aid = int(piece.aids[REF + piece.bars.ids.tolist().index(ident)])
            self.assertIn(aid, members, "every slot is a member of the day")
            self.assertEqual(self.universe.aid(self.universe.symbol(aid, day), day), aid)
        self.assertFalse(hasattr(piece.bars, "aids") or hasattr(c, "aids"))


if __name__ == "__main__":
    unittest.main()
