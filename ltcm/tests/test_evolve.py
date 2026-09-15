import copy
import json
import random
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from ltcm.broker import Instrument
from ltcm.evolve import (
    EFFORTS,
    MEMORY_LIMITS,
    MODEL_PROFILES,
    PROFILE_MUTATION_ODDS,
    Evolution,
    base_name,
    lineage,
    roman,
)
from ltcm.events import EventLog
from ltcm.manifest import DeskManifest, load_manifest
from ltcm.provider import PROFILES
from ltcm.tests.test_manifest import SAMPLE

AAPL = Instrument("equity", "AAPL", "alpaca")


class FakeProvider:
    def __init__(self, text="# Rewritten playbook\n\nOne rule, tested forward.\n"):
        self.text = text
        self.calls = []

    def respond(self, profile, items, **kwargs):
        self.calls.append({"profile": profile, "items": items, **kwargs})
        if self.text is None:
            raise RuntimeError("budget_exceeded")
        return SimpleNamespace(
            output_text=self.text, cost_usd=Decimal("0.05"),
            incomplete=getattr(self, "incomplete", False), incomplete_reason=getattr(self, "incomplete_reason", None),
        )


class EvolveCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.desks = self.root / "desks"
        self.playbooks = self.root / "playbooks"
        self.desks.mkdir()
        self.playbooks.mkdir()
        self.log = EventLog(self.root / "events.sqlite")
        self.provider = FakeProvider()

    def tearDown(self):
        self.log.close()
        self.tmp.cleanup()

    def write_manifest(self, desk_id, **overrides):
        data = copy.deepcopy(SAMPLE)
        data["id"] = desk_id
        data["playbook"] = f"playbooks/{desk_id}.md"
        data.update(overrides)
        DeskManifest.from_dict(data)  # fail loudly in the test, not later
        (self.desks / f"{desk_id}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        (self.playbooks / f"{desk_id}.md").write_text(
            f"# {desk_id} playbook\n\n## What I trade\n\nDrift.\n", encoding="utf-8"
        )
        return data

    def evolution(self, **config):
        config = {"live_venues": ("alpaca", "kalshi"), **config}
        return Evolution(
            self.log, self.desks, self.playbooks, provider=self.provider, config=config
        )

    def allocate(self, allocations, at):
        self.log.append(
            "committee",
            "committee.allocation",
            {"allocations": {k: str(v) for k, v in allocations.items()}, "reasons": {}},
            at=at,
        )

    def fill(self, desk, side, quantity, price, at):
        seq = self.log.latest_seq() + 1
        self.log.append(
            "broker:shadow",
            "broker.fill",
            {
                "fill_id": f"f{seq}",
                "order_id": f"o{seq}",
                "desk_id": desk,
                "instrument": AAPL.to_dict(),
                "side": side,
                "quantity": str(quantity),
                "price": str(price),
                "fee": "0",
                "at": at,
            },
            at=at,
        )

    def run_variant(self, desk_id, *, decisions=20, exit_price="101", days=30):
        """Give a variant a forward record: `decisions` fills and a closing mark."""
        self.fill(desk_id, "buy", "1", "100", "2026-09-01T14:00:00.000Z")
        for n in range(max(0, decisions - 2) // 2):
            day = f"2026-09-{2 + n:02d}"
            self.fill(desk_id, "buy", "1", "100", f"{day}T14:00:00.000Z")
            self.fill(desk_id, "sell", "1", "100", f"{day}T15:00:00.000Z")
        self.fill(desk_id, "sell", "1", exit_price, "2026-09-20T15:00:00.000Z")
        self.log.append(
            f"ledger:{desk_id}",
            "ledger.mark",
            {
                "equity": "0",
                "cash": "0",
                "positions": [],
                "daily_pnl": "0",
                "as_of": f"2026-09-{days:02d}T20:00:00.000Z",
            },
            at=f"2026-09-{days:02d}T20:00:00.000Z",
        )


class ScoreTests(EvolveCase):
    def test_score_is_return_over_pain(self):
        self.write_manifest("earnings-01")
        self.allocate({"earnings-01": "1000"}, "2026-09-01T13:00:00.000Z")
        self.fill("earnings-01", "buy", "10", "100", "2026-09-01T14:00:00.000Z")
        evolution = self.evolution()
        ledger = evolution.ledger("earnings-01")
        ledger.mark({AAPL.key: Decimal("120")}, "2026-09-02T20:00:00.000Z")
        ledger.mark({AAPL.key: Decimal("110")}, "2026-09-03T20:00:00.000Z")
        state = ledger.state("2026-09-03T20:00:00.000Z")
        self.assertEqual(state.time_weighted_return_pct, Decimal("10.0000"))
        self.assertEqual(state.max_drawdown_pct, Decimal("0.083333"))
        # 10 / (1 + 0.5 * 0.083333)
        self.assertEqual(evolution.score("earnings-01", "2026-09-03T20:00:00.000Z"),
                         Decimal("9.600002"))
        self.assertEqual(
            evolution.score(load_manifest(self.desks / "earnings-01.json"),
                            "2026-09-03T20:00:00.000Z"),
            Decimal("9.600002"),
        )


class SeedTests(EvolveCase):
    """Seeding is what starts a family's race: children of the live desk, born shadow."""

    def setUp(self):
        super().setUp()
        self.write_manifest("earnings-01", capital={"mode": "live", "usd": "1000"})
        self.allocate({"earnings-01": "1000"}, "2026-09-01T13:00:00.000Z")

    def test_a_family_is_bred_up_to_the_target_from_its_live_desk(self):
        evolution = self.evolution(target_variants=3)
        actions = evolution.seed("2026-09-15T19:00:00.000Z")
        self.assertEqual([a["action"] for a in actions], ["spawned", "spawned"])
        self.assertEqual({a["reason"] for a in actions}, {"seed"})
        self.assertEqual({a["parent_id"] for a in actions}, {"earnings-01"})
        family = evolution.families()["earnings"]
        self.assertEqual(len(family), 3)
        children = [m for m in family if m.id != "earnings-01"]
        self.assertTrue(all(m.capital_mode == "shadow" for m in children))
        self.assertTrue(all(m.parent_id == "earnings-01" for m in children))
        self.assertEqual(sorted(m.id for m in children), ["earnings-01-2", "earnings-01-3"])
        self.assertEqual(len(self.log.read(kind="evolution.spawned")), 2)

    def test_a_full_family_is_left_alone(self):
        evolution = self.evolution(target_variants=3)
        evolution.seed("2026-09-15T19:00:00.000Z")
        self.assertEqual(evolution.seed("2026-09-15T20:00:00.000Z"), [])
        self.assertEqual(len(evolution.families()["earnings"]), 3)

    def test_the_default_target_of_one_never_breeds(self):
        self.assertEqual(self.evolution().seed("2026-09-15T19:00:00.000Z"), [])

    def test_a_bounded_pass_gives_every_family_a_sibling_before_any_gets_a_third(self):
        self.write_manifest("crypto-01", family="crypto", capital={"mode": "live", "usd": "500"})
        self.allocate({"earnings-01": "1000", "crypto-01": "500"}, "2026-09-01T13:00:00.000Z")
        evolution = self.evolution(target_variants=4)
        first = evolution.seed("2026-09-15T19:00:00.000Z", limit=2)
        self.assertEqual(sorted(a["family"] for a in first), ["crypto", "earnings"])
        second = evolution.seed("2026-09-15T20:00:00.000Z", limit=2)
        self.assertEqual(sorted(a["family"] for a in second), ["crypto", "earnings"])
        self.assertEqual({len(v) for v in evolution.families().values()}, {3})

    def test_the_ceiling_still_holds(self):
        evolution = self.evolution(target_variants=9, max_variants=2)
        actions = evolution.seed("2026-09-15T19:00:00.000Z")
        self.assertEqual(len(actions), 1)
        self.assertEqual(len(evolution.families()["earnings"]), 2)


class SelectionTests(EvolveCase):
    def setUp(self):
        super().setUp()
        self.write_manifest("earnings-01")
        self.write_manifest("earnings-02")
        self.allocate(
            {"earnings-01": "1000", "earnings-02": "1000"}, "2026-09-01T13:00:00.000Z"
        )

    def test_a_single_variant_family_is_left_alone(self):
        (self.desks / "earnings-02.json").unlink()
        self.assertEqual(self.evolution().select("2026-09-30T20:00:00.000Z"), [])
        self.assertEqual(self.log.read(kind="evolution.retired"), [])

    def test_a_young_family_is_left_alone(self):
        self.run_variant("earnings-01", exit_price="130")
        self.run_variant("earnings-02", exit_price="90")
        self.assertEqual(self.evolution(min_days=90).select("2026-09-30T20:00:00.000Z"), [])

    def test_the_worst_shadow_variant_is_retired_and_replaced(self):
        self.run_variant("earnings-01", exit_price="130")  # +30
        self.run_variant("earnings-02", exit_price="90")  # -10
        actions = self.evolution(margin="1").select("2026-09-30T20:00:00.000Z")
        self.assertEqual([a["action"] for a in actions], ["retired", "spawned"])
        retired, spawned = actions
        self.assertEqual(retired["desk_id"], "earnings-02")
        self.assertEqual(retired["reason"], "below family median")
        self.assertIn("family_median", retired["score"])

        self.assertEqual(spawned["desk_id"], "earnings-02-2")
        self.assertEqual(spawned["parent_id"], "earnings-02")
        self.assertEqual(spawned["generation"], 2)
        self.assertIn(spawned["mutation"]["reasoning_effort"], EFFORTS)
        self.assertIn(spawned["mutation"]["memory_limit"], MEMORY_LIMITS)

        # The spawned manifest is real, valid and loadable by the service.
        path = self.desks / "earnings-02-2.json"
        child = load_manifest(path)
        self.assertEqual(child.id, "earnings-02-2")
        self.assertEqual(child.family, "earnings")
        self.assertEqual(child.generation, 2)
        self.assertEqual(child.parent_id, "earnings-02")
        self.assertEqual(child.capital_mode, "shadow")
        self.assertEqual(child.playbook, "playbooks/earnings-02-2.md")
        self.assertTrue((self.playbooks / "earnings-02-2.md").exists())
        self.assertNotEqual(child.persona, load_manifest(self.desks / "earnings-02.json").persona)

        # The parent's own manifest was not touched.
        parent = json.loads((self.desks / "earnings-02.json").read_text())
        self.assertEqual(parent["generation"], 1)
        self.assertEqual(parent["capital"]["mode"], "shadow")

    def test_a_mature_variant_that_never_decided_is_retired_as_a_dud(self):
        # earnings-01 traded; earnings-02 sat for a month and never proposed a thing.
        self.run_variant("earnings-01", exit_price="105")
        self.log.append(
            "ledger:earnings-02", "ledger.mark",
            {"equity": "1000", "cash": "1000", "positions": [], "daily_pnl": "0", "as_of": "2026-09-30T20:00:00.000Z"},
            at="2026-09-30T20:00:00.000Z",
        )
        actions = self.evolution().select("2026-09-30T20:00:00.000Z")
        retired = [a for a in actions if a["action"] == "retired"]
        self.assertEqual([a["desk_id"] for a in retired], ["earnings-02"])
        self.assertEqual(retired[0]["reason"], "no decisions")
        self.assertEqual([a["action"] for a in actions if a["action"] == "spawned"], ["spawned"])

    def test_retirement_needs_enough_decisions(self):
        self.run_variant("earnings-01", exit_price="130")
        self.run_variant("earnings-02", exit_price="90", decisions=4)
        self.assertEqual(self.evolution(margin="1").select("2026-09-30T20:00:00.000Z"), [])

    def test_a_close_race_does_not_retire_anyone(self):
        self.run_variant("earnings-01", exit_price="101")
        self.run_variant("earnings-02", exit_price="100.5")
        self.assertEqual(self.evolution(margin="5").select("2026-09-30T20:00:00.000Z"), [])

    def test_selection_is_idempotent_within_a_run(self):
        self.run_variant("earnings-01", exit_price="130")
        self.run_variant("earnings-02", exit_price="90")
        evolution = self.evolution(margin="1")
        evolution.select("2026-09-30T20:00:00.000Z")
        self.assertEqual(len(self.log.read(kind="evolution.retired")), 1)
        evolution.select("2026-09-30T21:00:00.000Z")
        self.assertEqual(len(self.log.read(kind="evolution.retired")), 1)
        self.assertEqual(len(self.log.read(kind="evolution.spawned")), 1)


class PlaybookTests(EvolveCase):
    def test_the_provider_rewrites_the_child_playbook(self):
        self.write_manifest("earnings-01")
        self.write_manifest("earnings-02")
        self.log.append(
            "desk:earnings-02",
            "desk.postmortem",
            {"period": "2026-W37", "text": "I chased three gaps and paid for it.",
             "lessons": ["wait for the second session"]},
            at="2026-09-20T20:00:00.000Z",
        )
        evolution = self.evolution()
        parent = load_manifest(self.desks / "earnings-02.json")
        best = load_manifest(self.desks / "earnings-01.json")
        body = evolution.write_playbook(parent, best, "earnings-03", "2026-09-30T20:00:00.000Z")
        self.assertIn("Rewritten playbook", body)
        packet = self.provider.calls[0]["items"][1]["content"]
        self.assertIn("I chased three gaps", packet)
        self.assertIn("earnings-01", packet)
        self.assertEqual(self.provider.calls[0]["desk_id"], "earnings-03")
        self.assertIsNone(self.provider.calls[0]["tools"])

    def test_a_rewrite_cut_off_at_the_output_limit_is_not_a_playbook(self):
        self.write_manifest("earnings-01")
        self.provider.text = "# Half a playbook\n\n## Rules\n\n1. Always"
        self.provider.incomplete = True
        self.provider.incomplete_reason = "max_output_tokens"
        evolution = self.evolution()
        evolution.spawn(load_manifest(self.desks / "earnings-01.json"), None, "2026-09-15T19:00:00.000Z")
        child = (self.playbooks / "earnings-01-2.md").read_text(encoding="utf-8")
        self.assertNotIn("Half a playbook", child)
        self.assertIn("earnings-01 playbook", child)  # the parent's, whole
        alerts = [e.payload["text"] for e in self.log.read(kind="ops.alert")]
        self.assertTrue(any("incomplete (max_output_tokens)" in text for text in alerts), alerts)

    def test_a_provider_failure_copies_the_parent_playbook(self):
        self.write_manifest("earnings-01")
        self.write_manifest("earnings-02")
        self.provider.text = None
        evolution = self.evolution()
        parent = load_manifest(self.desks / "earnings-02.json")
        body = evolution.write_playbook(parent, None, "earnings-03", "2026-09-30T20:00:00.000Z")
        self.assertIn("earnings-02 playbook", body)
        alert = self.log.last("ops", "ops.alert")
        self.assertIn("copied from earnings-02", alert.payload["text"])


class PromotionTests(EvolveCase):
    def setUp(self):
        super().setUp()
        self.write_manifest("earnings-01")
        self.allocate({"earnings-01": "1000"}, "2026-09-01T13:00:00.000Z")

    def test_a_desk_that_fails_its_gates_is_not_promoted(self):
        self.assertEqual(self.evolution().promote("2026-09-30T20:00:00.000Z"), [])
        self.assertEqual(self.log.read(kind="evolution.promoted"), [])

    def test_a_desk_that_passes_its_gates_is_promoted(self):
        for n in range(10):
            day = f"2026-09-{2 + n:02d}"
            self.fill("earnings-01", "buy", "1", "100", f"{day}T14:00:00.000Z")
            self.fill("earnings-01", "sell", "1", "101", f"{day}T15:00:00.000Z")
        evolution = self.evolution()
        evolution.ledger("earnings-01").mark({}, "2026-09-21T20:00:00.000Z")
        promoted = evolution.promote("2026-09-21T20:00:00.000Z")
        self.assertEqual([p["desk_id"] for p in promoted], ["earnings-01"])
        event = self.log.last("evolution", "evolution.promoted")
        self.assertEqual(event.payload["from"], "shadow")
        self.assertEqual(event.payload["to"], "live")
        self.assertEqual(event.payload["gate"], "A")
        self.assertTrue(event.public)
        # Promotion is a log fact; the manifest file still says shadow.
        self.assertEqual(load_manifest(self.desks / "earnings-01.json").capital_mode, "shadow")
        # And it does not happen twice.
        self.assertEqual(evolution.promote("2026-09-22T20:00:00.000Z"), [])


class VenueGateTests(EvolveCase):
    """A desk can earn a live sleeve on a venue the floor has not opened. Say so, and wait."""

    def setUp(self):
        super().setUp()
        self.write_manifest("earnings-01")
        self.allocate({"earnings-01": "1000"}, "2026-09-01T13:00:00.000Z")
        for n in range(10):
            day = f"2026-09-{2 + n:02d}"
            self.fill("earnings-01", "buy", "1", "100", f"{day}T14:00:00.000Z")
            self.fill("earnings-01", "sell", "1", "101", f"{day}T15:00:00.000Z")

    def evolve(self, **config):
        evolution = self.evolution(**config)
        evolution.ledger("earnings-01").mark({}, "2026-09-21T20:00:00.000Z")
        return evolution

    def test_a_passing_desk_on_a_closed_venue_is_deferred_in_public(self):
        evolution = self.evolve(live_venues=("kalshi",))  # alpaca is not open yet
        self.assertEqual(evolution.promote("2026-09-21T20:00:00.000Z"), [])
        self.assertEqual(self.log.read(kind="evolution.promoted"), [])
        gate = self.log.last("committee", "committee.gate")
        self.assertEqual(gate.payload["desk_id"], "earnings-01")
        self.assertEqual(gate.payload["reason"], "venue not enabled")
        self.assertFalse(gate.payload["passed"])
        self.assertEqual(gate.payload["failed"], ["venue"])
        self.assertEqual(gate.payload["evidence"]["venue"], "alpaca")
        self.assertFalse(gate.payload["evidence"]["venue_enabled"])
        self.assertTrue(gate.payload["evidence"]["gate_evidence_passed"])
        self.assertTrue(gate.public)

    def test_the_next_run_after_the_venue_opens_promotes_it_on_the_same_evidence(self):
        self.evolve(live_venues=("kalshi",)).promote("2026-09-21T20:00:00.000Z")
        promoted = self.evolve(live_venues=("kalshi", "alpaca")).promote("2026-09-22T20:00:00.000Z")
        self.assertEqual([p["desk_id"] for p in promoted], ["earnings-01"])
        event = self.log.last("evolution", "evolution.promoted")
        self.assertEqual(event.payload["venue"], "alpaca")
        self.assertEqual(event.payload["from"], "shadow")

    def test_a_desk_with_no_live_venues_configured_is_never_promoted(self):
        self.assertEqual(self.evolve(live_venues=()).promote("2026-09-21T20:00:00.000Z"), [])


class LineageTests(EvolveCase):
    def test_lineage_orders_variants_by_generation(self):
        self.write_manifest("earnings-01")
        self.write_manifest("earnings-03", generation=2, parent_id="earnings-01")
        self.write_manifest("kalshi-01", family="kalshi")
        manifests = [load_manifest(p) for p in sorted(self.desks.glob("*.json"))]
        self.assertEqual(
            lineage(manifests),
            {"earnings": ["earnings-01", "earnings-03"], "kalshi": ["kalshi-01"]},
        )

    def test_a_child_is_named_after_its_parent_and_generation(self):
        self.write_manifest("rosenfeld", name="Rosenfeld", family="earnings")
        parent = load_manifest(self.desks / "rosenfeld.json")
        self.assertEqual(self.evolution().next_id(parent), ("rosenfeld-2", 2))
        data, _ = self.evolution().mutate(parent, "rosenfeld-2", 2)
        self.assertEqual(data["name"], "Rosenfeld II")
        self.assertEqual(data["family"], "earnings")
        self.assertEqual(data["parent_id"], "rosenfeld")
        self.assertEqual(data["generation"], 2)
        DeskManifest.from_dict(data)  # the manifest schema accepts the lineage id

    def test_a_grandchild_counts_on_without_repeating_the_numeral(self):
        self.write_manifest(
            "rosenfeld-2", name="Rosenfeld II", generation=2, parent_id="rosenfeld"
        )
        child = load_manifest(self.desks / "rosenfeld-2.json")
        desk_id, generation = self.evolution().next_id(child)
        self.assertEqual((desk_id, generation), ("rosenfeld-2-3", 3))
        data, _ = self.evolution().mutate(child, desk_id, generation)
        self.assertEqual(data["name"], "Rosenfeld III")
        DeskManifest.from_dict(data)

    def test_an_id_is_never_reused_even_after_a_retirement(self):
        self.write_manifest("rosenfeld", name="Rosenfeld")
        self.write_manifest(
            "rosenfeld-2", name="Rosenfeld II", generation=2, parent_id="rosenfeld"
        )
        parent = load_manifest(self.desks / "rosenfeld.json")
        self.log.append(
            "evolution",
            "evolution.retired",
            {"desk_id": "rosenfeld-2", "reason": "below family median", "score": {}},
            at="2026-09-20T20:00:00.000Z",
        )
        self.assertEqual(self.evolution().next_id(parent), ("rosenfeld-3", 3))

    def test_the_curated_model_list_is_one_the_provider_prices(self):
        self.assertTrue(MODEL_PROFILES)
        for profile in MODEL_PROFILES:
            self.assertIn(profile, PROFILES)

    def test_about_one_child_in_three_is_born_on_another_model(self):
        self.write_manifest("rosenfeld", name="Rosenfeld")
        parent = load_manifest(self.desks / "rosenfeld.json")
        self.assertEqual(parent.model.profile, "pro_flex")
        evolution = self.evolution()

        rng = random.Random(20260915)
        alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
        sample = 300
        changed = []
        for _ in range(sample):
            desk_id = "rosenfeld-" + "".join(rng.choice(alphabet) for _ in range(6))
            data, mutation = evolution.mutate(parent, desk_id, 2)
            profile = data["model"]["profile"]
            self.assertIn(profile, PROFILES)  # never a profile the provider cannot price
            self.assertEqual(mutation["model_profile"], profile)
            self.assertEqual(mutation["parent_model_profile"], "pro_flex")
            self.assertEqual(mutation["model_changed"], profile != "pro_flex")
            # The rest of the genome still moves on every child.
            self.assertIn(mutation["reasoning_effort"], EFFORTS)
            self.assertIn(mutation["memory_limit"], MEMORY_LIMITS)
            if mutation["model_changed"]:
                self.assertIn(profile, MODEL_PROFILES)
                self.assertNotEqual(profile, parent.model.profile)
                changed.append(profile)

        expected = sample / PROFILE_MUTATION_ODDS
        self.assertGreater(len(changed), expected * 0.7, "the model almost never moves")
        self.assertLess(len(changed), expected * 1.3, "the model moves too often to keep a control")
        # Every alternative is reachable; none of them is the parent's own profile.
        self.assertEqual(set(changed), set(MODEL_PROFILES) - {"pro_flex"})

    def test_the_mutation_is_deterministic_in_the_childs_id(self):
        self.write_manifest("rosenfeld", name="Rosenfeld")
        parent = load_manifest(self.desks / "rosenfeld.json")
        first = self.evolution().mutate(parent, "rosenfeld-2", 2)
        second = self.evolution().mutate(parent, "rosenfeld-2", 2)
        self.assertEqual(first, second)

    def test_a_parent_on_an_uncurated_model_still_breeds_onto_the_list(self):
        self.write_manifest("krasker", name="Krasker", model={**SAMPLE["model"], "profile": "k3"})
        parent = load_manifest(self.desks / "krasker.json")
        evolution = self.evolution()
        rng = random.Random(7)
        seen = set()
        for _ in range(60):
            desk_id = "krasker-" + "".join(rng.choice("abcdefghij") for _ in range(5))
            data, mutation = evolution.mutate(parent, desk_id, 2)
            if mutation["model_changed"]:
                seen.add(data["model"]["profile"])
            else:
                self.assertEqual(data["model"]["profile"], "k3")  # inherited, not invented
        self.assertTrue(seen <= set(MODEL_PROFILES))
        self.assertTrue(seen)

    def test_a_spawned_desk_publishes_the_model_it_was_born_on(self):
        self.write_manifest("earnings-01")
        self.write_manifest("earnings-02")
        parent = load_manifest(self.desks / "earnings-02.json")
        spawned = self.evolution().spawn(parent, None, "2026-09-30T20:00:00.000Z")
        child = load_manifest(self.desks / f"{spawned['desk_id']}.json")
        self.assertEqual(spawned["mutation"]["model_profile"], child.model.profile)
        self.assertEqual(spawned["mutation"]["parent_model_profile"], parent.model.profile)
        self.assertIn(child.model.profile, PROFILES)
        event = self.log.last("evolution", "evolution.spawned")
        self.assertEqual(event.payload["mutation"]["model_profile"], child.model.profile)

    def test_roman_numerals_and_base_names(self):
        self.assertEqual([roman(n) for n in (1, 2, 3, 4, 9, 14)], ["I", "II", "III", "IV", "IX", "XIV"])
        self.assertEqual(base_name("Rosenfeld II"), "Rosenfeld")
        self.assertEqual(base_name("Rosenfeld"), "Rosenfeld")
        self.assertEqual(base_name("Meriwether XIV"), "Meriwether")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
