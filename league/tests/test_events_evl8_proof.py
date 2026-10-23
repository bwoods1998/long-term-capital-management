"""PREREG-EVL-8's PROOF AND ITS TESTS OF TIME (its sections 4.4, 1.2, 7.2 and 4.6; F10; the task's item 6), on the
invented week of league/tests/evl8_world.py (no figure here is a market's):

- every earlier program's shadow intents (PREREG-EVL-1 to -5's and R3's births') and every earlier seatable program's
  real-money picks are byte-identical with and without PREREG-EVL-8 (pinned, its morning passes, PX runs, meta-learners'
  parts and re-decisions made at their times), and so are the lane's eligibility, universe, bars and marks (PX never
  changes an earlier record, F10) and R3's births job's facts and its validator's Jaccards (section 4.4's exclusion);
- the House's own book plans every earlier row of an auction exactly as without this file, and this file's buys only
  after them, BY TIME, PX's learning room 4 (league/equity/live.py `_event_decide_8`, through the real book);
- THE MEMBERS RULE (section 7.2): fixed by stored times alone, the same `mrl_pool` rows live and in a catch-up a day
  later; a re-decision's late event, a cut part's rows and a mark stored after the lane's first finish are never read;
- section 1.2's TEST (i)-(v) and section 4.6's TEST (i)-(v), the House's timing;
- a look-ahead test plants a future bar and a future member outcome and shows both ignored;
- a meta-learner fed noise records picks noise."""

from __future__ import annotations

import datetime as dt
import json
import math
import random
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

from league.equity import live as L
from league.events import book as EB
from league.events import calendar as C
from league.events import house as H
from league.events import meta as MT
from league.events import programs as P
from league.events import px as PXL
from league.events import run as R
from league.events import store as S
from league.tests import evl5_world as W5
from league.tests import evl8_world as W
from league.tests import test_events_book as TB

et = W.et
D_DAY, N_DAY, P_DAY = W.D_DAY, W.N_DAY, W.P_DAY


def lane_tables(root: Path) -> dict[str, list]:
    with S.Store(root) as st:
        out = {}
        for table, order in (("eligibility", "day, cik, rule"), ("universe", "day, symbol"), ("bars", "symbol, day, adj"),
                             ("marks", "symbol, day, label")):
            cols = [r[1] for r in st.db.execute(f"PRAGMA table_info({table})")]
            keep = [c for c in cols if c not in ("decided_at", "fetched_at")]
            out[table] = [tuple(r) for r in st.db.execute(f"SELECT {', '.join(keep)} FROM {table} ORDER BY {order}")]
        return out


class TheWeekWithAndWithout(unittest.TestCase):
    """THE PROOF: the same invented week decided twice, PREREG-EVL-8 off (unpinned, none of its runs) and on."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.off = W.run_week(root / "off", eight=False)
        cls.on = W.run_week(root / "on", eight=True)
        cls.off_tables = lane_tables(root / "off")
        cls.on_tables = lane_tables(root / "on")
        with W.pinned():
            with S.Store(root / "on") as st:
                cls.mine = [dict(r) for r in st.db.execute(
                    "SELECT program, status, COUNT(*) AS n FROM intents GROUP BY program, status")]
                cls.receipts = [str(r[0]) for r in st.db.execute("SELECT job FROM receipts ORDER BY id")]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_earlier_programs_shadow_intents_are_byte_identical(self):
        off = [r for r in self.off["intents"] if not P.is_8(r[0])]
        on = [r for r in self.on["intents"] if not P.is_8(r[0])]
        self.assertTrue(off)
        self.assertEqual(off, on)
        self.assertEqual([r for r in self.off["intents"] if P.is_8(r[0])], [], "off: no intent of this file")

    def test_every_earlier_seatable_programs_real_money_picks_are_identical(self):
        self.assertTrue(any(self.off["picks"].values()), "the week trades")
        self.assertEqual(self.off["picks"], self.on["picks"])

    def test_births_facts_and_jaccards_are_identical(self):
        self.assertTrue(self.off["births"]["facts"], "the facts are read")
        self.assertEqual(self.off["births"], self.on["births"])
        self.assertNotIn("PX-DROP-ON", json.dumps(self.on["births"]), "births never read a row of this file")

    def test_px_never_changes_an_earlier_record(self):
        for table in ("eligibility", "universe", "bars", "marks"):
            self.assertEqual(self.off_tables[table], self.on_tables[table], table)

    def test_and_this_files_rows_were_decided(self):
        programs = {r["program"] for r in self.mine}
        self.assertTrue({"PX-DROP-ON", "PX-SURGE-ON", "PX-GAP-O1", "CTRL-PX-ALL-ON", "CTRL-PX-ALL-O1"} <= programs,
                        programs)
        for job in ("decide-close-px8:2026-10-27", "decide-open-px8:2026-10-27", "decide-open-meta8:2026-10-27",
                    "decide-close-meta8:2026-10-27", "decide-close-px8:2026-10-28"):
            self.assertIn(job, self.receipts)
        removed = [r for r in self.mine if r["status"] == PXL.WHY_REMOVED]
        self.assertTrue(removed, "PXB's article stored after D's decision: the re-decision removed it")


def learners_failed(h, auction: str) -> None:
    """PREREG-EVL-7's learners of the auction (pinned in the tree) with their own live receipts FINISHED and naming none
    of them (league/events/learner.py `live_state` "not_named": section 4.6, "a part the receipt does not name has
    failed"), so their pass of the auction plans nothing and this file's pass may follow it."""
    from league.events import learner as LR

    at = dt.datetime(2026, 11, 4, 20, 47, 30, tzinfo=dt.timezone.utc)
    for prog in P.learners():
        if (prog.entry_at == "close") == (auction == "on"):
            rid = h.lane.st.start_receipt(LR.live_job(prog, TB.DAY), now=at)
            h.lane.st.finish_receipt(rid, "failed", {"error": "invented"}, now=at)


def seat(program: str) -> P.Program:
    """The SEATING version of an earlier program in the tree as it stands (PREREG-EVL-6's version 3 of the nine)."""
    return next(p for p in P.SEATING if p.id == program)


class TheBookWithAndWithout(TB.EventTest):
    """THE HOUSE'S OWN BOOK (league/equity/live.py, the real `size_entry`): an earlier close-entry row and PX-DROP-ON at
    the same close. The earlier row's buys are planned and sized exactly as without this file; PX's in its own late pass
    after them, at most its learning room 4, never a name the earlier row was given."""

    def seed(self, h, *, eight: bool) -> None:
        # EVL-ERN-REACT-ON (version 2, a close entry): an earnings 8-K and its reaction
        prog = seat("EVL-ERN-REACT-ON")
        h.lane.filing("a-1", TB.CIK, accepted=TB.iso(TB.DAY, 11, 0), received=TB.iso(TB.DAY, 11, 1))
        h.lane.universe(TB.DAY, "ACME", TB.CIK, 16.0)
        h.lane.intent(prog, "8k:a-1", "ACME", TB.CIK, TB.DAY, TB.NEXT)
        h.lane.st.db.execute("INSERT INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES('ACME', ?, 'raw', 16, "
                             "16, 16, 16.0, 1e6, 'x')", (TB.PRIOR.isoformat(),))
        h.lane.st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES('ACME', ?, '1530', "
                             "16.8, 'x', 'sip-1min', 'x')", (TB.DAY.isoformat(),))
        h.symbol("ACME", last=16.0)
        if not eight:
            return
        px = PXL.open_px(h.lane.st.root)
        try:
            run = "decide-close-px8:invented"
            for n, sym in enumerate(("ACME", "PXA", "PXB", "PXC", "PXD", "PXE"), 1):
                cik = TB.CIK if sym == "ACME" else W.PX_CIK[sym]
                px.put_result(TB.DAY, cik, S.LIVE_RULE, {"symbol": sym, "name": sym, "exchange": "NASDAQ",
                                                          "prev_close": 16.0, "adv20": 4e7, "adv20sh": 2e6,
                                                          "bench": "IWM", "adjusted61": 61, "inputs_at": "x"},
                              why=None, run="u", now=dt.datetime(2026, 11, 4, 12, tzinfo=dt.timezone.utc))
                event = f"px:PX-DROP-ON:{TB.DAY}:{cik}"
                px.db.execute("INSERT INTO px_decisions(run, auction, day, program, rank, event, cik, symbol, rank_key, "
                              "adv20, prev_close) VALUES(?, 'on', ?, 'PX-DROP-ON', ?, ?, ?, ?, ?, 4e7, 16.0)",
                              (run, TB.DAY.isoformat(), n, event, cik, sym, 10.0 - n))
                h.lane.intent(P.BY_KEY[("PX-DROP-ON", 1)], event, sym, cik, TB.DAY, TB.NEXT)
                if sym != "ACME":
                    h.symbol(sym, last=16.0)
            px.db.execute("INSERT INTO px_meta(key, value) VALUES(?, ?)",
                          (PXL.DECIDED_KEY.format(auction="on", day=TB.DAY.isoformat()),
                           json.dumps({"run": run, "kind": "live", "receipt": 1, "at": "x"})))
        finally:
            px.close()

    def run_day(self, *, eight: bool):
        ctx = W.pinned() if eight else mock.patch.object(P, "REGISTERED_AT_8", None)
        with ctx:
            root = self.root / ("on" if eight else "off")
            root.mkdir()
            h = TB.Harness(root)
            self.addCleanup(h.state.close)
            self.addCleanup(h.lane.st.close)
            self.addCleanup(lambda: h.book._event_lane is not None and h.book._event_lane.close())
            self.seed(h, eight=eight)
            learners_failed(h, "on")
            self.ready(h)
            h.day(upto=(15, 48))
            return h, [dict(r) for r in h.event_intents("buy")]

    def test_the_earlier_rows_buys_identical_and_px_after_them(self):
        _, off = self.run_day(eight=False)
        h, on = self.run_day(eight=True)
        earlier = [r for r in on if not P.is_8(r["program"])]
        self.assertEqual({r["symbol"] for r in off}, {"ACME"}, "the earlier rows buy ACME at the close")
        keep = ("program", "version", "event", "symbol", "band", "tif", "limit_px", "rank_key", "target_usd", "status")
        self.assertEqual([{k: r[k] for k in keep} for r in off], [{k: r[k] for k in keep} for r in earlier])
        mine = [r for r in on if P.is_8(r["program"])]
        self.assertEqual([r["symbol"] for r in mine], ["PXA", "PXB", "PXC", "PXD"],
                         "ACME was given to the earlier row; the learning room is 4")
        self.assertTrue(all(int(m["iid"]) > max(int(r["iid"]) for r in earlier) for m in mine), "planned after them")
        rows = {r["at"]: r for r in h.state.rows("SELECT * FROM eq_event_decisions WHERE day=?", (TB.DAY.isoformat(),))}
        self.assertIn("close-px8", rows)
        self.assertEqual(json.loads(rows["close-px8"]["summary"])["programs"]["PX-DROP-ON"]["room"], 4)
        sent = [b["symbol"] for b in h.bodies() if b["side"] == "buy" and b["time_in_force"] == "cls"]
        if sent:
            self.assertEqual(sent[0], "ACME", "the earlier row's buy is sent first")


class TheLookAhead(unittest.TestCase):
    """Section 1.2: nothing read after tau. A future bar in the vendor's answer and a future member outcome are planted:
    both are ignored."""

    def setUp(self):
        ctx = W.pinned()
        ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def decide(self, name: str, plant: bool) -> tuple[dict, list]:
        w = W.World8(Path(self.tmp.name) / name)
        try:
            w.st.set_meta("equity:2026-10-26", "1900")
            w.at(et(D_DAY, 9, 5)).morning(D_DAY)
            real = W.Gateway8._minutes

            def planted(gw, symbols, start, end):
                out = real(gw, symbols, start, end)
                if plant:
                    for s in symbols:
                        out[s].append({"t": S.iso(end + dt.timedelta(minutes=1)), "o": 1.0, "h": 1.0, "l": 1.0,
                                       "c": 1.0, "v": 9e9})
                return out
            with mock.patch.object(W.Gateway8, "_minutes", planted):
                w.at(et(D_DAY, 15, 46, 5)).px_decide(D_DAY, "on")
            if plant:      # a future member outcome: an outcome of a source event of D settled after the state time
                w.st.db.execute("INSERT INTO outcomes(program, version, event, entry_px, exit_px, bench, bench_entry, "
                                "bench_exit, cost_entry_bp, cost_exit_bp, r, b, a, tradable, settled_at, status) SELECT "
                                "program, version, event, 20, 30, 'SPY', 1, 1, 7, 7, 0.5, 0, 0.5, 1, ?, 'settled' FROM "
                                "intents WHERE program='CTRL-PX-ALL-ON'", (S.iso(et(D_DAY, 15, 40)),))
            w.at(et(D_DAY, 15, 47)).decide("close", D_DAY)
            w.at(et(D_DAY, 15, 48, 10)).meta_decide(D_DAY, "on")
            px = w.px()
            try:
                values = {c: {k: v.get(k) for k in ("x", "zd", "move_d", "vd")}
                          for c, v in PXL.features(px.db, D_DAY, "on").items()}
            finally:
                px.close()
            state = [tuple(r) for r in w.st.db.execute("SELECT rule_h, a, g, nb FROM mrl_stats ORDER BY rule_h")]
            mine = [tuple(r) for r in w.st.db.execute("SELECT program, event, status, rank_key FROM intents WHERE "
                                                      "program LIKE 'PX-%' OR program LIKE 'EVL-META%' ORDER BY 1, 2")]
            return values, state + mine
        finally:
            w.close()

    def test_a_future_bar_and_a_future_member_outcome_are_ignored(self):
        clean = self.decide("clean", False)
        planted = self.decide("planted", True)
        self.assertEqual(clean[0], planted[0], "a bar after the value's knowable time is never read")
        self.assertEqual(clean[1], planted[1], "an outcome settled after the state time is never in the state")

    def test_the_state_reads_only_outcomes_settled_before_sigma(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = S.Store(Path(tmp) / "lane")
            try:
                MT.ensure(st)
                st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                              "exit_day, exit_at, rank_key, mode, status, why) VALUES('EVL-CTRL-NEWS-ALL-O1', 1, 'news:1', "
                              "'S', '1', 'x', '2026-10-26', 'open', '2026-10-26', 'close', NULL, 'shadow', 'exited', NULL)")
                st.db.execute("INSERT INTO outcomes(program, version, event, entry_px, exit_px, bench, bench_entry, "
                              "bench_exit, cost_entry_bp, cost_exit_bp, r, b, a, tradable, settled_at, status) VALUES("
                              "'EVL-CTRL-NEWS-ALL-O1', 1, 'news:1', 20, 21, 'SPY', 1, 1, 7, 7, 0.05, 0, 0.05, 1, "
                              "'2026-10-27T13:30:00Z', 'settled')")
                st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES('S', '2026-10-26', "
                              "'open', 20, 't', 'sip', 'x')")
                st.db.execute("INSERT INTO universe(day, symbol, cik, name, exchange, prev_close, adv20, bench, sigma60) "
                              "VALUES('2026-10-26', 'S', '1', 'n', 'NASDAQ', 20, 1e8, 'SPY', NULL)")
                before = S.parse_iso("2026-10-27T13:00:00Z")
                after = S.parse_iso("2026-10-27T14:00:00Z")
                day = dt.date(2026, 10, 26)
                tags = ["EVL-CTRL-NEWS-ALL-O1:1"]
                self.assertEqual(MT.member_outcome(st, "1", day, "o1", tags, before)["status"], "pending")
                got = MT.member_outcome(st, "1", day, "o1", tags, after)
                self.assertEqual((got["status"], got["event"]), ("settled", "news:1"),
                                 "the first tag's intent OF THE ISSUER at the member's auctions")
                self.assertEqual(MT.member_outcome(st, "1", day, "on", tags, after)["status"], "terminal",
                                 "another auction's intent is not the member's")
                st.db.execute("UPDATE marks SET px=26 WHERE symbol='S'")
                self.assertEqual(MT.member_outcome(st, "1", day, "o1", tags, after),
                                 {"status": "terminal", "why": "limit at entry"},
                                 "F9: an entry printed above 1.25 x the previous close is no outcome")
            finally:
                st.close()


class TheNoise(unittest.TestCase):
    """A meta-learner fed noise records picks noise: with no sub-rule's edge, few sub-rules ever qualify (Z = 3, a prior
    of 30 bp, the cost hurdle), and what it picks earns what the pool earns."""

    def test_noise_in_noise_out(self):
        rng = random.Random(20261022)
        gof = MT.group_of(MT.GROUPS_ON)
        cost = 0.0014
        pool = [MT.features({"fam": rng.choice(["news-on", "news-day", "8k", "ern", "price"]),
                             "score": rng.choice([None, -1, 0, 1, 2, 3]), "hour_et": (rng.randrange(24), 0),
                             "cov72": rng.randrange(6), "adv20": rng.choice([5e6, 5e7, 5e8]),
                             "prev_close": rng.choice([5.0, 20.0, 80.0]), "react": rng.uniform(0.9, 1.1),
                             "gap": rng.uniform(0.95, 1.05)}, "on") for _ in range(300)]
        rules = [MT.rules_of(f, [], gof) for f in pool]
        sessions, picked, outcomes, days_with = [], 0, [], 0
        for day in range(60):
            if len(sessions) > MT.WARM:
                st = MT.state(sessions)
                today = [{"event": f"{day}:{i}", "cik": str(i), "adv20": 1e6 * (i + 1), "rules": rules[i],
                          "eligible": True, "cost_rt": cost} for i in range(len(pool))]
                picks = MT.walk(today, st, MT.cbar_of(today), session_index=len(sessions))
                days_with += bool(picks)
                picked += len(picks)
                a_today = [rng.gauss(-cost, 0.03) for _ in pool]
                outcomes += [a_today[int(e.split(":")[1])] - (math.fsum(a_today) / len(a_today)) for e, _, _ in picks]
            else:
                a_today = [rng.gauss(-cost, 0.03) for _ in pool]
            sessions.append(MT.session_stats([{"rules": r, "a": a, "tradable": True} for r, a in zip(rules, a_today)]))
        share = days_with / (60 - MT.WARM - 1)
        self.assertLess(share, 0.15, f"a noise pool qualifies a sub-rule on {share:.0%} of the sessions")
        if outcomes:
            mean = math.fsum(outcomes) / len(outcomes)
            se = 0.03 / math.sqrt(len(outcomes))
            self.assertLess(abs(mean), 4 * se, "its picks earn what the pool earns")


class Eight(unittest.TestCase):
    """A pinned world (the PX store seeded, the equity of P), its own temporary root."""

    def setUp(self):
        ctx = W.pinned()
        ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def world(self, name: str = "lane", *, rows: bool = True) -> W.World8:
        w = W.World8(Path(self.tmp.name) / name)
        self.addCleanup(w.close)
        for day in ("2026-10-26", "2026-10-27"):
            w.st.set_meta(f"equity:{day}", "1900")
        if rows:
            w.births()
            W5.evl4_rows(w)
            W5.evl5_rows(w)
        return w

    @staticmethod
    def pool(w: W.World8, program: str, day: dt.date = D_DAY) -> list[tuple]:
        if not MT.has_tables(w.st.db):
            return []
        return [tuple(r) for r in w.st.db.execute(
            "SELECT cik, symbol, event, knowable_at, tags, features, xrules, eligible, adv20, prev_close, cost_rt FROM "
            "mrl_pool WHERE program=? AND day=? ORDER BY cik", (program, day.isoformat()))]

    @staticmethod
    def tags(rows: list[tuple]) -> set[str]:
        return {t.rsplit(":", 1)[0] for r in rows for t in json.loads(r[4])}


def the_open(w: W.World8, day: dt.date = D_DAY, *, meta: bool = True) -> None:
    """D's open as the House runs it: the morning pass at 09:05, the lane's live open decision at 09:15:30, then the open
    run on its receipt (PX-GAP-O1's part, then EVL-META-O1's unless `meta` is False)."""
    w.at(et(P_DAY, 15, 47)).decide("close", P_DAY)
    w.at(et(day, 9, 5)).morning(day)
    w.at(et(day, 9, 15, 30)).decide("open", day)
    w.at(et(day, 9, 16)).px_decide(day, "o1")
    if meta:
        w.at(et(day, 9, 16, 20)).meta_decide(day, "o1")
    w.ran("open", day)


def the_close(w: W.World8, day: dt.date = D_DAY, *, meta: bool = True, px: bool = True) -> None:
    """D's close as the House runs it: PX-DROP-ON's and PX-SURGE-ON's run at 15:46:05 (unless `px` is False), the
    lane's live close decision at 15:47, EVL-META-ON's part on its receipt (unless `meta` is False)."""
    if px:
        w.at(et(day, 15, 46, 5)).px_decide(day, "on")
    w.at(et(day, 15, 47)).decide("close", day)
    if meta:
        w.at(et(day, 15, 48, 10)).meta_decide(day, "on")
        w.ran("close-meta", day)


class TheMembersRule(Eight):
    """SECTION 7.2's MEMBERS RULE, FIXED BY STORED TIMES ALONE, and its TEST."""

    def test_a_px_gap_pick_is_a_member_live_and_in_a_catch_up_alike(self):
        live = self.world("live")
        the_open(live)
        later = self.world("later")
        the_open(later, meta=False)
        later.at(et(N_DAY, 20, 0)).meta_decide(D_DAY, "o1", kind="catchup")
        px = live.px()
        try:
            chosen = {str(r["cik"]) for r in PXL.live_selections(px.db, D_DAY, "o1").get("PX-GAP-O1", [])}
        finally:
            px.close()
        self.assertTrue(chosen, "PX-GAP-O1 picks at D's open")
        rows = self.pool(live, "EVL-META-O1")
        self.assertTrue(chosen <= {r[0] for r in rows if "PX-GAP-O1:1" in json.loads(r[4])})
        self.assertEqual(rows, self.pool(later, "EVL-META-O1"), "a catch-up a day later writes the same mrl_pool rows")
        self.assertEqual(MT.decided(later.st.db, MT.learner("o1"), D_DAY)["kind"], "catchup")
        self.assertIn(f"decide-meta:open:{D_DAY}", [str(r[0]) for r in later.st.db.execute("SELECT job FROM receipts")])

    def test_an_event_stored_after_tau_that_the_re_decision_adds_is_a_member_of_neither(self):
        def week(name: str, *, catchup: bool) -> W.World8:
            w = self.world(name)
            w.article("n-jjj-late", "JJJ", knowable=et(D_DAY, 8, 0), stored=et(D_DAY, 9, 40))
            the_open(w, meta=not catchup)
            w.at(et(D_DAY, 10, 0)).decide("open", D_DAY, live=False)     # (the hourly re-decision)
            if catchup:
                w.at(et(N_DAY, 20, 0)).meta_decide(D_DAY, "o1", kind="catchup")
            return w
        live, later = week("live", catchup=False), week("later", catchup=True)
        jjj = str(W5.TICKERS.index("JJJ") + 1).zfill(10) if hasattr(W5, "TICKERS") else None
        added = [r for r in live.st.db.execute("SELECT program FROM intents WHERE event='news:n-jjj-late'")]
        self.assertTrue(added, "the re-decision took the late article into the shadow")
        for w in (live, later):
            events = {r[2] for r in self.pool(w, "EVL-META-O1")}
            self.assertNotIn("news:n-jjj-late", events)
            if jjj is not None:
                self.assertNotIn(jjj, {r[0] for r in self.pool(w, "EVL-META-O1")})
        self.assertEqual(self.pool(live, "EVL-META-O1"), self.pool(later, "EVL-META-O1"))

    def test_a_cut_evl5_part_gives_no_member_live_or_after_its_own_decision(self):
        five = {p.id for p in R.five_programs()}
        self.assertTrue(five, "PREREG-EVL-5 has programs on this tree")
        whole = self.world("whole")
        the_open(whole)
        the_close(whole)
        self.assertTrue(five & self.tags(self.pool(whole, "EVL-META-ON")), "named: PREREG-EVL-5's rows give members")

        def cut(name: str, *, catchup: bool) -> W.World8:
            w = self.world(name)
            the_open(w)
            w.at(et(D_DAY, 15, 46, 5)).px_decide(D_DAY, "on")
            with mock.patch.object(R, "part_until", lambda ctx, budget: -1.0):
                w.at(et(D_DAY, 15, 47)).decide("close", D_DAY)
            got = json.loads(w.st.db.execute("SELECT summary FROM receipts WHERE job=?",
                                             (f"decide-close:{D_DAY}",)).fetchone()[0])
            self.assertIn("evl5_error", got, "PREREG-EVL-5's part was cut")
            if catchup:
                w.at(et(D_DAY, 16, 0))
                R.decide_close(w.ctx, D_DAY, backfill_run=True, evl5_only=True)
                w.at(et(N_DAY, 20, 0)).meta_decide(D_DAY, "on", kind="catchup")
            else:
                w.at(et(D_DAY, 15, 48, 10)).meta_decide(D_DAY, "on")
            return w
        live, later = cut("live", catchup=False), cut("later", catchup=True)
        self.assertIn(f"decide-close-evl5:{D_DAY}", [str(r[0]) for r in later.st.db.execute("SELECT job FROM receipts")])
        for w in (live, later):
            rows = self.pool(w, "EVL-META-ON")
            self.assertTrue(rows)
            self.assertFalse(five & self.tags(rows), "no PREREG-EVL-5 row gives a member")
        self.assertEqual(self.pool(live, "EVL-META-ON"), self.pool(later, "EVL-META-ON"))

    def test_the_marks_and_the_eligibility_cut(self):
        w = self.world("marks", rows=False)
        w.at(et(P_DAY, 15, 47)).decide("close", P_DAY)
        w.at(et(D_DAY, 15, 47)).decide("close", D_DAY)
        st = w.st
        first = MT.first_decision(st, D_DAY, "on")
        finish = S.parse_iso(first["finished_at"])
        s = C.session(st, D_DAY)
        tau = s.close_decide
        rows = [("MA", "1530", S.iso(et(D_DAY, 15, 29)), finish), ("MB", "1530", S.iso(et(D_DAY, 15, 29)),
                                                                    finish + dt.timedelta(seconds=1)),
                ("MC", "0930", S.iso(et(D_DAY, 9, 30)), finish - dt.timedelta(minutes=5)),
                ("MD", "1530", S.iso(et(D_DAY, 15, 45)), finish - dt.timedelta(seconds=1))]
        for sym, label, t, fetched in rows:
            st.db.execute("INSERT OR REPLACE INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES(?, ?, ?, 10, ?, "
                          "'sip', ?)", (sym, D_DAY.isoformat(), label, t, S.iso(fetched)))
        for cik, sym, at in (("901", "MA", finish), ("902", "MB", finish + dt.timedelta(seconds=1))):
            st.db.execute("INSERT INTO universe(day, symbol, cik, name, exchange, prev_close, adv20, bench, sigma60) VALUES("
                          "?, ?, ?, 'n', 'NASDAQ', 10, 1e8, 'SPY', NULL)", (D_DAY.isoformat(), sym, cik))
            st.db.execute("INSERT INTO eligibility(day, cik, rule, eligible, symbol, decided_at) VALUES(?, ?, 'live', 1, ?, "
                          "?)", (D_DAY.isoformat(), cik, sym, S.iso(at)))
        view = MT.AsOf(st, s, "on", tau, finish)
        try:
            self.assertEqual(view.mark("MA", "1530"), 10.0, "stored at the lane's first finish: read")
            self.assertIsNone(view.mark("MB", "1530"), "stored after it: missing")
            self.assertEqual(view.mark("MC", "0930"), 10.0)
            self.assertIsNone(view.mark("MD", "1530"), "a bar that does not end before tau: missing")
            uni = EB.universe_rows(view, D_DAY)
            self.assertIn("901", uni)
            self.assertNotIn("902", uni, "ELIGIBLE TO PICK: a live result decided after the first finish is not")
            self.assertEqual(view.eligible_by, min(finish, s.close_at))
        finally:
            view.close()
        self.assertEqual(st.db.execute("SELECT COUNT(*) FROM marks WHERE symbol='MB'").fetchone()[0], 1,
                         "the lane's own marks are untouched (the view's table is its connection's own)")
        early = MT.AsOf(st, s, "o1", s.open_decide, et(D_DAY, 9, 40))
        try:
            self.assertEqual(early.eligible_by, s.open_at, "never later than the entry auction (09:30 for O1)")
        finally:
            early.close()


class TheClockTest(Eight):
    """SECTION 1.2's TEST (ii)-(iv) on the House's runs (league/tests/test_events_evl8.py `TheClock` holds (i), (iii)'s
    PX reads and the re-decision of (v))."""

    def test_ii_meta_on_reads_the_live_px_runs_selections_and_rows_live_and_in_a_catch_up(self):
        live = self.world("live")
        the_open(live)
        the_close(live)
        later = self.world("later")
        the_open(later)
        the_close(later, meta=False)
        px = later.px()
        try:          # (another run's row of D: never read by the meta-learner)
            px.db.execute("INSERT OR IGNORE INTO px_features(day, cik, kind, symbol, value, decided_at, inputs_at, source, "
                          "run, as_of, bar_end) VALUES(?, '0000009999', 'on@c', 'ZZZ', '{\"zd\": -9}', 'x', 'x', 'live', "
                          "'other', 'x', 'x')", (D_DAY.isoformat(),))
        finally:
            px.close()
        later.at(et(N_DAY, 20, 0)).meta_decide(D_DAY, "on", kind="catchup")
        px = live.px()
        try:
            chosen = PXL.live_selections(px.db, D_DAY, "on")
        finally:
            px.close()
        rows = self.pool(live, "EVL-META-ON")
        by = {r[0]: json.loads(r[4]) for r in rows}
        for pid in ("PX-DROP-ON", "CTRL-PX-ALL-ON"):
            self.assertTrue(chosen.get(pid), pid)
            for r in chosen[pid]:
                self.assertIn(f"{pid}:1", by.get(str(r["cik"]), []), (pid, r["cik"]))
        self.assertTrue(any(json.loads(r[6]) for r in rows), "x: experts read the live run's px_features rows")
        self.assertEqual(rows, self.pool(later, "EVL-META-ON"), "the same mrl_pool rows, live and in a catch-up")

    def test_iv_a_cut_px_run_gives_no_buy_no_judged_block_and_no_meta_member(self):
        def week(name: str, *, catchup: bool) -> W.World8:
            w = self.world(name)
            the_open(w)
            w.at(et(D_DAY, 15, 46, 5)).px_decide(D_DAY, "on", late=lambda: True)
            w.at(et(D_DAY, 15, 47)).decide("close", D_DAY)
            if catchup:
                w.at(et(N_DAY, 20, 0)).px_decide(D_DAY, "on", kind="catchup")
                w.at(et(N_DAY, 20, 5)).meta_decide(D_DAY, "on", kind="catchup")
            else:
                w.at(et(D_DAY, 15, 48, 10)).meta_decide(D_DAY, "on")
            return w
        live, later = week("live", catchup=False), week("later", catchup=True)
        lane = EB.Lane(later.st.root / S.DB_NAME)
        try:
            prog = P.BY_KEY[("PX-DROP-ON", 1)]
            self.assertEqual(EB.picks(lane, prog, D_DAY, decided_at=C.session(lane, D_DAY).close_decide), [],
                             "PX-DROP-ON buys nothing at D's close")
        finally:
            lane.close()
        px = later.px()
        try:
            self.assertEqual(PXL.decided(px.db, D_DAY, "on")["kind"], "catchup")
            self.assertNotIn(D_DAY.isoformat(), PXL.judged_days(px.db, "on"), "its catch-up is never a judged block")
        finally:
            px.close()
        for w in (live, later):
            rows = self.pool(w, "EVL-META-ON")
            self.assertFalse({t for t in self.tags(rows) if P.is_px8(t)}, "no PX selection is a member")
            self.assertFalse(any(json.loads(r[6]) for r in rows), "every x: sub-rule is empty")
        self.assertEqual(self.pool(live, "EVL-META-ON"), self.pool(later, "EVL-META-ON"))


class Clock:
    """One clock for the House's wall time and its monotonic time (a read that hangs moves both)."""

    def __init__(self, at: dt.datetime):
        self.at = at.timestamp()

    def clock(self) -> float:
        return self.at

    def __call__(self) -> float:
        return self.at

    def advance(self, s: float) -> None:
        self.at += float(s)


class Hanging:
    """A gateway client whose PX reads hang until their timeout (`timeout` the client's, as gw.Gateway's), the first
    `slow` of them returning after `slow_s` seconds instead (the invented answers of `inner`)."""

    def __init__(self, inner, clock: Clock, *, slow: int = 0, slow_s: float = 0.0):
        self.inner, self.clock, self.timeout = inner, clock, 45.0
        self.seen = {"reads": 0, "timeouts": []}
        self.slow, self.slow_s = slow, slow_s

    def get_json(self, path, params=None):
        if not path.endswith("/v2/stocks/bars"):
            return self.inner.get_json(path, params)
        self.seen["reads"] += 1
        if self.seen["reads"] <= self.slow:
            self.clock.advance(self.slow_s)
            return self.inner.get_json(path, params)
        self.seen["timeouts"].append(self.timeout)
        self.clock.advance(self.timeout)
        raise TimeoutError("the read hung until its timeout")


class TheHouseTiming(Eight):
    """SECTION 4.6's TIMING on the House's lane and its TEST (i)-(iv) ((v) is the book's, `TheLatePasses`): the PX
    close run from tau, its reads' timeouts capped at tau + 50 s and its end by tau + 55 s; the record and verdict tasks
    inside the lead bounded to tau; PREREG-EVL-5's pre-pass first; the lowest-priority tasks yield; the morning pass
    until 15:30; the pre-passes' windows; EVL-META-ON on the lane's close receipt, never past the close - 11:20."""

    def lane(self, w: W.World8, at: dt.datetime, gateway=None) -> tuple[H.EventLane, Clock]:
        clock = Clock(at)
        lane = H.EventLane(clock, w.st.root, gateway=gateway or w.gw, sec=W.sec8, settings={"px_data": True},
                           monotonic=clock, sleep=clock.advance)
        lane.throttle = lambda: None
        return lane, clock

    @staticmethod
    def ctx(lane: H.EventLane, w: W.World8) -> H.LaneContext:
        return H.LaneContext(lane, w.st, H.LaneGateway(w.gw, lane, None, cut=False), W.sec8, lane.now)

    def test_i_a_hanging_gateway_ends_the_px_close_run_by_tau_plus_55(self):
        for slow, slow_s in ((0, 0.0), (1, 44.0)):
            w = self.world(f"hang{slow}", rows=False)
            w.at(et(D_DAY, 9, 5)).morning(D_DAY)
            s = C.session(w.st, D_DAY)
            tau = s.close_decide
            lane, clock = self.lane(w, tau)
            stub = Hanging(w.gw, clock, slow=slow, slow_s=slow_s)
            lane._gateway = stub
            task = lane._eight_close_due(w.st, lane.now(), D_DAY, s, [])
            self.assertEqual(task.name, "px8-close")
            got = lane._eight_close_run(self.ctx(lane, w), D_DAY)
            self.assertNotEqual(got["_status"], "ok")
            self.assertLessEqual(lane.now(), tau + dt.timedelta(seconds=55), "ended unfinished by 15:46:55")
            self.assertTrue(stub.seen["timeouts"])
            self.assertLessEqual(max(stub.seen["timeouts"]), 45.0)
            if slow:
                self.assertAlmostEqual(stub.seen["timeouts"][0], 6.0, places=3,
                                       msg="a read sent at tau + 44 s waits min(45 s, tau + 50 s - now)")
            px = w.px()
            try:
                self.assertIsNone(PXL.decided(px.db, D_DAY, "on"))
                self.assertEqual(px.db.execute("SELECT COUNT(*) FROM px_features WHERE day=? AND kind='on'",
                                               (D_DAY.isoformat(),)).fetchone()[0], 0, "no row written")
            finally:
                px.close()
            self.assertIsNone(lane._eight_close_due(w.st, tau + dt.timedelta(seconds=45), D_DAY, s, []),
                              "no read sent after tau + 45 s")
            clock.at = (tau + dt.timedelta(seconds=60)).timestamp()
            task, _ = lane._plan(w.st, lane.now())
            self.assertEqual(getattr(task, "name", None), "decide-close", "the lane's live close run at 15:47:00")

    def test_ii_a_record_pass_waits_for_the_px_close_run_and_one_inside_the_lead_ends_by_tau(self):
        w = self.world(rows=False)
        w.at(et(D_DAY, 9, 5)).morning(D_DAY)
        s = C.session(w.st, D_DAY)
        tau = s.close_decide
        lane, clock = self.lane(w, tau + dt.timedelta(seconds=10))
        task, _ = lane._plan(w.st, lane.now())
        self.assertEqual(task.name, "px8-close", "a record pass due at 15:46:10 starts only after it")
        clock.at = (tau - dt.timedelta(seconds=10)).timestamp()
        record = H.Task("record", lambda ctx, deadline: {}, H.RECORD_BUDGET)
        self.assertAlmostEqual(lane._deadline(w.st, lane.now(), record) - clock(), 10.0, places=3,
                               msg="a record pass started at 15:45:50 ends by 15:46:00")
        verdicts = H.Task("verdicts", lambda ctx, deadline: {}, H.VERDICT_BUDGET, cut=True)
        self.assertAlmostEqual(lane._deadline(w.st, lane.now(), verdicts) - clock(), 10.0, places=3)
        pre = H.Task("verdicts", lambda ctx, deadline: {}, H.VERDICT_BUDGET, cut=True, pre=True)
        self.assertGreater(lane._deadline(w.st, lane.now(), pre) - clock(), 10.0, "PREREG-EVL-5's pre-pass keeps its own")
        clock.at = (tau - dt.timedelta(seconds=200)).timestamp()
        self.assertAlmostEqual(lane._deadline(w.st, lane.now(), record) - clock(), H.RECORD_BUDGET, places=3,
                               msg="before the lead: as before")
        with mock.patch.object(P, "REGISTERED_AT_8", None):
            P.refresh_8()
            try:
                clock.at = (tau - dt.timedelta(seconds=10)).timestamp()
                self.assertIsNone(lane._eight_lead_tau(w.st, lane.now()), "nothing while unpinned")
            finally:
                pass
        P.refresh_8()

    def test_iii_prereg_evl5s_pre_pass_runs_first_while_its_key_is_not_stored(self):
        w = self.world(rows=False)
        w.at(et(D_DAY, 9, 5)).morning(D_DAY)
        s = C.session(w.st, D_DAY)
        lane, _ = self.lane(w, s.close_decide)
        self.assertTrue(R.five_programs())
        rid = w.st.start_receipt("record", now=s.close_decide - dt.timedelta(seconds=30))     # (a record pass just ran)
        w.st.finish_receipt(rid, "ok", {}, now=s.close_decide - dt.timedelta(seconds=20))
        with mock.patch.object(lane, "_verdict_targets", lambda *a, **k: (("close", D_DAY, True), None)):
            task, _ = lane._plan(w.st, lane.now())
            self.assertEqual((task.name, task.pre), ("verdicts", True))
            w.st.set_meta(f"{R.PRE_KEY}{D_DAY.isoformat()}", json.dumps({"cut": "x"}))
            task, _ = lane._plan(w.st, lane.now())
            self.assertEqual(task.name, "px8-close")

    def test_iv_the_morning_pass_and_the_pre_pass_yield(self):
        w = self.world(rows=False)
        s = C.session(w.st, D_DAY)
        lane, clock = self.lane(w, et(D_DAY, 9, 6))
        due = H.Task("verdicts", lambda ctx, deadline: {}, H.VERDICT_BUDGET, cut=True)
        mine = H.Task("px8-am", lambda ctx, deadline: {}, 60.0)
        with mock.patch.object(lane, "_plan", lambda st, now: (due, now)):
            self.assertTrue(lane._eight_yield(w.st, "px8-am"))
        with mock.patch.object(lane, "_plan", lambda st, now: (mine, now)):
            self.assertFalse(lane._eight_yield(w.st, "px8-am"))
        reads = len(w.gw.px_gets)
        px = w.px()
        try:
            got = PXL.morning(px, w.st, w.gw, D_DAY, now=et(D_DAY, 9, 6), run="am", late=lambda: len(w.gw.px_gets) > reads)
            self.assertIn(got.get("_status"), ("partial", None))
            self.assertIsNone(PXL._meta(px.db, PXL.AM_KEY.format(day=D_DAY.isoformat())), "stopped before its next read")
            self.assertEqual(px.db.execute("SELECT COUNT(*) FROM px_am").fetchone()[0], 0, "PXU(D) is written whole")
            got = PXL.morning(px, w.st, w.gw, D_DAY, now=et(D_DAY, 9, 8), run="am2", clock=lambda: et(D_DAY, 9, 8, 30))
            self.assertGreater(got["pxu"], 0)
            self.assertEqual(json.loads(PXL._meta(px.db, PXL.AM_KEY.format(day=D_DAY.isoformat())))["serves"], "both")
        finally:
            px.close()
        MT.ensure(w.st)
        prog = MT.learner("o1")
        w.st.db.execute("INSERT INTO mrl_pool(program, version, day, cik, symbol, event, knowable_at, tags, features, xrules, "
                        "eligible, adv20, prev_close, cost_rt) VALUES(?, 1, '2026-10-26', '1', 'S', 'news:1', NULL, '[]', "
                        "'[]', '[]', 1, 1e8, 20, 0.001)", (prog.id,))
        clock.at = et(D_DAY, 9, 1).timestamp()
        with mock.patch.object(lane, "_eight_yield", lambda st, me: True):
            got = lane._eight_prepass(self.ctx(lane, w), D_DAY, "o1", None)
        self.assertEqual(got["_status"], "yielded")
        self.assertIsNone(MT.stored_state(w.st, prog, D_DAY, MT.sigma_time(s, "o1")), "nothing written until whole")
        self.assertEqual(w.st.db.execute("SELECT status FROM receipts WHERE job=?",
                                         (f"prepass-meta:open:{D_DAY}",)).fetchone()[0], "yielded")
        with mock.patch.object(lane, "_eight_yield", lambda st, me: False):     # (the slot free again: whole)
            got = lane._eight_prepass(self.ctx(lane, w), D_DAY, "o1", None)
        self.assertIsNotNone(MT.stored_state(w.st, prog, D_DAY, MT.sigma_time(s, "o1")))

    def test_a_morning_pass_after_the_open_decision_serves_only_the_on_auction(self):
        w = self.world(rows=False)
        px = w.px()
        try:
            PXL.morning(px, w.st, w.gw, D_DAY, now=et(D_DAY, 11, 0), run="am", clock=lambda: et(D_DAY, 11, 0, 30))
            self.assertEqual(json.loads(PXL._meta(px.db, PXL.AM_KEY.format(day=D_DAY.isoformat())))["serves"], "on")
            s = C.session(w.st, D_DAY)
            self.assertEqual(PXL.pxu(px.db, D_DAY, before=s.open_decide), {}, "no PX-GAP-O1 event of D")
            self.assertTrue(PXL.pxu(px.db, D_DAY, before=s.close_decide))
        finally:
            px.close()

    def test_the_morning_and_the_prepasses_in_their_windows(self):
        w = self.world(rows=False)
        st, s = w.st, C.session(w.st, D_DAY)
        lane, _ = self.lane(w, et(D_DAY, 9, 0))
        self.assertEqual(lane._eight_due(st, et(D_DAY, 9, 6), D_DAY, s, []).name, "px8-am")
        self.assertIsNone(lane._eight_due(st, et(D_DAY, 9, 14, 55), D_DAY, s, []), "never inside a decision's margin")
        self.assertEqual(lane._eight_due(st, et(D_DAY, 11, 0), D_DAY, s, []).name, "px8-am",
                         "it resumes after the open decisions and runs until 15:30")
        got = lane._eight_due(st, et(D_DAY, 9, 1), D_DAY, s, [])
        self.assertEqual(got.name, "meta8-prepass-o1")
        got = lane._eight_due(st, et(D_DAY, 15, 31), D_DAY, s, [])
        self.assertEqual(got.name, "meta8-prepass-on")
        self.assertIsNone(lane._eight_due(st, et(D_DAY, 15, 44), D_DAY, s, []), "never past the close - 17 min")
        self.assertIsNotNone(lane._hold_at(st, et(D_DAY, 15, 0)), "the lead holds for this file too")

    def test_meta_on_on_the_lanes_close_receipt_never_past_the_close_less_1120(self):
        for name, now, made in (("in", et(D_DAY, 15, 48, 30), True), ("past", et(D_DAY, 15, 48, 41), False)):
            w = self.world(name)
            the_open(w)
            w.at(et(D_DAY, 15, 46, 5)).px_decide(D_DAY, "on")
            w.at(et(D_DAY, 15, 47)).decide("close", D_DAY)
            lane, _ = self.lane(w, now)
            lane._eight_close_meta(self.ctx(lane, w), D_DAY)
            got = MT.decided(w.st.db, MT.learner("on"), D_DAY)
            self.assertEqual(got is not None and got["kind"] == "live", made, name)
            self.assertEqual(w.st.meta(PXL.RAN_KEY.format(key="close-meta", day=D_DAY.isoformat())) is not None, made)

    def test_the_meta_catch_ups_from_oct_20_oldest_first_once_the_lanes_decision_is_in(self):
        w = self.world(rows=False)
        lane, _ = self.lane(w, et(D_DAY, 12, 0))
        oct20 = dt.date(2026, 10, 20)
        self.assertIsNone(lane._eight_owed(w.st, lane.now(), D_DAY), "the lane's decision of Oct 20's open is not in")
        rid = w.st.start_receipt(f"decide-open:{oct20}", now=et(oct20, 9, 15))
        w.st.finish_receipt(rid, "ok", {}, now=et(oct20, 9, 16))
        self.assertEqual(lane._eight_owed(w.st, lane.now(), D_DAY), ("meta", oct20, "o1"))
        w.at(et(D_DAY, 12, 0)).meta_decide(oct20, "o1", kind="catchup")
        self.assertIsNone(lane._eight_owed(w.st, lane.now(), D_DAY), "next: Oct 20's close, whose decision is not in")
        far = et(dt.date(2027, 1, 20), 12, 0)
        self.assertEqual(lane._eight_owed(w.st, far, D_DAY)[:2], ("meta", oct20),
                         "a session older than the look-back is decided with none, never skipped (section 8)")

    def test_the_open_run_marks_its_end_for_the_book(self):
        w = self.world(rows=False)
        w.at(et(D_DAY, 9, 5)).morning(D_DAY)
        w.at(et(D_DAY, 9, 15, 30)).decide("open", D_DAY)
        lane, _ = self.lane(w, et(D_DAY, 9, 16))
        lane._eight_open(self.ctx(lane, w), D_DAY)
        jobs = [str(r[0]) for r in w.st.db.execute("SELECT job FROM receipts")]
        self.assertIn(f"decide-open-px8:{D_DAY}", jobs)
        self.assertIn(f"decide-open-meta8:{D_DAY}", jobs)
        self.assertIsNotNone(w.st.meta(PXL.RAN_KEY.format(key="open", day=D_DAY.isoformat())))
        past = self.world("past", rows=False)
        past.at(et(D_DAY, 9, 15, 30)).decide("open", D_DAY)
        lane, _ = self.lane(past, et(D_DAY, 9, 19, 31))
        lane._eight_open(self.ctx(lane, past), D_DAY)
        self.assertNotIn(f"decide-open-px8:{D_DAY}", [str(r[0]) for r in past.st.db.execute("SELECT job FROM receipts")],
                         "never past 09:19:30")


class TheLatePasses(TB.EventTest):
    """SECTION 4.6's TEST (v) AND THE LATE PASSES BY TIME (league/equity/live.py `_event_decide_8`): PX-DROP-ON's buys
    are planned at the first tick at which the lane's close receipt is in, after every PREREG-EVL-7 row of the close is
    planned or has failed; a receipt after the 15:48 tick: never planned; the open's pass at the first tick after the
    House's open run has finished."""

    def harness8(self, name: str):
        root = self.root / name
        root.mkdir()
        h = TB.Harness(root)
        self.addCleanup(h.state.close)
        self.addCleanup(h.lane.st.close)
        self.addCleanup(lambda: h.book._event_lane is not None and h.book._event_lane.close())
        return h

    def seed(self, h, program: str, auction: str) -> None:
        px = PXL.open_px(h.lane.st.root)
        try:
            run = f"{PXL.JOB_LIVE[auction]}:invented"
            for n, sym in enumerate(("PXA", "PXB", "PXC"), 1):
                cik = W.PX_CIK[sym]
                px.put_result(TB.DAY, cik, S.LIVE_RULE, {"symbol": sym, "name": sym, "exchange": "NASDAQ",
                                                          "prev_close": 16.0, "adv20": 4e7, "adv20sh": 2e6,
                                                          "bench": "IWM", "adjusted61": 61, "inputs_at": "x"},
                              why=None, run="u", now=dt.datetime(2026, 11, 4, 12, tzinfo=dt.timezone.utc))
                event = f"px:{program}:{TB.DAY}:{cik}"
                px.db.execute("INSERT INTO px_decisions(run, auction, day, program, rank, event, cik, symbol, rank_key, "
                              "adv20, prev_close) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 4e7, 16.0)",
                              (run, auction, TB.DAY.isoformat(), program, n, event, cik, sym, 10.0 - n))
                exit_ = TB.NEXT if auction == "on" else TB.DAY
                h.lane.intent(P.BY_KEY[(program, 1)], event, sym, cik, TB.DAY, exit_)
                h.symbol(sym, last=16.0)
            px.db.execute("INSERT INTO px_meta(key, value) VALUES(?, ?)",
                          (PXL.DECIDED_KEY.format(auction=auction, day=TB.DAY.isoformat()),
                           json.dumps({"run": run, "kind": "live", "receipt": 1, "at": "x"})))
        finally:
            px.close()

    def mine(self, h) -> list[str]:
        return [r["symbol"] for r in h.event_intents("buy") if P.is_8(r["program"])]

    def learners_failed(self, h, auction: str) -> None:
        learners_failed(h, auction)

    def test_v_planned_at_the_first_tick_the_lanes_close_receipt_is_in(self):
        with W.pinned():
            on = self.harness8("in")
            self.seed(on, "PX-DROP-ON", "on")
            self.learners_failed(on, "on")
            on.lane.decided(TB.DAY, "open")
            for hh, mm in ((15, 46), (15, 47)):
                on.tick(hh, mm)
            self.assertEqual(self.mine(on), [], "the lane's close receipt is not in yet: nothing planned")
            on.lane.decided(TB.DAY, "close")            # (the receipt at 15:47:40)
            on.tick(15, 48)
            self.assertEqual(self.mine(on), ["PXA", "PXB", "PXC"], "planned at the 15:48 tick")
            late = self.harness8("late")
            self.seed(late, "PX-DROP-ON", "on")
            self.learners_failed(late, "on")
            late.lane.decided(TB.DAY, "open")
            for hh, mm in ((15, 46), (15, 47), (15, 48)):
                late.tick(hh, mm)
            late.lane.decided(TB.DAY, "close")          # (the receipt at 15:48:20, after the 15:48 tick)
            late.tick(15, 49)
            late.tick(16, 1)
            self.assertEqual(self.mine(late), [], "the last tick inside the window has passed: never planned")
            self.assertFalse(late.state.rows("SELECT 1 AS x FROM eq_event_decisions WHERE at='close-px8'"))

    def test_after_every_prereg_evl7_row_planned_or_failed(self):
        """Section 4.2 and 4.6 on the tree's own learners (PREREG-EVL-7, pinned): while EVL-LRN-ON's own live receipt
        of the close has not finished, the learners' pass waits and this file's close pass waits behind it, whatever
        the lane's close receipt; once that receipt finishes (here naming none: its part failed), the learners' pass is
        made and this file's pass follows it IN THE SAME TICK, after it."""
        from league.events import learner as LR

        with W.pinned():
            h = self.harness8("lrn")
            self.seed(h, "PX-DROP-ON", "on")
            self.ready(h)
            self.assertTrue(P.learners(), "the tree carries PREREG-EVL-7's learners, pinned")
            h.tick(15, 46)
            out = h.tick(15, 47)
            self.assertEqual(self.mine(h), [], "the learners' own receipt is not in: their pass and this file's wait")
            self.assertIn("comes after PREREG-EVL-7's rows", str(out.get("event_decide_8")))
            self.assertFalse(h.state.rows("SELECT 1 AS x FROM eq_event_decisions WHERE at IN ('close-lrn', 'close-px8')"))
            at = dt.datetime(2026, 11, 4, 20, 47, 40, tzinfo=dt.timezone.utc)
            for prog in P.learners():
                if prog.entry_at == "close":
                    rid = h.lane.st.start_receipt(LR.live_job(prog, TB.DAY), now=at)
                    h.lane.st.finish_receipt(rid, "failed", {"error": "invented"}, now=at)
            h.tick(15, 48)
            self.assertEqual(self.mine(h), ["PXA", "PXB", "PXC"], "the learners' part failed: this file's pass goes")
            rows = h.state.rows("SELECT at, status FROM eq_event_decisions WHERE at IN ('close-lrn', 'close-px8') "
                                "ORDER BY rowid")
            self.assertEqual([(r["at"], r["status"]) for r in rows], [("close-lrn", "done"), ("close-px8", "done")])

    def test_the_open_pass_after_the_houses_open_run(self):
        with W.pinned():
            h = self.harness8("open")
            self.seed(h, "PX-GAP-O1", "o1")
            self.learners_failed(h, "o1")
            self.ready(h)
            h.tick(9, 15)
            h.tick(9, 16)
            self.assertEqual(self.mine(h), [], "the open run has not finished")
            h.lane.st.set_meta(PXL.RAN_KEY.format(key="open", day=TB.DAY.isoformat()), "{}")
            h.tick(9, 17)
            self.assertEqual(self.mine(h), ["PXA", "PXB", "PXC"])

    def test_a_learner_of_the_other_auction_alone_never_holds_this_files_pass(self):
        """The learners' pass of the open writes its row only when it has a live learner entering there or a birth held
        back for one (league/equity/live.py `_event_decide_lrn`); with EVL-LRN-O1 retired and EVL-LRN-ON (a close
        entry) alive, the open's learners' pass never comes, and this file's open pass goes once the House's open run
        has finished (`_event_lrn_settled`), not never."""
        with W.pinned():
            h = self.harness8("other")
            self.seed(h, "PX-GAP-O1", "o1")
            h.lane.band("EVL-LRN-O1", "retired", version=1)
            self.ready(h)
            h.lane.st.set_meta(PXL.RAN_KEY.format(key="open", day=TB.DAY.isoformat()), "{}")
            h.tick(9, 15)
            h.tick(9, 16)
            alive = {i.family: i.live for i in h.book._instances(alive=True) if P.is_learner(i.family)}
            self.assertFalse(alive.get("EVL-LRN-O1"), alive)
            self.assertTrue(alive.get("EVL-LRN-ON"), alive)
            self.assertFalse(h.state.rows("SELECT 1 AS x FROM eq_event_decisions WHERE at='open-lrn'"))
            self.assertEqual(self.mine(h), ["PXA", "PXB", "PXC"])


class ThePromotedSizing(TB.EventTest):
    """SECTION 4.1: a Probe or Sized buy of a version of this file is PREREG-EVL-6 section 6's (clause 2, A99, A123's
    literal reading): THE FEWEST whole shares whose value at the limit reaches Done's 0.8 bar of the band's target,
    judged again by every cap; at E $1,898 and goal V3's Probe share (5%, A138) a target of $94.90 and a $5.00 limit
    that is 16 shares ($80.00 >= $75.92), never release 1019h's S2 floor of the target, 18 (league/equity/live.py
    `_v6_sized`, programs.py `Program8.v6_sized`)."""

    def run_probe(self, sized: bool):
        with W.pinned(), mock.patch.object(P.Program8, "v6_sized", property(lambda self: sized and self.seatable)):
            root = self.root / ("v6" if sized else "s2")
            root.mkdir()
            h = TB.Harness(root, cash="1898", E="1898")
            self.addCleanup(h.state.close)
            self.addCleanup(h.lane.st.close)
            self.addCleanup(lambda: h.book._event_lane is not None and h.book._event_lane.close())
            h.lane.band("PX-GAP-O1", "probe", version=1)
            px = PXL.open_px(h.lane.st.root)
            try:
                run, cik = f"{PXL.JOB_LIVE['o1']}:invented", W.PX_CIK["PXA"]
                px.put_result(TB.DAY, cik, S.LIVE_RULE, {"symbol": "PXA", "name": "PXA", "exchange": "NASDAQ",
                                                         "prev_close": 4.0, "adv20": 4e7, "adv20sh": 2e6, "bench": "IWM",
                                                         "adjusted61": 61, "inputs_at": "x"},
                              why=None, run="u", now=dt.datetime(2026, 11, 4, 12, tzinfo=dt.timezone.utc))
                event = f"px:PX-GAP-O1:{TB.DAY}:{cik}"
                px.db.execute("INSERT INTO px_decisions(run, auction, day, program, rank, event, cik, symbol, rank_key, "
                              "adv20, prev_close) VALUES(?, 'o1', ?, 'PX-GAP-O1', 1, ?, ?, 'PXA', 9.0, 4e7, 4.0)",
                              (run, TB.DAY.isoformat(), event, cik))
                px.db.execute("INSERT INTO px_meta(key, value) VALUES(?, ?)",
                              (PXL.DECIDED_KEY.format(auction="o1", day=TB.DAY.isoformat()),
                               json.dumps({"run": run, "kind": "live", "receipt": 1, "at": "x"})))
            finally:
                px.close()
            h.lane.intent(P.BY_KEY[("PX-GAP-O1", 1)], event, "PXA", cik, TB.DAY, TB.DAY)
            h.symbol("PXA", last=4.0, sd=0.02)
            learners_failed(h, "o1")
            self.ready(h)
            h.lane.st.set_meta(PXL.RAN_KEY.format(key="open", day=TB.DAY.isoformat()), "{}")
            with mock.patch.object(L, "event_orders_today", lambda rows, day: 0), \
                    mock.patch.object(EB, "LINE_ACROSS_AUCTIONS", False):
                h.tick(9, 15)
                h.tick(9, 16)
            return {b["symbol"]: b["qty"] for b in h.bodies() if b["side"] == "buy"}, h.event_intents("buy")

    def test_a_probe_buy_takes_the_fewest_whole_shares_that_reach_dones_bar(self):
        share = EB.settings().share("probe")
        target = share * D("1898")
        self.assertEqual(EB.at_size_count("probe", target, D("5"), D("1898")), 16)
        sent, rows = self.run_probe(True)
        self.assertEqual(sent, {"PXA": "16"}, f"the fewest whole shares reaching 0.8 x ${target} at $5.00")
        self.assertEqual(D(rows[0]["target_usd"]).quantize(D("0.01")), target.quantize(D("0.01")),
                         "the target stays the band's")
        old, _ = self.run_probe(False)
        self.assertEqual(old, {"PXA": "18"}, "without section 4.1's sizing: S2's floor of the target")


class TheLine8(TB.EventTest):
    """SECTION 4.3: THE 150-ORDER LINE REFUSES THIS FILE'S ENTRIES FIRST AMONG THE PREREG ROWS, AFTER PREREG-EVL-7'S
    (league/equity/live.py `_event_line_keep`): an entry of this file keeps every order every earlier PREREG row may still
    send on the day's line, PREREG-EVL-7's learners among them, across the day's auctions (A130 R5's reading, the one
    that trades less), so its keep is a learner's keep plus the learners' own room."""

    def test_an_open_entry_keeps_the_days_close_entries_of_every_earlier_row_the_learners_included(self):
        with W.pinned():
            root = self.root / "line"
            root.mkdir()
            h = TB.Harness(root)
            self.addCleanup(h.state.close)
            self.addCleanup(h.lane.st.close)
            self.addCleanup(lambda: h.book._event_lane is not None and h.book._event_lane.close())
            TheLatePasses.seed(self, h, "PX-GAP-O1", "o1")
            learners_failed(h, "o1")
            self.ready(h)
            h.lane.st.set_meta(PXL.RAN_KEY.format(key="open", day=TB.DAY.isoformat()), "{}")
            for minute in (15, 16, 17):
                h.tick(9, minute)
            s, adapter = EB.settings(), h.book._event_adapter()
            buys = [r for r in h.event_intents("buy") if r["program"] == "PX-GAP-O1"]
            self.assertEqual([r["symbol"] for r in buys], ["PXA", "PXB", "PXC"], "planned in the open's late pass")
            intent = h.book._intent(int(buys[0]["iid"]))
            mine = h.book._instance(L.instance_key("PX-GAP-O1", 1))
            lrn_o1 = h.book._instance(L.instance_key("EVL-LRN-O1", 1))
            lrn_on = h.book._instance(L.instance_key("EVL-LRN-ON", 1))
            keep = h.book._event_line_keep(intent, mine, TB.DAY.isoformat(), "open", s, adapter)
            learner = h.book._event_line_keep(intent, lrn_o1, TB.DAY.isoformat(), "open", s, adapter)
            on_room = s.max_open(lrn_on.band, adapter.program_of(lrn_on.family, lrn_on.version))
            self.assertGreater(learner, 0)
            self.assertEqual(keep, learner + 2 * on_room, "a learner's keep plus EVL-LRN-ON's close room (send and re-send)")
            self.assertEqual(h.book._event_line_keep(intent, h.book._instance(L.instance_key("PX-DROP-ON", 1)),
                                                     TB.DAY.isoformat(), "open", s, adapter) > 0, True)
            read = next(p for p in EB.seatable() if p.id == "EVL-ERN-READ-O1")
            self.assertEqual(h.book._event_line_keep(intent, h.book._instance(L.instance_key(read.id, read.version)),
                                                     TB.DAY.isoformat(), "open", s, adapter), 0, "an earlier row keeps none")
            # THE STATED EFFECT (the reading that trades less): the close rows' room alone exceeds the 150 line, so this
            # file's open entries are refused on an empty day, as EVL-LRN-O1's are, and nothing is sent
            self.assertGreater(keep, int(s.max_orders_day))
            for r in h.event_intents("buy"):
                if r["program"] == "PX-GAP-O1":
                    self.assertEqual(r["status"], "planned")
                    self.assertIn("the event kind's day order count", r["why"])
            self.assertEqual([b for b in h.bodies() if b.get("side") == "buy"], [])


if __name__ == "__main__":
    unittest.main()
