"""Recovering the work past consultations named: what is found, what counts as done, and that a
backfill, an incremental run and a dry run never write a row twice (or, for the dry run, at all)."""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from league.consult_recovery import ConsultRecovery, extract, main, scan
from league.ledger import Ledger
from league.tests.fakes import Clock

HOUR = 3600.0
SCHEMA = {"key", "kind", "summary", "evidence", "agents", "source", "severity"}

DEFECT_ANSWER = ("Change your cancellation rule, not your thresholds. Your file currently cancels only by age, so a resting bid "
                 "stays live for four hours after the favourite is marked down. Keep holding filled contracts to settlement.")
TOOL_ANSWER = ("Your blocker is the missing underlying-price feed you already identified, not the favourite-band parameters. "
               "Request it before spending another replay.")
EARNINGS_SUMMARY = ("Every OHLCV branch already measured null; PEAD remains blocked by the missing point-in-time earnings panel. "
                    "Spent no credits.")


class Recovery(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "ledger.sqlite"
        self.clock = Clock()
        self.ledger = Ledger(self.path, clock=self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    # ------------------------------------------------------------------ helpers
    def consult(self, agent, answer, *, tool=None, wrote_code=False, error=False, session="research:s1"):
        """What `Merton.consult` and `Researcher._consult` append for one hire."""
        payload = {"role": "consultant", "agent": agent, "at_epoch": self.clock(), "question": "what is wrong with my file?",
                   "answer": answer, "confidence": "medium", "cost_usd": "0.7", "wrote_code": wrote_code, "tool": tool}
        if error:
            payload = {"role": "consultant", "agent": agent, "answer": "Merton returned an unreadable answer (incomplete).",
                       "code": "", "confidence": "low", "cost_usd": "0.7", "error": True}
        passed = self.ledger.append("merton.pass", payload)
        if tool:
            self.ledger.append("tool.request", {"name": tool["name"], "description": f"Merton, for {agent}: {tool['description']}"}, agent=agent)
        self.ledger.append("agent.research", {"tool": "merton", "session": session, "at_epoch": self.clock(), "question": "q",
                                              "answer": payload["answer"][:2000], "confidence": "medium", "cost_usd": "0.7",
                                              "wrote_code": wrote_code}, agent=agent)
        return passed

    def summary(self, agent, text):
        return self.ledger.append("agent.research", {"tool": "summary", "session": f"research:{agent}:x", "summary": text,
                                                     "candidate": False, "reason": "finished"}, agent=agent)

    def rows(self):
        return [{"seq": e.seq, "id": e.id, "at": e.at, "kind": e.kind, "agent": e.agent, "payload": e.payload}
                for e in self.ledger.iter()]

    def reported(self):
        return list(self.ledger.iter(kinds="repair.reported"))

    # ------------------------------------------------------------------ the three kinds
    def test_each_kind_is_found_with_its_original_excerpt(self):
        defect = self.consult("mullins", DEFECT_ANSWER)
        tooled = self.consult("hilibrand", TOOL_ANSWER, tool={"name": "Crypto Settlement Spot", "description": "the BTC and ETH spot price history at each settlement, point-in-time"})
        said = self.summary("mcentee-4", EARNINGS_SUMMARY)
        reports = {r["key"]: r for r in extract(self.rows())}

        fix = reports[f"strategy_defect:mullins:consult:{defect.seq}"]
        self.assertEqual(fix["kind"], "strategy_defect")
        self.assertEqual(fix["severity"], "high")
        self.assertIn("cancels only by age", fix["evidence"][0]["excerpt"])
        tool = reports["missing_data:tool:crypto_settlement_spot"]
        self.assertEqual(tool["kind"], "missing_data")
        self.assertEqual(tool["evidence"][0]["seq"], tooled.seq)
        self.assertIn("still open", tool["summary"])
        self.assertIn("missing_data:underlying_price", reports)
        earnings = reports["missing_data:earnings"]
        self.assertEqual(earnings["evidence"], [{"seq": said.seq, "at": said.at, "agent": "mcentee-4",
                                                 "excerpt": "PEAD remains blocked by the missing point-in-time earnings panel."}])
        for report in reports.values():
            self.assertEqual(set(k for k in report if not k.startswith("_")), SCHEMA)
            self.assertEqual(report["source"], "consult")
            self.assertTrue(report["_id"].startswith("consult:"))
            self.assertTrue(all(set(item) == {"seq", "at", "agent", "excerpt"} and len(item["excerpt"]) <= 400 for item in report["evidence"]))

    def test_one_consult_is_one_report_though_it_is_two_rows(self):
        passed = self.consult("mullins", DEFECT_ANSWER)
        keys = [r["key"] for r in extract(self.rows())]
        self.assertEqual(keys, [f"strategy_defect:mullins:consult:{passed.seq}"])

    def test_a_replacement_file_is_reported_and_says_the_file_is_not_on_the_ledger(self):
        passed = self.consult("huang", "Replace the resting YES-only rule with a symmetric calibration experiment. The file applies it.", wrote_code=True)
        (report,) = extract(self.rows())
        self.assertEqual(report["key"], f"strategy_defect:huang:consult:{passed.seq}")
        self.assertEqual(report["severity"], "medium")
        self.assertIn("not on the ledger", report["summary"])

    def test_sentences_that_name_no_known_topic_or_deny_the_gap_are_dropped(self):
        self.summary("a", "No replay or paid research is justified now. The market is closed.")
        self.summary("b", "It needs no earnings panel, observed instrument or unavailable venue feature.")
        self.summary("c", "5-min spot bars are live (the old missing spot feed blocker is resolved).")
        self.consult("d", "Official rounding and revisions alter that calculation, before spread and fee rounding.")
        self.assertEqual(extract(self.rows()), [])

    def test_funding_and_open_interest_in_one_claim_are_one_feed(self):
        self.summary("rosenfeld-9", "Runtime still lacks the only new candidate input, perpetual funding/open-interest.")
        self.assertEqual([r["key"] for r in extract(self.rows())], ["missing_data:funding_rates"])

    # ------------------------------------------------------------------ acted on
    def test_a_fulfilled_tool_is_not_reported_and_a_legacy_block_still_is(self):
        self.consult("hilibrand", "Request the spot feed.", tool={"name": "spot_feed", "description": "spot price history for BTC"})
        request = self.ledger.last("tool.request")
        self.ledger.append("tool.fulfilled", {"request": request.id, "outcome": "built", "change": "merton/toolsmith/x", "status": "deployed"})
        self.consult("leahy", "Request the value feed.", tool={"name": "value_feed", "description": "published values per market"})
        blocked = self.ledger.last("tool.request")
        self.ledger.append("tool.fulfilled", {"request": blocked.id, "outcome": "cannot be a pure tool: counts are missing", "status": "answered"})
        keys = [r["key"] for r in extract(self.rows())]
        self.assertNotIn("missing_data:tool:spot_feed", keys)
        self.assertIn("missing_data:tool:value_feed", keys)

    def test_a_request_that_was_never_filed_is_reported_as_such(self):
        self.ledger.append("merton.pass", {"role": "consultant", "agent": "x", "answer": "I am requesting a tool.",
                                           "tool": {"name": "Order Book", "description": "depth"}, "wrote_code": False})
        (report,) = extract(self.rows())
        self.assertEqual(report["key"], "bug_report:tool:order_book")
        self.assertIn("never filed", report["summary"])

    def test_a_later_strategy_or_a_tested_candidate_means_the_fix_was_acted_on(self):
        self.consult("mullins", DEFECT_ANSWER)
        self.ledger.append("agent.strategy", {"code_sha256": "ab", "params": {}, "needs": {}, "reason": "research"}, agent="mullins")
        self.consult("huang", DEFECT_ANSWER.replace("Keep", "Then keep"), wrote_code=True, session="research:huang:1")
        self.ledger.append("agent.research", {"tool": "replay", "session": "research:huang:1", "arguments": {}}, agent="huang")
        self.assertEqual([r for r in extract(self.rows()) if r["kind"] == "strategy_defect"], [])

    def test_its_own_pause_or_edit_is_not_the_fix(self):
        """Review of #249: an agent's pause of its entries (an `agent.strategy` row restating its code) read
        as the fix Merton named, so the defect never reached the repair queue."""
        self.consult("mullins", DEFECT_ANSWER)
        for control in ("pause_entries", "edit_params"):
            self.ledger.append("agent.strategy", {"code_sha256": "ab", "params": {}, "needs": {}, "control": control}, agent="mullins")
        self.assertEqual(len([r for r in extract(self.rows()) if r["kind"] == "strategy_defect"]), 1)

    def test_a_strategy_adopted_before_the_consult_does_not_count(self):
        self.ledger.append("agent.strategy", {"code_sha256": "ab", "params": {}, "needs": {}, "reason": "research"}, agent="mullins")
        self.consult("mullins", DEFECT_ANSWER)
        self.assertEqual(len([r for r in extract(self.rows()) if r["kind"] == "strategy_defect"]), 1)

    def test_error_consults_are_skipped(self):
        self.consult("huang-6", "", error=True)
        self.ledger.append("agent.research", {"tool": "merton", "session": "s", "answer": "Merton could not be reached (HTTP 502).",
                                              "wrote_code": False}, agent="huang-7")
        self.assertEqual(extract(self.rows()), [])

    # ------------------------------------------------------------------ the House job
    def test_backfill_twice_writes_each_row_once_and_incremental_writes_only_new_rows(self):
        self.consult("mullins", DEFECT_ANSWER)
        self.summary("mcentee-4", EARNINGS_SUMMARY)
        self.clock.advance(25 * HOUR)
        job, state = ConsultRecovery(self.ledger, clock=self.clock), {}
        first = job.run(state)
        self.assertEqual(first["emitted"], 2)
        self.assertEqual(state["seq"], self.ledger.head()[0] - 2)  # the two rows it just wrote are not sources
        again = ConsultRecovery(self.ledger, clock=self.clock).run({})  # a fresh backfill over the same history
        self.assertEqual(again["emitted"], 0)
        self.assertEqual(len(self.reported()), 2)

        later = self.summary("krasker-2", "Replay remains smoke-only because historical option chains are unavailable.")
        self.clock.advance(2 * HOUR)
        step = job.run(state)
        self.assertEqual(step["emitted"], 1)
        self.assertGreaterEqual(state["seq"], later.seq)
        self.assertEqual(state["emitted"], 3)
        self.assertEqual(sorted(e.payload["key"] for e in self.reported()),
                         ["missing_data:earnings", "missing_data:options_history", f"strategy_defect:mullins:consult:{self.ledger.read(kinds='merton.pass')[0].seq}"])
        rows = {e.payload["key"]: e for e in self.reported()}
        self.assertEqual(rows["missing_data:earnings"].agent, "mcentee-4")
        self.assertFalse(rows["missing_data:earnings"].public)

    def test_a_young_consult_waits_and_the_cursor_waits_for_it(self):
        passed = self.consult("mullins", DEFECT_ANSWER)
        job, state = ConsultRecovery(self.ledger, clock=self.clock), {}
        self.clock.advance(2 * HOUR)
        self.assertEqual(job.run(state)["emitted"], 0)
        self.assertLess(state["seq"], passed.seq)
        self.clock.advance(23 * HOUR)
        self.assertEqual(job.run(state)["emitted"], 1)
        self.assertGreaterEqual(state["seq"], passed.seq)

    def test_the_fix_adopted_while_it_waited_is_never_reported(self):
        self.consult("mullins", DEFECT_ANSWER)
        job, state = ConsultRecovery(self.ledger, clock=self.clock), {}
        job.run(state)
        self.clock.advance(3 * HOUR)
        self.ledger.append("agent.strategy", {"code_sha256": "cd", "params": {}, "needs": {}, "reason": "research"}, agent="mullins")
        self.clock.advance(24 * HOUR)
        self.assertEqual(job.run(state)["emitted"], 0)

    def test_summaries_count_once_per_key_agent_and_day(self):
        for _ in range(3):
            self.summary("mcentee-4", EARNINGS_SUMMARY)
        self.summary("mcentee-5", EARNINGS_SUMMARY)
        self.clock.advance(24 * HOUR)
        self.summary("mcentee-4", EARNINGS_SUMMARY)
        reports = extract(self.rows())
        self.assertEqual(len(reports), 3)
        self.assertEqual(len({r["_id"] for r in reports}), 3)

    def test_a_split_batch_decides_nothing_it_has_not_read_past(self):
        passed = self.consult("mullins", DEFECT_ANSWER)
        for n in range(4):
            self.summary(f"filler-{n}", "Nothing new.")
        self.clock.advance(48 * HOUR)
        state = {}
        job = ConsultRecovery(self.ledger, clock=self.clock, settings={"batch_rows": 2})
        job.run(state)
        self.assertEqual(self.reported(), [])  # the batch ended at the consult: it cannot know what came after
        self.assertLess(state["seq"], passed.seq)
        ConsultRecovery(self.ledger, clock=self.clock).run(state)
        self.assertEqual(len(self.reported()), 1)

    def test_a_cursor_that_cannot_move_moves_on_the_second_try(self):
        """More rows within a day of an undecided consult than one batch holds pinned the cursor for
        ever (found in review, Sept 22, 2026). The second stuck run decides by the real clock."""
        passed = self.consult("mullins", DEFECT_ANSWER)
        for n in range(6):
            self.summary(f"filler-{n}", "Nothing new.")
        self.clock.advance(48 * HOUR)
        state = {}
        job = ConsultRecovery(self.ledger, clock=self.clock, settings={"batch_rows": 3})
        job.run(state)
        self.assertEqual(self.reported(), [])
        self.assertLess(state["seq"], passed.seq)
        job.run(state)
        self.assertEqual(len(self.reported()), 1)
        self.assertGreaterEqual(state["seq"], passed.seq)
        job.run(state)
        self.assertEqual(len(self.reported()), 1)  # and never twice

    def test_due_follows_the_settings(self):
        job = ConsultRecovery(self.ledger, clock=self.clock, settings={"every_seconds": 600})
        self.assertTrue(job.due())
        job.run({})
        self.assertFalse(job.due())
        self.clock.advance(601)
        self.assertTrue(job.due())
        self.assertFalse(ConsultRecovery(self.ledger, clock=self.clock, settings={"enabled": False}).due())

    # ------------------------------------------------------------------ dry run
    def test_the_dry_run_prints_the_reports_and_writes_nothing(self):
        self.consult("mullins", DEFECT_ANSWER)
        self.summary("mcentee-4", EARNINGS_SUMMARY)
        head = self.ledger.head()
        self.ledger.close()
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(main(["--ledger", str(self.path), "--dry-run", "--all"]), 0)
        printed = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual(sorted(p["key"] for p in printed)[0], "missing_data:earnings")
        self.assertTrue(all(p["exists"] is False and p["source"] == "consult" for p in printed))
        self.assertEqual(json.loads(err.getvalue())["new"], 2)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)
        self.ledger = Ledger(self.path, clock=self.clock)
        self.assertEqual(self.ledger.head(), head)

    def test_scan_reports_the_oldest_pending_seq(self):
        passed = self.consult("mullins", DEFECT_ANSWER)
        _, pending = scan(self.rows(), now=self.clock() + HOUR)
        self.assertEqual(pending, passed.seq)
        self.assertIsNone(scan(self.rows(), now=None)[1])


if __name__ == "__main__":
    unittest.main()
