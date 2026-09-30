"""Shared plumbing for the fixed judges: arguments, the seeded generator, and the one-line JSON answer."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from typing import Any, Callable, Mapping


def args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--split", choices=("dev", "heldout"), required=True)
    p.add_argument("--seed", default="dev")
    return p.parse_args(argv)


def rng(seed: str, salt: str) -> random.Random:
    return random.Random(int(hashlib.sha256(f"{seed}:{salt}".encode()).hexdigest()[:16], 16))


def answer(protocol: str, split: str, seed: str, body: Callable[[], Mapping[str, Any]]) -> None:
    began, cpu = time.monotonic(), time.process_time()
    out = dict(body())
    out.update(protocol=protocol, split=split, seed=seed if split == "heldout" else "dev", provider_calls=0,
               seconds=round(time.monotonic() - began, 6), cpu_seconds=round(time.process_time() - cpu, 6))
    print(json.dumps(out, sort_keys=True, allow_nan=False))
