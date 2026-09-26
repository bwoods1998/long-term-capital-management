"""What the House reads of the swarm: each family's band and the program that holds it.

    from league.swarm import bands
    view = bands.read(root)            # never raises, never waits more than a second
    for fam in view["families"]:       # every living family, and the retired ones with a band history
        fam["band"]                    # gym | candidate | probe | sized | retired
        fam["program"]                 # {version, sha, params, path} of the version that holds the band (None in the Gym)
    code = bands.program_code(root, fam["id"])    # that program's source (for the live path's runner)
    bands.record_forward(root, fam["id"], "shadow", [{"id", "day", "pnl", "max_loss"}, ...])   # the House's records

The swarm writes bands (the gate: Candidate and Probe; the forward record: Sized, or back to the Gym); the
MONEY rules for Probe and Sized (sizes, caps, stops) are the live path's. The House never blocks on the
swarm: `read` opens the store read-only with a one-second timeout and returns {"families": [], "error": ...}
when it cannot.

Standard library only.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import DB_NAME
from .store import CLOSEABLE, SwarmStore, loads


def read(root: str | Path) -> dict[str, Any]:
    """Every living family's band, the program holding it and its evidence summaries (see the module doc)."""
    path = Path(root) / DB_NAME
    out: dict[str, Any] = {"as_of": time.time(), "families": []}
    if not path.exists():
        out["error"] = "no swarm store yet"
        return out
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        db.row_factory = sqlite3.Row
        try:
            rows = [dict(r) for r in db.execute("SELECT * FROM families WHERE retired_at IS NULL OR band != 'retired' ORDER BY id")]
            versions = {}
            for r in db.execute("SELECT family, n, sha, params, path FROM versions"):
                versions[(r["family"], r["n"])] = dict(r)
            forward = {}
            for r in db.execute("SELECT family, source, COUNT(*) AS n, SUM(pnl) AS pnl, SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins"
                                " FROM forward GROUP BY family, source"):
                forward.setdefault(r["family"], {})[r["source"]] = {"trades": r["n"], "wins": r["wins"], "pnl_usd": round(r["pnl"] or 0.0, 2)}
        finally:
            db.close()
    except sqlite3.Error as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out
    for r in rows:
        state = loads(r.get("state"), {}) or {}
        n = state.get("banded_version") if r["band"] in ("candidate", "probe", "sized") else None
        v = versions.get((r["id"], n)) if n else None
        out["families"].append({
            "id": r["id"], "lineage": r["lineage"], "band": r["band"], "band_since": r.get("band_since"),
            "structure": r["structure"], "closeable": r["structure"] in CLOSEABLE, "roots": loads(r["roots"], []),
            "mechanism": r["mechanism"], "born_at": r["born_at"], "retired_at": r.get("retired_at"),
            "program": ({"version": v["n"], "sha": v["sha"], "params": loads(v["params"], {}), "path": str(Path(root) / v["path"])}
                        if v else None),
            "validation": state.get("validation_view"), "holdout": "pass" if r["band"] in ("candidate", "probe", "sized") else None,
            "forward": forward.get(r["id"], {}), "forward_record": state.get("forward"),
            "trials": int(r["trials"]) + int(r["inherited_trials"]), "revisions": r["revisions"],
        })
    return out


def program_code(root: str | Path, family: str) -> str | None:
    """The source of the version holding a family's band (None in the Gym band or when unreadable)."""
    for fam in read(root)["families"]:
        if fam["id"] == family and fam.get("program"):
            try:
                return Path(fam["program"]["path"]).read_text(encoding="utf-8")
            except OSError:
                return None
    return None


def record_forward(root: str | Path, family: str, source: str, trades: Iterable[Mapping[str, Any]]) -> int:
    """The House's forward trades for a family (`shadow` or `real`), each once by id. Returns how many were new."""
    if source not in ("shadow", "real"):
        raise ValueError("the House records shadow or real trades; the swarm records its nightly replays")
    store = SwarmStore(root)
    try:
        return store.add_forward(family, source, trades)
    finally:
        store.close()


__all__ = ["read", "program_code", "record_forward"]
