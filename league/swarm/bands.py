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

THE PRACTICE LEAGUE (the observe band: the sprint, B4, Sept 26, 2026; the Train tier Sept 29, 2026): `observe(root)` ->
one SHADOW-ONLY row per alive Gym-band family that has a version to practise, in one of two tiers:

- "validated": its state's `validation_version` (the current best version the tournament validated), whatever the
  validation line or the bundle said (the rule of Sept 26, unchanged);
- "train": no validated version, but an ELIGIBLE TRAIN VERSION: the version the tournament validates next
  (`Tournament.candidate_version`: the submitted best, else the best by Train score) that was not demoted (a loss at 1.5x,
  `robust_failed`, or a failed drift screen, `drift_failed`; a demotion also clears the best, so this is a belt).

The live path runs each row in the shadow book (`<family>@<version>:o`) with the version pinned for a session: never
real, never tuition, never a forward row, never a band move. A version whose own program review failed, or that the
gate refused, has no row. Each row says `observe: True`, `holdout_passed: False` and `validation_passed: False`, so
nothing that reads it can take it for a Candidate, and carries its `tier`, `lineage`, `best_train` and `needs_roots`
(the roots its program's NEEDS names: what the live path reads for it). THE ORDER (the live path admits in it, under its
caps): the validated tier by validation t (highest first, unknown last), then the Train tier by Train score (highest
first, unknown last), ties by family id. The validation t orders the House's admissions only; it is never shown to
research. `observe(root, family=f, version=n)` is the pinned version `n` of `f` while `f` is alive, still in the Gym
band and has a version in either tier, and `n` (when it is not the validated version) was not demoted ([] otherwise):
what the live path admits a pinned instance's shadow opens against.

`read(root, family=f)` and `observe(root, family=f)` read one family only (the live path's per-minute admissions). The
Gym bundle's version is built once per `BUNDLE_TTL` seconds a process, not once per call (it reads and hashes every file
of the Gym's code).

OWNERSHIP OF THE BANDS. The swarm moves gym <-> candidate (the gate's holdout pass; a Candidate whose forward
record turns negative over 20 trades goes back to the Gym) and retires families. The LIVE PATH alone moves
candidate <-> probe <-> sized by the Money table, writing through `SwarmStore(root).set_band(fid, band,
reason=...)`, and records its trades with `SwarmStore(root).add_forward(fid, "shadow" | "real", trades)` (ids
unique per family). A Probe or Sized family whose forward record turns negative is flagged here
(`forward.negative`) for the live path to demote.

Standard library only.
"""

from __future__ import annotations

import functools
import math
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from . import DB_NAME, settings
from .store import loads

LIVE_BANDS = ("candidate", "probe", "sized")
#: Seconds a process reuses the Gym bundle's version (`_bundle`).
BUNDLE_TTL = 300.0
_bundle_cache: tuple[float, str] | None = None
_bundle_lock = threading.Lock()


def _bundle() -> str | None:
    """The Gym bundle's version (`league.gym.driver.build_bundle`), built at most once per `BUNDLE_TTL` seconds a process:
    it tars and hashes every file of the Gym's code, and the live path asks once a minute per live instance. A failed
    build is not cached (None: no Gym row is admitted until it builds)."""
    global _bundle_cache
    now = time.monotonic()
    with _bundle_lock:
        cached = _bundle_cache
    if cached is not None and 0.0 <= now - cached[0] < BUNDLE_TTL:
        return cached[1]
    from ..gym.driver import build_bundle

    try:
        value = build_bundle()[1]
    except OSError:
        return None
    with _bundle_lock:
        _bundle_cache = (now, value)
    return value


def _families(db: sqlite3.Connection, family: str | None, *, gym_only: bool = False) -> list[dict[str, Any]]:
    where = "retired_at IS NULL" + (" AND band='gym'" if gym_only else "") + (" AND id=?" if family is not None else "")
    return [dict(r) for r in db.execute(f"SELECT id, band, structure, roots, state, lineage, best_version, best_train FROM "
                                        f"families WHERE {where} ORDER BY id", (() if family is None else (str(family),)))]


def read(root: str | Path, *, family: str | None = None) -> list[dict[str, Any]]:
    """The rows (the module docstring); `family`: that family's row only. [] when there is no store or it cannot be read
    within a second."""
    path = Path(root) / DB_NAME
    if not path.exists():
        return []
    image = settings.load(root)["gym"]["image_checkpoint"]
    bundle = _bundle()
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        db.row_factory = sqlite3.Row
        try:
            fams = _families(db, family)
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
            if not image or state.get("validation_image") != image or not bundle or state.get("validation_bundle") != bundle:
                continue
            # Tuition only for a validated version the review (and the audit) passed and the gate has not failed, refused
            # or demoted: a program the reviewer called dangerous, or one whose holdout or forward record failed, never
            # sends a real order.
            review = state.get("review") or {}
            outcome = state.get("gate_outcome") or {}
            if review.get("sha") != sha or review.get("verdict") != "pass" or (review.get("audit") or {}).get("verdict") != "pass":
                continue
            if outcome.get("sha") == sha and outcome.get("result") in ("refused", "failed", "demoted"):
                continue
        validated = state.get("validation_version") == v["n"] and bool((state.get("validation_line") or {}).get("passed"))
        out.append({
            "family": fam["id"], "band": fam["band"], "structure": fam["structure"], "roots": loads(fam["roots"], []),
            "holdout_passed": fam["band"] in LIVE_BANDS, "validation_passed": validated or fam["band"] in LIVE_BANDS,
            "version": int(v["n"]), "code": code, "params": params, "run_sha": sha,
            "typical_max_loss_usd": (state.get("typical_by_version") or {}).get(str(v["n"]),
                state.get("typical_max_loss_usd") if state.get("validation_version") == v["n"] else None),
            "seed_era": True, "forward": state.get("forward"),
        })
    return out


TIERS = ("validated", "train")


def _count(value: Any) -> int | None:
    """A positive int (a version number), else None."""
    return int(value) if isinstance(value, int) and not isinstance(value, bool) and value >= 1 else None


def _finite(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def demoted(state: Mapping[str, Any], n: int) -> bool:
    """Version `n` lost at 1.5x (`robust_failed`) or failed the drift screen (`drift_failed`)."""
    robust = {int(v) for v in (state.get("robust_failed") or []) if isinstance(v, int) and not isinstance(v, bool)}
    return int(n) in robust or str(int(n)) in (state.get("drift_failed") or {})


def practice_tier(fam: Mapping[str, Any], state: Mapping[str, Any]) -> tuple[str, int] | None:
    """(tier, version) of a family's practice row (the module docstring), or None: its validated version, else its
    eligible Train version (the tournament's candidate, `Tournament.candidate_version`, not demoted)."""
    validated = _count(state.get("validation_version"))
    if validated is not None:
        return "validated", validated
    n = _count(fam.get("best_version")) if fam.get("best_version") else _count(state.get("best_train_version"))
    if n is not None and not demoted(state, n):
        return "train", n
    return None


def priority(row: Mapping[str, Any]) -> tuple:
    """The practice league's admission order (the module docstring): validated by validation t, then Train by Train
    score, each highest first with unknown last, then by family id."""
    if row.get("tier", "validated") == "validated":
        t = _finite(row.get("validation_t"))
        return (0, t is None, -(t or 0.0), str(row.get("family")))
    b = _finite(row.get("best_train"))
    return (1, b is None, -(b or 0.0), str(row.get("family")))


@functools.lru_cache(maxsize=1024)
def _needs_roots(code: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
    try:
        from .researcher import needs_roots
    except Exception:  # noqa: BLE001 - the House can always fall back to the family's roots
        return fallback
    try:
        return tuple(needs_roots(code, fallback))
    except Exception:  # noqa: BLE001
        return fallback


def observe(root: str | Path, *, family: str | None = None, version: int | None = None) -> list[dict[str, Any]]:
    """The practice league's rows (the module docstring), in its admission order (`priority`). `family` narrows to one
    family; with `version`, that family's version `version` (a pinned one) instead of its current one. [] when there is no
    store. A store that cannot be read within a second RAISES (`sqlite3.Error`), unlike `read`: the live path then keeps
    the observe instances and pins it has, rather than taking an unreadable store for an empty band and pinning afresh in
    the middle of a session."""
    path = Path(root) / DB_NAME
    if not path.exists() or (version is not None and family is None):
        return []
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
    db.row_factory = sqlite3.Row
    try:
        fams = _families(db, family, gym_only=True)
        versions, tiers = {}, {}
        for fam in fams:
            state = loads(fam["state"], {}) or {}
            fam["state"] = state
            tier = practice_tier(fam, state)
            if tier is None:
                continue  # no validated and no eligible Train version: no row until it has one
            if version is None:
                name, n = tier
            else:
                n = int(version)
                name = "validated" if n == _count(state.get("validation_version")) else "train"
                if name == "train" and demoted(state, n):
                    continue  # the pinned Train version was demoted since: it winds down
            row = db.execute("SELECT n, sha, params, path FROM versions WHERE family=? AND n=?", (fam["id"], n)).fetchone()
            if row is not None:
                versions[fam["id"]], tiers[fam["id"]] = dict(row), name
    finally:
        db.close()
    from .gate import run_sha

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
        sha = run_sha({"sha": v["sha"], "params": params})
        review, outcome = state.get("review") or {}, state.get("gate_outcome") or {}
        if (review.get("sha") == sha and review.get("verdict") == "fail") or (
                outcome.get("sha") == sha and outcome.get("result") == "refused"):
            continue  # this exact version's program review failed, or the gate refused it: not even shadow
        t = _finite((state.get("validation_numbers") or {}).get("t"))
        roots = [str(r).upper() for r in loads(fam["roots"], []) or []]
        out.append({
            "family": fam["id"], "band": "gym", "observe": True, "tier": tiers[fam["id"]], "lineage": fam.get("lineage"),
            "structure": fam["structure"], "roots": roots, "needs_roots": list(_needs_roots(code, tuple(roots))),
            "holdout_passed": False, "validation_passed": False, "version": int(v["n"]), "code": code, "params": params,
            "run_sha": sha, "typical_max_loss_usd": None, "seed_era": True, "forward": None,
            "validated_version": _count(state.get("validation_version")), "validation_t": t,
            "best_train": _finite(fam.get("best_train")),
        })
    out.sort(key=priority)
    return out


__all__ = ["read", "observe", "priority", "practice_tier", "demoted", "LIVE_BANDS", "TIERS", "BUNDLE_TTL"]
