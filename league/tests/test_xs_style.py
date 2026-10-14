"""THE STYLE READING (league/xs/style.py; the captain's A22, item 1): the four characteristics against their
definitions written out by hand, the rank, a run's block on hand-built holdings, and THE RULE: a uniform picker is not
style-open; a top-third and a bottom-third picker of each of size, beta, momentum and volatility are, with the sign;
too few lots is; a malformed reading is; and no verdict but a whole "not open" under this module's own figures lets a
passer take a seat.

Invented bars and holdings only: no market data. The bars are `league.xs.store.PanelBars` and the decisions carry
`league.xs.ctx.Derived` (the two shapes are the contract's); the holdings log is a stand-in with `engine.Log`'s two
attributes (`lots`, `decisions`), since the log is package D's and the reading needs nothing else of it.
"""

from __future__ import annotations

import inspect
import json
import math
import statistics
import unittest
from types import SimpleNamespace

import numpy as np

from league.xs import config, ctx, engine, runner, store, style

REF = len(config.REF)


def bars_of(raw: np.ndarray, adj: np.ndarray) -> store.PanelBars:
    """A `PanelBars` over invented arrays (`raw` (n, m, 5), `adj` (n, m, 4)); the columns are REF first."""
    n, m = raw.shape[:2]
    return store.PanelBars(days=np.arange(n, dtype=np.int32), early=np.zeros(n, dtype=bool), first=0, raw=raw, adj=adj,
                           elig0=np.ones((n, m), dtype=bool), ref=REF, ids=np.arange(m - REF, dtype=np.int32),
                           exit=np.zeros(m, dtype=np.int8), hs=np.full((m, 2), 3e-4),
                           sector_perm=np.arange(11, dtype=np.int8), dither_key=b"test", window="train",
                           data_version="synthetic")


def derived_of(m: int, *, beta, mom, elig=None) -> ctx.Derived:
    """A decision's `Derived`: the members eligible (REF never), the given beta and momentum by column."""
    e = np.zeros(m, dtype=bool)
    e[REF:] = True
    if elig is not None:
        e &= np.asarray(elig, dtype=bool)
    none = np.full(m, -1, dtype=np.int8)
    return ctx.Derived(elig=e, beta=np.asarray(beta, dtype=np.float64), mom=np.asarray(mom, dtype=np.float64),
                       sector=none, bg=none, mg=none, cell=np.full(m, -1, dtype=np.int32), rung=config.RUNG)


def log_of(lots, decisions) -> SimpleNamespace:
    """A stand-in for `engine.Log`: `lots` rows {lid, col, weight, decided, ...} and `decisions` rows {t, called,
    derived}."""
    return SimpleNamespace(lots=list(lots), decisions=list(decisions))


def lot(lid: int, col: int, weight: float, decided: int, held: int | None = 1) -> dict:
    """A holdings-log row: bought the session after `decided` and held `held` sessions (None: still open at the
    run's end)."""
    return {"lid": lid, "col": col, "weight": weight, "decided": decided, "entry": decided + 1, "entry_at": "open",
            "exit": None if held is None else decided + 1 + held, "exit_at": None if held is None else "open",
            "reason": None, "hs_open": 3e-4, "hs_close": 3e-4, "cell": 0, "members": np.zeros(0, dtype=np.int32)}


def hand_panel(sessions: int = 140) -> tuple[np.ndarray, np.ndarray, int]:
    """Six member names whose characteristics are known by construction. Name j (0..5, column REF + j): a raw close of
    10 and a raw volume of (j + 1) x 100,000 every session, so its dollar volume is (j + 1) million; its total-return
    close alternates up and down by a step that GROWS with j, so its volatility ranks as j does."""
    m = REF + 6
    raw = np.full((sessions, m, 5), 10.0)
    raw[:, :, 4] = 1e6
    adj = np.full((sessions, m, 4), 10.0)
    for j in range(6):
        col = REF + j
        raw[:, col, 4] = (j + 1) * 1e5
        step = 0.001 * (j + 1)
        path = 20.0 * np.exp(np.cumsum(np.where(np.arange(sessions) % 2 == 0, step, -step)))
        adj[:, col, :] = path[:, None]
    return raw, adj, m


class TheConstants(unittest.TestCase):
    def test_the_figures_are_the_studys_and_the_rules_two(self):
        self.assertEqual(style.CHARACTERISTICS, ("size", "beta", "mom", "vol"))
        self.assertEqual((style.SIZE_SESSIONS, style.SIZE_MIN_VALID), (63, 55), "the pre-registration's arm STYLE")
        self.assertEqual((style.VOL_SESSIONS, style.VOL_MIN_VALID), (60, 55), "its archetype X4's volatility")
        self.assertEqual((style.TILT, style.MIN_LOTS), (1.0 / 3.0, 40))
        self.assertEqual((style.OPEN, style.UNMEASURED), ("style-open", "unmeasured"))
        self.assertLessEqual(max(style.SIZE_SESSIONS, style.VOL_SESSIONS + 1), config.DERIVE_SESSIONS,
                             "a decision's own window holds every session a characteristic reads")

    def test_no_figure_of_the_rule_is_an_argument(self):
        """No threshold of the rule is a setting: neither function takes one."""
        self.assertEqual(list(inspect.signature(style.style_open).parameters), ["reading"])
        self.assertEqual(list(inspect.signature(style.seat_refusal).parameters), ["verdict"])
        self.assertEqual(list(inspect.signature(style.block).parameters), ["bars", "log"])

    def test_the_engine_and_the_runner_ask_for_the_block_by_one_switch(self):
        for function in (engine.run, engine.run_isolated, runner.run_bars, runner.Isolated.train):
            self.assertIs(inspect.signature(function).parameters["style"].default, False)


class TheCharacteristics(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(22)
        self.n, self.m = 80, REF + 9
        close = 20.0 + 60.0 * rng.random((1, self.m))
        raw_close = close * np.exp(np.cumsum(0.02 * (rng.random((self.n, self.m)) - 0.5), axis=0))
        volume = 1e5 * (1.0 + 9.0 * rng.random((self.n, self.m)))
        self.raw = np.stack([raw_close, raw_close * 1.01, raw_close * 0.99, raw_close, volume], axis=2)
        total = raw_close * np.linspace(0.8, 1.0, self.n)[:, None]          # dividends: another level, other returns
        self.adj = np.stack([total, total * 1.01, total * 0.99, total], axis=2)
        self.beta = 0.5 + rng.random(self.m)
        self.mom = rng.random(self.m) - 0.5
        self.derived = derived_of(self.m, beta=self.beta, mom=self.mom)

    def test_each_is_its_definition_written_out(self):
        got = style.characteristics(self.raw, self.adj, self.derived)
        self.assertEqual(tuple(got), style.CHARACTERISTICS)
        for col in range(REF, self.m):
            dollars = [float(self.raw[t, col, 3] * self.raw[t, col, 4]) for t in range(self.n - 63, self.n)]
            self.assertEqual(got["size"][col], statistics.median(dollars), "the median raw dollar volume of 63 sessions")
            closes = self.adj[self.n - 61:, col, 3]
            steps = [math.log(closes[k] / closes[k - 1]) for k in range(1, 61)]
            self.assertAlmostEqual(got["vol"][col], statistics.stdev(steps), delta=1e-15)
            self.assertEqual((got["beta"][col], got["mom"][col]), (self.beta[col], self.mom[col]), "the decision's own")

    def test_a_ref_column_and_an_ineligible_name_have_none(self):
        elig = np.ones(self.m, dtype=bool)
        elig[REF + 2] = False
        got = style.characteristics(self.raw, self.adj, derived_of(self.m, beta=self.beta, mom=self.mom, elig=elig))
        for name in style.CHARACTERISTICS:
            self.assertTrue(np.isnan(got[name][:REF]).all(), f"{name}: a REF column is no name")
            self.assertTrue(np.isnan(got[name][REF + 2]), f"{name}: outside U(d)")
            self.assertTrue(np.isfinite(np.delete(got[name][REF:], 2)).all())

    def test_too_few_valid_sessions_leave_it_undefined(self):
        col = REF + 1
        raw, adj = self.raw.copy(), self.adj.copy()
        raw[-63:-63 + 9, col, 4] = 0.0                      # nine sessions with no volume: 54 valid of 63
        adj[-9:-1, col, 3] = np.nan                         # eight closes gone: 9 returns invalid, 51 valid of 60
        got = style.characteristics(raw, adj, self.derived)
        self.assertTrue(np.isnan(got["size"][col]) and np.isnan(got["vol"][col]))
        raw[-63, col, 4] = 1e5                              # 55 valid: defined again, on the valid sessions alone
        adj[-9:-5, col, 3] = self.adj[-9:-5, col, 3]        # four closes back: 5 returns invalid, 55 valid
        got = style.characteristics(raw, adj, self.derived)
        dollars = [float(raw[t, col, 3] * raw[t, col, 4]) for t in range(self.n - 63, self.n) if raw[t, col, 4] > 0]
        self.assertEqual((len(dollars), got["size"][col]), (55, statistics.median(dollars)))
        closes = adj[self.n - 61:, col, 3]
        steps = [math.log(closes[k] / closes[k - 1]) for k in range(1, 61)
                 if math.isfinite(closes[k]) and math.isfinite(closes[k - 1])]
        self.assertEqual(len(steps), 55)
        self.assertAlmostEqual(got["vol"][col], statistics.stdev(steps), delta=1e-15)
        # a name whose beta or momentum the decision could not form has none here either
        beta = self.beta.copy()
        beta[col] = np.nan
        self.assertTrue(np.isnan(style.characteristics(self.raw, self.adj,
                                                       derived_of(self.m, beta=beta, mom=self.mom))["beta"][col]))

    def test_a_short_window_and_shapes_that_do_not_agree(self):
        got = style.characteristics(self.raw[-61:], self.adj[-61:], self.derived)
        self.assertTrue(np.isnan(got["size"]).all(), "63 sessions are not there")
        self.assertTrue(np.isfinite(got["vol"][REF:]).all(), "61 closes are 60 returns")
        self.assertTrue(np.isnan(style.characteristics(self.raw[-60:], self.adj[-60:], self.derived)["vol"]).all())
        with self.assertRaises(ValueError):
            style.characteristics(self.raw, self.adj[:, :-1], self.derived)
        with self.assertRaises(ValueError):
            style.characteristics(self.raw[:, :-1], self.adj[:, :-1], self.derived)

    def test_size_reads_the_raw_tape_and_volatility_the_total_return(self):
        """A split restates the adjusted series and leaves the tape: size does not move; a level does not move
        volatility either, only returns do."""
        got = style.characteristics(self.raw, self.adj, self.derived)
        again = style.characteristics(self.raw, self.adj * 0.5, self.derived)
        np.testing.assert_array_equal(again["size"], got["size"])
        np.testing.assert_allclose(again["vol"][REF:], got["vol"][REF:], rtol=0, atol=1e-15)
        doubled = self.raw.copy()
        doubled[:, :, 4] *= 2.0
        np.testing.assert_array_equal(style.characteristics(doubled, self.adj, self.derived)["size"][REF:],
                                      2.0 * got["size"][REF:])


class TheRank(unittest.TestCase):
    def test_the_lowest_is_near_minus_one_and_the_highest_near_plus_one(self):
        got = style.ranks(np.array([30.0, 10.0, 20.0, 40.0]))
        np.testing.assert_array_equal(got, np.array([0.25, -0.75, -0.25, 0.75]))        # 2 (q + 0.5) / 4 - 1
        self.assertEqual(float(got.sum()), 0.0, "the ranks of a day are centred")

    def test_a_tie_goes_to_the_lower_column_and_a_missing_value_has_no_rank(self):
        got = style.ranks(np.array([5.0, np.nan, 5.0, 1.0, np.nan, 5.0]))
        self.assertTrue(np.isnan(got[[1, 4]]).all())
        np.testing.assert_array_equal(got[[3, 0, 2, 5]], 2.0 * (np.arange(4) + 0.5) / 4 - 1.0)
        self.assertTrue(np.isnan(style.ranks(np.full(3, np.nan))).all())
        self.assertEqual(style.ranks(np.array([7.0])).tolist(), [0.0], "one name is the middle")
        self.assertEqual(len(style.ranks(np.zeros(0))), 0)


class TheBlock(unittest.TestCase):
    def setUp(self):
        self.raw, self.adj, self.m = hand_panel()
        self.t = 65
        # beta falls as the column rises; momentum is given with a tie the column order settles
        self.derived = derived_of(self.m, beta=np.linspace(2.0, 0.5, self.m),
                                  mom=np.concatenate([np.zeros(REF), [0.1, 0.3, 0.3, -0.2, 0.0, 0.5]]))
        self.decisions = [{"t": self.t, "called": True, "derived": self.derived}]

    def block(self, lots, *, raw=None, adj=None, decisions=None):
        bars = bars_of(self.raw if raw is None else raw, self.adj if adj is None else adj)
        return style.block(bars, log_of(lots, self.decisions if decisions is None else decisions))

    def test_two_lots_by_hand(self):
        """The highest name by size at weight 0.2 and the lowest at 0.1. Six names: ranks 2 p - 1 = -5/6, -1/2, -1/6,
        1/6, 1/2, 5/6. So the size sum is 0.2 x 5/6 - 0.1 x 5/6 = 1/12 and the loading 5/18; volatility ranks as size
        does here; beta ranks the other way; momentum's two names at 0.3 are a tie the lower column takes."""
        got = self.block([lot(1, REF + 5, 0.2, self.t), lot(2, REF + 0, 0.1, self.t)])
        self.assertEqual(set(got), set(style.BLOCK_KEYS))
        self.assertEqual((got["lots"], got["n"]), (2, {name: 2 for name in style.CHARACTERISTICS}))
        for name in style.CHARACTERISTICS:
            self.assertAlmostEqual(got["weight"][name], 0.3, delta=1e-15)
        self.assertAlmostEqual(got["sum"]["size"], 1.0 / 12.0, delta=1e-15)
        self.assertAlmostEqual(got["sum"]["vol"], 1.0 / 12.0, delta=1e-15)
        self.assertAlmostEqual(got["sum"]["beta"], -1.0 / 12.0, delta=1e-15)
        # momentum, ascending by (value, column): name 3 (-0.2), 4 (0.0), 0 (0.1), 1 (0.3), 2 (0.3), 5 (0.5)
        self.assertAlmostEqual(got["sum"]["mom"], 0.2 * (5.0 / 6.0) + 0.1 * (-1.0 / 6.0), delta=1e-15)
        reading = style.pooled([got])
        self.assertAlmostEqual(reading["loadings"]["size"], 5.0 / 18.0, delta=1e-15)
        self.assertEqual((reading["lots"], reading["n"]["size"]), (2, 2))

    def test_a_lot_weighs_by_the_sessions_it_was_held(self):
        """WHAT IT HELD, NOT WHAT IT BOUGHT: the highest name by size at 0.2 held thirty sessions and the lowest at
        0.1 held one. Bought, the loading is 5/18 (the test above); held, the first lot is sixty times the second."""
        got = self.block([lot(1, REF + 5, 0.2, self.t, held=30), lot(2, REF + 0, 0.1, self.t, held=1)])
        self.assertEqual((got["lots"], got["n"]["size"]), (2, 2), "the count is of lots, as MIN_LOTS reads it")
        self.assertAlmostEqual(got["weight"]["size"], 0.2 * 30 + 0.1 * 1, delta=1e-12)
        self.assertAlmostEqual(got["sum"]["size"], (0.2 * 30 - 0.1 * 1) * 5.0 / 6.0, delta=1e-12)
        self.assertAlmostEqual(style.pooled([got])["loadings"]["size"], (5.9 / 6.1) * 5.0 / 6.0, delta=1e-12)
        # A lot still open at the run's end is held through the run's last close.
        sessions = len(self.raw)
        still = self.block([lot(1, REF + 5, 0.2, self.t, held=None), lot(2, REF + 0, 0.1, self.t, held=1)])
        self.assertAlmostEqual(still["weight"]["size"], 0.2 * (sessions - (self.t + 1)) + 0.1, delta=1e-12)
        # A lot whose sessions cannot be read is counted and carries nothing (it can only open the program).
        for broken in ({"entry": None}, {"exit": self.t + 1}, {"exit": self.t}, {"exit": sessions + 5}, {"entry": -1},
                       {"exit": True}):
            row = {**lot(1, REF + 5, 0.2, self.t, held=30), **broken}
            got = self.block([row, lot(2, REF + 0, 0.1, self.t)])
            self.assertEqual((got["lots"], got["n"]["size"]), (2, 1), broken)
            self.assertAlmostEqual(got["weight"]["size"], 0.1, delta=1e-15)
        no_key = lot(1, REF + 5, 0.2, self.t)
        del no_key["entry"]
        self.assertEqual(self.block([no_key])["n"]["size"], 0)

    def test_the_block_holds_counts_and_sums_and_nothing_that_names_a_holding(self):
        got = self.block([lot(1, REF + 5, 0.2, self.t), lot(2, REF + 0, 0.1, self.t)])
        self.assertEqual(json.loads(json.dumps(got)), got, "plain counts and sums: it is stored as it is")
        flat = json.dumps(got)
        for banned in ("col", "lid", "id", "decided", "price", "close"):
            self.assertNotIn(f'"{banned}"', flat)

    def test_a_lot_is_read_at_its_decision_close_and_no_row_after_it_is_read(self):
        lots = [lot(1, REF + 5, 0.2, self.t), lot(2, REF + 0, 0.1, self.t)]
        before = self.block(lots)
        raw, adj = self.raw.copy(), self.adj.copy()
        raw[self.t + 1:], adj[self.t + 1:] = 1e9, 1e-9                 # every later row changed
        self.assertEqual(self.block(lots, raw=raw, adj=adj), before)
        # ... nor is one needed for a rank: with the rows cut at the lots' exit (the sessions they were held are the
        # log's own figures, inside the run) the block is the same.
        self.assertEqual(self.block(lots, raw=raw[:self.t + 3], adj=adj[:self.t + 3]), before, "nor is one needed")
        cut = self.block(lots, raw=raw[:self.t + 1], adj=adj[:self.t + 1])
        self.assertEqual((cut["lots"], cut["n"]["size"]), (2, 0), "a lot entered after the run's last session is unread")
        adj[self.t, REF + 0, 3] *= 1.5                                 # the decision close itself IS read: the
        moved = self.block(lots, raw=raw, adj=adj)                     # quietest name's last return is now the widest
        self.assertAlmostEqual(moved["sum"]["vol"], 0.2 * (1.0 / 2.0) + 0.1 * (5.0 / 6.0), delta=1e-15)

    def test_each_lot_takes_its_own_decisions_ranks(self):
        """Two decisions: by the second the size order has reversed. A lot decided at the first keeps the first's
        rank (as it keeps the first's cell); the same name bought at the second takes the second's."""
        raw = self.raw.copy()
        late = self.t + 70
        raw[late - 62:late + 1, REF:, 4] = raw[late - 62:late + 1, REF:, 4][:, ::-1]      # the later 63 sessions
        later = {"t": late, "called": False, "derived": self.derived}
        col = REF + 5
        early = self.block([lot(1, col, 0.2, self.t)], raw=raw, decisions=[*self.decisions, later])
        after = self.block([lot(1, col, 0.2, late)], raw=raw, decisions=[*self.decisions, later])
        self.assertAlmostEqual(early["sum"]["size"], 0.2 * (5.0 / 6.0), delta=1e-15, msg="the highest at its own close")
        self.assertAlmostEqual(after["sum"]["size"], 0.2 * (-5.0 / 6.0), delta=1e-15, msg="the lowest at the later close")
        both = self.block([lot(1, col, 0.2, self.t), lot(2, col, 0.2, late)], raw=raw, decisions=[*self.decisions, later])
        self.assertAlmostEqual(both["sum"]["size"], 0.0, delta=1e-15)

    def test_a_lot_it_cannot_read_is_counted_and_carries_nothing(self):
        good = lot(1, REF + 5, 0.2, self.t)
        for bad in (lot(2, REF + 0, 0.1, self.t - 1),                   # no decision row at that close
                    lot(2, self.m + 3, 0.1, self.t),                    # a column outside the bars
                    lot(2, REF + 0, 0.0, self.t), lot(2, REF + 0, float("nan"), self.t),
                    lot(2, REF + 0, -0.1, self.t), {"lid": 2}, "not a row",
                    lot(2, REF + 0, 0.1, 10 ** 6)):                     # a session outside the bars
            got = self.block([good, bad])
            self.assertEqual((got["lots"], got["n"]["size"]), (2, 1), bad)
            self.assertAlmostEqual(got["weight"]["size"], 0.2, delta=1e-15)
        # a REF column or a name outside U(d) has no rank: counted, carries nothing
        self.assertEqual(self.block([good, lot(2, 0, 0.1, self.t)])["n"], {name: 1 for name in style.CHARACTERISTICS})
        self.assertEqual(self.block([])["lots"], 0)
        self.assertEqual(style.block(bars_of(self.raw, self.adj), SimpleNamespace())["lots"], 0, "a log with no rows")

    def test_a_characteristic_a_name_lacks_is_left_out_of_that_one_alone(self):
        raw = self.raw.copy()
        raw[self.t - 62:self.t - 50, REF + 5, 4] = 0.0                   # twelve sessions with no volume: no size
        got = self.block([lot(1, REF + 5, 0.2, self.t), lot(2, REF + 0, 0.1, self.t)], raw=raw)
        self.assertEqual(got["n"], {"size": 1, "beta": 2, "mom": 2, "vol": 2})
        self.assertAlmostEqual(got["weight"]["size"], 0.1, delta=1e-15)


class ThePickers(unittest.TestCase):
    """THE RULE on hand-built holdings: sixty names over a hundred and fifty decisions' worth of sessions, whose four
    characteristics are independent of one another. A picker holds five names a decision at the contract's weights."""

    NAMES, SESSIONS, FIRST = 60, 330, 252
    WEIGHTS = (0.20, 0.18, 0.16, 0.14, 0.12)

    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(20261011)
        m = REF + cls.NAMES
        level = np.argsort(rng.random(m))                               # each name's size, its volatility: two
        noise = np.argsort(rng.random(m))                               # independent orders
        close = 30.0 * np.exp(np.cumsum((0.004 + 0.0006 * noise)[None, :] * (rng.random((cls.SESSIONS, m)) - 0.5),
                                        axis=0))
        volume = (2e5 + 4e4 * level)[None, :] * (0.8 + 0.4 * rng.random((cls.SESSIONS, m))) / close
        cls.raw = np.stack([close, close, close, close, volume], axis=2)
        cls.adj = np.stack([close, close, close, close], axis=2)
        cls.m = m
        cls.bars = bars_of(cls.raw, cls.adj)
        cls.decisions = [{"t": t, "called": True,
                          "derived": derived_of(m, beta=0.4 + 1.2 * rng.random(m), mom=rng.random(m) - 0.5)}
                         for t in range(cls.FIRST, cls.SESSIONS - 1, 2)]
        cls.keys = rng.random((len(cls.decisions), m))
        cls.values = [style.characteristics(cls.raw[max(0, d["t"] + 1 - config.DERIVE_SESSIONS):d["t"] + 1],
                                            cls.adj[max(0, d["t"] + 1 - config.DERIVE_SESSIONS):d["t"] + 1],
                                            d["derived"]) for d in cls.decisions]

    def verdict(self, pick, *, spans: int = 1):
        """The rule's verdict on a picker: `pick(i, values) -> the columns it may hold at decision i`; it holds the
        five with the smallest seeded keys among them. `spans`: the same holdings cut into that many runs' blocks."""
        lots = []
        for i, decision in enumerate(self.decisions):
            allowed = np.asarray(pick(i, self.values[i]))
            chosen = allowed[np.argsort(self.keys[i][allowed], kind="stable")][:len(self.WEIGHTS)]
            lots += [lot(len(lots) + j, int(col), w, decision["t"]) for j, (col, w) in enumerate(zip(chosen, self.WEIGHTS))]
        cut = [lots[k::spans] for k in range(spans)]
        blocks = [style.block(self.bars, log_of(part, self.decisions)) for part in cut]
        return style.style_open(style.pooled(blocks))

    @staticmethod
    def third(values: np.ndarray, top: bool) -> np.ndarray:
        """The columns in the top (or the bottom) third of the day's names by one characteristic."""
        order = np.argsort(np.where(np.isfinite(values), values, np.inf), kind="stable")[:int(np.isfinite(values).sum())]
        k = len(order) // 3
        return order[-k:] if top else order[:k]

    def test_a_tilted_core_held_long_beside_a_churned_counter_tilt_is_open(self):
        """The review's evidence-1, on hand-built holdings: six of the HIGHEST-volatility names at 0.14 each, held
        sixty sessions (84% of the sleeve for as long as the House lets a lot stand), beside two of the LOWEST at
        0.04 swapped every week. By what it BOUGHT the churned satellite outvotes the core and the program read not
        open (and could be seated on an XS1 pass); by what it HELD it is a high-volatility program."""
        lots: list[dict] = []
        weeks = self.decisions[::2]                                   # four sessions apart: a week of this panel
        for i, decision in enumerate(weeks):
            values = self.values[self.decisions.index(decision)]
            t = decision["t"]
            if i == 0:                                                # the core: bought once, kept to the maximum hold
                lots += [lot(len(lots), int(col), 0.14, t, held=60) for col in self.third(values["vol"], True)[-6:]]
            week = 4 if t + 1 + 4 <= self.SESSIONS else None          # (the last week's are still open at the end)
            lots += [lot(len(lots), int(col), 0.04, t, held=week)
                     for col in self.third(values["vol"], False)[2 * (i % 3):][:2]]   # the satellite: new names a week
        self.assertEqual(len(lots), 6 + 2 * len(weeks))
        self.assertGreaterEqual(len(lots), style.MIN_LOTS)
        got = style.style_open(style.pooled([style.block(self.bars, log_of(lots, self.decisions))]))
        self.assertEqual((got["open"], got["why"]), (True, style.OPEN), got)
        self.assertIn(["vol", 1], got["tilts"])
        self.assertGreater(got["loadings"]["vol"], 0.6, "what it held: the core, by a wide margin")
        self.assertEqual(style.seat_refusal(got)[:len(style.OPEN)], style.OPEN, "no seat on an XS1 pass alone")
        # THE SAME LOTS BY ENTRY WEIGHT ALONE (every lot one session: what the rule read before): under the bar.
        once = [{**row, "exit": row["entry"] + 1} for row in lots]
        bought = style.style_open(style.pooled([style.block(self.bars, log_of(once, self.decisions))]))
        self.assertLess(abs(bought["loadings"]["vol"]), style.TILT, "by lots bought the satellite hides the core")
        self.assertFalse(["vol", 1] in bought["tilts"])
        # Without the satellite the core alone reads open either way.
        core = [row for row in lots if row["weight"] > 0.1]
        alone = style.pooled([style.block(self.bars, log_of(core, self.decisions))])
        self.assertGreater(alone["loadings"]["vol"], 0.8)

    def test_a_uniform_picker_is_not_style_open(self):
        got = self.verdict(lambda i, values: np.arange(REF, self.m))
        self.assertEqual((got["open"], got["why"], got["tilts"]), (False, None, []))
        self.assertEqual(got["lots"], 5 * len(self.decisions))
        for name in style.CHARACTERISTICS:
            self.assertLess(abs(got["loadings"][name]), 0.15, f"{name}: a uniform pick's mean rank is the middle")
        self.assertIsNone(style.seat_refusal(got), "it may take a seat on its pass")
        cut = self.verdict(lambda i, values: np.arange(REF, self.m), spans=3)
        self.assertEqual((cut["open"], cut["why"], cut["tilts"], cut["lots"]), (False, None, [], got["lots"]))
        for name in style.CHARACTERISTICS:
            self.assertAlmostEqual(cut["loadings"][name], got["loadings"][name], delta=1e-14,
                                   msg="the seen spans' runs read as one: the cut does not move the reading")

    def test_a_top_third_and_a_bottom_third_picker_of_each_characteristic_are(self):
        for name in style.CHARACTERISTICS:
            for top, sign in ((True, 1), (False, -1)):
                with self.subTest(characteristic=name, top=top):
                    got = self.verdict(lambda i, values, name=name, top=top: self.third(values[name], top))
                    self.assertEqual((got["open"], got["why"]), (True, style.OPEN))
                    self.assertEqual(got["tilts"], [[name, sign]], "this style and no other, with its direction")
                    self.assertAlmostEqual(got["loadings"][name], sign * 2.0 / 3.0, delta=0.05,
                                           msg="the mean rank of a third's names is two thirds of the way out")
                    self.assertEqual(style.seat_refusal(got), f"style-open: {name} {'+' if sign > 0 else '-'}")

    def test_a_picker_of_the_middle_third_is_not(self):
        def middle(i, values):
            order = np.argsort(np.where(np.isfinite(values["size"]), values["size"], np.inf), kind="stable")[:self.NAMES]
            return order[self.NAMES // 3:2 * self.NAMES // 3]

        got = self.verdict(middle)
        self.assertFalse(got["open"])
        self.assertLess(abs(got["loadings"]["size"]), 0.1)

    def test_too_few_lots_is_open_unmeasured(self):
        keep = style.MIN_LOTS // len(self.WEIGHTS)
        few = [d for d in self.decisions][:keep - 1]                     # 35 lots
        lots = []
        for i, decision in enumerate(few):
            cols = np.arange(REF, self.m)[np.argsort(self.keys[i][REF:], kind="stable")][:len(self.WEIGHTS)]
            lots += [lot(len(lots) + j, int(c), w, decision["t"]) for j, (c, w) in enumerate(zip(cols, self.WEIGHTS))]
        got = style.style_open(style.pooled([style.block(self.bars, log_of(lots, self.decisions))]))
        self.assertEqual((got["open"], got["why"], got["lots"]), (True, style.UNMEASURED, style.MIN_LOTS - 5))
        self.assertEqual(style.seat_refusal(got), "style-open: unmeasured")
        cols = np.arange(REF, self.m)[np.argsort(self.keys[keep][REF:], kind="stable")][:len(self.WEIGHTS)]
        lots += [lot(900 + j, int(c), w, self.decisions[keep - 1]["t"]) for j, (c, w) in enumerate(zip(cols, self.WEIGHTS))]
        got = style.style_open(style.pooled([style.block(self.bars, log_of(lots, self.decisions))]))
        self.assertEqual((got["lots"], got["why"] == style.UNMEASURED), (style.MIN_LOTS, False), "forty lots are read")


def reading(lots=200, **loadings) -> dict:
    """A `pooled` reading with these loadings (0 where not given), every characteristic read on every lot."""
    return {"lots": lots, "n": {name: lots for name in style.CHARACTERISTICS},
            "loadings": {name: float(loadings.get(name, 0.0)) for name in style.CHARACTERISTICS}}


class TheRule(unittest.TestCase):
    def test_the_bar_is_one_third_in_either_direction(self):
        self.assertFalse(style.style_open(reading(size=0.33, beta=-0.33, mom=0.2, vol=-0.1))["open"])
        for name in style.CHARACTERISTICS:
            for value, sign in ((0.34, 1), (-0.34, -1), (1.0, 1), (-1.0, -1)):
                got = style.style_open(reading(**{name: value}))
                self.assertEqual((got["open"], got["why"], got["tilts"]), (True, style.OPEN, [[name, sign]]), (name, value))
        both = style.style_open(reading(vol=-0.5, size=0.4))
        self.assertEqual(both["tilts"], [["size", 1], ["vol", -1]], "in the characteristics' own order")
        self.assertEqual(style.seat_refusal(both), "style-open: size +, vol -")

    def test_a_loading_exactly_at_the_bar_is_open(self):
        at = style.style_open(reading(beta=style.TILT))
        self.assertEqual((at["open"], at["tilts"]), (True, [["beta", 1]]))
        # one third formed by a division that lands a bit under the float (a sum of 4.1 over a weight of 12.3): still
        # at the bar
        under = 4.1 / 12.3
        self.assertTrue(0.0 < style.TILT - under < 1e-15)
        self.assertTrue(style.style_open(reading(beta=-under))["open"])
        self.assertFalse(style.style_open(reading(beta=style.TILT - 1e-9))["open"], "just under it is not")

    def test_fewer_than_forty_lots_on_any_characteristic_is_unmeasured(self):
        for name in style.CHARACTERISTICS:
            short = reading()
            short["n"][name] = style.MIN_LOTS - 1
            got = style.style_open(short)
            self.assertEqual((got["open"], got["why"], got["tilts"]), (True, style.UNMEASURED, []), name)
            short["n"][name] = style.MIN_LOTS
            self.assertFalse(style.style_open(short)["open"])
        # unmeasured wins over a tilt that was read; the tilt is still named
        mixed = reading(beta=0.6)
        mixed["n"]["size"] = 3
        got = style.style_open(mixed)
        self.assertEqual((got["why"], got["tilts"]), (style.UNMEASURED, [["beta", 1]]))
        self.assertEqual(style.seat_refusal(got), "style-open: unmeasured, beta +")

    def test_it_fails_closed_on_no_reading_and_on_a_malformed_one(self):
        bad = [None, {}, [], "reading", 7, {"lots": 200}, {**reading(), "n": None}, {**reading(), "loadings": []},
               {**reading(), "lots": None}, {**reading(), "lots": True}, {**reading(), "lots": -1},
               {**reading(), "lots": 199.5}]
        for name in style.CHARACTERISTICS:
            for value in (None, float("nan"), float("inf"), "0.1", True, 1.5, -1.5):
                broken = reading()
                broken["loadings"][name] = value
                bad.append(broken)
            for count in (None, -1, 201, "200", 200.0, True):
                broken = reading()
                broken["n"][name] = count
                bad.append(broken)
            missing = reading()
            del missing["loadings"][name]
            bad.append(missing)
        for case in bad:
            got = style.style_open(case)
            self.assertEqual((got["open"], got["why"]), (True, style.UNMEASURED), case)
            self.assertEqual(set(got), set(style.VERDICT_KEYS))
            self.assertEqual(got["rule"], {"tilt": style.TILT, "min_lots": style.MIN_LOTS})
            self.assertTrue(str(style.seat_refusal(got)).startswith("style-open: unmeasured"), case)
        self.assertEqual(style.style_open(style.pooled([]))["why"], style.UNMEASURED, "no run, no reading")

    def test_the_verdict_names_what_it_read(self):
        got = style.style_open(reading(lots=120, mom=-0.4))
        self.assertEqual(got, {"open": True, "why": style.OPEN, "tilts": [["mom", -1]],
                               "loadings": {"size": 0.0, "beta": 0.0, "mom": -0.4, "vol": 0.0}, "lots": 120,
                               "rule": {"tilt": style.TILT, "min_lots": style.MIN_LOTS}})


class ThePooledReading(unittest.TestCase):
    def one(self, lots=50, weight=10.0, total=1.0) -> dict:
        return {"lots": lots, "n": {name: lots for name in style.CHARACTERISTICS},
                "weight": {name: weight for name in style.CHARACTERISTICS},
                "sum": {name: total for name in style.CHARACTERISTICS}}

    def test_several_runs_read_as_one(self):
        got = style.pooled([self.one(50, 10.0, 1.0), self.one(30, 6.0, -3.0), self.one(0, 0.0, 0.0)])
        self.assertEqual(set(got), set(style.POOLED_KEYS))
        self.assertEqual((got["lots"], got["n"]["vol"]), (80, 80))
        for name in style.CHARACTERISTICS:
            self.assertAlmostEqual(got["loadings"][name], (1.0 - 3.0) / 16.0, delta=1e-15, msg="sums over sums")
        empty = style.pooled([self.one(0, 0.0, 0.0)])
        self.assertEqual(empty["loadings"], {name: None for name in style.CHARACTERISTICS}, "no lot carries it")
        self.assertEqual(style.style_open(empty)["why"], style.UNMEASURED)

    def test_the_sums_are_exact_whatever_the_python(self):
        """`math.fsum`: three blocks whose plain left-to-right sum loses the small one."""
        big = self.one(50, 1e16, 1e16)
        small = self.one(50, 1.0, 1.0)
        got = style.pooled([big, small, {**self.one(50, 1e16, -1e16)}])
        self.assertEqual(got["loadings"]["size"], 1.0 / (2e16 + 1.0))

    def test_a_missing_or_malformed_block_makes_the_whole_reading_unread(self):
        good = self.one()
        unread = {"lots": None, "n": {name: None for name in style.CHARACTERISTICS},
                  "loadings": {name: None for name in style.CHARACTERISTICS}}
        bad = [None, {}, "block", {k: v for k, v in good.items() if k != "sum"}, {**good, "lots": -1},
               {**good, "lots": 49}, {**good, "n": {**good["n"], "beta": 51}}, {**good, "n": None},
               {**good, "weight": {**good["weight"], "mom": -1.0}}, {**good, "weight": {**good["weight"], "mom": 0.0}},
               {**good, "sum": {**good["sum"], "vol": float("nan")}}, {**good, "sum": {**good["sum"], "vol": 10.5}},
               {**good, "sum": {**good["sum"], "vol": "1.0"}}, {**good, "n": {**good["n"], "size": True}}]
        for block in bad:
            self.assertEqual(style.pooled([good, block]), unread, block)
        for blocks in (None, [], (), good, "blocks", 3):
            self.assertEqual(style.pooled(blocks), unread, blocks)


class TheSeat(unittest.TestCase):
    """A style-open program takes no live seat on an XS1 pass alone: `seat_refusal` is None for one verdict only."""

    def test_only_a_whole_not_open_verdict_under_these_figures_seats(self):
        clean = style.style_open(reading(size=0.1, vol=-0.2))
        self.assertIsNone(style.seat_refusal(clean))
        self.assertIsNone(style.seat_refusal(json.loads(json.dumps(clean))), "as the swarm's store hands it back")
        self.assertEqual(style.seat_refusal(None), "style-open: unmeasured", "no reading is style-open")
        for missing in style.VERDICT_KEYS:
            self.assertIsNotNone(style.seat_refusal({k: v for k, v in clean.items() if k != missing}), missing)
        for over in ({"open": None}, {"open": 0}, {"open": "False"}, {"open": True}, {"why": style.OPEN},
                     {"why": style.UNMEASURED}, {"tilts": [["size", 1]]}, {"tilts": None}, {"tilts": ["junk"]},
                     {"loadings": None}, {"loadings": {**clean["loadings"], "beta": None}},
                     {"loadings": {**clean["loadings"], "beta": 0.5}}, {"loadings": {**clean["loadings"], "mom": -style.TILT}},
                     {"loadings": {k: v for k, v in clean["loadings"].items() if k != "vol"}},
                     {"lots": style.MIN_LOTS - 1}, {"lots": None}, {"lots": "200"}):
            self.assertIsNotNone(style.seat_refusal({**clean, **over}), over)

    def test_a_verdict_made_under_other_figures_is_refused(self):
        clean = style.style_open(reading())
        for rule in ({"tilt": 0.5, "min_lots": style.MIN_LOTS}, {"tilt": style.TILT, "min_lots": 10},
                     {"tilt": style.TILT}, {}, None, "rule", {"tilt": "0.3333333333333333", "min_lots": style.MIN_LOTS}):
            why = style.seat_refusal({**clean, "rule": rule})
            self.assertIn("other figures", str(why), rule)
        self.assertEqual(style.seat_refusal(clean), None)

    def test_the_words_a_report_prints(self):
        self.assertEqual(style.seat_refusal(style.style_open(reading(mom=0.9))), "style-open: mom +")
        self.assertEqual(style.seat_refusal(style.style_open(reading(size=-0.5, beta=0.5, mom=-0.5, vol=0.5))),
                         "style-open: size -, beta +, mom -, vol +")
        self.assertEqual(style.seat_refusal(style.style_open(None)), "style-open: unmeasured")
        # an open verdict that names no tilt it can read is unmeasured, never a seat
        self.assertEqual(style.seat_refusal({**style.style_open(reading(mom=0.9)), "tilts": []}), "style-open: unmeasured")


if __name__ == "__main__":
    unittest.main()
