"""Publish consistent local research snapshots. No provider calls or deployment.

The optional --site copy requires Node and a personal-site checkout containing
its three real publication validators. Exporting this repository alone needs
only Python and the existing private research ledger.
"""
import argparse
from contextlib import closing
from copy import deepcopy
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import investigator as investigations
import operations
import portfolio as portfolio

STATES = ('checkpoint', 'running', 'awaiting_review', 'needs_attention', 'idle')


def read_json(path, *, raw=False):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
        raise ValueError('Expected a bounded regular JSON file')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON field')
            result[key] = value
        return result
    content = path.read_bytes()
    if len(content) > 2_000_000:
        raise ValueError('JSON file exceeds its envelope')
    value = json.loads(content, object_pairs_hook=unique)
    return (value, content) if raw else value


def money(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+(?:\.\d+)?', value):
        raise ValueError('Invalid recorded cost')
    number = Decimal(value)
    if not number.is_finite() or number > 100000 or len(value) > 28:
        raise ValueError('Recorded cost outside publication bounds')
    return number


def compute_costs(root):
    """Count the dated isolation trials once, plus private live-worker journals."""
    known, unknown = Decimal(0), 0
    try:
        history = read_json(root / 'data/experiments/sailbox-validation-2026-09-12.json')
        attempts = history['attempts']
        if not isinstance(attempts, list) or not attempts:
            raise ValueError('Missing historical compute attempts')
        for attempt in attempts:
            try:
                known += money(attempt['finalized_usd'])
                unknown += attempt.get('terminated') is not True
            except (ValueError, KeyError, TypeError):
                unknown += 1
    except (OSError, ValueError, KeyError, TypeError):
        unknown += 1
    folder = root / '.data/cloud-research'
    if folder.is_symlink() or not folder.is_dir():
        return known, unknown + 1
    seen = set()
    for directory in sorted(folder.iterdir()):
        if not directory.is_dir():
            continue  # The global admission lock is not a compute session.
        try:
            if directory.is_symlink():
                raise ValueError('Invalid compute journal directory')
            record = read_json(directory / 'state.json')
            if record.get('phase') == 'prepared':
                continue
            identity = record.get('sailbox_id')
            if not isinstance(identity, str) or not identity or identity in seen:
                raise ValueError('Missing or repeated compute identity')
            seen.add(identity)
            costs = record['costs']
            total = money(costs['estimated_total_cost_usd'])
            finalized = money(costs['finalized_cost_usd'])
            active = money(costs['estimated_active_cost_usd'])
            if total != finalized + active:
                raise ValueError('Compute accounting is inconsistent')
            known += total
            unknown += not (record.get('finished') is True and record.get('phase') == 'closed' and active == 0)
        except (OSError, ValueError, KeyError, TypeError):
            unknown += 1
    return known, unknown


def metadata(template):
    if not isinstance(template, dict) or set(template) != {
            'schema_version', 'saved_at', 'state', 'current_focus', 'next_milestone',
            'costs', 'reviewed', 'sail', 'links'} or template['schema_version'] != 1:
        raise ValueError('Invalid public status template')
    def text(value, limit):
        return isinstance(value, str) and 0 < len(value) <= limit and not any(ord(c) < 32 for c in value)
    focus = template['current_focus']
    if (not isinstance(focus, dict) or set(focus) != {'company', 'symbol', 'question'} or
            focus['company'] != 'Microsoft' or focus['symbol'] != 'MSFT' or
            not text(focus['question'], 240) or not text(template['next_milestone'], 240)):
        raise ValueError('Invalid public focus metadata')
    products = template['sail']
    if not isinstance(products, list) or not 1 <= len(products) <= 3:
        raise ValueError('Invalid product metadata')
    seen = set()
    for item in products:
        if (not isinstance(item, dict) or set(item) != {'product', 'status', 'detail', 'docs_url'} or
                item['product'] not in {'inference', 'voyages', 'sailbox'} or item['product'] in seen or
                item['status'] not in {'used', 'planned'} or not text(item['detail'], 220) or
                not text(item['docs_url'], 300) or not re.fullmatch(r'https://docs\.sailresearch\.com/[a-z0-9/-]*', item['docs_url'])):
            raise ValueError('Invalid product metadata')
        seen.add(item['product'])
    if not isinstance(template['links'], list) or not 1 <= len(template['links']) <= 3:
        raise ValueError('Invalid public reference links')
    for item in template['links']:
        if (not isinstance(item, dict) or set(item) != {'label', 'href'} or not text(item['label'], 40) or
                not text(item['href'], 300) or not re.fullmatch(
                    r'https://github\.com/bwoods1998/portfolio-agent/blob/main/(?:docs/[A-Za-z0-9_-]+\.md|data/experiments/[a-z0-9-]+\.json)', item['href'])):
            raise ValueError('Invalid public reference link')
    return deepcopy(template)


def projections(database, root, state):
    if state not in STATES:
        raise ValueError('Unknown publication state')
    template = metadata(read_json(root / 'public/project-status.json'))
    # The existing investigator projection runs idempotent schema setup. A
    # frozen in-memory backup keeps that work off the real read-only ledger.
    with closing(operations.connect(database)) as source, closing(sqlite3.connect(':memory:')) as frozen:
        source.execute('BEGIN')
        source.backup(frozen)
        source.rollback()
        frozen.row_factory = sqlite3.Row
        thesis = portfolio.public_snapshot(frozen)
        reports = investigations.public_snapshot(frozen)
    stamp = portfolio.iso(time.time())
    thesis['published_at'] = reports['published_at'] = template['saved_at'] = stamp
    known, unknown = compute_costs(root)
    template.update(state=state, reviewed={'theses': len(thesis['thesis']['revisions']),
                                         'investigations': len(reports['investigations'])},
                    costs={'inference_known_usd': thesis['costs']['known_estimated_usd'],
                           'inference_unknown_requests': thesis['costs']['unknown_runs'],
                           'compute_known_usd': format(known, 'f'), 'compute_unknown_items': unknown})
    for field in ('inference_known_usd', 'compute_known_usd'):
        money(template['costs'][field])
    for count in [*template['reviewed'].values(), unknown, thesis['costs']['unknown_runs']]:
        if type(count) is not int or not 0 <= count <= 1_000_000:
            raise ValueError('Invalid publication count')
    return {'portfolio.json': thesis, 'investigations.json': reports, 'project-status.json': template}


def export_project(database=None, *, root=ROOT, site=None, state='checkpoint'):
    root = Path(root)
    data = projections(database or root / '.data/portfolio.sqlite', root, state)
    raw = {name: (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode()
           for name, value in data.items()}
    destinations = {root / 'public' / name: body for name, body in raw.items()}
    if site is not None:
        site = Path(site).resolve()
        universe, universe_raw = read_json(root / 'public/universe.json', raw=True)
        # Reuse the actual publication contracts. Node evaluates local modules;
        # there is no DOM, network request, model client, or shell interpolation.
        validator = """import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
const base=process.argv[1];const d=JSON.parse(fs.readFileSync(0,'utf8'));
const p=await import(pathToFileURL(base+'/portfolio/portfolio.js'));
const i=await import(pathToFileURL(base+'/portfolio/investigations.js'));
const u=await import(pathToFileURL(base+'/portfolio/universe.js'));
if(!p.validSnapshot(d['portfolio.json'])||!i.validInvestigations(d['investigations.json'])||
 !p.validProjectStatus(d['project-status.json'],d['portfolio.json'],d['investigations.json'])||
 !u.validUniverse(d.universe))process.exitCode=1;"""
        result = subprocess.run(['node', '--input-type=module', '-e', validator, str(site)],
                                input=json.dumps({**data, 'universe': universe}, allow_nan=False).encode(),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        if result.returncode:
            raise ValueError('Website publication contracts rejected the projection')
        for name, body in raw.items():
            destinations[site / 'portfolio' / ('snapshot.json' if name == 'portfolio.json' else name)] = body
        destinations[site / 'portfolio/universe.json'] = universe_raw
    temporary = []
    try:
        for path, body in destinations.items():
            if path.is_symlink() or any(p.is_symlink() for p in path.parents) or '.data' in path.parts:
                raise ValueError('Public destinations must not traverse private storage or symlinks')
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
            temporary.append((Path(name), path))
            with os.fdopen(fd, 'wb') as output:
                output.write(body)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(name, 0o644)
        for temporary_path, destination in temporary:
            temporary_path.replace(destination)
    finally:
        for temporary_path, _ in temporary:
            temporary_path.unlink(missing_ok=True)
    status = data['project-status.json']
    return {'files': len(destinations), **status['reviewed'], **status['costs']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path)
    parser.add_argument('--site', type=Path, help='Personal-site checkout; requires Node and its local validators')
    parser.add_argument('--state', choices=STATES, default='checkpoint')
    args = parser.parse_args()
    print(json.dumps(export_project(args.database, site=args.site, state=args.state)))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit('Project export stopped: ' + type(error).__name__ + '. No provider requests were made.') from None
