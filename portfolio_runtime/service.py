"""Persistent paper portfolio with bounded, immutable weekday research epochs.

The cloud supervisor owns funding/availability decisions. This process alone
writes the paper account, conservatively reserves inference before an epoch,
and resumes exact accepted requests after interruption. It never trades live.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, time as daytime, timedelta
from decimal import Decimal
import fcntl
import hashlib
import json
from pathlib import Path
import re
import signal
import shutil
import sqlite3
import threading
import time

from .contracts import NEW_YORK, UniverseSnapshot, identifier, timestamp
from .evidence import assemble, capture, save
from .ledger import PortfolioLedger
from .market import YahooMarketData
from .provider import Client, ClosingConnection, PROFILES, TERMINAL, canonical
from . import runner


def stamp(epoch):
    return runner.stamp(epoch)


def read_config(path):
    config = json.loads(Path(path).read_text())
    required = {"schema_version", "service_id", "state_dir", "week_starts_at",
                "week_ends_at", "weekly_inference_budget_usd",
                "session_inference_budget_usd", "session_seconds", "account_created_at",
                "key_fingerprint", "initial_evidence_path", "admission_path"}
    if not isinstance(config, dict) or not required <= config.keys() or config["schema_version"] != 1:
        raise ValueError("Incomplete weekday service contract")
    identifier(config["service_id"])
    if len(config["service_id"]) > 64:
        raise ValueError("Service identity is too long")
    start, end = timestamp(config["week_starts_at"]), timestamp(config["week_ends_at"])
    timestamp(config["account_created_at"])
    if not timedelta(hours=1) <= end-start <= timedelta(days=7):
        raise ValueError("An explicit one-week envelope is required")
    if timestamp(config["account_created_at"]) > start:
        raise ValueError("Paper account must exist before the service window")
    for key in ("weekly_inference_budget_usd", "session_inference_budget_usd"):
        value = Decimal(str(config[key]))
        if not value.is_finite() or not 0 < value <= (100 if key.startswith("session") else 100000):
            raise ValueError("Invalid inference allocation")
    if Decimal(config["session_inference_budget_usd"]) > Decimal(config["weekly_inference_budget_usd"]):
        raise ValueError("An epoch cannot exceed the weekly allocation")
    if type(config["session_seconds"]) is not int or not 600 <= config["session_seconds"] <= 28800:
        raise ValueError("Each research epoch is bounded to 10 minutes–8 hours")
    for key in ("state_dir", "initial_evidence_path", "admission_path", "seed_dir"):
        if key in config and (not isinstance(config[key], str) or not Path(config[key]).is_absolute() or Path(config[key]).is_symlink()):
            raise ValueError("Service paths must be explicit and nonsymlink")
    if not re.fullmatch(r"[0-9a-f]{64}", config["key_fingerprint"]):
        raise ValueError("A private key fingerprint is required")
    if config.get("publish_url") not in (None, "https://blakewoods.us/api/portfolio/state"):
        raise ValueError("Unexpected public destination")
    if type(config.get("admission_max_age_seconds", 180)) is not int or not 60 <= config.get("admission_max_age_seconds", 180) <= 600:
        raise ValueError("Invalid supervisor freshness bound")
    if type(config.get("settlement_drain_seconds", 300)) is not int or not 60 <= config.get("settlement_drain_seconds", 300) <= 3600:
        raise ValueError("Invalid final settlement window")
    if type(config.get("adaptive_spending", False)) is not bool:
        raise ValueError("Adaptive spending must be explicit")
    return config


def next_weekday(epoch):
    local = timestamp(stamp(epoch)).astimezone(NEW_YORK)
    while local.weekday() >= 5:
        local = datetime.combine(local.date()+timedelta(days=1), daytime(), NEW_YORK)
    return int(local.timestamp())


def weekday_seconds(start, end):
    """Elapsed weekday time; weekends cannot unlock additional spending."""
    total = 0
    while start < end:
        local = timestamp(stamp(start)).astimezone(NEW_YORK)
        boundary = datetime.combine(local.date()+timedelta(days=1), daytime(), NEW_YORK).timestamp()
        stop = min(end, boundary)
        if local.weekday() < 5:
            total += max(0, stop-start)
        start = stop
    return total


def request_totals(path):
    empty = {"known_cost_usd": "0", "committed_usd": "0", "unsettled_requests": 0,
             "requests": 0, "completed": 0, "pending_requests": 0}
    if not Path(path).is_file():
        return empty
    with sqlite3.connect("file:"+str(path)+"?mode=ro", uri=True, factory=ClosingConnection) as db:
        rows = db.execute("SELECT reserved,cost,status FROM requests").fetchall()
    known = sum((Decimal(cost) for _, cost, _ in rows if cost is not None), Decimal(0))
    committed = sum((Decimal(cost if cost is not None else reserved) for reserved, cost, _ in rows), Decimal(0))
    return {"known_cost_usd": format(known, "f"), "committed_usd": format(committed, "f"),
            "unsettled_requests": sum(cost is None for _, cost, _ in rows),
            "requests": len(rows), "completed": sum(status == "completed" for _, _, status in rows),
            "pending_requests": sum(status not in TERMINAL for _, _, status in rows)}


class Service:
    def __init__(self, config, *, clock=time.time, sleeper=time.sleep, executor=runner.run,
                 refresher=None, market_factory=YahooMarketData, policy_factory=None, trace_factory=None,
                 disk_free=None):
        self.config, self.clock, self.sleeper, self.executor = config, clock, sleeper, executor
        self.root = Path(config["state_dir"])
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.refresher = refresher or self._refresh
        self.market_factory = market_factory
        self.policy_factory = policy_factory
        self.disk_free = disk_free or (lambda: shutil.disk_usage(self.root).free)
        self.trace_factory, self.trace = trace_factory, None
        self.start = timestamp(config["week_starts_at"]).timestamp()
        self.end = timestamp(config["week_ends_at"]).timestamp()
        self.stopping = False
        self.terminal = False
        self.status, self.reason, self.next_wake, self.current = "starting", None, self.start, None
        self._thread_stop = threading.Event()
        self._health_lock = threading.Lock()
        self._last_market = 0
        self._last_evaluation = None
        self._last_recovery = 0
        self._paper_issue = False
        self.progress_at = self.clock()
        self.stage = "initializing"
        self.lab = None
        self.outcomes = None
        self.funding_plan = self._funding_plan("exploration", "initial_exploration")
        with self.connect() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS contract(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS epochs(id TEXT PRIMARY KEY,config TEXT NOT NULL,reserved TEXT NOT NULL,known TEXT NOT NULL DEFAULT '0',committed TEXT NOT NULL DEFAULT '0',status TEXT NOT NULL DEFAULT 'prepared',created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS value_receipts(epoch_id TEXT PRIMARY KEY,body TEXT NOT NULL,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS checked_fundamentals(identity TEXT PRIMARY KEY,first_epoch TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS consumed_outcomes(identity TEXT PRIMARY KEY,epoch_id TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS immutable_contract BEFORE UPDATE ON contract BEGIN SELECT RAISE(ABORT,'immutable service contract'); END;
CREATE TRIGGER IF NOT EXISTS immutable_value_receipt BEFORE UPDATE ON value_receipts BEGIN SELECT RAISE(ABORT,'immutable value receipt'); END;
CREATE TRIGGER IF NOT EXISTS immutable_epoch BEFORE UPDATE OF id,config,reserved,created ON epochs BEGIN SELECT RAISE(ABORT,'immutable research epoch'); END;""")
            old = db.execute("SELECT body FROM contract WHERE id=1").fetchone()
            if old and old[0] != canonical(config):
                raise ValueError("The running week's service contract cannot change")
            db.execute("INSERT OR IGNORE INTO contract VALUES(1,?)", (canonical(config),))
            latest = db.execute("SELECT config FROM epochs ORDER BY created DESC LIMIT 1").fetchone()
            if latest and json.loads(latest[0]).get("funding_plan"):
                self.funding_plan = json.loads(latest[0])["funding_plan"]

    def connect(self):
        db = sqlite3.connect(self.root / "service.sqlite", timeout=30, factory=ClosingConnection)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    @contextmanager
    def locked(self):
        with (self.root / "service.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield

    def admission(self):
        try:
            path = Path(self.config["admission_path"])
            if path.is_symlink() or path.stat().st_size > 8192:
                raise ValueError("Invalid supervisor permission")
            doc = json.loads(path.read_text())
            age = self.clock()-timestamp(doc["updated_at"]).timestamp()
            if (doc.get("schema_version") != 1 or doc.get("service_id") != self.config["service_id"]
                or type(doc.get("allow_new_research")) is not bool
                or not 0 <= age <= self.config.get("admission_max_age_seconds", 180)):
                raise ValueError("Missing or stale supervisor permission")
            return doc
        except (OSError, ValueError, KeyError, TypeError):
            return {"allow_new_research": False, "reason_code": "recovering"}

    def admission_allowed(self):
        doc = self.admission()
        return (not self.stopping and not doc.get("stop_requested")
                and self.start <= self.clock() < self.end
                and timestamp(stamp(self.clock())).astimezone(NEW_YORK).weekday() < 5
                and doc["allow_new_research"] and self.storage_available())

    def storage_available(self):
        return self.disk_free() >= 1024**3

    def should_stop(self):
        # Accepted requests stay attached to their immutable epoch and settle
        # through normal polling. A stop prevents new intent immediately.
        if self.stopping:
            return True
        if self.admission().get("stop_requested"):
            if self.current is None:
                return True
            path = self.root / "epochs" / self.current / "requests.sqlite"
            return request_totals(path)["pending_requests"] == 0
        return False

    def request_stop(self):
        self.stopping = True

    def reservation_allowed(self, reserve):
        if not self.admission_allowed():
            return False
        absolute = self.admission().get("max_inference_committed_usd")
        if absolute is None:
            return False
        try:
            cap = Decimal(str(absolute))
            return cap.is_finite() and cap >= 0 and Decimal(self.totals()["committed_usd"])+reserve <= cap
        except (ValueError, ArithmeticError):
            return False

    def totals(self):
        result = {"known_cost_usd": Decimal(0), "committed_usd": Decimal(0),
                  "reserved_usd": Decimal(0), "requests": 0, "completed": 0,
                  "unsettled_requests": 0, "pending_requests": 0, "parked_requests": 0}
        with self.connect() as db:
            rows = db.execute("SELECT * FROM epochs").fetchall()
        for row in rows:
            config = json.loads(row["config"])
            totals = request_totals(Path(config["state_dir"]) / "requests.sqlite")
            result["known_cost_usd"] += Decimal(totals["known_cost_usd"])
            result["committed_usd"] += Decimal(totals["committed_usd"])
            # Release unused allowance only after terminal reconciliation.
            result["reserved_usd"] += (Decimal(totals["committed_usd"])
                                       if row["status"] in ("complete", "drained_unsettled", "parked_unsettled") else Decimal(row["reserved"]))
            for key in ("requests", "completed", "unsettled_requests", "pending_requests"):
                result[key] += totals[key]
            if row["status"] == "parked_unsettled":
                result["parked_requests"] += totals["pending_requests"]
        return {key: format(value, "f") if isinstance(value, Decimal) else value
                for key, value in result.items()}

    def health(self):
        result = {"schema_version": 1, "service_id": self.config["service_id"],
                  "status": self.status, "heartbeat_at": stamp(self.clock()),
                  "next_wake_at": stamp(self.next_wake) if self.next_wake is not None else None,
                  "current_epoch": self.current, "week_ends_at": self.config["week_ends_at"],
                  "progress_at": stamp(self.progress_at), "stage": self.stage,
                  "progress_timeout_seconds": 1800 if self.stage in ("refreshing_sources", "paper_reconciliation") else 600,
                  "reason_code": self.reason,
                  "weekly_inference_budget_usd": self.config["weekly_inference_budget_usd"],
                  "funding": self.funding_plan,
                  "storage": {"free_bytes": self.disk_free(), "minimum_free_bytes": 1024**3},
                  "inference": self.totals()}
        # A dedicated writer prevents partial/overlapping atomic replacements
        # while the main thread assembles evidence or waits on a provider.
        with self._health_lock:
            path = self.root / "service-health.json"
            tmp = self.root / ("service-health-"+str(threading.get_ident())+".tmp")
            tmp.write_text(canonical(result)+"\n")
            tmp.chmod(0o600)
            tmp.replace(path)
        return result

    def heartbeat_loop(self):
        while not self._thread_stop.wait(30):
            try:
                self.health()
            except Exception:
                # A missing heartbeat is independently detected in Cloudflare;
                # this thread must never mutate accounting or retry research.
                pass

    def public_service(self):
        state = "waiting" if self.status == "starting" else self.status
        return {"id": self.config["service_id"], "status": state,
                "heartbeat_at": stamp(self.clock()),
                "next_wake_at": stamp(self.next_wake) if self.next_wake is not None else None,
                "week_ends_at": self.config["week_ends_at"], "reason_code": self.reason}

    def initialize(self):
        target = self.root / "paper.sqlite"
        seed = Path(self.config["seed_dir"]) if self.config.get("seed_dir") else None
        if not target.exists() and seed and (seed / "paper.sqlite").is_file():
            tmp = self.root / "paper-seed.tmp"
            with sqlite3.connect("file:"+str(seed / "paper.sqlite")+"?mode=ro", uri=True, factory=ClosingConnection) as source:
                with sqlite3.connect(tmp, factory=ClosingConnection) as dest:
                    source.backup(dest)
            tmp.chmod(0o600)
            tmp.replace(target)
        with PortfolioLedger(target, created_at=self.config["account_created_at"]) as ledger:
            ledger.public_state()  # Replay/check all existing event hashes.
        if self.lab is None:
            if self.policy_factory is None:
                from .improvement import PolicyLab
                self.policy_factory = PolicyLab
            self.lab = self.policy_factory(self.root / "improvement.sqlite")
        if self.outcomes is None:
            from .outcomes import OutcomeJournal
            self.outcomes = OutcomeJournal(self.root / "outcomes.sqlite")
        if self.config.get("adaptive_spending"):
            self.seed_value_coverage()
        if self.config.get("voyage_id") and self.trace is None:
            if self.trace_factory is None:
                from .telemetry import Voyage
                self.trace_factory = Voyage
            self.trace = self.trace_factory(self.root / "voyage.sqlite", self.config)

    def history_paths(self):
        paths = []
        if self.config.get("seed_dir"):
            seed = Path(self.config["seed_dir"])
            if (seed / "research.sqlite").is_file():
                paths.append(seed / "research.sqlite")
            paths.extend(sorted(seed.glob("epochs/*/research.sqlite")))
        paths.extend(sorted((self.root / "epochs").glob("*/research.sqlite")))
        return paths

    def initialize_epoch(self, config, research, client):
        self.funding_plan = config.get("funding_plan", self.funding_plan)
        client.reservation_guard = self.reservation_allowed
        research.bounded_novelty = True
        research.memory_limit = config["research_policy"]["memory_limit"]
        research.allocation_profile = "pro_asap"
        research.outcome_review_requested = bool(config.get("funding_plan", {}).get("new_outcome_ids"))
        input_bound = len(research.prefix("shared").encode())+4608
        estimated_write_hold = (Decimal(input_bound)*Decimal(PROFILES["kimi_flex"][2])*100
                                +Decimal(256)*Decimal(PROFILES["kimi_flex"][4]))/1_000_000
        research.enable_cache_write = estimated_write_hold <= Decimal(config["inference_budget_usd"])*Decimal("0.35")
        save(Path(config["state_dir"])/"cache-policy.json", {
            "schema_version": 1, "new_write_economical": research.enable_cache_write,
            "estimated_conservative_write_hold_usd": format(estimated_write_hold, "f"),
            "maximum_epoch_share": "0.35", "default": "ordinary_cache",
            "confirmed_shared_cache_available": self.cache_ready(research)})
        research.carry_history(self.history_paths())
        with PortfolioLedger(self.root / "paper.sqlite") as ledger:
            research.portfolio_context = ledger.public_state()
            self.outcomes.observe(ledger, observed_at=stamp(self.clock()))
            self.bind_outcome_context(config, ledger)
            research.investment_outcomes = self.outcomes.context(cutoff=stamp(self.clock()), limit=6)
        outcome_only = research.outcome_review_requested and not research.choose(1)
        research.enable_experiments = config.get("funding_plan", {}).get("mode") != "maintenance" and not outcome_only
        if research.enable_experiments:
            self.lab.plan_epoch(research, epoch_id=config["run_id"],
                                cutoff=stamp(config["started_epoch"]),
                                max_pairs=self.config.get("experiment_pairs_per_epoch", 4))

    def bind_outcome_context(self, config, ledger):
        for event in ledger.events():
            if event["kind"] == "decision" and event["id"].startswith(config["run_id"]+":"):
                self.outcomes.bind_context(event["id"], run_id=config["run_id"],
                    evidence_cutoff=stamp(config["started_epoch"]),
                    evidence_sha256=config["evidence_sha256"], policy=config["research_policy"],
                    observed_at=stamp(self.clock()))

    def _funding_plan(self, mode, reason, *, latest_receipt=None):
        initial = Decimal(self.config["session_inference_budget_usd"])
        cap = min(initial, Decimal("1.5")) if mode == "maintenance" else initial
        interval = max(21600, self.config["session_seconds"]) if mode == "maintenance" else self.config["session_seconds"]
        return {"schema_version": 1, "mode": mode, "reason_code": reason,
                "epoch_cap_usd": format(cap, "f"), "minimum_interval_seconds": interval,
                "planned_inference_usd_per_day": float(cap*Decimal(86400)/Decimal(interval)),
                "expansion_eligible": False,
                "expansion_blocker": "prospective_investment_policy_comparator_not_implemented",
                "investment_roi_proven": False, "latest_value_receipt": latest_receipt}

    @staticmethod
    def fundamental_fingerprints(evidence):
        # Price ticks, HTTP hashes, model confidence and reworded questions are
        # not new business evidence and cannot authorize more spending.
        return {company["symbol"]: hashlib.sha256(canonical(company.get("facts", {})).encode()).hexdigest()
                for company in evidence["companies"]}

    def seed_value_coverage(self):
        """Already completed Sunday research is not paid-for novelty Monday."""
        if not self.config.get("seed_dir"):
            return
        with self.connect() as db:
            if db.execute("SELECT 1 FROM checked_fundamentals WHERE identity='seed_import_complete'").fetchone():
                return
        seed = Path(self.config["seed_dir"])
        paths = [seed/"research.sqlite", *sorted(seed.glob("epochs/*/research.sqlite"))]
        identities = set()
        for path in paths:
            if not path.is_file():
                continue
            with sqlite3.connect("file:"+str(path)+"?mode=ro", uri=True, factory=ClosingConnection) as source:
                for symbol, body, grade in source.execute("SELECT symbol,body,grade FROM tasks WHERE kind='company' AND status='complete'"):
                    try:
                        if not json.loads(grade)["source_check_passed"]:
                            continue
                        company = json.loads(json.loads(body)["input"][-1]["content"])["evidence"]
                        if company["symbol"] != symbol:
                            continue
                        digest = hashlib.sha256(canonical(company.get("facts", {})).encode()).hexdigest()
                        identities.add(symbol+":"+digest)
                    except (ValueError, KeyError, TypeError):
                        continue
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for identity in identities:
                db.execute("INSERT OR IGNORE INTO checked_fundamentals VALUES(?,'seed')", (identity,))
            db.execute("INSERT OR IGNORE INTO checked_fundamentals VALUES('seed_import_complete','seed')")

    def record_value(self, epoch_id, config):
        """Seal observational research productivity, never claim trading ROI."""
        if not self.config.get("adaptive_spending"):
            return
        with self.connect() as db:
            if db.execute("SELECT 1 FROM value_receipts WHERE epoch_id=?", (epoch_id,)).fetchone():
                return
        totals = request_totals(Path(config["state_dir"])/"requests.sqlite")
        if totals["pending_requests"] or totals["unsettled_requests"]:
            return  # Unknown cost cannot establish measured value for money.
        evidence = json.loads(Path(config["evidence_path"]).read_text())
        fingerprints = self.fundamental_fingerprints(evidence)
        path = Path(config["state_dir"])/"research.sqlite"
        checked = set()
        attempts = 0
        if path.exists():
            from .research import grade_result
            companies = {c["symbol"]: c for c in evidence["companies"]}
            with sqlite3.connect("file:"+str(path)+"?mode=ro", uri=True, factory=ClosingConnection) as source:
                for symbol, status, result in source.execute("SELECT symbol,status,result FROM tasks WHERE kind='company'"):
                    if status not in ("complete", "failed"):
                        continue
                    attempts += 1
                    if status == "complete" and symbol in companies and grade_result(json.loads(result), companies)["source_check_passed"]:
                        checked.add(symbol+":"+fingerprints[symbol])
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            fresh = [identity for identity in checked if not db.execute("SELECT 1 FROM checked_fundamentals WHERE identity=?", (identity,)).fetchone()]
            for identity in fresh:
                db.execute("INSERT OR IGNORE INTO checked_fundamentals VALUES(?,?)", (identity, epoch_id))
            cost = Decimal(totals["known_cost_usd"])
            receipt = {"schema_version": 1, "epoch_id": epoch_id, "observed_at": stamp(self.clock()),
                       "evidence_sha256": config["evidence_sha256"], "source_fingerprints": fingerprints,
                       "new_checked_fundamentals": len(fresh), "checked_fundamentals": len(checked),
                       "company_attempts": attempts, "known_inference_cost_usd": totals["known_cost_usd"],
                       "investment_outcomes_reserved_for_review": config.get("funding_plan", {}).get("new_outcome_ids", []),
                       "new_checked_fundamentals_per_usd": format(Decimal(len(fresh))/cost, "f") if cost else None,
                       "investment_roi_proven": False,
                       "interpretation": "New source-checked business evidence is research coverage, not demonstrated investment skill."}
            db.execute("INSERT OR IGNORE INTO value_receipts VALUES(?,?,?)", (epoch_id, canonical(receipt), self.clock()))
        save(Path(config["state_dir"])/"value-receipt.json", receipt)

    def choose_funding(self, evidence):
        if not self.config.get("adaptive_spending"):
            return self._funding_plan("exploration", "fixed_exploration")
        with self.connect() as db:
            rows = db.execute("SELECT body FROM value_receipts ORDER BY created DESC LIMIT 2").fetchall()
        receipts = [json.loads(row[0]) for row in rows]
        mode, reason = "exploration", "initial_exploration"
        if len(receipts) >= 2:
            changed = self.fundamental_fingerprints(evidence) != receipts[0]["source_fingerprints"]
            if changed:
                reason = "fresh_business_evidence"
            elif all(receipt["new_checked_fundamentals"] == 0 for receipt in receipts):
                mode, reason = "maintenance", "repeated_work_without_new_checked_evidence"
            else:
                reason = "continuing_unproven_investment_research"
        fresh_outcomes = []
        if self.outcomes is not None:
            with self.connect() as db:
                for outcome in self.outcomes.context(cutoff=stamp(self.clock()), limit=20):
                    # Later benchmark recovery for the same decision/close is
                    # improved attribution, not a fresh trading outcome that
                    # can repeatedly unlock another research allocation.
                    identity = hashlib.sha256(canonical([outcome["decision_id"], outcome["market_as_of"]]).encode()).hexdigest()
                    if not db.execute("SELECT 1 FROM consumed_outcomes WHERE identity=?", (identity,)).fetchone():
                        fresh_outcomes.append(identity)
        if fresh_outcomes:
            mode, reason = "exploration", "new_observed_investment_outcome"
        plan = self._funding_plan(mode, reason, latest_receipt=receipts[0]["epoch_id"] if receipts else None)
        plan["new_outcome_ids"] = fresh_outcomes
        save(self.root/"funding-plan.json", plan)
        return plan

    def cache_ready(self, research):
        digest = hashlib.sha256(research.prefix("shared").encode()).hexdigest()
        path = self.root / "cache" / (digest + ".json")
        if not path.exists():
            return False
        receipt = json.loads(path.read_text())
        return (receipt.get("prefix_sha256") == digest and receipt.get("confirmed") is True
                and isinstance(receipt.get("created_epoch"), (int, float))
                and 0 <= self.clock()-receipt["created_epoch"] < 23*3600)

    def record_cache(self, research, client):
        for row in client.observations():
            if runner.cache_write_confirmed(row):
                digest = hashlib.sha256(research.prefix("shared").encode()).hexdigest()
                save(self.root / "cache" / (digest + ".json"), {
                    "schema_version": 1, "prefix_sha256": digest, "confirmed": True,
                    "request_id": row["id"], "known_cost_usd": row["cost"],
                    "created_epoch": row["created"], "observed_at": stamp(row["updated"]),
                    "receipt_sha256": hashlib.sha256(row["response"].encode()).hexdigest()})

    def paper_sync(self, ledger):
        if self.clock()-self._last_market < 60:
            return
        self._last_market = self.clock()
        self.progress_at, self.stage = self.clock(), "paper_reconciliation"
        market = self.market_factory(self.root / "market")
        states = {}
        self._paper_issue = False
        if self.start <= self.clock() < self.end and timestamp(stamp(self.clock())).astimezone(NEW_YORK).weekday() < 5:
            try:
                data = self.daily_evidence()
                u = data["universe"]
                ledger.register_universe(UniverseSnapshot(u["id"], u["effective_at"], u["captured_at"],
                    tuple(c["symbol"] for c in u["companies"]), u["source"], u["expires_at"]))
                self.progress_at, self.stage = self.clock(), "paper_reconciliation"
            except (ValueError, KeyError, OSError, TimeoutError):
                self._paper_issue = True
                states["membership"] = {"status": "data_unavailable"}
                save(self.root / "paper-health.json", {"schema_version": 1, "updated_at": stamp(self.clock()), **states})
                return
        baseline = None
        for label, action in (("fill", market.fill_pending), ("mark", market.mark_close)):
            # Fill a precommitted opening first. Recording a cash baseline at
            # receipt time before it would be intervening accounting and could
            # legitimately block retroactive modeled opening execution.
            if label == "mark" and hasattr(market, "establish_baseline"):
                try:
                    baseline = market.establish_baseline(ledger, now=stamp(self.clock()))["status"]
                    states["baseline"] = {"status": baseline}
                except (ValueError, OSError, TimeoutError):
                    baseline = "unavailable"
                    states["baseline"] = {"status": "data_unavailable"}
                    self._paper_issue = True
            if label == "mark" and baseline in ("unavailable", "waiting_for_pending_fill") and not ledger.public_state()["history"]:
                # A missing benchmark opening must not quietly move an all-cash
                # start to the close and erase that day's index opportunity.
                states[label] = {"status": "waiting_for_baseline"}
                self._paper_issue = True
                continue
            try:
                states[label] = {"status": action(ledger, now=stamp(self.clock()))["status"]}
            except (ValueError, OSError, TimeoutError):
                states[label] = {"status": "data_unavailable"}
                self._paper_issue = True
        save(self.root / "paper-health.json", {"schema_version": 1,
             "updated_at": stamp(self.clock()), **states})
        self.progress_at, self.stage = self.clock(), "scheduling"

    def checkpoint(self, config, ledger, research, client, projection):
        self.progress_at, self.stage = self.clock(), "researching"
        self.paper_sync(ledger)
        self.outcomes.observe(ledger, observed_at=stamp(self.clock()))
        self.bind_outcome_context(config, ledger)
        research.investment_outcomes = self.outcomes.context(cutoff=stamp(self.clock()), limit=6)
        self.record_cache(research, client)
        self.lab.reconcile(research, client)
        self._last_evaluation = self.lab.evaluate()
        self.reconcile_parked()
        save(self.root / "policy-evaluation.json", self._last_evaluation)
        admission = self.admission()
        if self._paper_issue or not self.storage_available():
            self.status, self.reason = "needs_attention", "data_unavailable"
        elif not admission["allow_new_research"]:
            self.status, self.reason = "waiting", self._admission_reason(admission)
        else:
            self.status, self.reason = "running", None
        self.next_wake = min(self.end, self.clock()+60)
        totals = self.totals()
        projection["portfolio"] = ledger.public_state()
        research.portfolio_context = projection["portfolio"]
        projection["service"] = self.public_service()
        projection["sail"]["known_cost_usd"] = totals["known_cost_usd"]
        projection["sail"]["unsettled_requests"] = totals["unsettled_requests"]
        activity = projection["sail"].get("activity")
        if activity:
            activity.update(completed_requests=totals["completed"], total_requests=totals["requests"],
                            reserved_cost_usd=format(Decimal(totals["committed_usd"])-Decimal(totals["known_cost_usd"]), "f"))
        save(self.root / "public.json", projection)
        self.health()
        return projection

    def reconcile_parked(self):
        """Bounded recovery of old exact identities without giving them trades.

        Provider outages/ambiguous usage retain conservative holds and visible
        issues while independent research may use the remaining allocation.
        No new task or request identity is minted by this path.
        """
        if self.clock()-self._last_recovery < 60:
            return
        self._last_recovery = self.clock()
        with self.connect() as db:
            rows = db.execute("SELECT id,config FROM epochs WHERE status='parked_unsettled' ORDER BY created").fetchall()
        candidates = []
        for row in rows:
            config = json.loads(row["config"])
            path = Path(config["state_dir"])/"requests.sqlite"
            with sqlite3.connect("file:"+str(path)+"?mode=ro", uri=True, factory=ClosingConnection) as db:
                for request in db.execute("SELECT id,status,response_id,attempts,created,updated FROM requests"):
                    identity, status, response_id, attempts, created, updated = request
                    if status in TERMINAL:
                        continue
                    if not response_id and attempts > 0 and (attempts >= 10 or self.clock()-created > 23*3600):
                        continue
                    candidates.append((updated, identity, row["id"], config))
        # Old permanently unavailable IDs cannot starve newer epochs: select
        # the globally least recently observed identities across all journals.
        selected = sorted(candidates, key=lambda x: (x[0], x[1]))[:4]
        groups = {}
        for _, identity, epoch_id, config in selected:
            groups.setdefault(epoch_id, (config, []))[1].append(identity)
        for epoch_id, (config, identities) in groups.items():
            validated, evidence = runner.read_config(Path(config["state_dir"])/"config.json")
            client = Client(Path(config["state_dir"])/"requests.sqlite", validated)
            from .research import Research
            research = Research(Path(config["state_dir"])/"research.sqlite", evidence)
            for identity in identities:
                client.step(identity)
            research.reconcile(client.iter_rows())
            self.lab.reconcile(research, client)
            from .journal import publish_journal
            publish_journal(validated, research, client)
            runner.report(validated, client, research)
            totals = request_totals(Path(config["state_dir"])/"requests.sqlite")
            status = "parked_unsettled" if totals["pending_requests"] else "drained_unsettled" if totals["unsettled_requests"] else "complete"
            with self.connect() as db:
                db.execute("UPDATE epochs SET known=?,committed=?,status=? WHERE id=?",
                           (totals["known_cost_usd"], totals["committed_usd"], status, epoch_id))
            if status == "complete":
                self.record_value(epoch_id, config)

    @staticmethod
    def _admission_reason(doc):
        if doc.get("stop_requested"):
            return "manual_pause"
        reason = doc.get("reason_code")
        return reason if reason in ("funding_needed", "scheduled_wait", "manual_pause") else "recovering"

    def _refresh(self, directory, previous):
        result = capture(directory)
        if result["failures"] or result["captured"] != result["companies"]:
            raise ValueError("Incomplete daily source refresh")
        return assemble(directory)

    def daily_evidence(self):
        day = timestamp(stamp(self.clock())).astimezone(NEW_YORK).date().isoformat()
        directory = self.root / "evidence" / day
        assembled = directory / "evidence.json"
        if assembled.exists():
            result = json.loads(assembled.read_text())
        else:
            if not self.storage_available():
                raise ValueError("Source refresh paused for disk headroom")
            previous = json.loads(Path(self.config["initial_evidence_path"]).read_text())
            self.status, self.reason = "waiting", "scheduled_wait"
            self.progress_at, self.stage = self.clock(), "refreshing_sources"
            self.health()
            result = self.refresher(directory, previous)
            self.progress_at, self.stage = self.clock(), "scheduling"
            if timestamp(result["universe"]["captured_at"]).astimezone(NEW_YORK).date().isoformat() != day:
                raise ValueError("Daily refresh did not produce today's membership capture")
            if {c["symbol"] for c in result["companies"]} != {c["symbol"] for c in result["universe"]["companies"]}:
                raise ValueError("Daily refresh must preserve full constituent coverage")
            save(assembled, result)
        if not timestamp(result["universe"]["captured_at"]).timestamp() <= self.clock() < timestamp(result["universe"]["expires_at"]).timestamp():
            raise ValueError("Daily sources are stale or from the future")
        return result

    def _enrich_prices(self, evidence):
        """Freeze actual research prices before admission, never future fills.

        A small rotating set and existing holdings are refreshed each epoch.
        Other companies retain missing prices; agents must explicitly abstain
        when valuation evidence is inadequate.
        """
        market = self.market_factory(self.root / "market")
        if not hasattr(market, "snapshot_price"):
            return evidence
        with PortfolioLedger(self.root / "paper.sqlite") as ledger:
            state = ledger.public_state()
        symbols = {h["symbol"] for h in state["holdings"]}
        for decision in state["pending_decisions"]:
            symbols.update(t["symbol"] for t in decision["targets"])
        ordered = sorted((c["symbol"] for c in evidence["companies"]), key=lambda s: hashlib.sha256(s.encode()).hexdigest())
        offset = int((self.clock()-self.start)//self.config["session_seconds"])*32 % len(ordered)
        symbols = set(sorted(symbols)[:32]) | set((ordered+ordered)[offset:offset+32])
        companies = {c["symbol"]: c for c in evidence["companies"]}
        # Old quotes keep their actual capture/as-of. They are never restamped.
        self.progress_at, self.stage = self.clock(), "refreshing_prices"
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(market.snapshot_price, symbol): symbol for symbol in sorted(symbols) if symbol in companies}
            for future in as_completed(futures):
                try:
                    companies[futures[future]]["research_price"] = future.result()
                except (ValueError, OSError, TimeoutError):
                    pass
                self.progress_at = self.clock()
        # The common overview remains frozen for the entire source day. Fresh
        # focal-company quotes live in the task suffix, so a measured cache
        # write can be reused across epochs without pretending evidence is new.
        return evidence

    def allowance(self):
        total = Decimal(self.config["weekly_inference_budget_usd"])
        elapsed = Decimal(str(weekday_seconds(self.start, min(self.clock(), self.end))))
        duration = Decimal(str(weekday_seconds(self.start, self.end)))
        if duration <= 0:
            return Decimal(0)
        if self.config.get("adaptive_spending"):
            # A larger emergency ceiling or account top-up cannot increase the
            # authorized research rate. The base exploration rate sets pacing.
            total = min(total, Decimal(self.config["session_inference_budget_usd"])*duration/Decimal(self.config["session_seconds"]))
        # A small initial allowance then linear weekday pacing; unused money
        # rolls forward, never unlocks the entire week on Monday morning.
        paced = total * min(Decimal(1), Decimal("0.05")+Decimal("0.95")*elapsed/duration)
        local = timestamp(stamp(self.clock())).astimezone(NEW_YORK)
        tomorrow = datetime.combine(local.date()+timedelta(days=1), daytime(), NEW_YORK).timestamp()
        daily = total * Decimal(str(weekday_seconds(self.start, min(tomorrow, self.end))))/duration
        return max(Decimal(0), min(total, paced, daily)-Decimal(self.totals()["reserved_usd"]))

    def prepare_epoch(self):
        now = int(self.clock())
        local = timestamp(stamp(now)).astimezone(NEW_YORK)
        midnight = datetime.combine(local.date(), daytime(), NEW_YORK).timestamp()
        slot = int((now-midnight)//self.config["session_seconds"])
        identity = local.date().isoformat()+"-"+str(slot).zfill(2)
        with self.connect() as db:
            old = db.execute("SELECT config FROM epochs WHERE id=?", (identity,)).fetchone()
        if old:
            return None  # Never relaunch fresh work in an already used time slot.
        evidence = self.daily_evidence()
        self.funding_plan = self.choose_funding(evidence)
        if self.funding_plan["mode"] == "maintenance":
            with self.connect() as db:
                last = db.execute("SELECT max(created) FROM epochs").fetchone()[0]
            if last is not None and now-last < self.funding_plan["minimum_interval_seconds"]:
                return None
        allowance = min(Decimal(self.funding_plan["epoch_cap_usd"]), self.allowance())
        additional = self.admission().get("max_additional_inference_usd")
        if additional is not None:
            try:
                limit = Decimal(str(additional))
                if not limit.is_finite() or limit < 0:
                    return None
                allowance = min(allowance, limit)
            except (ValueError, ArithmeticError):
                return None
        if allowance < Decimal("0.10"):
            return None
        evidence = self._enrich_prices(evidence)
        now = int(self.clock())
        end = min(int(midnight+(slot+1)*self.config["session_seconds"]), int(self.end),
                  int(datetime.combine(local.date()+timedelta(days=1), daytime(), NEW_YORK).timestamp()))
        if end-now < 360 or not self.admission_allowed():
            return None
        directory = self.root / "epochs" / identity
        evidence_path = directory / "evidence.json"
        save(evidence_path, evidence)
        config = {"schema_version": 1, "run_id": self.config["service_id"]+"-"+identity,
                  "state_dir": str(directory), "paper_path": str(self.root / "paper.sqlite"),
                  "evidence_path": str(evidence_path),
                  "evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
                  "started_epoch": now, "ends_epoch": end,
                  "inference_budget_usd": format(allowance.quantize(Decimal("0.00000001")), "f"),
                  "account_created_at": self.config["account_created_at"],
                  "key_fingerprint": self.config["key_fingerprint"],
                  "injected_auth": self.config.get("injected_auth", False),
                  "drain_seconds": 300, "fetch_filings": self.config.get("fetch_filings", True),
                  "max_concurrency": self.config.get("max_concurrency", 8),
                  "wave_size": self.config.get("wave_size", 12),
                  "wave_seconds": self.config.get("wave_seconds", 600),
                  "min_wave_seconds": 300, "research_policy": self.lab.policy(),
                  "funding_plan": self.funding_plan}
        for key in ("publish_url", "publish_token_path", "voyage_id", "voyage_headers"):
            if self.config.get(key):
                config[key] = self.config[key]
        # Service DB is the authoritative transaction. Regenerate config.json
        # from these exact bytes after a crash between reservation and save.
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO epochs(id,config,reserved,created) VALUES(?,?,?,?)",
                       (identity, canonical(config), config["inference_budget_usd"], self.clock()))
            for outcome_id in self.funding_plan.get("new_outcome_ids", []):
                db.execute("INSERT OR IGNORE INTO consumed_outcomes VALUES(?,?)", (outcome_id, identity))
        save(directory / "config.json", config)
        return identity, config

    def _idle_projection(self, *, reconcile=True):
        with (self.root / "paper-writer.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with PortfolioLedger(self.root / "paper.sqlite", created_at=self.config["account_created_at"]) as ledger:
                if reconcile:
                    self.paper_sync(ledger)
                    self.outcomes.observe(ledger, observed_at=stamp(self.clock()))
                portfolio = ledger.public_state()
        if (self._paper_issue or not self.storage_available()) and self.status not in ("complete", "paused"):
            self.status, self.reason = "needs_attention", "data_unavailable"
        previous = self.root / "public.json"
        projection = json.loads(previous.read_text()) if previous.exists() else {
            "schema_version": 1, "research": {"status": "paused", "updated_at": stamp(self.clock()),
             "question": "Researching an S&P 500 portfolio.", "next": "Continue from the latest evidence and investment questions."},
            "latest_decision": None, "sail": {"status": "not_started", "started_at": None,
             "ends_at": None, "known_cost_usd": "0", "unsettled_requests": 0}}
        projection.update(published_at=stamp(self.clock()), portfolio=portfolio, service=self.public_service())
        projection["research"]["status"] = "complete" if self.status == "complete" else "paused"
        totals = self.totals()
        projection["sail"].update(known_cost_usd=totals["known_cost_usd"],
            unsettled_requests=totals["unsettled_requests"],
            status="running" if totals["pending_requests"] else "complete" if self.status == "complete" else "not_started")
        activity = projection["sail"].get("activity")
        if activity:
            activity["tasks"] = []
            activity["heartbeat_at"] = stamp(self.clock())
            activity.update(completed_requests=totals["completed"], total_requests=totals["requests"],
                            reserved_cost_usd=format(Decimal(totals["committed_usd"])-Decimal(totals["known_cost_usd"]), "f"))
        runner.publish(self.config, projection)

    def tick(self):
        """One scheduling turn. Caller holds service.lock; an epoch may block."""
        self.initialize()
        self.progress_at, self.stage = self.clock(), "scheduling"
        self.reconcile_parked()
        now = self.clock()
        with self.connect() as db:
            pending = db.execute("SELECT id,config FROM epochs WHERE status IN ('prepared','running') ORDER BY created LIMIT 1").fetchone()
        # Recover the accepted journal before any later epoch may reserve money.
        chosen = (pending["id"], json.loads(pending["config"])) if pending else None
        doc = self.admission()
        if now >= self.end and not pending:
            totals = self.totals()
            if totals["pending_requests"] and now < self.end+self.config.get("settlement_drain_seconds", 300):
                self.status, self.reason, self.next_wake, self.stage = "needs_attention", "recovering", now+30, "settling"
                self._idle_projection()
                self.health()
                return self.status
            if totals["pending_requests"]:
                self.status, self.reason, self.next_wake, self.stage = "needs_attention", "recovering", None, "settlement_incomplete"
                self.terminal = True
                self._idle_projection()
                if self.trace:
                    self.trace.event("week:terminal", "voyage.failed", {"reason_code": "settlement_incomplete", "pending_requests": totals["pending_requests"]})
                    self.trace.flush()
                self.health()
                return self.status
        if now < self.end and doc.get("stop_requested") and (not pending or request_totals(Path(json.loads(pending["config"])["state_dir"])/"requests.sqlite")["pending_requests"] == 0):
            self.status, self.reason, self.next_wake = "paused", "manual_pause", None
            self._idle_projection()
            self.health()
            return self.status
        if not chosen:
            if now >= self.end:
                self.status, self.reason, self.next_wake = "complete", "week_complete", None
            elif self.stopping or doc.get("stop_requested"):
                self.status, self.reason, self.next_wake = "paused", "manual_pause", None
            elif now < self.start or next_weekday(now) != int(now):
                self.status, self.reason = "waiting", "scheduled_wait"
                self.next_wake = max(self.start, next_weekday(now))
            elif not self.admission_allowed():
                self.status, self.reason, self.next_wake = "waiting", self._admission_reason(doc), now+60
            else:
                try:
                    chosen = self.prepare_epoch()
                except (OSError, ValueError, KeyError):
                    self.status, self.reason, self.next_wake = "needs_attention", "data_unavailable", now+300
                if not chosen and self.status != "needs_attention":
                    self.status, self.reason, self.next_wake = "waiting", "scheduled_wait", now+300
        if chosen:
            identity, config = chosen
            self.current, self.status, self.reason = identity, "running", None
            self.next_wake = min(self.end, now+60)
            save(Path(config["state_dir"]) / "config.json", config)
            # read_config verifies the source hash before request recovery.
            validated, evidence = runner.read_config(Path(config["state_dir"]) / "config.json")
            self.health()
            self.executor(validated, evidence, controller=self)
            totals = request_totals(Path(config["state_dir"]) / "requests.sqlite")
            expired = self.clock() >= config["ends_epoch"]
            finished = expired and totals["pending_requests"] == 0
            status = ("complete" if totals["unsettled_requests"] == 0 else "drained_unsettled") if finished else "parked_unsettled" if expired else "running"
            with self.connect() as db:
                db.execute("UPDATE epochs SET known=?,committed=?,status=? WHERE id=?",
                           (totals["known_cost_usd"], totals["committed_usd"], status, identity))
            if status == "complete":
                self.record_value(identity, config)
            if expired:
                self.current = None
            if expired and totals["pending_requests"]:
                self.status, self.reason = "needs_attention", "recovering"
        else:
            self._idle_projection()
        if self.status == "complete" and self.trace:
            self.trace.event("week:terminal", "voyage.completed", {"requests": self.totals()["requests"]})
            self.trace.flush()
        self.health()
        return self.status

    def run(self, *, once=False):
        with self.locked():
            old = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
            for sig in old:
                signal.signal(sig, lambda *_: setattr(self, "stopping", True))
            thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
            thread.start()
            try:
                while not self.stopping:
                    try:
                        self.tick()
                    except Exception:
                        self.status, self.reason, self.next_wake = "needs_attention", "runtime_error", self.clock()+60
                        self.health()
                    if self.stopping or once or self.terminal or self.status in ("complete", "paused"):
                        break
                    self.sleeper(30)
            finally:
                if self.stopping:
                    self.status, self.reason, self.next_wake = "paused", "manual_pause", None
                    self.health()
                    # runner.run has released the paper writer lock by now.
                    # Publish the stopped state without starting fresh market
                    # requests while the supervisor is waiting to sleep the VM.
                    try:
                        self._idle_projection(reconcile=False)
                    except Exception:
                        pass  # Private health/accepted journals remain durable.
                self._thread_stop.set()
                thread.join(timeout=2)
                for sig, handler in old.items():
                    signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "status"))
    parser.add_argument("--config", required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    config = read_config(args.config)
    if args.command == "status":
        path = Path(config["state_dir"]) / "service-health.json"
        print(path.read_text() if path.exists() else "No service heartbeat yet.")
    else:
        Service(config).run(once=args.once)


if __name__ == "__main__":
    main()
