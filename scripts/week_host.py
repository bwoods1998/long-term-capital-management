#!/usr/bin/env python3
"""Freeze/provision one explicit weekday service; configure the independent supervisor.

Preparation is offline. Provision installs code and a checked paper/history seed.
Enrollment arms the cloud supervisor, and must use a tested deployment and a
standing owner-selected spending allowance. No brokerage keys are uploaded.
"""
import argparse
from datetime import datetime,timezone
from decimal import Decimal, ROUND_CEILING
import hashlib
import gzip
import json
from pathlib import Path
import re
import sqlite3
import sys
from urllib.request import Request,build_opener
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from host_runtime import HostDeployment,clients,private_read,private_lock,cloud_cost_bound
from portfolio_runtime.evidence import save
from portfolio_runtime.credentials import load_api_key,NoRedirect
from portfolio_runtime.sail_host import encoded,sha,freeze_bundle
from portfolio_runtime.provider import ClosingConnection
from portfolio_runtime.contracts import timestamp
ROOT=Path(__file__).resolve().parents[1]
SUPERVISOR='https://portfolio-supervisor.blake-woods-personal-site.workers.dev'

def rehearsal_config(value, *, starts, ends, inference=None, available=False):
    if value is None:return None
    fields={'starts_at','ends_at'} | (set() if available else {'inference_budget_usd','session_inference_budget_usd'})
    if not isinstance(value,dict) or set(value)!=fields:raise ValueError('Explicit bounded rehearsal required')
    begin,finish=timestamp(value['starts_at']),timestamp(value['ends_at'])
    if (not 3600<=(finish-begin).total_seconds()<=8*3600
        or finish>timestamp(starts) or not 3600<=(timestamp(ends)-begin).total_seconds()<=7*86400):
        raise ValueError('Rehearsal must precede the week inside its cloud schedule')
    if available:return {'starts_at':value['starts_at'],'ends_at':value['ends_at']}
    try:
        budget=Decimal(str(value['inference_budget_usd']));hourly=Decimal(str(value['session_inference_budget_usd']))
    except ArithmeticError:raise ValueError('Invalid rehearsal budget') from None
    if (not budget.is_finite() or not hourly.is_finite() or not 0<hourly<=min(Decimal('2'),budget)
        or not budget<=min(Decimal('10'),inference)
        or not 3600<=(finish-begin).total_seconds()<=8*3600
        or finish>timestamp(starts) or not 3600<=(timestamp(ends)-begin).total_seconds()<=7*86400):
        raise ValueError('Rehearsal must precede the week inside its cloud and inference envelope')
    return {'starts_at':value['starts_at'],'ends_at':value['ends_at'],
        'inference_budget_usd':format(budget,'f'),'session_inference_budget_usd':format(hourly,'f')}

def prepare(directory, *, total=None, starts, ends, seed, rehearsal=None, spending_mode=None):
    directory=Path(directory).resolve();seed=Path(seed).resolve()
    if directory.exists():raise ValueError('Choose a fresh service directory')
    spending_mode=spending_mode or ('available_credit' if total is None else 'capped')
    if spending_mode not in ('available_credit','capped'):raise ValueError('Unknown spending mode')
    available=spending_mode=='available_credit'
    if available and total is not None:raise ValueError('Available-credit mode does not accept a fixed inference budget')
    cloud=Decimal('7.5')  # Offline estimate; available-credit provisioning freezes actual rate-derived reserve.
    if not available:
        total=Decimal(total)
        if not total.is_finite() or not Decimal('10')<=total<=Decimal('10000'):raise ValueError('Invalid weekly budget')
    start,end=timestamp(starts),timestamp(ends)
    if not 3600 <= (end-start).total_seconds() <= 7*86400:raise ValueError('Expected an explicit service week')
    rehearsal=rehearsal_config(rehearsal,starts=starts,ends=ends,inference=total-cloud if not available else None,available=available)
    for path in [seed/'paper.sqlite',seed/'research.sqlite',seed/'requests.sqlite']:
        if not path.is_file() or path.is_symlink():raise ValueError('Expected stopped private seed')
        wal=path.with_name(path.name+'-wal')
        if wal.exists() and wal.stat().st_size:raise ValueError('Checkpoint the stopped seed before preparation')
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,factory=ClosingConnection) as db:
            if db.execute('PRAGMA quick_check').fetchone()!=('ok',):raise ValueError('Seed integrity failed')
    anchor=json.loads((ROOT/'.data/runtime/account-anchor.json').read_text())
    created=anchor.get('created_at',anchor.get('account_created_at'))
    if not created:raise ValueError('Missing permanent account anchor')
    if timestamp(created)>timestamp(rehearsal['starts_at'] if rehearsal else starts):raise ValueError('The existing account must precede the full schedule')
    with sqlite3.connect((seed/'paper.sqlite').as_uri()+'?mode=ro',uri=True,factory=ClosingConnection) as db:
        row=db.execute("SELECT payload,digest FROM paper_config WHERE key='mandate'").fetchone()
    if not row:raise ValueError('Paper seed has no account mandate')
    mandate=json.loads(row[0])
    digest=sha(json.dumps(mandate,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
    if digest!=row[1] or mandate.get('created_at')!=created:raise ValueError('Paper seed does not match the permanent account anchor')
    key=load_api_key();identity='week-'+datetime.fromisoformat(starts.replace('Z','+00:00')).strftime('%Y%m%d')+'-v1'
    config={'schema_version':1,'kind':'weekday_service','service_id':identity,'state_dir':'/workspace/state',
        'week_starts_at':starts,'week_ends_at':ends,'cloud_budget_usd':format(cloud,'f'),
        'session_seconds':3600,'adaptive_spending':True,'account_created_at':created,'key_fingerprint':sha(key.encode()),
        'initial_evidence_path':'/workspace/data/sp500-evidence.json','seed_dir':'/workspace/state/seed',
        'admission_path':'/workspace/config/admission.json','admission_max_age_seconds':180,
        'publish_url':'https://blakewoods.us/api/portfolio/state','injected_auth':True,
        'backup_url':SUPERVISOR+'/v1/backups','max_concurrency':8,'wave_size':12,'wave_seconds':600,
        'experiment_pairs_per_epoch':4,'fetch_filings':True}
    if available:config['spending_mode']='available_credit'
    else:config.update(weekly_inference_budget_usd=format(total-cloud,'f'),weekly_total_usd=format(total,'f'),
        session_inference_budget_usd=format(min(Decimal('4.625'),total-cloud),'f'))
    if rehearsal:config['rehearsal']=rehearsal
    directory.mkdir(parents=True,mode=0o700)
    save(directory/'run.json',config)
    manifest={name:{'sha256':sha((seed/name).read_bytes()),'bytes':(seed/name).stat().st_size}
              for name in ['paper.sqlite','research.sqlite','requests.sqlite']}
    save(directory/'seed.json',{'source':str(seed),'files':manifest})
    return config

def reserve_cloud(directory, config, api):
    """Freeze the actual full resource allowance before any host identity exists."""
    if config.get('spending_mode')!='available_credit':return config
    directory=Path(directory)
    with private_lock(directory):
        path=directory/'cloud-reserve.json'
        if path.exists():
            receipt=json.loads(path.read_text())
            frozen=receipt['config']
            if frozen!={**config,'cloud_budget_usd':receipt['reserve_usd']} or receipt['ends_at']!=config['week_ends_at']:
                raise ValueError('Frozen cloud reserve changed')
            if config!=frozen:
                if (directory/'host/deployment.json').exists():raise ValueError('Existing host config cannot be restored implicitly')
                save(directory/'run.json',frozen)
            return frozen
        if (directory/'host/deployment.json').exists():raise ValueError('Cannot retrofit resource funding onto an existing host')
        rates=api('GET','/v1/sailboxes/spend').get('rates',{})
        envelope=freeze_bundle(ROOT,('portfolio_runtime/runner.py',),config,deadline=config['week_ends_at'])
        bound=cloud_cost_bound(rates,envelope)
        reserve=format(bound.quantize(Decimal('0.01'),rounding=ROUND_CEILING),'f')
        updated={**config,'cloud_budget_usd':reserve}
        receipt={'schema_version':1,'reserve_usd':reserve,'bound_usd':format(bound,'f'),
                 'rates':rates,'ends_at':config['week_ends_at'],'observed_at':datetime.now(timezone.utc).isoformat(),
                 'resources':{'vcpus':1,'memory_gib':2,'disk_gib':32,'shutdown_grace_seconds':300}}
        # Save the receipt first so an interrupted operation can restore the exact config.
        receipt['config']=updated
        save(path,receipt)
        save(directory/'run.json',updated)
        return updated

def provision(directory, app_id):
    directory=Path(directory).resolve();config=json.loads((directory/'run.json').read_text())
    key,deps=clients();config=reserve_cloud(directory,config,deps['api']) if config.get('spending_mode')=='available_credit' else config
    host=HostDeployment(directory/'host',**deps)
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
    result={'schema_version':1,'service_id':config['service_id'],'box_id':host['sailbox_id'],
        'manifest_sha256':host['manifest_sha256'],'starts_at':config['week_starts_at'],'ends_at':config['week_ends_at'],
        'cloud_budget_usd':config['cloud_budget_usd'],'credit_floor_usd':'2'}
    if config.get('spending_mode')=='available_credit':result['spending_mode']='available_credit'
    else:result.update(weekly_total_usd=config['weekly_total_usd'],weekly_inference_usd=config['weekly_inference_budget_usd'])
    if config.get('rehearsal'):result['rehearsal']=config['rehearsal']
    return result

def control(method,path,body=None):
    if path not in ('/v1/configure','/v1/replace','/v1/release','/v1/status','/v1/pause','/v1/resume','/v1/tick'):raise ValueError('Unexpected control path')
    req=Request(SUPERVISOR+path,data=encoded(body) if body is not None else None,method=method,
        headers={'Authorization':'Bearer '+private_read(ROOT/'.data/runtime/control/admin-token'),'Content-Type':'application/json','User-Agent':'Blake Woods Portfolio Agent'})
    with build_opener(NoRedirect).open(req,timeout=60) as r:return json.loads(r.read(256000))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['prepare','provision','enroll','status','pause','resume'])
    p.add_argument('--directory',required=True);p.add_argument('--budget');p.add_argument('--starts-at');p.add_argument('--ends-at');p.add_argument('--seed');p.add_argument('--app-id')
    p.add_argument('--spending-mode',choices=('available_credit','capped'),default='available_credit')
    p.add_argument('--rehearsal-starts-at');p.add_argument('--rehearsal-ends-at')
    p.add_argument('--rehearsal-budget');p.add_argument('--rehearsal-session-budget');args=p.parse_args()
    if args.command=='prepare':
        if not all([args.starts_at,args.ends_at,args.seed]):raise ValueError('Specify dates and stopped seed')
        if args.spending_mode=='capped' and not args.budget:raise ValueError('Capped mode requires an explicit total budget')
        if args.spending_mode=='available_credit' and any((args.budget,args.rehearsal_budget,args.rehearsal_session_budget)):raise ValueError('Available-credit mode does not accept fixed inference caps')
        rehearsal=None
        if args.rehearsal_starts_at or args.rehearsal_ends_at:
            if not (args.rehearsal_starts_at and args.rehearsal_ends_at):raise ValueError('Specify both rehearsal boundaries')
            rehearsal={'starts_at':args.rehearsal_starts_at,'ends_at':args.rehearsal_ends_at}
            if args.spending_mode=='capped':rehearsal.update(inference_budget_usd=args.rehearsal_budget or '10',session_inference_budget_usd=args.rehearsal_session_budget or '2')
        c=prepare(args.directory,total=args.budget,starts=args.starts_at,ends=args.ends_at,seed=args.seed,rehearsal=rehearsal,spending_mode=args.spending_mode)
        result={k:c[k] for k in ('service_id','week_starts_at','week_ends_at','spending_mode','weekly_total_usd') if k in c}
        if c.get('rehearsal'):result['rehearsal']=c['rehearsal']
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
