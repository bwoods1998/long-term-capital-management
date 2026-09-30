#!/usr/bin/env python3
"""House-only SIP historical bars relay; the data box receives data, never a token.

Alpaca stamps each bar at its start. We place finalized history at start+1 minute;
that is a bar-completion grid, not a publication/as-of receipt. Historical volume
remains unavailable to strategies. Requests use raw prices; index underlyings keep
the ThetaData/parity path. Nightly is strict; only the historical gap queue may
advance past incomplete roots, without claiming completion.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

try:
    import storelib as sl
except ImportError:
    from . import storelib as sl

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
NY = ZoneInfo('America/New_York')
SOURCE = sl.SIP_SOURCE
INDEX_ROOTS = frozenset({'XSP', 'SPXW'})


class SIPError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class GatewayBars:
    """Only the gateway's allowlisted, read-only stock-bars endpoint."""

    def __init__(self, base: str, token: str, *, opener: Any = None):
        parsed = urllib.parse.urlsplit(base)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise SIPError('invalid gateway base URL')
        if not token:
            raise SIPError('the House gateway token is missing')
        self.url = base.rstrip('/') + '/v1/alpaca/v2/stocks/bars'
        self.token = token
        self.opener = opener or urllib.request.build_opener(NoRedirect())

    def fetch(self, symbols: list[str], day: dt.date, hours: tuple[int, int]) -> dict[str, list[dict]]:
        start = dt.datetime.combine(day, dt.time(), NY) + dt.timedelta(minutes=hours[0])
        end = dt.datetime.combine(day, dt.time(), NY) + dt.timedelta(minutes=hours[1])
        params = {'symbols': ','.join(symbols), 'timeframe': '1Min', 'feed': 'sip', 'adjustment': 'raw',
                  'asof': day.isoformat(), 'start': start.astimezone(dt.timezone.utc).isoformat(),
                  'end': end.astimezone(dt.timezone.utc).isoformat(), 'limit': '10000', 'sort': 'asc'}
        rows: dict[str, list[dict]] = {symbol: [] for symbol in symbols}
        seen_tokens = set()
        for _ in range(100):
            request = urllib.request.Request(self.url + '?' + urllib.parse.urlencode(params), method='GET',
                                             headers={'Authorization': 'Bearer ' + self.token,
                                                      'User-Agent': 'ltcm-sip-relay/1'})
            try:
                with self.opener.open(request, timeout=60) as response:
                    page = json.load(response)
            except urllib.error.HTTPError as error:
                raise SIPError(f'gateway stock bars returned HTTP {error.code}') from None
            if not isinstance(page, dict) or not isinstance(page.get('bars'), dict):
                raise SIPError('gateway stock bars did not return a bars map')
            for symbol, items in page['bars'].items():
                if symbol not in rows or not isinstance(items, list):
                    raise SIPError('gateway stock bars returned an unexpected symbol or shape')
                rows[symbol].extend(items)
            token = page.get('next_page_token')
            if not token:
                return rows
            if not isinstance(token, str) or token in seen_tokens:
                raise SIPError('stock bars pagination repeated a token')
            seen_tokens.add(token)
            params['page_token'] = token
        raise SIPError('stock bars exceeded the pagination limit')


def completed_rows(bars: list[dict], day: dt.date, hours: tuple[int, int]) -> list[dict]:
    """Convert start-stamped bars to the engine's completed-minute grid."""
    rows = {}
    for bar in bars:
        if not isinstance(bar, dict):
            raise SIPError('a stock bar is not an object')
        try:
            stamp = dt.datetime.fromisoformat(str(bar['t']).replace('Z', '+00:00'))
            if stamp.tzinfo is None or stamp.second or stamp.microsecond:
                raise ValueError('bar timestamp is not an aware minute boundary')
            local = stamp.astimezone(NY)
            minute = local.hour * 60 + local.minute
            if local.date() != day or not hours[0] <= minute < hours[1]:
                continue
            vals = {name: float(bar[key]) for name, key in [('open', 'o'), ('high', 'h'), ('low', 'l'),
                                                          ('close', 'c'), ('volume', 'v')]}
            if not all(math.isfinite(v) for v in vals.values()):
                raise ValueError('nonfinite OHLCV')
            if min(vals[k] for k in ('open', 'high', 'low', 'close')) <= 0 or vals['volume'] < 0:
                raise ValueError('invalid OHLCV sign')
            if not vals['low'] <= min(vals['open'], vals['close']) <= max(vals['open'], vals['close']) <= vals['high']:
                raise ValueError('inconsistent OHLC range')
        except (KeyError, ValueError, TypeError) as error:
            raise SIPError('invalid SIP bar: ' + str(error)) from None
        row = {'minute': minute + 1, 'price': vals['close'], **vals}
        if minute in rows and rows[minute] != row:
            raise SIPError('conflicting duplicate bars for one minute')
        rows[minute] = row
    return [rows[minute] for minute in sorted(rows)]


def status_day(data: Any, day: dt.date) -> dict:
    ok, output = data.run(f'backfill.py sip-status --date {day.isoformat()}', timeout=600)
    if not ok:
        raise SIPError('could not verify the data box SIP files')
    try:
        result = json.loads(output.strip().splitlines()[-1])
        roots = result['roots']
        if result['day'] != str(day) or not isinstance(roots, list):
            raise ValueError('invalid SIP status shape')
        names = [row['root'] for row in roots]
        if len(set(names)) != len(names) or any(not re.fullmatch(r'[A-Z]{1,6}', r) or r in INDEX_ROOTS for r in names):
            raise ValueError('invalid SIP status roots')
        return result
    except (ValueError, KeyError, TypeError, IndexError):
        raise SIPError('invalid data-box SIP verification response') from None


def packet_digest(packet: dict) -> str:
    return hashlib.sha256(json.dumps(packet, sort_keys=True, allow_nan=False).encode()).hexdigest()


def relay_day(day: dt.date, data: Any, *, gateway: Any = None, calendar: Any = None,
              source_root: Callable[[str, dt.date], str] | None = None, allow_gaps: bool = False,
              roots: list[str] | None = None, verified: dict | None = None,
              check_lease: Callable[[], None] = lambda: None) -> dict[str, Any]:
    """Complete root packets only. `allow_gaps` is for the durable historical queue, never nightly."""
    if calendar is None or source_root is None:
        if calendar is None:
            calendar = sl.Calendar.from_json(json.loads(data.download('/data/work/calendar.json'))['exceptions'])
        source_root = source_root or sl.source_root
    hours = calendar.hours(day)
    if hours is None:
        return {'day': day.isoformat(), 'skipped': 'not a trading day'}
    before = verified or status_day(data, day)
    by_root = {row['root']: row for row in before['roots']}
    wanted = sorted(by_root) if roots is None else sorted(set(roots))
    if set(wanted) - set(by_root):
        raise SIPError('requested SIP roots are absent from the verified day plan')
    needed = [root for root in wanted if not by_root[root].get('complete')]
    if not needed:
        return {'day': str(day), 'roots': wanted, 'already': True, 'complete': True,
                'coverage': [by_root[r] for r in wanted]}
    if gateway is None:
        config = json.loads((REPO / 'league' / 'config.json').read_text())
        gateway = GatewayBars(config['gateway_url'], os.environ.get('GATEWAY_TOKEN', ''))
    sources = {root: source_root(root, day) for root in needed}
    bars = gateway.fetch(sorted(set(sources.values())), day, hours)
    packets, receipts = [], []
    for root, symbol in sources.items():
        error = None
        try:
            rows = completed_rows(bars.get(symbol, []), day, hours)
        except SIPError as exc:
            rows, error = [], str(exc)[:200]
        coverage = sl.sip_coverage([r['minute'] for r in rows], hours)
        packet = {'root': root, 'day': str(day), 'completed_minutes': True, 'source_symbol': symbol, 'rows': rows,
                  'decoded_response_sha256': hashlib.sha256(json.dumps(bars.get(symbol, []), sort_keys=True).encode()).hexdigest()}
        receipt = {**coverage, 'root': root, 'day': str(day), 'source': SOURCE, 'source_symbol': symbol,
                   'packet_sha256': packet_digest(packet),
                   'status': 'error' if error else ('complete' if coverage['complete'] else ('partial' if rows else 'empty'))}
        if error:
            receipt['error'] = error
        if coverage['complete']:
            packets.append(packet)
        else:
            # Content-addressed and independent of attempt time: identical retries use the same private file.
            path = f"/data/work/sip-partial-{day}-{root}-{receipt['packet_sha256']}.json"
            check_lease()
            data.upload(path, json.dumps({'packet': packet, 'coverage': receipt}, allow_nan=False,
                                        sort_keys=True).encode(), 0o600)
            receipt['quarantine'] = path
        receipts.append(receipt)
    gaps = [row for row in receipts if not row['complete']]
    if gaps and not allow_gaps:
        raise SIPError('incomplete regular-session SIP bars: ' + ', '.join(f"{r['root']} {r['known']}/{r['expected']}" for r in gaps))
    if packets:
        path = f'/data/work/sip-{day.isoformat()}.json'
        check_lease()
        data.upload(path, json.dumps(packets, allow_nan=False, separators=(',', ':')).encode(), 0o600)
        check_lease()
        ok, _ = data.run(f'backfill.py ingest-underlying --input {path}', timeout=600)
        if not ok:
            raise SIPError('the data box refused completed SIP bars')
        confirmed = {row['root']: row for row in status_day(data, day)['roots']}
        for receipt in receipts:
            if receipt['complete']:
                found = confirmed.get(receipt['root']) or {}
                if not found.get('complete') or found.get('packet_sha256') != receipt['packet_sha256']:
                    raise SIPError('SIP complete grid and packet hash were not confirmed by the data box')
                receipt.update(found)
    return {'day': str(day), 'roots': needed, 'rows': sum(len(p['rows']) for p in packets),
            'complete': not gaps, 'coverage': receipts}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--env', type=Path, help='owner-private House environment file, read on this host only')
    parser.add_argument('--start', type=dt.date.fromisoformat, required=True)
    parser.add_argument('--end', type=dt.date.fromisoformat, required=True)
    args = parser.parse_args(argv)
    if args.start > args.end or args.end >= dt.datetime.now(NY).date():
        parser.error('the range must contain completed days, with start <= end')
    if (args.end - args.start).days >= 31:
        parser.error('use chunks of at most 31 calendar days so the data lease and backfill pause stay bounded')
    sys.path.insert(0, str(REPO))
    os.environ['LTCM_GYM_STATE'] = str(args.state)
    if args.env:
        from league.service import load_env
        load_env(args.env)
    import boxlib as bl
    from nightly import BoxHandle
    import storelib as sl

    api = bl.client()
    data = BoxHandle(api, bl.data_box_id())
    data.wake()
    with bl.RemoteLease(api, data.box_id) as lease:
        calendar = sl.Calendar.from_json(json.loads(data.download('/data/work/calendar.json'))['exceptions'])
        state = bl.read_json(bl.DATA_BOX)
        runs = state.get('runs') or []
        backfill_args = state.get('backfill_args') or (runs[-1].get('args') if runs else None)
        was_running = data.backfill_running()
        if was_running and not backfill_args:
            raise SIPError('a running backfill has no recorded restart arguments')
        if was_running:
            lease.check()
            data.stop_backfill()
        try:
            lease.check()
            bl.push_code(api, data.box_id)
            for day in calendar.days(args.start, args.end):
                print(json.dumps(relay_day(day, data, calendar=calendar, source_root=sl.source_root,
                                           check_lease=lease.check)), flush=True)
        finally:
            if was_running:
                lease.check()
                data.start_backfill(backfill_args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
