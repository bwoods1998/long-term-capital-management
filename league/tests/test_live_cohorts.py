"""Frozen practice survives research churn; its private receipts remain isolated from capital evidence."""

import datetime as dt
import json
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from league.tests.test_live_practice import PracticeCase, trained, validated, TUESDAY
from league.tests.live_fakes import MONDAY, at


def ny_day(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).astimezone(ZoneInfo("America/New_York")).date().isoformat()
from league.live.observe import ObserveStore


class Cohorts(PracticeCase):
    def pre_ladder(self):
        """Make the frozen cohorts ones frozen BEFORE the forward ladder (evidence v3, Oct 2, 2026): no `ladder` mark, and
        the window the old freeze gave (its declared DTE horizon). The old observation target and window still govern such
        a cohort; every cohort frozen from evidence v3 on is a ladder cohort (`league/tests/test_live_ladder.py`)."""
        import ast
        import math

        db = self.live.observe_store._connect()
        for family, version, snapshot in db.execute("SELECT family, version, snapshot FROM cohorts").fetchall():
            snap = json.loads(snapshot)
            snap.pop("ladder", None)
            snap.pop("practice_max_sessions", None)
            for node in ast.parse(snap["code"]).body:
                if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "NEEDS" for t in node.targets):
                    needs = ast.literal_eval(node.value)
                    snap["practice_max_sessions"] = min(60, math.ceil(float(needs["dte"][1]) * 5 / 7) + 3)
            db.execute("UPDATE cohorts SET snapshot=? WHERE family=? AND version=?", (json.dumps(snap, sort_keys=True),
                                                                                     family, version))

    def test_live_only_semantic_upgrade_restarts_the_programs_practice_after_restart(self):
        """The plan's "practice cohorts restart on the new fingerprint" (evidence v3, the WP6 review): the program is
        frozen again as a new cohort; the restored account of its old cohort winds down (its closes forced, never either
        cohort's program record) and, once flat, a new account is made under the new evaluator."""
        with patch("league.swarm.evaluator.execution_fingerprint", return_value="old-live-code"):
            self.build(observed=[trained("f", params={"hold": 600, "opens": 2})])
            self.run_to(9, 34)
        old_evaluator = self.live.observe_store.evaluator
        old = self.live.shadow.accounts["f@1:o"]
        self.assertTrue(old.positions)
        with patch("league.swarm.evaluator.execution_fingerprint", return_value="new-live-code"):
            self.restart()
            new_evaluator = self.live.observe_store.evaluator
            self.assertNotEqual(new_evaluator, old_evaluator)
            self.live.sync_families(self.clock(), force=True)
            self.assertEqual(self.observing(), ["f@1:o"], "frozen again under the new evaluator")
            self.assertEqual(self.live.shadow.accounts["f@1:o"].practice_evaluator, old_evaluator)
            self.run_to(9, 39)
            self.assertGreater(self.row("f")["forced"], 0, "the restored old account closes without new decisions")
            self.assertEqual(self.row("f")["program"]["trades"], 0)
            account = self.live.shadow.accounts["f@1:o"]
            self.assertEqual(account.practice_evaluator, new_evaluator, "a new account once the old one was flat")
            self.assertNotEqual(account.nonce, old.nonce)
        db = self.live.observe_store._connect()
        snapshot, evaluator = db.execute("SELECT snapshot, evaluator FROM cohorts").fetchone()
        self.assertEqual((json.loads(snapshot)["practice_evaluator"], evaluator), (new_evaluator, new_evaluator))
        archived = db.execute("SELECT snapshot, reason FROM cohort_archive").fetchone()
        self.assertEqual(json.loads(archived[0])["practice_evaluator"], old_evaluator)
        self.assertIn("evaluator changed", archived[1])
        forced = db.execute("SELECT DISTINCT forced FROM trades WHERE account=? AND evaluator=?",
                            (old.nonce, new_evaluator)).fetchall()
        self.assertEqual(forced, [(1,)], "every close of the old account since is forced: no cohort's record")
        self.assertEqual(self.venue.sent, [])

    def out_and_back(self, minutes: int):
        """One evaluator, another for `minutes` session minutes, then the first again, each a new House process on the
        same state: (the first cohort's account, the first evaluator, the session day)."""
        with patch("league.swarm.evaluator.execution_fingerprint", return_value="one"):
            self.build(observed=[trained("f", params={"hold": 3, "opens": 3})])
            self.run_to(9, 49)
        first, one = self.live.shadow.accounts["f@1:o"], self.live.observe_store.evaluator
        db = self.live.observe_store._connect()
        self.assertGreater(db.execute("SELECT COUNT(*) FROM trades WHERE account=? AND forced=0 AND evaluator=?",
                                      (first.nonce, one)).fetchone()[0], 0, "the first cohort closed trades today")
        with patch("league.swarm.evaluator.execution_fingerprint", return_value="two"):
            self.restart()                                        # the deploy, mid-session
            self.assertNotEqual(self.live.observe_store.evaluator, one)
            self.live.sync_families(self.clock(), force=True)
            for _ in range(minutes):
                self.clock.set(self.clock() + 60)
                self.live.minute()
        with patch("league.swarm.evaluator.execution_fingerprint", return_value="one"):
            self.restart()                                        # the rollback, the same session
            self.assertEqual(self.live.observe_store.evaluator, one)
            self.live.sync_families(self.clock(), force=True)
            self.assertEqual(self.observing(), ["f@1:o"], "frozen again: the third cohort")
            for _ in range(12):
                self.clock.set(self.clock() + 60)
                self.live.minute()
        return first, one, ny_day(self.clock())

    def the_third_cohort_is_its_own(self, first, one, today):
        store = self.live.observe_store
        db = store._connect()
        account = self.live.shadow.accounts["f@1:o"]
        self.assertNotEqual(account.nonce, first.nonce, "the first cohort's account is never the third cohort's")
        self.assertEqual((account.practice_evaluator, account.winding_down), (one, False))
        entrants = db.execute("SELECT id, evaluator, entered_day FROM entrants ORDER BY id").fetchall()
        self.assertEqual([e[1] == one for e in entrants], [True, False, True], "three cohorts, three entrants")
        status, evaluator, entrant = db.execute("SELECT status, evaluator, entrant FROM cohorts").fetchone()
        self.assertEqual((status, evaluator, entrant), ("active", one, entrants[-1][0]))
        archived = [set(json.loads(a)) for (a,) in db.execute("SELECT accounts FROM cohort_archive ORDER BY rowid")]
        self.assertEqual(len(archived), 2)
        self.assertTrue(all(first.nonce in accounts for accounts in archived), "barred for good")
        self.assertTrue(store.earlier_account("f", 1, first.nonce))
        self.assertFalse(store.earlier_account("f", 1, account.nonce))
        # The third cohort's record: its own account's closes alone, though the first cohort's are under its evaluator
        # and of its first day.
        _, closes = store.ladder_rows("f", 1, evaluator=one, first_day=today, through=today)
        mine = {seq for (seq,) in db.execute("SELECT seq FROM trades WHERE account=?", (account.nonce,))}
        self.assertTrue({c["seq"] for c in closes} <= mine, "none of the first cohort's closes of that day")
        late = db.execute("SELECT DISTINCT forced FROM trades WHERE account=? AND seq > (SELECT MIN(seq) FROM trades "
                          "WHERE evaluator != ?)", (first.nonce, one)).fetchall()
        self.assertIn(late, ([], [(1,)]), "every close of the first account since the change is forced")
        practice = db.execute("SELECT account, first_day, base_pnl FROM practice").fetchone()
        self.assertEqual(practice, (account.nonce, today, 0.0), "its practice row is its own account's, from zero")
        self.assertEqual(self.venue.sent, [])

    def test_an_evaluator_that_comes_back_is_a_third_cohort_with_its_own_account_and_record(self):
        """THE COHORT'S OWN RECORD through the House's own minutes: the deploy ran long enough to wind the first
        cohort's account down and make its own."""
        self.the_third_cohort_is_its_own(*self.out_and_back(6))

    def test_an_evaluator_that_comes_back_at_once_still_winds_the_first_cohorts_account_down(self):
        """The deploy froze the program again and stopped before a minute ran: the first cohort's account comes back as it
        was saved, made under the very evaluator that returned, neither winding down nor flat. It is still an earlier
        cohort's (`ObserveStore.earlier_account`): wound down, never the third cohort's record, and replaced."""
        self.the_third_cohort_is_its_own(*self.out_and_back(0))

    def test_a_pinned_program_that_may_never_practise_again_fails_no_families_pass(self):
        """A release mid-session ends a latched cohort for good (THE RE-ENTRY RULE) after research moved its family to a
        new version: `freeze` refuses the pinned older version, and the families pass goes on (the real instances are
        synced by the same pass)."""
        from league.live.observe import EVALUATOR_CHANGED_FINAL

        self.build(observed=[trained("f")])
        self.run_to(9, 34)
        store = self.live.observe_store
        store.add_decision({"day": MONDAY.isoformat(), "family": "f", "version": 1, "run_sha": "sha-f-1", "inputs": "x",
                            "stats": {}, "p_value": 0.001, "verdict": "await_prefilter", "binding": False, "checkpoint": 40,
                            "latch": "prefilter"})
        self.families.observed["f"][2] = {**trained("f", version=2), "observe": True, "band": "gym"}
        store.evaluator = "new-evaluator"
        self.live.sync_families(self.clock(), force=True)         # the pinned version 1 is offered to `freeze`: refused
        db = store._connect()
        self.assertEqual(db.execute("SELECT version, status, reason FROM cohorts ORDER BY version").fetchall()[0],
                         (1, "complete", EVALUATOR_CHANGED_FINAL))
        self.assertEqual(db.execute("SELECT COUNT(*) FROM cohort_archive").fetchone(), (0,), "never frozen again")
        self.run_to(9, 39)
        self.assertNotIn("f@1:o", self.observing(), "its instance winds down: its cohort admits no entry")
        self.assertEqual(self.venue.sent, [])

    def a_release_on_the_day_of_its_sixtieth_session(self, hh: int, mm: int) -> tuple:
        """A ladder cohort whose sixtieth calendar session is MONDAY, which the House never practised (it was down all
        day), and a release that changes the evaluator at hh:mm that day: its row's (status, reason), and the archive."""
        from league.live import ladder as L

        self.clock.set(at(MONDAY, hh, mm))
        self.build(observed=[trained("f")])
        store = self.live.observe_store
        days = L.sessions_between((MONDAY - dt.timedelta(days=120)).isoformat(), MONDAY.isoformat())[-60:]
        self.assertEqual((len(days), days[-1]), (60, MONDAY.isoformat()))
        store.freeze({**trained("f"), "observe": True, "band": "gym"}, day=days[0])
        db = store._connect()
        db.execute("INSERT INTO practice(family, version, tier, capital, first_at, first_day, last_at, last_day, sessions) "
                   "VALUES('f', 1, 'train', 10000, 1, ?, 2, ?, 59)", (days[0], days[58]))
        store.evaluator = "new-evaluator"                         # a release that touched the live path
        self.live.sync_families(self.clock(), force=True)
        return (db.execute("SELECT status, reason FROM cohorts").fetchone(),
                db.execute("SELECT COUNT(*) FROM cohort_archive").fetchone()[0])

    def test_a_release_after_the_close_of_a_last_session_the_house_never_practised_starts_nothing_again(self):
        """THE RE-ENTRY RULE's count is the House's clock's: after the close, the day's session is behind every cohort,
        practised or not, so a window that ended is never started again."""
        from league.live.observe import EVALUATOR_CHANGED_WINDOW

        self.assertEqual(self.a_release_on_the_day_of_its_sixtieth_session(16, 5),
                         (("complete", EVALUATOR_CHANGED_WINDOW), 0))
        self.clock.set(at(TUESDAY, 9, 31))
        self.live.minute()
        self.assertEqual(self.observing(), [], "never frozen again, at the next session's pins either")
        db = self.live.observe_store._connect()
        self.assertEqual((db.execute("SELECT reason FROM cohorts").fetchone()[0],
                          db.execute("SELECT COUNT(*) FROM entrants").fetchone()[0],
                          db.execute("SELECT COUNT(*) FROM cohort_archive").fetchone()[0]),
                         (EVALUATOR_CHANGED_WINDOW, 1, 0))

    def test_a_release_before_the_open_of_its_last_session_interrupts_it(self):
        from league.live.observe import EVALUATOR_CHANGED

        self.assertEqual(self.a_release_on_the_day_of_its_sixtieth_session(9, 0), (("complete", EVALUATOR_CHANGED), 0))
        self.clock.set(at(MONDAY, 9, 31))
        self.live.minute()
        self.assertEqual(self.observing(), ["f@1:o"], "frozen again at the session's pins: a new cohort")
        db = self.live.observe_store._connect()
        self.assertEqual((db.execute("SELECT COUNT(*) FROM entrants").fetchone()[0],
                          db.execute("SELECT COUNT(*) FROM cohort_archive").fetchone()[0]), (2, 1))

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
        self.pre_ladder()
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
        change or a failure still end it. Empty, the league's own rule, byte for byte. (A cohort frozen before the
        forward ladder: a ladder cohort has no observation target.)"""
        self.build(observed=[validated("f", params={"hold": 600})])
        self.run_to(9, 34)
        self.pre_ladder()
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
        self.pre_ladder()
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
        store = self.live.observe_store
        result = store.cohort_candidates([], day="2026-10-12", in_session=True)
        self.assertEqual([r["family"] for r in result], ["f"], "a ladder cohort practises its whole window")
        self.assertEqual([r["family"] for r in store.cohort_candidates([], day="2026-12-21", in_session=True)], ["f"])
        # The ladder judged it at its last checkpoint, the 60th session's end, and it met no line: its window is over.
        store.add_decision({"day": "2026-12-21", "family": "f", "version": 1, "inputs": "x", "stats": {}, "p_value": 1.0,
                            "verdict": "short", "binding": False, "checkpoint": 60})
        result = store.cohort_candidates([], day="2026-12-22", in_session=True)
        self.assertEqual(result, [], "sixty calendar sessions elapsed, regardless of absent fills")
        self.assertEqual(store._connect().execute("SELECT reason FROM cohorts").fetchone()[0],
                         "ladder: its practice window ended")

    def test_a_cohort_never_judged_at_its_last_checkpoint_is_held_for_it_and_then_expires(self):
        self.build(observed=[trained("f")])
        self.run_to(9, 32)
        store = self.live.observe_store
        for day in ("2026-12-22", "2026-12-23", "2026-12-24", "2026-12-28", "2026-12-29"):   # sessions 61 to 65
            result = store.cohort_candidates([], day=day, in_session=True)
            self.assertEqual([r["family"] for r in result], ["f"], f"{day}: the session's end that judges it is still owed")
        result = store.cohort_candidates([], day="2026-12-30", in_session=True)
        self.assertEqual(result, [], "the ladder's wait (five sessions) past its window, and no longer")
        self.assertEqual(store._connect().execute("SELECT reason FROM cohorts").fetchone()[0],
                         "ladder: its practice window ended and its last checkpoint was never judged")

    def test_a_pre_ladder_nontrading_cohort_expires_at_its_old_window(self):
        self.build(observed=[trained("f")])
        self.run_to(9, 32)
        self.pre_ladder()
        result = self.live.observe_store.cohort_candidates([], day="2026-10-12", in_session=True)
        self.assertEqual(result, [], "ten calendar sessions elapsed, regardless of absent fills")
        self.assertEqual(self.live.observe_store._connect().execute("SELECT reason FROM cohorts").fetchone()[0],
                         "maximum session window reached")

    def test_evaluator_change_never_appends_new_engine_decisions_to_an_old_cohort(self):
        self.build(observed=[trained("f")])
        self.run_to(9, 34)
        inst = self.live.instances["f@1:o"]
        old = self.live.shadow.accounts["f@1:o"]
        self.live.observe_store.evaluator = "new-evaluator"
        self.assertFalse(self.live.observe_store.cohort_allowed(self.live._entry_identity(inst)))
        self.live.sync_families(self.clock(), force=True)
        db = self.live.observe_store._connect()
        reason = db.execute("SELECT reason FROM cohort_archive").fetchone()[0]
        self.assertIn("evaluator changed", reason)
        self.assertEqual(json.loads(db.execute("SELECT snapshot FROM cohorts").fetchone()[0])["practice_evaluator"],
                         "new-evaluator", "the program practises again as a new cohort under the new evaluator")
        self.assertEqual(self.live.observe_store.cohort_candidates(self.families.observe(), day=MONDAY.isoformat(),
                                                                  in_session=True)[0]["practice_evaluator"],
                         "new-evaluator", "and never as the old one")
        self.run_to(9, 39)
        self.assertTrue(old.winding_down)
        forced = db.execute("SELECT DISTINCT forced FROM trades WHERE account=? AND evaluator='new-evaluator'",
                            (old.nonce,)).fetchall()
        self.assertEqual(forced, [(1,)], "the old account's new-engine wind-down exits are never program evidence")
        self.assertGreater(self.row("f")["forced"], 0)

    def test_long_dated_snapshot_gets_enough_sessions_to_observe_its_declared_horizon(self):
        row = trained("long")
        row["code"] = row["code"].replace('"dte": [0, 3]', '"dte": [0, 45]')
        self.build(observed=[row])
        self.run_to(9, 32)
        result = self.live.observe_store.cohort_candidates([], day="2026-10-12", in_session=True)
        self.assertEqual(result[0]["practice_max_sessions"], 60, "a ladder cohort's window is the ladder's, whatever its DTE")
        self.pre_ladder()
        result = self.live.observe_store.cohort_candidates([], day="2026-10-12", in_session=True)
        self.assertEqual(result[0]["practice_max_sessions"], 36, "before the ladder: its declared horizon")
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
