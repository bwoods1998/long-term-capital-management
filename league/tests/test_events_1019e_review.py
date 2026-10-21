"""RELEASE 1019e'S REVIEW: the adversarial reviews' majors, each with the test that fails without its fix, on invented
data only (R3's synthetic store, league/tests/test_events_births.py `Synth`, and the House lane's harness,
league/tests/test_events_house.py `LaneCase`):

- THE BIRTHS CALL IS INSIDE THE LANE'S LINE (league/events/house.py `_spend_today`, `birth_usd`, `line_left`;
  league/events/births.py `propose`'s `line_left`; league/ops/budget.py `lane_spend`; league/site_lane.py
  `verdict_usd`): its stored cost counts in the lane's day line, in the budget rule's measure of the lane (window, peak
  and today) and in the site's bill; the next verdict is refused once births and verdicts reach the line; the call
  itself is made only when its worst case fits under what is left of the line;
- EVERY FAMILY A SEATABLE BIRTH CAN HAVE TRADES WHAT ITS SHADOW DECIDES (league/events/book.py `rows_for`: the `ins`
  family's Form 4 cluster triggers were missing): for a seatable birth of each of the eight families, the House's
  real-money picks at each auction are exactly its shadow's planned intents; a family the book reads no rows for is
  an error, never silence;
- A DECISION MADE WITHOUT A BIRTH IS NOT MADE FOR IT (league/events/screen.py `final_until`, `births_made_without`;
  league/events/run.py `births_only`; the House's lane and the CLI's catchup): a week decided by a release without
  births (release 1019d's receipts) leaves the birth's looks waiting, not final over an incomplete record; the births'
  own decisions, as a backfill, decide exactly what the whole decisions would have, and no PREREG row moves; the
  House's lane schedules them for the decisions its hourly re-decision no longer reaches;
- A BIRTH'S LOOK WAITS WHEN ITS CONTROL'S PART FAILED (`final_until` reads the birth's group);
- A PROGRAM THE PROCESS DOES NOT KNOW TAKES THE LIMIT AT ENTRY (league/events/score.py `_above_limit`, fail closed);
- A READ ERROR OF THE BIRTHS TABLE KEEPS THE BIRTHS LAST READ FROM THAT STORE (league/events/programs.py
  `load_births`), and loads none for a store never read."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from league import site_lane
from league.events import births as BI
from league.events import book as EB
from league.events import calendar as C
from league.events import house as H
from league.events import programs as P
from league.events import run as R
from league.events import score as SC
from league.events import screen as SN
from league.events import store as S
from league.ops import budget as B
from league.tests import test_events_births as TB
from league.tests import test_events_house as TH

UTC = dt.timezone.utc
spec, et, unload = TB.spec, TB.et, TB.unload


# ======================================================================================================== the line
class TheBirthsCallIsInsideTheLine(TH.LaneCase):
    """The births job at 21:15 ET of Tue Oct 20 (01:15Z Wed Oct 21, the UTC day the line holds) with the lane's line at
    $0.10 and the gateway stating $0.20 for the call (the reviewer's case)."""

    def night(self, *, line: float, cost: str) -> None:
        self.addCleanup(unload)
        self.lane = self.new_lane(births=True, verdict_usd_day=line)
        self.gw.cost = cost
        self.at(TH.et("2026-10-20", "20:31"))
        with self.store() as st:
            for kind, t in (("open", "09:15"), ("close", "15:46")):
                rid = st.start_receipt(f"decide-{kind}:2026-10-20", now=TH.et("2026-10-20", t))
                st.finish_receipt(rid, "ok", {}, now=TH.et("2026-10-20", t))
            st.set_meta(TH.SC.equity_key(dt.date(2026, 10, 20)), repr(2000.0))
        self.lane._redecide_next = TH.et("2026-10-21", "00:00")
        for when in ("20:31", "20:32", "20:33", "21:10", "21:16"):
            self.at(TH.et("2026-10-20", when))
            self.mark_recorded()
            self.turn()

    def births_receipt(self) -> dict:
        [row] = self.receipts("births")
        return json.loads(row["summary"])

    def test_its_cost_counts_in_the_lanes_line_the_budgets_measure_and_the_bill(self):
        self.night(line=0.10, cost="0.20")
        self.assertEqual(self.births_receipt()["call"]["status"], "ok", "its worst case fit under the $0.10 left")
        with self.store() as st:
            [row] = [dict(r) for r in st.db.execute("SELECT answered_at, usd FROM birth_calls")]
        self.assertEqual(row["usd"], 0.2)
        self.assertTrue(row["answered_at"].startswith("2026-10-21T01:16"), "the UTC day of Wed Oct 21")
        # The lane's own line: the next task reads the births call in the day's spend, so the next verdict is refused.
        self.at(TH.et("2026-10-20", "21:17"))
        with self.store() as st:
            self.lane._spend_today(st, self.clock_dt())
            self.assertEqual(H.birth_usd(st.db, *H.verdict_day(self.clock_dt())[1]), 0.2)
        self.assertAlmostEqual(self.lane._usd["usd"], 0.2)
        self.assertEqual(self.lane.claude_refusal(None), "cap", "births and verdicts reached the line: no verdict asked")
        self.assertEqual(self.lane.line_left(), 0.0)
        # The budget rule's measure of the lane: today, its heaviest day and its window.
        state = self.root.parent
        spend = B.lane_spend(state, self.clock())
        self.assertEqual((spend["today_usd"], spend["peak_usd_day"], spend["usd_day"]), (0.2, 0.2, round(0.2 / 7, 4)))
        self.assertIn("0 verdicts and 1 births calls answered in the last 7 days, $0.20", spend["source"])
        # The site's bill: the Claude part holds it (never understated).
        self.assertEqual(site_lane.read_verdict_usd(state), Decimal("0.2"))

    def test_the_call_is_not_made_when_its_worst_case_is_over_what_is_left_of_the_line(self):
        self.night(line=0.01, cost="0.002")
        call = self.births_receipt()["call"]
        self.assertEqual(call["status"], "cap")
        self.assertIn("left of the lane's line today", call["why"])
        self.assertEqual([c for c in self.gw.claude_calls if c.get("system") == BI.SYSTEM], [], "no call was made")
        with self.store() as st:
            self.assertIsNone(st.db.execute("SELECT 1 FROM birth_calls").fetchone())

    def test_propose_holds_the_call_to_the_line_left_and_to_the_nights_cap_both(self):
        self.addCleanup(unload)
        with self.store() as st:
            sheet = {"sessions": 0}
            worst = BI.worst_usd(BI.render(sheet, BI.budget(st), k=BI.K))
            now = lambda: dt.datetime(2026, 10, 21, 1, 16, tzinfo=UTC)  # noqa: E731
            gw = TB.FakeArchitect("{}")
            got = BI.propose(st, gw, sheet, night=dt.date(2026, 10, 20), now=now, line_left=worst - 0.0001)
            self.assertEqual((got["status"], gw.calls), ("cap", []))
            got = BI.propose(st, gw, sheet, night=dt.date(2026, 10, 20), now=now, line_left=worst + 0.0001)
            self.assertEqual(got["status"], "ok")
            self.assertEqual(len(gw.calls), 1)


# ======================================================================================================== every family
class EveryFamilyTradesWhatItsShadowDecides(unittest.TestCase):
    """The invented week of test_events_births (Nov 2-6, 2026), with Form 4 CLUSTERS added (two insiders of one issuer,
    $30,000 each, in two filings), and one seatable birth of each of the eight families, registered Mon Nov 2 20:00 ET.
    At every auction each birth's real-money picks (league/events/book.py `picks`, the book's read-only view) are its
    shadow's planned intents of that entry session, event for event."""

    DAYS = TB.PreregIntentsAreUnchanged.DAYS
    BORN_AT = TB.PreregIntentsAreUnchanged.BORN_AT
    CLUSTER = ("KKK", "LLL", "MMM", "NNN", "OOO")
    SPECS = (spec("EVL-B-ERN-2", "ern", {"score_min": 2}, rank="score"),
             spec("EVL-B-8K-801", "8k", {"items": ["8.01"]}),
             spec("EVL-B-INS-CL", "ins", {"value_min": 50000}, rank="value", seatable=False),   # A89: a record
             spec("EVL-B-INSB-OFF", "ins-buy", {"value_min": 50000, "roles": "officer"}, rank="value"),
             spec("EVL-B-NEWS-GN", "news", {"sources": ["globenewswire"]}),
             spec("EVL-B-ERNR", "ern-react", {"react_min": 1.02}, rank="reaction", exit_="close"),
             spec("EVL-B-NDAY", "news-day", {"score_min": 2}, rank="score", exit_="close"),
             spec("EVL-B-NREACT", "news-react", {"react_min": 1.02}, rank="reaction", exit_="close"))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(unload)

    def cluster_buy(self, s: TB.Synth, sym: str, accepted: dt.datetime, owner: str, usd: float) -> None:
        acc = s.filing(sym, accepted, (), form="4")
        s.st.db.execute("INSERT INTO form4_owners(accession, owner_cik, owner_name, is_director, is_officer, officer_title, "
                        "is_ten_pct) VALUES(?, ?, 'Owner', 1, 0, NULL, 0)", (acc, owner))
        s.st.db.execute("INSERT INTO form4_tx(accession, seq, security, tx_date, code, shares, price, acquired, owned_after) "
                        "VALUES(?, 1, 'Common', ?, 'P', ?, 10.0, 'A', 1)",
                        (acc, accepted.astimezone(TB.NY).date().isoformat(), usd / 10.0))

    def week(self, root: Path) -> TB.Synth:
        s = TB.Synth(root)
        self.addCleanup(s.st.close)
        for i, day in enumerate(self.DAYS):
            prior = C.previous(s.st, day, 1)[0].day
            for sym in TB.ISSUERS.values():
                s.eligible(day, sym)
                s.bar(prior, sym)
                s.bar(day, sym)
            a = s.filing("AAA", et(prior, 16, 30))
            s.doc_verdict(a, 3, "raised")
            b = s.filing("BBB", et(prior, 16, 35))
            s.doc_verdict(b, 1)
            s.filing("CCC", et(prior, 17), ("5.02",))
            d = s.filing("DDD", et(prior, 17, 10), ("8.01",))
            s.doc_verdict(d, 2)
            s.insider("EEE", et(prior, 18), 120_000, director=True)
            s.insider("FFF", et(prior, 18, 5), 60_000, director=False, officer=True)
            sym = self.CLUSTER[i]          # a Form 4 cluster: two insiders, two filings, $60,000 in all
            self.cluster_buy(s, sym, et(prior, 18, 20), "91", 30_000)
            self.cluster_buy(s, sym, et(prior, 18, 40), "92", 30_000)
            s.news_verdict(s.article("AAA", et(prior, 19)), 2)
            s.news_verdict(s.article("GGG", et(day, 7), "globenewswire"), 3)
            h = s.filing("HHH", et(day, 12))
            s.doc_verdict(h, 2)
            s.news_verdict(s.article("BBB", et(day, 11)), 3)
            s.news_verdict(s.article("III", et(day, 13), "prnewswire"), -1)
        for i, sp in enumerate(self.SPECS):
            s.register(sp, self.BORN_AT, seq=i)
        P.load_births(s.st)
        return s

    def test_every_seatable_births_real_money_picks_are_its_shadows_intents(self):
        s = self.week(Path(self.tmp.name) / "w")
        families = {json.loads(p.spec)["family"] for p in EB.seatable() if p.spec is not None}
        self.assertEqual(families, set(BI.FAMILIES) - {"ins"}, "a seatable birth of every family real money can read "
                                                               "(A89: an ins cluster birth is a record only)")
        self.assertNotIn("EVL-B-INS-CL", {p.id for p in EB.seatable()})
        ctx = R.Context(s.st, TH.FakeGateway(), lambda url: b"", now=lambda: dt.datetime(2026, 11, 7, 1, 0, tzinfo=UTC))
        for day in self.DAYS:
            R.decide_open(ctx, day)
            R.decide_close(ctx, day)
        lane = EB.Lane(Path(s.st.root) / S.DB_NAME)
        self.addCleanup(lane.close)
        traded: dict[str, int] = {}
        for p in EB.seatable():
            if p.spec is None:
                continue
            for day in self.DAYS:
                session = C.session(lane, day)
                moment = session.open_decide if p.entry_at == "open" else session.close_decide
                picks = EB.picks(lane, p, day, decided_at=moment, reaction=lambda row, uni: 1.05)
                shadow = [r[0] for r in s.st.db.execute(
                    "SELECT event FROM intents WHERE program=? AND version=? AND entry_day=? AND status='planned' "
                    "ORDER BY event", (p.id, p.version, day.isoformat()))]
                self.assertEqual(sorted(x.event for x in picks), shadow, f"{p.id} at the {p.entry_at} of {day}")
                traded[p.id] = traded.get(p.id, 0) + len(picks)
        self.assertEqual({k for k, n in traded.items() if n}, {p.id for p in EB.seatable() if p.spec is not None},
                         f"every birth trades in the week: {traded}")

    def test_a_seatable_ins_cluster_birth_is_refused_and_the_book_reads_no_cluster_rows(self):
        # A89 (release 1019e's last review): a Form 4 cluster is judged over every Form 4 of the issuer in its window,
        # including filings stored after a decision; real money may read only what was stored before it (A72). So an
        # ins birth is a record (free), never seatable, and the House's book reads no rows for the family.
        with self.assertRaises(BI.SpecError) as raised:
            BI.parse(spec("EVL-B-INS-X", "ins", {"value_min": 50000}, rank="value"))
        self.assertIn("A89", str(raised.exception))
        self.assertFalse(BI.parse(spec("EVL-B-INS-X", "ins", {"value_min": 50000}, rank="value", seatable=False))["seatable"])
        s = self.week(Path(self.tmp.name) / "w")
        lane = EB.Lane(Path(s.st.root) / S.DB_NAME)
        self.addCleanup(lane.close)
        cluster = P.Program("EVL-B-INS-Y", 1, True, "ins", "open", 1, False, rule="birth", prereg=3,
                            born_at=self.BORN_AT, spec="{}")
        with self.assertRaises(LookupError):
            EB.rows_for(lane, cluster, self.DAYS[2], C.session(lane, self.DAYS[2]).open_decide)

    def test_a_family_the_book_reads_no_rows_for_is_an_error_never_silence(self):
        s = self.week(Path(self.tmp.name) / "w")
        lane = EB.Lane(Path(s.st.root) / S.DB_NAME)
        self.addCleanup(lane.close)
        odd = P.Program("EVL-B-ODD", 1, True, "options", "open", 1, False, rule="birth", prereg=3,
                        born_at=self.BORN_AT, spec="{}")
        with self.assertRaises(LookupError):
            EB.rows_for(lane, odd, self.DAYS[2], C.session(lane, self.DAYS[2]).open_decide)


# ======================================================================================================== named
def named(kind: str, *, births: bool) -> dict:
    """A whole decision's summary that names every program of its entry kind (a PREREG one only when `births` is False:
    release 1019d's receipts, made without the births' rows)."""
    return {SN.program_key(p.id, p.version): {"planned": 0} for p in P.PROGRAMS
            if p.entry_at == kind and (births or p.spec is None)}


class ADecisionWithoutABirthIsNotMadeForIt(unittest.TestCase):
    """The invented week decided by a release WITHOUT births (release 1019d, the documented rollback), its births
    registered in the store all along; then the later sessions decided whole, more than the three the House decides
    again, by release 1019e."""

    NOW = dt.datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
    TODAY = dt.date(2026, 11, 13)
    BIRTH = "EVL-B-ERN-TOP"          # an open-entry READ birth, with its control
    CLOSE_BIRTH = "EVL-B-ERNREACT-ON"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(unload)

    def week(self, root: Path, *, decided_with_births: bool) -> S.Store:
        """test_events_births' invented week and its five births; decided with them loaded, or without (1019d)."""
        st = _decide(TB.PreregIntentsAreUnchanged, root, decided_with_births)
        self.addCleanup(st.close)
        return st

    def finish(self, st: S.Store) -> None:
        """The sessions after the week, decided whole by release 1019e (naming every program, births too), and the
        daily-index backfill done: so only the week's own receipts decide whether its closes are final."""
        later = TB.sessions_between(st, dt.date(2026, 11, 9), dt.date(2026, 11, 12))
        earlier = TB.sessions_between(st, dt.date(2026, 10, 19), dt.date(2026, 10, 30))
        for day in earlier + later:
            for kind in ("open", "close"):
                rid = st.start_receipt(f"decide-{kind}:{day}", now=self.NOW)
                st.finish_receipt(rid, "ok", named(kind, births=True), now=self.NOW)
        for day in TB.sessions_between(st, dt.date(2026, 10, 19), dt.date(2026, 11, 12)):
            st.set_meta(f"evl:backfill:{day}", "done")

    def intents(self, st: S.Store, prereg: bool) -> list[dict]:
        ids = {p.id for p in P.PREREG_PROGRAMS}
        return [dict(r) for r in st.db.execute("SELECT program, version, event, symbol, entry_day, status FROM intents "
                                                "ORDER BY program, version, event") if (r["program"] in ids) == prereg]

    def test_release_1019d_receipts_leave_a_births_looks_waiting_and_its_own_decisions_catch_up(self):
        whole = self.week(Path(self.tmp.name) / "whole", decided_with_births=True)
        births_whole = self.intents(whole, prereg=False)
        prereg_whole = self.intents(whole, prereg=True)
        st = self.week(Path(self.tmp.name) / "d", decided_with_births=False)
        self.finish(st)
        self.assertEqual(self.intents(st, prereg=False), [], "release 1019d decided none of the births")
        self.assertEqual(self.intents(st, prereg=True), prereg_whole)
        # THE JUDGE: the births' first decision after their registration (Tue Nov 3's open; their close-entry rows'
        # Tue Nov 3 close) is not made for them, so none of their closes is final: their looks wait.
        for birth, kind in ((self.BIRTH, "open"), (self.CLOSE_BIRTH, "close")):
            horizon, why = SN.final_until(st, birth, 1, self.TODAY, self.NOW)
            self.assertEqual(horizon, dt.date(2026, 11, 2), f"{birth}: only the session of its registration ({why})")
            self.assertIn(f"the {kind} decision of 2026-11-03 is made without its rows", why)
        prereg, _ = SN.final_until(st, "EVL-8K-READ-O1", 2, self.TODAY, self.NOW)
        self.assertEqual(prereg, dt.date(2026, 11, 9), "every PREREG program's closes are final as before")
        waiting = SN.births_made_without(st, self.TODAY)
        self.assertEqual(set(waiting), {(kind, d) for d in TB.PreregIntentsAreUnchanged.DAYS[1:]
                                        for kind in ("open", "close")},
                         "every decision after their registration (Mon Nov 2's are before it)")
        self.assertFalse(any(waiting.values()), "none decided by themselves yet")
        # THE BIRTHS' OWN DECISIONS (the CLI's catchup, as the House's lane runs them): exactly the whole decisions'
        # intents of the births, and no PREREG row decided again.
        gw = TH.FakeGateway()
        ctx = R.Context(st, gw, lambda url: b"", now=lambda: self.NOW)
        from league.events import __main__ as CLI

        out = CLI.catchup(ctx)
        self.assertEqual(sorted(k for k in out if "births" in k),
                         sorted(f"{SN.BIRTHS_KIND[kind]}:{day}" for kind, day in waiting))
        self.assertEqual(gw.claude_calls, [], "every verdict they read was stored")
        self.assertEqual(self.intents(st, prereg=True), prereg_whole, "no PREREG row moves")
        self.assertEqual(self.intents(st, prereg=False), births_whole, "the births' record as the whole decisions make it")
        self.assertEqual(SN.births_made_without(st, self.TODAY), {})
        for birth in (self.BIRTH, self.CLOSE_BIRTH):
            horizon, why = SN.final_until(st, birth, 1, self.TODAY, self.NOW)
            self.assertEqual(horizon, dt.date(2026, 11, 9), f"{birth}: {why}")
        # A whole re-decision made later by a release without births again (stale) puts the session back.
        rid = st.start_receipt("decide-open:2026-11-04", now=self.NOW)
        st.finish_receipt(rid, "ok", named("open", births=False), now=self.NOW)
        self.assertEqual(SN.births_made_without(st, self.TODAY), {("open", dt.date(2026, 11, 4)): True},
                         "stale: decided by themselves, then again whole without them")
        self.assertIn("the open decision of 2026-11-04 is made without its rows",
                      SN.final_until(st, self.BIRTH, 1, self.TODAY, self.NOW)[1])
        self.assertEqual(SN.final_until(st, self.CLOSE_BIRTH, 1, self.TODAY, self.NOW)[0], dt.date(2026, 11, 9),
                         "a close-entry birth reads only the close decisions")

    def test_a_decision_made_before_a_births_registration_is_made_for_it(self):
        st = self.week(Path(self.tmp.name) / "d", decided_with_births=True)
        self.finish(st)
        # Mon Nov 2's close (15:46 ET) is before the births' registration (20:00 ET): its receipt need not name them.
        rid = st.start_receipt("decide-close:2026-11-02", now=self.NOW)
        st.finish_receipt(rid, "ok", named("close", births=False), now=self.NOW)
        self.assertEqual(SN.births_made_without(st, self.TODAY), {})
        self.assertEqual(SN.final_until(st, self.CLOSE_BIRTH, 1, self.TODAY, self.NOW)[0], dt.date(2026, 11, 9))

    def test_a_births_look_waits_when_its_controls_part_failed_or_waits(self):
        st = self.week(Path(self.tmp.name) / "d", decided_with_births=True)
        self.finish(st)
        self.assertEqual(SN.birth_group(P.BY_KEY[(self.BIRTH, 1)]), [self.BIRTH, f"{self.BIRTH}-CTRL"])
        self.assertEqual(SN.birth_group(P.BY_KEY[("EVL-ERN-READ-O1", 2)]), [], "no PREREG program has a births group")
        self.assertEqual(SN.final_until(st, self.BIRTH, 1, self.TODAY, self.NOW)[0], dt.date(2026, 11, 9))
        failed = {R.BIRTHS_FAILED: {f"{self.BIRTH}-CTRL": "KeyError: 'x'"}}
        body = named("open", births=True)
        del body[f"{self.BIRTH}-CTRL"]          # (as run.py writes it: a part that raised names nothing)
        rid = st.start_receipt("decide-open:2026-11-04", now=self.NOW)
        st.finish_receipt(rid, "ok", body | failed, now=self.NOW)
        horizon, why = SN.final_until(st, self.BIRTH, 1, self.TODAY, self.NOW)
        self.assertEqual(horizon, dt.date(2026, 11, 3), "the control's record of Nov 4 is missing its events")
        self.assertIn("the open decision of 2026-11-04 is made without its rows", why)
        rid = st.start_receipt("decide-open:2026-11-04", now=self.NOW)
        st.finish_receipt(rid, "ok", named("open", births=True) | failed, now=self.NOW)
        horizon, why = SN.final_until(st, self.BIRTH, 1, self.TODAY, self.NOW)
        self.assertEqual(horizon, dt.date(2026, 11, 3))
        self.assertIn("the open decision of 2026-11-04 is failed", why, "its control's part raised")
        rid = st.start_receipt("decide-open:2026-11-04", now=self.NOW)
        st.finish_receipt(rid, "pending", named("open", births=True) | {"pending": {f"{self.BIRTH}-CTRL": 1}}, now=self.NOW)
        self.assertEqual(SN.final_until(st, self.BIRTH, 1, self.TODAY, self.NOW)[0], dt.date(2026, 11, 3))
        self.assertEqual(SN.final_until(st, "EVL-ERN-READ-O1", 2, self.TODAY, self.NOW)[0], dt.date(2026, 11, 9),
                         "a PREREG program reads neither")


def _decide(case: type, root: Path, loaded: bool) -> S.Store:
    """test_events_births' invented week (`case`'s days, births and registration time), its births registered in the
    store either way; decided with them loaded (release 1019e) or with none loaded (release 1019d, which has no loader).
    Returns the store, its births loaded."""
    s = TB.Synth(root)
    for day in case.DAYS:
        prior = C.previous(s.st, day, 1)[0].day
        for sym in TB.ISSUERS.values():
            s.eligible(day, sym)
            s.bar(prior, sym)
            s.bar(day, sym)
        a = s.filing("AAA", et(prior, 16, 30))
        s.doc_verdict(a, 3, "raised")
        b = s.filing("BBB", et(prior, 16, 35))
        s.doc_verdict(b, 1)
        s.filing("CCC", et(prior, 17), ("5.02",))
        d = s.filing("DDD", et(prior, 17, 10), ("8.01",))
        s.doc_verdict(d, 2)
        s.insider("EEE", et(prior, 18), 120_000, director=True)
        s.insider("FFF", et(prior, 18, 5), 60_000, director=False, officer=True)
        s.news_verdict(s.article("AAA", et(prior, 19)), 2)
        s.news_verdict(s.article("GGG", et(day, 7), "globenewswire"), 3)
        h = s.filing("HHH", et(day, 12))
        s.doc_verdict(h, 2)
        s.news_verdict(s.article("BBB", et(day, 11)), 3)
        s.news_verdict(s.article("III", et(day, 13), "prnewswire"), -1)
    for i, sp in enumerate(case.SPECS):
        s.register(sp, case.BORN_AT, seq=i)
    if loaded:
        P.load_births(s.st)
    else:
        P.load_births(None)
    ctx = R.Context(s.st, TH.FakeGateway(), lambda url: b"", now=lambda: dt.datetime(2026, 11, 7, 1, 0, tzinfo=UTC))
    for day in case.DAYS:
        R.decide_open(ctx, day)
        R.decide_close(ctx, day)
    P.load_births(s.st)
    return s.st


# ======================================================================================================== the House
class TheHouseDecidesTheBirthsByThemselves(TH.LaneCase):
    """A birth registered Mon Oct 19 20:30 ET; every decision from Tue Oct 20 to Tue Oct 27 made by a release without
    births (release 1019d's receipts); release 1019e's lane on the evening of Tue Oct 27: the hourly re-decision decides
    the last three sessions again whole, and the births' own decision decides each older one, once."""

    BORN_AT = "2026-10-20T00:30:00Z"

    def test_the_lane_runs_the_births_own_decision_for_each_older_session_once(self):
        self.addCleanup(unload)
        sp = spec("EVL-B-8K-502", "8k", {"items": ["5.02"]})
        days = ["2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-26", "2026-10-27"]
        with self.store() as st:
            text = BI.canonical(sp)
            st.db.execute("INSERT INTO births(id, version, sha, spec, seatable, registered_at, committed_at, received_at, "
                          "path, commit_sha, seq, line, why, by, night) VALUES(?, 1, ?, ?, 1, ?, ?, ?, 'docs/births/x', ?, "
                          "0, '{}', 'invented', 'captain', '2026-10-19')",
                          (sp["id"], BI.sha(sp), text, self.BORN_AT, self.BORN_AT, self.BORN_AT, "c" * 40))
            for day in days:
                for kind, t in (("open", "09:15"), ("close", "15:47")):
                    rid = st.start_receipt(f"decide-{kind}:{day}", now=TH.et(day, t))
                    st.finish_receipt(rid, "ok", {}, now=TH.et(day, t))
                st.set_meta(f"evl:backfill:{day}", "done")
            for day in days[:-1]:
                st.set_meta(TH.SC.equity_key(dt.date.fromisoformat(day)), repr(2000.0))
        self.lane = self.new_lane(redecide=True)
        self.at(TH.et("2026-10-27", "16:30"))
        tasks = []
        for _ in range(16):
            self.mark_recorded()
            tasks.append(self.turn().get("task"))
            self.clock.advance(5)
        own = [t for t in tasks if t == "decide-open-births"]
        self.assertEqual(len(own), 3, tasks)
        self.assertNotIn("decide-close-births", tasks, "an open-entry birth has no close decision of its own")
        for day in days[:3]:
            [row] = self.receipts(f"decide-open-births:{day}")
            self.assertEqual(row["status"], "ok")
            self.assertTrue(SN.names(row["summary"], "EVL-B-8K-502"), day)
            body = json.loads(row["summary"])
            self.assertEqual({k for k in body if k.startswith("EVL-")}, {"EVL-B-8K-502"}, "the birth alone")
        for day in days[3:]:
            self.assertEqual(self.receipts(f"decide-open-births:{day}"), [], "the hourly re-decision's reach")
            self.assertTrue(SN.names(self.receipts(f"decide-open:{day}")[-1]["summary"], "EVL-B-8K-502"))
        with self.store() as st:
            self.assertEqual(SN.births_made_without(st, dt.date(2026, 10, 27)), {})


# ======================================================================================================== the limit
class AnUnknownProgramTakesTheLimit(unittest.TestCase):
    def test_a_program_the_process_does_not_know_takes_the_limit_at_entry(self):
        uni = {"prev_close": 10.0}
        self.assertTrue(SC._above_limit({"program": "EVL-B-GONE", "version": 1}, uni, 12.6), "fail closed")
        self.assertFalse(SC._above_limit({"program": "EVL-B-GONE", "version": 1}, uni, 12.4))
        self.assertTrue(SC._above_limit({"program": "EVL-B-GONE", "version": 1}, {"prev_close": None}, 9.0))
        self.assertFalse(SC._above_limit({"program": "EVL-ERN-READ-O1", "version": 1}, uni, 99.0),
                         "PREREG-EVL-1's version 1 takes none, as before")
        self.assertTrue(SC._above_limit({"program": "EVL-ERN-READ-O1", "version": 2}, uni, 12.6))


# ======================================================================================================== the loader
class AReadErrorKeepsTheBirthsLastRead(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(unload)

    def test_a_read_error_keeps_the_same_stores_births_and_loads_none_for_another(self):
        a = TB.Synth(Path(self.tmp.name) / "a")
        self.addCleanup(a.st.close)
        a.register(spec("EVL-B-ERN-TOP", "ern", {"score_min": 3}, rank="score"), "2026-11-03T01:00:00Z")
        born = P.load_births(a.st)
        self.assertEqual([p.id for p in born], ["EVL-B-ERN-TOP", "EVL-B-ERN-TOP-CTRL"])
        lane = EB.Lane(Path(a.st.root) / S.DB_NAME)        # the book's read-only view of the same store
        self.addCleanup(lane.close)
        with mock.patch.object(BI, "registered_programs", side_effect=sqlite3.OperationalError("database is locked")):
            self.assertEqual(P.load_births(a.st), born, "the lane's thread keeps them")
            self.assertEqual(P.load_births(lane), born, "and so does the book's view of the same store")
            self.assertIn(("EVL-B-ERN-TOP", 1), P.BY_KEY)
            other = TB.Synth(Path(self.tmp.name) / "b")
            self.addCleanup(other.st.close)
            self.assertEqual(P.load_births(other.st), (), "a store never read loads none (fail closed)")
            self.assertEqual(P.PROGRAMS, P.PREREG_PROGRAMS)
            self.assertEqual(P.load_births(a.st), born, "a failed load of another store forgets nothing kept")
        self.assertEqual(P.load_births(a.st), born)
        P.load_births(None)
        with mock.patch.object(BI, "registered_programs", side_effect=sqlite3.OperationalError("x")):
            self.assertEqual(P.load_births(a.st), (), "an unload forgets them")
        self.assertEqual(P.PROGRAMS, P.PREREG_PROGRAMS)


if __name__ == "__main__":
    unittest.main()
