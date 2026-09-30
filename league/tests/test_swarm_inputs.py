"""Audited raw columns cannot masquerade as usable inputs or survive an image change."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from league.swarm import inputs
from league.swarm.architect import Architect
from league.tests.test_swarm_researcher import ResearcherCase
from league.tests.test_swarm_rounds import RoundCase


def card():
    """Synthetic metadata only; the operational image's audit remains private."""
    return {"schema": 1, "image_checkpoint": "sbcp_synthetic_a", "audited_at": "2026-09-30T01:00:00+00:00",
            "train_from": "2020-01-02", "train_through": "2024-12-31", "raw_file_count": 100,
            "raw_volume_file_count": 3, "raw_complete_volume_sessions": 2,
            "point_in_time_verified_volume_sessions": 0,
            "claim": "untrusted narrative must not enter the prompt",
            "roots": {"SPY": {"train_sessions": 80, "raw_volume_sessions": 3, "raw_complete_sessions": 2,
                              "asof_verified_sessions": 0, "raw_first": "2022-01-03", "raw_last": "2022-01-05"},
                      "NVDA": {"train_sessions": 20, "raw_volume_sessions": 0, "raw_complete_sessions": 0,
                               "asof_verified_sessions": 0, "raw_first": None, "raw_last": None}}}


def install(root, row=None):
    # Same atomic local replacement expected of the operator, including while the process is running.
    temp = root / "capabilities.tmp"
    temp.write_text(json.dumps(card() if row is None else row), encoding="utf-8")
    temp.replace(root / inputs.CARD_NAME)


class LocalCards(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        inputs._read.cache_clear()

    def test_raw_counts_do_not_unlock_historical_volume_and_unaudited_roots_are_unknown(self):
        install(self.root)
        text = inputs.context(self.root, "sbcp_synthetic_a", ["SPY", "QQQ"])
        self.assertIn("Card: exact image sbcp_synthetic_a", text)
        self.assertIn("3/100 root-sessions (3.00%)", text)
        self.assertIn("SPY: 3/80; 2 complete; 2022-01-03 through 2022-01-05", text)
        self.assertIn("QQQ: unknown (not audited", text)
        self.assertNotIn("NVDA:", text)
        self.assertIn("Point-in-time verified volume sessions: 0", text)
        self.assertIn("Historical strategy volume: unavailable", text)
        self.assertIn("remain NaN even when raw columns exist", text)
        self.assertNotIn("untrusted narrative", text)

    def test_missing_stale_and_invalid_cards_never_reuse_raw_counts(self):
        self.assertIn("unknown (missing_or_invalid)", inputs.context(self.root, "sbcp_synthetic_a", ["SPY"]))
        install(self.root)
        for image, reason in ((None, "image_unknown"), ("sbcp_synthetic_b", "image_mismatch")):
            text = inputs.context(self.root, image, ["SPY"])
            self.assertIn(f"unknown ({reason})", text)
            self.assertNotIn("3/100", text)
            self.assertNotIn("2022-01-03", text)
            self.assertIn("Historical strategy volume: unavailable", text)
        bad = card()
        bad["raw_volume_file_count"] = 1000
        install(self.root, bad)
        self.assertIn("unknown (missing_or_invalid)", inputs.context(self.root, "sbcp_synthetic_a", ["SPY"]))
        (self.root / inputs.CARD_NAME).write_text('{"schema":', encoding="utf-8")
        self.assertIn("unknown (missing_or_invalid)", inputs.context(self.root, "sbcp_synthetic_a", ["SPY"]))

    def test_local_cache_reloads_replacement_and_rechecks_image_without_a_new_audit(self):
        install(self.root)
        with patch.object(inputs.json, "loads", wraps=json.loads) as read:
            a = inputs.context(self.root, "sbcp_synthetic_a", ["SPY"])
            self.assertEqual(inputs.context(self.root, "sbcp_synthetic_a", ["SPY"]), a)
            self.assertIn("image_mismatch", inputs.context(self.root, "sbcp_synthetic_b", ["SPY"]))
            self.assertEqual(read.call_count, 1)
            revised = card()
            revised["image_checkpoint"] = "sbcp_synthetic_b"
            install(self.root, revised)
            self.assertIn("exact image sbcp_synthetic_b", inputs.context(self.root, "sbcp_synthetic_b", ["SPY"]))
            self.assertEqual(read.call_count, 2)


class ResearchContext(ResearcherCase):
    def test_revise_turn_receives_card_before_selecting_a_hypothesis_with_no_extra_call(self):
        self.settings["gym"]["image_checkpoint"] = "sbcp_synthetic_a"
        install(self.root)
        researcher = self.researcher()
        researcher.cycle(self.fam["id"])  # the existing seed starter makes no paid call
        jobs = len(self.pool.jobs)
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "Need publication receipts for volume."})]}]
        out = researcher.cycle(self.fam["id"])
        self.assertTrue(out["hold"], out)
        self.assertEqual((out["model_calls"], len(self.sail.bodies), len(self.pool.jobs)), (1, 1, jobs))
        brief = self.sail.bodies[0]["input"][1]["content"]
        self.assertIn("YOUR FAMILY", brief)
        self.assertIn("Card: exact image sbcp_synthetic_a", brief)
        self.assertIn("SPY: 3/80", brief)
        self.assertIn("Historical strategy volume: unavailable", brief)
        self.settings["gym"]["image_checkpoint"] = "sbcp_synthetic_b"
        self.assertIn("image_mismatch", researcher.brief(self.fam))
        self.assertEqual(len(self.sail.bodies), 1, "context refresh is local, never a model/data query")


class ArchitectContext(RoundCase):
    def test_proposal_turn_sees_all_admitted_roots_before_family_selection(self):
        self.settings["gym"].update(image_checkpoint="sbcp_synthetic_a", roots=["SPY", "NVDA", "QQQ"])
        install(self.root)
        self.replies = [{"text": '{"families": []}'}]
        Architect(self.store, self.router, self.settings, clock=self.clock).run()
        self.assertEqual(len(self.sail.bodies), 1)
        text = self.sail.bodies[0]["input"][-1]["content"]
        self.assertIn("Card: exact image sbcp_synthetic_a", text)
        self.assertIn("NVDA: 0/20; 0 complete; none", text)
        self.assertIn("QQQ: unknown (not audited", text)
        self.assertIn("Historical strategy volume: unavailable", text)


if __name__ == "__main__":
    unittest.main()
