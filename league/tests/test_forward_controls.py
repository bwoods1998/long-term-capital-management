"""Release E3, the skill-free controls of the forward record (league/ops/forward_controls.py, the spec's D5): the
counter hash; a group's symbols; the draw against golden values and against a second implementation written from the
definition; its determinism (a longer calendar only adds lots and closes open ones); the cap skip; the minimum hold;
the half-spread each k fills; that the draw reads no price (two synthetic stores whose every price differs give the
same lots); and the cost-free series r0: a one-lot fixture by hand, every control's net return at or below its r0 on
every session, and the mean cost-free excess of 200 controls on a driftless synthetic store within two standard
errors of zero. Every store here is synthetic (league/equity/synth.py) and every figure a rule-level simulation
figure; no market data is read."""

from __future__ import annotations

import ast
import datetime as dt
import hashlib
import inspect
import math
import tempfile
import unittest
from decimal import Decimal

import numpy as np

from league.equity import config, results, screen, synth
from league.equity.store import EquityStore, mint_equity_gate_capability
from league.ops import forward_controls as C
from league.ops import forward_db as F
from league.swarm import elane_train

INDEX = ("SPY", "QQQ", "IWM", "DIA")
#: A universe with every base group in it.
UNIVERSE = ("SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "TLT", "GLD", "AAPL", "MSFT", "NVDA")


def calendar(n: int) -> list[dt.date]:
    """`n` invented consecutive "sessions": the draw reads their order, never their dates."""
    return [dt.date(2030, 1, 1) + dt.timedelta(days=i) for i in range(n)]


def indexed(lots: list[dict], sessions: list[dt.date]) -> list[tuple]:
    """Lots as (lid, symbol, entry index, entry_at, exit index | None)."""
    where = {day.isoformat(): i for i, day in enumerate(sessions)}
    return [(lot["lid"], lot["symbol"], where[lot["entry_day"]], lot["entry_at"],
             None if lot["exit_day"] is None else where[lot["exit_day"]]) for lot in lots]


def by_definition(group: str, n: int, symbols: list[str], sessions: int) -> list[tuple]:
    """D5's draw written a second time, from the definition: session by session, slot by slot, every draw from the
    counter hash computed here. Rows as `indexed` gives them."""
    def draw(i: int, j: int) -> float:
        raw = hashlib.sha256(f"fwd-control-1|{group}|{n}|{i}|{j}".encode()).digest()[:8]
        return int.from_bytes(raw, "big") / 2 ** 64

    f = (0.10, 0.25, 0.50, 0.75, 0.95)[n // 10]
    p = min(1.0, f / (10.5 * (1 - f)))
    book: dict[int, dict] = {}                    # slot -> its lot
    rows, made = [], {k: 0 for k in range(4)}
    for i in range(sessions - 1):                 # the last session's entry day does not exist yet
        for k in range(4):
            lot = book.get(k)
            if lot is not None and lot["x"] > i:
                continue
            book.pop(k, None)
            if draw(i, 4 * k) >= p:
                continue
            sym = symbols[int(draw(i, 4 * k + 1) * len(symbols))]
            entry_at = "open" if draw(i, 4 * k + 2) < 0.5 else "close"
            hold = 1 + int(draw(i, 4 * k + 3) * 20)
            cap = config.POSITION_SHARE[config.UNIVERSE[sym]]
            omega = min(Decimal("0.25"), cap)
            in_symbol = sum((Decimal(str(other["omega"])) for slot, other in book.items()
                             if slot != k and other["sym"] == sym and other["x"] > i), Decimal(0))
            if omega + in_symbol > cap:
                continue
            made[k] += 1
            book[k] = {"sym": sym, "omega": float(omega), "x": i + 1 + hold}
            rows.append((1000 * k + made[k], sym, i + 1, entry_at, i + 1 + hold if i + 1 + hold < sessions else None))
    return sorted(rows)


class TheCounterHash(unittest.TestCase):
    def test_it_is_the_formula(self):
        for args in (("index", 0, 0, 0), ("stocks", 49, 1234, 15), ("sectors", 7, 3, 9), ("defensive", 20, 0, 1)):
            group, n, i, j = args
            by_hand = int.from_bytes(hashlib.sha256(f"fwd-control-1|{group}|{n}|{i}|{j}".encode()).digest()[:8],
                                     "big") / 2 ** 64
            self.assertEqual(C.u(*args), by_hand)
            self.assertTrue(0.0 <= C.u(*args) < 1.0)

    def test_golden_values(self):
        # Pinned: a change to the draw is a captain's release (it opens other controls), never a refactor.
        self.assertEqual(C.VERSION, "fwd-control-1")
        self.assertEqual([C.u("index", 0, 0, j) for j in range(4)],
                         [0.964532343757863, 0.0035931190789108046, 0.9104423900698015, 0.06485901342087466])
        self.assertEqual(C.u("stocks", 49, 1234, 15), 0.868165147230714)

    def test_it_is_spread_over_the_unit_interval(self):
        draws = [C.u("index", n, i, j) for n in range(5) for i in range(200) for j in range(16)]
        self.assertAlmostEqual(math.fsum(draws) / len(draws), 0.5, delta=0.01)
        tenths = [sum(1 for x in draws if k / 10 <= x < (k + 1) / 10) / len(draws) for k in range(10)]
        self.assertTrue(all(abs(share - 0.1) < 0.01 for share in tenths), tenths)


class TheGroups(unittest.TestCase):
    def test_a_groups_symbols_in_the_universes_order(self):
        self.assertEqual(C.group_symbols("index", list(reversed(UNIVERSE))), INDEX)
        self.assertEqual(C.group_symbols("sectors", UNIVERSE), ("XLE", "XLF", "XLK"))
        self.assertEqual(C.group_symbols("defensive", UNIVERSE), ("TLT", "GLD"))
        self.assertEqual(C.group_symbols("stocks", UNIVERSE), ("AAPL", "MSFT", "NVDA"))
        self.assertEqual(C.group_symbols("index", ["spy", " qqq "]), ("SPY", "QQQ"))

    def test_a_group_with_no_symbol_in_the_universe_has_none(self):
        self.assertEqual(C.group_symbols("stocks", INDEX), ())
        self.assertEqual(C.group_symbols("sectors", []), ())
        self.assertEqual(C.group_symbols("index", "SPY"), (), "a universe is a list of symbols")
        for group in ("none", "index+sectors", "", "Index"):
            self.assertEqual(C.group_symbols(group, UNIVERSE), (), group)

    def test_the_groups_split_the_whole_universe_by_the_train_maps_rule(self):
        whole = list(config.UNIVERSE)
        parts = {group: C.group_symbols(group, whole) for group in elane_train.GROUPS}
        self.assertEqual(sorted(sym for part in parts.values() for sym in part), sorted(whole))
        for group, part in parts.items():
            self.assertTrue(part, group)
            for sym in part:
                self.assertEqual(elane_train.symbols_group([sym]), group)
        self.assertEqual(parts["index"], config.INDEX_ETFS)
        self.assertEqual(set(parts["defensive"]), {"TLT", "GLD"})
        self.assertTrue(all(sym.startswith("XL") and config.UNIVERSE[sym] == config.ETF for sym in parts["sectors"]))
        self.assertTrue(all(config.UNIVERSE[sym] == config.STOCK for sym in parts["stocks"]))


class TheSpec(unittest.TestCase):
    def test_its_fields_and_the_exposure_grid(self):
        self.assertEqual(C.spec("index", 0, INDEX), {"control": "fwd-control-1", "group": "index", "n": 0, "f": 0.10,
                                                     "symbols": list(INDEX)})
        self.assertEqual([C.spec("index", n, INDEX)["f"] for n in (0, 9, 10, 19, 20, 29, 30, 39, 40, 49)],
                         [0.10, 0.10, 0.25, 0.25, 0.50, 0.50, 0.75, 0.75, 0.95, 0.95])
        self.assertEqual((C.SLOTS, C.F_GRID, C.MEAN_HOLD, C.HOLD), (4, (0.10, 0.25, 0.50, 0.75, 0.95), 10.5, (1, 20)))
        self.assertEqual(C.MEAN_HOLD, math.fsum(range(C.HOLD[0], C.HOLD[1] + 1)) / 20)

    def test_its_registry_code_is_canonical(self):
        code = results.canonical(C.spec("index", 12, INDEX))
        self.assertEqual(code, '{"control":"fwd-control-1","f":0.25,"group":"index","n":12,'
                               '"symbols":["SPY","QQQ","IWM","DIA"]}')
        self.assertEqual(code, results.canonical(C.spec("index", 12, tuple(INDEX))))

    def test_what_is_refused(self):
        for n in (-1, 50, 1.0, True, "3", None):
            with self.assertRaises(ValueError, msg=n):
                C.spec("index", n, INDEX)
        for symbols in ((), [], "SPY"):
            with self.assertRaises(ValueError):
                C.spec("index", 0, symbols)
        good = C.spec("index", 0, INDEX)
        for bad in ({**good, "control": "fwd-control-2"}, {**good, "n": 50}, {**good, "symbols": []},
                    {**good, "symbols": ["SPY", "ZZZZ"]}):
            with self.assertRaises(ValueError):
                C.control_lots(bad, calendar(5))
        for k in (-0.5, float("nan")):
            with self.assertRaises(ValueError):
                C.control_lots(good, calendar(5), k=k)


class TheDraw(unittest.TestCase):
    def test_golden_values(self):
        sessions = calendar(26)
        self.assertEqual(indexed(C.control_lots(C.spec("index", 40, INDEX), sessions), sessions), [
            (1, "QQQ", 1, "open", 7), (2, "IWM", 8, "close", 16), (3, "IWM", 17, "open", None),
            (1001, "IWM", 1, "close", 2), (1002, "SPY", 3, "open", 21), (1003, "IWM", 23, "close", None),
            (2001, "IWM", 1, "open", 4), (2002, "IWM", 5, "open", 22), (2003, "SPY", 23, "open", None),
            (3001, "SPY", 1, "close", 6), (3002, "DIA", 7, "open", 11), (3003, "SPY", 12, "close", 15),
            (3004, "DIA", 16, "open", None)])
        self.assertEqual(indexed(C.control_lots(C.spec("stocks", 25, ["AAPL", "MSFT", "NVDA"]), sessions), sessions),
                         [(1, "NVDA", 6, "open", 13), (2, "MSFT", 14, "close", None), (1001, "AAPL", 7, "open", None)])
        self.assertEqual(C.control_lots(C.spec("index", 3, INDEX), sessions), [], "a quiet control on a short calendar")

    def test_a_lot_row(self):
        sessions = calendar(26)
        first = C.control_lots(C.spec("index", 40, INDEX), sessions)[0]
        self.assertEqual(first, {"lid": 1, "symbol": "QQQ", "class": "etf", "weight": 0.25, "entry_day": "2030-01-02",
                                 "entry_at": "open", "exit_day": "2030-01-08", "exit_at": "open", "hs": None})
        stock = C.control_lots(C.spec("stocks", 25, ["AAPL", "MSFT", "NVDA"]), sessions)[0]
        self.assertEqual((stock["class"], stock["weight"]), ("stock", 0.20))

    def test_it_is_the_definition_for_every_control_of_every_group(self):
        sessions = calendar(140)
        for group in elane_train.GROUPS:
            symbols = list(C.group_symbols(group, UNIVERSE))
            for n in range(50):
                got = indexed(C.control_lots(C.spec(group, n, symbols), sessions), sessions)
                self.assertEqual(got, by_definition(group, n, symbols, len(sessions)), (group, n))

    def test_the_same_lots_every_time_and_a_longer_calendar_only_adds(self):
        long = calendar(120)
        for group, n in (("index", 21), ("stocks", 44), ("defensive", 35)):
            spec = C.spec(group, n, C.group_symbols(group, UNIVERSE))
            whole = C.control_lots(spec, long)
            self.assertEqual(whole, C.control_lots(dict(spec), list(long)))
            for cut in (1, 2, 30, 77, 119):
                short = long[:cut]
                last = short[-1].isoformat()
                # What tonight's shorter calendar holds of the whole: the lots entered by its last session, one that
                # exits after it still open.
                expect = [{**lot, "exit_day": lot["exit_day"] if lot["exit_day"] and lot["exit_day"] <= last else None}
                          for lot in whole if lot["entry_day"] <= last]
                self.assertEqual(C.control_lots(spec, short), expect, (group, n, cut))
        self.assertEqual(C.control_lots(C.spec("index", 40, INDEX), []), [])
        self.assertEqual(C.control_lots(C.spec("index", 40, INDEX), calendar(1)), [], "no entry day exists yet")

    def test_iso_days_are_sessions_too(self):
        sessions = calendar(40)
        spec = C.spec("index", 30, INDEX)
        self.assertEqual(C.control_lots(spec, [d.isoformat() for d in sessions]), C.control_lots(spec, sessions))

    def test_the_cap_skip(self):
        sessions = calendar(200)
        # One stock: its lot is the whole class cap (20%), so a second slot's entry in it is skipped.
        one = indexed(C.control_lots(C.spec("stocks", 40, ["AAPL"]), sessions), sessions)
        self.assertTrue(one)
        self.assertEqual([row for row in one if row[2] == 1], [(1, "AAPL", 1, one[0][3], one[0][4])],
                         "the first decision enters slot 0 and skips the three slots after it")
        # One ETF: two quarter lots fill its 50%; the third and the fourth slot stay flat that session.
        etf = indexed(C.control_lots(C.spec("index", 40, ["SPY"]), sessions), sessions)
        self.assertEqual([row[0] for row in etf if row[2] == 1], [1, 1001])
        for symbols, rows in ((["AAPL"], one), (["SPY"], etf)):
            cap = float(config.POSITION_SHARE[config.UNIVERSE[symbols[0]]])
            omega = min(0.25, cap)
            for t in range(len(sessions)):
                held = sum(1 for row in rows if row[2] <= t and (row[4] is None or row[4] > t))
                self.assertLessEqual(held * omega, cap + 1e-12, (symbols, t))

    def test_no_control_ever_holds_more_than_its_class_cap_or_its_slots(self):
        sessions = calendar(300)
        for group in elane_train.GROUPS:
            symbols = list(C.group_symbols(group, UNIVERSE))
            for n in (0, 17, 29, 38, 49):
                lots = C.control_lots(C.spec(group, n, symbols), sessions)
                rows = indexed(lots, sessions)
                weight = {lot["lid"]: lot["weight"] for lot in lots}
                for t in range(len(sessions)):
                    live = [row for row in rows if row[2] <= t and (row[4] is None or row[4] > t)]
                    self.assertLessEqual(len(live), C.SLOTS)
                    self.assertEqual(len({row[0] // 1000 for row in live}), len(live), "one lot a slot")
                    for sym in symbols:
                        held = math.fsum(weight[row[0]] for row in live if row[1] == sym)
                        self.assertLessEqual(held, float(config.POSITION_SHARE[config.UNIVERSE[sym]]) + 1e-12)

    def test_the_minimum_hold_and_the_fill_points(self):
        sessions = calendar(400)
        holds, points = set(), set()
        for group in elane_train.GROUPS:
            symbols = list(C.group_symbols(group, UNIVERSE))
            for n in (5, 25, 45):
                for lid, sym, e, entry_at, x in indexed(C.control_lots(C.spec(group, n, symbols), sessions), sessions):
                    self.assertGreaterEqual(e, 1, "no lot before first_day: sessions[0] is the first decision's close")
                    points.add(entry_at)
                    if x is not None:
                        self.assertTrue(config.may_sell(e, x), "a lot never sells in the session it was bought")
                        self.assertTrue(C.HOLD[0] <= x - e <= C.HOLD[1])
                        holds.add(x - e)
        self.assertEqual(points, {"open", "close"})
        self.assertEqual(holds, set(range(1, 21)), "every hold of 1..20 sessions is drawn")
        self.assertTrue(all(lot["exit_at"] == "open" for lot in C.control_lots(C.spec("index", 45, INDEX), sessions)))
        self.assertLessEqual(C.HOLD[1], 20, "the registry's needs give a control max_hold_sessions 20")

    def test_the_half_spread_each_k_fills(self):
        sessions = calendar(120)
        spec = C.spec("defensive", 33, ["TLT", "GLD"])
        base, stress, free = (C.control_lots(spec, sessions, k=k) for k in (1.0, 1.5, 0.0))
        self.assertTrue(base)
        strip = lambda lots: [{k: v for k, v in lot.items() if k != "hs"} for lot in lots]  # noqa: E731
        self.assertEqual(strip(base), strip(stress))
        self.assertEqual(strip(base), strip(free))
        self.assertTrue(all(lot["hs"] is None for lot in base), "the screen's own half-spread")
        self.assertTrue(all(lot["hs"] == 0.0 for lot in free))
        for lot in stress:
            self.assertEqual(lot["hs"], config.K_STRESS * config.half_spread(lot["symbol"]))
        self.assertEqual(C.control_lots(spec, sessions), base, "k defaults to 1.0")

    def test_the_exposure_grid_spans_the_feasible_range(self):
        # A rule-level simulation figure: the share of the sleeve ten controls of each grid step hold, on average.
        sessions = calendar(2500)
        means = []
        for band in range(5):
            held = 0.0
            for n in range(10 * band, 10 * band + 10):
                for _, _, e, _, x in indexed(lots := C.control_lots(C.spec("index", n, INDEX), sessions), sessions):
                    held += 0.25 * ((len(sessions) if x is None else x) - e)
                self.assertTrue(all(lot["weight"] == 0.25 for lot in lots))
            means.append(held / (10 * (len(sessions) - 1)))
        self.assertEqual(means, sorted(means))
        for mean, f in zip(means, C.F_GRID):
            self.assertAlmostEqual(mean, f, delta=0.06, msg=f"the grid step {f}")


class SkillFree(unittest.TestCase):
    """The lot list is a pure function of (group, n, symbols, sessions): the draw reads no bar, price, event or ctx."""

    def test_the_draw_takes_no_price(self):
        self.assertEqual(list(inspect.signature(C.control_lots).parameters), ["spec", "sessions", "k"])
        # Nothing it names can hold a price: of the lane's constants it reads the class, the cap and the half-spread.
        trees = [ast.parse(inspect.getsource(fn)) for fn in (C.control_lots, C.u)]
        names = {node.id for tree in trees for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attrs = {node.attr for tree in trees for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertFalse((names | attrs) & {"bars", "adj", "raw", "prices", "screen", "series", "store", "EquityStore",
                                            "ctx", "numpy", "np", "open", "read", "execute"}, sorted(names | attrs))
        self.assertEqual({node.attr for tree in trees for node in ast.walk(tree) if isinstance(node, ast.Attribute)
                          and isinstance(node.value, ast.Name) and node.value.id == "config"},
                         {"class_of", "POSITION_SHARE", "half_spread"})

    def test_fuzzing_every_price_of_a_store_leaves_every_controls_lots_identical(self):
        lots = []
        with tempfile.TemporaryDirectory() as tmp:
            for i, (seed, drift, vol) in enumerate(((7, 0.0, 0.18), (8, 0.30, 0.45), (9, -0.40, 0.05))):
                root = synth.synthetic_store(f"{tmp}/store{i}", symbols=UNIVERSE, start=dt.date(2026, 9, 1),
                                             end=dt.date(2027, 3, 31), seed=seed, drift=drift, vol=vol, gate=True)
                store = EquityStore(root, gate=mint_equity_gate_capability(root, "an invented reason"))
                close = F.first_close(0.0)
                made = {}
                for group in elane_train.GROUPS:
                    symbols = C.group_symbols(group, UNIVERSE)
                    bars = store.bars(symbols, "forward", history=1, start=F.first_day(close))
                    sessions = [bars.day(t) for t in range(bars.n)]
                    self.assertEqual((sessions[0], sessions[1], bars.first), (close, F.t0(), 1))
                    for n in range(50):
                        made[group, n] = (C.control_lots(C.spec(group, n, symbols), sessions),
                                          float(bars.adj[symbols[0]][5, 3]))
                lots.append(made)
        a, b, c = lots
        self.assertEqual(len(a), 200)
        for key in a:
            self.assertEqual(a[key][0], b[key][0], key)
            self.assertEqual(a[key][0], c[key][0], key)
            self.assertNotEqual(a[key][1], b[key][1], "the stores do differ in their prices")
        self.assertGreater(sum(len(v[0]) for v in a.values()), 2000)


class TheCostFreeSeries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = synth.synthetic_store(cls.tmp.name + "/store", symbols=UNIVERSE, start=dt.date(2026, 9, 1),
                                     end=dt.date(2028, 9, 29), seed=7, drift=0.0, gate=True)
        cls.store = EquityStore(root, gate=mint_equity_gate_capability(root, "an invented reason"))
        cls.first_day = F.first_day(F.first_close(0.0))
        cls.capital = config.SLEEVE_USD

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def slice(self, symbols):
        bars = self.store.bars(symbols, "forward", history=1, start=self.first_day)
        return bars, [bars.day(t) for t in range(bars.n)]

    def test_one_open_lot_by_hand(self):
        bars, sessions = self.slice(["SPY"])
        o, c = bars.adj["SPY"][:, 0], bars.adj["SPY"][:, 3]
        e, x = 3, 7
        lot = {"lid": 1, "symbol": "SPY", "class": "etf", "weight": 0.25, "entry_day": sessions[e].isoformat(),
               "entry_at": "open", "exit_day": sessions[x].isoformat(), "exit_at": "open", "hs": 0.0}
        r0 = C.cost_free([lot], bars, capital=self.capital)
        self.assertEqual(len(r0), bars.n - bars.first)
        by_hand = np.zeros(bars.n)
        by_hand[e] = 0.25 * (c[e] / o[e] - 1.0)
        for t in range(e + 1, x):
            by_hand[t] = 0.25 * (c[t] / c[t - 1] - 1.0)
        by_hand[x] = 0.25 * (o[x] / c[x - 1] - 1.0)
        np.testing.assert_allclose(r0, by_hand[bars.first:], rtol=0, atol=1e-15)
        # Its whole return is the price ratio of its fills: bought at the open of e, sold at the open of x, no cost.
        self.assertAlmostEqual(float(np.prod(1.0 + r0 / 0.25)) - 1.0, o[x] / o[e] - 1.0, places=12)
        # The screen's own series at hs 0.0 still pays the SEC and TAF fees, each rounded up to a cent, on the exit.
        net0 = screen.series([lot], bars, universe=["SPY"], capital=self.capital).r
        fee = float(config.sell_fees(Decimal("0.25") * self.capital,
                                     Decimal(str(0.25 * float(self.capital) / o[e])))) / float(self.capital)
        self.assertGreaterEqual(fee, 0.02 / float(self.capital), "two fees of at least a cent")
        self.assertAlmostEqual(float(r0[x - bars.first] - net0[x - bars.first]), fee, places=15)
        self.assertEqual([t for t in range(len(r0)) if r0[t] != net0[t]], [x - bars.first])

    def test_one_close_entered_lot_by_hand(self):
        bars, sessions = self.slice(["QQQ"])
        o, c = bars.adj["QQQ"][:, 0], bars.adj["QQQ"][:, 3]
        e, x = 2, 3
        lot = {"lid": 1, "symbol": "QQQ", "class": "etf", "weight": 0.25, "entry_day": sessions[e].isoformat(),
               "entry_at": "close", "exit_day": sessions[x].isoformat(), "exit_at": "open", "hs": 0.0}
        r0 = C.cost_free([lot], bars, capital=self.capital)
        by_hand = np.zeros(bars.n)
        by_hand[x] = 0.25 * (o[x] / c[e] - 1.0)       # bought at the close of e at no cost: nothing earned that day
        np.testing.assert_allclose(r0, by_hand[bars.first:], rtol=0, atol=1e-15)

    def test_the_fee_added_back_is_read_at_the_lots_own_entry_price(self):
        # On a $250 lot both fees round up to a cent whatever the price. On a sleeve large enough for the per-share fee
        # to move with the share count, a fee read at the other fill point would leave a residue in r0.
        bars, sessions = self.slice(["SPY"])
        o, c = bars.adj["SPY"][:, 0], bars.adj["SPY"][:, 3]
        e = next(t for t in range(bars.first + 1, bars.n - 3) if abs(c[t] / o[t] - 1.0) > 0.005)
        x = e + 2
        capital = Decimal(int(4.0 / float(config.TAF_PER_SHARE) / 0.25 * o[e]))     # a TAF of about four dollars
        fees = [config.sell_fees(Decimal("0.25") * capital, Decimal(str(0.25 * float(capital) / price)))
                for price in (o[e], c[e])]
        self.assertNotEqual(fees[0], fees[1], "the fixture: the sale's fee moves with the entry price")
        for entry_at in ("open", "close"):
            lot = {"lid": 1, "symbol": "SPY", "class": "etf", "weight": 0.25, "entry_day": sessions[e].isoformat(),
                   "entry_at": entry_at, "exit_day": sessions[x].isoformat(), "exit_at": "open", "hs": 0.0}
            by_hand = np.zeros(bars.n)
            by_hand[e] = 0.25 * (c[e] / o[e] - 1.0) if entry_at == "open" else 0.0
            by_hand[e + 1] = 0.25 * (c[e + 1] / c[e] - 1.0)
            by_hand[x] = 0.25 * (o[x] / c[x - 1] - 1.0)
            r0 = C.cost_free([lot], bars, capital=capital)
            np.testing.assert_allclose(r0, by_hand[bars.first:], rtol=0, atol=1e-13, err_msg=entry_at)
            net0 = screen.series([lot], bars, universe=["SPY"], capital=capital).r
            self.assertAlmostEqual(float(r0[x - bars.first] - net0[x - bars.first]),
                                   float(fees[0 if entry_at == "open" else 1]) / float(capital), places=13)

    def test_an_open_lot_pays_no_fee_yet(self):
        bars, sessions = self.slice(["SPY"])
        lot = {"lid": 1, "symbol": "SPY", "class": "etf", "weight": 0.25, "entry_day": sessions[4].isoformat(),
               "entry_at": "open", "exit_day": None, "exit_at": "open", "hs": 0.0}
        np.testing.assert_array_equal(C.cost_free([lot], bars, capital=self.capital),
                                      screen.series([lot], bars, universe=["SPY"], capital=self.capital).r)
        np.testing.assert_array_equal(C.cost_free([], bars, capital=self.capital), np.zeros(bars.n - bars.first))

    def test_only_a_cost_free_draw_is_taken(self):
        bars, sessions = self.slice(list(INDEX))
        spec = C.spec("index", 30, INDEX)
        for k in (1.0, 1.5):
            with self.assertRaises(ValueError):
                C.cost_free(C.control_lots(spec, sessions, k=k), bars, capital=self.capital)

    def test_costs_only_subtract_and_two_hundred_controls_have_no_skill(self):
        mean_x0, mean_x, turnover = [], [], 0
        for group in elane_train.GROUPS:
            symbols = C.group_symbols(group, UNIVERSE)
            bars, sessions = self.slice(symbols)
            self.assertGreater(len(sessions), 450)
            for n in range(50):
                spec = C.spec(group, n, symbols)
                lots, lots15, lots0 = (C.control_lots(spec, sessions, k=k) for k in (1.0, 1.5, 0.0))
                net = screen.series(lots, bars, universe=list(symbols), capital=self.capital)
                net15 = screen.series(lots15, bars, universe=list(symbols), capital=self.capital)
                r0 = C.cost_free(lots0, bars, capital=self.capital)
                self.assertTrue((net.r <= r0 + 1e-12).all(), (group, n))
                self.assertTrue((net15.r <= net.r + 1e-12).all(), (group, n))
                turnover += len(lots)
                mean_x0.append(r0 - net.w * net.b)
                mean_x.append(net.r - net.w * net.b)
        self.assertEqual(len(mean_x0), 200)
        self.assertGreater(turnover, 5000)
        # The 200 controls share one market, so the standard error is that of the DAILY mean across them.
        daily0 = np.mean(np.array(mean_x0), axis=0)
        daily = np.mean(np.array(mean_x), axis=0)
        sessions_n = len(daily0)
        mean0 = math.fsum(daily0) / sessions_n
        se0 = math.sqrt(math.fsum((x - mean0) ** 2 for x in daily0) / (sessions_n - 1)) / math.sqrt(sessions_n)
        self.assertLess(abs(mean0), 2.0 * se0, "the cost-free excess of the controls is no different from zero")
        # Net of their own half-spreads and fees the same controls read below zero, by their turnover, not their skill:
        # why every comparison with the controls reads x0.
        mean = math.fsum(daily) / sessions_n
        self.assertLess(mean, mean0)
        self.assertLess(mean, -2.0 * se0)


if __name__ == "__main__":
    unittest.main()
