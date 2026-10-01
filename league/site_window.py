"""The swarm window (Oct 1, 2026): where each agent stands in the game, how far the families have come since the reset,
and why each real position was opened and closed, for the site's `levels` and `rationale` blocks (`league/publish.py`
`site_levels` and `site_rationale` allowlist them; the design is the swarm-window spec).

    levels     {as_of, agents: [{id, level}], funnel: {since, born, practice, validation, tuition, incubator, looks,
                looks_passed, candidate, probe, sized, retired, calibration, live_test}}
    rationale  {as_of, agents: [{id, thesis}], trades: [{id, route, open_why, close_why, exit, max_loss_usd}]}

THE LEVELS. The main stairs: Train (the Gym) -> Validation -> Tuition (D2: one real contract that measures fills, never
evidence) -> Candidate (past the holdout look) -> Probe -> Sized. The side path off Train: Practice (shadow trades on live
quotes) -> Incubator (real money at tuition size, never evidence), which never reaches the top. An agent's level now
(`level_of`) is the first rule that holds: it holds open real money (the highest route of its open positions, so a
retired agent still holding money stands on that money's step); its band is Candidate, Probe or Sized; it is retired;
it has an active tuition instance; an active incubator instance; a validation run on the current evaluator; it practises
now; else Train. A level never contradicts the band the page shows (`LEVELS_BY_BAND`, the site's own rule).

THE FUNNEL (`funnel`): families since `since` (`performance.start_at`, the reset), each count a union: a family counts at
a level when it reached that level or any higher one on its track (the higher levels require the lower ones), so each
chain only narrows. The tracks (`publish.FUNNEL_CHAINS`): Sized -> Probe -> Candidate -> Validation -> born; Tuition ->
Validation, a branch of its own (the swarm window's safety review, Oct 1, 2026: a holdout look needs no tuition lot
first, and a failed look means none follows, so Tuition counts only the families that held a D2 tuition instance or
position, never one that only looked or reached Candidate); Incubator -> Practice -> born; Retired -> born. A count
whose source cannot be read is None (the page shows a dash), never a guess. `looks` and `looks_passed` count holdout
looks, not families. `calibration` and `live_test` count the House's own real positions. Every family in the swarm's
store was born after the reset (2,246 of 2,246 on Oct 1, 2026), so `born` is the families born since it.

THE RATIONALE. A thesis is the family's FULL mechanism from the swarm store (a retired family keeps its reason) through
`public.thesis_text`: whole sentences only, no number (no digit or numeral of any script, no number word, cardinal,
ordinal or run together, "one" only as a pronoun: `public.numbered`, `public.plain_glyphs`), no colon, no bracket, no code
mark, no parameter name (every version's PARAMS overrides, every version's program's PARAMS and the PARAMS of every live
instance of the family, written with underscores, spaces, hyphens or nothing between its words; but a name the agent's
public id already spells word for word, `public.unspelled`: "qqq_flat" in `googl-lags-msft-ai-cloud-qqq-flat`). A family
whose current program, or whose live instances, cannot be read gets no thesis. A trade's `open_why` is its opening
order's stored tag and its `close_why` the reason its own program gave its close, each through `public.tag_text`; both
are None on the House's rows, and `close_why` is None unless the agent closed it itself (`exit` "agent"). `route` is
the route it was opened on: tuition and incubator from the book's own flags; Probe or Sized from the family's band when
it opened (the newest `swarm.band` move before the book's opening time, so a Probe position whose instance has since
moved to Sized still says Probe; the instance's band now when no move since the reset says). `exit` is an enum, never
text; `max_loss_usd` is the position's maximum loss at open. Never a price, a strike, a mark, a parameter's value, a
threshold, a program, a sketch, a private note, `positions.note` or the raw `positions.reason`. A trade's reason on the
public tape (`agent.trade` `why`) is filtered against the same names (`tape_names`, `publish.tape_why`).

Every store is read read-only (`mode=ro`, a one-second timeout), each read guarded so a failure costs only its part.
Nothing in `league/live` or `league/gym` is imported: the constants below are spelled here and held equal to the live
modules' own by their tests. Standard library only (and `trading_profit`, which imports nothing live).
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import trading_profit

#: The live book's file in the House's state root (`league.live.state.STATE_FILE`).
LIVE_FILE = "live.sqlite"
#: The practice league's record in the House's state root (`league.live.observe.FILE`).
OBSERVE_FILE = "observe.sqlite"
#: The incubator's instance suffix (`league.live.real.INCUBATOR_SUFFIX`).
INCUBATOR_SUFFIX = ":i"
#: The House's calibration round trips (`league.live.calibration.FAMILY`) and its live test (`league.live.house_test.FAMILY`).
CALIBRATION_FAMILY = "house:calibration"
HOUSE_TEST_FAMILY = "house:rebound-live"
#: The swarm's store (`league.swarm.DB_NAME`).
SWARM_DB = "swarm.sqlite"

LEVELS = ("train", "practice", "validation", "incubator", "tuition", "candidate", "probe", "sized", "retired")
#: The levels each band may stand on (the site's `LEVELS_BY_BAND`): a band above the Gym is its own level; a Gym family is
#: somewhere on the way up; a retired family is retired unless it still holds open real money.
LEVELS_BY_BAND = {"gym": ("train", "practice", "validation", "incubator", "tuition"), "candidate": ("candidate",),
                  "probe": ("probe",), "sized": ("sized",), "retired": ("retired", "tuition", "incubator", "probe", "sized")}
#: The funnel's keys, in the site's order (`FUNNEL_KEYS`).
FUNNEL_KEYS = ("since", "born", "practice", "validation", "tuition", "incubator", "looks", "looks_passed", "candidate", "probe",
               "sized", "retired", "calibration", "live_test")
ABOVE_GYM = ("candidate", "probe", "sized")
OPEN_STATUSES = ("open", "awaiting_expiry")
#: An order's reason when its program gave none (`league/live/step.py`): no reason at all.
NO_REASON = ("program",)
TIMEOUT = 1.0


def _epoch(value: Any) -> float | None:
    """Epoch seconds of an ISO stamp (with a zone, or UTC when it has none) or of a number; None when unreadable."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        at = dt.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return (at if at.tzinfo else at.replace(tzinfo=dt.timezone.utc)).timestamp()


def _since(value: Any, since: float) -> bool:
    at = _epoch(value)
    return at is not None and at >= since


def _connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=TIMEOUT)
    db.row_factory = sqlite3.Row
    return db


def _loads(text: Any, default: Any = None) -> Any:
    try:
        return json.loads(text) if text not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _house(family: Any) -> bool:
    return str(family or "").startswith("house:")


# ------------------------------------------------------------------------------------ the reads
def read_swarm(root: str | Path, ids: Sequence[str], since: float) -> dict[str, Any] | None:
    """The swarm store's part (read-only): every family's band and dates, the shown families' full mechanisms, states
    and parameter names, the validation runs, the looks and the band moves since `since`. None when it cannot be read."""
    from .swarm import sitefeed

    path = Path(root) / SWARM_DB
    if not path.is_file():
        return None
    try:
        with closing(_connect(path)) as db:
            db.execute("BEGIN")
            fams = {r["id"]: dict(r) for r in db.execute("SELECT id, band, born_at, retired_at FROM families")}
            shown: dict[str, dict[str, Any]] = {}
            wanted = [i for i in dict.fromkeys(ids) if i in fams]
            for start in range(0, len(wanted), 500):
                chunk = wanted[start:start + 500]
                for r in db.execute(f"SELECT id, mechanism, state FROM families WHERE id IN ({','.join('?' * len(chunk))})", chunk):
                    shown[r["id"]] = {"mechanism": r["mechanism"], "state": _loads(r["state"], {}) or {}}
            names = sitefeed.param_names(db, root, wanted)
            validated = {r["family"] for r in db.execute(
                "SELECT family, at FROM runs WHERE window='validation' AND status='ok'") if _since(r["at"], since)}
            looks = [dict(r) for r in db.execute("SELECT family, at, passed FROM looks") if _since(r["at"], since)]
            moves = []
            for r in db.execute("SELECT family, at, payload FROM events WHERE kind='swarm.band' ORDER BY seq"):
                if r["family"] and _since(r["at"], since):
                    moves.append((r["family"], (_loads(r["payload"], {}) or {}).get("band_to"), _epoch(r["at"])))
            db.rollback()
    except sqlite3.Error:
        return None
    return {"fams": fams, "shown": shown, "names": names, "validated": validated, "looks": looks, "moves": moves}


def read_live(state_root: str | Path) -> dict[str, Any] | None:
    """The live book's part (read-only): each instance's family, flags, mode, band and dates (never its program here),
    and each position's family, instance, flags, status and opening time (never a price). Empty when there is no book
    (the House never traded real money); None when it cannot be read."""
    path = Path(state_root) / LIVE_FILE
    if not path.is_file():
        return {"instances": [], "positions": []}
    try:
        with closing(_connect(path)) as db:
            db.execute("BEGIN")
            instances = [dict(r) for r in db.execute(
                "SELECT id, family, run_sha, band, tuition, mode, created_at, retired_at FROM instances")]
            positions = [dict(r) for r in db.execute("SELECT pid, instance, family, status, tuition, opened_at FROM positions")]
            db.rollback()
    except sqlite3.Error:
        return None
    return {"instances": instances, "positions": positions}


_INSTANCE_NAMES: dict[tuple[str, str, str], tuple[str, ...]] = {}


def instance_names(state_root: str | Path, ids: Iterable[str]) -> dict[str, tuple[str, ...]] | None:
    """{instance id: its program's parameter names} (the PARAMS keys of `instances.code` and the keys of its stored
    params), read-only and cached by (book, instance, run sha); None when the book cannot be read."""
    from .swarm import public

    wanted = sorted({str(i) for i in ids if i})
    path = Path(state_root) / LIVE_FILE
    if not wanted or not path.is_file():
        return {}
    out: dict[str, tuple[str, ...]] = {}
    try:
        with closing(_connect(path)) as db:
            for start in range(0, len(wanted), 500):
                chunk = wanted[start:start + 500]
                marks = ",".join("?" * len(chunk))
                for r in db.execute(f"SELECT id, run_sha FROM instances WHERE id IN ({marks})", chunk):
                    key = (str(path), str(r["id"]), str(r["run_sha"] or ""))
                    if key in _INSTANCE_NAMES:
                        out[r["id"]] = _INSTANCE_NAMES[key]
                        continue
                    row = db.execute("SELECT code, params FROM instances WHERE id=?", (r["id"],)).fetchone()
                    given = _loads(row["params"], {}) if row is not None else {}
                    names = set(public.param_names_of(row["code"] if row is not None else ""))
                    names.update(str(k) for k in (given if isinstance(given, Mapping) else {}))
                    if len(_INSTANCE_NAMES) > 20_000:
                        _INSTANCE_NAMES.clear()
                    out[r["id"]] = _INSTANCE_NAMES[key] = tuple(sorted(names))
    except sqlite3.Error:
        return None
    return out


def read_practice(state_root: str | Path, since: float) -> set[str] | None:
    """The families that practised since `since`, read-only from `observe.sqlite`: a practice row begun since
    (`practice.first_at`), or a practice trade or event recorded since (`trades`, `events`: an evidence reset completes
    the practice rows and their cohorts but keeps what was traded). Empty when there is no record, None when it cannot be
    read."""
    path = Path(state_root) / OBSERVE_FILE
    if not path.is_file():
        return set()
    try:
        with closing(_connect(path)) as db:
            db.execute("BEGIN")
            out = {str(r["family"]) for r in db.execute("SELECT family, first_at FROM practice")
                   if r["family"] and _since(r["first_at"], since)}
            for table in ("trades", "events"):
                out |= {str(r["family"]) for r in db.execute(
                    f"SELECT family, MAX(recorded_at) AS at FROM {table} GROUP BY family") if r["family"] and _since(r["at"], since)}
            db.rollback()
            return out
    except sqlite3.Error:
        return None


# ------------------------------------------------------------------------------------ the levels
def money_routes(live: Mapping[str, Any] | None) -> dict[str, list[str]]:
    """{family: the routes of its open real positions}: what puts real money on the map."""
    if not live:
        return {}
    bands = {str(i["id"]): i.get("band") for i in live["instances"]}
    out: dict[str, list[str]] = {}
    for pos in live["positions"]:
        if pos.get("status") in OPEN_STATUSES and not _house(pos.get("family")):
            route = trading_profit.route_of(pos, bands)
            if route in trading_profit.ROUTE_RANK:
                out.setdefault(str(pos["family"]), []).append(route)
    return out


def _active(inst: Mapping[str, Any]) -> bool:
    return inst.get("retired_at") is None and str(inst.get("mode") or "") == "live" and not _house(inst.get("family"))


def level_of(band: str, *, money: Sequence[str] = (), tuition: bool = False, incubator: bool = False, validated: bool = False,
             practising: bool = False) -> str | None:
    """An agent's level now (the module docstring), never one its band rules out (`LEVELS_BY_BAND`); None for a band the
    site does not know."""
    allowed = LEVELS_BY_BAND.get(band)
    if allowed is None:
        return None
    held = sorted((r for r in money if r in allowed), key=lambda r: trading_profit.ROUTE_RANK.get(r, -1))
    if held:
        return held[-1]                       # 1. open real money: the highest route's step
    if band in ABOVE_GYM:
        return band                           # 2. Candidate, Probe or Sized
    if band == "retired":
        return "retired"                      # 3.
    for rule, level in ((tuition, "tuition"), (incubator, "incubator"), (validated, "validation"), (practising, "practice")):
        if rule:
            return level                      # 4.-7.
    return "train"                            # 8.


def agent_levels(agents: Sequence[Mapping[str, Any]], swarm: Mapping[str, Any] | None, live: Mapping[str, Any] | None,
                 practice_rows: Iterable[Mapping[str, Any]] | None) -> list[dict[str, str]]:
    """[{id, level}] for each agent shown (`level_of`). An agent's validation and practice are read only while its
    sources can be read; open money and active instances need the live book."""
    money = money_routes(live)
    instances = live["instances"] if live else []
    tuition = {str(i["family"]) for i in instances if _active(i) and int(i.get("tuition") or 0)
               and not str(i.get("id") or "").endswith(INCUBATOR_SUFFIX)}
    incubator = {str(i["family"]) for i in instances if _active(i) and str(i.get("id") or "").endswith(INCUBATOR_SUFFIX)}
    practising = {str(r.get("family")) for r in practice_rows or () if isinstance(r, Mapping) and r.get("live") is True}
    shown = (swarm or {}).get("shown") or {}
    out, seen = [], set()
    for agent in agents:
        fid, band = str(agent.get("id") or ""), str(agent.get("band") or "")
        if not fid or fid in seen:
            continue
        seen.add(fid)
        state = (shown.get(fid) or {}).get("state") or {}
        version = state.get("validation_version")
        level = level_of(band, money=money.get(fid, ()), tuition=fid in tuition, incubator=fid in incubator,
                         validated=isinstance(version, int) and not isinstance(version, bool) and version >= 1,
                         practising=fid in practising)
        if level is not None:
            out.append({"id": fid, "level": level})
    return out


def funnel(since_at: str, since: float, swarm: Mapping[str, Any] | None, live: Mapping[str, Any] | None,
           practised: set[str] | None) -> dict[str, Any]:
    """The ever-counts since `since` (the module docstring): unions up each track, None where a source is unreadable."""
    out: dict[str, Any] = {key: None for key in FUNNEL_KEYS}
    out["since"] = since_at
    tuition_live = incubator_live = None
    if live is not None:
        instances = [i for i in live["instances"] if not _house(i.get("family"))]
        positions = live["positions"]
        tuition_live = {str(i["family"]) for i in instances if int(i.get("tuition") or 0)
                        and not str(i.get("id") or "").endswith(INCUBATOR_SUFFIX) and _since(i.get("created_at"), since)}
        tuition_live |= {str(p["family"]) for p in positions if int(p.get("tuition") or 0) and not _house(p.get("family"))
                         and not str(p.get("instance") or "").endswith(INCUBATOR_SUFFIX) and _since(p.get("opened_at"), since)}
        incubator_live = {str(i["family"]) for i in instances if str(i.get("id") or "").endswith(INCUBATOR_SUFFIX)
                          and _since(i.get("created_at"), since)}
        incubator_live |= {str(p["family"]) for p in positions if str(p.get("instance") or "").endswith(INCUBATOR_SUFFIX)
                           and not _house(p.get("family")) and _since(p.get("opened_at"), since)}
        out["calibration"] = sum(1 for p in positions if p.get("family") == CALIBRATION_FAMILY and _since(p.get("opened_at"), since))
        out["live_test"] = sum(1 for p in positions if p.get("family") == HOUSE_TEST_FAMILY and _since(p.get("opened_at"), since))
        out["incubator"] = len(incubator_live)
        if practised is not None:
            out["practice"] = len(practised | incubator_live)
    if swarm is None:
        return out
    fams = swarm["fams"]
    moved = lambda bands: {move[0] for move in swarm["moves"] if move[1] in bands}  # noqa: E731
    now_in = lambda bands: {f for f, row in fams.items() if row.get("band") in bands and not row.get("retired_at")}  # noqa: E731
    sized = moved(("sized",)) | now_in(("sized",))
    probe = moved(("probe", "sized")) | now_in(("probe", "sized")) | sized
    candidate = moved(ABOVE_GYM) | now_in(ABOVE_GYM) | probe
    looked = {str(look["family"]) for look in swarm["looks"]}
    retired = {f for f, row in fams.items() if _since(row.get("retired_at"), since)}
    born = {f for f, row in fams.items() if _since(row.get("born_at"), since)} | swarm["validated"] | looked | candidate | retired
    born |= practised or set()
    out.update(sized=len(sized), probe=len(probe), candidate=len(candidate), retired=len(retired),
               looks=len(swarm["looks"]), looks_passed=sum(1 for look in swarm["looks"] if int(look.get("passed") or 0)))
    if tuition_live is not None:
        validation = swarm["validated"] | looked | candidate | tuition_live
        out.update(tuition=len(tuition_live), validation=len(validation))
        born |= validation | incubator_live
    out["born"] = len(born)
    return out


# ------------------------------------------------------------------------------------ the rationale
def theses(agents: Sequence[Mapping[str, Any]], swarm: Mapping[str, Any] | None,
           extra_names: Mapping[str, Iterable[str] | None]) -> list[dict[str, Any]]:
    """[{id, thesis}] for each agent shown: its family's full mechanism through `public.thesis_text`, filtered against
    its parameter names (`sitefeed.param_names`) and its live instances' (`extra_names`, by family); None when the
    family's program cannot be read, its names cannot be known, or nothing survives."""
    from .swarm import public

    shown = (swarm or {}).get("shown") or {}
    names = (swarm or {}).get("names") or {}
    out, seen = [], set()
    for agent in agents:
        fid = str(agent.get("id") or "")
        if not fid or fid in seen:
            continue
        seen.add(fid)
        family_names, known = names.get(fid, ((), False))
        mechanism = (shown.get(fid) or {}).get("mechanism")
        extra = extra_names.get(fid)
        thesis = None
        if mechanism and known and extra is not None:
            thesis = public.thesis_text(mechanism, param_names=public.unspelled((*family_names, *extra), fid))
        out.append({"id": fid, "thesis": thesis})
    return out


def band_at(moves: Iterable[Sequence[Any]], family: str, at: Any) -> str | None:
    """The band the newest of `family`'s band moves (family, band_to, epoch) at or before `at` left it in; None when no
    move before it is known."""
    when = at if isinstance(at, (int, float)) and not isinstance(at, bool) else None
    if when is None:
        return None
    out, newest = None, None
    for move in moves:
        if move[0] == family and move[2] is not None and move[2] <= when and (newest is None or move[2] >= newest):
            out, newest = move[1], move[2]
    return out


def trades(rows: Sequence[Mapping[str, Any]] | None, family_names: Mapping[str, tuple[tuple[str, ...], bool]],
           names_by_instance: Mapping[str, Iterable[str]] | None, moves: Sequence[Sequence[Any]] = ()) -> list[dict[str, Any]]:
    """[{id, route, open_why, close_why, exit, max_loss_usd}] for each row of the positions table
    (`trading_profit.position_rows`, with the publisher's private keys); `moves` are the swarm's band moves since the
    reset (`read_swarm`), for the band an agent's position was opened on (the module docstring)."""
    from .swarm import public

    out = []
    for row in rows or ():
        pid = row.get("pid")
        if not isinstance(pid, int) or isinstance(pid, bool):
            continue
        house = row.get("source") not in ("agent", "incubator")
        closed = row.get("status") == "closed"
        exit_kind = row.get("_exit") if closed else None
        open_why = close_why = None
        if not house:
            fam, known = family_names.get(str(row.get("family") or ""), ((), False))
            inst = (names_by_instance or {}).get(str(row.get("_instance") or "")) if names_by_instance is not None else None
            if known and inst is not None:
                names = public.unspelled((*fam, *inst), row.get("family"))
                open_why = _why(row.get("_tag"), names, public)
                if closed and exit_kind == "agent":
                    close_why = _why(row.get("_close_why"), names, public)
        route = row.get("_route")
        if route in ("probe", "sized"):
            then = band_at(moves, str(row.get("family") or ""), row.get("_opened"))
            if then is not None:
                route = then if then in ("probe", "sized") else None  # opened on neither: no route rather than today's
        out.append({"id": f"real:{pid}", "route": route, "open_why": open_why, "close_why": close_why,
                    "exit": exit_kind, "max_loss_usd": row.get("_max_loss")})
    return out


def tape_names(state_root: str | Path, swarm_root: str | Path | None, family: Any, *, oid: Any = None,
               pid: Any = None) -> tuple[str, ...] | None:
    """The parameter names a trade's reason on the tape is filtered against (`publish.tape_why`; the post-fix verification
    of Oct 1, 2026): those of the instance that traded it (its opening order `oid`, or its position `pid`, in the live
    book: `instance_names`) and of every version of its family (the swarm's store: `sitefeed.param_names`), but those its
    public id spells (`public.unspelled`), as `trades` filters a reason. None, so the trade carries no reason, when the
    book does not name the instance, or either cannot be read, or the family's current program cannot be read."""
    from .swarm import public, sitefeed

    family = str(family or "")
    path = Path(state_root) / LIVE_FILE
    if not family or swarm_root is None or not path.is_file() or not (Path(swarm_root) / SWARM_DB).is_file():
        return None
    sql, key = ("SELECT instance FROM orders WHERE oid=?", oid) if oid is not None else ("SELECT instance FROM positions WHERE pid=?", pid)
    if not isinstance(key, int) or isinstance(key, bool):
        return None
    try:
        with closing(_connect(path)) as db:
            row = db.execute(sql, (key,)).fetchone()
        with closing(_connect(Path(swarm_root) / SWARM_DB)) as db:
            fam, known = sitefeed.param_names(db, swarm_root, [family]).get(family, ((), False))
    except sqlite3.Error:
        return None
    instance = str(row["instance"]) if row is not None and row["instance"] else ""
    inst = instance_names(state_root, [instance]) if instance and known else None
    if inst is None or instance not in inst:
        return None
    return tuple(public.unspelled(sorted({*fam, *inst[instance]}), family))


def _why(text: Any, names: Iterable[str], public: Any) -> str | None:
    if text is None or str(text).strip().lower() in NO_REASON:
        return None
    return public.tag_text(text, param_names=names)


# ------------------------------------------------------------------------------------ the window
def site_window(swarm_root: str | Path | None, state_root: str | Path, *, agents: Sequence[Mapping[str, Any]],
                positions_rows: Sequence[Mapping[str, Any]] | None, practice_rows: Iterable[Mapping[str, Any]] | None,
                start_at: Any, at: str) -> dict[str, Any] | None:
    """{levels, rationale} before the publisher's allowlist, read now (`at`); None when there is no reset to count from
    or no swarm store to read."""
    since = _epoch(start_at)
    if since is None or swarm_root is None:
        return None
    ids = [str(a.get("id")) for a in agents if a.get("id")]
    families = list(dict.fromkeys(ids + [str(r.get("family")) for r in positions_rows or () if r.get("source") in ("agent", "incubator")]))
    swarm = read_swarm(swarm_root, families, since)
    if swarm is None:
        return None
    live = read_live(state_root)
    practised = read_practice(state_root, since)
    # Every live instance of a shown family, and every instance a published row was traded from: their parameter names.
    shown = set(families)
    wanted = {str(i["id"]) for i in (live or {}).get("instances", []) if str(i.get("family")) in shown}
    wanted |= {str(r.get("_instance")) for r in positions_rows or () if r.get("_instance")}
    by_instance = instance_names(state_root, wanted) if live is not None else None
    extra: dict[str, set[str] | None] = {fid: (None if by_instance is None else set()) for fid in families}
    for inst in (live or {}).get("instances", []) if by_instance is not None else ():
        if str(inst.get("family")) in extra:
            extra[str(inst["family"])].update(by_instance.get(str(inst["id"]), ()))
    start = dt.datetime.fromtimestamp(since, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(since * 1000) % 1000:03d}Z"
    return {
        "levels": {"as_of": at, "agents": agent_levels(agents, swarm, live, practice_rows),
                   "funnel": funnel(start, since, swarm, live, practised)},
        "rationale": {"as_of": at, "agents": theses(agents, swarm, extra),
                      "trades": trades(positions_rows, swarm["names"], by_instance, swarm["moves"])},
    }


__all__ = ["CALIBRATION_FAMILY", "FUNNEL_KEYS", "HOUSE_TEST_FAMILY", "INCUBATOR_SUFFIX", "LEVELS", "LEVELS_BY_BAND", "LIVE_FILE",
           "OBSERVE_FILE", "agent_levels", "band_at", "funnel", "level_of", "money_routes", "site_window", "tape_names", "theses",
           "trades"]
