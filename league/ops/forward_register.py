"""The `forward_register` job: the forward registry of every equity version judged on the Train bar (release E3).

Owner: A (league/ops/E3_INTERFACES.md). Protected. Hourly at :25 and at the House's start; in a pause too (it reads
the swarm store and the live book read-only and writes only `<state>/forward.sqlite`). The nightly forward shadow
calls `sync` itself before its runs.

WHAT IS REGISTERED (`sync`, idempotent: the registry's key is UNIQUE and each insert is one transaction with its chain
link, league/ops/forward_db.py `append_registry`):
- every version whose Train runs finished "ok" and were judged on the bar, PASSED OR FAILED (`scored_versions`: its
  verdict's `pnl_10` is not None): reason "train_pass" or "train_fail". Forward statistics are then survivor-free,
  and "do Train passers beat Train failers on days no author saw" is the only clean test of the bar itself. A version
  that could not be judged (RUN, DQ, LOAD, WINDOW) has no figure and is not registered;
- the captain-seeded programs (`seed_versions`: reason "seed") and every live instance not yet registered
  (`live_instances`: reason "live", from the book row's own code and params);
- with a base group's first non-control program, that group's skill-free controls (league/ops/forward_controls.py:
  reason and lane "control", family and version NULL, author "house", evidence "registry", `run_sha` = `program_sha`,
  route "none", alpha_f "0"; code the canonical JSON of its spec, params "{}", needs {"symbols", "history": 1,
  "max_hold_sessions": 20}). A group with no symbol in the universe has no control; a control never stops.

WHEN A PROGRAM EXISTED (D2): `created_at` is the `at` of the earliest swarm event of kind `swarm.elane` whose payload
has `pass` "scored" and names its family, version and code sha (evidence "event:<seq>"; the swarm store keeps `at` as
ISO text to the second); with none, the instant the registry first saw it (evidence "registry"). No row claims a
time before its evidence. The scored events are read from `seq >` kv `scored_seq`; the cursor moves past the rows
handled. Every program row carries `forward_db.E3_ROUTE` and `E3_ALPHA_F` in its hashed row.

REFUSED, each a `register_skipped` event (once a key and cause) and a `skipped` entry, never a row: sha256(code)
differs from the version's sha or the event's; `elane_train.needs_literal(code)` is None or `program.parse_needs`
refuses it; a family whose structure is not "etf" or "stock".

TAGS, each run, from the swarm store and the live book: review_pass (the record's `passed_version` is the version),
review_fail (its fails are ["REVIEW"]), try and try_entered (`elane_try`), look_pass / look_fail (`elane_look`'s
verdict), live (value: the instance id).

THE STOP RULES, each run, from the forward store's own rows and events, counting only nights after the pid's latest
"resumed" tag. A FAILURE NEVER STOPS A PROGRAM.
- stopped, value "cap:<night>": its STORED days (any status, the newest engine) reach its reason's session cap
  (`stop_after_sessions`: train_pass, seed, live; `stop_fail_after_sessions`: train_fail);
- stopped, value "disqualified:<night>": a `run_disqualified` event on each of the last `DQ_NIGHTS` nights (its own
  doing, three nights running). The shadow then writes its FINAL checkpoint, so what it earned stays in the meters;
- suspect, value the night: a `run_failed` event on each of the last `SUSPECT_NIGHTS` nights whose `fwd_runs` row has
  programs >= 1. A suspect is not stopped: it runs last and is counted in the report;
- `data_failed` and `night_failed` events mark no program and count toward nothing.
`resume` is the operator's undo of a stop; no job calls it. The next night's whole recompute fills every day the stop
left out.

THE IDENTITY WATCH: `evaluator.equity_fingerprint()` against kv `equity_sha`; a move while `eq_instances` holds a live
row is an `identity_moved` event (once a new value) and a `ctx.alert("warning", ...)`; the kv is then updated.

The receipt holds counts, `chain_ok` and `head`, never a program's figure; every alert text holds ids, counts and
dates only. Standard library only.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Mapping


def run(ctx: Any) -> dict[str, Any]:
    """THE JOB (league/ops/registry.py): skipped when `forward_db.mode` is "off" or the swarm store is absent; else
    `sync` on `<root>/forward.sqlite` (opened writable) with the swarm's settings, and the identity watch. The receipt:
    `sync`'s counts with `chain_ok` and `head`."""
    raise NotImplementedError("A: league/ops/forward_register.py run")


def sync(root: str | Path, db: sqlite3.Connection, *, now: float, settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """Register, tag and apply the stop rules (the module docstring), reading the swarm store and the live book
    read-only: {"registered", "controls", "tagged", "stopped", "suspect" (counts), "skipped": [{"key", "why"}],
    "chain": `forward_db.verify_chain`'s answer}. Idempotent: a second call adds nothing."""
    raise NotImplementedError("A: league/ops/forward_register.py sync")


def scored_versions(store: Any) -> list[dict[str, Any]]:
    """Every equity version judged on the bar: for each family of `elane_seal.equity_families(store)` with an
    `elane_train.STATE_KEY` record, each version n whose verdict has `pnl_10` not None. Each row: family, version,
    lane, lineage (`elane.lineage_key(lane, fam["lineage"])`), code, params, sha, run_sha (`gate.run_sha`), author,
    `bar_passed` (the scored event's; else `verdict.get("bar_passed") or verdict["passed"]`), created_at (epoch),
    evidence ("event:<seq>" | "registry"), reason ("train_pass" when `bar_passed`, else "train_fail")."""
    raise NotImplementedError("A: league/ops/forward_register.py scored_versions")


def seed_versions(store: Any) -> list[dict[str, Any]]:
    """The captain-seeded programs (the swarm store's kv `elane.SEEDS_KEY`), each at the version `elane.candidate(fam,
    store)` names: rows as `scored_versions`' with reason "seed"."""
    raise NotImplementedError("A: league/ops/forward_register.py seed_versions")


def live_instances(live_path: str | Path) -> list[dict[str, Any]]:
    """The live book's `eq_instances` rows (read-only; [] when the book or the table is absent): id, family, version,
    lane, run_sha, code, params, created_at, retired_at. An instance's registry key is its id less ":r"; one not yet
    registered is registered with reason "live" from the row's own code and params."""
    raise NotImplementedError("A: league/ops/forward_register.py live_instances")


def resume(db: sqlite3.Connection, key: str, *, why: str, at: float) -> bool:
    """The operator's undo of a stop: a "resumed" tag (value `<at>|<why>`) and a `resumed` event on the key's pid;
    False when the key is not registered. Nights before it no longer count toward a stop or a suspect tag."""
    raise NotImplementedError("A: league/ops/forward_register.py resume")


__all__ = ["run", "sync", "scored_versions", "seed_versions", "live_instances", "resume"]
