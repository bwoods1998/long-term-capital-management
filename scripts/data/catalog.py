#!/usr/bin/env python3
"""Private, advisory research catalog. No collector, trading, settings or budget mutations.

``plan --assets-receipt GET.json --out catalog.json`` retains every optionable asset;
without a verified coverage receipt none is advertised as ready. ``audit`` can run
inside an already sealed Gym (never a gate): hashes Train/Validation files and reads
only contract-expiration columns, never quotes or fitted values. ``discover`` is an
explicit House-only GET through the gateway; no credentials enter the catalog.

Readiness means the declared historical quote slice exists, not that it is profitable,
directly fill-calibrated, tradable by this account, or approved for paper/live orders.
All receipts are operator-owned local inputs; their hashes bind identity, not authorship.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Sequence
import urllib.error
import urllib.parse
import urllib.request

WINDOWS = {'train': ['2022-01-03', '2024-12-31'], 'validation': ['2025-01-02', '2025-12-31']}
HORIZONS = ((0, 7), (8, 14), (15, 45), (46, 60))
ASSETS_PATH = 'v2/assets?status=active&attributes=options_enabled'
SIP_SOURCE = 'alpaca SIP completed-minute OHLCV v1'
ROOT = re.compile(r'[A-Z]{1,6}\Z')
SHA = re.compile(r'[a-f0-9]{64}\Z')
# https://docs.alpaca.markets/us/docs/index-options (Broker API catalog), not a
# claim that this Trading API account/contract is enabled. AM rules
# and DJXW are deliberately unavailable in the current Gym/live engine.
INDICES = {'SPX': ('SPX', 'AM'), 'SPXW': ('SPX', 'PM'), 'XSP': ('XSP', 'PM'),
           'VIX': ('VIX', 'AM'), 'VIXW': ('VIX', 'AM'), 'DJX': ('DJX', 'AM'), 'DJXW': ('DJX', 'PM')}


class CatalogError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def identity(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(part)
    return value.hexdigest()


def date(value: Any) -> dt.date:
    if isinstance(value, dt.datetime):
        raise CatalogError('a date must not be a timestamp')
    parsed = value if isinstance(value, dt.date) else dt.date.fromisoformat(value)
    if not isinstance(value, dt.date) and parsed.isoformat() != value:
        raise CatalogError('a date must be canonical')
    return parsed


def timestamp(value: Any) -> str:
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else None
    if parsed is None or parsed.tzinfo is None:
        raise CatalogError('an aware observation timestamp is required')
    return parsed.astimezone(dt.timezone.utc).isoformat()


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def private_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(canonical(value) + b'\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def discover(gateway: str, token: str, *, opener: Any = None, at: str | None = None) -> dict:
    """One allowlisted GET; explicit call only. Never follow a token-bearing redirect."""
    parsed = urllib.parse.urlsplit(gateway)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or not token):
        raise CatalogError('invalid gateway configuration')
    request = urllib.request.Request(gateway.rstrip('/') + '/v1/alpaca/' + ASSETS_PATH, method='GET',
                                     headers={'Authorization': 'Bearer ' + token})
    try:
        with (opener or urllib.request.build_opener(NoRedirect())).open(request, timeout=60) as response:
            if response.status != 200:
                raise CatalogError('asset GET did not return HTTP 200')
            raw = response.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024:
                raise CatalogError('asset response exceeds the size bound')
            body = json.loads(raw)
    except urllib.error.HTTPError as error:
        raise CatalogError(f'asset GET returned HTTP {error.code}') from None
    result = {'at': at or now(), 'responses': [{'path': ASSETS_PATH, 'status': 200, 'body': body}]}
    assets(result)  # validate before saving a purported discovery receipt
    return result


def assets(receipt: Mapping[str, Any]) -> dict[str, dict]:
    """Keep the complete catalog, including currently nontradable candidates."""
    timestamp(receipt.get('at'))
    responses = receipt.get('responses')
    if not isinstance(responses, list) or len(responses) != 1:
        raise CatalogError('one complete asset GET receipt is required')
    response = responses[0]
    if (not isinstance(response, dict) or response.get('status') != 200 or response.get('path') != ASSETS_PATH
            or not isinstance(response.get('body'), list) or not response['body']):
        raise CatalogError('invalid asset GET receipt')
    found = {}
    for row in response['body']:
        if not isinstance(row, dict):
            raise CatalogError('an asset is not an object')
        symbol, flags = row.get('symbol'), row.get('attributes')
        if (not isinstance(symbol, str) or not re.fullmatch(r'[A-Z0-9][A-Z0-9./-]{0,31}', symbol)
                or not isinstance(flags, list) or not all(isinstance(f, str) for f in flags)
                or type(row.get('tradable')) is not bool or row.get('class') != 'us_equity'
                or row.get('status') not in ('active', 'inactive')
                or not {'has_options', 'options_enabled'}.intersection(flags)):
            raise CatalogError('invalid or non-optionable asset in filtered receipt')
        item = {'symbol': symbol, 'status': row['status'], 'tradable': row['tradable'],
                'class': row['class'], 'exchange': str(row.get('exchange') or ''),
                'optionable': True, 'late_close': 'options_late_close' in flags}
        if symbol in found and found[symbol] != item:
            raise CatalogError('conflicting duplicate asset')
        found[symbol] = item
    return found


def image_identity(entry: Mapping[str, Any], checkpoint: str) -> dict:
    if (not isinstance(entry, Mapping) or entry.get('sealed') != {'no_network': True}
            or entry.get('gate_mark') is not False or set(entry.get('windows') or []) != {'train', 'validation'}
            or not isinstance(entry.get('checkpoints'), list) or checkpoint not in entry['checkpoints']
            or not isinstance(entry.get('roots'), list) or not entry['roots']
            or not all(isinstance(r,str) and ROOT.fullmatch(r) for r in entry['roots'])
            or not isinstance(checkpoint, str) or not checkpoint or not entry.get('version')):
        raise CatalogError('an exact sealed Gym checkpoint receipt is required')
    return {'checkpoint': checkpoint, 'image_sha256': identity(entry), 'version': entry['version']}


def sessions(calendar: Mapping[str, Any], windows: Mapping[str, Sequence[str]]) -> dict[str, list[list]]:
    years, exceptions = calendar.get('years'), calendar.get('exceptions')
    if (not isinstance(years, list) or not years or not all(type(y) is int for y in years)
            or not isinstance(exceptions, dict) or set(windows) != {'train', 'validation'}):
        raise CatalogError('canonical calendar and Train/Validation windows are required')
    for key, hours in exceptions.items():
        date(key)
        if hours is not None and (not isinstance(hours, list) or len(hours) != 2
                or not all(type(x) is int for x in hours) or not 0 <= hours[0] < hours[1] <= 1440):
            raise CatalogError('invalid calendar session')
    result, seen = {}, set()
    for window, bounds in windows.items():
        start, end = map(date, bounds)
        permitted_start, permitted_end = map(date,WINDOWS[window])
        if not permitted_start <= start <= end <= permitted_end:
            raise CatalogError('requested window is outside the fixed research split')
        if not set(range(start.year, end.year + 1)) <= set(years):
            raise CatalogError('calendar does not cover the requested window')
        rows, day = [], start
        while day <= end:
            hours = exceptions.get(day.isoformat(), [570, 960]) if day.weekday() < 5 else None
            if hours is not None:
                if day in seen:
                    raise CatalogError('overlapping historical windows')
                rows.append([day.isoformat(), *hours])
                seen.add(day)
            day += dt.timedelta(days=1)
        if not rows:
            raise CatalogError('historical window has no sessions')
        result[window] = rows
    return result


def _source_horizon(source: str) -> int:
    if not source.startswith('thetadata option_history_quote 1m'):
        return -1
    match = re.search(r'\bmax_dte=(\d+)\b', source)
    limit = int(match[1]) if match else -1
    back = re.search(r'\+ back months to (\d+) DTE by expiry', source)
    return max(limit, int(back[1])) if back else limit


def audit_store(store: Path, calendar: Mapping[str, Any], image: Mapping[str, Any], checkpoint: str,
                *, windows: Mapping[str, Sequence[str]] = WINDOWS) -> dict:
    """Local sealed-Gym audit. No holdout, quote values, strategies, model parameters or network.

    A horizon covers every listed expiry in its range on every expected root/session;
    days with no listed expiry are counted explicitly, not invented as tradable days.
    The v1 collector enumerates expiries only to45DTE: higher ranges stay unverified.
    Missing pre-listing history remains a gap; no silent shorter-window substitution.
    """
    source = image_identity(image, checkpoint)
    store = Path(store).resolve()
    if (store / 'GATE').exists():
        raise CatalogError('the gate must not be read by the research catalog')
    import pyarrow.parquet as pq  # only the optional audit needs the Gym dependency

    expected = sessions(calendar, windows)
    expected_rows = sorted(r for rows in expected.values() for r in rows)
    metadata = ('VERSION','manifest.parquet','calendar.parquet','expiries.parquet')
    if any((store/name).is_symlink() or not (store/name).resolve().is_relative_to(store) for name in metadata):
        raise CatalogError('store control metadata must remain inside the sealed store')
    control_hashes = {name: digest(store/name) for name in metadata}
    manifest = pq.read_table(store / 'manifest.parquet').to_pylist()
    # Reject before opening any per-day file, including a mislabeled gate without its mark.
    if any(r.get('window') not in ('train', 'validation') for r in manifest):
        raise CatalogError('manifest includes data outside Train/Validation')
    actual_rows = sorted([date(r['date']).isoformat(), r['open_min'], r['close_min']]
                         for r in pq.read_table(store / 'calendar.parquet').to_pylist())
    if actual_rows != expected_rows or (store / 'VERSION').read_text().strip() != 'store-v1':
        raise CatalogError('store calendar/version differs from the canonical receipt')
    day_window = {r[0]: name for name, rows in expected.items() for r in rows}
    records = {}
    for row in manifest:
        root, kind, day = row['root'], row['kind'], date(row['date']).isoformat()
        key = (root, day, kind)
        if (not isinstance(root, str) or not ROOT.fullmatch(root) or kind not in ('nbbo','underlying','oi','trade_quote')
                or day_window.get(day) != row['window'] or key in records
                or (kind == 'trade_quote' and row['window'] != 'train')):
            raise CatalogError('invalid/duplicate manifest identity')
        records[key] = row
    if not {r for r, _, _ in records} <= set(image['roots']):
        raise CatalogError('manifest has a root outside the image receipt')
    listed: dict[tuple[str, str], set[dt.date]] = {}
    for row in pq.read_table(store / 'expiries.parquet').to_pylist():
        root, day, expiration = row['root'], date(row['date']), date(row['expiration'])
        if (not isinstance(root, str) or not ROOT.fullmatch(root) or day.isoformat() not in day_window
                or not 0 <= (expiration - day).days <= 45):
            raise CatalogError('invalid expiry metadata')
        listed.setdefault((root, day.isoformat()), set()).add(expiration)
    facts = {}
    for root in sorted({r for r, _, _ in records}):
        root_windows = {}
        for window, days in expected.items():
            totals = {'expected': len(days), 'nbbo_verified': 0, 'underlying_verified': 0, 'oi_verified': 0,
                      'horizons': {f'{lo}:{hi}': {'covered': 0, 'with_contracts': 0, 'scope_verified': 0,
                                                'listing_days': 0} for lo, hi in HORIZONS}}
            for day, *_ in days:
                good, expirations = {}, set()
                for kind in ('nbbo', 'underlying', 'oi'):
                    row = records.get((root, day, kind))
                    path = store / kind / root / (day + '.parquet')
                    before = path.stat() if path.is_file() else None
                    valid = bool(row and path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(store)
                                 and type(row.get('rows')) is int and row['rows'] > 0
                                 and type(row.get('bytes')) is int and path.stat().st_size == row['bytes']
                                 and isinstance(row.get('sha256'), str) and SHA.fullmatch(row['sha256'])
                                 and digest(path) == row['sha256'])
                    if valid and kind == 'underlying' and root not in ('XSP','SPXW'):
                        valid = row.get('source') == SIP_SOURCE
                    if valid:
                        file = pq.ParquetFile(path)
                        valid = file.metadata.num_rows == row['rows']
                        if valid and kind == 'nbbo':
                            for batch in file.iter_batches(columns=['expiration'], batch_size=65536):
                                expirations.update(date(e) for e in batch.column(0).to_pylist())
                        after = path.stat()
                        valid = valid and (before.st_ino,before.st_mtime_ns,before.st_size) == \
                            (after.st_ino,after.st_mtime_ns,after.st_size)
                    good[kind] = valid
                    totals[kind + '_verified'] += int(valid)
                for lo, hi in HORIZONS:
                    counts = totals['horizons'][f'{lo}:{hi}']
                    needed = {e for e in listed.get((root, day), ()) if lo <= (e-date(day)).days <= hi}
                    counts['with_contracts'] += int(bool(needed))
                    limit = _source_horizon(str((records.get((root,day,'nbbo')) or {}).get('source','')))
                    counts['scope_verified'] += int(hi <= min(limit,45))
                    counts['listing_days'] += int((root,day) in listed)
                    counts['covered'] += int(good['nbbo'] and good['underlying'] and (root,day) in listed
                                             and hi <= min(limit,45) and needed <= expirations)
            root_windows[window] = totals
        facts[root] = root_windows
    if control_hashes != {name: digest(store/name) for name in metadata}:
        raise CatalogError('store metadata changed during audit')
    result = {'schema': 1, 'kind': 'research-coverage', 'at': now(), 'identity': source,
              'windows': dict(windows), 'expected_sessions': {k: len(v) for k,v in expected.items()},
              'calendar_sha256': identity(calendar), 'files_sha256': control_hashes,
              'full_content_hashes_checked': True, 'roots': facts,
              'audit_code_sha256': digest(Path(__file__)), 'quote_values_read': False,
              'fill_calibration_scope': 'not_assessed; availability does not prove calibrated fill behavior'}
    result['receipt_sha256'] = identity(result)
    return result


def coverage_roots(receipt: Mapping[str, Any] | None, image: Mapping[str, Any] | None, checkpoint: str | None,
                   windows: Mapping[str, Sequence[str]]) -> dict:
    if receipt is None:
        return {}
    if image is None or checkpoint is None:
        raise CatalogError('coverage requires the exact selected Gym receipt/checkpoint')
    body = {k:v for k,v in receipt.items() if k != 'receipt_sha256'}
    if (receipt.get('schema') != 1 or receipt.get('kind') != 'research-coverage'
            or receipt.get('full_content_hashes_checked') is not True or receipt.get('quote_values_read') is not False
            or receipt.get('windows') != dict(windows) or receipt.get('identity') != image_identity(image, checkpoint)
            or receipt.get('receipt_sha256') != identity(body) or not isinstance(receipt.get('roots'), dict)
            or receipt.get('audit_code_sha256') != digest(Path(__file__))
            or not isinstance(receipt.get('calendar_sha256'), str) or not SHA.fullmatch(receipt['calendar_sha256'])
            or not isinstance(receipt.get('files_sha256'), dict)
            or set(receipt['files_sha256']) != {'VERSION','manifest.parquet','calendar.parquet','expiries.parquet'}
            or not all(isinstance(v,str) and SHA.fullmatch(v) for v in receipt['files_sha256'].values())):
        raise CatalogError('coverage receipt does not match selected image/windows')
    if not set(receipt['roots']) <= set(image['roots']):
        raise CatalogError('coverage root is outside selected image')
    return receipt['roots']


def plan(asset_receipt: Mapping[str, Any], *, coverage: Mapping[str, Any] | None = None,
         image: Mapping[str, Any] | None = None, checkpoint: str | None = None,
         priority_roots: Sequence[str] = (), windows: Mapping[str, Sequence[str]] = WINDOWS) -> dict:
    """No hard universe ceiling. Catalog and backlog are complete; no work is dispatched."""
    observed = assets(asset_receipt)
    facts = coverage_roots(coverage, image, checkpoint, windows)
    candidates, backlog = [], []
    priority = {r:i for i,r in enumerate(dict.fromkeys(priority_roots))}
    for root in sorted(set(observed) | set(INDICES)):
        asset = observed.get(root)
        is_index = root in INDICES
        venue_rules = root in ('XSP','SPXW') if is_index else bool(ROOT.fullmatch(root))
        eligible = (asset is None and is_index) or bool(asset and asset['tradable'] and asset['status'] == 'active')
        blockers = []
        if not eligible:
            blockers.append('asset_not_currently_tradable')
        if not venue_rules:
            blockers.append('index_rules_unimplemented' if is_index else 'symbol_mapping_unverified')
        record = facts.get(root, {})
        ready, horizon_status = [], []
        progress = []
        for lo, hi in HORIZONS:
            missing_evidence = []
            for window in windows:
                row = record.get(window, {})
                expected = (coverage or {}).get('expected_sessions', {}).get(window)
                counts = row.get('horizons', {}).get(f'{lo}:{hi}', {})
                numbers = [expected, row.get('expected'), row.get('nbbo_verified'), row.get('underlying_verified'),
                           counts.get('covered'), counts.get('with_contracts'), counts.get('scope_verified'),
                           counts.get('listing_days')]
                valid = all(type(n) is int and n >= 0 for n in numbers) and expected > 0
                if not valid or row['expected'] != expected or any(n > expected for n in numbers[2:]):
                    missing_evidence.append(window + ':coverage_unverified')
                else:
                    for key, why in (('nbbo_verified','NBBO_sessions_missing'),
                                     ('underlying_verified','underlying_sessions_or_source_missing')):
                        if row[key] != expected:
                            missing_evidence.append(window + ':' + why)
                    for key, why in (('scope_verified','collector_horizon_unverified'),
                                     ('listing_days','expiry_listings_missing'),
                                     ('covered','quoted_expiries_incomplete')):
                        if counts[key] != expected:
                            missing_evidence.append(window + ':' + why)
                    if not counts['with_contracts']:
                        missing_evidence.append(window + ':no_observed_contracts_in_horizon')
                if lo == 0 and valid:
                    progress.append(min(row['nbbo_verified'],row['underlying_verified'],counts['covered']) / expected)
            if not missing_evidence:
                ready.append([lo,hi])
            horizon_status.append({'dte':[lo,hi],'ready':not missing_evidence,'missing':missing_evidence})
        missing = [list(h) for h in HORIZONS if list(h) not in ready]
        if not ready:
            blockers.append('historical_coverage_unverified' if not record else 'historical_coverage_incomplete')
        candidate = {'root': root, 'underlier': INDICES[root][0] if is_index else root, 'asset': asset,
                     'venue': {'kind': 'index' if is_index else 'equity',
                               'settlement': INDICES[root][1] if is_index else 'physical',
                               'rules_implemented': venue_rules, 'account_contract_verified': False},
                     'data': {'verified_horizons': ready, 'missing_horizons': missing, 'windows': record,
                              'horizons': horizon_status,
                              'fill_calibration': 'not_assessed'},
                     'research_ready': bool(ready and not blockers), 'blockers': blockers,
                     'paper_ready': False, 'live_ready': False}
        candidates.append(candidate)
        if missing:
            backlog.append({'root': root, 'horizons': missing, 'blockers': blockers,
                            'completed_fraction': min(progress) if progress else 0.0,
                            'priority_explicit': priority.get(root), 'asset_eligible': eligible})
    backlog.sort(key=lambda r: (not r['asset_eligible'], r['priority_explicit'] is None,
                               r['priority_explicit'] if r['priority_explicit'] is not None else 0,
                               -r['completed_fraction'], r['root']))
    for rank, row in enumerate(backlog,1):
        row['rank'] = rank
    return {'schema': 1, 'kind': 'research-catalog', 'private': True, 'at': now(),
            'assets_observed_at': timestamp(asset_receipt['at']), 'asset_receipt_sha256': identity(asset_receipt),
            'coverage_receipt_sha256': (coverage or {}).get('receipt_sha256'),
            'image': (coverage or {}).get('identity'), 'windows': dict(windows),
            'engine_dte_limit': 60, 'longer_horizons': 'pending_engine_and_data_support',
            'readiness_basis': 'NBBO and underlying availability; optional OI/events/features require program-level checks',
            'summary': {'assets': len(observed), 'observed_tradable_assets': sum(r['tradable'] for r in observed.values()),
                        'candidates': len(candidates), 'research_ready': sum(r['research_ready'] for r in candidates),
                        'backlog_roots': len(backlog)}, 'candidates': candidates, 'backlog': backlog,
            'priority_basis': 'asset availability, explicit operator priority, verified coverage fraction, symbol',
            'actions': {'data_jobs_started': 0, 'settings_changed': False, 'trading_authorized': False}}


def prompt_context(catalog: Mapping[str, Any], *, backlog_limit: int = 20) -> dict:
    """Complete ready universe; bounded backlog preview with visible total/omission count."""
    if type(backlog_limit) is not int or not 0 <= backlog_limit <= 100:
        raise CatalogError('backlog preview limit must be 0..100')
    ready = {}
    for row in catalog['candidates']:
        if row['research_ready']:
            merged = []
            for lo, hi in row['data']['verified_horizons']:
                if merged and lo == merged[-1][1] + 1:
                    merged[-1][1] = hi
                else:
                    merged.append([lo,hi])
            ready[row['root']] = merged
    backlog = catalog['backlog']
    return {'schema': 1, 'catalog_sha256': identity(catalog), 'checkpoint': (catalog.get('image') or {}).get('checkpoint'),
            'ready_roots': ready, 'backlog_total': len(backlog), 'backlog_omitted': max(0,len(backlog)-backlog_limit),
            'backlog_preview': [{'root':r['root'],'horizons':r['horizons'],'blockers':r['blockers']}
                                for r in backlog[:backlog_limit]],
            'note': 'Use only ready root/horizon slices. Backlog is a data request, not execution permission. '
                    'No paper/live readiness or calibrated-fill claim is implied.'}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    discover_cmd = commands.add_parser('discover')
    discover_cmd.add_argument('--gateway', required=True)
    audit_cmd = commands.add_parser('audit')
    audit_cmd.add_argument('--store', type=Path, required=True)
    audit_cmd.add_argument('--calendar', type=Path, required=True)
    plan_cmd = commands.add_parser('plan')
    plan_cmd.add_argument('--assets-receipt', type=Path, required=True)
    plan_cmd.add_argument('--coverage', type=Path)
    plan_cmd.add_argument('--priority-roots', default='')
    plan_cmd.add_argument('--prompt-out', type=Path)
    for command in (audit_cmd,plan_cmd):
        command.add_argument('--image-entry', type=Path, required=command is audit_cmd)
        command.add_argument('--checkpoint', required=command is audit_cmd)
    for command in (discover_cmd,audit_cmd,plan_cmd):
        command.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    read = lambda p: json.loads(p.read_text()) if p else None
    try:
        if args.command == 'discover':
            result = discover(args.gateway, os.environ.get('GATEWAY_TOKEN',''))
        elif args.command == 'audit':
            result = audit_store(args.store,read(args.calendar),read(args.image_entry),args.checkpoint)
        else:
            result = plan(read(args.assets_receipt),coverage=read(args.coverage),image=read(args.image_entry),
                          checkpoint=args.checkpoint,priority_roots=args.priority_roots.split(',') if args.priority_roots else ())
        private_write(args.out,result)
        if args.command == 'plan' and args.prompt_out:
            private_write(args.prompt_out,prompt_context(result))
        print(json.dumps({'schema':1,'command':args.command,'written':True,
                          'summary':result.get('summary'),'sha256':identity(result)}))
        return 0
    except Exception as error:  # no response/file contents or credentials in errors
        print(json.dumps({'schema':1,'command':args.command,'written':False,'error':type(error).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
