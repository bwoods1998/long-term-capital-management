"""Harness canary arms: a harness change gated to a deterministic fraction of units until the loop retains or reverts it.

The persistent improvement loop (`league/swarm/improvement.py`, `playbooks/harness-improvement.md`) ships a candidate
harness change behind a gate, then compares the units the gate routes to the new behavior (the canary arm) with the
units it leaves on the old behavior (the control arm) over the same window. That is a concurrent, randomized comparison:
the day's workload, the model's mood and the market hit both arms alike, which a before/after window cannot promise.

A candidate's code asks one question, with the key the loop gave it and the unit it is about to act on::

    from league.swarm import canary
    if canary.enabled("harness:research:train_dq_rate:0123456789abcdef", family_id, root=store.root):
        ...  # the new behavior
    else:
        ...  # the old behavior, unchanged

The unit is the lane's (`league/swarm/harness_lanes.py`, `Lane.canary["unit"]`): the family id for the research lane,
`mechanism_unit(mechanism)` for the memory lane (a proposal has no final family id yet). Only the arms lanes gate: no
gate may sit in the evaluator fingerprint's files (`league/gym`, `league/live`, the four shared files), whose changes
are planned releases compared before and after, and the staging guard refuses one there.

THE FILE. `<state>/harness/canary.json`, written only by the loop's `canary` command in its own private directory
(never by the swarm, never in `swarm.json`)::

    {"schema": 1, "arms": {"<key>": {"lane": "research", "fraction": 0.25, "salt": "<hex>", "state": "canary"}}}

`state` is `canary` (a unit is in the arm when `in_arm` says so), `retained` (every unit gets the new behavior) or
`reverted` (none does: a revert is a flag flip, effective at the next read, with no deploy). A missing, unreadable or
malformed file, an unknown key, or a fraction outside [0, 1] all mean the OLD behavior: the gate fails closed.

Arm membership is `sha256(salt NUL key NUL unit)` below `fraction` of the hash space, so the same unit stays in the
same arm for the whole window, across restarts and processes, and the observer computes the same split from the data.
The file is re-read at most every `RECHECK_SECONDS` per process (a stat call per check otherwise). Standard library only.

THE JUDGES' OVERRIDE. The loop's fixed judges score a candidate twice, with its gate forced open (every unit gets the new
behavior: the change itself is judged) and forced closed (none does: the old behavior must be exactly the baseline's).
They set `_FORCED[key]` in their own sandboxed process (`harness_judges/_common.force_gate`). Nothing on the House sets
it, and a candidate may never name it (`harness_lanes.content_guard`).
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Mapping

FILE = Path("harness") / "canary.json"
SCHEMA = 1
STATES = ("canary", "retained", "reverted")
RECHECK_SECONDS = 30.0
#: key -> True (open) or False (closed), set only by the fixed judges (the module docstring). Empty in production.
_FORCED: dict[str, bool] = {}
#: The architect keeps a mechanism's first 600 characters, whitespace-normalized (`Architect.admit`).
MECHANISM_CHARS = 600


def in_arm(salt: str, key: str, unit: str, fraction: float) -> bool:
    """Whether `unit` falls in the canary arm of `key` (deterministic; the module docstring)."""
    try:
        fraction = float(fraction)
    except (TypeError, ValueError):
        return False
    if not 0.0 < fraction <= 1.0:
        return False
    digest = hashlib.sha256(f"{salt}\0{key}\0{unit}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") < fraction * 2 ** 64


def mechanism_unit(mechanism: Any) -> str:
    """The unit of a proposal that has no family id yet (the store may still change its slug): its mechanism text,
    whitespace-normalized, cut to the architect's 600 characters, normalized again (the store's own normalization
    drops a space the cut leaves at the end) and lowercased, hashed. So the gate at proposal time (raw or admitted text
    alike) and the observer after the birth compute the same unit."""
    text = " ".join(" ".join(str(mechanism or "").split())[:MECHANISM_CHARS].split())
    return hashlib.sha256(text.lower().encode("utf-8")).hexdigest()[:16]


def decide(arms: Mapping[str, Any], key: str, unit: str) -> bool:
    """The gate's answer from a parsed `arms` mapping: fail closed on anything unexpected."""
    arm = arms.get(key) if isinstance(arms, Mapping) else None
    if not isinstance(arm, Mapping):
        return False
    state = arm.get("state")
    if state == "retained":
        return True
    if state != "canary" or not isinstance(arm.get("salt"), str) or not arm.get("salt"):
        return False
    return in_arm(arm["salt"], key, str(unit), arm.get("fraction"))


def read(path: Path) -> dict[str, Any]:
    """The arms in `path`, or {} (a missing or malformed file is no canary)."""
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(value, dict) or value.get("schema") != SCHEMA or not isinstance(value.get("arms"), dict):
        return {}
    return {str(k): v for k, v in value["arms"].items() if isinstance(v, dict) and v.get("state") in STATES}


class _Cache:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.entries: dict[str, tuple[float, Any, dict[str, Any]]] = {}

    def arms(self, path: Path, clock=time.monotonic) -> dict[str, Any]:
        name = str(path)
        now = clock()
        with self.lock:
            entry = self.entries.get(name)
            if entry is not None and now - entry[0] < RECHECK_SECONDS:
                return entry[2]
        try:
            stat = path.stat()
            mark: Any = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
        except OSError:
            mark = None
        with self.lock:
            entry = self.entries.get(name)
            if entry is not None and entry[1] == mark:
                self.entries[name] = (now, mark, entry[2])
                return entry[2]
        arms = read(path) if mark is not None else {}
        with self.lock:
            self.entries[name] = (now, mark, arms)
        return arms


_CACHE = _Cache()


def enabled(key: str, unit: Any, *, root: str | Path) -> bool:
    """True when `unit` should get the new behavior of the harness change `key` (the module docstring). `root` is the
    swarm's state directory (`SwarmStore.root`). Never raises: any trouble is the old behavior."""
    try:
        forced = _FORCED.get(str(key))
        if forced is not None:
            return bool(forced)
        return decide(_CACHE.arms(Path(root) / FILE), str(key), str(unit))
    except Exception:  # noqa: BLE001 - a gate never breaks the caller
        return False


__all__ = ["FILE", "SCHEMA", "STATES", "MECHANISM_CHARS", "in_arm", "mechanism_unit", "decide", "read", "enabled"]
