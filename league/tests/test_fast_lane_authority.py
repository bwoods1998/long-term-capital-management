"""Offline fast-lane behavior with invented programs, quotes, receipts and venue responses."""

import datetime as dt
from unittest.mock import patch

from league.live import money as M
from league.live.ladder import FAST_LANE_AUTHORITY, fast_lane_inputs, fast_lane_receipt
from league.tests import test_live_round3 as races
from league.tests.live_fakes import MONDAY, at
from league.tests.test_live_step import LiveCase


class FastLaneAuthority(LiveCase):
    def tearDown(self):
        if getattr(self, "live", None) is not None:
            self.live.observe_store.close()
        super().tearDown()

    def swarm_live(self, band="candidate"):
        live, store, other = races.BandRace.swarm_live(self, band)
        # Selection is known, before all synthetic forward evidence, under this exact program/evaluator.
        other.set_state("vert", banded_at="2026-08-01T16:00:00Z")
        other._exec("UPDATE versions SET created_at=? WHERE family=? AND n=?", ("2026-07-01T16:00:00Z", "vert", 1))
        return live, store, other

    def evidence(self, store, *, count=20, version=1, source="real", losing=False):
        returns = [-.3, -.1, -.2, -.05, -.25] if losing else [.3, .1, .2, -.1, .25]
        store.add_forward("vert", source, [
            {"id": f"{source}-{version}-{i}", "day": f"2026-09-{i % 20 + 1:02d}", "pnl": returns[i % 5] * 100,
             "max_loss": 100, "version": version} for i in range(count)])

    def receipts(self, live):
        return live.observe_store._connect().execute(
            "SELECT id FROM ladder_decisions WHERE verdict='fast_lane_proposed' ORDER BY id").fetchall()

    def test_a_current_confirmed_pass_enters_probe_in_the_same_session_without_a_forced_order(self):
        live, store, _ = self.swarm_live()
        with patch("league.swarm.gate.Gate.prefilter_round", side_effect=AssertionError("no second unseen read")):
            live.sync_families(self.clock(), force=True)
            self.assertEqual(store.family("vert")["band"], "probe")
            self.assertIn("vert@1:r", live.instances)
            self.assertEqual(self.venue.sent, [], "eligibility does not manufacture an intent")
            self.run_to(9, 31)
        self.assertEqual(len(self.venue.sent), 1, "only the invented program's normal intent reaches the fake venue")
        [position] = live.book.positions.values()
        self.assertLessEqual(position.max_loss, float(M.probe_cap(live.table, live.sizing_equity())))
        self.assertEqual(store.looks_made(), 1)
        self.assertEqual(self.receipts(live), [], "the ladder does not qualify or delay the first Probe")

    def test_rich_old_forward_evidence_does_not_skip_the_first_probe(self):
        live, store, _ = self.swarm_live()
        self.evidence(store)
        live.sync_families(self.clock(), force=True)
        self.assertEqual(store.family("vert")["band"], "probe")
        self.assertEqual(live._probe_sessions("vert", "probe"), 0)
        self.assertEqual(self.receipts(live), [])

    def test_a_missing_passed_look_cannot_enter_on_a_copied_band_label(self):
        live, store, other = self.swarm_live("probe")
        other._exec("DELETE FROM looks")
        live.sync_families(self.clock(), force=True)
        self.assertNotIn("vert@1:r", live.instances)
        self.assertFalse(live._real_eligible("vert"))

    def test_a_removed_pass_between_read_and_atomic_confirmation_is_refused(self):
        live, _, other = self.swarm_live()
        read = live.families.forward_rows

        def altered(fid):
            rows = read(fid)
            other._exec("DELETE FROM looks")
            return rows

        live.families.forward_rows = altered
        live.sync_families(self.clock(), force=True)
        self.assertNotIn("vert@1:r", live.instances)

    def test_stale_execution_proof_and_unreadable_forward_state_cannot_enter(self):
        live, store, other = self.swarm_live("probe")
        with patch.object(live.families, "forward_rows", side_effect=RuntimeError("unreadable")):
            self.assertFalse(live._real_eligible("vert"))
        proof = dict(store.family("vert")["state"]["banded_evaluator"], execution_sha256="obsolete")
        other.set_state("vert", banded_evaluator=proof)
        self.assertFalse(live._real_eligible("vert"))

    def test_same_session_eligibility_survives_a_missing_local_promotion_record_and_restart(self):
        from league.live.families import SwarmFamilies

        live, store, _ = self.swarm_live()
        live.sync_families(self.clock(), force=True)
        self.assertEqual(store.family("vert")["state"]["live_promoted_at"], self.clock())
        live.state.execute("DELETE FROM kv WHERE key='band_moves'")
        live.state.close()
        again = self.make([])
        again.families = SwarmFamilies(self.root)
        self.addCleanup(lambda: again.families._store.close() if again.families._store is not None else None)
        self.assertTrue(again._real_eligible("vert"))
        self.assertEqual(again._probe_sessions("vert", "probe"), 0, "sizing tenure still uses the durable promotion")

    def test_a_current_pass_without_legacy_promotion_time_needs_no_entry_wait(self):
        live, _, other = self.swarm_live("probe")
        other.set_state("vert", live_promoted_at=None)
        live.sync_families(self.clock(), force=True)
        self.assertIn("vert@1:r", live.instances)
        self.assertIsNone(live.state.get("real_first_seen"))
        self.assertEqual(live._probe_sessions("vert", "probe"), 0)

    def ready_sized(self):
        live, store, other = self.swarm_live("probe")
        other.set_state("vert", live_promoted_at=at(MONDAY - dt.timedelta(days=10), 9, 0))
        self.evidence(store)
        return live, store, other

    def test_size_up_is_authorized_by_an_exact_receipt_before_atomic_application(self):
        live, store, _ = self.ready_sized()
        original = live.families.confirm_band
        checked = []

        def confirm(row, band, why, forward, **kwargs):
            if band != row["band"]:
                self.assertEqual(store.family("vert")["band"], "probe")
                receipt = live.observe_store.decision(kwargs["receipt"])
                self.assertEqual(receipt["stats"]["authority"], FAST_LANE_AUTHORITY)
                self.assertEqual(receipt["stats"]["to"], "sized")
                self.assertEqual(receipt["inputs"], fast_lane_inputs(row, forward))
                self.assertEqual(receipt["run_sha"], row["run_sha"])
                self.assertTrue(receipt["binding"], "distinct sizing authority while practice binding remains false")
                checked.append(receipt["id"])
            return original(row, band, why, forward, **kwargs)

        live.families.confirm_band = confirm
        live.sync_families(self.clock(), force=True)
        self.assertEqual(store.family("vert")["band"], "sized")
        self.assertEqual(store.family("vert")["state"]["fast_lane_ladder"]["receipt"], checked[0])
        applied = [p for p, _ in self.ledger.of("live.band") if p.get("authority") == "fast_lane"]
        self.assertEqual(applied[0]["receipt"], checked[0])
        self.assertEqual(store.looks_made(), 1)

    def test_insufficient_whole_probe_sessions_hold_size_up(self):
        live, store, other = self.ready_sized()
        other.set_state("vert", live_promoted_at=at(MONDAY - dt.timedelta(days=3), 9, 0))
        live.sync_families(self.clock(), force=True)
        self.assertEqual(store.family("vert")["band"], "probe")
        self.assertEqual(self.receipts(live), [])

    def test_nineteen_real_trades_hold_size_up_even_after_the_full_probe_tenure(self):
        live, store, other = self.swarm_live("probe")
        other.set_state("vert", live_promoted_at=at(MONDAY - dt.timedelta(days=10), 9, 0))
        self.evidence(store, count=19)
        live.sync_families(self.clock(), force=True)
        self.assertEqual(store.family("vert")["band"], "probe")
        self.assertEqual(self.receipts(live), [])

    def test_shadow_and_other_version_results_cannot_size_up(self):
        live, store, other = self.swarm_live("probe")
        other.set_state("vert", live_promoted_at=at(MONDAY - dt.timedelta(days=10), 9, 0))
        self.evidence(store, source="shadow")
        self.evidence(store, version=2)
        live.sync_families(self.clock(), force=True)
        self.assertEqual(store.family("vert")["band"], "probe")
        self.assertEqual(self.receipts(live), [])

    def test_selected_same_day_or_unknown_selection_preserves_the_sizing_embargo(self):
        live, store, other = self.ready_sized()
        for selected in ("2026-09-20T16:00:00Z", None):
            with self.subTest(selected=selected):
                other.set_state("vert", banded_at=selected)
                live.sync_families(self.clock(), force=True)
                self.assertEqual(store.family("vert")["band"], "probe")
        self.assertEqual(self.receipts(live), [])

    def test_ten_losing_real_fills_reduce_sized_to_probe_with_a_receipt(self):
        live, store, _ = self.swarm_live("sized")
        self.evidence(store, count=10, losing=True)
        live.sync_families(self.clock(), force=True)
        self.assertEqual(store.family("vert")["band"], "probe")
        [receipt] = self.receipts(live)
        self.assertEqual(live.observe_store.decision(receipt[0])["stats"]["to"], "probe")

    def test_negative_forward_demotes_with_a_receipt_and_preserves_program_exit_ownership(self):
        live, store, _ = self.swarm_live("probe")
        self.run_to(9, 31)
        self.assertTrue(live.book.positions)
        self.evidence(store, losing=True)
        live.sync_families(self.clock(), force=True)
        self.assertEqual(store.family("vert")["band"], "candidate", "existing negative evidence policy is preserved")
        self.assertEqual(live.instances["vert@1:r"].mode, "exit_only")
        self.assertTrue(live.book.positions)
        [receipt] = self.receipts(live)
        self.assertEqual(live.observe_store.decision(receipt[0])["stats"]["to"], "candidate")
        self.assertEqual(len(self.venue.sent), 1, "no forced close is created by a band decision")

    def test_a_receipt_write_failure_holds_the_band_and_prevents_new_real_instances(self):
        live, store, _ = self.ready_sized()
        with patch.object(live.observe_store, "add_decision", side_effect=RuntimeError("disk unavailable")):
            live.sync_families(self.clock(), force=True)
        self.assertEqual(store.family("vert")["band"], "probe")
        self.assertNotIn("vert@1:r", live.instances)
        self.assertTrue(any("decision could not be recorded" in message for _, message in self.alerts))

    def test_retirement_after_the_decision_leaves_a_proposal_and_never_claims_a_size_up(self):
        live, store, other = self.ready_sized()
        record = live.observe_store.add_decision

        def retire(row, **kwargs):
            receipt = record(row, **kwargs)
            other.retire("vert", "synthetic concurrent retirement")
            return receipt

        live.observe_store.add_decision = retire
        live.sync_families(self.clock(), force=True)
        self.assertEqual(store.family("vert")["band"], "retired")
        self.assertNotIn("vert@1:r", live.instances)
        [receipt] = self.receipts(live)
        self.assertEqual(live.observe_store.decision(receipt[0])["verdict"], "fast_lane_proposed")
        self.assertFalse([p for p, _ in self.ledger.of("live.band") if p.get("authority") == "fast_lane"])

    def test_changed_selection_clock_after_receipt_refuses_preselection_sizing_evidence(self):
        live, store, other = self.ready_sized()
        record = live.observe_store.add_decision

        def select_again(row, **kwargs):
            receipt = record(row, **kwargs)
            other.set_state("vert", banded_at="2026-09-20T16:00:00Z")
            return receipt

        live.observe_store.add_decision = select_again
        live.sync_families(self.clock(), force=True)
        self.assertEqual(store.family("vert")["band"], "probe")
        self.assertNotIn("vert@1:r", live.instances)
        self.assertEqual(len(self.receipts(live)), 1, "the recorded proposal was never applied")

    def test_changed_creation_clock_or_structure_after_receipt_refuses_the_stale_snapshot(self):
        live, store, other = self.ready_sized()
        from league.live.ladder import Ladder

        row = live.families.read("vert")[0]
        forward = live.families.forward_rows("vert")
        fwd = M.forward_stats(forward, live.table.sized_confidence, version=1)
        band, why, receipt = Ladder(live).fast_lane_band(
            row, live.sizing_equity(), forward, fwd, probe_sessions=5, embargo=None)
        other._exec("UPDATE versions SET created_at=? WHERE family=? AND n=?", ("2026-09-20T16:00:00Z", "vert", 1))
        self.assertFalse(live.families.confirm_band(row, band, why, forward, receipt=receipt))
        other._exec("UPDATE versions SET created_at=? WHERE family=? AND n=?", (row["version_created_at"], "vert", 1))
        other._exec("UPDATE families SET structure=? WHERE id=?", ("credit_vertical", "vert"))
        self.assertFalse(live.families.confirm_band(row, band, why, forward, receipt=receipt))
        self.assertEqual(store.family("vert")["band"], "probe")

    def test_missing_copied_or_malformed_receipts_cannot_authorize_a_size_change(self):
        live, store, _ = self.ready_sized()
        row = live.families.read("vert")[0]
        forward = live.families.forward_rows("vert")
        for receipt in (None, True, "1", 0, -1, 99999):
            self.assertFalse(live.families.confirm_band(row, "sized", "copied", forward, receipt=receipt))
        self.assertEqual(store.family("vert")["band"], "probe")
        receipt = live.observe_store.add_decision({
            "day": MONDAY.isoformat(), "family": "another-family", "version": 1, "run_sha": row["run_sha"],
            "inputs": fast_lane_inputs(row, forward), "stats": {"authority": FAST_LANE_AUTHORITY,
            "from": "probe", "to": "sized"}, "verdict": "fast_lane_proposed", "binding": True})
        self.assertFalse(live.families.confirm_band(row, "sized", "copied", forward, receipt=receipt))
        live.observe_store._connect().execute("UPDATE ladder_decisions SET stats=? WHERE id=?", ("[]", receipt))
        self.assertFalse(fast_lane_receipt(self.root, receipt, row, "sized", forward))

    def test_a_stale_evidence_receipt_is_refused_and_unchanged_bands_do_not_spam_receipts(self):
        live, store, _ = self.ready_sized()
        row = live.families.read("vert")[0]
        forward = live.families.forward_rows("vert")
        live.sync_families(self.clock(), force=True)
        [receipt] = self.receipts(live)
        self.assertFalse(fast_lane_receipt(self.root, receipt[0], row, "sized", forward + [{"new": "evidence"}]))
        live.sync_families(self.clock(), force=True)
        self.assertEqual(self.receipts(live), [receipt])
        self.assertEqual(store.looks_made(), 1)
