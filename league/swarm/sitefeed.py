"""The swarm's part of the site (schema 2): the agents and the Gym's pace, through `house.site_inputs()`.

    agents  [{id, family, mechanism, structure, band, born_at, retired_at,
              record: {trials, revisions, forward: {trades, wins, pnl_usd} | None, real: {...} | None}}]
    gym     {as_of, trials, market_years, families_alive, families_retired}

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

from . import DB_NAME
from .store import loads


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


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
                                                " inherited_trials, revisions FROM families")]
            totals = dict(db.execute("SELECT COALESCE(SUM(trials),0) AS trials, COALESCE(SUM(program_years),0) AS years FROM runs").fetchone())
            forward: dict[str, dict[str, dict[str, Any]]] = {}
            for r in db.execute("SELECT family, source, COUNT(*) AS n, SUM(pnl) AS pnl, SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins"
                                " FROM forward GROUP BY family, source"):
                forward.setdefault(r["family"], {})[r["source"]] = {"trades": int(r["n"]), "wins": int(r["wins"] or 0),
                                                                   "pnl_usd": round(float(r["pnl"] or 0.0), 2)}
        finally:
            db.close()
    except sqlite3.Error:
        return {}
    alive = [f for f in fams if not f["retired_at"]]
    dead = sorted((f for f in fams if f["retired_at"]), key=lambda f: f["retired_at"], reverse=True)[:retired_shown]
    agents = []
    for f in alive + dead:
        rec = forward.get(f["id"], {})
        fwd = None
        if rec:
            fwd = {"trades": sum(v["trades"] for v in rec.values()), "wins": sum(v["wins"] for v in rec.values()),
                   "pnl_usd": round(sum(v["pnl_usd"] for v in rec.values()), 2)}
        agents.append({"id": f["id"], "family": f["lineage"], "mechanism": f["mechanism"], "structure": f["structure"],
                       "band": "retired" if f["retired_at"] else f["band"], "born_at": f["born_at"], "retired_at": f["retired_at"],
                       "record": {"trials": int(f["trials"]) + int(f["inherited_trials"]), "revisions": int(f["revisions"]),
                                  "forward": fwd, "real": rec.get("real")}})
    gym = {"as_of": _iso(time.time()), "trials": int(totals["trials"]), "market_years": round(float(totals["years"]), 1),
           "families_alive": len(alive), "families_retired": len(fams) - len(alive)}
    return {"gym": gym, "agents": agents}


__all__ = ["site_inputs"]
