"""THE SEAT RULE'S COUNTS REACH NO GENERATOR (release E5-A; the seal of the equity lanes, league/swarm/elane_seal.py).

K's two counts are written beside a program's look (`elane_seat` in its family's state), the gate's private events
carry them, and the EquityBook's seat plan (the kv `eq_seat` in live.sqlite) orders the waiting programs by them. A
generator that read any of it would learn which programs passed a sealed look and how active they were in the
Validation year.

TWO WORLDS OF K: three swarm stores that differ ONLY in what the seat rule keeps (the counts, the private events, the
book's plan with another queue; one store has none of it). The architect's equity request (system and user), every
E2 family's researcher brief, the route choice, the Train map (rows and text), the refuted rows, the Train facts and
the options generators' graveyard reads are the same bytes in all three, and no count and no key of the rule is in
any of them. And the seal's own list names the key (`SEALED_KEYS`), so a view built as "the family's state less the
sealed keys" is the same in the three worlds too.

Every family, program and number here is invented."""

from __future__ import annotations

import json
import re
import sqlite3
import types
import unittest
from fractions import Fraction
from pathlib import Path

from league.equity import live
from league.swarm import elane, elane_seal, elane_train, elane_yield
from league.swarm.architect import Architect, GraveyardDigest
from league.swarm.elane_births import EquityPass, EquityQuota
from league.swarm.elane_train import STATE_KEY, EquityResearcher
from league.swarm.researcher import Researcher
from league.tests import elane_e2_fakes as fx
from league.tests import elane_e3_fakes as e3

#: The invented counts of each world: (Validation close days, Train-era close days, Train-era sessions).
WORLDS = {"a": {"won": (193, 1187, 1759), "seed-overnight-spy": (67, 433, 1759)},
          "b": {"won": (7, 53, 1759), "seed-overnight-spy": (229, 1601, 1759)},
          "none": {}}
#: What no generator may read: the worlds' own counts, and every name the rule keeps them under.
WORDS = ("193", "1187", "433", "1601", "229", "close_days", "elane_seat", "seat_activity", "seat_counts", "eq_seat")


def world(case: unittest.TestCase, name: str):
    clock = fx.Clock()
    store = fx.new_store(case, clock)
    verdict = {"passed": True, "fails": [], "score": 1.93, "pnl_10": 180.0, "pnl_15": 120.0,
               "years": {"2016": {"trades": 60, "days_traded": 30, "pnl": 20.0, "t": 0.6, "active": True}}}
    e3.hidden_family(store, "won", 2018, lane="equity", agenda="reversal", symbols=("QQQ",), code=fx.program("QQQ"))
    store.set_state("won", **{STATE_KEY: {"status": "passed", "passed_version": 1, "versions": {"1": verdict}}})
    store.update_family("won", best_version=1, best_train=1.93)
    e3.hidden_family(store, "busy", 2023, code=fx.program())
    store.set_state("busy", **{STATE_KEY: {"status": "researching", "versions": {
        "1": {"passed": False, "fails": ["P1"], "pnl_10": 30.0, "pnl_15": -2.0}}}})
    fx.e2_family(store, "dead", lane="equity", agenda="trend", symbols=("IWM",),
                 record={"status": "refuted", "versions": {"1": {"passed": False, "fails": ["Y2"]}},
                         "refuted": {"at": "2026-10-10T01:00:00Z", "codes": ["Y2"], "versions": 1, "why": "spent"}})
    store.bury("dead", "REFUTED on Train (equity-v1): spent.")
    store.retire("dead", "REFUTED on Train")
    seed = store.add_family({"id": "seed-overnight-spy", "mechanism": "The captain's seed: SPY overnight, every session.",
                             "structure": "etf", "roots": ["SPY"], "lane": "beta"}, origin="seed")
    store.put(elane.SEEDS_KEY, {"seed-overnight-spy": seed["id"]})
    opt = store.add_family({"id": "opt-dead", "mechanism": "An invented options idea that died on Train.",
                            "structure": "debit_vertical", "roots": ["SPY"]}, origin="architect")
    store.bury(opt["id"], "REFUTED: an invented options lesson.")
    elane_yield.book(store, "sail:pro_asap", usd=0.4, known=True, purpose="births", answered=True, now=clock())
    elane_yield.book_births(store, "sail:pro_asap", 3)
    # Both passed their looks in EVERY world (the same sealed outcome): the worlds differ in the seat rule's records only.
    for fid in ("won", seed["id"]):
        store.set_state(fid, elane_try={"version": 1, "entered": True, "precheck": {"passed": True, "t": 0.5}},
                        elane_look={"version": 1, "verdict": {"passed": True, "t": 0.5}, "beside": "one line"},
                        banded_version=1, banded_at=1000.0)
        store.update_family(fid, validated_version=1, best_validation=0.5, band="candidate")
        store.add_look(fid, 1, f"sha-{fid}", passed=True, p_value=0.01, detail={"why": "one line"})
    # ---- WHAT DIFFERS: the two counts, the private events that carry them, the book's plan
    counts = WORLDS[name]
    for fid, (kv, kt, ts) in counts.items():
        record = {"version": 1, "run_sha": f"sha-{fid}", "floor": "0.25", "validation": {"close_days": kv, "sessions": 250},
                  "train": {"close_days": kt, "sessions": ts}, "at": "2026-10-11T20:00:00Z", "source": "look",
                  "validation_run": "look"}
        store.set_state(fid, **{elane.SEAT_KEY: record})
        store.event("swarm.gate", fid, {"action": "look", "version": 1, "passed": True, "_seat": record})
        store.event("swarm.gate", fid, {"action": "seat_counts", "version": 1, "source": "backfill", "_counts": record})
    if counts:
        best = max(counts, key=lambda f: min(Fraction(counts[f][0]), Fraction(counts[f][1] * 250, counts[f][2])))
        rest = [f for f in counts if f != best]
        plan = {"rule": "activity-1-free", "seats": 6, "day": "2026-10-12", "holders": [],
                "waiting": [{"family": best, "version": 1, "rank": 1, "seeded": False, "flagged": False, "ranked": True},
                            {"family": rest[0], "version": 1, "rank": 2, "seeded": False, "flagged": name == "b",
                             "ranked": True}],
                "idle": {rest[0]: {"day": "2026-10-12", "why": "it yielded"}} if name == "b" else {}, "last": None}
        db = sqlite3.connect(Path(store.root) / "live.sqlite")
        db.executescript(live.SCHEMA)
        db.execute("CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT)")
        db.execute("INSERT OR REPLACE INTO kv(key, value) VALUES(?, ?)", (live.SEAT_KEY, json.dumps(plan)))
        db.commit()
        db.close()
    return store, clock


def reads(case: unittest.TestCase, name: str) -> dict:
    """Everything a generator of either lane reads, in one world."""
    settings = e3.settings()
    store, clock = world(case, name)
    router = fx.FakeRouter()
    arch = Architect(store, router, settings, clock=clock)
    system, user = EquityPass(arch).request(EquityQuota(store, settings, now=clock()))
    researcher = EquityResearcher(store, router, settings, runner=fx.FakeRunner(), clock=clock)
    routes = elane_yield.routes(settings, router)
    fams = [f for f in elane_seal.equity_families(store) if elane_train.e2_family(f)]
    tool = Researcher._local_tool(types.SimpleNamespace(store=store, settings=settings), {"id": "x"}, "graveyard",
                                  {"query": ""}, {})
    return {"system": system, "user": user, "briefs": {f["id"]: researcher.brief(f) for f in fams},
            "choice": [elane_yield.choose(store, settings, routes, turn=t, train_key=STATE_KEY)[0].key for t in range(6)],
            "map": elane_train.train_map(store), "map_text": elane_train.train_map_text(store, settings),
            "graveyard": elane_train.refuted_rows(store),
            "train_facts": {f["id"]: elane_seal.train_facts(f, STATE_KEY) for f in elane_seal.equity_families(store)},
            "options": {"graves": [r["family"] for r in arch.graves(limit=50)], "ids": sorted(arch.graveyard_ids()),
                        "digest": [p["id"] for p in GraveyardDigest(store, settings, clock=clock).rows()],
                        "tool": [r["family"] for r in tool["lessons"]], "prompt": arch.prompt()},
            # The view the seal's own list is for: a family's state less the keys no generator reads.
            "state_less_the_sealed_keys": {f["id"]: {k: v for k, v in (f.get("state") or {}).items()
                                                     if k not in elane_seal.SEALED_KEYS}
                                           for f in elane_seal.equity_families(store)}}


def text(value) -> str:
    return json.dumps(value, sort_keys=True, default=str)


class TwoWorldsOfK(unittest.TestCase):
    def setUp(self):
        fx.switch_on(self)

    def test_the_seal_names_the_counts(self):
        self.assertEqual(elane.SEAT_KEY, "elane_seat")
        self.assertIn(elane.SEAT_KEY, elane_seal.SEALED_KEYS)
        self.assertIn(elane.LOOK_KEY, elane_seal.SEALED_KEYS, "beside the look it is written with")

    def test_every_generator_reads_the_same_bytes_whatever_k_is(self):
        a, b, none = reads(self, "a"), reads(self, "b"), reads(self, "none")
        for key in a:
            self.assertEqual(text(a[key]), text(b[key]), f"{key} differs with the programs' K")
            self.assertEqual(text(a[key]), text(none[key]), f"{key} differs between a store with the counts and one without")
        self.assertIn("won", a["user"])
        self.assertEqual(sorted(a["briefs"]), ["busy", "dead", "won"], "really read")
        self.assertEqual(sorted(a["state_less_the_sealed_keys"]), ["busy", "dead", "seed-overnight-spy", "won"])
        self.assertTrue(a["state_less_the_sealed_keys"]["won"], "the view is not empty: the unsealed keys are in it")

    def test_no_count_and_no_key_of_the_seat_rule_reaches_a_generator(self):
        for name in ("a", "b"):
            read = text(reads(self, name))
            for word in WORDS:
                self.assertFalse(re.search(rf"(?<!\d){re.escape(word)}(?!\d)", read), f"world {name}: a generator read {word}")

    def test_the_worlds_really_differ(self):
        (a, _), (b, _), (none, _) = world(self, "a"), world(self, "b"), world(self, "none")
        sa, sb, sn = (x.family("won")["state"].get(elane.SEAT_KEY) for x in (a, b, none))
        self.assertTrue(sa and sb and sa != sb and sn is None)
        self.assertNotEqual(Path(a.root, "live.sqlite").read_bytes(), Path(b.root, "live.sqlite").read_bytes())
        self.assertFalse(Path(none.root, "live.sqlite").exists())

        def gate(store) -> list:
            return [e["payload"] for e in store.events_after(0, limit=5000) if e["kind"] == "swarm.gate"]

        self.assertNotEqual(gate(a), gate(b))
        # With the key left out of the seal's list, the same view WOULD differ: the list is what holds it.
        open_keys = elane_seal.SEALED_KEYS - {elane.SEAT_KEY}
        seen = [{k: v for k, v in x.family("won")["state"].items() if k not in open_keys} for x in (a, b)]
        self.assertNotEqual(text(seen[0]), text(seen[1]))


if __name__ == "__main__":
    unittest.main()
