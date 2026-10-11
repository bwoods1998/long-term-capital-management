"""THE PROBE'S PANEL STRATA P4-P6 AND THE LOOK'S PERMIT (release E4, package B's patch 18; league/ops/contam_xs.py and
the plan seam of league/ops/contam_probe.py; the captain's A22 (3): the contamination probe before a panel look).

- `TheWords`: the three strata's questions are the probe's own words over names and the calendar, a full grid under
  E3's hash rule, and a plan cannot put a figure in a prompt.
- `ThePlan`: the periods a panel stratum may ask (never 2016, 2020 or 2021, by base or by end), the members asked
  about (in the index through the era), the truth of a member against its sector's fund and of the House panel
  factors (held to a real run's own `factors`), and the seal: a 2025 or 2026 truth opens only for the gate.
- `TheJob`: a route's published result carries the three strata beside E3's cells, which are byte for byte what they
  were; the permit holds two words a cell and no figure, and `elane_xs.probed` opens on it; every request key is
  new; the run's dollars are capped as shipped; truths are read after answers; nothing written holds a truth.
- `TheHousesJob`: `contam_xs.run` on a House state: release E3's probe with the lane off or no panel store; the
  strata and the permit with them; a panel store that cannot be read fails before any route is marked; a wall skips.
- `TheWiring`: the registry's row, the constants held equal, and the seals (the probe imports nothing of league/xs;
  no sealed tree imports this module).

The panel is package C's synthetic one (seeded noise on the true calendar, made-up tickers) and the router is
scripted: every price, member, answer and dollar here is invented. No model is called and no network is used."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from league.equity.store import (STORE_DIR, EquityStore, MissingData, StoreRefused, from_ordinal,
                                 mint_equity_gate_capability, ordinal)
from league.ops import contam_probe as P
from league.ops import contam_xs as X
from league.ops import equity_data, registry, schedule
from league.ops.context import Context
from league.swarm import elane_xs, elane_yield
from league.swarm.store import SwarmStore
from league.tests import elane_e2_fakes as fx
from league.tests import test_e3_seal_imports as seal
from league.tests.test_contam_probe import ROUTES, WEEK, ProbeRouter, question_of
from league.xs import config as xs_config
from league.xs import ctx as xs_ctx
from league.xs import runner as xs_runner
from league.xs import store as xs_store
from league.xs import synth as xs_synth

REPO = Path(__file__).resolve().parents[2]
#: E3's strata are asked of these (the synthetic panel's own E1 store holds the REF symbols).
UNIVERSE = {"SPY": "etf", "XLK": "etf", "XLF": "etf"}
ASSETS = 40
#: One asset of the synthetic panel is masked and one loses its bars while still a member.
MASKED_AID = xs_store.FIRST_MEMBER_AID + 3
VANISHED_AID = xs_store.FIRST_MEMBER_AID + 5
VANISHED_LAST = dt.date(2026, 2, 27)
RESERVE_AND_HISTORY = (2016, 2020, 2021)
CASH = ('NEEDS = {"panel": "sp500", "history": 20, "max_names": 5, "rebalance": "monthly"}\nPARAMS = {}\n\n\n'
        'def decide(ctx):\n    return {"target": {}, "at": "open"}\n')


def settings(panel_mode: str | None = None, **contam) -> dict:
    block = {"mode": "record", "usd_run": 3.0, "batch": 10, "questions_per_cell": 24, "every_days": 28, **contam}
    lane: dict = {"mode": "gate", "contam": block, "e2": {"routes": list(ROUTES), "usd_day": 8.0}}
    if panel_mode is not None:
        lane["panel"] = {"mode": panel_mode}
    return {"elane": lane}


class FakePlan:
    """A plan of names and periods only (no store): what `panel_questions` asks of one."""

    def __init__(self, names=("ZQAA", "ZQAB"), periods=None, truths=None):
        self._names, self._periods, self._truths = list(names), periods, truths
        self.published_docs: list = []

    def names(self, stratum, era):
        return list(self._names)

    def periods(self, stratum, era):
        if self._periods is not None:
            return list(self._periods.get((stratum, era), ()))
        return [name for name, _, _ in P.periods(stratum, era)][:8]

    def truths(self, questions):
        return [self._truths(q) if self._truths else "more" for q in questions]

    def published(self, doc):
        self.published_docs.append(json.loads(json.dumps(doc)))


#: The module's synthetic panels, written once (`setUpModule`): "a" and "b" hold ONE membership (the same seed) under
#: different prices; "v" is "a" with one asset masked and one whose bars end while it is still a member.
PANELS: dict[str, Path] = {}
_TMP: list = []


def setUpModule():
    tmp = tempfile.TemporaryDirectory()
    _TMP.append(tmp)
    made = dict(n_assets=ASSETS, seed=7, gate=True)
    PANELS["a"] = xs_synth.synthetic_panel(Path(tmp.name) / "a" / STORE_DIR, vol=0.25, **made)
    PANELS["b"] = xs_synth.synthetic_panel(Path(tmp.name) / "b" / STORE_DIR, vol=0.40, drift=0.07, **made)
    PANELS["v"] = xs_synth.synthetic_panel(Path(tmp.name) / "v" / STORE_DIR, vol=0.25, masked={MASKED_AID: "no_bars"},
                                           vanish=[(VANISHED_AID, VANISHED_LAST)], **made)


def tearDownModule():
    PANELS.clear()
    while _TMP:
        _TMP.pop().cleanup()


class Panels(unittest.TestCase):
    """The module's synthetic panels, each with the House's mark."""

    panels = PANELS

    def capability(self, which: str = "a"):
        return mint_equity_gate_capability(self.panels[which], P.GATE_REASON)

    def panel(self, which: str = "a", *, gate: bool = True) -> xs_store.PanelStore:
        return xs_store.PanelStore(self.panels[which], gate=self.capability(which) if gate else None)

    def plan(self, which: str = "a", *, gate: bool = True, root=None) -> X.Plan:
        return X.Plan(self.panel(which, gate=gate), root)

    @staticmethod
    def cells(questions) -> dict:
        out: dict = {}
        for q in questions:
            out.setdefault((q["stratum"], q["era"]), []).append(q)
        return out


# ====================================================================================================== the words
class TheWords(unittest.TestCase):
    def test_the_three_strata_are_the_ones_the_look_reads(self):
        self.assertEqual(P.PANEL_STRATA, elane_xs.PROBE_STRATA)
        self.assertEqual(P.STRATA, ("S1", "S2", "S3", "S4"), "E3's own strata are what they were")
        self.assertFalse(set(P.PANEL_STRATA) & set(P.STRATA))
        self.assertEqual({s: P.WORDS[s] for s in P.PANEL_STRATA}, {s: ("more", "less") for s in P.PANEL_STRATA})
        self.assertEqual((P.WEEKLY, P.FACTORS), (("S4", "P5"), ("mom", "strev", "beta")))
        for era in P.ERAS:
            self.assertEqual(P.periods("P4", era), P.periods("S1", era), "a month is a month")
            self.assertEqual(P.periods("P6", era), P.periods("S1", era))
            self.assertEqual(P.periods("P5", era), P.periods("S4", era), "a week is a week")
        with self.assertRaises(KeyError):
            P.periods("P7", "2025")

    def test_every_word_of_a_question_is_the_probes(self):
        asked = P.panel_questions(FakePlan(), per_cell=24)
        self.assertEqual(list(dict.fromkeys((q["stratum"], q["era"]) for q in asked)),
                         [(s, e) for s in P.PANEL_STRATA for e in P.ERAS], "a fixed order: stratum, then era")
        self.assertEqual(set(asked[0]), {"id", "stratum", "era", "symbol", "against", "first", "last", "period", "text"})
        self.assertEqual(len({q["id"] for q in asked}), len(asked))
        by = {(q["stratum"], q["symbol"]): q for q in asked if q["era"] == "2025"}
        p4, p5 = by["P4", "ZQAA"], by["P5", "ZQAB"]
        month = f"{P.MONTHS[int(p4['period'][5:7]) - 1]} {p4['period'][:4]}"
        self.assertEqual(p4["text"], f"Did ZQAA return more or less than the Select Sector SPDR fund of its sector in {month}?")
        self.assertEqual(p5["text"], "Did ZQAB return more or less than the Select Sector SPDR fund of its sector in the "
                                     f"week ending {p5['period']}?")
        self.assertEqual((p5["last"], p4["against"], p5["against"]), (p5["period"], None, None))
        texts = {}
        for name in P.FACTORS:
            q = by["P6", name]
            month = f"{P.MONTHS[int(q['period'][5:7]) - 1]} {q['period'][:4]}"
            top, bottom = P.FACTOR_WORDS[name]
            self.assertEqual(q["text"], f"In {month}, did the equally weighted third of S&P 500 stocks {top} return "
                                        f"more or less than the third {bottom}?")
            texts[name] = q["text"].replace(month, "")
        self.assertEqual(len(set(texts.values())), 3, "three factors, three questions")
        for q in asked:
            self.assertNotRegex(q["text"], r"\d+\.\d|%", "no price, no return")
            words = q["text"].replace(q["period"], "").replace(q["period"][:4], "").replace("S&P 500", "")
            self.assertNotRegex(words, r"\d", "the only digits of a question are its period's (and the index's name)")
            self.assertLess(q["first"], q["last"])

    def test_a_cell_is_a_full_grid_under_e3s_hash_rule(self):
        names = [f"ZQ{a}{b}" for a in "ABC" for b in "ABCDE"]
        asked = P.panel_questions(FakePlan(names=names, periods={(s, e): [n for n, _, _ in P.periods(s, e)]
                                                                 for s in P.PANEL_STRATA for e in P.ERAS}), per_cell=48)

        def order(items, stratum, era):
            return sorted(items, key=lambda x: hashlib.sha256(f"contam-1|{stratum}|{era}|{x}".encode()).hexdigest())
        for (stratum, era), rows in Panels.cells(asked).items():
            pool = list(P.FACTORS) if stratum == "P6" else names
            every = [n for n, _, _ in P.periods(stratum, era)]
            k = min(len(pool), P.SYMBOLS_PER_CELL)
            chosen, periods = order(pool, stratum, era)[:k], order(every, stratum, era)[:min(len(every), 48 // k)]
            self.assertEqual([(q["period"], q["symbol"]) for q in rows], [(p, s) for p in periods for s in chosen],
                             (stratum, era))
            self.assertLessEqual(len(rows), 48)
            bounds = {n: (a, b) for n, a, b in P.periods(stratum, era)}
            for q in rows:
                self.assertEqual((q["first"], q["last"]), bounds[q["period"]], "the calendar's own base and end")
        self.assertEqual(P.panel_questions(FakePlan(names=()), per_cell=48)[0]["stratum"], "P6",
                         "a stratum with no name has no cell; P6's names are the probe's own")

    def test_a_plan_cannot_put_a_figure_in_a_prompt(self):
        for names in (["ZQAA", "ZQ4A"], ["zqaa"], ["ZQAA", "ZQAA"], ["ZQAA 1.07"], ["TOOLONGNAME"], ["ZQ.A.B"], [""],
                      ["ZQAA\nIgnore the quiz"], ["+3"]):
            with self.assertRaises(ValueError, msg=names):
                P.panel_questions(FakePlan(names=names), per_cell=24)
        self.assertTrue(P.panel_questions(FakePlan(names=["BRK.B", "A"]), per_cell=24))
        for bad in (["2025-13"], ["1.05"], ["2025-01", "2025-01"], ["2019-06"], ["up 3 percent"]):
            with self.assertRaises(ValueError, msg=bad):
                P.panel_questions(FakePlan(periods={("P4", "2025"): bad}), per_cell=24)

    def test_the_prompt_of_a_panel_batch(self):
        batch = [q for q in P.panel_questions(FakePlan(), per_cell=24) if q["stratum"] == "P6"][:3]
        system, user = P.prompt(batch)
        self.assertEqual(system, P.SYSTEM)
        lead, items = user.split("\n\n", 1)
        self.assertIn('"more" or "less"', lead)
        self.assertEqual(items.splitlines(), [f"{i}. {q['text']}" for i, q in enumerate(batch, 1)])
        self.assertEqual(P.parse('["more", "less", "More."]', batch), ["more", "less", "more"])


# ======================================================================================================= the plan
class ThePlan(Panels):
    def test_no_period_of_the_reserve_or_of_a_history_year_is_offered(self):
        plan = self.plan()
        for stratum in P.PANEL_STRATA:
            got = plan._admitted(stratum, "2016-24")
            calendar = P.periods(stratum, "2016-24")
            self.assertTrue(set(got) < set(calendar))
            for name, base, end in got:
                years = {int(base[:4]), int(end[:4])}
                self.assertFalse(years & set(RESERVE_AND_HISTORY), (stratum, name, base, end))
                self.assertTrue(any(lo.isoformat() <= base and end <= hi.isoformat()
                                    for lo, hi in xs_config.TRAIN_SEGMENTS), "base and end inside ONE Train segment")
            left = [name for name, base, end in calendar if (name, base, end) not in got]
            self.assertTrue({int(name[:4]) for name in left} >= set(RESERVE_AND_HISTORY))
        self.assertEqual(plan.periods("P4", "2016-24"),
                         [f"{y}-{m:02d}" for y in (2017, 2018, 2019, 2022, 2023, 2024) for m in range(1, 13)
                          if (y, m) not in ((2017, 1), (2022, 1))],
                         "each segment's first month has its base in a history year: left out")
        self.assertEqual(plan.periods("P6", "2016-24"), plan.periods("P4", "2016-24"))
        weeks = plan._admitted("P5", "2016-24")
        self.assertEqual((weeks[0], weeks[-1]), (("2017-01-13", "2017-01-06", "2017-01-13"),
                                                 ("2024-12-27", "2024-12-20", "2024-12-27")))
        for era in ("2025", "2026H1"):
            for stratum in P.PANEL_STRATA:
                self.assertEqual(plan.periods(stratum, era), [name for name, _, _ in P.periods(stratum, era)], (stratum, era))
        self.assertEqual({e: [plan.periods(s, e) for s in P.PANEL_STRATA] for e in P.ERAS},
                         {e: [self.plan("b").periods(s, e) for s in P.PANEL_STRATA] for e in P.ERAS},
                         "the calendar and the lane's constants, whatever the prices")

    def test_the_members_asked_about_were_in_the_index_through_the_era(self):
        plan, universe = self.plan("v"), self.panel("v").universe()
        seen = set()
        for era in P.ERAS:
            names = plan.names("P4", era)
            self.assertEqual(names, plan.names("P5", era), "one pool for the month and the week")
            self.assertEqual(plan.names("P6", era), [], "P6 asks about no member")
            self.assertEqual(names, sorted(set(names)))
            months = plan._admitted("P4", era)
            days = sorted({base for _, base, _ in months} | {months[-1][2]})
            first, last = dt.date.fromisoformat(days[0]), dt.date.fromisoformat(days[-1])
            for day in days:
                today = {symbol for _, symbol in universe.members(dt.date.fromisoformat(day))}
                self.assertTrue(set(names) <= today, (era, day))
            left = {symbol for aid, symbol in universe.members(first) if not universe.member(aid, last)}
            joined = {symbol for aid, symbol in universe.members(last) if not universe.member(aid, first)}
            self.assertFalse(set(names) & (left | joined))
            seen |= left | joined
            self.assertNotIn(universe.symbol(MASKED_AID, last), names, "a masked asset is asked about by nobody")
            for name in names:
                self.assertRegex(name, P.NAME)
        self.assertTrue(seen, "the synthetic index does change: the rule above was exercised")
        self.assertEqual({e: self.plan("b").names("P4", e) for e in P.ERAS},
                         {e: self.plan("a").names("P4", e) for e in P.ERAS}, "membership and nothing of a price")
        self.assertEqual({e: set(self.plan("a").names("P4", e)) - set(plan.names("P4", e)) for e in P.ERAS},
                         {e: {universe.symbol(MASKED_AID, VANISHED_LAST)} for e in P.ERAS}, "the mask is the one difference")

    def closes(self, which: str = "a"):
        """The panel's valid adjustment=all closes straight off its files (a test's own read of a synthetic store):
        (days, {aid: column}, closes (n, m) with NaN where the bar is not valid)."""
        folder = self.panels[which] / xs_store.PANEL_DIR
        days = [from_ordinal(int(d)) for d in np.load(folder / "days.npy")]
        raw, adj = np.load(folder / "raw.npy"), np.load(folder / "adj.npy")
        with np.errstate(invalid="ignore"):
            ok = (raw[:, :, 3] > 0) & (raw[:, :, 4] > 0) & np.isfinite(adj[:, :, 3]) & (adj[:, :, 3] > 0)
        return days, {int(a): j for j, a in enumerate(np.load(folder / "aids.npy").tolist())}, np.where(ok, adj[:, :, 3], np.nan)

    def test_the_truth_of_a_member_against_its_sectors_fund(self):
        plan, universe = self.plan(), self.panel().universe()
        days, column, closes = self.closes()
        index = {d.isoformat(): i for i, d in enumerate(days)}
        funds = list(xs_config.FUND_COLUMNS)
        seen = set()
        for (stratum, era), rows in self.cells(P.panel_questions(plan, per_cell=24)).items():
            if stratum == "P6":
                continue
            got = plan.truths(rows)
            for q, truth in zip(rows, got):
                i0, i1 = index[q["first"]], index[q["last"]]
                col = column[universe.aid(q["symbol"], dt.date.fromisoformat(q["first"]))]
                window = slice(i0 + 1 - xs_config.DERIVE_SESSIONS, i0 + 1)
                _, _, sector = xs_ctx.characteristics(closes[window][:, [col]], closes[window, xs_config.MARKET_COLUMN],
                                                      closes[window][:, funds])
                fund = funds[int(sector[0])]
                gap = closes[i1, col] / closes[i0, col] - closes[i1, fund] / closes[i0, fund]
                self.assertEqual(truth, "more" if gap > 0 else "less", q["id"])
                seen.add((stratum, era, truth))
        self.assertEqual(seen, {(s, e, w) for s in ("P4", "P5") for e in P.ERAS for w in ("more", "less")})

    def test_a_zero_is_a_tie_and_a_missing_figure_is_none(self):
        self.assertEqual([X._word(g) for g in (0.25, -1e-12, 0.0, float("nan"), None)], ["more", "less", "tie", None, None])
        plan, universe = self.plan("v"), self.panel("v").universe()
        gone = universe.symbol(VANISHED_AID, VANISHED_LAST)
        self.assertIn(gone, plan.names("P4", "2026H1"), "still a member: its bars ended")
        asked = {q["period"]: q for q in P.panel_questions(plan, per_cell=200) if (q["stratum"], q["era"]) == ("P4", "2026H1")}
        rows = [{**asked[month], "symbol": gone} for month in ("2026-02", "2026-03", "2026-04")]
        self.assertEqual([t in ("more", "less") for t in plan.truths(rows)], [True, False, False],
                         "no close at the end, then none at the base either")
        stranger = [{**asked["2026-02"], "symbol": "ZQZZ"}, {**asked["2026-02"], "symbol": universe.symbol(MASKED_AID, VANISHED_LAST)}]
        self.assertEqual(plan.truths(stranger), [None, None], "a name the plan never offered has no truth")
        self.assertEqual(X.thirds([1.0, 2.0], [True, True]), None, "a third would be empty")
        low, high = X.thirds([3.0, float("nan"), 1.0, 2.0, 2.0, 9.0, 5.0], [True, True, True, True, True, False, True])
        self.assertEqual((low.tolist(), high.tolist()), ([2], [6]), "five ranked names: ascending by (value, column)")

    def test_the_panel_factors_are_a_run_records_own(self):
        """P6's truth is the House panel factor as league/xs/engine.py writes it beside a run: a real run of a
        monthly program that holds cash, over 2023, against `factor_days` month by month, to the engine's rounding."""
        store = self.panel(gate=False)
        bars = store.train(dt.date(2023, 1, 3), dt.date(2023, 12, 29), history=20, run_key="conformance").bars
        result = xs_runner.run_bars(CASH, {}, bars)
        self.assertEqual(result["status"], "ok")
        days = [from_ordinal(int(d)) for d in bars.days]
        rows = {row[0]: row for row in result["factors"]}
        sums: dict = {}
        compared, j = 0, int(bars.first)
        while j < bars.n:
            k = j
            while k + 1 < bars.n and days[k + 1].month == days[j].month:
                k += 1
            mine = X.factor_days(bars, j - 1, k)
            for offset, i in enumerate(range(j, k + 1)):
                for position, name in ((2, "mom"), (3, "strev"), (4, "beta")):
                    self.assertAlmostEqual(mine[name][offset], rows[days[i].isoformat()][position], places=9)
                    compared += 1
            for name in P.FACTORS:
                sums[f"{days[j].year}-{days[j].month:02d}", name] = math.fsum(mine[name])
            j = k + 1
        self.assertEqual(compared, 3 * (bars.n - int(bars.first)))
        self.assertTrue(any(value != 0 for value in sums.values()))
        # And the plan's own truths of those months (its own slices, another run key) are the signs of the sums.
        plan = self.plan(gate=False)
        calendar = {name: (a, b) for name, a, b in P.periods("P6", "2016-24")}
        asked = [{"id": f"P6|2016-24|{name}|{month}", "stratum": "P6", "era": "2016-24", "symbol": name, "against": None,
                  "first": calendar[month][0], "last": calendar[month][1], "period": month, "text": ""}
                 for month, name in sums if month != "2023-01"]
        got = plan.truths(asked)
        self.assertEqual(got, ["more" if sums[q["period"], q["symbol"]] > 0 else "less" for q in asked])
        self.assertEqual(set(got), {"more", "less"})

    def test_a_2025_or_2026_truth_opens_only_for_the_gate(self):
        plain, cells = self.plan(gate=False), self.cells(P.panel_questions(self.plan(), per_cell=24))
        for stratum in P.PANEL_STRATA:
            for era in ("2025", "2026H1"):
                with self.assertRaises(StoreRefused, msg=(stratum, era)):
                    plain.truths(cells[stratum, era])
            self.assertEqual(plain.truths(cells[stratum, "2016-24"]), self.plan().truths(cells[stratum, "2016-24"]),
                             "a Train period needs no capability")
        gated = self.plan()
        for era in ("2025", "2026H1"):
            self.assertTrue(all(t in ("more", "less") for t in gated.truths(cells["P6", era])))
        with self.assertRaises(StoreRefused):
            X.Plan(xs_store.PanelStore(self.panels["a"], gate=self.capability("b")))

    def test_no_row_of_the_reserve_or_of_a_history_year_is_asked_for(self):
        """Every slice a truth reads names its run sessions; none lies in 2016, 2020 or 2021, a Train one lies inside
        ONE Train segment, and every other one is the sealed "look" window's."""
        plan = self.plan()
        asked: list = []
        train, bars = plan.store.train, plan.store.bars

        def spy_train(start, end, **kw):
            asked.append(("train", start, end))
            return train(start, end, **kw)

        def spy_bars(window, **kw):
            asked.append((window, kw["start"], kw["end"]))
            return bars(window, **kw)
        plan.store.train, plan.store.bars = spy_train, spy_bars
        for rows in self.cells(P.panel_questions(plan, per_cell=24)).values():
            plan.truths(rows)
        self.assertEqual({window for window, _, _ in asked}, {"train", "look"})
        for window, start, end in asked:
            self.assertFalse({start.year, end.year} & set(RESERVE_AND_HISTORY), (window, start, end))
            if window == "train":
                self.assertTrue(any(lo <= start <= end <= hi for lo, hi in xs_config.TRAIN_SEGMENTS))
            else:
                self.assertTrue(dt.date(2024, 12, 31) <= start < end <= dt.date(2026, 6, 30))
        # A period the plan never offered has no truth, and no slice is read for it.
        asked.clear()
        calendar = {name: (a, b) for name, a, b in P.periods("P4", "2016-24")}
        name = plan.names("P4", "2016-24")[0]
        never = [{"stratum": "P4", "era": "2016-24", "symbol": name, "period": month, "first": calendar[month][0],
                  "last": calendar[month][1]} for month in ("2016-06", "2017-01", "2020-03", "2021-05", "2022-01")]
        self.assertEqual(plan.truths(never), [None] * 5)
        self.assertEqual(asked, [])


# ======================================================================================================== the job
class Jobs(Panels):
    def setUp(self):
        self.clock = fx.Clock()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.router = ProbeRouter()
        self.settings = settings()

    def probe(self, *, which: str = "a", settings_=None, router=None, plan="real", root=None):
        root = root or self.root
        store = self.store if root == self.root else SwarmStore(root, clock=self.clock)
        if store is not self.store:
            self.addCleanup(store.close)
        ctx = Context("contam_probe", root=root, due_at=self.clock(), clock=self.clock, config={}, settings_value={})
        if plan == "real":
            plan = self.plan(which, root=root)
        out = P.Probe(ctx, store=store, settings=settings_ or self.settings, router=router or self.router,
                      equity=EquityStore(self.panels[which], gate=self.capability(which)), symbols=UNIVERSE,
                      clock=lambda: 0.0, panel=plan).run()
        return out, ctx

    def doc(self, root=None) -> dict:
        return json.loads(((root or self.root) / P.FILE).read_text())

    def permit(self) -> dict:
        return json.loads((self.root / elane_xs.PROBE_FILE).read_text())

    def oracle(self, which: str = "a") -> dict:
        """question text -> its truth on a market (a model that recalls everything)."""
        equity, plan = EquityStore(self.panels[which], gate=self.capability(which)), self.plan(which)
        table = {q["text"]: P.truth(equity, q) for q in P.questions(UNIVERSE, per_cell=24)}
        table.update({q["text"]: round(P.truth(equity, q)) for q in P.recall_questions()})
        for rows in self.cells(P.panel_questions(plan, per_cell=24)).values():
            table.update({q["text"]: t for q, t in zip(rows, plan.truths(rows))})
        return table


class TheJob(Jobs):
    def test_a_published_result_carries_the_three_strata_and_the_permit_opens_the_look(self):
        out, ctx = self.probe()
        self.assertEqual((out["finished"], out["stopped"], out["panel"], out["permit"]), (True, None, 9, True), out)
        row = self.doc()["routes"]["sail:pro_asap"]
        self.assertEqual({s: list(row["cells"][s]) for s in P.PANEL_STRATA}, {s: list(P.ERAS) for s in P.PANEL_STRATA})
        for stratum in P.PANEL_STRATA:
            for cell in row["cells"][stratum].values():
                self.assertEqual(set(cell), set(P.CELL_KEYS), "E3's own shape: aggregates only")
                self.assertEqual((cell["p_perm"], cell["recalled"], cell["skipped"]), (1.0, False, 0), "it always says more")
        self.assertEqual(out["cells"], sum(len(eras) for eras in row["cells"].values()) + 1)
        self.assertEqual(ctx.alerts, [])
        self.assertNotIn("partial", row)
        # THE PERMIT: the route's `at` and model, and two words a cell of the three strata.
        permit = self.permit()
        self.assertEqual(permit, {"version": "xs-look-permit-1", "routes": {"sail:pro_asap": {
            "at": row["at"], "model": "pro_asap",
            "cells": {s: {e: {"readable": row["cells"][s][e]["readable"], "recalled": False} for e in P.ERAS}
                      for s in P.PANEL_STRATA}}}})
        self.assertEqual(stat.S_IMODE((self.root / elane_xs.PROBE_FILE).stat().st_mode), 0o600)
        # ... which is what the look's gate reads (league/swarm/elane_xs.py `probed`: None opens the look).
        self.assertIsNone(elane_xs.probed(self.root, {"spec": {"e2_route": "sail:pro_asap"}}))
        self.assertIn("no published result", elane_xs.probed(self.root, {"spec": {"e2_route": "sail:glm_asap"}}))
        reading = elane_xs.probe_reading(self.root, "sail:pro_asap")
        self.assertEqual((reading["at"], sorted(reading["strata"])), (row["at"], list(P.PANEL_STRATA)))

    def test_e3s_own_cells_are_byte_for_byte_what_they_were(self):
        with_plan, _ = self.probe()
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        plain_router = ProbeRouter()
        without, _ = self.probe(plan=None, router=plain_router, root=Path(other.name))
        self.assertNotIn("panel", without)
        self.assertNotIn("permit", without)
        mine, theirs = self.doc()["routes"]["sail:pro_asap"], self.doc(Path(other.name))["routes"]["sail:pro_asap"]
        self.assertEqual(list(theirs["cells"]), ["S1", "S2", "S4"], "this universe holds no stock: S3 has no cell")
        self.assertEqual(json.dumps({s: mine["cells"][s] for s in theirs["cells"]}, sort_keys=True),
                         json.dumps(theirs["cells"], sort_keys=True))
        self.assertEqual(sorted(mine["cells"]), [*P.PANEL_STRATA, "S1", "S2", "S4"])
        self.assertEqual((mine["recall"], mine["at"], mine["model"]), (theirs["recall"], theirs["at"], theirs["model"]))
        self.assertFalse((Path(other.name) / elane_xs.PROBE_FILE).exists(), "no plan, no permit")
        # E3's requests are the very same, in the same order; the panel's come after them and before the recall.
        def sent(router):
            return [(c["system"], c["user"]) for c in router.calls]
        e3 = sent(plain_router)
        self.assertEqual([call for call in sent(self.router) if call in e3], e3)
        kinds = ["panel" if "Select Sector SPDR" in user or "equally weighted third" in user
                 else ("recall" if "total return" in user else "e3") for _, user in sent(self.router)]
        self.assertEqual(kinds, sorted(kinds, key=("e3", "panel", "recall").index))
        self.assertEqual(kinds.count("panel"), len(self.router.calls) - len(plain_router.calls))

    def test_the_permit_holds_two_words_a_cell_and_no_figure(self):
        table = self.oracle()
        self.probe(router=ProbeRouter(lambda text: table[text]))

        def leaves(value, path=()):
            if isinstance(value, dict):
                for key, inner in value.items():
                    yield from leaves(inner, (*path, key))
            else:
                yield path, value
        text = (self.root / elane_xs.PROBE_FILE).read_text()
        allowed = {"version", "routes", "sail:pro_asap", "at", "model", "cells", *P.PANEL_STRATA, *P.ERAS, "readable", "recalled"}
        for path, value in leaves(json.loads(text)):
            self.assertFalse(set(path) - allowed, path)
            if path[-1] in ("readable", "recalled"):
                self.assertIsInstance(value, bool)
            else:
                self.assertIsInstance(value, str, "the version, when it was published, and the model's name")
        bare = re.sub(r'"at": "[^"]*"', "", text)
        for name in ("xs-look-permit-1", *P.PANEL_STRATA, "2016-24", "2026H1", "2025"):
            bare = bare.replace(name, "")
        self.assertNotRegex(bare, r"\d", "no count, no rate, no p: the only digits are in the names and the time")
        for stratum in P.STRATA:
            self.assertNotIn(f'"{stratum}"', text, "nothing of E3's own strata")
        # A probe file with figures in its panel cells gives the same two words and nothing else.
        doc = self.doc()
        doc["routes"]["sail:glm_asap"] = {"model": "x", "cells": doc["routes"]["sail:pro_asap"]["cells"]}   # not published
        doc["routes"]["sail:k3"] = {"at": "2026-10-03T00:20:00Z", "model": "k3",                           # one stratum short
                                    "cells": {s: doc["routes"]["sail:pro_asap"]["cells"][s] for s in ("P4", "P5", "S1")}}
        self.assertEqual(X.permit(doc), json.loads(text))
        self.assertEqual(X.permit(None), {"version": elane_xs.PROBE_VERSION, "routes": {}})
        self.assertEqual(X.permit({"routes": {"r": {"at": "t", "cells": {s: {} for s in P.PANEL_STRATA}}}})["routes"], {},
                         "a stratum with no cell is no stratum")

    def test_every_request_key_is_new_and_the_dollars_are_capped_as_shipped(self):
        tight = settings(usd_run=0.3)
        runs = [self.probe(settings_=tight)[0]]
        self.assertEqual((runs[0]["stopped"], runs[0]["finished"], runs[0]["usd"], runs[0]["bound"]), ("usd", False, 0.3, 0.3))
        self.assertFalse((self.root / elane_xs.PROBE_FILE).exists(), "nothing is published before the probe is whole")
        while not runs[-1]["finished"]:
            self.clock.advance(WEEK)
            self.router.compact()   # the swarm's loop blanks the stored answers of the week before
            out, _ = self.probe(settings_=tight)
            self.assertEqual(out["route"], "sail:pro_asap", "the probe under way goes on before another route starts")
            self.assertLessEqual(out["usd"], out["bound"] + 1e-9)
            self.assertIsNone(out.get("error"))
            runs.append(out)
            self.assertLess(len(runs), 30)
        self.assertGreater(len(runs), 3, "the panel's cells were asked over several runs too")
        keys = [call["key"] for call in self.router.calls]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(self.router.repeats, [], "A KEY IS ASKED ONCE: no run sent a key an earlier run sent")
        for call in self.router.calls:
            self.assertRegex(call["key"], r"^swarm:elane:probe:sail:pro_asap:1:\d+:[0-9a-f]{12}$")
            self.assertEqual(call["key"].rsplit(":", 1)[1], hashlib.sha256(call["user"].encode()).hexdigest()[:12])
            self.assertLessEqual(len(call["key"]), 120)
            self.assertEqual((call["role"], call["system"], call["max_output"], call["effort"]), (P.ROLE, P.SYSTEM, 2000, "low"))
        row = self.doc()["routes"]["sail:pro_asap"]
        self.assertAlmostEqual(row["usd"], 0.05 * len(self.router.billed), places=6, msg="every batch was paid for once")
        self.assertAlmostEqual(sum(r["usd"] for r in runs), row["usd"], places=6)
        self.assertAlmostEqual(elane_yield.ledger(self.store)["routes"]["probe:sail:pro_asap"]["usd"], row["usd"], places=6,
                               msg="E2's ledger holds what was billed, on the probe's own row, no more")
        self.assertEqual(sum(r["cells"] for r in runs), 9 + 9 + 1, "E3's nine cells here, the panel's nine, the recall")
        whole_root = tempfile.TemporaryDirectory()
        self.addCleanup(whole_root.cleanup)
        whole = ProbeRouter()
        self.probe(router=whole, root=Path(whole_root.name))
        self.assertEqual(sorted(k.rsplit(":", 1)[1] for k in self.router.billed),
                         sorted(k.rsplit(":", 1)[1] for k in whole.billed), "the same batches as one whole run asks, once each")
        self.assertEqual(self.doc(Path(whole_root.name))["routes"]["sail:pro_asap"]["cells"], row["cells"])
        self.assertEqual(self.permit()["routes"]["sail:pro_asap"]["at"], row["at"])

    def test_a_run_never_takes_more_than_e2s_day_has_left(self):
        elane_yield.book(self.store, "sail:pro_asap", usd=7.8, known=True, purpose="research", answered=True, now=self.clock())
        out, _ = self.probe()
        self.assertEqual((out["bound"], out["stopped"], out["finished"]), (0.2, "usd", False))
        self.assertLessEqual(out["usd"], 0.2 + 1e-9)
        self.assertAlmostEqual(elane_yield.spent_today(self.store, self.clock()), 7.8 + out["usd"], places=6)
        elane_yield.book(self.store, "sail:k3", usd=8.0, known=True, purpose="research", answered=True, now=self.clock())
        self.assertEqual(self.probe()[0]["status"], "skipped", "the day's line is spent: nothing is asked")

    def test_the_prompts_are_identical_whatever_the_prices(self):
        calls = {}
        for which in ("a", "b"):
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            router = ProbeRouter()
            out, _ = self.probe(which=which, router=router, root=Path(tmp.name))
            self.assertTrue(out["finished"])
            calls[which] = [(c["system"], c["user"], c["key"], c["role"]) for c in router.calls]
            calls[which, "cells"] = self.doc(Path(tmp.name))["routes"]["sail:pro_asap"]["cells"]
        self.assertEqual(calls["a"], calls["b"], "the same requests, byte for byte, on two different markets")
        for stratum in P.PANEL_STRATA:
            self.assertNotEqual(calls["a", "cells"][stratum], calls["b", "cells"][stratum], "and the markets differ: the scores do")

    def test_a_cells_truths_are_read_only_once_its_answers_are_in(self):
        events = []
        plan = self.plan(root=self.root)
        real = plan.truths

        def truths(questions):
            events.append(("truth", questions[0]["stratum"], questions[0]["era"], len(questions)))
            return real(questions)
        plan.truths = truths

        class Recording(ProbeRouter):
            def ask(inner, **kw):   # noqa: N805
                events.append(("ask", question_of(kw["user"].split("\n\n", 1)[1].splitlines()[0])))
                return ProbeRouter.ask(inner, **kw)
        asked = P.panel_questions(plan, per_cell=24)
        cell_of = {q["text"]: (q["stratum"], q["era"]) for q in asked}
        self.probe(router=Recording(), plan=plan)
        scored = []
        for event in events:
            if event[0] == "truth":
                scored.append(event[1:3])
                self.assertEqual(event[3], len(self.cells(asked)[event[1:3]]), "a whole cell at once")
            elif event[1] in cell_of:
                self.assertNotIn(cell_of[event[1]], scored, "a batch asked after its own cell's truths were read")
        self.assertEqual(scored, [(s, e) for s in P.PANEL_STRATA for e in P.ERAS], "each panel cell once")

    def test_nothing_the_probe_writes_holds_a_per_question_truth_or_outcome(self):
        table = self.oracle()
        self.probe(router=ProbeRouter(lambda text: table[text]), settings_=settings(usd_run=1.4))   # a partial first
        partial = (self.root / P.FILE).read_text()
        self.assertIn("panel_qset", partial)
        self.assertTrue(set(json.loads(partial)["routes"]["sail:pro_asap"]["partial"]["cells"]) & set(P.PANEL_STRATA))
        self.clock.advance(WEEK)
        out, _ = self.probe(router=ProbeRouter(lambda text: table[text]))
        self.assertTrue(out["finished"])
        asked = [*P.questions(UNIVERSE, per_cell=24), *P.panel_questions(self.plan(), per_cell=24), *P.recall_questions()]

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
                   "attempts", "attempted_at", "first_attempted_at", "idle", "cells", "recall", "partial", "probe_n",
                   "qset", "panel_qset", "batch_usd", "route", "newly_recalled", "[]", *ROUTES, *P.STRATA,
                   *P.PANEL_STRATA, *P.ERAS}
        names = set(self.plan().names("P4", "2016-24")) | set(self.plan().names("P4", "2025"))
        for text in (partial, (self.root / P.FILE).read_text(), (self.root / elane_xs.PROBE_FILE).read_text()):
            for path, value in leaves(json.loads(text)):
                self.assertFalse(set(path) - allowed - {"readable", "recalled"}, path)
                self.assertNotIn(value, ("higher", "lower", "more", "less", "tie"), path)
            for q in asked:
                self.assertNotIn(q["id"], text)
                self.assertNotIn(q["text"], text)
            for name in (*names, *P.FACTORS):
                self.assertNotIn(f'"{name}"', text, "no member and no factor is named in a file")
            self.assertNotRegex(text, r'"\d{4}-(0[1-9]|1[0-2])(-\d{2})?"', "no period (a month or the day a week ends on)")
            self.assertNotRegex(text, r"\[(true|false|0|1)(, ?(true|false|0|1)){5,}\]", "no row of outcomes")
        dump = json.dumps({name: self.store._all(f"SELECT * FROM {name}") for name in
                           [r["name"] for r in self.store._all("SELECT name FROM sqlite_master WHERE type='table'")]}, default=str)
        for q in asked:
            self.assertNotIn(q["id"], dump)
            self.assertNotIn(q["text"], dump)
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if not p.name.startswith("swarm.sqlite")),
                         sorted([P.FILE, elane_xs.PROBE_FILE, self.store.programs.name, self.store.runs_dir.name]),
                         "the probe's file and the permit: the two files it writes")

    def test_a_model_that_recalls_the_panel_is_read_as_recalling_it(self):
        table = self.oracle()
        out, ctx = self.probe(router=ProbeRouter(lambda text: table[text]))
        self.assertTrue(out["finished"])
        row = self.doc()["routes"]["sail:pro_asap"]
        recalled = [f"{s}/{e}" for s in P.PANEL_STRATA for e, cell in row["cells"][s].items() if cell["recalled"]]
        self.assertTrue(recalled, "a perfect answerer of the panel's cells is read as recalling some")
        for name in recalled:
            stratum, era = name.split("/")
            cell = row["cells"][stratum][era]
            self.assertEqual((cell["acc"], cell["readable"]), (1.0, True))
            self.assertIn(name, row["newly_recalled"])
            self.assertIs(self.permit()["routes"]["sail:pro_asap"]["cells"][stratum][era]["recalled"], True)
        judged = [name for name in recalled if name.split("/")[1] in P.JUDGED_ERAS]
        texts = [alert["text"] for alert in ctx.alerts if alert["level"] == "info"]
        for name in judged:
            self.assertTrue(any(f"cell {name} as recalled" in text for text in texts), "CP1 names a panel cell as it does E3's")
        # The report job's rows (league/ops/forward_report.py reads the probe's file as it is): the panel's cells
        # are counted with E3's and its recalled cells named, with no change to that module.
        from league.ops import forward_report

        carried = forward_report._contamination(self.root)["routes"]["sail:pro_asap"]
        self.assertEqual(carried["cells"], sum(len(eras) for eras in row["cells"].values()))
        self.assertTrue(set(recalled) <= set(carried["recalled"]))

    def test_a_panel_question_set_that_moved_drops_the_panel_cells_and_nothing_of_e3s(self):
        first, _ = self.probe(settings_=settings(usd_run=1.4))
        self.assertEqual(first["stopped"], "usd")
        partial = self.doc()["routes"]["sail:pro_asap"]["partial"]
        held = [s for s in partial["cells"] if s in P.PANEL_STRATA]
        self.assertTrue(held and set(P.STRATA) & set(partial["cells"]) == {"S1", "S2", "S4"}, partial["cells"].keys())
        e3_qset = partial["qset"]
        self.assertEqual(e3_qset, P.qset([*P.questions(UNIVERSE, per_cell=24), *P.recall_questions()]),
                         "`qset` is E3's own questions' sha: nothing of the panel's is in it")
        self.assertEqual(partial["panel_qset"], P.qset(P.panel_questions(self.plan(), per_cell=24)))
        # The membership was revised: one name fewer in the pool, so another panel question set.
        moved = self.plan(root=self.root)
        dropped = P.panel_questions(moved, per_cell=24)[0]["symbol"]
        for era in P.ERAS:
            moved._names[era] = [name for name in moved._names[era] if name != dropped]
        self.clock.advance(WEEK)
        router = ProbeRouter()
        out, _ = self.probe(plan=moved, router=router)
        self.assertTrue(out["finished"])
        users = "\n".join(call["user"] for call in router.calls)
        self.assertNotIn("higher or lower", users, "E3's S1 cells were kept: none was asked again")
        self.assertNotIn(" than SPY ", users, "nor S2's or S4's")
        self.assertNotIn(f"Did {dropped} ", users)
        self.assertEqual(out["cells"], 9 + 1, "every panel cell again, and the recall")
        row = self.doc()["routes"]["sail:pro_asap"]
        self.assertEqual({s: row["cells"][s] for s in ("S1", "S2", "S4")}, {s: partial["cells"][s] for s in ("S1", "S2", "S4")})
        self.assertEqual(self.router.repeats + router.repeats, [])

    def test_without_a_plan_a_partials_panel_cells_are_dropped_and_none_is_published(self):
        self.probe(settings_=settings(usd_run=1.4))
        self.assertTrue(set(self.doc()["routes"]["sail:pro_asap"]["partial"]["cells"]) & set(P.PANEL_STRATA))
        self.clock.advance(WEEK)
        out, _ = self.probe(plan=None)   # the lane was switched off
        self.assertTrue(out["finished"])
        self.assertNotIn("panel", out)
        row = self.doc()["routes"]["sail:pro_asap"]
        self.assertEqual(list(row["cells"]), ["S1", "S2", "S4"])
        self.assertFalse((self.root / elane_xs.PROBE_FILE).exists())
        self.assertIn("no published result", elane_xs.probed(self.root, {"spec": {"e2_route": "sail:pro_asap"}}))

    def test_a_route_published_without_the_panel_strata_is_due_at_once(self):
        for route in ROUTES:   # release E3's probe, before the panel's strata existed
            out, _ = self.probe(plan=None)
            self.assertEqual((out["route"], out["finished"]), (route, True))
            self.clock.advance(86400)
        self.assertEqual(self.probe(plan=None)[0], {"status": "skipped", "why": "no route is due a probe"})
        before = self.doc()
        for n, route in enumerate(ROUTES):
            out, _ = self.probe()
            self.assertEqual((out["route"], out["probe"], out["finished"], out["panel"]), (route, 2, True, 9),
                             "its result is not whole: probed again now, E3's cells with it")
            self.assertEqual(sorted(self.permit()["routes"]), sorted(ROUTES[:n + 1]))
            self.clock.advance(86400)
        self.assertEqual(self.probe()[0], {"status": "skipped", "why": "no route is due a probe"})
        self.assertEqual(self.doc()["routes"]["sail:k3"]["probes"], 2)
        self.assertEqual(before["routes"]["sail:k3"]["probes"], 1)
        self.assertEqual(P._owing(before, [])["routes"], before["routes"], "with no stratum asked nothing is owed")
        self.assertNotIn("at", P._owing(before, ["P4"])["routes"]["sail:k3"])
        self.assertIn("at", before["routes"]["sail:k3"], "the view is never written")

    def test_a_plan_that_cannot_say_a_truth_ends_the_run_and_scores_no_cell_on_it(self):
        self.settings["elane"]["e2"]["routes"] = ["sail:pro_asap"]   # one route: it is tried again each week

        def failing(error):
            plan = self.plan(root=self.root)

            def truths(questions):
                raise error
            plan.truths = truths
            return plan
        out, _ = self.probe(plan=failing(MissingData("the panel store is being rewritten")))
        self.assertEqual((out["stopped"], out["finished"], out["cells"]), ("data", False, 9), "E3's nine cells stay scored")
        self.assertIn("MissingData", out["error"])
        self.assertEqual(out["usd"], round(0.05 * len(self.router.calls), 6), "the cut cell's dollars are booked")
        self.assertFalse(set(self.doc()["routes"]["sail:pro_asap"]["partial"]["cells"]) & set(P.PANEL_STRATA))
        self.clock.advance(WEEK)
        out, _ = self.probe(plan=failing(StoreRefused("no capability")))
        self.assertEqual((out["stopped"], out["cells"]), ("data", 0))
        self.clock.advance(WEEK)
        out, _ = self.probe(plan=failing(ZeroDivisionError("a fault of the plan's own")))
        self.assertEqual(out["stopped"], "data")
        self.assertIn("the panel plan: ZeroDivisionError", out["error"])
        self.clock.advance(WEEK)
        short = self.plan(root=self.root)
        short.truths = lambda questions: ["more"]
        self.assertIn("no truth a question", self.probe(plan=short)[0]["error"])
        self.assertFalse((self.root / elane_xs.PROBE_FILE).exists())
        self.assertEqual(self.router.repeats, [], "the cut cell was asked again under each run's own keys")
        # A truth outside the stratum's words is no truth: the cell is scored on none of it.
        self.clock.advance(WEEK)
        odd = self.plan(root=self.root)
        odd.truths = lambda questions: [0.031] * len(questions)
        out, _ = self.probe(plan=odd)
        self.assertTrue(out["finished"])
        for stratum in P.PANEL_STRATA:
            for cell in self.doc()["routes"]["sail:pro_asap"]["cells"][stratum].values():
                self.assertEqual((cell["n"], cell["correct"], cell["readable"]), (0, 0, False))

    def test_a_plan_that_cannot_be_asked_marks_no_route(self):
        with self.assertRaises(ValueError):
            self.probe(plan=FakePlan(names=["ZQ1"]))
        self.assertFalse((self.root / P.FILE).exists(), "before any route is marked")
        self.assertEqual(self.router.calls, [])

    def test_a_permit_that_cannot_be_written_is_a_warning_and_the_result_stays(self):
        plan = self.plan(root=self.root)

        def published(doc):
            raise OSError("the disk is full")
        plan.published = published
        out, ctx = self.probe(plan=plan)
        self.assertEqual((out["finished"], out["permit"]), (True, False))
        self.assertEqual([(a["level"], "look permit" in a["text"]) for a in ctx.alerts], [("warning", True)])
        self.assertIn("at", self.doc()["routes"]["sail:pro_asap"])
        self.assertEqual(sorted(X.write_permit(self.root)["routes"]), ["sail:pro_asap"], "the job writes it again from the file")
        self.assertIsNone(elane_xs.probed(self.root, {"spec": {"e2_route": "sail:pro_asap"}}))


# ================================================================================================ the House's job
class TheHousesJob(Panels):
    """`contam_xs.run(ctx)` on a House state (the registry's job), with the swarm's router scripted."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.clock = fx.Clock()
        self.router = ProbeRouter(cost=0.0)
        SwarmStore(self.root).close()

    def ctx(self) -> Context:
        return Context("contam_probe", root=self.root, due_at=self.clock(), clock=self.clock, config={}, settings_value={})

    def on(self, panel_mode: str | None = "train", **block) -> None:
        lane: dict = {"contam": {"mode": "record", "questions_per_cell": 20, "batch": 40, **block}}
        if panel_mode is not None:
            lane["panel"] = {"mode": panel_mode}
        (self.root / "swarm.json").write_text(json.dumps({"elane": lane}))

    def house(self, which: str = "a") -> Path:
        """The synthetic panel as this state's `equity-daily` (a copy: a test may break it)."""
        return Path(shutil.copytree(self.panels[which], self.root / STORE_DIR))

    def run_job(self, job=X.run):
        with mock.patch("league.swarm.models.build_router", lambda root, store, settings_, *, config=None: self.router):
            return job(self.ctx())

    def route(self) -> str:
        return elane_yield.cfg(None)["routes"][0]

    def test_with_the_lane_off_or_no_panel_store_it_is_release_e3s_probe(self):
        self.house()
        for mode in (None, "off"):   # policy.json ships "off"
            self.on(mode)
            out = self.run_job()
            self.assertEqual((out["finished"], out["stopped"]), (True, None), out)
            self.assertNotIn("panel", out)
            self.assertFalse((self.root / elane_xs.PROBE_FILE).exists(), "no permit: every panel look waits")
            doc = json.loads((self.root / P.FILE).read_text())
            self.assertFalse(set(doc["routes"][out["route"]]["cells"]) & set(P.PANEL_STRATA))
            self.clock.advance(86400)
        self.assertEqual(X.asked(self.root, {"elane": {"panel": {"mode": "off"}}}), "elane.panel.mode is off")
        self.assertEqual(X.asked(self.root, None), "elane.panel.mode is off", "the code default")
        # The lane on, and no panel store yet (the data jobs have not written it).
        shutil.rmtree(self.root / STORE_DIR / xs_store.PANEL_DIR)
        self.on("train")
        self.assertEqual(X.asked(self.root, {"elane": {"panel": {"mode": "train"}}}), "no panel store yet")
        out = self.run_job()
        self.assertTrue(out["finished"])
        self.assertNotIn("panel", out)
        self.assertFalse((self.root / elane_xs.PROBE_FILE).exists())
        # ... and it is `contam_probe.run` to the byte: the same receipt on a state of its own.
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        mine, self.root = self.root, Path(other.name)
        SwarmStore(self.root).close()
        self.on("off")
        self.house()
        self.clock = fx.Clock()
        plain = self.run_job(P.run)
        again = tempfile.TemporaryDirectory()
        self.addCleanup(again.cleanup)
        self.root = Path(again.name)
        SwarmStore(self.root).close()
        self.on("off")
        self.house()
        self.assertEqual(self.run_job(), plain)
        self.assertEqual(json.loads((self.root / P.FILE).read_text()), json.loads((Path(other.name) / P.FILE).read_text()))
        self.root = mine

    def test_with_the_lane_on_it_asks_the_three_strata_and_writes_the_permit(self):
        self.house()
        self.on("train")
        self.assertIsNone(X.asked(self.root, {"elane": {"panel": {"mode": "train"}}}))
        out = self.run_job()
        self.assertEqual((out["finished"], out["stopped"], out["panel"], out["permit"]), (True, None, 9, True), out)
        route = self.route()
        self.assertEqual(out["route"], route)
        doc = json.loads((self.root / P.FILE).read_text())
        self.assertTrue(set(P.PANEL_STRATA) <= set(doc["routes"][route]["cells"]))
        self.assertIsNone(elane_xs.probed(self.root, {"spec": {"e2_route": route}}))
        self.assertEqual(sorted(json.loads((self.root / elane_xs.PROBE_FILE).read_text())["routes"]), [route])
        # A permit lost is made again by the next run, whatever that run asked.
        (self.root / elane_xs.PROBE_FILE).unlink()
        (self.root / "swarm.json").write_text(json.dumps({"elane": {"contam": {"mode": "record", "questions_per_cell": 20,
                                                                              "batch": 40},
                                                                   "panel": {"mode": "train"}, "e2": {"routes": [route]}}}))
        self.clock.advance(86400)
        self.assertEqual(self.run_job(), {"status": "skipped", "why": "no route is due a probe"})
        self.assertIsNone(elane_xs.probed(self.root, {"spec": {"e2_route": route}}))

    def test_a_panel_store_that_cannot_be_read_fails_before_any_route_is_marked(self):
        house = self.house()
        self.on("train")
        with open(house / xs_store.PANEL_DIR / "adj.npy", "r+b") as handle:   # a file changed under its manifest
            handle.seek(-8, 2)
            handle.write(b"\x00" * 8)
        out = self.run_job()
        self.assertEqual(out["status"], "failed")
        self.assertIn("the panel store cannot be read (MissingData)", out["error"])
        self.assertFalse((self.root / P.FILE).exists(), "the House's own trouble marks no route")
        self.assertFalse((self.root / elane_xs.PROBE_FILE).exists())
        self.assertEqual(self.router.calls, [], "and costs nothing")
        # The lane's switch is the way back to E3's probe while the panel is mended.
        self.on("off")
        self.assertTrue(self.run_job()["finished"])

    def test_a_panel_of_insufficient_coverage_asks_no_panel_stratum(self):
        house = self.house()
        self.on("train")
        path = house / xs_store.PANEL_DIR / xs_store.PANEL_MANIFEST
        manifest = json.loads(path.read_text())
        manifest["verdict"] = "insufficient"
        path.write_text(json.dumps(manifest))
        out = self.run_job()
        self.assertTrue(out["finished"])
        self.assertNotIn("panel", out)
        self.assertFalse((self.root / elane_xs.PROBE_FILE).exists())

    def test_no_panel_work_starts_where_it_could_meet_a_wall(self):
        self.house()
        self.on("train")
        monday = dt.datetime(2026, 10, 5, 19, 0, tzinfo=dt.timezone.utc)   # 15:00 New York: the close wall is ahead
        self.clock = fx.Clock(monday.timestamp())
        out = self.run_job()
        self.assertEqual(out["status"], "skipped")
        self.assertIn("wall", out["why"])
        self.assertFalse((self.root / P.FILE).exists())
        self.assertEqual(self.router.calls, [])
        self.on("off")   # E3's probe alone reads no panel and asks no wall, as before
        self.assertTrue(self.run_job()["finished"])
        saturday = dt.datetime(2026, 10, 10, 0, 10, tzinfo=dt.timezone.utc)   # the job's own time: never a session
        self.assertIsNone(xs_config.quiet(saturday.timestamp(), X.WALL_S))
        self.assertIsNone(xs_config.quiet(saturday.timestamp() + 6 * 3600, X.WALL_S), "nor at the end of its grace")

    def test_the_probes_switch_is_still_the_probes(self):
        self.house()
        (self.root / "swarm.json").write_text(json.dumps({"elane": {"contam": {"mode": "off"}, "panel": {"mode": "train"}}}))
        self.assertEqual(self.run_job(), {"status": "skipped", "why": "elane.contam.mode is off"})
        self.assertFalse((self.root / P.FILE).exists() or (self.root / elane_xs.PROBE_FILE).exists())


# ===================================================================================================== the wiring
class TheWiring(unittest.TestCase):
    def test_the_houses_job_is_this_module_and_its_row_is_e3s(self):
        job = registry.by_name()["contam_probe"]
        self.assertEqual(job.module, "league.ops.contam_xs")
        self.assertEqual((job.triggers, job.cpu, job.wall, job.paid, job.retry, job.in_pause),
                         ((schedule.weekly(5, 0, 10),), 300, 3300, True, False, False), "release E3's row, unmoved")
        self.assertEqual(X.WALL_S, job.wall)
        self.assertLess(P.ASK_SECONDS, job.wall)
        self.assertEqual((X.STORE_DIR, X.STORE_DIR, X.STORE_DIR), (STORE_DIR, equity_data.STORE_DIR, elane_xs.STORE_DIR))
        self.assertEqual(X.TRAIN_ERA, next(iter(P.ERAS)))
        self.assertTrue(callable(X.run) and callable(P.run) and callable(P.probe))

    def test_the_probe_imports_nothing_of_the_panel_and_e3s_seal_is_as_it_was(self):
        """Release E3's seal T1 lets its ops modules import only what its contract lists, and the probe is one of
        them: every panel read is this module's, handed to the probe as a plan."""
        reached = {module for module, _, _ in seal.imports(REPO, REPO / "league" / "ops" / "contam_probe.py")}
        self.assertFalse({m for m in reached if m.startswith("league.xs") or m in ("league.ops.contam_xs", "league.swarm.elane_xs")})
        self.assertEqual(seal.outside(REPO, REPO / "league" / "ops" / "contam_probe.py", seal.OPS_MAY), [])
        self.assertNotIn("contam_xs", seal.E3_OPS)
        self.assertFalse({m for m in seal.OPS_MAY if "xs" in m.split(".")[-1]}, "nothing of the panel was let in")
        mine = {module for module, _, _ in seal.imports(REPO, REPO / "league" / "ops" / "contam_xs.py")}
        self.assertTrue({"league.ops.contam_probe", "league.xs.store", "league.xs.ctx", "league.swarm.elane_xs"} <= mine)
        top = {module for module, inside, _ in seal.imports(REPO, REPO / "league" / "ops" / "contam_xs.py") if not inside}
        self.assertEqual(top, set(), "numpy and the panel are imported where they are used")

    def test_the_permit_the_lanes_own_tests_fake_is_the_shape_the_job_writes(self):
        """league/tests/elane_xs_fakes.py `write_probe` (the panel lane's tests and the end-to-end test write a permit
        by hand): the same keys at every depth as `permit` gives of a probe file."""
        from league.tests import elane_xs_fakes

        def shape(value):
            return {key: shape(inner) for key, inner in value.items()} if isinstance(value, dict) else type(value).__name__
        cell = {name: None for name in P.CELL_KEYS} | {"readable": True, "recalled": False}
        doc = {"routes": {elane_xs_fakes.ROUTE: {"at": "2026-10-10T00:20:00Z", "model": "fake-model", "cells": {
            s: {"2016-24": dict(cell), "2025": dict(cell)} for s in (*P.STRATA, *P.PANEL_STRATA)}}}}
        with tempfile.TemporaryDirectory() as tmp:
            elane_xs_fakes.write_probe(tmp)
            faked = json.loads((Path(tmp) / elane_xs.PROBE_FILE).read_text())
            self.assertEqual(shape(X.write_permit(tmp, doc)), shape(faked))
            self.assertEqual(json.loads((Path(tmp) / elane_xs.PROBE_FILE).read_text()), faked)

    def test_no_sealed_tree_imports_this_module(self):
        for tree in seal.SEALED_TREES:
            for path in seal.sources(REPO, tree):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("contam_xs", text, path)
                self.assertNotIn("league.ops.contam_xs", {m for m, _, _ in seal.imports(REPO, path)}, path)
        swarm = (REPO / "league" / "swarm" / "elane_xs.py").read_text(encoding="utf-8")
        self.assertNotIn(P.FILE, swarm, "the swarm names the permit, never the probe's own file")
        self.assertIn("xs-look-permit.json", swarm)


if __name__ == "__main__":
    unittest.main()
