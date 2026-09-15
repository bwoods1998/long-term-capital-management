import copy
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from ltcm.broker import Instrument
from ltcm.evolve import EFFORTS, MEMORY_LIMITS, Evolution, lineage
from ltcm.events import EventLog
from ltcm.manifest import DeskManifest, load_manifest
from ltcm.tests.test_manifest import SAMPLE

AAPL = Instrument("equity", "AAPL", "paper")


class FakeProvider:
    def __init__(self, text="# Rewritten playbook\n\nOne rule, tested forward.\n"):
        self.text = text
        self.calls = []

    def respond(self, profile, items, **kwargs):
        self.calls.append({"profile": profile, "items": items, **kwargs})
        if self.text is None:
            raise RuntimeError("budget_exceeded")
        return SimpleNamespace(output_text=self.text, cost_usd=Decimal("0.05"))


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
            "broker:paper",
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

    def test_the_worst_paper_variant_is_retired_and_replaced(self):
        self.run_variant("earnings-01", exit_price="130")  # +30
        self.run_variant("earnings-02", exit_price="90")  # -10
        actions = self.evolution(margin="1").select("2026-09-30T20:00:00.000Z")
        self.assertEqual([a["action"] for a in actions], ["retired", "spawned"])
        retired, spawned = actions
        self.assertEqual(retired["desk_id"], "earnings-02")
        self.assertEqual(retired["reason"], "below family median")
        self.assertIn("family_median", retired["score"])

        self.assertEqual(spawned["desk_id"], "earnings-03")
        self.assertEqual(spawned["parent_id"], "earnings-02")
        self.assertEqual(spawned["generation"], 2)
        self.assertIn(spawned["mutation"]["reasoning_effort"], EFFORTS)
        self.assertIn(spawned["mutation"]["memory_limit"], MEMORY_LIMITS)

        # The spawned manifest is real, valid and loadable by the service.
        path = self.desks / "earnings-03.json"
        child = load_manifest(path)
        self.assertEqual(child.id, "earnings-03")
        self.assertEqual(child.family, "earnings")
        self.assertEqual(child.generation, 2)
        self.assertEqual(child.parent_id, "earnings-02")
        self.assertEqual(child.capital_mode, "paper")
        self.assertEqual(child.playbook, "playbooks/earnings-03.md")
        self.assertTrue((self.playbooks / "earnings-03.md").exists())
        self.assertNotEqual(child.persona, load_manifest(self.desks / "earnings-02.json").persona)

        # The parent's own manifest was not touched.
        parent = json.loads((self.desks / "earnings-02.json").read_text())
        self.assertEqual(parent["generation"], 1)
        self.assertEqual(parent["capital"]["mode"], "paper")

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
        self.assertEqual(event.payload["from"], "paper")
        self.assertEqual(event.payload["to"], "live")
        self.assertEqual(event.payload["gate"], "A")
        self.assertTrue(event.public)
        # Promotion is a log fact; the manifest file still says paper.
        self.assertEqual(load_manifest(self.desks / "earnings-01.json").capital_mode, "paper")
        # And it does not happen twice.
        self.assertEqual(evolution.promote("2026-09-22T20:00:00.000Z"), [])


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

    def test_next_id_skips_used_numbers(self):
        self.write_manifest("earnings-01")
        self.write_manifest("earnings-07", generation=2, parent_id="earnings-01")
        self.assertEqual(self.evolution().next_id("earnings"), "earnings-08")
        self.assertEqual(self.evolution().next_id("kalshi"), "kalshi-01")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
