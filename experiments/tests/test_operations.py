from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import investigator as inv
import operations as ops
import portfolio as p


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'ledger.sqlite'
        self.db = p.database(self.path)
        self.addCleanup(self.db.close)

    def reserve(self, key):
        return p.reserve_task(self.db,
            p.build_task_request('deepseek-ai/DeepSeek-V4-Flash-0731', 'PRIVATE PROMPT'),
            p.load_packet(), key, 'investigate')

    def test_read_only_summary_retains_unknown_and_excludes_private_fields(self):
        first, second = self.reserve('private:first'), self.reserve('private:second')
        response = {'status': 'completed', 'usage': {'input_tokens': 100, 'output_tokens': 50},
                    'output': [{'text': 'PRIVATE RESPONSE'}]}
        with self.db:
            self.db.execute('UPDATE runs SET response_id=?,response=? WHERE id=?',
                            ('private-response-id', json.dumps(response), first))
            self.db.execute('UPDATE runs SET error=? WHERE id=?', ('PRIVATE ERROR', second))
        before = self.path.read_bytes()
        with closing(ops.connect(self.path)) as reader:
            result = ops.snapshot(reader, now=1789259400)
            self.assertEqual(reader.total_changes, 0)
            with self.assertRaises(sqlite3.OperationalError):
                reader.execute('DELETE FROM runs')
        self.assertEqual(before, self.path.read_bytes())
        total = result['inference']
        self.assertEqual(total['logical_requests'], 2)
        self.assertEqual(total['accepted_responses'], 1)
        self.assertEqual(total['provider_states'], {'completed': 1, 'unconfirmed': 1})
        self.assertEqual(total['unknown_usage_requests'], 1)
        self.assertIsNone(total['estimated_usd'])
        self.assertGreater(float(total['known_estimated_usd']), 0)
        serialized = json.dumps(result)
        for private in ['PRIVATE', 'private-response-id', 'private:first', first, second]:
            self.assertNotIn(private, serialized)

    def test_completion_and_review_are_separate(self):
        inv.setup(self.db)
        states = [{'phase': 'awaiting_review'}, {'phase': 'awaiting_review'}, {'phase': 'needs_attention'}]
        with self.db:
            for index, state in enumerate(states):
                self.db.execute('INSERT INTO investigations VALUES(?,?,?)', (str(index), 1, p.encoded(state)))
            self.db.execute('INSERT INTO investigation_reviews VALUES(?,?,?,?)',
                            ('0', 1, 'PRIVATE REVIEWER', p.digest(states[0])))
            self.db.execute('CREATE TABLE research_queue_jobs (investigation_id TEXT, state TEXT, paused INTEGER)')
            self.db.execute('INSERT INTO research_queue_jobs VALUES(?,?,?)', ('0', 'awaiting_review', 0))
        with closing(ops.connect(self.path)) as reader:
            full = ops.snapshot(reader)
            result = full['investigations']
        self.assertEqual(result, {'total': 3, 'reviewed': 1,
                                  'unreviewed_states': {'awaiting_review': 1, 'needs_attention': 1}})
        self.assertEqual(full['queue']['states'], {'reviewed': 1})
        self.assertEqual(self.db.execute('SELECT state FROM research_queue_jobs').fetchone()[0], 'awaiting_review')

    def test_changed_reviewed_state_and_unknown_purpose_fail_closed(self):
        inv.setup(self.db)
        with self.db:
            self.db.execute('INSERT INTO investigations VALUES(?,?,?)',
                            ('x', 1, p.encoded({'phase': 'awaiting_review'})))
            self.db.execute('INSERT INTO investigation_reviews VALUES(?,?,?,?)', ('x', 1, 'owner', 'wrong'))
        with closing(ops.connect(self.path)) as reader, self.assertRaisesRegex(ValueError, 'Reviewed investigation changed'):
            ops.snapshot(reader)
        rid = self.reserve('private:unknown')
        with self.db:
            self.db.execute('UPDATE runs SET purpose=? WHERE id=?', ('PRIVATE UNKNOWN', rid))
        with closing(ops.connect(self.path)) as reader, self.assertRaisesRegex(ValueError, 'Unknown request purpose'):
            ops.snapshot(reader)

    def test_missing_ledger_does_not_create_one_and_symlink_is_rejected(self):
        missing = self.path.with_name('missing.sqlite')
        with self.assertRaises(ValueError):
            ops.connect(missing)
        self.assertFalse(missing.exists())
        link = self.path.with_name('link.sqlite')
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            ops.connect(link)

    def test_legitimate_budget_wait_remains_visible_without_advancing_the_queue(self):
        with self.db:
            self.db.execute('CREATE TABLE research_queue_jobs (investigation_id TEXT, state TEXT, paused INTEGER)')
            self.db.execute('INSERT INTO research_queue_jobs VALUES(?,?,?)', ('synthetic-job', 'budget_wait', 0))
        with closing(ops.connect(self.path)) as reader:
            result = ops.snapshot(reader)['queue']
            self.assertEqual(reader.total_changes, 0)
        self.assertEqual(result, {'jobs': 1, 'paused': 0, 'states': {'budget_wait': 1}})

    def test_saved_future_phase_is_not_rendered_as_arbitrary_prose(self):
        inv.setup(self.db)
        with self.db:
            self.db.execute('INSERT INTO investigations VALUES(?,?,?)',
                            ('x', 1, p.encoded({'phase': 'PRIVATE UNKNOWN PHASE'})))
        with closing(ops.connect(self.path)) as reader, self.assertRaisesRegex(ValueError, 'Unknown investigation phase'):
            ops.snapshot(reader)


if __name__ == '__main__':
    unittest.main()
