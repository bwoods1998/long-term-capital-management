"""No paid calls: reuse is fresh ordinary work, never an extension of the old pilot."""
import json
import unittest
from unittest.mock import patch

import overnight_cache as reuse
import portfolio as p
import test_supercache_experiment as fixtures


class OvernightCacheTests(unittest.TestCase):
    def setUp(self):
        self.base = fixtures.SupercacheTests()
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.db = self.base.db
        self.spec = self.base.path.parent / 'spec.json'
        self.spec.write_text(json.dumps(self.base.spec))
        self.identifier = self.base.prepare()

    def test_exact_prefix_ordinary_request_and_transaction_remain_unchanged(self):
        self.base.finish(self.identifier)
        old = [tuple(r) for r in self.db.execute('SELECT * FROM shared_context_campaigns')]
        self.db.execute('PRAGMA query_only=ON')
        self.db.execute('BEGIN')
        with patch.object(p, 'api') as api:
            built = reuse.build_scout_request(self.db, self.spec, 'Identify a shared risk and missing evidence.')
            api.assert_not_called()
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()
        self.assertEqual(built['request']['input'][0]['content'], self.base.spec['prefix'])
        self.assertEqual(built['request']['metadata'], {'completion_window': 'flex'})
        self.assertNotIn('prompt_cache_key', built['request'])
        self.assertNotIn('supercache_write', p.encoded(built['request']))
        self.assertEqual(p.validate_task_envelope(built['request']), p.TASK_PROFILES[p.SUPERCACHE_MODEL])
        self.assertEqual(built['request_sha256'], p.digest(built['request']))
        self.assertNotIn('prefix', built['provenance'])
        self.assertEqual(old, [tuple(r) for r in self.db.execute('SELECT * FROM shared_context_campaigns')])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)

    def test_changed_prefix_and_symlink_or_duplicate_keys_fail(self):
        self.base.finish(self.identifier)
        modified = dict(self.base.spec, prefix=self.base.spec['prefix']+' changed')
        self.spec.write_text(json.dumps(modified))
        with self.assertRaisesRegex(ValueError, 'Prefix'):
            reuse.validate_existing_prefix(self.db, self.spec)
        self.spec.write_text('{"prefix":"one","prefix":"two","tasks":[]}')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            reuse.validate_existing_prefix(self.db, self.spec)
        self.spec.unlink(); self.spec.symlink_to(self.base.path)
        with self.assertRaisesRegex(ValueError, 'regular'):
            reuse.validate_existing_prefix(self.db, self.spec)

    def test_unknown_write_accounting_and_changed_response_fail(self):
        self.base.finish(self.identifier, metadata={})
        with self.assertRaises(ValueError):
            reuse.validate_existing_prefix(self.db, self.spec)
        row=self.db.execute('SELECT * FROM runs').fetchone()
        response=json.loads(row['response']);response['model']='different/model'
        with self.db:
            self.db.execute('UPDATE runs SET response=? WHERE id=?',(p.encoded(response),row['id']))
        with self.assertRaises(ValueError):
            reuse.validate_existing_prefix(self.db,self.spec)

    def test_output_limited_write_needs_actual_positive_subsequent_read(self):
        self.base.incomplete_write(self.identifier)
        with self.assertRaisesRegex(ValueError, 'independently observed'):
            reuse.validate_existing_prefix(self.db, self.spec)
        import supercache_experiment as sc
        sc.authorize_incomplete_write_reads(self.db,self.identifier,'Synthetic reviewer')
        self.base.finish(self.identifier)
        source=reuse.validate_existing_prefix(self.db,self.spec)
        self.assertEqual(source['written_tokens'],3072)
        self.assertEqual(source['observed_prior_reads'],1)

    def test_reuse_window_is_original_write_age_not_old_pilot_work_deadline(self):
        self.base.finish(self.identifier)
        created=self.db.execute('SELECT created FROM runs').fetchone()[0]
        with patch.object(reuse.time,'time',return_value=created+7200):
            source=reuse.validate_existing_prefix(self.db,self.spec)
            self.assertEqual(source['expires_at'],p.iso(created+23*3600))
        with patch.object(reuse.time,'time',return_value=created+23*3600), self.assertRaisesRegex(ValueError,'reuse window'):
            reuse.build_scout_request(self.db,self.spec,'New question')
        with patch.object(reuse.time,'time',return_value=created-1), self.assertRaises(ValueError):
            reuse.validate_existing_prefix(self.db,self.spec)

    def test_new_ordinary_admission_leaves_original_pilot_bounds_intact(self):
        for _ in range(10):self.base.finish(self.identifier)
        before=self.db.execute("SELECT COUNT(*),SUM(reserved_cents) FROM runs WHERE purpose='cache_research'").fetchone()
        built=reuse.build_scout_request(self.db,self.spec,'A newly declared complementary risk scout.')
        new=p.reserve_task(self.db,built['request'],p.load_packet(),'overnight:new-risk-scout','investigate')
        self.assertEqual(new,p.reserve_task(self.db,built['request'],p.load_packet(),'overnight:new-risk-scout','investigate'))
        after=self.db.execute("SELECT COUNT(*),SUM(reserved_cents) FROM runs WHERE purpose='cache_research'").fetchone()
        self.assertEqual(tuple(before),(10,440));self.assertEqual(tuple(after),tuple(before))
        self.assertEqual(p.get_run(self.db,new)['reserved_cents'],20)


if __name__ == '__main__':
    unittest.main()
