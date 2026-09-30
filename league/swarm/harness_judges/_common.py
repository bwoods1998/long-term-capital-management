"""Shared plumbing for the fixed judges: arguments, the gate override, the seeded generator, and the one-line answer.

A judge runs a candidate tree twice more than its baseline: with the candidate's canary gate forced OPEN (the change
itself is judged) and forced CLOSED (the old behavior must be exactly the baseline's). `--gate open|closed --key KEY`
sets `league.swarm.canary._FORCED[KEY]` in this sandboxed process before the tree's code runs; nothing else ever sets
it. `--nonce-stdin` reads the loop's per-run nonce from standard input (never argv, which the tree's code could read);
the answer carries it, so a line printed by the tree's code cannot pass for the judge's.
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
    opts = p.parse_args(argv)
    opts.nonce = sys.stdin.readline().strip() if opts.nonce_stdin else ""
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
