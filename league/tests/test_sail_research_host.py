"""Offline documented Sail response fixtures; every readiness/contract fact is synthetic.

No key, provider call, paid POST, production state or financial operation is used.
The real broker, shared ledger, SailboxClient, GymDriver and durable receipts are
exercised with an injected transport, rather than a simulated host adapter.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import unittest
from unittest import mock

from league.swarm.sail_research_host import SailBridgeInputs, build_sail_host_adapters, HOST_EVENT
from league.swarm.research_host import ReviewedFile
from league.swarm.research_transport import (ResearchBroker, ResearchCapabilityError, ResearchJob, ModelPolicy,
                                            IsolationProof, ISOLATION_FACTS, NAMESPACE_FACTS, _digest)
from league.swarm.daily_compute import DailyAdmissionError, DailyBudget, ResourceBound
from league.swarm.research_sandbox import HostContextEvidence
from league.swarm.store import SwarmStore
from league.tests import test_research_host as host_fixtures
from league.tests.test_research_transport import BOX, PRODUCTION, CODE


class SailFixture:
    """Shapes follow published Sailbox OpenAPI2026-09-07 and Responses2026-02-18."""
    def __init__(self, owner):
        self.owner=owner; self.calls=[]; self.rows={}; self.lost_create=False; self.lost_model=False
        self.duplicate=False; self.offsets=[]; self.model_reply=None; self.exec_commands=[]; self.uploads=[]
        self.probe_existing=False

    def __call__(self, method, path, body=None, **options):
        self.calls.append((method, path, body, options))
        f=self.owner.f
        if path == "/sailboxes/from_checkpoint":
            now=dt.datetime.now(dt.timezone.utc).isoformat()
            self.rows[BOX]={"sailbox_id":BOX,"name":body["name"],"app_id":self.owner.app,
                           "image_id":self.owner.image,"status":"running","vcpu_count":1,"memory_mib":16384,
                           "state_disk_size_gib":32,"volume_mounts":[],"created_at":now,
                           "egress_policy":{"document":{"no_network":True}}}
            reply={"sailbox_id":BOX,"name":body["name"],"status":"running","checkpoint_id":body["checkpoint_id"],
                   "source_checkpoint_generation":3}
            self.creation_reply=reply
            if self.lost_create: raise TimeoutError("synthetic lost POST after allocation")
            return reply
        if method=="GET" and path=="/sailboxes":
            self.offsets.append(options["query"]["offset"])
            rows=list(self.rows.values())
            return {"data":rows+rows if self.duplicate else rows,"has_more":False,"total":len(rows),"offset":0,"limit":100}
        if method=="GET" and path==f"/sailboxes/{BOX}":return dict(self.rows[BOX])
        if method=="GET" and path==f"/sailboxes/{BOX}/egress-policy":return self.rows[BOX]["egress_policy"]
        if method=="POST" and path in [f"/sailboxes/{BOX}/"+x for x in ("sleep","resume","terminate")]:
            status={"sleep":"sleeping","resume":"running","terminate":"terminated"}[path.rsplit("/",1)[1]]
            self.rows[BOX]["status"]=status
            return {"sailbox_id":BOX,"status":status}
        if method=="PUT" and path==f"/sailboxes/{BOX}/files":
            self.uploads.append(options["query"]["path"])
            return {"path":options["query"]["path"],"bytes_written":len(options["data"])}
        if method=="POST" and path==f"/sailboxes/{BOX}/exec":
            command=body["command"]; self.exec_commands.append(command)
            code=1 if command.startswith("test -f ") or command.startswith("test ! -e ") and self.probe_existing else 0
            return iter([{"type":"started","exec_request_id":"exec_fixture"},
                         {"type":"exit","status":"completed","return_code":code}])
        if method=="GET" and path==f"/sailboxes/{BOX}/files":
            return json.dumps({"batch":{},"results":[{"window":"train","roots":["SPY"],"stress":1.0,
                              "run_id":"fixture-train-run","trials":1,"status":"ok","summary":{"trades":0}}]}).encode()
        if method=="POST" and path=="/v1/responses":
            if self.lost_model:raise TimeoutError("synthetic lost one-shot model POST")
            return self.model_reply or {"id":"resp_fixture-1","object":"response","model":body["model"],
                                       "status":"completed","created_at":int(time.time()),"output":[],"metadata":{},
                                       "usage":{"input_tokens":10,"output_tokens":3,"total_tokens":13,
                                                "input_tokens_details":{"cached_tokens":0},"output_tokens_details":{"reasoning_tokens":1}}}
        raise AssertionError("unexpected documented fixture route: "+method+" "+path)


class SailResearchHost(unittest.TestCase):
    def setUp(self):
        self.f=host_fixtures.ResearchHost("runTest"); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        f=self.f
        f.bound=ResourceBound("synthetic-sail-small", "gym",1,"16","32","0","0.005",
                              "SYNTHETIC inclusive fee/resource guarantee; documented S shape")
        f.policy=replace(f.policy,resource_bound=f.bound)
        f.config=replace(f.config,research_policy=f.policy)
        self.app="app_aaaaaaaa-0000-0000-0000-000000000001";self.image="sha256:"+"a"*64
        self.contract=f.file("SYNTHETIC-contract.txt",b"SYNTHETIC maximum-inclusive-charge fixture, not a provider agreement\n")
        self.cp={"schema":1,"scope":f.policy.scope,"checkpoint_id":f.policy.checkpoint,"source_sailbox_id":PRODUCTION,
                 "app_id":self.app,"image_id":self.image,"source_checkpoint_generation":3,
                 "resource_bound":asdict(f.bound),"gym_bundle":f.policy.gym_bundle,"gym_execution":f.policy.execution,
                 "store_root":"/data/approved-train-validation","remote_root":"/workspace/isolated-fixture",
                 "python":"python3","train_validation_only":True,"guest_credentials_absent":True,
                 "no_live_processes":True,"no_network":True,"provenance":"SYNTHETIC reviewed checkpoint evidence"}
        self.model=ModelPolicy("zai-org/GLM-5.3","0.01","0.02","0",10000,1000,f.now-10,f.now+3600,
                               "SYNTHETIC guaranteed entire billable input and output, not current tariff",timeout_seconds=30)
        self.models={"schema":1,"scope":f.policy.scope,"profiles":{"reviewed":{"policy":asdict(self.model),
                    "max_request_bytes":100000,"billable_input_ceiling":10000,"completion_window":"asap",
                    "agreement":self.agreement(model=True)}},"provenance":"SYNTHETIC separately reviewed model evidence"}
        self.billing={"schema":1,"scope":f.policy.scope,"observed_at":f.now-5,"valid_until":f.now+120,
                      "tariff":asdict(f.tariff),"inventory":asdict(f.inventory),"agreement":self.agreement(),
                      "provenance":"SYNTHETIC complete billing/writer guarantees; no production readiness"}
        self.cp_file=f.file("checkpoint.json",json.dumps(self.cp).encode())
        self.model_file=f.file("models.json",json.dumps(self.models).encode())
        self.bill_file=f.file("billing.json",json.dumps(self.billing).encode())
        self.ancestry=None;self.actual_bill=None
        self.inputs=SailBridgeInputs(self.cp_file,self.model_file,lambda:self.bill_file,f.context,
                                     lambda name,cp:self.ancestry,lambda key,response:self.actual_bill)
        self.transport=SailFixture(self)
        self.adapters=self.build()
        self.store=SwarmStore(f.broker_root);self.addCleanup(self.store.close)
        self.budget=DailyBudget(self.store,f.tariff,f.inventory)
        self.broker=self.make_broker()
        self.peer()
        self.broker.open_runtime()

    def agreement(self,model=False):
        return {"kind":"binding_maximum_billable_tokens_and_rates" if model else "binding_maximum_rates",
                "path":str(self.contract.path),"sha256":self.contract.sha256,"inclusive_fees_taxes":True,
                "ongoing_liability_covered":True}

    def build(self,inputs=None):
        return build_sail_host_adapters(self.f.config,inputs=inputs or self.inputs,key_source=lambda:"UNUSED-OFFLINE-FIXTURE",
                                       box_transport=self.transport,inference_transport=self.transport)

    def make_broker(self):
        f=self.f
        def proof(peer,**kw):
            now=time.time()
            return IsolationProof(f.policy.scope,peer,os.getuid(),str(f.broker_root),kw["policy_digest"],"namespaces",now,now+60,
                                  f.runbook.sha256,"b"*64,"c"*64,f.adapter_file.sha256,
                                  tuple(sorted(ISOLATION_FACTS|NAMESPACE_FACTS)),"SYNTHETIC verifier; no physical isolation claimed")
        return ResearchBroker(self.store,self.budget,f.policy,artifact_root=f.artifact,provider=self.adapters.provider,
                              driver_factory=self.adapters.driver_factory,model_adapters=self.adapters.models,verify_isolation=proof)

    def peer(self):self.broker.authorize_peer(os.getpid(),os.getuid(),os.getgid())

    def create(self):
        self.peer();self.broker._ensure_gym()
        return self.broker._resource()

    def model_call(self,key="model-fixture"):
        self.peer();return self.broker.evaluate("reviewed",[{"role":"user","content":"hello"}],key=key)

    def posts(self,path):return [r for r in self.transport.calls if r[0]=="POST" and r[1]==path]

    def rewrite(self,name,value):return self.f.file(name,json.dumps(value).encode())

    def test_official_shapes_create_readback_and_restart_bind_the_original_resource(self):
        key,row=self.create()
        self.assertEqual(row["observation"]["bound"]["memory_gib"],"16")
        self.assertEqual(row["observation"]["bound"]["disk_gib"],"32")
        self.assertNotIn("checkpoint_id",self.transport.rows[BOX],"GET fixture intentionally has no ancestry")
        self.adapters=self.build();self.broker=self.make_broker();self.peer()
        self.assertEqual(self.broker.recover_gym()["status"],"running")
        self.assertEqual(len(self.posts("/sailboxes/from_checkpoint")),1)
        self.assertEqual(len(self.budget._load()["resources"]),1)

    def test_lost_create_discovers_candidate_but_requires_reviewed_original_ancestry(self):
        self.transport.lost_create=True
        with self.assertRaises(TimeoutError):self.create()
        name=self.broker._resource()[1]["name"]
        self.adapters=self.build();self.broker=self.make_broker();self.peer()
        self.assertEqual(self.broker.recover_gym(),{"status":"creating","outcome_known":False})
        self.assertEqual(len(self.budget._load()["resources"]),1)
        self.peer()
        with self.assertRaises(ResearchCapabilityError):self.broker._ensure_gym()
        self.ancestry=self.rewrite("original-ancestry.json",{"schema":1,"scope":self.f.policy.scope,"name":name,
             "checkpoint_id":self.f.policy.checkpoint,"provider_response":self.transport.creation_reply,
             "provenance":"SYNTHETIC independently reviewed original provider ancestry receipt"})
        self.peer();self.assertEqual(self.broker.recover_gym()["status"],"running")
        self.assertEqual(len(self.posts("/sailboxes/from_checkpoint")),1)

    def test_duplicate_name_wrong_ancestry_and_missing_hard_capacity_refuse_attachment(self):
        self.transport.lost_create=True
        with self.assertRaises(TimeoutError):self.create()
        self.transport.duplicate=True;self.peer()
        with self.assertRaisesRegex(ResearchCapabilityError,"ambiguous"):self.broker.recover_gym()
        self.transport.duplicate=False
        name=self.broker._resource()[1]["name"]
        wrong={**self.transport.creation_reply,"checkpoint_id":"sbcp_bbbbbbbb-cccc"}
        self.ancestry=self.rewrite("wrong-ancestry.json",{"schema":1,"scope":self.f.policy.scope,"name":name,
             "checkpoint_id":self.f.policy.checkpoint,"provider_response":wrong,"provenance":"SYNTHETIC wrong origin"})
        self.peer()
        with self.assertRaisesRegex(ResearchCapabilityError,"ancestry"):self.broker.recover_gym()
        self.assertEqual(len(self.posts("/sailboxes/from_checkpoint")),1)

    def test_billing_expiry_observed_rates_unknown_inventory_and_missing_contract_stop_before_post(self):
        variants=[]
        for field,value in (("valid_until",self.f.now-1),("agreement",{**self.billing["agreement"],"kind":"current_documented_rate"}),
                            ("inventory",{**self.billing["inventory"],"exclusive_writer":False}),
                            ("inventory",{**self.billing["inventory"],"unknown_obligations":True})):
            variants.append({**self.billing,field:value})
        for i,value in enumerate(variants):
            self.bill_file=self.rewrite(f"bad-billing-{i}.json",value)
            with self.subTest(i=i),self.assertRaises(Exception):self.create()
        self.assertEqual(self.posts("/sailboxes/from_checkpoint"),[])

    def test_checkpoint_sealed_data_credentials_live_processes_and_artifact_are_not_defaulted(self):
        for field,value in (("train_validation_only",False),("guest_credentials_absent",False),("no_live_processes",False),
                            ("no_network",False),("gym_execution","b"*64)):
            receipt=self.rewrite("bad-checkpoint.json",{**self.cp,field:value})
            with self.subTest(field=field),self.assertRaises(ResearchCapabilityError):self.build(replace(self.inputs,checkpoint=receipt))
        self.assertEqual(self.transport.calls,[])

    def test_arbitrary_production_id_and_unsent_checkpoint_mutation_are_refused(self):
        for method in ("resume","sleep","terminate","observe","egress"):
            with self.subTest(method=method),self.assertRaises(Exception):getattr(self.adapters.provider,method)(PRODUCTION)
        with self.assertRaises(ResearchCapabilityError):
            self.adapters.provider.from_checkpoint(self.f.policy.checkpoint,name="ltcm-research-"+"a"*12+"-"+"a"*32)
        self.assertEqual(self.transport.calls,[])

    def test_receipt_corruption_and_symlink_are_not_accepted_on_restart(self):
        self.create()
        root=self.f.broker_root/"sail-bridge-results"
        result=next(r for r in self.store._all("SELECT payload FROM events WHERE kind=?",(HOST_EVENT,))
                    if json.loads(r["payload"])["action"]=="sail_bridge_result")
        digest=json.loads(result["payload"])["sha256"];path=root/(digest+".json")
        path.write_bytes(b"{}")
        self.adapters=self.build();self.broker=self.make_broker();self.peer()
        with self.assertRaisesRegex(ResearchCapabilityError,"bytes changed"):self.broker.recover_gym()
        path.unlink();path.symlink_to(self.cp_file.path)
        self.peer()
        with self.assertRaisesRegex(ResearchCapabilityError,"private Sail receipt"):self.broker.recover_gym()
        self.assertEqual(len(self.posts("/sailboxes/from_checkpoint")),1)

    def test_one_shot_namespaced_model_wire_and_unknown_cost_keep_the_original_hold(self):
        result=self.model_call()
        self.assertIsNone(result["cost_usd"])
        calls=self.posts("/v1/responses");self.assertEqual(len(calls),1)
        wire=calls[0][2]
        self.assertEqual(wire["model"],"zai-org/GLM-5.3")
        self.assertEqual(wire["reasoning"],{"effort":"low"})
        self.assertEqual(wire["metadata"],{"completion_window":"asap"})
        self.assertFalse(wire["background"]);self.assertFalse(wire["stream"])
        self.assertNotIn("request_key",wire);self.assertNotIn("timeout_seconds",wire)
        self.assertEqual(len(self.budget._load()["inference"]),1)
        held=next(iter(self.budget._load()["inference"].values()))
        self.assertIsNone(held["receipt"])
        self.assertEqual(held["max_nanos"],120000,"whole10000 input cap, not observed10 input tokens")
        self.assertEqual(self.model_call(),result)
        self.assertEqual(len(self.posts("/v1/responses")),1)

    def test_linked_terminal_actual_bill_settles_exact_utc_day(self):
        def bill(key,response):
            intent=self.adapters.provider.bridge.journal("intent","model:"+key)
            return self.rewrite("actual-bill.json",{"schema":1,"scope":self.f.policy.scope,"request_key":key,
               "response_id":response,"model":self.model.model,"body_sha256":intent["body_sha256"],
               "actual_usd":"0.000002","accrued_day":dt.datetime.now(dt.timezone.utc).date().isoformat(),
               "final":True,"provenance":"SYNTHETIC exact provider terminal bill, not token-rate estimate"})
        self.adapters.provider.bridge.inputs=replace(self.inputs,bill=bill)
        result=self.model_call();self.assertEqual(result["cost_usd"],"0.000002")
        self.assertEqual(next(iter(self.budget._load()["inference"].values()))["receipt"]["actual_nanos"],2000)

    def test_late_actual_bill_reconciles_once_after_restart_without_post_or_reply_rewrite(self):
        original=self.model_call()
        self.assertIsNone(original["cost_usd"])
        self.adapters=self.build();self.broker=self.make_broker()
        self.assertFalse(self.adapters.provider.reconcile_model_bill("model-fixture")["outcome_known"])
        intent=self.adapters.provider.bridge.journal("intent","model:model-fixture")
        self.actual_bill=self.rewrite("late-bill.json",{"schema":1,"scope":self.f.policy.scope,"request_key":"model-fixture",
           "response_id":"resp_fixture-1","model":self.model.model,"body_sha256":intent["body_sha256"],"actual_usd":"0.000000000001",
           "accrued_day":dt.datetime.now(dt.timezone.utc).date().isoformat(),"final":True,
           "provenance":"SYNTHETIC later original-request invoice; conservative nanodollar rounding"})
        for _ in range(2):
            self.assertTrue(self.adapters.provider.reconcile_model_bill("model-fixture")["vendor_actual"])
        self.assertEqual(next(iter(self.budget._load()["inference"].values()))["receipt"]["actual_nanos"],1)
        self.assertEqual(self.model_call(),original,"immutable original unknown-cost reply remains unchanged")
        self.assertEqual(len(self.posts("/v1/responses")),1)

    def test_late_over_bound_bill_commits_breach_before_raising_and_cannot_dispatch(self):
        original = self.model_call()
        hold = next(iter(self.budget._load()["inference"].values()))
        intent = self.adapters.provider.bridge.journal("intent", "model:model-fixture")
        self.actual_bill = self.rewrite("late-over-bound-bill.json", {
            "schema": 1, "scope": self.f.policy.scope, "request_key": "model-fixture",
            "response_id": "resp_fixture-1", "model": self.model.model,
            "body_sha256": intent["body_sha256"], "actual_usd": "1",
            "accrued_day": dt.datetime.now(dt.timezone.utc).date().isoformat(), "final": True,
            "provenance": "SYNTHETIC authoritative original invoice above admitted ceiling"})
        for _ in range(2):
            with self.assertRaises(DailyAdmissionError):
                self.adapters.provider.reconcile_model_bill("model-fixture")
            state = self.budget._load()
            self.assertTrue(state["breached"], "outer transaction must not erase the breach")
            self.assertEqual(next(iter(state["inference"].values())), hold)
        # A fresh bridge/store sees the durable breach, while the original immutable
        # controller reply and unknown-cost hold remain unchanged.
        with self.assertRaises(DailyAdmissionError):
            self.build()
        self.assertTrue(self.budget._load()["breached"])
        self.assertEqual(self.model_call(), original)
        with self.assertRaises(DailyAdmissionError):
            self.model_call("new-refused-request")
        bill = self.adapters.provider.bridge.journal("bill", "model:model-fixture")
        self.assertEqual(bill["actual_usd"], "1")
        self.assertEqual(len(self.posts("/v1/responses")), 1)

    def test_wrong_model_nonterminal_and_url_response_never_qualify_or_release_liability(self):
        for i,changes in enumerate(({"model":"moonshotai/Kimi-K3"},{"status":"queued"},{"id":"https://example.com/response"})):
            self.transport.model_reply={"id":"resp_fixture-1","object":"response","model":self.model.model,
                                        "status":"completed","output":[],"usage":{},**changes}
            key="bad-model-"+str(i)
            with self.subTest(changes=changes),self.assertRaises(ResearchCapabilityError):self.model_call(key)
            self.assertIsNotNone(self.adapters.provider.bridge.journal("result","model:"+key),"raw response remains host private")
        self.assertEqual(len(self.posts("/v1/responses")),3)
        self.assertTrue(all(row["receipt"] is None for row in self.budget._load()["inference"].values()))

    def test_missing_original_baseline_fails_before_creating_a_credentialed_client(self):
        empty=self.f.base/"uninitialized-host"
        empty.mkdir(mode=0o700)
        self.f.broker_root=empty
        self.f.config=replace(self.f.config,broker_root=empty)
        key=mock.Mock(return_value="UNUSED")
        with mock.patch("league.swarm.sail_research_host.BoxTransport") as box, self.assertRaises(Exception):
            build_sail_host_adapters(self.f.config,inputs=self.inputs,key_source=key)
        box.assert_not_called();key.assert_not_called();self.assertEqual(self.transport.calls,[])

    def test_atomic_durable_creation_slot_allows_only_one_concurrent_post(self):
        bridge=self.adapters.provider.bridge
        evidence=self.f.context(bridge.policy_digest)
        bridge.inputs=replace(self.inputs,context=lambda digest:evidence)
        name="ltcm-research-"+"a"*12+"-"+"b"*32;key="concurrent-resource"
        with self.store.atomic():
            self.budget.reserve_resource(key,self.f.bound);self.budget.dispatch(key)
            self.broker._record("resource_started",key=key,name=name)
        barrier=threading.Barrier(2);outcomes=[]
        def call():
            barrier.wait()
            try:outcomes.append(self.adapters.provider.from_checkpoint(self.f.policy.checkpoint,name=name))
            except Exception as exc:outcomes.append(exc)
        threads=[threading.Thread(target=call) for _ in range(2)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(timeout=10)
        self.assertTrue(all(not t.is_alive() for t in threads))
        self.assertEqual(sum(isinstance(x,dict) for x in outcomes),1)
        self.assertEqual(len(self.posts("/sailboxes/from_checkpoint")),1)
        journal=bridge.store()
        try:self.assertEqual(journal._one("PRAGMA synchronous")["synchronous"],2)
        finally:journal.close()

    def test_repeated_confirmed_sleep_resume_uses_new_lifecycle_slots_without_retry(self):
        self.create()
        for _ in range(2):
            self.peer();self.assertEqual(self.broker.sleep_gym()["status"],"sleeping")
            self.peer();self.broker._ensure_gym()
        self.assertEqual(len(self.posts(f"/sailboxes/{BOX}/sleep")),2)
        self.assertEqual(len(self.posts(f"/sailboxes/{BOX}/resume")),2)

    def test_cleanup_only_adapter_stops_original_resource_with_stale_prices_but_cannot_send_paid_work(self):
        self.create();key,row=self.broker._resource()
        self.bill_file=self.rewrite("expired-billing.json",{**self.billing,"valid_until":self.f.now-1})
        cleanup=build_sail_host_adapters(self.f.config,inputs=self.inputs,key_source=lambda:"UNUSED",
                 box_transport=self.transport,inference_transport=self.transport,cleanup_only=True)
        with self.store.atomic():self.broker._record("resource_state",key=key,status="stop_requested")
        self.assertEqual(cleanup.provider.terminate(BOX)["status"],"terminated")
        self.assertIsNone(self.budget._load()["resources"][key]["terminal_at"],"control response alone does not rewrite authority in the bridge")
        for action in (lambda:cleanup.driver_factory(cleanup.provider,BOX),
                       lambda:cleanup.provider.from_checkpoint(self.f.policy.checkpoint,name=row["name"]),
                       lambda:cleanup.provider.resume(BOX)):
            with self.assertRaises(ResearchCapabilityError):action()
        self.assertEqual(len(self.posts("/sailboxes/from_checkpoint")),1)
        self.assertEqual(len(self.posts(f"/sailboxes/{BOX}/terminate")),1)

    def test_resource_bound_contradiction_closes_the_scope_before_any_evaluation(self):
        self.create();self.transport.rows[BOX]["memory_mib"]=32768
        self.peer()
        with self.assertRaisesRegex(ResearchCapabilityError,"hard ceilings"):self.broker._ensure_gym()
        self.assertTrue(self.broker._load()["closed"])
        self.assertEqual(self.transport.exec_commands,[])
        self.assertEqual(len(self.budget._load()["resources"]),1)

    def test_mismatched_actual_bill_and_wrong_model_cannot_release_a_hold(self):
        self.actual_bill=self.rewrite("wrong-bill.json",{"schema":1,"scope":self.f.policy.scope,"request_key":"wrong",
           "response_id":"resp_fixture-1","model":self.model.model,"body_sha256":"a"*64,"actual_usd":"0",
           "accrued_day":"2026-10-04","final":True,"provenance":"SYNTHETIC mismatched bill"})
        with self.assertRaisesRegex(ResearchCapabilityError,"not linked"):self.model_call()
        self.assertIsNone(next(iter(self.budget._load()["inference"].values()))["receipt"])
        with self.assertRaises(ResearchCapabilityError):self.model_call()
        self.assertEqual(len(self.posts("/v1/responses")),1)

    def test_lost_model_post_survives_restart_without_retry_or_fallback(self):
        self.transport.lost_model=True
        with self.assertRaises(TimeoutError):self.model_call()
        before=self.budget.summary()["total_upper_usd"]
        self.adapters=self.build();self.broker=self.make_broker()
        with self.assertRaisesRegex(ResearchCapabilityError,"unresolved"):self.model_call()
        self.assertEqual(self.budget.summary()["total_upper_usd"],before)
        self.assertEqual(len(self.posts("/v1/responses")),1)

    def test_full_payload_limit_and_direct_unslotted_send_never_dispatch(self):
        capability=self.adapters.models["reviewed"]
        body={"model":self.model.model,"input":[{"role":"user","content":"x"*100001}],"tools":[],
              "tool_choice":"auto","reasoning_effort":"low","max_output_tokens":1,"cache_key":None,
              "request_key":"unowned","timeout_seconds":30}
        with self.assertRaisesRegex(ResearchCapabilityError,"byte ceiling"):capability.count_tokens(body)
        body["input"]=[{"role":"user","content":"hello"}]
        with self.assertRaisesRegex(ResearchCapabilityError,"original broker request"):capability.send(body)
        self.assertEqual(self.transport.calls,[])

    def test_default_actual_http_transport_has_pinned_host_one_shot_and_policy_timeout(self):
        from ltcm.provider import TransportError
        opener=mock.Mock()
        opener.open.side_effect=TimeoutError("SYNTHETIC transport timeout")
        secret=mock.Mock(return_value="UNUSED-OFFLINE-KEY")
        with mock.patch("league.swarm.sail_research_host.build_opener",return_value=opener):
            self.adapters=build_sail_host_adapters(self.f.config,inputs=self.inputs,key_source=secret,
                                                   box_transport=self.transport)
            self.broker=self.make_broker()
            secret.assert_not_called()
            with self.assertRaises(TransportError):self.model_call()
        opener.open.assert_called_once();secret.assert_called_once()
        args,kwargs=opener.open.call_args
        self.assertEqual(args[0].full_url,"https://api.sailresearch.com/v1/responses")
        self.assertEqual(kwargs["timeout"],30)
        self.assertEqual(args[0].get_method(),"POST")
        self.assertIsNone(next(iter(self.budget._load()["inference"].values()))["receipt"])

    def test_actual_driver_has_one_attempt_exact_artifact_and_unique_original_request_results(self):
        self.peer()
        reply=self.broker.run_gym(ResearchJob("fixture-family",None,CODE,{},"train",("SPY",)),key="gym-original")
        driver=self.broker._driver
        self.assertEqual(driver.retries,1);self.assertEqual(driver.version,self.f.policy.gym_bundle)
        self.assertEqual(reply["gym_execution"],self.f.policy.execution)
        commands=self.transport.exec_commands
        self.assertTrue(commands[0].startswith("test ! -e "))
        self.assertTrue(any("tar -xzf" in c and "code/" in c for c in commands))
        self.assertFalse(any("READY" in c for c in commands))
        self.assertIn(hashlib.sha256(b"gym-original").hexdigest(),driver.remote_root)
        count=len(self.transport.calls)
        self.peer();self.assertEqual(self.broker.run_gym(ResearchJob("fixture-family",None,CODE,{},"train",("SPY",)),key="gym-original"),reply)
        self.assertEqual(len(self.transport.calls),count)

    def test_existing_evaluation_path_and_sealed_windows_are_refused_without_reusing_trials(self):
        self.transport.probe_existing=True;self.peer()
        with self.assertRaisesRegex(ResearchCapabilityError,"no rerun or evaluation reuse"):
            self.broker.run_gym(ResearchJob("fixture-family",None,CODE,{},"train",("SPY",)),key="old-results")
        self.assertEqual(self.transport.uploads,[])
        calls=len(self.transport.calls)
        for window,purpose in (("unseen","train"),("validation","gate"),("forward","train")):
            self.peer()
            with self.subTest(window=window),self.assertRaises(ResearchCapabilityError):
                self.broker.run_gym(ResearchJob("fixture-family",None,CODE,{},window,("SPY",),purpose=purpose),key="refused")
        self.assertEqual(len(self.transport.calls),calls)

    def test_gym_exec_timeout_is_not_retried(self):
        original=self.transport.__call__
        def fail(method,path,body=None,**options):
            if path.endswith("/exec"):
                self.transport.calls.append((method,path,body,options));raise TimeoutError("synthetic uncertain exec")
            return original(method,path,body,**options)
        self.adapters.provider.client.transport=fail
        self.peer()
        with self.assertRaises(Exception):self.broker.run_gym(ResearchJob("fixture-family",None,CODE,{},"train",("SPY",)),key="lost-exec")
        self.assertEqual(len(self.posts(f"/sailboxes/{BOX}/exec")),1)
        self.peer()
        with self.assertRaisesRegex(ResearchCapabilityError,"unresolved evaluation"):
            self.broker.run_gym(ResearchJob("fixture-family",None,CODE,{},"train",("SPY",)),key="another")
        self.assertEqual(len(self.posts(f"/sailboxes/{BOX}/exec")),1)

    def test_provider_receipt_events_use_existing_private_house_mirror_kind(self):
        from league.swarm.hook import SKIPPED_KINDS
        self.create();self.model_call()
        rows=self.store._all("SELECT payload FROM events WHERE kind=?",(HOST_EVENT,))
        self.assertIn(HOST_EVENT,SKIPPED_KINDS)
        self.assertTrue(any(json.loads(r["payload"])["action"]=="sail_bridge_result" for r in rows))
        for row in rows:
            self.assertNotIn("usage",row["payload"]);self.assertNotIn("output",row["payload"])


if __name__=="__main__":unittest.main()
