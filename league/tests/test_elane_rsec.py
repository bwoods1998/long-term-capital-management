"""R-SEC, SECTOR PROGRAMS ARE FORWARD-ONLY (league/swarm/elane.py `forward_only`, asked by `try_open` and `look`; the
captain's decision from the widening review of Oct 14, 2026): an equity family whose symbols name anything outside the
four index ETFs takes no sealed Validation try and no sealed look, whatever `elane.fwd1.seats` says and whether or not
the forward screen's permit file lists its lineage; the look holds it before the sealed run (no look spent, no refusal
row, no bad gate outcome) and nothing retires it for that reason; its one path to a seat is a forward pass of FWD1-R
under the switch. An index-only family is unchanged; a panel family is not touched (A34 governs it). The store is the
real SwarmStore on a temporary root; the runner and the screen are faked at their interfaces (test_elane_gate's)."""

from __future__ import annotations

import json
from unittest import mock

from league.equity import BETA, EQUITY, EQUITY_ENGINE_VERSION
from league.equity import config as econfig
from league.swarm import elane
from league.swarm import elane_forward as EF
from league.swarm.evaluator import equity_fingerprint
from league.swarm.gate import run_sha
from league.tests.test_elane import CODE, ON, equity_spec
from league.tests.test_elane_gate import EquityCase, screen

SEATS_OFF = {"elane": {"mode": "gate", "fwd1": {"mode": "record", "seats": "off"}}}
SEATS_ON = {"elane": {"mode": "gate", "fwd1": {"mode": "record", "seats": "on"}}}
#: The switch's three positions as R-SEC reads them: no block (the code's default), "off" (policy.json's), "on".
POSITIONS = {"no fwd1 block": ON, "seats off": SEATS_OFF, "seats on": SEATS_ON}
#: The families the decision names: a sector fund, a bond fund, and an index fund beside a sector fund.
OUTSIDE = {"xlk": ["XLK"], "tlt": ["TLT"], "spy-xlk": ["SPY", "XLK"]}


class Case(EquityCase):
    def born(self, fid="b1", *, seeded=True, code=None, lane=BETA, symbols=("SPY",)):
        """A family of its own lineage (its own code: identical code on the same slice joins lineages)."""
        self.store.add_family(equity_spec(fid, lane=lane, seeded=seeded, symbols=symbols), origin="seed")
        return self.store.add_version(fid, code or CODE + f"# {fid}\n", {}, author=elane.SEED_AUTHOR)

    def alive(self):
        return [str(f["id"]) for f in self.store.families(alive=True, lanes=elane.LANES)]

    def permit(self, rows):
        (self.store.root / EF.PERMITS).write_text(json.dumps({"version": EF.PERMITS_VERSION, "screen": "FWD1-R",
                                                             "receipt": "c" * 64, "start": "2026-10-16", "at": "x",
                                                             "lineages": rows}))

    def events(self, fid, kind=None):
        return [e for e in self.store.events_after(0, limit=100000)
                if e["family"] == fid and (kind is None or e["kind"] == kind)]

    def entered(self, fid, symbols, settings):
        """A family of `symbols` standing at the gate's door: born, then validated AS IF R-SEC were not there (a family
        that entered before the rule, or any path that reached the gate): the look is the rule's second wall."""
        version = self.born(fid, symbols=symbols)
        self.tournament.settings = settings
        with mock.patch.object(elane, "forward_only", return_value=False), screen():
            verdict = elane.validate(self.tournament, self.store.family(fid), version)
        self.assertTrue(verdict["entered"], fid)
        return version, run_sha(version)


class TheRule(Case):
    def test_the_index_etfs_are_the_four(self):
        self.assertEqual(tuple(econfig.INDEX_ETFS), ("SPY", "QQQ", "IWM", "DIA"))

    def test_symbols_outside_the_index_etfs_are_forward_only(self):
        for fid, symbols in OUTSIDE.items():
            self.born(fid, symbols=symbols)
            with self.subTest(family=fid):
                self.assertTrue(elane.forward_only(self.store.family(fid)))
        self.born("idx", symbols=("SPY", "QQQ", "IWM", "DIA"))
        self.assertFalse(elane.forward_only(self.store.family("idx")), "an index-only family is unchanged")

    def test_every_place_a_symbol_is_kept_is_read_and_unreadable_fails_closed(self):
        index = {"id": "x", "structure": "etf", "roots": ["SPY"], "spec": {"lane": BETA, "roots": ["SPY"], "symbols": ["SPY"]}}
        self.assertFalse(elane.forward_only(index))
        self.assertFalse(elane.forward_only({**index, "roots": json.dumps(["spy"])}), "the store's text, any case")
        self.assertTrue(elane.forward_only({**index, "spec": {**index["spec"], "symbols": ["SPY", "GLD"]}}))
        self.assertTrue(elane.forward_only({**index, "spec": json.dumps({**index["spec"], "roots": ["XLE"]})}))
        self.assertTrue(elane.forward_only({**index, "roots": {"SPY": 1}}), "a shape that cannot be read")
        self.assertTrue(elane.forward_only({**index, "roots": "not json"}))
        self.assertTrue(elane.forward_only({"id": "x", "structure": "etf", "spec": {"lane": BETA}}), "no symbol named")
        self.assertTrue(elane.forward_only(None))

    def test_a_panel_family_is_not_touched(self):
        from league.swarm import elane_xs

        panel = {"id": "p", "structure": elane_xs.STRUCTURE, "roots": [], "spec": {"lane": EQUITY,
                                                                                "structure": elane_xs.STRUCTURE}}
        self.assertFalse(elane.forward_only(panel), "A34 governs a panel family")
        self.assertFalse(elane.forward_only({**panel, "structure": "etf"}), "its spec says panel")


class TheSealedTry(Case):
    def test_no_sealed_try_whatever_the_switch_and_the_permit_file_say(self):
        for fid, symbols in OUTSIDE.items():
            self.born(fid, symbols=symbols)
        for name, settings in POSITIONS.items():
            for listed in (None, "pending", "pass", "fail", "void"):
                rows = {} if listed is None else {
                    EF.lineage_of(self.store, self.store.family(fid)): {"status": listed} for fid in OUTSIDE}
                self.permit(rows)
                for fid in OUTSIDE:
                    with self.subTest(switch=name, listed=listed, family=fid):
                        fam = self.store.family(fid)
                        self.assertFalse(elane.try_open(self.store, fam, 1, settings))
                        self.assertIsNone(elane.next_try(self.store, fam, settings))
                        with screen():
                            self.tournament.settings = settings
                            verdict = elane.validate(self.tournament, fam, self.store.version(fid, 1))
                        self.assertEqual((verdict["entered"], verdict["refused"]), (False, elane.SPENT_TRY))
        self.assertEqual(self.runner.calls, [], "no Validation run, so no sealed pre-check, for any of them")
        for fid in OUTSIDE:
            self.assertEqual(self.store.runs(fid, window="validation"), [])
            self.assertEqual(elane.lineage_tries(self.store, fid), [], "no try is counted")

    def test_an_index_only_family_is_unchanged(self):
        self.born("idx", symbols=("SPY", "QQQ"))
        for name, settings in POSITIONS.items():
            self.permit({})
            with self.subTest(switch=name):
                fam = self.store.family("idx")
                self.assertTrue(elane.try_open(self.store, fam, 1, settings))
                self.assertEqual(elane.next_try(self.store, fam, settings), 1)
        self.permit({EF.lineage_of(self.store, self.store.family("idx")): {"status": "pending"}})
        self.assertFalse(elane.try_open(self.store, self.store.family("idx"), 1, SEATS_ON), "FWD1's own rule, as built")
        self.assertTrue(elane.try_open(self.store, self.store.family("idx"), 1, SEATS_OFF))

    def test_the_tournament_round_asks_nothing_and_retires_nothing(self):
        for fid, symbols in OUTSIDE.items():
            self.born(fid, symbols=symbols)
        self.born("idx", symbols=("SPY",))
        for name, settings in POSITIONS.items():
            self.tournament.settings = settings
            with self.subTest(switch=name), screen():
                out = self.tournament.equity_round()
                self.assertEqual(out["retired"], [])
                self.assertFalse(set(out["validated"]) & set(OUTSIDE))
        self.assertIn("idx", self.alive())
        self.assertEqual(sorted(f for f in self.alive() if f in OUTSIDE), sorted(OUTSIDE), "no retirement for that reason")
        for fid in OUTSIDE:
            self.assertIsNone(elane.lineage_spent(self.store, self.store.family(fid), SEATS_ON))


class TheLook(Case):
    def test_the_look_holds_it_before_the_sealed_run_and_spends_nothing(self):
        for name, settings in POSITIONS.items():
            for fid, symbols in OUTSIDE.items():
                fid = f"{fid}-{name.replace(' ', '-')}"
                with self.subTest(switch=name, family=fid):
                    version, sha = self.entered(fid, symbols, settings)
                    self.gate.settings = settings
                    self.runner.calls.clear()
                    for _ in range(2):  # asked again next round: the same hold, its record written once
                        out = {"looked": [], "held": []}
                        with screen() as mint:
                            self.assertIsNone(elane.look(self.gate, self.store.family(fid), version, sha))
                            self.gate.equity_round(out)
                        self.assertEqual(mint.call_count, 0, "no capability minted")
                        self.assertEqual(mint.floor.call_count, 0, "no floor computed")
                    self.assertFalse([x for x in out["looked"] if x["family"] == fid])
                    self.assertEqual([c for c in self.runner.calls if c[1] == fid], [], "no run of any kind")
                    self.assertFalse([lk for lk in self.store.looks() if lk["run_sha"] == sha], "no look spent")
                    self.assertFalse(self.store.looked(sha))
                    self.assertEqual(self.store.lineage_looks(fid, include_inflight=True), 0)
                    self.assertEqual(self.store.refusals(fid), [], "no refusal row: the lineage is not spent")
                    fam = self.store.family(fid)
                    state = fam["state"]
                    self.assertEqual((fam["band"], state["gate_outcome"]["result"], state["gate_ready"]),
                                     ("gym", "waiting", True))
                    self.assertIn("R-SEC", state["gate"])
                    self.assertIsNone(state.get(elane.LOOK_KEY))
                    self.assertIsNone(state.get("look_inflight"))
                    waits = [e for e in self.events(fid, "swarm.gate") if e["payload"].get("action") == "equity_look_waits"]
                    self.assertEqual(len(waits), 1, "one record, not one a round")
                    self.assertIsNone(elane.lineage_spent(self.store, fam, settings), "nothing retires it")

    def test_an_index_only_family_still_takes_its_look(self):
        for name, settings in POSITIONS.items():
            fid = f"idx-{name.replace(' ', '-')}"
            with self.subTest(switch=name):
                version, sha = self.entered(fid, ("SPY",), settings)
                self.gate.settings = settings
                out = {"looked": [], "held": []}
                with screen() as mint:
                    self.gate.equity_round(out)
                self.assertIn({"family": fid, "passed": True, "lane": BETA}, out["looked"])
                self.assertEqual(mint.call_count, 1)
                self.assertTrue(self.store.looked(sha))
                self.assertEqual(self.store.family(fid)["band"], "candidate")


class TheForwardPath(Case):
    def test_a_forward_pass_under_the_switch_is_its_one_path_to_a_seat(self):
        self.born("s-xlk", symbols=("XLK",))
        fam = self.store.family("s-xlk")
        lineage = EF.lineage_of(self.store, fam)
        engine = f"{EQUITY_ENGINE_VERSION}+{equity_fingerprint()[:12]}+fwd-1"
        self.permit({lineage: {"status": "pass", "type": "ETF", "case": "N", "cell": "beta / sector / sectors",
                               "family": "s-xlk", "version": 1, "run_sha": run_sha(self.store.version("s-xlk", 1)),
                               "k": 5, "weak": True, "engine": engine,
                               "words": "FWD1-R forward screen (ETF, case N): passed at checkpoint 5"}})
        self.assertEqual(EF.step(self.gate_with(SEATS_OFF)), {}, "the switch off: no seat")
        self.assertEqual(self.store.family("s-xlk")["band"], "gym")
        out = EF.step(self.gate_with(SEATS_ON))
        self.assertEqual(out["seated"], ["s-xlk"])
        fam = self.store.family("s-xlk")
        self.assertEqual(fam["band"], "candidate")
        self.assertIn("WEAK", self.events("s-xlk", "swarm.band")[-1]["payload"]["reason"])
        self.assertFalse(self.store.looks(), "seated with no sealed look")
        self.assertFalse(elane.try_open(self.store, fam, 1, SEATS_ON), "and still no sealed try")

    def gate_with(self, settings):
        self.gate.settings = settings
        return self.gate


if __name__ == "__main__":
    import unittest

    unittest.main()
