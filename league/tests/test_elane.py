"""THE EQUITY LANES' swarm side (release E1, Oct 2026; league/swarm/elane.py): the settings and their bounds, card
admission, the lane-scoped graveyard and lineages (A8.12), one Validation try and one look per lineage (and R3's retry),
the receipt refusal, the equity roster's seats apart from dlane's, the options readers skipping equity families, and the
band rules swarm owns in league/equity/bands.py (with `league.live.money.band_for`'s forward)."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from unittest import mock

from league.equity import BETA, EQUITY, LANES
from league.equity import bands as ebands
from league.equity import screen as S
from league.swarm import bands, cards, dlane, elane
from league.swarm import settings as settings_mod
from league.swarm.gate import run_sha
from league.swarm.store import OPTIONS_ONLY_SQL
from league.tests import REAL_POLICY_PATH
from league.tests.test_swarm_store import SPEC, StoreCase

REPO = Path(__file__).resolve().parents[2]
ON = {"elane": {"mode": "gate"}}
SHA = "a" * 64
CODE = "NEEDS = {'symbols': ['SPY'], 'history': 2}\nPARAMS = {}\n\n\ndef decide(ctx):\n    return []\n"


def card(lane: str = BETA, **over):
    out = {"lane": lane, "structure": "etf", "symbols": ["SPY"],
           "hypothesis": "Most of the index's long-run return has accrued overnight, between the close and the next open, "
                         "and holders who carry the gap are paid for it.",
           "mechanism_class": "calendar_flow", "inputs": ["clock"], "holding": "days_1_3",
           "cost": {"hurdle": 0.0003, "why": "two half-spreads and the SEC and TAF fees on the sale"},
           "comparison": "the same-exposure buy-and-hold of SPY over the same sessions (S1-X)",
           "falsification": "refuted when its one sealed look fails S1 (the pooled t below c_used)"}
    out.update(over)
    return out


def equity_spec(fid: str = "beta-overnight", lane: str = BETA, symbols=("SPY",), **over):
    return {"id": fid, "mechanism": "Hold the ETF overnight from each close to the next open (MARKET BETA).",
            "structure": "etf", "roots": list(symbols), "symbols": list(symbols), "lane": lane, **over}


def pinned_block(**over):
    block = {"name": "S1", "receipt_sha256": SHA, "c_R": 1.5, "c_X": 0.9, "fp_cap": 0.12, "owner_wall": 0.15,
             "retry": True, "r4": {}, "beside": "c_used {c_used}, c_H {c_H}, own FP {own_fp}"}
    block.update(over)
    return block


class Settings(StoreCase):
    def test_defaults_are_the_rollback(self):
        c = elane.cfg({})
        self.assertEqual((c["mode"], c["structures"], c["roster"], c["val_tries"], c["looks_per_lineage"]),
                         ("off", ["etf"], 3, 1, 1))
        self.assertFalse(elane.on({}))
        self.assertFalse(elane.on({"elane": {"mode": "shadow"}}), "a malformed mode reads off")
        self.assertTrue(elane.on(ON))

    def test_each_value_is_held_inside_its_bound(self):
        c = elane.cfg({"elane": {"mode": "gate", "roster": 9, "val_tries": 4, "looks_per_lineage": 2,
                                 "program_loss_usd": -1000, "universe": ["spy", "XYZ", "qqq"], "structures": ["etf", "bond"],
                                 "birth_share": 0.9}})
        self.assertEqual((c["roster"], c["val_tries"], c["looks_per_lineage"], c["program_loss_usd"]), (3, 1, 1, -300.0))
        self.assertEqual((c["universe"], c["structures"], c["birth_share"]), (["SPY", "QQQ"], ["etf"], 0.5))
        self.assertEqual(elane.cfg({"elane": {"roster": 1.5, "program_loss_usd": -10}})["roster"], 3)
        self.assertEqual(elane.cfg({"elane": {"program_loss_usd": -10}})["program_loss_usd"], -25.0)
        self.assertEqual(elane.cfg({"elane": {"roster": 0}})["roster"], 0)

    def test_the_policy_layer_holds_the_block_and_the_defaults_hold_its_shape(self):
        self.assertEqual(settings_mod.DEFAULTS["elane"], {"mode": "off"})
        self.assertIn("elane", settings_mod.policy_shape({"elane": None}))
        layer, status = settings_mod.read_policy(REAL_POLICY_PATH)
        self.assertEqual(status["state"], "ok")
        block = layer["elane"]
        self.assertEqual((block["mode"], block["structures"], block["birth_share"], block["roster"], block["val_tries"],
                          block["looks_per_lineage"], block["program_loss_usd"]), ("off", ["etf"], 0.0, 3, 1, 1, -300))
        self.assertEqual(sorted(block["screens"]), sorted(LANES))
        self.assertEqual(elane.cfg({"elane": block})["roster"], 3)

    def test_the_roster_equals_the_constitutions_probe_programs(self):
        from league import constitution

        layer, _ = settings_mod.read_policy(REAL_POLICY_PATH)
        money = getattr(constitution, "CONSTITUTION", {}).get("equity_money")
        if not money:
            self.skipTest("the constitution's equity_money block is the money package's (merged before swarm)")
        self.assertEqual(layer["elane"]["roster"], money["probe"]["max_programs"])

    def test_a_pinned_receipt_is_the_files_bytes(self):
        layer, _ = settings_mod.read_policy(REAL_POLICY_PATH)
        path = REPO / S.RECEIPT_PATH
        for lane in LANES:
            pinned = layer["elane"]["screens"][lane]["receipt_sha256"]
            if pinned is None:
                continue  # E1 merges with none pinned: the integrator pins the study's receipt
            self.assertTrue(path.exists(), "a pinned receipt names a file the repository holds")
            self.assertEqual(pinned, hashlib.sha256(path.read_bytes()).hexdigest())


class Cards(StoreCase):
    def test_an_equity_card_is_admitted_inside_its_lanes_box(self):
        got, errors = cards.validate(card(), "etf", roots=["SPY"], settings=ON)
        self.assertEqual(errors, [])
        self.assertEqual((got["lane"], got["structure"], got["symbols"]), (BETA, "etf", ["SPY"]))
        self.assertNotIn("ablation", got, "its comparison is the same-exposure buy-and-hold, never an ablation switch")
        self.assertEqual(cards.key_of(got, "etf")["family"], "beta:etf", "its cell is lane-scoped")
        eq, errors = cards.validate(card(EQUITY, mechanism_class="trend_momentum"), "etf", roots=["SPY"], settings=ON)
        self.assertEqual((errors, cards.key_of(eq, "etf")["family"]), ([], "equity:etf"))
        premium, errors = cards.validate(card(mechanism_class="equity_premium"), "etf", roots=["SPY"], settings=ON)
        self.assertEqual(errors, [])

    def test_every_reason_outside_the_box_is_named(self):
        self.assertTrue(any("equity lanes are closed" in e for e in elane.card_errors(card(), "etf", ["SPY"], {})))
        _, errors = cards.validate(card(), "etf", roots=["SPY"], settings={"dlane": {"mode": "gate"}})
        self.assertEqual(errors[0], "lane: 'beta' is not one of alpha, direction", "the lanes off: read as before")
        got, _ = cards.validate(card(), "etf", roots=["SPY"], settings={})
        self.assertNotIn("lane", got or {}, "the lanes off: an unknown key, ignored as before")
        with self.assertRaises(ValueError):
            self.store.add_family({**equity_spec(), "lane": None}, origin="seed")
        _, errors = cards.validate(card(symbols=["XLK"]), "etf", roots=["XLK"], settings=ON)
        self.assertTrue(any(e.startswith("symbols:") and "XLK" in e for e in errors), errors)
        _, errors = cards.validate(card(structure="stock"), "stock", roots=["SPY"],
                                   settings={"elane": {"mode": "gate", "structures": ["etf", "stock"]}})
        self.assertTrue(any("beta card trades ETFs only" in e for e in errors), errors)
        _, errors = cards.validate(card(structure="stock"), "stock", roots=["SPY"], settings=ON)
        self.assertTrue(any(e.startswith("structure:") for e in errors), errors)
        _, errors = cards.validate(card(inputs=["implied_vol"]), "etf", roots=["SPY"], settings=ON)
        self.assertTrue(any(e.startswith("inputs:") and "implied_vol" in e for e in errors), errors)
        _, errors = cards.validate(card(ablation={"flat": True}), "etf", roots=["SPY"], settings=ON)
        self.assertTrue(any(e.startswith("ablation:") and "never flat" in e for e in errors), errors)
        _, errors = cards.validate(card(symbols=["QQQ"]), "etf", roots=["SPY"], settings=ON)
        self.assertTrue(any("not the proposal's" in e for e in errors), errors)

    def test_options_cards_are_unchanged(self):
        raw = {k: v for k, v in card().items() if k not in ("lane", "structure", "symbols")}
        got, errors = cards.validate(raw, "debit_vertical", settings=ON)
        self.assertEqual(errors, [])
        self.assertNotIn("lane", got)
        self.assertEqual(got["ablation"], cards.DEFAULT_ABLATION)
        self.assertEqual(cards.key_of(got, "debit_vertical")["family"], "directional")
        on = {"dlane": {"mode": "gate"}, **ON}
        _, errors = cards.validate(card(), "etf", roots=["SPY"], settings=on)
        self.assertEqual(errors, [], "the direction lane on never reads an equity card's lane as its own")


class Lineages(StoreCase):
    def test_the_options_readers_skip_equity_families(self):
        self.store.add_family(SPEC, origin="seed")
        self.store.add_family(equity_spec("b1"), origin="seed")
        self.store.add_family(equity_spec("e1", lane=EQUITY), origin="seed")
        ids = lambda **kw: [f["id"] for f in self.store.families(**kw)]  # noqa: E731
        self.assertEqual(ids(), ["condor-vrp"])
        self.assertEqual(ids(alive=True), ["condor-vrp"])
        self.assertEqual(ids(lanes=LANES), ["b1", "e1"])
        self.assertEqual(ids(lanes=(BETA,)), ["b1"])
        self.assertEqual(ids(lanes=EQUITY), ["e1"])
        self.assertEqual(sorted(ids(lanes="all")), ["b1", "condor-vrp", "e1"])
        with self.assertRaises(ValueError):
            self.store.families(lanes=("alpha",))

    def test_a_lane_and_its_structure_go_together(self):
        with self.assertRaises(ValueError):
            self.store.add_family({**equity_spec(), "lane": None}, origin="seed")
        with self.assertRaises(ValueError):
            self.store.add_family({**equity_spec(), "structure": "iron_condor"}, origin="seed")
        with self.assertRaises(ValueError):
            self.store.add_family({**equity_spec(), "lane": "direction"}, origin="seed")
        self.store.add_family(SPEC, origin="seed")
        with self.assertRaises(ValueError):
            self.store.add_family(equity_spec("fork"), origin="fork", parent="condor-vrp")
        self.store.add_family(equity_spec("b1"), origin="seed")
        with self.assertRaises(ValueError):
            self.store.add_family({**SPEC, "id": "opt-fork"}, origin="fork", parent="b1")
        with self.assertRaises(ValueError):
            self.store.add_family(equity_spec("e-fork", lane=EQUITY), origin="fork", parent="b1")
        child = self.store.add_family(equity_spec("b-fork"), origin="fork", parent="b1")
        self.assertEqual(child["lineage"], "b1")

    def test_identical_code_links_lineages_only_inside_one_lane(self):
        self.store.add_family({**SPEC, "roots": ["SPY"]}, origin="seed")
        self.store.add_family(equity_spec("b1"), origin="seed")
        self.store.add_family(equity_spec("b2"), origin="seed")
        self.store.add_family(equity_spec("e1", lane=EQUITY), origin="seed")
        for fid in ("condor-vrp", "b1", "b2", "e1"):
            self.store.add_version(fid, CODE, {}, author="test")
        self.assertEqual(self.store._connected_lineages("b1"), ["b1", "b2"], "the same template in one lane: one lineage")
        self.assertEqual(self.store._connected_lineages("e1"), ["e1"])
        self.assertEqual(self.store._connected_lineages("condor-vrp"), ["condor-vrp"])
        self.assertFalse(self.store.link_lineages("condor-vrp", "b1"), "never an options lineage to an equity one")
        self.assertEqual(elane.lineage_key(BETA, "SPY"), "beta:SPY")
        self.assertEqual(elane.lineage_key("direction", "SPY"), "SPY", "the options keys never move")

    def test_the_learning_game_never_arms_an_equity_family_nor_counts_one_in_its_ceiling(self):
        """Integration (A8.12): the options learning game hashes every family born after its T0 on a core-five root into
        an arm, and its control arm's extra looks go to the options Gym; an equity family is never armed (whichever
        columns the game reads: the parsed row or the raw `spec`), and the game's population ceiling counts the options
        lanes only."""
        from league.swarm import game

        c = game.cfg({})
        start = "2026-01-01T00:00:00Z"
        self.store.add_family(SPEC, origin="seed")
        self.store.add_family(equity_spec("b1"), origin="seed")
        fam = self.store.family("b1")
        self.assertIsNone(game._arm_of({**fam, "born_at": "2026-10-11T00:00:00Z"}, c, start))
        raw = {"id": "b1", "lineage": "b1", "born_at": "2026-10-11T00:00:00Z", "roots": json.dumps(["SPY"]),
               "spec": json.dumps(fam["spec"])}
        self.assertIsNone(game._arm_of(raw, c, start), "the raw columns `_hidden` reads")
        options = {**self.store.family("condor-vrp"), "born_at": "2026-10-11T00:00:00Z", "roots": ["SPY"],
                   "spec": {"roots": ["SPY"]}}
        self.assertIn(game._arm_of(options, c, start), ("game", "control"), "an options family is armed as before")
        n = self.store._one(f"SELECT COUNT(*) AS n FROM families WHERE retired_at IS NULL AND {OPTIONS_ONLY_SQL}")["n"]
        self.assertEqual(n, 1)

    def test_an_equity_look_never_counts_in_an_options_lanes_leakage_alarm(self):
        """Every reader of the store's looks (the gate's own reads skip them; the progress view reads them all) counts
        an equity look in its equity lane, never in the alpha count (10 looks, more than 30% passed)."""
        from league.swarm import evidence

        equity = [{"passed": True, "detail": {"lane": lane}} for lane in (BETA, EQUITY) * 6]
        options = [{"passed": i < 3, "detail": {}} for i in range(10)]
        self.assertEqual({evidence.look_lane(x) for x in equity}, {BETA, EQUITY})
        for settings in ({}, {"dlane": {"mode": "gate"}}):
            self.assertEqual(evidence.leakage_alarms(equity + options, settings)["alpha"], False, settings)
        self.assertTrue(evidence.leakage_alarms([{"passed": True, "detail": {}}] * 10, {})["alpha"])

    def test_dlane_never_reads_an_equity_family(self):
        self.store.add_family(equity_spec("b1"), origin="seed")
        self.store.event("swarm.born", "b1", {"lane": BETA})
        self.store.event("swarm.born", None, {"lane": "direction"})
        self.assertEqual(dlane._families_in(self.store, ["b1"]), [])
        self.assertEqual([r["lane"] for r in dlane._born(self.store)], ["direction"])
        self.assertIsNone(dlane.birth_spent(self.store, ["b1"], {"dlane": {"mode": "gate"}}))
        self.assertEqual(dlane.declared_lane(self.store, self.store.family("b1")), dlane.ALPHA)
        self.assertEqual(elane.lane_of(self.store, self.store.family("b1")), BETA)
        self.assertIsNone(elane.lane_of(self.store, {"id": "x", "spec": {}}))


class Graveyard(StoreCase):
    def bury(self, fid, raw_card, spec):
        self.store.add_family(spec, origin="seed")
        got, errors = cards.validate(raw_card, spec["structure"], roots=spec["roots"], settings=ON)
        self.assertEqual(errors, [])
        cards.put(self.store, fid, got, spec["structure"])
        self.store.retire(fid, "refuted: its one sealed look failed")
        self.store.bury(fid, f"{fid}: refuted")

    def test_a_refuted_row_binds_only_its_own_lanes_cards(self):
        self.bury("beta-dead", card(), equity_spec("beta-dead"))
        self.bury("eq-dead", card(EQUITY), equity_spec("eq-dead", lane=EQUITY))
        options_card = {k: v for k, v in card().items() if k not in ("lane", "structure", "symbols")}
        self.bury("opt-dead", options_card, {**SPEC, "id": "opt-dead", "structure": "debit_vertical"})
        idx = cards.RebirthIndex(self.store, ON)
        self.assertEqual([r["row"] for r in idx.rows], ["opt-dead"], "no equity row is listed for an options card")
        self.assertEqual(sorted(r["row"] for r in idx.equity_rows), ["beta-dead", "eq-dead"])
        beta, _ = cards.validate(card(), "etf", roots=["SPY"], settings=ON)
        verdict = idx.check(beta, "etf", "Hold SPY overnight")
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["matched"], ["beta-dead"], "the equity lane's row does not bind a beta card")
        equity_card, _ = cards.validate(card(EQUITY), "etf", roots=["SPY"], settings=ON)
        self.assertEqual(idx.check(equity_card, "etf", "Hold SPY overnight")["matched"], ["eq-dead"])
        opt, _ = cards.validate(options_card, "debit_vertical", settings=ON)
        self.assertEqual(idx.check(opt, "debit_vertical", "Hold overnight")["matched"], ["opt-dead"])
        self.assertFalse(any("dead" in line and ("beta" in line or "eq-" in line) for line in idx.cells()))


class Ration(StoreCase):
    def setUp(self):
        super().setUp()
        self.fam = self.store.add_family(equity_spec("b1"), origin="seed")
        self.v1 = self.store.add_version("b1", CODE, {}, author="test")
        self.v2 = self.store.add_version("b1", CODE, {"x": 1}, author="test")

    def validated(self, fid="b1", n=1, status="ok"):
        self.store.add_run(fid, n, {"run_id": f"v-{fid}-{n}-{status}", "status": status, "trials": 1, "summary": {}},
                           window="validation", stress=1.0, purpose="validation")

    def test_one_validation_try_a_lineage(self):
        fam = self.store.family("b1")
        self.assertTrue(elane.try_open(self.store, fam, 1, ON))
        self.validated(status="error")
        self.assertTrue(elane.try_open(self.store, fam, 2, ON), "a run the runner could not make is no try")
        self.validated(n=1)
        self.assertTrue(elane.try_open(self.store, fam, 1, ON), "its own try, validated again: the same try")
        self.assertFalse(elane.try_open(self.store, fam, 2, ON))
        self.store.add_family(equity_spec("b2"), origin="seed")
        self.store.add_version("b2", CODE, {}, author="test")  # the same template: the same lineage
        self.assertFalse(elane.try_open(self.store, self.store.family("b2"), 1, ON))
        self.assertFalse(elane.try_open(self.store, self.store.family("condor-vrp") or {"id": "x"}, 1, ON))
        self.assertEqual([(t["family"], t["version"]) for t in elane.lineage_tries(self.store, "b1")], [("b1", 1)])

    def test_one_look_a_lineage_and_the_spent_causes(self):
        self.assertIsNone(elane.lineage_spent(self.store, self.store.family("b1"), ON))
        self.validated(n=1)
        self.assertIsNone(elane.lineage_spent(self.store, self.store.family("b1"), ON), "owed its verdict first")
        self.store.set_state("b1", **{elane.TRY_KEY: {"version": 1, "precheck": True, "entered": True, "retry_sha": None}})
        self.assertIsNone(elane.lineage_spent(self.store, self.store.family("b1"), ON), "it waits for its one look")
        self.store.add_look("b1", 1, run_sha(self.v1), passed=False, p_value=None, detail={"lane": BETA})
        self.assertEqual(elane.lineage_spent(self.store, self.store.family("b1"), ON), elane.SPENT_LOOK)
        self.assertEqual(elane.lineage_spent(self.store, self.store.family("b1"), {}), elane.SPENT_LOOK)
        self.store.add_family(equity_spec("b2"), origin="seed")
        self.store.add_version("b2", CODE, {}, author="test")
        self.assertEqual(elane.lineage_spent(self.store, self.store.family("b2"), ON), elane.SPENT_LOOK)

    def test_a_failed_precheck_spends_the_try(self):
        self.validated(n=1)
        self.store.set_state("b1", **{elane.TRY_KEY: {"version": 1, "precheck": False, "entered": False, "retry_sha": None}})
        self.assertEqual(elane.lineage_spent(self.store, self.store.family("b1"), ON), elane.SPENT_TRY)
        self.assertIsNone(elane.next_try(self.store, self.store.family("b1"), ON))

    def test_r3_one_validation_only_retry_after_a_failed_precheck_when_the_receipt_permits(self):
        self.validated(n=1)
        state = {elane.TRY_KEY: {"version": 1, "precheck": False, "entered": False, "retry_sha": run_sha(self.v2)},
                 elane.VERDICTS_KEY: {"1": {"entered": False}}}
        self.store.set_state("b1", **state)
        fam = self.store.family("b1")
        with mock.patch.object(elane, "_receipt", return_value=(object(), None)), \
                mock.patch.object(S, "retry_permitted", return_value=False):
            self.assertFalse(elane.try_open(self.store, fam, 2, ON), "the receipt does not permit it")
        with mock.patch.object(elane, "_receipt", return_value=(None, "no receipt")):
            self.assertFalse(elane.try_open(self.store, fam, 2, ON), "no receipt, no retry")
        with mock.patch.object(elane, "_receipt", return_value=(object(), None)), \
                mock.patch.object(S, "retry_permitted", return_value=True) as permitted:
            self.assertTrue(elane.try_open(self.store, fam, 2, ON))
            permitted.assert_called_with(mock.ANY, first_precheck_failed=True)
            self.assertIsNone(elane.lineage_spent(self.store, fam, ON), "its pre-registered retry is owed")
            self.assertEqual(elane.next_try(self.store, fam, ON), 2)
            v3 = self.store.add_version("b1", CODE, {"x": 2}, author="test")
            self.assertFalse(elane.try_open(self.store, self.store.family("b1"), v3["n"], ON),
                             "only the version hashed at the first try")
            self.validated(n=2)
            self.store.set_state("b1", **{elane.TRY_KEY: {"version": 2, "precheck": False, "entered": False,
                                                          "retry_sha": run_sha(self.v2)}})
            self.assertTrue(elane.try_open(self.store, self.store.family("b1"), 2, ON), "the same retry, again")
            self.assertEqual(elane.lineage_spent(self.store, self.store.family("b1"), ON), elane.SPENT_TRY)
            self.assertFalse(elane.try_open(self.store, self.store.family("b1"), v3["n"], ON), "never a third")
            self.assertTrue(elane.try_open(self.store, self.store.family("b1"), 1, ON), "the first try is the lineage's own")


class Receipt(StoreCase):
    def test_a_screen_with_no_pinned_receipt_is_refused(self):
        eff = elane.screen_effective(ON, BETA, policy={"elane": {"screens": {}}})
        self.assertIsNone(eff["receipt"])
        self.assertIn("no receipt sha256 is pinned", eff["why"])
        real, _ = settings_mod.read_policy(REAL_POLICY_PATH)
        committed = hashlib.sha256((REPO / S.RECEIPT_PATH).read_bytes()).hexdigest()
        for lane in LANES:
            # The integrator pinned the study's receipt (A9): the committed policy reads it whole, both lanes.
            eff = elane.screen_effective(ON, lane, policy=real)
            self.assertEqual((eff["receipt"], eff["why"], eff["screen"]), (committed, None, "S1"), lane)
        eff = elane.screen_effective(ON, BETA, policy={"elane": {"screens": {BETA: pinned_block()}}})
        self.assertEqual((eff["receipt"], eff["why"], eff["c_R"], eff["screen"]), (SHA, None, 1.5, "S1"))
        eff = elane.screen_effective(ON, BETA, policy={"elane": {"screens": {BETA: pinned_block(c_R=None)}}})
        self.assertIn("incomplete", eff["why"])
        self.assertIsNone(eff["receipt"])
        eff = elane.screen_effective({}, BETA, policy={"elane": {"screens": {BETA: pinned_block()}}})
        self.assertIn("off", eff["why"])
        eff = elane.screen_effective(ON, BETA, policy={"elane": {"screens": {BETA: pinned_block(fp_cap=0.2)}}})
        self.assertIsNotNone(eff["why"], "an FP cap past the owner's 15% wall pins nothing")

    def test_a_receipt_is_read_from_the_repositorys_policy_never_from_swarm_json(self):
        settings = {"elane": {"mode": "gate", "screens": {BETA: pinned_block()}}}
        self.assertIsNotNone(elane.screen_effective(settings, BETA, policy={"elane": {"screens": {}}})["why"])
        receipt, why = elane._receipt(settings, BETA, policy={"elane": {"screens": {}}})
        self.assertIsNone(receipt)
        self.assertIn("no receipt", why)

    def test_the_screen_judges_whether_the_pinned_block_is_a_receipt(self):
        policy = {"elane": {"screens": {BETA: pinned_block()}}}
        with mock.patch.object(S, "pinned_receipt", return_value=None):
            receipt, why = elane._receipt(ON, BETA, policy=policy)
        self.assertIsNone(receipt)
        self.assertIn("does not accept", why)
        with mock.patch.object(S, "pinned_receipt", return_value="R") as pinned:
            self.assertEqual(elane._receipt(ON, BETA, policy=policy), ("R", None))
        self.assertEqual(pinned.call_args.args[0]["receipt_sha256"], SHA)


class RosterSeats(StoreCase):
    def setUp(self):
        super().setUp()
        self.root = self.store.root
        elane._roster_good.clear()
        bands._roster_good.clear()
        self.addCleanup(elane._roster_good.clear)
        self.addCleanup(bands._roster_good.clear)

    def write(self, doc):
        (self.root / "swarm.json").write_text(doc if isinstance(doc, str) else json.dumps(doc))

    def test_the_equity_roster_reads_fail_closed(self):
        self.assertEqual(elane.roster_seats(self.root), 3, "no swarm.json: the policy's")
        self.write({"dlane": {"roster": 5}})
        self.assertEqual(elane.roster_seats(self.root), 3, "dlane.roster is not the equity roster")
        self.write({"elane": {"roster": 2}})
        self.assertEqual(elane.roster_seats(self.root), 2)
        self.write({"elane": {"roster": 7}})
        self.assertEqual(elane.roster_seats(self.root), 3, "a setting may only lower it")
        self.write({"elane": {"roster": "two"}})
        self.assertEqual(elane.roster_seats(self.root), 3, "unreadable: the last good value")
        self.write("{not json")
        self.assertEqual(elane.roster_seats(self.root), 3)
        elane._roster_good.clear()
        self.assertEqual(elane.roster_seats(self.root), elane.ROSTER_CLOSED, "no last good value: no new seat")
        self.assertEqual(bands.equity_seats(0), bands.ROSTER_CLOSED, "0 seats no equity program at all")

    def banded(self, fid, band, spec, at):
        self.store.add_family(spec, origin="seed")
        version = self.store.add_version(fid, CODE + f"# {fid}\n", {}, author="test")
        proof = {"engine": "equity-engine-1", "equity_sha256": "f" * 64, "run_sha": run_sha(version)}
        self.store.set_state(fid, banded_version=1, banded_at=at, banded_evaluator=proof)
        self.store.set_band(fid, "candidate", reason="passed its sealed look")
        if band != "candidate":
            self.store.set_band(fid, band, reason="the EquityBook")

    def test_equity_seats_apart_from_dlanes(self):
        from league.tests.evaluator_fakes import band_proof

        for i, fid in enumerate(("o1", "o2")):
            self.store.add_family({**SPEC, "id": fid, "structure": "debit_vertical"}, origin="test")
            version = self.store.add_version(fid, CODE.replace("SPY", "QQQ") + f"# {fid}\n", {}, author="test")
            self.store.set_state(fid, banded_version=1, banded_evaluator=band_proof(version), banded_at=100.0 + i,
                                 typical_by_version={"1": 50})
            self.store.set_band(fid, "candidate", reason="passed its holdout look")
        self.banded("e-probe", "probe", equity_spec("e-probe"), self.clock())
        for i, fid in enumerate(("e1", "e2", "e3")):
            self.banded(fid, "candidate", equity_spec(fid), self.clock() + 1 + i)
        self.write({"dlane": {"roster": 1}, "elane": {"roster": 3}})
        options = bands.roster(self.root)
        self.assertEqual((options["seated"], options["waiting"]), (["o1"], ["o2"]), "the options roster seats options only")
        equity = bands.roster(self.root, lanes=LANES)
        self.assertEqual((equity["probe"], equity["seated"], equity["waiting"]), (["e-probe"], ["e-probe", "e1", "e2"], ["e3"]))
        with mock.patch("league.swarm.evaluator.equity_fingerprint", return_value="f" * 64):
            bands._equity_cache = None
            self.addCleanup(setattr, bands, "_equity_cache", None)
            rows = {r["family"]: r for r in bands.read(self.root, lanes=LANES)}
            self.assertEqual(sorted(rows), ["e-probe", "e1", "e2"], "a Candidate waiting for an equity seat has no row")
            self.assertEqual((rows["e1"]["lane"], rows["e1"]["label"], rows["e1"]["symbols"], rows["e1"]["seat"]),
                             (BETA, "MARKET BETA", ["SPY"], "seated"))
            self.assertEqual(rows["e-probe"]["seat"], "probe")
            self.assertEqual([r["family"] for r in bands.read(self.root)], ["o1"], "bands.read(root) skips equity rows")
            self.assertEqual(sorted(r["family"] for r in bands.read(self.root, lanes="all")), ["e-probe", "e1", "e2", "o1"])
            self.assertEqual(bands.read(self.root, family="e1"), [], "the options reader never returns an equity row")
            self.assertEqual(bands.observe(self.root), [])
            self.assertEqual(bands.incubator(self.root, family="e1", version=1), [])
            self.write({"dlane": {"roster": 1}, "elane": {"roster": 0}})
            self.assertEqual(sorted(r["family"] for r in bands.read(self.root, lanes=LANES)), ["e-probe"],
                             "0 equity seats: no Candidate is shown, a Probe never hidden")
        with mock.patch("league.swarm.evaluator.equity_fingerprint", return_value="0" * 64):
            bands._equity_cache = None
            self.assertEqual(bands.read(self.root, lanes=LANES), [], "a band proven under another equity identity")
        with mock.patch("league.swarm.evaluator.equity_fingerprint", side_effect=RuntimeError("no identity")):
            bands._equity_cache = None
            self.assertEqual(bands.read(self.root, lanes=LANES), [], "fail-closed")


class EquityBands(StoreCase):
    ROW = {"family": "b1", "band": "candidate", "lane": BETA, "holdout_passed": True}

    def record(self):
        return ebands.EquityRecord(n=0, returns=(), pnl=Decimal("0"), bh_pnl=None, probe_sessions=0,
                                   realized_net=Decimal("0"))

    def test_the_band_transitions(self):
        with mock.patch.object(ebands, "edm1", return_value=None), \
                mock.patch.object(ebands, "sized_up", return_value=(True, "sized up")):
            self.assertEqual(ebands.next_band({**self.ROW, "holdout_passed": False}, None, None, seat_free=True)[0],
                             "candidate")
            self.assertEqual(ebands.next_band(self.ROW, None, None, seat_free=False)[0], "candidate")
            self.assertEqual(ebands.next_band(self.ROW, None, None, seat_free=True)[0], "probe")
            self.assertEqual(ebands.next_band(self.ROW, None, None, seat_free=True, sticky="EDM1")[0], "candidate")
            self.assertEqual(ebands.next_band({**self.ROW, "band": "probe"}, self.record(), None, seat_free=True),
                             ("sized", "sized up"))
            self.assertEqual(ebands.next_band({**self.ROW, "band": "probe"}, None, None, seat_free=True)[0], "probe")
            self.assertEqual(ebands.next_band({**self.ROW, "band": "sized"}, self.record(), None, seat_free=False)[0],
                             "sized")
        with mock.patch.object(ebands, "edm1", return_value="sum below the line"):
            band, why = ebands.next_band({**self.ROW, "band": "probe"}, self.record(), None, seat_free=True)
            self.assertEqual((band, why), ("candidate", "EDM1: sum below the line"))
        with mock.patch.object(ebands, "edm1", return_value=None), \
                mock.patch.object(ebands, "sized_up", return_value=(False, "n below 20")):
            self.assertEqual(ebands.next_band({**self.ROW, "band": "probe"}, self.record(), None, seat_free=True),
                             ("probe", "n below 20"))

    def test_the_options_band_for_forwards_an_equity_row_unchanged(self):
        from league.live import equity_hook
        from league.live import money as M
        from league.tests import money_fakes

        self.assertEqual(ebands.band_for_row({"band": "probe", "lane": BETA})[0], "probe")
        with mock.patch.object(equity_hook, "is_equity_row", return_value=True), \
                mock.patch.object(equity_hook, "band_for", side_effect=ebands.band_for_row):
            self.assertEqual(M.band_for(money_fakes.table(), {"band": "probe", "lane": BETA}, Decimal("2000"), None)[0],
                             "probe")
        with mock.patch.object(equity_hook, "is_equity_row", side_effect=AssertionError("an options row never asks")):
            band, _ = M.band_for(money_fakes.table(), {"band": "candidate", "holdout_passed": False}, Decimal("2000"), None)
        self.assertEqual(band, "candidate")


class Views(StoreCase):
    def test_a_beta_family_is_labelled_market_beta_and_a_seed_says_so(self):
        fam = {"spec": {"seeded": True}, "state": {elane.TRY_KEY: {"version": 1, "entered": True},
                                                   elane.LOOK_KEY: {"version": 1, "verdict": {"passed": True}, "beside": "x"}}}
        line = elane.view(fam, lane=BETA)
        self.assertEqual((line["label"], line["seeded"], line["try"], line["look"], line["beside"]),
                         ("MARKET BETA", True, {"version": 1, "entered": True}, {"version": 1, "passed": True}, "x"))
        self.assertEqual(line["notes"], [elane.BETA_NOTE, elane.SEEDED_NOTE])
        self.assertEqual(elane.view({}, lane=EQUITY)["label"], "EQUITY")
        self.assertEqual(elane.label("direction"), "")
