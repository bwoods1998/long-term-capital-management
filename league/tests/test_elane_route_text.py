"""THE ROUTE BY SYMBOLS AND THE INDEX-ONLY ASK (L2, Oct 15, 2026; league/swarm/elane_births.py `SYSTEM`, `route_text`,
`lanes_text`, `tried_text`, `EquityQuota.index_ask` and `text`): the equity architect is told the route R-SEC gives a
program by its symbols (an index-only program takes the one Validation try and the one sealed look, then waits for a
Probe seat; any other symbol, and a panel program, goes by the forward screen FWD1-R alone), in R-SEC's own index set,
rules only (no count, no seat yield, no word of a look's outcome: A26, A9 D3); and THE EQUITY QUOTA's lines ask, softly,
for at least 1 and up to half of the share-program places to be index-only families in cells no row binds, with no place
reserved and no admission changed. L2's follow-up: the Train bar's last sentence, THE RATION, the continuation
refusal's sentence and the panel block say the same route, and the whole request is read for the old claim. Every
family and number here is invented."""

from __future__ import annotations

import json
import re
import unittest
from unittest import mock

from league.equity import config as econfig
from league.ops import elane_health, fwd1_rule
from league.swarm import elane, elane_births, elane_train, elane_xs
from league.swarm.elane_births import LAST_KEY, EquityPass, EquityQuota
from league.tests import elane_e2_fakes as fx
from league.tests import elane_xs_fakes as F
from league.tests import test_elane_e2_births as births

#: Words a generator text may never carry of a look or a seat (A26: "spent" by rule, never "looked at", "passed" or
#: "failed"; A9 D3: no outcome; L2: no pass count and no seat yield). "pass" itself is said only as "this pass" (the
#: births pass the request is for: `PASS_WORD`).
OUTCOME = re.compile(r"\b(looked|look(?:ed)?[- ]at|passed|fail|fails|failed|yield|yields|seated|won|lost)\b|%",
                     re.IGNORECASE)
PASS_WORD = re.compile(r"\bpass\w*", re.IGNORECASE)
#: The claim R-SEC made false, in the words the request used to carry: the system prompt's, THE RATION's, the Train
#: bar's last sentence (league/swarm/elane_train.py `bar_text`, the panel's in league/swarm/elane_xs.py), the panel
#: block's and the next request's sentence for a continuation refusal (L2's follow-up).
OLD_CLAIMS = ("Every program is judged the same way", "if it passes, real money", "ONE Validation try and ONE sealed look "
              "a LINEAGE", "one already looked at", "a looked-at program", "ONE Validation try, then ONE sealed look",
              "has its one Validation try", "then by the screen XS1")


def flat(text: str) -> str:
    return " ".join(text.split())


def ration_line(lanes: str) -> str:
    return next(line for line in lanes.splitlines() if line.startswith("- THE RATION"))


class Case(births.BirthCase):
    def quota(self, want: int, panel: int = 0, settings=None) -> EquityQuota:
        q = EquityQuota(self.store, settings or self.settings, now=self.clock())
        q.want, q.panel = want, panel
        return q


class TheRouteIsSaid(Case):
    def test_the_system_prompt_says_the_route_by_symbols(self):
        system = flat(elane_births.SYSTEM)
        index = ", ".join(econfig.INDEX_ETFS)
        for words in (f"A program whose every symbol is an index ETF ({index}) takes its lineage's ONE Validation try "
                      "(2025) and ONE sealed holdout look (2026) by the share screen S2,",
                      "a program S2's rule admits then waits for a Probe seat",
                      "A program naming any other symbol (a sector ETF, TLT, GLD) never takes a sealed try or a sealed look",
                      "its only route to money is the forward screen FWD1-R, which reads only the sessions after the "
                      "program is registered",
                      f"its first verdict after {fwd1_rule.PLAN[0]} forward sessions, labelled WEAK",
                      "A panel program likewise never takes a sealed try (A34)",
                      "Its route after Train is set by its symbols alone (R-SEC)"):
            self.assertIn(words, system)
        for claim in OLD_CLAIMS:
            self.assertNotIn(claim, system)

    def test_the_first_verdict_is_fwd1s_first_checkpoint(self):
        # No swarm module imports league/ops/fwd1_rule.py (its docstring), so the test holds the two equal.
        self.assertEqual(elane_births.FWD1_FIRST_SESSIONS, fwd1_rule.PLAN[0])
        self.assertTrue(fwd1_rule.weak("ETF", fwd1_rule.PLAN[0]), "every ETF verdict is labelled WEAK")

    def test_the_lanes_block_says_it_in_the_universes_own_symbols(self):
        lanes = elane_births.lanes_text(self.settings)
        route = next(line for line in lanes.splitlines() if line.startswith("- THE ROUTE BY SYMBOLS"))
        self.assertIn("A program whose every symbol is an index ETF (SPY, QQQ, IWM and DIA) then takes its lineage's ONE "
                      "Validation try and ONE sealed holdout look by the share screen S2", route)
        self.assertIn("waits for a Probe seat", route)
        self.assertIn("A program naming any other symbol of THE UNIVERSE (XLK, XLF, XLE, TLT, GLD) never takes a sealed "
                      "try or a sealed look: its only route to money is the forward screen FWD1-R, on the sessions after "
                      f"it is registered, with its first verdict after {fwd1_rule.PLAN[0]} forward sessions, labelled "
                      "WEAK", route)
        self.assertIn("A panel program likewise (A34)", route)
        self.assertIn("- THE RATION: ONE route a LINEAGE.", lanes)
        # What `elane.same_lineage` compares at a look: a program that has taken its sealed look or is taking it (a
        # forward-only lineage spent by its Train pass is never looked at, so it is not named here).
        self.assertIn("At an index-only program's sealed look, it is the same lineage as a program that has taken its "
                      "sealed look, or is taking it, when it has that program's template in the same lane or its Train "
                      "daily returns correlate 0.7 or more with that program's; such a near-copy is refused at its own "
                      "look.", ration_line(lanes))
        self.assertNotIn("of a spent lineage", ration_line(lanes))
        self.assertLess(lanes.index("- THE ROUTE BY SYMBOLS"), lanes.index("- THE RATION"))
        for claim in OLD_CLAIMS:
            self.assertNotIn(claim, lanes)
        self.assertNotRegex(lanes, r"\b202[56]\b", "the request names no Validation or holdout year")

    def test_the_request_carries_it(self):
        # The whole request, with a lineage that has its try and a continuation refusal of the last pass in it (so
        # LINEAGES WITH THEIR TRY and the refusal's sentence are read too).
        fx.e2_family(self.store, "tried-one", record={"status": "passed", "passed_version": 1, "versions": {}})
        self.store.put(LAST_KEY, {"at": "not a time",  # said as "the last pass": the request names no year
                                  "refused": [{"slug": "x", "why": "x", "cls": "tried_lineage", "n": 1}]})
        system, user = EquityPass(self.arch).request(EquityQuota(self.store, self.settings, now=self.clock()))
        self.assertIn("Its route after Train is set by its symbols alone (R-SEC)", flat(system))
        self.assertIn("- THE ROUTE BY SYMBOLS", user)
        self.assertIn("A SOFT ASK, no place reserved", user)
        self.assertIn("LINEAGES WITH THEIR TRY (each below is spent by rule", user)
        self.assertIn("- proposal 1: it continues a lineage spent by rule", user)
        self.assertIn(flat(elane_train.bar_text()), flat(user))
        for claim in OLD_CLAIMS:
            self.assertNotIn(claim, flat(system), claim)
            self.assertNotIn(claim, flat(user), claim)
        self.assertNotRegex(user, r"\b202[56]\b")

    def test_an_index_only_universe_names_no_forward_symbol_and_still_says_the_rule(self):
        index = fx.settings()
        index["elane"]["universe"] = ["SPY", "QQQ"]
        route = elane_births.route_text(index)
        self.assertIn("an index ETF (SPY and QQQ)", route)
        self.assertIn("A program naming any other symbol of THE UNIVERSE never takes a sealed try", route)

    def test_a_universe_with_no_index_etf_says_so(self):
        sectors = fx.settings()
        sectors["elane"]["universe"] = ["XLK", "TLT"]
        self.assertEqual(elane_births.route_symbols(sectors), ([], ["XLK", "TLT"]))
        self.assertIn("an index ETF (none is open now)", elane_births.route_text(sectors))


class TheOtherTextsSayTheSameRoute(Case):
    """L2's follow-up: the texts the request (and a Train brief) carries beside the route line say no other route."""

    def test_the_train_bar_is_route_neutral(self):
        # elane_train.bar_text ends the LANES/EQUITY block and every share family's Train brief, sector ones included.
        bar = flat(elane_train.bar_text())
        self.assertTrue(bar.endswith("The first version that passes spends its lineage's one route, set by its symbols "
                                     "(R-SEC): for an index-only program its ONE Validation try and ONE sealed look; for "
                                     "any other, the forward screen FWD1-R. No outcome of either is ever shown to anyone "
                                     "who writes programs."), bar[-300:])
        for claim in OLD_CLAIMS:
            self.assertNotIn(claim, bar, claim)
        self.assertTrue(flat(elane_births.lanes_text(self.settings)).endswith(bar), "the block ends with the bar")

    def test_the_continuation_refusal_says_spent_and_health_still_reads_the_admissions_words(self):
        said = elane_births.refusal_said({"cls": "tried_lineage"}, self.settings)
        self.assertEqual(said, "it continues a lineage spent by rule (LINEAGES WITH THEIR TRY; no outcome is shown): "
                               "propose a different idea")
        self.assertIsNone(OUTCOME.search(said))
        # league/ops/elane_health.py classes a refusal by the admission's own text, which is unchanged.
        for why in ("it continues seed-x's lineage, which has its one Validation try (outcome sealed): propose a "
                    "different idea", "its rebirth continues seed-x's lineage, which has its one Validation try (outcome "
                    "sealed): propose a different idea"):
            self.assertEqual(next(cls for start, cls, _ in elane_health.REFUSALS if why.startswith(start)),
                             "tried_lineage", why)


class ThePanelSaysItsRoute(unittest.TestCase):
    """The panel block of the equity request (league/swarm/elane_xs.py `request_text`, `bar_text`) under the House's
    A34: no sealed try and no XS1 look; with the historical route open (a test's world), the words as built."""

    def block(self, historical: bool) -> str:
        F.switch_on(self, historical=historical)
        store = F.new_store(self)
        F.ready(store.root)
        block = elane_xs.request_text(store, F.settings("gate"), 4)
        self.assertTrue(block)
        return flat(block)

    def test_under_a34_the_panel_block_says_the_forward_screen(self):
        self.assertIs(elane_xs.A34_FORWARD_ONLY, True, "the House's value")
        block = self.block(historical=False)
        self.assertIn(elane_xs.ROUTE_A34, block)
        self.assertIn("by the bar below on Train and then by the forward screen FWD1-R alone (A34: no XS1 look)", block)
        self.assertIn("XS1", flat(elane_xs.bar_text()))
        for claim in OLD_CLAIMS:
            self.assertNotIn(claim, block, claim)

    def test_with_the_historical_route_open_the_words_are_as_built(self):
        block = self.block(historical=True)
        self.assertIn(elane_xs.ROUTE_HISTORICAL, block)
        self.assertIn("by the bar below on Train and then by the screen XS1;", block)


class TheIndexSetIsRSECs(Case):
    def test_the_split_is_forward_only_itself_over_the_whole_code_universe(self):
        wide = fx.settings()
        wide["elane"]["universe"] = list(econfig.UNIVERSE)
        sealed, forward = elane_births.route_symbols(wide)
        named = [s for s in elane_births.universe(wide)["etf"]]
        self.assertEqual(sorted(sealed + forward), sorted(named))
        for sym in named:
            self.assertEqual(sym in forward, elane.forward_only({"roots": [sym]}), sym)
        self.assertEqual(set(sealed), set(econfig.INDEX_ETFS) & set(named))
        self.assertTrue(forward, "the code's universe holds symbols outside the index ETFs")

    def test_not_a_copied_list(self):
        # R-SEC's tuple narrowed in place: the route, the soft ask and the split follow it (the system prompt is built
        # from the same tuple at import).
        with mock.patch.object(econfig, "INDEX_ETFS", ("SPY",)):
            sealed, forward = elane_births.route_symbols(self.settings)
            self.assertEqual(sealed, ["SPY"])
            self.assertIn("QQQ", forward)
            self.assertIn("an index ETF (SPY) then", elane_births.route_text(self.settings))
            self.assertIn("every symbol one of SPY:", self.quota(3).text())
        self.assertIn("(" + ", ".join(econfig.INDEX_ETFS) + ")", elane_births.SYSTEM)


class NoOutcomeWord(Case):
    def texts(self) -> dict[str, str]:
        lanes = elane_births.lanes_text(self.settings)
        texts = {"the system prompt": elane_births.SYSTEM, "the route": elane_births.route_text(self.settings),
                 "the ration": ration_line(lanes)}
        for want in (1, 2, 3, 6):
            q = self.quota(want)
            text = q.text()
            texts[f"the soft ask at want {want}"] = text[text.index("A SOFT ASK"):]
        fam = fx.e2_family(self.store, "tried-one", record={"status": "passed", "passed_version": 1, "versions": {}})
        self.assertTrue(elane_births.tried(fam))
        tried = elane_births.tried_text(self.store)
        texts["the tried lineages' header"] = tried.splitlines()[0]
        return texts

    def test_no_pass_count_no_seat_yield_no_look_outcome(self):
        for where, text in self.texts().items():
            self.assertTrue(text, where)
            self.assertIsNone(OUTCOME.search(text), (where, OUTCOME.search(text)))
            for m in PASS_WORD.finditer(text):
                self.assertEqual((m.group(0).lower(), text[max(0, m.start() - 5):m.start()].lower()), ("pass", "this "),
                                 (where, text[max(0, m.start() - 30):m.end() + 30]))
            self.assertNotIn("seat yield", text, where)

    def test_the_tried_header_says_the_route_taken(self):
        fx.e2_family(self.store, "tried-two", record={"status": "passed", "passed_version": 1, "versions": {}})
        header = elane_births.tried_text(self.store).splitlines()[0]
        self.assertIn("LINEAGES WITH THEIR TRY (each below is spent by rule", header)
        self.assertIn("an index-only one its one Validation try, any other the forward screen", header)
        self.assertIn("a proposal continuing one is not born", header)


class TheSoftAsk(Case):
    def test_at_want_3_it_cannot_take_every_place(self):
        q = self.quota(3)
        self.assertEqual(q.index_ask(), (1, 1))
        text = q.text()
        self.assertIn("This pass: propose 3; more are not born.", text)
        self.assertIn("A SOFT ASK, no place reserved: 1 of this pass's 3 share-program places should be an index-only "
                      "family (every symbol one of SPY, QQQ, IWM and DIA: THE ROUTE BY SYMBOLS) in cells no row binds "
                      "and not CLOSED (the equity birth cells block lists the bound cells, most rows first; THE EQUITY "
                      "GRAVEYARD lists the CLOSED ones); the other places are open to any symbol of THE UNIVERSE.", text)
        # The block may list only the bound cells with the most rows (it says how many more it does not list), and a
        # CLOSED cell is another key: the ask never calls an unlisted cell unbound.
        self.assertNotIn("does not list", text)
        # The block's own name stays the block's: a request with no bound cell carries no "EQUITY BIRTH CELLS"
        # (test_elane_birth_cells.py reads the name as the block's presence).
        self.assertNotIn("EQUITY BIRTH CELLS", text)

    def test_at_want_6_at_least_1_and_up_to_half(self):
        q = self.quota(6)
        self.assertEqual(q.index_ask(), (1, 3))
        self.assertIn("at least 1 and up to 3 of this pass's 6 share-program places should be index-only families",
                      q.text())

    def test_the_places_are_the_share_programs_not_the_panels(self):
        self.assertEqual(self.quota(6, panel=2).index_ask(), (1, 2))
        self.assertIn("up to 2 of this pass's 4 share-program places", self.quota(6, panel=2).text())
        self.assertEqual(self.quota(3, panel=3).index_ask(), (0, 0))
        self.assertNotIn("SOFT ASK", self.quota(3, panel=3).text())

    def test_small_passes(self):
        # ONE PLACE, ASKED (accepted): want 1 is the quota's floor whenever the equity lanes are at their share, so
        # making no ask at one place would drop the ask from every pass there; it stays a soft ask.
        self.assertEqual(self.quota(1).index_ask(), (1, 1))
        self.assertEqual(self.quota(2, panel=1).index_ask(), (1, 1))
        self.assertIn("1 of this pass's 1 share-program place should be an index-only family", self.quota(1).text())
        self.assertNotIn("the other places", self.quota(1).text())
        self.assertEqual(self.quota(2).index_ask(), (1, 1))
        for want in range(1, 21):
            least, most = self.quota(want).index_ask()
            self.assertEqual((least, most), (1, max(1, want // 2)), want)
            if want >= 2:
                self.assertLess(most, want, "never every place once there are two")

    def test_no_ask_with_no_index_etf_open_or_while_off(self):
        sectors = fx.settings(max_per_pass=4)
        sectors["elane"]["universe"] = ["XLK", "XLF", "TLT"]
        q = self.quota(3, settings=sectors)
        self.assertEqual(q.index_ask(), (0, 0))
        self.assertNotIn("SOFT ASK", q.text())
        off = fx.settings()
        off["elane"]["mode"] = "off"
        q = EquityQuota(self.store, off, now=self.clock())
        self.assertEqual((q.index_ask(), q.text()), ((0, 0), ""))

    def test_no_place_is_reserved(self):
        # The quota's own arithmetic and admission are unchanged: `admits` takes a lane and a structure, never a
        # symbol, so the ask cannot change which proposal takes a place, and every place is admitted while there is room.
        self.born_options(30)
        q = EquityQuota(self.store, self.settings, now=self.clock())
        self.assertEqual((q.want, q.index_ask()), (4, (1, 2)))
        for _ in range(q.want):
            self.assertTrue(q.admits("equity"))
            q.born("equity")
        self.assertFalse(q.admits("equity"))
        self.assertEqual(q.event()["equity_births"], {"beta": 0, "equity": 4})
        event = json.dumps(q.event())
        for words in ("index", "SOFT ASK", "ask"):
            self.assertNotIn(words, event, "the pass's event carries no ask, in its keys or its values")


if __name__ == "__main__":
    unittest.main()
