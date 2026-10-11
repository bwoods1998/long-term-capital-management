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
- stopped, value "disqualified:<night>": a `run_disqualified` event on each of the program's last `DQ_NIGHTS`
  COMPLETED runs (its own doing, three runs running). The shadow then writes its FINAL checkpoint, so what it earned
  stays in the meters;
- suspect, value the night: a `run_failed` event on each of the program's last `SUSPECT_NIGHTS` attempted nights
  whose `fwd_runs` row has programs >= 1. A suspect is not stopped: it runs last and is counted in the report;
- `data_failed`, `night_failed` and `run_behind` events mark no program and count toward nothing.
ITS OWN ATTEMPTED NIGHTS (`_attempts`; the review's fix). Both rules count the nights THE PROGRAM was run, never the
calendar's: the nights it has a `run_disqualified` or a `run_failed` event for, and the nights a run of it completed
(its row for the night's day written by that night). A night the budget left it stale, a night the data failed it and
a night it was not due are no night of its own: they neither count nor break the run of nights. Counted by the
calendar ("an event on each of the last N nights", the spec's words), neither rule could ever fire once the registry
outgrew the night: the budget's rotation then runs a program every other night or less, so a program disqualified at
every run was never stopped and a program the child cannot finish was never tagged.
`resume` is the operator's undo of a stop; no job calls it. The next night's whole recompute fills every day the stop
left out.

THE IDENTITY WATCH: `evaluator.equity_fingerprint()` against kv `equity_sha`; a move while `eq_instances` holds a live
row is an `identity_moved` event (once a new value) and a `ctx.alert("warning", ...)`; the kv is then updated.

WHOSE FAILURE. A store that cannot be read is the House's, never a version's: a swarm store or a live book under a
lock is a `skipped` entry under its file's name (no event, nothing refused), the rest of the run goes on (the stop
rules and the chain read the forward store alone), and the job's receipt is `failed`, so the runner starts it again
inside its grace. A `register_skipped` event is written only for what a version IS (`CAUSES`), once a key and cause.

WHAT THE REGISTRY KEEPS OF A PROGRAM: its text; its PARAMS as the swarm keeps them (`league.swarm.store.dumps`: exact,
so `gate.run_sha` of the registry's own row is the row's `run_sha` and the shadow runs the very parameters; never
rounded); its NEEDS as `results.canonical`.

The receipt holds counts, `chain_ok` and `head`, never a program's figure; every alert text holds ids, counts and
dates only. Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import forward_controls, forward_db

#: The House's stores this job reads, under the state root (league/swarm/__init__.py `DB_NAME`; league/equity/live.py).
SWARM_DB = "swarm.sqlite"
LIVE_DB = "live.sqlite"
#: The swarm event that is a version's time evidence (E2's own kind; payload `pass` "scored").
SCORED_KIND = "swarm.elane"
SCORED_PASS = "scored"
#: The real route's instance suffix (league/equity/live.py `REAL_SUFFIX`): an instance's registry key is its id less it.
REAL_SUFFIX = ":r"
#: The structures the forward record registers: an ETF or a stock program's (E1's and E2's). Release E4's third equity
#: structure, "panel" (league/swarm/elane.py `STRUCTURES`), is not among them on purpose: a panel version's row, its
#: nightly shadow and its twin are package J's (league/ops/forward_xs.py, owed).
STRUCTURES = ("etf", "stock")
#: A control's author and the NEEDS beside its symbols.
CONTROL_AUTHOR = "house"
CONTROL_NEEDS = {"history": 1, "max_hold_sessions": 20}
#: WHY A VERSION IS REFUSED (`register_skipped`, once a key and cause; never a row): cause -> the words.
CAUSES: dict[str, str] = {
    "version": "the swarm store holds no such version",
    "code": "the program text cannot be read, so its sha256 is not the version's",
    "sha": "sha256 of the program text differs from the version's sha",
    "event_sha": "sha256 of the program text differs from the sha its scored event names",
    "structure": "the family's structure is not etf or stock",
    "lane": "the family declares no equity lane",
    "needs": "NEEDS is not a literal dict the lane accepts",
    "params": "PARAMS are not a JSON object",
    "run_sha": "the run sha is not that of the program text with its PARAMS",
    "window": "its forward window cannot be read from the House's calendar",
    "row": "the registry refused its row (league/ops/forward_db.py `append_registry`)",
    "live_sha": "the live instance runs another run sha than the registry row of its key: not tagged live",
}


class _Refused(Exception):
    """A version the registry does not take (`cause`: a key of `CAUSES`)."""

    def __init__(self, cause: str):
        super().__init__(CAUSES[cause])
        self.cause = cause


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ------------------------------------------------------------------------------------------------------ the swarm's side
def _scored_events(store: Any, *, after: int = 0, family: str | None = None) -> list[dict[str, Any]]:
    """The scored events (kind `SCORED_KIND`, payload `pass` "scored") with `seq > after`, of `family` only when
    given, in seq order: {"seq", "at" (epoch), "family", "version", "sha", "bar_passed"}. A row whose time, family or
    version cannot be read is no evidence and is left out."""
    from . import schedule
    from ..swarm.store import loads

    sql, params = "SELECT seq, at, family, payload FROM events WHERE kind=? AND seq>?", [SCORED_KIND, int(after)]
    if family is not None:
        sql += " AND family=?"
        params.append(str(family))
    out = []
    for row in store._all(sql + " ORDER BY seq", params):
        payload = loads(row.get("payload"), {})
        if not isinstance(payload, Mapping) or payload.get("pass") != SCORED_PASS:
            continue
        at, version = schedule.epoch(row.get("at")), payload.get("version")
        if at is None or not row.get("family") or isinstance(version, bool) or not isinstance(version, int):
            continue
        out.append({"seq": int(row["seq"]), "at": float(at), "family": str(row["family"]), "version": int(version),
                    "sha": str(payload.get("sha") or ""), "bar_passed": payload.get("bar_passed")})
    return out


def _earliest(events: Iterable[Mapping[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    """Each (family, version)'s earliest scored event (D2)."""
    out: dict[tuple[str, int], dict[str, Any]] = {}
    for event in events:
        out.setdefault((str(event["family"]), int(event["version"])), dict(event))
    return out


def _families(store: Any) -> dict[str, dict[str, Any]]:
    """Every equity-lane family, alive or retired (a retired family keeps accruing forward days), by id."""
    from ..swarm import elane_seal

    return {str(fam["id"]): fam for fam in elane_seal.equity_families(store)}


def _row(store: Any, fam: Mapping[str, Any], n: int, *, reason: str | None, event: Mapping[str, Any] | None = None,
         verdict: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """One version of an equity family as the registry takes it, or `_Refused` (the module docstring, REFUSED)."""
    from ..equity import program
    from ..swarm import elane, elane_seal, elane_train
    from ..swarm.gate import run_sha
    from ..swarm.store import dumps

    fid = str(fam["id"])
    version = store.version(fid, int(n))
    if version is None:
        raise _Refused("version")
    code = version.get("code")
    if not isinstance(code, str):
        raise _Refused("code")
    sha = _sha(code)
    if sha != str(version.get("sha") or ""):
        raise _Refused("sha")
    if event is not None and str(event.get("sha") or "") != sha:
        raise _Refused("event_sha")
    if fam.get("structure") not in STRUCTURES:
        raise _Refused("structure")
    lane = elane_seal.lane_of_spec(fam.get("spec"))
    if lane is None:
        raise _Refused("lane")
    literal = elane_train.needs_literal(code)
    if literal is None:
        raise _Refused("needs")
    try:
        needs = program.parse_needs(literal)
    except Exception:  # noqa: BLE001 - `NeedsRefused`, whatever it says: the lane does not accept this NEEDS
        raise _Refused("needs") from None
    params = version.get("params")
    params = {} if params is None else params
    if not isinstance(params, dict):
        raise _Refused("params")
    held = (verdict or {}).get("bar_passed") or (verdict or {}).get("passed")
    passed = event.get("bar_passed") if event is not None and isinstance(event.get("bar_passed"), bool) else held
    return {"key": f"{fid}@{int(n)}", "family": fid, "version": int(n), "lane": lane,
            "lineage": elane.lineage_key(lane, str(fam.get("lineage") or fid)), "code": code, "params": dict(params),
            "params_text": dumps(params), "sha": sha, "run_sha": run_sha(version),
            "author": str(version.get("author") or ""), "bar_passed": bool(passed),
            "created_at": float(event["at"]) if event is not None else None,
            "evidence": f"event:{int(event['seq'])}" if event is not None else "registry",
            "reason": reason or ("train_pass" if passed else "train_fail"), "needs": needs.as_dict(),
            "ugroup": elane_train.symbols_group(needs.symbols)}


def _scored(store: Any, *, families: Mapping[str, Mapping[str, Any]] | None = None,
            events: Mapping[tuple[str, int], Mapping[str, Any]] | None = None, known: Any = (),
            lookup: bool = False) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """(the rows of every version judged on the bar whose key is not in `known`, the refused as (key, cause)). With
    `lookup` (`events` holds only the rows after the cursor), a version not yet registered is looked up by its family
    in the whole log: its earliest event may be one the cursor already passed."""
    from ..swarm import elane_train

    families = _families(store) if families is None else families
    events = _earliest(_scored_events(store)) if events is None else events
    rows: list[dict[str, Any]] = []
    refused: list[tuple[str, str]] = []
    for fid, fam in families.items():
        versions = elane_train.versions_of(elane_train.record_of(fam))
        older: dict[tuple[str, int], dict[str, Any]] | None = None
        for n in sorted(int(k) for k in versions):
            verdict = versions[str(n)]
            key = f"{fid}@{n}"
            if verdict.get("pnl_10") is None or key in known:   # not judged on the bar (RUN, DQ, LOAD, WINDOW): no figure
                continue
            event = events.get((fid, n))
            if lookup:                      # the EARLIEST event is the time (D2): one the cursor passed comes first
                if older is None:
                    older = _earliest(_scored_events(store, family=fid))
                event = older.get((fid, n), event)
            try:
                rows.append(_row(store, fam, n, reason=None, event=event, verdict=verdict))
            except _Refused as exc:
                refused.append((key, exc.cause))
    # Oldest evidence first, so pids follow the order the programs came to exist; one with no event after them.
    rows.sort(key=lambda r: (r["created_at"] is None, r["created_at"] or 0.0, r["family"], r["version"]))
    return rows, refused


def scored_versions(store: Any) -> list[dict[str, Any]]:
    """Every equity version judged on the bar: for each family of `elane_seal.equity_families(store)` with an
    `elane_train.STATE_KEY` record, each version n whose verdict has `pnl_10` not None. Each row: family, version,
    lane, lineage (`elane.lineage_key(lane, fam["lineage"])`), code, params, sha, run_sha (`gate.run_sha`), author,
    `bar_passed` (the scored event's; else `verdict.get("bar_passed") or verdict["passed"]`), created_at (epoch),
    evidence ("event:<seq>" | "registry"), reason ("train_pass" when `bar_passed`, else "train_fail").

    Also `key`, `needs` and `ugroup` (from the program's own NEEDS) and `params_text` (the PARAMS as the swarm keeps
    them). `created_at` is the earliest scored event's time; None with evidence "registry" (the registry's own first
    sighting is the time, which `sync` writes). A version the registry refuses (`CAUSES`) is left out."""
    return _scored(store)[0]


def _seeds(store: Any, families: Mapping[str, Mapping[str, Any]] | None = None, known: Any = ()
           ) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    from ..swarm import elane

    held = store.get(elane.SEEDS_KEY) or {}
    rows: list[dict[str, Any]] = []
    refused: list[tuple[str, str]] = []
    for _, fid in sorted(held.items()) if isinstance(held, Mapping) else ():
        fam = (families or {}).get(str(fid)) or store.family(str(fid))
        if fam is None:
            continue
        n = elane.candidate(fam, store)
        if n is None or f"{fam['id']}@{int(n)}" in known:
            continue
        try:
            rows.append(_row(store, fam, int(n), reason="seed"))
        except _Refused as exc:
            refused.append((f"{fam['id']}@{int(n)}", exc.cause))
    return rows, refused


def seed_versions(store: Any) -> list[dict[str, Any]]:
    """The captain-seeded programs (the swarm store's kv `elane.SEEDS_KEY`), each at the version `elane.candidate(fam,
    store)` names: rows as `scored_versions`' with reason "seed"."""
    return _seeds(store)[0]


# ------------------------------------------------------------------------------------------------------- the live book
def live_instances(live_path: str | Path) -> list[dict[str, Any]]:
    """The live book's `eq_instances` rows (read-only; [] when the book or the table is absent): id, family, version,
    lane, run_sha, code, params, created_at, retired_at. An instance's registry key is its id less ":r"; one not yet
    registered is registered with reason "live" from the row's own code and params."""
    from . import guard

    path = Path(live_path)
    if not path.exists():
        return []

    def read(db: Any) -> list[dict[str, Any]]:
        if "eq_instances" not in set(guard.ids(db, "SELECT name FROM sqlite_master WHERE type='table'")):
            return []
        return guard.rows(db, "SELECT id, family, version, lane, run_sha, code, params, created_at, retired_at FROM "
                              "eq_instances ORDER BY id")

    out = []
    for row in guard.read(path, read):
        try:
            params = json.loads(row["params"]) if isinstance(row["params"], str) else row["params"]
        except ValueError:
            params = None
        out.append({**row, "id": str(row["id"]), "family": str(row["family"]), "version": int(row["version"]),
                    "params": params})
    return out


def instance_key(instance_id: str) -> str:
    """An instance's registry key: its id less ":r" ("<family>@<version>")."""
    text = str(instance_id)
    return text[:-len(REAL_SUFFIX)] if text.endswith(REAL_SUFFIX) else text


def _live_row(store: Any, families: Mapping[str, Mapping[str, Any]], instance: Mapping[str, Any]) -> dict[str, Any]:
    """A live instance the registry does not hold, from the book row's own code and params (reason "live")."""
    from ..equity import LANES, program
    from ..swarm import elane, elane_train
    from ..swarm.gate import run_sha
    from ..swarm.store import dumps

    code, params = instance.get("code"), instance.get("params")
    if not isinstance(code, str):
        raise _Refused("code")
    if not isinstance(params, dict):
        raise _Refused("params")
    sha = _sha(code)
    if run_sha({"sha": sha, "params": params}) != str(instance.get("run_sha") or ""):
        raise _Refused("run_sha")
    lane = instance.get("lane")
    if lane not in LANES:
        raise _Refused("lane")
    literal = elane_train.needs_literal(code)
    if literal is None:
        raise _Refused("needs")
    try:
        needs = program.parse_needs(literal)
    except Exception:  # noqa: BLE001 - as `_row`
        raise _Refused("needs") from None
    fid, n = str(instance["family"]), int(instance["version"])
    fam = families.get(fid) or {}
    author = ""
    if store is not None:
        try:
            author = str((store.version(fid, n) or {}).get("author") or "")
        except Exception:  # noqa: BLE001 - the author is ops' note, never a reason to refuse
            author = ""
    return {"key": instance_key(instance["id"]), "family": fid, "version": n, "lane": lane,
            "lineage": elane.lineage_key(lane, str(fam.get("lineage") or fid)), "code": code, "params": dict(params),
            "params_text": dumps(params), "sha": sha, "run_sha": str(instance["run_sha"]), "author": author,
            "bar_passed": None, "created_at": None, "evidence": "registry", "reason": "live",
            "needs": needs.as_dict(), "ugroup": elane_train.symbols_group(needs.symbols)}


# ------------------------------------------------------------------------------------------------------------ the sync
def _refuse(db: sqlite3.Connection, out: dict[str, Any], key: str, cause: str, *, now: float) -> None:
    """A version the registry does not take: a `skipped` entry every run, its `register_skipped` event once."""
    out["skipped"].append({"key": key, "why": CAUSES[cause]})
    forward_db.event(db, "register_skipped", payload={"key": key, "cause": cause, "why": CAUSES[cause]}, at=now,
                     once=f"{key}|{cause}")


def _register(db: sqlite3.Connection, row: Mapping[str, Any], known: dict[str, int], out: dict[str, Any], *,
              now: float) -> int | None:
    """One program row into the chain (D2: its window from the event's time, else from now). The new pid, or None for
    a key the registry holds or a row it refuses."""
    from ..equity import results
    from ..swarm.gate import run_sha

    key = str(row["key"])
    if key in known:
        return None
    try:
        if run_sha({"sha": row["sha"], "params": json.loads(row["params_text"])}) != row["run_sha"]:
            raise _Refused("run_sha")
        created = float(row["created_at"]) if row["evidence"] != "registry" else now
        try:
            close = forward_db.first_close(created)
            day = forward_db.first_day(close)
        except ValueError:
            raise _Refused("window") from None
    except _Refused as exc:
        _refuse(db, out, key, exc.cause, now=now)
        return None
    try:
        pid = forward_db.append_registry(db, {
            "key": key, "family": row["family"], "version": row["version"], "lane": row["lane"],
            "reason": row["reason"], "ugroup": row["ugroup"], "lineage": row["lineage"], "code": row["code"],
            "params": row["params_text"], "needs": results.canonical(row["needs"]), "program_sha": row["sha"],
            "run_sha": row["run_sha"], "author": row["author"], "created_at": created, "evidence": row["evidence"],
            "first_close": close, "first_day": day, "registered_at": now, "route": forward_db.E3_ROUTE,
            "alpha_f": forward_db.E3_ALPHA_F})
    except sqlite3.IntegrityError:          # another writer registered the key meanwhile: it stands
        return None
    except ValueError:                      # fail closed: one row the chain refuses never stops the others
        _refuse(db, out, key, "row", now=now)
        return None
    known[key] = pid
    out["registered"] += 1
    return pid


def _controls(db: sqlite3.Connection, known: dict[str, int], out: dict[str, Any], *, now: float,
              settings: Mapping[str, Any] | None) -> None:
    """Each base group a registered program's `ugroup` names gets its controls (D5), once: the ones not there yet (a
    run cut short is finished by the next). A group with no symbol in the universe has none."""
    from ..equity import results
    from ..swarm import elane, elane_train

    per = int(forward_db.cfg(settings)["controls_per_group"])
    if per <= 0:
        return
    named = {part for row in db.execute("SELECT DISTINCT ugroup FROM fwd_registry WHERE reason != 'control'").fetchall()
             for part in str(row[0]).split("+")}
    universe = elane.cfg(settings)["universe"]
    close = day = None
    for group in elane_train.GROUPS:
        if group not in named:
            continue
        symbols = forward_controls.group_symbols(group, universe)
        if not symbols:
            continue
        for n in range(per):
            key = f"control:{group}:{n}"
            if key in known:
                continue
            if close is None:
                try:
                    close = forward_db.first_close(now)
                    day = forward_db.first_day(close)
                except ValueError:          # the calendar does not reach: the next run registers them
                    out["skipped"].append({"key": "control", "why": CAUSES["window"]})
                    return
            code = results.canonical(forward_controls.spec(group, n, symbols))
            try:
                known[key] = forward_db.append_registry(db, {
                    "key": key, "family": None, "version": None, "lane": "control", "reason": "control",
                    "ugroup": group, "lineage": key, "code": code, "params": "{}",
                    "needs": results.canonical({"symbols": list(symbols), **CONTROL_NEEDS}), "program_sha": _sha(code),
                    "run_sha": _sha(code), "author": CONTROL_AUTHOR, "created_at": now, "evidence": "registry",
                    "first_close": close, "first_day": day, "registered_at": now,
                    "route": forward_db.CONTROL_ROUTE, "alpha_f": forward_db.CONTROL_ALPHA_F})
            except sqlite3.IntegrityError:
                continue
            out["controls"] += 1


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _tags(db: sqlite3.Connection, families: Mapping[str, Mapping[str, Any]], instances: Sequence[Mapping[str, Any]],
          out: dict[str, Any], *, now: float) -> None:
    """The facts learned later (the module docstring, TAGS), each written once: `at` is the run that first saw it."""
    from ..swarm import elane, elane_train

    held = {(int(r["pid"]), str(r["tag"]), str(r["value"])) for r in db.execute(
        "SELECT pid, tag, value FROM fwd_tags WHERE tag NOT IN ('stopped', 'resumed', 'suspect')").fetchall()}
    rows = db.execute("SELECT pid, key, family, version, run_sha FROM fwd_registry WHERE reason != 'control' "
                      "ORDER BY pid").fetchall()
    wanted: list[tuple[int, str, str]] = []
    for row in rows:
        fam = families.get(str(row["family"]))
        if fam is None:
            continue
        pid, n = int(row["pid"]), int(row["version"])
        state = _mapping(fam.get("state"))
        verdict = elane_train.versions_of(elane_train.record_of(fam)).get(str(n)) or {}
        if elane_train.passed_version(fam) == n:
            wanted.append((pid, "review_pass", ""))
        if list(verdict.get("fails") or []) == ["REVIEW"]:
            wanted.append((pid, "review_fail", ""))
        tried, verdicts = _mapping(state.get(elane.TRY_KEY)), _mapping(state.get(elane.VERDICTS_KEY))
        own = _mapping(verdicts.get(str(n)))
        if tried.get("version") == n or str(n) in verdicts:
            wanted.append((pid, "try", ""))
        if (tried.get("version") == n and tried.get("entered") is True) or own.get("entered") is True:
            wanted.append((pid, "try_entered", ""))
        looked = _mapping(state.get(elane.LOOK_KEY))
        if looked and looked.get("version") == n:
            passed = _mapping(looked.get("verdict")).get("passed") is True
            wanted.append((pid, "look_pass" if passed else "look_fail", ""))
    by_key = {str(row["key"]): row for row in rows}
    for instance in instances:
        row = by_key.get(instance_key(instance["id"]))
        if row is None:
            continue
        if str(row["run_sha"]) != str(instance.get("run_sha") or ""):
            _refuse(db, out, str(instance["id"]), "live_sha", now=now)
            continue
        wanted.append((int(row["pid"]), "live", str(instance["id"])))
    fresh = [item for item in dict.fromkeys(wanted) if item not in held]
    if fresh:
        with forward_db.transaction(db):
            for pid, tag, value in fresh:
                out["tagged"] += int(forward_db.tag(db, pid, tag, value, at=now))


def _night_of(row: Mapping[str, Any]) -> str | None:
    """The night an event of the shadow names: its `day`, else its `once` key when that is a day."""
    if row["day"]:
        return str(row["day"])
    try:
        once = str((json.loads(row["payload"]) or {}).get("once") or "")
    except (TypeError, ValueError, AttributeError):
        return None
    return once if len(once) == 10 and once[4] == "-" and once[7] == "-" else None


def _attempts(db: sqlite3.Connection, pid: int, nights: Sequence[tuple[str, int, float]],
              marks: Mapping[str, Mapping[int, Mapping[str, float]]], since: float | None) -> list[tuple[str, int, str]]:
    """A pid's OWN ATTEMPTED NIGHTS of `nights` (each (through, the programs it completed, when it ended); those after
    the pid's resume), oldest first: (night, the night's completed programs, how the pid's attempt ended). An attempt
    ended "run_disqualified" or "run_failed" when the shadow wrote that event for the night, and "ran" when the pid's
    row for the night's day was written by that night (a run of it completed and was not disqualified). A night that
    left the pid stale, gave it no data or did not have it due is NOT an attempt: it is no night of the pid's at all,
    so it neither counts toward a rule nor breaks a run of nights (a row for that day written by a LATER night's whole
    recompute is that later night's attempt)."""
    wrote = {str(r["day"]): float(r["at"]) for r in db.execute(
        "SELECT day, MIN(at) AS at FROM fwd_days WHERE pid=? GROUP BY day", (int(pid),)).fetchall()}
    out: list[tuple[str, int, str]] = []
    for night, programs, finished in nights:
        for kind in ("run_disqualified", "run_failed"):
            at = marks[kind].get(pid, {}).get(night)
            if at is not None and (since is None or at > since):
                out.append((night, programs, kind))
                break
        else:
            at = wrote.get(night)
            if at is not None and at <= finished and (since is None or at > since):
                out.append((night, programs, "ran"))
    return out


def _stops(db: sqlite3.Connection, out: dict[str, Any], *, now: float, settings: Mapping[str, Any] | None) -> None:
    """THE STOP RULES (the module docstring), from the forward store's own rows and events."""
    c = forward_db.cfg(settings)
    engine = forward_db.engine_now(db)
    stopped = forward_db._stopped(db)
    resumed = {int(r["pid"]): float(r["at"]) for r in db.execute(
        "SELECT pid, MAX(at) AS at FROM fwd_tags WHERE tag='resumed' GROUP BY pid").fetchall()}
    stored: dict[int, tuple[int, str]] = {}
    if engine is not None:
        stored = {int(r["pid"]): (int(r["n"]), str(r["last"])) for r in db.execute(
            "SELECT pid, COUNT(*) AS n, MAX(day) AS last FROM fwd_days WHERE engine=? GROUP BY pid", (engine,)).fetchall()}
    # A NIGHT is a shadow run that got past its preflight, named by the store's last day: (through, the most programs
    # a run of it completed, when its last run ended).
    nights = [(str(r["through"]), int(r["programs"] or 0), float(r["finished"])) for r in db.execute(
        "SELECT through, MAX(programs) AS programs, MAX(finished) AS finished FROM fwd_runs WHERE through IS NOT NULL "
        "GROUP BY through ORDER BY through").fetchall()]
    marks: dict[str, dict[int, dict[str, float]]] = {"run_disqualified": {}, "run_failed": {}}
    for row in db.execute("SELECT kind, pid, day, at, payload FROM fwd_events WHERE kind IN ('run_disqualified', "
                          "'run_failed') AND pid IS NOT NULL").fetchall():
        night = _night_of(row)
        if night is not None:
            marks[str(row["kind"])].setdefault(int(row["pid"]), {})[night] = float(row["at"])
    marked = set(marks["run_disqualified"]) | set(marks["run_failed"])
    for row in db.execute("SELECT pid, key, reason FROM fwd_registry WHERE reason != 'control' ORDER BY pid").fetchall():
        pid, since = int(row["pid"]), resumed.get(int(row["pid"]))
        if pid in stopped:
            continue
        cap = int(c["stop_fail_after_sessions"] if row["reason"] == "train_fail" else c["stop_after_sessions"])
        count, last = stored.get(pid, (0, ""))
        if since is not None and engine is not None:
            # After a resume the days stored before it no longer count (an engine move writes them again; they stay old).
            fresh = db.execute(
                "SELECT COUNT(*) AS n, MAX(day) AS last FROM fwd_days WHERE pid=? AND engine=? AND day > COALESCE((SELECT "
                "MAX(day) FROM fwd_days WHERE pid=? AND at<=?), '')", (pid, engine, pid, since)).fetchone()
            count, last = int(fresh["n"]), str(fresh["last"] or "")
        # ITS OWN ATTEMPTED NIGHTS (the module docstring), oldest first: read only for a pid that has a mark at all.
        tried = _attempts(db, pid, [n for n in nights if since is None or n[2] > since], marks, since) \
            if pid in marked else []

        def running(kind: str, of: Sequence[tuple[str, int, str]], need: int) -> str | None:
            """The latest of the pid's last `need` attempted nights of `of` when each of them ended `kind`."""
            if len(of) < need or any(n[2] != kind for n in of[-need:]):
                return None
            return of[-1][0]

        cause = night = None
        if count >= cap:
            cause, night = "cap", last
        else:
            # Its last runs that COMPLETED (a night the child failed it says nothing of what the program does).
            night = running("run_disqualified", [n for n in tried if n[2] != "run_failed"], forward_db.DQ_NIGHTS)
            cause = "disqualified" if night is not None else None
        if cause is not None:
            with forward_db.transaction(db):
                if forward_db.tag(db, pid, "stopped", f"{cause}:{night}", at=now):
                    payload = {"key": str(row["key"]), "cause": cause, "night": night}
                    if cause == "cap":
                        payload.update(sessions=count, cap=cap,
                                       why=f"its stored days reached its session cap ({count} of {cap})")
                    else:
                        payload.update(nights=forward_db.DQ_NIGHTS,
                                       why=f"disqualified by its own errors on its last {forward_db.DQ_NIGHTS} runs "
                                           "running (its own attempted nights)")
                    forward_db.event(db, "stopped", pid=pid, day=night, payload=payload, at=now)
                    out["stopped"] += 1
            continue
        night = running("run_failed", [n for n in tried if n[1] >= 1], forward_db.SUSPECT_NIGHTS)
        if night is not None:
            with forward_db.transaction(db):
                if forward_db.tag(db, pid, "suspect", night, at=now):
                    forward_db.event(db, "suspect", pid=pid, day=night,
                                     payload={"key": str(row["key"]), "nights": forward_db.SUSPECT_NIGHTS,
                                              "why": f"its run failed alone on its last {forward_db.SUSPECT_NIGHTS} "
                                                     "attempted nights running while other programs' runs completed: "
                                                     "it runs last, never stopped"},
                                     at=now)
                    out["suspect"] += 1


def sync(root: str | Path, db: sqlite3.Connection, *, now: float, settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """Register, tag and apply the stop rules (the module docstring), reading the swarm store and the live book
    read-only: {"registered", "controls", "tagged", "stopped", "suspect" (counts), "skipped": [{"key", "why"}],
    "chain": `forward_db.verify_chain`'s answer}. Idempotent: a second call adds nothing.

    A swarm store or a live book that cannot be read is a `skipped` entry under its file's name (`SWARM_DB`,
    `LIVE_DB`) and the House's failure, never a version's: the rest goes on."""
    from ..swarm.store import SwarmStore

    root, now = Path(root), float(now)
    out: dict[str, Any] = {"registered": 0, "controls": 0, "tagged": 0, "stopped": 0, "suspect": 0, "skipped": [],
                           "chain": None}
    known = {str(r["key"]): int(r["pid"]) for r in db.execute("SELECT key, pid FROM fwd_registry").fetchall()}
    families: dict[str, dict[str, Any]] = {}
    instances: list[dict[str, Any]] = []
    store = None
    readable = True
    try:
        if (root / SWARM_DB).exists():
            store = SwarmStore(root, readonly=True)
            families = _families(store)
            cursor = forward_db.kv_get(db, "scored_seq", 0)
            cursor = int(cursor) if isinstance(cursor, int) and not isinstance(cursor, bool) and cursor > 0 else 0
            fresh = _scored_events(store, after=cursor)
            rows, refused = _scored(store, families=families, events=_earliest(fresh), known=known, lookup=cursor > 0)
            seeds, seeds_refused = _seeds(store, families, known)
            for row in (*rows, *seeds):
                _register(db, row, known, out, now=now)
            for key, cause in (*refused, *seeds_refused):
                _refuse(db, out, key, cause, now=now)
            if fresh:                       # the cursor moves past the rows handled
                forward_db.kv_put(db, "scored_seq", max(cursor, fresh[-1]["seq"]))
    except sqlite3.Error as exc:
        readable = False
        out["skipped"].append({"key": SWARM_DB, "why": f"the swarm store could not be read ({type(exc).__name__}): "
                                                       "nothing registered from it this run"})
    try:
        try:
            instances = live_instances(root / LIVE_DB)
        except sqlite3.Error as exc:
            instances = []
            out["skipped"].append({"key": LIVE_DB, "why": f"the live book could not be read ({type(exc).__name__}): no "
                                                          "live instance registered or tagged this run"})
        if readable and store is not None and instances:
            try:    # a live instance's family may be no equity family of the swarm's any more: read it by its id
                for fid in sorted({str(i["family"]) for i in instances} - set(families)):
                    fam = store.family(fid)
                    if fam is not None:
                        families[fid] = fam
            except sqlite3.Error as exc:
                readable = False
                out["skipped"].append({"key": SWARM_DB, "why": f"the swarm store could not be read ({type(exc).__name__}"
                                                               "): no live instance registered or tagged this run"})
        for instance in instances:
            key = instance_key(instance["id"])
            if key in known or not readable:    # its lineage is the swarm's to say: the next run that reads it registers
                continue
            try:
                row = _live_row(store, families, instance)
            except _Refused as exc:
                _refuse(db, out, key, exc.cause, now=now)
                continue
            _register(db, row, known, out, now=now)
        _controls(db, known, out, now=now, settings=settings)
        if readable:
            _tags(db, families, instances, out, now=now)
    finally:
        if store is not None:
            store.close()
    _stops(db, out, now=now, settings=settings)
    out["chain"] = forward_db.verify_chain(db)
    return out


def resume(db: sqlite3.Connection, key: str, *, why: str, at: float) -> bool:
    """The operator's undo of a stop: a "resumed" tag (value `<at>|<why>`) and a `resumed` event on the key's pid;
    False when the key is not registered. Nights before it no longer count toward a stop or a suspect tag.

    False too, with nothing written, for a program that is not stopped (there is no stop to undo)."""
    program = forward_db.program(db, str(key))
    if program is None or forward_db.active(db, program.pid):
        return False
    words = " ".join(str(why or "").split())[:200]
    with forward_db.transaction(db):
        if not forward_db.tag(db, program.pid, "resumed", f"{float(at)!r}|{words}", at=float(at)):
            return False
        forward_db.event(db, "resumed", pid=program.pid, payload={"key": program.key, "why": words}, at=float(at))
    return True


# ------------------------------------------------------------------------------------------------- the identity watch
def identity_watch(root: str | Path, db: sqlite3.Connection, *, now: float) -> dict[str, Any]:
    """THE IDENTITY WATCH (the module docstring): {"moved", "live", "alert" (the warning's text, or None), "was",
    "now" (12 hex characters each)}. The first sighting only records the fingerprint. A move while the book holds a
    live instance is one `identity_moved` event (once a new value) and the alert; the kv then holds the new value. A
    live book that cannot be read leaves the kv as it was: the next run reads the move again."""
    from ..swarm import evaluator

    current = str(evaluator.equity_fingerprint())
    seen = forward_db.kv_get(db, "equity_sha")
    out: dict[str, Any] = {"moved": False, "live": 0, "alert": None, "was": str(seen)[:12] if seen else None,
                           "now": current[:12]}
    if seen == current:
        return out
    if seen is None:
        forward_db.kv_put(db, "equity_sha", current)
        return out
    out["moved"] = True
    out["live"] = sum(1 for i in live_instances(Path(root) / LIVE_DB) if i.get("retired_at") is None)
    with forward_db.transaction(db):
        if out["live"] and forward_db.event(
                db, "identity_moved", payload={"was": out["was"], "now": out["now"], "live": out["live"],
                                               "why": "the equity evidence identity moved while a lineage is live"},
                at=float(now), once=current):
            out["alert"] = (f"forward_register: the equity identity moved ({out['was']} to {out['now']}) while "
                            f"{out['live']} equity instances are live: the forward record opens a new engine series "
                            "(FW8)")
        forward_db.kv_put(db, "equity_sha", current)
    return out


def run(ctx: Any) -> dict[str, Any]:
    """THE JOB (league/ops/registry.py): skipped when `forward_db.mode` is "off" or the swarm store is absent; else
    `sync` on `<root>/forward.sqlite` (opened writable) with the swarm's settings, and the identity watch. The receipt:
    `sync`'s counts with `chain_ok` and `head`.

    `failed` (the runner starts it again inside its grace; `sync` is idempotent) when a store could not be read. A
    chain that does not verify is a House warning (FW4)."""
    from ..swarm import settings as settings_mod

    root = Path(ctx.root)
    settings = settings_mod.load(root, config=getattr(ctx, "config", None))
    if forward_db.mode(settings) == "off":
        return {"status": "skipped", "why": "elane.forward.mode is off"}
    if not (root / SWARM_DB).exists():
        return {"status": "skipped", "why": "no swarm store: nothing to register"}
    now = float(ctx.now())
    watch: dict[str, Any] = {"moved": False, "alert": None}
    unread: list[str] = []
    db = forward_db.open_db(root)
    try:
        out = sync(root, db, now=now, settings=settings)
        try:
            watch = identity_watch(root, db, now=now)
        except sqlite3.Error as exc:
            unread.append(f"{LIVE_DB} ({type(exc).__name__})")
    except sqlite3.Error as exc:
        return {"status": "failed", "ok": False, "error": f"the forward store could not be written: "
                                                          f"{type(exc).__name__}: {str(exc)[:200]}"}
    finally:
        db.close()
    chain = out["chain"]
    unread += [row["key"] for row in out["skipped"] if row["key"] in (SWARM_DB, LIVE_DB)]
    receipt = {"ok": bool(chain["ok"]) and not unread, "registered": out["registered"], "controls": out["controls"],
               "tagged": out["tagged"], "stopped": out["stopped"], "suspect": out["suspect"],
               "skipped": len([row for row in out["skipped"] if row["key"] not in (SWARM_DB, LIVE_DB)]),
               "rows": chain["rows"], "chain_ok": bool(chain["ok"]), "head": chain["head"],
               "identity_moved": bool(watch.get("moved"))}
    if not chain["ok"]:
        ctx.alert("warning", f"forward_register: the forward registry's hash chain does not hold at pid "
                             f"{chain['first_bad']} of {chain['rows']} rows (FW4): stop the forward jobs and compare "
                             "with the backup")
    if watch.get("alert"):
        ctx.alert("warning", watch["alert"])
    if unread:
        return {**receipt, "status": "failed", "error": f"could not be read: {', '.join(sorted(set(unread)))}"}
    return receipt


__all__ = ["run", "sync", "scored_versions", "seed_versions", "live_instances", "resume", "identity_watch",
           "instance_key", "CAUSES", "SWARM_DB", "LIVE_DB", "SCORED_KIND", "SCORED_PASS"]
