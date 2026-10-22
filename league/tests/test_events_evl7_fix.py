"""RELEASE 1019i's FIX ROUND OF PREREG-EVL-7 (the judges' and the money reviews of PR 602), on INVENTED rows only (no
figure here is a market's; no House or desktop store is opened). Each test fails without its fix:

- THE LEARNERS HAVE A JUDGE (league/events/judge7.py, the blocker): a pinned learner whose live record reaches 22
  blocks gets its look written through COST-7's one interface to PREREG-EVL-6's screen, with its band move (PASS to
  probe, RETIRE to retired) in the look's own transaction; every look waits without the night's cost_basis row; the
  run ends at its 60th block and its next run starts only when the lane's count holds 0.13, at most three runs, a run
  that cannot start refused for good; with no PREREG-EVL-6 screen in the tree nothing is written, and the real-money
  gate refuses the learner's buys once a look is due and not written (and the H5 alarm says so);
- COST-7's SELECTION POPULATION (section 2.2 (b)): a shadow-skipped attempt neither blocks a checkpoint nor counts; on
  release 1019i's own ledger (`SCHEMA_1019I`), an unsent pick and a refused order are no attempt, a re-send the same;
- ROOM (section 1.9): at one auction a learner at learning takes a name before an R3 birth at learning; a learner at
  Probe is the last program of each Probe pass; no learner, no change; A85's reservation reads a learner's picks;
- THE DAY ORDER LINE (section 1.9): EVL-LRN-O1's open entry keeps the day's close entries of every earlier row, so the
  line refuses it where a fixed keep let it take an earlier row's close slot."""

from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.equity import live as L
from league.equity import schedule as ES
from league.events import book as EB
from league.events import calendar as C
from league.events import costs7 as C7
from league.events import judge7 as J7
from league.events import learner as LR
from league.events import programs as P
from league.events import screen as SN
from league.events import store as S
from league.ops import evl_learner as EL
from league.tests import test_events_book as TB
from league.tests import test_events_evl7 as T7

O1, ON = T7.O1, T7.ON
et, pin, learner = T7.et, T7.pin, T7.learner
FINAL = J7.final        # (the module's own, before a JudgeCase invents the pool programs' finality)

#: Release 1019i's attempt ledger AS ITS INFRASTRUCTURE BRANCH WRITES IT (origin/feat/infra-1019i league/events/store.py
#: `SCHEMA_1019I`, the `real_attempts` table), copied here so COST-7's population is tested on the very table it reads
#: once the branches merge; held equal to the tree's own wherever the tree carries it.
SCHEMA_1019I_ATTEMPTS = """
CREATE TABLE IF NOT EXISTS real_attempts(client_id TEXT PRIMARY KEY, venue_id TEXT, program TEXT NOT NULL,
  version INTEGER NOT NULL, event TEXT NOT NULL, side TEXT NOT NULL, kind TEXT NOT NULL, day TEXT NOT NULL, at TEXT,
  band TEXT, rung INTEGER, resend INTEGER NOT NULL DEFAULT 0, replaces TEXT, sent INTEGER NOT NULL,
  accepted INTEGER NOT NULL, state TEXT NOT NULL, final INTEGER NOT NULL, venue_status TEXT, qty REAL NOT NULL,
  filled_qty REAL NOT NULL, avg_px REAL, limit_px REAL, cancel_ms INTEGER, sent_at TEXT, submitted_at TEXT,
  filled_at TEXT, canceled_at TEXT, expired_at TEXT, binding TEXT, first_seen TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS real_attempts_day ON real_attempts(day, side, at);
"""


def extend(w: T7.World, until: dt.date = dt.date(2027, 4, 30)) -> None:
    """The invented lane's calendar and equity carried on past 2026 (enough sessions for a run's 60th block)."""
    d = dt.date(2027, 1, 1)
    with w.st.tx() as db:
        while d <= until:
            m = ES.moments(d)
            if m is not None:
                db.execute("INSERT OR IGNORE INTO sessions(day, open_at, close_at, early) VALUES(?, ?, ?, ?)",
                           (d.isoformat(), S.iso(dt.datetime.fromtimestamp(m.open_at, dt.timezone.utc)),
                            S.iso(dt.datetime.fromtimestamp(m.close_at, dt.timezone.utc)), int(m.early)))
                db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, '10000.0')", (f"equity:{d.isoformat()}",))
            d += dt.timedelta(days=1)


def live_sessions(case: T7.WorldCase, days: list[dt.date], *, per: int = 2, a_g: float = 0.01, pid: str = O1,
                  kind: str = "live") -> None:
    """For each of `days`: the learner's decision of the session as league/events/learner.py writes it (its fits row,
    `per` picked candidates of new issuers, each an article knowable after REGISTERED_AT_7) and each pick's intent
    settled TRADABLE that night with the gross abnormal return `a_g` (World.outcome)."""
    w, st = case.w, case.st
    prog = learner(pid)
    for day in days:
        s = w.session(day)
        tau = s.open_decide if prog.entry_at == "open" else s.close_decide
        st.db.execute("INSERT INTO learner_fits(program, version, day, tau, kind, status, n_picks, finished_at, e_prev) "
                      "VALUES(?, 1, ?, ?, ?, 'ok', ?, ?, 10000.0)", (pid, day.isoformat(), S.iso(tau), kind, per,
                                                                    S.iso(tau)))
        feats = json.dumps({"x": [0.0] * len(LR.FEATURES[pid]), "hist": 0})
        for rank in range(1, per + 1):
            cik, sym = w.issuer()
            w.universe(day, sym, cik)
            ev = w.article(f"lrn-{pid}-{day.isoformat()}-{rank}", sym, knowable=et(w.prior(day), 18, rank))
            st.db.execute("INSERT INTO learner_cands(program, version, day, cik, event, symbol, families, kept, eligible, "
                          "features, sig20, adv20, prev_close, knowable_at, picked, rank, kind) VALUES(?, 1, ?, ?, ?, ?, '[]', "
                          "1, 1, ?, 0.03, 2e7, 20.0, ?, 1, ?, ?)", (pid, day.isoformat(), cik, ev, sym, feats,
                                                                   S.iso(et(w.prior(day), 18, rank)), rank, kind))
            w.outcome(pid, ev, sym, cik, day, a_g=a_g, settled=et(day, 20, 30))
            st.db.execute("UPDATE intents SET rank_key=? WHERE program=? AND event=?", (0.05 - 0.001 * rank, pid, ev))
        if kind == "live":
            T7.name_live(st, pid, day)


class FakeScreen:
    """PREREG-EVL-6's screen at its one interface (`screen.v6_judge` over `blocks6`), invented: a look's S is the
    record's block count, its decision `decide(S, tag)`; every call is kept."""

    def __init__(self, decide=lambda S, tag: None):
        self.decide, self.calls = decide, []

    def blocks6(self, rows):
        return [r for r in rows if r.get("tradable") in (True, 1)]

    def v6_judge(self, blocks, *, program, version, tag, control_rows, control, draws=None):
        days = sorted({r["entry_day"] for r in blocks})
        self.calls.append({"program": program, "S": len(days), "tag": tag, "control": control, "n": len(blocks),
                           "control_rows": len(control_rows)})
        decision = self.decide(len(days), tag)
        return {"S": len(days), "tag": tag, "seed": f"{program}|v{version}|evl6|{tag}S{len(days)}", "n": len(blocks),
                "issuers": len({r["issuer"] for r in blocks}), "mean_a": -0.01 if decision == "retire" else 0.01,
                "mean_r": 0.01, "p": 0.001 if decision == "pass" else 0.5, "q": 0.001 if decision == "retire" else 0.5,
                "p_issuer": 0.05, "alpha": 0.02, "guards": {}, "top14": {}, "money_a": 0.0, "block_mean": 0.0,
                "control": {"program": control}, "beside": {}, "decision": decision,
                "why": {"pass": "PASS", "retire": "RETIRE"}.get(decision, "fail: p")}

    def __enter__(self):
        self._p = [mock.patch.object(SN, "v6_judge", self.v6_judge, create=True),
                   mock.patch.object(SN, "blocks6", self.blocks6, create=True)]
        for p in self._p:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._p:
            p.stop()


class JudgeCase(T7.WorldCase):
    """A WorldCase with the pool programs' finality invented as final through today (`judge7.final` reads
    screen.py `final_until` of each pool program: held in its own test), and the night's cost_basis row."""

    def setUp(self):
        super().setUp()
        extend(self.w)
        patch = mock.patch.object(J7, "final", lambda store, lrn, today, now: (today, "invented: final"))
        patch.start()
        self.addCleanup(patch.stop)

    def night(self, day: dt.date) -> dt.datetime:
        C7.nightly(self.st, day, et(day, 21, 0))
        return et(day, 22, 0)

    def gate(self, pid: str = O1) -> dict | None:
        return J7.blocked(self.st, learner(pid))


# ------------------------------------------------------------------------------------------- the learners' judge
class TheLooks(JudgeCase):
    def test_a_pinned_learner_reaching_22_live_blocks_gets_a_look_written_and_its_gate_opens(self):
        days = self.days(23)
        live_sessions(self, days)
        last = days[-1]
        self.assertEqual(self.gate()["kind"], "look_overdue", "22 blocks and no look: its real money stops")
        now = self.night(last)
        with FakeScreen() as fake:
            got = J7.run(self.st, last, now=now)
        self.assertEqual(got["errors"], [])
        [look] = got["written"]
        self.assertEqual((look["k"], look["look"], look["S"], look["tag"]), (1022, 1, 22, ""))
        self.assertEqual([c["S"] for c in fake.calls], [22], "judged once, at the 22nd block, through judge_record")
        self.assertEqual(fake.calls[0]["control"], f"{O1}-POOL")
        row = self.st.db.execute("SELECT * FROM looks WHERE program=? AND version=1", (O1,)).fetchone()
        self.assertEqual((row["k"], row["blocks"], row["held"], row["passed"]), (1022, 22, 1, 0))
        self.assertEqual(row["at"], S.iso(self.w.session(days[21]).close_at), "as of the close covering block 22")
        detail = json.loads(self.st.meta(J7.LOOK_KEY.format(program=O1, version=1, k=1022)))
        self.assertEqual((detail["rule"], detail["cost"], detail["look"], detail["S"]), ("PREREG-EVL-6", "COST-7", 1, 22))
        self.assertEqual(detail["basis"]["night"], last.isoformat(), "valued on the latest basis before the look")
        self.assertIsNone(self.gate(), "the look is on record: real money goes on")
        with FakeScreen() as fake:
            again = J7.run(self.st, last, now=now)
        self.assertEqual((again["written"], fake.calls), ([], []), "a look is written once; none at 23 blocks")

    @unittest.skipUnless(getattr(SN, "v6_judge", None) is not None, "PREREG-EVL-6's screen is not in this tree")
    def test_with_preregevl6s_own_screen_the_look_is_judged_by_it(self):
        days = self.days(23)
        live_sessions(self, days, a_g=0.02)
        got = J7.run(self.st, days[-1], now=self.night(days[-1]), draws=999)
        self.assertEqual(got["errors"], [])
        [look] = got["written"]
        detail = json.loads(self.st.meta(J7.LOOK_KEY.format(program=O1, version=1, k=look["k"])))
        self.assertEqual((detail["S"], detail["tag"], detail["seed"]), (22, "", f"{O1}|v1|evl6|S22"))
        self.assertIsNotNone(detail["p"])
        self.assertIn(detail["decision"], (None, "pass", "retire"))

    def test_with_no_preregevl6_screen_nothing_is_written_and_the_gate_stays_shut(self):
        days = self.days(23)
        live_sessions(self, days)
        now = self.night(days[-1])
        with mock.patch.object(SN, "v6_judge", None, create=True):
            got = J7.run(self.st, days[-1], now=now)
        self.assertEqual(got["written"], [])
        self.assertTrue(any("PREREG-EVL-6's screen is not in this tree" in w["why"] for w in got["waiting"]))
        self.assertEqual(self.st.db.execute("SELECT COUNT(*) FROM looks").fetchone()[0], 0)
        self.assertEqual(self.gate()["kind"], "look_overdue", "no judge: the learner's real money buys nothing")
        lane = EB.Lane(self.st.root / S.DB_NAME)
        self.addCleanup(lane.close)
        self.assertIn("is not written", EB.learner_gate(lane, learner(O1)))

    def test_every_look_waits_without_the_nights_cost_basis_row(self):
        days = self.days(23)
        live_sessions(self, days)
        with FakeScreen() as fake:
            got = J7.run(self.st, days[-1], now=et(days[-1], 22, 0))
        self.assertEqual((got["written"], fake.calls), ([], []))
        self.assertIn("no cost_basis row for the night", got["waiting"][0]["why"])
        C7.nightly(self.st, days[-2], et(days[-2], 21, 0))
        with FakeScreen():
            self.assertEqual(J7.run(self.st, days[-1], now=et(days[-1], 22, 0))["written"], [],
                             "the night's own row: an older night's is not it")

    def test_a_look_waits_for_its_close_to_be_final_and_its_intents_settled(self):
        days = self.days(23)
        live_sessions(self, days)
        now = self.night(days[-1])
        with mock.patch.object(J7, "final", lambda *a: (days[20], "invented: two closes short")), FakeScreen() as fake:
            got = J7.run(self.st, days[-1], now=now)
        self.assertEqual((got["written"], fake.calls), ([], []))
        self.assertIn("not final yet", got["waiting"][0]["why"])
        self.st.db.execute("UPDATE intents SET status='entered' WHERE program=? AND entry_day=?", (O1, days[3].isoformat()))
        with FakeScreen() as fake:
            got = J7.run(self.st, days[-1], now=now)
        self.assertEqual((got["written"], fake.calls), ([], []), "an intent due by the as-of close has not settled")

    def test_pass_moves_to_probe_and_retire_retires_in_the_looks_own_transaction(self):
        days = self.days(23)
        live_sessions(self, days)
        now = self.night(days[-1])
        with FakeScreen(lambda S, tag: "pass"):
            got = J7.run(self.st, days[-1], now=now)
        self.assertEqual(got["written"][0]["band"], "probe")
        self.assertEqual(J7.band_of(self.st, learner(O1)), "probe")
        self.assertEqual(J7.runs(self.st, learner(O1))[-1]["ended"]["why"], "pass")
        self.assertEqual(self.gate()["kind"], "no_stay_judge", "at Probe with no stay judge: no real money")
        live_sessions(self, self.days(23), pid=ON)
        with FakeScreen(lambda S, tag: "retire"):
            got = J7.run(self.st, days[-1], now=now)
        self.assertEqual([(w["program"], w["band"]) for w in got["written"]], [(ON, "retired")])
        self.assertEqual(self.gate(ON)["kind"], "retired")
        with FakeScreen() as fake:
            self.assertEqual(J7.run(self.st, days[-1], now=now)["written"], [])
        self.assertEqual(fake.calls, [], "a retired and a promoted run are judged no more")


class TheRuns(JudgeCase):
    def test_the_run_ends_at_its_60th_block_and_run_two_starts_when_the_count_holds_it(self):
        days = [s.day for s in C.sessions(self.st, dt.date(2026, 10, 26), dt.date(2027, 4, 30))][:62]
        self.assertEqual(len(days), 62)
        live_sessions(self, days)
        night = days[59]        # (the night of the close covering its 60th block)
        with FakeScreen() as fake:
            got = J7.run(self.st, night, now=self.night(night))
        self.assertEqual([c["S"] for c in fake.calls], list(J7.LOOKS), "every look of the run, never one past 60")
        end = json.loads(self.st.meta(J7.END_KEY.format(program=O1, version=1, n=1)))
        self.assertEqual(end["last_day"], days[59].isoformat())
        [started] = got["started"]
        self.assertEqual((started["n"], started["charge"], started["after_day"]), (2, 0.13, days[59].isoformat()))
        self.assertEqual(json.loads(self.st.meta(J7.RUN_KEY.format(program=O1, version=1, n=2)))["after_day"],
                         days[59].isoformat())
        history = J7.runs(self.st, learner(O1))
        self.assertEqual([r["n"] for r in history], [1, 2])
        self.assertIsNone(history[-1]["ended"])
        record = J7.run_record(J7.live_rows(self.st, learner(O1)), history[-1])
        self.assertEqual({r["entry_day"] for r in record}, set(days[60:]), "run 2's record: the blocks after run 1's 60th")
        self.assertIsNone(self.gate(), "a run in force: real money goes on")
        self.assertEqual(J7.used(self.st)["used"], 13 * (sum(1 for p in P.SEATING if p.can_seat) + 1),
                         "run 2's 0.13 is in the lane's count")

    def test_a_run_the_count_cannot_hold_is_refused_for_good_and_a_fourth_never_starts(self):
        lrn = learner(O1)
        self.st.set_meta(J7.END_KEY.format(program=O1, version=1, n=1), json.dumps({"at": "2027-01-29T21:00:00Z",
                                                                                   "last_day": "2027-01-29"}))
        with mock.patch.object(J7, "used", lambda store: {"used": 380, "waiting": 0, "budget": 390}):
            got = J7.start_runs(self.st, et(dt.date(2027, 1, 29), 22, 0), [lrn])
        self.assertEqual(got["started"], [])
        self.assertEqual(got["refused"][0]["n"], 2)
        self.assertIn("cannot hold 0.13 more", got["refused"][0]["why"])
        self.assertEqual(self.gate()["kind"], "no_run", "the version never seats again")
        self.assertEqual(J7.start_runs(self.st, et(dt.date(2027, 2, 1), 22, 0), [lrn]), {"started": [], "refused": []},
                         "refused once, for good: a later night with room changes nothing")
        # an earlier file's run still waiting holds its 0.13 first (registration order)
        other = learner(ON)
        self.st.set_meta(J7.END_KEY.format(program=ON, version=1, n=1), json.dumps({"at": "2027-01-29T21:00:00Z",
                                                                                   "last_day": "2027-01-29"}))
        with mock.patch.object(J7, "used", lambda store: {"used": 364, "waiting": 13, "budget": 390}):
            got = J7.start_runs(self.st, et(dt.date(2027, 1, 29), 22, 0), [other])
        self.assertEqual([r["n"] for r in got["started"]], [2], "364 + 13 held + 13 = 390: it fits")
        # three runs spent: a fourth is refused
        for n in (2, 3):
            self.st.set_meta(J7.END_KEY.format(program=ON, version=1, n=n), json.dumps({"at": "2027-03-01T21:00:00Z",
                                                                                       "last_day": "2027-03-01"}))
        self.st.set_meta(J7.RUN_KEY.format(program=ON, version=1, n=3), json.dumps({"n": 3, "after_day": "2027-02-26"}))
        got = J7.start_runs(self.st, et(dt.date(2027, 3, 1), 22, 0), [other])
        self.assertEqual(got["started"], [])
        self.assertEqual((got["refused"][0]["n"], "runs are spent" in got["refused"][0]["why"]), (4, True))
        self.assertEqual(self.gate(ON)["kind"], "no_run")

    def test_after_a_demotion_from_probe_the_next_run_starts_from_it(self):
        days = self.days(23)
        live_sessions(self, days)
        now = self.night(days[-1])
        with FakeScreen(lambda S, tag: "pass"):
            J7.run(self.st, days[-1], now=now)
        self.assertEqual(J7.start_runs(self.st, now, [learner(O1)]), {"started": [], "refused": []}, "passed: at Probe")
        from league.events import bands as BA

        BA.set_band(self.st, O1, 1, "learning", since=S.iso(et(days[-1], 23, 0)), why="invented demotion",
                    now=et(days[-1], 23, 0))
        got = J7.start_runs(self.st, et(days[-1], 23, 30), [learner(O1)])
        self.assertEqual(got["started"][0]["n"], 2)
        self.assertEqual(got["started"][0]["after"], S.iso(et(days[-1], 23, 0)), "its record: the entries after it")

    def test_the_lane_count_and_the_stored_forms_are_preregevl6s(self):
        self.assertEqual(J7.used(self.st)["used"], 13 * sum(1 for p in P.SEATING if p.can_seat))
        self.assertEqual((J7.CHARGE, J7.BUDGET, J7.RUNS_MAX), (LR.CHARGE7_HUNDREDTHS, 390, LR.RUNS_MAX))
        if getattr(SN, "V6_LOOKS", None) is not None:      # (wherever the tree carries PREREG-EVL-6's code)
            self.assertEqual(J7.LOOKS, tuple(SN.V6_LOOKS))
            self.assertEqual((J7.RUN_BLOCKS, J7.MIN_EVENTS, J7.MIN_ISSUERS, J7.MIN_BLOCKS),
                             (SN.V6_RUN_BLOCKS, SN.V6_MIN_EVENTS, SN.V6_MIN_ISSUERS, SN.V6_MIN_BLOCKS))
            self.assertEqual((J7.RUN_KEY, J7.END_KEY, J7.STAY_BASE), (SN.V6_RUN_KEY, SN.V6_END_KEY, SN.V6_STAY_BASE))
            self.assertEqual((J7.CHARGE, J7.BUDGET), (SN.V6_CHARGE_HUNDREDTHS, SN.V6_BUDGET_HUNDREDTHS))
            self.assertEqual(J7.look_key("run", 2, 25), SN.look_key6("run", 2, 25))
        self.assertEqual((J7.look_key("run", 1, 22), J7.key_of(2025)), (1022, ("run", 2, 25)))
        self.assertTrue(set(J7.ALARM_KINDS) <= set(EL.ALARM_GATES))

    def test_every_report_shows_the_learners_false_passes_three_ways_and_beside_them_per_version_and_per_id(self):
        """Section 4 as frozen: each learner charge (its run 1, each fresh run started) at c7 0.13, the base model 0.03
        and the stresses' worst 0.13, with each learner's per-version and per-id figures, in the report's learner
        lines; nothing while no learner is pinned."""
        got = J7.false_passes(self.st)
        self.assertEqual((got["charges"], got["count"], got["base"], got["stress"]), (2, 0.26, 0.06, 0.26))
        self.assertEqual(got["learners"][O1]["per_version"], 0.1585)
        self.assertEqual((got["learners"][ON]["per_version"], got["learners"][ON]["per_id"]), (0.1683, 0.233))
        self.st.set_meta(J7.RUN_KEY.format(program=O1, version=1, n=2), json.dumps({"n": 2, "after_day": "2027-01-29"}))
        self.st.set_meta(J7.NORUN_KEY.format(program=ON, version=1, n=2), json.dumps({"n": 2, "why": "invented"}))
        got = J7.false_passes(self.st)
        self.assertEqual((got["charges"], got["count"], got["base"], got["stress"]), (3, 0.39, 0.09, 0.39),
                         "O1's run 2 is a charge; ON's refused run 2 is none")
        lines = {x["program"]: x for x in LR.report_lines(self.st, dt.date(2026, 10, 26))}
        self.assertEqual(lines[O1]["false_passes"], {"charges": 2, "count": 0.26, "base": 0.06, "stress": 0.26,
                                                     "per_version": 0.1585, "per_id": 0.235})
        [text] = LR.render_lines([lines[ON]])
        self.assertIn("false passes 0.13 for 1 run(s) at 0.13 (base 0.03, stresses 0.13; per version 0.1683, per id "
                      "0.233)", text)
        pin(self, None)
        self.assertEqual(J7.false_passes(self.st), {})

    def test_final_is_the_earliest_pool_programs_and_none_while_one_has_none(self):
        lrn = learner(O1)
        today = dt.date(2026, 11, 20)
        got = {pid: (today - dt.timedelta(days=i), f"{pid} why") for i, pid in enumerate(LR.POOLS[O1])}
        with mock.patch.object(SN, "final_until", lambda store, pid, v, t, n: got[pid]):
            day, why = FINAL(self.st, lrn, today, et(today, 22, 0))
        self.assertEqual(day, today - dt.timedelta(days=len(LR.POOLS[O1]) - 1), "the earliest pool program's")
        got[LR.POOLS[O1][1]] = (None, "unmade")
        with mock.patch.object(SN, "final_until", lambda store, pid, v, t, n: got[pid]):
            self.assertEqual(FINAL(self.st, lrn, today, et(today, 22, 0)), (None, f"{LR.POOLS[O1][1]}: unmade"))


class TheGateAndTheAlarm(JudgeCase):
    def test_the_book_buys_nothing_for_a_learner_whose_look_is_overdue_and_the_alarm_says_so(self):
        days = self.days(23)
        live_sessions(self, days)
        moment = et(days[-1], 22, 0)
        f = EL.facts(self.tmp.name, moment.timestamp())
        self.assertEqual(f["learners"][O1]["gate"]["kind"], "look_overdue")
        self.assertEqual(f["learners"][O1]["gate"]["since"], days[21].isoformat(), "the 22nd block's session")
        self.assertNotIn("is not written", EL.judge(moment.timestamp(), f)["what"],
                         "a look waiting for its final close: not said yet")
        later = et(C.nth(self.st, days[-1], EL.OVERDUE_SESSIONS + 1).day, 22, 0)
        out = EL.judge(later.timestamp(), EL.facts(self.tmp.name, later.timestamp()))
        self.assertTrue(out["stalled"])
        self.assertIn("is not written", out["what"])
        self.assertEqual(f["learners"][ON]["gate"], None, "a learner with no live block: nothing to say")
        # the book: its live picks of the next session are not traded while the look is overdue
        nxt = C.nth(self.st, days[-1], 2).day
        live_sessions(self, [nxt])
        self.st.db.execute("DELETE FROM outcomes WHERE program=? AND event IN (SELECT event FROM intents WHERE "
                           "program=? AND entry_day=?)", (O1, O1, nxt.isoformat()))
        lane = EB.Lane(self.st.root / S.DB_NAME)
        self.addCleanup(lane.close)
        tau = self.w.session(nxt).open_decide
        self.assertEqual(EB.picks(lane, learner(O1), nxt, decided_at=tau), [])
        self.assertEqual(len(LR.live_picks(lane, learner(O1), nxt)), 2, "its shadow keeps every pick")
        with FakeScreen():
            J7.run(self.st, days[-1], now=self.night(days[-1]))
        self.assertTrue(EB.picks(lane, learner(O1), nxt, decided_at=tau), "the look written: its money goes on")


# ----------------------------------------------------------------------------------- COST-7's selection population
class ThePopulation(T7.WorldCase):
    def ledger(self) -> None:
        if getattr(S, "SCHEMA_1019I", None) is not None:
            self.assertIn(SCHEMA_1019I_ATTEMPTS.strip(), S.SCHEMA_1019I, "release 1019i's own ledger, verbatim")
        self.st.db.executescript(SCHEMA_1019I_ATTEMPTS)

    def attempt(self, day: dt.date, ev: str, *, cid: str, sent: int = 1, state: str = "filled", resend: int = 0,
                at: dt.datetime | None = None) -> None:
        when = S.iso(at or et(day, 9, 16))
        self.st.db.execute("INSERT INTO real_attempts(client_id, program, version, event, side, kind, day, at, band, resend, "
                           "sent, accepted, state, final, qty, filled_qty, sent_at, first_seen, updated_at) VALUES(?, "
                           "'EVL-NEWS-READ-O1', 3, ?, 'buy', 'loo', ?, 'open', 'learning', ?, ?, ?, ?, 1, 1, ?, ?, ?, ?)",
                           (cid, ev, day.isoformat(), resend, sent, sent, state, 1 if state == "filled" else 0,
                            when if sent else None, when, when))

    def shadow(self, day: dt.date, ev: str, a_g: float, *, settled: bool = True, status: str = "exited") -> None:
        cik, sym = self.w.issuer()
        self.w.universe(day, sym, cik)
        if settled:
            self.w.outcome("EVL-CTRL-NEWS-ALL-O1", ev, sym, cik, day, a_g=a_g, settled=et(day, 20, 30))
            self.st.db.execute("UPDATE outcomes SET program='EVL-NEWS-READ-O1', version=3 WHERE event=?", (ev,))
        else:
            self.st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                               "exit_day, exit_at, mode, status) VALUES('EVL-CTRL-NEWS-ALL-O1', 1, ?, ?, ?, ?, ?, 'open', ?, "
                               "'close', 'shadow', ?)", (ev, sym, cik, S.iso(et(day, 9, 15)), day.isoformat(),
                                                         day.isoformat(), status))
        self.st.db.execute("UPDATE intents SET program='EVL-NEWS-READ-O1', version=3 WHERE event=?", (ev,))

    def fill(self, day: dt.date, ev: str) -> None:
        self.st.db.execute("INSERT INTO real_fills(program, version, event, side, qty, price, fee, filled_at, band) VALUES("
                           "'EVL-NEWS-READ-O1', 3, ?, 'buy', 1, 20, 0, ?, 'learning')", (ev, S.iso(et(day, 9, 31))))

    def test_a_shadow_skipped_attempt_neither_blocks_a_checkpoint_nor_counts(self):
        self.ledger()
        days = self.days(4)
        for s, day in enumerate(days):
            for k in range(30):
                ev = f"news:pop-{s}-{k}"
                filled = k % 4 != 0
                self.shadow(day, ev, 0.01 if filled else 0.04)
                self.attempt(day, ev, cid=f"c-{s}-{k}", state="filled" if filled else "canceled")
                if filled:
                    self.fill(day, ev)
        pop = C7.attempts(self.st, set())
        g, done, last = C7.checkpoints(pop, [], 0.0)
        self.assertEqual((len(pop), done), (120, [100]))
        self.assertGreater(g, 0.0)
        # an attempt whose shadow was skipped (the auction printed above 1.25 x the previous close): no outcome, ever
        self.shadow(days[0], "news:skipped", 0.0, settled=False, status="skipped:limit")
        self.attempt(days[0], "news:skipped", cid="c-skipped", state="canceled")
        pop2 = C7.attempts(self.st, set())
        self.assertNotIn("news:skipped", [a["event"] for a in pop2], "left out of the population")
        self.assertEqual(C7.checkpoints(pop2, [], 0.0), (g, done, last), "and the checkpoint still falls due")
        # one still waiting on its shadow (planned) does hold the checkpoint until it settles
        self.shadow(days[0], "news:waiting", 0.0, settled=False, status="planned")
        self.attempt(days[0], "news:waiting", cid="c-waiting", state="canceled")
        self.assertEqual(C7.checkpoints(C7.attempts(self.st, set()), [], 0.0)[1], [])

    def test_on_release_1019is_ledger_an_unsent_pick_and_a_refused_order_are_no_attempt(self):
        self.ledger()
        day = self.days(1)[0]
        self.shadow(day, "news:unsent", 0.05)
        self.attempt(day, "news:unsent", cid="unsent:41", sent=0, state="unsent")
        self.shadow(day, "news:refused", 0.05)
        self.attempt(day, "news:refused", cid="c-r", sent=0, state="refused")
        self.shadow(day, "news:later", 0.02)            # refused by the gateway, then sent (A80): one attempt
        self.attempt(day, "news:later", cid="c-l0", sent=0, state="refused", at=et(day, 9, 15, 50))
        self.attempt(day, "news:later", cid="c-l1", state="canceled", at=et(day, 9, 16, 10))
        self.attempt(day, "news:later", cid="c-l2", state="filled", resend=1, at=et(day, 9, 16, 30))
        self.fill(day, "news:later")
        self.shadow(day, "news:missed", 0.03)
        self.attempt(day, "news:missed", cid="c-m", state="canceled")
        got = [(a["event"], a["filled"]) for a in C7.attempts(self.st, set())]
        self.assertEqual(got, [("news:missed", False), ("news:later", True)],
                         "no send, no attempt; a re-send is the same attempt, filled when real_fills holds its buy")


# ------------------------------------------------------------------------------------------------ ROOM and the line
BIRTH = "EVL-B-8K-502"


class TheRoom(TB.EventTest):
    """The REAL book (league/equity/live.py) at DAY's open with PREREG-EVL-7 pinned, an R3 birth registered (an 8k
    birth, an open entry, league/tests/test_events_1019f_births_a85.py's) and the learner's live decision."""

    def setUp(self):
        super().setUp()
        pin(self)
        from league.events import births as BI
        from league.tests.test_events_births import spec

        self.addCleanup(P.load_births, None)
        self.h = self.harness()
        sp = spec(BIRTH, "8k", {"items": ["5.02"]})
        self.h.lane.st.db.execute(
            "INSERT INTO births(id, version, sha, spec, seatable, registered_at, committed_at, received_at, path, "
            "commit_sha, seq, line, why, by, night) VALUES(?, 1, ?, ?, 1, ?, ?, ?, 'docs/births/2026-11-02.jsonl', ?, 0, "
            "'{}', 'x', 'captain', '2026-11-02')",
            (BIRTH, BI.sha(sp), BI.canonical(sp), "2026-11-03T01:00:00Z", "2026-11-03T01:00:00Z",
             "2026-11-03T01:00:00Z", "c" * 40))
        self.birth = P.load_births(self.h.lane.st)[0]

    def live(self, pid: str, picks: list[tuple[str, str, float]], *, named: bool | None = True) -> None:
        T7.TheMoney.live(self, self.h.lane, pid, TB.DAY, picks, named=named)

    def wants_brth(self) -> None:
        """BRTH: an 8-K with item 5.02 (no PREREG program reads it) that the birth takes."""
        TB.earnings(self.h.lane, "b-1", TB.CIK2, "BRTH", items=("5.02",))
        self.h.lane.intent(self.birth, "8k:b-1", "BRTH", TB.CIK2, TB.DAY, TB.DAY)
        self.h.symbol("BRTH", last=17.0, sd=0.02)

    def buys(self) -> list[tuple[str, str]]:
        return [(r["program"], r["symbol"]) for r in self.h.event_intents("buy")]

    def test_a_learner_at_learning_takes_a_name_before_a_birth_at_learning(self):
        self.wants_brth()
        LR.ensure(self.h.lane.st.db)
        self.ready(self.h)
        self.h.tick(9, 15)
        self.assertEqual(self.buys(), [], "the birth's names wait for the learner's part, still running")
        main = self.h.book._event_summary(TB.DAY.isoformat(), "open")
        self.assertIn(BIRTH, main["learners"]["deferred"])
        self.assertEqual([p["symbol"] for p in main["learners"]["deferred"][BIRTH]["picks"]], ["BRTH"],
                         "its picks read as of the auction's own decision")
        self.live(O1, [(TB.CIK2, "BRTH", 16.0)])
        self.h.tick(9, 16)
        self.assertEqual(self.buys(), [(O1, "BRTH")], "ROOM: the learner, after every PREREG row and before R3's births")
        main = self.h.book._event_summary(TB.DAY.isoformat(), "open")
        self.assertEqual(main["programs"][BIRTH].get("skipped"), {"name_given": 1})
        self.assertEqual((main["programs"][O1]["picks"], main["programs"][O1]["planned"]), (1, 1),
                         "the learner's summary in the auction's own row")

    def test_with_no_learner_able_to_take_a_name_the_birth_is_decided_at_once_as_before(self):
        self.wants_brth()
        self.live(O1, [(TB.CIK2, "BRTH", 16.0)])
        self.h.lane.band(O1, "retired", version=1)
        self.ready(self.h)
        self.h.tick(9, 15)
        self.assertEqual(self.buys(), [(BIRTH, "BRTH")])
        self.assertNotIn("learners", self.h.book._event_summary(TB.DAY.isoformat(), "open"))

    def test_at_probe_every_prereg_row_takes_its_names_first_and_the_learner_comes_before_the_bands_births(self):
        """The final text's section 1.9: a learner pick waits for its own live receipt and keeps no room from any
        earlier row, IN EVERY BAND, so a Probe PREREG row is given its names at the auction's own decision (both of
        them, whatever the round-robin would have given the learner), and the learner comes before its band's R3
        birth, which waits for it."""
        read = next(p for p in EB.seatable() if p.id == "EVL-8K-READ-O1")
        for acc, cik, sym in (("o-1", TB.CIK, "ACME"), ("o-2", TB.CIK2, "BETA")):     # (8.01, score 2: no ERN(D))
            self.h.lane.filing(acc, cik, accepted=TB.iso(TB.PRIOR, 17, 0), items=("8.01",))
            self.h.lane.verdict(acc, 2, answered=TB.iso(TB.PRIOR, 17, 5))
            self.h.lane.universe(TB.DAY, sym, cik, 16.0)
            self.h.lane.intent(read, f"8k:{acc}", sym, cik, TB.DAY, TB.DAY)
        TB.earnings(self.h.lane, "b-1", TB.CIK3, "GAMA", items=("5.02",))           # the birth's: GAMA
        self.h.lane.intent(self.birth, "8k:b-1", "GAMA", TB.CIK3, TB.DAY, TB.DAY)
        for sym in ("ACME", "BETA", "GAMA"):
            self.h.symbol(sym, last=17.0, sd=0.02)
        self.h.lane.band(read.id, "probe", version=read.version)
        self.h.lane.band(O1, "probe", version=1)
        self.h.lane.band(BIRTH, "probe", version=1)
        self.live(O1, [(TB.CIK2, "BETA", 16.0), (TB.CIK3, "GAMA", 16.0)])
        self.ready(self.h)
        with mock.patch.object(J7, "STAYS_JUDGED", True):
            self.h.tick(9, 15)
            self.h.tick(9, 16)
        got = sorted(self.buys())
        self.assertEqual(got, sorted([(read.id, "ACME"), (read.id, "BETA"), (O1, "GAMA")]),
                         "the PREREG Probe row's two names; the learner GAMA before the Probe birth")
        main = self.h.book._event_summary(TB.DAY.isoformat(), "open")
        self.assertEqual(list(main["learners"]["deferred"]), [BIRTH], "only the birth waited for the learner")
        self.assertEqual(main["programs"][BIRTH].get("skipped"), {"name_given": 1})
        inst = self.h.book._instance(L.instance_key(O1, 1))
        counts, _ = self.h.book._event_recent(inst, "open", 5)
        self.assertEqual(counts, [2], "A85's reservation reads the learner's real-money picks in the auction's own row")

    def test_no_earlier_rows_wait_includes_the_learners_live_receipt(self):
        """Section 10: the book's wait for the lane's own decision (`EVENT_DECIDE_WAIT_S`, `book.decided`) reads the
        House's receipt only: finished, the auction is decided for every earlier row while the learner's own live
        receipt still runs."""
        st = self.h.lane.st
        self.h.lane.decided(TB.DAY, "open")
        st.start_receipt(LR.live_job(learner(O1), TB.DAY))        # (running: never finished)
        lane = EB.Lane(st.root / S.DB_NAME)
        self.addCleanup(lane.close)
        self.assertTrue(EB.decided(lane, TB.DAY, "open"))
        self.assertEqual(LR.live_state(lane, learner(O1), TB.DAY)["state"], "waiting")
        self.assertTrue(EB.learner_pending(lane, learner(O1), TB.DAY))

    def test_a_waiting_learner_keeps_no_room_from_an_earlier_row(self):
        """While the learner's own live receipt runs, every PREREG row's buy is planned and SENT; only the birth waits."""
        TB.earnings(self.h.lane, "a-1", TB.CIK, "ACME")
        read = next(p for p in EB.seatable() if p.id == "EVL-ERN-READ-O1")
        self.h.lane.intent(read, "8k:a-1", "ACME", TB.CIK, TB.DAY, TB.DAY)
        self.h.symbol("ACME", last=17.0, sd=0.02)
        self.wants_brth()
        self.live(O1, [(TB.CIK2, "BRTH", 16.0)], named=None)        # its live receipt still running
        self.ready(self.h)
        self.h.tick(9, 15)
        self.h.tick(9, 16)
        self.assertEqual(self.buys(), [(read.id, "ACME")])
        self.assertEqual([b["symbol"] for b in self.h.bodies() if b.get("side") == "buy"], ["ACME"], "sent, not held")
        T7.name_live(self.h.lane.st, O1, TB.DAY)
        self.h.tick(9, 17)
        self.assertEqual(self.buys(), [(read.id, "ACME"), (O1, "BRTH")], "then the learner, then nothing for the birth")


class TheLine(TB.EventTest):
    def setUp(self):
        super().setUp()
        pin(self)

    def test_o1s_open_entry_keeps_the_days_close_entries_of_every_earlier_row(self):
        h = self.harness()
        TB.earnings(h.lane, "a-1", TB.CIK, "ACME")
        read = next(p for p in EB.seatable() if p.id == "EVL-ERN-READ-O1")
        h.lane.intent(read, "8k:a-1", "ACME", TB.CIK, TB.DAY, TB.DAY)
        T7.TheMoney.live(self, h.lane, O1, TB.DAY, [(TB.CIK2, "BETA", 16.0)])
        self.ready(h)
        for sym in ("ACME", "BETA"):
            h.symbol(sym, last=17.0, sd=0.02)
        h.tick(9, 15)
        s, adapter = EB.settings(), h.book._event_adapter()
        # A day whose line has room for an open entry with a fixed keep of 32 but not for the close's earlier entries:
        cap = int(s.max_orders_day)
        with mock.patch.object(L, "event_orders_today", lambda rows, day: cap - 40):
            h.tick(9, 16)
            h.tick(9, 17)
        rows = {r["program"]: r for r in h.event_intents("buy")}
        self.assertNotEqual(rows[read.id]["status"], "planned", "the earlier row's entry went")
        self.assertEqual(rows[O1]["status"], "planned")
        self.assertIn("the event kind's day order count", rows[O1]["why"], "the learner's waits on the line")
        self.assertEqual([b["symbol"] for b in h.bodies() if b.get("side") == "buy"], ["ACME"],
                         "a fixed keep of 32 would have sent BETA here (40 free), and its exit at the close with it")
        close_rows = [i for i in h.book._instances(alive=True) if i.kind == L.EVENT_KIND and i.live and not
                      adapter.is_learner(i.family) and adapter.program_of(i.family, i.version).entry_at == "close"]
        self.assertTrue(close_rows)
        [buy] = [r for r in h.event_intents("buy") if r["program"] == O1]
        intent, inst = h.book._intent(int(buy["iid"])), h.book._instance(L.instance_key(O1, 1))
        keep = h.book._event_line_keep(intent, inst, TB.DAY.isoformat(), "open", s, adapter)
        self.assertEqual(keep, 1 + 1 + 2 * sum(s.max_open(i.band) for i in close_rows),
                         "the close's every earlier entry and its A80 re-send, the open's sent buy's re-send, and one "
                         "for the last entry's own exit")
        read_inst = h.book._instance(L.instance_key(read.id, read.version))
        self.assertEqual(h.book._event_line_keep(intent, read_inst, TB.DAY.isoformat(), "open", s, adapter), 0)

    def empty_day(self) -> tuple[TB.Harness, list]:
        """DAY's open with nothing sent all day but EVL-LRN-O1's one live pick (BETA)."""
        h = self.harness()
        T7.TheMoney.live(self, h.lane, O1, TB.DAY, [(TB.CIK2, "BETA", 16.0)])
        self.ready(h)
        h.symbol("BETA", last=17.0, sd=0.02)
        for minute in (15, 16, 17):
            h.tick(9, minute)
        s, adapter = EB.settings(), h.book._event_adapter()
        close_rows = [i for i in h.book._instances(alive=True) if i.kind == L.EVENT_KIND and i.live and not
                      adapter.is_learner(i.family) and adapter.program_of(i.family, i.version).entry_at == "close"]
        return h, close_rows

    def test_across_the_days_auctions_o1_buys_nothing_while_the_ten_close_rows_hold_room(self):
        """THE STATED EFFECT of the reading that trades less (`book.LINE_ACROSS_AUCTIONS`, for the captain's amendment):
        release 1019h's ten close-entry PREREG rows at learning keep 1 + 10 x 2 x 8 = 161 orders of the 150 line on an
        EMPTY day, so O1's one open entry is refused, and the refusal says it is this file's line keep (no buy ahead of
        it waits on the lane's close decision)."""
        self.assertTrue(EB.LINE_ACROSS_AUCTIONS, "the text's reading until the captain amends it")
        h, close_rows = self.empty_day()
        s = EB.settings()
        self.assertEqual((len(close_rows), {i.band for i in close_rows}, s.max_open("learning"), int(s.max_orders_day)),
                         (10, {"learning"}, 8, 150), "release 1019h's rows (invented book, the registry's programs)")
        [buy] = [r for r in h.event_intents("buy") if r["program"] == O1]
        self.assertEqual(buy["status"], "planned")
        self.assertIn("0 of 150 sent", buy["why"])
        self.assertIn("161 for the earlier PREREG rows' orders still to come today", buy["why"])
        self.assertNotIn("buys ahead of it that", buy["why"], "no held buy is named: the keep is its own")
        self.assertEqual([b for b in h.bodies() if b.get("side") == "buy"], [], "nothing sent all day: O1 sends nothing")

    def test_with_the_line_held_inside_the_auction_only_o1_buys_on_an_empty_day(self):
        """The amendment's reading (`LINE_ACROSS_AUCTIONS` False): the keep is the learner's own auction's earlier buys
        not yet sent and their re-sends, so on an empty day O1's open entry goes."""
        with mock.patch.object(EB, "LINE_ACROSS_AUCTIONS", False):
            h, _ = self.empty_day()
            [buy] = [r for r in h.event_intents("buy") if r["program"] == O1]
            intent, inst = h.book._intent(int(buy["iid"])), h.book._instance(L.instance_key(O1, 1))
            keep = h.book._event_line_keep(intent, inst, TB.DAY.isoformat(), "open", EB.settings(),
                                           h.book._event_adapter())
        self.assertNotEqual(buy["status"], "planned", buy["why"])
        self.assertEqual([b["symbol"] for b in h.bodies() if b.get("side") == "buy"], ["BETA"])
        self.assertEqual(keep, 1, "inside its own auction: no earlier buy there, only the entry's own exit")


# --------------------------------------------------------------------------------------------------------- the site
class TheSite(T7.WorldCase):
    """The site's lane rows with the learners pinned (league/site_lane.py, lane_v1 unchanged): each learner has a plain
    name of its own (two rows reading "Event rule" before), and no next look, PREREG-EVL-3's being never theirs."""

    def test_each_learner_has_a_plain_name_of_its_own_and_no_preregevl3_look(self):
        from types import SimpleNamespace

        from league import publish, site_lane

        names = [site_lane.name_of(p) for p in P.PROGRAMS if p.version == 1]
        self.assertEqual(len(set(names)), len(names), "every name unique, the learners' included")
        for pid in (O1, ON):
            name = site_lane.name_of(learner(pid))
            self.assertRegex(name, publish._PROGRAM_NAME)
            self.assertNotEqual(name, site_lane.name_of(SimpleNamespace(id="EVL-X", family="learner-o1")))
        lane = EB.Lane(self.st.root / S.DB_NAME)
        self.addCleanup(lane.close)
        live_sessions(self, self.days(3))
        with mock.patch.object(SN, "next_look_v2", lambda *a, **k: {"k": 1, "events_needed": 80, "events": 6}):
            rows = {r["id"]: r for r in site_lane.read_programs(lane, dt.date(2026, 10, 29))["programs"]}
        self.assertEqual((rows["lrn-o1"]["band"], rows["lrn-o1"]["look"]), ("learning", None))
        self.assertIsNone(rows["lrn-on"]["look"])
        self.assertEqual(rows["lrn-o1"]["name"], "Learner, open to close")
        self.assertIsNotNone(rows["ern-read-o1"]["look"], "an earlier row's look is PREREG-EVL-3's, as before")


# ----------------------------------------------------------------------------------------------- the House's night
from league.events import house as H  # noqa: E402
from league.tests import test_events_house as TH  # noqa: E402


class TheScreenStep(TH.LaneCase):
    """The House's nightly screen (league/events/house.py `_screen`) runs the learners' looks and runs after every
    earlier file's, pinned only; a failure there is the learners' own (the receipt says partial)."""

    def night(self) -> tuple[dt.datetime, dt.date]:
        evening = TH.et("2026-10-20", "20:40")
        self.at(evening)
        with self.store() as st:
            st.set_meta("equity:2026-10-20", "10000.0")
            rid = st.start_receipt("score", now=TH.et("2026-10-20", "20:31"))
            st.finish_receipt(rid, "ok", {}, now=TH.et("2026-10-20", "20:35"))
        return evening, evening.astimezone(C.NY).date()

    def screen(self, calls: list, *, raises: bool = False) -> tuple[str, dict]:
        evening, day = self.night()

        def fake(store, today, *, now=None, draws=None):
            calls.append(today)
            if raises:
                raise RuntimeError("an invented failure")
            return {"written": [{"program": O1, "version": 1, "k": 1022, "decision": None}], "waiting": [],
                    "started": [], "refused": [], "errors": []}
        with self.store() as st, mock.patch.object(J7, "run", fake):
            task = self.lane._nightly(st, evening, day, C.session(st, day), [])
            if task.name == H.COST_BASIS_JOB:
                self.lane._do(st, task)
                task = self.lane._nightly(st, evening, day, C.session(st, day), [])
            self.assertEqual(task.name, "screen")
            return self.lane._do(st, task)

    def test_pinned_the_screen_judges_the_learners_after_every_earlier_look(self):
        pin(self)
        calls: list = []
        status, out = self.screen(calls)
        self.assertEqual(calls, [dt.date(2026, 10, 20)], "once, as of the night's session")
        self.assertEqual(status, "ok")
        self.assertEqual(out["learners"]["written"][0]["k"], 1022)

    def test_a_failing_learner_judge_leaves_the_screen_partial_and_unpinned_it_never_runs(self):
        pin(self)
        calls: list = []
        status, out = self.screen(calls, raises=True)
        self.assertEqual((status, calls), ("partial", [dt.date(2026, 10, 20)]))
        self.assertIn("an invented failure", out["learners"]["error"])

    def test_the_cost_basis_is_owed_only_before_the_nights_screen_and_never_inside_a_decisions_lead(self):
        """Section 2.2 ("after the score and before the screen"), as the House plans it once the learners are pinned:
        a night whose screen is on record (a release before the learners screened it) owes no cost_basis row, so the
        first morning after the deploy computes none; and, like the screen, the row never starts within SCREEN_CLEAR of
        the lane's next decision, so a row owed in the morning never holds that morning's verdicts or decisions."""
        pin(self)
        _, day = self.night()
        morning = TH.et("2026-10-21", "09:12")       # (the open's decision at 09:15 ET: inside SCREEN_CLEAR)
        self.at(morning)
        with self.store() as st:
            self.assertIsNone(self.lane._nightly(st, morning, morning.astimezone(C.NY).date(),
                                                 C.session(st, morning.astimezone(C.NY).date()), []),
                              "inside the open's lead: no cost-basis task (nor the screen)")
        early = TH.et("2026-10-21", "07:31")
        self.at(early)
        with self.store() as st:
            task = self.lane._nightly(st, early, early.astimezone(C.NY).date(), C.session(st, early.astimezone(C.NY).date()), [])
            self.assertEqual(getattr(task, "name", None), H.COST_BASIS_JOB, "clear of a decision: the row is owed")
            rid = st.start_receipt("screen", now=TH.et("2026-10-20", "21:00"))
            st.finish_receipt(rid, "ok", {}, now=TH.et("2026-10-20", "21:01"))
            task = self.lane._nightly(st, early, early.astimezone(C.NY).date(), C.session(st, early.astimezone(C.NY).date()), [])
            self.assertNotEqual(getattr(task, "name", None), H.COST_BASIS_JOB, "the night is screened: no row owed")

    def test_unpinned_the_learner_judge_never_runs(self):
        pin(self, None)
        calls: list = []
        status, out = self.screen(calls)
        self.assertEqual((calls, "learners" in out), ([], False))


if __name__ == "__main__":
    unittest.main()
