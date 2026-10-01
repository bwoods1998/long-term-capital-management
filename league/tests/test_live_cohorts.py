"""Frozen practice survives research churn; its private receipts remain isolated from capital evidence."""

import datetime as dt
import json
import unittest
from unittest.mock import patch

from league.tests.test_live_practice import PracticeCase, trained, validated, TUESDAY
from league.tests.live_fakes import MONDAY, at
from league.live.observe import ObserveStore


class Cohorts(PracticeCase):
    def test_live_only_semantic_upgrade_winds_down_an_existing_cohort_after_restart(self):
        with patch("league.swarm.evaluator.execution_fingerprint", return_value="old-live-code"):
            self.build(observed=[trained("f", params={"hold": 600, "opens": 2})])
            self.run_to(9, 34)
        old_evaluator = self.live.observe_store.evaluator
        self.assertTrue(self.live.shadow.accounts["f@1:o"].positions)
        with patch("league.swarm.evaluator.execution_fingerprint", return_value="new-live-code"):
            self.restart()
            self.assertNotEqual(self.live.observe_store.evaluator, old_evaluator)
            self.live.sync_families(self.clock(), force=True)
            self.assertEqual(self.observing(), [])
            self.assertEqual(self.live.shadow.accounts["f@1:o"].practice_evaluator, old_evaluator)
            self.run_to(9, 39)
            self.assertGreater(self.row("f")["forced"], 0, "the restored orphan account closes without new decisions")
            self.assertEqual(self.row("f")["program"]["trades"], 0)
        snapshot = self.live.observe_store._connect().execute("SELECT snapshot FROM cohorts").fetchone()[0]
        self.assertEqual(json.loads(snapshot)["practice_evaluator"], old_evaluator)
        self.assertEqual(self.venue.sent, [])

    def test_retired_snapshot_survives_restart_with_open_positions_and_rejects_identity_changes(self):
        self.build(observed=[trained("f", params={"hold": 600, "opens": 2})])
        self.run_to(9, 35)
        before = self.live.shadow.accounts["f@1:o"].to_state()
        self.assertTrue(before["positions"])
        del self.families.observed["f"]
        self.restart()
        self.clock.set(at(TUESDAY, 9, 31))
        self.live.minute()
        self.assertEqual(self.observing(), ["f@1:o"])
        acc = self.live.shadow.accounts["f@1:o"]
        self.assertEqual(acc.nonce, before["nonce"])
        inst = self.live.instances["f@1:o"]
        expected = self.live._entry_identity(inst)
        self.assertTrue(self.live.observe_store.cohort_allowed(expected))
        self.assertFalse(self.live.observe_store.cohort_allowed({**expected, "params": {"hold": 1}}))
        self.assertFalse(self.live.observe_store.cohort_allowed({**expected, "observe": False}))
        self.assertFalse(self.live.observe_store.cohort_allowed({**expected, "tuition": True}))
        self.assertEqual(self.families.forward, {})
        self.assertEqual(self.venue.sent, [])

    def test_rotation_needs_completed_sessions_and_trades_and_never_readmits_same_snapshot(self):
        self.build(observed=[validated("f", params={"hold": 600})])
        self.run_to(9, 34)
        db = self.live.observe_store._connect()
        self.families.observed["f"][2] = {**validated("f", version=2), "observe": True, "band": "gym"}
        db.execute("UPDATE practice SET sessions=3, last_day='2026-09-30' WHERE family='f'")
        self.live.observe_store.add("f@1:o", "f", 1, [
            {"id": n, "day": "2026-09-30", "exit_day": "2026-09-30", "pnl": 2, "max_loss": 50,
             "evaluator": self.live.observe_store.evaluator}
            for n in range(10)], account="synthetic")
        # The still-running third session does not count as completed.
        same = self.live.observe_store.cohort_candidates(self.families.observe(), day="2026-09-30", in_session=True)
        self.assertEqual(same[0]["version"], 1)
        held = self.live.observe_store.cohort_candidates(self.families.observe(), day="2026-10-01", in_session=True)
        self.assertEqual(held[0]["version"], 1, "collecting enough winners never discards unresolved positions")
        db.execute("UPDATE practice SET open_positions=0 WHERE family='f'")
        next_day = self.live.observe_store.cohort_candidates(self.families.observe(), day="2026-10-01", in_session=True)
        self.assertEqual(next_day[0]["version"], 2)
        self.assertEqual(db.execute("SELECT status, reason FROM cohorts").fetchone(),
                         ("complete", "observation target reached"))
        self.assertEqual(self.live.observe_store.cohort_candidates([self.families.observed["f"][1]],
                         day="2026-10-01", in_session=True), [])

    def test_a_kept_cohort_is_not_completed_at_its_target_but_still_at_its_window(self):
        """L2' (release B): `keep` holds a cohort the incubator passed past its observation target; its window, an evaluator
        change or a failure still end it. Empty, the league's own rule, byte for byte."""
        self.build(observed=[validated("f", params={"hold": 600})])
        self.run_to(9, 34)
        db = self.live.observe_store._connect()
        db.execute("UPDATE practice SET sessions=3, last_day='2026-09-30', open_positions=0 WHERE family='f'")
        self.live.observe_store.add("f@1:o", "f", 1, [
            {"id": n, "day": "2026-09-30", "exit_day": "2026-09-30", "pnl": 2, "max_loss": 50,
             "evaluator": self.live.observe_store.evaluator}
            for n in range(10)], account="synthetic")
        kept = self.live.observe_store.cohort_candidates(self.families.observe(), day="2026-10-01", in_session=True,
                                                         keep={("f", 1)})
        self.assertEqual(kept[0]["version"], 1)
        self.assertEqual(db.execute("SELECT status FROM cohorts").fetchone()[0], "active")
        later = self.live.observe_store.cohort_candidates(self.families.observe(), day="2026-10-13", in_session=True,
                                                         keep={("f", 1)})
        self.assertNotIn(1, [r["version"] for r in later if r["family"] == "f" and r.get("practice_frozen")])
        self.assertEqual(db.execute("SELECT status, reason FROM cohorts").fetchone(),
                         ("complete", "maximum session window reached"))

    def test_an_empty_keep_is_the_leagues_own_rule(self):
        self.build(observed=[validated("f", params={"hold": 600})])
        self.run_to(9, 34)
        db = self.live.observe_store._connect()
        db.execute("UPDATE practice SET sessions=3, last_day='2026-09-30', open_positions=0 WHERE family='f'")
        self.live.observe_store.add("f@1:o", "f", 1, [
            {"id": n, "day": "2026-09-30", "exit_day": "2026-09-30", "pnl": 2, "max_loss": 50,
             "evaluator": self.live.observe_store.evaluator}
            for n in range(10)], account="synthetic")
        self.live.observe_store.cohort_candidates(self.families.observe(), day="2026-10-01", in_session=True,
                                                  keep=frozenset({("other", 1)}))
        self.assertEqual(db.execute("SELECT status, reason FROM cohorts").fetchone(),
                         ("complete", "observation target reached"))

    def test_nontrading_cohort_expires_at_bounded_session_window(self):
        self.build(observed=[trained("f")])
        self.run_to(9, 32)
        result = self.live.observe_store.cohort_candidates([], day="2026-10-12", in_session=True)
        self.assertEqual(result, [], "ten calendar sessions elapsed, regardless of absent fills")
        self.assertEqual(self.live.observe_store._connect().execute("SELECT reason FROM cohorts").fetchone()[0],
                         "maximum session window reached")

    def test_evaluator_change_never_appends_new_engine_decisions_to_an_old_cohort(self):
        self.build(observed=[trained("f")])
        self.run_to(9, 34)
        inst = self.live.instances["f@1:o"]
        self.live.observe_store.evaluator = "new-evaluator"
        self.assertFalse(self.live.observe_store.cohort_allowed(self.live._entry_identity(inst)))
        self.live.sync_families(self.clock(), force=True)
        self.assertEqual(inst.mode, "wind_down")
        self.assertEqual(self.live.observe_store.cohort_candidates(self.families.observe(),
                         day=MONDAY.isoformat(), in_session=True), [], "a new source version is required")
        snapshot, reason = self.live.observe_store._connect().execute("SELECT snapshot, reason FROM cohorts").fetchone()
        self.assertNotEqual(json.loads(snapshot)["practice_evaluator"], "new-evaluator")
        self.assertIn("evaluator changed", reason)
        self.run_to(9, 39)
        record = self.row("f")
        self.assertGreater(record["forced"], 0)
        self.assertEqual(record["program"]["trades"], 0, "new-engine wind-down exits are never program evidence")

    def test_long_dated_snapshot_gets_enough_sessions_to_observe_its_declared_horizon(self):
        row = trained("long")
        row["code"] = row["code"].replace('"dte": [0, 3]', '"dte": [0, 45]')
        self.build(observed=[row])
        self.run_to(9, 32)
        result = self.live.observe_store.cohort_candidates([], day="2026-10-12", in_session=True)
        self.assertEqual(result[0]["practice_max_sessions"], 36)
        self.assertEqual(self.live.observe_store.cohort_candidates([], day="2026-12-01", in_session=True), [])

    def test_program_errors_are_visible_and_never_count_as_successful_decisions(self):
        row = trained("broken")
        row["code"] = row["code"].split("def decide", 1)[0] + "def decide(ctx):\n    return ctx.unknown_field\n"
        self.build(observed=[row])
        self.run_to(9, 39)
        record = self.row("broken")
        self.assertGreater(record["missed_errors"], 0)
        self.assertEqual(record["decisions_made"], 0)
        self.assertEqual(record["decisions_due"], record["missed_errors"] + record["missed_quotes"] + record["missed_budget"])
        self.run_to(10, 5)
        self.assertNotIn("broken@1:o", self.live.instances, "a disqualified cohort frees its slot")
        status, reason = self.live.observe_store._connect().execute("SELECT status, reason FROM cohorts").fetchone()
        self.assertEqual(status, "failed")
        self.assertIn("disqualified", reason)

    def test_private_journal_records_decisions_quotes_orders_fills_and_rejections(self):
        self.build(observed=[trained("f", params={"hold": 3, "opens": 3})])
        self.run_to(9, 49)
        acc = self.live.shadow.accounts["f@1:o"]
        acc._reject("invented rejected order")
        self.run_to(9, 50)
        rows = self.live.observe_store._connect().execute("SELECT kind, body FROM events").fetchall()
        kinds = {r[0] for r in rows}
        self.assertTrue({"decision", "coverage", "intent", "order", "fill", "rejected"} <= kinds, kinds)
        fills = [json.loads(body) for kind, body in rows if kind == "fill"]
        self.assertTrue(all(f["quotes"] and f["quantity"] > 0 and f["fees"] >= 0 for f in fills))
        self.assertTrue({"open", "close"} <= {f["action"] for f in fills})
        self.assertTrue(all("decision_mid" in f and "decision_natural" in f for f in fills))
        self.assertFalse(acc.practice_events)
        self.assertEqual(self.families.forward, {})
        self.assertEqual(self.venue.sent, [])

    def test_legacy_outcomes_remain_in_the_headline_without_becoming_new_evaluator_feedback(self):
        self.build(observed=[trained("f", params={"hold": 3, "opens": 3})])
        self.run_to(9, 49)
        before = self.row("f")
        self.live.observe_store.add("f@1:o", "f", 1, [{"id": 999, "day": MONDAY.isoformat(),
            "exit_day": MONDAY.isoformat(), "pnl": 5000, "max_loss": 50}], account="legacy")
        after = self.row("f")
        self.assertEqual(after["trades"], before["trades"] + 1)
        self.assertEqual(after["program"], before["program"])
        self.assertEqual(after["unmatched_evaluator"], 1)

    def test_unwritten_receipts_survive_restart_and_retries_are_idempotent(self):
        self.build(observed=[trained("f")])
        with patch.object(self.live.observe_store, "events", return_value=False):
            self.run_to(9, 34)
        saved = list(self.live.shadow.accounts["f@1:o"].practice_events)
        self.assertTrue(saved)
        self.restart()
        self.clock.set(self.clock() + 60)
        self.live.minute()
        acc = self.live.shadow.accounts["f@1:o"]
        db = self.live.observe_store._connect()
        before = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        self.assertTrue(self.live.observe_store.events(acc.instance, acc.family, 1, acc.nonce, saved))
        self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], before)
        self.assertFalse(acc.practice_events)


if __name__ == "__main__":
    unittest.main()
