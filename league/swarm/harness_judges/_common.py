"""Shared plumbing for the fixed judges: arguments, the gate override, the private pool, the seeded generator, and the
one-line answer.

A judge runs a candidate tree twice more than its baseline: with the candidate's canary gate forced OPEN (the change
itself is judged) and forced CLOSED (the old behavior must be exactly the baseline's). `--gate open|closed --key KEY`
sets `league.swarm.canary._FORCED[KEY]` in this sandboxed process before the tree's code runs; nothing else ever sets
it, and the gate honors it only under the sandbox's marker (`LTCM_HARNESS_JUDGE=1`). `--nonce-stdin` reads the loop's
per-run nonce from standard input (never argv, which the tree's code could read); the answer carries it, so a line
printed by the tree's code cannot pass for the judge's. `--pool-stdin` (held-out runs) reads the lane's PRIVATE pool
from the next line of standard input, before the tree's code loads: it is never a file here, never in this public repo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from typing import Any, Callable, Mapping


def args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--split", choices=("dev", "heldout"), required=True)
    p.add_argument("--seed", default="dev")
    p.add_argument("--gate", choices=("none", "open", "closed"), default="none")
    p.add_argument("--key", default="")
    p.add_argument("--nonce-stdin", action="store_true")
    p.add_argument("--pool-stdin", action="store_true")
    opts = p.parse_args(argv)
    opts.nonce = sys.stdin.readline().strip() if opts.nonce_stdin else ""
    opts.pool = None
    if opts.pool_stdin:
        try:
            opts.pool = json.loads(sys.stdin.readline())
        except ValueError:
            raise SystemExit("the held-out pool on standard input is not JSON")
        if not isinstance(opts.pool, dict) or opts.pool.get("schema") != 1:
            raise SystemExit("the held-out pool is not a schema-1 object")
    if opts.split == "heldout" and opts.pool is None:
        raise SystemExit("the held-out split needs its private pool (--pool-stdin)")
    force_gate(opts.gate, opts.key)
    return opts


def force_gate(gate: str, key: str) -> None:
    """Force the candidate's gate open or closed for every unit (the module docstring). A tree without the override
    cannot be judged open: it exits non-zero, which the loop reads as no valid answer."""
    if gate == "none":
        return
    if not key:
        raise SystemExit("--gate needs --key")
    try:
        from league.swarm import canary
    except ImportError:
        if gate == "open":
            raise SystemExit("this tree has no canary gate to open")
        return
    forced = getattr(canary, "_FORCED", None)
    if not isinstance(forced, dict):
        if gate == "open":
            raise SystemExit("this tree's canary gate has no judges' override")
        return
    forced[key] = gate == "open"
    # The override must be honored here (a process without the sandbox's marker ignores it): a gate forced open that
    # still reads closed would judge the old behavior as the change.
    if canary.enabled(key, "judge-probe-unit", root="/nonexistent-judge-root") is not (gate == "open"):
        raise SystemExit("the gate does not honor the judges' override in this process (no LTCM_HARNESS_JUDGE=1)")


def rng(seed: str, salt: str) -> random.Random:
    return random.Random(int(hashlib.sha256(f"{seed}:{salt}".encode()).hexdigest()[:16], 16))


def answer(protocol: str, opts: argparse.Namespace, body: Callable[[], Mapping[str, Any]]) -> None:
    began, cpu = time.monotonic(), time.process_time()
    out = dict(body())
    out.update(protocol=protocol, split=opts.split, seed=opts.seed if opts.split == "heldout" else "dev", provider_calls=0,
               gate=opts.gate, nonce=opts.nonce, seconds=round(time.monotonic() - began, 6),
               cpu_seconds=round(time.process_time() - cpu, 6))
    sys.stdout.write(json.dumps(out, sort_keys=True, allow_nan=False) + "\n")
    sys.stdout.flush()
