"""Source changes are durable curation events, never implicit paid assignments."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import portfolio as p
import research_sources as sources
import source_watch as w


class SourceWatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / '.data' / 'portfolio.sqlite'
        store = sources.SourceStore(self.root)
        store._prepare()
        self.baselines = {}
        for identifier in sources.SOURCE_REGISTRY:
            text = 'Original evidence for ' + identifier
            artifact = {**sources.allowed_source(identifier), 'fetched_at': '2026-09-12T20:00:00Z',
                        'sha256': hashlib.sha256(text.encode()).hexdigest(), 'text': text}
            target = store.path / (identifier + '.json')
            target.write_text(json.dumps(artifact))
            self.baselines[target] = target.read_bytes()
        self.no_paid = patch.object(p, 'api', side_effect=AssertionError('Source watch cannot call Sail'))
        self.no_paid.start()
        self.addCleanup(self.no_paid.stop)

    def seeded(self):
        db = w.initialize(p.database(self.path))
        w.seed(db, self.root)
        return db

    def due(self, db):
        with db:
            db.execute('UPDATE source_watch_schedule SET next_check=0')

    def download(self, source):
        return '<p>Original evidence for ' + source['id'] + '</p>'

    def test_seed_is_local_idempotent_and_does_not_create_missing_captures(self):
        with closing(self.seeded()) as db, patch.object(sources, '_download') as network:
            w.seed(db, self.root)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM source_watch_versions').fetchone()[0], 2)
            network.assert_not_called()
            next(iter(self.baselines)).unlink()
            with self.assertRaises(ValueError):
                w.seed(db, self.root)
            network.assert_not_called()

    def test_unchanged_source_observations_are_throttled_across_restart(self):
        with closing(self.seeded()) as db, patch.object(sources, '_download', side_effect=self.download) as network:
            first = w.scan(db)
            self.assertEqual(network.call_count, 2)
            self.assertTrue(all(item['last_state'] == 'baseline_match' for item in first['sources']))
        with closing(w.initialize(p.database(self.path))) as db, patch.object(sources, '_download') as network:
            again = w.scan(db)
            network.assert_not_called()
            self.assertTrue(all(item['checks'] == 1 for item in again['sources']))
        for path, data in self.baselines.items():
            self.assertEqual(path.read_bytes(), data)

    def test_changes_create_one_candidate_and_repeated_or_reverted_content_is_preserved(self):
        with closing(self.seeded()) as db, patch.object(sources, '_download', return_value='<p>Changed evidence</p>'):
            first = w.scan(db)
            ids = [item['candidates'][0]['id'] for item in first['sources']]
            self.due(db)
            again = w.scan(db)
            self.assertEqual([item['candidates'][0]['id'] for item in again['sources']], ids)
            self.assertTrue(all(item['last_state'] == 'known_candidate' for item in again['sources']))
            before = w.inspect(db, ids[0])
            self.assertIn('+Changed evidence', before['diff_lines'])
            self.assertEqual(before['original_published_at'], '2026-07-29')
            self.assertNotEqual(before['first_observed_at'][:10], before['original_published_at'])
            self.due(db)
            with patch.object(sources, '_download', side_effect=self.download):
                reverted = w.scan(db)
            self.assertTrue(all(item['last_state'] == 'baseline_match' for item in reverted['sources']))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM source_watch_versions').fetchone()[0], 4)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM source_watch_observations').fetchone()[0], 6)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0], 0)
        for path, data in self.baselines.items():
            self.assertEqual(path.read_bytes(), data)

    def test_decisions_are_final_and_do_not_publish_or_requeue_rejected_content(self):
        with closing(self.seeded()) as db, patch.object(sources, '_download', return_value='<p>Changed</p>'):
            report = w.scan(db)
            one, two = [item['candidates'][0]['id'] for item in report['sources']]
            w.review(db, one, 'reject', 'Local Editor')
            w.review(db, two, 'accept', 'Local Editor')
            with self.assertRaises(sqlite3.IntegrityError):
                w.review(db, one, 'accept', 'Different Editor')
            self.due(db)
            final = w.scan(db)
            self.assertEqual([item['candidates'][0]['decision'] for item in final['sources']], ['reject', 'accept'])
            self.assertEqual(final['publication'], 'unchanged')
            self.assertEqual(final['checked_facts'], 'unchanged')
            self.assertEqual(final['paid_calls'], 0)
            self.assertIsNone(p.current(db))

    def test_fetch_failure_is_sanitized_and_backoff_survives_restart(self):
        with closing(self.seeded()) as db, patch.object(sources, '_download', side_effect=OSError('PRIVATE ERROR')):
            report = w.scan(db)
            self.assertTrue(all(item['last_state'] == 'fetch_failed' for item in report['sources']))
            self.assertTrue(all(item['consecutive_failures'] == 1 for item in report['sources']))
            self.assertNotIn('PRIVATE ERROR', json.dumps(report))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM source_watch_versions').fetchone()[0], 2)
            starts = db.execute('SELECT source_id,started FROM source_watch_observations').fetchall()
            for row in starts:
                due = db.execute('SELECT next_check FROM source_watch_schedule WHERE source_id=?', (row['source_id'],)).fetchone()[0]
                self.assertEqual(due - row['started'], 7200)
        with closing(w.initialize(p.database(self.path))) as db, patch.object(sources, '_download') as network:
            w.scan(db)
            network.assert_not_called()

    def test_killed_download_holds_slot_and_concurrent_controller_cannot_enter(self):
        with closing(self.seeded()) as db:
            with w.lock(db), self.assertRaises(ValueError):
                w.scan(db)
            with patch.object(sources, '_download', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    w.scan(db)
            reserved = db.execute('SELECT * FROM source_watch_schedule ORDER BY source_id').fetchall()
            self.assertGreater(reserved[0]['next_check'], 0)
            self.assertEqual(reserved[1]['next_check'], 0)
        with closing(w.initialize(p.database(self.path))) as db, patch.object(sources, '_download', side_effect=self.download) as network:
            w.scan(db)
            self.assertEqual(network.call_count, 1)

    def test_source_identity_changed_cache_and_future_documents_fail_closed(self):
        with closing(self.seeded()) as db:
            identifier = next(iter(sources.SOURCE_REGISTRY))
            with patch.dict(sources.SOURCE_REGISTRY[identifier], {'url': 'https://example.invalid/unapproved'}), \
                    patch.object(sources, '_download') as network:
                with self.assertRaises(ValueError):
                    w.scan(db)
                network.assert_not_called()
            target = next(iter(self.baselines))
            artifact = json.loads(target.read_text())
            artifact['text'] = 'Changed frozen baseline'
            artifact['sha256'] = hashlib.sha256(artifact['text'].encode()).hexdigest()
            target.write_text(json.dumps(artifact))
            with self.assertRaises(ValueError):
                w.seed(db, self.root)

    def test_public_status_omits_source_text_errors_and_reviewer_names(self):
        with closing(self.seeded()) as db, patch.object(sources, '_download', return_value='<p>MODEL INJECTION TEXT</p>'):
            report = w.scan(db)
            candidate = report['sources'][0]['candidates'][0]['id']
            w.review(db, candidate, 'reject', 'PRIVATE REVIEWER')
            text = json.dumps(w.status(db))
            self.assertNotIn('MODEL INJECTION TEXT', text)
            self.assertNotIn('PRIVATE REVIEWER', text)
            for table in ('source_watch_versions', 'source_watch_reviews', 'source_watch_observations'):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute('DELETE FROM ' + table)

    def test_request_trace_noise_deduplicates_without_hiding_financial_changes(self):
        for path in self.baselines:
            artifact = json.loads(path.read_text())
            artifact['text'] = 'Microsoft report\nThis is the Trace Id: ' + 'a'*32 + '\nCash 10'
            artifact['sha256'] = hashlib.sha256(artifact['text'].encode()).hexdigest()
            path.write_text(json.dumps(artifact))
        def page(trace, cash):
            return '<p>Microsoft report</p><p>This is the Trace Id: ' + trace*32 + '</p><p>Cash ' + cash + '</p>'
        with closing(self.seeded()) as db:
            with patch.object(sources, '_download', return_value=page('b', '10')):
                noise = w.scan(db)
            self.assertTrue(all(item['last_state'] == 'metadata_only' and item['candidates'] == [] for item in noise['sources']))
            self.due(db)
            with patch.object(sources, '_download', return_value=page('c', '11')):
                changed = w.scan(db)
            ids = [item['candidates'][0]['id'] for item in changed['sources']]
            self.assertTrue(all(item['last_state'] == 'new_candidate' for item in changed['sources']))
            self.due(db)
            with patch.object(sources, '_download', return_value=page('d', '11')):
                again = w.scan(db)
            self.assertEqual([item['candidates'][0]['id'] for item in again['sources']], ids)
            self.assertTrue(all(item['last_state'] == 'known_candidate' for item in again['sources']))
            # Every distinct raw capture remains available, including trace lines.
            self.assertEqual(db.execute('SELECT COUNT(*) FROM source_watch_versions').fetchone()[0], 8)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        original = {'id': 'fy26-call', 'text': 'Title\nCash 10\nThis is the Trace Id: ' + 'a'*32}
        later = {**original, 'text': original['text'].replace('a'*32, 'b'*32)}
        self.assertNotEqual(w.content_key(original), w.content_key(later))


if __name__ == '__main__':
    unittest.main()
