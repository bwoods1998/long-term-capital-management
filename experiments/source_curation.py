"""Private, immutable handoff from accepted captures to separately checked facts.

Exact passages, decimal arithmetic and identities are checked mechanically.
The named local reviewer owns the accounting meaning of headers and commentary.
This module performs no network, inference, publication or brokerage operations.
"""
from datetime import datetime
from decimal import Decimal, localcontext
import json
import math
import re
import time
import uuid

import portfolio as p
import research_sources as sources
import source_watch as watch

NAMESPACE = uuid.UUID('ef92440f-c81e-5a5c-91bc-57b41684cd58')
MAX_BUNDLE_BYTES = 12 * 1024 * 1024
MAX_PACKET_BYTES = 128 * 1024
MAX_PROVENANCE_BYTES = 256 * 1024


def _json(value, limit):
    if isinstance(value, str):
        if len(value.encode()) > limit:
            raise ValueError('Curation JSON exceeds its size limit')
        def pairs(items):
            result = {}
            for key, item in items:
                if key in result:
                    raise ValueError('Duplicate curation JSON field')
                result[key] = item
            return result
        value = json.loads(value, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    text = p.encoded(value)
    if len(text.encode()) > limit:
        raise ValueError('Curation JSON exceeds its size limit')
    return json.loads(text)


def _uuid(value, version=None):
    if (not isinstance(value, str) or str(uuid.UUID(value)) != value or
            version is not None and uuid.UUID(value).version != version):
        raise ValueError('Expected a canonical curation UUID')
    return value


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value):
        raise ValueError('Expected a SHA256 digest')
    return value


def _stamp(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value):
        raise ValueError('Expected a whole-second UTC timestamp')
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def _raw_time(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('Invalid source-watch timestamp')
    return value


def _packet(packet):
    packet = _json(packet, MAX_PACKET_BYTES)
    p.validate_packet(packet)
    if type(packet['schema_version']) is not int:
        raise ValueError('Invalid packet schema version')
    if {item['id'] for item in packet['sources']} != set(sources.SOURCE_REGISTRY):
        raise ValueError('Curation requires the complete registered source set')
    for source in packet['sources']:
        if source != sources.allowed_source(source['id']) or source['published_at'] > packet['evidence_as_of']:
            raise ValueError('Checked packet source identity or publication date differs')
    for fact in packet['facts']:
        _decimal(fact['value'])
    return packet


def _decimal(value):
    result = Decimal(str(value))
    if not result.is_finite() or len(result.as_tuple().digits) > 40 or abs(result.as_tuple().exponent) > 40:
        raise ValueError('Financial quantity exceeds exact arithmetic bounds')
    return result


def _snapshots(packet, snapshots, as_of):
    if not isinstance(snapshots, dict) or set(snapshots) != set(sources.SOURCE_REGISTRY):
        raise ValueError('Curation requires every registered snapshot')
    end = _stamp(as_of) + 1  # Caller time names a complete UTC second.
    if packet['evidence_as_of'] > as_of[:10]:
        raise ValueError('Evidence cutoff is in the future')
    for identifier, snapshot in snapshots.items():
        sources.validate_snapshot(snapshot, cutoff=packet['evidence_as_of'])
        if snapshot['id'] != identifier or _stamp(snapshot['fetched_at']) >= end:
            raise ValueError('Snapshot identity or retrieval time differs')
        if snapshot['fetched_at'][:10] > packet['evidence_as_of']:
            raise ValueError('Snapshot was retrieved after the checked evidence date')


def _span(span, text, limit=1800):
    p.exact_keys(span, ['start', 'end', 'text'], 'source passage')
    start, end, quote = span['start'], span['end'], span['text']
    if (type(start) is not int or type(end) is not int or not isinstance(quote, str) or
            not quote.strip() or len(quote) > limit or not 0 <= start < end <= len(text) or
            text[start:end] != quote):
        raise ValueError('Passage does not match the selected snapshot at its exact offsets')
    return quote


def _number(token):
    # Parentheses are an explicit negative sign; comma grouping must be valid.
    if not re.fullmatch(r'(?:[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\))', token):
        raise ValueError('Reported number is not an exact supported numeric token')
    return _decimal(('-' + token[1:-1] if token.startswith('(') else token).replace(',', ''))


def _reported(span, text):
    token = _span(span, text, 64)
    # Do not accept a substring that silently drops scale digits or a sign.
    for adjacent in (text[span['start']-1:span['start']] if span['start'] else '',
                     text[span['end']:span['end']+1]):
        if adjacent and (adjacent.isdigit() or adjacent in '.,+-()eE−﹣－＋'):
            raise ValueError('Reported passage must include the complete signed numeric token')
    return _number(token)


def _provenance(packet, snapshots, provenance):
    provenance = _json(provenance, MAX_PROVENANCE_BYTES)
    facts = {item['id']: item for item in packet['facts']}
    contexts = {item['id']: item for item in packet['context']}
    if not isinstance(provenance, list) or len(provenance) != len(facts) + len(contexts):
        raise ValueError('Every retained fact and context item requires explicit provenance')
    entries = {}
    for entry in provenance:
        if not isinstance(entry, dict) or entry.get('kind') not in ('fact', 'context'):
            raise ValueError('Unsupported provenance kind')
        fields = ['kind', 'evidence_id', 'source_id', 'snapshot_sha256']
        fields += (['operation', 'reported_number', 'operands', 'unit', 'period']
                   if entry['kind'] == 'fact' else ['passages'])
        p.exact_keys(entry, fields, 'evidence provenance')
        identifier = entry['evidence_id']
        if not isinstance(identifier, str) or identifier in entries:
            raise ValueError('Duplicate or invalid provenance identity')
        item = (facts if entry['kind'] == 'fact' else contexts).get(identifier)
        if item is None or entry['source_id'] != item['source_id']:
            raise ValueError('Provenance evidence or source identity differs')
        snapshot = snapshots[item['source_id']]
        if entry['snapshot_sha256'] != snapshot['sha256']:
            raise ValueError('Provenance refers to a different source version')
        text = snapshot['text']
        if entry['kind'] == 'context':
            if not isinstance(entry['passages'], list) or not 1 <= len(entry['passages']) <= 3:
                raise ValueError('Context requires one to three exact source passages')
            for passage in entry['passages']:
                _span(passage, text)
        else:
            for name in ('unit', 'period'):
                p.exact_keys(entry[name], ['value', 'passage'], 'financial ' + name)
                if entry[name]['value'] != item[name]:
                    raise ValueError('Provenance financial unit or period differs')
                _span(entry[name]['passage'], text)
            if entry['operation'] in ('identity', 'negate'):
                if entry['operands'] != []:
                    raise ValueError('Reported facts cannot include derived operands')
                _reported(entry['reported_number'], text)
            elif entry['operation'] in ('add', 'subtract'):
                operands = entry['operands']
                if (entry['reported_number'] is not None or not isinstance(operands, list) or
                        len(operands) != 2 or any(not isinstance(op, str) for op in operands)):
                    raise ValueError('Derived facts require exactly two fact operands')
            else:
                raise ValueError('Unsupported financial operation')
        entries[identifier] = entry
    if set(entries) != set(facts) | set(contexts):
        raise ValueError('Provenance coverage differs')
    done, visiting = {}, set()
    def calculate(identifier):
        if identifier in done:
            return done[identifier]
        if identifier in visiting or identifier not in facts:
            raise ValueError('Cyclic or unknown financial operand')
        visiting.add(identifier)
        entry, item = entries[identifier], facts[identifier]
        operation = entry['operation']
        if operation in ('identity', 'negate'):
            value = _number(entry['reported_number']['text'])
            if operation == 'negate':
                value = -value
        else:
            for operand in entry['operands']:
                other = facts.get(operand)
                if other is None or any(other[name] != item[name] for name in ('source_id', 'unit', 'period')):
                    raise ValueError('Derived operands must share source, period and unit')
            left, right = map(calculate, entry['operands'])
            value = left + right if operation == 'add' else left - right
        if value != _decimal(item['value']):
            raise ValueError('Checked financial value does not equal its reported or derived provenance')
        visiting.remove(identifier)
        done[identifier] = value
        return value
    with localcontext() as context:
        context.prec = 200  # Covers the bounded 40-digit, 40-exponent inputs exactly.
        for identifier in facts:
            calculate(identifier)
    return provenance


def initialize(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS curation_bundles (
            id TEXT PRIMARY KEY, bundle_key TEXT NOT NULL UNIQUE, created REAL NOT NULL,
            input_sha256 TEXT NOT NULL, body_json TEXT NOT NULL, body_sha256 TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS curation_reviews (
            id TEXT PRIMARY KEY, bundle_id TEXT NOT NULL UNIQUE REFERENCES curation_bundles(id),
            reviewed REAL NOT NULL, decision TEXT NOT NULL, reviewer TEXT NOT NULL,
            bundle_sha256 TEXT NOT NULL, receipt_json TEXT NOT NULL, receipt_sha256 TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS keep_curation_bundles_update BEFORE UPDATE ON curation_bundles
            BEGIN SELECT RAISE(ABORT,'Curation bundles are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS keep_curation_bundles_delete BEFORE DELETE ON curation_bundles
            BEGIN SELECT RAISE(ABORT,'Curation bundles are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS keep_curation_reviews_update BEFORE UPDATE ON curation_reviews
            BEGIN SELECT RAISE(ABORT,'Curation reviews are immutable'); END;
        CREATE TRIGGER IF NOT EXISTS keep_curation_reviews_delete BEFORE DELETE ON curation_reviews
            BEGIN SELECT RAISE(ABORT,'Curation reviews are immutable'); END;
    ''')
    return db


def _version(db, identifier, source_id, cutoff, now):
    _uuid(identifier, 4)
    row = db.execute('SELECT * FROM source_watch_versions WHERE id=?', (identifier,)).fetchone()
    if row is None or row['source_id'] != source_id or row['baseline'] not in (0, 1):
        raise ValueError('Unknown or wrong-source watch version')
    snapshot = _json(row['snapshot_json'], MAX_BUNDLE_BYTES)
    sources.validate_snapshot(snapshot, cutoff=cutoff)
    first_seen = _raw_time(row['first_seen'])
    if (snapshot['id'] != source_id or snapshot['sha256'] != row['sha256'] or
            first_seen > now or _stamp(snapshot['fetched_at']) > first_seen or
            p.iso(first_seen)[:10] > cutoff):
        raise ValueError('Source-watch identity or observation chronology differs')
    return row, snapshot


def _selection(db, versions, cutoff, now, require_current):
    if not isinstance(versions, dict) or set(versions) != set(sources.SOURCE_REGISTRY):
        raise ValueError('Select one watch version for every registered source')
    snapshots, identities, changed = {}, {}, False
    for source_id, identifier in versions.items():
        schedule = db.execute('SELECT * FROM source_watch_schedule WHERE source_id=?', (source_id,)).fetchone()
        registry_hash = p.digest(sources.allowed_source(source_id))
        if schedule is None or schedule['registry_sha256'] != registry_hash:
            raise ValueError('Source registration changed or was never watched')
        baseline_rows = db.execute('SELECT id FROM source_watch_versions WHERE source_id=? AND baseline=1',
                                   (source_id,)).fetchall()
        if len(baseline_rows) != 1:
            raise ValueError('Expected one immutable watched baseline')
        _, baseline = _version(db, baseline_rows[0]['id'], source_id, cutoff, now)
        row, snapshot = _version(db, identifier, source_id, cutoff, now)
        source_review, observation = None, None
        if not row['baseline']:
            accepted = db.execute('SELECT * FROM source_watch_reviews WHERE version_id=?', (identifier,)).fetchone()
            if accepted is None or accepted['decision'] != 'accept':
                raise ValueError('Changed capture needs a separate source-watch acceptance')
            reviewed = _raw_time(accepted['reviewed'])
            p.require_text(accepted['reviewer'], 80, 'source reviewer')
            observed = db.execute('SELECT * FROM source_watch_observations WHERE version_id=? ORDER BY started,id LIMIT 1',
                                  (identifier,)).fetchone()
            if (observed is None or observed['source_id'] != source_id or
                    not row['first_seen'] <= _raw_time(observed['started']) <=
                    _raw_time(observed['finished']) <= reviewed <= now):
                raise ValueError('Candidate was not observed and accepted before curation')
            _uuid(observed['id'], 4)
            if (observed['version_id'] != identifier or
                    observed['state'] not in ('new_candidate', 'known_candidate') or
                    observed['comparison_version'] not in (watch.COMPARISON_VERSION, 'raw-sha256-v0')):
                raise ValueError('Unsupported candidate observation identity, state or comparison version')
            if p.iso(observed['finished'])[:10] > cutoff:
                raise ValueError('Candidate capture completed after the checked evidence date')
            if watch.content_key(snapshot) == watch.content_key(baseline):
                raise ValueError('Select the baseline instead of an accepted metadata-only version')
            source_review = {'decision': 'accept', 'reviewed': reviewed, 'reviewer': accepted['reviewer']}
            observation = {name: observed[name] for name in
                           ('id', 'started', 'finished', 'state', 'comparison_version')}
            changed = True
        if require_current:
            latest = db.execute('''SELECT * FROM source_watch_observations WHERE source_id=? AND version_id IS NOT NULL
                                   ORDER BY started DESC,id DESC LIMIT 1''', (source_id,)).fetchone()
            if latest:
                if not _raw_time(latest['started']) <= _raw_time(latest['finished']) <= now:
                    raise ValueError('Latest observation is in the future or out of order')
                _, current = _version(db, latest['version_id'], source_id, p.iso(now)[:10], now)
                if watch.content_key(current) != watch.content_key(snapshot):
                    raise ValueError('A different substantive source version is now current; curate it first')
        snapshots[source_id] = snapshot
        identities[source_id] = {'version_id': identifier, 'first_seen': row['first_seen'],
            'baseline': bool(row['baseline']), 'baseline_sha256': baseline['sha256'],
            'registry_sha256': registry_hash, 'source_review': source_review, 'observation': observation}
    if not changed:
        raise ValueError('Curation requires an accepted substantive change, not metadata-only noise')
    return snapshots, identities


def _input(prior_packet, packet, source_versions, provenance):
    prior, checked = _packet(prior_packet), _packet(packet)
    if any(prior[name] != checked[name] for name in ('id', 'symbol', 'company')):
        raise ValueError('Curation cannot change the thesis or company identity')
    if prior['evidence_as_of'] > checked['evidence_as_of']:
        raise ValueError('Checked evidence cannot move backwards in time')
    return _json({'prior_packet': prior, 'packet': checked,
                  'source_versions': source_versions, 'provenance': provenance}, MAX_BUNDLE_BYTES)


def _body(db, bundle_id, now, require_current):
    _uuid(bundle_id, 5)
    row = db.execute('SELECT * FROM curation_bundles WHERE id=?', (bundle_id,)).fetchone()
    if row is None:
        raise ValueError('Unknown curation bundle')
    body = _json(row['body_json'], MAX_BUNDLE_BYTES)
    p.exact_keys(body, ['schema_version', 'bundle_id', 'key', 'prepared_at', 'input',
                        'snapshots', 'watch_identities'], 'curation bundle')
    if (type(body['schema_version']) is not int or body['schema_version'] != 1 or
            body['bundle_id'] != bundle_id or body['key'] != row['bundle_key'] or
            p.digest(body) != row['body_sha256'] or p.digest(body['input']) != row['input_sha256'] or
            bundle_id != str(uuid.uuid5(NAMESPACE, body['key'] + ':' + row['input_sha256']))):
        raise ValueError('Curation bundle integrity check failed')
    p.require_text(body['key'], 100, 'curation key')
    created = _raw_time(row['created'])
    if created > now or body['prepared_at'] != p.iso(created):
        raise ValueError('Curation preparation timestamp differs')
    p.exact_keys(body['input'], ['prior_packet', 'packet', 'source_versions', 'provenance'], 'curation input')
    data = _input(**body['input'])
    snapshots, identities = _selection(db, data['source_versions'], data['packet']['evidence_as_of'], now, require_current)
    if snapshots != body['snapshots'] or identities != body['watch_identities']:
        raise ValueError('Frozen source identities differ from the accepted watch versions')
    # These checks apply against preparation time, even on much later reads.
    _selection(db, data['source_versions'], data['packet']['evidence_as_of'], created, False)
    _snapshots(data['packet'], snapshots, body['prepared_at'])
    _provenance(data['packet'], snapshots, data['provenance'])
    return row, body


def prepare(db, key, *, prior_packet, packet, source_versions, provenance):
    """Freeze a pending bundle. Existing keys cannot change inputs or old captures."""
    p.require_text(key, 100, 'curation key')
    data = _input(prior_packet, packet, source_versions, provenance)
    input_hash = p.digest(data)
    initialize(db)
    with db:
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT * FROM curation_bundles WHERE bundle_key=?', (key,)).fetchone()
        if old:
            if old['input_sha256'] != input_hash:
                raise ValueError('Curation key is already bound to different inputs')
            row, _ = _body(db, old['id'], time.time(), False)
            review_row = db.execute('SELECT decision FROM curation_reviews WHERE bundle_id=?', (row['id'],)).fetchone()
            return {'bundle_id': row['id'], 'sha256': row['body_sha256'],
                    'state': review_row['decision'] if review_row else 'pending_review'}
        now = time.time()
        snapshots, identities = _selection(db, source_versions, data['packet']['evidence_as_of'], now, True)
        _snapshots(data['packet'], snapshots, p.iso(now))
        _provenance(data['packet'], snapshots, provenance)
        identifier = str(uuid.uuid5(NAMESPACE, key + ':' + input_hash))
        body = {'schema_version': 1, 'bundle_id': identifier, 'key': key, 'prepared_at': p.iso(now),
                'input': data, 'snapshots': snapshots, 'watch_identities': identities}
        body = _json(body, MAX_BUNDLE_BYTES)
        sha = p.digest(body)
        db.execute('INSERT INTO curation_bundles VALUES(?,?,?,?,?,?)',
                   (identifier, key, now, input_hash, p.encoded(body), sha))
    return {'bundle_id': identifier, 'sha256': sha, 'state': 'pending_review'}


def _receipt(body, sha, review_id, decision, reviewer, reviewed_at):
    data = body['input']
    receipt = {'schema_version': 1, 'bundle_id': body['bundle_id'], 'bundle_sha256': sha,
        'packet_sha256': p.digest(data['packet']), 'prior_packet_sha256': p.digest(data['prior_packet']),
        'evidence_cutoff': data['packet']['evidence_as_of'], 'source_versions': data['source_versions'],
        'source_sha256': {identifier: item['sha256'] for identifier, item in body['snapshots'].items()},
        'provenance_sha256': p.digest(data['provenance']), 'prepared_at': body['prepared_at'],
        'review': {'id': review_id, 'decision': decision, 'reviewed_at': reviewed_at, 'reviewer': reviewer}}
    return {**receipt, 'sha256': p.digest(receipt)}


def validate_receipt(receipt, *, packet, snapshots, evidence_cutoff, as_of):
    """Pure validation for a queue's frozen inputs; no clock, DB or cache reads."""
    p.exact_keys(receipt, ['schema_version', 'bundle_id', 'bundle_sha256', 'packet_sha256',
        'prior_packet_sha256', 'evidence_cutoff', 'source_versions', 'source_sha256',
        'provenance_sha256', 'prepared_at', 'review', 'sha256'], 'curation receipt')
    if type(receipt['schema_version']) is not int or receipt['schema_version'] != 1:
        raise ValueError('Invalid curation receipt version')
    _uuid(receipt['bundle_id'], 5)
    for name in ('bundle_sha256', 'packet_sha256', 'prior_packet_sha256', 'provenance_sha256', 'sha256'):
        _hash(receipt[name])
    if p.digest({key: value for key, value in receipt.items() if key != 'sha256'}) != receipt['sha256']:
        raise ValueError('Curation receipt hash mismatch')
    checked = _packet(packet)
    _snapshots(checked, snapshots, as_of)
    if (evidence_cutoff != checked['evidence_as_of'] or evidence_cutoff != receipt['evidence_cutoff'] or
            receipt['packet_sha256'] != p.digest(checked)):
        raise ValueError('Receipt is bound to a different checked packet or date')
    for name in ('source_versions', 'source_sha256'):
        if not isinstance(receipt[name], dict) or set(receipt[name]) != set(sources.SOURCE_REGISTRY):
            raise ValueError('Receipt requires all registered source identities')
    for identifier in snapshots:
        _uuid(receipt['source_versions'][identifier], 4)
        _hash(receipt['source_sha256'][identifier])
        if receipt['source_sha256'][identifier] != snapshots[identifier]['sha256']:
            raise ValueError('Receipt snapshot hash binding differs')
    review_data = receipt['review']
    p.exact_keys(review_data, ['id', 'decision', 'reviewed_at', 'reviewer'], 'curation approval')
    _uuid(review_data['id'], 4)
    p.require_text(review_data['reviewer'], 80, 'curation reviewer')
    if (review_data['decision'] != 'approve' or not _stamp(receipt['prepared_at']) <=
            _stamp(review_data['reviewed_at']) <= _stamp(as_of)):
        raise ValueError('Receipt lacks a dated, prior curation approval')
    if any(_stamp(item['fetched_at']) > _stamp(receipt['prepared_at']) for item in snapshots.values()):
        raise ValueError('Receipt preparation predates its source capture')
    return receipt


def review(db, bundle_id, decision, reviewer, *, expected_sha256):
    """Record one final local decision over the exact pending bundle digest."""
    if decision not in ('approve', 'reject'):
        raise ValueError('Choose approve or reject for the separate fact curation review')
    p.require_text(reviewer, 80, 'curation reviewer')
    _hash(expected_sha256)
    with db:
        db.execute('BEGIN IMMEDIATE')
        now = time.time()
        row, body = _body(db, bundle_id, now, decision == 'approve')
        if expected_sha256 != row['body_sha256']:
            raise ValueError('Review digest differs from the prepared bundle')
        identifier = str(uuid.uuid4())
        receipt = _receipt(body, row['body_sha256'], identifier, decision, reviewer, p.iso(now))
        if decision == 'approve':
            validate_receipt(receipt, packet=body['input']['packet'], snapshots=body['snapshots'],
                             evidence_cutoff=receipt['evidence_cutoff'], as_of=p.iso(now))
        db.execute('INSERT INTO curation_reviews VALUES(?,?,?,?,?,?,?,?)',
            (identifier, bundle_id, now, decision, reviewer, row['body_sha256'], p.encoded(receipt), receipt['sha256']))
    return receipt


def load_reviewed(db, bundle_id, *, as_of, require_current=True):
    """Read only, including inside the queue's existing BEGIN IMMEDIATE transaction."""
    if type(require_current) is not bool:
        raise ValueError('require_current must be a boolean')
    now = _stamp(as_of) + 0.999999
    row, body = _body(db, bundle_id, now, require_current)
    decision = db.execute('SELECT * FROM curation_reviews WHERE bundle_id=?', (bundle_id,)).fetchone()
    if decision is None or decision['decision'] != 'approve':
        raise ValueError('Bundle requires a separate curation approval')
    receipt = _json(decision['receipt_json'], MAX_PROVENANCE_BYTES)
    expected = _receipt(body, row['body_sha256'], decision['id'], decision['decision'],
                        decision['reviewer'], p.iso(_raw_time(decision['reviewed'])))
    if (not row['created'] <= decision['reviewed'] <= now or receipt != expected or
            decision['bundle_sha256'] != row['body_sha256'] or decision['receipt_sha256'] != receipt['sha256']):
        raise ValueError('Curation review identity or integrity differs')
    result = {'packet': body['input']['packet'], 'snapshots': body['snapshots'],
              'evidence_cutoff': receipt['evidence_cutoff'], 'receipt': receipt}
    validate_receipt(receipt, packet=result['packet'], snapshots=result['snapshots'],
                     evidence_cutoff=result['evidence_cutoff'], as_of=as_of)
    return result
