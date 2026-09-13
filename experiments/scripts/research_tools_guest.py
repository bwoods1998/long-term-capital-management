"""Evidence-only Sailbox worker. No credentials, model client, or spending ledger."""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import research_sources as sources


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode()).hexdigest()


def execute(root, request):
    """Check the frozen evidence, execute one allowlisted tool, cache its receipt."""
    root = Path(root)
    if (not isinstance(request, dict) or set(request) !=
            {'schema_version', 'call_key', 'name', 'args', 'cutoff', 'manifest_sha256'} or
            request['schema_version'] != 1 or
            not isinstance(request['call_key'], str) or
            not re.fullmatch(r'[a-f0-9]{64}', request['call_key'])):
        raise ValueError('Invalid tool envelope')
    raw_manifest = (root / 'manifest.json').read_bytes()
    if hashlib.sha256(raw_manifest).hexdigest() != request['manifest_sha256']:
        raise ValueError('Manifest identity mismatch')
    manifest = json.loads(raw_manifest)
    source_ids = manifest.get('source_ids')
    if (manifest.get('schema_version') != 1 or not isinstance(source_ids, list) or
            not source_ids or len(set(source_ids)) != len(source_ids)):
        raise ValueError('Invalid source manifest')
    for source_id in source_ids:
        sources.allowed_source(source_id)
    expected = {'packet.json', 'research_sources.py', 'scripts/research_tools_guest.py'} | {
        'sources/' + source_id + '.json' for source_id in source_ids}
    if (not isinstance(manifest.get('files'), list) or len(manifest['files']) != len(expected) or
            {item['path'] for item in manifest['files']} != expected):
        raise ValueError('Manifest must freeze every consumed code and evidence file')
    for item in manifest['files']:
        relative = Path(item['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Invalid manifest path')
        path = root / relative
        if any(parent.is_symlink() for parent in [path, *path.parents] if parent != root.parent) or not path.is_file():
            raise ValueError('Missing frozen file')
        data = path.read_bytes()
        if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError('Frozen bytes changed')
    packet = json.loads((root / 'packet.json').read_text())
    snapshots = {key: sources.validate_snapshot(json.loads(
        (root / 'sources' / (key + '.json')).read_text()), request['cutoff'])
        for key in manifest['source_ids']}
    receipt_path = root / 'receipts' / (request['call_key'] + '.json')
    if receipt_path.is_symlink() or receipt_path.parent.is_symlink():
        raise ValueError('Receipt paths cannot be symlinks')
    request_hash = digest(request)
    if receipt_path.exists():
        value = json.loads(receipt_path.read_text())
        if (not isinstance(value, dict) or set(value) !=
                {'schema_version', 'call_key', 'manifest_sha256', 'request_sha256',
                 'success', 'result', 'result_sha256'} or value['schema_version'] != 1 or
                value['call_key'] != request['call_key'] or
                value['manifest_sha256'] != request['manifest_sha256'] or type(value['success']) is not bool or
                value['request_sha256'] != request_hash or value['result_sha256'] != digest(value['result'])):
            raise ValueError('Stored tool receipt changed')
        return value
    try:
        result = sources.dispatch(request['name'], request['args'], packet, snapshots,
                                  cutoff=request['cutoff'])
        success = True
    except (ValueError, KeyError, TypeError):
        result = {'error': 'Tool arguments or evidence do not satisfy the research contract.'}
        success = False
    receipt = {'schema_version': 1, 'call_key': request['call_key'],
               'manifest_sha256': request['manifest_sha256'], 'request_sha256': request_hash,
               'success': success, 'result': result, 'result_sha256': digest(result)}
    receipt_path.parent.mkdir(exist_ok=True)
    temporary = receipt_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(receipt, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n')
    temporary.replace(receipt_path)
    return receipt


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2 or not re.fullmatch(r'[a-f0-9]{64}', sys.argv[1]):
            raise ValueError('Use a frozen tool key')
        request = json.loads((ROOT / 'requests' / (sys.argv[1] + '.json')).read_text())
        execute(ROOT, request)
        print('Tool receipt saved.')
    except Exception:
        raise SystemExit('Research tool stopped; inspect the frozen request.') from None
