"""Release E3, THE HIDDEN YEAR (league/swarm/elane_folds.py; D14): the assignment at birth, the seen spans, and seal T4,
`NoSeenRunHasAHiddenSession`: for each of the seven work years the seen spans cover exactly the other six years'
sessions and no reserve session; on E1's own runner (its engine in this process, over its synthetic store) no seen
run's result holds a day, a lot, a trade, an action or a by-year key of the hidden year; E2's `outside_years` refuses a
seen result carrying one; E2's bar reads six years; and the hidden run's result is handed to the out-of-fold arithmetic
and to nothing else. `TheListingRule`: a family whose symbol is listed inside the Train years is given only a hidden
year whose every stretch E1's engine can run. Every family, program, price and number here is invented."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.equity.store import nyse_sessions
from league.swarm import elane, elane_effects, elane_folds, elane_memory, elane_train
from league.tests import elane_e2_fakes as fx
from league.tests import elane_e3_fakes as e3

CELL = ("beta", "overnight", "index")
_DAY = re.compile(r"^(\d{4})-\d{2}-\d{2}")
_YEAR = re.compile(r"^\d{4}$")


def sessions_of(spans) -> list[dt.date]:
    return [d for first, last in spans for d, _ in nyse_sessions(first, last)]


def years_named(value, found: set | None = None) -> set[int]:
    """Every year a result names anywhere: an ISO day in a string (a row's day, a start, an end) and a four-digit
    mapping key (a by-year row), at any depth."""
    found = set() if found is None else found
    if isinstance(value, dict):
        for key, inner in value.items():
            if isinstance(key, str) and _YEAR.match(key):
                found.add(int(key))
            years_named(inner, found)
    elif isinstance(value, (list, tuple)):
        for inner in value:
            years_named(inner, found)
    elif isinstance(value, str):
        hit = _DAY.match(value)
        if hit:
            found.add(int(hit.group(1)))
    return found


class TheAssignment(unittest.TestCase):
    def setUp(self):
        self.clock = fx.Clock()
        self.store = fx.new_store(self, self.clock)
        self.settings = e3.settings()

    def born(self, slug: str, **kw) -> int | None:
        """One birth as `EquityPass.birth` stamps it: `birth_fields` into the spec, then the family."""
        symbols = kw.pop("symbols", ("SPY",))
        lane, agenda = kw.pop("lane", "beta"), kw.pop("agenda", "overnight")
        fields = elane_folds.birth_fields(self.store, kw.pop("settings", self.settings), lane=lane, agenda=agenda,
                                          symbols=symbols)
        e3.hidden_family(self.store, slug, fields["hidden_year"], lane=lane, agenda=agenda, symbols=symbols,
                         mechanism=f"Invented idea {slug}: holders are paid for overnight risk.")
        return fields["hidden_year"]

    def test_the_work_years_are_e2s_train_years_and_never_the_reserve(self):
        self.assertEqual(elane_folds.WORK_YEARS, elane_train.TRAIN_YEARS)
        self.assertEqual(elane_folds.WORK_YEARS, (2016, 2017, 2018, 2019, 2022, 2023, 2024))
        self.assertEqual(elane_folds.RESERVE_YEARS, elane_train.RESERVE_YEARS)
        self.assertFalse(set(elane_folds.WORK_YEARS) & {2020, 2021})

    def test_the_cell_hash_is_the_pinned_formula(self):
        literal = int(hashlib.sha256(b"fold-1|beta/overnight/index").hexdigest()[:8], 16)
        self.assertEqual(elane_folds.cell_hash(CELL), literal)
        self.assertEqual(literal, 765104902, "a rule's constant, never a market figure")
        self.assertEqual(elane_folds.cell_hash(list(CELL)), literal)
        self.assertNotEqual(elane_folds.cell_hash(("equity", "overnight", "index")), literal)

    def test_a_cells_seven_births_take_the_seven_years_and_the_rotation_goes_round(self):
        first = elane_folds.WORK_YEARS[elane_folds.cell_hash(CELL) % 7]
        self.assertEqual(elane_folds.assign(self.store, CELL), first, "k_c is 0 in an empty cell")
        years = [self.born(f"b-{i}") for i in range(14)]
        self.assertEqual(years[0], first)
        self.assertEqual(sorted(years[:7]), sorted(elane_folds.WORK_YEARS), "seven births, the seven years")
        self.assertEqual(years[7:], years[:7], "the eighth birth takes the first's year again")
        start = elane_folds.WORK_YEARS.index(first)
        self.assertEqual(years[:7], [elane_folds.WORK_YEARS[(start + i) % 7] for i in range(7)])
        self.assertFalse(set(years) & set(elane_folds.RESERVE_YEARS))

    def test_each_cell_rotates_on_its_own_and_only_hidden_year_families_count(self):
        other = elane_train.cell_of("equity", "reversal", ("XLK",))
        self.assertEqual(other, ("equity", "reversal", "sectors"))
        self.born("beta-0")
        self.born("beta-1")
        self.assertEqual(self.born("eq-0", lane="equity", agenda="reversal", symbols=("XLK",)),
                         elane_folds.WORK_YEARS[elane_folds.cell_hash(other) % 7], "another cell starts at its own hash")
        # A family of the cell born with no hidden year (before E3, or with the mode off) is not counted.
        before = elane_folds.assign(self.store, CELL)
        e3.hidden_family(self.store, "old", None)
        self.born("off", settings=e3.settings("off"))
        self.assertEqual(elane_folds.assign(self.store, CELL), before)
        # A retired one is: the year it took stays taken.
        fam = e3.hidden_family(self.store, "gone", before)
        self.store.retire(fam["id"], "an invented retirement")
        self.assertEqual(elane_folds.assign(self.store, CELL),
                         elane_folds.WORK_YEARS[(elane_folds.WORK_YEARS.index(before) + 1) % 7])

    def test_no_cell_is_ever_assigned_a_reserve_year(self):
        for lane in ("beta", "equity"):
            for agenda in elane_train.AGENDA:
                for symbols in (("SPY",), ("XLK",), ("TLT",), ("AAPL",), ("SPY", "XLK", "TLT")):
                    year = elane_folds.assign(self.store, elane_train.cell_of(lane, agenda, symbols))
                    self.assertIn(year, elane_folds.WORK_YEARS)

    def test_birth_fields_with_the_mode_off_or_unreadable(self):
        want = {"hidden_year": None, "gid": "g0", "expected_oof": None}
        for settings in (e3.settings("off"), {}, None, {"elane": None}, {"elane": {"memory": "record"}},
                         {"elane": {"memory": {"mode": "on"}}}, {"elane": {"memory": {"mode": ["record"]}}}):
            self.assertEqual(elane_folds.mode(settings), "off", settings)
            self.assertEqual(elane_folds.birth_fields(self.store, settings, lane="beta", agenda="overnight",
                                                      symbols=("SPY",)), want, settings)
        self.assertEqual(want, elane_folds.FALLBACK)
        self.assertEqual(elane_folds.mode(self.settings), "record")
        got = elane_folds.birth_fields(self.store, self.settings, lane="beta", agenda="overnight", symbols=("SPY",))
        self.assertEqual(got, {"hidden_year": elane_folds.assign(self.store, CELL), "gid": elane_folds.GID0,
                               "expected_oof": None})

    def test_the_reserved_forecast_is_kept_only_as_a_finite_number_in_range(self):
        def kept(value):
            return elane_folds.birth_fields(self.store, self.settings, lane="beta", agenda="overnight", symbols=("SPY",),
                                            expected_oof=value)["expected_oof"]
        for value in (0.25, -1, 1, 0, -0.999):
            self.assertEqual(kept(value), float(value))
        for value in (1.5, -1.01, float("nan"), float("inf"), "0.2", True, None, [0.1], {"x": 1}):
            self.assertIsNone(kept(value), repr(value))

    def test_a_familys_hidden_year_is_its_specs_and_never_raises(self):
        self.assertEqual(elane_folds.hidden_year({"spec": {"hidden_year": 2018}}), 2018)
        self.assertEqual(elane_folds.hidden_year(e3.hidden_family(self.store, "has", 2023)), 2023)
        self.assertIsNone(elane_folds.hidden_year(e3.hidden_family(self.store, "none", None)))

        class Broken(dict):
            def get(self, *a, **k):
                raise RuntimeError("an unreadable family")
        for fam in (None, {}, {"spec": None}, {"spec": "{}"}, {"spec": {"hidden_year": "2018"}}, [], "fam", Broken(),
                    {"spec": {"hidden_year": 2018.0}}, {"spec": {"hidden_year": True}}, {"spec": {"hidden_year": 2020}},
                    {"spec": {"hidden_year": 2021}}, {"spec": {"hidden_year": 2025}}, {"spec": {"hidden_year": [2018]}},
                    {"spec": Broken()}):
            self.assertIsNone(elane_folds.hidden_year(fam), repr(fam))

    def test_the_brief_note_names_no_year(self):
        self.assertNotRegex(elane_folds.BRIEF_NOTE, r"\d{4}")
        self.assertIn("held out", elane_folds.BRIEF_NOTE)


class TheSeenSpans(unittest.TestCase):
    def test_no_hidden_year_reads_the_train_spans(self):
        self.assertEqual(elane_folds.seen_spans(None), elane_train.TRAIN_SPANS)
        self.assertIsInstance(elane_folds.seen_spans(None), tuple)

    def test_the_cut_is_as_pinned(self):
        d = dt.date
        self.assertEqual(elane_folds.seen_spans(2016), ((d(2017, 1, 1), d(2019, 12, 31)), (d(2022, 1, 3), d(2024, 12, 31))))
        self.assertEqual(elane_folds.seen_spans(2018), ((d(2016, 1, 4), d(2017, 12, 31)), (d(2019, 1, 1), d(2019, 12, 31)),
                                                        (d(2022, 1, 3), d(2024, 12, 31))))
        self.assertEqual(elane_folds.seen_spans(2019), ((d(2016, 1, 4), d(2018, 12, 31)), (d(2022, 1, 3), d(2024, 12, 31))))
        self.assertEqual(elane_folds.seen_spans(2022), ((d(2016, 1, 4), d(2019, 12, 31)), (d(2023, 1, 1), d(2024, 12, 31))))
        self.assertEqual(elane_folds.seen_spans(2023), ((d(2016, 1, 4), d(2019, 12, 31)), (d(2022, 1, 3), d(2022, 12, 31)),
                                                        (d(2024, 1, 1), d(2024, 12, 31))))
        self.assertEqual(elane_folds.seen_spans(2024), ((d(2016, 1, 4), d(2019, 12, 31)), (d(2022, 1, 3), d(2023, 12, 31))))
        self.assertEqual(elane_folds.hidden_span(2018), (d(2018, 1, 1), d(2018, 12, 31)))

    def test_the_seen_spans_are_the_other_six_years_sessions_and_the_hidden_span_the_years_own(self):
        train = sessions_of(elane_train.TRAIN_SPANS)
        for year in elane_folds.WORK_YEARS:
            spans = elane_folds.seen_spans(year)
            self.assertIn(len(spans), (2, 3), year)
            self.assertTrue(all(a <= b for a, b in spans) and all(x[1] < y[0] for x, y in zip(spans, spans[1:])), year)
            seen = sessions_of(spans)
            self.assertEqual(seen, [d for d in train if d.year != year], f"{year}: exactly the other six years' sessions")
            self.assertEqual(len(seen), len(set(seen)))
            self.assertEqual({d.year for d in seen}, set(elane_folds.WORK_YEARS) - {year})
            hidden = sessions_of([elane_folds.hidden_span(year)])
            self.assertEqual(hidden, [d for d in train if d.year == year], f"{year}: exactly its own sessions")
            self.assertFalse({d.year for d in seen + hidden} & set(elane_folds.RESERVE_YEARS), "no reserve session")
            self.assertEqual(sorted(seen + hidden), train, "together: the Train spans, each session once")
            for first, last in spans:
                self.assertTrue(any(a <= first <= last <= b for a, b in elane_train.TRAIN_SPANS), "inside a Train span")

    def test_a_year_that_is_no_work_year_is_refused(self):
        for bad in (2020, 2021, 2015, 2025, 2026, "2018", 2018.0, True, 0, -2018, (2018,)):
            with self.assertRaises(ValueError, msg=repr(bad)):
                elane_folds.seen_spans(bad)
            with self.assertRaises(ValueError, msg=repr(bad)):
                elane_folds.hidden_span(bad)
        with self.assertRaises(ValueError):
            elane_folds.hidden_span(None)

    def test_a_work_year_outside_every_train_span_fails_closed(self):
        """Were `WORK_YEARS` and E2's spans ever to drift apart, a family told of six years is never run on seven."""
        with mock.patch.object(elane_train, "TRAIN_SPANS", ((dt.date(2016, 1, 4), dt.date(2017, 12, 31)),)):
            with self.assertRaises(ValueError):
                elane_folds.seen_spans(2023)


class TheListingRule(unittest.TestCase):
    """THE LISTING RULE (as built): an invented House whose store holds one symbol with a bar on every session and one
    first listed in the middle of 2018 (as XLC is), and a third that left the store before the second Train span."""

    LISTED = dt.date(2018, 6, 19)
    #: The hidden years whose every stretch (each seen span and the year's own) holds a bar of the late symbol.
    RUNNABLE = (2019, 2022, 2023, 2024)

    @classmethod
    def setUpClass(cls):
        from league.equity import synth

        cls.tmp = tempfile.TemporaryDirectory()
        cls.house = Path(cls.tmp.name) / "house"
        end = dt.date(2024, 12, 31)
        before = [d for d, _ in nyse_sessions(dt.date(2016, 1, 4), cls.LISTED - dt.timedelta(days=1))]
        after = [d for d, _ in nyse_sessions(dt.date(2020, 1, 2), end)]
        cls.market = {"symbols": ("XLK", "XLC", "XLE"), "end": end, "seed": 9, "drift": 0.5, "vol": 0.05}
        cls.root = synth.synthetic_store(cls.house / elane.STORE_DIR, gaps={"XLC": before, "XLE": after}, **cls.market)
        cls.code = fx.program("XLC")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def swarm(self):
        """A swarm store on a House of its own that holds the equity store (`store.root` is where `birth_fields`
        looks)."""
        store = fx.new_store(self)
        shutil.copytree(self.root, Path(store.root) / elane.STORE_DIR)
        return store

    def test_the_years_a_symbol_has_a_bar_in(self):
        held = elane_folds.bar_years(self.house, ["xlk", " XLC ", "XLE", "XLK"])
        self.assertEqual(held, {"XLK": frozenset(elane_folds.WORK_YEARS), "XLC": frozenset({2018, 2019, 2022, 2023, 2024}),
                                "XLE": frozenset({2016, 2017, 2018, 2019})})
        self.assertEqual(list(held), ["XLK", "XLC", "XLE"])
        self.assertIsNone(elane_folds.bar_years(self.house, []), "no symbol: nothing to read")
        self.assertIsNone(elane_folds.bar_years(None, ["XLK"]))
        self.assertIsNone(elane_folds.bar_years(Path(self.tmp.name) / "nowhere", ["XLK"]), "a House with no equity store yet")

    def test_it_reads_one_train_span_at_a_time_and_never_a_reserve_session(self):
        from league.equity.store import EquityStore

        asked = []
        real = EquityStore.bars

        def bars(store, symbols, window, **kw):
            asked.append((window, kw["history"], kw["start"], kw["end"]))
            out = real(store, symbols, window, **kw)
            self.assertFalse({out.day(i).year for i in range(out.n)} & set(elane_folds.RESERVE_YEARS))
            return out
        with mock.patch.object(EquityStore, "bars", bars):
            elane_folds.bar_years(self.house, ["XLC"])
        self.assertEqual(asked, [("train", 0, first, last) for first, last in elane_train.TRAIN_SPANS])
        # Two markets that differ only in the reserve (here: whether the symbol has a bar there at all) read the same.
        from league.equity import synth

        other = Path(self.tmp.name) / "other"
        reserve = [d for d, _ in nyse_sessions(dt.date(2020, 1, 2), dt.date(2021, 12, 31))]
        before = [d for d, _ in nyse_sessions(dt.date(2016, 1, 4), self.LISTED - dt.timedelta(days=1))]
        synth.synthetic_store(other / elane.STORE_DIR, gaps={"XLC": before + reserve}, **{**self.market, "seed": 10})
        self.assertEqual(elane_folds.bar_years(other, ["XLK", "XLC"]), elane_folds.bar_years(self.house, ["XLK", "XLC"]))

    def test_a_store_that_cannot_be_read_raises(self):
        from league.equity.store import MissingData

        with self.assertRaises(MissingData):
            elane_folds.bar_years(self.house, ["XLK", "NOPE"])
        torn = Path(self.tmp.name) / "torn"
        (torn / elane.STORE_DIR).mkdir(parents=True)
        (torn / elane.STORE_DIR / "VERSION").write_text((self.root / "VERSION").read_text())
        with self.assertRaises(MissingData):
            elane_folds.bar_years(torn, ["XLK"])

    def test_a_year_is_runnable_when_every_stretch_holds_a_bar_of_every_symbol(self):
        every = frozenset(elane_folds.WORK_YEARS)
        late = frozenset({2018, 2019, 2022, 2023, 2024})
        for year in elane_folds.WORK_YEARS:
            self.assertTrue(elane_folds.runnable(year, {"XLK": every}), year)
            self.assertTrue(elane_folds.runnable(year, {}), "no symbol read: nothing to hold it back")
            self.assertEqual(elane_folds.runnable(year, {"XLK": every, "XLC": late}), year in self.RUNNABLE, year)
            self.assertFalse(elane_folds.runnable(year, {"XLE": frozenset({2016, 2017, 2018, 2019})}),
                             "gone before the second Train span: one stretch is always empty")
            self.assertFalse(elane_folds.runnable(year, {"XLK": frozenset()}))
        # 2016 hidden: its seen spans do hold the late symbol, its own span does not (no out-of-fold run to make).
        self.assertTrue(all(any(y in late for y in range(a.year, b.year + 1)) for a, b in elane_folds.seen_spans(2016)))
        self.assertFalse(elane_folds.runnable(2016, {"XLC": late}))
        for bad in (2020, 2021, 2015, None, "2018"):
            with self.assertRaises(ValueError):
                elane_folds.runnable(bad, {"XLK": every})

    def test_e1s_engine_agrees_year_by_year(self):
        """Why the rule: on E1's own runner each stretch of a runnable year ends "ok", and each other year has a
        stretch that ends "no_data" (which E2 reads as the House's failure: never scored)."""
        from league.equity.runner import Isolated
        from league.live.decider import InlineDecider

        runner = Isolated(InlineDecider(), self.root)
        held = elane_folds.bar_years(self.house, ["XLC"])
        for year in elane_folds.WORK_YEARS:
            spans = (*elane_folds.seen_spans(year), elane_folds.hidden_span(year))
            statuses = [runner.train(self.code, {}, name="late", start=first, end=last, k=1.0).result["status"]
                        for first, last in spans]
            self.assertEqual(set(statuses) == {"ok"}, elane_folds.runnable(year, held), (year, statuses))
            self.assertLessEqual(set(statuses), {"ok", "no_data"})
        whole = [runner.train(self.code, {}, name="late", start=first, end=last, k=1.0).result["status"]
                 for first, last in elane_train.TRAIN_SPANS]
        self.assertEqual(whole, ["ok", "ok"], "before E3 the family was scoreable: each whole span holds a bar")

    def test_a_birth_draws_by_the_formula_over_the_years_its_symbols_can_run(self):
        store = self.swarm()
        settings = e3.settings()
        cell = elane_train.cell_of("equity", "reversal", ("XLC",))
        self.assertEqual(cell, elane_train.cell_of("equity", "reversal", ("XLK",)), "one cell: the sector ETFs")
        h = elane_folds.cell_hash(cell)
        taken = []
        for i in range(36):
            symbols = ("XLC",) if i % 3 == 0 else ("XLK",)
            self.assertEqual(elane_folds.born(store, cell), i, "k_c: every hidden-year family of the cell")
            fields = elane_folds.birth_fields(store, settings, lane="equity", agenda="reversal", symbols=symbols)
            if symbols == ("XLK",):
                self.assertEqual(fields["hidden_year"], elane_folds.assign(store, cell),
                                 "a bar in every work year: D14's formula exactly")
                self.assertEqual(fields["hidden_year"], elane_folds.WORK_YEARS[(i + h) % 7])
            else:
                self.assertEqual(fields["hidden_year"], self.RUNNABLE[(i + h) % len(self.RUNNABLE)])
            self.assertEqual((fields["gid"], fields["expected_oof"]), ("g0", None))
            e3.hidden_family(store, f"s-{i}", fields["hidden_year"], lane="equity", agenda="reversal", symbols=symbols,
                             mechanism=f"Invented sector idea {i}: holders are paid for an invented risk.")
            taken.append((symbols[0], fields["hidden_year"]))
        self.assertEqual({y for s, y in taken if s == "XLK"}, set(elane_folds.WORK_YEARS))
        late = [y for s, y in taken if s == "XLC"]
        self.assertEqual(sorted(late.count(y) for y in self.RUNNABLE), [3, 3, 3, 3],
                         "spread evenly over the years it can run: no year takes the births of the years it cannot")
        # Both symbols in one family: every symbol must have its bar in every stretch.
        both = elane_folds.birth_fields(store, settings, lane="equity", agenda="reversal", symbols=("XLK", "XLC"))
        self.assertEqual(both["hidden_year"], self.RUNNABLE[(36 + h) % len(self.RUNNABLE)])

    def test_no_runnable_year_is_no_hidden_year_and_an_unreadable_store_raises(self):
        from league.equity.store import MissingData

        store = self.swarm()
        settings = e3.settings()
        gone = elane_folds.birth_fields(store, settings, lane="equity", agenda="reversal", symbols=("XLE",))
        self.assertEqual(gone, elane_folds.FALLBACK, "seven Train years, no out-of-fold row")
        with self.assertRaises(MissingData):   # the birth's guard (11.8) stamps FALLBACK and says so
            elane_folds.birth_fields(store, settings, lane="equity", agenda="reversal", symbols=("NOPE",))
        off = elane_folds.birth_fields(store, e3.settings("off"), lane="equity", agenda="reversal", symbols=("NOPE",))
        self.assertEqual(off, elane_folds.FALLBACK, "with the mode off nothing is read")


class NoSeenRunHasAHiddenSession(unittest.TestCase):
    """T4 on E1's own runner: its `Isolated` over its synthetic store (invented prices: a paying overnight market with
    an invented dividend inside every work year, so each hidden year has a booked action to hide), its engine in this
    process (`InlineDecider`)."""

    @classmethod
    def setUpClass(cls):
        from league.equity import synth

        from league.equity.store import EquityStore

        cls.tmp = tempfile.TemporaryDirectory()
        market = {"symbols": ("SPY",), "end": dt.date(2024, 12, 31), "seed": 5, "drift": 0.8, "vol": 0.04}
        # Each invented dividend is one percent of the close before it (the market's level rises a great deal).
        plain = EquityStore(synth.synthetic_store(Path(cls.tmp.name) / "plain", **market))
        bars = plain.bars(("SPY",), "train", history=0)
        close = {bars.day(i): float(bars.raw["SPY"][i, 3]) for i in range(bars.n)}
        cls.ex_days = {y: dt.date(y, 3, 15) for y in elane_folds.WORK_YEARS}
        paid = [(day, round(0.01 * close[max(d for d in close if d < day)], 2)) for day in cls.ex_days.values()]
        cls.root = synth.synthetic_store(Path(cls.tmp.name) / elane.STORE_DIR, dividends={"SPY": paid}, **market)
        cls.code = fx.program()
        cls.runs: dict = {}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def runner(self):
        from league.equity.runner import Isolated
        from league.live.decider import InlineDecider

        return Isolated(InlineDecider(), self.root)

    def seen(self, year: int, k: float = 1.0) -> list:
        """The seen runs of a hidden year at `k`, as E3's `score` makes them: one run a seen span."""
        key = (year, k)
        if key not in self.runs:
            runner = self.runner()
            self.runs[key] = [runner.train(self.code, {}, name="p", start=first, end=last, k=k)
                              for first, last in elane_folds.seen_spans(year)]
        return self.runs[key]

    def test_no_seen_result_names_the_hidden_year_anywhere(self):
        for year in elane_folds.WORK_YEARS:
            spans = elane_folds.seen_spans(year)
            named: set[int] = set()
            for run, span in zip(self.seen(year), spans):
                result = run.result
                self.assertEqual(result["status"], "ok")
                self.assertEqual(elane_train.outside_years(result, spans=[span]), [], "inside its own seen span")
                mine = years_named(result)
                self.assertNotIn(year, mine, f"{year}: a day or a by-year key of the hidden year in a seen result")
                self.assertFalse(mine & set(elane_folds.RESERVE_YEARS))
                for part in ("daily", "lots", "trades", "actions", "entry_days"):
                    self.assertNotIn(year, years_named(result[part]), f"{year}: {part}")
                for rows in (result["by_year"], result["bh"]["by_year"], result["exposure"]["by_year"]):
                    self.assertNotIn(str(year), rows)
                self.assertTrue(result["lots"] and result["actions"], "it really traded and was paid a dividend")
                named |= mine
            self.assertEqual(named, set(elane_folds.WORK_YEARS) - {year}, f"{year}: the other six years, every one")

    def test_the_hidden_run_holds_the_hidden_years_sessions_and_no_other(self):
        runner = self.runner()
        for year in (2016, 2018, 2024):
            first, last = elane_folds.hidden_span(year)
            result = runner.train(self.code, {}, name="p", start=first, end=last, k=1.0).result
            self.assertEqual([row[0] for row in result["daily"]], [d.isoformat() for d, _ in nyse_sessions(first, last)])
            self.assertEqual(years_named(result), {year})
            self.assertEqual([a["day"] for a in result["actions"]], [f"{year}-03-15"], "the year's own dividend")

    def test_e2s_window_check_refuses_a_seen_result_carrying_a_hidden_row(self):
        year = 2018
        spans = elane_folds.seen_spans(year)
        clean = self.seen(year)[1].result
        span = spans[1]
        self.assertEqual(span, (dt.date(2019, 1, 1), dt.date(2019, 12, 31)))
        row = dict(next(iter(clean["by_year"].values())))
        carried = {
            "a by-year row": {**clean, "by_year": {**clean["by_year"], "2018": row}},
            "a buy-and-hold row": {**clean, "bh": {**clean["bh"], "by_year": {**clean["bh"]["by_year"], "2018": 1.0}}},
            "an exposure row": {**clean, "exposure": {**clean["exposure"],
                                                      "by_year": {**clean["exposure"]["by_year"], "2018": 0.4}}},
            "a daily row": {**clean, "daily": [["2018-12-31", 1.0, 1001.0, 0.5], *clean["daily"]]},
            "a lot's entry day": {**clean, "lots": [{**clean["lots"][0], "entry_day": "2018-12-31"}, *clean["lots"][1:]]},
            "a trade's day": {**clean, "trades": [{**clean["trades"][0], "day": "2018-12-31"}, *clean["trades"][1:]]},
            "an action": {**clean, "actions": [{"symbol": "SPY", "day": "2018-03-15", "kind": "dividend"}]},
            "an entry day": {**clean, "entry_days": ["2018-12-31", *clean["entry_days"]]},
            "its start": {**clean, "start": "2018-12-31"},
        }
        for what, result in carried.items():
            self.assertTrue(elane_train.outside_years(result, spans=[span]), what)
        # The run E3 never makes: a whole Train span holds the hidden year, and is refused against each seen span.
        whole = self.runner().train(self.code, {}, name="p", start=elane_train.TRAIN_SPANS[0][0],
                                    end=elane_train.TRAIN_SPANS[0][1], k=1.0).result
        self.assertIn(year, years_named(whole))
        for seen_span in spans[:2]:
            self.assertTrue(elane_train.outside_years(whole, spans=[seen_span]))

    def test_e2s_bar_reads_six_years_on_the_seen_runs(self):
        for year in (2016, 2018, 2019, 2022, 2023, 2024):
            base = [run.result for run in self.seen(year, 1.0)]
            stress = [run.result for run in self.seen(year, 1.5)]
            verdict = elane_train.train_score(elane_train.combine(base), elane_train.combine(stress))
            self.assertEqual(sorted(verdict["years"]), [str(y) for y in elane_folds.WORK_YEARS if y != year], year)
            self.assertEqual(verdict["active_years"], 6)
            self.assertEqual(verdict["fails"], [], "the invented market pays the overnight hold in every seen year")
            self.assertEqual(elane_train.combine(base)["spans"], len(elane_folds.seen_spans(year)))
            self.assertNotIn(str(year), json.dumps(verdict["years"]))

    def test_the_restart_check_counts_no_hidden_session(self):
        year = 2023
        runs = self.seen(year)
        runner = self.runner()
        check = elane_train.restart_check(runner.decider, self.code, {}, name="p",
                                          streams=[elane_train.state_inputs(run) for run in runs])
        decisions = sum(run.bars.n - max(run.bars.first - 1, 0) - 1 for run in runs)
        self.assertEqual((check["sessions"], check["matched"], check["held"]), (decisions, decisions, True))
        run_sessions = sum(run.bars.n - run.bars.first for run in runs)
        self.assertEqual(run_sessions, len(sessions_of(elane_folds.seen_spans(year))), "the six seen years' sessions")
        whole = sum(len(sessions_of([span])) for span in elane_train.TRAIN_SPANS)
        self.assertEqual(whole - run_sessions, len(sessions_of([elane_folds.hidden_span(year)])))

    def test_the_hidden_runs_result_goes_to_the_out_of_fold_arithmetic_and_nowhere_else(self):
        """The ingest on E1's runner: every run it makes is a hidden-span run, each result is handed to
        `elane_effects.contribution` (the very object) and to nothing else: no `add_run`, no record key, no event, no
        row of any table but the memory's own."""
        year = 2018
        clock = fx.Clock()
        store = fx.new_store(self, clock)
        fam = e3.hidden_family(store, "h-2018", year, code=self.code)
        seen = {k: self.seen(year, k) for k in (1.0, 1.5)}
        verdict = elane_train.train_score(elane_train.combine([r.result for r in seen[1.0]]),
                                          elane_train.combine([r.result for r in seen[1.5]]))
        store.set_state(fam["id"], **{elane_train.STATE_KEY: {
            "status": "researching", "versions": {"1": elane_train.compact(verdict, at=store.now())}}})
        fam = store.family(fam["id"])
        runner = self.runner()
        made, handed = [], []
        real_train, real_contribution = runner.train, elane_effects.contribution

        def train(code, params, **kw):
            run = real_train(code, params, **kw)
            made.append((kw["start"], kw["end"], kw["k"], run))
            return run

        def contribution(run, *, k):
            handed.append(run)
            return real_contribution(run, k=k)

        elane_memory.ensure(store)
        before = e3.dump(store, less=elane_memory.TABLES)
        files = sorted(p.name for p in store.runs_dir.iterdir())
        with mock.patch.object(runner, "train", train), mock.patch.object(elane_effects, "contribution", contribution), \
                mock.patch.object(type(store), "add_run", side_effect=AssertionError("a hidden run was stored")) as add_run:
            out = elane_memory.ingest(store, fam, 1, runner=runner, code=self.code, params={}, seen=seen, verdict=verdict,
                                      settings=e3.settings())
        self.assertEqual(out, {"seen": 1, "contrib": 2, "hidden_year": year})
        self.assertEqual([(a, b, k) for a, b, k, _ in made], [(*elane_folds.hidden_span(year), k) for k in (1.0, 1.5)],
                         "the only runs it makes: the hidden span at each k")
        self.assertEqual([id(r) for r in handed], [id(run) for *_, run in made], "each result, to `contribution`")
        add_run.assert_not_called()
        self.assertEqual(e3.dump(store, less=elane_memory.TABLES), before,
                         "no family state, no run, no event, no note, no kv: nothing but the memory tables moved")
        self.assertEqual(sorted(p.name for p in store.runs_dir.iterdir()), files, "no stored result file")
        self.assertNotIn(str(year), json.dumps(store.family(fam["id"])["state"]), "no record key of the hidden year")
        rows = e3.table(store, "mem_contrib")
        self.assertEqual([(r["year"], r["k"], r["status"], r["n_days"]) for r in rows],
                         [(year, 1.0, "ok", len(sessions_of([elane_folds.hidden_span(year)]))),
                          (year, 1.5, "ok", len(sessions_of([elane_folds.hidden_span(year)])))])


if __name__ == "__main__":
    unittest.main()
