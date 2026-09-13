"""Export one saved campaign for the public page without making provider calls."""
import argparse
from contextlib import closing
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import operations
import overnight


def trace_recorded(identifier):
    """Expose confirmation, never the private dashboard URL or trace identity."""
    digest = hashlib.sha256(('overnight:' + identifier).encode()).hexdigest()
    path = ROOT / '.data/voyages' / (digest + '.json')
    if not path.exists():
        return False
    saved = json.loads(path.read_text())
    return (
        saved.get('workflow_sha256') == digest
        and saved.get('delivery_confirmed') is True
        and isinstance(saved.get('voyage_id'), str)
        and bool(saved['voyage_id'])
    )


def project(database, identifier):
    """Derive both views from one immutable copy of the read-only ledger."""
    with closing(operations.connect(database)) as source:
        with closing(sqlite3.connect(':memory:')) as frozen:
            frozen.row_factory = sqlite3.Row
            source.execute('BEGIN')
            source.backup(frozen)
            source.rollback()
            status = overnight.status(frozen, identifier)
            metrics = overnight.sail_metrics(frozen, identifier)

    models = metrics['models']
    requests = sum(group['requests'] for group in models.values())
    cost = sum(Decimal(group['estimated_usd']) for group in models.values())
    if requests != status['submitted_requests'] or cost != Decimal(status['estimated_usd']):
        raise ValueError('Research measurement snapshots disagree')

    # Select explicit scalar fields. Raw drafts and checker diagnostics stay private.
    companies = []
    for company in status['companies']:
        before = company.get('baseline_checks')
        after = company.get('revised_checks')
        companies.append({
            'symbol': company['symbol'],
            'finished': company['completed_steps'] == 9,
            'initial_check': before.get('valid') if isinstance(before, dict) else None,
            'revised_check': after.get('valid') if isinstance(after, dict) else None,
            'judge_preferences': company['judge_preferences'],
        })

    cloud = metrics.get('sailbox') or {}
    return {
        'schema_version': 1,
        'saved_at': status['saved_at'],
        'state': status['state'],
        'companies': companies,
        'source_documents': status['source_documents'],
        'model_count': len(models),
        'requests': status['submitted_requests'],
        'known_inference_usd': status['estimated_usd'],
        'unknown_requests': status['unknown_requests'],
        'supercache_tokens': metrics['supercache']['observed_reused_tokens'],
        'cloud_checks': cloud.get('verified_companies', 0),
        'cloud_persistence_verified': cloud.get('persistence_verified') is True,
        'cloud_finished': cloud.get('finished') is True,
        'trace_recorded': trace_recorded(identifier),
        'scope': 'One research run. Model preferences and mechanical checks do not approve financial conclusions.',
    }


def export(identifier, site=None, database=None):
    value = project(database or ROOT / '.data/portfolio.sqlite', identifier)
    raw = json.dumps(value, indent=2) + '\n'
    overnight.write_atomic(ROOT / 'public/agent-state.json', raw, private=False)
    if site is not None:
        overnight.write_atomic(Path(site) / 'portfolio/agent-state.json', raw, private=False)
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('identifier')
    parser.add_argument('--site', type=Path)
    args = parser.parse_args()
    value = export(args.identifier, args.site)
    print(json.dumps({key: value[key] for key in (
        'state', 'requests', 'known_inference_usd', 'cloud_checks'
    )}))
