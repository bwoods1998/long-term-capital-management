#!/usr/bin/env python3
"""Owner-only external kill-switch control. The admin token never goes to a Sailbox.

`provision` generates an owner credential once and installs it as a Worker secret.
`unkill` explicitly releases the external switch; provisioning does not change its state.
`kill` engages it (any holder of the ordinary gateway token may: stopping is never gated).
`status` prints the switch, today's counters, the frontier month and the Sail balance.
No credential value is printed, passed in argv, or included in deployment archives.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
KEY = ROOT / '.data' / 'ltcm' / 'keys' / 'gateway-admin.token'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['provision', 'unkill', 'kill', 'status'])
    args = parser.parse_args()
    if args.command == 'provision':
        KEY.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(KEY, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'w') as output:
                output.write(secrets.token_urlsafe(48) + '\n')
        os.chmod(KEY, 0o600)
        token = KEY.read_text().strip()
        if len(token) < 32:
            raise SystemExit('Owner credential is missing or invalid; no changes made.')
        result = subprocess.run(['npx', 'wrangler', 'secret', 'put', 'GATEWAY_ADMIN_TOKEN'],
                                cwd=ROOT/'gateway', input=token+'\n', text=True)
        if result.returncode:
            raise SystemExit(result.returncode)
        print('Owner credential provisioned; trading VM has no copy. Kill-switch state unchanged.')
        return
    if args.command in ('kill', 'status'):
        config = json.loads((ROOT/'league/config.json').read_text())
        url = str(config.get('gateway_url') or '').rstrip('/')
        token = os.environ.get('GATEWAY_TOKEN', '')
        if not token:
            for line in (ROOT/'.env').read_text().splitlines():
                if line.startswith('GATEWAY_TOKEN='):
                    token = line.split('=', 1)[1].strip().strip('"').strip("'")
        path, method = ('/v1/kill', 'POST') if args.command == 'kill' else ('/v1/health', 'GET')
        request = urllib.request.Request(url+path, data=b'' if method == 'POST' else None, method=method, headers={'Authorization': 'Bearer '+token, 'User-Agent': 'ltcm-floor/1.0'})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
        sail = data.get('sail') or {}
        print(json.dumps({'kill_switch': data.get('kill_switch'), 'today': data.get('today'), 'frontier': data.get('frontier'), 'typesafe': data.get('typesafe'), 'github': data.get('github'),
                          'sail_balance_usd': sail.get('balance_usd'), 'box_status': sail.get('box_status')}, indent=1))
        return
    token = KEY.read_text().strip()
    config = json.loads((ROOT/'ltcm/config.json').read_text())
    url = str(config.get('gateway_url') or '').rstrip('/')
    if not url.startswith('https://'):
        raise SystemExit('No HTTPS gateway configured; no changes made.')
    request = urllib.request.Request(url+'/v1/unkill', data=b'', method='POST', headers={'Authorization': 'Bearer '+token, 'User-Agent': 'ltcm-floor/1.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    print(json.dumps({'kill_switch': data.get('kill_switch'), 'ok': data.get('ok')}))


if __name__ == '__main__':
    main()
