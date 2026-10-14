"""The forward screen's seat path, the swarm's half (league/swarm/elane_forward.py): BUILT AND OFF. With the switch
off nothing acts; on, a FWD1-judged lineage takes no sealed Validation try, an ETF pass becomes a Candidate through the
roster's own machinery (one live forward seat a mechanism cell), and a panel pass is made eligible only (its seat pool
is E4 step two's). The store is a fake; every row is invented."""

from __future__ import annotations

import contextlib
import json
import tempfile
import types
import unittest
from pathlib import Path

from league.equity import EQUITY_ENGINE_VERSION
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
            retired: bool = False) -> dict:
        self.fams[fid] = {"id": fid, "structure": structure, "band": band, "retired_at": "x" if retired else None,
                          "spec": {"lane": "equity", "agenda": "trend"}, "lineage": lineage, "state": dict(state or {})}
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


if __name__ == "__main__":
    unittest.main()
