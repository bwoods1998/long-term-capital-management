"""Publish only typed overnight checkpoints after the bounded runner finishes."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import overnight
import portfolio

SITE = ROOT.parent / 'personal-site'
PROJECT_PATHS = ['public/agent-state.json', 'public/overnight-research.json', 'public/overnight-sail-metrics.json', 'public/portfolio.json', 'public/investigations.json', 'public/project-status.json']
SITE_PATHS = ['portfolio/agent-state.json', 'portfolio/overnight-research.json', 'portfolio/snapshot.json', 'portfolio/investigations.json', 'portfolio/project-status.json']


def command(args, cwd, timeout=120):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Publication command failed: ' + args[0])
    return result.stdout.strip()


def changed(repo):
    return (set(command(['git', 'diff', '--name-only', 'HEAD'], repo).splitlines()) |
            set(command(['git', 'ls-files', '--others', '--exclude-standard'], repo).splitlines()))


def head_path(identifier):
    if not __import__('re').fullmatch('[0-9a-f-]{36}', identifier):
        raise ValueError('Invalid campaign identity')
    return ROOT / '.data/overnight' / identifier / 'publication-heads.json'


def verify_parent_heads(identifier):
    heads = json.loads(head_path(identifier).read_text())
    if set(heads) != {'portfolio-agent', 'personal-site'}:
        raise ValueError('Expected two frozen publication parents')
    for repo in (ROOT, SITE):
        if (command(['git', 'branch', '--show-current'], repo) != 'main' or
                command(['git', 'rev-parse', 'HEAD'], repo) != heads[repo.name]):
            raise RuntimeError('Repository moved beyond the authorized publication parent')


def record_parent_head(identifier, repo):
    path = head_path(identifier)
    heads = json.loads(path.read_text())
    heads[repo.name] = command(['git', 'rev-parse', 'HEAD'], repo)
    overnight.write_atomic(path, json.dumps(heads) + '\n')


def publish(identifier):
    # A concurrent, authorized presentation edit can take over publication while
    # the frozen research controller continues. The hold never changes inference.
    if head_path(identifier).with_name('publication-hold.json').exists():
        print('Publication handed off to the active presentation edit; research artifacts remain saved.')
        return
    # Never publish an intermediate restart as a finished run, or silently carry
    # unrelated work into a deployment made while the owner is away.
    with closing(portfolio.database()) as db:
        before = overnight.status(db, identifier)
        if before['state'] == 'running':
            print('Research is still running; no final publication.')
            return
    verify_parent_heads(identifier)
    if changed(ROOT) - set(PROJECT_PATHS) or changed(SITE) - set(SITE_PATHS):
        raise RuntimeError('Unrelated tracked edits require a separate publication review')
    with closing(portfolio.database()) as db:
        value = overnight.report(db, identifier)
    state = 'checkpoint' if value['state'] == 'complete' else 'needs_attention'
    command([sys.executable, 'scripts/export_project.py', '--site', str(SITE), '--state', state], ROOT)
    command([sys.executable, 'scripts/export_presentation.py', identifier, '--site', str(SITE)], ROOT)
    payload = (ROOT / 'public/overnight-research.json').read_text()
    overnight.write_atomic(SITE / 'portfolio/overnight-research.json', payload, private=False)
    command(['npm', 'run', 'check'], SITE)
    command(['npm', 'test'], SITE)
    command(['npm', 'run', 'build'], SITE)
    for repo, paths in ((ROOT, PROJECT_PATHS), (SITE, SITE_PATHS)):
        if changed(repo) - set(paths):
            raise RuntimeError('Unrelated edits appeared during publication')
        actual = [path for path in paths if (repo / path).exists() and path in changed(repo)]
        if actual:
            command(['git', 'add', '--', *actual], repo)
            # Commit only the explicitly generated paths, never unrelated staged changes.
            command(['git', 'commit', '--only', '-m', 'Record the overnight research checkpoint', '--', *actual], repo)
            record_parent_head(identifier, repo)
        command(['git', 'push', 'origin', 'main'], repo)
    command(['npm', 'run', 'deploy'], SITE, timeout=240)
    print(json.dumps({'publication': 'complete', 'state': value['state'], 'saved_at': value['saved_at']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('identifier')
    args = parser.parse_args()
    try:
        publish(args.identifier)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        # Provider/CLI stderr can contain credentials or sensitive paths. Keep it private.
        print(json.dumps({'publication': 'needs_attention', 'error_type': type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)
