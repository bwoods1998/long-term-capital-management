import copy
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.manifest import DeskManifest, ManifestError, load_all, load_manifest

SAMPLE = {
    "schema_version": 1,
    "id": "earnings-01",
    "family": "earnings",
    "generation": 1,
    "parent_id": None,
    "name": "Earnings",
    "persona": "Fast reader of transcripts.",
    "mandate": "Trade post-earnings drift in liquid US equities.",
    "venues": ["alpaca"],
    "instruments": {"asset_classes": ["equity", "option"], "allow": [], "deny": ["GME"], "min_price": "5", "min_adv_usd": "5000000", "allow_short": False},
    "limits": {"max_position_pct": "0.25", "max_gross_pct": "1.0", "max_order_notional_pct": "0.25", "max_daily_loss_pct": "0.10", "max_orders_per_day": 20},
    "model": {"profile": "pro_flex", "reasoning_effort": "medium", "max_output_tokens": 8192, "max_turns": 24},
    "cadence": {"sessions": ["09:35", "15:30"], "timezone": "America/New_York", "triggers": ["earnings_release"]},
    "tools": ["quote", "bars", "news", "filing", "memory_read", "memory_write", "memo", "propose_order", "playbook_read", "playbook_write"],
    "budget": {"usd_per_day": "3"},
    "capital": {"mode": "shadow", "usd": "1000"},
    "playbook": "playbooks/earnings-01.md",
}


class ManifestTests(unittest.TestCase):
    def test_roundtrip(self):
        manifest = DeskManifest.from_dict(SAMPLE)
        self.assertEqual(manifest.id, "earnings-01")
        self.assertEqual(manifest.limits.max_position_pct, Decimal("0.25"))
        self.assertEqual(manifest.stream, "desk:earnings-01")
        self.assertFalse(manifest.live)
        self.assertEqual(DeskManifest.from_dict(manifest.to_dict()), manifest)
        self.assertTrue(manifest.instruments.permits_symbol("AAPL"))
        self.assertFalse(manifest.instruments.permits_symbol("GME"))

    def assertInvalid(self, mutate):
        data = copy.deepcopy(SAMPLE)
        mutate(data)
        with self.assertRaises(ManifestError):
            DeskManifest.from_dict(data)

    def test_validation(self):
        self.assertInvalid(lambda d: d.update(id="Bad Id"))
        self.assertInvalid(lambda d: d.update(generation=2))
        self.assertInvalid(lambda d: d.update(venues=["nyse"]))
        self.assertInvalid(lambda d: d["instruments"].update(asset_classes=["bond"]))
        self.assertInvalid(lambda d: d["limits"].update(max_position_pct="1.5"))
        self.assertInvalid(lambda d: d["limits"].update(max_orders_per_day=0))
        self.assertInvalid(lambda d: d["model"].update(reasoning_effort="extreme"))
        self.assertInvalid(lambda d: d["cadence"].update(sessions=["25:00"]))
        self.assertInvalid(lambda d: d["cadence"].update(sessions=[], triggers=[]))
        self.assertInvalid(lambda d: d.update(tools=["teleport"]))
        self.assertInvalid(lambda d: d["budget"].update(usd_per_day="0"))
        self.assertInvalid(lambda d: d["capital"].update(mode="margin"))
        self.assertInvalid(lambda d: d.update(venues=["shadow"]))  # routing key, never a venue
        self.assertInvalid(lambda d: d.update(playbook="../etc/passwd"))
        self.assertInvalid(lambda d: d.update(schema_version=2))

    def test_a_shadow_desk_names_the_venue_it_would_trade_on(self):
        manifest = DeskManifest.from_dict(SAMPLE)
        self.assertEqual(manifest.capital_mode, "shadow")
        self.assertTrue(manifest.shadow)
        self.assertFalse(manifest.live)
        self.assertEqual(manifest.market_venue, "alpaca")
        self.assertEqual(manifest.venues, ("alpaca",))

    def test_a_manifest_written_before_the_rename_still_loads(self):
        data = copy.deepcopy(SAMPLE)
        data["capital"] = {"mode": "paper", "usd": "1000"}
        data["venues"] = ["paper", "alpaca"]
        manifest = DeskManifest.from_dict(data)
        self.assertEqual(manifest.capital_mode, "shadow")
        self.assertEqual(manifest.venues, ("alpaca",))
        # What is written back is the new vocabulary, so the old word dies on the next save.
        self.assertEqual(manifest.to_dict()["capital"]["mode"], "shadow")
        self.assertEqual(DeskManifest.from_dict(manifest.to_dict()), manifest)

    def test_live_desk_needs_live_venues(self):
        data = copy.deepcopy(SAMPLE)
        data["venues"] = ["alpaca"]
        data["capital"] = {"mode": "live", "usd": "500"}
        manifest = DeskManifest.from_dict(data)
        self.assertTrue(manifest.live)

    def test_load_from_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "earnings-01.json"
            path.write_text(json.dumps(SAMPLE))
            self.assertEqual(load_manifest(path).id, "earnings-01")
            dup = Path(tmp) / "copy.json"
            dup.write_text(json.dumps(SAMPLE))
            with self.assertRaises(ManifestError):
                load_all(tmp)
            dup.write_text("{not json")
            with self.assertRaises(ManifestError):
                load_manifest(dup)



class FamilyToolTests(unittest.TestCase):
    """A bred desk carries every tool its founder carries, along the parent chain."""

    def test_children_inherit_tools_given_to_the_founder_later(self):
        import copy
        from ltcm.manifest import DeskManifest, inherit_family_tools

        founder = copy.deepcopy(SAMPLE)
        founder["id"] = "mullins"
        founder["tools"] = list(SAMPLE["tools"]) + ["record_forecast", "run_code"]
        child = copy.deepcopy(SAMPLE)
        child.update({"id": "mullins-2", "parent_id": "mullins", "generation": 2})
        grandchild = copy.deepcopy(SAMPLE)
        grandchild.update({"id": "mullins-2-3", "parent_id": "mullins-2", "generation": 3})
        other = copy.deepcopy(SAMPLE)
        other.update({"id": "hilibrand", "family": "crypto"})
        loaded = inherit_family_tools([DeskManifest.from_dict(d) for d in (founder, child, grandchild, other)])
        by_id = {m.id: m for m in loaded}
        for desk_id in ("mullins-2", "mullins-2-3"):
            self.assertIn("record_forecast", by_id[desk_id].tools, desk_id)
            self.assertIn("run_code", by_id[desk_id].tools, desk_id)
        self.assertNotIn("run_code", by_id["hilibrand"].tools, "another family inherits nothing")
        self.assertEqual(len(by_id["mullins-2"].tools), len(set(by_id["mullins-2"].tools)))

if __name__ == "__main__":
    unittest.main()
