"""Read-only reuse of a previously observed research prefix in new ordinary tasks.

This helper neither extends the old pilot nor buys inference. Its dated shared
corpus is suitable for complementary risk scouting, not refreshed issuer facts.
The new controller owns its independently frozen task identities and allowance.
"""
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import time

import portfolio as p
import supercache_experiment as previous


def _spec(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 1 <= path.stat().st_size <= 500_000:
        raise ValueError('Expected a bounded regular shared-context specification')
    value = json.loads(path.read_text(), object_pairs_hook=_unique)
    if (not isinstance(value, dict) or set(value) != {'prefix', 'tasks'} or
            not isinstance(value['prefix'], str) or not value['prefix'].strip()):
        raise ValueError('Expected the original shared-context specification')
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate specification field')
        result[key] = value
    return result


def validate_existing_prefix(db, spec_path):
    """Return exact prefix and private provenance; no I/O except SELECT/file read.

The expiry is a conservative 23 hours from the original write reservation. The
old pilot's work deadline is not the provider's cache lifetime. No lifetime is
extended here and no future cache hit is guaranteed.
"""
    spec = _spec(spec_path)
    rows = db.execute('SELECT * FROM shared_context_campaigns').fetchall()
    if len(rows) != 1:
        raise ValueError('Exactly one original shared-context campaign is required')
    campaign = rows[0]
    frozen = previous.protocol(db, campaign['id'])
    prefix = spec['prefix']
    sha = hashlib.sha256(prefix.encode()).hexdigest()
    stage = frozen['stages'][0]
    if (stage['id'] != 'write' or stage['phase'] != 'write' or
            frozen['prefix_sha256'] != sha or stage['request']['model'] != p.SUPERCACHE_MODEL or
            stage['request']['input'][0] != {'role': 'system', 'content': prefix}):
        raise ValueError('Prefix differs from the original frozen write')
    write, mapped = previous._run(db, campaign['id'], stage, frozen)
    if write is None or mapped is None or not mapped['result']:
        raise ValueError('A recorded original write result is required')
    if p._accounting_object(mapped['result']) != previous._saved_result(write):
        raise ValueError('Original write result changed')
    facts = p._settlement_facts(write)
    measured = previous.measure(write)
    if (measured['estimated_usd'] is None or measured['usage'] is None or
            measured['usage']['written_tokens'] < 1025 or
            Decimal(facts['estimated_usd']) > Decimal(write['reserved_cents']) / 100 or
            db.execute('SELECT COUNT(*) FROM runs WHERE response_id=?', (write['response_id'],)).fetchone()[0] != 1):
        raise ValueError('Original prefix write or its accounting is unconfirmed')
    # The observed incomplete write did successfully feed later reads. Require
    # that independent observation before reusing an incomplete generation.
    observed_reads = 0
    for read_stage in frozen['stages'][1:]:
        read, saved = previous._run(db, campaign['id'], read_stage, frozen)
        if read is None or saved is None or not saved['result']:
            continue
        if p._accounting_object(saved['result']) != previous._saved_result(read):
            raise ValueError('Original cache-read observation changed')
        result = previous.measure(read)
        if (result['provider_status'] == 'completed' and result['estimated_usd'] is not None and
                result['usage'] and result['usage']['supercached_tokens'] > 0 and
                read_stage['request']['input'][0] == stage['request']['input'][0]):
            observed_reads += 1
    if facts['response_status'] != 'completed':
        response = p._accounting_object(write['response'])
        if (facts['response_status'] != 'incomplete' or
                response.get('incomplete_details') != {'reason': 'max_output_tokens'} or not observed_reads):
            raise ValueError('An incomplete write requires an independently observed subsequent cache read')
    now, expires = time.time(), write['created'] + 23 * 3600
    if not write['created'] <= now < expires:
        raise ValueError('The original prefix is outside its conservative reuse window')
    return {'schema_version': 1, 'prefix': prefix, 'prefix_sha256': sha,
            'write_run_id': write['id'], 'write_response_sha256': facts['response_sha256'],
            'source_protocol_sha256': campaign['sha256'],
            'written_tokens': measured['usage']['written_tokens'],
            'observed_prior_reads': observed_reads, 'write_created_at': p.iso(write['created']),
            'expires_at': p.iso(expires), 'validated_at': p.iso(now),
            'scope': 'Dated shared-context risk scouting; not refreshed company evidence.'}


def build_scout_request(db, spec_path, question):
    """Construct a fresh ordinary request, without reserving or sending it."""
    p.require_text(question, 16000, 'shared-context question')
    source = validate_existing_prefix(db, spec_path)
    request = p.build_task_request(p.SUPERCACHE_MODEL, [
        {'role': 'system', 'content': source['prefix']},
        {'role': 'user', 'content': question}])
    if time.time() >= datetime.fromisoformat(source['expires_at'].replace('Z', '+00:00')).timestamp():
        raise ValueError('Shared context expired during request construction')
    return {'request': request, 'request_sha256': p.digest(request),
            'provenance': {k: v for k, v in source.items() if k != 'prefix'}}
