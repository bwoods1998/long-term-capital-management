"""A bounded wall-clock research controller; queue completion is not run completion."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import hashlib
import json
import math
import re
from pathlib import Path
import signal
import time
from urllib.request import Request, build_opener
from urllib.error import HTTPError
from .contracts import UniverseSnapshot, utc_now
from .evidence import save, NoRedirect
from .ledger import PortfolioLedger
from .provider import Client, AdmissionClosed, TERMINAL, canonical
from .research import Research

ROOT = Path(__file__).resolve().parents[1]


def stamp(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_config(path):
    c = json.loads(Path(path).read_text())
    required = {
        "schema_version",
        "run_id",
        "state_dir",
        "evidence_path",
        "evidence_sha256",
        "started_epoch",
        "ends_epoch",
        "inference_budget_usd",
        "key_fingerprint",
        "account_created_at",
    }
    if not isinstance(c, dict) or not required <= set(c) or c["schema_version"] != 1:
        raise ValueError("Incomplete runtime config")
    if any(
        type(c[k]) not in (int, float) or not math.isfinite(c[k])
        for k in ("started_epoch", "ends_epoch")
    ):
        raise ValueError("Invalid research timestamps")
    if not 60 <= c["ends_epoch"] - c["started_epoch"] <= 8 * 3600:
        raise ValueError("Research window outside bounded range")
    amount = Decimal(str(c["inference_budget_usd"]))
    mode = c.get("spending_mode", "capped")
    if mode not in ("capped", "available_credit"):
        raise ValueError("Unknown spending authority")
    if not amount.is_finite() or amount <= 0 or (mode == "capped" and amount > 100):
        raise ValueError("Expected an explicit research allocation")
    from .contracts import timestamp, identifier

    identifier(c["run_id"])
    timestamp(c["account_created_at"])
    for key in ("evidence_sha256", "key_fingerprint"):
        if not isinstance(c[key], str) or not re.fullmatch(r"[0-9a-f]{64}", c[key]):
            raise ValueError("Expected frozen provenance hash")
    for key in ("state_dir", "evidence_path"):
        if (
            not isinstance(c[key], str)
            or not Path(c[key]).is_absolute()
            or Path(c[key]).is_symlink()
        ):
            raise ValueError("Use explicit nonsymlink runtime paths")
    for key, lo, hi, default in [
        ("max_concurrency", 1, 32, 32),
        ("wave_size", 1, 32, 24),
        ("wave_seconds", 120, 3600, 300),
        ("min_wave_seconds", 30, 600, 120),
        ("drain_seconds", 1, 900, 300),
    ]:
        value = c.get(key, default)
        if type(value) is not int or not lo <= value <= hi:
            raise ValueError("Invalid runtime bound: " + key)
    if c.get("drain_seconds", 300) >= c["ends_epoch"] - c["started_epoch"]:
        raise ValueError("Drain exceeds runtime window")
    raw = Path(c["evidence_path"]).read_bytes()
    if len(raw) > 8000000 or hashlib.sha256(raw).hexdigest() != c["evidence_sha256"]:
        raise ValueError("Frozen evidence changed")
    if c.get("publish_url") not in (None, "https://blakewoods.us/api/portfolio/state"):
        raise ValueError("Unexpected publication destination")
    return c, json.loads(raw)


def public_activity(research, totals, now, *, running=True):
    """Bounded, template-only activity; never expose prompts or model responses."""
    kinds = {
        "company",
        "cache_control",
        "fresh_review",
        "window_pair",
        "cache_write",
        "allocation",
        "portfolio_critic",
        "memory_review",
    }
    profiles = {"pro_flex", "pro_asap", "kimi_flex", "kimi_asap", "kimi_balanced", "glm_flex", "k3"}
    tasks = []
    if running:
        with research.connect() as db:
            rows = db.execute(
                "SELECT symbol,kind,profile,status FROM tasks WHERE status IN ('running','waiting') ORDER BY CASE status WHEN 'running' THEN 0 ELSE 1 END,created DESC LIMIT 12"
            )
            for row in rows:
                if row["kind"] not in kinds or row["profile"] not in profiles:
                    continue
                symbol = row["symbol"]
                if symbol is not None and symbol not in research.companies:
                    continue
                tasks.append(
                    {
                        "symbol": symbol,
                        "kind": row["kind"],
                        "profile": row["profile"],
                        "status": "running" if row["status"] == "running" else "queued",
                    }
                )
                if len(tasks) == 3:
                    break
    return {
        "heartbeat_at": now,
        "completed_requests": totals["completed"],
        "total_requests": totals["requests"],
        "companies_researched": research.summary()["companies_researched"],
        "universe_size": len(research.companies),
        "reserved_cost_usd": format(
            Decimal(totals["committed_usd"]) - Decimal(totals["known_cost_usd"]), "f"
        ),
        "tasks": tasks,
    }


def public_projection(config, ledger, research, client, *, status="running"):
    totals = client.totals()
    summary = research.summary()
    count = summary["companies_researched"]
    now = utc_now()
    p = ledger.public_state()
    latest = None
    with research.connect() as db:
        saved = db.execute(
            "SELECT at,result,status FROM decisions WHERE status IN ('pending','hold_cash','unchanged') ORDER BY at DESC,rowid DESC LIMIT 1"
        ).fetchone()
    if saved:
        decision = json.loads(saved["result"])
        targets = decision.get("targets", [])
        symbols = ", ".join(
            t["symbol"]
            for t in sorted(targets, key=lambda x: Decimal(x["weight"]), reverse=True)[
                :4
            ]
        )
        latest = {
            "at": saved["at"],
            "action": "rebalance" if targets else "hold",
            "summary": f"Selected {len(targets)} stocks. Largest target positions: {symbols}."
            if targets
            else "Keep the paper portfolio in cash while researching stronger evidence.",
            "sources": [],
        }
        cited = list(
            dict.fromkeys(
                [t["symbol"] for t in targets]
                + [c["symbol"] for c in decision.get("claims", [])]
            )
        )[:4]
        for symbol in cited:
            company = research.companies[symbol]
            latest["sources"].append(
                {
                    "title": symbol + " SEC filings",
                    "url": f"https://www.sec.gov/Archives/edgar/data/{int(company['cik'])}/",
                }
            )
    return {
        "schema_version": 1,
        "published_at": now,
        "portfolio": p,
        "research": {
            "status": status
            if status in ("running", "complete", "paused", "needs_attention")
            else "not_started",
            "updated_at": now,
            "question": f"{count} of {len(research.companies)} stocks researched. Which businesses justify a place in the portfolio?",
            "next": (
                "Review the completed research and pending allocation."
                if status == "complete"
                else "Challenge the latest thesis; investigate the evidence most likely to change the allocation."
            ),
        },
        "latest_decision": latest,
        "sail": {
            "status": status
            if status in ("running", "complete")
            else "needs_attention",
            "started_at": stamp(config["started_epoch"]),
            "ends_at": stamp(config["ends_epoch"]),
            "known_cost_usd": totals["known_cost_usd"],
            "unsettled_requests": totals["unsettled_requests"],
            "activity": public_activity(
                research, totals, now, running=status == "running"
            ),
        },
    }


def publish(config, projection):
    path = Path(config["state_dir"]) / "public.json"
    save(path, projection)
    if not config.get("publish_url"):
        return False
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Blake Woods Portfolio Agent",
    }
    if not config.get("injected_auth"):
        token_path = Path(config.get("publish_token_path", ""))
        if not token_path.is_file() or token_path.stat().st_mode & 0o077:
            raise ValueError("Private publication credential unavailable")
        headers["Authorization"] = "Bearer " + token_path.read_text().strip()
    health = Path(config["state_dir"]) / "publication-health.json"
    for attempt in range(2):
        request = Request(
            config["publish_url"],
            data=canonical(projection).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with build_opener(NoRedirect).open(request, timeout=20) as response:
                success = response.status == 200
            save(health, {"at": utc_now(), "published": success})
            return success
        except HTTPError as error:
            code = error.code
            error.close()
            if code == 409 and attempt == 0:
                # A final state may differ from a checkpoint in the same UTC second. Wait
                # for actual time to move forward; never mint a future publication timestamp.
                time.sleep(1 - (time.time() % 1) + 0.02)
                projection = {**projection, "published_at": utc_now()}
                save(path, projection)
                continue
            save(
                health,
                {"at": utc_now(), "published": False, "error": "http_" + str(code)},
            )
            return False
        except Exception:
            save(
                health,
                {"at": utc_now(), "published": False, "error": "transport_unconfirmed"},
            )
            return False
    return False


def initialize(config, evidence):
    path = Path(config["state_dir"])
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    client = Client(path / "requests.sqlite", config)
    research = Research(path / "research.sqlite", evidence)
    ledger = PortfolioLedger(
        Path(config.get("paper_path", path / "paper.sqlite")), created_at=config["account_created_at"]
    )
    u = evidence["universe"]
    ledger.register_universe(
        UniverseSnapshot(
            u["id"],
            u["effective_at"],
            u["captured_at"],
            tuple(c["symbol"] for c in u["companies"]),
            u["source"],
            u["expires_at"],
        )
    )
    return client, research, ledger


def propose_checked(config, research, ledger):
    """A checked critic approves the exact proposal; durable intent spans both DBs."""
    from .market import next_session
    from .contracts import timestamp

    # Once a precommitted opening arrives, later research must not cancel that
    # order after observing its execution-time information. Resolve its actual
    # paper fill (or an explicit operational cancellation) first.
    pending_ids = {p["id"] for p in ledger.public_state()["pending_decisions"]}
    if any(event["payload"].get("expected_open_at")
           and timestamp(event["payload"]["expected_open_at"]) <= timestamp(utc_now())
           for event in ledger.events() if event["kind"] == "decision" and event["id"] in pending_ids):
        return

    with research.connect() as db:
        rows = db.execute(
            """SELECT * FROM tasks WHERE kind='allocation' AND status='complete'
AND wave > coalesce((SELECT max(prior.wave) FROM decisions decision
JOIN tasks prior ON prior.id=decision.task_id
WHERE decision.status IN ('pending','hold_cash','unchanged')),-1)
ORDER BY wave DESC LIMIT 3"""
        ).fetchall()
    for row in rows:
        with research.connect() as db:
            if db.execute(
                "SELECT 1 FROM decisions WHERE id=?", (row["id"],)
            ).fetchone():
                continue
            grade = json.loads(row["grade"])
            result = json.loads(row["result"])
            if not grade["source_check_passed"]:
                continue
            critic = db.execute(
                "SELECT result,grade FROM tasks WHERE wave=? AND kind='portfolio_critic' AND status='complete'",
                (row["wave"],),
            ).fetchone()
            if not critic or not json.loads(critic["grade"])["source_check_passed"]:
                continue
            reviewed = json.loads(critic["result"])
            proposal = hashlib.sha256(row["result"].encode()).hexdigest()
            if reviewed.get("proposal_sha256") != proposal:
                continue
            if reviewed.get("review_verdict") != "approve":
                db.execute(
                    "INSERT INTO decisions VALUES(?,?,?,?,?)",
                    (
                        row["id"],
                        utc_now(),
                        row["id"],
                        canonical(result),
                        "revision_requested",
                    ),
                )
                continue
            existing = db.execute(
                "SELECT payload FROM decision_intents WHERE id=?", (row["id"],)
            ).fetchone()
        if existing:
            intent = json.loads(existing[0])
        else:
            targets = {t["symbol"]: t["weight"] for t in result["targets"]}
            at = utc_now()
            pending = ledger.public_state()["pending_decisions"]
            prior = pending[-1] if pending else None
            if prior and {
                t["symbol"]: Decimal(t["weight"]) for t in prior["targets"]
            } == {symbol: Decimal(weight) for symbol, weight in targets.items()}:
                with research.connect() as db:
                    db.execute(
                        "INSERT INTO decisions VALUES(?,?,?,?,?)",
                        (row["id"], at, row["id"], canonical(result), "unchanged"),
                    )
                return
            session = next_session(at)
            refs = sorted(
                {
                    "sec-"
                    + c["symbol"]
                    + "-"
                    + research.companies[c["symbol"]]["sha256"][:16]
                    for c in result["claims"]
                }
            )
            intent = {
                "decided_at": at,
                "targets": targets,
                "universe_id": research.evidence["universe"]["id"],
                "evidence_refs": refs,
                "rationale": result["thesis"],
                "supersedes": prior["id"] if prior else None,
                "expected_open_at": session.opens_at,
                "calendar_source": session.source,
            }
            with research.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "INSERT OR IGNORE INTO decision_intents VALUES(?,?)",
                    (row["id"], canonical(intent)),
                )
                intent = json.loads(
                    db.execute(
                        "SELECT payload FROM decision_intents WHERE id=?", (row["id"],)
                    ).fetchone()[0]
                )
        try:
            # Task IDs restart at wave zero in a fresh immutable epoch. The
            # shared portfolio uses the run identity as its global namespace.
            decision_id = (config["run_id"] + ":" + row["id"]
                           if config.get("paper_path") else row["id"])
            ledger.propose(decision_id, **intent)
        except ValueError:
            research.event(
                "allocation_rejected",
                {"task": row["id"], "reason": "paper_mandate_validation"},
            )
            continue
        with research.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO decisions VALUES(?,?,?,?,?)",
                (
                    row["id"],
                    intent["decided_at"],
                    row["id"],
                    canonical(result),
                    "pending" if intent["targets"] else "hold_cash",
                ),
            )
        break


def _counter(value):
    return value if type(value) is int and value >= 0 else None


def cache_write_confirmed(row):
    if (
        row["task_id"] != "cache-write-v1"
        or row["status"] not in ("completed", "incomplete")
        or row["cost"] is None
        or row.get("error")
    ):
        return False
    try:
        response = json.loads(row["response"])
        metadata = response.get("metadata")
        return (
            isinstance(metadata, dict)
            and isinstance(metadata.get("supercache_write_input_tokens"), str)
            and bool(
                re.fullmatch(r"[0-9]{1,16}", metadata["supercache_write_input_tokens"])
            )
            and int(metadata["supercache_write_input_tokens"]) >= 1025
        )
    except (ValueError, TypeError, KeyError):
        return False


def report(config, client, research):
    rows = client.observations() if hasattr(client, "observations") else client.rows()
    groups = {}
    for row in rows:
        response = json.loads(row["response"]) if row["response"] else {}
        usage = response.get("usage") if isinstance(response, dict) else None
        meta = response.get("metadata") if isinstance(response, dict) else None
        usage = usage if isinstance(usage, dict) else {}
        meta = meta if isinstance(meta, dict) else {}
        group = groups.setdefault(
            row["profile"],
            {
                "requests": 0,
                "completed": 0,
                "known_cost_usd": Decimal(0),
                "unsettled": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_tokens": 0,
                "supercached_tokens": 0,
                "usage_unavailable": 0,
                "latencies_seconds": [],
            },
        )
        group["requests"] += 1
        group["completed"] += row["status"] == "completed"
        group["unsettled"] += row["cost"] is None
        if row["cost"] is not None:
            group["known_cost_usd"] += Decimal(row["cost"])
        details = usage.get("input_tokens_details")
        details = details if isinstance(details, dict) else {}
        counters = {
            key: _counter(usage.get(key)) for key in ("input_tokens", "output_tokens")
        }
        counters["cached_tokens"] = _counter(details.get("cached_tokens"))
        sc = meta.get("supercached_input_tokens")
        counters["supercached_tokens"] = (
            int(sc)
            if isinstance(sc, str) and re.fullmatch(r"[0-9]{1,16}", sc)
            else None
        )
        group["usage_unavailable"] += any(v is None for v in counters.values())
        for key, value in counters.items():
            if value is not None:
                group[key] += value
        if row["status"] in TERMINAL:
            group["latencies_seconds"].append(round(row["updated"] - row["created"], 2))
    for group in groups.values():
        group["known_cost_usd"] = format(group["known_cost_usd"], "f")
        values = sorted(group.pop("latencies_seconds"))
        group["median_completion_seconds"] = (
            values[len(values) // 2] if values else None
        )
        group["p95_completion_seconds"] = (
            values[min(len(values) - 1, int(len(values) * 0.95))] if values else None
        )
    result = {
        "schema_version": 1,
        "run_id": config["run_id"],
        "as_of": utc_now(),
        "starts_at": stamp(config["started_epoch"]),
        "ends_at": stamp(config["ends_epoch"]),
        "elapsed_seconds": max(0, round(time.time() - config["started_epoch"])),
        "budget_usd": config["inference_budget_usd"],
        "cost": client.totals(),
        "research": research.summary(),
        "profiles": groups,
        "limitations": [
            "Source checks test extracted claims, not investment merit.",
            "Completion latency includes local queueing and polling; partial/missing usage is retained.",
            "No five-hour experiment can establish durable investment outperformance.",
            "No live brokerage execution.",
        ],
    }
    from .evaluation import evaluate

    result["evaluation"] = (
        evaluate(client.path, research.path)
        if hasattr(client, "path")
        else {"available": False}
    )
    save(Path(config["state_dir"]) / "report.json", result)
    return result


def run(config, evidence, *, once=False, branch=False, controller=None):
    if config.get("research_only") and not branch:
        raise ValueError("Research fork cannot start portfolio authority")
    state = Path(config["state_dir"])
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (state / "runner.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    paper_lock = None
    if config.get("paper_path") and not branch:
        paper_lock = (Path(config["paper_path"]).parent / "paper-writer.lock").open("a")
        try:
            fcntl.flock(paper_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            paper_lock.close()
            lock.close()
            raise
    if branch:
        try:
            if config.get("research_only") is not True or config.get("publish_url"):
                raise ValueError("Branch authority invalid")
            return run_branch(config, evidence)
        finally:
            lock.close()
    try:
        client, research, ledger = initialize(config, evidence)
    except BaseException:
        if paper_lock:
            paper_lock.close()
        lock.close()
        raise
    if controller:
        try:
            controller.initialize_epoch(config, research, client)
        except BaseException:
            ledger.close()
            if paper_lock:
                paper_lock.close()
            lock.close()
            raise
    stopping = [False]
    trace = controller.trace if controller else None
    if config.get("voyage_id") and not controller:
        from .telemetry import Voyage

        trace = Voyage(state / "voyage.sqlite", config)
    if trace:
        client.transport.headers.update(trace.headers())

    def stop(*_):
        stopping[0] = True
        if controller:
            controller.request_stop()

    previous_handlers = {
        sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)
    }
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    filings = None
    if config.get("fetch_filings", True):
        from .filings import Filings

        filings = Filings(state / "filings")
    futures = {}
    last_publish = 0
    last_plan_attempt = 0
    pool = ThreadPoolExecutor(max_workers=config.get("max_concurrency", 32))
    try:
        # Recover crash gaps once from exact durable bodies. Completed futures
        # reconcile individually below; polling never reloads historical prompts.
        research.reconcile(client.iter_rows())
        while not stopping[0] and not (controller and controller.should_stop()):
            at = time.time()
            elapsed = at - config["started_epoch"]
            remaining = config["ends_epoch"] - at
            if elapsed < 0:
                time.sleep(min(10, -elapsed))
                continue
            for allocation in config.get("branch_allocations", []):
                client.allocate(allocation["id"], allocation["reserved_usd"])
            for identity, future in list(futures.items()):
                if future.done():
                    row = future.result()
                    futures.pop(identity)
                    if row["status"] in TERMINAL:
                        research.complete(row)
            rows = client.observations()
            # Recover all accepted response IDs before planning fresh work after a restart.
            inflight = [r for r in rows if r["status"] not in TERMINAL]
            concurrency = config.get("max_concurrency", 32)
            if config.get("spending_mode") != "available_credit":
                concurrency = min(concurrency, [1, 4, 8, 16, 24, 32][min(5, int(elapsed // 900))])
            if any(
                r.get("error") == "provider_http_429" and at - r["updated"] < 120
                for r in rows
            ):
                concurrency = max(1, concurrency // 2)
            for row in inflight:
                if len(futures) >= concurrency:
                    break
                if row["id"] not in futures and at - row["updated"] >= min(
                    30, 3 * max(1, row["attempts"])
                ):
                    futures[row["id"]] = pool.submit(client.step, row["id"])
            if remaining > config.get("drain_seconds", 300) and (not controller or controller.admission_allowed()):
                waiting = research.waiting()
                with research.connect() as db:
                    wave = db.execute(
                        "SELECT coalesce(max(number),-1)+1 FROM waves"
                    ).fetchone()[0]
                    last = (
                        db.execute("SELECT max(created) FROM waves").fetchone()[0] or 0
                    )
                should_plan = (
                    at - last >= config.get("wave_seconds", 300) and len(waiting) < 64
                ) or (
                    not waiting
                    and not inflight
                    and at - last >= config.get("min_wave_seconds", 120)
                )
                if should_plan and at-last_plan_attempt >= config.get("min_wave_seconds", 120):
                    last_plan_attempt = at
                    cache_ready = any(cache_write_confirmed(r) for r in rows) or bool(
                        controller and controller.cache_ready(research)
                    )
                    planned_count = research.plan_wave(
                        wave,
                        size=config.get("wave_size", 24),
                        cache_ready=cache_ready,
                        filings=filings,
                    )
                    waiting = research.waiting()
                    if planned_count != 0:
                        research.event(
                            "wave_planned",
                            {
                                "wave": wave,
                                "concurrency": concurrency,
                                "elapsed_seconds": int(elapsed),
                            },
                        )
                outstanding = len(inflight)
                for task in waiting:
                    if outstanding >= concurrency:
                        break
                    if controller and not controller.admission_allowed():
                        break
                    try:
                        if controller and task["kind"] == "allocation" and remaining <= 900:
                            # Leave an explicit review interval before final
                            # admission closes; a proposal alone is not a trade.
                            continue
                        identity = client.submit_intent(
                            task["id"],
                            task["profile"],
                            json.loads(task["body"]),
                            cache=task["cache"],
                        )
                    except AdmissionClosed:
                        if controller and task["kind"] in ("allocation", "portfolio_critic"):
                            # Cheap company tasks must not consume each newly
                            # released dollar while a critical review waits for
                            # enough of the paced allowance to accumulate.
                            break
                        continue
                    research.attach(task["id"], identity)
                    if identity not in futures:
                        futures[identity] = pool.submit(client.step, identity)
                        outstanding += 1
            if at - last_publish >= 60 or remaining <= 0 or once:
                # Settled critiques still affect the final paper allocation while
                # admission is closed; this submits no additional inference.
                if controller:
                    controller.paper_sync(ledger)
                propose_checked(config, research, ledger)
                status = (
                    "running"
                    if remaining > 0
                    else "complete"
                    if client.totals()["unsettled_requests"] == 0
                    else "needs_attention"
                )
                projection = public_projection(
                    config, ledger, research, client, status=status
                )
                if controller:
                    projection = controller.checkpoint(config, ledger, research, client, projection)
                from .journal import publish_journal
                publish_journal(config, research, client)
                try:
                    published = publish(config, projection)
                except Exception:
                    published = False
                checkpoint_id = research.event(
                    "checkpoint",
                    {
                        "published": published,
                        "elapsed_seconds": int(elapsed),
                        "concurrency": concurrency,
                    },
                )
                if trace:
                    trace.event(
                        ((config["run_id"] + ":") if controller else "") + "checkpoint-" + str(checkpoint_id),
                        "research.checkpoint",
                        {
                            "companies_researched": research.summary()[
                                "companies_researched"
                            ],
                            "requests": client.totals()["requests"],
                        },
                    )
                    trace.flush()
                report(config, client, research)
                last_publish = at
            if remaining <= 0 or once:
                break
            time.sleep(min(3, max(0.1, remaining)))
    finally:
        try:
            pool.shutdown(wait=True, cancel_futures=True)
            research.reconcile(client.iter_rows())
            if controller:
                controller.paper_sync(ledger)
            propose_checked(config, research, ledger)
            final_status = (
                "paused"
                if stopping[0]
                else "complete"
                if time.time() >= config["ends_epoch"]
                and client.totals()["unsettled_requests"] == 0
                else "needs_attention"
                if time.time() >= config["ends_epoch"]
                else "running"
            )
            try:
                projection = public_projection(config, ledger, research, client, status=final_status)
                if controller:
                    projection = controller.checkpoint(config, ledger, research, client, projection)
                from .journal import publish_journal
                publish_journal(config, research, client)
                publish(config, projection)
            except Exception:
                pass
            report(config, client, research)
            if trace:
                if final_status == "complete":
                    trace.event(
                        config["run_id"] + ":terminal" if controller else "terminal",
                        "research.epoch_completed" if controller else "voyage.completed",
                        {"requests": client.totals()["requests"]},
                    )
                trace.flush()
        finally:
            ledger.close()
            if paper_lock:
                paper_lock.close()
            lock.close()
            for sig, previous in previous_handlers.items():
                signal.signal(sig, previous)

    return report(config, client, research)


def run_branch(config, evidence):
    """Finite isolated fork task; no paper ledger or publication authority."""
    client = Client(Path(config["state_dir"]) / "requests.sqlite", config)
    assigned = config.get("assigned_tasks", [])
    if not assigned or {t["id"] for t in assigned} != set(config["assigned_task_ids"]):
        raise ValueError("Frozen branch task assignment mismatch")
    while time.time() < config["ends_epoch"]:
        for task in assigned:
            try:
                identity = client.submit_intent(
                    task["id"],
                    task["profile"],
                    task["body"],
                    cache=task.get("cache", "ordinary"),
                )
                client.step(identity)
            except AdmissionClosed:
                continue
        rows = client.observations()
        if len(rows) == len(assigned) and all(r["status"] in TERMINAL for r in rows):
            break
        time.sleep(5)
    result = {
        "schema_version": 1,
        "research_only": True,
        "run_id": config["run_id"],
        "cost": client.totals(),
        "tasks": [
            {
                k: r[k]
                for k in (
                    "task_id",
                    "profile",
                    "status",
                    "response",
                    "cost",
                    "created",
                    "updated",
                )
            }
            for r in client.iter_rows()
        ],
    }
    save(Path(config["state_dir"]) / "branch-receipt.json", result)
    return result


def paper(config, evidence, *, market=None):
    """One paper-market synchronization; this path never submits model requests."""
    if config.get("research_only"):
        raise ValueError("Research fork has no paper-account authority")
    from .market import YahooMarketData

    state = Path(config["state_dir"])
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / "runner.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        paper_lock = None
        if config.get("paper_path"):
            paper_lock = (Path(config["paper_path"]).parent / "paper-writer.lock").open("a")
            try:
                fcntl.flock(paper_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BaseException:
                paper_lock.close()
                raise
        client, research, ledger = initialize(config, evidence)
        try:
            market = market or YahooMarketData(state / "market")
            fill = market.fill_pending(ledger)
            mark = market.mark_close(ledger)
            status = (
                "running"
                if config["started_epoch"] <= time.time() < config["ends_epoch"]
                else "complete"
                if time.time() >= config["ends_epoch"]
                else "not_started"
            )
            projection = public_projection(
                config, ledger, research, client, status=status
            )
            published = publish(config, projection)
            return {
                "schema_version": 1,
                "paper_only": True,
                "fill_status": fill["status"],
                "mark_status": mark["status"],
                "published": published,
                "portfolio": ledger.public_state(),
            }
        finally:
            ledger.close()
            if paper_lock:
                paper_lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["prepare", "run", "branch", "status", "paper"]
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    config, evidence = read_config(args.config)
    if args.command == "prepare":
        client, research, ledger = initialize(config, evidence)
        projection = public_projection(
            config, ledger, research, client, status="not_started"
        )
        projection["research"]["status"] = "not_started"
        projection["sail"].update(status="not_started", started_at=None, ends_at=None)
        save(Path(config["state_dir"]) / "public.json", projection)
        ledger.close()
        print("Prepared private paper state. No provider requests made.")
    elif args.command == "paper":
        print(canonical(paper(config, evidence)))
    elif args.command == "status":
        p = Path(config["state_dir"]) / "report.json"
        print(p.read_text() if p.exists() else "No runtime checkpoint yet.")
    else:
        result = run(config, evidence, once=args.once, branch=args.command == "branch")
        print(canonical(result))


if __name__ == "__main__":
    main()
