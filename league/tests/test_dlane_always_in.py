"""THE ALWAYS-IN CARD (Oct 10, 2026; league/swarm/cards.py `RebirthIndex.check`, league/swarm/dlane.py `always_in`,
`always_in_entries`, `always_in_try`, `always_in_failed`, league/swarm/architect.py `admit`, `closed`, `card_block`,
league/swarm/tournament.py; A REPORTED LOOSENING). A direction card whose DECLARED inputs are exactly ["clock"] is
always-in: bound only by the always-in direction rows on its roots (any class or holding), joined at birth to every
always-in lineage on its roots (one Validation try a root), and checked on Train (G1: it enters on 90% of the sessions
it is flat, or it is never validated and retires). Alpha cards, legacy rows, gated direction cards and the lane off are
judged as on main.

Every family, mechanism, date and figure here is invented.
"""

from __future__ import annotations

import datetime as dt
import unittest

from league.ops import dlane_report as R
from league.swarm import cards, dlane
from league.swarm.architect import ALWAYS_IN_SPENT, LANE_CELLS_NOTE, SYSTEM, Architect, system_text, tag_of
from league.swarm.tournament import Tournament
from league.tests.test_dlane import always_in as train_years
from league.tests import test_dlane_d1b as d1b
from league.tests.swarm_fakes import result
from league.tests.test_dlane_births import ALWAYS, DIR, DRIFT, GATE, OFF, LaneCase
from league.tests.test_swarm_cards import CARD, GOOD, Case, proposal
from league.tests.test_swarm_rounds import RoundCase

REFUTED = "Refuted: it loses after costs on every root tested."
LANE = {"dlane": GATE}
#: The dead always-in program's words name the price ("returns"): the word reading would call it gated.
WORDY = {**ALWAYS, "hypothesis": "The equity premium: index returns are positive on average, so a call bought every "
                                 "session at the same minute rents that drift for the holder."}
#: The same always-in idea reworded, in another class and holding.
REWORDED = {**ALWAYS, "mechanism_class": "trend_momentum", "holding": "days_1_3",
            "hypothesis": "The index drifts up over years; a call bought each session at the same minute keeps renting "
                          "that drift while holders are paid to bear market risk."}
#: A gated direction card that reads the clock too (its gate: implied vol).
GATED = {**DIR, "inputs": ["clock", "implied_vol"]}
AMECH = "Rent the index's drift with a cheap call bought every session at the same minute and held a week."
#: Train sessions: the weekdays of 2022-24.
SESSIONS = [d.isoformat() for d in (dt.date(2022, 1, 3) + dt.timedelta(days=k) for k in range(1100))
            if d.weekday() < 5 and d.year <= 2024]


def held(entries, hold: int, root: str = "SPY") -> list[dict]:
    """One trade a session index of `entries`, exited `hold` sessions later."""
    return [{"day": SESSIONS[i], "exit_day": SESSIONS[min(i + hold, len(SESSIONS) - 1)], "root": root, "max_loss": 70.0,
             "fees": 2.6, "qty": 1, "pnl": 1.0} for i in entries]


def one_at_a_time(hold: int = 2, gate=lambda i: True, root: str = "SPY") -> list[dict]:
    """A program holding one position on `root` at a time: it enters on the first flat session `gate` allows."""
    out, i = [], 0
    while i < len(SESSIONS):
        if gate(i):
            out.append(i)
            i += hold + 1
        else:
            i += 1
    return held(out, hold, root)


def train(trades: list[dict]) -> dict:
    """An invented Train result (every year in the market) with these trades and the sessions as its daily series."""
    out = train_years()
    out["trades"], out["daily"] = trades, [[s, 0.0, 1000.0] for s in SESSIONS]
    return out


GATED_RUN = one_at_a_time(gate=lambda i: (i // 20) % 2 == 0)


# ------------------------------------------------------------------------------------------------ B. the card's status
class Status(unittest.TestCase):
    def test_the_status_is_the_declared_inputs_never_the_words(self):
        self.assertTrue(dlane.always_in(ALWAYS))
        self.assertTrue(dlane.always_in({**ALWAYS, "inputs": "Clock"}), "a list written as text reads the same")
        self.assertTrue(dlane.always_in({**ALWAYS, "hypothesis": "Calls are cheap when implied vol is low: buy one."}),
                        "its words never change its status (G1 checks the program)")
        self.assertFalse(dlane.always_in({**ALWAYS, "inputs": ["clock", "implied_vol"]}))
        self.assertFalse(dlane.always_in({k: v for k, v in ALWAYS.items() if k != "lane"}), "an alpha card never is")
        card, errors = cards.validate(ALWAYS, "long_single", roots=["SPY"], settings=LANE)
        self.assertEqual(errors, [])
        self.assertTrue(dlane.always_in(card))
        self.assertEqual(cards.match_inputs(WORDY, AMECH), ["clock", "underlying_price"],
                         "the word reading would have called the wordy one gated")

    def test_an_always_in_card_says_that_it_enters_every_session(self):
        quiet = {**ALWAYS, "comparison": "the same call bought at the same minute with the regime gate switched off",
                 "falsification": "its pooled daily t on Train is below 1 or it loses money at 1.5x the half-spread"}
        card, errors = cards.validate(quiet, "long_single", roots=["SPY"], settings=LANE)
        self.assertIsNone(card)
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(errors[0].startswith("inputs: [\"clock\"] alone declares an ALWAYS-IN card"), errors)
        self.assertEqual(dlane.card_errors(quiet, "long_single", ["SPY"], LANE), errors, "the lane's box says it")
        for field, text in (("falsification", "it fails when its call bought each session loses money on Train"),
                            ("comparison", "itself: an always-in program has no gate to switch off")):
            card, problems = cards.validate({**quiet, field: text}, "long_single", roots=["SPY"], settings=LANE)
            self.assertEqual(problems, [], field)
        gated = {**quiet, "inputs": ["clock", "implied_vol"]}
        self.assertEqual(dlane.card_errors(gated, "long_single", ["SPY"], LANE), [], "a gated card says nothing of it")


# ------------------------------------------------------------------------------------------------ A, B. the graveyard
class GraveyardCase(Case):
    def setUp(self):
        super().setUp()
        self.settings["dlane"] = dict(GATE)

    def dead(self, fid, raw, *, reason=REFUTED, roots=("SPY",), mechanism=AMECH, own=True, alpha=False,
             structure="long_single"):
        """A dead family a minute after the last, carded with `raw` (validated in the lane unless `alpha`); with `own`
        False a fork's card: its spec's card_sha only."""
        self.clock.t += 60
        card = (cards.validate(raw, structure)[0] if alpha
                else cards.validate(raw, structure, roots=list(roots), settings=LANE)[0])
        self.assertIsNotNone(card, raw)
        spec = {"id": fid, "mechanism": mechanism, "structure": structure, "roots": list(roots), "dte": [4, 10],
                "card_sha": cards.card_sha(card)}
        if not alpha:
            spec["lane"] = "direction"
        if not own:
            source = f"{fid}-parent"
            self.store.add_family({**spec, "id": source}, origin="architect")
            cards.put(self.store, source, card, structure)
        fam = self.store.add_family(spec, origin="architect")
        if own:
            cards.put(self.store, fam["id"], card, structure)
        self.assertEqual(self.store.retire_gym(fam["id"], reason, floor=0, source="test")["status"], "retired")
        return fam["id"]

    def index(self, settings=None) -> cards.RebirthIndex:
        return cards.RebirthIndex(self.store, self.settings if settings is None else settings)

    def card(self, raw, roots=("SPY",)):
        return cards.validate(raw, "long_single", roots=list(roots), settings=LANE)[0]


class Graveyard(GraveyardCase):
    def test_alpha_cards_and_legacy_rows_are_judged_as_on_main(self):
        """The first cut's blocker: an alpha clock-only card stays bound by legacy rows and overlapping carded rows."""
        self.bury("monday-call-legacy", None, reason=REFUTED, structure="long_call",
                  mechanism="Mondays rebalance flows: buy one call on Mondays at 10:30, held to the next session.")
        calendar = {**CARD, "mechanism_class": "calendar_flow", "inputs": ["clock", "event_calendar"],
                    "hypothesis": "Benchmark funds rebalance mechanically on Mondays and patient call buyers are "
                                  "paid for taking the other side into the next session."}
        self.dead("monday-call-carded", calendar, alpha=True,
                  mechanism="Mondays rebalance flows lift the index into the next session: buy a call.")
        clocked = cards.validate({**calendar, "inputs": ["clock"]}, "long_single")[0]
        text = "Buy one SPY call on Mondays at 10:30 and hold it to the next session."
        on = self.index().check(clocked, "long_single", text, [1, 3], roots=["SPY"])
        off = self.index({**self.settings, "dlane": OFF}).check(clocked, "long_single", text, [1, 3], roots=["SPY"])
        self.assertFalse(on["ok"])
        self.assertEqual(on, off, "the lane on or off, an alpha card's verdict is main's")
        self.assertEqual(on["count"], 2, "the legacy row and the overlapping carded row both bind it")
        self.assertNotIn("always_in", on)
        # `cards.matches` itself is main's: every caller (the mechanism test's lineage, the yields, the memory judge).
        key = {"class": "equity_premium", "family": "directional", "holding": "days_4_10"}
        self.assertTrue(cards.matches({**key, "inputs": ["clock"]}, {**key, "inputs": ["clock", "implied_vol"]}))
        self.assertTrue(cards.matches({**key, "inputs": ["clock"]}, {**key, "inputs": None}))

    def test_a_gated_direction_card_is_bound_as_before_and_an_always_in_card_is_not(self):
        gated_row = self.dead("gated-ivgate-dead", GATED, mechanism="Buy the call each session only while implied "
                              "vol sits calm against its own trailing year, held a week.")
        self.dead("gated-trend-dead", {**DIR, "inputs": ["clock", "underlying_price"]},
                  mechanism="Buy the call each session only while the index sits above its own 50-day average, held "
                            "a week.")
        index = self.index()
        verdict = index.check(self.card(GATED), "long_single", "A calm-vol call held a week.", [4, 10], roots=["SPY"])
        self.assertFalse(verdict["ok"])
        self.assertIn(verdict["row"], ("gated-ivgate-dead", "gated-trend-dead"))
        always = index.check(self.card(ALWAYS), "long_single", AMECH, [4, 10], roots=["SPY"])
        self.assertEqual((always["ok"], always["always_in"], always["gated_rows"], always["matched"]),
                         (True, True, 2, []))
        # The lane off: the rollback reads it as main did (the gated rows bind it).
        off = self.index({**self.settings, "dlane": OFF}).check(self.card(ALWAYS), "long_single", AMECH, [4, 10],
                                                                 roots=["SPY"])
        self.assertFalse(off["ok"])
        self.assertNotIn("always_in", off)
        self.assertFalse(self.index().by_id[gated_row]["always_in"])

    def test_an_always_in_row_binds_by_its_declared_inputs_on_its_roots_whatever_its_words_class_or_holding(self):
        """The first cut's finding: a dead always-in row read from its words escaped a reworded repeat."""
        row = self.dead("ai-wordy-dead", WORDY, roots=("SPY",))
        index = self.index()
        self.assertTrue(index.by_id[row]["always_in"])
        self.assertEqual(index.by_id[row]["inputs"], ["clock", "underlying_price"], "its words read a price")
        again = self.card(REWORDED)
        text = "Buy a call each session at the same minute and hold it to the next session."
        verdict = index.check(again, "long_single", text, [1, 3], roots=["SPY"])
        self.assertFalse(verdict["ok"])
        self.assertEqual((verdict["row"], verdict["tag"], verdict["always_in"]), (row, "REFUTED", True))
        self.assertIn("bound by the always-in direction rows on its roots, whatever their class or holding: 1 on SPY",
                      verdict["reason"])
        self.assertIn("no rebirth claim can free it", verdict["reason"])
        self.assertFalse(index.check({**again, "rebirth": {"row": row, **GOOD}}, "long_single", text, [1, 3],
                                     roots=["SPY"])["ok"], "no claim frees it")
        self.assertTrue(index.check(again, "long_single", text, [1, 3], roots=["QQQ"])["ok"], "another root is open")
        self.assertFalse(index.check(again, "long_single", text, [1, 3], roots=["QQQ", "SPY"])["ok"])
        self.assertFalse(index.check(again, "long_single", text, [1, 3])["ok"], "no roots given: every root's rows")
        # A gated card in the dead row's own cell is bound by it as before (its clock overlaps); a claim is open to it.
        gated = index.check(self.card(GATED), "long_single", "A calm-vol call held a week.", [4, 10], roots=["SPY"])
        self.assertEqual((gated["ok"], gated["row"]), (False, row))

    def test_a_fork_reads_its_parents_card_and_an_alpha_clock_card_is_no_always_in_row(self):
        fork = self.dead("ai-fork-dead", ALWAYS, own=False, roots=("IWM",))
        alpha = self.dead("alpha-clock-dead", {**CARD, "mechanism_class": "calendar_flow", "inputs": ["clock"]},
                          alpha=True, roots=("IWM",), mechanism="Turn of the month flows lift the index: buy a call.")
        index = self.index()
        self.assertTrue(index.by_id[fork]["always_in"], "a fork's row reads the card its spec's card_sha names")
        self.assertEqual((index.by_id[alpha]["lane"], index.by_id[alpha]["always_in"]), ("alpha", False))
        self.assertEqual([r["row"] for r in index.always_in_bound(["IWM"])], [fork])

    def test_a_family_whose_program_failed_g1_lost_the_status_however_it_died(self):
        """Its researcher retired it (SELF-REFUTED, a binding verdict) before the tournament's G1 retirement: its program
        was gated, so its row binds no always-in card (it still binds gated ones by the cell's rule)."""
        from league.swarm.researcher import SELF_REFUTED

        self.clock.t += 60
        card = self.card(ALWAYS)
        self.store.add_family({"id": "ai-gated-in-fact", "mechanism": AMECH, "structure": "long_single",
                               "roots": ["SPY"], "dte": [4, 10], "lane": "direction", "card_sha": cards.card_sha(card)},
                              origin="architect")
        cards.put(self.store, "ai-gated-in-fact", card, "long_single")
        score = dlane.train_score(train(GATED_RUN), settings=LANE, always_in=True)
        dlane.record(self.store, "ai-gated-in-fact", 1, score=score)
        self.store.retire_gym("ai-gated-in-fact", f"{SELF_REFUTED}: the calm-vol gate did not pay.", floor=0,
                              source="test")
        index = self.index()
        self.assertEqual(index.by_id["ai-gated-in-fact"]["tag"], "SELF-REFUTED")
        self.assertFalse(index.by_id["ai-gated-in-fact"]["always_in"])
        self.assertTrue(index.check(self.card(REWORDED), "long_single", AMECH, [1, 3], roots=["SPY"])["ok"])

    def test_a_drift_always_in_row_binds_none_and_a_claim_an_always_in_card_carries_is_dropped(self):
        row = self.dead("ai-drift-dead", ALWAYS, reason=DRIFT)
        index = self.index()
        self.assertEqual(index.always_in_rows(["SPY"])[0]["row"], row)
        self.assertEqual(index.always_in_bound(["SPY"]), [], "a DRIFT row binds no direction card")
        self.dead("gated-dead", GATED, mechanism="Buy the call each session only while implied vol sits calm.")
        claim = {**self.card(ALWAYS), "rebirth": {"row": "gated-dead", **GOOD}}
        verdict = self.index().check(claim, "long_single", AMECH, [4, 10], roots=["SPY"])
        self.assertTrue(verdict["ok"])
        self.assertIn("its claim is not needed and is not kept", verdict["dropped"])
        self.assertNotIn("rebirth", verdict)


# ------------------------------------------------------------------------------------------------ C. one idea a root
class OneIdeaARoot(LaneCase):
    def setUp(self):
        super().setUp()
        self.settings["architect"]["require_card"] = True
        self.settings["population"].update(start=12, ceiling=60)

    def always(self, slug, roots, raw=ALWAYS, mechanism=None):
        return proposal(slug, card=raw, structure="long_single", roots=list(roots), dte=[4, 10],
                        mechanism=mechanism or f"{AMECH} ({slug})")

    def links(self):
        return sorted((r["a"], r["b"]) for r in self.store._all("SELECT a,b FROM lineage_links"))

    def try_of(self, fid):
        v = self.store.add_version(fid, f"# {fid}\n" + d1b.CallsOnly.CALLS, {}, author="r")
        self.store.add_run(fid, v["n"], result(fid, window="validation"), window="validation", stress=1.0,
                           purpose="validation")

    def test_one_validation_try_a_root_for_the_always_in_idea(self):
        a = self.arch()
        born = a.admit([self.always("ai-spy", ["SPY"]),
                        self.always("ai-spy-again", ["SPY"], REWORDED, "Buy a call each session at the same minute and "
                                    "hold it to the next session, renting the index's drift."),
                        self.always("ai-qqq", ["QQQ"]),
                        proposal("gated-spy", card=GATED, structure="long_single", roots=["SPY"], dte=[4, 10],
                                 mechanism="Buy the call each session only while implied vol sits calm against its own "
                                           "trailing year, held a week.")])
        self.assertEqual(born, ["ai-spy", "ai-qqq", "gated-spy"])
        refused = {r["slug"]: r for r in a.card_refused}
        self.assertEqual(refused["ai-spy-again"]["spent"], "claim", "born in the same pass: it claims the root's try")
        self.assertTrue(refused["ai-spy-again"]["why"].endswith(ALWAYS_IN_SPENT))
        self.assertEqual(self.links(), [], "a root's first always-in family starts its lineage; a gated one joins none")
        payload = {e["family"]: e["payload"] for e in self.born()}
        first = payload["ai-spy"]["card"]
        self.assertEqual((first["always_in"], first["always_in_lines"]), (True, []))
        self.assertNotIn("always_in", payload["gated-spy"]["card"])
        # The SPY always-in try is spent: a later always-in card on SPY (any class, holding or words; a second root too)
        # is refused before birth, though no graveyard row binds it (ai-spy lives).
        self.try_of("ai-spy")
        b = self.arch()
        self.assertEqual(b.admit([self.always("ai-spy-iwm", ["SPY", "IWM"]),
                                  self.always("ai-spy-short", ["SPY"], REWORDED, "Hold a call bought each session at "
                                              "the same minute to the next session.")]), [])
        self.assertEqual([item["slug"] for item in b.card_refused], ["ai-spy-iwm", "ai-spy-short"])
        for item in b.card_refused:
            self.assertEqual(item["spent"], "try")
            self.assertIn("whose one Validation try is spent (ai-spy v1)", item["why"])
        self.assertEqual(b.admit([self.always("ai-iwm", ["IWM"])]), ["ai-iwm"])
        # A family on two roots joins both roots' always-in lineages, so their tries count together from now on.
        c = self.arch()
        self.assertEqual(c.admit([self.always("ai-qqq-iwm", ["QQQ", "IWM"])]), ["ai-qqq-iwm"])
        self.assertEqual(self.links(), [("ai-iwm", "ai-qqq-iwm"), ("ai-qqq", "ai-qqq-iwm")])
        payload = {e["family"]: e["payload"] for e in self.born()}
        self.assertEqual(sorted(payload["ai-qqq-iwm"]["card"]["always_in_lines"]), ["ai-iwm", "ai-qqq"])
        self.try_of("ai-qqq")
        self.assertEqual(dlane.lineage_spent(self.store, self.store.family("ai-iwm"), self.settings), dlane.SPENT_TRY)
        self.assertFalse(dlane.try_open(self.store, self.store.family("ai-qqq-iwm"), 1, self.settings))
        self.assertEqual(self.arch().admit([self.always("ai-iwm-2", ["IWM"])]), [], "IWM's try went with QQQ's")

    def test_the_lane_off_links_nothing(self):
        self.settings["dlane"] = dict(OFF)
        self.assertEqual(cards.always_in_families(self.store, ["SPY"]), [])
        self.assertEqual(self.arch().always_in_ration(), {})


# ------------------------------------------------------------------------------------------------ D. G1
class Behaviour(unittest.TestCase):
    def test_the_reading_holds_for_any_hold_and_catches_any_gate(self):
        for hold in (2, 5, 8):
            got = dlane.always_in_entries(train(one_at_a_time(hold)))
            self.assertEqual((got["known"], got["passed"], got["share"], got["flat"] == got["entered"]),
                             (True, True, 1.0, True), hold)
        every = dlane.always_in_entries(train(held(range(len(SESSIONS)), 3)))
        self.assertEqual((every["known"], every["passed"], every["share"], every["flat"]), (True, True, None, 1),
                         "a new call every session: never flat after the first, in the market every session")
        gated = dlane.always_in_entries(train(GATED_RUN))
        self.assertEqual((gated["known"], gated["passed"]), (True, False))
        self.assertLess(gated["share"], 0.5)
        mondays = one_at_a_time(gate=lambda i: dt.date.fromisoformat(SESSIONS[i]).weekday() == 0)
        monday = dlane.always_in_entries(train(mondays))
        self.assertEqual(monday["passed"], False, "a weekday is a gate too (a clock-only calendar card)")
        spy_qqq = dlane.always_in_entries(train(one_at_a_time() + held([10, 400], 2, "QQQ")))
        self.assertFalse(spy_qqq["passed"], "a root it trades only now and then is gated there")
        rare = dlane.always_in_entries(train([{**t, "exit_day": None} for t in held([0], 2)]))
        self.assertEqual((rare["flat"], rare["passed"]), (1, True), "a position never closed: never flat again")
        self.assertFalse(dlane.always_in_entries(train([{k: v for k, v in t.items() if k != "exit_day"}
                                                        for t in one_at_a_time()]))["known"], "no exit day: unread")
        self.assertFalse(dlane.always_in_entries({**train(one_at_a_time()), "daily": None})["known"])
        self.assertFalse(dlane.always_in_entries(train([]))["known"], "no Train trade")
        older = [{**t, "day": "2021" + t["day"][4:], "exit_day": "2021" + t["exit_day"][4:]} for t in GATED_RUN]
        self.assertEqual(dlane.always_in_entries(train(one_at_a_time() + older))["passed"], True,
                         "a year before Train is never read")

    def test_g1_is_a_bar_of_an_always_in_familys_score_only(self):
        base = dlane.train_score(train(GATED_RUN), settings=LANE)
        self.assertTrue(base["eligible"], base["why"])
        self.assertNotIn("always_in", base)
        self.assertNotIn("always_in", dlane.compact(base), "a gated family's score is the release before's")
        score = dlane.train_score(train(GATED_RUN), settings=LANE, always_in=True)
        self.assertEqual((score["eligible"], score["fails"]), (False, ["G1"]))
        self.assertTrue(score["why"].startswith("fails G1: its card is always-in (inputs: the clock alone), and its "
                                                "program entered on"), score["why"])
        kept = dlane.compact(score)
        self.assertEqual(kept["always_in"]["passed"], False)
        again = dlane._score_from_compact(kept, None, LANE)
        self.assertEqual((again["eligible"], again["fails"]), (False, ["G1"]), "a pruned run keeps its G1 failure")
        good = dlane.train_score(train(one_at_a_time()), settings=LANE, always_in=True)
        self.assertEqual((good["eligible"], good["always_in"]["passed"]), (True, True))

    def test_its_words_are_counts_that_never_read_as_a_year(self):
        text = dlane.always_in_why({"flat": 2025, "entered": 2020})
        self.assertIn("2,020 of the 2,025 Train sessions", text)
        self.assertNotIn("2025", text.replace(",", "|"))


class AtTheTry(RoundCase):
    """G1 at the tournament: a failing version is never validated (no try spent) and its family retires (IDLE)."""

    def setUp(self):
        super().setUp()
        self.settings["dlane"] = dict(GATE)
        self.settings["researcher"]["extension_hold_checks"] = 0
        self.settings["population"]["floor"] = 0

    def put(self, fid, roots=("SPY",), raw=ALWAYS, trades=None, record=True):
        card = cards.validate(raw, "long_single", roots=list(roots), settings=self.settings)[0]
        self.store.add_family({"id": fid, "mechanism": f"{AMECH} ({fid})", "structure": "long_single",
                               "roots": list(roots), "lane": "direction", "card_sha": cards.card_sha(card)},
                              origin="architect")
        cards.put(self.store, fid, card, "long_single")
        v = self.store.add_version(fid, f"# {fid}\n" + d1b.CallsOnly.CALLS, {}, author="r")
        self.store.update_family(fid, best_version=v["n"])
        if trades is not None and record:
            dlane.record(self.store, fid, v["n"], score=dlane.train_score(train(trades), settings=self.settings,
                                                                         always_in=dlane.always_in(card)))
        elif trades is not None:
            self.store.add_run(fid, v["n"], {**train(trades), "run_id": f"train-{fid}", "trials": 1}, window="train",
                               stress=1.0, purpose="train")
        return fid

    def test_a_g1_failure_is_never_validated_spends_no_try_and_retires_as_an_idle_death(self):
        self.put("ai-bad", trades=GATED_RUN)
        self.put("ai-good", roots=("QQQ",), trades=one_at_a_time())
        self.put("ai-unread", roots=("IWM",))
        self.put("gated-dir", raw=GATED, trades=GATED_RUN)
        t = Tournament(self.store, self.pool, self.settings)
        out = t.validate(self.store.families(alive=True))
        self.assertEqual(out["always_in_refused"], ["ai-bad", "ai-unread"])
        self.assertEqual(sorted(j.family for j in self.pool.jobs), ["ai-good", "gated-dir"],
                         "a G1 pass and a gated family are validated as before")
        self.assertEqual(dlane.lineage_tries(self.store, "ai-bad"), [], "no try spent")
        gone = t.retirements([self.store.family(f) for f in ("ai-bad", "ai-unread")])
        self.assertEqual(gone, [{"family": "ai-bad", "why": dlane.ALWAYS_IN_CAUSE}], "an unread one waits")
        fam = self.store.family("ai-bad")
        row = self.store._one("SELECT * FROM graveyard WHERE family=?", ("ai-bad",))
        self.assertEqual(tag_of(row, fam), "IDLE", "an untested death: no row of it binds a card")
        self.assertNotIn("ai-bad", cards.RebirthIndex(self.store, self.settings).by_id)
        from league.swarm import public

        self.assertEqual(public.note_text(dlane.ALWAYS_IN_CAUSE), "Retired because its program did not enter on the "
                         "clock alone as its always-in card declared.", "its first sentence is the public one")
        # The rollback reads none of it.
        self.settings["dlane"] = dict(OFF)
        self.assertNotIn("always_in_refused", Tournament(self.store, self.pool, self.settings).validate(
            self.store.families(alive=True)))
        self.assertIsNone(dlane.always_in_failed(self.store, self.store.family("ai-unread"), self.settings))

    def test_with_no_score_on_record_the_try_reads_the_train_run_itself(self):
        self.put("ai-run", trades=GATED_RUN, record=False)
        fam = self.store.family("ai-run")
        self.assertEqual(dlane.always_in_try(self.store, fam, 1, self.settings), "failed")
        fam = self.store.family("ai-run")
        self.assertEqual(fam["state"][dlane.ALWAYS_IN_KEY]["version"], 1)
        self.assertEqual(dlane.always_in_failed(self.store, fam, self.settings), dlane.ALWAYS_IN_CAUSE)
        self.put("ai-run-good", roots=("QQQ",), trades=one_at_a_time(), record=False)
        self.assertIsNone(dlane.always_in_try(self.store, self.store.family("ai-run-good"), 1, self.settings))
        self.put("gated-run", roots=("IWM",), raw=GATED, trades=GATED_RUN, record=False)
        self.assertIsNone(dlane.always_in_try(self.store, self.store.family("gated-run"), 1, self.settings),
                          "a gated family is never read for it")


# ------------------------------------------------------------------------------------------------ E. the views
class Views(GraveyardCase):
    def test_the_birth_cells_end_with_each_lane_roots_always_in_state(self):
        self.settings["architect"].update(structures=["debit_vertical", "long_single"])
        self.dead("ai-qqq-dead", ALWAYS, roots=("QQQ",))
        self.clock.t += 60
        card = self.card(ALWAYS, ("IWM",))
        self.store.add_family({"id": "ai-iwm", "mechanism": AMECH, "structure": "long_single", "roots": ["IWM"],
                               "lane": "direction", "card_sha": cards.card_sha(card)}, origin="architect")
        cards.put(self.store, "ai-iwm", card, "long_single")
        v = self.store.add_version("ai-iwm", "# ai-iwm\n" + d1b.CallsOnly.CALLS, {}, author="r")
        self.store.add_run("ai-iwm", v["n"], result("ai-iwm", window="validation"), window="validation", stress=1.0,
                           purpose="validation")
        a = Architect(self.store, None, self.settings, clock=self.clock)
        block = a.card_block()
        self.assertIn(LANE_CELLS_NOTE + ":\n", block)
        self.assertIn("ALWAYS-IN direction card (declared inputs exactly [\"clock\"]) is bound by no cell's rows",
                      LANE_CELLS_NOTE)
        last = [line for line in block.split("\n\n")[1].splitlines() if line][-1]
        self.assertTrue(last.startswith(cards.ALWAYS_IN_LINE), last)
        self.assertTrue(last.endswith("By root: SPY open; QQQ bound by ai-qqq-dead (REFUTED); IWM its always-in "
                                      "lineage's one Validation try is spent (ai-iwm v1)"), last)
        self.assertEqual(a.always_in_open(cards.RebirthIndex(self.store, self.settings)), ["SPY"])
        off = Architect(self.store, None, {**self.settings, "dlane": OFF}, clock=self.clock).card_block()
        self.assertNotIn("ALWAYS-IN", off)

    def test_a_list_with_no_cell_stays_empty(self):
        self.assertEqual(self.index().cells(), [], "no graveyard row: no list, so the golden prompts hold")

    def test_the_system_prompt_says_it_while_the_lane_is_on(self):
        text = system_text(LANE)
        self.assertIn("A DIRECTION card whose declared inputs are exactly [\"clock\"] is ALWAYS-IN", text)
        self.assertIs(system_text({"dlane": OFF}), SYSTEM)

    def test_the_card_brief_says_g1_to_an_always_in_family_only(self):
        always = cards.brief_text({"card": self.card(ALWAYS)}, LANE)
        self.assertIn("- ALWAYS-IN (your card's declared inputs are the clock alone", always)
        self.assertIn("Every Train run is checked (G1)", always)
        self.assertNotIn("ALWAYS-IN", cards.brief_text({"card": self.card(GATED)}, LANE))
        self.assertNotIn("ALWAYS-IN", cards.brief_text({"card": self.card(ALWAYS)}, {"dlane": OFF}))

    def test_the_report_lists_the_loosening_with_its_cost(self):
        row = {r["rule"]: r for r in R.LOOSENED}["the graveyard for an always-in direction card (Oct 10)"]
        for words in ("at most one always-in Validation try per root (SPY, QQQ, IWM)",
                      "10.37% per program at zero edge", "higher when the screen windows rose",
                      "index beta minus option costs", "same-risk buy-and-hold"):
            self.assertIn(words, row["cost"])
        self.assertIn("G1", row["now"])


class ClosedByTheRation(Case):
    """NO PAID PASS WITHOUT A CELL: a lane root whose always-in try is spent bears no always-in birth either."""

    def test_spent_always_in_tries_on_every_root_close_the_pass(self):
        self.settings["architect"].update(structures=["debit_vertical", "long_single"], max_rebirths_per_cell=0)
        for c in [*cards.MECHANISM_CLASSES, "equity_premium"]:  # every cell at rebirth room 0 (test_dlane_births)
            for h in cards.HOLDING:
                if c == "equity_premium" and h not in ("days_1_3", "days_4_10"):
                    continue
                raw = {**CARD, "mechanism_class": c, "holding": h}
                card = (cards.validate(raw)[0] if c in cards.MECHANISM_CLASSES
                        else {**cards.validate({**raw, "mechanism_class": "skew"})[0], "mechanism_class": c,
                              "lane": "direction"})
                self.bury(f"{c}-{h}".replace("_", "-")[:36], card, reason=REFUTED)
        self.settings["dlane"] = {**GATE, "classes": ["equity_premium"]}
        a = Architect(self.store, None, self.settings, clock=self.clock)
        self.assertIsNone(a.closed(), "the lane's roots are open to an always-in card")
        card = cards.validate(ALWAYS, "long_single", roots=list(dlane.ROOTS), settings=self.settings)[0]
        self.store.add_family({"id": "ai-all", "mechanism": AMECH, "structure": "long_single",
                               "roots": list(dlane.ROOTS), "lane": "direction", "card_sha": cards.card_sha(card)},
                              origin="architect")
        cards.put(self.store, "ai-all", card, "long_single")
        v = self.store.add_version("ai-all", "# ai-all\n" + d1b.CallsOnly.CALLS, {}, author="r")
        self.assertIsNone(a.closed(), "alive without a try or a claim: still open")
        self.store.add_run("ai-all", v["n"], result("ai-all", window="validation"), window="validation", stress=1.0,
                           purpose="validation")
        self.assertEqual(a.closed(), {"cells": 46, "full": 46, "spent": 0})


if __name__ == "__main__":
    unittest.main()
