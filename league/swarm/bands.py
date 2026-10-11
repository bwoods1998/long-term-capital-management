"""What the live path reads of the swarm: the families it may run, with their programs.

    from league.swarm import bands
    rows = bands.read(root)        # never raises, never waits more than a second ([] when it cannot read)

One row per family the live path may run: every family in the Candidate, Probe or Sized band (but a Candidate
waiting for a seat while THE PROBE ROSTER, `dlane.roster`, is on: `seating`), and every
family in the Gym band whose validated version met the validation line AND passed the gate's review and audit,
and whose holdout look (or forward record) has not failed, was not refused and was not held (THE LOOK HOLDS, Oct 2,
2026: a held look ends the version's tuition as a failed one does) (execution tuition: 1-lot real orders that measure
multi-leg fills and are never evidence). Each row:

    family                the family's id
    band                  gym | candidate | probe | sized
    structure, roots      its DECLARED structure type and roots (`long_single` too: the live path reads it through
                          `league.live.money.order_types`, real only while both singles are real types)
    holdout_passed        it passed its holdout look (Candidate or better)
    validation_passed     its validated version met the validation line
    version, code, params, run_sha
                          the program the row stands for: the version that holds the band (holdout passed),
                          else the version that met the validation line
    typical_max_loss_usd  the median maximum loss of ONE structure in that version's validation run (None when
                          it opened none; a `long_single`'s calls and puts together): the Probe fit only, since each
                          real order is sized by its own unit
    seed_era              the program was written by a model that knows 2024-2026 (every program in this swarm
                          is): it needs a forward record before it is Sized
    forward               its forward record (nightly + shadow + real): trades, wins, pnl_usd, mean_rom, lcb80,
                          negative (>= 20 trades and P&L below zero)
    version_created_at    when that version was written (UTC ISO): a Sized move counts only the forward record of
                          sessions after it (the forward embargo, Sept 29, 2026; `league/live/step.py` `_move_band`)
    version_selected_at   when the gate selected the banded version (UTC epoch); fresh forward also starts after this
                          so practice cannot select an old version and reuse its selection period as evaluation

THE PRACTICE LEAGUE (the observe band: the sprint, B4, Sept 26, 2026; the Train tier Sept 29, 2026): `observe(root)` ->
one SHADOW-ONLY row per alive Gym-band family that has a version to practise, in one of two tiers:

- "validated": its state's `validation_version` (the current best version the tournament validated), with an actual
  successful replay on the current image and bundle, whatever the validation line said;
- "train": no validated version, but an ELIGIBLE TRAIN VERSION: the version the tournament validates next
  (`Tournament.candidate_version`: the submitted best, else the best by Train score) that was not demoted (a loss at 1.5x,
  `robust_failed`, or a failed drift screen, `drift_failed`; a demotion also clears the best, so this is a belt), backed
  by an eligible Train replay or completed Validation replay on the current image and bundle.

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

THE INCUBATOR'S FACTS (release B, Oct 1, 2026; `league/live/incubator.py`): `incubator(root, family=f, version=n)` -> one
row, or [], saying whether version `n` of `f` may trade the incubator route (one lot of real money after positive live
practice; never evidence, never a promotion): `f` is alive and in the Gym band, `n` was not demoted (1.5x or drift),
`n` carries a Train-and-drift pass (`state.train_passed[str(n)]`) made under the CURRENT research evaluator and Train
objective (the store's `research_evaluator` and `train_objective`, both known: adoption clears alive families only, so a
retired and revived family's stale mark never passes) and showing a positive 1.5x Train P&L and the drift screen's
figures, the family is not on D2's route (no validated version that met the validation line: its tuition row comes
first, even when `read` cannot be read), the gate's review AND audit passed on `n`'s run sha under the current review
contract (`state.review`, or `state.incubator_reviews[sha]`), and the gate did not refuse, fail, demote or hold that
sha (`BAD_OUTCOMES`). A DIRECTION mark (release D-1, Oct 9, 2026: `lane` "direction", made by the lane's bar in place
of the drift screen alone, `incubator._direction_mark`) is accepted only while the direction lane takes marks
(`_lane_marks_open`: its effective mode "gate", so not in "shadow", not while K5 holds, not while the lane is off).
THE READER'S BELT (`incubator_refusal`; Oct 1, 2026, the owner's term that a program whose review or audit failed never
trades the incubator) comes first and does not rely on the mark: no row for a program the swarm barred
(`incubator_barred`, kept for good), one the gate's `review` names without a readable pass and passed audit, one whose
incubator review or audit failed, a version the gate refused at any stage (its `refusals` rows), a program whose holdout
look failed (its `looks` rows), or a family whose records cannot be read (fail-closed). The row carries no program:
{family, version, run_sha, structure, roots, band "gym", incubator True, observe False, holdout_passed False,
validation_passed False}; the live path trades the practice cohort's own snapshot and requires
its run sha to be this row's. `read` never returns it. Unlike `read`, an unreadable store RAISES (`sqlite3.Error`): the
live path then takes no new incubator pin and refuses incubator opens; exits are unaffected.

THE EQUITY LANES (release E1, Oct 2026; league/swarm/elane.py; league/equity/INTERFACES.md section 8.3). Every reader
here is the options lanes' unless asked otherwise: `read(root)`, `observe` and `incubator` never return an equity-lane
family (one whose structure is "etf" or "stock": `store.EQUITY_STRUCTURES`), so no OptionsLive instance, observe row
or incubator row is ever made of one, and THE PROBE ROSTER's seats (`dlane.roster`) are the options lanes' alone.
`read(root, lanes=LANES)` is the EquityBook's reader (league/equity/families.py): one row per equity-lane family in the
Candidate, Probe or Sized band whose banded version's proof is the CURRENT equity identity (`banded_evaluator`
{"engine": `league.equity.EQUITY_ENGINE_VERSION`, "equity_sha256": `evaluator.equity_fingerprint()`, "run_sha"}, read
once per `BUNDLE_TTL` a process; unreadable: no row), with the options row's keys plus `lane`, `label` ("MARKET BETA" |
"EQUITY"), `symbols`, `seeded` (one of the three captain-seeded programs, A4), `seat` ("probe" | "seated" | "sized"),
`validation_version`, `validation_r_sd_by_version` (EDM1's sigma by version), `beside` (the screen's line stated beside
every live trade) and `forward`. THE EQUITY ROSTER (`elane.roster`, `elane.roster_seats`, failing closed): its own seats,
apart from `dlane.roster`: a Probe family holds one, the Candidates queue for the rest by `banded_at` (`seating` with
`equity_seatable`), and a Candidate waiting for a seat has no row; unlike the options roster, 0 seats no equity program
at all. `read(root, lanes="all")` is both. `roster(root, lanes=LANES)` is the equity roster for reports.
`read(root, lanes=LANES, strict=True)` (the EquityBook's reader asks so) RAISES `EquityUnreadable` where the plain read
answers [] for a store it could not read (no store, a read that failed within its second, no equity identity): the book
must tell "no equity row" from "could not read", because it retires an instance whose family is gone and a retirement
sells its lots (A8.5; league/equity/live.py `_sync_instances`).

THE PANEL (release E4; league/swarm/elane_xs.py). A family of structure "panel" is an equity-lane family (every scope
here reads `store.EQUITY_STRUCTURES`), and its band proof binds to ITS OWN identity: `banded_evaluator` {"engine":
`league.xs.XS_ENGINE_VERSION`, "xs_sha256": `league.xs.identity.xs_fingerprint()`, "run_sha"}, checked against the
fingerprint of the RUNNING release's files (`_xs_sha`, `current_xs_evaluator`), never against the store's kv
`xs_evaluator`. No panel row is returned when that fingerprint cannot be computed (`strict`: `EquityUnreadable` while
a panel family is in a running band), and `equity_proof_current` judges a proof by the engine it names. A panel
Candidate is seatable only while the panel lane's effective mode is "live" (`elane_xs.seatable(root)`, handed to
`equity_seating`); its row's `beside` is XS1's sentence, stated beside every live panel trade. A SEATED PANEL FAMILY
HAS A ROW ONLY WHILE THE LANE IS LIVE TOO (`_read_equity`): at Probe or Sized with the lane's mode put down, or a leg
of `elane_xs.live_ready` failed (the nightly I6, the twin marker, the universe), it has no row, so the book opens
nothing for it, and `equity_seat_withdrawn` is the store's word the book retires its instance on (its lots exit at the
next open by E1's rule; a lane that cannot be READ retires nothing). Its band in the store is not moved: when the lane
is live again its row is back and the same instance runs again.

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

import calendar
import functools
import gzip
import json
import math
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import DB_NAME, settings
from .store import EQUITY_LANES, EQUITY_ONLY_SQL, EQUITY_STRUCTURES, OPTIONS_ONLY_SQL, lane_of_spec, loads

LIVE_BANDS = ("candidate", "probe", "sized")
#: The gate's outcomes (`gate_outcome.result` naming the program) that end its execution tuition (`read`) and refuse it
#: the incubator (`program_refusal`; `incubator.BAD_OUTCOMES` is this tuple): refused, failed (its holdout look), demoted,
#: and held (THE LOOK HOLDS, Oct 2, 2026: the owner approved them as a tightening, so a held look stops every real order
#: the look it replaces would have stopped, at whatever stage the hold lands, a passed review and audit included).
BAD_OUTCOMES = ("refused", "failed", "demoted", "held")
#: Seconds a process reuses the Gym bundle's version (`_bundle`).
BUNDLE_TTL = 300.0
_bundle_cache: tuple[float, str] | None = None
_bundle_lock = threading.Lock()


def current_banded_evaluator(state: dict[str, Any], sha: str) -> bool:
    """A band label alone cannot carry old PARAMS semantics into current execution.

    Pin execution source and engine/parameter versions as well as the exact program. A doc-only bundle change
    does not erase a genuine forward band; an engine semantic change requires new qualification.
    """
    from ..gym import ENGINE_VERSION
    from ..gym.experiment import CONTRACT_VERSION
    from .evaluator import execution_fingerprint

    proof = state.get("banded_evaluator") or {}
    return (proof.get("engine") == ENGINE_VERSION and proof.get("parameter_contract") == CONTRACT_VERSION and
            proof.get("execution_sha256") == execution_fingerprint() and
            proof.get("run_sha") == sha and bool(proof.get("holdout_bundle")) and
            str(proof["holdout_bundle"]).startswith(ENGINE_VERSION + "-") and
            proof.get("validation_bundle") == proof.get("holdout_bundle"))


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


def _families(db: sqlite3.Connection, family: str | None, *, gym_only: bool = False,
              equity: bool = False) -> list[dict[str, Any]]:
    """The living families (the Gym band's alone with `gym_only`; one with `family`): the options lanes' by default, the
    equity lanes' alone with `equity` (THE EQUITY LANES: no options reader here ever sees an equity family)."""
    where = "retired_at IS NULL" + (" AND band='gym'" if gym_only else "") + (" AND id=?" if family is not None else "")
    where += f" AND {EQUITY_ONLY_SQL}" if equity else f" AND {OPTIONS_ONLY_SQL}"
    return [dict(r) for r in db.execute(f"SELECT id, band, band_since, structure, roots, state, lineage, best_version, "
                                        f"best_train, spec, born_at FROM families WHERE {where} ORDER BY id",
                                        (() if family is None else (str(family),)))]


#: Seconds after a family became a Candidate (`banded_at`) within which its band's last move is that promotion: a later
#: move into the Candidate band is a demotion from Probe (the money table's, DM1's), and the family queues behind every
#: fresh Candidate (`seating`).
ROSTER_SLACK_S = 300.0
#: `_roster_seats` when `dlane.roster` is present but unreadable and this process never read a good value: no NEW seat.
ROSTER_CLOSED = -1
#: The last good `dlane.roster` this process read, by state root (`_roster_seats`).
_roster_good: dict[str, int] = {}
_roster_lock = threading.Lock()
_real_table: Any = None


def _epoch(text: Any) -> float | None:
    """`store.iso`'s text (UTC, whole seconds) as epoch seconds, else None."""
    try:
        return float(calendar.timegm(time.strptime(str(text), "%Y-%m-%dT%H:%M:%SZ")))
    except (TypeError, ValueError, OverflowError):
        return None


def _seat_structure(structure: Any) -> bool:
    """Whether a Candidate of this declared structure could reach Probe with real money: every order type it may send is
    one of the money table's real types (`league.live.money.Table.family_real`, read, never edited). A structure that
    cannot (credit types under the credit equity, types shadow-only until a paper round trip) takes no roster seat."""
    global _real_table
    try:
        if _real_table is None:
            from ..live.money import Table

            _real_table = Table.from_constitution()
        return bool(_real_table.family_real(str(structure or "")))
    except Exception:  # noqa: BLE001 - an unreadable table: the family queues (it can only wait, never trade past the roster)
        return True


def seating(fams: Sequence[Mapping[str, Any]], seats: int, *,
            seatable: Any = None) -> dict[str, list[str]]:
    """THE PROBE ROSTER (REDESIGN-1010, Oct 10, 2026; `dlane.roster`): who holds the Probe band's seats. Pure but for the
    money table's real types (`_seat_structure`). `fams`: the alive Candidate and Probe families (id, band, band_since,
    structure, state as a dict); `seats`: the roster (0 = none, `ROSTER_CLOSED` = no new seat). Returns {probe, seated,
    waiting, seatless}: `waiting` gets no `read` row.

    Why: the Probe budget is one envelope for every program, and Done needs >= 5 real closes from each of >= 2 programs.
    With no roster, every program that passes its look trades at once and the shared budget spreads one or two closes
    over each of many programs, so the clause fails even for a real edge (the operator's private simulation,
    REDESIGN-1010). A roster seats a few programs, which then earn the closes that can show an edge; the others wait.

    The rule:
    - every Probe family holds a seat and is never hidden (a Sized family is not an input: it neither holds nor waits);
    - SEATLESS and shown as before: a Candidate whose structure cannot trade real money (`_seat_structure`), or with no
      readable `state.banded_at`;
    - the other Candidates QUEUE: first the fresh ones (never at Probe since `banded_at`), by `banded_at` then id; then
      the ones that came back from Probe (their band moved more than `ROSTER_SLACK_S` after `banded_at`: a demotion), by
      that move's time then id. The first `seats - Probe` of the queue hold a seat (shown); the rest WAIT (no row), so a
      demoted family can come back to Probe only into a free seat.
    With `seats` 0 nothing waits. `seatable` (THE EQUITY LANES: `equity_seatable`): whether a Candidate's structure can
    hold a seat, in place of `_seat_structure`."""
    fits = _seat_structure if seatable is None else seatable
    probe = sorted(str(f["id"]) for f in fams if f.get("band") == "probe")
    if seats == 0:
        return {"probe": probe, "seated": [], "waiting": [], "seatless": []}
    fresh: list[tuple[float, str]] = []
    back: list[tuple[float, str]] = []
    seatless: list[str] = []
    for fam in fams:
        if fam.get("band") != "candidate":
            continue
        fid = str(fam["id"])
        state = fam.get("state") if isinstance(fam.get("state"), Mapping) else {}
        at = _finite(state.get("banded_at"))
        if at is None or not fits(fam.get("structure")):
            seatless.append(fid)
            continue
        since = _epoch(fam.get("band_since"))
        if since is not None and since > at + ROSTER_SLACK_S:
            back.append((since, fid))
        else:
            fresh.append((at, fid))
    queue = [fid for _, fid in sorted(fresh)] + [fid for _, fid in sorted(back)]
    free = 0 if seats < 0 else max(0, int(seats) - len(probe))
    return {"probe": probe, "seated": queue[:free], "waiting": sorted(queue[free:]), "seatless": sorted(seatless)}


def waiting(fams: Sequence[Mapping[str, Any]], seats: int, *, seatable: Any = None) -> set[str]:
    """The Candidates `seating` leaves waiting: `read` gives them no row."""
    return set(seating(fams, seats, seatable=seatable)["waiting"])


def equity_seatable(structure: Any) -> bool:
    """THE EQUITY ROSTER: an equity Candidate of an equity structure can hold a seat (the money table's equity block, not
    its options types, decides what it may trade: league/equity)."""
    return str(structure or "") in EQUITY_STRUCTURES


def equity_seats(seats: int) -> int:
    """`elane.roster` as `seating` reads it: a positive count is itself; 0 (no equity seat) and an unreadable setting
    (`ROSTER_CLOSED`) both seat no new Candidate (unlike `dlane.roster`, where 0 means no roster)."""
    return int(seats) if int(seats) > 0 else ROSTER_CLOSED


def equity_seating(fams: Sequence[Mapping[str, Any]], seats: int, *,
                   seatable: Any = equity_seatable) -> dict[str, list[str]]:
    """THE EQUITY ROSTER's `seating` over the equity Candidate and Probe families (`seats`: `elane.roster_seats`).
    `seatable` (RELEASE E4): the seat rule by structure; the callers that hold the state root pass
    `elane_xs.seatable(root)`, under which a PANEL Candidate is seatable only while the panel lane's effective mode is
    "live" (otherwise it is seatless: no row, so no instance and no order)."""
    return seating(fams, equity_seats(seats), seatable=seatable)


def _equity_seatable(root: str | Path) -> Any:
    """The equity roster's seat rule for a state root: `elane_xs.seatable(root)` (RELEASE E4), and E1's own rule less the
    panel when that cannot be built (a panel Candidate is then seatless: fail closed)."""
    try:
        from . import elane_xs

        return elane_xs.seatable(root)
    except Exception:  # noqa: BLE001 - no panel rule: no panel seat
        return lambda structure: equity_seatable(structure) and str(structure or "") != "panel"


def roster(root: str | Path, *, lanes: Any = None) -> dict[str, Any] | None:
    """The roster as it stands, for reports: {seats, closed, probe, seated, waiting, seatless} (`seated`: the Probe
    families and the Candidates holding a seat). None when it is off or the store cannot be read. `lanes` (THE EQUITY
    LANES: `LANES`): the equity roster (`elane.roster`) over the equity families, never off."""
    equity = lanes is not None
    if equity:
        from . import elane

        seats = elane.roster_seats(root)
    else:
        seats = _roster_seats(root)
        if seats == 0:
            return None
    try:
        db = sqlite3.connect(f"file:{Path(root) / DB_NAME}?mode=ro", uri=True, timeout=1.0)
        db.row_factory = sqlite3.Row
        try:
            fams = _banded(db, equity=equity)
        finally:
            db.close()
    except (sqlite3.Error, OSError):
        return None
    seat = equity_seating(fams, seats, seatable=_equity_seatable(root)) if equity else seating(fams, seats)
    return {"seats": max(seats, 0), "closed": seats == ROSTER_CLOSED, "probe": seat["probe"],
            "seated": sorted(seat["probe"] + seat["seated"]), "waiting": seat["waiting"], "seatless": seat["seatless"]}


def _roster_seats(root: str | Path) -> int:
    """`dlane.roster` from <root>/swarm.json, read here and FAILING CLOSED (the review of PR #523): no file, no `dlane`
    block or no `roster` key is 0 (no roster); a whole number 0-50 is itself (above 50 is 50) and is remembered as this
    process's last good value; a file that exists but cannot be read or parsed, or a `dlane`/`roster` of the wrong shape
    (a string, a bool, a fraction, a negative) is the last good value, else `ROSTER_CLOSED` (no new seat: the queue all
    waits). Never raises. The policy layer does not carry it: the roster is an operator's switch."""
    path = Path(root) / "swarm.json"
    key = str(path)
    bad = False
    try:
        doc = json.loads(path.read_text())
    except FileNotFoundError:
        return 0
    except (OSError, ValueError):
        doc, bad = None, True
    if not bad:
        block = doc.get("dlane") if isinstance(doc, Mapping) else None
        if not isinstance(doc, Mapping) or ("dlane" in doc and not isinstance(block, Mapping)):
            bad = True
        elif block is None or "roster" not in block:
            return 0
        else:
            value = block["roster"]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                bad = True
            else:
                good = min(int(value), 50)
                with _roster_lock:
                    _roster_good[key] = good
                return good
    with _roster_lock:
        return _roster_good.get(key, ROSTER_CLOSED)


def _banded(db: sqlite3.Connection, *, equity: bool = False) -> list[dict[str, Any]]:
    """The alive Candidate and Probe families, their state parsed (the roster's input): the options lanes' (THE PROBE
    ROSTER), or with `equity` the equity lanes' (THE EQUITY ROSTER), never both."""
    out = []
    scope = EQUITY_ONLY_SQL if equity else OPTIONS_ONLY_SQL
    for r in db.execute("SELECT id, band, band_since, structure, state FROM families WHERE retired_at IS NULL AND band IN "
                        f"('candidate', 'probe') AND {scope} ORDER BY id"):
        row = dict(r)
        row["state"] = loads(row["state"], {}) or {}
        out.append(row)
    return out


def read(root: str | Path, *, family: str | None = None, lanes: Any = None,
         strict: bool = False) -> list[dict[str, Any]]:
    """The rows (the module docstring); `family`: that family's row only. [] when there is no store or it cannot be read
    within a second. `lanes` (THE EQUITY LANES): None the options lanes only (every existing reader); `LANES` (or one
    equity lane) the equity rows only (`_read_equity`); "all" both. `strict` (the equity rows only): raise
    `EquityUnreadable` in place of that [] (the options rows are read as before)."""
    if lanes is not None:
        if lanes == "all":
            return read(root, family=family) + _read_equity(root, family=family, lanes=EQUITY_LANES, strict=strict)
        return _read_equity(root, family=family, lanes=lanes, strict=strict)
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
            # THE PROBE ROSTER (`seating`): read inside the same connection, over every Candidate and Probe family, and
            # only when a Candidate is among the rows asked for (a Probe, Sized or Gym row is never hidden)
            seats = _roster_seats(root)
            hidden = waiting(_banded(db), seats) if seats and any(f["band"] == "candidate" for f in fams) else set()
            wanted: dict[str, int] = {}
            for fam in fams:
                state = loads(fam["state"], {}) or {}
                fam["state"] = state
                if fam["id"] in hidden:
                    continue  # a Candidate waiting for a roster seat: no row, so no shadow or real instance
                if fam["band"] in LIVE_BANDS and state.get("banded_version"):
                    wanted[fam["id"]] = int(state["banded_version"])
                elif fam["band"] == "gym" and (state.get("validation_line") or {}).get("passed") and state.get("validation_version"):
                    wanted[fam["id"]] = int(state["validation_version"])  # tuition: checked against its review below
            versions = {}
            for fid, n in wanted.items():
                row = db.execute("SELECT n, sha, params, path, created_at FROM versions WHERE family=? AND n=?",
                                 (fid, n)).fetchone()
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
        if fam["band"] in LIVE_BANDS and not current_banded_evaluator(state, sha):
            continue  # preserved historical band/positions, but no new entry under unqualified semantics
        if fam["band"] == "gym":
            if not image or state.get("validation_image") != image or not bundle or state.get("validation_bundle") != bundle:
                continue
            # Tuition only for a validated version the review (and the audit) passed and the gate has not failed, refused,
            # demoted or held (`BAD_OUTCOMES`): a program the reviewer called dangerous, one whose holdout or forward record
            # failed, or one whose look the gate held (no look is coming, so its tuition would never end), never sends a
            # real order.
            review = state.get("review") or {}
            outcome = state.get("gate_outcome") or {}
            if review.get("sha") != sha or review.get("verdict") != "pass" or (review.get("audit") or {}).get("verdict") != "pass":
                continue
            from .gate import gate_contract as review_contract

            if review.get("contract_sha") != review_contract()["sha256"] or (review.get("audit") or {}).get("contract_sha") != review_contract()["sha256"]:
                continue
            if outcome.get("sha") == sha and outcome.get("result") in BAD_OUTCOMES:
                continue
        validated = state.get("validation_version") == v["n"] and bool((state.get("validation_line") or {}).get("passed"))
        out.append({
            "family": fam["id"], "band": fam["band"], "structure": fam["structure"], "roots": loads(fam["roots"], []),
            "holdout_passed": fam["band"] in LIVE_BANDS, "validation_passed": validated or fam["band"] in LIVE_BANDS,
            "version": int(v["n"]), "code": code, "params": params, "run_sha": sha,
            "typical_max_loss_usd": (state.get("typical_by_version") or {}).get(str(v["n"]),
                state.get("typical_max_loss_usd") if state.get("validation_version") == v["n"] else None),
            "seed_era": True, "forward": state.get("forward"),
            # When the version was written (UTC): the live path's Sized move counts only the forward record of sessions
            # after it (the forward embargo, Sept 29, 2026: `OptionsLive._move_band`).
            "version_created_at": v.get("created_at"),
            "version_selected_at": state.get("banded_at"),
        })
    return out


#: THE EQUITY IDENTITY as `read(lanes=...)` checks a band against it (`evaluator.equity_fingerprint`), reused for
#: `BUNDLE_TTL` seconds a process (it hashes every file of league/equity): (when, the sha or None).
_equity_cache: tuple[float, str] | None = None


def _equity_sha() -> str | None:
    """The current equity fingerprint, or None when it cannot be computed (no equity row is then current)."""
    global _equity_cache
    now = time.monotonic()
    with _bundle_lock:
        cached = _equity_cache
    if cached is not None and 0.0 <= now - cached[0] < BUNDLE_TTL:
        return cached[1]
    try:
        from .evaluator import equity_fingerprint

        value = str(equity_fingerprint())
    except Exception:  # noqa: BLE001 - not cached: the next read tries again
        return None
    with _bundle_lock:
        _equity_cache = (now, value)
    return value


#: THE XS IDENTITY (release E4) as `read(lanes=...)` checks a PANEL band against it (`league.xs.identity
#: .xs_fingerprint`, computed from the running release's own files), reused for `BUNDLE_TTL` seconds a process.
_xs_cache: tuple[float, str] | None = None


def _xs_sha() -> str | None:
    """The current xs fingerprint, or None when it cannot be computed (no panel row is then current). FROM THE RUNNING
    CODE, never from the store's kv `xs_evaluator` (written only when the swarm loop starts): with the loop stopped
    after a release that changed an xs evidence module, a kv check would let the book go on opening positions under
    code no look judged."""
    global _xs_cache
    now = time.monotonic()
    with _bundle_lock:
        cached = _xs_cache
    if cached is not None and 0.0 <= now - cached[0] < BUNDLE_TTL:
        return cached[1]
    try:
        from ..xs.identity import xs_fingerprint

        value = str(xs_fingerprint())
    except Exception:  # noqa: BLE001 - not cached: the next read tries again
        return None
    with _bundle_lock:
        _xs_cache = (now, value)
    return value


def current_xs_evaluator(state: Mapping[str, Any], sha: str, xs_sha: str | None) -> bool:
    """A PANEL band's proof (`banded_evaluator`, written by `elane_xs.look` when its one look passed and the style rule
    let it be seated) names the panel engine, the xs identity of the running release and the exact program
    (`run_sha`)."""
    from ..xs import XS_ENGINE_VERSION

    proof = state.get("banded_evaluator") if isinstance(state.get("banded_evaluator"), Mapping) else {}
    return (xs_sha is not None and proof.get("engine") == XS_ENGINE_VERSION
            and proof.get("xs_sha256") == xs_sha and proof.get("run_sha") == sha)


def current_equity_evaluator(state: Mapping[str, Any], sha: str, equity_sha: str | None) -> bool:
    """An equity band's proof (`banded_evaluator`, written by `elane.look` when its one look passed) names the engine,
    the equity identity in force and the exact program (`run_sha`): an equity release that moves the identity sends the
    band back to qualification (`evaluator.adopt_equity`), as an options release does with `current_banded_evaluator`."""
    from ..equity import EQUITY_ENGINE_VERSION

    proof = state.get("banded_evaluator") if isinstance(state.get("banded_evaluator"), Mapping) else {}
    return (equity_sha is not None and proof.get("engine") == EQUITY_ENGINE_VERSION
            and proof.get("equity_sha256") == equity_sha and proof.get("run_sha") == sha)


def equity_proof_current(state: Mapping[str, Any], version: Mapping[str, Any]) -> bool | None:
    """Whether an equity family's band proof (`current_equity_evaluator`) is the CURRENT equity identity for the program
    of `version` (its versions row: `sha`, `params`); None when the identity cannot be computed (no answer either way).
    The EquityBook's reader asks it about a family that has no row (league/equity/families.py `standing`)."""
    from .gate import run_sha

    sha = run_sha({"sha": version["sha"], "params": version.get("params") or {}})
    proof = state.get("banded_evaluator") if isinstance(state.get("banded_evaluator"), Mapping) else {}
    if _panel_proof(proof):
        # RELEASE E4: a proof naming the panel engine is judged by the xs identity (judged against the equity identity
        # it would always read "not current", and the book would retire a healthy panel program the first time its
        # row could not be read). None when that identity cannot be computed: unknown, nothing retired.
        xs_sha = _xs_sha()
        return None if xs_sha is None else current_xs_evaluator(state, sha, xs_sha)
    equity_sha = _equity_sha()
    if equity_sha is None:
        return None
    return current_equity_evaluator(state, sha, equity_sha)


def equity_seat_withdrawn(root: str | Path, fam: Mapping[str, Any]) -> tuple[str, str] | None:
    """RELEASE E4: THE STORE'S WORD on the seat of a family in a running band that `read` gave no row for a reason of
    the LANE's, as league/equity/families.py `standing` answers the book: None for a family that is no panel family and
    while the panel lane is live (the question is then E1's own: the version, the proof); ("demoted", why) on the
    lane's POSITIVE word that no panel program holds a seat now (`elane_xs.seat_standing`: a switch put down, or a
    named leg of `live_ready` failed): the book retires the instance and its lots exit at the next open; ("unknown",
    why) when the lane cannot be read, on which the book retires nothing (A8.5) and, having no row, opens nothing."""
    if str((fam or {}).get("structure") or "") != "panel":
        return None
    try:
        from . import elane_xs

        live, why = elane_xs.seat_standing(root)
    except Exception as exc:  # noqa: BLE001 - no evidence either way
        return "unknown", f"the panel lane could not be read ({type(exc).__name__})"
    if live is True:
        return None
    return ("demoted" if live is False else "unknown"), str(why)


def _panel_proof(proof: Mapping[str, Any]) -> bool:
    """Whether a band proof names the panel engine (`league.xs.XS_ENGINE_VERSION`): the proof's engine says which
    identity judges it."""
    try:
        from ..xs import XS_ENGINE_VERSION
    except Exception:  # noqa: BLE001 - no panel package: no panel proof
        return False
    return proof.get("engine") == XS_ENGINE_VERSION


class EquityUnreadable(RuntimeError):
    """`read(..., strict=True)`: the equity rows could not be READ (no store, a store that could not be read within its
    second, or no equity identity to check a band against). Never raised for a store that was read and holds no row."""


def _read_equity(root: str | Path, *, family: str | None, lanes: Any, strict: bool = False) -> list[dict[str, Any]]:
    """`read(root, lanes=...)`: the equity rows (the module docstring), the lanes `lanes` names. [] when there is no
    store, it cannot be read within a second, or the equity identity cannot be computed (fail-closed); with `strict`
    each of those three raises `EquityUnreadable` instead, so the caller can tell them from a store with no row. One
    family's own trouble (its code file or its version row cannot be read) leaves that family out either way: the
    EquityBook asks the store about a missing family before it retires its instance (league/equity/families.py
    `standing`)."""
    wanted = {str(x) for x in ([lanes] if isinstance(lanes, str) else lanes)}
    unknown = sorted(wanted - set(EQUITY_LANES))
    if unknown:
        raise ValueError(f"lanes: {', '.join(unknown)} is no equity lane")
    path = Path(root) / DB_NAME
    if not path.exists():
        if strict:
            raise EquityUnreadable(f"no swarm store at {path}")
        return []
    equity_sha = _equity_sha()
    if equity_sha is None:
        if strict:
            raise EquityUnreadable("the equity identity could not be computed")
        return []
    from . import elane

    xs_sha: str | None = None
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        db.row_factory = sqlite3.Row
        try:
            fams = [f for f in _families(db, family, equity=True) if f["band"] in LIVE_BANDS]
            if any(f["structure"] == "panel" for f in fams):
                # RELEASE E4: a panel family is in a running band. Its proof is judged by the xs identity of THIS
                # release's files; where that cannot be computed no panel row is current, and the strict reader is told
                # "could not read" (it retires an instance on "no row").
                xs_sha = _xs_sha()
                if xs_sha is None and strict:
                    raise EquityUnreadable("the xs identity could not be computed while a panel family is in a running "
                                           "band")
            seat = equity_seating(_banded(db, equity=True), elane.roster_seats(root), seatable=_equity_seatable(root)) \
                if any(f["band"] == "candidate" for f in fams) else {"probe": [], "seated": [], "waiting": [], "seatless": []}
            hidden = set(seat["waiting"]) | set(seat["seatless"])
            if any(f["structure"] == "panel" and f["band"] != "candidate" for f in fams) \
                    and not _equity_seatable(root)("panel"):
                # RELEASE E4, THE SEAT OF A SEATED PANEL FAMILY: the seat rule that gives a panel Candidate a row only
                # while the lane's effective mode is "live" holds for one at Probe or Sized too. Left to the Candidates
                # alone, a seated panel program went on buying after the lane's mode was put down, the nightly I6
                # failed or its shadow twin stopped. No row: the book opens nothing for it (league/equity/live.py
                # `_seat_block`) and asks `equity_seat_withdrawn` before it retires the instance.
                hidden |= {f["id"] for f in fams if f["structure"] == "panel"}
            versions = {}
            for fam in fams:
                fam["state"] = loads(fam["state"], {}) or {}
                fam["spec"] = loads(fam["spec"], {}) or {}
                if fam["id"] in hidden or lane_of_spec(fam["spec"]) not in wanted:
                    continue  # a Candidate waiting for an equity roster seat (or holding none): no row
                n = fam["state"].get("banded_version")
                if not n:
                    continue
                row = db.execute("SELECT n, sha, params, path, created_at FROM versions WHERE family=? AND n=?",
                                 (fam["id"], int(n))).fetchone()
                if row is not None:
                    versions[fam["id"]] = dict(row)
        finally:
            db.close()
    except sqlite3.Error as exc:
        if strict:
            raise EquityUnreadable(f"{type(exc).__name__}: {str(exc)[:160]}") from exc
        return []
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
        state, spec = fam["state"], fam["spec"]
        params = loads(v["params"], {}) or {}
        sha = run_sha({"sha": v["sha"], "params": params})
        panel = fam["structure"] == "panel"
        if not (current_xs_evaluator(state, sha, xs_sha) if panel else current_equity_evaluator(state, sha, equity_sha)):
            continue  # its lots keep their exits (the EquityBook's), but no new entry under an unqualified identity
        lane = lane_of_spec(spec)
        symbols = [str(r).upper() for r in loads(fam["roots"], []) or []]
        look_key = "elane_xs_look" if panel else elane.LOOK_KEY  # `elane_xs.LOOK_KEY`: XS1's sentence beside its trades
        looked = state.get(look_key) if isinstance(state.get(look_key), Mapping) else {}
        out.append({
            "family": fam["id"], "band": fam["band"], "structure": fam["structure"], "roots": symbols, "symbols": symbols,
            "lane": lane, "label": elane.label(lane), "seeded": spec.get("seeded") is True,
            "seat": "sized" if fam["band"] == "sized" else "probe" if fam["band"] == "probe" else "seated",
            "holdout_passed": True, "validation_passed": True, "version": int(v["n"]), "code": code, "params": params,
            "run_sha": sha, "typical_max_loss_usd": None, "seed_era": True, "forward": state.get("forward"),
            "version_created_at": v.get("created_at"), "version_selected_at": state.get("banded_at"),
            "validation_version": state.get("validation_version"),
            "validation_r_sd_by_version": dict(state.get(elane.SIGMA_KEY) or {})
            if isinstance(state.get(elane.SIGMA_KEY), Mapping) else {},
            "beside": looked.get("beside"),
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


def _current_practice_run(db: sqlite3.Connection, root: Path, fid: str, n: int, tier: str,
                          image: Any, bundle: Any) -> bool:
    """New cohorts need real current-evaluator evidence, not a surviving best/validation label."""
    if not image or not bundle:
        return False
    windows = ("validation", "validation") if tier == "validated" else ("train", "validation")
    rows = db.execute("SELECT summary,path,window FROM runs WHERE family=? AND version=? AND window IN (?,?) "
                      "AND stress=1.0 AND status='ok' ORDER BY at DESC LIMIT 30", (fid, n, *windows))
    for row in rows:
        summary = loads(row["summary"], {}) or {}
        result = summary
        if "gym_bundle" not in summary and row["path"]:
            try:
                result = json.loads(gzip.decompress((root / row["path"]).read_bytes()))
            except (OSError, ValueError, TypeError):
                continue
        if result.get("gym_image") != image or result.get("gym_bundle") != bundle:
            continue
        if row["window"] == "validation" or summary.get("train_eligible") is True:
            return True
    return False


def observe(root: str | Path, *, family: str | None = None, version: int | None = None) -> list[dict[str, Any]]:
    """The practice league's rows (the module docstring), in its admission order (`priority`). `family` narrows to one
    family; with `version`, that family's version `version` (a pinned one) instead of its current one. [] when there is no
    store. A store that cannot be read within a second RAISES (`sqlite3.Error`), unlike `read`: the live path then keeps
    the observe instances and pins it has, rather than taking an unreadable store for an empty band and pinning afresh in
    the middle of a session."""
    path = Path(root) / DB_NAME
    if not path.exists() or (version is not None and family is None):
        return []
    image, bundle = settings.load(root)["gym"]["image_checkpoint"], _bundle()
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
            if not _current_practice_run(db, Path(root), fam["id"], n, name, image, bundle):
                continue
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


def _review_passed(review: Any, sha: str, contract: str) -> bool:
    """The gate's review AND audit passed on `sha` under the current review contract (`read`'s own check)."""
    if not isinstance(review, Mapping):
        return False
    audit = review.get("audit") if isinstance(review.get("audit"), Mapping) else {}
    return (review.get("sha") == sha and review.get("verdict") == "pass" and audit.get("verdict") == "pass"
            and review.get("contract_sha") == contract and audit.get("contract_sha") == contract)


#: THE READER'S BELT's records: a family's records that can name a verdict against a program. One that is there but is
#: not a mapping cannot be read, and refuses every program of the family (fail-closed), as do the records `incubator`
#: reads its other conditions from.
BELT_RECORDS = ("review", "incubator_reviews", "incubator_barred", "gate_outcome")
_READ_RECORDS = ("train_passed", "validation_line", "drift_failed")
#: The gate's bars not yet in the store (`gate.Gate.bars_owed`: an error kept them out), kept beside it so a restart (and
#: the evaluator adoption at its start) cannot lose them: {"bars": [{family, sha, version, why}]}. The belt refuses a
#: program named there, and every program while the file is there but cannot be read (fail-closed).
BARS_OWED_FILE = "incubator-bars-owed.json"
_UNREADABLE = object()


def owed_bars(root: str | Path) -> list[dict[str, Any]] | None:
    """The bars owed (`BARS_OWED_FILE`): [] when there is no file, None when it is there but cannot be read."""
    path = Path(root) / BARS_OWED_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    bars = data.get("bars") if isinstance(data, Mapping) else None
    if not isinstance(bars, list) or not all(isinstance(b, Mapping) and isinstance(b.get("sha"), str) for b in bars):
        return None
    return [dict(b) for b in bars]


def _pass_and_audit(record: Mapping[str, Any]) -> bool:
    """A review record that reads as a pass with a passed audit (both the word "pass"), whatever its contract."""
    audit = record.get("audit")
    return record.get("verdict") == "pass" and isinstance(audit, Mapping) and audit.get("verdict") == "pass"


def incubator_refusal(state: Any, sha: str) -> str | None:
    """THE READER'S BELT (Oct 1, 2026; the owner's term: a program whose review or audit failed never trades the
    incubator): why `incubator` refuses program `sha` of a family whose state is `state`, whatever its Train-and-drift
    mark says, or None. It reads the verdicts themselves, not the swarm's removal of the mark (`program_refusal`), and
    FAILS CLOSED when a record the conditions read (`train_passed`, `validation_line`, `drift_failed`, `robust_failed`)
    cannot be read. `incubator` also reads `program_refusal` in every other family holding the same program (the same
    `run_sha`), the gate's refusal rows of every version of it, its failed holdout looks and the bars owed
    (`BARS_OWED_FILE`)."""
    if not isinstance(state, Mapping):
        return "the family's state cannot be read"
    for key in _READ_RECORDS:
        if state.get(key) is not None and not isinstance(state.get(key), Mapping):
            return f"its {key} cannot be read"
    if state.get("robust_failed") is not None and not isinstance(state.get("robust_failed"), list):
        return "its robust_failed cannot be read"
    return program_refusal(state, sha)


def program_refusal(state: Any, sha: str) -> str | None:
    """THE READER'S BELT's verdicts on program `sha` in one family's state (its own, or any other family holding the same
    program: a verdict is on the PROGRAM, whichever family it was made in), or None:
    - the swarm recorded a bar for the program (`incubator_barred[sha]`, any entry: bars are kept for good);
    - the gate's `review` names the program without a readable pass and a readable passed audit (a failed review or
      audit, an unclear or unreadable verdict, and a pass whose audit is still owed: not final, so the House waits);
    - the incubator's own review of it (`incubator_reviews[sha]`) failed, was revoked, or has an audit that did not
      pass, whatever its contract, or cannot be read as this program's;
    - the gate's `gate_outcome` names it refused, failed, demoted or held (`BAD_OUTCOMES`);
    - FAIL-CLOSED: the state or one of `BELT_RECORDS` cannot be read, or the gate's `review` names no program.
    The swarm reads this same function in every other family holding the program (`incubator.program_bar`), so it
    never marks, or pays to review, a program refused here for another family's records."""
    if not isinstance(state, Mapping):
        return "the family's state cannot be read"
    for key in BELT_RECORDS:
        if state.get(key) is not None and not isinstance(state.get(key), Mapping):
            return f"its {key} cannot be read"
    if sha in (state.get("incubator_barred") or {}):
        return "the swarm barred its program (incubator_barred)"
    review = state.get("review") or {}
    if review:
        named = review.get("sha")
        if not isinstance(named, str) or not named:
            return "the gate's review record names no program"
        if named == sha and not _pass_and_audit(review):
            return "the gate's review of it is not a pass with a passed audit"
    reviews = state.get("incubator_reviews") or {}
    if sha in reviews:
        record = reviews[sha]
        if not isinstance(record, Mapping) or record.get("sha") != sha:
            return "the incubator's review of it cannot be read"
        if record.get("verdict") != "pass" or ("audit" in record and not _pass_and_audit(record)):
            return "the incubator's review or audit of it did not pass"
    outcome = state.get("gate_outcome") or {}
    if outcome.get("sha") == sha and outcome.get("result") in BAD_OUTCOMES:
        return f"the gate's outcome for it is {outcome['result']}"
    return None


def _program_rows(db: sqlite3.Connection, fid: str, code_sha: str, sha: str) -> tuple[str | None, list[tuple[str, Any]]]:
    """THE PROGRAM's other records in one read-only connection: (a refusal of any version of program `sha` in any
    family, alive or retired, or None; [(family, state)] of every OTHER family holding it, its state as read, or
    `_UNREADABLE`). The same code sha with the same params is the same `run_sha` (`gate.run_sha`)."""
    from .gate import run_sha

    ruled = None
    others: dict[str, Any] = {}
    for twin in db.execute("SELECT v.family AS family, v.n AS n, v.params AS params, f.id AS fid, f.state AS state "
                           "FROM versions v LEFT JOIN families f ON f.id=v.family WHERE v.sha=?", (code_sha,)):
        if run_sha({"sha": code_sha, "params": loads(twin["params"], {}) or {}}) != sha:
            continue
        if ruled is None and db.execute("SELECT 1 FROM refusals WHERE family=? AND version=? LIMIT 1",
                                        (twin["family"], twin["n"])).fetchone() is not None:
            ruled = f"the gate refused it ({twin['family']}@{twin['n']})"
        if twin["family"] != fid and twin["fid"] is not None and twin["family"] not in others:
            others[twin["family"]] = loads(twin["state"], _UNREADABLE)
    return ruled, list(others.items())


def _lane_marks_open(root: str | Path, lane: Any, k5: Any) -> bool:
    """THE DIRECTION LANE'S MARK at the reader (release D-1, Oct 9, 2026; PLAN D5, the operator's decision 9): a mark
    that names a lane (`incubator._direction_mark` writes `lane` "direction"; an alpha mark names none) is accepted only
    while that lane is "direction" and takes marks: its effective mode is "gate" (`dlane.candidates_open`), read from
    the swarm's own settings for this state directory (policy.json, then `<root>/swarm.json`, as `read` reads the image)
    and the store's K5 kv (`dlane_k5`, read in this reader's own connection; the operator's `dlane.k5_clear` in swarm.json
    lifts it). So "shadow", K5 and the lane off (THE ROLLBACK) refuse every direction mark, and accept no new one either.
    Fail-closed: settings that cannot be read accept no direction mark (an alpha mark never reads them)."""
    from . import dlane

    if lane != dlane.DIRECTION:
        return False
    try:
        conf = settings.load(root)
    except Exception:  # noqa: BLE001 - fail-closed
        return False
    return dlane.candidates_open({} if k5 is None else {dlane.K5_KEY: k5}, conf)


def incubator(root: str | Path, *, family: str, version: int) -> list[dict[str, Any]]:
    """The incubator's facts for version `version` of `family` (the module docstring): one row, or []. Standard library
    and read-only (`mode=ro`, a one-second timeout); RAISES `sqlite3.Error` when the store cannot be read (fail-closed:
    no new pin, no incubator open). THE READER'S BELT (`incubator_refusal`, and the gate's refusal and look rows) comes
    before every other condition."""
    path = Path(root) / DB_NAME
    n = _count(version)
    if not path.exists() or n is None or not family:
        return []
    from .gate import run_sha
    from .gate import gate_contract as review_contract

    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
    db.row_factory = sqlite3.Row
    try:
        fams = _families(db, str(family), gym_only=True)
        if not fams:
            return []
        fam = fams[0]
        kv = {str(r["key"]): loads(r["value"], None) for r in db.execute(
            "SELECT key, value FROM kv WHERE key IN ('research_evaluator', 'train_objective', 'dlane_k5')")}
        row = db.execute("SELECT n, sha, params FROM versions WHERE family=? AND n=?", (fam["id"], n)).fetchone()
        if row is None:
            return []
        params = loads(row["params"], {}) or {}
        sha = run_sha({"sha": row["sha"], "params": params})
        # THE READER'S BELT's rows, kept for good (no adoption clears them): the gate refused a version of this PROGRAM
        # (the same code and params, the same run_sha) at any stage in any family, or a holdout look on it failed; and
        # every other family holding the program, whose verdicts on it are this program's too.
        ruled, others = _program_rows(db, str(fam["id"]), str(row["sha"]), sha)
        failed = db.execute("SELECT 1 FROM looks WHERE run_sha=? AND passed=0 LIMIT 1", (sha,)).fetchone()
    finally:
        db.close()
    if fam["band"] != "gym" or ruled is not None or failed is not None:
        return []
    state = loads(fam["state"], _UNREADABLE)
    state = {} if state is None else state
    if incubator_refusal(state, sha) is not None:
        return []
    if any(program_refusal({} if other is None else other, sha) is not None for _, other in others):
        return []  # a verdict on the same program in another family (or one of its records cannot be read)
    owed = owed_bars(root)
    if owed is None or any(bar.get("sha") == sha for bar in owed):
        return []  # a bar the gate owes the store (an error kept it out), or a record of them that cannot be read
    if demoted(state, n):
        return []
    if (state.get("validation_line") or {}).get("passed") and state.get("validation_version"):
        # D2's route (its tuition row: `:t` > `:i`), decided from the family's own state here, so a `read` that came back
        # empty for a moment (a lock) never lets the incubator trade a family D2 owns.
        return []
    mark = (state.get("train_passed") or {}).get(str(n))
    evaluator, objective = kv.get("research_evaluator"), kv.get("train_objective")
    if (not isinstance(mark, Mapping) or evaluator is None or objective is None or mark.get("evaluator") != evaluator
            or mark.get("objective") != objective):
        return []  # no Train-and-drift pass under the current evaluator and Train objective (both known)
    robust = _finite(mark.get("robust_pnl"))
    if robust is None or robust <= 0 or not isinstance(mark.get("drift"), Mapping):
        return []  # a belt: the mark itself shows a profit at 1.5x the half-spread and the drift screen's figures
    if mark.get("lane") is not None and not _lane_marks_open(root, mark.get("lane"), kv.get("dlane_k5")):
        return []  # THE DIRECTION LANE's mark (release D-1) while its lane takes none: "shadow", K5, or the lane off
    contract = review_contract()["sha256"]
    reviews = state.get("incubator_reviews") or {}
    if not (_review_passed(state.get("review"), sha, contract) or _review_passed(reviews.get(sha), sha, contract)):
        return []
    return [{"family": fam["id"], "version": n, "run_sha": sha, "structure": fam["structure"],
             "roots": [str(r).upper() for r in loads(fam["roots"], []) or []], "band": "gym", "incubator": True,
             "observe": False, "holdout_passed": False, "validation_passed": False}]


__all__ = ["read", "observe", "incubator", "incubator_refusal", "program_refusal", "owed_bars", "priority", "practice_tier",
           "demoted", "LIVE_BANDS", "TIERS", "BUNDLE_TTL", "BELT_RECORDS", "BARS_OWED_FILE", "BAD_OUTCOMES",
           "seating", "waiting", "roster", "equity_seatable", "equity_seats", "equity_seating",
           "current_equity_evaluator", "equity_proof_current", "equity_seat_withdrawn", "EquityUnreadable"]
