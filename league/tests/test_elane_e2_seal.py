"""Release E2, THE SEAL (amendment A9 D3; league/swarm/elane_seal.py): no Validation or look outcome of a share program
reaches a generator. Two worlds share one Train history (the same E2 records, births, programs and route ledger) and
differ only in what happened to share programs after Train: in one the Train pass and the seeded program met their
pre-check, passed the sealed look and went live; in the other both failed, retired, and left graveyard rows whose
lessons tell the outcome. The equity request (system and user), the equity researcher's brief, the route choice, the
equity Train map and graveyard, and the options generators' graveyard reads are the same in both, and carry no
sentinel of either outcome. Every family, program and number here is invented."""

from __future__ import annotations

import re
import types
import unittest

from league.swarm import elane, elane_seal, elane_train, elane_yield
from league.swarm.architect import Architect, GraveyardDigest
from league.swarm.elane_births import EquityPass, EquityQuota
from league.swarm.elane_train import STATE_KEY, EquityResearcher
from league.swarm.researcher import Researcher
from league.tests import elane_e2_fakes as fx

SENTINELS = ("SENTINEL", "0.9731", "-0.4417", "probe", "candidate")


class TwoWorlds(unittest.TestCase):
    def setUp(self):
        fx.switch_on(self)
        self.settings = fx.settings()

    def world(self, outcome: str):
        clock = fx.Clock()
        store = fx.new_store(self, clock)
        verdict = {"passed": True, "fails": [], "score": 1.93, "pnl_10": 180.0, "pnl_15": 120.0,
                   "years": {"2016": {"trades": 60, "days_traded": 30, "pnl": 20.0, "t": 0.6, "active": True}}}
        fx.e2_family(store, "won", lane="equity", agenda="reversal", symbols=("QQQ",), code=fx.program("QQQ"),
                     record={"status": "passed", "passed_version": 1, "versions": {"1": verdict}})
        store.update_family("won", best_version=1, best_train=1.93)
        fx.e2_family(store, "dead", lane="equity", agenda="trend", symbols=("XLK",),
                     record={"status": "refuted", "versions": {"1": {"passed": False, "fails": ["Y2"]}},
                             "refuted": {"at": "2026-10-10T01:00:00Z", "codes": ["Y2"], "versions": 1, "why": "spent"}})
        store.bury("dead", "REFUTED on Train (equity-v1): spent.")
        store.retire("dead", "REFUTED on Train")
        fx.e2_family(store, "busy", lane="beta", agenda="overnight", symbols=("SPY",), code=fx.program(),
                     record={"status": "researching",
                             "versions": {"1": {"passed": False, "fails": ["P1"], "pnl_10": 30.0, "pnl_15": -2.0}}})
        seed = store.add_family({"id": "seed-overnight-spy", "mechanism": "The captain's seed: SPY overnight, every "
                                 "session.", "structure": "etf", "roots": ["SPY"], "lane": "beta"}, origin="seed")
        store.put(elane.SEEDS_KEY, {"seed-overnight-spy": seed["id"]})
        opt = store.add_family({"id": "opt-dead", "mechanism": "An invented options idea that died on Train.",
                                "structure": "debit_vertical", "roots": ["SPY"]}, origin="architect")
        store.bury(opt["id"], "REFUTED: an invented options lesson.")
        elane_yield.book(store, "sail:pro_asap", usd=0.4, known=True, purpose="births", answered=True, now=clock())
        elane_yield.book_births(store, "sail:pro_asap", 3)
        # What happens after Train: the only difference between the worlds.
        for fid in ("won", seed["id"]):
            if outcome == "pass":
                store.set_state(fid, elane_try={"version": 1, "entered": True, "precheck": {"passed": True, "t": 0.9731}},
                                elane_look={"version": 1, "verdict": {"passed": True, "t": 0.9731}, "beside": "SENTINEL-A"},
                                validation_r_sd_by_version={"1": 0.9731}, validation_line={"met": True})
                store.update_family(fid, validated_version=1, best_validation=0.9731, band="probe")
                store.add_look(fid, 1, f"sha-{fid}", passed=True, p_value=0.01, detail={"why": "SENTINEL-A"})
                store.add_forward(fid, "real", [{"id": f"eq-{fid}", "day": "2026-10-13", "pnl": 0.9731, "max_loss": 100.0}])
            else:
                store.set_state(fid, elane_try={"version": 1, "entered": False, "precheck": {"passed": False, "t": -0.4417}},
                                elane_look={"version": 1, "verdict": {"passed": False}, "beside": "SENTINEL-B"},
                                validation_line={"met": False})
                store.update_family(fid, validated_version=1, best_validation=-0.4417)
                store.add_look(fid, 1, f"sha-{fid}", passed=False, p_value=0.4417, detail={"why": "SENTINEL-B"})
                store.bury(fid, "best validation: not met (SENTINEL-B); the look failed")
                store.retire(fid, "SENTINEL-B: failed its look")
        return store, clock

    def reads(self, outcome: str) -> dict:
        store, clock = self.world(outcome)
        router = fx.FakeRouter()
        arch = Architect(store, router, self.settings, clock=clock)
        system, user = EquityPass(arch).request(EquityQuota(store, self.settings, now=clock()))
        researcher = EquityResearcher(store, router, self.settings, runner=fx.FakeRunner(), clock=clock)
        routes = elane_yield.routes(self.settings, router)
        tool = Researcher._local_tool(types.SimpleNamespace(store=store, settings=self.settings), {"id": "x"}, "graveyard",
                                      {"query": ""}, {})
        return {
            "system": system, "user": user, "brief": researcher.brief(store.family("busy")),
            "choice": [elane_yield.choose(store, self.settings, routes, turn=t, train_key=STATE_KEY)[0].key
                       for t in range(6)],
            "map": elane_train.train_map(store), "graveyard": elane_train.refuted_rows(store),
            "options": {"graves": [r["family"] for r in arch.graves(limit=50)], "ids": sorted(arch.graveyard_ids()),
                        "digest": [p["id"] for p in GraveyardDigest(store, self.settings, clock=clock).rows()],
                        "tool": [r["family"] for r in tool["lessons"]], "prompt_mentions": [
                            fid for fid in ("won", "dead", "busy", "seed-overnight-spy")
                            if re.search(rf"(?<![\w-]){re.escape(fid)}(?![\w-])", arch.prompt())]},
        }

    def test_every_generator_reads_the_same_in_both_worlds(self):
        a, b = self.reads("pass"), self.reads("fail")
        for key in a:
            self.assertEqual(a[key], b[key], f"{key} differs with the sealed outcomes")

    def test_no_sentinel_of_either_outcome_reaches_a_generator(self):
        for outcome in ("pass", "fail"):
            reads = self.reads(outcome)
            for key in ("system", "user", "brief"):
                for word in SENTINELS:
                    self.assertNotIn(word, reads[key], f"{outcome}: {key} carries {word}")

    def test_the_options_generators_read_no_equity_row(self):
        for outcome in ("pass", "fail"):
            reads = self.reads(outcome)["options"]
            self.assertEqual(reads, {"graves": ["opt-dead"], "ids": ["opt-dead"], "digest": ["opt-dead"],
                                     "tool": ["opt-dead"], "prompt_mentions": []}, outcome)

    def test_the_request_still_says_what_has_its_try_and_what_was_refuted(self):
        user = self.reads("fail")["user"]
        self.assertIn("won (equity / reversal / QQQ; passed Train (v1))", user)
        self.assertIn("seed-overnight-spy (beta / other / SPY; seeded by the captain's build agents)", user)
        self.assertIn("dead (equity / trend / XLK): ", user)
        self.assertIn("busy (beta / overnight / SPY; in Train research, 1 versions scored)", user)

    def test_train_facts_carry_no_sealed_field(self):
        store, _ = self.world("pass")
        for fid in ("won", "busy", "seed-overnight-spy"):
            facts = elane_seal.train_facts(store.family(fid), STATE_KEY)
            self.assertFalse(set(facts) & (elane_seal.SEALED_KEYS | elane_seal.SEALED_COLUMNS))
            self.assertFalse(set(facts["record"]) & elane_seal.SEALED_KEYS)

    def test_the_operators_report_does_see_the_outcomes(self):
        store, clock = self.world("pass")
        row = elane_yield.report(store, self.settings, train_key=STATE_KEY)["routes"]["sail:pro_asap"]
        self.assertEqual((row["train_passes"], row["validation_entries"], row["looks_passed"], row["live"]), (1, 1, 1, 1))


if __name__ == "__main__":
    unittest.main()
