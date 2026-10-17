"""THE ONE-SESSION ASK (goal item 1, Oct 16, 2026; league/swarm/elane_births.py `SESSION_ASK`, `EquityQuota.session_ask`
and `text`): THE EQUITY QUOTA's lines say the floor is short of programs that close every session and ask, softly, for
mechanisms that hold one session (a close-to-open overnight hold of an index ETF, or another 1-session hold) in cells no
row binds and not CLOSED. RELEASE 1023a (T1): the overnight index hold reads as calendar_flow / days_1_3, a cell rows
bind for the index ETFs, so the ask says that it needs a valid card.rebirth there (by the cell's own binding as the
request reads it: league/tests/test_rel_1023a_births.py holds the bound form), and keeps "or another 1-session hold". Words only, as L2's index-only ask: a preference, not a rule; no edge claimed; the same Train
bar and route by symbols; no place reserved and no admission, quota, seat, screen or bar changed; within its size
budget (`SESSION_ASK_CHARS`). And the engine answer: a bred program can hold one session close-to-open today (a buy "at"
"close", then the lot sold "at" "open" by the next decide, or NEEDS max_hold_sessions 1), as seed-overnight-qqq does.
Every family and number here is invented."""

from __future__ import annotations

import inspect
import json
import re
import unittest
from unittest import mock

from league.equity import config as econfig
from league.equity import engine, synth
from league.equity.program import load_program
from league.equity.store import EquityStore
from league.swarm import elane_births, elane_train
from league.swarm.elane_births import (OVERNIGHT, OVERNIGHT_PLAIN, SESSION_ASK, SESSION_ASK_CHARS, EquityPass,
                                       EquityQuota, bound_cells, overnight_bound)
from league.tests import elane_e2_fakes as fx
from league.tests import test_elane_route_text as rt
from league.tests.test_equity_engine import gym_sizing

#: The ask as the quota says it with no binding read (`EquityQuota.session_ask()`: the rule in words), as a request says
#: it where no row binds the overnight cell, as it says it where rows bind it, and with no index ETF open.
INDEX_FORM = SESSION_ASK.format(overnight=OVERNIGHT["unknown"])
OPEN_FORM = SESSION_ASK.format(overnight=OVERNIGHT["open"])
BOUND_FORMS = [SESSION_ASK.format(overnight=OVERNIGHT["bound"].format(lanes=lanes))
               for lanes in ("in both lanes", "in the beta lane", "in the equity lane")]
PLAIN_FORM = SESSION_ASK.format(overnight=OVERNIGHT_PLAIN)
ALL_FORMS = [INDEX_FORM, OPEN_FORM, *BOUND_FORMS, PLAIN_FORM]


class Case(rt.Case):
    pass


class TheAskIsSaid(Case):
    def test_the_quota_lines_carry_it_after_the_index_only_ask(self):
        text = self.quota(3).text()
        self.assertIn(INDEX_FORM, text)
        self.assertTrue(text.endswith(INDEX_FORM), "the ask closes the quota lines")
        self.assertLess(text.index("A SOFT ASK, no place reserved"), text.index("ONE-SESSION HOLDS (a soft ask"))
        # L2's ask is whole before it (test_elane_route_text.py holds its words).
        self.assertIn("the other places are open to any symbol of THE UNIVERSE. ONE-SESSION HOLDS", text)
        flat = rt.flat(INDEX_FORM)
        for words in ("ONE-SESSION HOLDS (a soft ask: a preference, not a rule)",
                      "the floor is short of programs that CLOSE EVERY SESSION",
                      "In a cell no row binds and not CLOSED",
                      "prefer a 1-session hold",
                      "An overnight index hold reads as calendar_flow / days_1_3", "buy \"at\": \"close\"",
                      "sell the lot \"at\": \"open\" at the next decide", "NEEDS max_hold_sessions 1",
                      "it needs a valid card.rebirth naming one of its rows",
                      "or propose another 1-session hold", "No edge is claimed",
                      "the same Train bar, THE ROUTE BY SYMBOLS and THE RATION hold as for any program"):
            self.assertIn(words, flat, words)

    def test_the_request_carries_it_once_and_the_system_prompt_not(self):
        system, user = EquityPass(self.arch).request(EquityQuota(self.store, self.settings, now=self.clock()))
        self.assertEqual(user.count(OPEN_FORM), 1, "no row binds the overnight cell here: the ask as 1017r said it")
        self.assertEqual(user.count("ONE-SESSION HOLDS"), 1)
        self.assertNotIn("ONE-SESSION HOLDS", system)
        # The blocks it names are in the request it is said in.
        for block in ("- THE ROUTE BY SYMBOLS", "- THE RATION", "THE TRAIN BAR", "- days_1_3: one to three sessions (a "
                      "close-to-open overnight hold is one)"):
            self.assertIn(block, user, block)

    def test_every_pass_with_a_share_program_place_and_none_without(self):
        for want in range(1, 21):
            self.assertEqual(self.quota(want).session_ask(), INDEX_FORM, want)
            self.assertIn(INDEX_FORM, self.quota(want).text(), want)
        self.assertEqual(self.quota(2, panel=1).session_ask(), INDEX_FORM, "one share-program place is asked")
        self.assertEqual(self.quota(3, panel=3).session_ask(), "", "every place a panel one: no share-program ask")
        self.assertNotIn("ONE-SESSION", self.quota(3, panel=3).text())
        off = fx.settings()
        off["elane"]["mode"] = "off"
        q = EquityQuota(self.store, off, now=self.clock())
        self.assertEqual((q.session_ask(), q.text()), ("", ""))

    def test_with_no_index_etf_open_it_names_none(self):
        sectors = fx.settings(max_per_pass=4)
        sectors["elane"]["universe"] = ["XLK", "XLF", "TLT"]
        q = self.quota(3, settings=sectors)
        self.assertEqual(q.session_ask(), PLAIN_FORM)
        self.assertEqual(q.session_ask(["beta", "equity"]), PLAIN_FORM, "no index ETF open: no index cell is named")
        self.assertIn("A close-to-open overnight hold is one, or another 1-session hold.", q.text())
        self.assertNotIn("index ETF", q.session_ask())
        self.assertNotIn("SOFT ASK", q.text(), "L2's index-only ask stays off: \"A SOFT ASK\" is its name alone")


class TheSizeBudget(Case):
    def test_both_forms_inside_the_budget(self):
        for form in ALL_FORMS:
            self.assertLessEqual(len(form), SESSION_ASK_CHARS)
        self.assertLessEqual(SESSION_ASK_CHARS, 600, "a short ask: the budget is not raised to fit longer words")

    def test_the_request_grows_by_the_ask_alone(self):
        quota = EquityQuota(self.store, self.settings, now=self.clock())
        system, user = EquityPass(self.arch).request(quota)
        form = quota.session_ask(overnight_bound(bound_cells(EquityPass(self.arch).rebirth_index())))
        with mock.patch.object(EquityQuota, "session_ask", return_value=""):
            before_system, before_user = EquityPass(self.arch).request(quota)
        self.assertEqual(system, before_system)
        self.assertEqual(len(user) - len(before_user), len(form) + 1)
        self.assertEqual(user.replace(" " + form, "", 1), before_user)


class NoOutcomeWordNoNumber(Case):
    def test_no_outcome_word_no_pass_word_no_figure(self):
        for form in ALL_FORMS:
            self.assertIsNone(rt.OUTCOME.search(form), rt.OUTCOME.search(form))
            self.assertIsNone(rt.PASS_WORD.search(form), "no pass word at all")
            for claim in rt.OLD_CLAIMS:
                self.assertNotIn(claim, form)
            # The only figures are the contract's (a 1-session hold, NEEDS max_hold_sessions 1) and the holding's own
            # vocabulary word (days_1_3, T1): no count, rate or year.
            self.assertEqual(set(re.findall(r"\d+", form.replace("days_1_3", ""))), {"1"}, form)
            for word in ("edge is", "profit", "earn", "beat", "seat", "close rate", "closes a session"):
                self.assertNotIn(word, form.replace("No edge is claimed", ""), word)

    def test_what_happened_after_train_never_moves_it(self):
        # The ask reads the switch, the places and R-SEC's open index ETFs alone: never a family's record.
        base = self.quota(3).session_ask()
        fx.e2_family(self.store, "tried-one", record={"status": "passed", "passed_version": 1, "versions": {}})
        fx.e2_family(self.store, "dead-one", symbols=("QQQ",), record={"status": "refuted", "versions": {}})
        self.store.put(elane_births.LAST_KEY, {"at": "x", "short": 2,
                                               "refused": [{"slug": "x", "why": "x", "cls": "graveyard", "n": 1}]})
        self.assertEqual(self.quota(3).session_ask(), base)


class NoPlaceReserved(Case):
    def test_the_quota_and_its_event_are_unchanged(self):
        self.born_options(30)
        q = EquityQuota(self.store, self.settings, now=self.clock())
        self.assertEqual((q.want, q.index_ask(), q.session_ask()), (4, (1, 2), INDEX_FORM), "L2's quota, asked")
        for _ in range(q.want):
            self.assertTrue(q.admits("equity"))
            q.born("equity")
        self.assertFalse(q.admits("equity"))
        event = json.dumps(q.event())
        for words in ("session", "SOFT ASK", "ask"):
            self.assertNotIn(words, event, "the pass's event carries no ask, in its keys or its values")

    def test_no_admission_or_quota_code_reads_it(self):
        for fn in (EquityPass.admit, EquityPass.run, EquityQuota.__init__, EquityQuota.why_not, EquityQuota.admits,
                   EquityQuota.born, EquityQuota.short, EquityQuota.event, EquityQuota.index_ask):
            source = inspect.getsource(fn)
            self.assertNotIn("session_ask", source, fn.__qualname__)
            self.assertNotIn("SESSION_ASK", source, fn.__qualname__)

    def test_a_longer_hold_is_born_as_before(self):
        # A proposal that holds five sessions is admitted exactly as a one-session one: the ask binds nothing.
        five = fx.PROGRAM.replace('"max_hold_sessions": 2', '"max_hold_sessions": 5')
        self.born_options(9)
        self.answers.append(fx.answer([fx.proposal("hold-five", code=five),
                                       fx.proposal("overnight-one", symbols=("QQQ",), code=ONE_SESSION)]))
        out = self.pass_()
        self.assertEqual(len(out["born"]), 2, out)


#: A bred-style one-session program (the shape the ask names): every decide sells each lot at the next open and buys at
#: the next close, so a lot is held from a close to the next open. `MAX_HOLD` 1 is the House's own exit at that open.
ONE_SESSION = '''import math

NEEDS = {"symbols": ["QQQ"], "history": 2, "max_hold_sessions": 1}
PARAMS = {"share": 0.5}


def decide(ctx):
    out = [{"sell": lot["id"], "at": "open", "tag": "overnight-exit"} for lot in ctx.positions]
    close = ctx.bars["QQQ"].close
    if len(close) >= 2 and math.isfinite(float(close[-1] / close[-2])):
        out.append({"buy": "QQQ", "share": float(ctx.params["share"]), "at": "close", "tag": "overnight-entry"})
    return out
'''
#: The same with no sell: NEEDS max_hold_sessions 1 alone exits each close-bought lot at the next open.
HOUSE_EXIT = ONE_SESSION.replace(
    '    out = [{"sell": lot["id"], "at": "open", "tag": "overnight-exit"} for lot in ctx.positions]\n',
    '    out = []\n')


class TheEngineHoldsOneSession(unittest.TestCase):
    """The engine answer: a bred program can hold one session close-to-open today, under the contract every program
    has (league/equity/EQUITY.md), the static checks a v1 passes (`elane_train.check_code`) and the Gym engine
    (`league.equity.engine.run`). A same-session hold is not possible (`MIN_HOLD_SESSIONS`)."""

    SESSIONS = 14

    def setUp(self):
        import tempfile
        from pathlib import Path

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = synth.constant_store(Path(tmp.name) / "c", symbol="QQQ", sessions=self.SESSIONS, price=50.0, step=0.5)
        self.bars = EquityStore(root).bars(["QQQ"], "validation", history=0)
        patcher = gym_sizing()
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_contracts_rules(self):
        self.assertEqual(econfig.MIN_HOLD_SESSIONS, 1, "a lot never sells in the session it was bought")
        self.assertTrue(econfig.may_sell(5, 6), "a close-bought lot may sell at the next open")
        self.assertFalse(econfig.may_sell(5, 5))
        self.assertTrue(econfig.max_hold_due(0, 1), "max_hold_sessions 1: the lot exits at the next open")
        self.assertIn("A lot bought at a close with a maximum of 1 is sold at the next open.",
                      " ".join(elane_train.contract_text().split()))

    def test_a_bred_program_passes_the_static_checks(self):
        for code in (ONE_SESSION, HOUSE_EXIT):
            self.assertIsNone(elane_train.check_code(code, ["QQQ"]))

    def run_program(self, code: str) -> list[dict]:
        result = engine.run(load_program(code, name="one-session"), self.bars)
        return [t for t in result["trades"] if t["exit_at"] is not None]

    def test_it_closes_every_session_close_to_open(self):
        for code, reason in ((ONE_SESSION, "program"), (HOUSE_EXIT, "max_hold")):
            trades = self.run_program(code)
            self.assertGreaterEqual(len(trades), self.SESSIONS - 3, (reason, len(trades)))
            for trade in trades:
                self.assertEqual((trade["entry_at"], trade["exit_at"], trade["held_sessions"], trade["reason"]),
                                 ("close", "open", 1, reason))
            exits = [t["exit_day"] for t in trades]
            self.assertEqual(len(exits), len(set(exits)), "one close a session")


if __name__ == "__main__":
    unittest.main()
