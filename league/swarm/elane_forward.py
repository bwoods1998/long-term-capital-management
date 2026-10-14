"""THE FORWARD SCREEN'S SEAT PATH (FWD1-R, the captain's A33), the swarm's half: BUILT AND OFF.

Owner: the FWD1-R build. The judge is an ops job (league/ops/forward_screen.py, rule league/ops/fwd1_rule.py); this
module never imports it and never opens a forward store (release E3's seal T1): it reads ONE file the job writes under
the state root, the permit file (`PERMITS`: lineage ids, a status word, a family id, a version, a run sha, a cell, a
checkpoint count and the verdict's words; no t, no P&L and no figure of a program), as the panel lane reads the twin
marker. No generator reads anything of it: the family-state key it writes (`STATE_KEY`) is sealed
(league/swarm/elane_seal.py `SEALED_KEYS`).

THE SWITCH: `elane.fwd1.seats`, "off" (the code's default and policy.json's) or "on". WITH IT OFF NOTHING HERE ACTS:
`try_refused` refuses nothing and `step` moves nothing; the job still records its verdicts.

WITH IT ON:
1. NO SEALED TRY FOR A LINEAGE FWD1 JUDGES (`try_refused`, asked by league/swarm/elane.py `try_open`, so for the ETF
   lanes and the panel lane alike): a family whose lineage the permit file lists "pending", "pass" or "fail" takes no
   Validation try (its pre-check is a sealed look: FWD1-R's "a case-N lineage takes no sealed look afterwards"; and
   nothing judges a lineage after its FWD1 fail). A lineage FWD1 does not judge, or one it voided or found ineligible,
   keeps its sealed path. The file unreadable while the switch is on: every try of an equity family whose lineage
   cannot be read is refused (fail closed: the wall holds only if a judged lineage never looks).
2. THE SEAT (`step`, called once a round by league/swarm/gate.py `equity_round`): a lineage the file lists "pass"
   becomes eligible THROUGH THE LANE'S OWN SEAT MACHINERY, never around it:
   - an ETF lineage: its family, alive in the Gym band and holding the permitted version (the run sha the job judged)
     under the equity identity the verdict was read under, is made a Candidate (`banded_*` as a passed look makes it,
     with the band proof of the identity in force); the roster (league/swarm/bands.py `equity_seating`, the seat rule
     in force: league/equity/bands.py) then seats it or keeps it waiting, sizes it by the Probe money rows and demotes
     it by them. AT MOST ONE LIVE FORWARD SEAT A MECHANISM CELL: a pass waits while another family made a Candidate by
     this path in the same cell is a Candidate, at Probe or Sized and alive (the review's F5: the seat goes to one copy
     of a cell, not to the luckiest of many);
   - a PANEL lineage: ELIGIBLE ONLY. No panel seat exists in E4's step one; the panel seat pool is step two's
     (branch feat/equity-e4-step2, B3), which reads `eligible(state)` for a panel family. This module records the
     eligibility (`STATE_KEY`) and moves no panel band.
   The verdict's words are kept beside it (`STATE_KEY`["words"]); the operator's sentence with the t and the shadow
   P&L stays in the job's own report.

Standard library only.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping

#: The permit file under the state root (league/ops/forward_screen.py `PERMITS`; a test holds the two equal).
PERMITS = "forward-screen-permits.json"
PERMITS_VERSION = 1
#: The family-state key of a forward pass (sealed from every generator: league/swarm/elane_seal.py `SEALED_KEYS`).
STATE_KEY = "elane_forward"
SEATS = ("off", "on")
#: The statuses whose lineage takes no sealed Validation try while the switch is on.
JUDGED = ("pending", "pass", "fail")
#: The bands a forward seat counts as live in (`one_a_cell`).
LIVE_BANDS = ("candidate", "probe", "sized")
REFUSED = "the FWD1-R forward screen judges this lineage: it takes no sealed look (FWD1-R, A33)"
UNREADABLE = "the FWD1-R permit file cannot be read while forward seats are on: no sealed try (fail closed)"


def seats_on(settings: Mapping[str, Any] | None) -> bool:
    """`elane.fwd1.seats` is "on" (anything else, a missing block included, is off)."""
    raw = settings.get("elane") if isinstance(settings, Mapping) else None
    raw = raw.get("fwd1") if isinstance(raw, Mapping) else None
    return isinstance(raw, Mapping) and raw.get("seats") == "on"


def permits(root: str | Path) -> dict[str, Any] | None:
    """The permit file's lineages {lineage: row}, {} when there is no file yet (no lineage judged), None when it exists
    and cannot be read or is not the job's shape."""
    path = Path(root) / PERMITS
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return None
    if not isinstance(doc, Mapping) or doc.get("version") != PERMITS_VERSION or not isinstance(doc.get("lineages"), Mapping):
        return None
    return {str(k): dict(v) for k, v in doc["lineages"].items() if isinstance(v, Mapping)}


def lineage_of(store: Any, fam: Mapping[str, Any]) -> str | None:
    """A family's lineage as the forward registry keys it (league/ops/forward_register.py: `elane.lineage_key(lane,
    family.lineage or id)`), None for a family of no equity lane."""
    from . import elane, elane_seal

    lane = elane_seal.lane_of_spec(fam.get("spec"))
    if lane is None:
        return None
    return elane.lineage_key(lane, str(fam.get("lineage") or fam["id"]))


def try_refused(store: Any, fam: Mapping[str, Any], settings: Mapping[str, Any] | None) -> str | None:
    """Why this family's lineage takes no sealed Validation try (the module docstring, 1), or None."""
    if not seats_on(settings):
        return None
    lineage = lineage_of(store, fam)
    if lineage is None:
        return None
    rows = permits(store.root)
    if rows is None:
        return UNREADABLE
    row = rows.get(lineage)
    if row is not None and row.get("status") in JUDGED:
        return REFUSED
    return None


def eligible(state: Mapping[str, Any] | None) -> bool:
    """Whether a family's state holds a forward pass made eligible here (a panel family: what step two's seat pool
    reads; an ETF family: it was made a Candidate by this path)."""
    held = state.get(STATE_KEY) if isinstance(state, Mapping) else None
    return isinstance(held, Mapping) and held.get("eligible") is True


def one_a_cell(store: Any, cell: str, *, but: str) -> str | None:
    """THE CELL'S ONE LIVE FORWARD SEAT: the family (other than `but`) made a Candidate by this path in `cell` that is
    still alive in a live band, or None."""
    from . import elane

    for fam in store.families(alive=True, lanes=elane.LANES):
        if str(fam["id"]) == str(but) or fam.get("band") not in LIVE_BANDS:
            continue
        held = (fam.get("state") or {}).get(STATE_KEY)
        if isinstance(held, Mapping) and held.get("seated") is True and held.get("cell") == cell:
            return str(fam["id"])
    return None


def _proof(row: Mapping[str, Any], sha: str) -> dict[str, Any] | None:
    """The band proof of an ETF pass (league/swarm/elane.py `look`'s), or None when the equity identity in force is not
    the one the verdict was read under (the permit's `engine`: the forward record's engine label)."""
    from ..equity import EQUITY_ENGINE_VERSION
    from .evaluator import equity_fingerprint

    fingerprint = equity_fingerprint()
    engine = str(row.get("engine") or "")
    if engine and engine.split("+")[:2] != [EQUITY_ENGINE_VERSION, fingerprint[:12]]:
        return None
    return {"engine": EQUITY_ENGINE_VERSION, "equity_sha256": fingerprint, "run_sha": sha}


def step(gate: Any) -> dict[str, Any]:
    """THE SEAT PATH's round (the module docstring, 2): {"seated": [family], "eligible": [panel family], "waits":
    {family: why}}; {} with the switch off. One family's failure never stops the others."""
    if not seats_on(gate.settings):
        return {}
    from .gate import run_sha

    store = gate.store
    rows = permits(store.root)
    out: dict[str, Any] = {"seated": [], "eligible": [], "waits": {}}
    if not rows:
        return out
    for lineage, row in sorted(rows.items()):
        if row.get("status") != "pass":
            continue
        fid = str(row.get("family") or "")
        try:
            fam = store.family(fid)
            if fam is None or fam.get("retired_at"):
                continue
            state = fam.get("state") or {}
            if eligible(state):
                continue
            if lineage_of(store, fam) != lineage:
                out["waits"][fid] = "the family is not the permitted lineage's"
                continue
            version = store.version(fid, row.get("version"))
            if version is None or not version.get("code"):
                out["waits"][fid] = "the permitted version cannot be read"
                continue
            sha = run_sha(version)
            if sha != row.get("run_sha"):
                out["waits"][fid] = "the version's run sha is not the judged one"
                continue
            cell = str(row.get("cell") or "")
            held = {"eligible": True, "lineage": lineage, "version": int(version["n"]), "run_sha": sha, "cell": cell,
                    "type": row.get("type"), "case": row.get("case"), "k": row.get("k"), "weak": row.get("weak"),
                    "words": row.get("words"), "at": gate.clock() if hasattr(gate, "clock") else time.time()}
            if row.get("type") == "PANEL":
                # ELIGIBLE ONLY: the panel seat pool is E4 step two's (B3); no panel band moves here.
                store.set_state(fid, **{STATE_KEY: {**held, "seated": False}})
                store.event("swarm.gate", fid, {"action": "forward_eligible", "version": held["version"],
                                                "lane": row.get("type"), "screen": "FWD1-R"})
                out["eligible"].append(fid)
                continue
            if fam.get("band") != "gym" or state.get("gate_hold"):
                out["waits"][fid] = f"in the {fam.get('band')} band" if fam.get("band") != "gym" else "held by the operator"
                continue
            other = one_a_cell(store, cell, but=fid)
            if other is not None:
                out["waits"][fid] = f"one live forward seat a mechanism cell: {other} holds {cell}'s"
                continue
            proof = _proof(row, sha)
            if proof is None:
                out["waits"][fid] = "the equity identity moved after the verdict was read"
                continue
            with store.atomic():
                store.set_state(fid, banded_version=int(version["n"]), banded_sha=version.get("sha"),
                                banded_at=gate.clock(), banded_evaluator=proof, **{STATE_KEY: {**held, "seated": True}})
                store.set_band(fid, "candidate", reason=f"passed the FWD1-R forward screen ({row.get('type')}, case "
                                                        f"{row.get('case')}){', WEAK' if row.get('weak') else ''}")
            store.event("swarm.gate", fid, {"action": "forward_seat", "version": int(version["n"]), "screen": "FWD1-R",
                                            "case": row.get("case"), "cell": cell})
            out["seated"].append(fid)
        except Exception as exc:  # noqa: BLE001 - the next pass is asked; nothing was half-written (one atomic)
            out["waits"][fid or lineage] = f"could not be read ({type(exc).__name__})"
    return out


__all__ = ["PERMITS", "PERMITS_VERSION", "STATE_KEY", "SEATS", "JUDGED", "LIVE_BANDS", "REFUSED", "UNREADABLE",
           "seats_on", "permits", "lineage_of", "try_refused", "eligible", "one_a_cell", "step"]
