"""Release E3, THE CONTAMINATION PROBE (league/ops/contam_probe.py; D16): the questions (a full grid a cell, from symbol
names and the calendar only), the truth on a synthetic store, the answers' parse, a cell's score (agreement beyond a
constant answer; a permutation test by whole period, so an always-"higher" answerer scores exactly 1 and same-period
symbols are one observation), which route is due, the job on a scripted router (the dollar and the time stop, the
resume at no cost, the request keys, the idle route and CP2), and seal T7, `NoTruthLeavesTheHouse`: the prompts are
identical whatever the prices, and nothing the probe writes holds a per-question truth or outcome. The store is E1's
synthetic one and the router is scripted: every price, answer and dollar here is invented."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.equity import config, synth
from league.equity.store import (STORE_DIR, EquityStore, MissingData, StoreRefused, mint_equity_gate_capability,
                                 nyse_sessions, write_store)
from league.ops import contam_probe as P
from league.ops import schedule
from league.ops.context import Context
from league.swarm import elane_yield
from league.swarm.store import SwarmStore
from league.tests import elane_e2_fakes as fx

UNIVERSE = {"SPY": "etf", "QQQ": "etf", "XLK": "etf", "TLT": "etf", "AAPL": "stock", "MSFT": "stock"}
ROUTES = ["sail:pro_asap", "sail:glm_asap", "sail:k3"]
WEEK = 7 * 86400.0


def settings(**contam) -> dict:
    block = {"mode": "record", "usd_run": 3.0, "batch": 10, "questions_per_cell": 24, "every_days": 28, **contam}
    return {"elane": {"mode": "gate", "contam": block, "e2": {"routes": list(ROUTES), "usd_day": 8.0}}}


def question_of(line: str) -> str:
    return line.split(". ", 1)[1]


class ProbeRouter:
    """The swarm's router as the probe drives it, scripted: `answerer(question text) -> answer` for each numbered item of
    a call's user text. Like the Provider, it answers a request key it has seen from its own store at no cost; a new
    key costs `cost` dollars. `fails[profile]` is an exception that route's every call raises; `moves[profile]` is the
    profile the router's own window fallback answers on in its place (league/swarm/models.py: the answer then says
    so, and the fallback's call has a key of its own); `calls` keeps each call and `billed` the keys that cost."""

    def __init__(self, answerer=None, *, cost: float = 0.05):
        self.answerer = answerer or (lambda text: "higher" if "higher or lower" in text else
                                     ("more" if "more or less" in text else 2))
        self.cost = float(cost)
        self.seen: dict[str, dict] = {}
        self.calls: list[dict] = []
        self.billed: list[str] = []
        self.fails: dict[str, BaseException] = {}
        self.moves: dict[str, str] = {}

    def claude_enabled(self, role: str) -> bool:
        return False

    def ask(self, **kw):
        self.calls.append(kw)
        profile = kw["sail_profile"]
        if profile in self.fails:
            raise self.fails[profile]
        moved = self.moves.get(profile)
        key = kw["key"] if moved is None else f"{kw['key']}:fallback:{moved}"
        if key in self.seen:
            return {**self.seen[key], "cost_usd": 0.0}
        items = [line for line in kw["user"].split("\n\n", 1)[1].splitlines() if re.match(r"^\d+\. ", line)]
        answer = {"text": json.dumps([self.answerer(question_of(line)) for line in items]), "route": "sail",
                  "model": moved or profile, "cost_usd": self.cost}
        if moved is not None:
            answer["sail_fallback"] = {"from": profile, "to": moved, "why": "flagged"}
        self.seen[key] = answer
        self.billed.append(key)
        return answer


class Stores(unittest.TestCase):
    """Two synthetic markets of the same universe (invented prices; the House's store carries the gate's mark)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.roots = {seed: synth.synthetic_store(Path(cls.tmp.name) / f"m{seed}" / STORE_DIR, symbols=tuple(UNIVERSE),
                                                 seed=seed, drift=0.06, vol=0.2, gate=True) for seed in (3, 4)}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def equity(self, seed: int = 3) -> EquityStore:
        root = self.roots[seed]
        return EquityStore(root, gate=mint_equity_gate_capability(root, P.GATE_REASON))


class TheSettings(unittest.TestCase):
    def test_the_defaults_and_the_bounds(self):
        self.assertEqual(P.cfg(None), {"mode": "off", "usd_run": 3.0, "every_days": 28, "batch": 20, "questions_per_cell": 120})
        for raw in ({}, {"elane": None}, {"elane": {"contam": "record"}}, {"elane": {"contam": ["record"]}}):
            self.assertEqual(P.cfg(raw), P.DEFAULTS, raw)
            self.assertEqual(P.mode(raw), "off")
        got = P.cfg({"elane": {"contam": {"mode": "record", "usd_run": 1.5, "every_days": 7, "batch": 40,
                                          "questions_per_cell": 200}}})
        self.assertEqual(got, {"mode": "record", "usd_run": 1.5, "every_days": 7, "batch": 40, "questions_per_cell": 200})
        bad = P.cfg({"elane": {"contam": {"mode": "on", "usd_run": 10.01, "every_days": 6, "batch": 7.5,
                                          "questions_per_cell": "120"}}})
        self.assertEqual(bad, P.DEFAULTS, "a value outside its bound or of another shape is its code default")
        self.assertEqual(P.cfg({"elane": {"contam": {"usd_run": True, "batch": float("nan")}}}), P.DEFAULTS)
        self.assertEqual(P.cfg({"elane": {"contam": {"usd_run": 0}}})["usd_run"], 0.0)


class TheGrid(unittest.TestCase):
    def test_a_stratums_symbols(self):
        self.assertEqual(P.stratum_symbols(UNIVERSE, "S1"), ["SPY", "QQQ"])
        self.assertEqual(P.stratum_symbols(UNIVERSE, "S2"), ["QQQ", "XLK", "TLT"])
        self.assertEqual(P.stratum_symbols(UNIVERSE, "S3"), ["AAPL", "MSFT"])
        self.assertEqual(P.stratum_symbols(UNIVERSE, "S4"), ["QQQ", "XLK", "TLT", "AAPL", "MSFT"])
        whole = dict(config.UNIVERSE)
        self.assertEqual(P.stratum_symbols(whole, "S1"), list(config.INDEX_ETFS))
        self.assertEqual(len(P.stratum_symbols(whole, "S4")), len(whole) - 1)
        with self.assertRaises(KeyError):
            P.stratum_symbols(UNIVERSE, "S9")

    def test_a_cell_is_k_symbols_and_p_periods_first_by_their_hash(self):
        whole = dict(config.UNIVERSE)
        for stratum in P.STRATA:
            for era in P.ERAS:
                names, chosen = P.grid(whole, stratum, era, per_cell=120)
                pool = P.stratum_symbols(whole, stratum)
                every = [name for name, _, _ in P.periods(stratum, era)]
                k = min(len(pool), P.SYMBOLS_PER_CELL)
                self.assertEqual(len(names), k)
                self.assertEqual(len(chosen), min(len(every), 120 // k))

                def order(items):
                    return sorted(items, key=lambda x: hashlib.sha256(f"contam-1|{stratum}|{era}|{x}".encode()).hexdigest())
                self.assertEqual(names, order(pool)[:k], (stratum, era))
                self.assertEqual(chosen, order(every)[:len(chosen)], (stratum, era))
        self.assertEqual(P.grid({"XLK": "etf"}, "S1", "2025", per_cell=120), ([], []), "a stratum with no symbol has no cell")
        self.assertEqual(P.grid(whole, "S1", "2026H1", per_cell=120)[1].__len__(), 6, "an era's periods bound P")

    def test_every_symbol_is_asked_every_period_of_its_cell(self):
        asked = P.questions(UNIVERSE, per_cell=24)
        cells: dict = {}
        for q in asked:
            cells.setdefault((q["stratum"], q["era"]), []).append(q)
        self.assertEqual(list(cells), [(s, e) for s in P.STRATA for e in P.ERAS], "a fixed order: stratum, then era")
        for (stratum, era), rows in cells.items():
            names, chosen = P.grid(UNIVERSE, stratum, era, per_cell=24)
            self.assertEqual([(q["period"], q["symbol"]) for q in rows], [(p, s) for p in chosen for s in names],
                             "the full grid, period by period, the same symbols in the same order each period")
            self.assertLessEqual(len(rows), 24)
        self.assertEqual(len({q["id"] for q in asked}), len(asked))
        self.assertEqual(set(asked[0]), {"id", "stratum", "era", "symbol", "against", "first", "last", "period", "text"})

    def test_the_questions_are_built_from_names_and_the_calendar_only(self):
        self.assertEqual(P.questions(UNIVERSE, per_cell=24), P.questions(dict(UNIVERSE), per_cell=24), "no store is read")
        by_id = {q["id"]: q for q in P.questions(UNIVERSE, per_cell=24)}
        s1 = next(q for q in by_id.values() if q["stratum"] == "S1" and q["era"] == "2025" and q["period"] == "2025-03")
        self.assertEqual((s1["first"], s1["last"], s1["against"]), ("2025-02-28", "2025-03-31", None))
        self.assertEqual(s1["text"], f"Did {s1['symbol']} finish March 2025 higher or lower than it finished the month before?")
        s3 = next(q for q in by_id.values() if q["stratum"] == "S3")
        self.assertRegex(s3["text"], r"^Did (AAPL|MSFT) return more or less than SPY in [A-Z][a-z]+ \d{4}\?$")
        s4 = next(q for q in by_id.values() if q["stratum"] == "S4")
        self.assertEqual(s4["text"], f"Did {s4['symbol']} return more or less than SPY in the week ending {s4['period']}?")
        self.assertEqual((s4["against"], s4["last"]), ("SPY", s4["period"]))
        for q in by_id.values():
            self.assertNotRegex(q["text"], r"\d+\.\d", "no price, no return")
            self.assertLess(q["first"], q["last"])

    def test_a_period_runs_from_the_last_session_before_it_and_belongs_to_the_era_it_ends_in(self):
        months = P.periods("S1", "2016-24")
        self.assertEqual(months[0], ("2016-02", "2016-01-29", "2016-02-29"), "January 2016 has no month before it in the store")
        self.assertEqual((len(months), months[-1]), (107, ("2024-12", "2024-11-29", "2024-12-31")))
        self.assertEqual([m[0] for m in P.periods("S2", "2026H1")], [f"2026-0{i}" for i in range(1, 7)])
        self.assertEqual(P.periods("S3", "2025")[0], ("2025-01", "2024-12-31", "2025-01-31"))
        weeks = P.periods("S4", "2026H1")
        self.assertEqual(weeks[0], ("2026-01-02", "2025-12-26", "2026-01-02"), "the week ends in the era; its base is before it")
        self.assertEqual(weeks[-1], ("2026-06-26", "2026-06-18", "2026-06-26"), "the next week ends in July: another era's")
        self.assertEqual(P.periods("S4", "2016-24")[0], ("2016-01-15", "2016-01-08", "2016-01-15"))
        for stratum, era in (("S1", "2025"), ("S4", "2025"), ("S4", "2016-24")):
            lo, hi = P.ERAS[era]
            for name, first, last in P.periods(stratum, era):
                first_day, last_day = dt.date.fromisoformat(first), dt.date.fromisoformat(last)
                self.assertTrue(lo <= last_day <= hi)
                between = [d for d, _ in nyse_sessions(first_day, last_day)]
                self.assertEqual((between[0], between[-1]), (first_day, last_day), "both are sessions")
                span = {tuple(d.isocalendar()[:2]) if stratum == "S4" else (d.year, d.month) for d in between[1:]}
                self.assertEqual(len(span), 1, "every session after the base is the period's own")
        with self.assertRaises(KeyError):
            P.periods("S1", "2027")

    def test_the_reserve_recall_is_24_months_of_spy(self):
        recall = P.recall_questions()
        self.assertEqual([q["period"] for q in recall], [f"{y}-{m:02d}" for y in (2020, 2021) for m in range(1, 13)])
        self.assertEqual({(q["stratum"], q["era"], q["symbol"], q["against"]) for q in recall}, {("R2021", "2020-21", "SPY", None)})
        self.assertEqual(recall[0]["text"], "State SPY's total return in January 2020 to the nearest percent.")
        self.assertEqual((recall[0]["first"], recall[0]["last"]), ("2019-12-31", "2020-01-31"))

    def test_the_question_set_has_a_sha_that_moves_with_any_question(self):
        asked = P.questions(UNIVERSE, per_cell=24)
        self.assertEqual(P.qset(asked), hashlib.sha256("\n".join(q["id"] for q in asked).encode()).hexdigest())
        self.assertNotEqual(P.qset(asked), P.qset(asked[:-1]))
        self.assertNotEqual(P.qset(asked), P.qset(P.questions(UNIVERSE, per_cell=40)))
        self.assertNotEqual(P.qset(asked), P.qset(P.questions({**UNIVERSE, "IWM": "etf"}, per_cell=24)))


class TheTruth(Stores):
    def closes(self, seed: int = 3) -> dict:
        store = EquityStore(self.roots[seed], gate=mint_equity_gate_capability(self.roots[seed], "a test's own read"))
        out = {}
        for window in ("train", "validation", "holdout"):
            bars = store.bars(tuple(UNIVERSE), window, history=0)
            for i in range(bars.n):
                for sym in UNIVERSE:
                    out[(sym, bars.day(i).isoformat())] = float(bars.adj[sym][i, 3])
        return out

    def test_the_truth_is_the_sign_of_the_as_of_close_ratio(self):
        store, close = self.equity(), self.closes()
        seen = set()
        for q in P.questions(UNIVERSE, per_cell=24):
            own = close[(q["symbol"], q["last"])] / close[(q["symbol"], q["first"])]
            if q["stratum"] == "S1":
                want = "higher" if own > 1 else "lower"
            else:
                spy = close[("SPY", q["last"])] / close[("SPY", q["first"])]
                want = "more" if own > spy else "less"
            self.assertEqual(P.truth(store, q), want, q["id"])
            seen.add((q["stratum"], want))
        self.assertEqual(seen, {("S1", "higher"), ("S1", "lower"), *((s, w) for s in ("S2", "S3", "S4") for w in ("more", "less"))})
        for q in P.recall_questions():
            want = (close[("SPY", q["last"])] / close[("SPY", q["first"])] - 1.0) * 100.0
            self.assertAlmostEqual(P.truth(store, q), want, places=9)

    def test_a_zero_is_a_tie_and_a_missing_price_is_none(self):
        days = nyse_sessions(dt.date(2024, 11, 1), dt.date(2025, 3, 31))
        flat = [100.0] * len(days)
        series = {sym: {"days": [d for d, _ in days], "raw_v": [1e6] * len(days),
                        **{name: list(flat) for name in ("raw_o", "raw_h", "raw_l", "raw_c", "all_o", "all_h", "all_l", "all_c")}}
                  for sym in ("SPY", "QQQ")}
        with tempfile.TemporaryDirectory() as tmp:
            write_store(tmp, calendar=days, series=series, classes={"SPY": "etf", "QQQ": "etf"},
                        fetched_through=days[-1][0], source="synthetic", gate=True)
            store = EquityStore(tmp, gate=mint_equity_gate_capability(tmp, P.GATE_REASON))
            asked = {q["id"]: q for q in P.questions({"SPY": "etf", "QQQ": "etf", "XLK": "etf"}, per_cell=200)}
            self.assertEqual(P.truth(store, asked["S1|2025|SPY|2025-02"]), "tie", "it finished where it finished before")
            self.assertEqual(P.truth(store, asked["S2|2025|QQQ|2025-02"]), "tie", "it returned exactly what SPY did")
            self.assertIsNone(P.truth(store, asked["S2|2025|XLK|2025-02"]), "a symbol the store does not hold")
            self.assertIsNone(P.truth(store, asked["S1|2025|SPY|2025-06"]), "a month past the store's last day")
            self.assertIsNone(P.truth(store, {**asked["S1|2025|SPY|2025-02"], "first": "2024-10-31"}), "no bar that day")

    def test_a_sealed_day_needs_the_gates_capability(self):
        q = next(q for q in P.questions(UNIVERSE, per_cell=24) if q["era"] == "2026H1")
        with self.assertRaises(StoreRefused):
            P.truth(EquityStore(self.roots[3]), q)
        self.assertIn(P.truth(self.equity(), q), ("higher", "lower"))


class TheAnswers(unittest.TestCase):
    def setUp(self):
        self.batch = [q for q in P.questions(UNIVERSE, per_cell=24) if q["stratum"] == "S1"][:4]

    def test_the_prompt_is_the_fixed_system_and_numbered_items(self):
        system, user = P.prompt(self.batch)
        self.assertEqual(system, P.SYSTEM)
        lead, items = user.split("\n\n", 1)
        self.assertIn('"higher" or "lower"', lead)
        self.assertIn("JSON array of 4 strings", lead)
        self.assertEqual(items.splitlines(), [f"{i}. {q['text']}" for i, q in enumerate(self.batch, 1)])
        recall = P.prompt(P.recall_questions()[:3])[1]
        self.assertIn("JSON array of 3 numbers", recall)
        self.assertIn('"more" or "less"', P.prompt([q for q in P.questions(UNIVERSE, per_cell=24) if q["stratum"] == "S4"][:2])[1])
        with self.assertRaises(ValueError):
            P.prompt([self.batch[0], P.recall_questions()[0]])

    def test_a_good_a_short_and_a_non_json_answer(self):
        self.assertEqual(P.parse('["higher", "lower", "higher", "lower"]', self.batch), ["higher", "lower", "higher", "lower"])
        self.assertEqual(P.parse('Here you are:\n```json\n["Higher", " lower.", "HIGHER", "lower"]\n```', self.batch),
                         ["higher", "lower", "higher", "lower"])
        self.assertEqual(P.parse('["higher", "lower"]', self.batch), ["higher", "lower", None, None], "a short answer")
        self.assertEqual(P.parse('["higher", "up", 1, null, "lower", "lower"]', self.batch), ["higher", None, None, None])
        self.assertEqual(P.parse('[{"answer": "lower"}, {"1": "higher"}, {"a": 1, "b": 2}, "more"]', self.batch),
                         ["lower", "higher", None, None], "a word of another stratum is no answer")
        for text in ("higher, lower, higher, lower", "", None, 7, '{"answers": "higher"}', "[higher", "] [", "[", "[,",
                     "[higher, lower], sorry", '{"a": ["x", "y"]}'):
            self.assertEqual(P.parse(text, self.batch), [None] * 4, repr(text))

    def test_the_array_is_found_among_a_models_other_words(self):
        want = ["higher", "lower", "higher", "lower"]
        for text in ('Items [1-4], from memory [as asked]: ["higher", "lower", "higher", "lower"] (my best guesses).',
                     '[1] ["higher", "lower", "higher", "lower"]',
                     '["higher", "lower", "higher", "lower"] and again [1, 2, 3, 4]',
                     '[["higher", "lower", "higher", "lower"]]',
                     '{"answers": ["higher", "lower", "higher", "lower"]}'):
            self.assertEqual(P.parse(text, self.batch), want, text)
        self.assertEqual(P.parse('["lower", "lower"] or ["higher", "higher"]', self.batch), ["lower", "lower", None, None],
                         "the earliest of two arrays that answer as much")
        self.assertEqual(P.parse("[" * 40 + '"higher"' + "]" * 40, self.batch), [None] * 4,
                         f"only the first {P.ARRAY_STARTS} brackets are tried")
        self.assertEqual(P.ARRAY_STARTS, 32)

    def test_a_reply_cut_before_its_array_ends_gives_the_entries_before_the_cut(self):
        """A route's answer cut at its output bound (league/swarm/models.py: a Sail answer `truncated`): the items it
        did answer are its answers; the rest are not answered and count in `skipped`."""
        self.assertEqual(P.parse('["higher",', self.batch), ["higher", None, None, None])
        self.assertEqual(P.parse('```json\n["higher", "lower", "hig', self.batch), ["higher", "lower", None, None])
        self.assertEqual(P.parse('["higher", "lower", "higher", "low', self.batch), ["higher", "lower", "higher", None])
        self.assertEqual(P.parse('[{"answer": "lower"}, {"answer": "hi', self.batch), ["lower", None, None, None])
        self.assertEqual(P.parse('["higher"', self.batch), [None] * 4, "no whole entry is known to be whole")
        self.assertEqual(P.parse('[3, -2, 1', P.recall_questions()[:4]), [3.0, -2.0, None, None],
                         "a number cut short is not read as a smaller one")

    def test_the_recalls_numbers(self):
        batch = P.recall_questions()[:5]
        self.assertEqual(P.parse('[3, -2.5, "4%", "+1", "about two"]', batch), [3.0, -2.5, 4.0, 1.0, None])
        self.assertEqual(P.parse('[true, null, "nan", 1e400, 0]', batch), [None, None, None, None, 0.0])


def cell(k: int, p: int, stratum: str = "S1", era: str = "2025") -> list[dict]:
    """A full grid of invented questions: `p` periods, `k` symbols each."""
    return [{"id": f"{stratum}|{era}|X{j}|P{i:02d}", "stratum": stratum, "era": era, "symbol": f"X{j}", "period": f"P{i:02d}"}
            for i in range(p) for j in range(k)]


class TheScore(unittest.TestCase):
    def test_wilson(self):
        self.assertEqual(P.wilson(0, 0), (0.0, 1.0))
        lo, hi = P.wilson(8, 10)
        self.assertAlmostEqual(lo, 0.4901625, places=6)
        self.assertAlmostEqual(hi, 0.9433178, places=6)
        self.assertAlmostEqual(P.wilson(10, 10)[1], 1.0, places=12)
        self.assertEqual(P.wilson(0, 10)[0], 0.0)

    def test_accuracy_base_and_agreement_beyond_a_constant_answer(self):
        asked = cell(2, 6)
        truths = ["higher"] * 9 + ["lower"] * 3
        answers = ["higher"] * 6 + ["lower"] * 3 + ["lower"] * 3   # nine right: six of the highers, the three lowers
        got = P.score(asked, answers, truths)
        self.assertEqual((got["n"], got["correct"], got["ties"], got["skipped"], got["periods"], got["symbols"]), (12, 9, 0, 0, 6, 2))
        self.assertEqual((got["acc"], got["base"], got["m"]), (0.75, 0.75, 0.0), "no better than always answering higher")
        self.assertEqual((got["lo"], got["hi"]), tuple(round(x, 4) for x in P.wilson(9, 12)))
        self.assertEqual(set(got), set(P.CELL_KEYS))

    def test_a_tie_a_missing_truth_and_a_skipped_answer_enter_no_share(self):
        asked = cell(2, 6)
        truths = ["higher", "lower"] * 6
        truths[0], truths[1] = "tie", None
        answers = list(["higher", "lower"] * 6)
        answers[2], answers[3] = None, "lower"
        got = P.score(asked, answers, truths)
        self.assertEqual((got["ties"], got["skipped"], got["n"], got["correct"]), (1, 1, 9, 9))
        self.assertEqual(got["acc"], 1.0)

    def test_an_always_higher_answerer_scores_exactly_one_and_is_not_recalled(self):
        asked = cell(4, 12)
        truths = [("higher" if (i * 7 + j * 3) % 5 < 3 else "lower") for i in range(12) for j in range(4)]
        got = P.score(asked, ["higher"] * 48, truths)
        self.assertEqual(got["p_perm"], 1.0, "truths move by whole period: a constant answer agrees as much under every one")
        self.assertEqual((got["m"], got["recalled"], got["readable"]), (0.0, False, True))
        self.assertGreater(got["acc"], 0.5, "and yet it is right most of the time: index ETFs rise most months")

    def test_a_perfect_answerer_on_a_mixed_truth_cell_is_recalled(self):
        asked = cell(4, 12)
        truths = [("higher" if (i * 7 + j * 3) % 5 < 3 else "lower") for i in range(12) for j in range(4)]
        got = P.score(asked, list(truths), truths)
        self.assertEqual((got["acc"], got["readable"], got["recalled"]), (1.0, True, True))
        self.assertLessEqual(got["p_perm"], P.ALPHA)
        self.assertGreater(got["m"], 0.3)

    def test_four_copies_of_one_coin_flip_month_series_are_not_recalled(self):
        """Four symbols that move together are one observation a month. A coin-flip answerer who gets 9 of 12 months
        (36 of 48 questions) would clear a per-question test easily; by whole period it does not."""
        months = ["higher", "lower", "higher", "higher", "lower", "higher", "lower", "lower", "higher", "lower", "higher",
                  "higher"]
        flips = list(months)
        for i in (1, 6, 10):   # the coin misses three of the twelve months
            flips[i] = "lower" if months[i] == "higher" else "higher"
        asked = cell(4, 12)
        truths = [m for m in months for _ in range(4)]
        got = P.score(asked, [f for f in flips for _ in range(4)], truths)
        self.assertEqual((got["n"], got["correct"], got["acc"]), (48, 36, 0.75))
        binomial = sum(math.comb(48, i) for i in range(36, 49)) / 2 ** 48
        self.assertLess(binomial, 0.001, "what counting 48 independent questions would have claimed")
        self.assertGreater(got["p_perm"], P.ALPHA)
        self.assertEqual((got["readable"], got["recalled"]), (True, False))

    def test_six_months_that_all_rose_are_unreadable(self):
        asked = cell(4, 6)
        got = P.score(asked, ["higher"] * 24, ["higher"] * 24)
        self.assertEqual((got["acc"], got["p_perm"], got["readable"], got["recalled"]), (1.0, 1.0, False, False),
                         "a perfect answerer could not clear the test either: the cell cannot show recall")

    def test_too_few_answers_or_periods_are_unreadable(self):
        truths = [("higher" if (i * 7 + j * 3) % 5 < 3 else "lower") for i in range(12) for j in range(4)]
        answers = list(truths)
        for i in range(10):   # 38 of 48 answered: under 80%
            answers[i] = None
        got = P.score(cell(4, 12), answers, truths)
        self.assertEqual((got["skipped"], got["readable"], got["recalled"]), (10, False, False))
        self.assertLessEqual(got["p_perm"], P.ALPHA, "it would have been recalled, were it readable")
        few = P.score(cell(4, 5), truths[:20], truths[:20])
        self.assertEqual((few["periods"], few["readable"]), (5, False))
        none = P.score(cell(2, 6), [None] * 12, ["higher", "lower"] * 6)
        self.assertEqual((none["n"], none["acc"], none["base"], none["m"], none["p_perm"], none["recalled"]),
                         (0, None, None, None, None, False))

    def test_the_permutation_is_seeded_by_the_cell_and_needs_a_full_grid(self):
        asked = cell(3, 8)
        truths = [("higher" if (i + j) % 3 else "lower") for i in range(8) for j in range(3)]
        answers = [("higher" if (i * j) % 2 else "lower") for i in range(8) for j in range(3)]
        names = [q["period"] for q in asked]
        seed = hashlib.sha256(b"contam-1|perm|S1|2025").hexdigest()
        p = P.perm_p(answers, truths, names, seed=seed)
        self.assertEqual(p, P.perm_p(answers, truths, names, seed=seed))
        self.assertEqual(P.score(asked, answers, truths)["p_perm"], round(p, 6))
        self.assertEqual(round(p * (P.PERMUTATIONS + 1)), p * (P.PERMUTATIONS + 1), "(1 + a count) / 2,001")
        self.assertGreaterEqual(p, 1 / (P.PERMUTATIONS + 1))
        with self.assertRaises(ValueError):
            P.perm_p(answers[:-1], truths[:-1], names[:-1], seed=seed)
        with self.assertRaises(ValueError):
            P.perm_p(answers, truths, names[:-1], seed=seed)
        self.assertEqual(P.perm_p([], [], [], seed=seed), 1.0)
        self.assertEqual(P.PERMUTATIONS, 2000)

    def test_the_recall_of_a_perfect_and_of_a_shuffled_answerer(self):
        asked = P.recall_questions()
        truths = [round(8 * math.sin(1.3 * i) + 0.4 * i - 3, 2) for i in range(24)]
        perfect = P.score(asked, [float(round(t)) for t in truths], truths)
        self.assertEqual(set(perfect), set(P.RECALL_KEYS))
        self.assertEqual(perfect["n"], 24)
        self.assertGreater(perfect["rho"], 0.99)
        self.assertLess(perfect["p_perm"], 0.01)
        self.assertGreater(perfect["sign_acc"], 0.9)
        shuffled = [truths[(7 * i + 3) % 24] for i in range(24)]
        got = P.score(asked, shuffled, truths)
        self.assertLess(abs(got["rho"]), 0.5)
        self.assertGreater(got["p_perm"], 0.05)
        partly = P.score(asked, [None] * 22 + [1.0, 2.0], truths)
        self.assertEqual((partly["n"], partly["rho"], partly["p_perm"]), (2, None, None))
        with self.assertRaises(ValueError):
            P.score([], [], [])


class WhichRouteIsDue(unittest.TestCase):
    NOW = 1_800_000_000.0

    def due(self, routes: dict, names=("a", "b", "c"), every: float = 28) -> str | None:
        return P.due({"version": "contam-1", "routes": routes}, list(names), now=self.NOW, every_days=every)

    def at(self, days_ago: float, *, text: bool = True):
        when = self.NOW - days_ago * 86400.0
        return schedule.iso(when) if text else when

    def test_a_route_never_tried_goes_first_in_list_order(self):
        self.assertEqual(P.due(None, ["a", "b"], now=self.NOW, every_days=28), "a")
        self.assertEqual(self.due({"a": {"attempted_at": self.at(1), "idle": 1}}), "b")
        self.assertIsNone(P.due({}, [], now=self.NOW, every_days=28))

    def test_a_fresh_result_is_not_due_and_an_old_one_is(self):
        fresh = {"at": self.at(27), "attempted_at": self.at(27), "idle": 0}
        self.assertIsNone(self.due({k: dict(fresh) for k in "abc"}))
        self.assertEqual(self.due({"a": dict(fresh), "b": {**fresh, "at": self.at(29), "attempted_at": self.at(29)},
                                   "c": dict(fresh)}), "b")
        self.assertEqual(self.due({k: dict(fresh) for k in "abc"}, every=7), "a")
        self.assertEqual(self.due({"a": {"at": self.at(40, text=False), "attempted_at": self.at(40, text=False)},
                                   "b": {"at": self.at(50), "attempted_at": self.at(50)}, "c": dict(fresh)}), "b",
                         "epoch seconds or ISO text; the oldest goes first")

    def test_a_probe_under_way_and_moving_is_chosen_before_an_older_route(self):
        rows = {"a": {"at": self.at(60), "attempted_at": self.at(60), "idle": 0},
                "b": {"attempted_at": self.at(7), "idle": 0, "partial": {"probe_n": 1, "cells": {"S1": {}}}},
                "c": {"attempted_at": self.at(14), "idle": 0, "partial": {"probe_n": 1, "cells": {}}}}
        self.assertEqual(self.due(rows), "c", "of two under way, the one attempted longest ago")
        rows["c"]["idle"] = 1
        self.assertEqual(self.due(rows), "b", "a partial that did not move last time is not `moving`")
        rows["b"]["idle"] = 2
        self.assertEqual(self.due(rows), "a", "then the oldest of max(at, attempted_at)")

    def test_a_route_that_keeps_failing_goes_to_the_back_of_the_line(self):
        rows = {"a": {"attempted_at": self.at(1), "idle": 3}, "b": {"at": self.at(30), "attempted_at": self.at(30)},
                "c": {"at": self.at(29), "attempted_at": self.at(29)}}
        self.assertEqual(self.due(rows), "b")
        rows["b"] = {"at": self.at(0), "attempted_at": self.at(0)}
        self.assertEqual(self.due(rows), "c")
        rows["c"] = {"at": self.at(0), "attempted_at": self.at(0)}
        self.assertEqual(self.due(rows), "a", "alone in the line, it is tried again: it never blocks the others")


class Jobs(Stores):
    """The job's parts as `run` opens them, with a scripted router in the place of `models.build_router`'s."""

    def setUp(self):
        self.clock = fx.Clock()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.router = ProbeRouter()
        self.settings = settings()
        self.ticks = iter(range(10 ** 9))

    def probe(self, *, seed: int = 3, settings_=None, router=None, clock=None):
        ctx = Context("contam_probe", root=self.root, due_at=self.clock(), clock=self.clock, config={}, settings_value={})
        out = P.Probe(ctx, store=self.store, settings=settings_ or self.settings, router=router or self.router,
                      equity=self.equity(seed), symbols=UNIVERSE, clock=clock or (lambda: 0.0)).run()
        return out, ctx

    def doc(self) -> dict:
        return json.loads((self.root / P.FILE).read_text())

    def oracle(self, seed: int = 3) -> dict:
        """question text -> its truth on a market (a model that recalls everything)."""
        store = self.equity(seed)
        table = {q["text"]: P.truth(store, q) for q in P.questions(UNIVERSE, per_cell=24)}
        table.update({q["text"]: round(P.truth(store, q)) for q in P.recall_questions()})
        return table


class TheJob(Jobs):
    def test_one_run_probes_one_route_whole_and_publishes_aggregates(self):
        out, ctx = self.probe()
        asked = P.questions(UNIVERSE, per_cell=24)
        batches = sum(-(-n // 10) for n in [sum(1 for q in asked if (q["stratum"], q["era"]) == (s, e))
                                              for s in P.STRATA for e in P.ERAS]) + 3
        self.assertEqual(out, {"route": "sail:pro_asap", "probe": 1, "usd": round(0.05 * batches, 6), "bound": 3.0,
                               "finished": True, "cells": 13, "asked": batches, "stopped": None})
        doc = self.doc()
        self.assertEqual((doc["version"], list(doc["routes"]), len(doc["history"])), ("contam-1", ["sail:pro_asap"], 1))
        row = doc["routes"]["sail:pro_asap"]
        self.assertEqual(set(row), {"at", "model", "usd", "probes", "attempted_at", "idle", "cells", "recall", "newly_recalled"})
        self.assertEqual((row["at"], row["attempted_at"], row["model"], row["probes"], row["idle"], row["usd"]),
                         (schedule.iso(self.clock()), schedule.iso(self.clock()), "pro_asap", 1, 0, out["usd"]))
        self.assertEqual({s: list(eras) for s, eras in row["cells"].items()}, {s: list(P.ERAS) for s in P.STRATA})
        for eras in row["cells"].values():
            for got in eras.values():
                self.assertEqual(set(got), set(P.CELL_KEYS))
                self.assertEqual((got["p_perm"], got["recalled"], got["skipped"]), (1.0, False, 0), "it always says higher")
        self.assertEqual(set(row["recall"]), set(P.RECALL_KEYS))
        self.assertEqual(doc["history"][0], {"route": "sail:pro_asap", "probe_n": 1, **{k: row[k] for k in
                                                                                       ("at", "model", "usd", "cells", "recall")}})
        self.assertEqual(stat.S_IMODE((self.root / P.FILE).stat().st_mode), 0o600)
        self.assertEqual(ctx.alerts, [])

    def test_each_call_is_one_route_one_role_and_a_key_of_its_own(self):
        self.probe()
        self.assertEqual(P.KEY_PREFIX, "swarm:elane:probe", "the equity lanes' mark in the swarm's spend rows")
        keys = []
        for call in self.router.calls:
            self.assertEqual((call["role"], call["system"], call["sail_profile"], call["openai_model"], call["claude"],
                              call["max_output"], call["effort"]), (P.ROLE, P.SYSTEM, "pro_asap", None, False, 2000, "low"))
            self.assertEqual(call["key"], f"swarm:elane:probe:sail:pro_asap:1:{hashlib.sha256(call['user'].encode()).hexdigest()[:12]}")
            keys.append(call["key"])
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(self.router.billed, keys)

    def test_the_dollars_are_booked_on_a_probe_row_inside_e2s_day_line(self):
        out, _ = self.probe()
        book = elane_yield.ledger(self.store)
        row = book["routes"]["probe:sail:pro_asap"]
        self.assertEqual((row["requests"], row["answered"], row["failed"]), (out["asked"], out["asked"], 0))
        self.assertAlmostEqual(row["usd"], out["usd"], places=6)
        self.assertAlmostEqual(elane_yield.spent_today(self.store, self.clock()), out["usd"], places=6)
        self.assertEqual(set(book["routes"]), {"probe:sail:pro_asap"}, "never on a birth route's row: no yield moves")

    def test_nothing_to_do(self):
        self.assertEqual(self.probe(settings_=settings(mode="off"))[0], {"status": "skipped", "why": "elane.contam.mode is off"})
        self.assertEqual(self.probe(settings_=settings(usd_run=0))[0]["status"], "skipped", "no dollar, no probe, no idle mark")
        self.assertFalse((self.root / P.FILE).exists())
        elane_yield.book(self.store, "sail:pro_asap", usd=8.0, known=True, purpose="research", answered=True, now=self.clock())
        out, _ = self.probe()
        self.assertEqual(out["status"], "skipped", "the day's $8 are spent")
        self.assertIn("elane.e2.usd_day", out["why"])
        self.assertEqual(self.router.calls, [])
        self.assertFalse((self.root / P.FILE).exists(), "a run that did not start marks no route")
        self.clock.advance(86400)   # the next UTC day: the line is whole
        for _ in ROUTES:
            self.assertTrue(self.probe()[0]["finished"])
            self.clock.advance(86400)
        self.assertEqual(self.probe()[0], {"status": "skipped", "why": "no route is due a probe"})
        no_routes = settings()
        no_routes["elane"]["e2"]["routes"] = ["claude:architect"]   # a Claude role this router does not serve
        self.assertEqual(self.probe(settings_=no_routes)[0]["status"], "skipped")

    def test_a_run_never_takes_more_than_e2s_day_has_left(self):
        """THE BOUND: min(`usd_run`, E2's room for the day). With $0.20 of the day's line left a $3 run spends $0.20
        and goes on the next week; it is not skipped for want of the whole $3."""
        elane_yield.book(self.store, "sail:pro_asap", usd=7.8, known=True, purpose="research", answered=True, now=self.clock())
        out, _ = self.probe()
        self.assertEqual((out["bound"], out["usd"], out["stopped"], out["finished"], out["asked"]), (0.2, 0.2, "usd", False, 4))
        self.assertAlmostEqual(elane_yield.spent_today(self.store, self.clock()), 8.0, places=6)
        self.assertEqual(self.probe()[0]["status"], "skipped", "the line is spent: the same day asks nothing more")
        self.assertEqual(len(self.router.calls), 4)
        self.clock.advance(WEEK)
        out, _ = self.probe()
        self.assertEqual((out["route"], out["bound"], out["finished"]), ("sail:pro_asap", 3.0, True))
        # A day line under `usd_run` (E2 holds its day to a share of the swarm's model line) still lets a probe move.
        small = settings()
        small["elane"]["e2"]["usd_day"] = 0.5
        self.clock.advance(86400)
        out, _ = self.probe(settings_=small)
        self.assertEqual((out["route"], out["bound"], out["stopped"]), ("sail:glm_asap", 0.5, "usd"))
        self.assertGreater(out["cells"], 0)

    def test_the_dollar_stop_leaves_a_partial_that_the_next_run_finishes(self):
        tight = settings(usd_run=0.3)
        first, _ = self.probe(settings_=tight)
        self.assertEqual((first["stopped"], first["finished"], first["asked"], first["usd"]), ("usd", False, 6, 0.3))
        row = self.doc()["routes"]["sail:pro_asap"]
        self.assertEqual((row["idle"], row["partial"]["probe_n"], row["partial"]["usd"]), (0, 1, 0.3))
        self.assertNotIn("at", row, "nothing is published before the probe is whole")
        done = [(s, e) for s, eras in row["partial"]["cells"].items() for e in eras]
        self.assertEqual(len(done), first["cells"])
        self.assertTrue(0 < len(done) < 12)
        runs = [first]
        while not runs[-1]["finished"]:
            self.clock.advance(WEEK)
            before = (len(self.router.calls), len(self.router.billed))
            out, _ = self.probe(settings_=tight)
            self.assertEqual(out["route"], "sail:pro_asap", "the probe under way goes on before another route starts")
            again = self.router.calls[before[0]:]
            self.assertEqual(len(again) - (len(self.router.billed) - before[1]), sum(c["key"] in self.router.billed[:before[1]]
                                                                                    for c in again))
            runs.append(out)
            self.assertLess(len(runs), 12)
        row = self.doc()["routes"]["sail:pro_asap"]
        self.assertNotIn("partial", row)
        self.assertEqual((row["probes"], row["idle"]), (1, 0))
        self.assertAlmostEqual(row["usd"], 0.05 * len(self.router.billed), places=6, msg="every batch was paid for once")
        self.assertAlmostEqual(sum(r["usd"] for r in runs), row["usd"], places=6)
        self.assertEqual(sum(r["cells"] for r in runs), 13)
        whole = ProbeRouter()
        self.root.joinpath(P.FILE).unlink()
        self.probe(router=whole)
        self.assertEqual(set(self.router.billed), set(whole.billed), "the same batches as one whole run asks")
        self.assertEqual(self.doc()["routes"]["sail:pro_asap"]["cells"], row["cells"], "and the same aggregates")

    def test_a_resumed_cell_re_reads_its_answered_batches_at_no_cost(self):
        """A stop in the middle of a cell: its answered batches are not in the partial (aggregates only); the next run
        asks them again under the same keys and the Provider answers from its store for nothing."""
        tight = settings(usd_run=0.05, batch=5)   # one billed batch a run; a 24-question cell is five batches
        tight["elane"]["e2"]["routes"] = ["sail:pro_asap"]
        first, _ = self.probe(settings_=tight)
        self.assertEqual((first["asked"], first["cells"], first["stopped"]), (1, 0, "usd"))
        row = self.doc()["routes"]["sail:pro_asap"]
        self.assertEqual((row["idle"], row["partial"]["cells"], row["partial"]["usd"]), (1, {}, 0.05),
                         "no cell yet; the dollars stay with the probe that spent them")
        self.clock.advance(WEEK)
        calls = len(self.router.calls)
        second, _ = self.probe(settings_=tight)
        again = self.router.calls[calls:]
        self.assertEqual(again[0]["key"], self.router.calls[0]["key"], "the first batch, asked again under its own key")
        self.assertEqual((second["asked"], second["usd"], len(self.router.billed)), (2, 0.05, 2), "one re-read free, one new")

    def test_the_time_stop_leaves_a_partial_too(self):
        ticks = iter([0.0] + [100.0] * 4 + [float(P.ASK_SECONDS)] * 50)
        out, _ = self.probe(clock=lambda: next(ticks))
        self.assertEqual((out["stopped"], out["finished"], out["asked"]), ("time", False, 4))
        self.assertIn("partial", self.doc()["routes"]["sail:pro_asap"])
        self.assertEqual(sum(len(e) for e in self.doc()["routes"]["sail:pro_asap"]["partial"]["cells"].values()), 1,
                         "three batches made the first cell; the fourth was the second cell's first")
        self.clock.advance(WEEK)
        calls = len(self.router.calls)
        out, _ = self.probe()
        self.assertEqual((out["finished"], out["route"]), (True, "sail:pro_asap"))
        self.assertEqual(self.router.calls[calls]["key"], self.router.calls[3]["key"], "the unfinished cell's batch again")
        self.assertEqual(out["usd"], round(0.05 * (out["asked"] - 1), 6), "and it cost nothing the second time")
        self.assertEqual(P.ASK_SECONDS, 2300)

    def test_a_second_probe_sends_new_keys_and_a_resumed_one_repeats_them(self):
        self.probe()
        first = [c["key"] for c in self.router.calls]
        self.assertTrue(all(k.startswith("swarm:elane:probe:sail:pro_asap:1:") for k in first))
        self.clock.advance(29 * 86400)
        for _ in ROUTES:   # the other two routes, then the first again: its second probe
            self.probe()
            self.clock.advance(86400)
        second = [c["key"] for c in self.router.calls if c["sail_profile"] == "pro_asap"][len(first):]
        self.assertEqual(len(second), len(first))
        self.assertTrue(all(k.startswith("swarm:elane:probe:sail:pro_asap:2:") for k in second))
        self.assertEqual([k.rsplit(":", 1)[1] for k in second], [k.rsplit(":", 1)[1] for k in first], "the same questions")
        self.assertFalse(set(first) & set(second), "asked afresh, and billed")
        self.assertEqual(self.doc()["routes"]["sail:pro_asap"]["probes"], 2)
        self.assertEqual(len(self.router.billed), 4 * len(first))

    def test_a_partial_made_on_another_question_set_is_dropped(self):
        first, _ = self.probe(settings_=settings(usd_run=0.3))
        self.assertTrue(self.doc()["routes"]["sail:pro_asap"]["partial"]["cells"])
        self.clock.advance(WEEK)
        out, _ = self.probe(settings_=settings(questions_per_cell=40))
        self.assertEqual((out["finished"], out["cells"]), (True, 13), "every cell asked again: none carried over")
        row = self.doc()["routes"]["sail:pro_asap"]
        self.assertGreater(row["cells"]["S4"]["2025"]["n"] + row["cells"]["S4"]["2025"]["ties"], 24)

    def test_a_route_that_cannot_answer_is_marked_first_and_does_not_block_the_others(self):
        error = RuntimeError("no such profile")
        error.billed = [{"cost_usd": 0.02}]
        self.router.fails["pro_asap"] = error
        out, ctx = self.probe()
        self.assertEqual((out["route"], out["stopped"], out["finished"], out["asked"], out["usd"]),
                         ("sail:pro_asap", "error", False, 0, 0.02))
        self.assertIn("RuntimeError", out["error"])
        row = self.doc()["routes"]["sail:pro_asap"]
        self.assertEqual((row["idle"], row["attempted_at"]), (1, schedule.iso(self.clock())))
        book = elane_yield.ledger(self.store)["routes"]["probe:sail:pro_asap"]
        self.assertEqual((book["failed"], book["usd"]), (1, 0.02), "what the failed call was billed is booked")
        self.assertEqual(ctx.alerts, [])
        order = []
        for _ in range(4):
            self.clock.advance(WEEK)
            out, ctx = self.probe()
            order.append((out["route"], out["finished"]))
        self.assertEqual(order, [("sail:glm_asap", True), ("sail:k3", True), ("sail:pro_asap", False),
                                 ("sail:pro_asap", False)], "the others are probed before it is tried again")
        row = self.doc()["routes"]["sail:pro_asap"]
        self.assertEqual(row["idle"], 3)
        self.assertEqual(ctx.alerts, [{"level": "warning", "text": "CP2: the contamination probe's route sail:pro_asap "
                                                                    "added no cell in its last 3 attempts"}])
        # Once the others are due again it is behind every one of them.
        self.clock.advance(28 * 86400)
        self.assertEqual(P.due(self.doc(), ROUTES, now=self.clock(), every_days=28), "sail:glm_asap")
        del self.router.fails["pro_asap"]
        out, ctx = self.probe(router=self.router)
        self.assertEqual(out["route"], "sail:glm_asap")

    def test_an_answer_another_profile_gave_is_no_answer_of_the_route(self):
        """The router's own window fallback (a Sail profile outside the asap window, its window stalled) answers on
        another profile, which may be another model: the probe of route A never scores what route B remembered."""
        self.router.moves["pro_asap"] = "glm_asap"
        out, ctx = self.probe()
        self.assertEqual((out["route"], out["stopped"], out["finished"], out["cells"], out["asked"], out["usd"]),
                         ("sail:pro_asap", "fallback", False, 0, 0, 0.05))
        self.assertIn("sail:glm_asap", out["error"])
        self.assertEqual(len(self.router.calls), 1, "the run ends at the first answer that is not the route's")
        book = elane_yield.ledger(self.store)["routes"]
        self.assertEqual(set(book), {"probe:sail:glm_asap"}, "the dollars, on the row of the route that answered")
        self.assertEqual((book["probe:sail:glm_asap"]["answered"], book["probe:sail:glm_asap"]["usd"]), (1, 0.05))
        self.assertAlmostEqual(elane_yield.spent_today(self.store, self.clock()), 0.05, places=6)
        row = self.doc()["routes"]["sail:pro_asap"]
        self.assertEqual((row["idle"], row["partial"]["cells"], row["partial"]["recall"], row["partial"]["model"]),
                         (1, {}, None, None), "no cell, no model named: nothing of the other profile's answer is kept")
        self.assertNotIn("at", row)
        self.assertEqual(ctx.alerts, [])
        # It goes to the back of the line; once its own profile answers, the same batch is asked under its own key.
        order = []
        for _ in range(2):
            self.clock.advance(WEEK)
            order.append(self.probe()[0]["route"])
        self.assertEqual(order, ["sail:glm_asap", "sail:k3"])
        del self.router.moves["pro_asap"]
        self.clock.advance(WEEK)
        out, _ = self.probe()
        self.assertEqual((out["route"], out["finished"], out["stopped"]), ("sail:pro_asap", True, None))
        row = self.doc()["routes"]["sail:pro_asap"]
        self.assertEqual((row["model"], row["idle"], row["probes"]), ("pro_asap", 0, 1))
        mine = [c["key"] for c in self.router.calls if c["sail_profile"] == "pro_asap"]
        self.assertEqual(mine[1], mine[0], "the batch the fallback answered, asked again of the route itself")
        self.assertAlmostEqual(row["usd"], 0.05 * (1 + out["asked"]), places=6, msg="the probe's dollars, the fallback's too")

    def test_a_fallback_that_names_the_routes_own_profile_is_the_routes_answer(self):
        only = settings()
        only["elane"]["e2"]["routes"] = ["sail:k3"]
        self.router.moves["k3"] = "k3"
        out, _ = self.probe(settings_=only)
        self.assertEqual((out["finished"], out["stopped"]), (True, None))
        self.assertEqual(set(elane_yield.ledger(self.store)["routes"]), {"probe:sail:k3"})
        self.assertEqual(self.doc()["routes"]["sail:k3"]["model"], "k3")

    def test_three_runs_a_fallback_answered_raise_cp2(self):
        only = settings()
        only["elane"]["e2"]["routes"] = ["sail:k3"]
        self.router.moves["k3"] = "pro_asap"
        alerts = []
        for _ in range(3):
            out, ctx = self.probe(settings_=only)
            self.assertEqual(out["stopped"], "fallback")
            alerts.append(ctx.alerts)
            self.clock.advance(WEEK)
        self.assertEqual(alerts[:2], [[], []])
        self.assertEqual(alerts[2], [{"level": "warning", "text": "CP2: the contamination probe's route sail:k3 added no "
                                                                   "cell in its last 3 attempts"}])
        self.assertEqual(len(self.router.billed), 1, "the fallback's stored answer is read again at no cost")
        self.assertAlmostEqual(elane_yield.ledger(self.store)["routes"]["probe:sail:pro_asap"]["usd"], 0.05, places=6)

    def test_the_stores_trouble_keeps_what_is_scored_and_books_what_was_billed(self):
        real, seen = P.truth, []

        def rewritten(store, question):
            if (question["stratum"], question["era"]) not in seen:
                seen.append((question["stratum"], question["era"]))
            if len(seen) > 2:
                raise MissingData("the equity store's SPY bars does not match its manifest")
            return real(store, question)
        with mock.patch.object(P, "truth", rewritten):
            out, _ = self.probe()
        self.assertEqual((out["stopped"], out["finished"], out["cells"]), ("data", False, 2))
        self.assertIn("MissingData", out["error"])
        row = self.doc()["routes"]["sail:pro_asap"]
        self.assertEqual(sum(len(e) for e in row["partial"]["cells"].values()), 2)
        self.assertAlmostEqual(elane_yield.ledger(self.store)["routes"]["probe:sail:pro_asap"]["usd"], out["usd"], places=6)
        self.clock.advance(WEEK)
        out, _ = self.probe()
        self.assertTrue(out["finished"])

    def test_the_probe_count_outlives_the_history(self):
        old = [{"route": "sail:k3", "probe_n": i, "at": schedule.iso(self.clock() - (40 - i) * 86400.0), "model": "k3",
                "usd": 0.1, "cells": {}, "recall": {}} for i in range(1, 25)]
        (self.root / P.FILE).write_text(json.dumps({"version": "contam-1", "history": old, "routes": {
            "sail:pro_asap": {"at": schedule.iso(self.clock() - 30 * 86400.0), "probes": 30, "idle": 0,
                              "attempted_at": schedule.iso(self.clock() - 30 * 86400.0), "model": "pro_asap", "usd": 1.0,
                              "cells": {}, "recall": {}}}}))
        only = settings()
        only["elane"]["e2"]["routes"] = ["sail:pro_asap"]
        out, _ = self.probe(settings_=only)
        self.assertEqual((out["probe"], out["finished"]), (31, True))
        doc = self.doc()
        self.assertEqual(doc["routes"]["sail:pro_asap"]["probes"], 31)
        self.assertEqual((len(doc["history"]), doc["history"][-1]["probe_n"], doc["history"][0]["probe_n"]), (24, 31, 2))
        self.assertTrue(all(c["key"].startswith("swarm:elane:probe:sail:pro_asap:31:") for c in self.router.calls))

    def test_a_model_that_recalls_the_market_is_read_as_recalling_it(self):
        table = self.oracle()
        out, ctx = self.probe(router=ProbeRouter(lambda text: table[text]))
        row = self.doc()["routes"]["sail:pro_asap"]
        recalled = sorted(f"{s}/{e}" for s, eras in row["cells"].items() for e, got in eras.items() if got["recalled"])
        self.assertTrue(recalled, row["cells"])
        self.assertEqual(sorted(row["newly_recalled"]), recalled, "its first probe: every recalled cell is new")
        for eras in row["cells"].values():
            for got in eras.values():
                self.assertEqual((got["acc"], got["correct"]), (1.0, got["n"]))
                self.assertEqual(got["recalled"], got["readable"], "a perfect answerer is recalled wherever a cell can show it")
        self.assertGreater(row["recall"]["rho"], 0.99)
        judged = [name for name in recalled if name.split("/")[1] in P.JUDGED_ERAS]
        self.assertEqual(ctx.alerts, [{"level": "info", "text": f"CP1: the contamination probe of route sail:pro_asap newly "
                                                               f"reads cell {name} as recalled"} for name in
                                      row["newly_recalled"] if name in judged])
        for alert in ctx.alerts:
            self.assertNotRegex(alert["text"], r"\d\.\d|%|\bbp\b", "ids, counts and names only")


class NoTruthLeavesTheHouse(Jobs):
    """T7."""

    def test_the_prompts_are_identical_whatever_the_prices(self):
        calls = {}
        for seed in (3, 4):
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            self.root = Path(tmp.name)
            self.store = SwarmStore(self.root, clock=self.clock)
            self.addCleanup(self.store.close)
            router = ProbeRouter()
            out, _ = self.probe(seed=seed, router=router)
            self.assertTrue(out["finished"])
            calls[seed] = [(c["system"], c["user"], c["key"], c["role"]) for c in router.calls]
            calls[seed, "cells"] = self.doc()["routes"]["sail:pro_asap"]["cells"]
        self.assertEqual(calls[3], calls[4], "the same requests, byte for byte, on two different markets")
        self.assertNotEqual(calls[3, "cells"], calls[4, "cells"], "and the markets really differ: the scores do")

    def test_a_prompt_carries_no_truth_and_no_score(self):
        table = self.oracle()
        router = ProbeRouter(lambda text: table[text])
        self.probe(router=router)
        store = self.equity()
        for call in router.calls:
            self.assertNotRegex(call["user"].split("\n\n", 1)[1], r"\d+\.\d|%", "no price, no return, no score")
        truths = [P.truth(store, q) for q in P.recall_questions()]
        for call in router.calls:
            for value in truths:
                self.assertNotIn(f"{value:.2f}", call["user"])

    def test_nothing_the_probe_writes_holds_a_per_question_truth_or_outcome(self):
        table = self.oracle()
        self.probe(router=ProbeRouter(lambda text: table[text]), settings_=settings(usd_run=0.3))   # a partial first
        partial = (self.root / P.FILE).read_text()
        self.clock.advance(WEEK)
        out, _ = self.probe(router=ProbeRouter(lambda text: table[text]))
        self.assertTrue(out["finished"])
        asked = [*P.questions(UNIVERSE, per_cell=24), *P.recall_questions()]

        def leaves(value, path=()):
            if isinstance(value, dict):
                for key, inner in value.items():
                    yield from leaves(inner, (*path, key))
            elif isinstance(value, list):
                for inner in value:
                    yield from leaves(inner, (*path, "[]"))
            else:
                yield path, value
        allowed = {*P.CELL_KEYS, *P.RECALL_KEYS, "version", "routes", "history", "at", "model", "usd", "probes",
                   "attempted_at", "idle", "cells", "recall", "partial", "probe_n", "qset", "route", "newly_recalled", "[]",
                   *ROUTES, *P.STRATA, *P.ERAS}
        for text in (partial, (self.root / P.FILE).read_text()):
            doc = json.loads(text)
            for path, value in leaves(doc):
                self.assertFalse(set(path) - allowed, path)
                self.assertNotIn(value, ("higher", "lower", "more", "less", "tie"), path)
            for q in asked:
                self.assertNotIn(q["id"], text)
                self.assertNotIn(q["text"], text)
            self.assertNotRegex(text, r'"\d{4}-(0[1-9]|1[0-2])(-\d{2})?"', "no period (a month or the day a week ends on)")
            self.assertNotRegex(text, r"\[(true|false|0|1)(, ?(true|false|0|1)){5,}\]", "no row of outcomes")
        # The swarm store: the ledger's dollars and counts, nothing of a question.
        dump = json.dumps({name: self.store._all(f"SELECT * FROM {name}") for name in
                           [r["name"] for r in self.store._all("SELECT name FROM sqlite_master WHERE type='table'")]}, default=str)
        for q in asked:
            self.assertNotIn(q["id"], dump)
            self.assertNotIn(q["text"], dump)
        for word in ("higher", "lower", '"more"', '"less"'):
            self.assertNotIn(word, dump)
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if not p.name.startswith("swarm.sqlite")),
                         sorted([P.FILE, self.store.programs.name, self.store.runs_dir.name]), "the one file it writes")

    def test_a_cells_truths_are_read_only_once_its_answers_are_in(self):
        events = []
        real_truth = P.truth

        def truth(store, question):
            events.append(("truth", question["stratum"], question["era"]))
            return real_truth(store, question)

        class Recording(ProbeRouter):
            def ask(inner, **kw):   # noqa: N805
                first = question_of(kw["user"].split("\n\n", 1)[1].splitlines()[0])
                events.append(("ask", first))
                return ProbeRouter.ask(inner, **kw)
        asked = P.questions(UNIVERSE, per_cell=24)
        cell_of = {q["text"]: (q["stratum"], q["era"]) for q in asked}
        with mock.patch.object(P, "truth", truth):
            self.probe(router=Recording())
        scored: set = set()
        for event in events:
            if event[0] == "truth":
                scored.add(event[1:])
            elif event[1] in cell_of:
                self.assertNotIn(cell_of[event[1]], scored, "a batch asked after its own cell's truths were read")
        self.assertEqual(len(scored), 13)


class TheJobsOwnParts(unittest.TestCase):
    """`run(ctx)` on a House state: what it opens, and what stops it before any route is marked or dollar spent."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.clock = fx.Clock()

    def ctx(self) -> Context:
        return Context("contam_probe", root=self.root, due_at=self.clock(), clock=self.clock, config={}, settings_value={})

    def on(self, **block) -> None:
        (self.root / "swarm.json").write_text(json.dumps({"elane": {"contam": {"mode": "record", **block}}}))

    def test_off_by_the_code_default(self):
        with mock.patch("league.swarm.settings.read_policy", lambda: ({}, {"read": "test"})):
            self.assertEqual(P.run(self.ctx()), {"status": "skipped", "why": "elane.contam.mode is off"})
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), [], "nothing opened, nothing written")

    def test_no_swarm_store_or_no_equity_store(self):
        self.on()
        self.assertEqual(P.run(self.ctx()), {"status": "skipped", "why": "no swarm store yet"})
        SwarmStore(self.root).close()
        out = P.run(self.ctx())
        self.assertEqual(out["status"], "failed")
        self.assertIn("MissingData", out["error"])
        synth.constant_store(self.root / STORE_DIR, gate=False)
        out = P.run(self.ctx())
        self.assertEqual(out["status"], "failed", "a store without the House's mark gives no capability")
        self.assertIn("StoreRefused", out["error"])
        self.assertFalse((self.root / P.FILE).exists(), "the House's own trouble marks no route")

    def test_it_builds_the_swarms_router_and_probes_the_house_universe(self):
        self.on(questions_per_cell=20, batch=40)
        SwarmStore(self.root).close()
        synth.synthetic_store(self.root / STORE_DIR, symbols=("SPY", "QQQ", "XLK", "AAPL"), seed=8, gate=True)
        # The calls cost nothing here: the run's dollar bound is E2's own day line as the swarm's settings give it
        # (policy.json and the budget's levers), which is not this test's to fix; the bound has its own tests above.
        router = ProbeRouter(cost=0.0)
        built = []

        def build(root, store, settings_, *, config=None):
            built.append((Path(root), config))
            return router
        with mock.patch("league.swarm.models.build_router", build):
            out = P.run(self.ctx())
        self.assertEqual(built, [(self.root, {})])
        self.assertEqual((out["finished"], out["stopped"], out["usd"]), (True, None, 0.0), out)
        self.assertGreater(out["bound"], 0.0)
        doc = json.loads((self.root / P.FILE).read_text())
        (route,) = doc["routes"]
        self.assertEqual(route, elane_yield.cfg(None)["routes"][0], "E2's first route, never tried")
        cells = doc["routes"][route]["cells"]
        self.assertEqual(cells["S3"]["2025"]["symbols"], 8, "the House universe (league/ops/equity_data.py), not a setting")
        self.assertEqual(cells["S1"]["2025"]["symbols"], 4)
        db = sqlite3.connect(self.root / "swarm.sqlite")
        self.addCleanup(db.close)
        ledger = json.loads(db.execute("SELECT value FROM kv WHERE key=?", (elane_yield.LEDGER_KEY,)).fetchone()[0])
        self.assertEqual(list(ledger["routes"]), [f"probe:{route}"])


if __name__ == "__main__":
    unittest.main()
