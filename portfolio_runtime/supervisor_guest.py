"""Fixed supervisor probe and private off-machine snapshots; no inference authority."""
from __future__ import annotations
import argparse
from contextlib import closing
from datetime import datetime, timezone
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import sys
import tempfile
import time
from urllib.request import Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portfolio_runtime.evidence import save
from portfolio_runtime.credentials import NoRedirect
ROOT = Path('/workspace')
MAX_ARTIFACT = 64 * 1024 * 1024

def utc(): return datetime.now(timezone.utc).isoformat()
def digest(raw): return hashlib.sha256(raw).hexdigest()
def locked(path):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with path.open('a') as handle:
        try: fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB);return False
        except BlockingIOError:return True

def probe(root=ROOT):
    root=Path(root);state=root/'state'
    manifest=json.loads((root/'host-manifest.json').read_text())
    identity=digest(json.dumps(manifest,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())
    health=json.loads((state/'service-health.json').read_text()) if (state/'service-health.json').exists() else None
    backup=json.loads((state/'backup-health.json').read_text()) if (state/'backup-health.json').exists() else {}
    backup['running']=locked(state/'backup.lock')
    return {'manifest_sha256':identity,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'running':locked(state/'coordinator.lock'),'health':health,'backup':backup}

def force_stop(root=ROOT):
    """Last resort after grace: only our verified bootstrap and its service child."""
    root=Path(root)
    path=root/'state/host-process.json'
    if not path.exists():return {'stopped':True}
    saved=json.loads(path.read_text());pid=saved.get('pid')
    if type(pid) is not int or pid<=1 or saved.get('boot_id')!=Path('/proc/sys/kernel/random/boot_id').read_text().strip():
        raise ValueError('process_identity_changed')
    parent=Path('/proc')/str(pid)
    if not parent.exists():return {'stopped':True}
    if b'/workspace/host-boot.py' not in (parent/'cmdline').read_bytes().split(b'\0'):
        raise ValueError('process_identity_changed')
    for proc in Path('/proc').iterdir():
        if not proc.name.isdecimal():continue
        try:
            status=(proc/'status').read_text()
            match=re.search(r'^PPid:\s*(\d+)$',status,re.M)
            args=(proc/'cmdline').read_bytes().split(b'\0')
            if match and int(match[1])==pid and b'portfolio_runtime.service' in args and b'-m' in args:
                os.kill(int(proc.name),signal.SIGKILL)
        except (FileNotFoundError,ProcessLookupError):pass
    try:os.kill(pid,signal.SIGKILL)
    except ProcessLookupError:pass
    return {'stopped':not locked(root/'state/coordinator.lock')}

def artifact_paths(root):
    state=root/'state';items=[]
    for path in state.rglob('*'):
        if not path.is_file() or path.is_symlink():continue
        relative=path.relative_to(state)
        # Exclude large re-fetchable raw source caches and temporary snapshots.
        if any(part.startswith('.') or part in ('filings','raw','snapshots') for part in relative.parts):continue
        if path.suffix in ('.sqlite','.json'):
            if path.stat().st_size > 1_500_000_000:raise ValueError('database_too_large')
            items.append(path)
    for path in (root/'config/run.json',root/'host-manifest.json',root/'data/sp500-evidence.json'):
        if path.is_file() and not path.is_symlink():items.append(path)
    if len(items)>4000:raise ValueError('snapshot_file_limit')
    return sorted(items,key=lambda p: (p.name!='paper.sqlite',p.suffix!='.sqlite',str(p)))

def upload(url,path,hash_value,*,opener=None):
    # Only our dedicated supervisor accepts a private artifact; no redirect following.
    if not re.fullmatch(r'https://portfolio-supervisor\.[a-z0-9-]+\.workers\.dev/v1/backups/[a-z0-9-]+/[a-z0-9-]+/[a-f0-9]{64}\.(gz|json)',url):
        raise ValueError('invalid_backup_destination')
    if not 0<path.stat().st_size<=MAX_ARTIFACT:raise ValueError('artifact_too_large')
    with path.open('rb') as body:
        request=Request(url,data=body,method='PUT',headers={'Content-Type':'application/octet-stream',
            'Content-Length':str(path.stat().st_size),'X-Content-SHA256':hash_value,'User-Agent':'Blake Woods Portfolio Agent'})
        with (opener or build_opener(NoRedirect)).open(request,timeout=90) as response:
            receipt=json.loads(response.read(16001))
            if receipt.get('stored') is not True:raise ValueError('backup_unconfirmed')

def backup(root=ROOT,*,uploader=upload,clock=time.time):
    root=Path(root);state=root/'state';state.mkdir(parents=True,exist_ok=True,mode=0o700)
    config=json.loads((root/'config/run.json').read_text())
    destination=config['backup_url'].rstrip('/')
    service=config['service_id']
    if not re.fullmatch('[a-z0-9-]{8,64}',service):raise ValueError('invalid_service')
    with (state/'backup.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'running':True}
        previous=json.loads((state/'backup-health.json').read_text()) if (state/'backup-health.json').exists() else {}
        started=utc();snapshot='snapshot-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+os.urandom(4).hex()
        save(state/'backup-health.json',{**previous,'running':True,'status':'running','started_at':started})
        rows=[];until=clock()+840
        try:
            with tempfile.TemporaryDirectory(prefix='portfolio-snapshot-') as tmp:
                tmp=Path(tmp)
                for i,path in enumerate(artifact_paths(root)):
                    if clock()>until:raise TimeoutError('backup_deadline')
                    source=path;temporary=tmp/(str(i)+'.sqlite')
                    if path.suffix=='.sqlite':
                        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
                            with closing(sqlite3.connect(temporary)) as copied:
                                def progress(*_):
                                    if clock()>until:raise TimeoutError('backup_deadline')
                                db.backup(copied,pages=1024,progress=progress)
                                if copied.execute('PRAGMA quick_check').fetchone()!=('ok',):raise ValueError('snapshot_integrity')
                        source=temporary
                    target=tmp/(str(i)+'.gz');rawhash=hashlib.sha256();size=0
                    with source.open('rb') as original,gzip.open(target,'wb',compresslevel=6) as compressed:
                        while part:=original.read(1024*1024):rawhash.update(part);size+=len(part);compressed.write(part)
                    if target.stat().st_size>MAX_ARTIFACT:raise ValueError('artifact_too_large')
                    hashed=hashlib.sha256()
                    with target.open('rb') as handle:
                        while part:=handle.read(1024*1024):hashed.update(part)
                    h=hashed.hexdigest();key=f'{service}/{snapshot}/{h}.gz'
                    uploader(destination+'/'+key,target,h)
                    rows.append({'path':str(path.relative_to(root)),'bytes':size,'sha256':rawhash.hexdigest(),
                                 'object_key':key,'compressed_sha256':h,'compressed_bytes':target.stat().st_size})
                    target.unlink();temporary.unlink(missing_ok=True)
                manifest={'schema_version':1,'service_id':service,'snapshot_id':snapshot,'started_at':started,
                          'completed_at':utc(),'consistent_across_databases':False,'files':rows,
                          'recovery':'Stop writers, verify hashes and reconcile provider requests before restoring authority.'}
                data=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode();h=digest(data)
                target=tmp/'manifest.json';target.write_bytes(data);key=f'{service}/{snapshot}/{h}.json'
                uploader(destination+'/'+key,target,h)
                result={'running':False,'status':'complete','completed_at':manifest['completed_at'],'manifest_key':key,
                        'files':len(rows),'bytes':sum(row['compressed_bytes'] for row in rows)}
                save(state/'backup-health.json',result);return result
        except Exception:
            save(state/'backup-health.json',{**previous,'running':False,'status':'failed','failed_at':utc(),'reason_code':'backup_unavailable'})
            raise

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['probe','backup','force-stop']);args=parser.parse_args()
    print(json.dumps({'probe':probe,'backup':backup,'force-stop':force_stop}[args.command](),sort_keys=True))
if __name__=='__main__':
    try:main()
    except Exception:
        print('Supervisor guest operation failed.',file=sys.stderr);raise SystemExit(1)
