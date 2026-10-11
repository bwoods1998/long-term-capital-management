"""THE PANEL LANE'S HALF OF THE FORWARD RECORD (release E4, package J): the registry row, the nightly shadow and the
shadow twin of a panel program, on release E3's forward record.

Owner: package J (league/xs/E4_INTERFACES.md). Protected (league/ops/ is FORBIDDEN to every role); ops only: no module
of league/swarm, league/equity, league/live or league/gym imports it (release E3's seal T1 holds it as it holds E3's
own ops modules). It writes E3's own tables of `<state>/forward.sqlite` through E3's modules (league/ops/forward_db.py)
and ONE file a generator-side process may read, the twin marker. It moves no money, gates nothing and writes no
verdict; it moves no evidence identity and no money digest (plumbing: outside the xs identity).

WHY IT EXISTS. E3's registry takes ETF and stock programs. Without this module a scored panel version has no
hash-chained forward row (its forward days from birth could never be shown clean), and a live panel close would enter
the next Done checkpoint with every session missing its twin row: E3's A14 reading counts a session with no
`fwd_twins` row as NOT agreed, so the whole checkpoint, the seeds' closes included, would read "not consistent".

WITH EVERY SWITCH OFF NOTHING HERE RUNS OR WRITES: the job is skipped while `elane.forward.mode` is "off" or
`elane.panel.mode` is "off"; with no panel row in the registry E3's own night is byte for byte what it was (its
engine label, its queue, its groups).

1. THE REGISTRY (`scored`, `scored_rows`, `live_row`; called by league/ops/forward_register.py `sync`). Every version
   of a panel family JUDGED ON THE TRAIN BAR (its `elane_xs` record's verdict carries Train facts: a version judged on
   its program alone, RUN, DQ or LOAD, has none and is not registered), passed or failed, with the time of the scored
   event `elane_xs.score` writes, exactly as E3 registers an ETF version. The row: lane "equity", `ugroup`
   "panel:<panel>" (`UGROUP`), `needs` the program's own NEEDS literal parsed by `league.xs.program.parse_needs`,
   `route` "XS1" and `alpha_f` "0.03" IN THE HASHED ROW (E3's rule for a row registered before its forward screen is
   pinned: XS1's look and 3% forward stay inside the owner's 15%). A live panel instance the registry does not hold
   is registered from the book row's own code, as E3's. No control group holds a panel row.

2. THE PANEL NIGHT (`run`, the job `forward_xs`; `panel_shadow`). E3's own night (`forward_shadow.Shadow.night`:
   preflight, the registry's sync, the queue in E3's order, THE RETRY, the checkpoints, the twins) on a subclass that
   reads the PANEL store and runs the "panel" kind in the forward job's own decider child.
   - WHEN: after `equity_panel` has written the night's store (01:55Z), never inside 09:00-17:30 New York on a
     session. NOT A RIDE ON E3's 22:35Z NIGHT (the spec's first plan): the panel store is a session behind at that
     hour, and the lane's own rule (`league.swarm.elane_xs.live_ready`: the marker no older than the session before
     the last closed one) would have read "twin marker behind" from every close to 22:35Z, the 16:30 decide included.
   - ROWS LAG ONE SESSION, TWINS TWO (`ROW_LAG`, `TWIN_LAG`). The panel engine opens no lot at a slice's last session
     (entry validity reads the session after the fill) and reads membership `config.MEMBER_AHEAD` sessions ahead,
     "as at the last" past the slice's end. So a decision at close d is FINAL once d + 2 is in the store, and a
     day's row once the next session is. With the store through P the night writes `fwd_days` rows for days up to
     L = P - 1 and `fwd_twins` rows for decisions up to P - 2. First write stands (E3's rule), so a row written a
     session early would stand wrong for good. THE NIGHT IS NAMED BY L: its `fwd_runs.through`, the day of its
     events, the day a completed run has a row for. Its `fwd_runs.job` is `JOB`, and E3's readers of a night
     (the stop rules, FW2, the funnel) each read their own job's nights.
   - ONE RUN A PROGRAM A NIGHT, at k 1.0 (`run_program`). The pinned pre-registration's forward series (XSCREEN-1
     section 11) is the residual x and THE STRESS RESIDUAL x15 = x - 0.5 s - f OF ONE RUN; it wins over the build
     spec's "k 1.0 and k 1.5". `series`: r = the run's daily r, w = its exposure, b = bench / w (0 where w is 0, where
     bench is 0 too), so E3's x = r - w * b IS the residual, and r15 = r - (x - x15), so E3's stress excess r15 - w * b
     IS x15. E3's checkpoints, N_eff, CEY and the BH/BY meter then read a panel program in its own currency. What is
     NOT recorded: a run of the 1.5x-cost book (a program that reads its own cash may decide otherwise under it).
   - THE BUDGET, ON ONE CORE: the panel night spends what E3's night left of `elane.forward.cpu_seconds_night`
     (`night_budget`: one budget a night, not raised). With many panel programs registered the stale ones go first
     the next night (E3's queue); FX3 says when two nights running left some. A live instance's twin run is outside
     it, bounded by the night's deadline, as E3's. ONE OPEN OF THE PANEL STORE A NIGHT: every run reads the night's
     own store (the ops child's address space is capped 500 MB above its start, and each open maps the two bar
     arrays again).
   - `fwd_days.bars` of a panel row (`bars_hash`): 16 hex over the panel store's bars as the decision behind the
     day's orders could read them (the 253 sessions through the session before it, every column), one hash a session
     for every panel program. It moves when the vendor restates any name's history (E3's "moved"), which is what
     tells a routine ex-day restatement from a recompute that is not deterministic.
   - NO LIVE-LIKE ROW: no minute bars exist for 500 names (`fwd_ll` holds none of a panel pid; a panel lot's
     `fwd_lotgap` row has its model, slip and twin gap and no timing part).

3. THE TWIN OF A LIVE PANEL INSTANCE (`twin`; called by league/ops/forward_twins.py for an instance whose registry
   row is a panel row, on the panel night only). The registered program run flat from the session after the
   instance's first decision (E3's `d_first`, its retirements and revivals) with RUN KEY = THE INSTANCE ID, so the
   twin reads the ids, the sector codes and the dither the live ctx read (an id is a hash of the run's salt and the
   aid over the whole asset table: the column set does not move it). One `fwd_twins` row a decision session d.
   LIVE KEYS: the instance's `eq_intents` rows of d with the panel's tag: a buy "B|SYM|at" with its weight usd over
   the decision's budget (`eq_rebalances.budget`), a sell of a lot "S|SYM|at|<the lot's opened day>". TWIN KEYS: the
   twin run's own `picks` entry decided on d (no decide is replayed), ids named by the parent. `agree`: the same
   sells, the same buys, every buy's WEIGHT within `WEIGHT_TOL` (weights, not dollars: the live sleeve moves with the
   account and the Gym's is $1,000). UNREADABLE (agree NULL): "retired" (E3's rule) and "audit" (the decision's
   morning re-read was a mismatch: its orders were voided). E3's "split" rule is not applied: it guards a rebuilt
   decide, and the twin's keys are the run's own. THE TWO HASHES of a panel row are 16 hex of the sha256 of the ctx
   each side read (`eq_rebalances.ctx_sha`, the pick's `ctx_sha`; a hold day has none): "bars" then says the two
   decisions did not read the same ctx, "program" that they did.
   BESIDE, never a rule (`rebalance_agreement`, `beside`; the dlane report prints them): the REBALANCE sessions
   agreed k of n (a monthly program's hold days agree by saying nothing: twenty quiet days would hide one rebalance
   that differed), and the twin's residual over the instance's own sessions (kept in `fwd_kv`, `BESIDE_KEY`).

4. THE MARKER (`write_marker`, `league.xs.book.TWINS_FILE`). After the twins: per ALIVE panel instance `due` (the
   latest decision session whose row the lag allows; null before the first) and `last` (the latest session with a
   row), with the panel store's last session as `through`. `league.swarm.elane_xs.live_ready` reads that one file:
   no marker, or one behind, and mode "live" reads as "gate". INSTANCE IDS AND DAYS ONLY: no agreement bit, no
   figure and no symbol crosses to the swarm's process (seal X14).

5. THE ALARMS (`alarms`; the forward report carries them, each warning also an alert of that job; ids, counts and
   dates only): FX1 the twin marker is behind the panel store, or an alive instance's twin is behind its due day;
   FX2 a REBALANCE session whose live and twin orders disagree (told once, with its cause); FX3 panel programs left
   stale two panel nights running (the budget does not cover the panel registry). Each follows two switches
   (`raised`): `elane.forward.mode` and `elane.panel.mode`.

THE MORNING MARKS (`audit_marks`): a live panel decision whose 08:30 re-read was a mismatch marks that day of its
program's registry row (`audit_mismatch`, once a (pid, day)): the day leaves its counted days.

STATED LIMITS. A panel row lags a session behind an ETF row, so once a panel program is registered a day's meters
(league/ops/forward_report.py) wait for its rows and are written the second morning after the day. The panel's
Train runs enter the replay multiple's numerator and its independent history is not in the denominator (the
multiple overstates). No panel control exists (no control pair reads a panel group). The forward route's own
verdict (c_FX, the placebo rank over the first n sessions) is a later release's: E3 records and judges nothing.

Standard library at import; numpy and league.xs inside the functions that read arrays.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import forward_db

#: A panel row's `ugroup` is this and the panel's name.
UGROUP_PREFIX = forward_db.PANEL_UGROUP
UGROUP = "panel:sp500"
#: The forward route and alpha a panel row carries in its hashed row (the module docstring, 1).
ROUTE = forward_db.XS_ROUTE
ALPHA_F = forward_db.E3_ALPHA_F
#: A twin's buy agrees with the live one when their weights differ by no more than this.
WEIGHT_TOL = 1e-3
#: D9's groups of panel pids (`group`): never pooled with an ETF group.
GROUP_PREFIX = "xs:"
GROUPS = ("xs:train_pass", "xs:train_fail", "xs:look_pass", "xs:look_fail")
#: `fwd_runs.job` of the panel night, and of E3's own (league/ops/forward_shadow.py `JOB`: a test holds them equal).
JOB = "forward_xs"
E3_JOB = "forward_shadow"
#: The decider kind of a panel program, and the tag of a panel decision's intents (league/xs/book.py `KIND`, `TAG`).
KIND = "panel"
TAG = "xs"
#: The reason the night mints its `EquityGateCapability` with (the forward days are sealed).
GATE_REASON = "forward-xs"
#: The House's daily store under the state root (league/equity/store.py `STORE_DIR`), the live book and the panel
#: store's manifest inside it.
STORE_DIR = "equity-daily"
LIVE_DB = "live.sqlite"
PANEL_MANIFEST = "panel/PANEL_MANIFEST.json"
PANEL_VERSION = "panel/VERSION"
#: ROWS LAG ONE SESSION, TWINS TWO (the module docstring): a day's row is final once this many later sessions are in
#: the store, and a decision's twin row once that many are. `TWIN_LAG` is `league.xs.config.MEMBER_AHEAD` (a test).
ROW_LAG = 1
TWIN_LAG = 2
#: `fwd_twins.why` of a panel session that is not read.
UNREADABLE = ("audit", "retired")
#: The run key of the night's own slice (its row digests: `bars_hash`); no program runs under it.
NIGHT_KEY = "forward-xs|night"
#: The seconds of `fwd_runs` rows that count against one night's budget: those that ended in the last twelve hours.
NIGHT_WINDOW_S = 12 * 3600.0
#: THE CANARY of the panel kind: it reads the panel and never trades. The preflight runs it over the store's last
#: forward sessions through the same child op as any panel program.
CANARY = '''NEEDS = {"panel": "sp500", "history": 20, "rebalance": "monthly"}
PARAMS = {}


def decide(ctx):
    return {"hold": True}
'''
CANARY_SESSIONS = 5
#: What a panel run's second result says in place of a k 1.5 run (ONE RUN A PROGRAM A NIGHT).
STRESS = "x15 of the one run"
#: The alarms: id -> level.
ALARMS: dict[str, str] = {"FX1": "warning", "FX2": "warning", "FX3": "warning"}
#: `fwd_kv` key: {instance: the twin's residual over the instance's own sessions} (beside the dlane report).
BESIDE_KEY = "xs_beside"
#: The marker's keys, and an instance row's.
MARKER_KEYS = ("version", "through", "at", "instances")
MARKER_ROW = ("due", "last")
_ZERO = 1e-12


def is_panel(program: Any) -> bool:
    """Whether a registry row (a `forward_db.Program`, or a mapping with `ugroup`) is a panel program's."""
    ugroup = program.get("ugroup") if isinstance(program, Mapping) else getattr(program, "ugroup", None)
    return isinstance(ugroup, str) and ugroup.startswith(UGROUP_PREFIX)


def registered(db: sqlite3.Connection) -> bool:
    """Whether the registry holds a panel row."""
    return db.execute("SELECT 1 FROM fwd_registry WHERE ugroup LIKE ? LIMIT 1", (UGROUP_PREFIX + "%",)).fetchone() \
        is not None


def engine_label(db: sqlite3.Connection, label: str) -> str:
    """Tonight's engine label for both nights (league/ops/forward_shadow.py `Shadow._label`): `label` itself while the
    registry holds no panel row (E3's label, unmoved); once it holds one, `label` + "+xs." + the first 12 hex of the
    xs evidence fingerprint. A forward row of a panel program is computed under league/xs's evidence, so a change
    there opens a new labelled series, as a change to an equity evidence module does (one current series for every
    row: every reader takes the newest engine id). It raises when the xs identity cannot be read (a release that
    lacks one of its files has no label to write a row under)."""
    if not registered(db):
        return str(label)
    from ..xs import identity

    return f"{label}+xs.{identity.xs_fingerprint()[:12]}"


def group(row: Any, name: str) -> str:
    """D9's group of a registry row under the group name `name`: `name` itself, or "xs:" + `name` for a panel row (a
    residual and an ETF excess are not one quantity)."""
    return GROUP_PREFIX + str(name) if is_panel(row) else str(name)


# ---------------------------------------------------------------------------------------------------------- 1. registry
def judged(verdict: Any) -> bool:
    """Whether a panel version's verdict was JUDGED ON THE BAR: it carries Train facts (a version judged on its
    program alone, RUN, DQ or LOAD, has none: league/swarm/elane_xs.py `program_fault`)."""
    return isinstance(verdict, Mapping) and isinstance(verdict.get("facts"), Mapping) and bool(verdict["facts"])


def needs_of(code: Any) -> dict[str, Any] | None:
    """A panel program's NEEDS from its literal (`league.xs.program.parse_needs`; the ops process executes no
    program); None when the text declares no NEEDS literal the panel lane accepts."""
    from ..swarm import elane_train
    from ..xs import program as xprogram

    literal = elane_train.needs_literal(code) if isinstance(code, str) else None
    if literal is None:
        return None
    try:
        return xprogram.parse_needs(literal).as_dict()
    except Exception:  # noqa: BLE001 - `NeedsRefused`, whatever it says: no panel NEEDS
        return None


def look_key(fam: Any) -> str | None:
    """The family-state key of a panel family's look (league/swarm/elane_xs.py `LOOK_KEY`: {"version", "verdict":
    {"passed"}}, the shape E3's tags read); None for a family of another structure."""
    from ..swarm import elane_xs

    return elane_xs.LOOK_KEY if elane_xs.is_panel(fam) else None


def oldest_first(row: Mapping[str, Any]) -> tuple[Any, ...]:
    """The registry's order (league/ops/forward_register.py `_scored`): oldest evidence first, so pids follow the
    order the programs came to exist; one with no event after them."""
    return (row["created_at"] is None, row["created_at"] or 0.0, row["family"], row["version"])


def _row(store: Any, fam: Mapping[str, Any], n: int, *, event: Mapping[str, Any] | None,
         verdict: Mapping[str, Any] | None) -> dict[str, Any]:
    """One version of a panel family as the registry takes it, or `forward_register._Refused` (E3's own causes)."""
    from ..swarm import elane, elane_seal
    from ..swarm.gate import run_sha
    from ..swarm.store import dumps
    from . import forward_register as R

    fid = str(fam["id"])
    version = store.version(fid, int(n))
    if version is None:
        raise R._Refused("version")
    code = version.get("code")
    if not isinstance(code, str):
        raise R._Refused("code")
    sha = R._sha(code)
    if sha != str(version.get("sha") or ""):
        raise R._Refused("sha")
    if event is not None and str(event.get("sha") or "") != sha:
        raise R._Refused("event_sha")
    lane = elane_seal.lane_of_spec(fam.get("spec"))
    if lane is None:
        raise R._Refused("lane")
    needs = needs_of(code)
    if needs is None:
        raise R._Refused("needs")
    params = version.get("params")
    params = {} if params is None else params
    if not isinstance(params, dict):
        raise R._Refused("params")
    held = (verdict or {}).get("bar_passed") or (verdict or {}).get("passed")
    passed = event.get("bar_passed") if event is not None and isinstance(event.get("bar_passed"), bool) else held
    return {"key": f"{fid}@{int(n)}", "family": fid, "version": int(n), "lane": lane,
            "lineage": elane.lineage_key(lane, str(fam.get("lineage") or fid)), "code": code, "params": dict(params),
            "params_text": dumps(params), "sha": sha, "run_sha": run_sha(version),
            "author": str(version.get("author") or ""), "bar_passed": bool(passed),
            "created_at": float(event["at"]) if event is not None else None,
            "evidence": f"event:{int(event['seq'])}" if event is not None else "registry",
            "reason": "train_pass" if passed else "train_fail", "needs": needs,
            "ugroup": UGROUP_PREFIX + str(needs["panel"]), "route": ROUTE, "alpha_f": ALPHA_F}


def scored_rows(store: Any, *, families: Mapping[str, Mapping[str, Any]] | None = None,
                events: Mapping[tuple[str, int], Mapping[str, Any]] | None = None, known: Any = (),
                lookup: bool = False) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """(the registry rows of every panel version judged on the bar whose key is not in `known`, the refused as (key,
    cause)): `forward_register._scored`'s reading of the panel lane's own record. `families`, `events`, `lookup`: as
    that function's (the sync hands them; a version not yet registered is looked up by its family in the whole log
    when `events` holds only the rows after the cursor)."""
    from ..swarm import elane_train, elane_xs
    from . import forward_register as R

    families = R._families(store) if families is None else families
    events = R._earliest(R._scored_events(store)) if events is None else events
    rows: list[dict[str, Any]] = []
    refused: list[tuple[str, str]] = []
    for fid, fam in families.items():
        if not elane_xs.is_panel(fam):
            continue
        versions = elane_train.versions_of(elane_train.record_of(fam))
        older: dict[tuple[str, int], dict[str, Any]] | None = None
        for n in sorted(int(k) for k in versions):
            verdict = versions[str(n)]
            key = f"{fid}@{n}"
            if not judged(verdict) or key in known:
                continue
            event = events.get((fid, n))
            if lookup:                      # the EARLIEST event is the time (D2): one the cursor passed comes first
                if older is None:
                    older = R._earliest(R._scored_events(store, family=fid))
                event = older.get((fid, n), event)
            try:
                rows.append(_row(store, fam, n, event=event, verdict=verdict))
            except R._Refused as exc:
                refused.append((key, exc.cause))
    rows.sort(key=oldest_first)
    return rows, refused


def scored(store: Any) -> list[dict[str, Any]]:
    """The registry rows of every panel version judged on the Train bar (the module docstring, 1): rows as
    `forward_register.scored_versions`', with `route` and `alpha_f` beside. A version the registry refuses is left
    out."""
    return scored_rows(store)[0]


def live_row(store: Any, families: Mapping[str, Mapping[str, Any]], instance: Mapping[str, Any]
             ) -> dict[str, Any] | None:
    """A live PANEL instance the registry does not hold, from the book row's own code and params (reason "live"), as
    `forward_register._live_row` makes an ETF instance's; None for an instance whose program is no panel program
    (that function then reads it). `forward_register._Refused` as that function raises it."""
    from ..equity import LANES
    from ..swarm import elane
    from ..swarm.gate import run_sha
    from ..swarm.store import dumps
    from . import forward_register as R

    code, params = instance.get("code"), instance.get("params")
    needs = needs_of(code)
    if needs is None:
        return None
    if not isinstance(params, dict):
        raise R._Refused("params")
    sha = R._sha(code)
    if run_sha({"sha": sha, "params": params}) != str(instance.get("run_sha") or ""):
        raise R._Refused("run_sha")
    lane = instance.get("lane")
    if lane not in LANES:
        raise R._Refused("lane")
    fid, n = str(instance["family"]), int(instance["version"])
    fam = families.get(fid) or {}
    author = ""
    if store is not None:
        try:
            author = str((store.version(fid, n) or {}).get("author") or "")
        except Exception:  # noqa: BLE001 - the author is ops' note, never a reason to refuse
            author = ""
    return {"key": R.instance_key(instance["id"]), "family": fid, "version": n, "lane": lane,
            "lineage": elane.lineage_key(lane, str(fam.get("lineage") or fid)), "code": code, "params": dict(params),
            "params_text": dumps(params), "sha": sha, "run_sha": str(instance["run_sha"]), "author": author,
            "bar_passed": None, "created_at": None, "evidence": "registry", "reason": "live", "needs": needs,
            "ugroup": UGROUP_PREFIX + str(needs["panel"]), "route": ROUTE, "alpha_f": ALPHA_F}


# ------------------------------------------------------------------------------------------------------------ 2. series
@dataclass(frozen=True)
class Series:
    """A panel forward run as E3's rows read it, one value a written session: `days` (the sessions' int ordinals, as
    `league.equity.screen.Series.days`), `iso` (the same as ISO days), `r`, `w`, `b` (= bench / w), `r15` (the stress
    series in r's currency), the run's own `x` and `x15` beside, and `exits`."""

    days: tuple[int, ...]
    iso: tuple[str, ...]
    r: tuple[float, ...]
    w: tuple[float, ...]
    b: tuple[float, ...]
    r15: tuple[float, ...]
    x: tuple[float, ...]
    x15: tuple[float, ...]
    exits: tuple[int, ...]


def series(result: Mapping[str, Any], *, through: str | None = None) -> Series:
    """A forward run as E3's series (the module docstring, 2): from the run's `daily` rows, the sessions up to
    `through` (an ISO day; every session when None). r = the run's r, w = its exposure, b = bench / w (0 where w is
    0), r15 = r - (x - x15): E3's x = r - w * b is then the run's residual and r15 - w * b its stress residual.
    ValueError (the data's) for a row that is not finite, or one with a benchmark and no exposure."""
    from ..equity.store import as_date, ordinal
    from ..xs import results as XR

    at = {name: XR.DAILY.index(name) for name in ("day", "r", "x", "x15", "w", "bench", "exits")}
    cols: dict[str, list[Any]] = {name: [] for name in ("days", "iso", "r", "w", "b", "r15", "x", "x15", "exits")}
    for row in result.get("daily") or ():
        day = str(row[at["day"]])[:10]
        if through is not None and day > str(through):
            break
        r, x, x15, w, bench = (float(row[at[name]]) for name in ("r", "x", "x15", "w", "bench"))
        if not all(math.isfinite(v) for v in (r, x, x15, w, bench)):
            raise ValueError(f"the run's row of {day} holds a value that is not finite")
        if abs(w) <= _ZERO and abs(bench) > _ZERO:
            raise ValueError(f"the run's row of {day} holds a benchmark and no exposure")
        cols["days"].append(ordinal(as_date(day)))
        cols["iso"].append(day)
        cols["r"].append(r)
        cols["w"].append(w)
        cols["b"].append(bench / w if abs(w) > _ZERO else 0.0)
        cols["r15"].append(r - (x - x15))
        cols["x"].append(x)
        cols["x15"].append(x15)
        cols["exits"].append(int(row[at["exits"]]))
    return Series(**{name: tuple(values) for name, values in cols.items()})


def night_budget(db: sqlite3.Connection, cfg: Mapping[str, Any], now: float) -> float:
    """THE BUDGET of a panel night (the module docstring, 2): `cpu_seconds_night` less the child seconds of every
    `fwd_runs` row that ended in the last `NIGHT_WINDOW_S` (E3's night of the same evening, and an earlier start of
    this one); never under 0."""
    spent = db.execute("SELECT COALESCE(SUM(seconds), 0) FROM fwd_runs WHERE finished>=?",
                       (float(now) - NIGHT_WINDOW_S,)).fetchone()[0]
    return max(0.0, float(cfg["cpu_seconds_night"]) - float(spent or 0.0))


# -------------------------------------------------------------------------------------------------- 2. the panel night
_SHADOW: Any = None


def is_panel_night(shadow: Any) -> bool:
    """Whether `shadow` is the panel night's (`panel_shadow`), not E3's own."""
    return getattr(shadow, "JOB", None) == JOB


def _shadow_class() -> Any:
    """`PanelShadow`, built on first use (league/ops/forward_shadow.py imports this module inside its functions)."""
    global _SHADOW
    if _SHADOW is not None:
        return _SHADOW
    from ..equity import schedule
    from ..equity.store import STORE_DIR as E1_STORE_DIR
    from ..equity.store import MissingData, mint_equity_gate_capability
    from . import forward_shadow
    from .forward_db import ShadowRun

    class PanelShadow(forward_shadow.Shadow):
        """E3's night over the PANEL store (the module docstring, 2). `panel`: the `league.xs.store.PanelStore`
        opened with the capability; `panel_through`: its last session P; `through` and `night_day`: L, the last day
        whose rows are final tonight (the session before P): the night's name. `twin_due`: {instance: the latest
        decision session its twin row was owed tonight | None}, filled by `twin`."""

        JOB = JOB

        def __init__(self, root: str | Path, db: sqlite3.Connection, *, decider: Any,
                     settings: Mapping[str, Any] | None, clock: Callable[[], float] = time.time,
                     fresh: Callable[[], Any] | None = None):
            super().__init__(root, db, decider=decider, settings=settings, clock=clock, fresh=fresh)
            from ..xs import store as XS

            store_root = self.root / E1_STORE_DIR
            self._gate = mint_equity_gate_capability(store_root, GATE_REASON)
            self.panel = XS.PanelStore(store_root, gate=self._gate)
            self.panel_through: dt.date = self.panel.fetched_through
            self.through = self.panel_through
            for _ in range(ROW_LAG):        # ROWS LAG ONE SESSION: the night's day is the last whose rows are final
                self.through = schedule.previous_session(self.through)
            self.night_day = self.through.isoformat()
            self.cfg = {**self.cfg, "cpu_seconds_night": night_budget(db, self.cfg, clock())}
            self.twin_due: dict[str, str | None] = {}
            self._digests: dict[int, bytes] | None = None
            self._order: list[int] = []
            self._place: dict[int, int] = {}
            self._hashes: dict[str, str] = {}
            self._live: dict[str, Any] | None = None

        # ------------------------------------------------------------------------------------------ whose night
        def _mine(self, program: Any) -> bool:
            return is_panel(program)

        def _completed(self, but: int | None = None) -> int:
            """The PANEL programs whose run completed tonight (those of every pid but `but`): a pid with a row for
            the night's day under tonight's engine id. An ETF program's row for that day is E3's night's."""
            return int(self.db.execute(
                "SELECT COUNT(DISTINCT d.pid) FROM fwd_days d JOIN fwd_registry r ON r.pid=d.pid WHERE d.day=? AND "
                "d.engine=? AND d.pid IS NOT ? AND d.bars IS NOT NULL AND r.ugroup LIKE ?",
                (self.night_day, self.engine, None if but is None else int(but), UGROUP_PREFIX + "%")).fetchone()[0])

        def controls(self) -> dict[str, int]:
            """No panel control exists (the module docstring): the controls are E3's night's."""
            return {"groups": 0, "rows": 0, "checks": 0, "restated": 0, "errors": 0, "data_failed": 0, "deferred": 0}

        def finals(self) -> int:
            """The final checkpoint of a stopped program, a panel one too, is E3's night's."""
            return 0

        def marks(self) -> int:
            """THE MORNING MARKS, MADE UP, of the panel's own (`audit_marks`)."""
            live = self.root / LIVE_DB
            return audit_marks(self.db, live, now=self.clock()) if live.exists() else 0

        # ------------------------------------------------------------------------------------------------ the child
        def _forward(self, *, code: str, params: Mapping[str, Any], name: str, start: dt.date,
                     run_key: str | None = None) -> Any:
            """One forward run of the panel kind in the night's decider child (`league.xs.runner.Isolated.forward`),
            its seconds added to `spent`. A program the child would not load is the child's failure (`RunFailed`),
            as E3 reads a refusal. THE CLOCK RULE (`elane_xs.steady`): a run whose runtime shows a decide timeout is
            made again, `elane_xs.CLOCK_RUNS` times at most, and never read: a decide's limit is a second of WALL
            time and this box has stood still for longer, so such a run is not the program's. With a timeout in
            every run of the bound it is the child's failure too (`RunFailed`, with the measured seconds): no row of
            that night, E3's retry, and E3's `run_failed` only when other programs' runs completed."""
            from ..swarm import elane_xs
            from ..xs import runner as XR

            panel = self.panel

            class OneStore(XR.Isolated):
                """The panel's own runner over THE NIGHT'S ONE STORE. `Isolated` opens the store again for every
                run, and each open maps the two bar arrays again (about 120 MB of address space at the real panel's
                size, held until a full collection: the store and its universe name each other). The ops child's
                address space is capped 500 MB above its start: the third run of a night found no room to map
                them (measured: every program after the first two a `data_failed`)."""

                def _store(self, gate: Any = None) -> Any:
                    return panel

            iso = OneStore(self.decider, self.root / E1_STORE_DIR,
                           budget_seconds=float(self.cfg["run_budget_seconds"]), nice=None)
            began = self.clock()
            try:
                return elane_xs.steady(lambda: iso.forward(code, dict(params or {}), name=name, gate=self._gate,
                                                           start=start, run_key=run_key), what="forward run")
            except XR.ProgramRefused as exc:
                raise XR.RunFailed(f"the program does not load: {str(exc)[:200]}") from None
            except (elane_xs.TooSlow, elane_xs.ClockUnsteady) as exc:
                raise XR.RunFailed(str(exc)[:400]) from None
            finally:
                self.spent += max(0.0, self.clock() - began)

        def _panel_days(self) -> list[dt.date]:
            """D1: the panel store's forward days, from `forward_db.t0()`."""
            return [d for d in self.panel.sessions("forward") if d >= self._t0]

        def _canary(self) -> str | None:
            """E3's canary, then the panel kind's (`CANARY` over the panel store's last forward sessions)."""
            why = super()._canary()
            if why is not None:
                return why
            days = self._panel_days()
            if not days:
                return None          # no forward day in the panel store yet: nothing a panel program could run on
            run = self._forward(code=CANARY, params={}, name="forward-xs-canary", start=days[-CANARY_SESSIONS:][0])
            status = run.result.get("status")
            return None if status == "ok" else f"the panel canary ended {status!r}"

        # -------------------------------------------------------------------------------------------------- the run
        def run_program(self, program: Any) -> tuple[Any, Mapping[str, Any]]:
            """(the one run of a panel program on its forward days, what stands for a k 1.5 result: ONE RUN A
            PROGRAM A NIGHT). Raises as E3's: the child's (`RunFailed`), or the data's (`MissingData`,
            `StoreRefused`, `ValueError`)."""
            from ..xs import runner as XR

            program = self._whole(program)
            if program.first_day > self.through:
                raise ValueError(f"{program.key} has no final forward day through {self.night_day}")
            run = self._forward(code=program.code, params=program.params, name=program.key, start=program.first_day)
            status = run.result.get("status")
            if status == "no_data":
                raise MissingData(f"{program.key}: the panel store holds no bar for its run")
            if status not in forward_shadow.STATUSES:
                raise XR.RunFailed(str(run.result.get("reason") or f"the run ended {status!r}"))
            found = series(run.result, through=self.night_day)
            if found.iso and found.iso[0] != program.first_day.isoformat():
                raise ValueError(f"{program.key}: its run does not start at its first day")
            return (ShadowRun(program=program, result=run.result, bars=None, series=found),
                    {"status": status, "stress": STRESS})

        def write(self, run: Any, result15: Mapping[str, Any]) -> dict[str, int]:
            """One transaction a program (E3's `_put`): its rows through the night's day, each with THE BARS HASH of
            the decision behind it, the restated event, the due checkpoints, the disqualified event."""
            found, status = run.series, str(run.result.get("status"))
            if status not in forward_shadow.STATUSES:
                raise ValueError(f"{run.program.key}: a run of status {status!r} has no rows")
            days = list(found.iso)
            if not days:
                return {"new_days": 0, "restated": 0, "checks": 0}
            entered = Counter(str(lot.get("entry_day"))[:10] for lot in run.result.get("lots") or [])
            return self._put(run.program.pid, days, r=found.r, w=found.w, b=found.b, r15=found.r15, r0=None,
                             entries=[entered.get(day, 0) for day in days], exits=found.exits, status=status,
                             bars_at=lambda i: self.bars_hash(days[i]))

        def bars_hash(self, day: str) -> str:
            """THE BARS HASH of the decision behind `day`'s orders (the module docstring): 16 hex over the row
            digests of the `DERIVE_SESSIONS` panel sessions through the session before `day`. ValueError when the
            store holds no session before it."""
            found = self._hashes.get(day)
            if found is not None:
                return found
            from ..equity.store import as_date, ordinal
            from ..xs import config as XC

            if self._digests is None:
                bars = self.panel.bars("forward", history=XC.MIN_HISTORY, run_key=NIGHT_KEY, start=self._t0).bars
                self._order = [int(d) for d in bars.days]
                self._digests = {d: hashlib.sha256(bars.raw[i].tobytes() + bars.adj[i].tobytes()).digest()
                                 for i, d in enumerate(self._order)}
                self._place = {d: i for i, d in enumerate(self._order)}
            at = self._place.get(ordinal(as_date(day)))
            if at is None or at < 1:
                raise ValueError(f"the panel store holds no session before {day} to decide at")
            window = self._order[max(0, at - XC.DERIVE_SESSIONS):at]
            found = hashlib.sha256(b"".join(self._digests[d] for d in window)).hexdigest()[:forward_db.BARS_HEX]
            self._hashes[day] = found
            return found

        # ------------------------------------------------------------------------------------------------ the night
        def night(self) -> dict[str, Any]:
            """E3's night on the panel store, then THE MARKER (written whatever the twins did: a twin that is
            behind is what it says)."""
            receipt = super().night()
            receipt["panel_through"] = self.panel_through.isoformat()
            receipt["marker"] = self._guarded(self.mark)
            return receipt

        def live_book(self) -> dict[str, Any]:
            """The live book as the panel's twins read it (`read_live`), read once a night."""
            if self._live is None:
                self._live = read_live(self.root / LIVE_DB)
            return self._live

        def due_day(self, first: dt.date) -> dt.date | None:
            """The latest decision session, from `first`, whose twin row the lag allows tonight (None before it)."""
            last = self.panel_through
            for _ in range(TWIN_LAG):
                last = schedule.previous_session(last)
            return last if last >= first else None

        def mark(self) -> dict[str, int]:
            """THE MARKER (the module docstring, 4): {"instances", "behind"} (counts)."""
            from . import forward_twins

            book = self.live_book()
            rows: dict[str, dict[str, Any]] = {}
            behind = 0
            for iid, inst in sorted(book["instances"].items()):
                if book["kinds"].get(iid) != KIND or inst.get("retired_at") is not None:
                    continue
                if iid in self.twin_due:
                    due = self.twin_due[iid]
                else:           # no twin was made of it tonight (not registered, another run sha, an error): owed
                    try:
                        found = self.due_day(forward_twins.d_first(inst))
                    except (TypeError, ValueError):
                        found = None
                    due = None if found is None else found.isoformat()
                last = self.db.execute("SELECT MAX(day) FROM fwd_twins WHERE instance=?", (iid,)).fetchone()[0]
                rows[iid] = {"due": due, "last": None if last is None else str(last)}
                behind += int(due is not None and (last is None or str(last) < due))
            write_marker(self.root / E1_STORE_DIR, rows, through=self.panel_through.isoformat(),
                         at=_iso_time(self.clock()))
            return {"instances": len(rows), "behind": behind}

    _SHADOW = PanelShadow
    return _SHADOW


def panel_shadow(root: str | Path, db: sqlite3.Connection, *, decider: Any, settings: Mapping[str, Any] | None,
                 clock: Callable[[], float] = time.time, fresh: Callable[[], Any] | None = None) -> Any:
    """One panel night over the state root `root` and the forward store `db` (the module docstring, 2): E3's
    `forward_shadow.Shadow` on the panel store. `MissingData` / `StoreRefused` when the daily store or the panel
    store cannot be opened."""
    return _shadow_class()(root, db, decider=decider, settings=settings, clock=clock, fresh=fresh)


def _iso_time(now: float) -> str:
    return dt.datetime.fromtimestamp(float(now), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------------------------------------------------- 3. twins
def read_live(live_path: str | Path) -> dict[str, Any]:
    """The live book as the panel's twins read it, in one read-only pass: {"instances": {id: its `eq_instances` row},
    "kinds": {id: its decider kind}, "intents": {instance: {decided day: [its buy and sell rows of the panel's tag by
    iid, each with its lot's symbol and opened day]}}, "rebalances": {instance: {decided day: its `eq_rebalances`
    row}}}. A book that is absent, or from before the panel lane (no `kind` column), holds no panel instance."""
    from . import guard

    out: dict[str, Any] = {"instances": {}, "kinds": {}, "intents": {}, "rebalances": {}}
    path = Path(live_path)
    if not path.exists():
        return out

    def read(db: sqlite3.Connection) -> dict[str, Any]:
        tables = set(guard.ids(db, "SELECT name FROM sqlite_master WHERE type='table'"))
        if "eq_instances" not in tables:
            return out
        columns = {str(row["name"]) for row in guard.rows(db, "PRAGMA table_info(eq_instances)")}
        if "kind" not in columns:
            return out
        for row in guard.rows(db, "SELECT id, family, version, run_sha, kind, created_at, retired_at FROM eq_instances "
                                  "ORDER BY id"):
            out["instances"][str(row["id"])] = row
            out["kinds"][str(row["id"])] = str(row["kind"])
        if {"eq_intents", "eq_lots"} <= tables:
            for row in guard.rows(db, "SELECT i.iid, i.instance, i.decided_day, i.at, i.kind, i.symbol, i.lid, i.usd, "
                                      "l.symbol AS lot_symbol, l.opened_day AS lot_day FROM eq_intents i LEFT JOIN "
                                      "eq_lots l ON l.lid = i.lid WHERE i.kind IN ('buy', 'sell') AND i.tag=? "
                                      "ORDER BY i.iid", (TAG,)):
                out["intents"].setdefault(str(row["instance"]), {}).setdefault(str(row["decided_day"]), []).append(row)
        if "eq_rebalances" in tables:
            for row in guard.rows(db, "SELECT instance, decided_day, called, status, audit, budget, ctx_sha FROM "
                                      "eq_rebalances ORDER BY rid"):
                out["rebalances"].setdefault(str(row["instance"]), {})[str(row["decided_day"])] = row
        return out

    return guard.read(path, read)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def keys(picks: Mapping[str, Any] | None, symbols: Mapping[int, str]) -> dict[str, Any]:
    """A twin decision's order keys from its run's `picks` entry (None: no program order that session): {"sells":
    ["S|SYM|at|<the lot's entry day>", ...] (sorted), "buys": {"B|SYM|at": weight}}, a buy's weight its dollars over
    the pick's budget; `symbols`: {id: the symbol it traded under that day}. KeyError for an id with no symbol."""
    out: dict[str, Any] = {"sells": [], "buys": {}}
    if not isinstance(picks, Mapping):
        return out
    at = str(picks.get("at") or "open")
    budget = _number(picks.get("budget"))
    for _lid, slot, entry in picks.get("sells") or ():
        out["sells"].append(f"S|{symbols[int(slot)]}|{at}|{str(entry)[:10]}")
    for slot, usd in picks.get("buys") or ():
        usd = _number(usd)
        out["buys"][f"B|{symbols[int(slot)]}|{at}"] = None if usd is None or not budget or budget <= 0 else usd / budget
    out["sells"].sort()
    return out


def live_keys(intents: Sequence[Mapping[str, Any]] | None, rebalance: Mapping[str, Any] | None) -> dict[str, Any]:
    """A live decision's order keys, in `keys`' shape: from the instance's `eq_intents` rows of that session with the
    panel's tag (`read_live`): a buy's weight is its dollars over the decision's budget (`eq_rebalances.budget`);
    a sell is kept iff it names a lot. A row's status is not read (a buy the send refused was still decided)."""
    out: dict[str, Any] = {"sells": [], "buys": {}}
    budget = _number((rebalance or {}).get("budget"))
    for row in intents or ():
        at = str(row.get("at") or "open")
        if at not in ("open", "close"):
            continue
        if row.get("kind") == "buy" and row.get("symbol"):
            usd = _number(row.get("usd"))
            out["buys"][f"B|{str(row['symbol']).upper()}|{at}"] = \
                None if usd is None or not budget or budget <= 0 else usd / budget
        elif row.get("kind") == "sell" and row.get("lid") is not None and row.get("lot_symbol"):
            out["sells"].append(f"S|{str(row['lot_symbol']).upper()}|{at}|{str(row.get('lot_day') or '')[:10]}")
    out["sells"].sort()
    return out


def agree(live: Mapping[str, Any], twin: Mapping[str, Any]) -> bool:
    """Whether a live session's keys and its twin's agree (the module docstring, 3): the same sells, the same buys,
    and every buy's weight within `WEIGHT_TOL` of its twin's. A session with no program order on either side agrees;
    a buy whose weight cannot be read agrees with nothing."""
    if Counter(live.get("sells") or ()) != Counter(twin.get("sells") or ()):
        return False
    mine, theirs = dict(live.get("buys") or {}), dict(twin.get("buys") or {})
    if set(mine) != set(theirs):
        return False
    return all(mine[key] is not None and theirs[key] is not None and abs(mine[key] - theirs[key]) <= WEIGHT_TOL
               for key in mine)


def _flat(found: Mapping[str, Any]) -> str:
    """A side's keys as `fwd_twins` keeps them: a JSON list, each buy with its weight to four places."""
    buys = [f"{key}|{'?' if weight is None else format(weight, '.4f')}" for key, weight in sorted(found["buys"].items())]
    return json.dumps([*found["sells"], *buys])


def _hex(value: Any) -> str | None:
    return str(value)[:forward_db.BARS_HEX] if isinstance(value, str) and value else None


def twin(root: str | Path, db: sqlite3.Connection, shadow: Any, inst: Mapping[str, Any], book: Mapping[str, Any],
         program: Any, out: dict[str, Any], *, now: float, late: bool = False) -> None:
    """THE TWIN OF ONE LIVE INSTANCE on a night (the module docstring, 3; league/ops/forward_twins.py `_one_instance`
    hands every registered instance here once its run sha is checked). EACH NIGHT TWINS ITS OWN LANE: E3's night
    writes nothing for a panel instance and the panel night nothing for an ETF one. For a panel instance on the panel
    night: its `fwd_twins` rows (one a decision session the lag allows, in day order), the night's `fwd_part` row and
    the twin's residual beside (`BESIDE_KEY`), counted in `out` as E3's (`forward_twins.FINISH_KEYS`). A child that
    fails the run is one `twin_interrupted` event and no row; past the night's deadline the instance is `deferred`."""
    if not (is_panel(program) and is_panel_night(shadow)):
        return
    from ..equity import schedule
    from . import forward_stats, forward_twins

    iid, pid = str(inst["id"]), int(program.pid)
    live = shadow.live_book()
    intents, rebalances = live["intents"].get(iid, {}), live["rebalances"].get(iid, {})
    lots = book["lots"].get(iid, [])
    runs = forward_twins._epochs(db, inst, book, pid, now=now)
    have = {str(r[0]) for r in db.execute("SELECT day FROM fwd_twins WHERE instance=?", (iid,))}
    night = shadow.night_day
    parted = db.execute("SELECT 1 FROM fwd_part WHERE instance=? AND through=?", (iid, night)).fetchone() is not None
    shadow.twin_due[iid] = None
    for k, (first, retired) in enumerate(runs):
        current = k == len(runs) - 1
        end = shadow.due_day(first)
        if end is None:
            continue
        if current and retired is None:
            shadow.twin_due[iid] = end.isoformat()
        if not current:
            end = min(end, schedule.previous_session(runs[k + 1][0]))
        elif retired is not None:
            stop = forward_twins._last_needed(lots, retired)
            end = end if stop is None else min(end, stop)
        wanted = forward_twins._sessions(first, end)
        if not wanted or (all(day in have for day in wanted) and (parted or retired is not None)):
            continue
        if late:
            out["deferred"] += 1
            return
        start = schedule.next_session(first)
        if start > shadow.panel_through:
            continue
        try:
            run = shadow._forward(code=shadow._whole(program).code, params=program.params, name=program.key,
                                  start=start, run_key=iid)
        except Exception as exc:  # noqa: BLE001 - the child's failure is an interruption; the data's the caller's
            if not any(base.__name__ in forward_twins.RUN_FAILURES for base in type(exc).__mro__):
                raise
            forward_db.event(db, "twin_interrupted", pid=pid, day=night, at=float(now), once=iid, payload={
                "instance": iid, "why": f"the decider child failed the twin's run ({type(exc).__name__})"})
            out["interrupted"] += 1
            return
        if run.result.get("status") not in ("ok", "disqualified"):
            raise ValueError(f"{iid}: the twin's run ended {run.result.get('status')!r}")
        universe = shadow.panel.universe()
        aid_of = {int(slot): int(aid) for slot, aid in zip(run.slice.bars.ids, run.slice.aids[int(run.slice.bars.ref):])}

        def named(slots: Any, day: str) -> dict[int, str]:
            return {int(slot): universe.symbol(aid_of[int(slot)], day) for slot in slots}

        picks = {str(pick.get("decided")): pick for pick in run.result.get("picks") or () if isinstance(pick, Mapping)}
        rows, kept = [], set(wanted)
        for day in wanted:
            if day not in kept or day in have:
                continue
            pick = picks.get(day)
            slots = [] if pick is None else [*(s[1] for s in pick.get("sells") or ()), *(b[0] for b in pick.get("buys") or ())]
            theirs = keys(pick, named(slots, day))
            mine = live_keys(intents.get(day), rebalances.get(day))
            row = rebalances.get(day) or {}
            if retired is not None and day >= retired.isoformat():
                agreed, why = None, "retired"
            elif row.get("audit") == "mismatch":
                agreed, why = None, "audit"
            else:
                agreed, why = agree(mine, theirs), None
            seen, read = _hex(row.get("ctx_sha")), _hex((pick or {}).get("ctx_sha"))
            rows.append((iid, day, pid, _flat(mine), _flat(theirs), None if agreed is None else int(agreed), why,
                         float(now), seen, read, forward_twins.cause(agreed, seen, read)))
        last = min(shadow.through, retired) if retired is not None else shadow.through
        entered = [lot for lot in (run.result.get("lots") or []) if isinstance(lot, Mapping)
                   and start.isoformat() <= str(lot.get("entry_day") or "") <= last.isoformat()]
        part = forward_twins.participation(
            [lot for lot in lots if start.isoformat() <= str(lot.get("opened_day") or "") <= last.isoformat()],
            [{"symbol": named([lot["id"]], str(lot["entry_day"]))[int(lot["id"])], "entry_day": lot.get("entry_day"),
              "entry_at": lot.get("entry_at")} for lot in entered])
        found = series(run.result, through=night)
        with db:    # one transaction a run of the instance: its sessions in day order, and the night's participation
            db.executemany("INSERT OR IGNORE INTO fwd_twins(instance, day, pid, live_keys, shadow_keys, agree, why, at, "
                           "live_bars, shadow_bars, cause) VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows)
            if current:
                db.execute("INSERT OR IGNORE INTO fwd_part(instance, through, pid, matched, missed, extra, at) "
                           "VALUES(?,?,?,?,?,?,?)",
                           (iid, night, pid, part["matched"], part["missed"], part["extra"], float(now)))
                held = forward_db.kv_get(db, BESIDE_KEY, {})
                held = dict(held) if isinstance(held, Mapping) else {}
                held[iid] = {"of": "its shadow twin (the Gym sleeve, the model's costs)", "from": start.isoformat(),
                             "through": found.iso[-1] if found.iso else None, "sessions": len(found.iso),
                             "sum_x": math.fsum(found.x), "sum_x15": math.fsum(found.x15),
                             "t_x": forward_stats.t_stat(list(found.x)), "at": float(now)}
                forward_db.kv_put(db, BESIDE_KEY, held)
        have.update(row[1] for row in rows)
        out["twins"] += len(rows)
        out["disagreed"] += sum(1 for row in rows if row[5] == 0)
        out["unreadable"] += sum(1 for row in rows if row[5] is None)


def rebalance_agreement(rows: Sequence[Mapping[str, Any]], needs: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Beside, for the reports, never a rule: an instance's REBALANCE sessions agreed k of n. `rows`: its `fwd_twins`
    rows ({"day", "agree"}); `needs`: its program's NEEDS (a rebalance session is one its program is asked at:
    `league.xs.config.decision_due`). {"sessions" (read), "agreed", "disagreed": [the days that differ],
    "unreadable"}; every count None when the NEEDS cannot be read."""
    from ..equity.store import as_date
    from ..xs import config as XC

    out: dict[str, Any] = {"sessions": None, "agreed": None, "disagreed": None, "unreadable": None}
    try:
        rule, weekday = str((needs or {})["rebalance"]), int((needs or {}).get("weekday") or 0)
        called = [row for row in rows if XC.decision_due(as_date(str(row["day"])), rule, weekday)]
    except (KeyError, TypeError, ValueError):
        return out
    read = [row for row in called if row["agree"] is not None]
    return {"sessions": len(read), "agreed": sum(1 for row in read if int(row["agree"]) == 1),
            "disagreed": sorted(str(row["day"]) for row in read if int(row["agree"]) == 0),
            "unreadable": len(called) - len(read)}


# ------------------------------------------------------------------------------------------------------------ 4. marker
def write_marker(root: str | Path, instances: Mapping[str, Mapping[str, Any]], *, through: str, at: str) -> Path:
    """Rewrite the twin marker (the module docstring, 4) under the daily store `root` (`<state>/equity-daily`):
    `league.xs.book.TWINS_FILE`, version `TWINS_VERSION`; atomic, owner-only. INSTANCE IDS AND DAYS ONLY: each row is
    cut to `MARKER_ROW`, and a value that is no ISO day (or None) is a ValueError before anything is written."""
    from ..xs import book
    from .context import write_json

    def day(value: Any) -> str | None:
        if value is None:
            return None
        return dt.date.fromisoformat(str(value)).isoformat()

    doc = {"version": book.TWINS_VERSION, "through": day(through), "at": str(at),
           "instances": {str(key): {name: day(row.get(name)) for name in MARKER_ROW}
                         for key, row in sorted(instances.items())}}
    if doc["through"] is None:
        raise ValueError("the marker names the panel store's last session")
    return write_json(Path(root) / book.TWINS_FILE, doc)


# ------------------------------------------------------------------------------------------------------------- the marks
def audit_marks(db: sqlite3.Connection, live_path: str | Path, *, now: float) -> int:
    """THE MORNING MARKS of the panel lane (the module docstring): for each live panel decision whose morning re-read
    was a mismatch (`eq_rebalances.audit`), one `audit_mismatch` event on that day of its program's registry row (a
    panel row whose forward days hold the day), once a (pid, day); how many were written. `sqlite3.Error` when the
    book cannot be read."""
    from . import forward_twins

    written = 0
    for iid, rows in sorted(read_live(live_path)["rebalances"].items()):
        program = None
        for day, row in sorted(rows.items()):
            if row.get("audit") != "mismatch":
                continue
            if program is None:
                program = forward_db.program(db, forward_twins.registry_key(iid))
            if program is None or not is_panel(program):
                break
            try:
                when = dt.date.fromisoformat(day)
            except ValueError:
                continue
            if program.first_day > when:
                continue
            seq = forward_db.event(db, "audit_mismatch", pid=program.pid, day=day, at=float(now), once="audit",
                                   payload={"why": "the morning re-read of the bars this panel decision used was a "
                                                   "mismatch: the day leaves the counted days", "instance": iid})
            written += 1 if seq else 0
    if db.in_transaction:
        db.commit()
    return written


# ------------------------------------------------------------------------------------------------------------ 5. alarms
def _lane_on(settings: Mapping[str, Any] | None) -> bool:
    """Whether `elane.panel.mode` is set above "off" (the SETTING, as the panel's data jobs read it). A switch that
    cannot be read is off."""
    try:
        from ..swarm import elane_xs

        return elane_xs.cfg(settings)["mode"] != "off"
    except Exception:  # noqa: BLE001
        return False


def raised(alarm: Any, settings: Mapping[str, Any] | None) -> bool:
    """Whether an FX alarm is raised as the settings stand: `elane.forward.mode` above "off" AND `elane.panel.mode`
    above "off"."""
    try:
        on = forward_db.mode(settings) != "off"
    except Exception:  # noqa: BLE001 - an unreadable block is "off"
        on = False
    return str(alarm) in ALARMS and on and _lane_on(settings)


def _alarm(alarm: str, text: str, subject: str = "", level: str | None = None) -> dict[str, Any]:
    head = f"{alarm} {subject}".strip()
    return {"id": alarm, "level": level or ALARMS[alarm], "text": f"{head}: {text}", "new": True}


def _marker_rows(root: Path) -> list[dict[str, Any]]:
    """FX1."""
    from ..equity import schedule
    from ..xs import book
    from .context import read_json

    manifest = read_json(root / STORE_DIR / PANEL_MANIFEST, None)
    if not isinstance(manifest, Mapping) or not manifest.get("fetched_through"):
        return []
    through = dt.date.fromisoformat(str(manifest["fetched_through"])[:10])
    doc = read_json(root / STORE_DIR / book.TWINS_FILE, None)
    if not isinstance(doc, Mapping) or doc.get("version") != book.TWINS_VERSION or not doc.get("through"):
        return [_alarm("FX1", f"no twin marker though the panel store is through {through.isoformat()}: the forward_xs "
                              "job has not completed a night (its receipt says why); mode live reads as gate until it "
                              "does", "marker")]
    out = []
    marked = dt.date.fromisoformat(str(doc["through"])[:10])
    if marked < through:
        behind, day = 0, through
        while day > marked and behind < schedule.HORIZON_DAYS:
            day, behind = schedule.previous_session(day), behind + 1
        out.append(_alarm("FX1", f"the twin marker is through {marked.isoformat()} and the panel store through "
                                 f"{through.isoformat()} ({behind} sessions behind): the forward_xs job did not complete "
                                 "(its receipt says why); from two sessions the panel lane holds every open", "marker"))
    for key, row in sorted((doc.get("instances") or {}).items()):
        if not isinstance(row, Mapping) or row.get("due") is None:
            continue
        if row.get("last") is None or str(row["last"]) < str(row["due"]):
            out.append(_alarm("FX1", f"its shadow twin is behind: its last row is of {row.get('last') or 'no session'} "
                                     f"and one of {row['due']} was due", f"instance {key}"))
    return out


def _disagreed_rows(db: sqlite3.Connection, since: float) -> list[dict[str, Any]]:
    """FX2: the rebalance sessions written since `since` whose live and twin orders disagree."""
    from ..equity.store import as_date
    from ..xs import config as XC
    from . import guard

    out = []
    for row in guard.rows(
            db, "SELECT t.instance, t.day, t.cause, r.needs FROM fwd_twins t JOIN fwd_registry r ON r.pid=t.pid WHERE "
                "r.ugroup LIKE ? AND t.agree=0 AND t.at>=? ORDER BY t.instance, t.day",
            (UGROUP_PREFIX + "%", float(since))):
        try:
            needs = json.loads(row["needs"])
            due = XC.decision_due(as_date(str(row["day"])), str(needs["rebalance"]), int(needs.get("weekday") or 0))
        except (TypeError, ValueError, KeyError):
            due = True      # a row whose NEEDS cannot be read is told, not hidden
        if due:
            cause = row["cause"] if row["cause"] in forward_db.CAUSES else "unknown"
            out.append(_alarm("FX2", f"the live and the twin orders of the rebalance session {row['day']} disagree "
                                     f"(cause: {cause}); a disagreement is data, counted in its A14 reading",
                              f"instance {row['instance']} {row['day']}"))
    return out


def _stale_rows(db: sqlite3.Connection) -> list[dict[str, Any]]:
    """FX3: the last two panel nights."""
    from . import guard

    nights: list[dict[str, Any]] = []
    for row in guard.rows(db, "SELECT through, stale FROM fwd_runs WHERE through IS NOT NULL AND job=? ORDER BY run "
                              "DESC LIMIT 20", (JOB,)):
        if all(row["through"] != held["through"] for held in nights):
            nights.append(row)
    nights = sorted(nights, key=lambda row: row["through"], reverse=True)[:2]
    if len(nights) < 2 or not (int(nights[0]["stale"] or 0) > 0 and int(nights[1]["stale"] or 0) > 0):
        return []
    new, old = nights
    return [_alarm("FX3", f"panel programs were left stale two panel nights running ({old['through']}: "
                          f"{int(old['stale'])}, {new['through']}: {int(new['stale'])}): what E3's night leaves of the "
                          "night's budget does not cover the panel registry", "stale")]


def alarms(db: sqlite3.Connection, root: str | Path, *, now: float, since: float,
           settings: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """THE ALARMS (the module docstring, 5) as rows of the forward report: {"id", "level", "text", "new"}; [] while
    either switch is off. Each is read on its own: one that cannot be read is an info row under its id that says so.
    Never raises."""
    if not raised("FX1", settings):
        return []
    root = Path(root)
    out: list[dict[str, Any]] = []
    for alarm, read in (("FX1", lambda: _marker_rows(root)), ("FX2", lambda: _disagreed_rows(db, float(since))),
                        ("FX3", lambda: _stale_rows(db))):
        try:
            out += read()
        except Exception as exc:  # noqa: BLE001
            out.append(_alarm(alarm, f"this alarm could not be read ({type(exc).__name__})", "unread", level="info"))
    return out


def beside(root: str | Path) -> dict[str, dict[str, Any]]:
    """What the forward record says BESIDE a live panel program, for the dlane report (never a rule): {instance:
    {"residual": the twin's residual over the instance's own sessions (`BESIDE_KEY`: {"of", "from", "through",
    "sessions", "sum_x", "sum_x15", "t_x"}) | None, "rebalance": `rebalance_agreement` of its `fwd_twins` rows}} for
    every instance whose registry row is a panel row. {} with no forward store. Read-only; it raises what the store
    raises (the report says "unread")."""
    from . import guard

    root = Path(root)
    if not (root / forward_db.DB).exists():
        return {}
    db = forward_db.open_db(root, readonly=True)
    try:
        held = forward_db.kv_get(db, BESIDE_KEY, {})
        held = held if isinstance(held, Mapping) else {}
        rows: dict[str, list[dict[str, Any]]] = {}
        needs: dict[str, Any] = {}
        for row in guard.rows(db, "SELECT t.instance, t.day, t.agree, r.needs FROM fwd_twins t JOIN fwd_registry r ON "
                                  "r.pid=t.pid WHERE r.ugroup LIKE ? ORDER BY t.instance, t.day",
                              (UGROUP_PREFIX + "%",)):
            rows.setdefault(str(row["instance"]), []).append({"day": row["day"], "agree": row["agree"]})
            needs[str(row["instance"])] = row["needs"]
        out = {}
        for iid in sorted(set(rows) | set(held)):
            try:
                own = json.loads(needs[iid]) if iid in needs else None
            except (TypeError, ValueError):
                own = None
            residual = held.get(iid)
            out[iid] = {"residual": {k: v for k, v in residual.items() if k != "at"} if isinstance(residual, Mapping)
                        else None, "rebalance": rebalance_agreement(rows.get(iid, []), own)}
        return out
    finally:
        db.close()


# --------------------------------------------------------------------------------------------------------------- the job
def run(ctx: Any) -> dict[str, Any]:
    """THE JOB (league/ops/registry.py, after `equity_panel`): skipped when `forward_db.mode` is "off", when
    `elane.panel.mode` is "off", inside 09:00-17:30 New York on a session, with no panel store, and WHERE E3'S OWN JOB
    SKIPS: while the House's daily store holds no forward day (the panel night's preflight runs E3's canary on that
    store first, and with no forward day in it the night FAILED where E3's skipped: three failed receipts, three
    warnings and a `night_failed` event on the first evening the lane was at "train", measured in the rehearsal on
    the House's box), and while the panel store holds no session whose rows are final (its last session, less the
    row lag, is before the first forward day). Else the panel night (`panel_shadow(...).night()`) in the forward
    job's own decider child, closed in `finally`. A preflight that fails is {"status": "failed"} (nobody run or
    marked; the runner starts it again inside its grace); a store that cannot be opened is a failed receipt too. A
    night with failures of the House's own is one warning."""
    import contextlib

    from ..equity.store import EquityStore, MissingData, StoreRefused
    from ..swarm import settings as swarm_settings
    from . import forward_shadow

    root = Path(ctx.root)
    settings = swarm_settings.load(root, config=getattr(ctx, "config", None))
    if forward_db.mode(settings) == "off":
        return {"status": "skipped", "why": "elane.forward.mode is off"}
    if not _lane_on(settings):
        return {"status": "skipped", "why": "the panel lane is off (elane.panel.mode)"}
    if forward_shadow.quiet(ctx.now()):
        return {"status": "skipped", "why": "inside 09:00-17:30 New York time on a session: the night's run does it"}
    store_root = root / STORE_DIR
    if not (store_root / PANEL_VERSION).is_file() or not (store_root / "VERSION").is_file():
        return {"status": "skipped", "why": "no panel store yet: no panel forward day"}
    try:
        through = EquityStore(store_root).fetched_through
    except (MissingData, StoreRefused) as exc:
        return {"status": "failed", "error": f"the equity store could not be opened ({forward_shadow._why(exc)})"}
    if through < forward_db.t0():
        return {"status": "skipped", "why": f"no forward day in the House's daily store yet (its last day is "
                                           f"{through.isoformat()}): the night's canary has no day to run on"}
    db = forward_db.open_db(root)
    children: list[Any] = []

    def fresh() -> Any:
        """A newly started child for THE RETRY: the old one is closed first (one child at a time)."""
        while children:
            with contextlib.suppress(Exception):
                children.pop().close()
        children.append(forward_shadow._decider(root))
        return children[-1]

    try:
        shadow = panel_shadow(root, db, decider=fresh(), settings=settings, clock=ctx.now, fresh=fresh)
        if shadow.through < forward_db.t0():
            return {"status": "skipped", "why": f"no final forward day in the panel store yet (its last session is "
                                               f"{shadow.panel_through.isoformat()}, and a panel row is final a "
                                               "session later)"}
        receipt = shadow.night()
        failures = forward_shadow.house_failures(receipt)
        if isinstance(receipt.get("marker"), Mapping) and "error" in receipt["marker"]:
            failures.append(f"the twin marker raised {str(receipt['marker']['error'])[:60]}")
        if failures:
            ctx.alert("warning", f"forward_xs: the panel night of {receipt['through']} had failures of the House's own "
                                 f"({'; '.join(failures)}): no program is marked for them, and the next night's "
                                 "recompute fills what was left out")
        return receipt
    except forward_shadow.NightFailed as exc:
        return {"status": "failed", "error": f"the preflight failed, nobody was run or marked: {exc}"}
    except (MissingData, StoreRefused) as exc:
        return {"status": "failed", "error": f"the panel store could not be opened ({forward_shadow._why(exc)})"}
    finally:
        for child in children:
            with contextlib.suppress(Exception):
                child.close()
        db.close()


__all__ = ["UGROUP_PREFIX", "UGROUP", "ROUTE", "ALPHA_F", "WEIGHT_TOL", "GROUP_PREFIX", "GROUPS", "JOB", "E3_JOB",
           "KIND", "TAG", "ROW_LAG", "TWIN_LAG", "UNREADABLE", "CANARY", "ALARMS", "BESIDE_KEY", "MARKER_KEYS",
           "MARKER_ROW", "Series", "is_panel", "registered", "engine_label", "group", "judged", "needs_of",
           "look_key", "scored_rows", "scored", "live_row", "series", "night_budget", "is_panel_night", "panel_shadow",
           "read_live", "keys", "live_keys", "agree", "twin", "rebalance_agreement", "write_marker", "audit_marks",
           "raised", "alarms", "beside", "run"]
