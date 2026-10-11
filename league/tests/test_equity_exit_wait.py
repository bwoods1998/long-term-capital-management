"""AN EXIT'S WAIT FOR THE PRACTICE PROOF HAS AN END (the captain's A28, amending A10.1; league/equity/live.py
`_work_exit`, `_sell_proof`, `_sell_unproven`).

The stock paper proof's SELL stage gates every real equity sale (A10.1): the practice sale goes first in its window,
sent in the open window's first minute and normally witnessed in its second, and real exits wait for that pass. The
rehearsal of the first real-money session (Oct 11, 2026) found that the wait had no end: a stage that could not pass (a
practice sale that rests, FILL activities the practice account does not list, a practice position off its baseline)
held every real lot for as long as it could not, the maximum-hold exit and the owner's flatten among them, while a
failed stage also stops every new buy. From this release the wait ends at the session's entry cut-off
(`schedule.Moments.entry_until`, the open + 900 s: the minute the book stops trying open entries): from then on every
exit goes through the normal path whatever the stage says, and the owner is told once a session that the sale path is
unproven, with the stage's own reason.

WHAT MUST NOT CHANGE is held here too: inside the open window a real sale still waits for the stage; the minimum hold
and the gateway's kill switch still hold an exit; stage BUY still gates every real buy with no end; a failed SELL stage
still stops new real buys; and a week in which the proof passes is, order for order, the week it was (`TheWeeks`'s
normal week passes on the release before this one too).

The book's harness and fakes are league/tests/test_equity_book.py's; the practice account is
league/tests/test_equity_paper.py's, under the REAL `StockPaperProof`. No price here is a market's."""

import datetime as dt
import unittest
from decimal import Decimal as D

from league.equity import live as L
from league.equity import schedule as S
from league.tests.test_equity_book import (FRIDAY, MONDAY, TUESDAY, WEDNESDAY, BookTest, at, equity_table, family_row)

try:
    import numpy  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

THURSDAY = dt.date(2026, 10, 15)
WAITS = "SELL stage"
TOLD = "the sale path is unproven"
FAILED = "the stock paper proof's SELL stage failed on 2026-10-09: the round trip ended without activity_witness"
#: The proof's own alarm of a failed SELL stage (league/live/paper.py `_fail_sell`, inside the options fingerprint: its
#: words are from before A28 and are not this release's to change).
OWN_ALARM = "Real equity lots stay held and new real equity buys stop until it passes"


def told(h) -> list[str]:
    return [text for level, text in h.alerts if level == "error" and TOLD in text]


def sent(h) -> list[tuple[str, str]]:
    return [(b["side"], b["symbol"]) for b in h.venue.sent]


class TheWaitHasAnEnd(BookTest):
    def held(self, h, symbol="SPY", family="seed-overnight-spy", **kw):
        inst = h.instance(family)
        return inst, h.lot(inst, symbol, "0.5", "590", **kw)

    def test_a_real_sale_waits_through_the_open_window_then_goes(self):
        h = self.harness()
        inst, lot = self.held(h)
        sale = h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
        h.proof.sell = False
        for mm in range(31, 45):
            h.tick(9, mm)
        self.assertEqual(h.venue.sent, [], "the practice sale has the open window's fifteen minutes to go first")
        self.assertIn(WAITS, h.get_intent(sale.iid).why)
        self.assertEqual(h.book._lot(lot.lid).status, "open")
        self.assertEqual(h.alerts, [], "nothing is said while the stage may still pass first")
        self.assertIsNone(h.state.get("eq_sell_unproven"))
        h.tick(9, 45)
        self.assertEqual([(b["side"], b["symbol"], b["type"]) for b in h.venue.sent], [("sell", "SPY", "limit")])
        h.tick(9, 46)
        closed = h.book._lot(lot.lid)
        self.assertEqual((closed.status, closed.exit_at, closed.exit_day, closed.reason),
                         ("closed", "open", MONDAY.isoformat(), "program"))
        self.assertEqual(h.get_intent(sale.iid).status, "done")
        [(level, text)] = h.alerts
        self.assertEqual(level, "error")
        self.assertIn(TOLD, text)
        self.assertIn("Owner step", text)
        self.assertEqual(h.state.get("eq_sell_unproven")["day"], MONDAY.isoformat())
        self.assertEqual(sum(1 for kind, payload in h.events if kind == "equity.alert" and TOLD in payload["what"]), 1)

    def test_a_stage_that_passes_inside_the_window_releases_the_sale_at_once_and_nothing_is_said(self):
        h = self.harness()
        inst, lot = self.held(h)
        h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
        h.proof.sell = False
        h.tick(9, 31)
        self.assertEqual(h.venue.sent, [])
        h.proof.sell = True                                     # the practice sale witnessed in the second minute
        h.tick(9, 32)
        self.assertEqual(sent(h), [("sell", "SPY")])
        for mm in range(33, 47):
            h.tick(9, mm)
        self.assertEqual(h.alerts, [])
        self.assertIsNone(h.state.get("eq_sell_unproven"))

    def test_the_wait_ends_the_minute_the_book_stops_trying_entries(self):
        """ONE INSTANT, the money table's own offset (never a literal 09:45): the tick that records an open entry
        missed at its cut-off is the tick that lets the exits go."""
        offsets = {**S.DEFAULTS, "entry_until_after_open_s": 600}
        h = self.harness(table=equity_table(offsets=offsets))
        inst, lot = self.held(h)
        other = h.instance("fam-b")
        sale = h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
        buy = h.intent(other, "buy", symbol="QQQ", share="0.2")
        h.proof.ok = h.proof.sell = False                       # neither stage has passed: both intents wait
        for mm in range(31, 40):
            h.tick(9, mm)
        self.assertEqual(h.venue.sent, [])
        self.assertEqual((h.get_intent(buy.iid).status, h.get_intent(sale.iid).status), ("planned", "planned"))
        self.assertIn("BUY stage", h.get_intent(buy.iid).why)
        h.tick(9, 40)                                           # 09:40:03 >= the open + 600 s
        self.assertEqual(sent(h), [("sell", "SPY")])
        missed = h.get_intent(buy.iid)
        self.assertEqual(missed.status, "missed")
        self.assertIn("the entry cut-off passed", missed.why)
        self.assertIn("BUY stage", missed.why, "stage BUY gated the buy to its end: no real buy went unproven")
        self.assertEqual(len(told(h)), 1)

    def test_the_owner_is_told_once_a_session_however_many_exits_go(self):
        h = self.harness()
        a, spy = self.held(h, "SPY", "fam-a")
        b, qqq = self.held(h, "QQQ", "fam-b")
        c, iwm = self.held(h, "IWM", "fam-c")
        h.intent(a, "sell", symbol="SPY", lid=spy.lid)
        h.intent(b, "sell", symbol="QQQ", lid=qqq.lid)
        h.intent(c, "sell", symbol="IWM", lid=iwm.lid, exec_day=TUESDAY, decided=MONDAY)
        h.proof.sell = False
        h.tick(9, 44)
        self.assertEqual(h.venue.sent, [])
        h.tick(9, 45)
        self.assertEqual(sorted(b["symbol"] for b in h.venue.sent), ["QQQ", "SPY"])
        self.assertEqual(len(told(h)), 1)
        for mm in (46, 47, 48):
            h.tick(9, mm)
        self.assertEqual(len(told(h)), 1)
        h.tick(9, 44, day=TUESDAY)
        self.assertEqual(len(h.venue.sent), 2, "the next session waits through its own open window again")
        h.tick(9, 45, day=TUESDAY)
        self.assertEqual(sorted(b["symbol"] for b in h.venue.sent), ["IWM", "QQQ", "SPY"])
        self.assertEqual(len(told(h)), 2, "once a session")
        self.assertEqual(h.state.get("eq_sell_unproven")["day"], TUESDAY.isoformat())

    def test_the_alert_names_the_stages_own_reason(self):
        h = self.harness()
        inst, lot = self.held(h)
        h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
        h.proof.sell = False
        h.proof.failed = FAILED
        h.tick(9, 45)
        [text] = told(h)
        self.assertIn(FAILED, text, "a failed stage: its own failure, as the proof recorded it")
        self.assertEqual(h.state.get("eq_sell_unproven")["why"], FAILED)

    def test_a_stage_not_failed_says_where_its_attempt_stands(self):
        h = self.harness()
        inst, lot = self.held(h)
        h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
        h.proof.sell = False
        h.proof.status = lambda: {"status": "sold", "why": "sold; waiting for activity_witness", "stages": {}}
        h.tick(9, 45)
        [text] = told(h)
        self.assertIn("not passed yet; its attempt stands at sold: sold; waiting for activity_witness", text)

    def test_every_exit_kind_goes(self):
        """A program's sale, the House's maximum hold, a retired and a demoted program's lots, a carried exit: one
        path (`_work_exit`), one wait, one end."""
        h = self.harness()
        kinds = [("SPY", "fam-a", None), ("QQQ", "fam-b", "max_hold"), ("IWM", "fam-c", "retired"),
                 ("DIA", "fam-d", "demoted"), ("AAPL", "fam-e", "carried")]
        lots = {}
        for symbol, family, reason in kinds:
            inst, lot = self.held(h, symbol, family)
            lots[symbol] = lot
            if reason is None:
                h.intent(inst, "sell", symbol=symbol, lid=lot.lid)
            else:
                h.book._plan_exit(lot, exec_day=MONDAY.isoformat(), at="open", reason=reason, why=f"the House: {reason}",
                                  decided_day=FRIDAY.isoformat())
        h.proof.sell = False
        h.tick(9, 44)
        self.assertEqual(h.venue.sent, [])
        h.tick(9, 45)
        self.assertEqual(sorted(sent(h)), sorted(("sell", symbol) for symbol, _, _ in kinds))
        h.tick(9, 46)
        self.assertEqual({symbol: h.book._lot(lot.lid).reason for symbol, lot in lots.items()},
                         {"SPY": "program", "QQQ": "max_hold", "IWM": "retired", "DIA": "demoted", "AAPL": "carried"})
        self.assertEqual(len(told(h)), 1)

    def test_the_owners_flatten_is_out_within_minutes(self):
        h = self.harness()
        inst, lot = self.held(h)
        other, held = self.held(h, "QQQ", "fam-b")
        h.proof.sell = False
        # Inside the open window the flatten's exits wait with every other exit, and go at the cut-off.
        h.state.put(L.OWNER_FLATTEN, {"why": "a rollback", "by": "the owner", "at": at(MONDAY, 9, 33)})
        h.tick(9, 33)
        self.assertEqual(h.venue.sent, [])
        self.assertEqual(len(h.intents(kind="house_exit", tag="flatten")), 2)
        h.tick(9, 44)
        self.assertEqual(h.venue.sent, [])
        h.tick(9, 45)
        self.assertEqual(sorted(sent(h)), [("sell", "QQQ"), ("sell", "SPY")])
        h.tick(9, 46)
        self.assertEqual([(x.status, x.reason) for x in (h.book._lot(lot.lid), h.book._lot(held.lid))],
                         [("closed", "flatten")] * 2)

    def test_a_flatten_in_mid_session_is_sent_the_minute_it_is_read(self):
        h = self.harness()
        inst, lot = self.held(h)
        h.proof.sell = False
        h.proof.failed = FAILED
        h.clock.set(at(MONDAY, 11, 0))
        h.state.put(L.OWNER_FLATTEN, {"why": "a rollback", "by": "the owner", "at": h.clock()})
        h.tick(11, 0)
        self.assertEqual(sent(h), [("sell", "SPY")])
        h.tick(11, 1)
        self.assertEqual((h.book._lot(lot.lid).status, h.book._lot(lot.lid).reason), ("closed", "flatten"))
        self.assertEqual(len(told(h)), 1)

    def test_a_close_window_sale_goes_in_its_window(self):
        """A CLOSE-WINDOW SALE on a day the SELL stage has not passed: its window (the close - 300 s) is after the
        entry cut-off by construction, so it never waits on the stage. It waits for the close as it always did, goes
        there, and is the session's one alert when no open exit said it first."""
        h = self.harness()
        inst, lot = self.held(h)
        h.intent(inst, "sell", symbol="SPY", lid=lot.lid, at_="close")
        h.proof.sell = False
        h.tick(9, 45)
        h.tick(15, 54)
        self.assertEqual(h.venue.sent, [], "a close exit waits for the close, as before")
        self.assertEqual(h.alerts, [], "and nothing is said before an exit is due")
        h.tick(15, 55)
        self.assertEqual(sent(h), [("sell", "SPY")])
        h.tick(15, 56)
        closed = h.book._lot(lot.lid)
        self.assertEqual((closed.status, closed.exit_at), ("closed", "close"))
        self.assertEqual(len(told(h)), 1)

    def test_a_half_days_close_window_is_past_the_cut_off_too(self):
        before, half = dt.date(2026, 11, 25), dt.date(2026, 11, 27)     # the Friday after Thanksgiving closes at 13:00
        self.assertTrue(S.moments(half).early)
        self.assertLess(S.moments(half).entry_until, S.moments(half).close_send)
        h = self.harness()
        h.state.put("eq_decide", {"day": before.isoformat(), "status": "done"})
        inst, lot = self.held(h, opened=before)
        h.intent(inst, "sell", symbol="SPY", lid=lot.lid, at_="close", exec_day=half, decided=before)
        h.proof.sell = False
        h.tick(9, 45, day=half)
        h.tick(12, 54, day=half)
        self.assertEqual((h.venue.sent, h.alerts), ([], []))
        h.tick(12, 55, day=half)
        self.assertEqual(sent(h), [("sell", "SPY")])
        self.assertEqual(len(told(h)), 1)

    def test_the_min_hold_and_the_kill_switch_still_hold_an_exit(self):
        h = self.harness()
        inst, bought_today = self.held(h, opened=MONDAY, entry_at="open")
        other, lot = self.held(h, "QQQ", "fam-b")
        h.book._plan_exit(bought_today, exec_day=MONDAY.isoformat(), at="open", reason="flatten", why="a rollback",
                          decided_day=MONDAY.isoformat())
        kept = h.intent(other, "sell", symbol="QQQ", lid=lot.lid)
        h.proof.sell = False
        h.kill = True
        h.tick(9, 45)
        h.tick(9, 46)
        self.assertEqual(h.venue.sent, [], "never in the session it was bought; never through the gateway's kill")
        self.assertIn("kill switch", h.get_intent(kept.iid).why)
        h.kill = False
        h.tick(9, 47)
        self.assertEqual(sent(h), [("sell", "QQQ")])
        self.assertEqual(h.book._lot(bought_today.lid).status, "open")

    def test_a_lot_bought_today_says_nothing(self):
        h = self.harness()
        inst, bought_today = self.held(h, opened=MONDAY, entry_at="open")
        h.book._plan_exit(bought_today, exec_day=MONDAY.isoformat(), at="open", reason="flatten", why="a rollback",
                          decided_day=MONDAY.isoformat())
        h.proof.sell = False
        h.tick(9, 45)
        h.tick(11, 0)
        self.assertEqual((h.venue.sent, h.alerts), ([], []), "the minimum hold holds it: no exit met the unproven path")

    def test_a_failed_stage_still_stops_new_buys_while_exits_go(self):
        h = self.harness()
        inst, lot = self.held(h)
        other = h.instance("fam-b")
        h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
        opening = h.intent(other, "buy", symbol="IWM", share="0.2")
        closing = h.intent(other, "buy", symbol="QQQ", share="0.2", at_="close")
        h.proof.sell = False
        h.proof.failed = FAILED
        for mm in range(31, 46):
            h.tick(9, mm)
        self.assertEqual(sent(h), [("sell", "SPY")])
        for mm in (55, 56, 57, 58, 59):
            h.tick(15, mm)
        h.tick(16, 0)
        self.assertEqual(sent(h), [("sell", "SPY")], "no real buy, at the open or at the close")
        for buy in (opening, closing):
            self.assertEqual(h.get_intent(buy.iid).status, "missed")
            self.assertIn("new real equity buys stop", h.get_intent(buy.iid).why)

    def test_stage_buy_gates_every_real_buy_with_no_end(self):
        h = self.harness()
        inst = h.instance()
        opening = h.intent(inst, "buy", symbol="SPY", share="0.2")
        closing = h.intent(inst, "buy", symbol="QQQ", share="0.2", at_="close")
        h.proof.ok = h.proof.sell = False
        for hh, mm in [(9, m) for m in range(31, 47)] + [(11, 0), (15, 55), (15, 56), (15, 57), (15, 58), (15, 59), (16, 0)]:
            h.tick(hh, mm)
        self.assertEqual(h.venue.sent, [])
        self.assertEqual([h.get_intent(i.iid).status for i in (opening, closing)], ["missed", "missed"])
        self.assertEqual(h.alerts, [], "a buy that waits on stage BUY is no exit: nothing is said")

    def test_a_proof_that_cannot_be_read_holds_an_exit_no_longer_either(self):
        h = self.harness()
        inst, lot = self.held(h)
        sale = h.intent(inst, "sell", symbol="SPY", lid=lot.lid)

        def unreadable():
            raise RuntimeError("the state cannot be read")

        h.proof.sell_passed = h.proof.sell_failed = unreadable
        h.tick(9, 44)
        self.assertEqual(h.venue.sent, [])
        self.assertIn("could not be read", h.get_intent(sale.iid).why)
        h.tick(9, 45)
        self.assertEqual(sent(h), [("sell", "SPY")])
        [text] = told(h)
        self.assertIn("could not be read (RuntimeError)", text)

    def test_no_paper_account_at_all_says_nothing(self):
        h = self.harness()
        h.proof = None
        h.book = h.new_book()
        inst, lot = self.held(h)
        h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
        h.tick(9, 31)
        self.assertEqual(sent(h), [("sell", "SPY")], "no proof can ever run there: its exits never waited")
        self.assertEqual(h.alerts, [])


@unittest.skipUnless(HAVE, "numpy not installed")
class TheWeeks(BookTest):
    """MONDAY TO THURSDAY THROUGH THE REAL BOOK beside the REAL `StockPaperProof` on a practice account (the
    rehearsal's week): program A buys QQQ at Monday's open and holds to its maximum of 3 sessions (the House exits it
    at Thursday's open); program B buys SPY when flat and sells every lot at the next open. The decides, the House's
    exit rules, the windows and the proof are the book's own; the venue fills a marketable limit at once."""

    A, B = "bred-a-hold3", "bred-b-range"
    MINUTES = ([(8, 31), (9, 25)] + [(9, m) for m in range(30, 51)] + [(11, 0), (13, 0), (15, 0)]
               + [(15, m) for m in range(54, 60)] + [(16, 0), (16, 21), (16, 31)])

    def week(self, *, paper_setup=None, days=(MONDAY, TUESDAY, WEDNESDAY, THURSDAY), before=None):
        from league.live.paper import StockPaperProof
        from league.tests.live_fakes import Market as PaperMarket
        from league.tests.test_equity_paper import PaperStocks

        h = self.harness(rows=[family_row(self.A, symbols=("QQQ",)), family_row(self.B, symbols=("SPY",))])
        paper = PaperStocks(PaperMarket(h.clock))
        h.paper = paper
        h.proof = StockPaperProof(h.state, paper, clock=h.clock, alert=lambda level, text: h.alerts.append((level, text)))
        h.book = h.new_book()
        a, b = h.instance(self.A, max_hold=3), h.instance(self.B, max_hold=5)
        h.decider.needs[a.id] = {"symbols": ["QQQ"], "history": 5, "max_hold_sessions": 3}
        h.decider.needs[b.id] = {"symbols": ["SPY"], "history": 5, "max_hold_sessions": 5}
        # One table of invented daily bars through the week's last session (the book's fetch asks through its own day,
        # so each morning's audit reads the rows the decision before it read).
        h.decide_setup(days[-1], symbols=("SPY", "QQQ"))
        h.state.put("eq_decision", {"day": FRIDAY.isoformat(), "audit": "ok"})
        h.intent(a, "buy", symbol="QQQ", share="0.4", tag="hold3")
        h.intent(b, "buy", symbol="SPY", share="0.2", tag="range")
        if paper_setup is not None:
            paper_setup(paper, None)
        log, practice = [], []
        for day in days:
            if paper_setup is not None:
                paper_setup(paper, day)
            for hh, mm in self.MINUTES:
                if before is not None:
                    before(h, day, hh, mm)
                if (hh, mm) == (16, 31):
                    self.plan(h, a, b)
                n, p = len(h.venue.sent), len(paper.sent)
                out = h.tick(hh, mm, day=day)
                self.assertNotIn("errors", out, (day, hh, mm, out.get("errors")))
                log += [(day.isoformat(), f"{hh:02d}:{mm:02d}", x["side"], x["symbol"]) for x in h.venue.sent[n:]]
                practice += [(day.isoformat(), f"{hh:02d}:{mm:02d}", x["side"]) for x in paper.sent[p:]]
        return h, a, b, log, practice

    @staticmethod
    def plan(h, a, b) -> None:
        """The two programs' decisions of this close, from the book as it stands (the rehearsal's shapes)."""
        held = {inst.id: [lot for lot in h.lots(open_only=True) if lot.instance == inst.id] for inst in (a, b)}
        h.decider.plans[a.id] = [] if held[a.id] else [{"buy": "QQQ", "share": 0.4, "at": "open", "tag": "hold3"}]
        h.decider.plans[b.id] = ([{"sell": lot.lid, "at": "open", "tag": "range"} for lot in held[b.id]] if held[b.id]
                                 else [{"buy": "SPY", "share": 0.2, "at": "open", "tag": "range"}])

    #: THE NORMAL WEEK, order for order (it is the same list on the release before this one): stage BUY passes in
    #: Monday's 09:32 minute and both buys go in it; stage SELL passes in Tuesday's 09:32 minute and B's sale, which
    #: waited one minute for it, goes in it; from Wednesday on an order goes in the open window's first minute.
    NORMAL = [("2026-10-12", "09:32", "buy", "QQQ"), ("2026-10-12", "09:32", "buy", "SPY"),
              ("2026-10-13", "09:32", "sell", "SPY"),
              ("2026-10-14", "09:31", "buy", "SPY"),
              ("2026-10-15", "09:31", "sell", "SPY"), ("2026-10-15", "09:31", "sell", "QQQ")]
    NORMAL_PRACTICE = [("2026-10-12", "09:31", "buy"), ("2026-10-13", "09:31", "sell")]

    def test_the_normal_week_is_order_for_order_what_it_was(self):
        h, a, b, log, practice = self.week()
        self.assertEqual(log, self.NORMAL)
        self.assertEqual(practice, self.NORMAL_PRACTICE)
        self.assertTrue(h.proof.passed())
        self.assertEqual(told(h), [])
        self.assertIsNone(h.state.get("eq_sell_unproven"))
        self.assertEqual([(lot.symbol, lot.opened_day, lot.exit_day, lot.reason) for lot in h.lots()],
                         [("QQQ", "2026-10-12", "2026-10-15", "max_hold"), ("SPY", "2026-10-12", "2026-10-13", "program"),
                          ("SPY", "2026-10-14", "2026-10-15", "program")])

    def test_no_fill_activity_listed_the_lots_leave_at_the_cut_off(self):
        """THE REHEARSAL'S FAILING WEEK: the practice account lists no FILL activity, so stage SELL can never pass.
        Before this release Monday's lots were still held on Friday and no command got them out."""
        def no_activities(paper, day):
            paper.activity_lag = True

        h, a, b, log, practice = self.week(paper_setup=no_activities)
        self.assertEqual(log, [("2026-10-12", "09:32", "buy", "QQQ"), ("2026-10-12", "09:32", "buy", "SPY"),
                               ("2026-10-13", "09:45", "sell", "SPY"),      # B's own sale: Tuesday, at the cut-off
                               ("2026-10-15", "09:45", "sell", "QQQ")])     # A's maximum-hold exit: Thursday, the same
        self.assertEqual([(lot.symbol, lot.exit_day, lot.exit_at, lot.reason) for lot in h.lots()],
                         [("QQQ", "2026-10-15", "open", "max_hold"), ("SPY", "2026-10-13", "open", "program")])
        self.assertEqual(h.lots(open_only=True), [], "nothing is left held")
        # The stage fails at the end of each window it sold in, with its own alarm, and the proof tries again: a buy
        # the next session, a sale the one after.
        self.assertEqual(practice, [("2026-10-12", "09:31", "buy"), ("2026-10-13", "09:31", "sell"),
                                    ("2026-10-14", "09:31", "buy"), ("2026-10-15", "09:31", "sell")])
        self.assertEqual(sum(1 for _, text in h.alerts if OWN_ALARM in text), 2)
        self.assertFalse(h.proof.sell_passed())
        # ONE alert a session an exit went unproven (Tuesday, Thursday), each with the stage's own reason.
        tuesday, thursday = told(h)
        self.assertIn("its attempt stands at sold: sold; waiting for activity_witness", tuesday)
        self.assertIn("SELL stage failed on 2026-10-13: the round trip ended without activity_witness", thursday)
        # UNCHANGED: the failed stage stops every new real buy (B's rebuys of Wednesday and Thursday).
        rebuys = [i for i in h.intents(instance=b.id, kind="buy") if i.exec_day in ("2026-10-14", "2026-10-15")]
        self.assertEqual([i.status for i in rebuys], ["missed", "missed"])
        self.assertTrue(all("new real equity buys stop" in i.why for i in rebuys), [i.why for i in rebuys])

    def test_the_practice_sale_rests_the_lots_leave_at_the_cut_off(self):
        """THE REHEARSAL'S OTHER FAILING WEEK: the practice sale never fills (its buy does)."""
        def sale_rests(paper, day):
            paper.stock_fill = "natural" if day in (None, MONDAY) else "none"

        h, a, b, log, practice = self.week(paper_setup=sale_rests)
        self.assertEqual(log, [("2026-10-12", "09:32", "buy", "QQQ"), ("2026-10-12", "09:32", "buy", "SPY"),
                               ("2026-10-13", "09:45", "sell", "SPY"), ("2026-10-15", "09:45", "sell", "QQQ")])
        self.assertEqual(h.lots(open_only=True), [])
        tuesday, thursday = told(h)
        self.assertIn("its attempt stands at sell_sent", tuesday)
        # The lot that rests is sold again each session, so the stage's last failure on Thursday morning is Wednesday's.
        self.assertIn("SELL stage failed on 2026-10-14: the practice lot was not sold by the open window's end",
                      thursday)
        self.assertEqual(sum(1 for _, text in h.alerts if OWN_ALARM in text), 3, "Tuesday, Wednesday, Thursday")
        self.assertFalse(h.proof.sell_passed())

    def test_a_flatten_on_tuesday_morning_is_out_by_the_cut_offs_next_minute(self):
        def no_activities(paper, day):
            paper.activity_lag = True

        def flatten(h, day, hh, mm):
            if (day, hh, mm) == (TUESDAY, 9, 33):
                h.state.put(L.OWNER_FLATTEN, {"why": "the rehearsal's rollback", "by": "the owner", "at": h.clock()})

        h, a, b, log, practice = self.week(paper_setup=no_activities, days=(MONDAY, TUESDAY), before=flatten)
        self.assertEqual(log[2:], [("2026-10-13", "09:45", "sell", "SPY"), ("2026-10-13", "09:45", "sell", "QQQ")])
        self.assertEqual(h.lots(open_only=True), [])
        self.assertEqual({lot.symbol: (lot.exit_day, lot.reason) for lot in h.lots()},
                         {"QQQ": ("2026-10-13", "flatten"), "SPY": ("2026-10-13", "program")})
        self.assertEqual(len(told(h)), 1)

    def test_a_flatten_on_tuesday_at_eleven_is_out_in_the_minute(self):
        def no_activities(paper, day):
            paper.activity_lag = True

        def flatten(h, day, hh, mm):
            if (day, hh, mm) == (TUESDAY, 11, 0):
                h.state.put(L.OWNER_FLATTEN, {"why": "the rehearsal's rollback", "by": "the owner", "at": h.clock()})

        h, a, b, log, practice = self.week(paper_setup=no_activities, days=(MONDAY, TUESDAY), before=flatten)
        self.assertEqual(log[2:], [("2026-10-13", "09:45", "sell", "SPY"), ("2026-10-13", "11:00", "sell", "QQQ")])
        self.assertEqual(h.lots(open_only=True), [])


if __name__ == "__main__":
    unittest.main()
