"""The swarm's part of the site (schema 2): the agents and the Gym's pace, through `house.site_inputs()`.

    agents  [{id, family, mechanism, structure, band, born_at, retired_at,
              record: {trials, revisions, forward: {trades, wins, pnl_usd} | None, real: {...} | None}}]
    gym     {as_of, trials, market_years, families_alive, families_retired}
    compute {as_of, sail_usd, claude_usd, openai_usd}: the swarm's own spend; Sail as Sail billed it (`sail_billed`)

An agent is a family (its id); `family` is its lineage (the founder a fork descends from). Never a program,
a parameter, a quote, a spread, an implied vol or a result of the Gym beyond counts: the publisher's own
allowlist (`league/publish.py`) enforces it again. The newest retired families are kept for the page's
retired list; the publisher caps the list.

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


def site_inputs(root: str | Path, *, retired_shown: int = 24) -> dict[str, Any]:
    """{"gym": ..., "agents": [...]} from the swarm's store (read-only); {} when there is no store."""
    path = Path(root) / DB_NAME
    if not path.exists():
        return {}
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        db.row_factory = sqlite3.Row
        try:
            fams = [dict(r) for r in db.execute("SELECT id, lineage, mechanism, structure, band, born_at, retired_at, trials,"
                                                " revisions, spec FROM families")]
            totals = dict(db.execute("SELECT COALESCE(SUM(trials),0) AS trials, COALESCE(SUM(program_years),0) AS years FROM runs").fetchone())
            spend = {r["kind"]: float(r["usd"] or 0.0) for r in db.execute("SELECT kind, SUM(usd) AS usd FROM spend GROUP BY kind")}
            meter = {r["key"]: loads(r["value"], None) for r in db.execute(
                "SELECT key, value FROM kv WHERE key IN ('metered_spent', 'burst_started_at')")}
            rows: dict[str, list[dict[str, Any]]] = {}
            for r in db.execute("SELECT family, source, day, pnl, max_loss, version FROM forward"):
                rows.setdefault(r["family"], []).append(dict(r))
            banded = {r["id"]: (loads(r["state"], {}) or {}).get("banded_version") for r in db.execute("SELECT id, state FROM families")}
            links = list(db.execute("SELECT a,b FROM lineage_links")) if db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lineage_links'").fetchone() else []
        finally:
            db.close()
    except sqlite3.Error:
        return {}
    # A family's trials are its lineage's (`SwarmStore.lineage_trials`: every member, and any lineage its root was born
    # on the slice of), the count its evidence is deflated by.
    by_line: dict[str, int] = {}
    prior: dict[str, list[str]] = {}
    connected: dict[str, set[str]] = {}
    for a, b in links:
        connected.setdefault(a, set()).add(b)
        connected.setdefault(b, set()).add(a)
    for f in fams:
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

    alive = [f for f in fams if not f["retired_at"]]
    dead = sorted((f for f in fams if f["retired_at"]), key=lambda f: f["retired_at"], reverse=True)[:retired_shown]
    agents = []
    for f in alive + dead:
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
        agents.append({"id": f["id"], "family": f["lineage"], "mechanism": public.news_text(f["mechanism"]), "structure": f["structure"],
                       "band": "retired" if f["retired_at"] else f["band"], "born_at": f["born_at"], "retired_at": f["retired_at"],
                       "record": {"trials": lineage_trials(f["lineage"]), "revisions": int(f["revisions"]),
                                  "forward": fwd, "real": real}})
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


__all__ = ["PRE_METER_SAIL_USD", "sail_billed", "site_inputs"]
