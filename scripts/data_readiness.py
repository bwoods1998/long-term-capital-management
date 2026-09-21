#!/usr/bin/env python3
"""Read-only Alpaca account and subscribed-feed checks. Never submits an order."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from league.service import load_config, load_env, secret
from league.venues import gateway_broker


def report(config, token):
    now = datetime.now(timezone.utc)
    out = {'at': now.isoformat(), 'venues': {},
           'note': 'Subscription, options approval and options buying power are separate checks. Reads do not prove an order would execute.'}
    for venue in ('alpaca', 'alpaca-paper'):
        broker = gateway_broker(venue, gateway_url=config['gateway_url'], token=token)
        checks = {}
        try:
            account = broker._call('GET', '/v2/account', what='account readiness')
            checks['account'] = {k: account.get(k) for k in (
                'status', 'cash', 'equity', 'buying_power', 'non_marginable_buying_power',
                'options_approved_level', 'options_trading_level', 'options_buying_power',
                'trading_blocked', 'account_blocked')}
        except Exception as exc:
            checks['account'] = {'error': str(exc)[:300]}
        for feed, path, params in (
            ('sip', '/v2/stocks/quotes/latest', {'symbols': 'SPY,QQQ', 'feed': 'sip'}),
            ('opra', '/v1beta1/options/snapshots/F', {'feed': 'opra', 'limit': 1,
                'expiration_date_gte': (now + timedelta(days=1)).date().isoformat()}),
        ):
            try:
                data = broker._call('GET', path, params=params, base=broker.data, what=feed+' entitlement')
                rows = data.get('quotes') or data.get('snapshots') or {}
                checks[feed] = {'request_succeeded': True, 'rows': len(rows),
                    'quote_times': {symbol: (row.get('latestQuote') or row).get('t') for symbol, row in rows.items()}}
            except Exception as exc:
                checks[feed] = {'request_succeeded': False, 'error': str(exc)[:300]}
        out['venues'][venue] = checks
    return out


if __name__ == '__main__':
    load_env(ROOT / '.env')
    print(json.dumps(report(load_config(), secret('GATEWAY_TOKEN')), indent=2, default=str))
