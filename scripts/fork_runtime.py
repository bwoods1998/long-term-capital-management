#!/usr/bin/env python3
"""Bounded real Sailbox fork/context experiment; prepare/status are offline.

After the main frozen deployment exists:
  python scripts/fork_runtime.py prepare --config PRIVATE/run.json --directory PRIVATE/forks
  python scripts/fork_runtime.py run --directory PRIVATE/forks
  python scripts/fork_runtime.py status --directory PRIVATE/forks
  python scripts/fork_runtime.py stop --directory PRIVATE/forks

Run can be started by a local user service at main-start +20 minutes. It waits
until that frozen time, verifies the parent's two $2 holds, then creates one
sterile seed and two checkpoint forks. Each makes five fixed company reviews.
This measures full-universe versus focused context, NOT sequential memory.
No model controls provisioning, URLs, shell commands, or portfolio authority.
The local monitor recovers cold processes and terminates the three resources at
the finite deadline; it must remain running. The branch's own timeout also bounds
execution, but a local-monitor outage can delay resource cleanup. Main portfolio
hold release/merging is deliberately separate: do not double count branch costs.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
from urllib.parse import urlencode
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portfolio_runtime.sail_host import SailHost, encoded, sha, stamp, validate_bundle, restricted_policy, http_document
from portfolio_runtime.provider import PROFILES, MODEL_ALIASES, body_for, canonical, answer_json, TERMINAL
from portfolio_runtime.accounting import estimate_cost
from portfolio_runtime.research import SYSTEM, grade_result
from portfolio_runtime.evidence import save
from host_runtime import clients, load_bundle, save_bundle, private_lock

SYMBOLS = ('NVDA', 'JPM', 'XOM', 'UNH', 'CAT')
ARMS = {'fork-context': 'full_universe', 'fork-fresh': 'focused_context'}
PROFILE = 'kimi_flex'
OUTPUT_TOKENS = 12288
QUESTIONS = {
    'NVDA': 'Assess cash conversion, capital intensity and financing resilience. Separate reported facts from missing customer concentration and valuation evidence. What would overturn a favorable thesis?',
    'JPM': 'Assess the bank using appropriate financial-sector accounting. Explain why industrial free-cash-flow shortcuts can mislead, and identify missing capital adequacy and credit-quality evidence.',
    'XOM': 'Assess cash generation versus capital spending, shareholder distributions and balance-sheet resilience. Separate reported results from unobserved commodity-price assumptions.',
    'UNH': 'Assess reported earnings, operating cash generation and balance-sheet resilience. Identify absent underwriting, medical-cost and regulatory facts; do not infer insurance economics from cash flow alone.',
    'CAT': 'Assess cash generation, capital allocation and cyclicality. Identify missing financing-segment and end-market evidence that could change a long-horizon investment view.',
}


def _utc(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def _bundle(template, config, role, deadline):
    files = dict(template['files']); files['config/run.json'] = encoded(config)
    manifest = {'schema_version': 1, 'role': role, 'deadline': _utc(deadline),
                'files': {k: {'sha256': sha(v), 'bytes': len(v)} for k, v in sorted(files.items())}}
    result = {'manifest': manifest, 'files': files, 'sha256': sha(encoded(manifest))}
    validate_bundle(result)
    return result


def _hold(body, rates):
    # Identical conservative rule to Client.submit_intent; no Supercache write.
    bound = sum(len(item['content'].encode()) for item in body['input']) + 4096
    return (Decimal(bound) * Decimal(rates[0]) + Decimal(body['max_output_tokens']) * Decimal(rates[2])) / 1_000_000


def prepare(config_path, directory, *, launch_minutes=20, duration_minutes=30, clock=time.time):
    """Freeze one nonreplaceable protocol. Does not load a key or contact Sail."""
    if type(launch_minutes) is not int or not 0 <= launch_minutes <= 240 or type(duration_minutes) is not int or not 5 <= duration_minutes <= 30:
        raise ValueError('Invalid bounded fork window')
    config_path = Path(config_path).resolve(); directory = Path(directory).resolve()
    if directory.exists(): raise ValueError('Choose a fresh private experiment directory')
    main = json.loads(config_path.read_text())
    holds = {entry['id']: entry['reserved_usd'] for entry in main.get('branch_allocations', [])}
    if any(Decimal(str(holds.get(key, '0'))) != Decimal('2') for key in ARMS):
        raise ValueError('Main contract must declare both $2 branch allocations')
    deployment = config_path.parent / 'host'
    deployed = json.loads((deployment / 'deployment.json').read_text())
    if deployed['contract']['config_sha256'] != sha(encoded(main)):
        raise ValueError('Main deployment and supplied configuration differ')
    template = load_bundle(deployment / 'bundle')
    guest = json.loads(template['files']['config/run.json'])
    if not deployed['installed'] or guest['run_id'] != main['run_id']:
        raise ValueError('Install the frozen main deployment first')
    evidence_bytes = template['files']['data/sp500-evidence.json']
    if sha(evidence_bytes) != main['evidence_sha256']: raise ValueError('Evidence identity mismatch')
    evidence = json.loads(evidence_bytes); companies = {c['symbol']: c for c in evidence['companies']}
    if not set(SYMBOLS) <= set(companies): raise ValueError('Required cross-sector evidence is absent')
    # The builders/grader must match the frozen implementation that will run.
    root = Path(__file__).resolve().parents[1]
    for name in ('provider', 'research', 'accounting'):
        file = 'portfolio_runtime/' + name + '.py'
        if (root / file).read_bytes() != template['files'][file]:
            raise ValueError('Freeze matching request builders before preparing forks')
    start = main['started_epoch'] + launch_minutes * 60
    end = start + duration_minutes * 60
    if end > main['ends_epoch'] or clock() >= end:
        raise ValueError('Fork window exceeds the main window or has expired')
    overview = evidence['overview']
    if not isinstance(overview, list): raise ValueError('Expected per-company universe overview')
    focused = [row for row in overview if row.get('symbol') in SYMBOLS]
    if {row['symbol'] for row in focused} != set(SYMBOLS):
        raise ValueError('Focused context must cover exactly the selected companies')
    rates = list(PROFILES[PROFILE][2:]); arms = {}
    identity = uuid.uuid4().hex
    for allocation_id, variant in ARMS.items():
        prefix = ('Fork context experiment: ' + variant + '.\n' + SYSTEM +
                  '\nFROZEN UNIVERSE OVERVIEW:\n' + canonical(overview if variant == 'full_universe' else focused))
        tasks = []
        for symbol in SYMBOLS:
            question = canonical({'task': 'research', 'symbol': symbol, 'question': QUESTIONS[symbol],
                                  'evidence': companies[symbol], 'prior_work': []})
            body = body_for(PROFILE, prefix, question, max_output=OUTPUT_TOKENS,
                            cache_key='fork-' + sha(prefix.encode())[:40])
            if len(canonical(body).encode()) > 500000: raise ValueError('Fork request exceeds input envelope')
            tasks.append({'id': allocation_id + '-' + symbol, 'profile': PROFILE, 'body': body, 'cache': 'ordinary'})
        maximum = sum((_hold(t['body'], rates) for t in tasks), Decimal(0))
        if maximum > 2: raise ValueError('Frozen task upper bounds exceed the $2 branch allocation')
        config = {k: guest[k] for k in ('schema_version', 'account_created_at', 'evidence_sha256', 'key_fingerprint')}
        config.update(run_id=main['run_id'] + '-' + allocation_id, state_dir='/workspace/state',
                      evidence_path='/workspace/data/sp500-evidence.json', started_epoch=start, ends_epoch=end,
                      inference_budget_usd='2', injected_auth=True, drain_seconds=60, research_only=True,
                      fetch_filings=False, assigned_task_ids=[t['id'] for t in tasks], assigned_tasks=tasks)
        if deployed.get('voyage_id'):
            config['voyage_headers'] = {'X-Sail-Voyage-Id': deployed['voyage_id'], 'X-Sail-Voyage-Agent-Id': allocation_id}
        bundle = _bundle(template, config, 'research_branch', end)
        arms[allocation_id] = {'variant': variant, 'name': 'pa-fork-' + identity[:16] + '-' + variant.replace('_', '-'),
                               'manifest_sha256': bundle['sha256'], 'request_holds_usd': format(maximum, 'f'),
                               'requests': [{'task_id': t['id'], 'symbol': s, 'sha256': sha(canonical(t['body']).encode()),
                                             'reserved_usd': format(_hold(t['body'], rates), 'f')}
                                            for s, t in zip(SYMBOLS, tasks)], 'bundle': bundle}
    seed = _bundle(template, {'schema_version': 1, 'research_only': True, 'purpose': 'sterile-public-evidence-seed'}, 'research_seed', end)
    protocol = {'schema_version': 1, 'experiment': 'forked-context-comparison', 'identity': identity,
                'main_config_path': str(config_path), 'main_config_sha256': sha(encoded(main)),
                'main_deployment': str(deployment), 'main_run_id': main['run_id'],
                'main_manifest_sha256': template['sha256'], 'key_fingerprint': main['key_fingerprint'],
                'implementation': {name: sha(template['files']['portfolio_runtime/' + name + '.py'])
                                   for name in ('provider', 'research', 'accounting')},
                'started_epoch': start, 'ends_epoch': end, 'symbols': list(SYMBOLS), 'profile': PROFILE,
                'rates': rates, 'inference_reservations_usd': '4', 'cloud_envelope_usd': main['cloud_budget_usd'],
                'seed': {'name': 'pa-seed-' + identity[:20], 'manifest_sha256': seed['sha256']},
                'arms': {key: {k: v for k, v in value.items() if k != 'bundle'} for key, value in arms.items()},
                'limitations': ['Context selection changes information supplied, not only prompt length.',
                    'Five paired companies, one model and one draw per arm cannot establish a universal context-policy advantage.',
                    'Intent-to-observed-terminal latency includes provider waiting and polling.',
                    'Ordinary caching is automatic; no Supercache write or guaranteed cache savings.',
                    'Fork outputs are private research; they cannot place paper trades or publish portfolio state.',
                    'The external monitor must remain available for cold recovery and timely resource termination.']}
    directory.mkdir(parents=True, mode=0o700)
    save_bundle(directory / 'seed' / 'bundle', seed)
    for key, arm in arms.items(): save_bundle(directory / key / 'bundle', arm['bundle'])
    save(directory / 'protocol.json', protocol)
    save(directory / 'state.json', {'schema_version': 1, 'protocol_sha256': sha(encoded(protocol)),
         'phase': 'prepared', 'policy_key': str(uuid.uuid4()), 'policy_attempted': False, 'policy_id': None,
         'allocation_proof': None, 'arms': {}, 'resource_costs': {}})
    return {'protocol_sha256': sha(encoded(protocol)), 'starts_at': _utc(start), 'ends_at': _utc(end),
            'logical_requests': 10, 'inference_reserved_usd': '4', 'network_requests': 0}


class ForkExperiment:
    def __init__(self, directory, *, api, box_factory, clock=time.time, sleeper=time.sleep):
        self.directory = Path(directory).resolve(); self.api = api; self.box_factory = box_factory
        self.clock, self.sleep = clock, sleeper
    def read(self):
        p = json.loads((self.directory / 'protocol.json').read_text())
        state = json.loads((self.directory / 'state.json').read_text())
        if state['protocol_sha256'] != sha(encoded(p)): raise ValueError('Frozen fork protocol changed')
        for key, expected in [('seed', p['seed']), *p['arms'].items()]:
            if load_bundle(self.directory / key / 'bundle')['sha256'] != expected['manifest_sha256']:
                raise ValueError('Frozen fork bundle changed')
        return p, state
    def write(self, state): save(self.directory / 'state.json', state)
    def host(self, key, contract='http'):
        return SailHost(self.directory / key / 'host.json', api=self.api, box_factory=self.box_factory,
                        policy_contract=contract, allowed_hosts=('api.sailresearch.com',))
    def parent_allocation_proof(self, protocol):
        """Read-only query of parent allocations; never copies or mutates its DB."""
        directory = Path(protocol['main_deployment'])
        deployment = json.loads((directory / 'deployment.json').read_text())
        if (deployment['contract']['config_sha256'] != protocol['main_config_sha256'] or
                sha(encoded(json.loads(Path(protocol['main_config_path']).read_text()))) != protocol['main_config_sha256']):
            raise ValueError('Parent frozen configuration changed')
        parent = SailHost(directory / 'host.json', api=self.api, box_factory=self.box_factory)
        if parent._read()['manifest_sha256'] != protocol['main_manifest_sha256']: raise ValueError('Parent host differs')
        box = parent.attach()
        code = "import sqlite3,json,pathlib;d=sqlite3.connect('file:/workspace/state/requests.sqlite?mode=ro',uri=True);rows=d.execute(\"SELECT id,reserved,cost FROM allocations WHERE id IN ('fork-context','fork-fresh')\").fetchall();c=json.loads(d.execute(\"SELECT value FROM metadata WHERE key='contract'\").fetchone()[0]);d.close();pathlib.Path('/workspace/fork-allocation-proof.json').write_text(json.dumps({'run_id':c['run_id'],'allocations':rows,'key_fingerprint':c['key_fingerprint']},sort_keys=True))"
        done = box.exec(['python3', '-c', code], timeout=30).wait()
        if done.exit_code != 0: raise ValueError('Parent allocation proof unavailable')
        raw = box.fs.read('/workspace/fork-allocation-proof.json')
        if len(raw) > 16000: raise ValueError('Allocation proof exceeds envelope')
        proof = json.loads(raw)
        rows = proof.get('allocations', [])
        if (proof.get('run_id') != protocol['main_run_id'] or proof.get('key_fingerprint') != protocol['key_fingerprint'] or len(rows) != 2 or
                {r[0] for r in rows} != set(ARMS) or any(Decimal(r[1]) != 2 or r[2] is not None for r in rows)):
            raise ValueError('Both unchanged parent $2 allocations must already be reserved')
        return proof, deployment
    def provision(self):
        protocol, state = self.read()
        if not protocol['started_epoch'] <= self.clock() < protocol['ends_epoch'] - 60: raise ValueError('Outside branch admission window')
        proof, deployment = self.parent_allocation_proof(protocol)
        if state['allocation_proof'] is not None and state['allocation_proof'] != proof: raise ValueError('Parent allocation proof changed')
        state['allocation_proof'] = proof
        rates = self.api('GET', '/v1/sailboxes/spend').get('rates', {})
        names = ('vcpu_second_usd_nanos', 'memory_gib_second_usd_nanos', 'state_disk_gib_second_usd_nanos', 's_creation_usd_nanos')
        if any(type(rates.get(k)) is not int or rates[k] < 0 for k in names): raise ValueError('Missing current cloud rates')
        seconds = int(protocol['ends_epoch'] - self.clock()) + 120
        per_box = Decimal((rates[names[0]] + 2*rates[names[1]] + 8*rates[names[2]])*seconds + rates[names[3]]) / 1_000_000_000
        if per_box * 3 + Decimal(deployment['cloud_cost_bound_usd']) > Decimal(protocol['cloud_envelope_usd']): raise ValueError('Aggregate main plus fork cloud bound exceeds allowance')
        state['cloud_cost_bound_usd'] = format(per_box*3, 'f'); state['cloud_rates'] = rates; self.write(state)
        contract = deployment['policy_contract']; document = restricted_policy(deployment['inference_secret'])
        if not state['policy_id']:
            if state['policy_attempted']: raise RuntimeError('Fork policy creation unconfirmed; no replacement')
            state['policy_attempted'] = True; self.write(state)
            route = '/v1/http-policies' if contract == 'http' else '/v1/egress-policies'
            response = self.api('POST', route, {'name': 'pa-forks-' + protocol['identity'][:20],
                      'document': http_document(document) if contract == 'http' else document}, state['policy_key'])
            policy_id = response.get('policy_id', response.get('id'))
            if not isinstance(policy_id, str) or not policy_id.startswith(('hp_', 'ep_')): raise ValueError('Unconfirmed saved policy')
            state['policy_id'] = policy_id; self.write(state)
        seed = self.host('seed', contract); seed_bundle = load_bundle(self.directory / 'seed' / 'bundle')
        seed.create(deployment['contract']['app_id'], protocol['seed']['name'], seed_bundle)
        if not seed._read()['installed']:
            seed.bind_policy(state['policy_id'], document); seed.install(seed_bundle)
        seed.checkpoint_seed()
        for key, arm in protocol['arms'].items():
            child = self.host(key, contract); bundle = load_bundle(self.directory / key / 'bundle')
            child.fork_research(seed, bundle, arm['name'])
            if not child._read()['installed']:
                child.bind_policy(state['policy_id'], document); child.install(bundle)
            child.start()
            state['arms'].setdefault(key, {'started': True, 'receipt_saved': False}); self.write(state)
        state['phase'] = 'running'; self.write(state)
    def collect(self, key):
        protocol, state = self.read(); child = self.host(key)
        raw = child.attach().fs.read('/workspace/state/branch-receipt.json')
        if len(raw) > 6_000_000: raise ValueError('Branch receipt exceeds bounded output')
        receipt = json.loads(raw); bundle = load_bundle(self.directory / key / 'bundle')
        expected = json.loads(bundle['files']['config/run.json'])
        if receipt.get('research_only') is not True or receipt.get('run_id') != expected['run_id']:
            raise ValueError('Branch receipt identity mismatch')
        tasks = receipt.get('tasks')
        if not isinstance(tasks, list) or len(tasks) > 5 or len({t['task_id'] for t in tasks}) != len(tasks): raise ValueError('Duplicate or oversized branch receipt')
        expected_tasks = {t['id']: t for t in expected['assigned_tasks']}
        for task in tasks:
            if task.get('task_id') not in expected_tasks or task.get('profile') != PROFILE or task.get('status') not in TERMINAL | {'prepared', 'queued', 'in_progress'}:
                raise ValueError('Unexpected branch result')
        backup = self.directory / key / 'receipt-backup'
        if not backup.exists(): child.backup_state(backup)
        backup_receipt = json.loads((backup / 'receipt.json').read_text())
        if backup_receipt.get('manifest_sha256') != bundle['sha256'] or backup_receipt.get('sailbox_id') != child._read()['sailbox_id']:
            raise ValueError('Branch backup provenance mismatch')
        descriptor = backup_receipt['files'].get('requests.sqlite')
        database = backup / 'requests.sqlite'
        if not descriptor or sha(database.read_bytes()) != descriptor['sha256']:
            raise ValueError('Frozen branch request journal backup changed')
        db = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True); db.row_factory=sqlite3.Row
        try: rows = [dict(row) for row in db.execute('SELECT * FROM requests')]
        finally: db.close()
        observed = {row['task_id']: row for row in rows}
        if len(observed) != len(rows) or set(observed) != {t['task_id'] for t in tasks}:
            raise ValueError('Branch receipt and durable request journal differ')
        known = Decimal(0)
        for task in tasks:
            row = observed[task['task_id']]; wanted = expected_tasks[task['task_id']]
            if (row['body'] != canonical(wanted['body']) or row['profile'] != wanted['profile'] or row['cache'] != 'ordinary'
                    or any(row[field] != task[field] for field in ('profile','status','response','cost','created','updated'))):
                raise ValueError('Result is not bound to its exact frozen request')
            if row['cost'] is not None:
                value = Decimal(row['cost'])
                response = json.loads(row['response'])
                model = wanted['body']['model']
                if (not value.is_finite() or value < 0 or row['status'] not in TERMINAL
                        or response.get('id') != row['response_id'] or response.get('status') != row['status']
                        or response.get('model') not in {model,MODEL_ALIASES.get(model,model)}):
                    raise ValueError('Invalid terminal financial accounting identity')
                recomputed = estimate_cost(response.get('usage'),dict(zip(('input','cached','output'),protocol['rates'])),response.get('metadata'))
                if recomputed != value: raise ValueError('Frozen usage and cost disagree')
                known += value
        if Decimal(receipt['cost']['known_cost_usd']) != known:
            raise ValueError('Branch cost does not reconcile')
        path = self.directory / key / 'receipt.json'
        if path.exists() and path.read_bytes() != encoded(receipt): raise ValueError('Saved branch receipt changed')
        if not path.exists(): path.write_bytes(encoded(receipt)); path.chmod(0o600)
        arm_state = state['arms'].setdefault(key, {})
        arm_state.update(receipt_saved=True, receipt_sha256=sha(encoded(receipt)),
                         inference_budget_exceeded=known > Decimal('2'))
        self.write(state)
        return receipt
    def cleanup(self):
        """Terminate only experiment resource IDs; preserve confirmed/unknown costs."""
        protocol, state = self.read(); errors = []; resource_costs = dict(state['resource_costs'])
        for key in (*ARMS, 'seed'):
            path = self.directory / key / 'host.json'
            if not path.exists(): continue
            try:
                saved = json.loads(path.read_text()); sid = saved.get('sailbox_id')
                if not sid:
                    # Creation may have succeeded before its ID reached the controller.
                    query = urlencode({'app': saved['create_body']['app_id'], 'search': saved['create_body']['name'], 'limit':100})
                    page = self.api('GET', '/v1/sailboxes?' + query)
                    matches = [r for r in page.get('data', []) if r.get('name') == saved['create_body']['name'] and r.get('app_id') == saved['create_body']['app_id']]
                    if len(matches) != 1: errors.append(key + ':creation_unconfirmed'); continue
                    sid = matches[0]['sailbox_id']
                if key != 'seed' and saved.get('installed'):
                    child = self.host(key)
                    if sid == saved.get('sailbox_id'):
                        try: child.stop(sleep=False)
                        except Exception: pass
                        try: self.collect(key)
                        except Exception: pass
                        backup = self.directory / key / 'final-backup'
                        if not backup.exists():
                            try: child.backup_state(backup)
                            except Exception: pass
                self.api('POST', '/v1/sailboxes/' + sid + '/terminate', {})
                cost = self.api('GET', '/v1/sailboxes/spend?' + urlencode({'sailbox_id': sid}))
                fields = ('estimated_total_cost_usd_nanos', 'finalized_cost_usd_nanos', 'estimated_active_cost_usd_nanos')
                resource_costs[key] = {k: cost[k] for k in fields} if all(type(cost.get(k)) is int and cost[k] >= 0 for k in fields) else None
            except Exception: errors.append(key + ':cleanup_unconfirmed')
        # collect() may have durably saved receipts while resources were stopping.
        _, state = self.read(); state['resource_costs'] = resource_costs
        state['phase'] = 'finished' if not errors else 'needs_attention'; state['cleanup_errors'] = errors; self.write(state)
        result = summarize(self.directory); save(self.directory / 'report.json', result); return result
    def run(self):
        with private_lock(self.directory):
            protocol, state = self.read()
            if state['phase'] == 'finished': return summarize(self.directory)
            while self.clock() < protocol['started_epoch']:
                self.sleep(min(30, protocol['started_epoch'] - self.clock()))
            try:
                if state['phase'] == 'prepared': self.provision()
                while self.clock() < protocol['ends_epoch']:
                    _, state = self.read()
                    for key in ARMS:
                        if state['arms'].get(key, {}).get('receipt_saved'): continue
                        try: self.collect(key)
                        except (ValueError,TypeError,KeyError):raise
                        except Exception:
                            # Same managed execution/accepted request identities only.
                            self.host(key).start()
                    _, state = self.read()
                    if all(state['arms'].get(k, {}).get('receipt_saved') for k in ARMS): break
                    self.sleep(min(15, protocol['ends_epoch'] - self.clock()))
            finally: result = self.cleanup()
            return result


def summarize(directory):
    directory = Path(directory); protocol = json.loads((directory / 'protocol.json').read_text())
    state = json.loads((directory / 'state.json').read_text())
    if state['protocol_sha256'] != sha(encoded(protocol)): raise ValueError('Fork protocol changed')
    root = Path(__file__).resolve().parents[1]
    for name, expected in protocol['implementation'].items():
        if sha((root / 'portfolio_runtime' / (name + '.py')).read_bytes()) != expected:
            raise ValueError('Frozen fork grader or accounting implementation changed')
    evidence = json.loads(load_bundle(directory/'seed'/'bundle')['files']['data/sp500-evidence.json'])
    companies = {c['symbol']: c for c in evidence['companies']}; rows = []
    for key, arm in protocol['arms'].items():
        path = directory / key / 'receipt.json'; receipt = json.loads(path.read_text()) if path.exists() else None
        if receipt is not None and sha(encoded(receipt)) != state['arms'].get(key, {}).get('receipt_sha256'):
            raise ValueError('Saved branch receipt digest changed')
        tasks = {t['task_id']: t for t in receipt['tasks']} if receipt else {}
        for spec in arm['requests']:
            item = tasks.get(spec['task_id']); response = json.loads(item['response']) if item and item['response'] else {}
            usage = response.get('usage') if isinstance(response, dict) else None
            usage = usage if isinstance(usage, dict) else {}; details = usage.get('input_tokens_details')
            details = details if isinstance(details, dict) else {}
            grade = grade_result(answer_json(response), companies)
            counter = lambda x: x if type(x) is int and x >= 0 else None
            missing_cost = '0' if receipt is not None and item is None else None
            rows.append({'arm': key, 'variant': arm['variant'], 'symbol': spec['symbol'],
                 'status': item['status'] if item else 'not_admitted' if receipt is not None else 'unobserved',
                 'source_checks_passed': grade['source_check_passed'] if item and item['status'] == 'completed' else False,
                 'claims_checked': grade['claims_checked'], 'known_cost_usd': item['cost'] if item else missing_cost,
                 'input_tokens': counter(usage.get('input_tokens')), 'output_tokens': counter(usage.get('output_tokens')),
                 'cached_tokens': counter(details.get('cached_tokens')),
                 'intent_to_observed_terminal_seconds': max(0,item['updated']-item['created']) if item and item['status'] in TERMINAL else None})
    return {'schema_version':1,'experiment':protocol['experiment'],'protocol_sha256':state['protocol_sha256'],
            'phase':state['phase'],'logical_requests':10,'completed':sum(r['status']=='completed' for r in rows),
            'known_inference_cost_usd':format(sum((Decimal(r['known_cost_usd']) for r in rows if r['known_cost_usd'] is not None),Decimal(0)),'f'),
            'unknown_request_costs':sum(r['known_cost_usd'] is None for r in rows),'parent_reservations_retained_usd':'4',
            'all_research_completed':all(r['status']=='completed' for r in rows),
            'inference_budget_exceeded':any(a.get('inference_budget_exceeded',False) for a in state['arms'].values()),
            'rows':rows,'resource_costs':state['resource_costs'],'limitations':protocol['limitations']}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command',choices=['prepare','run','status','stop'])
    parser.add_argument('--directory',required=True);parser.add_argument('--config')
    parser.add_argument('--launch-minutes',type=int,default=20);parser.add_argument('--duration-minutes',type=int,default=30)
    args=parser.parse_args()
    if args.command=='prepare':
        if not args.config: parser.error('prepare requires --config')
        result=prepare(args.config,args.directory,launch_minutes=args.launch_minutes,duration_minutes=args.duration_minutes)
    elif args.command=='status':result=summarize(args.directory)
    else:
        key,dependencies=clients();experiment=ForkExperiment(args.directory,api=dependencies['api'],box_factory=dependencies['box_factory'])
        protocol,_=experiment.read()
        if hashlib.sha256(key.encode()).hexdigest()!=protocol['key_fingerprint']:raise ValueError('Frozen credential identity changed')
        if args.command=='run':result=experiment.run()
        else:
            with private_lock(args.directory):result=experiment.cleanup()
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
