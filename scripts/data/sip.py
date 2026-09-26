#!/usr/bin/env python3
"""House-only SIP historical bars relay; the data box receives data, never a token.

Alpaca stamps each bar at its start. A minute's OHLCV becomes visible at start+1
minute, after the bar is complete. Requests use raw prices to match historical
option strikes. Index underlyings keep the ThetaData/parity path.
"""
from __future__ import annotations

import argparse
import datetime as dt
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

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
NY = ZoneInfo('America/New_York')
SOURCE = 'alpaca SIP completed-minute OHLCV v1'
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


def _records(data: Any, day: dt.date) -> list[dict]:
    ok, output = data.run(f'backfill.py records --date {day.isoformat()}', timeout=600)
    if not ok:
        raise SIPError('could not read the data box records')
    records = [json.loads(line) for line in output.splitlines() if line.strip().startswith('{')]
    return [row for row in records if row.get('type') == 'file']


def relay_day(day: dt.date, data: Any, *, gateway: Any = None, calendar: Any = None,
              source_root: Callable[[str, dt.date], str] | None = None) -> dict[str, Any]:
    """Relay one day while the caller holds the data operation lease/backfill pause."""
    if calendar is None or source_root is None:
        import storelib as sl
        if calendar is None:
            calendar = sl.Calendar.from_json(json.loads(data.download('/data/work/calendar.json'))['exceptions'])
        source_root = source_root or sl.source_root
    hours = calendar.hours(day)
    if hours is None:
        return {'day': day.isoformat(), 'skipped': 'not a trading day'}
    records = _records(data, day)
    roots = sorted({row['root'] for row in records if row.get('kind') == 'nbbo'} - INDEX_ROOTS)
    if any(not isinstance(root, str) or not re.fullmatch(r'[A-Z]{1,6}', root) for root in roots):
        raise SIPError('invalid canonical root in store records')
    done = {row['root'] for row in records if row.get('kind') == 'underlying' and row.get('source') == SOURCE}
    needed = [root for root in roots if root not in done]
    if not needed:
        return {'day': day.isoformat(), 'roots': roots, 'already': True}
    if gateway is None:
        config = json.loads((REPO / 'league' / 'config.json').read_text())
        gateway = GatewayBars(config['gateway_url'], os.environ.get('GATEWAY_TOKEN', ''))
    sources = {root: source_root(root, day) for root in needed}
    bars = gateway.fetch(sorted(set(sources.values())), day, hours)
    packets = []
    for root, symbol in sources.items():
        rows = completed_rows(bars.get(symbol, []), day, hours)
        if not rows:
            raise SIPError(f'no regular-session SIP bars for {root} on {day}')
        packets.append({'root': root, 'day': day.isoformat(), 'completed_minutes': True, 'rows': rows})
    path = f'/data/work/sip-{day.isoformat()}.json'
    data.upload(path, json.dumps(packets, allow_nan=False, separators=(',', ':')).encode(), 0o600)
    ok, _ = data.run(f'backfill.py ingest-underlying --input {path}', timeout=600)
    if not ok:
        raise SIPError('the data box refused completed SIP bars')
    confirmed = {row['root'] for row in _records(data, day) if row.get('kind') == 'underlying' and row.get('source') == SOURCE}
    if not set(needed) <= confirmed:
        raise SIPError('SIP bars were not confirmed by the data box journal')
    return {'day': day.isoformat(), 'roots': needed, 'rows': sum(len(packet['rows']) for packet in packets)}


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
    with bl.RemoteLease(api, data.box_id):
        calendar = sl.Calendar.from_json(json.loads(data.download('/data/work/calendar.json'))['exceptions'])
        state = bl.read_json(bl.DATA_BOX)
        runs = state.get('runs') or []
        backfill_args = state.get('backfill_args') or (runs[-1].get('args') if runs else None)
        was_running = data.backfill_running()
        if was_running and not backfill_args:
            raise SIPError('a running backfill has no recorded restart arguments')
        if was_running:
            data.stop_backfill()
        try:
            for day in calendar.days(args.start, args.end):
                print(json.dumps(relay_day(day, data, calendar=calendar, source_root=sl.source_root)), flush=True)
        finally:
            if was_running:
                data.start_backfill(backfill_args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
