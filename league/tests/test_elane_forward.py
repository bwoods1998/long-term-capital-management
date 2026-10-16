"""The forward screen's seat path, the swarm's half (league/swarm/elane_forward.py): BUILT AND OFF. With the switch
off nothing acts; on, a FWD1-judged lineage takes no sealed Validation try (but an index-only case-N lineage before the
close of its FWD1_START session: L5, A48), an ETF pass becomes a Candidate through the roster's own machinery (one live
forward seat a mechanism cell), and a panel pass is made eligible only (its seat pool is E4 step two's). The store is a
fake; every row is invented."""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from league.equity import EQUITY_ENGINE_VERSION, schedule
from league.swarm import elane, elane_forward as EF
from league.swarm.evaluator import equity_fingerprint
from league.swarm.gate import run_sha

ON = {"elane": {"fwd1": {"mode": "record", "seats": "on"}}}
OFF = {"elane": {"fwd1": {"mode": "record", "seats": "off"}}}


class FakeStore:
    def __init__(self, root: Path):
        self.root = root
        self.fams: dict[str, dict] = {}
        self.versions: dict[tuple[str, int], dict] = {}
        self.events: list[tuple] = []
        self.bands: list[tuple] = []

    def add(self, fid: str, *, structure: str = "etf", band: str = "gym", lineage: str | None = None, state=None,
            retired: bool = False, symbols: list[str] | None = None) -> dict:
        spec = {"lane": "equity", "agenda": "trend", **({"symbols": list(symbols)} if symbols is not None else {})}
        self.fams[fid] = {"id": fid, "structure": structure, "band": band, "retired_at": "x" if retired else None,
                          "spec": spec, "lineage": lineage, "state": dict(state or {})}
        self.versions[(fid, 1)] = {"n": 1, "sha": f"{fid}-sha", "params": {}, "code": "PARAMS = {}\n"}
        return self.fams[fid]

    def family(self, fid):
        return self.fams.get(str(fid))

    def families(self, *, alive=None, lanes=None):
        return [f for f in self.fams.values() if not (alive and f["retired_at"])]

    def version(self, fid, n):
        return None if n is None else self.versions.get((str(fid), int(n)))

    def set_state(self, fid, **values):
        self.fams[fid]["state"].update(values)
        return self.fams[fid]["state"]

    def set_band(self, fid, band, *, reason):
        old = self.fams[fid]["band"]
        self.fams[fid]["band"] = band
        self.bands.append((fid, band, reason))
        return old

    def event(self, kind, fid, payload):
        self.events.append((kind, fid, dict(payload)))
        return len(self.events)

    def atomic(self):
        return contextlib.nullcontext()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = FakeStore(self.root)
        self.engine = f"{EQUITY_ENGINE_VERSION}+{equity_fingerprint()[:12]}+fwd-1"

    def tearDown(self):
        self.tmp.cleanup()

    def permit(self, rows: dict):
        (self.root / EF.PERMITS).write_text(json.dumps({"version": EF.PERMITS_VERSION, "screen": "FWD1-R",
                                                       "receipt": "c" * 64, "start": "2026-10-16", "at": "x",
                                                       "lineages": rows}))

    def passed(self, fid: str, *, cell: str = "equity / trend / index", typ: str = "ETF", engine: str | None = None):
        return {"status": "pass", "type": typ, "case": "N", "cell": cell, "family": fid, "version": 1,
                "run_sha": run_sha(self.store.versions[(fid, 1)]), "k": 10, "weak": typ == "ETF",
                "engine": engine or self.engine, "words": "FWD1-R forward screen (ETF, case N): passed at checkpoint 10"}

    def gate(self, settings=ON):
        return types.SimpleNamespace(store=self.store, settings=settings, clock=lambda: 1000.0)


class TheSwitch(Base):
    def test_off_nothing_acts(self):
        fam = self.store.add("f1")
        self.permit({"equity:f1": self.passed("f1")})
        self.assertIsNone(EF.try_refused(self.store, fam, OFF))
        self.assertIsNone(EF.try_refused(self.store, fam, {}))
        self.assertEqual(EF.step(self.gate(OFF)), {})
        self.assertEqual(fam["band"], "gym")
        self.assertFalse(EF.seats_on({"elane": {"fwd1": {"seats": True}}}))   # only the word "on" turns it on

    def test_policy_ships_it_off(self):
        policy = json.loads((Path(__file__).resolve().parents[2] / "league" / "swarm" / "policy.json").read_text())
        self.assertEqual(policy["elane"]["fwd1"]["seats"], "off")
        self.assertFalse(EF.seats_on(policy))


class TheSealedTry(Base):
    def test_a_judged_lineage_takes_no_sealed_try(self):
        fam = self.store.add("f1")
        for status in EF.JUDGED:
            self.permit({"equity:f1": {"status": status}})
            with self.subTest(status=status):
                self.assertEqual(EF.try_refused(self.store, fam, ON), EF.REFUSED)
                self.assertFalse(elane.try_open(self.store, fam, 1, ON))
        for status in ("void", "ineligible"):
            self.permit({"equity:f1": {"status": status}})
            self.assertIsNone(EF.try_refused(self.store, fam, ON))
        self.permit({})
        self.assertIsNone(EF.try_refused(self.store, fam, ON))

    def test_a_family_of_a_named_lineage(self):
        fam = self.store.add("f2", lineage="momentum")
        self.permit({"equity:momentum": {"status": "pending"}})
        self.assertEqual(EF.lineage_of(self.store, fam), "equity:momentum")
        self.assertEqual(EF.try_refused(self.store, fam, ON), EF.REFUSED)

    def test_an_unreadable_file_fails_closed(self):
        fam = self.store.add("f1")
        (self.root / EF.PERMITS).write_text("{not json")
        self.assertEqual(EF.try_refused(self.store, fam, ON), EF.UNREADABLE)
        (self.root / EF.PERMITS).write_text(json.dumps({"version": 99, "lineages": {}}))
        self.assertEqual(EF.try_refused(self.store, fam, ON), EF.UNREADABLE)
        (self.root / EF.PERMITS).unlink()
        self.assertIsNone(EF.try_refused(self.store, fam, ON))     # no file yet: nothing judged


#: L5's invented FWD1_START: Monday Oct 19, 2026, a full session (its close 16:00 New York, 20:00Z), the first forward
#: day of a lineage registered after the pin; the pin's first judged session (the file's top-level "start") is Friday
#: Oct 16, as `Base.permit` writes it.
START = "2026-10-19"
PIN_START = "2026-10-16"
CLOSE = schedule.moments(dt.date(2026, 10, 19)).close_at
#: The permit file's top-level "start" left out (`TheIndexLineageBeforeItsFirstForwardDay.permit`).
ABSENT = object()


class TheIndexLineageBeforeItsFirstForwardDay(Base):
    """L5 (A48): an index-only case-N lineage the file lists pending keeps its S2 try, for the row's own family and a
    start after the pin's, until the close of its FWD1_START session (the judge then voids it:
    league/tests/test_forward_screen.py `TheIndexLineageUntried`); any doubt keeps the refusal (fail closed)."""

    def permit(self, rows: dict, *, pin=PIN_START):
        doc = {"version": EF.PERMITS_VERSION, "screen": "FWD1-R", "receipt": "c" * 64, "start": pin, "at": "x",
               "lineages": rows}
        if pin is ABSENT:
            del doc["start"]
        (self.root / EF.PERMITS).write_text(json.dumps(doc))

    def row(self, **over):
        return {"status": "pending", "type": "ETF", "case": "N", "cell": "equity / trend / index", "family": "f1",
                "version": 1, "start": START, "run_sha": None, "k": None, "weak": None, "engine": None, "words": None,
                **over}

    def index(self, fid: str = "f1", **kw) -> dict:
        return self.store.add(fid, symbols=["SPY", "QQQ"], **kw)

    def test_the_close_is_new_yorks_four_oclock(self):
        self.assertEqual(CLOSE, dt.datetime(2026, 10, 19, 20, 0, tzinfo=dt.timezone.utc).timestamp())

    def test_exempt_before_the_close_of_its_start(self):
        fam = self.index()
        self.permit({"equity:f1": self.row()})
        for now in (CLOSE - 86400.0 * 4, CLOSE - 3600.0, CLOSE - 1.0):
            with self.subTest(now=now):
                self.assertTrue(EF.untried(self.store, fam, self.row(), pin_start=PIN_START, now=now))
                self.assertIsNone(EF.try_refused(self.store, fam, ON, now=now))
        self.assertFalse(EF.untried(self.store, fam, self.row(), now=CLOSE - 3600.0))   # no pin start given
        self.assertEqual(EF.permit_file(self.root), ({"equity:f1": self.row()}, PIN_START))   # one parse, both halves
        self.assertEqual(EF.permits(self.root), {"equity:f1": self.row()})                   # its shape kept

    def test_refused_at_and_after_the_close(self):
        fam = self.index()
        self.permit({"equity:f1": self.row()})
        for now in (CLOSE, CLOSE + 1.0, CLOSE + 86400.0 * 3):
            with self.subTest(now=now):
                self.assertEqual(EF.try_refused(self.store, fam, ON, now=now), EF.REFUSED)

    def test_refused_unless_its_start_is_after_the_pins(self):
        """FWD1_START = max(first_day, the pin's start): only a start after the pin's is the lineage's own first
        forward day (one registered before the pin has forward days in the record already)."""
        fam = self.index()
        own_close = schedule.moments(dt.date(2026, 10, 16)).close_at
        for start in ("2026-10-16", "2026-10-15"):                  # at the pin's start, and before it
            self.permit({"equity:f1": self.row(start=start)})
            with self.subTest(start=start):
                self.assertEqual(EF.try_refused(self.store, fam, ON, now=own_close - 86400.0 * 2), EF.REFUSED)
        for pin in (ABSENT, None, "", "20261016", "2026-10-16T00:00:00", 20261016, "2026-10-20"):
            self.permit({"equity:f1": self.row()}, pin=pin)
            with self.subTest(pin="absent" if pin is ABSENT else pin):
                self.assertEqual(EF.try_refused(self.store, fam, ON, now=CLOSE - 3600.0), EF.REFUSED)
        self.permit({"equity:f1": self.row()}, pin="2026-10-15")      # a start after the pin's: exempt
        self.assertIsNone(EF.try_refused(self.store, fam, ON, now=CLOSE - 3600.0))

    def test_refused_for_a_sibling_family_of_the_lineage(self):
        """The judge's void reads the families of the lineage's registry rows: the exemption is the representative's
        own family (the row's), never a sibling the registry may not have taken yet."""
        rep = self.index()
        sibling = self.index("f1b", lineage="f1")
        self.assertEqual(EF.lineage_of(self.store, sibling), "equity:f1")
        self.permit({"equity:f1": self.row()})
        early = CLOSE - 3600.0
        self.assertIsNone(EF.try_refused(self.store, rep, ON, now=early))
        self.assertEqual(EF.try_refused(self.store, sibling, ON, now=early), EF.REFUSED)
        for family in (None, "", "f1b "):
            self.permit({"equity:f1": self.row(family=family)})
            with self.subTest(family=family):
                self.assertEqual(EF.try_refused(self.store, rep, ON, now=early), EF.REFUSED)
        self.assertFalse(EF.untried(self.store, {**rep, "id": None}, self.row(family=None), pin_start=PIN_START,
                                    now=early))

    def test_the_stores_clock_when_no_time_is_given(self):
        fam = self.index()
        self.permit({"equity:f1": self.row()})
        self.store.clock = lambda: CLOSE - 60.0
        self.assertIsNone(EF.try_refused(self.store, fam, ON))
        self.store.clock = lambda: CLOSE
        self.assertEqual(EF.try_refused(self.store, fam, ON), EF.REFUSED)
        for bad in (lambda: float("nan"), lambda: "soon"):
            self.store.clock = bad
            self.assertEqual(EF.try_refused(self.store, fam, ON), EF.REFUSED)    # a clock that cannot be read
        del self.store.clock
        with mock.patch.object(EF.time, "time", return_value=CLOSE - 60.0):
            self.assertIsNone(EF.try_refused(self.store, fam, ON))              # no store clock: the wall's
        self.assertEqual(EF.try_refused(self.store, fam, ON, now=float("inf")), EF.REFUSED)

    def test_refused_with_no_start_or_one_that_cannot_be_read(self):
        fam = self.index()
        early = CLOSE - 3600.0
        row = self.row()
        del row["start"]                                   # a file of the earlier job: refused as before
        for bad in (row, self.row(start=None), self.row(start=""), self.row(start="2026-19-10"),
                    self.row(start="20261019"), self.row(start="2026-10-19T00:00:00"), self.row(start=20261019),
                    self.row(start=["2026-10-19"])):
            self.permit({"equity:f1": bad})
            with self.subTest(start=bad.get("start", "absent")):
                self.assertEqual(EF.try_refused(self.store, fam, ON, now=early), EF.REFUSED)

    def test_refused_when_the_start_is_no_session_or_the_calendar_cannot_answer(self):
        fam = self.index()
        self.assertIsNone(schedule.moments(dt.date(2026, 10, 17)))      # a Saturday
        self.assertIsNone(schedule.moments(dt.date(2200, 1, 2)))        # past the computed calendar's years
        for start in ("2026-10-17", "2200-01-02"):
            self.permit({"equity:f1": self.row(start=start)})
            with self.subTest(start=start):
                self.assertEqual(EF.try_refused(self.store, fam, ON, now=CLOSE - 86400.0 * 4), EF.REFUSED)
        self.permit({"equity:f1": self.row()})
        with mock.patch.object(schedule, "moments", side_effect=RuntimeError("the calendar")):
            self.assertEqual(EF.try_refused(self.store, fam, ON, now=CLOSE - 3600.0), EF.REFUSED)
        with mock.patch.object(schedule, "moments", return_value=None):
            self.assertEqual(EF.try_refused(self.store, fam, ON, now=CLOSE - 3600.0), EF.REFUSED)

    def test_refused_for_another_case_or_type_and_for_a_verdict(self):
        fam = self.index()
        early = CLOSE - 3600.0
        for over in ({"case": "XS1"}, {"case": None}, {"type": "PANEL"}, {"type": None}, {"status": "pass"},
                     {"status": "fail"}):
            self.permit({"equity:f1": self.row(**over)})
            with self.subTest(**{k: str(v) for k, v in over.items()}):
                self.assertEqual(EF.try_refused(self.store, fam, ON, now=early), EF.REFUSED)
        for status in ("void", "ineligible", "stopped", "stalled", "superseded"):
            self.permit({"equity:f1": self.row(status=status)})
            self.assertIsNone(EF.try_refused(self.store, fam, ON, now=CLOSE + 86400.0))   # its sealed path, as before

    def test_refused_when_forward_only_or_a_panel(self):
        early = CLOSE - 3600.0
        for fid, symbols in (("xlk", ["XLK"]), ("spy-xlk", ["SPY", "XLK"]), ("none", [])):
            fam = self.store.add(fid, symbols=symbols)
            self.permit({f"equity:{fid}": self.row(family=fid)})
            with self.subTest(family=fid):
                self.assertTrue(elane.forward_only(fam))
                self.assertEqual(EF.try_refused(self.store, fam, ON, now=early), EF.REFUSED)
        fam = self.store.add("unread")                     # no symbols at all: forward-only (fail closed)
        self.permit({"equity:unread": self.row(family="unread")})
        self.assertEqual(EF.try_refused(self.store, fam, ON, now=early), EF.REFUSED)
        fam = self.index("idx")
        self.permit({"equity:idx": self.row(family="idx")})
        with mock.patch.object(elane, "forward_only", return_value=True):          # R-SEC asked inside the exemption
            self.assertEqual(EF.try_refused(self.store, fam, ON, now=early), EF.REFUSED)
        with mock.patch.object(elane, "forward_only", side_effect=RuntimeError("unread")):
            self.assertEqual(EF.try_refused(self.store, fam, ON, now=early), EF.REFUSED)
        self.assertIsNone(EF.try_refused(self.store, fam, ON, now=early))
        panel = self.store.add("p1", structure="panel", symbols=["SPY"])
        self.permit({"equity:p1": self.row(family="p1")})
        self.assertEqual(EF.try_refused(self.store, panel, ON, now=early), EF.REFUSED)

    def test_seats_off_unchanged(self):
        fam = self.index()
        for row in (self.row(), self.row(status="pass"), self.row(start=None)):
            self.permit({"equity:f1": row})
            for now in (CLOSE - 3600.0, CLOSE + 3600.0):
                self.assertIsNone(EF.try_refused(self.store, fam, OFF, now=now))
                self.assertIsNone(EF.try_refused(self.store, fam, {}, now=now))

    def test_an_unreadable_file_still_fails_closed(self):
        fam = self.index()
        (self.root / EF.PERMITS).write_text("{not json")
        self.assertEqual(EF.try_refused(self.store, fam, ON, now=CLOSE - 3600.0), EF.UNREADABLE)
        self.assertIsNone(EF.permit_file(self.root))
        (self.root / EF.PERMITS).unlink()
        self.assertEqual(EF.permit_file(self.root), ({}, None))
        self.assertIsNone(EF.try_refused(self.store, fam, ON, now=CLOSE - 3600.0))   # no file yet: nothing judged


class TheSeat(Base):
    def test_an_etf_pass_becomes_a_candidate_through_the_roster(self):
        fam = self.store.add("f1")
        self.permit({"equity:f1": self.passed("f1")})
        out = EF.step(self.gate())
        self.assertEqual(out["seated"], ["f1"])
        self.assertEqual(fam["band"], "candidate")
        state = fam["state"]
        self.assertEqual(state["banded_version"], 1)
        self.assertEqual(state["banded_at"], 1000.0)
        self.assertEqual(state["banded_evaluator"], {"engine": EQUITY_ENGINE_VERSION, "equity_sha256": equity_fingerprint(),
                                                     "run_sha": run_sha(self.store.versions[("f1", 1)])})
        self.assertTrue(EF.eligible(state))
        self.assertTrue(state[EF.STATE_KEY]["seated"])
        self.assertIn("FWD1-R", self.store.bands[0][2])
        self.assertEqual(EF.step(self.gate()), {"seated": [], "eligible": [], "waits": {}})   # once

    def test_one_live_forward_seat_a_mechanism_cell(self):
        self.store.add("f1")
        other = self.store.add("f2")
        third = self.store.add("f3")
        self.permit({"equity:f1": self.passed("f1"), "equity:f2": self.passed("f2"),
                     "equity:f3": self.passed("f3", cell="equity / reversal / index")})
        out = EF.step(self.gate())
        self.assertEqual(sorted(out["seated"]), ["f1", "f3"])
        self.assertIn("one live forward seat a mechanism cell", out["waits"]["f2"])
        self.assertEqual(other["band"], "gym")
        self.assertEqual(third["band"], "candidate")
        self.store.fams["f1"]["retired_at"] = "later"               # the cell's seat is free again
        self.assertEqual(EF.step(self.gate())["seated"], ["f2"])

    def test_a_panel_pass_is_eligible_only(self):
        fam = self.store.add("p1", structure="panel")
        self.permit({"equity:p1": self.passed("p1", typ="PANEL")})
        out = EF.step(self.gate())
        self.assertEqual(out["eligible"], ["p1"])
        self.assertEqual(fam["band"], "gym")                         # no panel band moves: the pool is step two's
        self.assertTrue(EF.eligible(fam["state"]))
        self.assertFalse(fam["state"][EF.STATE_KEY]["seated"])
        self.assertEqual(self.store.bands, [])

    def test_two_panel_passes_in_one_cell_one_seat(self):
        """AT MOST ONE LIVE FORWARD SEAT A MECHANISM CELL for panel passes too (the review's major): the second pass of
        a cell is not made eligible while the first holds the cell, and the one call a pool asks refuses it."""
        cell = "equity / momentum / panel:sp500"
        p1 = self.store.add("p1", structure="panel")
        p2 = self.store.add("p2", structure="panel")
        self.permit({"equity:p1": self.passed("p1", typ="PANEL", cell=cell),
                     "equity:p2": self.passed("p2", typ="PANEL", cell=cell)})
        out = EF.step(self.gate())
        self.assertEqual(out["eligible"], ["p1"])
        self.assertIn("one live forward seat a mechanism cell: p1", out["waits"]["p2"])
        self.assertFalse(EF.eligible(p2["state"]))
        self.assertIsNone(EF.seat_refused(self.store, p1, ON))         # the pool may seat p1 ...
        self.assertIsNotNone(EF.seat_refused(self.store, p2, ON))      # ... and never p2
        self.assertTrue(EF.mark_seated(self.store, "p1", ON))          # the pool seats p1 and records it
        self.store.set_band("p1", "probe", reason="the panel pool's seat (a test's)")
        self.assertTrue(p1["state"][EF.STATE_KEY]["seated"])
        self.assertIn("one live forward seat a mechanism cell: p1", EF.step(self.gate())["waits"]["p2"])
        self.store.set_band("p1", "gym", reason="demoted by the money rows (a test's)")   # the seat is free again
        self.assertEqual(EF.step(self.gate())["eligible"], ["p2"])
        self.assertIsNone(EF.seat_refused(self.store, p2, ON))
        self.assertIsNotNone(EF.seat_refused(self.store, p2, OFF))     # the switch off: nothing seats

    def test_a_panel_pass_of_case_xs1_takes_no_seat(self):
        """A34: a panel program's only path to money is FWD1-R case N."""
        fam = self.store.add("p1", structure="panel")
        self.permit({"equity:p1": {**self.passed("p1", typ="PANEL"), "case": "XS1"}})
        out = EF.step(self.gate())
        self.assertEqual(out["eligible"], [])
        self.assertIn("A34", out["waits"]["p1"])
        self.assertFalse(EF.eligible(fam["state"]))
        fam["state"][EF.STATE_KEY] = {"eligible": True, "type": "PANEL", "case": "XS1", "lineage": "equity:p1"}
        self.assertIn("A34", EF.seat_refused(self.store, fam, ON))     # however its state was written

    def test_the_one_call_holds_for_an_etf_pass_and_reads_the_permit_file(self):
        fam = self.store.add("f1")
        self.permit({"equity:f1": self.passed("f1")})
        EF.step(self.gate())
        self.assertIsNone(EF.seat_refused(self.store, fam, ON))
        self.permit({"equity:f1": {"status": "pending"}})               # the file no longer lists its pass
        self.assertIn("permit file", EF.seat_refused(self.store, fam, ON))
        (self.root / EF.PERMITS).write_text("{not json")
        self.assertEqual(EF.seat_refused(self.store, fam, ON), EF.UNREADABLE)
        self.assertFalse(EF.mark_seated(self.store, "f1", ON))

    def test_it_waits_on_what_it_cannot_prove(self):
        self.store.add("f1")
        row = self.passed("f1")
        self.permit({"equity:f1": {**row, "run_sha": "0" * 64}})
        self.assertIn("run sha", EF.step(self.gate())["waits"]["f1"])
        self.permit({"equity:f1": self.passed("f1", engine=f"{EQUITY_ENGINE_VERSION}+000000000000+fwd-1")})
        self.assertIn("identity moved", EF.step(self.gate())["waits"]["f1"])
        self.store.add("f9", band="probe")
        self.permit({"equity:f9": self.passed("f9")})
        self.assertIn("probe", EF.step(self.gate())["waits"]["f9"])
        self.store.add("f8", retired=True)
        self.permit({"equity:f8": self.passed("f8")})
        self.assertEqual(EF.step(self.gate())["seated"], [])

    def test_the_seat_rounds_call_it(self):
        """league/swarm/gate.py `equity_round` asks the seat path once a round, after the seat counts."""
        import inspect

        from league.swarm import gate

        source = inspect.getsource(gate.Gate.equity_round)
        self.assertIn("elane_forward.step(self)", source)
        self.assertLess(source.index("seat_backfill"), source.index("elane_forward.step"))



#: POOL1 (A55a): the pooled screen's switch on (policy.json ships "record") and rolled back ("off").
POOL_ON = {"elane": {"fwd1": {"mode": "record", "seats": "on"}, "pool": {"mode": "record", "seats": "off"}}}
POOL_ROLLED = {"elane": {"fwd1": {"mode": "record", "seats": "on"}, "pool": {"mode": "off", "seats": "off"}}}
POOL_FWD1_OFF = {"elane": {"fwd1": {"mode": "record", "seats": "off"}, "pool": {"mode": "record", "seats": "off"}}}


class ThePoolRoute(Base):
    """POOL1's ROUTE REFUSAL (the module docstring, 4; PREREG-POOL1 7.2 and 11 P1 item 4): a lineage the pooled
    screen's permit file lists on its POOL route or hold list takes no FWD1-R seat and no sealed try, whatever
    `elane.pool.mode` and `elane.fwd1.seats` say, for good under the receipt; the file failing closed refuses every
    forward-only ETF pass and every lineage FWD1 lists as judged; `one_a_cell` counts a pooled seat."""

    def pool(self, routes=(), holds=(), *, words=None, raw=None):
        if raw is not None:
            (self.root / EF.POOL_PERMITS).write_text(raw)
            return
        cell = "trend_momentum/sectors"
        doc = {"version": EF.POOL_PERMITS_VERSION, "screen": "POOL1", "receipt": "d" * 64, "clock": "2026-10-26",
               "at": "x", "routes": {lin: {"cell": cell, "cluster": "trend_momentum"} for lin in routes},
               "holds": list(holds), "units": {cell: {"cluster": "trend_momentum", "word": words or "pending"}},
               "lineages": {}, "eligible": []}
        (self.root / EF.POOL_PERMITS).write_text(json.dumps(doc))

    def sector(self, fid: str = "f1", **kw) -> dict:
        return self.store.add(fid, symbols=["XLK"], **kw)

    def test_the_name_is_the_jobs(self):
        from league.ops import pool_screen

        self.assertEqual(EF.POOL_PERMITS, pool_screen.PERMITS)
        self.assertEqual(EF.POOL_PERMITS_VERSION, pool_screen.PERMITS_VERSION)

    def test_step_makes_no_candidate_of_a_pool_route_lineages_pass(self):
        for settings in (POOL_ON, POOL_ROLLED, ON):                 # whatever elane.pool.mode says (absent: off)
            store_fam = self.sector(f"f{len(self.store.fams)}")
            fid = store_fam["id"]
            self.permit({f"equity:{fid}": self.passed(fid)})
            self.pool(routes=[f"equity:{fid}"])
            with self.subTest(settings=settings["elane"].get("pool")):
                out = EF.step(self.gate(settings))
                self.assertEqual(out["seated"], [])
                self.assertEqual(out["waits"][fid], EF.POOL_REFUSED)
                self.assertEqual(store_fam["band"], "gym")
                self.assertFalse(EF.eligible(store_fam["state"]))

    def test_the_hold_list_refuses_alike(self):
        fam = self.sector()
        self.permit({"equity:f1": self.passed("f1")})
        self.pool(holds=["equity:f1"])
        self.assertEqual(EF.step(self.gate(POOL_ON))["waits"]["f1"], EF.POOL_REFUSED)
        self.assertEqual(fam["band"], "gym")

    def test_seat_refused_refuses_it(self):
        fam = self.sector()
        self.permit({"equity:f1": self.passed("f1")})
        self.pool()
        EF.step(self.gate(POOL_ON))                                   # seated before the pool listed it
        self.assertIsNone(EF.seat_refused(self.store, fam, POOL_ON))
        self.pool(routes=["equity:f1"])
        for settings in (POOL_ON, POOL_ROLLED, ON):
            self.assertEqual(EF.seat_refused(self.store, fam, settings), EF.POOL_REFUSED)
        self.assertFalse(EF.mark_seated(self.store, "f1", POOL_ON))

    def test_try_refused_refuses_it_with_fwd1_seats_off(self):
        fam = self.store.add("i1", symbols=["SPY"])                  # an index lineage FWD1 judges as case N
        self.permit({"equity:i1": {"status": "pending", "type": "ETF", "case": "N", "family": "i1",
                                   "start": "2026-10-13"}})
        self.pool(routes=["equity:i1"])
        for settings in (POOL_FWD1_OFF, OFF, {}, POOL_ROLLED):
            with self.subTest(settings=settings):
                self.assertEqual(EF.try_refused(self.store, fam, settings, now=CLOSE + 86400.0 * 5), EF.POOL_REFUSED)
                self.assertFalse(elane.try_open(self.store, fam, 1, settings))
        other = self.store.add("i2", symbols=["SPY"])               # a lineage the pool does not list: as before
        self.assertIsNone(EF.try_refused(self.store, other, POOL_FWD1_OFF, now=CLOSE))

    def test_a_held_index_lineage_keeps_its_l5_try_until_its_first_close(self):
        fam = self.store.add("f1", symbols=["SPY", "QQQ"])
        (self.root / EF.PERMITS).write_text(json.dumps({
            "version": EF.PERMITS_VERSION, "screen": "FWD1-R", "receipt": "c" * 64, "start": PIN_START, "at": "x",
            "lineages": {"equity:f1": {"status": "pending", "type": "ETF", "case": "N", "family": "f1",
                                       "start": START}}}))
        self.pool(holds=["equity:f1"])
        self.assertIsNone(EF.try_refused(self.store, fam, POOL_FWD1_OFF, now=CLOSE - 3600.0))
        self.assertIsNone(EF.try_refused(self.store, fam, POOL_ON, now=CLOSE - 3600.0))
        self.assertEqual(EF.try_refused(self.store, fam, POOL_FWD1_OFF, now=CLOSE), EF.POOL_REFUSED)
        sibling = self.store.add("f1b", symbols=["SPY"], lineage="f1")
        self.assertEqual(EF.try_refused(self.store, sibling, POOL_FWD1_OFF, now=CLOSE - 3600.0), EF.POOL_REFUSED)

    def test_rollback_and_a_pooled_fail_leave_the_refusal_in_place(self):
        fam = self.sector()
        self.permit({"equity:f1": self.passed("f1")})
        for words in ("FAIL", "DEMOTED", "VOID", "REFUTED", "PASS"):
            self.pool(routes=["equity:f1"], words=words)
            for settings in (POOL_ON, POOL_ROLLED):
                with self.subTest(words=words, mode=settings["elane"]["pool"]["mode"]):
                    self.assertEqual(EF.step(self.gate(settings))["waits"]["f1"], EF.POOL_REFUSED)
                    self.assertEqual(EF.try_refused(self.store, fam, settings, now=CLOSE), EF.POOL_REFUSED)
        self.assertEqual(fam["band"], "gym")

    def test_an_unreadable_pool_file_fails_closed(self):
        sector = self.sector("s1")
        index = self.store.add("x1", symbols=["SPY"])
        self.permit({"equity:s1": self.passed("s1"), "equity:x1": self.passed("x1", cell="equity / trend / index")})
        for raw in ("{not json", json.dumps({"version": 2, "routes": {}, "holds": []}),
                    json.dumps({"version": 1, "routes": [], "holds": []}), json.dumps([1])):
            self.pool(raw=raw)
            for settings in (POOL_ON, POOL_ROLLED, ON):               # unreadable: whatever the mode
                with self.subTest(raw=raw[:20], settings=settings["elane"].get("pool")):
                    self.assertEqual(EF.pool_listed(self.root, settings), (None, EF.POOL_UNREADABLE))
                    out = EF.step(self.gate(settings))
                    self.assertEqual(out["waits"].get("s1"), EF.POOL_UNREADABLE)   # a forward-only ETF pass waits
        self.assertEqual(sector["band"], "gym")
        self.assertEqual(index["band"], "candidate")                  # an index-only pass is not forward-only
        sector["state"][EF.STATE_KEY] = {"eligible": True, "type": "ETF", "case": "N", "lineage": "equity:s1"}
        self.assertEqual(EF.seat_refused(self.store, sector, POOL_ON), EF.POOL_UNREADABLE)

    def test_a_missing_pool_file_fails_closed_while_the_mode_is_on(self):
        sector = self.sector("s1")
        self.permit({"equity:s1": self.passed("s1")})
        self.assertEqual(EF.pool_listed(self.root, POOL_ON), (None, EF.POOL_MISSING))
        self.assertEqual(EF.step(self.gate(POOL_ON))["waits"]["s1"], EF.POOL_MISSING)
        self.assertEqual(EF.pool_listed(self.root, POOL_ROLLED), (frozenset(), None))
        self.assertEqual(EF.pool_listed(self.root, {}), (frozenset(), None))
        self.assertEqual(EF.pool_listed(self.root, {"elane": {"pool": {"mode": "recrod"}}}), (None, EF.POOL_MISSING))
        self.assertEqual(EF.step(self.gate(POOL_ROLLED))["seated"], ["s1"])
        del sector

    def test_the_fail_closed_try_refuses_every_lineage_fwd1_judges(self):
        judged = self.store.add("i1", symbols=["SPY"])
        free = self.store.add("i2", symbols=["SPY"])
        self.permit({"equity:i1": {"status": "pending", "type": "ETF", "case": "N", "family": "i1",
                                   "start": "2026-10-13"}})
        self.assertEqual(EF.try_refused(self.store, judged, POOL_FWD1_OFF, now=CLOSE), EF.POOL_MISSING)
        self.assertIsNone(EF.try_refused(self.store, free, POOL_FWD1_OFF, now=CLOSE))
        self.pool(raw="{bad")
        self.assertEqual(EF.try_refused(self.store, judged, OFF, now=CLOSE), EF.POOL_UNREADABLE)
        (self.root / EF.PERMITS).write_text("{bad")                 # FWD1's file unreadable too: no equity try
        self.assertEqual(EF.try_refused(self.store, free, OFF, now=CLOSE), EF.POOL_UNREADABLE)

    def test_seats_off_does_nothing_else(self):
        fam = self.sector()
        self.permit({"equity:f1": self.passed("f1")})
        self.pool(routes=["equity:other"])
        self.assertEqual(EF.step(self.gate(POOL_FWD1_OFF)), {})
        self.assertEqual(EF.seat_refused(self.store, fam, POOL_FWD1_OFF), "the forward seats are off (elane.fwd1.seats)")
        self.assertIsNone(EF.try_refused(self.store, fam, POOL_FWD1_OFF, now=CLOSE))
        self.assertEqual(fam["band"], "gym")

    def test_one_a_cell_counts_a_pooled_seat(self):
        cell = "equity / trend / sectors"
        holder = self.sector("p1", band="probe", state={EF.POOL_KEY: {"seated": True, "cluster": "trend_momentum",
                                                                      "fwd1_cell": cell}})
        self.sector("f1")
        self.permit({"equity:f1": self.passed("f1", cell=cell)})
        self.pool()
        self.assertEqual(EF.one_a_cell(self.store, cell, but="f1"), "p1")
        self.assertIn("one live forward seat a mechanism cell: p1", EF.step(self.gate(POOL_ON))["waits"]["f1"])
        holder["band"] = "gym"                                         # left the live bands: the cell is free
        self.assertIsNone(EF.one_a_cell(self.store, cell, but="f1"))
        self.assertEqual(EF.step(self.gate(POOL_ON))["seated"], ["f1"])


if __name__ == "__main__":
    unittest.main()
