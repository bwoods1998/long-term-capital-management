"""The Alpha Lab's evaluator: many candidate strategies over one development tape, in one sealed box.

`LabBox.evaluate(candidates, tape_id, tape, stake=..., limits=...)` answers one replay result per
candidate, in order -- each exactly what `replay.run_replay` returns for it, plus its `id` -- from a
batch run in the lab's own Sailbox (`sandbox.replay_batch`, `replay.run_batch`). The tape goes to
the box once, keyed by the SHA-256 of its canonical JSON (the id `league.experiments.Archive` gives
the same tape), and every later batch over it reuses the copy there. A box that lost it (rebuilt,
or its disk replaced) says so, and the tape is sent again.

The lab box is `scripts/lab_box.py`'s: larger than an agent's box, with no network and no
credential. `league/config.json`'s `lab` block names it (`box_id`); `LabBox.from_config` binds it
into the House's sandbox, which seals it again before its first batch. Without a `box_id` the
sandbox makes a box for the key from the agent image, as it would for an agent.

Only development data enters it: a tape any of whose data falls in, or spans, the sealed holdout
(`deep_replay.HOLDOUT`) is refused (`sandbox.TapeRefused`) before anything is sent. The holdout is
`HoldoutSeal`'s alone, one rationed single replay at a time.

A failure of the box or of Sail raises `sandbox.SandboxError`: an infrastructure failure, never a
candidate's result. Candidates the batch's time budget did not reach come back
`{"ok": False, "error": "not evaluated: batch budget", "id": ...}`, and candidates the box could not
start a process for come back `{"ok": False, "error": "not evaluated: the box could not start its
process (...)", "infrastructure": True, "id": ...}` (`replay.not_evaluated` is true of both); send
them again. Neither is a result against the candidate.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Mapping, Sequence

from .replay import NOT_EVALUATED, not_evaluated
from .sandbox import SandboxError, TapeMissing, TapeRefused, holdout_problem, tape_digest

__all__ = ["LabBox", "NOT_EVALUATED", "not_evaluated", "SandboxError", "TapeMissing", "TapeRefused", "DEFAULT_BOX_KEY"]

DEFAULT_BOX_KEY = "lab"
#: Candidates sent in one batch at most: a batch's spec carries every candidate's code (40 KB at
#: most each), and its answer every candidate's result.
MAX_BATCH = 256
#: Tapes whose digests are remembered (each entry keeps its tape alive, so an id is never reused).
MEMO = 8


class LabBox:
    """The lab's batch evaluator over a sandbox (`SailSandbox` on the floor, `LocalSandbox` in tests)."""

    def __init__(self, sandbox: Any, *, box_key: str = DEFAULT_BOX_KEY, clock: Any = time.time,
                 holdout: tuple[str, str] | None = None, keep_awake: bool = True, max_batch: int = MAX_BATCH,
                 budget_seconds: float | None = None, workers: int | None = None, candidate_seconds: float | None = None):
        self.sandbox = sandbox
        self.box_key = box_key
        self.clock = clock
        self.holdout = holdout
        self.keep_awake = keep_awake
        self.max_batch = max(1, int(max_batch))
        self.budget_seconds = budget_seconds
        self.workers = workers
        self.candidate_seconds = candidate_seconds
        self._lock = threading.Lock()
        self._digests: dict[str, tuple[Any, str]] = {}  # tape id -> (the tape object, its digest)
        #: What the watch reads: batches run, candidates asked and evaluated, seconds in the box,
        #: tape uploads and misses, and the last batch's numbers.
        self.stats: dict[str, Any] = {"batches": 0, "candidates": 0, "evaluated": 0, "seconds": 0.0, "uploads": 0,
                                      "misses": 0, "last": None}

    @classmethod
    def from_config(cls, sandbox: Any, config: Mapping[str, Any], **options: Any) -> "LabBox | None":
        """The lab box `config["lab"]` names, bound into `sandbox`; None when the block says
        `"enabled": false`. (`bind` exists on `SailSandbox`; a `LocalSandbox` needs none.)"""
        lab = dict(config.get("lab") or {})
        if lab.get("enabled") is False:
            return None
        key = str(lab.get("box_key") or DEFAULT_BOX_KEY)
        box_id = lab.get("box_id")
        if box_id and hasattr(sandbox, "bind"):
            sandbox.bind(key, str(box_id))
        return cls(sandbox, box_key=key, **options)

    # ------------------------------------------------------------------ tapes
    def digest(self, tape_id: str, tape: Mapping[str, Any]) -> str:
        """The tape's digest, once it has been checked (`check`): both are done once per tape object
        (a 20 MB tape takes a second to encode)."""
        with self._lock:
            known = self._digests.get(tape_id)
            if known is not None and known[0] is tape:
                return known[1]
        self.check(tape)
        value = tape_digest(tape)
        with self._lock:
            self._digests[tape_id] = (tape, value)
            while len(self._digests) > MEMO:
                self._digests.pop(next(iter(self._digests)))
        return value

    def check(self, tape: Mapping[str, Any]) -> None:
        """Raise `TapeRefused` for a tape a batch may not see (it reaches into the sealed holdout)."""
        problem = holdout_problem(tape, self.holdout)
        if problem:
            raise TapeRefused(f"unsupported input: {problem}")

    # ---------------------------------------------------------------- evaluate
    def evaluate(self, candidates: Sequence[Mapping[str, Any]], tape_id: str, tape: Mapping[str, Any], *, stake: float,
                 limits: Mapping[str, Any], timeout: float = 600) -> list[dict[str, Any]]:
        """One result per candidate (`{"id", "code", "params"}`), in order: what a single replay of it
        returns, plus its `id`. Batches of at most `max_batch`; each is answered within its budget."""
        candidates = [dict(c) for c in candidates]
        if not candidates:
            return []
        digest = self.digest(tape_id, tape)
        out: list[dict[str, Any]] = []
        for start in range(0, len(candidates), self.max_batch):
            out.extend(self._batch(candidates[start:start + self.max_batch], digest, tape, stake=stake, limits=limits,
                                   timeout=timeout))
        return out

    def _batch(self, candidates: list[dict[str, Any]], digest: str, tape: Mapping[str, Any], *, stake: float,
               limits: Mapping[str, Any], timeout: float) -> list[dict[str, Any]]:
        options = {"tape_digest": digest, "stake": stake, "limits": dict(limits), "timeout": timeout,
                   "keep_awake": self.keep_awake, "holdout": self.holdout, "budget_seconds": self.budget_seconds,
                   "workers": self.workers, "candidate_seconds": self.candidate_seconds}
        try:
            run = self.sandbox.replay_batch(self.box_key, candidates, None, **options)
        except TapeMissing:
            with self._lock:
                self.stats["misses"] += 1
            run = self.sandbox.replay_batch(self.box_key, candidates, tape, **options)
        result = run.result
        results = list(result.get("results") or [])
        if [r.get("id") for r in results] != [c.get("id") for c in candidates]:
            raise SandboxError("the lab box answered for other candidates than it was given")
        evaluated = int(result.get("evaluated") or 0)
        with self._lock:
            self.stats["batches"] += 1
            self.stats["candidates"] += len(candidates)
            self.stats["evaluated"] += evaluated
            self.stats["seconds"] = round(self.stats["seconds"] + float(run.seconds), 3)
            self.stats["uploads"] += 1 if result.get("uploaded") else 0
            self.stats["last"] = {"at": self.clock(), "candidates": len(candidates), "evaluated": evaluated,
                                  "seconds": round(float(run.seconds), 3), "box_seconds": result.get("box_seconds"),
                                  "workers": result.get("workers"), "uploaded": bool(result.get("uploaded")),
                                  "per_second": round(evaluated / run.seconds, 3) if run.seconds > 0 else None}
        return results

    def rest(self) -> None:
        """Put the lab box to sleep now (the lab is idle); the next batch wakes it."""
        rest = getattr(self.sandbox, "rest", None)
        if rest is not None:
            rest(self.box_key)
