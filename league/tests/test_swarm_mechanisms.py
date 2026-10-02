"""THE MECHANISM LIBRARY (LTCM v3, league/swarm/mechanisms.py): the curated entries are model-safe and consistent with the
card vocabulary, a card names an entry with its expected activity, the architect admits only births inside the library
(league/swarm/architect.py `admit`) with cross-root lead-lag at most a quarter of births, and its request and system prompt
carry the library while `architect.library` is on. Synthetic families only."""

from __future__ import annotations

import copy
import re
import tempfile
import unittest
from pathlib import Path

from league.swarm import cards, evidence, mechanisms
from league.swarm import settings as S
from league.swarm.architect import LIBRARY_CARD_RULE, SYSTEM, Architect
from league.swarm.store import STRUCTURES, SwarmStore
from league.tests.swarm_fakes import Clock

V3_TYPES = ("debit_vertical", "long_butterfly", "long_call", "long_put", "credit_vertical", "iron_condor", "iron_butterfly")

FLY = {"hypothesis": "Index option buyers pay for protection against market variance, so near-dated index implied volatility "
                     "sits above the variance that follows; a centered butterfly collects the gap.",
       "mechanism_class": "volatility_risk_premium", "inputs": ["implied_vol", "realized_vol"], "holding": "days_1_3",
       "cost": {"hurdle": 0.1, "why": "four legs of half-spread and fees on a narrow index butterfly"},
       "comparison": "the same centered butterfly opened every session at the same minute without the rich-volatility condition",
       "falsification": "the signal's entries do not beat the comparison's on Train in every year",
       "library_class": "index_variance_fly", "sessions_per_year": 120, "structures_per_session": 1}
FLY_MECH = "Near-dated index implied volatility exceeds the realized variance that follows; a long butterfly collects it."
LEAD = {"hypothesis": "A leader root's move against its own norm reaches the lagging root a session later because slow "
                      "capital takes time to rebalance across related roots.",
        "mechanism_class": "relative_value", "inputs": ["underlying_price", "cross_asset"], "holding": "days_1_3",
        "cost": {"hurdle": 0.08, "why": "two half-spreads and fees on a narrow debit vertical"},
        "comparison": "the same debit vertical on the lagging root at the same minute without the leader's condition",
        "falsification": "the signal's entries do not beat the comparison's on Train in every year",
        "library_class": "cross_root_lead_lag", "sessions_per_year": 150, "structures_per_session": 1}
LEAD_MECH = "QQQ's move against its norm while IWM stays flat predicts SPY's next move, which a debit vertical trades."


def fly(slug: str, card=FLY, **kw) -> dict:
    """A butterfly proposal; its mechanism opens with its slug, so no two are the same living idea (`admit`'s duplicate check)."""
    return {"slug": slug, "mechanism": f"{slug}: " + kw.pop("mechanism", FLY_MECH), "structure": kw.pop("structure", "long_butterfly"),
            "roots": kw.pop("roots", ["XSP", "SPY"]), "dte": [1, 2], "rejection": "no edge", "card": card, **kw}


def lead(slug: str, card=LEAD, **kw) -> dict:
    return {"slug": slug, "mechanism": f"{slug}: " + kw.pop("mechanism", LEAD_MECH), "structure": "debit_vertical",
            "roots": kw.pop("roots", ["SPY", "QQQ", "IWM"]), "dte": [3, 7], "rejection": "no edge", "card": card, **kw}


class TheLibrary(unittest.TestCase):
    def test_every_entry_is_consistent_with_the_card_vocabulary_and_the_structures(self):
        self.assertEqual(len(mechanisms.LIBRARY), len(mechanisms.ENTRIES), "one entry a name")
        for e in mechanisms.ENTRIES:
            self.assertTrue(set(e.structures) <= set(STRUCTURES), e.name)
            self.assertTrue(set(e.card_classes) <= set(cards.MECHANISM_CLASSES), e.name)
            self.assertTrue(set(e.holding) <= set(cards.HOLDING), e.name)
            self.assertTrue(set(e.root_groups) <= {"index", "etf", "names"}, e.name)
            self.assertTrue(e.citations, f"{e.name}: every entry cites its literature")
            for c in e.citations:
                self.assertLess(c.year, 2025, f"{e.name}: {c.title} is posted before 2025")
        covered = {s for e in mechanisms.ENTRIES for s in e.structures}
        self.assertTrue(set(V3_TYPES) <= covered, "every v3 structure type has an entry")
        singles = [e.name for e in mechanisms.ENTRIES if set(e.structures) & mechanisms.SINGLES]
        self.assertEqual(singles, ["timing_filtered_long_premium"], "long singles only for the timing-filter class")
        self.assertNotIn("calendar", covered, "no structure outside the v3 list")
        self.assertIn(mechanisms.LEAD_LAG, mechanisms.LIBRARY)

    def test_the_text_a_model_reads_is_model_safe(self):
        text = mechanisms.library_text()
        self.assertEqual(text, text.encode("ascii", "ignore").decode(), "plain ASCII")
        self.assertIsNone(re.search(r"\b(?:19|20)\d\d\b", text), "no year or date")
        self.assertIsNone(re.search(r"\b(?:validat\w*|hold[- ]?outs?|sealed|out[- ]of[- ]sample)\b", text, re.I),
                          "no word of Validation or the holdout")
        self.assertIsNone(re.search(r"\$\s*\d", text), "no dollar figure")
        for e in mechanisms.ENTRIES:
            self.assertIn(f"- {e.name}: ", text)
            for c in e.citations:
                self.assertIn(c.title, text)
        self.assertIn("no long single opened on a Friday and held over the weekend", text)
        self.assertIn("no bearish premium bought while implied volatility is rich", text)
        narrowed = mechanisms.library_text(("debit_vertical", "long_butterfly"))
        self.assertIn("- index_variance_credit: Index variance premium, sold through defined-risk credit structures. Closed",
                      narrowed, "an entry with no allowed structure is listed as closed")
        self.assertNotIn("credit_vertical", narrowed.split("index_variance_fly", 1)[1].split("index_variance_credit", 1)[0])

    def test_a_cards_expected_activity_and_class_are_checked(self):
        got, errors = mechanisms.activity({"library_class": "Index_Variance_Fly", "sessions_per_year": 120.0,
                                           "structures_per_session": "1.5"})
        self.assertEqual(errors, [])
        self.assertEqual(got, {"library_class": "index_variance_fly", "sessions_per_year": 120, "structures_per_session": 1.5})
        _, errors = mechanisms.activity({"library_class": "single_name_mining", "sessions_per_year": 300,
                                         "structures_per_session": 0})
        text = " | ".join(errors)
        for field in ("library_class", "sessions_per_year", "structures_per_session"):
            self.assertIn(field, text)
        self.assertEqual(len(mechanisms.activity({"sessions_per_year": 12.5, "structures_per_session": True})[1]), 3)

    def test_check_names_each_field_outside_its_entry(self):
        card, errors = cards.validate(FLY, "long_butterfly", library=True)
        self.assertEqual(errors, [])
        self.assertEqual(mechanisms.check(card, "long_butterfly", ["XSP", "SPY"]), [])
        bad = {**card, "mechanism_class": "trend_momentum", "holding": "days_11_plus"}
        text = " | ".join(mechanisms.check(bad, "debit_vertical", ["AAPL"]))
        for field in ("structure: debit_vertical", "roots: index_variance_fly trades index, etf roots, not names",
                      "mechanism_class: trend_momentum", "holding: days_11_plus"):
            self.assertIn(field, text)
        thin = {**card, "sessions_per_year": evidence.MIN_DAYS - 1}
        self.assertIn("expected activity", mechanisms.check(thin, "long_butterfly", ["SPY"])[0])
        sparse = {**card, "sessions_per_year": 30, "structures_per_session": 1}
        self.assertIn(f"{evidence.MIN_TRADES} trades", mechanisms.check(sparse, "long_butterfly", ["SPY"])[0],
                      "30 sessions of one structure never reach the line's trades")
        self.assertIn("library_class", mechanisms.check({**card, "library_class": "nope"}, "long_butterfly", ["SPY"])[0])


class Cards(unittest.TestCase):
    def test_without_the_library_the_fields_are_not_read_and_the_sha_is_unchanged(self):
        base = {k: v for k, v in FLY.items() if k not in ("library_class", "sessions_per_year", "structures_per_session")}
        plain, errors = cards.validate(base, "long_butterfly")
        self.assertEqual(errors, [])
        with_fields, _ = cards.validate(FLY, "long_butterfly")
        self.assertEqual(cards.card_sha(plain), cards.card_sha(with_fields), "off: the card is what it was before the library")
        self.assertNotIn("library_class", with_fields)
        missing, errors = cards.validate(base, "long_butterfly", library=True)
        self.assertIsNone(missing)
        self.assertTrue(any(e.startswith("library_class") for e in errors))
        self.assertIn("library_class", cards.validate(None, library=True)[1][0])

    def test_the_researcher_reads_its_class_and_expected_activity(self):
        card, _ = cards.validate(FLY, "long_butterfly", library=True)
        brief = cards.brief_text({"card": card})
        self.assertIn("Library class: index_variance_fly", brief)
        self.assertIn("about 120 traded sessions a year, 1.0 structures a traded session", brief)
        plain, _ = cards.validate(FLY, "long_butterfly")
        self.assertNotIn("Library class", cards.brief_text({"card": plain}))


class Case(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock()
        self.store = SwarmStore(Path(self.dir.name), clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = copy.deepcopy(S.DEFAULTS)
        self.settings["population"].update(start=40, ceiling=60, floor=0)  # refilling: want is max_refill (12)
        self.settings["architect"]["library"] = True
        self.settings["architect"]["max_new"] = 20
        self.settings["gym"]["roots"] = ["SPY", "QQQ", "IWM", "XSP", "SPXW", "AAPL"]

    def arch(self) -> Architect:
        return Architect(self.store, None, self.settings, clock=self.clock)


class Admission(Case):
    def test_only_births_inside_the_library_are_born_and_each_refusal_names_why(self):
        a = self.arch()
        no_class = {k: v for k, v in FLY.items() if k != "library_class"}
        born = a.admit([fly("fly-ok"), fly("fly-no-class", card=no_class),
                        fly("fly-names", roots=["AAPL"]),
                        fly("fly-wrong-type", structure="iron_condor"),
                        fly("fly-thin", card={**FLY, "sessions_per_year": 20})])
        self.assertEqual(born, ["fly-ok"])
        refused = {r["slug"]: r["why"] for r in a.card_refused}
        self.assertEqual(set(refused), {"fly-no-class", "fly-names", "fly-wrong-type", "fly-thin"})
        self.assertTrue(refused["fly-no-class"].startswith("incomplete card: library_class"))
        self.assertIn("roots: index_variance_fly trades index, etf roots, not names", refused["fly-names"])
        self.assertIn("structure: iron_condor is not one of index_variance_fly's", refused["fly-wrong-type"])
        self.assertIn("expected activity", refused["fly-thin"])
        self.assertEqual(a.library_refused, {"index_variance_fly": 3})
        stored = cards.card_of(self.store, "fly-ok")["card"]
        self.assertEqual((stored["library_class"], stored["sessions_per_year"], stored["structures_per_session"]),
                         ("index_variance_fly", 120, 1))
        born_event = [e for e in self.store.events_after(0) if e["kind"] == "swarm.born"][-1]
        self.assertEqual(born_event["payload"]["card"]["library_class"], "index_variance_fly")

    def test_the_library_needs_a_card_even_when_cards_are_optional(self):
        self.settings["architect"]["require_card"] = False
        a = self.arch()
        self.assertEqual(a.admit([fly("no-card", card=None)]), [])
        self.assertIn("library_class", a.card_refused[0]["why"])

    def test_off_the_library_reads_nothing_new(self):
        self.settings["architect"]["library"] = False
        a = self.arch()
        self.assertEqual(a.admit([fly("off-names", roots=["AAPL"])]), ["off-names"], "off: births as before")
        self.assertNotIn("library_class", cards.card_of(self.store, "off-names")["card"])
        self.assertNotIn("THE MECHANISM LIBRARY", a.card_block())

    def test_cross_root_lead_lag_is_at_most_a_quarter_of_births(self):
        a = self.arch()
        born = a.admit([lead("lead-a"), fly("fly-1"), fly("fly-2"), fly("fly-3"), lead("lead-b"), lead("lead-c")])
        self.assertEqual(born, ["fly-1", "fly-2", "fly-3", "lead-b"], "the first lead-lag would be all the window's births")
        self.assertEqual(a.library_refused, {mechanisms.LEAD_LAG: 2})
        self.assertIn("lead-lag quota is full", {r["slug"]: r["why"] for r in a.card_refused}["lead-c"])
        quota = mechanisms.LeadLagQuota(self.store, now=self.clock())
        self.assertEqual((quota.births, quota.lead_lag), (4, 1), "the window's births are read back from the cards")
        self.assertIn("no lead-lag family is born now", quota.text())
        self.clock.advance((mechanisms.LEAD_LAG_WINDOW_DAYS + 1) * 86400)
        self.assertEqual(self.arch().admit([lead("lead-d")]), [], "an empty window: one lead-lag birth alone is all of it")
        later = mechanisms.LeadLagQuota(self.store, now=self.clock())
        self.assertEqual((later.births, later.lead_lag), (0, 0), "births past the window no longer count")

    def test_the_request_and_the_system_prompt_carry_the_library(self):
        block = self.arch().card_block()
        self.assertIn("THE MECHANISM LIBRARY (every family is born from one entry", block)
        self.assertIn("LEAD-LAG QUOTA", block)
        self.assertIn('"library_class"', LIBRARY_CARD_RULE)
        self.assertNotIn("library_class", SYSTEM, "the base prompt is unchanged; the rule rides only while the library is on")

        class Router:
            claude_enabled = staticmethod(lambda role: False)

            def __init__(self):
                self.calls = []

            def ask(self, **kw):
                self.calls.append(kw)
                return {"text": '{"families": []}', "json": {"families": []}, "route": "sail", "cost_usd": 0.0}

        router = Router()
        out = Architect(self.store, router, self.settings, clock=self.clock).run()
        self.assertIn(LIBRARY_CARD_RULE, router.calls[0]["system"])
        self.assertIn("THE MECHANISM LIBRARY", router.calls[0]["user"])
        self.assertEqual(out["library_refused"], {})
        self.settings["architect"]["library"] = False
        router = Router()
        Architect(self.store, router, self.settings, clock=self.clock).run()
        self.assertNotIn(LIBRARY_CARD_RULE, router.calls[0]["system"])


if __name__ == "__main__":
    unittest.main()
