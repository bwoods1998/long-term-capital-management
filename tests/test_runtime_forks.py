"""Frozen fork protocol and mocked cloud lifecycle. No provider calls."""
from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import fork_runtime as f
from host_runtime import save_bundle
from portfolio_runtime.sail_host import freeze_bundle,encoded,sha
from portfolio_runtime.provider import Client,canonical


def rid(prefix):return prefix+'_'+str(uuid.uuid4())


class ForkTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.source=self.root/'source';self.source.mkdir()
        self.run=self.root/'main';self.run.mkdir();self.directory=self.root/'forks'
        self.at=int(datetime.now(timezone.utc).timestamp())
        self.companies=[]
        for index,symbol in enumerate(f.SYMBOLS):
            facts={name:[{'tag':tag,'unit':'USD','observations':[{'start':'2025-01-01','end':'2025-12-31','val':val}]}]
                   for name,tag,val in [('operating_cash','NetCashProvidedByUsedInOperatingActivities',100),('capital_spending','PaymentsToAcquirePropertyPlantAndEquipment',25),('net_income','NetIncomeLoss',50)]}
            self.companies.append({'symbol':symbol,'cik':str(index+1).zfill(10),'facts':facts,'sha256':'a'*64,'source':'https://example.com/public'})
        self.data={'companies':self.companies,'overview':[{'symbol':c['symbol'],'name':'Synthetic '+c['symbol']} for c in self.companies]+[{'symbol':'AAPL','name':'Additional context only'}],'universe':{}}
        raw=canonical(self.data).encode()
        self.config={'schema_version':1,'run_id':'main-test','account_created_at':'2026-09-13T00:00:00Z','evidence_sha256':sha(raw),
                     'key_fingerprint':'a'*64,'started_epoch':self.at,'ends_epoch':self.at+18000,'cloud_budget_usd':'3.5',
                     'branch_allocations':[{'id':key,'reserved_usd':'2'} for key in f.ARMS]}
        (self.run/'run.json').write_text(canonical(self.config));(self.source/'data').mkdir();(self.source/'data/sp500-evidence.json').write_bytes(raw)
        (self.source/'portfolio_runtime').mkdir();names=[]
        for name in ('provider','research','accounting','runner'):
            file='portfolio_runtime/'+name+'.py';shutil.copy(ROOT/file,self.source/file);names.append(file)
        names.append('data/sp500-evidence.json')
        self.template=freeze_bundle(self.source,names,self.config,deadline=datetime.fromtimestamp(self.at+18000,timezone.utc).isoformat())
        save_bundle(self.run/'host'/'bundle',self.template)
        self.deployment={'contract':{'config_sha256':sha(encoded(self.config)),'app_id':rid('app')},'installed':True,
                         'policy_contract':'http','inference_secret':'existing_inference_only','cloud_cost_bound_usd':'.10'}
        (self.run/'host'/'deployment.json').write_text(canonical(self.deployment))
    def tearDown(self):self.temp.cleanup()
    def prepare(self):return f.prepare(self.run/'run.json',self.directory,clock=lambda:self.at)
    def experiment(self,api=None):return f.ForkExperiment(self.directory,api=api or (lambda *a:{}),box_factory=lambda _:None,clock=lambda:self.at+1200,sleeper=lambda _:None)
    def test_offline_prepare_matches_focal_information_and_bounds_both_arms(self):
        result=self.prepare();self.assertEqual(result['logical_requests'],10);self.assertEqual(result['network_requests'],0)
        protocol,state=self.experiment().read();self.assertEqual(state['phase'],'prepared')
        configs=[json.loads(f.load_bundle(self.directory/key/'bundle')['files']['config/run.json']) for key in f.ARMS]
        for left,right in zip(configs[0]['assigned_tasks'],configs[1]['assigned_tasks']):
            self.assertEqual(left['body']['input'][-1],right['body']['input'][-1]);self.assertNotEqual(left['body']['input'][0],right['body']['input'][0])
            self.assertEqual(left['body']['model'],right['body']['model']);self.assertNotIn('supercache_write',left['body']['metadata'])
        for config in configs:
            self.assertTrue(config['research_only']);self.assertNotIn('publish_url',config);self.assertEqual(len(config['assigned_task_ids']),5)
        for arm in protocol['arms'].values():self.assertLessEqual(Decimal(arm['request_holds_usd']),2)
        seed=json.loads(f.load_bundle(self.directory/'seed'/'bundle')['files']['config/run.json'])
        self.assertNotIn('assigned_tasks',seed);self.assertNotIn('state_dir',seed)
        with self.assertRaises(ValueError):self.prepare()
    def test_missing_parent_allocations_or_expired_window_fails_offline(self):
        self.config['branch_allocations']=[];(self.run/'run.json').write_text(canonical(self.config))
        with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.directory.exists())
    def test_changed_frozen_bundle_is_rejected_before_provider_calls(self):
        self.prepare();(self.directory/'fork-context'/'bundle'/'config/run.json').write_text('{}')
        with self.assertRaises(ValueError):self.experiment().read()
    def test_parent_proof_required_and_cloud_bound_checked_before_creation(self):
        self.prepare();calls=[]
        rates={k:10**10 for k in ('vcpu_second_usd_nanos','memory_gib_second_usd_nanos','state_disk_gib_second_usd_nanos','s_creation_usd_nanos')}
        experiment=self.experiment(lambda *args:calls.append(args) or {'rates':rates})
        with patch.object(experiment,'parent_allocation_proof',side_effect=ValueError('missing holds')),self.assertRaises(ValueError):experiment.provision()
        self.assertEqual(calls,[])
        with patch.object(experiment,'parent_allocation_proof',return_value=({'allocations':'confirmed'},self.deployment)),self.assertRaises(ValueError):experiment.provision()
        self.assertTrue(all(call[0]=='GET' for call in calls))
    def test_duplicate_provision_uses_one_seed_two_forks_and_saved_policy(self):
        self.prepare();calls=[];records={};root=self.directory
        class Host:
            def __init__(self,key):self.key=key;self.state={'installed':False,'started':False};records[key]=self
            def create(self,*args):self.state.setdefault('created',1)
            def _read(self):return self.state
            def bind_policy(self,*args):self.state['policy_bound']=True
            def install(self,bundle):self.state['installed']=True;self.bundle=bundle
            def checkpoint_seed(self):self.state.setdefault('checkpoint',rid('sbcp'));return self.state['checkpoint']
            def fork_research(self,seed,bundle,name):self.state.setdefault('source_checkpoint',seed.checkpoint_seed());self.state.setdefault('created',1)
            def start(self):self.state['started']=True
        def host(key,*_):return records.get(key) or Host(key)
        rates={'vcpu_second_usd_nanos':1,'memory_gib_second_usd_nanos':1,'state_disk_gib_second_usd_nanos':1,'s_creation_usd_nanos':1}
        def api(*args):calls.append(args);return {'rates':rates} if args[0]=='GET' else {'policy_id':rid('hp')}
        experiment=self.experiment(api)
        with patch.object(experiment,'parent_allocation_proof',return_value=({'allocations':'confirmed'},self.deployment)),patch.object(experiment,'host',side_effect=host):
            experiment.provision();experiment.provision()
        self.assertEqual(set(records),{'seed',*f.ARMS});self.assertEqual(len([c for c in calls if c[0]=='POST']),1)
        self.assertFalse(records['seed'].state['started'])
        for key in f.ARMS:self.assertEqual(records[key].state['source_checkpoint'],records['seed'].state['checkpoint'])
    def fixture_receipt(self,key='fork-context',count=5):
        bundle=f.load_bundle(self.directory/key/'bundle');config=json.loads(bundle['files']['config/run.json']);database=self.root/(key+'.sqlite')
        def transport(method,route,body=None,identity=None):
            packet=json.loads(body['input'][-1]['content']);company=packet['evidence'];claims=[]
            for metric,variants in company['facts'].items():
                variant=variants[0];obs=variant['observations'][0];claims.append({'symbol':company['symbol'],'metric':metric,'tag':variant['tag'],'unit':variant['unit'],'start':obs['start'],'end':obs['end'],'value':obs['val']})
            result={'thesis':'Synthetic test evidence.','claims':claims,'questions':[],'targets':[],'confidence':'low','abstain_reason':None}
            return {'id':'resp_'+packet['symbol'],'status':'completed','model':body['model'],'output':[{'type':'message','content':[{'type':'output_text','text':canonical(result)}]}],
                    'usage':{'input_tokens':100,'output_tokens':100,'input_tokens_details':{'cached_tokens':0}}}
        client=Client(database,config,transport=transport,clock=lambda:config['started_epoch']+1000)
        for task in config['assigned_tasks'][:count]:client.step(client.submit_intent(task['id'],task['profile'],task['body']))
        receipt={'schema_version':1,'research_only':True,'run_id':config['run_id'],'cost':client.totals(),
                 'tasks':[{k:row[k] for k in ('task_id','profile','status','response','cost','created','updated')} for row in client.rows()]}
        sid=rid('sb')
        class Host:
            def _read(self):return {'sailbox_id':sid}
            def attach(self):return SimpleNamespace(fs=SimpleNamespace(read=lambda _:encoded(receipt)))
            def backup_state(self,destination):
                destination=Path(destination);destination.mkdir(parents=True)
                src=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True);dst=sqlite3.connect(destination/'requests.sqlite')
                try:src.backup(dst)
                finally:src.close();dst.close()
                raw=(destination/'requests.sqlite').read_bytes()
                (destination/'receipt.json').write_text(canonical({'sailbox_id':sid,'manifest_sha256':bundle['sha256'],
                  'files':{'requests.sqlite':{'sha256':sha(raw),'bytes':len(raw)}}}))
        return receipt,Host()
    def test_collector_verifies_exact_requests_and_frozen_usage_before_reporting(self):
        self.prepare();receipt,host=self.fixture_receipt();experiment=self.experiment()
        with patch.object(experiment,'host',return_value=host):
            observed=experiment.collect('fork-context');self.assertEqual(observed,receipt)
            receipt['tasks'][0]['cost']='0'
            with self.assertRaises(ValueError):experiment.collect('fork-context')
        report=f.summarize(self.directory);self.assertEqual(report['completed'],5);self.assertEqual(report['unknown_request_costs'],5)
        self.assertTrue(all(row['source_checks_passed'] for row in report['rows'] if row['arm']=='fork-context'))
        self.assertNotIn('response',canonical(report));self.assertNotIn('Synthetic test evidence',canonical(report))
    def test_unadmitted_tasks_are_known_zero_after_verified_finite_receipt(self):
        self.prepare();receipt,host=self.fixture_receipt(count=3);experiment=self.experiment()
        with patch.object(experiment,'host',return_value=host):experiment.collect('fork-context')
        report=f.summarize(self.directory);not_admitted=[row for row in report['rows'] if row['status']=='not_admitted']
        self.assertEqual(len(not_admitted),2);self.assertTrue(all(row['known_cost_usd']=='0' for row in not_admitted))
    def test_offline_report_rejects_changed_saved_receipt_or_grader(self):
        self.prepare();receipt,host=self.fixture_receipt();experiment=self.experiment()
        with patch.object(experiment,'host',return_value=host):experiment.collect('fork-context')
        path=self.directory/'fork-context'/'receipt.json';original=path.read_bytes()
        receipt['tasks'][0]['cost']='0';path.write_bytes(encoded(receipt))
        with self.assertRaisesRegex(ValueError,'receipt digest'):f.summarize(self.directory)
        path.write_bytes(original)
        original_read=Path.read_bytes
        def changed(path):
            raw=original_read(path)
            return raw+b'\n# changed' if path==ROOT/'portfolio_runtime/research.py' else raw
        with patch.object(Path,'read_bytes',changed),self.assertRaisesRegex(ValueError,'implementation changed'):f.summarize(self.directory)
    def test_cleanup_lookup_failure_does_not_skip_other_owned_resources(self):
        self.prepare();calls=[];sid=rid('sb')
        (self.directory/'fork-context'/'host.json').write_text(canonical({'sailbox_id':None,'create_body':{'app_id':rid('app'),'name':'uncertain-fork'}}))
        (self.directory/'seed'/'host.json').write_text(canonical({'sailbox_id':sid,'installed':False}))
        def api(*args):
            calls.append(args)
            if args[1].startswith('/v1/sailboxes?'):raise TimeoutError('lookup unavailable')
            return {}
        report=self.experiment(api).cleanup()
        self.assertEqual(report['phase'],'needs_attention')
        self.assertIn(('POST','/v1/sailboxes/'+sid+'/terminate',{}),calls)
    def test_cleanup_never_targets_main_host_and_retains_unknown_resource_costs(self):
        self.prepare();calls=[];ids=[]
        for key in ('seed',*f.ARMS):
            sid=rid('sb');ids.append(sid)
            (self.directory/key/'host.json').write_text(canonical({'sailbox_id':sid,'installed':False}))
        def api(*args):calls.append(args);return {}
        report=self.experiment(api).cleanup()
        terminated=[call[1].split('/')[3] for call in calls if call[0]=='POST']
        self.assertEqual(set(terminated),set(ids));self.assertEqual(report['phase'],'finished')
        self.assertEqual(report['resource_costs'],{key:None for key in ('seed',*f.ARMS)})
    def test_run_cleanup_still_happens_on_provision_failure_without_replacement(self):
        self.prepare();experiment=self.experiment();calls=[]
        with patch.object(experiment,'provision',side_effect=RuntimeError('uncertain create')),patch.object(experiment,'cleanup',side_effect=lambda:calls.append('cleanup') or {}),self.assertRaises(RuntimeError):experiment.run()
        self.assertEqual(calls,['cleanup'])


if __name__=='__main__':unittest.main()
