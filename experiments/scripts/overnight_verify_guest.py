"""Offline, frozen company-check worker. No credentials, network or inference."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

SYMBOLS = ('NVDA', 'TSM', 'AVGO', 'CEG', 'VRT', 'MSFT', 'AMZN', 'GOOGL', 'META')


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def execute(root, request):
    root = Path(root)
    if (not isinstance(request, dict) or set(request) != {'schema_version', 'call_key', 'symbol', 'manifest_sha256', 'draft'} or
            request['schema_version'] != 1 or request['symbol'] not in SYMBOLS or
            not isinstance(request['call_key'], str) or not re.fullmatch('[a-f0-9]{64}', request['call_key']) or
            len(encoded(request).encode()) > 60000):
        raise ValueError('Invalid bounded company-check request')
    raw = (root / 'manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != request['manifest_sha256']:
        raise ValueError('Changed worker manifest')
    manifest = json.loads(raw)
    expected = {'overnight_review.py', 'scripts/overnight_verify_guest.py'} | {'companies/'+s+'.json' for s in SYMBOLS}
    if (manifest.get('schema_version') != 1 or len(manifest['files']) != len(expected) or
            {f['path'] for f in manifest['files']} != expected):
        raise ValueError('Unexpected worker file manifest')
    for item in manifest['files']:
        path = root / item['path']
        if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
            raise ValueError('Invalid frozen worker file')
        data = path.read_bytes()
        if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError('Frozen worker bytes changed')
    company = json.loads((root / 'companies' / (request['symbol']+'.json')).read_text())
    module_spec = importlib.util.spec_from_file_location('frozen_overnight_review', root / 'overnight_review.py')
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    result = module.check_case(request['draft'], company)
    receipt = {'schema_version': 1, 'call_key': request['call_key'], 'symbol': request['symbol'],
               'manifest_sha256': request['manifest_sha256'], 'request_sha256': digest(request),
               'result': result, 'result_sha256': digest(result)}
    path = root / 'receipts' / (request['call_key']+'.json')
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('Receipt path cannot be a symlink')
    if path.exists():
        if json.loads(path.read_text()) != receipt:
            raise ValueError('A saved verification identity changed')
        return receipt
    path.parent.mkdir(exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(encoded(receipt)+'\n')
    temporary.replace(path)
    return receipt


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2 or not re.fullmatch('[a-f0-9]{64}', sys.argv[1]):
            raise ValueError('Use a frozen verification key')
        root = Path(__file__).resolve().parents[1]
        execute(root, json.loads((root / 'requests' / (sys.argv[1]+'.json')).read_text()))
        print('Company check receipt saved.')
    except Exception:
        raise SystemExit('Frozen company verification stopped.') from None
