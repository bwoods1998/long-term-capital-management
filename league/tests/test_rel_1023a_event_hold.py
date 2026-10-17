"""THE EVENT HOLD (the captain's A25 R1, built in release 1023a; league/swarm/event_hold.py): a program that reads fomc,
cpi or jobs takes no Validation, no look and no seat while a flag it reads is past its table's last row
(league/gym/events.py), in both lanes; no id moves; nothing is retired, refused, spent or sold on it; it lifts by itself
once a calendar release covers the windows. Every family, program and date here is invented, but for the tables' own
last rows."""

from __future__ import annotations

import copy
import datetime as dt
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from league.gym import events
from league.swarm import bands, elane, event_hold
from league.swarm.event_hold import FLAGS, hold, reads
from league.swarm.gate import Gate, run_sha
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import Clock
from league.tests.test_swarm_rounds import RoundCase

EVERY = frozenset(events.EVENT_NAMES)
#: Two days the tests judge on: before the cpi and jobs tables end, and after them (and, below, after fomc's).
SEPT_1 = dt.date(2026, 9, 1)
OCT_16 = dt.date(2026, 10, 16)
DEC_10 = dt.date(2026, 12, 10)


def at(day: dt.date) -> float:
    return dt.datetime(day.year, day.month, day.day, 21, 0, tzinfo=dt.timezone.utc).timestamp()


def program(body: str) -> str:
    """An options-shaped program file whose decide runs `body` (one or more lines)."""
    lines = "\n".join("    " + line for line in body.splitlines())
    return f"NEEDS = {{'roots': ['SPY']}}\nPARAMS = {{}}\n\n\ndef decide(ctx):\n{lines}\n    return []\n"


CPI = program('if ctx.events["cpi"]:\n    return []')
JOBS_NEXT = program('if ctx.events_next.get("jobs", False):\n    return []')
FOMC = program('if ctx.events["fomc"]:\n    return []')
OPEX = program('if ctx.events["monthly_opex"] or ctx.events_next["quarter_end"]:\n    return []')
WALKED = program('if any(ctx.events.values()):\n    return []')
PLAIN = program('x = 1')


class TheReading(unittest.TestCase):
    """WHAT "READS" MEANS: static and conservative; a flag named by a constant is that flag, any other use every flag."""

    def test_a_flag_named_by_a_constant(self):
        cases = {
            CPI: {"cpi"}, JOBS_NEXT: {"jobs"}, FOMC: {"fomc"}, OPEX: {"monthly_opex", "quarter_end"}, PLAIN: set(),
            program('return [] if "cpi" in ctx.events else []'): {"cpi"},
            program('ev = ctx.events\nif ev["jobs"] or ev.get("half_day"):\n    return []'): {"jobs", "half_day"},
            program('a = ctx.events_next\nb = a\nif b["cpi"]:\n    return []'): {"cpi"},
            program('ev: dict = ctx.events\nif ev.get("fomc"):\n    return []'): {"fomc"},
            program('if (ev := ctx.events)["cpi"]:\n    return []'): {"cpi"},
            program('if getattr(ctx, "events")["jobs"]:\n    return []'): {"jobs"},
        }
        for code, want in cases.items():
            self.assertEqual(reads(code), frozenset(want), code)

    def test_every_other_use_reads_every_flag(self):
        for body in ('if any(ctx.events.values()):\n    return []',
                     'for name, on in ctx.events.items():\n    pass',
                     'flags = dict(ctx.events_next)',
                     'k = "cpi"\nif ctx.events[k]:\n    return []',
                     'g = ctx.events.get\nif g("cpi"):\n    return []',
                     'if helper(ctx.events):\n    return []',
                     'if ctx.events:\n    return []',
                     'name = "ev" + "ents"\nif getattr(ctx, name)["x"]:\n    return []',
                     'if vars(ctx)["events"]["cpi"]:\n    return []',
                     'if ctx.__dict__:\n    return []',
                     'a, b = ctx.events, 1'):
            self.assertEqual(reads(program(body)), EVERY, body)
        self.assertEqual(reads("def decide(ctx:\n"), EVERY, "source that does not parse: every flag (fail closed)")
        for bad in (None, b"bytes", 3):
            self.assertEqual(reads(bad), EVERY)

    def test_the_calendar_flags_alone_are_never_held(self):
        self.assertEqual(set(FLAGS), {"fomc", "cpi", "jobs"})
        self.assertTrue({"monthly_opex", "quarter_end", "half_day"}.isdisjoint(FLAGS))
        for day in (SEPT_1, OCT_16, DEC_10, dt.date(2031, 1, 1)):
            self.assertIsNone(hold(OPEX, today=day))
            self.assertIsNone(hold(PLAIN, today=day))


class TheWindowsAndTheTables(unittest.TestCase):
    """WHAT "COVERS ITS WINDOWS" MEANS: each held flag it reads has a table row on or after today."""

    def test_the_tables_own_last_rows(self):
        ends = event_hold.table_ends()
        self.assertEqual(ends, {"fomc": max(events.FOMC), "cpi": max(events.CPI), "jobs": max(events.JOBS)})
        # As this release finds them (A25 R2 extends them; then this test is updated with the tables).
        self.assertEqual(ends, {"fomc": dt.date(2026, 12, 9), "cpi": dt.date(2026, 9, 11), "jobs": dt.date(2026, 9, 4)})

    def test_held_after_a_tables_last_row_never_on_or_before_it(self):
        ends = event_hold.table_ends()
        self.assertIsNone(hold(CPI, today=ends["cpi"]))
        self.assertEqual(hold(CPI, today=ends["cpi"] + dt.timedelta(days=1))["flags"], ["cpi"])
        self.assertIsNone(hold(JOBS_NEXT, today=ends["jobs"]))
        self.assertEqual(hold(JOBS_NEXT, today=ends["jobs"] + dt.timedelta(days=1))["flags"], ["jobs"])
        self.assertIsNone(hold(FOMC, today=OCT_16), "fomc's table covers today")
        self.assertIsNone(hold(FOMC, today=dt.date(2026, 12, 9)))
        self.assertEqual(hold(FOMC, today=DEC_10)["flags"], ["fomc"], "fomc after 2026-12-09")
        self.assertEqual(hold(WALKED, today=OCT_16)["flags"], ["cpi", "jobs"])
        self.assertEqual(hold(WALKED, today=DEC_10)["flags"], ["fomc", "cpi", "jobs"])
        self.assertIsNone(hold(WALKED, today=SEPT_1))

    def test_the_answer_says_the_rule_and_the_tables_dates_only(self):
        held = hold(WALKED, today=OCT_16)
        self.assertEqual(held["ends"], {"cpi": "2026-09-11", "jobs": "2026-09-04"})
        self.assertEqual(held["today"], "2026-10-16")
        self.assertEqual(held["why"], (
            "THE EVENT HOLD (A25 R1): its program reads cpi and jobs, whose tables (league/gym/events.py) end 2026-09-11 "
            "and 2026-09-04, before today: it takes no Validation, no look and no seat until a calendar release covers "
            "its windows (it may still be researched on Train)"))

    def test_a_calendar_release_lifts_it_by_itself(self):
        later = {"fomc": frozenset({dt.date(2027, 12, 15)}), "cpi": frozenset({dt.date(2027, 12, 10)}),
                 "jobs": frozenset({dt.date(2027, 12, 3)})}
        with mock.patch.object(event_hold, "tables", return_value=later):
            self.assertIsNone(hold(WALKED, today=OCT_16))
            self.assertEqual(hold(WALKED, today=dt.date(2027, 12, 11))["flags"], ["cpi", "jobs"])
        with mock.patch.object(event_hold, "tables", return_value={**later, "cpi": frozenset()}):
            self.assertEqual(hold(CPI, today=SEPT_1)["flags"], ["cpi"], "an empty table covers nothing")

    def test_it_never_raises_and_fails_closed(self):
        with mock.patch.object(event_hold, "table_ends", side_effect=RuntimeError("no tables")):
            held = hold(PLAIN, today=OCT_16)
        self.assertEqual(held["flags"], list(FLAGS))
        self.assertIn("THE EVENT HOLD", held["why"])

    def test_the_house_date_is_utc(self):
        self.assertEqual(event_hold.today_utc(at(OCT_16)), OCT_16)
        self.assertEqual(event_hold.today_utc(dt.datetime(2026, 10, 16, 23, 59, tzinfo=dt.timezone.utc).timestamp()),
                         OCT_16)

    def test_the_calendar_sentence_says_the_tables_own_last_rows(self):
        text = event_hold.calendar_text()
        for words in ("cpi reads False on every session after 2026-09-11", "jobs after 2026-09-04",
                      "fomc after 2026-12-09", "until a calendar release adds rows", "all of 2016",
                      "THE EVENT HOLD gives it no Validation, no look and no seat"):
            self.assertIn(words, text)
        with mock.patch.object(event_hold, "table_ends", side_effect=RuntimeError("x")):
            self.assertEqual(event_hold.calendar_text(), "", "left out rather than said wrong")


class TheRecord(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.clock = Clock(at(OCT_16))
        self.store = SwarmStore(Path(tmp.name), clock=self.clock)
        self.addCleanup(self.store.close)
        self.store.add_family({"id": "f", "mechanism": "An invented idea about calls before the release.",
                               "structure": "long_single", "roots": ["SPY"]}, origin="seed")

    def notes(self) -> list[dict]:
        return [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.gate"
                and e["payload"].get("action") == "event_hold"]

    def test_once_a_version_flags_and_stage(self):
        held = hold(WALKED, today=OCT_16)
        self.assertTrue(event_hold.note(self.store, "f", 2, held, stage="validation", clock=self.clock))
        self.assertFalse(event_hold.note(self.store, "f", 2, held, stage="validation", clock=self.clock))
        self.assertTrue(event_hold.note(self.store, "f", 2, held, stage="look", clock=self.clock))
        self.assertTrue(event_hold.note(self.store, "f", 3, held, stage="look", clock=self.clock))
        self.assertEqual([(n["stage"], n["version"], n["flags"]) for n in self.notes()],
                         [("validation", 2, ["cpi", "jobs"]), ("look", 2, ["cpi", "jobs"]), ("look", 3, ["cpi", "jobs"])])
        self.assertEqual(self.store.family("f")["state"][event_hold.STATE_KEY],
                         {"version": 3, "flags": ["cpi", "jobs"], "stage": "look", "at": at(OCT_16)})

    def test_a_record_that_cannot_be_written_never_raises(self):
        self.assertFalse(event_hold.note(None, "f", 1, hold(CPI, today=OCT_16), stage="look"))


# ============================================================================================ the options lanes
class OptionsCase(RoundCase):
    def family(self, fid="a", code=PLAIN, **kw):
        fam = self.store.add_family({"id": fid, "mechanism": "An invented condor idea on the index.",
                                     "structure": "iron_condor", "roots": ["SPY"], **kw}, origin="seed")
        v = self.store.add_version(fam["id"], code, {}, author="seed")
        self.store.update_family(fam["id"], best_version=v["n"])
        return self.store.family(fam["id"])


class TheOptionsValidation(OptionsCase):
    def test_a_held_candidate_is_validated_nothing(self):
        self.family("cpi-reader", CPI)
        self.family("fomc-reader", FOMC)
        self.family("plain", PLAIN)
        out = Tournament(self.store, self.pool, self.settings, clock=Clock(at(OCT_16))).validate(
            self.store.families(alive=True))
        self.assertEqual(sorted(j.family for j in self.pool.jobs), ["fomc-reader", "plain"], "no job for the held one")
        self.assertEqual(out["event_held"], ["cpi-reader"])
        self.assertNotIn("cpi-reader", out["judged"])
        state = self.store.family("cpi-reader")["state"]
        self.assertNotIn("validation_line", state, "no verdict, so no tuition and no gate")
        self.assertFalse(state.get("gate_ready"))
        self.assertEqual(state[event_hold.STATE_KEY]["stage"], "validation")
        self.assertIsNone(self.store.family("cpi-reader").get("retired_at"), "nothing retires on it")

    def test_the_same_program_before_the_tables_end_is_validated(self):
        self.family("cpi-reader", CPI)
        out = Tournament(self.store, self.pool, self.settings, clock=Clock(at(SEPT_1))).validate(
            self.store.families(alive=True))
        self.assertEqual([j.family for j in self.pool.jobs], ["cpi-reader"])
        self.assertNotIn("event_held", out)
        self.assertIn("cpi-reader", out["judged"])

    def test_after_fomcs_last_row_an_fomc_reader_is_held_too(self):
        self.family("fomc-reader", FOMC)
        out = Tournament(self.store, self.pool, self.settings, clock=Clock(at(DEC_10))).validate(
            self.store.families(alive=True))
        self.assertEqual((self.pool.jobs, out["event_held"]), ([], ["fomc-reader"]))


class TheOptionsLook(OptionsCase):
    def ready(self, fid: str, code: str) -> None:
        self.family(fid, code)
        Tournament(self.store, self.pool, self.settings, clock=Clock(at(SEPT_1))).validate(self.store.families(alive=True))
        self.assertTrue(self.store.family(fid)["state"]["gate_ready"])

    def test_it_waits_before_anything_is_paid_and_looks_once_the_tables_cover_it(self):
        self.ready("cpi-reader", CPI)
        out = Gate(self.store, self.pool, self.router, self.settings, clock=Clock(at(OCT_16))).run()
        self.assertEqual(out["event_held"], ["cpi-reader"])
        self.assertEqual(out["looked"], [])
        self.assertEqual([j for j in self.pool.jobs if j.window == "holdout"], [], "no look")
        self.assertEqual(self.sail.bodies, [], "no review, no audit: nothing paid")
        state = self.store.family("cpi-reader")["state"]
        self.assertTrue(state["gate_ready"], "gate_ready stays")
        self.assertTrue(state["gate"].startswith("waiting (THE EVENT HOLD (A25 R1): its program reads cpi"))
        self.assertEqual(state["gate_outcome"]["result"], "waiting", "no bad outcome")
        self.assertNotIn(state["gate_outcome"]["result"], bands.BAD_OUTCOMES)
        self.assertEqual(self.store.refusals("cpi-reader"), [], "no refusal row")
        self.assertEqual(len(self.store.looks()), 0)
        # A second round writes nothing new.
        before = len(self.store.events_after(0, limit=100000))
        Gate(self.store, self.pool, self.router, self.settings, clock=Clock(at(OCT_16))).run()
        self.assertEqual(len(self.store.events_after(0, limit=100000)), before)
        # The tables cover its windows (a calendar release): the gate goes on as before.
        later = {"fomc": frozenset({dt.date(2027, 12, 15)}), "cpi": frozenset({dt.date(2027, 12, 10)}),
                 "jobs": frozenset({dt.date(2027, 12, 3)})}
        self.replies = [{"text": '{"verdict": "pass", "reasons": []}'}] * 2
        with mock.patch.object(event_hold, "tables", return_value=later):
            out = Gate(self.store, self.pool, self.router, self.settings, clock=Clock(at(OCT_16))).run()
        self.assertEqual(out["looked"], [{"family": "cpi-reader", "passed": True}])

    def test_a_program_that_reads_no_held_flag_goes_on(self):
        self.ready("plain", PLAIN)
        self.replies = [{"text": '{"verdict": "pass", "reasons": []}'}] * 2
        out = Gate(self.store, self.pool, self.router, self.settings, clock=Clock(at(OCT_16))).run()
        self.assertEqual(out["looked"], [{"family": "plain", "passed": True}])
        self.assertNotIn("event_held", out)


# ============================================================================================ the equity lanes
ON = {"elane": {"mode": "gate", "universe": ["SPY", "QQQ", "IWM", "DIA"], "birth_share": 0.0}}


def equity_program(body: str) -> str:
    lines = "\n".join("    " + line for line in body.splitlines())
    return ('NEEDS = {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 1}\nPARAMS = {"share": 0.5}\n\n\n'
            f"def decide(ctx):\n{lines}\n    return []\n")


class EquityCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.clock = Clock(at(OCT_16))
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)

    def family(self, fid: str, code: str, *, symbols=("SPY",), lane="beta") -> tuple[dict, dict]:
        fam = self.store.add_family({"id": fid, "mechanism": "An invented overnight idea on the index, for a test.",
                                     "structure": "etf", "roots": list(symbols), "symbols": list(symbols),
                                     "lane": lane}, origin="seed")
        v = self.store.add_version(fam["id"], code, {}, author="seed")
        self.store.update_family(fam["id"], best_version=v["n"])
        return self.store.family(fam["id"]), self.store.version(fam["id"], v["n"])

    def owner(self, day: dt.date = OCT_16) -> SimpleNamespace:
        return SimpleNamespace(store=self.store, settings=ON, clock=Clock(at(day)))

    def events(self, action: str) -> list[dict]:
        return [e["payload"] for e in self.store.events_after(0, limit=100000) if e["payload"].get("action") == action]


class TheEquityValidation(EquityCase):
    def test_refused_before_any_run_and_the_lineage_keeps_its_try(self):
        fam, version = self.family("eq-cpi", equity_program('if ctx.events["cpi"]:\n    return []'))
        self.assertTrue(elane.try_open(self.store, fam, version["n"], ON))
        with mock.patch.object(elane, "_runner", side_effect=AssertionError("no run")):
            out = elane.validate(self.owner(), fam, version)
        self.assertEqual(out["event_hold"], ["cpi"])
        self.assertTrue(out["refused"].startswith("THE EVENT HOLD (A25 R1)"))
        self.assertFalse(out["passed"] or out["entered"])
        state = self.store.family("eq-cpi")["state"]
        self.assertNotIn(elane.TRY_KEY, state, "no try recorded")
        self.assertEqual(elane.lineage_tries(self.store, "eq-cpi"), [])
        self.assertTrue(elane.try_open(self.store, self.store.family("eq-cpi"), version["n"], ON), "its one try is kept")
        self.assertIsNone(elane.lineage_spent(self.store, self.store.family("eq-cpi"), ON), "nothing retires on it")
        self.assertEqual([e["stage"] for e in self.events("event_hold")], ["validation"])

    def test_a_program_that_reads_no_held_flag_is_run(self):
        fam, version = self.family("eq-opex", equity_program('if ctx.events["monthly_opex"]:\n    return []'))
        with mock.patch.object(elane, "_runner", side_effect=RuntimeError("the run was asked")):
            with self.assertRaisesRegex(RuntimeError, "the run was asked"):
                elane.validate(self.owner(), fam, version)


class TheEquityLook(EquityCase):
    def test_it_waits_before_the_sealed_run_once(self):
        fam, version = self.family("eq-jobs", equity_program('if ctx.events_next.get("jobs"):\n    return []'))
        sha = run_sha(version)
        gate = self.owner()
        with mock.patch.object(elane, "_receipt", side_effect=AssertionError("nothing past the hold")):
            self.assertIsNone(elane.look(gate, fam, version, sha))
            state = self.store.family("eq-jobs")["state"]
            self.assertTrue(state["gate"].startswith("waiting (THE EVENT HOLD (A25 R1): its program reads jobs"))
            self.assertEqual(state["gate_outcome"]["result"], "waiting")
            self.assertIsNone(elane.look(gate, self.store.family("eq-jobs"), version, sha))
        self.assertEqual(len(self.events("equity_look_waits")), 1, "its one record is written once")
        self.assertEqual([e["stage"] for e in self.events("event_hold")], ["look"])
        self.assertEqual(self.store.refusals("eq-jobs"), [])
        self.assertFalse(self.store.looked(sha))

    def test_before_the_tables_end_it_goes_on_to_the_receipt(self):
        fam, version = self.family("eq-jobs", equity_program('if ctx.events_next.get("jobs"):\n    return []'))
        with mock.patch.object(elane, "_receipt", side_effect=RuntimeError("the receipt was asked")):
            with self.assertRaisesRegex(RuntimeError, "the receipt was asked"):
                elane.look(self.owner(SEPT_1), fam, version, run_sha(version))


# ============================================================================================ the seats
class SeatCase(EquityCase):
    def banded(self, fid: str, code: str, band: str = "candidate", **kw) -> dict:
        from league.equity import EQUITY_ENGINE_VERSION
        from league.swarm.evaluator import equity_fingerprint

        fam, version = self.family(fid, code, **kw)
        self.store.set_band(fid, "candidate", reason="passed its look (invented)")
        if band != "candidate":
            self.store.set_band(fid, band, reason="a seat (invented)")
        self.store.set_state(fid, banded_version=version["n"], banded_at=at(OCT_16) - 3600.0,
                             banded_evaluator={"engine": EQUITY_ENGINE_VERSION, "equity_sha256": equity_fingerprint(),
                                               "run_sha": run_sha(version)})
        return self.store.family(fid)

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(event_hold, "today_utc", return_value=OCT_16)
        patcher.start()
        self.addCleanup(patcher.stop)
        roster = mock.patch.object(elane, "roster_seats", return_value=6)
        roster.start()
        self.addCleanup(roster.stop)


class TheEquitySeat(SeatCase):
    def test_a_held_candidate_is_seatless_and_has_no_row(self):
        self.banded("eq-cpi", equity_program('if ctx.events["cpi"]:\n    return []'))
        self.banded("eq-plain", equity_program('x = 1'))
        for queued in (False, True):
            rows = bands.read(self.root, lanes=elane.LANES, queued=queued)
            self.assertEqual([r["family"] for r in rows], ["eq-plain"], queued)
        roster = bands.roster(self.root, lanes=elane.LANES)
        self.assertIn("eq-cpi", roster["seatless"])
        self.assertNotIn("eq-cpi", roster["seated"] + roster["waiting"])
        self.assertIn("eq-plain", roster["seated"])
        self.assertEqual(roster["event_held"], ["eq-cpi"])
        self.assertTrue(roster["seatless_why"]["eq-cpi"].startswith("THE EVENT HOLD (A25 R1)"))

    def test_a_held_candidate_takes_no_seat_from_a_clean_one(self):
        fams = [{"id": f"c{i}", "band": "candidate", "structure": "etf", "state": {"banded_at": 100.0 + i}}
                for i in range(3)]
        plain = bands.equity_seating(fams, 2)
        self.assertEqual(plain["seated"], ["c0", "c1"])
        held = bands.equity_seating(fams, 2, held={"c0": "held"})
        self.assertEqual((held["seated"], held["waiting"], held["seatless"]), (["c1", "c2"], [], ["c0"]))
        # A held Probe holder keeps its seat: it is never displaced.
        fams[0]["band"] = "probe"
        kept = bands.equity_seating(fams, 2, held={"c0": "held"})
        self.assertEqual((kept["probe"], kept["seated"], kept["waiting"]), (["c0"], ["c1"], ["c2"]))

    def test_a_held_program_at_probe_keeps_its_seat_and_lots_and_opens_nothing(self):
        fam = self.banded("eq-cpi", equity_program('if ctx.events["cpi"]:\n    return []'), band="probe")
        self.assertEqual(bands.read(self.root, lanes=elane.LANES), [], "no row: the book opens nothing for it")
        code, why = bands.equity_seat_withdrawn(self.root, fam)
        self.assertEqual(code, "held", "opens stop, exits go on, nothing retired or sold")
        self.assertTrue(why.startswith("THE EVENT HOLD (A25 R1)"))
        self.assertEqual(self.store.family("eq-cpi")["band"], "probe", "its band is not moved")
        from league.equity.families import HELD, EquityFamilies

        self.assertEqual(EquityFamilies(self.root).standing("eq-cpi", 1)[0], HELD)

    def test_a_clean_program_is_untouched(self):
        fam = self.banded("eq-plain", equity_program('x = 1'), band="probe")
        self.assertEqual([r["family"] for r in bands.read(self.root, lanes=elane.LANES)], ["eq-plain"])
        self.assertIsNone(bands.equity_seat_withdrawn(self.root, fam))

    def test_it_lifts_once_the_tables_cover_today(self):
        self.banded("eq-cpi", equity_program('if ctx.events["cpi"]:\n    return []'))
        with mock.patch.object(event_hold, "today_utc", return_value=SEPT_1):
            self.assertEqual([r["family"] for r in bands.read(self.root, lanes=elane.LANES, queued=True)], ["eq-cpi"])


class TheOptionsSeat(EquityCase):
    def banded(self, fid: str, code: str, band: str) -> None:
        from league.gym import ENGINE_VERSION
        from league.gym.experiment import CONTRACT_VERSION
        from league.swarm.evaluator import execution_fingerprint

        fam = self.store.add_family({"id": fid, "mechanism": "An invented condor idea on the index.",
                                     "structure": "iron_condor", "roots": ["SPY"]}, origin="seed")
        v = self.store.add_version(fam["id"], code, {}, author="seed")
        self.store.set_band(fid, "candidate", reason="passed its look (invented)")
        if band != "candidate":
            self.store.set_band(fid, band, reason="a seat (invented)")
        self.store.set_state(fid, banded_version=v["n"], banded_at=at(OCT_16) - 3600.0, banded_evaluator={
            "engine": ENGINE_VERSION, "parameter_contract": CONTRACT_VERSION, "execution_sha256": execution_fingerprint(),
            "run_sha": run_sha(v), "holdout_bundle": ENGINE_VERSION + "-x", "validation_bundle": ENGINE_VERSION + "-x"})

    def test_no_row_for_a_held_program_in_a_running_band(self):
        with mock.patch.object(event_hold, "today_utc", return_value=OCT_16):
            self.banded("cpi-candidate", CPI, "candidate")
            self.banded("cpi-probe", CPI, "probe")
            self.banded("plain-probe", PLAIN, "probe")
            self.assertEqual([r["family"] for r in bands.read(self.root)], ["plain-probe"])
        with mock.patch.object(event_hold, "today_utc", return_value=SEPT_1):
            self.assertEqual(sorted(r["family"] for r in bands.read(self.root)),
                             ["cpi-candidate", "cpi-probe", "plain-probe"])

    def test_a_held_candidate_takes_no_roster_seat(self):
        fams = [{"id": f"c{i}", "band": "candidate", "structure": "etf", "state": {"banded_at": 100.0 + i}}
                for i in range(2)]
        with mock.patch.object(bands, "_seat_structure", return_value=True):
            self.assertEqual(bands.waiting(fams, 1), {"c1"})
            self.assertEqual(bands.waiting([f for f in fams if f["id"] != "c0"], 1), set(), "the hold leaves c0 out")


class NoIdMoves(unittest.TestCase):
    def test_the_hold_lives_outside_every_identity(self):
        from league.swarm import evaluator

        self.assertNotIn("league/swarm/event_hold.py", evaluator.EQUITY_GYM_FILES)
        root = Path(__file__).resolve().parents[2]
        for name in ("league/gym", "league/live", "league/equity"):
            self.assertFalse((root / name / "event_hold.py").exists())
        self.assertTrue((root / "league" / "swarm" / "event_hold.py").exists())

    def test_it_never_reads_the_forward_screens_registry(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / "league" / "swarm" / "event_hold.py").read_text()
        for word in ("forward_screen", "fwd1_rule", "registry", "PERMITS"):
            self.assertNotIn(word, source.split('"""', 2)[-1], word)
        screen = (root / "league" / "ops" / "forward_screen.py").read_text()
        self.assertNotIn("event_hold", screen, "FWD1-R's judge reads nothing of the hold")


if __name__ == "__main__":
    unittest.main()


from league.tests import test_ops_stall as stall_tests  # noqa: E402 - the stall job's own fixture


class TheStallJobOwesAHeldFamilyNothing(stall_tests.Base):
    """A family THE EVENT HOLD keeps from Validation (the tournament round's `event_held`) is owed none: the
    `validations` cause never stands on it, so the hold makes no owner step and costs no research day."""

    def test_an_event_held_candidate_is_owed_no_validation(self):
        self.healthy(validation_hours=30)
        self.family("held", best_version=1, best_train=0.5)
        self.assertEqual(self.check("validations")["numbers"]["owed_validation"], 1)
        self.ago(1)
        self.store.event("swarm.tournament", None, {"validation": {"queued": 0, "judged": {}, "errors": {},
                                                                    "event_held": ["held"]}})
        validations = self.check("validations")
        self.assertFalse(validations["stalled"])
        self.assertEqual(validations["numbers"]["owed_validation"], 0)


# ============================================================================================ the review's finding 1
class TheHeldEtfHolderKeepsItsSeat(unittest.TestCase):
    """THE EVENT HOLD AT AN ETF SEAT (the review's finding 1, release 1023a): an event-held ETF program at Probe has no
    row (`bands.read`) and the store says `HELD`; the EquityBook keeps its instance and its lots AND ITS SEAT
    (league/equity/live.py `_held_seats`), so the pool never counts it free, never seats a waiting Candidate into it and
    never holds more than `equity_money.probe.max_programs` live programs; under the seat rule in force and under the
    rollback "first-come" alike. When the hold lifts, the held program's row is back in the seat it never left."""

    HELD_WHY = "THE EVENT HOLD (A25 R1): its program reads cpi, whose table (league/gym/events.py) ends 2026-09-11"

    def setUp(self):
        from league.tests import equity_week as W

        self.W = W
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def decide(self, house, day) -> None:
        house.tick(day, 16, 21)
        house.tick(day, 16, 31)

    def alive(self, house) -> list[str]:
        from league.equity.live import EQUITY_KIND

        return sorted(i.family for i in house.book._instances(alive=True) if i.kind == EQUITY_KIND)

    def cap(self) -> int:
        from league.live import money as M

        return int(M.Table.from_constitution().equity.probe_max_programs)

    def test_a_held_holder_never_frees_its_seat(self):
        from league.tests.equity_design import seat_rule

        W = self.W
        for rule in ("activity-1-free", "first-come"):
            with self.subTest(rule=rule), seat_rule(rule):
                house = W.House(self.tmp / rule, W.ranked_programs(1))
                self.addCleanup(house.close)
                W.invented_week(house.market, through=W.FORTNIGHT_END)
                self.decide(house, W.FRIDAY)
                seated = sorted(r["family"] for r in W.ranked_programs(0))
                self.assertEqual(self.alive(house), seated)
                self.assertEqual(self.cap(), 6)
                house.families.held["bred-a-hold3"] = self.HELD_WHY
                for day in (W.MONDAY, W.TUESDAY):
                    for hh, mm in ((8, 31), (16, 21), (16, 31), (17, 1), (18, 1)):   # the seating pass every minute
                        house.tick(day, hh, mm)
                        alive = self.alive(house)
                        self.assertLessEqual(len(alive), self.cap(), f"{day} {hh}:{mm}: the pool never exceeds its seats")
                        self.assertIn("bred-a-hold3", alive, "nothing is retired on the hold")
                        self.assertNotIn("bred-e-wait", alive, "nobody is seated into the held seat")
                    inst = house.book._instance("bred-a-hold3@1:r")
                    self.assertIsNone(inst.retired_at)
                    if rule != "first-come":
                        plan = house.book.seats()
                        self.assertEqual(plan["held_seats"], ["bred-a-hold3"])
                        self.assertEqual(plan["seats"], 6, "the plan says the pool's seats, the held one among them")
                        self.assertEqual([w["family"] for w in plan["waiting"]], ["bred-e-wait"])
                        self.assertNotIn("bred-a-hold3", [h["family"] for h in plan["holders"]],
                                         "a held holder is in no seat plan, so it is never asked to yield")
                    self.assertTrue(any("seats_held" in out and "bred-a-hold3" in out["seats_held"]
                                        for _, out in house.ticks), "said: opens stop, exits go on")
                house.families.held.clear()                                            # the hold lifts
                day = W.sessions_from(W.TUESDAY, 2)[1]
                house.tick(day, 8, 31)
                self.decide(house, day)
                self.assertEqual(self.alive(house), seated, "its row is back in the seat it never left")
                if rule != "first-come":
                    plan = house.book.seats()
                    self.assertNotIn("held_seats", plan)
                    self.assertIn("bred-a-hold3", [h["family"] for h in plan["holders"]])

    def test_only_a_held_word_keeps_a_seat_with_no_row(self):
        """Any other alive ETF instance with no row is counted as main counted it (`_held_seats` names none)."""
        from league.equity.live import POOL_ETF

        W = self.W
        house = W.House(self.tmp / "h", W.ranked_programs(0))
        self.addCleanup(house.close)
        W.invented_week(house.market, through=W.FORTNIGHT_END)
        self.decide(house, W.FRIDAY)
        rows = house.families.read()
        self.assertEqual(house.book._held_seats(POOL_ETF, rows), [])
        house.families.hidden.add("bred-a-hold3")                          # no row; the store says "live"
        rows = house.families.read()
        self.assertEqual(house.book._held_seats(POOL_ETF, rows), [])
        house.families.hidden.clear()
        house.families.held["bred-a-hold3"] = self.HELD_WHY
        rows = house.families.read()
        self.assertEqual(house.book._held_seats(POOL_ETF, rows), ["bred-a-hold3"])

    def test_the_real_reader_keeps_the_seat_held(self):
        """THE REAL READER (`EquityFamilies` over a `SwarmStore`): a seated program whose banded version reads cpi is
        seated while the table covers today and held once it does not: no row, `standing` HELD, the seat kept."""
        W = self.W
        reader = W.HOLD3.replace("    if ctx.positions or ctx.orders:\n",
                                 "    if ctx.events.get(\"cpi\"):\n        return []\n"
                                 "    if ctx.positions or ctx.orders:\n")
        self.assertEqual(reads(reader), frozenset({"cpi"}))
        rows = W.ranked_programs(1)
        rows[0] = {**rows[0], "code": reader}
        self.assertEqual(rows[0]["family"], "bred-a-hold3")
        today = {"day": SEPT_1}
        with mock.patch.object(event_hold, "today_utc", side_effect=lambda now=None: today["day"]):
            house = W.House(self.tmp / "store", rows, reader="store")
            self.addCleanup(house.close)
            W.invented_week(house.market, through=W.FORTNIGHT_END)
            self.decide(house, W.FRIDAY)
            seated = sorted(r["family"] for r in W.ranked_programs(0))
            self.assertEqual(self.alive(house), seated)
            today["day"] = OCT_16                                                # past cpi's last row
            self.assertNotIn("bred-a-hold3", [r["family"] for r in house.families.read()], "no row")
            from league.equity.families import HELD

            self.assertEqual(house.families.standing("bred-a-hold3", 1)[0], HELD)
            for day in (W.MONDAY, W.TUESDAY):
                house.tick(day, 8, 31)
                self.decide(house, day)
                house.tick(day, 17, 1)
                alive = self.alive(house)
                self.assertLessEqual(len(alive), 6)
                self.assertIn("bred-a-hold3", alive)
                self.assertNotIn("bred-e-wait", alive)
            self.assertEqual(house.book.seats().get("held_seats"), ["bred-a-hold3"])
