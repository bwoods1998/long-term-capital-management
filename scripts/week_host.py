#!/usr/bin/env python3
"""Freeze/provision one explicit weekday service; configure the independent supervisor.

Preparation is offline. Provision installs code and a checked paper/history seed.
Enrollment arms the cloud supervisor, and must use a tested deployment and a
standing owner-selected spending allowance. No brokerage keys are uploaded.
"""
import argparse
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
import gzip
import json
from pathlib import Path
import re
import sqlite3
import sys
from urllib.request import Request,build_opener
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from host_runtime import HostDeployment,clients,private_read,private_lock
from portfolio_runtime.evidence import save
from portfolio_runtime.credentials import load_api_key,NoRedirect
from portfolio_runtime.sail_host import encoded,sha
from portfolio_runtime.provider import ClosingConnection
from portfolio_runtime.contracts import timestamp
ROOT=Path(__file__).resolve().parents[1]
SUPERVISOR='https://portfolio-supervisor.blake-woods-personal-site.workers.dev'

def prepare(directory, *, total, starts, ends, seed):
    directory=Path(directory).resolve();seed=Path(seed).resolve()
    if directory.exists():raise ValueError('Choose a fresh service directory')
    total=Decimal(total);cloud=Decimal('7.5')
    if not total.is_finite() or not Decimal('10')<=total<=Decimal('10000'):raise ValueError('Invalid weekly budget')
    start,end=timestamp(starts),timestamp(ends)
    if not 3600 <= (end-start).total_seconds() <= 7*86400:raise ValueError('Expected an explicit service week')
    for path in [seed/'paper.sqlite',seed/'research.sqlite',seed/'requests.sqlite']:
        if not path.is_file() or path.is_symlink():raise ValueError('Expected stopped private seed')
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,factory=ClosingConnection) as db:
            if db.execute('PRAGMA quick_check').fetchone()!=('ok',):raise ValueError('Seed integrity failed')
    anchor=json.loads((ROOT/'.data/runtime/account-anchor.json').read_text())
    created=anchor.get('created_at',anchor.get('account_created_at'))
    if not created:raise ValueError('Missing permanent account anchor')
    key=load_api_key();identity='week-'+datetime.fromisoformat(starts.replace('Z','+00:00')).strftime('%Y%m%d')+'-v1'
    config={'schema_version':1,'kind':'weekday_service','service_id':identity,'state_dir':'/workspace/state',
        'week_starts_at':starts,'week_ends_at':ends,'weekly_inference_budget_usd':format(total-cloud,'f'),
        'cloud_budget_usd':format(cloud,'f'),'weekly_total_usd':format(total,'f'),
        'session_inference_budget_usd':format(min(Decimal('4.625'),total-cloud),'f'),
        'session_seconds':3600,'adaptive_spending':True,'account_created_at':created,'key_fingerprint':sha(key.encode()),
        'initial_evidence_path':'/workspace/data/sp500-evidence.json','seed_dir':'/workspace/state/seed',
        'admission_path':'/workspace/config/admission.json','admission_max_age_seconds':180,
        'publish_url':'https://blakewoods.us/api/portfolio/state','injected_auth':True,
        'backup_url':SUPERVISOR+'/v1/backups','max_concurrency':8,'wave_size':12,'wave_seconds':600,
        'experiment_pairs_per_epoch':4,'fetch_filings':True}
    directory.mkdir(parents=True,mode=0o700)
    save(directory/'run.json',config)
    manifest={name:{'sha256':sha((seed/name).read_bytes()),'bytes':(seed/name).stat().st_size}
              for name in ['paper.sqlite','research.sqlite','requests.sqlite']}
    save(directory/'seed.json',{'source':str(seed),'files':manifest})
    return config

def provision(directory, app_id):
    directory=Path(directory).resolve();config=json.loads((directory/'run.json').read_text())
    key,deps=clients();host=HostDeployment(directory/'host',**deps)
    names=tuple('portfolio_runtime/'+p.name for p in sorted((ROOT/'portfolio_runtime').glob('*.py')))+('data/sp500-evidence.json',)
    result=host.provision(config,app_id,key=key,publication_token=private_read(ROOT/'.data/runtime/publish-token'),
        backup_token=private_read(ROOT/'.data/runtime/control/backup-token'),names=names)
    seed=json.loads((directory/'seed.json').read_text());box=host.host.attach()
    if host.host._read()['started']:raise ValueError('Cannot overwrite a started service seed')
    for name,expected in seed['files'].items():
        source=Path(seed['source'])/name;raw=source.read_bytes()
        if sha(raw)!=expected['sha256']:raise ValueError('Seed changed after preparation')
        target=config['seed_dir']+'/'+name
        # Research prompts compress well. Verify original bytes and SQLite on
        # the guest instead of transferring each large seed twice uncompressed.
        compressed=target+'.gz'
        box.fs.write(compressed,gzip.compress(raw,compresslevel=6,mtime=0),mode=0o600,create_parents=True)
        program="""import gzip,hashlib,json,os,sqlite3,sys
from pathlib import Path
source,target,expected,size=sys.argv[1:];target=Path(target);temporary=target.with_suffix('.uploading')
digest=hashlib.sha256();count=0
with gzip.open(source,'rb') as incoming,temporary.open('wb') as output:
 while part:=incoming.read(1024*1024):
  count+=len(part)
  if count>int(size):raise ValueError('seed_size_mismatch')
  digest.update(part);output.write(part)
if count!=int(size) or digest.hexdigest()!=expected:raise ValueError('seed_hash_mismatch')
db=sqlite3.connect(temporary.as_uri()+'?mode=ro',uri=True)
try:
 if db.execute('PRAGMA quick_check').fetchone()!=('ok',):raise ValueError('seed_integrity_failed')
finally:db.close()
temporary.chmod(0o600);os.replace(temporary,target);Path(source).unlink()
print(json.dumps({'sha256':digest.hexdigest(),'bytes':count,'integrity':'ok'}))
"""
        upload_result=box.exec(['python3','-c',program,compressed,target,expected['sha256'],str(expected['bytes'])],timeout=120).wait()
        if upload_result.exit_code!=0:raise ValueError('Seed upload integrity failed')
        receipt=json.loads(upload_result.stdout)
        if receipt!={**expected,'integrity':'ok'}:raise ValueError('Seed upload receipt mismatch')
    box.fs.write('/workspace/config/admission.json',encoded({'schema_version':1,'service_id':config['service_id'],
        'updated_at':datetime.now(timezone.utc).isoformat(),'allow_new_research':False,'reason_code':'not_enrolled'}),mode=0o600)
    save(directory/'installed.json',{'manifest_sha256':host.host._read()['manifest_sha256'],'seed_verified':True})
    return result

def enrollment(directory):
    directory=Path(directory);config=json.loads((directory/'run.json').read_text());host=json.loads((directory/'host/host.json').read_text())
    return {'schema_version':1,'service_id':config['service_id'],'box_id':host['sailbox_id'],
        'manifest_sha256':host['manifest_sha256'],'starts_at':config['week_starts_at'],'ends_at':config['week_ends_at'],
        'weekly_total_usd':config['weekly_total_usd'],'weekly_inference_usd':config['weekly_inference_budget_usd'],
        'cloud_budget_usd':config['cloud_budget_usd'],'credit_floor_usd':'2'}

def control(method,path,body=None):
    if path not in ('/v1/configure','/v1/status','/v1/pause','/v1/resume','/v1/tick'):raise ValueError('Unexpected control path')
    req=Request(SUPERVISOR+path,data=encoded(body) if body is not None else None,method=method,
        headers={'Authorization':'Bearer '+private_read(ROOT/'.data/runtime/control/admin-token'),'Content-Type':'application/json','User-Agent':'Blake Woods Portfolio Agent'})
    with build_opener(NoRedirect).open(req,timeout=60) as r:return json.loads(r.read(256000))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['prepare','provision','enroll','status','pause','resume'])
    p.add_argument('--directory',required=True);p.add_argument('--budget');p.add_argument('--starts-at');p.add_argument('--ends-at');p.add_argument('--seed');p.add_argument('--app-id');args=p.parse_args()
    if args.command=='prepare':
        if not all([args.budget,args.starts_at,args.ends_at,args.seed]):raise ValueError('Specify total budget, dates and stopped seed')
        c=prepare(args.directory,total=args.budget,starts=args.starts_at,ends=args.ends_at,seed=args.seed)
        result={k:c[k] for k in ('service_id','week_starts_at','week_ends_at','weekly_total_usd')}
    elif args.command=='provision':result=provision(args.directory,args.app_id)
    elif args.command=='enroll':
        if not (Path(args.directory)/'readiness.json').is_file():raise ValueError('Save a reviewed readiness receipt before enrollment')
        receipt=json.loads((Path(args.directory)/'readiness.json').read_text());body=enrollment(args.directory)
        if receipt.get('ready') is not True or receipt.get('manifest_sha256')!=body['manifest_sha256']:raise ValueError('Readiness does not match deployment')
        result=control('POST','/v1/configure',body)
    else:result=control('GET' if args.command=='status' else 'POST','/v1/'+args.command,None if args.command=='status' else {})
    print(json.dumps(result,sort_keys=True))
if __name__=='__main__':
    try:main()
    except Exception as error:
        print('Weekday host operation failed ('+type(error).__name__+'). Inspect the private operation journal.',file=sys.stderr);raise SystemExit(1)
