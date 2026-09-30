"""Fixed scheduler controls for the harness lab; executed from the trusted judge, outside the candidate tree.

Model-turn counts are a compute-cost proxy, not dollar profits. All data is synthetic. This fixture cannot be edited
by an optimizer candidate, and production retention additionally requires subsequent operational observations.
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

PROTOCOL = "scheduler-work-v1"


def benchmark() -> dict:
    from league.swarm.loop import Scheduler
    from league.swarm.store import SwarmStore

    class Clock:
        now = 1_790_000_000.0

        def __call__(self):
            return self.now

    clock = Clock()
    began = time.monotonic()
    cpu_began = time.process_time()
    with tempfile.TemporaryDirectory() as temp:
        store = SwarmStore(Path(temp), clock=clock)
        try:
            store.add_family({"id": "control", "mechanism": "Synthetic scheduling control, never a trading strategy.",
                              "structure": "long_call", "roots": ["SPY"]}, origin="seed")
            scheduler = Scheduler(store, clock=clock, settings={"researcher": {"dormant_cycles": 12}})
            queries = []
            store._db.set_trace_callback(queries.append)
            def take():
                return scheduler.take(idle_seconds=0)

            quality, required, turns = 0, 5, 0
            if take() == "control":
                quality += 1
                turns += 1
                store.set_state("control", dormant_cycles=1)
                scheduler.release("control", {"hold": True, "dormant_cycles": 1})
            # A paid call every five minutes cannot earn credit by doing nothing useful.
            for _ in range(72):
                clock.now += 300
                if take() is not None:
                    turns += 1
                    scheduler.release("control", {"hold": True, "dormant_cycles": 1})
            store.bump("control", trials=1)
            if take() == "control":
                quality += 1
                scheduler.release("control", {"pending_run": True})
            if take() == "control":
                quality += 1
                scheduler.release("control", {"hold": True, "dormant_cycles": 1})
            store.note("control", "A new independently measured result has arrived.")
            if take() == "control":
                quality += 1
                scheduler.release("control", {"hold": True, "dormant_cycles": 1})
            # Restart recovery must preserve the wait, while an explicit result after restart must wake it.
            scheduler = Scheduler(store, clock=clock, settings={})
            if take() is not None:
                turns += 1
                scheduler.release("control", {"hold": True, "dormant_cycles": 1})
            store.bump("control", trials=1)
            if take() == "control":
                quality += 1
            return {"protocol": PROTOCOL, "quality": quality, "required": required,
                    "idle_model_turns": max(0, turns - 1), "sqlite_statements": len(queries),
                    "seconds": round(time.monotonic() - began, 6), "cpu_seconds": round(time.process_time() - cpu_began, 6), "provider_calls": 0,
                    "cost_basis": "Model turns are a synthetic cost proxy; local compute time is measured, not priced."}
        finally:
            store.close()


if __name__ == "__main__":
    print(json.dumps(benchmark(), allow_nan=False))
