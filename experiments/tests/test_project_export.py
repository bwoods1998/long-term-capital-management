from copy import deepcopy
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

import investigator
import portfolio as p
from scripts import export_project as export
import test_portfolio

PROJECT = Path(__file__).resolve().parents[1]


class ProjectExportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_portfolio.PortfolioTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.root = Path(self.fixture.tmp.name)
        self.db = self.fixture.database(self.fixture.path)
        investigator.setup(self.db)
        self.fixture.packet.update(symbol='MSFT', company='Microsoft')
        rid = self.fixture.reserve(self.db)
        revision = self.fixture.finish(self.db, rid)
        p.review(self.db, revision, 'Public reviewer')
        self.unknown = self.fixture.reserve(self.db)
        self.template = json.loads((PROJECT / 'public/project-status.json').read_text())
        self.write('public/project-status.json', self.template)
        self.write('public/universe.json', json.loads((PROJECT / 'public/universe.json').read_text()))
        self.write('data/experiments/sailbox-validation-2026-09-12.json', {
            'attempts': [{'finalized_usd': '0.005', 'terminated': True},
                         {'finalized_usd': '0.005', 'terminated': True}]})
        (self.root / '.data/cloud-research').mkdir(parents=True)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return path

    def closed(self, identity='sb_private', value='0.02'):
        return {'phase': 'closed', 'finished': True, 'sailbox_id': identity,
                'credential_fingerprint': 'PRIVATE_CREDENTIAL',
                'costs': {'estimated_total_cost_usd': value,
                          'finalized_cost_usd': value, 'estimated_active_cost_usd': '0'}}

    def test_export_is_read_only_consistent_and_projects_no_raw_private_fields(self):
        self.write('.data/cloud-research/closed/state.json', self.closed())
        before = self.fixture.path.read_bytes()
        with patch.object(p, 'api', side_effect=AssertionError('No provider calls')), \
                patch.object(p, 'credential_fingerprint', side_effect=AssertionError('No credentials')):
            result = export.export_project(self.fixture.path, root=self.root)
        self.assertEqual(self.fixture.path.read_bytes(), before)
        self.assertEqual(result['compute_known_usd'], '0.030')
        self.assertEqual(result['compute_unknown_items'], 0)
        self.assertEqual(result['inference_unknown_requests'], 1)
        files = {name: json.loads((self.root / 'public' / name).read_text()) for name in
                 ['portfolio.json', 'investigations.json', 'project-status.json']}
        status = files['project-status.json']; thesis = files['portfolio.json']
        self.assertEqual(status['state'], 'checkpoint')
        self.assertEqual(status['costs']['inference_known_usd'], thesis['costs']['known_estimated_usd'])
        self.assertEqual(status['saved_at'], thesis['published_at'])
        self.assertEqual(status['saved_at'], files['investigations.json']['published_at'])
        self.assertEqual(status['reviewed'], {'theses': 1, 'investigations': 0})
        for name in ['current_focus', 'next_milestone', 'sail', 'links']:
            self.assertEqual(status[name], self.template[name])
        for secret in ['PRIVATE_CREDENTIAL', 'PRIVATE_PREDICTION_DO_NOT_EXPORT',
                       'DO_NOT_EXPORT_PROVIDER_RESPONSE', 'sb_private', 'resp_test']:
            self.assertNotIn(secret, json.dumps(files))

    def test_missing_active_and_malformed_compute_remain_unknown_without_double_count(self):
        self.write('.data/cloud-research/a-closed/state.json', self.closed())
        active = self.closed('sb_active', '0.03')
        active.update(phase='ready', finished=False)
        self.write('.data/cloud-research/b-active/state.json', active)
        self.write('.data/cloud-research/c-prepared/state.json', {'phase': 'prepared'})
        (self.root / '.data/cloud-research/d-missing').mkdir()
        self.write('.data/cloud-research/e-invalid/state.json', {'phase': 'creating'})
        self.write('.data/cloud-research/f-duplicate/state.json', self.closed())
        # The public summary describes the same VM and must never add its cost.
        self.write('data/experiments/cloud-research-tools.json', {'finalized_compute_usd': '999'})
        known, unknown = export.compute_costs(self.root)
        self.assertEqual(str(known), '0.060')
        self.assertEqual(unknown, 4)
        shutil.rmtree(self.root / '.data/cloud-research')
        (self.root / 'data/experiments/sailbox-validation-2026-09-12.json').unlink()
        self.assertEqual(export.compute_costs(self.root), (0, 2))

    def test_optional_site_receives_exact_bytes_after_real_js_validation(self):
        validators = PROJECT.parent.parent / 'personal-site/portfolio'
        names = ['portfolio.js', 'investigations.js', 'universe.js']
        if not shutil.which('node') or not all((validators / name).is_file() for name in names):
            self.skipTest('Optional site integration requires Node and the separate personal-site checkout')
        site = self.root / 'site'; (site / 'portfolio').mkdir(parents=True)
        (site / 'package.json').write_text('{"type":"module"}')
        for name in names:
            shutil.copyfile(validators / name, site / 'portfolio' / name)
        result = export.export_project(self.fixture.path, root=self.root, site=site, state='idle')
        self.assertEqual(result['files'], 7)
        for public, copied in [('portfolio.json', 'snapshot.json'), ('investigations.json', 'investigations.json'),
                               ('project-status.json', 'project-status.json'), ('universe.json', 'universe.json')]:
            self.assertEqual((self.root / 'public' / public).read_bytes(), (site / 'portfolio' / copied).read_bytes())

    def test_invalid_metadata_never_replaces_existing_publications(self):
        prior = self.write('public/portfolio.json', {'sentinel': 'keep'})
        original = prior.read_bytes()
        template = deepcopy(self.template)
        template['sail'][0]['private_prompt'] = 'PRIVATE_EXTRA'
        self.write('public/project-status.json', template)
        with self.assertRaises(ValueError):
            export.export_project(self.fixture.path, root=self.root)
        self.assertEqual(prior.read_bytes(), original)
        self.assertFalse((self.root / 'public/investigations.json').exists())

    def test_live_ledger_change_during_projection_does_not_split_the_snapshot(self):
        original = investigator.public_snapshot
        def concurrent_completion(db):
            with self.db:
                self.db.execute('UPDATE runs SET response=? WHERE id=?',
                                (json.dumps(self.fixture.response()), self.unknown))
            return original(db)
        with patch.object(investigator, 'public_snapshot', side_effect=concurrent_completion):
            result = export.projections(self.fixture.path, self.root, 'checkpoint')
        self.assertEqual(result['portfolio.json']['costs']['unknown_runs'], 1)
        self.assertEqual(result['project-status.json']['costs']['inference_unknown_requests'], 1)
        self.assertIsNotNone(p.run_cost(p.get_run(self.db, self.unknown)))

    def test_missing_database_is_not_created(self):
        missing = self.root / 'absent.sqlite'
        with self.assertRaises(ValueError):
            export.export_project(missing, root=self.root)
        self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()
