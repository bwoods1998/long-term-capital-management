"""RELEASE 1023a, THE BIRTHS-TEXT FIXES (the edge hunt of Oct 16, 2026, Tier 3; league/swarm/elane_births.py):
T1 the one-session ask says that an overnight index hold reads as calendar_flow / days_1_3, a cell rows bind for the
index ETFs, so it needs a valid card.rebirth (and keeps "or another 1-session hold"); T2 the card template carries
card.rebirth and the graveyard points at it ("differs_from alone does not admit it"), and each pass's event logs which
field each proposal filled; T3 an OPEN CELLS line per universe group, rules only; THE CALENDAR SENTENCE in the births'
agenda and the Train brief; the MTE label (T5's small part); THE BIRTHS YIELD info line (T4's, league/ops/
elane_health.py). Words and one event field only: no admission, quota, seat, screen, bar or graveyard code changes.
Every family and number here is invented."""

from __future__ import annotations

import inspect
import json
import re
import unittest

from league.ops import elane_health
from league.swarm import cards, elane_births, elane_train, event_hold
from league.swarm.elane_births import (OPEN_CELLS_HEADER, OVERNIGHT, SESSION_ASK, SESSION_ASK_CHARS, EquityPass,
                                       EquityQuota, bound_cells, claim_fields, open_cells_text, overnight_bound,
                                       overnight_words)
from league.tests import elane_e2_fakes as fx
from league.tests import test_elane_route_text as rt
from league.tests.test_elane_birth_cells import Cells


class T1TheOvernightCell(Cells):
    def request(self, arch=None) -> str:  # noqa: D401 - the request's user turn
        return super().request(arch)

    def test_rows_on_the_index_overnight_cell_make_the_ask_say_it_is_bound(self):
        self.refuted("dead-overnight-beta", lane="beta", symbols=("SPY",))
        self.refuted("dead-overnight-equity", lane="equity", symbols=("QQQ",))
        user = rt.flat(self.request())
        bound = rt.flat(SESSION_ASK.format(overnight=OVERNIGHT["bound"].format(lanes="in both lanes")))
        self.assertIn(bound, user)
        for words in ("An overnight index hold reads as calendar_flow / days_1_3, bound for the index ETFs in both lanes",
                      "it needs a valid card.rebirth naming one of that cell's rows",
                      "or propose another 1-session hold"):
            self.assertIn(words, user)
        self.assertLessEqual(len(bound), SESSION_ASK_CHARS)

    def test_one_lane_bound_names_that_lane(self):
        self.refuted("dead-overnight-beta", lane="beta", symbols=("SPY",))
        self.assertIn("bound for the index ETFs in the beta lane", rt.flat(self.request()))

    def test_a_sector_row_does_not_bind_the_index_cell(self):
        self.refuted("dead-flow")  # calendar_flow / equity:etf / days_1_3 on a sector ETF
        user = rt.flat(self.request())
        self.assertIn(rt.flat(SESSION_ASK.format(overnight=OVERNIGHT["open"])), user)
        self.assertNotIn("bound for the index ETFs", user)

    def test_the_binding_the_ask_reads_is_the_admissions_own(self):
        self.refuted("dead-overnight-beta", lane="beta", symbols=("SPY",))
        index = EquityPass(self.arch).rebirth_index()
        cells = bound_cells(index)
        self.assertIn(("calendar_flow", "beta:etf", "days_1_3", "index"), cells)
        self.assertEqual(overnight_bound(cells), ["beta"])
        # The admission refuses a claimless overnight card on SPY in that cell, as the ask now says.
        checked, _ = cards.validate(fx.card("beta", ("SPY",)), "etf", roots=["SPY"], settings=self.settings)
        self.assertFalse(index.check(checked, "etf", "Buy SPY at the close and sell it at the open, overnight.", None,
                                     roots=["SPY"])["ok"])
        self.assertIsNone(overnight_bound(None), "an unreadable binding: the rule in words")
        self.assertEqual(overnight_words(None), OVERNIGHT["unknown"])
        self.assertEqual(bound_cells(None), set(), "rebirth off: nothing binds")
        self.assertIsNone(bound_cells(False))

    def test_the_ask_still_binds_nothing(self):
        for fn in (EquityPass.admit, EquityQuota.__init__, EquityQuota.why_not, EquityQuota.admits, EquityQuota.born,
                   EquityQuota.event, EquityQuota.index_ask):
            source = inspect.getsource(fn)
            for word in ("overnight_bound", "overnight_words", "OVERNIGHT", "session_ask"):
                self.assertNotIn(word, source, fn.__qualname__)


class T2TheClaimField(Cells):
    def test_the_card_template_carries_card_rebirth(self):
        system = rt.flat(elane_births.SYSTEM)
        for words in ('"rebirth": {"row": "<only for a card in a cell the birth cells block lists: one of that cell\'s '
                      'row ids>", "different": "the mechanism-level change", "evidence": "names the input the row did not '
                      'read and what it shows, or cites a run id or a card_evidence seq"}',
                      '"differs_from": ["<an EQUITY GRAVEYARD id: a note only, it admits nothing>"]',
                      "differs_from alone does not admit it", 'Omit "rebirth" in a cell no row binds.'):
            self.assertIn(words, system)
        # The template's object is still one JSON shape a model can fill: the card holds the rebirth.
        self.assertLess(system.index('"card": {'), system.index('"rebirth": {'))
        self.assertLess(system.index('"rebirth": {'), system.index('"program":'))

    def test_the_graveyard_points_at_card_rebirth_while_rows_bind(self):
        self.refuted("dead-flow")
        user = rt.flat(self.request())
        self.assertIn(rt.flat(elane_births.GRAVEYARD_BINDS), user)
        for words in ("born only with a valid card.rebirth", "differs_from alone does not admit it",
                      "cites a run id or a card_evidence seq"):
            self.assertIn(words, user)
        self.assertNotIn("names it in differs_from and says the mechanism-level difference", user)

    def test_with_the_rebirth_switch_off_the_header_claims_no_rebirth_rule(self):
        self.refuted("dead-flow")
        settings = fx.settings(max_per_pass=4)
        settings["architect"]["card_rebirth"] = "off"
        from league.swarm.architect import Architect

        user = self.request(Architect(self.store, self.router, settings, clock=self.clock))
        self.assertIn(rt.flat(elane_births.GRAVEYARD_SOFT), rt.flat(user))
        self.assertNotIn("born only with a valid card.rebirth", rt.flat(user))

    def test_the_pass_event_logs_which_field_each_proposal_filled(self):
        self.born_options(9)
        rebirth = fx.proposal("with-rebirth", symbols=("QQQ",),
                              card=fx.card("beta", ("QQQ",), rebirth={"row": "dead-x", "different": "x", "evidence": "y"}))
        both = fx.proposal("with-both", symbols=("IWM",), differs_from=["dead-x"],
                           card=fx.card("beta", ("IWM",), rebirth={"row": "dead-x", "different": "x", "evidence": "y"}))
        differs = fx.proposal("with-differs", symbols=("DIA",), differs_from=["dead-x"])
        neither = fx.proposal("with-neither", symbols=("SPY",))
        self.answers.append(fx.answer([rebirth, both, differs, neither]))
        self.pass_()
        [event] = [e["payload"] for e in self.store.events_after(0, limit=10000) if e["kind"] == "swarm.elane"
                   and e["payload"].get("pass") == "births"]
        logged = event["claim_fields"]
        self.assertEqual(logged["counts"], {"rebirth": 2, "differs_from": 2, "both": 1, "neither": 1})
        self.assertEqual(logged["each"], [{"n": 1, "rebirth": True, "differs_from": False},
                                          {"n": 2, "rebirth": True, "differs_from": True},
                                          {"n": 3, "rebirth": False, "differs_from": True},
                                          {"n": 4, "rebirth": False, "differs_from": False}])
        self.assertNotIn("dead-x", json.dumps(logged), "places and booleans only, never a word the model wrote")

    def test_claim_fields_reads_any_answer(self):
        self.assertEqual(claim_fields([]), {"each": [], "counts": {"rebirth": 0, "differs_from": 0, "both": 0,
                                                                   "neither": 0}})
        odd = claim_fields(["not a row", {"card": "no card", "differs_from": "not a list"},
                            {"card": {"rebirth": {"row": "  "}}, "differs_from": [" "]}])
        self.assertEqual(odd["counts"], {"rebirth": 0, "differs_from": 0, "both": 0, "neither": 2})
        self.assertEqual([e["n"] for e in odd["each"]], [2, 3], "the place in the answer, a non-row skipped")
        many = claim_fields([{"slug": str(i)} for i in range(30)])
        self.assertEqual(len(many["each"]), elane_births.CLAIM_FIELDS_SHOWN)
        self.assertEqual(many["counts"]["neither"], 30)


class T3TheOpenCells(Cells):
    def block(self, user: str) -> str:
        start = user.index("OPEN CELLS (")
        return user[start:user.index("\n\n", start)] if "\n\n" in user[start:] else user[start:]

    def test_every_open_cell_per_universe_group_and_no_bound_one(self):
        self.refuted("dead-flow")  # calendar_flow / equity:etf / days_1_3, sectors
        self.refuted("dead-overnight-beta", lane="beta", symbols=("SPY",))  # calendar_flow / beta:etf / days_1_3, index
        block = self.block(self.request())
        lines = block.splitlines()
        self.assertTrue(lines[0].startswith(OPEN_CELLS_HEADER))
        groups = [line.split(" (", 1)[0] for line in lines[1:]]
        self.assertEqual(groups, ["- the index ETFs", "- the sector ETFs", "- the defensive ETFs"])
        index, sectors, defensive = lines[1:]
        self.assertIn("(SPY, QQQ, IWM and DIA)", index)
        self.assertIn("beta:etf: ", index)
        self.assertIn("calendar_flow (days_4_10, days_11_plus)", index.split(" | ")[0], "beta: the bound holding left out")
        self.assertIn("calendar_flow (any holding)", index.split(" | ")[1], "equity: no index row there")
        self.assertIn("calendar_flow (days_4_10, days_11_plus)", sectors.split(" | ")[1])
        self.assertIn("calendar_flow (any holding)", defensive)
        for line in lines[1:]:
            self.assertIn("equity_premium (any holding)", line)
            self.assertEqual(line.count(" | "), 1, "two lanes of one structure")

    def test_rules_only(self):
        self.refuted("dead-flow")
        block = self.block(self.request())
        self.assertNotIn("dead-flow", block, "no row id")
        self.assertIsNone(rt.OUTCOME.search(block))
        digits = set(re.findall(r"\d+", re.sub(r"days_\d+(?:_\d+|_plus)", "", block)))
        self.assertEqual(digits, set(), "no count, no Train figure: the holdings' words alone carry digits")
        for word in ("overnight", "intraday", "price", "volatility"):
            self.assertNotIn(word, block.split(":", 1)[1], "no word of the graveyard's text reading")

    def test_with_no_row_every_cell_is_open_and_with_the_binding_unread_nothing_is_said(self):
        text = open_cells_text(set(), self.settings)
        self.assertEqual(text.count("(any holding)"), 6 * 2 * 3, "six classes, two lanes, three groups")
        self.assertEqual(open_cells_text(None, self.settings), "")
        off = fx.settings()
        off["elane"]["mode"] = "off"
        self.assertEqual(open_cells_text(set(), off), "")

    def test_a_row_with_no_group_binds_every_group(self):
        index = type("I", (), {"equity_rows": [{"row": "r", "key": {"class": "trend_momentum", "family": "equity:etf",
                                                                     "holding": "days_4_10"}}]})()
        cells = bound_cells(index)
        self.assertEqual({c[3] for c in cells}, set(elane_train.GROUPS))
        for line in open_cells_text(cells, self.settings).splitlines()[1:]:
            beta, equity = line.split(" | ")
            self.assertIn("trend_momentum (any holding)", beta, "the row's own lane alone")
            self.assertIn("trend_momentum (days_1_3, days_11_plus)", equity, "every group of its lane")


class TheCalendarSentence(Cells):
    def test_in_the_births_agenda_and_the_train_brief(self):
        sentence = event_hold.calendar_text()
        self.assertTrue(sentence)
        self.assertIn(sentence, elane_births.agenda_text(self.settings))
        self.assertIn(sentence, elane_births.agenda_text())
        self.assertEqual(self.request().count(sentence), 1)
        fam = fx.e2_family(self.store, "researching-one")
        researcher = elane_train.EquityResearcher(self.store, self.router, self.settings, root=self.store.root,
                                                  clock=self.clock)
        brief = researcher.brief(self.store.family(fam["id"]))
        self.assertIn(sentence, brief)
        self.assertLess(brief.index("ITS AGENDA MECHANISM"), brief.index(sentence))

    def test_it_is_the_one_place_the_request_names_a_2026_date(self):
        user = self.request()
        self.assertRegex(event_hold.calendar_text(), r"2026-09-11")
        self.assertNotRegex(user.replace(event_hold.calendar_text(), ""), r"\b202[56]\b")


class TheMTELabel(unittest.TestCase):
    def test_wherever_an_author_reads_mte(self):
        self.assertIn("MTE: selection-only and timing-blind", rt.flat(elane_train.bar_text()))
        line = elane_train.version_text(1, {"passed": False, "fails": ["Y2"], "summary": {}, "years": {},
                                            "beside": {"bh_pnl": 1.0, "mte_mean": -0.1, "mte_t": -2.0,
                                                       "drift_share": 0.9}})
        self.assertIn("MTE (selection-only, timing-blind) mean", line)


class T4TheBirthsYield(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path

        from league.swarm.store import SwarmStore
        from league.tests.swarm_fakes import Clock

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.clock = Clock(1_792_000_000.0)
        self.root = Path(tmp.name)
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)

    def passes(self, *rows: dict) -> None:
        for row in rows:
            self.store.event("swarm.elane", None, {"pass": "births", **row})

    def yield_(self) -> dict:
        from league.ops import guard

        return guard.read(self.root / "swarm.sqlite",
                          lambda db: elane_health.births_yield(db, self.clock() - 86400.0, self.clock() + 1.0))

    def test_counts_by_share_places_and_claim_fields(self):
        self.passes({"born": [], "proposed": 6, "refused": {"count": 6, "items": []}, "equity_want": 6,
                     "equity_refused_by_quota": 6, "panel": {"want": 6, "born": 0}},
                    {"born": ["a", "b"], "proposed": 4, "refused": {"count": 2, "items": []}, "equity_want": 3,
                     "equity_refused_by_quota": 1, "panel": {"want": 1, "born": 0},
                     "claim_fields": {"each": [], "counts": {"rebirth": 1, "differs_from": 2, "both": 0, "neither": 1}}},
                    {"born": ["c", "d", "e"], "proposed": 5, "refused": {"count": 2, "items": []}, "equity_want": 5},
                    {"skipped": "usd_day", "why": "a line"})
        y = self.yield_()
        self.assertEqual((y["passes"], y["born"], y["proposed"], y["refused"], y["quota_refused"]), (3, 5, 15, 10, 7))
        self.assertEqual((y["share_places"], y["panel_places"], y["panel_born"]), (7, 7, 0))
        self.assertEqual(y["by_share_places"], {"0": {"passes": 1, "born": 0}, "1-3": {"passes": 1, "born": 2},
                                                "4+": {"passes": 1, "born": 3}})
        self.assertEqual(y["claims"], {"rebirth": 1, "differs_from": 2, "both": 0, "neither": 1})
        self.assertEqual(y["per_pass"], 1.67)
        self.assertTrue(y["line"].startswith("INFO, THE BIRTHS YIELD (not a cause, no owner step): 3 equity passes"))
        self.assertIn("0 places 1 passes 0 born; 1-3 places 1 passes 2 born; 4+ places 1 passes 3 born", y["line"])

    def test_no_pass(self):
        y = self.yield_()
        self.assertEqual((y["passes"], y["per_pass"], y["claims"]), (0, None, None))
        self.assertIn("no equity pass asked a model", y["line"])

    def test_not_a_cause_not_an_owner_step_no_lever_not_in_the_done_reader(self):
        self.assertNotIn("births_yield", elane_health.CAUSES)
        self.assertEqual(elane_health.CAUSES, ("elane_dq", "elane_births", "elane_idle", "elane_refused"))
        self.assertNotIn("births_yield", elane_health.BIRTH_LEVERS)
        self.assertNotIn("yield", " ".join(elane_health.BIRTH_LEVERS))
        for fn in (elane_health.judge, elane_health.checks, elane_health.mailed):
            self.assertNotIn("births_yield", inspect.getsource(fn))
        from pathlib import Path

        report = (Path(elane_health.__file__).resolve().parent / "dlane_report.py").read_text()
        self.assertNotIn("births_yield", report)
        self.assertNotIn("BIRTHS YIELD", report)
        self.assertEqual(set(elane_health.YIELD_CLAIMS),
                         set(claim_fields([])["counts"]), "the yield counts the births' own claim fields")

    def test_in_the_report_and_its_text(self):
        self.passes({"born": ["a"], "proposed": 2, "refused": {"count": 1, "items": []}, "equity_want": 2})
        doc = elane_health.report(self.root, now=self.clock() + 1.0, settings=fx.settings())
        self.assertIn("births_yield", doc["info"])
        self.assertNotIn("births_yield", doc["checks"])
        self.assertIn(doc["info"]["births_yield"]["line"], elane_health.text(doc))


if __name__ == "__main__":
    unittest.main()
