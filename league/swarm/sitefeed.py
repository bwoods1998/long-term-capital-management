"""The swarm's part of the site (schema 2): the agents and the Gym's pace, through `house.site_inputs()`.

    agents  [{id, family, mechanism, structure, band, born_at, retired_at,
              record: {trials, revisions, forward: {trades, wins, pnl_usd} | None, real: {...} | None}}]
    gym     {as_of, trials, market_years, families_alive, families_retired}
    compute {as_of, sail_usd, claude_usd, openai_usd}: the swarm's own spend; Sail as Sail billed it (`sail_billed`)

An agent is a family (its id); `family` is its lineage (the founder a fork descends from). Never a program,
a parameter, a quote, a spread, an implied vol or a result of the Gym beyond counts: the publisher's own
allowlist (`league/publish.py`) enforces it again. The newest retired families are kept for the page's
retired list; the publisher caps the list. `agent_rows(root, ids)` gives the same rows for any families, alive or
retired: the publisher pins every agent a real position names, so its card always has a name, a mechanism and a record.

A mechanism is `public.mechanism_text`: its whole sentences while they fit 240, each with no number (no digit, no number
word, no numeral of any script: so no entry window or threshold, "8-21 DTE", "over the next 1-3 sessions", ever reaches
the roster; the swarm window's safety review, Oct 1, 2026), no code mark and no parameter name of its family
(`param_names`: every version's PARAMS overrides and every version's program's PARAMS keys, cached by the newest version;
the window's review, C8). A mechanism with nothing left publishes as None.

Standard library only.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from . import DB_NAME, evidence, public
from .store import loads, priors_of


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


#: Sail's billed cost between the reset (T0, 2026-09-26T06:23:14Z) and the moment the Sail guard's balance meter began
#: (the swarm store's `burst_started_at`, 2026-09-26T10:22:26Z): the provider's app-scoped box billing for exactly that
#: window, $0.457 over 21 boxes (read Sept 30, 2026). No Sail model call was made before the meter began (the swarm's
#: first was at 10:23:35Z), so the meter plus this is every Sail charge since the reset.
PRE_METER_SAIL_USD = 0.46
#: The original meter's start, to the second. A later start (a new swarm store) missed more than that window.
METER_STARTED_BY = 1790418147.0


def sail_billed(spend: dict[str, float], metered: Any, started: Any) -> float:
    """Sail since the reset as Sail billed it (the owner, Sept 30, 2026: the public cost never understated): the guard's
    own meter (`guard.SailGuard._metered`: every fall of the Sail balance between two good readings since the swarm began,
    so every box and model call on the account, booked or not) plus the window before it, and never less than the model
    calls the swarm booked itself. The Gym's booked box estimate is NOT the bill: it runs about 70% above the provider's
    box billing (the economics report, Sept 30, 2026). A store whose meter began later than the original, or has no
    reading, cannot say what Sail billed before it, so the booked figures stand in (they run above the bill)."""
    booked = float(spend.get("sail_model", 0.0))
    try:
        metered, started = float(metered), float(started)
    except (TypeError, ValueError):
        return booked + float(spend.get("gym_box", 0.0))
    if started > METER_STARTED_BY or metered < 0:
        return booked + float(spend.get("gym_box", 0.0))
    return max(metered + PRE_METER_SAIL_USD, booked)


#: Each family's parameter names, by (store, family, newest version, its sha): read again only when a version is added.
_NAMES: dict[tuple[str, str, int, str], tuple[str, ...]] = {}
#: A program's PARAMS keys, by its code's sha (a program is immutable once stored).
_CODE_NAMES: dict[str, tuple[str, ...]] = {}
_CACHE_CAP = 20_000


def _remember(cache: dict, key: Any, value: Any) -> Any:
    if len(cache) >= _CACHE_CAP:
        cache.clear()
    cache[key] = value
    return value


def code_names(sha: str, read: Any) -> tuple[str, ...] | None:
    """The PARAMS keys of the program whose code has `sha` (`read()` gives the code), cached by `sha`; None when the code
    cannot be read (never cached: it is tried again)."""
    if sha and sha in _CODE_NAMES:
        return _CODE_NAMES[sha]
    try:
        names = tuple(public.param_names_of(read()))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return _remember(_CODE_NAMES, sha, names) if sha else names


def param_names(db: sqlite3.Connection, root: str | Path, ids: Any) -> dict[str, tuple[tuple[str, ...], bool]]:
    """{family: (its parameter names, known)}: the keys of every version's PARAMS overrides and of every version's
    program's PARAMS (read from the store's files, each program cached by its sha), from an open read-only connection to
    the store, so a name a family ever used is never published. A family with no version has none, known. When its
    newest program cannot be read, `known` is False and the rest is given: its mechanism is filtered against it, and it
    gets no thesis (`league/site_window.py`). Cached by the newest version, so a publish reads a family's versions again
    only when one was added."""
    out: dict[str, tuple[tuple[str, ...], bool]] = {}
    for fid in ids:
        newest = db.execute("SELECT n, sha FROM versions WHERE family=? ORDER BY n DESC LIMIT 1", (fid,)).fetchone()
        if newest is None:
            out[fid] = ((), True)
            continue
        key = (str(root), str(fid), int(newest["n"]), str(newest["sha"]))
        if key in _NAMES:
            out[fid] = (_NAMES[key], True)
            continue
        versions = list(db.execute("SELECT n, sha, params, path FROM versions WHERE family=? ORDER BY n", (fid,)))
        names: set[str] = set()
        known = True
        for v in versions:
            given = loads(v["params"], {})
            names.update(str(k) for k in (given if isinstance(given, dict) else {}))
        for v in {str(v["sha"]): v for v in versions}.values():  # each program once
            found = code_names(str(v["sha"]), lambda v=v: (Path(root) / str(v["path"])).read_text(encoding="utf-8"))
            if found is not None:
                names.update(found)
            elif v["sha"] == newest["sha"]:
                known = False  # the program the family runs now cannot be read: its names are not all known
        out[fid] = (_remember(_NAMES, key, tuple(sorted(names))) if known else tuple(sorted(names)), known)
    return out


def _read(root: str | Path, ids: Any = None, *, retired_shown: int = 24, light: bool = False) -> dict[str, Any] | None:
    """What the site's agents and the Gym's pace are made of, read once from the store (read-only); None when there is no
    store or it cannot be read. `ids`: whose parameter names to read (default: the families `site_inputs` shows). `light`:
    the agents' rows only (`agent_rows`, each publish): not the Gym's totals over every run, the spend or the meter."""
    path = Path(root) / DB_NAME
    if not path.exists():
        return None
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        db.row_factory = sqlite3.Row
        try:
            fams = [dict(r) for r in db.execute("SELECT id, lineage, mechanism, structure, band, born_at, retired_at, trials,"
                                                " revisions, spec, origin FROM families")]
            chosen = list(ids) if ids is not None else [f["id"] for f in _shown(fams, retired_shown)]
            totals, spend, meter = {}, {}, {}
            if not light:
                totals = dict(db.execute("SELECT COALESCE(SUM(trials),0) AS trials, COALESCE(SUM(program_years),0) AS years FROM runs").fetchone())
                spend = {r["kind"]: float(r["usd"] or 0.0) for r in db.execute("SELECT kind, SUM(usd) AS usd FROM spend GROUP BY kind")}
                meter = {r["key"]: loads(r["value"], None) for r in db.execute(
                    "SELECT key, value FROM kv WHERE key IN ('metered_spent', 'burst_started_at')")}
            rows: dict[str, list[dict[str, Any]]] = {}
            banded: dict[str, Any] = {}
            for start in range(0, len(chosen), 500):  # only the families shown: their records and banded versions
                chunk = chosen[start:start + 500]
                marks = ",".join("?" * len(chunk))
                for r in db.execute(f"SELECT family, source, day, pnl, max_loss, version FROM forward WHERE family IN ({marks})", chunk):
                    rows.setdefault(r["family"], []).append(dict(r))
                for r in db.execute(f"SELECT id, state FROM families WHERE id IN ({marks})", chunk):
                    banded[r["id"]] = (loads(r["state"], {}) or {}).get("banded_version")
            links = list(db.execute("SELECT a,b FROM lineage_links")) if db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lineage_links'").fetchone() else []
            names = param_names(db, root, chosen)
        finally:
            db.close()
    except sqlite3.Error:
        return None
    return {"fams": fams, "totals": totals, "spend": spend, "meter": meter, "rows": rows, "banded": banded, "links": links,
            "names": names}


#: THE LEARNING GAME's children (league/swarm/game.py `ORIGIN`): never on the site. A child is born only of a program that
#: ranked near the top of the game's private exam, and its row (its mechanism is its parent's, its lineage its parent's,
#: its trials its lineage's) would name which lineage passed. Nor are their trials in any other family's.
PRIVATE_ORIGINS = ("game",)


def _shown(fams: list[dict[str, Any]], retired_shown: int = 24) -> list[dict[str, Any]]:
    """The families `site_inputs` shows: every alive one, then the newest retired (never a game child)."""
    fams = [f for f in fams if f.get("origin") not in PRIVATE_ORIGINS]
    alive = [f for f in fams if not f["retired_at"]]
    dead = sorted((f for f in fams if f["retired_at"]), key=lambda f: f["retired_at"], reverse=True)[:retired_shown]
    return alive + dead


def _agents(data: dict[str, Any], chosen: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The site's agent rows for `chosen` (rows of `data["fams"]`)."""
    fams, rows, banded, links = data["fams"], data["rows"], data["banded"], data["links"]
    # A family's trials are its lineage's (`SwarmStore.lineage_trials`: every member, and any lineage its root was born
    # on the slice of), the count its evidence is deflated by.
    by_line: dict[str, int] = {}
    prior: dict[str, list[str]] = {}
    connected: dict[str, set[str]] = {}
    for a, b in links:
        connected.setdefault(a, set()).add(b)
        connected.setdefault(b, set()).add(a)
    for f in fams:
        if f.get("origin") in PRIVATE_ORIGINS:
            continue  # a game child's trials would show in its parent's lineage that it bred
        by_line[f["lineage"]] = by_line.get(f["lineage"], 0) + int(f["trials"] or 0)
        before = priors_of(loads(f["spec"], {}) or {})  # `prior_lineage`, and a singles' slice's `prior_lineages`
        if f["id"] == f["lineage"] and before:
            prior[f["id"]] = before

    def lineage_trials(line: str) -> int:
        seen, pending = set(), [line]
        while pending:
            line = pending.pop()
            if not line or line in seen:
                continue
            seen.add(line)
            pending.extend(connected.get(line, set()) - seen)
            pending.extend(prior.get(line, ()))
        return sum(by_line.get(x, 0) for x in seen)

    agents = []
    for f in chosen:
        if f.get("origin") in PRIVATE_ORIGINS:
            continue
        # The same record the bands are judged on (`evidence.one_record`: the banded version's rows, one source a day).
        counted = evidence.one_record(rows.get(f["id"], []), version=banded.get(f["id"]))
        fwd = real = None
        if counted:
            fwd = {"trades": len(counted), "wins": sum(1 for r in counted if float(r["pnl"]) > 0),
                   "pnl_usd": round(sum(float(r["pnl"]) for r in counted), 2)}
        # Real money is every real trade the family made, whichever version made it.
        reals = [r for r in rows.get(f["id"], []) if r["source"] == "real"]
        if reals:
            real = {"trades": len(reals), "wins": sum(1 for r in reals if float(r["pnl"]) > 0),
                    "pnl_usd": round(sum(float(r["pnl"]) for r in reals), 2)}
        names, _known = data["names"].get(f["id"], ((), True))
        agents.append({"id": f["id"], "family": f["lineage"],
                       "mechanism": public.mechanism_text(f["mechanism"], param_names=public.unspelled(names, f["id"])),
                       "structure": f["structure"], "band": "retired" if f["retired_at"] else f["band"], "born_at": f["born_at"],
                       "retired_at": f["retired_at"],
                       "record": {"trials": lineage_trials(f["lineage"]), "revisions": int(f["revisions"]),
                                  "forward": fwd, "real": real}})
    return agents


def agent_rows(root: str | Path, ids: Any) -> list[dict[str, Any]]:
    """The site's agent rows (`site_inputs`' shape) for the families `ids`, alive or retired ([] when there is no store
    or it cannot be read; an id the store does not hold has no row)."""
    wanted = {str(i) for i in ids or ()}
    if not wanted:
        return []
    data = _read(root, sorted(wanted), light=True)
    if data is None:
        return []
    return _agents(data, [f for f in data["fams"] if f["id"] in wanted])


def site_inputs(root: str | Path, *, retired_shown: int = 24) -> dict[str, Any]:
    """{"gym": ..., "agents": [...], "compute": ...} from the swarm's store (read-only); {} when there is no store."""
    data = _read(root, retired_shown=retired_shown)
    if data is None:
        return {}
    agents = _agents(data, _shown(data["fams"], retired_shown))
    fams, totals, spend, meter = data["fams"], data["totals"], data["spend"], data["meter"]
    alive = [f for f in fams if not f["retired_at"]]
    gym = {"as_of": _iso(time.time()), "trials": int(totals["trials"]), "market_years": round(float(totals["years"]), 1),
           "families_alive": len(alive), "families_retired": len(fams) - len(alive)}
    # The project's input costs since the reset, by service. Sail as Sail billed it (`sail_billed`), never the Gym's booked
    # estimate. Claude's gateway-settled charges (and conservative in-flight holds) live in this ledger under "claude" and
    # publish as their own part (Sept 30, 2026; #431 had put them in other_usd, and an older site still gets them there:
    # `publish.legacy_compute`). OpenAI's historical charges stay separate, unresolved holds included (they may yet bill).
    # The House's `site_inputs()` adds the House's own before the page shows compute.
    compute = {"as_of": gym["as_of"], "sail_usd": round(sail_billed(spend, meter.get("metered_spent"), meter.get("burst_started_at")), 2),
               "claude_usd": round(spend.get("claude", 0.0), 2), "openai_usd": round(spend.get("openai", 0.0), 2)}
    return {"gym": gym, "agents": agents, "compute": compute}


__all__ = ["PRE_METER_SAIL_USD", "agent_rows", "param_names", "sail_billed", "site_inputs"]
