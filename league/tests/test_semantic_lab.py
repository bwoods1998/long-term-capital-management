from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from league.ledger import Ledger
from league.semantic_lab import SemanticLab, MODEL, questions
from league.frontier import Answer


class Semantics(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.ledger=Ledger(self.root/'ledger.sqlite')
        self.calls=[];self.now=1800000000.0;self.open=True
        self.lab=self.make()

    def tearDown(self):
        self.ledger.close();self.tmp.cleanup()

    def client(self, ident, body):
        self.calls.append((ident,json.loads(body)))
        q=json.loads(body)['questions']
        return {'model':MODEL,'answers':{k:{'type':'noul','noul':.7} for k in q},'usage':{'input_tokens':100}},Decimal('.000005')

    def make(self, client=None):
        return SemanticLab(self.root,client or self.client,self.ledger,active=lambda:self.open,
                           clock=lambda:self.now,workers=2,batch_size=10)

    def queue(self, **kw):
        return self.lab.enqueue('research','agent',self.now,'test',kw or {'evidence':'a bounded test'})

    def test_identical_evidence_is_paid_once_and_saved_answers_survive_restart(self):
        a=self.queue();b=self.queue()
        self.assertEqual(a,b)
        self.lab.run();restarted=self.make();restarted.run()
        self.assertEqual(len(self.calls),1)
        self.assertEqual(restarted.stats()['known_cost_usd'],'0.000005')
        self.assertEqual(len(restarted.evidence('agent')['latest']),1)

    def test_changed_rubric_has_a_distinct_durable_request(self):
        a=self.queue()
        q=questions('research');q['specific_next_test']['instructions']='A revised atomic criterion.'
        b=self.lab.enqueue('research','agent',self.now,'test',{'evidence':'a bounded test'},rubrics=q)
        self.assertNotEqual(a,b)

    def test_research_context_includes_its_series_and_excludes_unrelated_markets(self):
        self.queue()
        self.lab.ingest_markets([{'market':s+'-EVENT-T1','series':s,'yes_bid':.4,'yes_ask':.42}
                                for s in ('KXWTI','KXBTC')],self.now,'market source')
        with patch('league.semantic_lab.time.sleep',lambda _:None):self.lab.run()
        result=self.lab.evidence('agent',series=['KXWTI'])
        self.assertEqual(len(result['latest']),1)
        self.assertEqual([r['entity'] for r in result['market_labels']],['KXWTI-EVENT-T1'])
        self.assertEqual(result['current_market_questions'],questions('market'))

    def test_unknown_provider_outcome_is_not_retried(self):
        def lost(ident,body):
            self.calls.append(ident);raise TimeoutError()
        self.lab=self.make(lost);self.queue();self.lab.run();self.make(lost).run()
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.lab.stats()['unconfirmed_calls'],1)
        self.assertEqual(self.lab.stats()['known_cost_usd'],'0')

    def test_crash_after_intent_keeps_request_unknown_instead_of_rebuying(self):
        ident=self.queue()
        with self.lab.db() as db:db.execute("UPDATE semantic_tasks SET status='calling' WHERE id=?",(ident,))
        self.make().run()
        self.assertEqual(self.calls,[])
        self.assertEqual(self.lab.stats()['unconfirmed_calls'],1)

    def test_concurrent_workers_cannot_claim_the_same_paid_batch(self):
        entered,release=threading.Event(),threading.Event()
        def slow(ident,body):
            entered.set();self.assertTrue(release.wait(5));return self.client(ident,body)
        self.lab=self.make(slow);self.queue()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(self.lab.run);self.assertTrue(entered.wait(5))
            try:self.assertEqual(self.make().run(),{'busy':True})
            finally:release.set()
            first.result()
        self.assertEqual(len(self.calls),1)

    def test_expired_window_keeps_queued_work_without_buying_it(self):
        self.queue();self.open=False;self.lab.run()
        self.assertEqual(self.calls,[])
        self.assertEqual(self.lab.stats()['tasks'][0]['status'],'queued')

    def test_invalid_typed_answer_retains_known_cost_but_is_never_shared(self):
        def bad(ident,body):
            answer,cost=self.client(ident,body);answer['answers']['missing_input']['noul']=2;return answer,cost
        self.lab=self.make(bad);self.queue();self.lab.run()
        self.assertEqual(self.lab.stats()['known_cost_usd'],'0.000005')
        self.assertEqual(self.lab.stats()['tasks'][0]['status'],'rejected')
        self.assertEqual(self.lab.evidence('agent')['latest'],[])

    def test_market_inputs_strip_outcomes_and_history_never_reaches_forward(self):
        m={'market':'KXBTC-1-T10','series':'KXBTC','title':'Bitcoin above ten?',
           'yes_bid':.4,'yes_ask':.42,'result':'yes','settled_value':1,'_private':'not public'}
        self.lab.ingest_markets([m],self.now,'first')
        self.lab.ingest_markets([{**m,'yes_bid':.5,'yes_ask':.52}],self.now+300,'future')
        with self.lab.db() as db:
            rows=db.execute('SELECT body FROM semantic_tasks ORDER BY observed').fetchall()
        first=json.loads(rows[0][0])['state'];later=json.loads(rows[1][0])['state']
        self.assertNotIn('result',first['market']);self.assertNotIn('_private',first['market'])
        self.assertEqual(first['earlier_quotes'],[])
        self.assertEqual(later['earlier_quotes'][0]['bid'],.4)
        self.assertTrue(all(r['observed']<later['observed_minute'] for r in later['earlier_quotes']))

    def test_invalid_or_crossed_quotes_and_oversized_packets_are_not_sent(self):
        self.lab.ingest_markets([{'market':'bad','yes_bid':.9,'yes_ask':.1}],self.now,'bad')
        self.assertIsNone(self.lab.enqueue('market','too-big',self.now,'test',{'text':'x'*65536}))
        self.lab.run();self.assertEqual(self.calls,[])

    def test_future_outcomes_are_separate_and_late_labels_cannot_enter_forward_evaluation(self):
        start=self.now
        m={'market':'KXBTC-EVENT-T10','series':'KXBTC','title':'Bitcoin above ten?',
           'yes_bid':.4,'yes_ask':.42}
        self.lab.ingest_markets([m],start,'initial')
        self.lab.run()
        self.now+=360
        self.lab.ingest_markets([{**m,'yes_bid':.6,'yes_ask':.62}],self.now,'later')
        report=self.lab.markouts(self.now+1)
        self.assertEqual(report['forward_labeled_rows'],1)
        self.assertEqual(report['train_rows'],1)
        self.assertEqual(report['status'],'insufficient_independent_forward_data')
        with self.lab.db() as db:
            db.execute('UPDATE semantic_tasks SET finished=? WHERE observed=?',(self.now+1,start))
        self.assertEqual(self.lab.markouts(self.now+1)['forward_labeled_rows'],0)

    def test_evolution_preserves_baseline_questions_and_never_reads_the_holdout(self):
        from league.semantic_lab import FEATURES
        start=self.now
        self.lab.burst={'id':'test','started':start}
        self.lab.batch_size=20
        for i in range(13):
            self.lab.enqueue('market','event-'+str(i),start-60 if i<12 else start+7201,'source',
                             {'market':{'title':'development' if i<12 else 'HOLDOUT SECRET'},'sample':i})
        with patch('league.semantic_lab.time.sleep',lambda _:None):self.lab.run()
        value={'questions':{
            'event_identity':{'type':'noul','instructions':'Does the supplied text uniquely identify the event?'},
            'official_source':{'type':'noul','instructions':'Does the supplied text identify an official resolution source?'}},
            'hypothesis':'Explicit source labels may distinguish ambiguous contracts.',
            'acceptance':'Compare frozen added features on later unseen events.'}
        calls=[]
        def propose(**kwargs):
            calls.append(kwargs)
            return Answer(json.dumps(value),Decimal('.02'),{'input_tokens':100,'output_tokens':100},'gpt-6-astra')
        self.lab.proposer=SimpleNamespace(ask=propose)
        self.lab.evolve();self.lab.evolve()
        self.assertEqual(len(calls),1)
        self.assertNotIn('HOLDOUT SECRET',calls[0]['user'])
        self.assertEqual(set(self.lab.market_questions()),set(FEATURES)|set(value['questions']))
        self.assertEqual(self.lab.stats()['question_evolution'][0]['status'],'completed')
        self.now=start+7200
        self.lab.evolve();self.assertEqual(len(calls),1)

    def test_question_proposals_cannot_replace_baseline_or_smuggle_execution_settings(self):
        good={'questions':{
            'one':{'type':'noul','instructions':'Does the contract specify an official publication?'},
            'two':{'type':'noul','instructions':'Is the event identity distinguishable from its peers?'}},
            'hypothesis':'A falsifiable semantic hypothesis.', 'acceptance':'Score on untouched later observations.'}
        self.lab.validate_proposal(good)
        for field,value in [('type','code'),('instructions','too short'),('max_output_tokens',10000)]:
            changed=json.loads(json.dumps(good));changed['questions']['one'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.lab.validate_proposal(changed)
        changed=json.loads(json.dumps(good));changed['questions']['continuous_threshold']=changed['questions'].pop('one')
        with self.assertRaises(ValueError):self.lab.validate_proposal(changed)
