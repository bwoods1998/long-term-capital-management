"""Synthetic, offline Sailbox lifecycle tests executing the actual frozen checker."""
from contextlib import nullcontext
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import cloud_research as cloud
import overnight_cloud as worker
import portfolio as p
from scripts import overnight_verify_guest as guest
from test_overnight_review import fixture
from test_cloud_research import RATES, ISOLATED


class OvernightCloudTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.remote=self.root/'remote';self.remote.mkdir()
        self.status='running';self.handles={};self.executions=0
        self.box=SimpleNamespace(fs=SimpleNamespace(write=Mock(side_effect=self.write),read=Mock(side_effect=self.read)),
                                 exec=Mock(side_effect=self.execute))
        self.sdk=SimpleNamespace(App=SimpleNamespace(find=Mock(return_value=SimpleNamespace(id='app_synthetic'))),
                                  Sailbox=SimpleNamespace(from_id=Mock(return_value=self.box)))
        self.api=Mock(side_effect=self.provider)
        for target,name,value in [(cloud,'SESSION_ROOT',self.root/'sessions'),
                                  (cloud,'_credentials',lambda:nullcontext()),
                                  (p,'credential_fingerprint',lambda:'a'*64),
                                  (worker.sandbox,'api',self.api),
                                  (worker.subprocess,'Popen',Mock(return_value=SimpleNamespace(pid=123)))]:
            obj=patch.object(target,name,value);obj.start();self.addCleanup(obj.stop)
        obj=patch.dict('sys.modules',{'sail':self.sdk});obj.start();self.addCleanup(obj.stop)
        company,self.draft=fixture()
        self.companies={s:{**deepcopy(company),'symbol':s} for s in worker.review.SYMBOLS}
        self.directory=Path(worker.prepare('synthetic',self.companies,p.iso(worker.time.time()+3600))['session'])

    def path(self,path):
        return self.remote/Path(path).relative_to(worker.REMOTE)

    def write(self,path,raw,**kwargs):
        target=self.path(path);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)

    def read(self,path):return self.path(path).read_bytes()

    def provider(self,method,route,body=None,request_id=None):
        if route=='/v1/sailboxes/spend':return {'rates':RATES}
        if route.startswith('/v1/sailboxes/spend?'):
            return {'estimated_total_cost_usd_nanos':7000000,'finalized_cost_usd_nanos':7000000,'estimated_active_cost_usd_nanos':0}
        if method=='POST' and route=='/v1/sailboxes':return {'sailbox_id':'sb_synthetic'}
        if route.endswith('/listeners'):return {'data':[]}
        if method=='POST':
            self.status={'sleep':'sleeping','resume':'running','terminate':'terminated'}[route.rsplit('/',1)[-1]]
            return {}
        if method=='GET' and route=='/v1/sailboxes/sb_synthetic':return {**ISOLATED,'status':self.status}
        raise AssertionError('Unexpected provider operation')

    def execute(self,command,**kwargs):
        self.assertEqual(command.split()[:2],['python3','scripts/overnight_verify_guest.py'])
        key=kwargs['idempotency_key']
        if key not in self.handles:
            self.executions+=1
            call=command.split()[-1]
            guest.execute(self.remote,json.loads((self.remote/'requests'/(call+'.json')).read_text()))
            self.handles[key]=SimpleNamespace(wait=Mock(return_value=SimpleNamespace(exit_code=0,timed_out=False)))
        return self.handles[key]

    def test_prepare_never_creates_and_upload_contains_no_credentials_or_ledger(self):
        self.api.assert_not_called();self.sdk.App.find.assert_not_called()
        directory,state=cloud._load(self.directory);files=worker._bundle(directory,state)
        self.assertEqual(len(files),12)
        self.assertNotIn(('a'*64).encode(),b''.join(files.values()))
        self.assertFalse(any('.env' in k or 'sqlite' in k or 'portfolio.py' in k for k in files))
        worker.create(self.directory)
        self.assertEqual(worker.summary(self.directory)['phase'],'ready')
        self.assertEqual(set(files),{str(p.relative_to(self.remote)) for p in self.remote.rglob('*') if p.is_file()})

    def test_actual_draft_checks_survive_sleep_and_resume_with_same_receipt(self):
        worker.create(self.directory)
        first=worker.verify(self.directory,'MSFT',self.draft)
        self.assertTrue(first['checks']['valid']);self.assertFalse(first['persistence_verified'])
        self.assertEqual(self.status,'sleeping')
        second=worker.verify(self.directory,'MSFT',self.draft)
        self.assertTrue(second['persistence_verified'])
        self.assertEqual(second['receipt_sha256'],first['receipt_sha256'])
        self.assertEqual(self.executions,1)
        self.assertTrue(any(c.args[1].endswith('/resume') for c in self.api.call_args_list))
        changed=deepcopy(self.draft);changed['headline']='Changed draft'
        with self.assertRaisesRegex(ValueError,'different frozen'):worker.verify(self.directory,'MSFT',changed)
        self.assertEqual(self.executions,1)

    def test_mechanical_failure_is_a_matching_result_not_approval(self):
        worker.create(self.directory)
        draft=deepcopy(self.draft);draft['cash_flow_bridge']['remainder']='999'
        value=worker.verify(self.directory,'MSFT',draft)
        self.assertFalse(value['checks']['valid'])
        self.assertFalse(value['checks']['checks']['bridge_arithmetic'])
        self.assertTrue(value['checks']['requires_editorial_review'])

    def test_uncertain_exec_reuses_identity_after_new_controller_invocation(self):
        worker.create(self.directory)
        normal=self.execute
        def uncertain(command,**kwargs):
            handle=normal(command,**kwargs)
            if self.box.exec.call_count==1:handle.wait.side_effect=[TimeoutError('unknown'),SimpleNamespace(exit_code=0,timed_out=False)]
            return handle
        self.box.exec.side_effect=uncertain
        with self.assertRaises(TimeoutError):worker.verify(self.directory,'MSFT',self.draft)
        worker.verify(self.directory,'MSFT',self.draft)
        self.assertEqual(self.executions,1)
        self.assertEqual(self.box.exec.call_args_list[0].kwargs['idempotency_key'],self.box.exec.call_args_list[1].kwargs['idempotency_key'])

    def test_uncertain_sleep_is_reconciled_before_persistence_is_claimed(self):
        worker.create(self.directory)
        normal=self.provider;keys=[]
        def uncertain(method,route,body=None,request_id=None):
            if route.endswith('/sleep'):
                keys.append(request_id)
                if len(keys)==1:raise TimeoutError('sleep not confirmed')
            return normal(method,route,body,request_id)
        self.api.side_effect=uncertain
        with self.assertRaises(TimeoutError):worker.verify(self.directory,'MSFT',self.draft)
        self.assertFalse(worker.summary(self.directory)['persistence_verified'])
        value=worker.verify(self.directory,'MSFT',self.draft)
        self.assertTrue(value['persistence_verified']);self.assertEqual(len(keys),2);self.assertEqual(keys[0],keys[1])

    def test_source_tamper_or_remote_receipt_tamper_is_rejected(self):
        worker.create(self.directory)
        source=self.directory/'bundle/companies/MSFT.json';source.write_bytes(source.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'Changed verifier'):worker.verify(self.directory,'MSFT',self.draft)
        self.assertEqual(self.executions,0)

    def test_creation_ambiguity_cannot_allocate_a_replacement(self):
        normal=self.provider
        def ambiguous(method,route,body=None,request_id=None):
            if method=='POST' and route=='/v1/sailboxes':raise TimeoutError('unknown creation')
            return normal(method,route,body,request_id)
        self.api.side_effect=ambiguous
        with patch.object(cloud,'finish') as finish:
            with self.assertRaises(TimeoutError):worker.create(self.directory)
            finish.assert_called_once()
        with self.assertRaisesRegex(ValueError,'already attempted'):worker.create(self.directory)
        self.assertEqual(sum(c.args[:2]==('POST','/v1/sailboxes') for c in self.api.call_args_list),1)

    def test_unknown_prior_compute_blocks_and_finished_cleanup_works_after_deadline(self):
        prior=cloud.SESSION_ROOT/'previous';prior.mkdir()
        (prior/'state.json').write_text(json.dumps({'phase':'created','finished':False}))
        with self.assertRaisesRegex(ValueError,'Earlier compute'):worker.create(self.directory)
        self.api.assert_not_called();(prior/'state.json').unlink();prior.rmdir()
        worker.create(self.directory)
        _,state=cloud._load(self.directory)
        with patch.object(worker.time,'time',return_value=state['deadline']+10):
            with self.assertRaisesRegex(ValueError,'deadline'):worker.verify(self.directory,'MSFT',self.draft)
            finished=worker.finish(self.directory)
        self.assertTrue(finished['finished']);self.assertEqual(finished['costs']['estimated_total_cost_usd'],'0.007')

    def test_cleanup_before_lazy_creation_records_known_zero_without_network(self):
        result=worker.finish(self.directory)
        self.assertTrue(result['finished']);self.assertEqual(result['costs']['estimated_total_cost_usd'],'0')
        self.assertTrue(worker.finish(self.directory)['finished'])
        self.api.assert_not_called();self.sdk.App.find.assert_not_called()


if __name__=='__main__':unittest.main()
