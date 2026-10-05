"""Predeclared developmental cards through ordinary gym_run, a fabricated Gym only."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from league.swarm import cards, mechanism, settings as S
from league.swarm.researcher import Researcher
from league.swarm.store import SwarmStore

CODE = 'NEEDS = {"roots": ["SPY"], "dte": [0, 5], "cadence": 30}\nPARAMS = {"signal_on": 1, "threshold": 600}\ndef decide(ctx):\n    if PARAMS["signal_on"] and ctx.minute < PARAMS["threshold"]:\n        return []\n    return []\n'
NEW = CODE + '\n# distinct unqualified development fixture\n'
CARD = {'hypothesis':'A fabricated late-selling condition proposes a rebound over the next session; this is a software fixture with no market-evidence claim.',
        'mechanism_class':'reversal_liquidity','inputs':['underlying_price','clock'],'holding':'days_1_3',
        'cost':{'hurdle':.08,'why':'Unmeasured synthetic estimate of spread and fee cost as a fraction of maximum loss.'},
        'comparison':'The same debit exposure without the declared fabricated late-selling condition.',
        'ablation':{'param':'signal_on','off':0},
        'falsification':'Reject if the signal fails the unchanged ordinary t 0.75 comparison threshold or either arm is untestable.'}

class FabricatedGym:
    def __init__(self):self.jobs=[];self.mode='thin';self.current='synthetic-evaluator-1'
    def image(self,kind):return 'fabricated-no-market-image'
    def bundle(self):return self.current
    def run(self,job,timeout=None,late=None):
        self.jobs.append(job)
        start=job.start or '2022-01-03';on=job.params.get('signal_on',1)!=0
        n=12 if self.mode in ('failed','passed','identical') else 1
        pnl = (30. if on else -10.) if self.mode=='passed' else (-30. if on else -10.)
        rows=[] if job.purpose=='probe' else [{'day':start[:8]+f'{i+1:02d}', 'pnl':(-5. if self.mode=='identical' else pnl)+(i%3),
               'max_loss':150.,'fees':1.,'type':'debit_vertical','entry_minute':600,'sessions_held':1,
               'dte':3,'moneyness':0.,'width':.3 if self.mode=='invalid' and not on else .01} for i in range(n)]
        return {'run_id':f'fabricated-{len(self.jobs)}-{job.purpose}-{job.version}', 'status':'ok','trials':1,
                'gym_image':self.image('gym'),'gym_bundle':self.bundle(),'fill_model':'fabricated-fees',
                'train_from':'2022-01-03','summary':{'trades':len(rows),'days':20},'trades':rows,'roots':list(job.roots)}

class DevelopmentCards(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory();self.addCleanup(self.dir.cleanup)
        self.store=SwarmStore(self.dir.name);self.addCleanup(self.store.close)
        self.fam=self.store.add_family({'id':'synthetic-developer','structure':'debit_vertical','roots':['SPY'],
             'mechanism':'A fabricated late-selling condition may predict a rebound; no empirical claim.'},origin='fixture')
        self.fid=self.fam['id'];cards.put(self.store,self.fid,CARD,'debit_vertical')
        self.settings=copy.deepcopy(S.DEFAULTS)
        self.settings['researcher'].update(development_cards=True,probe_year=2022,mechanism_test=False)
        self.pool=FabricatedGym();self.r=Researcher(self.store,None,self.pool,self.settings,background=False)
        self.call({'code':CODE,'params':{}}) # Parent registered by normal admission/probe, never add_version directly.
        self.assertEqual(len(self.pool.jobs),1);self.assertEqual(self.pool.jobs[0].purpose,'probe')
        self.settings['researcher']['mechanism_test']={'enabled':True,'mode':'gate'}
        self.parent=self.store.latest_version(self.fid);self.base=cards.card_of(self.store,self.fid)
    def call(self,args):
        out={};v=self.r._execute(self.store.family(self.fid),'gym_run',args,out,author='synthetic-fixture')
        return v,out
    def args(self,code=NEW):
        return {'code':code,'params':{},'development_card':{'card':copy.deepcopy(CARD),'parent_version':self.parent['n'],
                  'parent_sha':self.parent['sha'],'parent_params':{}}}
    def counts(self):
        f=self.store.family(self.fid)
        return (len(self.store.versions(self.fid)),f['trials'],self.store.lineage_trials(self.fid),len(self.pool.jobs))
    def refuse(self,args,contains):
        before=self.counts();v,o=self.call(args);self.assertEqual(v['status'],'refused',v)
        self.assertIn(contains,v['reason']);self.assertEqual(self.counts(),before);return v,o
    def test_ordinary_zero_trade_probe_records_parent_without_full_train(self):
        f=self.store.family(self.fid)
        self.assertEqual((self.parent['n'],f['trials'],f['best_version'],f['validated_version']),(1,1,None,None))
        self.assertEqual(self.store._one("SELECT COUNT(*) AS n FROM runs WHERE window='probe'")['n'],1)
    def test_fresh_development_gate_ignores_original_broad_and_passed_qualification(self):
        cards.add_evidence(self.store,self.fid,self.base['sha'],1,'mechanism_test','passed',{'fixture':True})
        self.store.add_run(self.fid,1,{'run_id':'synthetic-legacy-broad','status':'ok','trials':0,'summary':{}},
                           window='train',stress=1,purpose='train')
        self.assertIsNone(self.r._mechanism_plan(self.store.family(self.fid),CODE,{}))
        v,o=self.call(self.args());self.assertEqual(v['status'],'mechanism_thin');self.assertEqual(o['trials'],8)
        line=self.r.mechanism_lineage(self.fid);self.assertFalse(line['passed']);self.assertFalse(line['broad'])
        self.assertEqual(cards.card_of(self.store,self.fid),self.base)
        self.assertTrue(line['exposed'])
        [fresh]=[e for e in cards.evidence(self.store,self.fid) if e['card_sha']==self.r._research_card(self.fid)['sha']]
        self.assertTrue(fresh['detail']['exposed']);self.assertFalse(fresh['detail']['blind'])
    def test_exact_retry_reuses_only_binding_verdict_without_new_trials(self):
        self.call(self.args());before=self.counts();v,o=self.call({})
        self.assertEqual(v['status'],'mechanism_thin');self.assertTrue(o['mechanism_test']['stored'])
        self.assertEqual(self.counts(),before)
    def test_card_identity_is_immutable_and_includes_source_overrides_parent(self):
        self.call(self.args());entry=self.r._research_card(self.fid)
        self.assertEqual(entry['binding']['code_sha'],hashlib.sha256(NEW.encode()).hexdigest())
        self.assertEqual(entry['binding']['params'],{});self.assertEqual(entry['binding']['parent_sha'],self.parent['sha'])
        a=self.args();a['development_card']['card']['cost']['hurdle']=.09
        self.refuse(a,'immutable')
        for sql in ['UPDATE development_cards SET version=version','DELETE FROM development_cards']:
            with self.assertRaisesRegex(sqlite3.IntegrityError,'immutable'):self.store._exec(sql)
    def test_no_card_source_or_param_change_cannot_fall_back_to_birth_card(self):
        self.call(self.args());self.refuse({'code':NEW+'\n# changed\n','params':{}},'exact code/override-bound')
        self.refuse({'params':{'threshold':601}},'exact code/override-bound')
    def test_old_source_cannot_be_recarded_to_transfer_qualification(self):
        self.refuse(self.args(CODE),'new source')
    def test_declaration_and_switch_refusals_precede_registration(self):
        a=self.args();a['development_card']['card']['ablation']['param']='missing'
        self.refuse(a,'not in PARAMS')
        a=self.args();a['development_card']['parent_version']=False
        self.refuse(a,'integer')
        a=self.args();a['params']={'threshold':601}
        self.refuse(a,'exact latest parent')
    def test_gate_operator_extension_unseen_and_validation_holds_remain(self):
        for key,value in [('gate_hold',True),('gate_ready',True),('look_inflight',True),
                          ('extension_hold',{'isolation_reserved':True,'version':1})]:
            with self.subTest(key=key):
                self.store.set_state(self.fid,**{key:value})
                try:self.refuse(self.args(),'hold')
                finally:self.store.set_state(self.fid,**{key:None})
    def test_existing_best_pending_validation_is_not_displaced(self):
        self.store.update_family(self.fid,best_version=1)
        self.refuse(self.args(),'awaits Validation')
        self.assertEqual(self.store.family(self.fid)['best_version'],1)
    def test_preflight_race_rechecks_new_hold_before_any_registration(self):
        def hook(*a,**k):
            self.store.set_state(self.fid,gate_hold=True);return {'status':'passed'}
        self.r.preflight=hook;self.refuse(self.args(),'hold')
        self.assertEqual(self.store.family(self.fid)['state']['gate_hold'],True)
    def test_preflight_race_rechecks_parent_before_any_registration(self):
        # The synthetic race simulates another writer's newer parent metadata only.
        def hook(*a,**k):
            self.store._exec('UPDATE versions SET sha=? WHERE family=? AND n=1',('f'*64,self.fid))
            return {'status':'passed'}
        self.r.preflight=hook;self.refuse(self.args(),'actual latest')
        self.assertFalse(cards.development_exists(self.store,self.fid))
    def test_existing_sibling_failures_and_all_N_still_raise_fresh_bound(self):
        sibling=self.store.add_family({'id':'synthetic-sibling','structure':'debit_vertical','roots':['SPY'],
            'mechanism':'A fabricated sibling carries historical failed research within this same lineage.'},origin='fixture',parent=self.fid)
        cards.put(self.store,sibling['id'],CARD,'debit_vertical')
        cards.add_evidence(self.store,sibling['id'],cards.card_of(self.store,sibling['id'])['sha'],7,'mechanism_test','failed',{'below_base':True})
        self.store.bump(sibling['id'],trials=23)
        n=self.store.lineage_trials(self.fid);self.call(self.args())
        line=self.r.mechanism_lineage(self.fid)
        self.assertEqual(line['failed'],1);self.assertGreater(mechanism.bound(mechanism.config(self.settings),line['failed']),.75)
        self.assertEqual(self.store.lineage_trials(self.fid),n+8)
        self.assertEqual(self.store.family(sibling['id'])['trials'],23)
    def test_explicit_historical_failure_versions_in_state_still_raise_bound(self):
        self.store.set_state(self.fid,mechanism={'failed':[41,42],'untestable':[40]})
        self.call(self.args());line=self.r.mechanism_lineage(self.fid)
        self.assertEqual(line['failed'],2)
        self.assertEqual(self.store.family(self.fid)['state']['mechanism']['failed'],[41,42])
    def test_below_base_failures_count_hard_raised_bound_only_failures_do_not(self):
        cards.add_evidence(self.store,self.fid,self.base['sha'],9,'mechanism_test','failed',{'below_base':False})
        cards.add_evidence(self.store,self.fid,self.base['sha'],10,'mechanism_test','failed',{'below_base':True})
        self.call(self.args());line=self.r.mechanism_lineage(self.fid)
        self.assertEqual((line['failed'],line['hard']),(2,1))
    def test_normal_failure_and_invalid_ablation_refuse_broad_train(self):
        for mode,status in [('failed','mechanism_failed'),('invalid','mechanism_invalid'),('identical','mechanism_invalid')]:
            with self.subTest(mode=mode):
                # Source remains a distinct proposal per mode, via the newly registered latest parent.
                self.pool.mode=mode;self.parent=self.store.latest_version(self.fid)
                v,o=self.call(self.args(NEW+'\n# '+mode+'\n'))
                self.assertEqual(v['status'],status,v)
                self.assertTrue(all(j.purpose!='train' for j in self.pool.jobs))
                self.assertIsNone(self.store.family(self.fid)['best_version'])
    def test_fabricated_mechanism_pass_reaches_normal_broad_train_without_probe(self):
        self.pool.mode='passed';v,o=self.call(self.args())
        self.assertEqual(o['mechanism_test']['verdict'],'passed')
        self.assertEqual([j.purpose for j in self.pool.jobs[1:]],['mechanism']*8+['train'])
        self.assertEqual(self.store.family(self.fid)['trials'],10)
        self.assertIsNone(self.store.family(self.fid)['validated_version'])
    def test_enrolled_sweep_is_refused_without_versions_or_jobs(self):
        self.call(self.args());before=self.counts();out={}
        v=self.r._execute(self.store.family(self.fid),'gym_sweep',{'variants':[{}, {'threshold':601}]},out,author='fixture')
        self.assertEqual(v['stage'],'development_card');self.assertEqual(self.counts(),before)
    def test_legacy_no_declaration_behavior_stays_available_before_enrollment(self):
        self.settings['researcher']['mechanism_test']=False
        before=self.counts();v,o=self.call({'code':CODE+'\n# ordinary legacy revision\n','params':{}})
        self.assertEqual(v['status'],'disqualified',v)
        self.assertEqual(self.counts(),tuple(x+1 for x in before))
        self.assertFalse(cards.development_exists(self.store,self.fid))
    def test_actual_parent_source_bytes_are_verified(self):
        path=self.store.root/self.parent['path']; original=path.read_text()
        path.write_text(original+'\n# fabricated tampered parent\n')
        try:self.refuse(self.args(),'source bytes')
        finally:path.write_text(original)
    def test_pre_card_family_can_use_ordinary_new_card_evidence_storage(self):
        with tempfile.TemporaryDirectory() as temp:
            store=SwarmStore(temp)
            try:
                fam=store.add_family({'id':'synthetic-precard','structure':'debit_vertical','roots':['SPY'],
                    'mechanism':'A synthetic family predates birth cards and needs new immutable developmental evidence.'},origin='fixture')
                settings=copy.deepcopy(self.settings);settings['researcher']['mechanism_test']=False
                pool=FabricatedGym();r=Researcher(store,None,pool,settings,background=False)
                r._execute(fam,'gym_run',{'code':CODE,'params':{}},{},author='fixture')
                settings['researcher']['mechanism_test']={'enabled':True,'mode':'gate'}
                parent=store.latest_version(fam['id']);args=self.args()
                args['development_card'].update(parent_version=parent['n'],parent_sha=parent['sha'])
                v=r._execute(store.family(fam['id']),'gym_run',args,{},author='fixture')
                self.assertEqual(v['status'],'mechanism_thin')
                self.assertIsNone(cards.card_of(store,fam['id']))
                self.assertTrue(cards.development_exists(store,fam['id']))
            finally:store.close()
    def test_explicit_enablement_and_gate_are_required(self):
        self.settings['researcher']['development_cards']=False;self.refuse(self.args(),'not enabled')
        self.settings['researcher']['development_cards']=True
        self.settings['researcher']['mechanism_test']['mode']='shadow';self.refuse(self.args(),'gate mode')

if __name__=='__main__':unittest.main(verbosity=2)
