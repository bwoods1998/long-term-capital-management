"""What the live path reads of the swarm: the families it may run, with their programs.

    from league.swarm import bands
    rows = bands.read(root)        # never raises, never waits more than a second ([] when it cannot read)

One row per family the live path may run: every family in the Candidate, Probe or Sized band, and every
family in the Gym band whose validated version met the validation line AND passed the gate's review and audit,
and whose holdout look (or forward record) has not failed and was not refused (execution tuition: 1-lot real
orders that measure multi-leg fills and are never evidence). Each row:

    family                the family's id
    band                  gym | candidate | probe | sized
    structure, roots      its structure type and roots
    holdout_passed        it passed its holdout look (Candidate or better)
    validation_passed     its validated version met the validation line
    version, code, params, run_sha
                          the program the row stands for: the version that holds the band (holdout passed),
                          else the version that met the validation line
    typical_max_loss_usd  the median maximum loss of ONE structure in that version's validation run (None when
                          it opened none)
    seed_era              the program was written by a model that knows 2024-2026 (every program in this swarm
                          is): it needs a forward record before it is Sized
    forward               its forward record (nightly + shadow + real): trades, wins, pnl_usd, mean_rom, lcb80,
                          negative (>= 20 trades and P&L below zero)

OWNERSHIP OF THE BANDS. The swarm moves gym <-> candidate (the gate's holdout pass; a Candidate whose forward
record turns negative over 20 trades goes back to the Gym) and retires families. The LIVE PATH alone moves
candidate <-> probe <-> sized by the Money table, writing through `SwarmStore(root).set_band(fid, band,
reason=...)`, and records its trades with `SwarmStore(root).add_forward(fid, "shadow" | "real", trades)` (ids
unique per family). A Probe or Sized family whose forward record turns negative is flagged here
(`forward.negative`) for the live path to demote.

Standard library only.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from . import DB_NAME
from .store import loads

LIVE_BANDS = ("candidate", "probe", "sized")


def read(root: str | Path) -> list[dict[str, Any]]:
    """The rows (the module docstring). [] when there is no store or it cannot be read within a second."""
    path = Path(root) / DB_NAME
    if not path.exists():
        return []
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        db.row_factory = sqlite3.Row
        try:
            fams = [dict(r) for r in db.execute("SELECT id, band, structure, roots, state FROM families WHERE retired_at IS NULL ORDER BY id")]
            wanted: dict[str, int] = {}
            for fam in fams:
                state = loads(fam["state"], {}) or {}
                fam["state"] = state
                if fam["band"] in LIVE_BANDS and state.get("banded_version"):
                    wanted[fam["id"]] = int(state["banded_version"])
                elif fam["band"] == "gym" and (state.get("validation_line") or {}).get("passed") and state.get("validation_version"):
                    wanted[fam["id"]] = int(state["validation_version"])  # tuition: checked against its review below
            versions = {}
            for fid, n in wanted.items():
                row = db.execute("SELECT n, sha, params, path FROM versions WHERE family=? AND n=?", (fid, n)).fetchone()
                if row is not None:
                    versions[fid] = dict(row)
        finally:
            db.close()
    except sqlite3.Error:
        return []
    out = []
    for fam in fams:
        v = versions.get(fam["id"])
        if v is None:
            continue
        try:
            code = (Path(root) / v["path"]).read_text(encoding="utf-8")
        except OSError:
            continue
        state = fam["state"]
        params = loads(v["params"], {}) or {}
        from .gate import run_sha

        sha = run_sha({"sha": v["sha"], "params": params})
        if fam["band"] == "gym":
            # Tuition only for a validated version the review (and the audit) passed and the gate has not failed, refused
            # or demoted: a program the reviewer called dangerous, or one whose holdout or forward record failed, never
            # sends a real order.
            review = state.get("review") or {}
            outcome = state.get("gate_outcome") or {}
            if review.get("sha") != sha or review.get("verdict") != "pass":
                continue
            if outcome.get("sha") == sha and outcome.get("result") in ("refused", "failed", "demoted"):
                continue
        validated = state.get("validation_version") == v["n"] and bool((state.get("validation_line") or {}).get("passed"))
        out.append({
            "family": fam["id"], "band": fam["band"], "structure": fam["structure"], "roots": loads(fam["roots"], []),
            "holdout_passed": fam["band"] in LIVE_BANDS, "validation_passed": validated or fam["band"] in LIVE_BANDS,
            "version": int(v["n"]), "code": code, "params": params, "run_sha": sha,
            "typical_max_loss_usd": state.get("typical_max_loss_usd") if state.get("validation_version") == v["n"] else None,
            "seed_era": True, "forward": state.get("forward"),
        })
    return out


__all__ = ["read", "LIVE_BANDS"]
