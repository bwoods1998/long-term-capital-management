"""Research v3, B1 (league/swarm/researcher.py, league/swarm/family_ledger.py): every family on the Claude band (`is_top`'s
newborns, `claude_top` "all"), THE SWEEP CYCLE (one answer a cycle defines a sweep of 3 to 5 variants; the harness adds a
mandatory PLACEBO row from the card's ablation, or a shuffled-signal row for a flat card, and says whether every signal row
beat it on Train) and THE FAMILY LEDGER (a structured row written by the harness from every run and sweep, the whole of it
in every cycle's status). Synthetic programs, parameters and results only (a fake Gym; no quotes)."""

from __future__ import annotations

import json
import re
import unittest

from league.swarm import cards, family_ledger
from league.swarm.loop import Scheduler, sweep_wait
from league.swarm.researcher import (PLACEBO, SHUFFLE_PARAM, SWEEP_RULE, Researcher, placebo_beats, placebo_years,
                                     sweep_tool, sweep_variants)
from league.swarm.seeds import SEEDS, family_spec
from league.tests.test_swarm_claude_research import ClaudeCase, answer, call
from league.tests.test_swarm_researcher import ResearcherCase, calls_in
from league.tests.test_swarm_sweep import SweepPool, by_year, scored

CODE = ('NEEDS = {"roots": ["SPY"], "dte": [0, 5], "cadence": 30}\n'
        'PARAMS = {"signal_on": 1, "threshold": 600}\n\n'
        'def decide(ctx):\n'
        '    if PARAMS["signal_on"] and ctx.minute < PARAMS["threshold"]:\n'
        '        return []\n'
        '    return []\n')
NO_SWITCH = CODE.replace('"signal_on": 1, ', '').replace('PARAMS["signal_on"] and ', '')
BOOL_SWITCH = CODE.replace('"signal_on": 1', '"signal_on": True')
SHUFFLED = CODE.replace('"signal_on": 1', f'"{SHUFFLE_PARAM}": 0').replace('PARAMS["signal_on"]', f'not PARAMS["{SHUFFLE_PARAM}"]')

CARD = {"hypothesis": "Liquidity-demanding sellers push the close below value late in the day and patient buyers are paid "
                      "to absorb it over the next session.",
        "mechanism_class": "reversal_liquidity", "inputs": ["underlying_price", "clock"], "holding": "days_1_3",
        "cost": {"hurdle": 0.08, "why": "two half-spreads and fees on a narrow debit vertical"},
        "comparison": "the same debit vertical opened at the same minute every session without the late-selling condition",
        "ablation": {"param": "signal_on", "off": 0},
        "falsification": "signal entries do not beat the comparison's by t 0.75 on the mechanism sample"}
FLAT = {**CARD, "mechanism_class": "volatility_risk_premium", "ablation": {"flat": True},
        "hypothesis": "Index option buyers overpay for protection, so a hedged short premium position is paid for bearing "
                      "variance risk over its holding period."}

_YEAR = re.compile(r"(?<![0-9])(?:19|20)[0-9]{2}(?![0-9])")


def surface(job, placebo_t: float = 0.5, placebo_trades: bool = True) -> dict:
    """The switch program's synthetic Train surface: the placebo (signal_on 0) at `placebo_t` every year, a signal row at
    1 + threshold / 1000; P&L follows t."""
    on = job.params.get("signal_on", 1)
    t = placebo_t if on in (0, False) else 1.0 + float(job.params.get("threshold", 600)) / 1000.0
    r = scored(job, lambda p: t)
    r["summary"]["pnl"] = round(300.0 * t, 2)
    if on in (0, False) and not placebo_trades:
        r["summary"].update(trades=0, pnl=0.0, days_traded=0)
        r["by_year"] = by_year(0.0, trades=0, days=0)
    return r


def model_safe(test: unittest.TestCase, text: str) -> None:
    """Text a model reads that this package wrote: ASCII, no year or date, no Validation or holdout figure."""
    test.assertTrue(text.isascii(), text)
    test.assertIsNone(_YEAR.search(text), text)
    test.assertNotRegex(text.lower(), r"(validation|holdout)[^.]{0,40}\d")


class V3Case(ResearcherCase):
    """A Gym family on the synthetic switch program, THE SWEEP CYCLE on, the mechanism test off (its own tests)."""

    def setUp(self):
        super().setUp()
        self.fid = self.fam["id"]
        self.settings["researcher"]["sweep_cycle"] = True
        self.settings["researcher"]["mechanism_test"] = False
        self.settings["population"]["floor"] = 0
        self.placebo_t, self.placebo_trades = 0.5, True
        self.pool = SweepPool(answer=lambda job: surface(job, self.placebo_t, self.placebo_trades))

    def sweep(self, variants, fid=None, **args):
        out: dict = {"tool_calls": 0}
        view = self.researcher()._execute(self.store.family(fid or self.fid), "gym_sweep",
                                          {"code": CODE, "variants": variants, **args}, out, author="synthetic")
        return view, out

    def carded(self, fid: str, card: dict, structure: str = "debit_vertical") -> str:
        spec = {"id": fid, "mechanism": card["hypothesis"], "structure": structure, "roots": ["SPY"], "dte": [0, 5],
                "rejection": "no edge", "card_sha": cards.card_sha(card)}
        fam = self.store.add_family(spec, origin="architect")
        cards.put(self.store, fam["id"], card, structure)
        return fam["id"]


# ------------------------------------------------------------------------------------------------------- the ledger
class Ledger(ResearcherCase):
    def entry(self, **kw):
        return {"version": "3", "change": "a tighter entry window", "expectation": "fewer, better entries",
                "outcome": "ok, 60 trades", "verdict": "no_better", "why": "below the best", **kw}

    def test_rows_are_the_harness_words_ascii_one_line_and_scrubbed(self):
        family_ledger.add(self.store, "f", self.entry(change="café  late\nentries | wider", expectation="x" * 900,
                                                      why="validation t = 2.4 was close"))
        [row] = family_ledger.rows(self.store, "f")
        self.assertEqual(row["change"], "cafe late entries / wider")
        self.assertEqual(len(row["expectation"]), family_ledger.FIELD_CHARS["expectation"])
        self.assertNotIn("2.4", row["why"], "Validation's figures never reach a row")
        with self.assertRaises(ValueError):
            family_ledger.add(self.store, "f", self.entry(verdict="great"))
        self.assertEqual(family_ledger.rows(self.store, "other"), [])

    def test_the_rendering_keeps_the_newest_rows_whole_and_compresses_the_oldest_first(self):
        for i in range(40):
            family_ledger.add(self.store, "f", self.entry(version=str(i + 1), change=f"change number {i + 1} " + "w" * 120,
                                                          verdict="new_best" if i % 4 == 0 else "ineligible"))
        rows = family_ledger.rows(self.store, "f")
        whole = family_ledger.render(rows, 10 ** 6)
        self.assertEqual(whole.count("\n"), 40, "a header and every row")
        text = family_ledger.render(rows, 6000)
        self.assertLessEqual(len(text), 6000)
        self.assertTrue(text.startswith(family_ledger.HEADER))
        self.assertIn("#40 v40 ineligible: change number 40", text, "the newest row is read in full")
        self.assertIn("#1 v1 new_best: ok, 60 trades", text, "the oldest row compressed: its verdict and outcome")
        self.assertNotIn("change number 1 ", text)
        tight = family_ledger.render(rows, 1500)
        self.assertLessEqual(len(tight), 1500)
        self.assertRegex(tight, r"#1-#\d+: \d+ earlier rows folded \(new_best \d+, ineligible \d+\)")
        self.assertIn("#40 v40 ineligible: change number 40", tight)
        self.assertEqual(family_ledger.render(rows, 0), "")
        self.assertEqual(family_ledger.render([], 6000), "")
        self.assertLessEqual(len(family_ledger.render(rows, 50)), 50, "never above the limit")

    def test_the_rendering_never_shows_a_date_or_a_family_id(self):
        family_ledger.add(self.store, "condor-vrp-17", self.entry())
        text = family_ledger.view(self.store, "condor-vrp-17")
        self.assertNotIn("condor-vrp-17", text)
        self.assertIsNone(re.search(r"\d{4}-\d{2}-\d{2}", text))
        model_safe(self, family_ledger.HEADER)

    def test_a_run_answer_becomes_its_verdict(self):
        base = {"run_id": "r1", "version": 4, "status": "ok", "summary": {"trades": 80, "days_traded": 40, "pnl": 512.4}}
        best = family_ledger.run_entry({**base, "train_score": {"score": 1.2, "eligible": True}, "new_best_train_score": 1.2},
                                       {"why": "skip the open", "expectation": "a better worst year"})
        self.assertEqual((best["verdict"], best["version"], best["change"], best["expectation"]),
                         ("new_best", "4", "skip the open", "a better worst year"))
        self.assertIn("80 trades on 40 days, P&L $512, Train score 1.20 (eligible)", best["outcome"])
        flat = family_ledger.run_entry({**base, "train_score": {"score": 0.4, "eligible": True}}, {}, best=1.2)
        self.assertEqual(flat["verdict"], "no_better")
        self.assertIn("1.20", flat["why"])
        thin = family_ledger.run_entry({**base, "train_score": {"score": 0.4, "eligible": False,
                                                                "why_not_eligible": "too few trades in a year"}}, {"code": "x"})
        self.assertEqual((thin["verdict"], thin["why"], thin["change"]), ("ineligible", "too few trades in a year", "new code"))
        failed = family_ledger.run_entry({"run_id": "r2", "version": 5, "status": "disqualified",
                                          "runtime": {"messages": ["decide raised KeyError"]}}, {"params": {"a": 1}})
        self.assertEqual((failed["verdict"], failed["why"], failed["change"]), ("failed", "decide raised KeyError", "params a"))
        for none in ({"status": "refused", "reason": "x"}, {"status": "held"}, {**base, "already_run": "the stored result"},
                     {"status": "gym_error", "error": "busy"}, {"status": "mechanism_failed", "run_id": "m"}, None):
            self.assertIsNone(family_ledger.run_entry(none, {}), none)


# --------------------------------------------------------------------------------------------- the Claude band for all
class Band(ClaudeCase):
    def test_a_zero_kth_weight_never_switches_the_band_off_and_newborns_ride_it(self):
        newborn = self.store.add_family(family_spec(next(s for s in SEEDS if s["id"] == "ironfly-quiet")), origin="seed")
        self.store.update_family(self.fid, weight=0.0)
        r = self.researcher()
        route = lambda fid: r.claude_route(self.store.family(fid))  # noqa: E731
        self.assertEqual([route(self.fid), route(newborn["id"])], [True, True],
                         "no weights yet (a fresh population): before, every family was on Sail")
        self.store.update_family(self.fid, weight=1.0)
        self.settings["researcher"]["claude_top"] = 12
        self.assertEqual([route(self.fid), route(newborn["id"])], [True, True], "fewer weighted families than the band")
        self.settings["researcher"]["claude_top"] = 1
        self.assertEqual([route(self.fid), route(newborn["id"])], [True, False], "a full band keeps its number")
        self.assertFalse(r.is_top(self.store.family(newborn["id"]), top=12), "the Sail top profile keeps its rule")

    def test_all_puts_every_family_on_claude_while_the_role_is_configured(self):
        others = [self.store.add_family(family_spec(s), origin="seed") for s in SEEDS[1:4]]
        self.store.update_family(others[0]["id"], weight=0.9)
        self.settings["researcher"]["claude_top"] = "all"
        r = self.researcher()
        self.assertTrue(all(r.claude_route(self.store.family(f)) for f in [self.fid] + [o["id"] for o in others]))
        self.settings["claude"]["roles"] = ["architect"]
        self.assertFalse(r.claude_route(self.store.family(self.fid)), "no researcher role: no line, no Claude")
        self.settings["claude"]["roles"].append("researcher")
        self.settings["researcher"]["claude_top"] = "most"
        self.assertFalse(r.claude_route(self.store.family(self.fid)), "a typo is off, never every family")

    def test_a_sweep_cycle_on_claude_is_one_answer_with_its_ledger(self):
        self.settings["researcher"].update(sweep_cycle=True, claude_top="all", mechanism_test=False)
        self.settings["population"]["floor"] = 0
        self.pool = SweepPool(answer=surface)
        self.claude_script[:] = [answer(call("gym_sweep", {"code": CODE, "variants": [{"threshold": 500}, {"threshold": 600},
                                                                                     {"threshold": 700}],
                                                           "why": "where the late window starts",
                                                           "expectation": "every row beats the placebo"}))]
        out = self.cycle()
        self.assertEqual((out.get("route"), out["model_calls"], out.get("claude_calls")), ("claude", 1, 1), out)
        self.assertEqual(out.get("ledger"), "beat_placebo")
        [body] = self.bodies()
        self.assertIn("THE SWEEP CYCLE", json.dumps(body["system"]))
        sweep = next(t for t in body["tools"] if t["name"] == "gym_sweep")
        self.assertIn("expectation", sweep["input_schema"]["properties"])
        self.assertIn("the harness adds the placebo row", json.dumps(body["messages"][-1]))
        jobs = self.pool.train()
        self.assertEqual(sorted(j.params.get("signal_on", 1) for j in jobs), [0, 1, 1, 1], "three variants and the placebo")
        self.claude_script[:] = [lambda body: answer(call("gym_run", {"hold": True, "note": "reading"}))]
        self.cycle()
        last = self.bodies()[-1]
        self.assertIn("YOUR LEDGER", json.dumps(last["messages"]))
        self.assertIn("expected: every row beats the placebo | got: 4 of 4 rows ok", json.dumps(last["messages"]),
                      "the expectation, beside what came back")


# -------------------------------------------------------------------------------------------------- THE SWEEP CYCLE
class Placebo(V3Case):
    def test_the_harness_adds_the_placebo_row_and_says_whether_every_signal_row_beat_it(self):
        view, out = self.sweep([{"threshold": 500}, {"threshold": 600}, {"threshold": 700}], why="the window's start",
                               expectation="later starts earn more")
        self.assertEqual(len(self.pool.train()), 4)
        [placebo] = [r for r in view["table"] if r.get("label") == PLACEBO]
        self.assertEqual((placebo["params"], placebo["eligible"]), ({"signal_on": 0}, False))
        self.assertIn("placebo row", placebo["why_not"])
        signal = [r for r in view["table"] if r.get("label") != PLACEBO]
        self.assertTrue(all(r["beats_placebo"] is True and r["years_above_placebo"] == "3/3" for r in signal))
        self.assertIs(view["every_signal_row_beat_placebo"], True)
        self.assertEqual(view["placebo"]["version"], placebo["version"])
        self.assertEqual(out["sweep"]["placebo"], {"version": placebo["version"], "every_signal_beat": True})
        fam = self.store.family(self.fid)
        self.assertEqual(fam["state"]["placebo_versions"], [placebo["version"]])
        self.assertNotEqual(fam["state"]["best_train_version"], placebo["version"])
        [row] = family_ledger.rows(self.store, self.fid)
        self.assertEqual((row["verdict"], row["expectation"]), ("beat_placebo", "later starts earn more"))
        self.assertIn("grid over threshold", row["change"])
        self.assertIn(f"placebo v{placebo['version']} ok", row["outcome"])

    def test_a_placebo_that_earns_as_much_is_named_and_never_becomes_the_best(self):
        self.placebo_t = 2.0  # the placebo beats the 1.5 row: that row's edge is not its signal
        view, _ = self.sweep([{"threshold": 500}, {"threshold": 1200}, {"threshold": 1300}])
        self.assertIs(view["every_signal_row_beat_placebo"], False)
        beats = {r["params"].get("threshold"): r["beats_placebo"] for r in view["table"] if r.get("label") != PLACEBO}
        self.assertEqual(beats, {500: False, 1200: True, 1300: True})
        best = self.store.family(self.fid)["state"]["best_train_version"]
        placebo = view["placebo"]["version"]
        self.assertNotEqual(best, placebo)
        [row] = family_ledger.rows(self.store, self.fid)
        self.assertEqual(row["verdict"], "placebo_matched")
        self.assertIn("did not beat the placebo row", row["why"])
        r = self.researcher()
        submitted = r._local_tool(self.store.family(self.fid), "submit", {"run_id": view["placebo"]["run_id"]}, {})
        self.assertIn("placebo row", submitted["error"], "a placebo is never submitted")

    def test_a_placebo_that_made_no_trade_compares_against_doing_nothing_and_says_so(self):
        self.placebo_trades = False
        view, _ = self.sweep([{"threshold": 500}, {"threshold": 600}, {"threshold": 700}])
        self.assertIs(view["every_signal_row_beat_placebo"], True)
        self.assertIn("turned the program off", view["placebo_note"])
        self.assertIn("compared against doing nothing", family_ledger.rows(self.store, self.fid)[0]["why"])

    def test_a_variant_that_is_the_placebo_is_taken_as_it_and_never_run_twice(self):
        view, _ = self.sweep([{"threshold": 500}, {"threshold": 600}, {"signal_on": 0}])
        self.assertEqual(len(self.pool.train()), 3)
        self.assertEqual([r["params"] for r in view["table"] if r.get("label") == PLACEBO], [{"signal_on": 0}])

    def test_a_boolean_switch_takes_a_boolean_placebo(self):
        out: dict = {"tool_calls": 0}
        view = self.researcher()._execute(self.store.family(self.fid), "gym_sweep", {"code": BOOL_SWITCH, "variants": [
            {"threshold": 500}, {"threshold": 600}, {"threshold": 700}]}, out, author="synthetic")
        self.assertEqual([r["params"] for r in view["table"] if r.get("label") == PLACEBO], [{"signal_on": False}])

    def test_a_flat_card_gets_a_shuffled_signal_row(self):
        fid = self.carded("flat-premium", FLAT, structure="iron_condor")
        out: dict = {"tool_calls": 0}
        view = self.researcher()._execute(self.store.family(fid), "gym_sweep", {"code": SHUFFLED, "variants": [
            {"threshold": 500}, {"threshold": 600}, {"threshold": 700}]}, out, author="synthetic")
        self.assertEqual([r["params"] for r in view["table"] if r.get("label") == PLACEBO], [{SHUFFLE_PARAM: 1}])
        self.assertIn(f"PARAMS['{SHUFFLE_PARAM}'] = 1", self.researcher().brief(self.store.family(fid)))
        refused = self.researcher()._execute(self.store.family(fid), "gym_sweep", {"code": CODE, "variants": [
            {"threshold": 500}, {"threshold": 600}, {"threshold": 700}]}, {"tool_calls": 0}, author="synthetic")
        self.assertIn(SHUFFLE_PARAM, refused["reason"])

    def test_a_carded_ablation_names_the_switch(self):
        fid = self.carded("late-sell", {**CARD, "ablation": {"param": "threshold", "off": 0}})
        out: dict = {"tool_calls": 0}
        view = self.researcher()._execute(self.store.family(fid), "gym_sweep", {"code": CODE, "variants": [
            {"threshold": 500}, {"threshold": 600}, {"threshold": 700}]}, out, author="synthetic")
        self.assertEqual([r["params"] for r in view["table"] if r.get("label") == PLACEBO], [{"threshold": 0}])

    def test_no_switch_no_sweep(self):
        out: dict = {"tool_calls": 0}
        view = self.researcher()._execute(self.store.family(self.fid), "gym_sweep", {"code": NO_SWITCH, "variants": [
            {"threshold": 500}, {"threshold": 600}, {"threshold": 700}]}, out, author="synthetic")
        self.assertEqual(view["status"], "refused")
        self.assertIn("'signal_on'", view["reason"])
        self.assertIn("Declare 'signal_on' in PARAMS", view["hint"])
        self.assertEqual((self.pool.jobs, self.store.versions(self.fid), out.get("run_refused")), ([], [], 1))

    def test_three_to_five_variants(self):
        two, _ = self.sweep([{"threshold": 500}, {"threshold": 600}])
        self.assertIn("at least 3 variants", two["reason"])
        six, _ = self.sweep([{"threshold": 500 + 10 * i} for i in range(6)])
        self.assertIn("at most 5 variants", six["reason"])
        repeats, _ = self.sweep([{"threshold": 500}, {"threshold": 500}, {}])
        self.assertIn("fewer than 3 distinct variants", repeats["reason"])
        self.assertEqual(self.pool.jobs, [])

    def test_a_placebo_the_preflight_refuses_refuses_the_sweep(self):
        def check(code, params, **kw):
            if params.get("signal_on") == 0:
                return {"status": "refused", "why": "decide raised", "error": "KeyError", "hint": "read it safely"}
            return {"status": "passed"}

        r = Researcher(self.store, self.router, self.pool, self.settings, clock=self.clock, background=False, preflight=check)
        out: dict = {"tool_calls": 0}
        view = r._execute(self.store.family(self.fid), "gym_sweep", {"code": CODE, "variants": [
            {"threshold": 500}, {"threshold": 600}, {"threshold": 700}]}, out, author="synthetic")
        self.assertEqual(view["status"], "refused")
        self.assertIn("placebo row", view["reason"])
        self.assertEqual(self.pool.jobs, [])

    def test_off_the_sweep_cycle_is_the_sweep_as_before(self):
        self.settings["researcher"]["sweep_cycle"] = False
        view, _ = self.sweep([{"threshold": 500}, {"threshold": 600}])
        self.assertEqual(len(self.pool.train()), 2, "no placebo row added")
        self.assertNotIn("every_signal_row_beat_placebo", view)
        self.assertFalse(any(r.get("label") for r in view["table"]))
        self.assertEqual(family_ledger.rows(self.store, self.fid)[0]["verdict"], "new_best", "the ledger is written either way")
        self.assertNotIn("THE SWEEP CYCLE", self.researcher().prompt())


class Pure(unittest.TestCase):
    def test_beating_the_placebo(self):
        placebo = {"status": "ok", "pnl": 100.0, "score": 0.5, "trades": 60, "years": {"a": {"t": 0.5}, "b": {"t": 0.5}}}
        self.assertTrue(placebo_beats({"status": "ok", "pnl": 150.0, "score": 0.6}, placebo))
        self.assertFalse(placebo_beats({"status": "ok", "pnl": 150.0, "score": 0.5}, placebo), "the score must be above too")
        self.assertFalse(placebo_beats({"status": "ok", "pnl": 100.0, "score": 0.9}, placebo), "the P&L must be above")
        self.assertFalse(placebo_beats({"status": "error", "pnl": None}, placebo))
        self.assertTrue(placebo_beats({"status": "ok", "pnl": 1.0, "score": None}, {"status": "ok", "pnl": None, "trades": 0}),
                        "a placebo that made no trade earned nothing")
        self.assertIsNone(placebo_beats({"status": "ok", "pnl": 150.0}, {"status": "error"}))
        self.assertIsNone(placebo_beats({"status": "ok", "pnl": 150.0}, None))
        self.assertEqual(placebo_years({"years": {"a": {"t": 0.9}, "b": {"t": 0.1}, "c": {"t": 2.0}}}, placebo), "1/2")
        self.assertIsNone(placebo_years({"years": {}}, placebo))

    def test_the_variant_bounds(self):
        self.assertIn("at least 3", sweep_variants(CODE, [{}, {"threshold": 1}], minimum=3, limit=5)[2])
        ok, dropped, why = sweep_variants(CODE, [{}, {"threshold": 1}, {"threshold": 2}], minimum=3, limit=5)
        self.assertEqual((len(ok), dropped, why), (3, 0, None))
        self.assertIn("one variant is a gym_run", sweep_variants(CODE, [{}])[2], "the classic words are unchanged")

    def test_the_words_a_model_reads_are_model_safe(self):
        model_safe(self, SWEEP_RULE)
        model_safe(self, json.dumps(sweep_tool(5, cycle=True)))
        model_safe(self, Researcher.offer_note([{"name": "gym_sweep"}, {"name": "gym_run"}], True, sweep=True))


class Cycles(V3Case):
    def first(self):
        """The seed's starter cycle (no model call): version 1, one trial, the ledger's first row."""
        self.researcher().cycle(self.fid)

    def test_one_answer_runs_one_sweep_and_the_next_cycle_reads_it(self):
        self.first()
        self.steps = [{"calls": [("gym_sweep", {"code": CODE, "variants": [{"threshold": 500}, {"threshold": 600},
                                                                           {"threshold": 700}],
                                                "why": "where the window starts", "expectation": "later is better"})]}]
        out = self.researcher().cycle(self.fid)
        self.assertEqual((out["model_calls"], out["tool_calls"], out.get("pending_run")), (1, 1, False), out)
        self.assertEqual(out["ledger"], "beat_placebo")
        first = self.sail.bodies[0]
        self.assertEqual([t["name"] for t in first["tools"]], ["gym_sweep", "gym_run", "submit"])
        self.assertEqual(first["tool_choice"], "required")
        self.assertIn("THE SWEEP CYCLE", first["input"][0]["content"])
        self.assertIn("Placebo row of every sweep", first["input"][1]["content"])
        view = json.loads(self.store.convo(self.fid)[0][-1]["items"][-1]["output"])
        best = next(r for r in view["table"] if r.get("label") != PLACEBO)
        self.steps = [lambda body: {"calls": [("submit", {"run_id": best["run_id"]}),
                                              ("gym_sweep", {"code": CODE, "variants": [{"threshold": 800}, {"threshold": 900},
                                                                                        {"threshold": 1000}],
                                                             "expectation": "the plateau goes on"})]}]
        out = self.researcher().cycle(self.fid)
        self.assertEqual((out["model_calls"], out.get("submitted")), (1, best["version"]))
        second = self.sail.bodies[-1]
        status = second["input"][-1]["content"]
        self.assertIn("YOUR LEDGER", status)
        self.assertIn("expected: later is better | got: 4 of 4 rows ok", status, "the expectation beside what came back")
        self.assertIn("Now (the sweep cycle, ONE answer)", status)
        self.assertIn('\\"label\\": \\"placebo\\"', json.dumps(second["input"]),
                      "the last sweep's table, placebo labelled, in the history")
        self.assertEqual(len(family_ledger.rows(self.store, self.fid)), 3, "the starter run and two sweeps")

    def test_a_params_change_is_a_sweep_and_a_fix_is_a_run(self):
        self.first()
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.4}})]},
                      {"calls": [("gym_run", {"code": CODE, "why": "a switch to sweep against"})]}]
        out = self.researcher().cycle(self.fid)
        refused = json.loads(calls_in(self.sail.bodies[1])[-1]["output"])
        self.assertIn("a PARAMS change is a sweep", refused["reason"])
        self.assertTrue(out["single_run_refused"])
        self.assertEqual(out["model_calls"], 2, "a refused answer may be repaired within the cycle")
        self.assertEqual(len(self.pool.train()), 2, "the starter and the fix: never the PARAMS change")
        self.assertEqual(family_ledger.rows(self.store, self.fid)[-1]["change"], "a switch to sweep against")
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "nothing new"})]}]
        out = self.researcher().cycle(self.fid)
        self.assertTrue(out.get("hold"), "a hold is always allowed")

    def test_the_single_run_rule(self):
        self.first()  # the latest version: the seed's starter, its params {}
        r = self.researcher()
        fam = self.store.family(self.fid)
        latest = self.store.latest_version(self.fid)
        self.assertIsNone(r.single_run_refusal(fam, {}), "the latest version exactly")
        self.assertIsNone(r.single_run_refusal(fam, {"hold": True, "params": {"vrp_min": 1.4}}), "a hold")
        self.assertIsNone(r.single_run_refusal(fam, {"code": CODE, "params": {"threshold": 1}}), "new code: a fix")
        self.assertIsNotNone(r.single_run_refusal(fam, {"params": {"vrp_min": 1.4}}))
        self.assertIsNotNone(r.single_run_refusal(fam, {"code": latest["code"], "params": {"vrp_min": 1.4}}))
        self.assertIsNone(r.single_run_refusal(fam, {"code": latest["code"]}), "the program as written is the latest's {}")
        self.store.add_version(self.fid, latest["code"], {"vrp_min": 1.3}, author="synthetic")
        self.assertIsNotNone(r.single_run_refusal(self.store.family(self.fid), {"code": latest["code"]}),
                             "back to the defaults is a PARAMS change too")

    def test_a_second_sweep_in_one_answer_is_refused_never_queued(self):
        self.first()
        variants = [{"threshold": 500}, {"threshold": 600}, {"threshold": 700}]
        self.steps = [{"calls": [("gym_sweep", {"code": CODE, "variants": variants}),
                                 ("gym_sweep", {"code": CODE, "variants": [{"threshold": 800}, {"threshold": 900},
                                                                           {"threshold": 1000}]})]}]
        out = self.researcher().cycle(self.fid)
        self.assertFalse(out["pending_run"])
        self.assertIsNone(self.store.convo(self.fid)[1])
        outputs = [json.loads(i["output"]) for i in self.store.convo(self.fid)[0][-1]["items"]
                   if i.get("type") == "function_call_output"]
        self.assertIn("one sweep a cycle", outputs[-1]["reason"])
        self.assertEqual(len(self.pool.train()), 1 + 4)

    def test_no_room_for_a_sweep_costs_no_model_call(self):
        self.first()
        self.settings["researcher"]["max_sweep_jobs_in_flight"] = 6
        r = self.researcher()
        self.assertTrue(r._reserve_sweep("someone-else", 3))
        cycles = self.store.family(self.fid)["cycles"]
        events = len(self.store.events_after(0))
        out = r.cycle(self.fid)
        self.assertEqual((out["model_calls"], out.get("sweep_wait"), r.sweep_waits), (0, 3, 1))
        self.assertNotIn("error", out, "a wait for room is no error")
        self.assertEqual((self.store.family(self.fid)["cycles"], len(self.store.events_after(0))), (cycles, events),
                         "nothing was asked of a model or the Gym: no cycle, no event")
        self.assertEqual(self.sail.bodies, [])
        scheduler = Scheduler(self.store, clock=self.clock, settings=self.settings)
        self.assertEqual(scheduler.take(idle_seconds=0), self.fid)
        scheduler.release(self.fid, out)
        self.assertEqual((scheduler.cooldown[self.fid] - self.clock(), scheduler.errors.get(self.fid)), (60.0, None),
                         "a flat wait, never an error's growing backoff")
        self.settings["researcher"]["sweep_wait_seconds"] = 15
        self.assertEqual(sweep_wait(self.settings), 15.0)
        self.settings["researcher"]["max_sweep_jobs_in_flight"] = 3
        self.assertFalse(self.researcher().sweep_cycle, "room for no sweep and its placebo: the cycle as before, never a wait")

    def test_every_path_writes_its_row_and_the_status_can_leave_the_ledger_out(self):
        self.first()
        self.store.set_state(self.fid, rewrite_ready={"code": CODE, "profile": "pro_asap", "at": self.clock()})
        self.steps = [{"text": "read it"}]
        out = self.researcher().cycle(self.fid)
        self.assertEqual((out.get("rewrite"), out["model_calls"]), ("pro_asap", 1), "the rewrite's run is read in one answer")
        rows = family_ledger.rows(self.store, self.fid)
        self.assertEqual([r["change"] for r in rows], ["the starter program", "a rewrite by pro_asap after a stall"])
        fam = self.store.family(self.fid)
        self.assertIn("YOUR LEDGER", self.researcher().status(fam))
        self.settings["researcher"]["ledger_chars"] = 0
        self.assertNotIn("YOUR LEDGER", self.researcher().status(fam))

    def test_off_the_cycle_is_as_before(self):
        self.settings["researcher"]["sweep_cycle"] = False
        self.first()
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.4}})]}, {"text": "read it"}]
        out = self.researcher().cycle(self.fid)
        self.assertEqual(out["model_calls"], 2, "a REVISE and a READ turn")
        self.assertNotIn("single_run_refused", out)
        self.assertEqual([t["name"] for t in self.sail.bodies[0]["tools"]], ["gym_run", "gym_sweep"])
        self.assertNotIn("Placebo row", self.sail.bodies[0]["input"][1]["content"])


if __name__ == "__main__":
    unittest.main()
