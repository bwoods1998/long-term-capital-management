"""Publication gates with temporary repositories and mocked external commands."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import publish_overnight as publish


class PublishOvernightTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'project'
        self.site = Path(temp.name) / 'site'
        self.root.mkdir(); self.site.mkdir()
        self.calls = []
        self.edits = {self.root: set(), self.site: set()}
        self.status = {'state': 'complete', 'saved_at': '2026-09-13T08:00:00Z', 'completed_steps': 86}
        self.identifier = 'synthetic-publication'
        self.db = SimpleNamespace(close=Mock())
        for repo, paths in ((self.root, publish.PROJECT_PATHS), (self.site, publish.SITE_PATHS)):
            for name in paths:
                path = repo / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('{}\n')
        private = self.root / '.data/draft.json'; private.parent.mkdir()
        private.write_text('{"headline":"PRIVATE_UNREVIEWED_MODEL_PROSE"}')
        self.report = Mock(side_effect=self.generate)
        for target, name, kwargs in [
            (publish, 'ROOT', {'new': self.root}), (publish, 'SITE', {'new': self.site}),
            (publish, 'command', {'side_effect': self.command}),
            (publish, 'changed', {'side_effect': lambda repo: set(self.edits[repo])}),
            (publish.portfolio, 'database', {'return_value': self.db}),
            (publish.overnight, 'status', {'side_effect': lambda *_: dict(self.status)}),
            (publish.overnight, 'report', {'new': self.report}),
            (publish, 'verify_parent_heads', {'return_value': None, 'create': True}),
            (publish, 'record_parent_head', {'return_value': None, 'create': True}),
        ]:
            mocked = patch.object(target, name, **kwargs); mocked.start(); self.addCleanup(mocked.stop)

    def generate(self, *_):
        (self.root / 'public/overnight-research.json').write_text(json.dumps(self.status) + '\n')
        (self.root / 'public/overnight-sail-metrics.json').write_text('{"models":{}}\n')
        self.edits[self.root].update(publish.PROJECT_PATHS)
        return dict(self.status)

    def command(self, args, cwd, timeout=120):
        self.calls.append((list(args), cwd))
        if 'scripts/export_project.py' in args:
            self.edits[self.site].update(publish.SITE_PATHS)
        return ''

    def invoke(self):
        with redirect_stdout(StringIO()):
            publish.publish(self.identifier)

    def test_running_campaign_does_not_export_commit_push_or_deploy(self):
        self.status['state'] = 'running'
        self.invoke()
        self.report.assert_not_called()
        self.assertEqual(self.calls, [])
        self.assertEqual((self.root / 'public/overnight-research.json').read_text(), '{}\n')

    def test_unrelated_tracked_changes_block_before_any_export(self):
        self.edits[self.site].add('worker.mjs')
        with self.assertRaisesRegex(RuntimeError, 'Unrelated'):
            self.invoke()
        self.report.assert_not_called()
        self.assertEqual(self.calls, [])

    def test_successful_publication_commits_only_allowlisted_paths_and_preserves_private_draft(self):
        self.invoke()
        for repo, allowed in ((self.root, set(publish.PROJECT_PATHS)), (self.site, set(publish.SITE_PATHS))):
            commits = [args for args, cwd in self.calls if cwd == repo and args[:2] == ['git', 'commit']]
            self.assertEqual(len(commits), 1)
            self.assertIn('--only', commits[0])
            self.assertEqual(set(commits[0][commits[0].index('--') + 1:]), allowed)
            adds = [args for args, cwd in self.calls if cwd == repo and args[:2] == ['git', 'add']]
            self.assertEqual(set(adds[0][adds[0].index('--') + 1:]), allowed)
        self.assertEqual((self.site / 'portfolio/overnight-research.json').read_bytes(),
                         (self.root / 'public/overnight-research.json').read_bytes())
        self.assertNotIn('PRIVATE_UNREVIEWED_MODEL_PROSE', json.dumps(self.calls, default=str))
        self.assertNotIn('.data/', json.dumps(self.calls, default=str))
        self.assertIn('PRIVATE_UNREVIEWED_MODEL_PROSE', (self.root / '.data/draft.json').read_text())
        self.assertEqual(self.calls[-1][0], ['npm', 'run', 'deploy'])
        checks = [args for args, _ in self.calls]
        self.assertLess(checks.index(['npm', 'test']), next(i for i, args in enumerate(checks) if args[:2] == ['git', 'commit']))

    def test_new_unrelated_edits_during_build_prevent_commit_push_and_deploy(self):
        normal = self.command
        def changed_during_build(args, cwd, timeout=120):
            value = normal(args, cwd, timeout)
            if args == ['npm', 'run', 'build']:
                self.edits[self.root].add('README.md')
            return value
        with patch.object(publish, 'command', side_effect=changed_during_build), self.assertRaisesRegex(RuntimeError, 'Unrelated'):
            self.invoke()
        self.assertFalse(any(args[:2] in (['git', 'commit'], ['git', 'push']) or args == ['npm', 'run', 'deploy'] for args, _ in self.calls))

    def test_failed_site_checks_stop_before_git_or_deployment(self):
        normal = self.command
        def fail_tests(args, cwd, timeout=120):
            if args == ['npm', 'test']:
                raise RuntimeError('Offline tests failed')
            return normal(args, cwd, timeout)
        with patch.object(publish, 'command', side_effect=fail_tests), self.assertRaises(RuntimeError):
            self.invoke()
        self.assertFalse(any(args[0] == 'git' or args == ['npm', 'run', 'deploy'] for args, _ in self.calls))

    def test_incomplete_terminal_checkpoint_never_claims_complete_project_state(self):
        self.status['state'] = 'deadline'
        self.invoke()
        export = next(args for args, _ in self.calls if 'scripts/export_project.py' in args)
        self.assertEqual(export[export.index('--state') + 1], 'needs_attention')


class PublishGitGateTests(unittest.TestCase):
    def test_parent_gate_requires_saved_heads_and_rejects_unrelated_commits_or_branch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'portfolio-agent'; site = Path(temporary) / 'personal-site'
            root.mkdir(); site.mkdir()
            identifier = '11111111-1111-4111-8111-111111111111'
            expected = {'portfolio-agent': '1' * 40, 'personal-site': '2' * 40}
            actual = dict(expected)
            branches = {name: 'main' for name in expected}
            def output(args, repo, **_):
                if args == ['git', 'branch', '--show-current']:
                    return branches[repo.name]
                if args == ['git', 'rev-parse', 'HEAD']:
                    return actual[repo.name]
                raise AssertionError('Parent validation must only read Git state')
            with patch.object(publish, 'ROOT', root), patch.object(publish, 'SITE', site), \
                    patch.object(publish, 'command', side_effect=output) as command:
                with self.assertRaises(OSError):
                    publish.verify_parent_heads(identifier)
                command.assert_not_called()
                path = publish.head_path(identifier); path.parent.mkdir(parents=True)
                path.write_text(json.dumps(expected))
                publish.verify_parent_heads(identifier)
                actual['personal-site'] = '3' * 40
                with self.assertRaisesRegex(RuntimeError, 'publication parent'):
                    publish.verify_parent_heads(identifier)
                actual.update(expected); branches['portfolio-agent'] = 'unreviewed-work'
                with self.assertRaisesRegex(RuntimeError, 'publication parent'):
                    publish.verify_parent_heads(identifier)

    def test_owned_commit_head_is_saved_for_an_identical_retry_without_changing_other_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'portfolio-agent'; root.mkdir()
            identifier = '11111111-1111-4111-8111-111111111111'
            expected = {'portfolio-agent': '1' * 40, 'personal-site': '2' * 40}
            with patch.object(publish, 'ROOT', root), \
                    patch.object(publish, 'command', return_value='3' * 40):
                path = publish.head_path(identifier); path.parent.mkdir(parents=True)
                path.write_text(json.dumps(expected))
                publish.record_parent_head(identifier, root)
                self.assertEqual(json.loads(path.read_text()), {
                    'portfolio-agent': '3' * 40, 'personal-site': expected['personal-site']})

    def test_changed_includes_new_allowlisted_files_and_unrelated_untracked_files(self):
        def output(args, *_):
            if args[:3] == ['git', 'diff', '--name-only']:
                return 'public/portfolio.json'
            if args[:3] == ['git', 'ls-files', '--others']:
                return 'public/overnight-research.json\nunreviewed.txt'
            raise AssertionError('Unexpected git read')
        with patch.object(publish, 'command', side_effect=output):
            self.assertEqual(publish.changed(Path('/synthetic')), {
                'public/portfolio.json', 'public/overnight-research.json', 'unreviewed.txt'})

    def test_command_error_does_not_expose_captured_output(self):
        result = SimpleNamespace(returncode=1, stdout='PRIVATE_STDOUT', stderr='PRIVATE_CREDENTIAL')
        with patch.object(publish.subprocess, 'run', return_value=result):
            with self.assertRaises(RuntimeError) as caught:
                publish.command(['git', 'push'], Path('/synthetic'))
        self.assertNotIn('PRIVATE', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
