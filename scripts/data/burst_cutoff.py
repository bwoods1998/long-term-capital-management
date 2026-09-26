"""Stop only receipt-bound Completion backfills at the persisted end of the research burst.

This is cleanup of work admitted during the burst, never permission to wake a box or start
another pull. An unknown owner/outcome retains a conservative rolling liability in the same
Sail ledger. The account guard and ordinary paid admissions remain authoritative.
"""
from pathlib import Path
import time
from typing import Any

import boxlib as bl
from league.swarm.lifecycle import BoundedClient, SailBudget, capacity
from league.swarm.store import SwarmStore, dumps
from nightly import BoxHandle


class Cutoff:
    def __init__(self, state: Path, store: SwarmStore, settings: dict, *, api: Any = None, clock=time.time, lease=None):
        self.state, self.store, self.clock = state, store, clock
        self.budget = SailBudget(store, settings, clock=clock)
        self.api = api
        self.lease = lease or bl.RemoteLease

    def save(self, record):
        self.store.put("completion_cutoff", record)

    def account(self, record, *, final=False):
        rate = float(record["rate_usd_hour"])
        amount = max(0., self.clock() - float(record["boundary"])) * rate / 3600
        with self.store.atomic():
            row = self.store._one("SELECT * FROM sail_commitments WHERE key=?", (record["key"],))
            if row is None:
                raise RuntimeError("Completion's cleanup commitment is missing")
            if not final:
                # Record an already running liability, even if it exhausts the cap. This never
                # dispatches anything: new work is then refused by the ordinary shared ledger.
                self.store._exec("UPDATE sail_commitments SET reserved=MAX(reserved,?) WHERE key=? AND state='open'",
                                 (amount + rate*2400/3600, record["key"]))
            delta = max(0., amount - float(row["accounted"]))
            if delta:
                self.store.add_spend("data_box", delta, detail={"budget_key": record["key"], "completion_cleanup": True})
            self.budget.charge(record["key"], amount, final=final)

    def tick(self):
        record = self.store.get("completion_cutoff") or {}
        if record.get("status") == "cleaned":
            return record
        if self.budget.burst() or not record:
            config = bl.read_json(self.state / "completion-config.json")
            receipt = bl.read_json(self.state / "completion-process.json")
            data = bl.read_json(self.state / "data_box.json").get("box_id")
            if (config.get("enabled") is not True or not receipt or receipt.get("box") != data
                    or not receipt.get("resume_args") or not isinstance(receipt.get("process"), dict)
                    or not 0 < float(receipt.get("observed_at", 0)) < min(self.clock()+1, self.budget.boundary())):
                return {"status": "unowned", "reason": "no Completion process receipt"}
            api = self.api or bl.client()
            row = api.get(data)
            rate = float(self.budget.cfg.get("box_rate_usd_hour", .6))
            capacity(row, rate)
            if row.get("status") != "running":
                return {"status": "idle"}
            if BoxHandle(api, data).backfill_receipt() != receipt["process"]:
                return {"status": "unowned", "reason": "Completion process receipt changed"}
            key = "completion-cutoff:" + data + ":" + str(int(self.budget.boundary()))
            with self.store.atomic():
                if self.budget.burst():
                    self.budget.reserve(key, rate*2400/3600, kind="data_box", detail={"box": data, "existing_completion_work": True})
                else:
                    # Recovery can first read the durable pre-boundary receipt after the boundary.
                    # Record the observed existing liability even when no new work is affordable;
                    # there is still no wake, fork, model request or data pull on this path.
                    self.store._exec("INSERT OR IGNORE INTO sail_commitments(key,kind,bucket,reserved,accounted,state,created,updated,detail) "
                                     "VALUES(?,'data_box','research',?,0,'open',?,?,?)",
                                     (key, rate*2400/3600, self.budget.boundary(), self.clock(),
                                      dumps({"box": data, "existing_completion_work": True})))
                record = {**receipt, "key": key, "boundary": self.budget.boundary(), "rate_usd_hour": rate,
                          "status": "tracking", "resume_deferred": "bulk backfill cannot resume after the burst without a funded authorization"}
                self.save(record)
            if self.budget.burst():
                return record
        if not record:
            return {"status": "unowned", "reason": "no pre-boundary Completion ownership receipt; no wake or stop permitted"}
        self.account(record)
        if self.clock() < float(record.get("retry_not_before") or 0):
            return record
        api = self.api or bl.client()
        box = record["box"]
        try:
            state = api.get(box).get("status")
            if state in ("sleeping", "paused", "terminated", "failed", "create_failed"):
                self.account(record, final=True)
                record.update(status="cleaned", finished_at=self.clock(), error=None)
                self.save(record)
                return record
            if state != "running":
                raise RuntimeError("Completion box state is unreadable; no wake permitted")
            # Nothing resumes the box. All cleanup commands have a finite OS/RPC deadline.
            deadline = self.clock() + 300
            bounded = BoundedClient(api, lambda: deadline, clock=self.clock)
            with self.lease(bounded, box) as lease:
                lease.check()
                handle = BoxHandle(bounded, box)
                current = handle.backfill_receipt()
                if current is not None and current != record["process"]:
                    raise RuntimeError("Completion process was replaced; the new owner is untouched")
                if current is not None:
                    handle.stop_backfill(expected=record["process"])
                lease.check()
                if handle.backfill_receipt() is not None:
                    raise RuntimeError("Completion backfill stop is unconfirmed")
                lease.stop.set()
                if lease.worker is not None:
                    lease.worker.join(timeout=65)
                    if lease.worker.is_alive():
                        raise RuntimeError("Completion lease renewal did not stop")
                lease.check()
                lease.preserve_for_sleep = True
                record.update(status="cleanup_pending", lease_token=lease.token, retry_not_before=self.clock()+2400)
                self.save(record)
                api.sleep(box)
                if api.get(box).get("status") not in ("sleeping", "paused", "terminated"):
                    raise RuntimeError("Completion sleep is unconfirmed")
            self.account(record, final=True)
            record.update(status="cleaned", finished_at=self.clock(), error=None)
        except Exception as exc:
            record.update(status="cleanup_pending", error=f"{type(exc).__name__}: {str(exc)[:300]}")
        self.save(record)
        return record
