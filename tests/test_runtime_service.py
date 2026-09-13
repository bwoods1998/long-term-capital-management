"""Clock-driven service scheduling with real immutable journals; no paid calls."""

from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
import signal
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from portfolio_runtime import runner
from portfolio_runtime.contracts import BenchmarkPoint, UniverseSnapshot, YAHOO_SP500TR, timestamp
from portfolio_runtime.evidence import save
from portfolio_runtime.ledger import PortfolioLedger
from portfolio_runtime.provider import Client, canonical
from portfolio_runtime.research import Research, grade_result
from portfolio_runtime.service import Service, read_config, request_totals, stamp

from test_runtime_runner import evidence, answer, ImmediatePool
import test_runtime_runner as runtime_fixtures
from test_runtime_market import FixtureMarket, fixture, next_session


SUNDAY = "2026-09-13T15:00:00Z"
MONDAY = "2026-09-14T04:00:00Z"
SATURDAY = "2026-09-19T04:00:00Z"


class Lab:
    def __init__(self, path):
        self.path = path
        self.version = 0
    def policy(self):
        return {"version": self.version, "name": "memory_3", "memory_limit": 3}
    def plan_epoch(self, *args, **kwargs):
        return []
    def reconcile(self, *args):
        return {}
    def evaluate(self):
        return {"status": "insufficient_evidence"}


class NoMarket:
    def __init__(self, *args):
        pass
    def fill_pending(self, ledger, **kwargs):
        return {"status": "waiting_for_market"}
    def mark_close(self, ledger, **kwargs):
        return {"status": "up_to_date"}


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.at = timestamp(SUNDAY).timestamp()
        save(self.root / "initial.json", evidence())
        self.config = {"schema_version": 1, "kind": "weekday_service",
                       "service_id": "week-one", "state_dir": str(self.root / "state"),
                       "week_starts_at": MONDAY, "week_ends_at": SATURDAY,
                       "weekly_inference_budget_usd": "100", "session_inference_budget_usd": "10",
                       "session_seconds": 3600, "account_created_at": SUNDAY,
                       "key_fingerprint": "a"*64, "initial_evidence_path": str(self.root / "initial.json"),
                       "admission_path": str(self.root / "admission.json"), "injected_auth": True}
        self.captures = []
        self.runs = []

    def tearDown(self):
        self.tmp.cleanup()

    def admit(self, *, allow=True, **kwargs):
        save(self.root / "admission.json", {"schema_version": 1, "service_id": "week-one",
             "updated_at": stamp(self.at), "allow_new_research": allow,
             "reason_code": None if allow else "funding_needed", **kwargs})

    def refresh(self, directory, previous):
        data = evidence()
        capture_at = stamp(self.at)
        data["captured_at"] = capture_at
        data["universe"].update(id="capture-"+capture_at.replace(":", ""), effective_at=capture_at,
                                captured_at=capture_at,
                                expires_at=stamp(self.at+7*86400))
        for company in data["companies"]:
            company.update(captured_at=capture_at, cutoff=capture_at[:10])
        self.captures.append(capture_at)
        return data

    def execute(self, config, data, **kwargs):
        self.runs.append(deepcopy(config))
        self.at = config["ends_epoch"]
        return {}

    def service(self, **kwargs):
        return Service(self.config, clock=lambda: self.at, executor=kwargs.pop("executor", self.execute),
                       refresher=self.refresh, market_factory=kwargs.pop("market_factory", NoMarket),
                       policy_factory=Lab, **kwargs)

    def test_sunday_waits_and_weekday_epochs_preserve_one_account(self):
        service = self.service()
        self.admit()
        with service.locked():
            self.assertEqual(service.tick(), "waiting")
        self.assertEqual(self.runs, [])
        self.assertEqual(service.health()["next_wake_at"], MONDAY)
        path = self.root / "state/paper.sqlite"
        with PortfolioLedger(path) as ledger:
            original = ledger.events()
        for day in (0, 1, 2, 4):
            self.at = timestamp(MONDAY).timestamp()+day*86400
            self.admit()
            with service.locked():
                service.tick()
        self.assertEqual(len(self.runs), 4)
        self.assertEqual(len(self.captures), 4)
        self.assertEqual({c["paper_path"] for c in self.runs}, {str(path)})
        with PortfolioLedger(path) as ledger:
            self.assertEqual(ledger.events(), original)
            self.assertEqual(ledger.public_state()["created_at"], SUNDAY)
        self.at = timestamp(SATURDAY).timestamp()
        with service.locked():
            self.assertEqual(service.tick(), "complete")
        self.assertEqual(len(self.runs), 4)

    def test_missing_stale_wrong_identity_or_denied_admission_never_launches(self):
        self.at = timestamp(MONDAY).timestamp()
        service = self.service()
        with service.locked():
            service.tick()
            self.admit(allow=False)
            service.tick()
            self.admit()
            self.at += 181
            service.tick()
            self.admit(service_id="other-week")
            service.tick()
        self.assertEqual(self.runs, [])
        self.assertEqual(len(self.captures), 1)  # Free source/paper work continues while inference is denied.
        self.assertFalse(service.admission_allowed())

    def test_single_writer_lock_rejects_second_process_and_cli(self):
        first, second = self.service(), self.service()
        with first.locked():
            with self.assertRaises(BlockingIOError), second.locked():
                self.fail("Must not acquire second authority")
        with second.locked():
            pass

    def test_sigterm_publishes_paused_after_writer_release_and_restarts_same_epoch(self):
        self.at = timestamp(MONDAY).timestamp()
        self.admit()
        configs = []
        def interrupted(config, data, controller):
            configs.append(config)
            with (self.root/"state/paper-writer.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                signal.raise_signal(signal.SIGTERM)
        service = self.service(executor=interrupted)
        service.run()
        public = json.loads((self.root/"state/public.json").read_text())
        self.assertEqual(public["service"]["status"], "paused")
        self.assertEqual(public["service"]["reason_code"], "manual_pause")
        self.assertIsNone(public["service"]["next_wake_at"])
        self.assertEqual(service.health()["status"], "paused")
        resumed = self.service()
        resumed.run(once=True)
        self.assertEqual(self.runs, configs)
        self.assertEqual(len(self.runs), 1)

    def test_frozen_week_budget_and_epoch_cannot_mutate_on_restart(self):
        service = self.service()
        changed = {**self.config, "weekly_inference_budget_usd": "200"}
        with self.assertRaisesRegex(ValueError, "contract cannot change"):
            Service(changed)
        self.at = timestamp(MONDAY).timestamp()
        self.admit()
        service.initialize()
        identity, config = service.prepare_epoch()
        with service.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE epochs SET reserved='1000' WHERE id=?", (identity,))
        self.assertEqual(Decimal(config["inference_budget_usd"]), Decimal("5"))
        self.assertEqual(Decimal(service.totals()["reserved_usd"]), Decimal("5"))
        self.assertEqual(service.allowance(), Decimal(0))

    def test_unused_reservations_release_only_after_terminal_epoch(self):
        service = self.service()
        self.at = timestamp(MONDAY).timestamp()
        self.admit()
        service.initialize()
        identity, config = service.prepare_epoch()
        self.assertEqual(service.totals()["reserved_usd"], "5.00000000")
        with service.locked():
            service.tick()
        self.assertEqual(service.totals()["reserved_usd"], "0")
        self.assertEqual(self.runs[0], config)
        self.assertEqual(service.prepare_epoch(), None)  # Admission expired during fake epoch.

    def test_restart_recovers_same_accepted_request_without_new_post_or_reservation(self):
        self.at = timestamp(MONDAY).timestamp()+600
        self.admit()
        methods, identities, configs = [], [], []
        phase = [0]
        def execute(config, data, controller):
            configs.append(config)
            def transport(method, route, body=None, request_id=None):
                methods.append(method)
                if method == "POST":
                    return {"id": "resp_one", "status": "queued", "model": "moonshotai/Kimi-K2.6"}
                return {"id": "resp_one", "status": "completed", "model": "moonshotai/Kimi-K2.6",
                        "usage": {"input_tokens": 100, "output_tokens": 20,
                                  "input_tokens_details": {"cached_tokens": 0}},
                        "output": [{"type": "message", "content": [{"type": "output_text", "text": canonical(answer())}]}]}
            client = Client(Path(config["state_dir"])/"requests.sqlite", config,
                            transport=transport, clock=lambda: self.at)
            research = Research(Path(config["state_dir"])/"research.sqlite", data)
            research.add("one", 0, "company", "AAPL", "kimi_flex", "source", "question", max_output=128)
            task = research.waiting()
            if task:
                row = task[0]
                identity = client.submit_intent(row["id"], row["profile"], json.loads(row["body"]))
                research.attach(row["id"], identity)
            else:
                identity = client.observations()[0]["id"]
            identities.append(identity)
            if phase[0]:
                self.at = config["ends_epoch"]
            client.step(identity)
            phase[0] += 1
        first = self.service(executor=execute)
        with first.locked():
            first.tick()
        held = first.totals()["reserved_usd"]
        second = self.service(executor=execute)
        with second.locked():
            second.tick()
        self.assertEqual(methods, ["POST", "GET"])
        self.assertEqual(identities[0], identities[1])
        self.assertEqual(configs[0], configs[1])
        with second.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM epochs").fetchone()[0], 1)
        self.assertEqual(second.totals()["requests"], 1)
        self.assertGreater(Decimal(held), Decimal(0))

    def test_seed_pending_order_waits_sunday_and_fills_once_on_actual_monday(self):
        seed = self.root / "seed"
        seed.mkdir()
        with PortfolioLedger(seed/"paper.sqlite", created_at=SUNDAY) as ledger:
            ledger.register_universe(UniverseSnapshot("seed-universe", SUNDAY, SUNDAY, ("AAPL",),
                                     "https://example.com/constituents", "2026-09-20T00:00:00Z"))
            session = next_session(SUNDAY)
            ledger.propose("seed-decision", decided_at=SUNDAY, targets={"AAPL": "0.1"},
                           universe_id="seed-universe", evidence_refs=["source-proof"],
                           expected_open_at=session.opens_at, calendar_source=session.source)
        self.config["seed_dir"] = str(seed)
        def market(directory):
            monday = stamp(self.at) >= "2026-09-14T13:31:00Z"
            return FixtureMarket(directory, now=stamp(self.at), fixtures={"AAPL": fixture(monday=monday)})
        service = self.service(market_factory=market)
        with service.locked():
            service.tick()
        with PortfolioLedger(self.root/"state/paper.sqlite") as ledger:
            self.assertEqual(ledger.public_state()["holdings"], [])
        self.at = timestamp("2026-09-14T13:31:00Z").timestamp()
        # No research permission: paper synchronization still works.
        with service.locked():
            service.tick()
        self.at += 60
        with service.locked():
            service.tick()
        with PortfolioLedger(self.root/"state/paper.sqlite") as ledger:
            self.assertEqual(len(ledger.public_state()["holdings"]), 1)
            self.assertEqual(len([x for x in ledger.events() if x["kind"] == "rebalance"]), 1)
        with PortfolioLedger(seed/"paper.sqlite") as ledger:
            self.assertEqual(ledger.public_state()["holdings"], [])

    def test_daily_packets_keep_prior_epoch_bytes_and_new_membership_identity(self):
        service = self.service()
        self.at = timestamp(MONDAY).timestamp()
        self.admit()
        with service.locked():
            service.tick()
        prior = Path(self.runs[0]["evidence_path"])
        original = prior.read_bytes()
        self.at = timestamp(MONDAY).timestamp()+86400
        self.admit()
        with service.locked():
            service.tick()
        self.assertEqual(prior.read_bytes(), original)
        a, b = [json.loads(Path(config["evidence_path"]).read_text()) for config in self.runs]
        self.assertNotEqual(a["universe"]["id"], b["universe"]["id"])
        self.assertLess(a["universe"]["captured_at"], b["universe"]["captured_at"])

    def test_weekly_pacing_never_unlocks_entire_budget_on_monday(self):
        service = self.service()
        for hours in (0, 3, 12, 23):
            self.at = timestamp(MONDAY).timestamp()+hours*3600
            self.assertLessEqual(service.allowance(), Decimal("20"))
        self.at = timestamp(MONDAY).timestamp()+4*86400
        self.assertLess(service.allowance(), Decimal("100"))

    def test_config_validation_rejects_unbounded_or_changed_inputs(self):
        path = self.root/"config.json"
        save(path, self.config)
        self.assertEqual(read_config(path), self.config)
        for field, value in (("session_seconds", 86400), ("admission_max_age_seconds", 100000),
                             ("session_inference_budget_usd", "1000"), ("week_ends_at", "2027-01-01T00:00:00Z")):
            save(path, {**self.config, field: value})
            with self.assertRaises(ValueError):
                read_config(path)

    def test_terminal_unknown_usage_keeps_its_hold_without_blocking_next_epoch(self):
        self.at = timestamp(MONDAY).timestamp()+600
        self.admit()
        def terminal_unknown(config, data, controller):
            client = Client(Path(config["state_dir"])/"requests.sqlite", config,
                            transport=lambda *a: None, clock=lambda: self.at)
            research = Research(Path(config["state_dir"])/"research.sqlite", data)
            research.add("unknown", 0, "company", "AAPL", "kimi_flex", "source", "question", max_output=128)
            task = research.waiting()[0]
            identity = client.submit_intent(task["id"], task["profile"], json.loads(task["body"]))
            with client.connect() as db:
                db.execute("UPDATE requests SET status='completed',response_id='resp_unknown',error='terminal_usage_unsettled' WHERE id=?", (identity,))
            self.at = config["ends_epoch"]
        service = self.service(executor=terminal_unknown)
        with service.locked():
            service.tick()
        with service.connect() as db:
            row = db.execute("SELECT * FROM epochs").fetchone()
        self.assertEqual(row["status"], "drained_unsettled")
        held = Decimal(service.totals()["reserved_usd"])
        self.assertGreater(held, 0)
        self.assertLess(held, Decimal(row["reserved"]))
        self.admit()
        service.executor = self.execute
        with service.locked():
            service.tick()
        self.assertEqual(service.totals()["unsettled_requests"], 1)
        self.assertEqual(Decimal(service.totals()["reserved_usd"]), held)
        self.assertNotEqual(self.runs[0]["run_id"], json.loads(row["config"])["run_id"])

    def test_supercache_age_uses_original_request_clock_not_heartbeat(self):
        service = self.service()
        research = Research(self.root/"research.sqlite", evidence())
        created = self.at-3600
        row = {"id": "cache-one", "task_id": "cache-write-v1", "status": "completed", "cost": "1",
               "error": None, "created": created, "updated": created+30,
               "response": canonical({"metadata": {"supercache_write_input_tokens": "4096"}})}
        client = SimpleNamespace(observations=lambda: [row])
        service.record_cache(research, client)
        self.assertTrue(service.cache_ready(research))
        self.at += 23*3600
        service.record_cache(research, client)
        self.assertFalse(service.cache_ready(research))

    def test_fresh_credit_grant_caps_new_epoch_and_individual_reservation(self):
        self.at = timestamp(MONDAY).timestamp()
        self.admit(max_additional_inference_usd="0.25", max_inference_committed_usd="0.25")
        service = self.service()
        service.initialize()
        _, config = service.prepare_epoch()
        self.assertEqual(Decimal(config["inference_budget_usd"]), Decimal("0.25"))
        self.assertFalse(service.reservation_allowed(Decimal("0.26")))
        self.assertTrue(service.reservation_allowed(Decimal("0.25")))
        self.at += 181
        self.assertFalse(service.reservation_allowed(Decimal("0.01")))

    def test_main_progress_timestamp_is_not_advanced_by_heartbeat(self):
        service = self.service()
        first = service.health()
        self.at += 600
        later = service.health()
        self.assertEqual(first["progress_at"], later["progress_at"])
        self.assertNotEqual(first["heartbeat_at"], later["heartbeat_at"])

    def test_cash_baseline_preserves_first_market_open_and_is_idempotent(self):
        with PortfolioLedger(self.root/"paper.sqlite", created_at=SUNDAY) as ledger:
            session = next_session(SUNDAY)
            observed = "2026-09-14T13:31:00Z"
            point = BenchmarkPoint(as_of=session.opens_at, value="100", source=YAHOO_SP500TR,
                                   captured_at=observed, source_sha256="a"*64)
            for _ in range(2):
                ledger.establish_cash_baseline(market_session=session, benchmark=point, observed_at=observed)
            self.assertEqual(ledger.public_state()["performance"]["started_at"], session.opens_at)
            self.assertEqual(ledger.public_state()["performance"]["benchmark"]["return_pct"], "0")
            self.assertEqual(len(ledger.public_state()["history"]), 1)
            self.assertEqual(ledger.public_state()["holdings"], [])

    def test_real_runner_two_epochs_share_voyage_sequence_and_terminal_only_at_week_end(self):
        from portfolio_runtime.telemetry import Voyage
        self.at = timestamp(MONDAY).timestamp()
        self.config.update(voyage_id="voyage_week_test", fetch_filings=False,
                           wave_size=1, max_concurrency=1)
        sends = []
        def trace_factory(path, config):
            return Voyage(path, config, transport=lambda method, route, body: sends.extend(body["events"]))
        class Transport:
            headers = {}
            def __call__(self, method, route, body, request_id):
                result = answer()
                try:
                    packet = json.loads(body["input"][-1]["content"])
                except ValueError:
                    packet = {}
                if packet.get("task") == "allocation":
                    result["targets"] = [{"symbol": "AAPL", "weight": "0.1"}]
                if packet.get("task") == "portfolio_critic":
                    result.update(review_verdict="approve", proposal_sha256=packet["proposal_sha256"])
                return {"id": "resp_"+request_id.replace("-", ""), "status": "completed", "model": body["model"],
                        "usage": {"input_tokens": 100, "output_tokens": 20, "input_tokens_details": {"cached_tokens": 0}},
                        "output": [{"type": "message", "content": [{"type": "output_text", "text": canonical(result)}]}]}
        transport = Transport()
        def advance(seconds):
            self.at += seconds
            self.admit(max_additional_inference_usd="100", max_inference_committed_usd="100")
        def execute(config, data, controller):
            with (patch.object(runner, "Client", side_effect=lambda path, c: Client(path, c, transport=transport, clock=lambda: self.at)),
                  patch.object(runner, "ThreadPoolExecutor", ImmediatePool),
                  patch.object(runner.time, "time", side_effect=lambda: self.at),
                  patch.object(runner.time, "sleep", side_effect=advance),
                  patch.object(runner, "utc_now", side_effect=lambda: stamp(self.at))):
                return runner.run(config, data, controller=controller)
        service = self.service(executor=execute, trace_factory=trace_factory)
        for _ in range(2):
            self.admit(max_additional_inference_usd="100", max_inference_committed_usd="100")
            with service.locked():
                service.tick()
        self.assertEqual(len([e for e in sends if e["kind"] == "research.epoch_completed"]), 2)
        self.assertFalse(any(e["kind"] == "voyage.completed" for e in sends))
        self.assertEqual(len({e["sequence_id"] for e in sends}), len(sends))
        self.assertGreater(service.totals()["completed"], 5)
        self.at = timestamp(SATURDAY).timestamp()
        with service.locked():
            service.tick()
        self.assertEqual(len([e for e in sends if e["kind"] == "voyage.completed"]), 1)
        self.assertEqual(sends[-1]["kind"], "voyage.completed")

    def test_expanded_technical_ceiling_does_not_expand_exploration_and_duplicates_downshift(self):
        self.config.update(adaptive_spending=True, weekly_inference_budget_usd="1000", session_inference_budget_usd="4.625")
        self.at = timestamp(MONDAY).timestamp()
        service = self.service()
        for _ in range(2):
            self.admit(max_additional_inference_usd="1000", max_inference_committed_usd="1000")
            with service.locked():
                service.tick()
        self.assertEqual([config["inference_budget_usd"] for config in self.runs], ["4.62500000", "4.62500000"])
        self.admit(max_additional_inference_usd="1000", max_inference_committed_usd="1000")
        with service.locked():
            service.tick()
        self.assertEqual(len(self.runs), 2)
        self.assertEqual(service.funding_plan["mode"], "maintenance")
        self.assertEqual(service.health()["funding"]["planned_inference_usd_per_day"], 6)
        self.assertFalse(service.funding_plan["expansion_eligible"])
        self.at = timestamp(MONDAY).timestamp()+7*3600
        self.admit(max_additional_inference_usd="1000", max_inference_committed_usd="1000")
        with service.locked():
            service.tick()
        self.assertEqual(self.runs[-1]["inference_budget_usd"], "1.50000000")
        self.assertTrue((self.root/"state/paper-health.json").exists())

    def test_fresh_fundamentals_restore_base_but_quotes_or_rewording_cannot(self):
        self.config.update(adaptive_spending=True, weekly_inference_budget_usd="1000", session_inference_budget_usd="4.625")
        self.at = timestamp(MONDAY).timestamp()
        service = self.service()
        for _ in range(2):
            self.admit()
            with service.locked():
                service.tick()
        data = service.daily_evidence()
        data["captured_at"] = stamp(self.at)
        data["companies"][0]["research_price"] = {"price": "10000", "as_of": stamp(self.at)}
        data["companies"][0]["random_model_question"] = "A new question cannot authorize funding."
        self.assertEqual(service.choose_funding(data)["mode"], "maintenance")
        data["companies"][0]["facts"]["net_income"][0]["observations"][0]["val"] = 900
        restored = service.choose_funding(data)
        self.assertEqual(restored["mode"], "exploration")
        self.assertEqual(restored["epoch_cap_usd"], "4.625")
        self.assertEqual(restored["planned_inference_usd_per_day"], 111)
        self.assertFalse(restored["investment_roi_proven"])

    def test_storage_headroom_stops_new_reservations_but_not_request_recovery(self):
        self.at = timestamp(MONDAY).timestamp()
        self.admit(max_additional_inference_usd="100", max_inference_committed_usd="100")
        free = [2*1024**3]
        service = self.service(disk_free=lambda: free[0])
        self.assertTrue(service.admission_allowed())
        free[0] = 500*1024**2
        self.assertFalse(service.admission_allowed())
        self.assertFalse(service.reservation_allowed(Decimal("0.01")))
        self.assertFalse(service.should_stop())  # Existing provider receipts still settle.
        self.assertEqual(service.health()["storage"]["free_bytes"], free[0])

    def test_new_actual_loss_outcome_unlocks_one_review_but_repeated_receipt_does_not(self):
        self.config.update(adaptive_spending=True, weekly_inference_budget_usd="1000", session_inference_budget_usd="4.625")
        self.at = timestamp(MONDAY).timestamp()
        service = self.service()
        for _ in range(3):
            self.admit()
            with service.locked():
                service.tick()
        self.assertEqual(service.funding_plan["mode"], "maintenance")
        with PortfolioLedger(self.root/"state/paper.sqlite") as ledger:
            at = stamp(self.at)
            data = service.daily_evidence()
            session = next_session(at)
            ledger.propose("actual-observation", decided_at=at, targets={"AAPL": "0.1"},
                           universe_id=data["universe"]["id"], evidence_refs=["source-observation"],
                           expected_open_at=session.opens_at, calendar_source=session.source)
            market = FixtureMarket(self.root, now="2026-09-14T13:31:00Z", fixtures={"AAPL": fixture()})
            market.fill_pending(ledger)
            market.now = "2026-09-14T20:01:00Z"
            market.fixtures["AAPL"] = fixture(close=95, closed=True)
            market.mark_close(ledger)
            self.at = timestamp(market.now).timestamp()
            service.outcomes.observe(ledger, observed_at=market.now)
        context = service.outcomes.context(cutoff=stamp(self.at))
        self.assertLess(Decimal(context[0]["portfolio_return_pct"]), 0)
        self.assertEqual(service.choose_funding(data)["reason_code"], "new_observed_investment_outcome")
        self.admit(max_additional_inference_usd="1000", max_inference_committed_usd="1000")
        prepared = service.prepare_epoch()
        self.assertIsNotNone(prepared)
        self.assertEqual(prepared[1]["inference_budget_usd"], "4.62500000")
        self.assertEqual(len(prepared[1]["funding_plan"]["new_outcome_ids"]), 1)
        # Observing the same unchanged ledger again adds no spending authority.
        with PortfolioLedger(self.root/"state/paper.sqlite") as ledger:
            service.outcomes.observe(ledger, observed_at=stamp(self.at))
        self.assertEqual(service.choose_funding(data)["mode"], "maintenance")

    def test_exhausted_company_work_still_reviews_actual_loss_with_asap_proposal_and_critic(self):
        self.config.update(adaptive_spending=True, weekly_inference_budget_usd="1000",
                           session_inference_budget_usd="4.625", fetch_filings=False,
                           max_concurrency=1, wave_size=1, seed_dir=str(self.root/"seed"))
        seed = Research(self.root/"seed/research.sqlite", evidence())
        for company in evidence()["companies"]:
            for n in range(3):
                identity = company["symbol"]+str(n)
                result = answer()
                for claim in result["claims"]:
                    claim["symbol"] = company["symbol"]
                seed.add(identity, 0, "company", company["symbol"], "kimi_asap", "source",
                         canonical({"evidence": company, "question": "A resolved investment question "+str(n)}))
                with seed.connect() as db:
                    db.execute("UPDATE tasks SET status='complete',result=?,grade=? WHERE id=?",
                               (canonical(result), canonical(grade_result(result, seed.companies)), identity))
        self.at = timestamp(MONDAY).timestamp()
        service = self.service()
        service.initialize()
        # A focused investment-outcome review must not spend its allowance on
        # unrelated memory experiments, even when their planner is available.
        service.lab.plan_epoch = lambda *a, **k: self.fail("Outcome-only review must skip diagnostics")
        with PortfolioLedger(self.root/"state/paper.sqlite") as ledger:
            service.paper_sync(ledger)
            data = service.daily_evidence()
            decision_at = "2026-09-14T12:00:00Z"
            session = next_session(decision_at)
            ledger.propose("initial-loss", decided_at=decision_at, targets={"AAPL": "0.1"},
                           universe_id=data["universe"]["id"], evidence_refs=["original-evidence"],
                           expected_open_at=session.opens_at, calendar_source=session.source)
            market = FixtureMarket(self.root, now="2026-09-14T13:31:00Z", fixtures={"AAPL": fixture()})
            market.fill_pending(ledger)
            market.now = "2026-09-14T20:01:00Z"
            market.fixtures["AAPL"] = fixture(close=95, closed=True)
            market.mark_close(ledger)
            self.at = timestamp(market.now).timestamp()
            service.outcomes.observe(ledger, observed_at=market.now)
        calls = []
        test = self
        class Transport:
            headers = {}
            def __call__(self, method, route, body, request_id):
                packet = json.loads(body["input"][-1]["content"])
                calls.append(packet["task"])
                test.assertFalse(body["background"])
                result = answer()
                if packet["task"] == "allocation":
                    test.assertEqual(body["model"], "deepseek-ai/DeepSeek-V4-Pro-0813")
                    test.assertEqual(body["metadata"]["completion_window"], "asap")
                    test.assertEqual(packet["trigger"], "new_actual_investment_outcome")
                    test.assertTrue(packet["checked_research"])
                    test.assertLess(Decimal(packet["observed_investment_outcomes"][0]["portfolio_return_pct"]), 0)
                    result["targets"] = [{"symbol": "AAPL", "weight": "0.15"}]
                elif packet["task"] == "portfolio_critic":
                    result.update(review_verdict="approve", proposal_sha256=packet["proposal_sha256"])
                else:
                    test.fail("Exhausted company work must not create artificial research: "+packet["task"])
                return {"id": "resp_"+request_id.replace("-", ""), "status": "completed", "model": body["model"],
                        "usage": {"input_tokens": 100, "output_tokens": 20, "input_tokens_details": {"cached_tokens": 0}},
                        "output": [{"type": "message", "content": [{"type": "output_text", "text": canonical(result)}]}]}
        def advance(seconds):
            self.at += seconds
            self.admit(max_additional_inference_usd="1000", max_inference_committed_usd="1000")
        def execute(config, data, controller):
            with (patch.object(runner, "Client", side_effect=lambda path, c: Client(path, c, transport=Transport(), clock=lambda: self.at)),
                  patch.object(runner, "ThreadPoolExecutor", ImmediatePool),
                  patch.object(runner.time, "time", side_effect=lambda: self.at),
                  patch.object(runner.time, "sleep", side_effect=advance),
                  patch.object(runner, "utc_now", side_effect=lambda: stamp(self.at))):
                return runner.run(config, data, controller=controller)
        service.executor = execute
        self.admit(max_additional_inference_usd="1000", max_inference_committed_usd="1000")
        with service.locked():
            service.tick()
        self.assertEqual(calls, ["allocation", "portfolio_critic"])
        with PortfolioLedger(self.root/"state/paper.sqlite") as ledger:
            pending = ledger.public_state()["pending_decisions"]
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["targets"], [{"symbol": "AAPL", "weight": "0.15"}])


class DecisionBoundaryTests(unittest.TestCase):
    setUp = runtime_fixtures.RunnerTests.setUp
    tearDown = runtime_fixtures.RunnerTests.tearDown
    completed = runtime_fixtures.RunnerTests.completed
    checked_allocation = runtime_fixtures.RunnerTests.checked_allocation
    ledger = runtime_fixtures.RunnerTests.ledger
    def test_due_precommitted_open_cannot_be_superseded_by_new_postopen_research(self):
        first = self.checked_allocation(wave=0)
        with self.ledger() as ledger, patch.object(runner, "utc_now", return_value="2026-09-13T15:00:00Z"):
            runner.propose_checked(self.config, self.research, ledger)
            newest = self.checked_allocation(targets=[{"symbol": "MSFT", "weight": "0.1"}], wave=1)
            monday = "2026-09-14T13:31:00Z"
            with patch.object(runner, "utc_now", return_value=monday):
                runner.propose_checked(self.config, self.research, ledger)
                self.assertEqual(ledger.public_state()["pending_decisions"][0]["id"], first)
                market = FixtureMarket(self.root, now=monday, fixtures={"AAPL": fixture()})
                market.fill_pending(ledger)
                runner.propose_checked(self.config, self.research, ledger)
            self.assertEqual(ledger.public_state()["pending_decisions"][0]["id"], newest)
            event = next(e for e in ledger.events() if e["id"] == newest)
            self.assertEqual(event["payload"]["expected_open_at"], "2026-09-15T13:30:00Z")

    def test_paced_critic_reservation_blocks_cheaper_work_until_review_can_fit(self):
        self.config["inference_budget_usd"] = "1"
        self.research.add("critical", 0, "portfolio_critic", None, "k3", "x"*22000, "review", max_output=8192)
        self.research.add("cheap", 0, "company", "AAPL", "kimi_flex", "source", "research", max_output=16)
        with self.research.connect() as db:
            db.execute("INSERT INTO waves VALUES(0,?,?)", (self.at, "{}"))
        calls = []
        def transport(method, route, body, identity):
            calls.append(identity)
            return {"id": "resp_critical", "status": "completed", "model": body["model"],
                    "usage": {"input_tokens": 100, "output_tokens": 20, "input_tokens_details": {"cached_tokens": 0}},
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": canonical(answer())}]}]}
        client = Client(self.root/"requests.sqlite", self.config, transport=transport, clock=lambda: self.at)
        controller = SimpleNamespace(trace=None, initialize_epoch=lambda *a: None,
            admission_allowed=lambda: True, should_stop=lambda: False, paper_sync=lambda ledger: None,
            cache_ready=lambda research: False, checkpoint=lambda c,l,r,cl,p: p)
        def run_once():
            ledger = self.ledger()
            with (patch.object(runner, "initialize", return_value=(client, self.research, ledger)),
                  patch.object(runner, "ThreadPoolExecutor", ImmediatePool),
                  patch.object(runner.time, "time", side_effect=lambda: self.at),
                  patch.object(runner, "utc_now", side_effect=lambda: stamp(self.at))):
                runner.run(self.config, self.data, once=True, controller=controller)
        run_once()
        self.assertEqual(client.totals()["requests"], 0)
        self.assertEqual(calls, [])
        self.at += 200
        run_once()
        self.assertEqual([row["task_id"] for row in client.observations()], ["critical"])
        self.assertEqual(len(calls), 1)


class HistoryTests(unittest.TestCase):
    def test_prior_memory_is_regraded_and_trials_never_become_future_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = Research(root/"old.sqlite", evidence())
            for identity, kind in (("ordinary", "company"), ("holdout", "policy_trial")):
                old.add(identity, 0, kind, "AAPL", "kimi_asap", "source", canonical({
                    "question": "What supports this business?", "evidence": evidence()["companies"][0]}))
                with old.connect() as db:
                    db.execute("UPDATE tasks SET status='complete',result=?,grade=? WHERE id=?",
                               (canonical(answer()), canonical(grade_result(answer(), old.companies)), identity))
            changed = evidence()
            changed["companies"][0]["facts"]["net_income"][0]["observations"][0]["val"] = 500
            current = Research(root/"new.sqlite", changed)
            current.carry_history([old.path])
            current.carry_history([old.path])
            result = current.latest("AAPL", 3)
            self.assertEqual(len(result), 1)
            self.assertFalse(result[0]["grade"]["source_check_passed"])
            self.assertEqual(current.checked_for_allocation(), [])
            self.assertIn("Prior hypothesis", result[0]["notice"])
            with current.connect() as db:
                self.assertEqual(db.execute("SELECT count(*) FROM prior_work").fetchone()[0], 1)
            self.assertNotEqual(Research.source_fingerprint(old.companies["AAPL"]),
                                Research.source_fingerprint(current.companies["AAPL"]))

    def test_unchanged_capture_timestamp_does_not_create_novel_work(self):
        company = evidence()["companies"][0]
        before = Research.source_fingerprint(company)
        company["captured_at"] = "2026-09-15T12:00:00Z"
        company["sha256"] = "f"*64
        self.assertEqual(Research.source_fingerprint(company), before)


if __name__ == "__main__":
    unittest.main()
