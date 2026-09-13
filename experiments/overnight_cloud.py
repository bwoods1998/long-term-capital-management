"""One bounded Sailbox verifies actual overnight drafts; inference stays local."""
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

import cloud_research as cloud
import overnight_review as review
import portfolio as p
import sail_sandbox as sandbox
import sail_tracking as tracking

ROOT = Path(__file__).resolve().parent
REMOTE = '/workspace/overnight-verifier'
FILES = ('overnight_review.py', 'scripts/overnight_verify_guest.py')
MAX_SECONDS = 8 * 3600
MAX_COMPUTE_USD = Decimal('0.50')


def prepare(name, companies, deadline):
    """Freeze nine source packets and public checker code offline; no resource."""
    if not isinstance(name, str) or not re.fullmatch('[a-z0-9-]{1,60}', name):
        raise ValueError('Use a bounded overnight session name')
    if not isinstance(companies, dict) or set(companies) != set(review.SYMBOLS):
        raise ValueError('Supply the nine frozen company validator packets')
    for symbol, company in companies.items():
        if company.get('symbol') != symbol:
            raise ValueError('Company symbol mismatch')
        review._company(company)
    end = datetime.fromisoformat(deadline.replace('Z','+00:00'))
    if end.tzinfo is None or not time.time() < end.timestamp() <= time.time()+MAX_SECONDS:
        raise ValueError('Use an absolute deadline within eight hours')
    directory = cloud.SESSION_ROOT / ('overnight-' + name)
    cloud.SESSION_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.mkdir(mode=0o700)
    bundle = directory / 'bundle'; bundle.mkdir(mode=0o700)
    files = {name:(ROOT/name).read_bytes() for name in FILES}
    files.update({'companies/'+s+'.json':(p.encoded(companies[s])+'\n').encode() for s in review.SYMBOLS})
    if sum(map(len,files.values())) > 500000:
        raise ValueError('Frozen verifier bundle exceeds its allowance')
    manifest = {'schema_version':1,'kind':'overnight-company-checks',
                'files':[{'path':name,'bytes':len(raw),'sha256':sandbox.sha(raw)} for name,raw in sorted(files.items())],
                'max_checks':9,'guest_network':'no_network','guest_credentials':False}
    for name,raw in files.items():
        path=bundle/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    raw=(p.encoded(manifest)+'\n').encode();(bundle/'manifest.json').write_bytes(raw)
    state={'schema_version':1,'kind':'overnight-company-checks','phase':'prepared','finished':False,
           'name':'overnight-verifier-'+uuid.uuid4().hex,'steps':[],'tool_receipts':{},
           'manifest_sha256':sandbox.sha(raw),'deadline':end.timestamp(),'max_seconds':MAX_SECONDS,
           'compute_allowance_usd':str(MAX_COMPUTE_USD),'credential_fingerprint':p.credential_fingerprint(),
           'operations':{key:str(uuid.uuid4()) for key in ('create','terminate')},
           'persistence_verified':False}
    cloud._write(directory/'state.json',state)
    return {'session':str(directory),'manifest_sha256':state['manifest_sha256'],'phase':'prepared'}


def _bundle(directory,state):
    bundle=directory/'bundle';raw=(bundle/'manifest.json').read_bytes()
    if sandbox.sha(raw)!=state['manifest_sha256']:raise ValueError('Changed verifier manifest')
    manifest=json.loads(raw)
    expected=set(FILES)|{'companies/'+s+'.json' for s in review.SYMBOLS}
    if len(manifest['files'])!=len(expected) or {f['path'] for f in manifest['files']}!=expected:
        raise ValueError('Unexpected verifier files')
    result={'manifest.json':raw}
    for item in manifest['files']:
        path=bundle/item['path']
        if path.is_symlink() or path.parent.is_symlink() or not path.is_file():raise ValueError('Invalid verifier path')
        raw=path.read_bytes()
        if len(raw)!=item['bytes'] or sandbox.sha(raw)!=item['sha256']:raise ValueError('Changed verifier code or evidence')
        result[item['path']]=raw
    if sum(map(len,result.values()))>500000:raise ValueError('Verifier envelope exceeded')
    return result


def _bound(state):
    if p.credential_fingerprint()!=state['credential_fingerprint']:raise ValueError('Original credential required')
    if state.get('finished') or time.time()>=state['deadline']:raise ValueError('Verifier deadline reached')
    if not state.get('isolation_verified') or not state.get('sailbox_id'):raise ValueError('Isolated verifier not ready')


def create(directory):
    """Explicit paid resource creation; uncertain creation never makes another box."""
    import sail
    directory,state=cloud._load(directory)
    with cloud._lock(cloud.SESSION_ROOT),cloud._lock(directory),cloud._credentials():
        _,state=cloud._load(directory);files=_bundle(directory,state)
        if state['phase']!='prepared':raise ValueError('Creation already attempted; reconcile original resource')
        if p.credential_fingerprint()!=state['credential_fingerprint'] or time.time()>=state['deadline']:
            raise ValueError('Original credential and unexpired work window required')
        prior=Decimal('0.010')
        for path in cloud.SESSION_ROOT.glob('*/state.json'):
            if path.parent==directory:continue
            old=json.loads(path.read_text())
            if old['phase']=='prepared':continue
            if not old.get('finished') or not old.get('costs'):raise ValueError('Earlier compute requires cleanup/accounting')
            prior+=Decimal(old['costs']['estimated_total_cost_usd'])
        if prior+MAX_COMPUTE_USD>Decimal('4'):raise ValueError('Shared four-dollar compute ceiling exhausted')
        rates=sandbox.api('GET','/v1/sailboxes/spend').get('rates')
        keys=('vcpu_second_usd_nanos','memory_gib_second_usd_nanos','state_disk_gib_second_usd_nanos','s_creation_usd_nanos')
        if not isinstance(rates,dict) or any(type(rates.get(k)) is not int or rates[k]<0 for k in keys):
            raise ValueError('Unknown compute rates')
        bound=Decimal((rates[keys[0]]+2*rates[keys[1]]+8*rates[keys[2]])*(MAX_SECONDS+180)+rates[keys[3]])/10**9
        if bound>MAX_COMPUTE_USD:raise ValueError('Resource prices exceed the frozen allowance')
        state.update(started=time.time(),rates=rates,configured_maximum_usd=str(bound))
        state['app_id']=sail.App.find('portfolio-living-case',mint_if_missing=True).id
        cloud._record(directory,state,'creating')
        monitor=subprocess.Popen([sys.executable,str(ROOT/'sail_sandbox.py'),'_watchdog',str(directory/'state.json')],
                                 stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        state['watchdog_pid']=monitor.pid;cloud._write(directory/'state.json',state)
        try:
            row=sandbox.api('POST','/v1/sailboxes',sandbox.create_body(state['app_id'],state['name']),state['operations']['create'])
            state['sailbox_id']=sandbox._identifier(row.get('sailbox_id'));cloud._record(directory,state,'created')
            sandbox.validate_isolation(cloud._wait(state,{'running'}))
            if sandbox.api('GET','/v1/sailboxes/'+state['sailbox_id']+'/listeners').get('data')!=[]:
                raise ValueError('Unexpected listener')
            box=sail.Sailbox.from_id(state['sailbox_id'])
            for name,raw in files.items():box.fs.write(REMOTE+'/'+name,raw,create_parents=True,mode=0o644)
            for name,raw in files.items():
                if box.fs.read(REMOTE+'/'+name)!=raw:raise ValueError('Upload readback mismatch')
            state['isolation_verified']=True;cloud._record(directory,state,'ready')
        except BaseException:
            cloud._record(directory,state,'needs_attention')
            cloud.finish(directory)
            raise
    return summary(directory)


def _awake(directory,state,box):
    _bound(state)
    row=sandbox.api('GET','/v1/sailboxes/'+state['sailbox_id'])
    if state.get('pending_sleep'):
        if row.get('status') not in {'sleeping','paused'}:
            sandbox.api('POST','/v1/sailboxes/'+state['sailbox_id']+'/sleep',{},state['pending_sleep'])
            row=cloud._wait(state,{'sleeping'})
        state.pop('pending_sleep');cloud._record(directory,state,'sleeping')
    if row.get('status') in {'sleeping','paused'}:
        key=state.setdefault('pending_resume',str(uuid.uuid4()))
        cloud._record(directory,state,'resuming')
        sandbox.api('POST','/v1/sailboxes/'+state['sailbox_id']+'/resume',{},key)
        row=cloud._wait(state,{'running'})
    if row.get('status')!='running':raise ValueError('Verifier is not running')
    sandbox.validate_isolation(row)
    if state.pop('pending_resume',None):cloud._record(directory,state,'resumed')
    if state.get('persistence_probe') and not state['persistence_verified']:
        if not any(event['phase']=='sleeping' for event in state['steps']):
            raise ValueError('Persistence proof requires observed sleep')
        probe=state['persistence_probe'];raw=box.fs.read(REMOTE+'/receipts/'+probe['key']+'.json')
        if sandbox.sha(raw)!=probe['sha256']:raise ValueError('Receipt did not persist across sleep/resume')
        state['persistence_verified']=True;cloud._record(directory,state,'persistence_verified')


def verify(directory,symbol,draft):
    """One immutable actual draft per company, including mechanically invalid drafts."""
    import sail
    directory,_=cloud._load(directory)
    with cloud._lock(directory),cloud._credentials():
        _,state=cloud._load(directory);_bound(state);files=_bundle(directory,state)
        if symbol not in review.SYMBOLS:raise ValueError('Unknown company')
        if (ROOT/'overnight_review.py').read_bytes()!=files['overnight_review.py']:
            raise ValueError('Local verifier differs from its frozen guest version')
        company=json.loads(files['companies/'+symbol+'.json'])
        expected=review.check_case(draft,company)
        key=p.digest({'manifest_sha256':state['manifest_sha256'],'symbol':symbol})
        request={'schema_version':1,'call_key':key,'symbol':symbol,'manifest_sha256':state['manifest_sha256'],'draft':draft}
        if len(p.encoded(request).encode())>60000:raise ValueError('Draft exceeds verification envelope')
        receipts=directory/'verifications';receipts.mkdir(exist_ok=True,mode=0o700);path=receipts/(symbol+'.json')
        if path.exists():
            saved=json.loads(path.read_text())
            if saved['request']!=request:raise ValueError('Company already has a different frozen verification draft')
        else:
            saved={'request':request,'exec_key':str(uuid.uuid4()),'receipt':None};cloud._write(path,saved)
        box=sail.Sailbox.from_id(state['sailbox_id'])
        _awake(directory,state,box)
        if saved['receipt'] is None:
            raw=p.encoded(request).encode();remote=REMOTE+'/requests/'+key+'.json'
            box.fs.write(remote,raw,create_parents=True,mode=0o644)
            if box.fs.read(remote)!=raw:raise ValueError('Draft upload mismatch')
            with tracking.stage('company-verification',agent='SailboxVerifier'):
                done=box.exec('python3 scripts/overnight_verify_guest.py '+key,cwd=REMOTE,timeout=60,
                              idempotency_key=saved['exec_key'],output_mode='tail').wait()
            if done.exit_code!=0 or done.timed_out:raise ValueError('Remote check incomplete; saved identity retained')
            saved['receipt']=json.loads(box.fs.read(REMOTE+'/receipts/'+key+'.json'));cloud._write(path,saved)
        receipt=saved['receipt']
        wanted={'schema_version':1,'call_key':key,'symbol':symbol,'manifest_sha256':state['manifest_sha256'],
                'request_sha256':p.digest(request),'result':expected,'result_sha256':p.digest(expected)}
        if receipt!=wanted:raise ValueError('Remote company check differs from independent local computation')
        state['tool_receipts'][symbol]={'receipt_sha256':p.digest(receipt),'mechanical_valid':expected['valid']}
        cloud._record(directory,state,'tool_completed',symbol=symbol)
        if not state.get('persistence_probe'):
            raw=box.fs.read(REMOTE+'/receipts/'+key+'.json')
            state['persistence_probe']={'key':key,'sha256':sandbox.sha(raw)}
            state['pending_sleep']=str(uuid.uuid4());cloud._record(directory,state,'sleep_requested')
            sandbox.api('POST','/v1/sailboxes/'+state['sailbox_id']+'/sleep',{},state['pending_sleep'])
            cloud._wait(state,{'sleeping'});state.pop('pending_sleep',None);cloud._record(directory,state,'sleeping')
        return {'symbol':symbol,'checks':expected,'receipt_sha256':p.digest(receipt),
                'manifest_sha256':state['manifest_sha256'],'persistence_verified':state['persistence_verified']}


def finish(directory):
    directory,_=cloud._load(directory)
    with cloud._lock(directory),cloud._credentials():
        _,state=cloud._load(directory)
        if (state['phase']=='prepared' or state.get('finished') is True) and not state.get('app_id') and not state.get('sailbox_id'):
            # A campaign can end before any usable draft triggers lazy creation.
            # That is known zero compute, not an ambiguous resource allocation.
            state['finished']=True
            state['costs']={'estimated_total_cost_usd':'0','finalized_cost_usd':'0','estimated_active_cost_usd':'0'}
            cloud._record(directory,state,'closed')
            return summary(directory)
        return cloud.finish(directory)


def summary(directory):
    _,state=cloud._load(directory)
    return {k:state.get(k) for k in ('phase','finished','costs','manifest_sha256','persistence_verified')} | {
        'verified_companies':len(state['tool_receipts']), 'deadline':p.iso(state['deadline']),
        'scope':'Matching frozen mechanical checks; not independent financial approval.'}
