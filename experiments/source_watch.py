"""A local, zero-inference inbox for changes to registered primary sources.

Repeated checks never replace frozen research evidence or launch paid work.
Reviewing a candidate means source curation; financial facts still need checking.
"""
import argparse
from contextlib import closing, contextmanager
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

import portfolio as p
import research_sources as sources

ROOT = Path(__file__).resolve().parent
INTERVAL = 3600
MAX_BACKOFF = 24 * 3600
COMPARISON_VERSION = 'microsoft-trace-line-v1'


def content_key(artifact):
    """Ignore only the observed request trace line; retain complete raw evidence.

    Both registered Microsoft pages put an ephemeral request identifier on the
    second normalized line. It is not a financial disclosure. No other lines,
    dates, numbers, whitespace or source fields are discarded for comparison.
    """
    lines = artifact['text'].split('\n')
    if len(lines) > 1 and re.fullmatch(r'This is the Trace Id: [0-9a-f]{28,64}', lines[1]):
        del lines[1]
    return p.digest({'algorithm': COMPARISON_VERSION, 'source_id': artifact['id'], 'lines': lines})


def initialize(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS source_watch_versions (
            id TEXT PRIMARY KEY, source_id TEXT NOT NULL, sha256 TEXT NOT NULL,
            first_seen REAL NOT NULL, baseline INTEGER NOT NULL,
            snapshot_json TEXT NOT NULL, UNIQUE(source_id, sha256));
        CREATE TABLE IF NOT EXISTS source_watch_schedule (
            source_id TEXT PRIMARY KEY, registry_sha256 TEXT NOT NULL,
            next_check REAL NOT NULL, failures INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS source_watch_observations (
            id TEXT PRIMARY KEY, source_id TEXT NOT NULL, started REAL NOT NULL,
            finished REAL NOT NULL, state TEXT NOT NULL,
            version_id TEXT REFERENCES source_watch_versions(id));
        CREATE TABLE IF NOT EXISTS source_watch_reviews (
            version_id TEXT PRIMARY KEY REFERENCES source_watch_versions(id),
            reviewed REAL NOT NULL, reviewer TEXT NOT NULL, decision TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS immutable_watch_versions_update BEFORE UPDATE ON source_watch_versions
            BEGIN SELECT RAISE(ABORT,'Source versions are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_watch_versions_delete BEFORE DELETE ON source_watch_versions
            BEGIN SELECT RAISE(ABORT,'Source versions are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_watch_observations_update BEFORE UPDATE ON source_watch_observations
            BEGIN SELECT RAISE(ABORT,'Source observations are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_watch_observations_delete BEFORE DELETE ON source_watch_observations
            BEGIN SELECT RAISE(ABORT,'Source observations are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_watch_reviews_update BEFORE UPDATE ON source_watch_reviews
            BEGIN SELECT RAISE(ABORT,'Source decisions are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_watch_reviews_delete BEFORE DELETE ON source_watch_reviews
            BEGIN SELECT RAISE(ABORT,'Source decisions are immutable'); END;
    ''')
    columns = {row['name'] for row in db.execute('PRAGMA table_info(source_watch_observations)')}
    if 'comparison_version' not in columns:
        # Earlier raw-hash observations remain identifiable; do not rewrite them.
        db.execute("ALTER TABLE source_watch_observations ADD COLUMN comparison_version TEXT NOT NULL DEFAULT 'raw-sha256-v0'")
    return db


@contextmanager
def lock(db):
    path = db.execute('PRAGMA database_list').fetchone()['file']
    if not path:
        raise ValueError('Use the persistent private ledger')
    descriptor = os.open(path + '.source-watch.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    except BlockingIOError:
        raise ValueError('Another source watcher owns this ledger') from None
    finally:
        os.close(descriptor)


def seed(db, root=ROOT):
    """Register existing frozen captures, with no network or cache creation."""
    initialize(db)
    store = sources.SourceStore(root)
    captures = []
    for source_id in sources.SOURCE_REGISTRY:
        # _read validates size, symlinks, identity and digest without fetching.
        artifact = store._read(store.path / (source_id + '.json'), None)
        if artifact['id'] != source_id:
            raise ValueError('Frozen source filename and identity differ')
        captures.append(artifact)
    with lock(db), db:
        db.execute('BEGIN IMMEDIATE')
        for artifact in captures:
            source_id = artifact['id']
            registry_hash = p.digest(sources.allowed_source(source_id))
            existing = db.execute('SELECT * FROM source_watch_schedule WHERE source_id=?', (source_id,)).fetchone()
            if existing:
                if existing['registry_sha256'] != registry_hash:
                    raise ValueError('Registry changed; curate the new source identity before watching')
                baseline = db.execute('SELECT sha256 FROM source_watch_versions WHERE source_id=? AND baseline=1',
                                      (source_id,)).fetchone()
                if baseline is None or baseline['sha256'] != artifact['sha256']:
                    raise ValueError('Frozen research baseline changed')
                continue
            db.execute('INSERT INTO source_watch_versions VALUES(?,?,?,?,?,?)',
                       (str(uuid.uuid4()), source_id, artifact['sha256'], time.time(), 1, p.encoded(artifact)))
            db.execute('INSERT INTO source_watch_schedule VALUES(?,?,?,0)', (source_id, registry_hash, 0))
    return status(db)


def _snapshot(source, now):
    sources._source_at_cutoff(source['id'], p.iso(now)[:10])
    text = sources.normalize_html(sources._download(source))
    return sources.validate_snapshot({**source, 'text': text,
        'sha256': hashlib.sha256(text.encode()).hexdigest(),
        'fetched_at': p.iso(now)}, cutoff=p.iso(now)[:10])


def scan(db):
    """Check due sources once; claim their next slot durably before network I/O."""
    initialize(db)
    with lock(db):
        scheduled = db.execute('SELECT * FROM source_watch_schedule ORDER BY source_id').fetchall()
        for row in scheduled:
            if p.digest(sources.allowed_source(row['source_id'])) != row['registry_sha256']:
                raise ValueError('Registered source identity changed')
        for row in scheduled:
            now = time.time()
            if row['next_check'] > now:
                continue
            source = sources.allowed_source(row['source_id'])
            if p.digest(source) != row['registry_sha256']:
                raise ValueError('Registered source identity changed')
            with db:
                db.execute('UPDATE source_watch_schedule SET next_check=? WHERE source_id=?',
                           (now + INTERVAL, source['id']))
            # A killed downloader leaves the slot held; restart cannot hot-loop.
            try:
                artifact = _snapshot(source, now)
            except (ValueError, OSError, TimeoutError):
                failures = row['failures'] + 1
                with db:
                    db.execute('INSERT INTO source_watch_observations VALUES(?,?,?,?,?,NULL,?)',
                               (str(uuid.uuid4()), source['id'], now, time.time(), 'fetch_failed', COMPARISON_VERSION))
                    db.execute('UPDATE source_watch_schedule SET failures=?,next_check=? WHERE source_id=?',
                               (failures, now + min(MAX_BACKOFF, INTERVAL * 2 ** min(failures, 5)), source['id']))
                continue
            with db:
                db.execute('BEGIN IMMEDIATE')
                earlier = db.execute('SELECT * FROM source_watch_versions WHERE source_id=? ORDER BY first_seen,id',
                                     (source['id'],)).fetchall()
                baseline = next(item for item in earlier if item['baseline'])
                key = content_key(artifact)
                baseline_key = content_key(json.loads(baseline['snapshot_json']))
                known_content = any(content_key(json.loads(item['snapshot_json'])) == key for item in earlier)
                version = db.execute('SELECT * FROM source_watch_versions WHERE source_id=? AND sha256=?',
                                     (source['id'], artifact['sha256'])).fetchone()
                if version is None:
                    version_id = str(uuid.uuid4())
                    db.execute('INSERT INTO source_watch_versions VALUES(?,?,?,?,?,?)',
                               (version_id, source['id'], artifact['sha256'], now, 0, p.encoded(artifact)))
                else:
                    version_id = version['id']
                state = ('baseline_match' if artifact['sha256'] == baseline['sha256'] else
                         'metadata_only' if key == baseline_key else
                         'known_candidate' if known_content else 'new_candidate')
                db.execute('INSERT INTO source_watch_observations VALUES(?,?,?,?,?,?,?)',
                           (str(uuid.uuid4()), source['id'], now, time.time(), state, version_id, COMPARISON_VERSION))
                db.execute('UPDATE source_watch_schedule SET failures=0 WHERE source_id=?', (source['id'],))
    return status(db)


def inspect(db, identifier):
    version = db.execute('SELECT * FROM source_watch_versions WHERE id=?', (identifier,)).fetchone()
    if version is None or version['baseline']:
        raise ValueError('Choose a candidate version')
    before = db.execute('SELECT * FROM source_watch_versions WHERE source_id=? AND baseline=1',
                        (version['source_id'],)).fetchone()
    old, new = json.loads(before['snapshot_json']), json.loads(version['snapshot_json'])
    sources.validate_snapshot(old)
    sources.validate_snapshot(new)
    import difflib
    changes = list(difflib.unified_diff(old['text'].splitlines(), new['text'].splitlines(),
                                      fromfile='frozen-research-baseline', tofile='candidate-source-capture', n=3))
    return {'id': identifier, 'source_id': version['source_id'], 'first_observed_at': p.iso(version['first_seen']),
            'original_published_at': new['published_at'], 'baseline_sha256': before['sha256'],
            'candidate_sha256': version['sha256'], 'diff_lines': changes,
            'note': 'Local source curation only. Check changed facts and source dates before new research.'}


def review(db, identifier, decision, reviewer):
    if decision not in {'accept', 'reject'}:
        raise ValueError('Choose accept or reject')
    p.require_text(reviewer, 80, 'source reviewer')
    inspect(db, identifier)
    with db:
        db.execute('INSERT INTO source_watch_reviews VALUES(?,?,?,?)', (identifier, time.time(), reviewer, decision))
    return status(db)


def status(db):
    """An allowlisted local status: no source text, raw errors or reviewer prose."""
    initialize(db)
    result = []
    for schedule in db.execute('SELECT * FROM source_watch_schedule ORDER BY source_id'):
        source_id = schedule['source_id']
        observations = db.execute('SELECT * FROM source_watch_observations WHERE source_id=? ORDER BY started,id',
                                  (source_id,)).fetchall()
        versions = db.execute('''SELECT v.*,r.decision FROM source_watch_versions v
                                LEFT JOIN source_watch_reviews r ON r.version_id=v.id
                                WHERE v.source_id=? ORDER BY v.first_seen,v.id''', (source_id,)).fetchall()
        baseline_key = content_key(json.loads(next(item for item in versions if item['baseline'])['snapshot_json']))
        seen, candidates = {baseline_key}, []
        for item in versions:
            key = content_key(json.loads(item['snapshot_json']))
            if key not in seen:
                seen.add(key)
                candidates.append(item)
        latest = observations[-1] if observations else None
        result.append({**sources.allowed_source(source_id), 'checks': len(observations),
                       'last_checked_at': p.iso(latest['finished']) if latest else None,
                       'last_state': latest['state'] if latest else 'not_checked',
                       'last_comparison_version': latest['comparison_version'] if latest else None,
                       'next_check_at': p.iso(schedule['next_check']), 'consecutive_failures': schedule['failures'],
                       'candidates': [{'id': item['id'], 'sha256': item['sha256'],
                                       'first_observed_at': p.iso(item['first_seen']),
                                       'decision': item['decision'] or 'pending'} for item in candidates]})
    return {'schema_version': 1, 'sources': result, 'paid_calls': 0,
            'comparison_version': COMPARISON_VERSION,
            'publication': 'unchanged', 'checked_facts': 'unchanged'}


def watch(db, seconds=3600):
    if type(seconds) is not int or not 1 <= seconds <= 6 * 3600:
        raise ValueError('Use a one-second to six-hour watch limit')
    if not status(db)['sources']:
        raise ValueError('Seed the existing frozen sources before watching')
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        result = scan(db)
        print(json.dumps({'at': p.iso(time.time()), **result}), flush=True)
        now = time.time()
        due = [datetime.fromisoformat(item['next_check_at'].replace('Z', '+00:00')).timestamp()
               for item in result['sources']]
        remaining = end - time.monotonic()
        if remaining > 0:
            time.sleep(min(60, remaining, max(1, min(due, default=now+60) - now)))
    return status(db)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('seed', 'scan', 'status'):
        commands.add_parser(name)
    commands.add_parser('watch').add_argument('--seconds', type=int, default=3600)
    commands.add_parser('inspect').add_argument('version_id')
    command = commands.add_parser('review')
    command.add_argument('version_id')
    command.add_argument('decision', choices=['accept', 'reject'])
    command.add_argument('--reviewer', required=True)
    args = parser.parse_args()
    with closing(initialize(p.database(args.database))) as db:
        if args.command == 'seed': result = seed(db)
        elif args.command == 'scan': result = scan(db)
        elif args.command == 'watch': result = watch(db, args.seconds)
        elif args.command == 'status': result = status(db)
        elif args.command == 'inspect': result = inspect(db, args.version_id)
        else: result = review(db, args.version_id, args.decision, args.reviewer)
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError):
        raise SystemExit('Source watch could not advance. Frozen evidence and research remain unchanged.') from None
