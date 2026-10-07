"""Continuing-Gym/rollback regressions. Every tariff, bill and native call is fabricated."""
from dataclasses import asdict,replace
import datetime as dt
import hashlib,json,os
from pathlib import Path
import shutil,threading,time,unittest
from unittest import mock

from league.tests import test_self_service_cost_admission as original
from league.tests.test_research_transport import CODE,BOX
from league.swarm import daily_compute as daily,research_host as host,observed_cost_journal as journal
from league.swarm.research_transport import ResearchJob,IsolationProof,ISOLATION_FACTS,NAMESPACE_FACTS
from league.swarm.store import SwarmStore

class ObservedCostPersistence(unittest.TestCase):
    setUp=original.SelfServiceAdmission.setUp
    basis=original.SelfServiceAdmission.basis
    parsed=original.SelfServiceAdmission.parsed
    billing=original.SelfServiceAdmission.billing
    build=original.SelfServiceAdmission.build
    broker_for=original.SelfServiceAdmission.broker_for
    call=original.SelfServiceAdmission.call

    def gym(self,key='gym-first'):
        self.broker.authorize_peer(os.getpid(),os.getuid(),os.getgid())
        return self.broker.run_gym(ResearchJob('synthetic-family',1,CODE,{},'train',('SPY',)),key=key)

    def high(self, *, overcap=False):
        basis=self.basis();basis['resource_rates'].update(vcpu_usd_hour='1' if overcap else '0.05',memory_gib_usd_hour='0.03')
        basis['fees_taxes']['fixed_day_fee_upper_usd']='2'
        basis['prior']['upper_usd']='3'
        for row in basis['pending']:row['upper_usd']='14'
        self.changes={name:basis[name] for name in ('resource_rates','fees_taxes','prior','pending')}

    def restart_report(self,*,tomorrow=False):
        self.changes={}
        tariff,inventory=self.adapters.billing()
        store=SwarmStore(self.f.broker_root);self.addCleanup(store.close)
        if tomorrow:
            at=(int(time.time()//86400)+1)*86400+1;store.clock=lambda:at
            tariff=replace(tariff,valid_from=at-1,valid_until=at+120,prior_utc_day=dt.datetime.fromtimestamp(at,dt.timezone.utc).date().isoformat())
            inventory=replace(inventory,observed_at=at-1,valid_until=at+120)
        return daily.DailyBudget(store,tariff,inventory),store

    def use_actual_host_billing_verifier(self):
        runtime=host.HostRuntime(self.config,self.adapters);runtime._build_broker();self.addCleanup(runtime.shutdown)
        self.budget,self.store,self.broker=runtime.budget,runtime.store,runtime.broker
        def verify(peer,**kw):
            runtime._billing()
            now=time.time()
            return IsolationProof(self.f.policy.scope,peer,os.getuid(),str(self.f.broker_root),kw['policy_digest'],'namespaces',now,now+60,
                self.f.runbook.sha256,'b'*64,'c'*64,self.f.adapter_file.sha256,
                tuple(sorted(ISOLATION_FACTS|NAMESPACE_FACTS)),'SYNTHETIC peer proof; actual HostRuntime billing retained')
        self.broker._verify=verify
        return runtime

    def test_actual_host_existing_gym_new_job_retains_high_quote_without_inference_reserve(self):
        self.use_actual_host_billing_verifier();self.gym()
        before=self.budget._load();opened=self.store._all("SELECT payload FROM events WHERE kind=? AND json_extract(payload,'$.action')='opened'",(daily.EVENT_KIND,))
        self.high();self.gym('gym-second')
        state=self.budget._load();self.assertEqual(state['inference'],before['inference'])
        self.assertEqual(len(state['resources']),1)
        self.assertEqual(sum(m=='POST' and p=='/sailboxes/from_checkpoint' for m,p,*_ in self.transport.calls),1)
        self.assertEqual(self.store._all("SELECT payload FROM events WHERE kind=? AND json_extract(payload,'$.action')='opened'",(daily.EVENT_KIND,)),opened)
        budget,_=self.restart_report();report=budget.summary()
        self.assertGreaterEqual(report['resource_upper_nanos']+report['creation_upper_nanos'],14*daily.NANOS)
        self.assertGreaterEqual(report['admission_total_at_observed_rates_nanos'],19*daily.NANOS)
        self.assertTrue(state['observed_external_refs'])
        self.assertFalse(any(m=='POST' and p=='/v1/responses' for m,p,*_ in self.transport.calls))

    def test_paid_guest_route_retains_high_facts_without_broker_reservation(self):
        self.gym();before=self.budget._load();driver=self.broker._driver;run=driver.run
        def actual_guest(*args,**kwargs):
            # New price arrives only after the normal original request_started
            # commit, while this exact pending Gym owns its guest capability.
            self.high();self.adapters.provider.exec(BOX,'true',timeout=1)
            return run(*args,**kwargs)
        with mock.patch.object(driver,'run',side_effect=actual_guest):self.gym('guest-refresh')
        after=self.budget._load();self.assertEqual(after['inference'],before['inference'])
        budget,_=self.restart_report();self.assertGreaterEqual(budget.summary()['admission_total_at_observed_rates_nanos'],19*daily.NANOS)

    def test_actual_host_overcap_refresh_survives_outer_rollback_lower_quote_restart_and_utc(self):
        runtime=self.use_actual_host_billing_verifier();self.gym();self.high(overcap=True)
        with self.assertRaises(host.ResearchHostError):
            with self.store.atomic():runtime._billing()
        budget,store=self.restart_report()
        self.assertFalse(budget.summary()['within_cap'])
        self.assertGreater(budget.summary()['resource_upper_nanos'],25*daily.NANOS)
        tomorrow,_=self.restart_report(tomorrow=True);self.assertFalse(tomorrow.summary()['within_cap'])
        before=len(self.transport.calls)
        with self.assertRaises(host.ResearchHostError):self.gym('refused-new-job')
        self.assertEqual(len(self.transport.calls),before)
        self.assertEqual(budget._load()['inference'],{})

    def test_refused_new_reservation_retains_known_pending_increase_without_new_row(self):
        self.call();state=self.budget._load();key=next(iter(state['inference']))
        tariff,inventory=self.adapters.billing();tariff=replace(tariff,pending=((key,'24'),),fixed_day_fee_usd='2')
        budget=daily.DailyBudget(self.store,tariff,inventory)
        with self.assertRaises(daily.DailyAdmissionError):
            with self.store.atomic():budget.reserve_inference('must-not-exist','0.1',provenance='SYNTHETIC refused new allowance')
        restarted,_=self.restart_report();after=restarted._load()
        self.assertNotIn('must-not-exist',after['inference'])
        self.assertGreaterEqual(restarted.summary()['inference_upper_nanos'],24*daily.NANOS)
        self.assertFalse(restarted.summary()['within_cap'])
        self.assertEqual(after['inference'][key],state['inference'][key])

    def test_unsynchronized_high_fact_loss_after_refused_outer_transaction_is_refused(self):
        self.call();key=next(iter(self.budget._load()['inference']));directory=self.f.broker_root/journal.NAME
        old=set(directory.glob('*.json'));tariff,inventory=self.adapters.billing()
        high=replace(tariff,pending=((key,'24'),),fixed_day_fee_usd='2')
        with self.assertRaises(daily.DailyAdmissionError):
            with self.store.atomic():daily.DailyBudget(self.store,high,inventory).reserve_inference('refused','0.1',provenance='SYNTHETIC refused')
        # Deliberately delete only the newly appended HIGH fact: all prior SQL
        # refs, identity, old files, and complete manifest remain present.
        high_files=set(directory.glob('*.json'))-old;self.assertEqual(len(high_files),1)
        chosen=high_files.pop();raw=chosen.read_bytes();chosen.unlink()
        with self.assertRaises(daily.DailyAdmissionError):self.restart_report()
        chosen.write_bytes(raw);chosen.chmod(0o600)
        budget,_=self.restart_report();self.assertFalse(budget.summary()['within_cap'])

    def test_first_high_observation_refusal_with_no_sql_refs_detects_whole_book_loss(self):
        legacy=daily.DailyBudget(self.store,self.f.tariff,self.f.inventory)
        legacy.reserve_inference('original-before-mode','0.25',provenance='SYNTHETIC original schema1 hold')
        legacy.dispatch('original-before-mode')
        self.assertFalse((self.f.broker_root/journal.NAME).exists())
        tariff,inventory=self.adapters.billing();high=replace(tariff,pending=(('original-before-mode','24'),),fixed_day_fee_usd='2')
        budget=daily.DailyBudget(self.store,high,inventory)
        with self.assertRaises(daily.DailyAdmissionError):
            with self.store.atomic():budget.reserve_inference('refused-first','0.1',provenance='SYNTHETIC first capture refusal')
        raw=budget._sqlite_load();self.assertNotIn('observed_external_refs',raw)
        self.assertNotIn('observed_basis',raw)
        self.assertTrue((self.f.broker_root/journal.WITNESS).exists())
        directory=self.f.broker_root/journal.NAME;lost=directory.with_name(journal.NAME+'-lost');directory.rename(lost)
        with self.assertRaises(daily.DailyAdmissionError):self.restart_report()
        lost.rename(directory)
        restarted,_=self.restart_report();self.assertFalse(restarted.summary()['within_cap'])
        self.assertEqual(restarted._load()['inference']['original-before-mode'],raw['inference']['original-before-mode'])

    def test_completeness_manifest_loss_truncation_and_crash_orphan_refuse(self):
        self.call();directory=self.f.broker_root/journal.NAME;manifest=directory/'manifest.json';raw=manifest.read_bytes()
        manifest.unlink()
        with self.assertRaises(daily.DailyAdmissionError):self.budget._load()
        manifest.write_bytes(raw);manifest.chmod(0o600);manifest.write_bytes(raw[:10])
        with self.assertRaises(daily.DailyAdmissionError):self.budget._load()
        manifest.write_bytes(raw)
        chosen=next(p for p in directory.glob('*.json') if p.name not in ('identity.json','manifest.json'))
        value=json.loads(chosen.read_bytes());value['observed_at']+=0.00001
        orphan=journal.encode(value);path=directory/(journal.digest(orphan)+'.json');path.write_bytes(orphan);path.chmod(0o600)
        with self.assertRaises(daily.DailyAdmissionError):self.budget._load()
        path.unlink();self.assertIsNotNone(self.budget._load())

    def test_dispatch_transition_retains_quote_even_when_outer_operation_refuses(self):
        self.call();key=next(iter(self.budget._load()['inference']))
        tariff,inventory=self.adapters.billing();tariff=replace(tariff,pending=((key,'5'),),fixed_day_fee_usd='2')
        budget=daily.DailyBudget(self.store,tariff,inventory)
        with self.assertRaises(daily.DailyAdmissionError):
            with self.store.atomic():budget.dispatch(key) # already consumed original dispatch; no retry
        restarted,_=self.restart_report();self.assertGreaterEqual(restarted.summary()['inference_upper_nanos'],5*daily.NANOS)
        self.assertGreaterEqual(restarted.summary()['admission_total_at_observed_rates_nanos'],7*daily.NANOS)

    def test_readonly_billing_summary_and_preinit_do_not_publish_observations(self):
        before=self.budget._load();self.adapters.billing();self.budget.summary()
        self.assertFalse((self.f.broker_root/journal.NAME).exists())
        bridge=original._Bridge(self.config,self.inputs,time.time,cleanup_only=True);bridge.billing(initialization_preflight=True)
        self.assertFalse((self.f.broker_root/journal.NAME).exists());self.assertEqual(self.budget._load(),before)

    def test_truncated_missing_and_foreign_fact_files_refuse_original_scope(self):
        self.call();directory=self.f.broker_root/journal.NAME
        paths=[p for p in directory.glob('*.json') if p.name not in ('identity.json','manifest.json')]
        self.assertTrue(paths);chosen=paths[0];raw=chosen.read_bytes()
        chosen.write_bytes(raw[:10])
        with self.assertRaises(daily.DailyAdmissionError):self.budget._load()
        chosen.write_bytes(raw);chosen.unlink()
        with self.assertRaises(daily.DailyAdmissionError):self.budget._load()
        chosen.write_bytes(raw);chosen.chmod(0o600)
        renamed=directory.with_name(journal.NAME+'-missing');directory.rename(renamed)
        with self.assertRaises(daily.DailyAdmissionError):self.budget._load()
        renamed.rename(directory)
        header=directory/'identity.json';original_header=header.read_bytes();value=json.loads(original_header)
        value['scope']='foreign';header.write_bytes(journal.encode(value))
        with self.assertRaises(daily.DailyAdmissionError):self.budget._load()
        header.write_bytes(original_header);self.assertIsNotNone(self.budget._load())

    def test_partial_unpublished_fact_and_symlink_refuse_without_zeroing_hold(self):
        self.call();directory=self.f.broker_root/journal.NAME
        partial=directory/'.pending-crashed';partial.write_bytes(b'{');partial.chmod(0o600)
        with self.assertRaises(daily.DailyAdmissionError):self.budget.summary()
        partial.unlink();target=directory/'identity.json';alias=directory/'fake.json';alias.symlink_to(target)
        with self.assertRaises(daily.DailyAdmissionError):self.budget._load()
        alias.unlink();self.budget.tariff,self.budget.inventory=self.adapters.billing();self.assertGreater(self.budget.summary()['inference_upper_nanos'],0)

    def test_concurrent_independent_observers_retain_both_known_upper_facts(self):
        self.call();key=next(iter(self.budget._load()['inference']));tariff,inventory=self.adapters.billing()
        first=replace(tariff,basis_sha256='a'*64,pending=((key,'5'),),fixed_day_fee_usd='1')
        second=replace(tariff,basis_sha256='b'*64,pending=((key,'3'),),fixed_day_fee_usd='2')
        barrier=threading.Barrier(2);errors=[]
        def observe(t):
            store=SwarmStore(self.f.broker_root)
            try:barrier.wait(timeout=3);daily.DailyBudget(store,t,inventory).observe_prices()
            except BaseException as e:errors.append(e)
            finally:store.close()
        threads=[threading.Thread(target=observe,args=(t,)) for t in (first,second)]
        for t in threads:t.start()
        for t in threads:t.join(10)
        self.assertFalse(any(t.is_alive() for t in threads));self.assertEqual(errors,[])
        budget,_=self.restart_report();report=budget.summary()
        self.assertGreaterEqual(report['inference_upper_nanos'],5*daily.NANOS)
        self.assertGreaterEqual(report['admission_total_at_observed_rates_nanos'],7*daily.NANOS)
        with budget.store.atomic():budget.sync_observed_prices()
        self.assertEqual(self.budget._load(),budget._load())

    def final_model_quote(self,*,overcap=False):
        active=[True];observations=[0]
        def billing():
            state=self.budget._load()
            if active[0] and any(row['dispatch_at'] is not None for row in state['inference'].values()):
                observations[0]+=1
                # First is send.fresh; second is _original(sending=True), after
                # the sole original reservation/dispatch committed normally.
                if observations[0]>=2:
                    basis=self.basis();basis['fees_taxes']['fixed_day_fee_upper_usd']='25' if overcap else '2'
                    basis['prior']['upper_usd']='0' if overcap else '3'
                    for row in basis['pending']:row['upper_usd']='5'
                    self.changes={name:basis[name] for name in ('fees_taxes','prior','pending')}
            return self.billing()
        self.inputs=replace(self.inputs,billing=billing);self.adapters=self.build();self.broker=self.broker_for()
        return active,observations

    def test_final_model_send_quote_is_durable_one_post_one_original_hold_cached_replay(self):
        active,observations=self.final_model_quote();result=self.call('final-send')
        self.assertGreaterEqual(observations[0],2);active[0]=False
        state=self.budget._load();key=next(iter(state['inference']))
        self.assertEqual(state['observed_pending_upper'][key],5*daily.NANOS)
        self.assertEqual(len(state['inference']),1)
        self.assertEqual(sum(json.loads(row['payload'])['action']=='inference_reserved' for row in self.store._all("SELECT payload FROM events WHERE kind=?",(daily.EVENT_KIND,))),1)
        self.assertEqual(self.call('final-send'),result)
        self.assertEqual(sum(m=='POST' and p=='/v1/responses' for m,p,*_ in self.transport.calls),1)
        budget,_=self.restart_report();self.assertGreaterEqual(budget.summary()['admission_total_at_observed_rates_nanos'],10*daily.NANOS)

    def test_final_model_send_overcap_quote_refuses_post_and_survives_lower_restart(self):
        active,observations=self.final_model_quote(overcap=True)
        with self.assertRaises(original.ResearchCapabilityError):self.call('final-refused')
        self.assertGreaterEqual(observations[0],2);active[0]=False
        self.assertEqual(sum(m=='POST' and p=='/v1/responses' for m,p,*_ in self.transport.calls),0)
        before=self.budget._load();self.assertEqual(len(before['inference']),1)
        budget,_=self.restart_report();self.assertFalse(budget.summary()['within_cap'])
        self.assertEqual(budget._load()['inference'],before['inference'])

    def test_true_original_model_settlement_retires_retained_extra_hold(self):
        self.call();key=next(iter(self.budget._load()['inference']));tariff,inventory=self.adapters.billing()
        high=replace(tariff,pending=((key,'5'),));budget=daily.DailyBudget(self.store,high,inventory);budget.observe_prices()
        self.assertGreaterEqual(budget.summary()['inference_upper_nanos'],5*daily.NANOS)
        budget.settle_inference(key,accrued_day=dt.datetime.now(dt.timezone.utc).date().isoformat(),actual_usd='0.1',provenance='SYNTHETIC complete original final all-in bill')
        restarted,_=self.restart_report();self.assertEqual(restarted.summary()['inference_upper_nanos'],100000000)
        self.assertIsNotNone(restarted._load()['inference'][key]['receipt'])

if __name__=='__main__':unittest.main()
