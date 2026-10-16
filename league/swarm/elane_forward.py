"""THE FORWARD SCREEN'S SEAT PATH (FWD1-R, the captain's A33), the swarm's half: BUILT AND OFF.

Owner: the FWD1-R build. The judge is an ops job (league/ops/forward_screen.py, rule league/ops/fwd1_rule.py); this
module never imports it and never opens a forward store (release E3's seal T1): it reads ONE file the job writes under
the state root, the permit file (`PERMITS`: lineage ids, a status word, a family id, a version, a run sha, a cell, a
checkpoint count, the lineage's FWD1_START date and the verdict's words; no t, no P&L and no figure of a program), as
the panel lane reads the twin marker. No generator reads anything of it: the family-state key it writes (`STATE_KEY`)
is sealed (league/swarm/elane_seal.py `SEALED_KEYS`).

THE SWITCH: `elane.fwd1.seats`, "off" (the code's default and policy.json's) or "on". WITH IT OFF NOTHING HERE ACTS:
`try_refused` refuses nothing and `step` moves nothing; the job still records its verdicts.

WITH IT ON:
1. NO SEALED TRY FOR A LINEAGE FWD1 JUDGES (`try_refused`, asked by league/swarm/elane.py `try_open`, so for the ETF
   lanes and the panel lane alike): a family whose lineage the permit file lists "pending", "pass" or "fail" takes no
   Validation try (its pre-check is a sealed look: FWD1-R's "a case-N lineage takes no sealed look afterwards"; and
   nothing judges a lineage after its FWD1 fail). A lineage FWD1 does not judge, or one it voided or found ineligible,
   keeps its sealed path. The file unreadable while the switch is on: every try of an equity family whose lineage
   cannot be read is refused (fail closed: the wall holds only if a judged lineage never looks).
   L5 (A48), AN INDEX LINEAGE KEEPS ITS S2 TRY UNTIL ITS FIRST FORWARD DAY CLOSES (`untried`): an index-only case-N
   lineage keeps its S2 try until the close of its FWD1_START session; the judge then voids it (A33 (4): a case-N
   lineage that reached a sealed pre-check after FWD1_START, league/ops/forward_screen.py `judge`). A loosening of
   A39's stated cost "while on, a lineage FWD1 lists takes no sealed S2 try". Why: an index family's v1 that failed
   Train is registered and sighted before its v2 passes (hours later, most index Train passes coming on v2 or later),
   and the listing would push it from S2 to FWD1-R's WEAK screen on a timing race, not on evidence. Before that close
   no forward day of the lineage can be counted (the forward night runs after the close), so it has seen nothing
   forward; the void leaves it one look. Only a row listed "pending", case "N", type "ETF" (`UNTRIED`), asked for THE
   ROW'S OWN FAMILY (the representative's: the judge's void reads the families of the lineage's registry rows, so a
   sibling family of the lineage the registry has not taken yet is refused), with its FWD1_START ("start", an ISO
   date of a session) STRICTLY AFTER the file's top-level "start" (the pin's first judged session: only then is the
   start the lineage's own first forward day; the pin in force starts 2026-10-16 and A39 turns the seats on Oct 21,
   so this costs nothing now), and a family that is not forward-only (`elane.forward_only` False: R-SEC refuses every
   other ETF family first, in `try_open`, and this asks again so the exemption cannot outlive R-SEC) and not a panel.
   FAIL CLOSED: no "start" (a file of the earlier job) or no pin start, a date that is not one, a day that is no
   session or that the calendar cannot answer, a clock or a family that cannot be read: refused as above. A pass or a
   fail is never exempt; nor is a lineage at or after that close.
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
     (branch feat/equity-e4-step2, B3). This module records the eligibility (`STATE_KEY`) and moves no panel band.
     RELEASE U wires the pool (league/swarm/elane_xs.py `forward_seats`, asked right after `step` in the same round):
     it asks `seat_refused` and calls `mark_seated` in the transaction that moves the band, into a free seat of the
     panel pool only; under A34 it is the one way a panel program takes a seat.
     ONLY CASE N (the captain's A34, 18:42Z Oct 14: "a panel program's only path to money is FWD1-R case N"): a
     panel pass of case XS1 is recorded by the job and never made eligible here. AT MOST ONE A MECHANISM CELL here
     too: a panel pass waits while another family of its cell holds the cell's forward eligibility or seat
     (`one_a_cell`), so even a pool that read `eligible(state)` alone could seat no second copy of a cell.
3. THE ONE CALL A SEAT POOL ASKS (`seat_refused`, for both types; the review's major): why a family may not take a
   forward seat NOW, or None. A pool that seats a family on a forward pass asks it first and, when it seats one,
   records it (`mark_seated`), so the cell's one live forward seat is counted for both types alike. THE OBLIGATION
   STEP TWO TAKES ON (league/xs/E4_INTERFACES.md; docs/operations.md): the panel pool seats a panel family on a
   forward pass only when `seat_refused(store, fam, settings)` is None, and calls `mark_seated(store, fid, settings)`
   in the same transaction as the band move; reading `eligible(state)` alone is not the contract.
   The verdict's words are kept beside it (`STATE_KEY`["words"]); the operator's sentence with the t and the shadow
   P&L stays in the job's own report.
4. POOL1's ROUTE REFUSAL (the owner's A55, pre-registered in A55a: PREREG-POOL1 sections 7.2 and 11 P1 item 4; its job
   league/ops/pool_screen.py, which this module never imports): the pooled screen's permit file (`POOL_PERMITS`: ids
   and words) lists the lineages on its POOL ROUTE and its HOLD list (`pool_lists`, `pool_listed`). Such a lineage
   TAKES NO FWD1-R SEAT (`step`'s ETF branch, before the band move, and `seat_refused` refuse it) AND NO SEALED TRY
   (`try_refused`, whatever `elane.fwd1.seats` says), WHATEVER `elane.pool.mode` SAYS: the refusal is keyed by lineage
   id, the list is append-only and copied whole into every file the job writes (never shorter than the file before
   it), and nothing lifts it under the receipt (mode off, seats off, a pooled FAIL, DEMOTED or VOID). A lineage on the
   POOL-ROUTE list is refused its sealed try OUTRIGHT; FWD1's own L5 (A48, 1 above) is kept for a HELD lineage only:
   an index-only case-N lineage the pool holds (not yet routed) keeps its S2 try until the close of its FWD1_START
   session (index lineages keep S2 unchanged, PREREG 7.2), and is then judged no further by FWD1. FAIL CLOSED: with
   the file missing while `elane.pool.mode` is not "off" (absent: the code's "off"), or unreadable at any time,
   `step` and `seat_refused` refuse EVERY ETF FWD1-R pass (FWD1 judges an ETF lineage in case N only, and any of them
   could be on the route list the file no longer shows) and `try_refused` refuses every lineage FWD1's permit file
   lists as judged (`JUDGED`), L5 included (the route list cannot be read, so no exemption is safe), and every equity
   try when that file cannot be read either. `one_a_cell` counts a pooled seat too (P2's `POOL_KEY` state: seated, in
   a live band, its FWD1 cell). These are tightenings (scratch/pooled-screen/DEVIATIONS.log P1 D10); with
   `elane.fwd1.seats` off `step` and `seat_refused` still do nothing else. A CODE ROLLBACK to a release before POOL1
   has no reader of this file and lifts the refusal: while the route list is non-empty it needs a captain amendment
   (docs/operations.md).

Standard library only.
"""

from __future__ import annotations

import datetime as dt
import json
import math
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
#: L5 (A48): the one permit row whose lineage keeps its S2 try until the close of its FWD1_START session (`untried`):
#: an index-only (R-SEC) ETF lineage of case N that FWD1 has not judged yet. Every key must match; nothing else is
#: (and only for the row's own family, with a start after the pin's).
UNTRIED = {"status": "pending", "case": "N", "type": "ETF"}
#: The bands a forward seat counts as live in (`one_a_cell`).
LIVE_BANDS = ("candidate", "probe", "sized")
REFUSED = "the FWD1-R forward screen judges this lineage: it takes no sealed look (FWD1-R, A33)"
UNREADABLE = "the FWD1-R permit file cannot be read while forward seats are on: no sealed try (fail closed)"
#: The cases a PANEL pass may take a seat on (the captain's A34: case N only).
PANEL_CASES = ("N",)
A34 = "A34: a panel program's only path to money is FWD1-R case N (this pass is case {case}): recorded, no seat"
#: POOL1 (A55a; the module docstring, 4): the pooled screen's permit file under the state root (league/ops/
#: pool_screen.py `PERMITS`; a test holds the two equal), its version, and `elane.pool.mode`'s words.
POOL_PERMITS = "pool-screen-permits.json"
POOL_PERMITS_VERSION = 1
POOL_MODES = ("off", "record")
#: P2's family-state key of a pooled seat (sealed from every generator: league/swarm/elane_seal.py `SEALED_KEYS`):
#: {"seated": True, "cluster": <pool cluster id>, "fwd1_cell": <its FWD1 cell text>}; `one_a_cell` counts it.
POOL_KEY = "elane_pool"
POOL_REFUSED = ("POOL1 (A55a): the pooled screen lists this lineage on its POOL route or hold list: it takes no FWD1-R "
                "seat and no sealed try under this receipt")
POOL_UNREADABLE = ("POOL1 (A55a): the pooled screen's permit file cannot be read: no ETF FWD1-R pass is seated and no "
                   "lineage FWD1 judges takes a sealed try (fail closed)")
POOL_MISSING = ("POOL1 (A55a): the pooled screen's permit file is missing while elane.pool.mode is on: no ETF FWD1-R "
                "pass is seated and no lineage FWD1 judges takes a sealed try (fail closed)")


def seats_on(settings: Mapping[str, Any] | None) -> bool:
    """`elane.fwd1.seats` is "on" (anything else, a missing block included, is off)."""
    raw = settings.get("elane") if isinstance(settings, Mapping) else None
    raw = raw.get("fwd1") if isinstance(raw, Mapping) else None
    return isinstance(raw, Mapping) and raw.get("seats") == "on"


def permit_file(root: str | Path) -> tuple[dict[str, Any], Any] | None:
    """ONE PARSE of the permit file: ({lineage: row}, its top-level "start", the pin's first judged session, as the
    file holds it); ({}, None) when there is no file yet (no lineage judged), None when it exists and cannot be read or
    is not the job's shape."""
    path = Path(root) / PERMITS
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, None
    except (OSError, ValueError):
        return None
    if not isinstance(doc, Mapping) or doc.get("version") != PERMITS_VERSION or not isinstance(doc.get("lineages"), Mapping):
        return None
    return {str(k): dict(v) for k, v in doc["lineages"].items() if isinstance(v, Mapping)}, doc.get("start")


def permits(root: str | Path) -> dict[str, Any] | None:
    """The permit file's lineages {lineage: row}, {} when there is no file yet (no lineage judged), None when it exists
    and cannot be read or is not the job's shape (`permit_file`'s first half)."""
    read = permit_file(root)
    return None if read is None else read[0]


def _day(value: Any) -> dt.date | None:
    """An ISO date in the job's own form ("YYYY-MM-DD"), else None (a looser form the parser takes is doubt)."""
    if not isinstance(value, str):
        return None
    try:
        day = dt.date.fromisoformat(value)
    except ValueError:
        return None
    return day if day.isoformat() == value else None


def lineage_of(store: Any, fam: Mapping[str, Any]) -> str | None:
    """A family's lineage as the forward registry keys it (league/ops/forward_register.py: `elane.lineage_key(lane,
    family.lineage or id)`), None for a family of no equity lane."""
    from . import elane, elane_seal

    lane = elane_seal.lane_of_spec(fam.get("spec"))
    if lane is None:
        return None
    return elane.lineage_key(lane, str(fam.get("lineage") or fam["id"]))


def untried(store: Any, fam: Mapping[str, Any], row: Mapping[str, Any] | None, *, pin_start: Any = None,
            now: float | None = None) -> bool:
    """L5 (A48; the module docstring, 1): whether the lineage of permit `row` keeps its S2 try all the same. Every one
    must hold:
    - the row is `UNTRIED` (pending, case N, ETF);
    - `fam` IS THE ROW'S FAMILY (the representative's, which has a registry row of the lineage: the judge's void reads
      the families of the lineage's registry rows, so a sibling family of the lineage the registry has not taken yet
      could look unseen; it is refused);
    - `fam` is index-only (`elane.forward_only` False) and no panel;
    - the row's "start" is STRICTLY AFTER `pin_start` (the file's top-level "start", the pin's first judged session):
      FWD1_START = max(first_day, the pin's start), and only a start after the pin's is the lineage's own first
      forward day; a lineage registered before the pin has forward days in the record already. The pin in force starts
      2026-10-16 and A39 turns the seats on Oct 21, after the close of any start this refuses for it, so this costs
      nothing now; it bites at a re-pin;
    - `now` (the store's clock when it has one, else the wall's) is before the close of that start's session
      (league/equity/schedule.py `moments(day).close_at`; before it no forward day of the lineage can be counted).
    FAIL CLOSED: False for anything that cannot be read (no "start" or no pin start, a date that is not one in the
    job's own form, no session, a calendar that raises or does not cover the day, a clock that is not finite)."""
    try:
        if not isinstance(row, Mapping) or any(row.get(key) != value for key, value in UNTRIED.items()):
            return False
        if not isinstance(fam, Mapping) or not fam.get("id") or str(row.get("family") or "") != str(fam["id"]):
            return False                          # a sibling of the lineage: the judge's void may not see it (F1)
        day, pin = _day(row.get("start")), _day(pin_start)
        if day is None or pin is None or not day > pin:
            return False                          # no own first forward day after the pin's start (F2)
        from . import elane, elane_xs

        if elane.forward_only(fam) is not False or elane_xs.is_panel(fam):
            return False                          # R-SEC (and A34) refuse it first; the exemption never outlives them
        from ..equity import schedule

        moments = schedule.moments(day)
        if moments is None:
            return False                          # not a session, or a day the calendar does not cover
        if now is None:
            clock = getattr(store, "clock", None)
            now = clock() if callable(clock) else time.time()
        t = float(now)
        return math.isfinite(t) and t < float(moments.close_at)
    except Exception:  # noqa: BLE001 - a doubt keeps the refusal
        return False


def pool_on(settings: Mapping[str, Any] | None) -> bool:
    """`elane.pool.mode` is not "off" (the module docstring, 4: the fail-closed reading of a missing file). An absent
    block or key is the code's default, "off"; any other value, a malformed one included, is not "off"."""
    raw = settings.get("elane") if isinstance(settings, Mapping) else None
    raw = raw.get("pool") if isinstance(raw, Mapping) else None
    if not isinstance(raw, Mapping) or "mode" not in raw:
        return False
    return raw.get("mode") != "off"


def pool_lists(root: str | Path, settings: Mapping[str, Any] | None
               ) -> tuple[frozenset[str] | None, frozenset[str] | None, str | None]:
    """THE POOLED SCREEN'S TWO LISTS (the module docstring, 4), read WHATEVER `elane.pool.mode` says: (the POOL-route
    list, the hold list, None); (frozenset(), frozenset(), None) when there is no file and the mode is "off"; (None,
    None, why) when the swarm must FAIL CLOSED: no file while the mode is not "off" (`pool_on`), or a file that cannot
    be read or is not the job's shape, at any time."""
    path = Path(root) / POOL_PERMITS
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return (None, None, POOL_MISSING) if pool_on(settings) else (frozenset(), frozenset(), None)
    except (OSError, ValueError):
        return None, None, POOL_UNREADABLE
    if not isinstance(doc, Mapping) or doc.get("version") != POOL_PERMITS_VERSION \
            or not isinstance(doc.get("routes"), Mapping) or not isinstance(doc.get("holds"), list):
        return None, None, POOL_UNREADABLE
    return frozenset(str(k) for k in doc["routes"]), frozenset(str(x) for x in doc["holds"]), None


def pool_listed(root: str | Path, settings: Mapping[str, Any] | None) -> tuple[frozenset[str] | None, str | None]:
    """THE POOLED SCREEN'S REFUSAL LIST (the module docstring, 4): (the lineages its permit file lists on the POOL route
    or the hold list, None), or (None, why) when the swarm must fail closed (`pool_lists`)."""
    routes, holds, why = pool_lists(root, settings)
    if routes is None or holds is None:
        return None, why
    return routes | holds, None


def _pool_try(store: Any, fam: Mapping[str, Any], lineage: str, settings: Mapping[str, Any] | None,
              now: float | None) -> str | None:
    """POOL1's half of `try_refused` (the module docstring, 4), whatever `elane.fwd1.seats` says: a lineage on the
    POOL-route list takes no sealed try, OUTRIGHT; a HELD lineage takes none either but for L5 (an index lineage before
    the close of its FWD1_START session: `untried`); with the pool's file failing closed, no lineage FWD1's permit file
    lists as judged does (L5 included), and no equity family's at all while FWD1's file cannot be read either."""
    routes, holds, why = pool_lists(store.root, settings)
    if routes is not None and holds is not None:
        if lineage in routes:
            return POOL_REFUSED
        if lineage not in holds:
            return None
        read = permit_file(store.root)
        if read is None:
            return POOL_REFUSED
        rows, pin_start = read
        row = rows.get(lineage)
        return None if row is not None and untried(store, fam, row, pin_start=pin_start, now=now) else POOL_REFUSED
    read = permit_file(store.root)
    if read is None:
        return why
    rows, _ = read
    row = rows.get(lineage)
    if row is not None and row.get("status") in JUDGED:
        return why
    return None


def try_refused(store: Any, fam: Mapping[str, Any], settings: Mapping[str, Any] | None, *,
                now: float | None = None) -> str | None:
    """Why this family's lineage takes no sealed Validation try (the module docstring, 1 and 4), or None. POOL1 first,
    whatever `elane.fwd1.seats` says (`_pool_try`). Then, with the seats on, a lineage listed "pending", "pass" or
    "fail" is refused unless `untried` holds for it at `now` (L5, A48: the representative's own index-only family of a
    case-N lineage whose start is after the pin's, before the close of its FWD1_START session; the store's clock when
    `now` is None). The file is read once (`permit_file`)."""
    lineage = lineage_of(store, fam)
    if lineage is None:
        return None
    pooled = _pool_try(store, fam, lineage, settings, now)
    if pooled is not None:
        return pooled
    if not seats_on(settings):
        return None
    read = permit_file(store.root)
    if read is None:
        return UNREADABLE
    rows, pin_start = read
    row = rows.get(lineage)
    if row is not None and row.get("status") in JUDGED:
        return None if untried(store, fam, row, pin_start=pin_start, now=now) else REFUSED
    return None


def eligible(state: Mapping[str, Any] | None) -> bool:
    """Whether a family's state holds a forward pass made eligible here (an ETF family: it was made a Candidate by this
    path; a panel family: it may be seated by the pool, which asks `seat_refused` first: this flag alone is not the
    contract)."""
    held = state.get(STATE_KEY) if isinstance(state, Mapping) else None
    return isinstance(held, Mapping) and held.get("eligible") is True


def one_a_cell(store: Any, cell: str, *, but: str) -> str | None:
    """THE CELL'S ONE LIVE FORWARD SEAT: the family (other than `but`), of either type, alive, whose forward pass in
    `cell` holds it: one seated on its pass (made a Candidate here, or recorded by a pool's `mark_seated`) that is still
    in a live band, or one made eligible here and not yet seated (a panel pass waiting for the pool's seat); None when
    the cell is free. A seated family that left the live bands (demoted, exited) frees it, as a retired one does.
    POOL1 (the module docstring, 4): a family seated on a pooled pass (P2's `POOL_KEY` state, seated, its FWD1 cell
    `fwd1_cell`) in a live band holds its FWD1 cell's seat too."""
    from . import elane

    for fam in store.families(alive=True, lanes=elane.LANES):
        if str(fam["id"]) == str(but) or fam.get("retired_at"):
            continue
        pooled = (fam.get("state") or {}).get(POOL_KEY)
        if isinstance(pooled, Mapping) and pooled.get("seated") is True and pooled.get("fwd1_cell") == cell \
                and fam.get("band") in LIVE_BANDS:
            return str(fam["id"])
        held = (fam.get("state") or {}).get(STATE_KEY)
        if not isinstance(held, Mapping) or held.get("cell") != cell or held.get("eligible") is not True:
            continue
        if held.get("seated") is True and fam.get("band") not in LIVE_BANDS:
            continue
        return str(fam["id"])
    return None


def seat_refused(store: Any, fam: Mapping[str, Any] | None, settings: Mapping[str, Any] | None) -> str | None:
    """THE ONE CALL A SEAT POOL ASKS (the module docstring, 3), for an ETF and a panel family alike: why `fam` may not
    take a seat on its forward pass now, or None. Refused: the seat switch off; no eligible forward pass in its state;
    a panel pass of a case other than N (A34); the permit file unreadable, or no longer listing its lineage as a pass
    of this version and run sha; the version's run sha not the judged one; another family holding the mechanism
    cell's one live forward seat (`one_a_cell`); POOL1 (the module docstring, 4): its lineage on the pooled screen's
    POOL route or hold list, whatever `elane.pool.mode` says, or, failing closed on that file, any ETF pass."""
    if not seats_on(settings):
        return "the forward seats are off (elane.fwd1.seats)"
    if not isinstance(fam, Mapping) or fam.get("retired_at"):
        return "no such family alive"
    held = (fam.get("state") or {}).get(STATE_KEY)
    if not eligible(fam.get("state")) or not isinstance(held, Mapping):
        return "no forward pass is eligible in its state"
    listed, pool_why = pool_listed(store.root, settings)
    if listed is None:
        if held.get("type") != "PANEL":
            return pool_why                       # failing closed: every ETF FWD1-R pass (all are case N)
    elif str(held.get("lineage") or "") in listed:
        return POOL_REFUSED
    if held.get("type") == "PANEL" and held.get("case") not in PANEL_CASES:
        return A34.format(case=held.get("case"))
    rows = permits(store.root)
    if rows is None:
        return UNREADABLE
    row = rows.get(str(held.get("lineage") or ""))
    if row is None or row.get("status") != "pass" or str(row.get("family") or "") != str(fam["id"]) or \
            row.get("run_sha") != held.get("run_sha"):
        return "the permit file does not list this family's forward pass"
    from .gate import run_sha

    version = store.version(fam["id"], held.get("version"))
    if version is None or run_sha(version) != held.get("run_sha"):
        return "the version's run sha is not the judged one"
    other = one_a_cell(store, str(held.get("cell") or ""), but=str(fam["id"]))
    if other is not None:
        return f"one live forward seat a mechanism cell: {other} holds {held.get('cell')}'s"
    return None


def mark_seated(store: Any, fid: str, settings: Mapping[str, Any] | None) -> bool:
    """A SEAT POOL'S RECORD (the module docstring, 3): the family `fid` was seated on its forward pass (a panel pool
    calls it in the transaction that moves its band). Written only when `seat_refused` is None; whether it was."""
    fam = store.family(fid)
    if seat_refused(store, fam, settings) is not None:
        return False
    held = dict((fam.get("state") or {}).get(STATE_KEY) or {})
    store.set_state(fid, **{STATE_KEY: {**held, "seated": True}})
    store.event("swarm.gate", fid, {"action": "forward_seat", "version": held.get("version"), "screen": "FWD1-R",
                                    "case": held.get("case"), "cell": held.get("cell"), "lane": held.get("type")})
    return True


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
    listed, pool_why = pool_listed(store.root, gate.settings)
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
                # ELIGIBLE ONLY: the panel seat pool is E4 step two's (B3); no panel band moves here. Case N only
                # (A34), and one a mechanism cell (a second copy of a cell waits while the first holds it).
                if row.get("case") not in PANEL_CASES:
                    out["waits"][fid] = A34.format(case=row.get("case"))
                    continue
                other = one_a_cell(store, cell, but=fid)
                if other is not None:
                    out["waits"][fid] = f"one live forward seat a mechanism cell: {other} holds {cell}'s"
                    continue
                store.set_state(fid, **{STATE_KEY: {**held, "seated": False}})
                store.event("swarm.gate", fid, {"action": "forward_eligible", "version": held["version"],
                                                "lane": row.get("type"), "screen": "FWD1-R"})
                out["eligible"].append(fid)
                continue
            # POOL1 (the module docstring, 4): no FWD1-R seat for a lineage the pooled screen lists, whatever
            # elane.pool.mode says; failing closed on its file, no ETF pass at all (every one is case N)
            if listed is None:
                out["waits"][fid] = str(pool_why)
                continue
            if listed is not None and lineage in listed:
                out["waits"][fid] = POOL_REFUSED
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


__all__ = ["PERMITS", "PERMITS_VERSION", "STATE_KEY", "SEATS", "JUDGED", "UNTRIED", "LIVE_BANDS", "REFUSED",
           "UNREADABLE", "PANEL_CASES", "A34", "POOL_PERMITS", "POOL_PERMITS_VERSION", "POOL_MODES", "POOL_KEY",
           "POOL_REFUSED", "POOL_UNREADABLE", "POOL_MISSING", "seats_on", "permit_file", "permits", "lineage_of",
           "untried", "pool_on", "pool_lists", "pool_listed", "try_refused", "eligible", "one_a_cell", "seat_refused", "mark_seated",
           "step"]
