"""Prepare and review local source bundles; inspect/status never modify the ledger.

Source acceptance and fact review are separate. These commands neither submit
research nor publish it. Exact passages are private local review material.
"""
import argparse
from contextlib import closing
from decimal import DecimalException
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import source_curation as c

MAX_INPUT_BYTES = 1024 * 1024
MAX_SOURCE_VERSIONS = 100  # Per registered source; always retain the baseline in the list.
INPUT_FIELDS = ('prior_packet', 'packet', 'source_versions', 'provenance')
REVIEW_NOTE = (
    'Source-watch acceptance is separate from factual approval. Exact spans and '
    'arithmetic are checked mechanically; the curator checks accounting meaning, '
    'periods, scale, attribution, and completeness. No research or publication is authorized.'
)


def read_input(path):
    """Read one bounded regular UTF-8 JSON file without following a final symlink."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_INPUT_BYTES:
            raise ValueError('Expected a bounded regular curation input file')
        with os.fdopen(descriptor, 'rb', closefd=False) as handle:
            raw = handle.read(MAX_INPUT_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError('Curation input exceeds its size limit')
    value = c._json(raw.decode('utf-8'), MAX_INPUT_BYTES)
    c.p.exact_keys(value, INPUT_FIELDS, 'curation input')
    return value


def connect(path, *, readonly):
    """Both modes require an existing ledger; only curation APIs create tables."""
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('An existing regular research ledger is required')
    mode = 'ro' if readonly else 'rw'
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=' + mode, uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    if readonly:
        db.execute('PRAGMA query_only=ON')
    return db


def _tables(db):
    tables = {row['name'] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    present = {'curation_bundles', 'curation_reviews'} & tables
    if present and len(present) != 2:
        raise ValueError('Incomplete curation schema')
    return bool(present)


def _decision(db, row, body, now):
    saved = db.execute('SELECT * FROM curation_reviews WHERE bundle_id=?', (row['id'],)).fetchone()
    if saved is None:
        return 'pending_review', None
    if saved['decision'] not in ('approve', 'reject'):
        raise ValueError('Unexpected saved curation decision')
    c._uuid(saved['id'], 4)
    c.p.require_text(saved['reviewer'], 80, 'curation reviewer')
    reviewed = c._raw_time(saved['reviewed'])
    receipt = c._json(saved['receipt_json'], c.MAX_PROVENANCE_BYTES)
    expected = c._receipt(body, row['body_sha256'], saved['id'], saved['decision'],
                          saved['reviewer'], c.p.iso(reviewed))
    if (not row['created'] <= reviewed <= now or receipt != expected or
            saved['bundle_sha256'] != row['body_sha256'] or
            saved['receipt_sha256'] != receipt['sha256']):
        raise ValueError('Saved curation review integrity differs')
    if saved['decision'] == 'approve':
        c.validate_receipt(receipt, packet=body['input']['packet'], snapshots=body['snapshots'],
                           evidence_cutoff=receipt['evidence_cutoff'], as_of=c.p.iso(now))
    return ('approved' if saved['decision'] == 'approve' else 'rejected'), receipt


def _inspect(db, bundle_id, now):
    row, body = c._body(db, bundle_id, now, False)
    state, receipt = _decision(db, row, body, now)
    # Saved integrity is already checked. A failed current-source check must not
    # erase that historical decision or imply that later work is authorized.
    try:
        c._body(db, bundle_id, now, True)
        freshness = 'current'
    except (ValueError, TypeError, KeyError, DecimalException, OverflowError):
        freshness = 'not_current_or_invalid'
    inputs = body['input']
    return {
        'schema_version': 1, 'bundle_id': row['id'], 'key': row['bundle_key'],
        'sha256': row['body_sha256'], 'prepared_at': body['prepared_at'],
        'saved_state': state, 'review': receipt['review'] if receipt else None,
        'source_check': {'checked_at': c.p.iso(now), 'freshness': freshness,
                         'approved_and_current': state == 'approved' and freshness == 'current'},
        'prior_packet': inputs['prior_packet'], 'packet': inputs['packet'],
        'provenance': inputs['provenance'],
        'hashes': {'input': row['input_sha256'], 'prior_packet': c.p.digest(inputs['prior_packet']),
                   'packet': c.p.digest(inputs['packet']), 'provenance': c.p.digest(inputs['provenance']),
                   'review_receipt': receipt['sha256'] if receipt else None},
        'sources': [{**{key: artifact[key] for key in
                       ('id', 'title', 'url', 'published_at', 'fetched_at', 'sha256')},
                     'version_id': body['watch_identities'][identifier]['version_id'],
                     'baseline': body['watch_identities'][identifier]['baseline'],
                     'first_observed_at': c.p.iso(body['watch_identities'][identifier]['first_seen']),
                     'observation_finished_at': (
                         c.p.iso(body['watch_identities'][identifier]['observation']['finished'])
                         if body['watch_identities'][identifier]['observation'] else None),
                     'source_review': body['watch_identities'][identifier]['source_review']}
                    for identifier, artifact in sorted(body['snapshots'].items())],
        'review_note': REVIEW_NOTE,
    }


def inspect(db, bundle_id, *, now=None):
    if db.in_transaction:
        raise ValueError('Use a connection without an active transaction')
    db.execute('BEGIN')
    try:
        if not _tables(db):
            raise ValueError('There are no curation bundles')
        return _inspect(db, bundle_id, time.time() if now is None else now)
    finally:
        db.rollback()


def status(db, *, now=None):
    if db.in_transaction:
        raise ValueError('Use a connection without an active transaction')
    db.execute('BEGIN')
    try:
        now = time.time() if now is None else now
        bundles = []
        if _tables(db):
            for row in db.execute('SELECT id FROM curation_bundles ORDER BY created,id'):
                item = _inspect(db, row['id'], now)
                bundles.append({key: item[key] for key in
                                ('bundle_id', 'key', 'sha256', 'prepared_at', 'saved_state', 'source_check')})
        return {'schema_version': 1, 'checked_at': c.p.iso(now), 'bundles': bundles,
                'review_note': REVIEW_NOTE}
    finally:
        db.rollback()


def sources(db, *, now=None):
    """List saved version identities, without treating acceptance as fact review."""
    if db.in_transaction:
        raise ValueError('Use a connection without an active transaction')
    db.execute('BEGIN')
    try:
        now = time.time() if now is None else now
        tables = {row['name'] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        present = {'source_watch_versions', 'source_watch_reviews'} & tables
        if present and len(present) != 2:
            raise ValueError('Incomplete source-watch schema')
        items = []
        if present:
            for source_id in sorted(c.sources.SOURCE_REGISTRY):
                total = db.execute('SELECT COUNT(*) FROM source_watch_versions WHERE source_id=?',
                                   (source_id,)).fetchone()[0]
                selected = db.execute('''SELECT id FROM source_watch_versions WHERE source_id=?
                    ORDER BY baseline DESC,first_seen DESC,id LIMIT ?''',
                    (source_id, MAX_SOURCE_VERSIONS)).fetchall()
                versions = []
                for selected_row in selected:
                    row, snapshot = c._version(db, selected_row['id'], source_id, c.p.iso(now)[:10], now)
                    decision = db.execute('SELECT decision,reviewed FROM source_watch_reviews WHERE version_id=?',
                                          (row['id'],)).fetchone()
                    if decision and (decision['decision'] not in ('accept', 'reject') or
                                     not row['first_seen'] <= c._raw_time(decision['reviewed']) <= now):
                        raise ValueError('Unexpected saved source decision')
                    versions.append({'version_id': row['id'], 'baseline': bool(row['baseline']),
                        'sha256': row['sha256'], 'published_at': snapshot['published_at'],
                        'fetched_at': snapshot['fetched_at'], 'first_observed_at': c.p.iso(row['first_seen']),
                        'saved_source_decision': decision['decision'] if decision else None})
                items.append({**c.sources.allowed_source(source_id), 'versions': versions,
                              'omitted_versions': total - len(versions)})
        return {'schema_version': 1, 'checked_at': c.p.iso(now), 'scope': 'source_metadata_only',
                'sources': items, 'maximum_versions_per_source': MAX_SOURCE_VERSIONS,
                'note': 'Saved source acceptance does not approve facts or establish current suitability. '
                        'Prepare checks substantive changes and freshness; factual review is separate.'}
    finally:
        db.rollback()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=ROOT / '.data/portfolio.sqlite')
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare', help='Save a pending local bundle; no research calls')
    prepare.add_argument('key')
    prepare.add_argument('--input', type=Path, required=True, help='Strict UTF-8 JSON, at most 1 MiB')
    commands.add_parser('inspect', help='Read exact review material without modifying state').add_argument('bundle_id')
    review = commands.add_parser('review', help='Record one immutable local factual-review decision')
    review.add_argument('bundle_id')
    review.add_argument('decision', choices=('approve', 'reject'))
    review.add_argument('--sha256', required=True, help='The exact bundle digest shown by inspect')
    review.add_argument('--reviewer', required=True)
    commands.add_parser('status', help='Read saved decisions and current source suitability')
    commands.add_parser('sources', help='List bounded source-version metadata, including baseline IDs')
    args = parser.parse_args(argv)
    try:
        inputs = read_input(args.input) if args.command == 'prepare' else None
        with closing(connect(args.database, readonly=args.command in ('inspect', 'status', 'sources'))) as db:
            if args.command == 'prepare':
                result = c.prepare(db, args.key, **inputs)
            elif args.command == 'review':
                result = c.review(db, args.bundle_id, args.decision, args.reviewer, expected_sha256=args.sha256)
            elif args.command == 'inspect':
                result = inspect(db, args.bundle_id)
            elif args.command == 'sources':
                result = sources(db)
            else:
                result = status(db)
        print(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, TypeError, KeyError, DecimalException, OverflowError,
            RecursionError, sqlite3.Error, OSError):
        parser.exit(1, 'Curation command failed. Check the local input, saved digest, source decisions, and ledger integrity.\n')


if __name__ == '__main__':
    main()
