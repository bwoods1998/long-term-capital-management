"""The options desk's structure founders, seated (Sept 25, 2026; the options-desk run, builder S2).

The owner's amendment of 06:01Z (`docs/runs/2026-09-25-options-desk.md`): at least ten replay-passed
structure founders on the options desk, seated on practice, with seats freed for them from desks whose
7-day forward record is negative. A STRUCTURE FOUNDER is an entry of the `alpaca-options` row's
`founders` in `league/niches.json` whose seed's NEEDS literal says `"structures": True`
(`declares_structures`, read from the source, never run).

`House.found` seats founders only while the league is under `min_population`, which it has not been
since the rebuild: a founder added to niches.json now is never born. `seat_founders` is the population
step for them (one call line after `House.enroll` in the births pass): at most one a tick, born as
`House.found` births one (`spawn` with the desk and the founder's key, seated at rung 1: forward-tested
on practice from the first day, its replay still run and counted as its family's first trial).

**The seat rule** (the integrator's, Sept 25, 2026, agreed with the forward-first run, which owns the
seat market). Measured on the House box: at 05:43Z 128 of 128 seats taken (the population rule's ceiling),
39 lab graduates and 16 cards waiting, and `_displaceable` offered NOBODY even to an evidenced newcomer
(health.json `seats.displaceable` 0); at 06:35Z the seven options residents were all `options-pullback`,
with 2 to 14 fills each: traders short of their record, which the seat market keeps.
So a founder does not ask the seat market; when the league is at its ceiling (or the options desk at its
cap) and a structure founder is owed, the House RETIRES one practice resident a tick for it, cause
`CAUSE` ("options_seat", its own cause: not revivable as a displacement, not a strategy defect), with a
post-mortem naming the founder and this rule, in this order (`retiree`):

  (a) the options desk's own practice residents (rung <= 1) whose family's pooled forward record is
      negative (`House.family_forward`, lifetime, every member) and whose own 7-day practice record is
      at or under zero, the most negative first (at 06:35Z: krasker-10 -0.174, krasker-21 -0.145,
      krasker-13 -0.111, krasker-19 -0.051, all options-pullback);
  (b) then residents of the OTHER Alpaca desks whose desk-level 7-day practice record is negative
      (`desk_records`, computed, never written down: at 06:35Z alpaca-crypto-majors -0.059,
      alpaca-index-etfs -0.032, alpaca-open -0.023) whose own 7-day record is at or under zero (a
      resident that never traded has none), the most negative first, then one that never traded, then
      the oldest. Never a Kalshi desk (the Kalshi-scale run's).

Always kept: real money (rung >= 2); a winner (a positive 7-day record of its own, or a positive standing:
`Standing.mean_growth` or `score_growth`); a proven family's member (`House._family_proven`); one holding
a position while its market is shut (eligible at the open); one with a working order on any book; one
born less than `MIN_AGE_SECONDS` ago; and any structure agent (a founder never retires another). When
the options desk is at its cap only (a) is asked, so the desk stays within it. At most `RETIRE_CAP`
retirements in all (counted from the ledger's deaths of this cause), one a tick, none while no founder is
owed; each is an `ops.budget` row ("options desk seat rule": who, why, the count and the cap) and an info
alert. The count is the ledger's (`retired_count`: the registry's deaths of cause `CAUSE`, folded from the
`agent.died` rows), never a house.json list.

A 7-day record is the sum of the log growth of the ACTIVE `eval.block` rows written on practice books in
the last seven days (`records`, folded incrementally from the ledger); a desk's is every member's, living
or dead (a desk's record, not its survivors'). No House number is either: `family_forward` is a family's
lifetime record, and the foundry's `desk_forward` counts only its own cards.

Locking: the founder's NEEDS are read in the probe box first, outside the lock (about 20 s of Sail); the
choice of the resident, its retirement and the birth (from that probe, `spawn(described=...)`, no Sail call)
run under the House's lifecycle lock, as the births pass's admissions do, so no wake or background pass sees
half of it. The seat is freed before the birth, and only once the probe says the founder can be born: a
retirement that fails leaves the founder unborn, never the league over its ceiling (the adversarial review
of Sept 25, 2026). Only `seat_founders` births a structure founder: `House.founders` leaves them out
(`is_structure_founder`), so `House.found` (a fresh canary under `min_population`) never probes all twelve.

Idempotent and restart-safe: a founder is owed only while no agent, living or dead, carries its key (the
registry, from the ledger); a founder whose program cannot be born is not tried again until its code
changes (`options_desk.refused`). Cheap when nothing is owed: one pass over the desk's founders, whose
seeds are read once a process.
"""

from __future__ import annotations

import ast
from typing import Any

from . import seeds as seeds_module
from .agents import Agent, code_sha

#: The desk whose structure founders this seats (`league/niches.json`).
OPTIONS_DESK = "alpaca-options"
#: The window of a 7-day record, in days.
RECORD_DAYS = 7.0
#: A record under this is negative, over its negative positive (a net of float noise is neither: `House._losing_family`).
EPSILON = 1e-9
#: The cause of a death this rule makes (`House.kill`): its own, so the deaths it makes are counted apart.
CAUSE = "options_seat"
#: At most this many residents are retired by this rule, in all (the integrator's cap).
RETIRE_CAP = 12
#: A resident born less than this long ago is never retired by it, in seconds.
MIN_AGE_SECONDS = 2 * 3600.0
#: How often a founder that waits for a seat is said, in seconds.
TELL_EVERY_SECONDS = 3600.0
#: How long after no seat could be found the rule is asked again, in seconds (it reads every standing).
RETRY_SECONDS = 300.0

_DECLARES: dict[str, bool] = {}  # seed name -> its NEEDS say "structures": True (a process's seeds never change)


def declares_structures(code: str) -> bool:
    """Whether a program's `NEEDS` literal carries `"structures": True`: read from its source, never run."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "NEEDS" for target in node.targets):
            try:
                needs = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                return False
            return isinstance(needs, dict) and needs.get("structures") is True
    return False


def is_structure_founder(founder: Any) -> bool:
    """Whether a niches.json `founders` row's seed declares structures (read once a process; a seed that cannot
    be read is not one). `House.founders` leaves these out, so `House.found` never births them: only
    `seat_founders` does, one a tick (a fresh canary House is under `min_population` and would otherwise probe
    all twelve in its first tick)."""
    seed = str((founder or {}).get("seed") or "") if isinstance(founder, dict) else ""
    if seed not in _DECLARES:
        try:
            _DECLARES[seed] = declares_structures(seeds_module.load(seed))
        except Exception:  # noqa: BLE001 - an unreadable seed seats nothing
            _DECLARES[seed] = False
    return _DECLARES[seed]


def structure_founders(house: Any) -> list[dict[str, Any]]:
    """The options desk's `founders` rows whose seed declares structures, in niches.json order; none when the
    desk is missing or dormant."""
    niche = house.niches.get(OPTIONS_DESK)
    if niche is None or niche.dormant:
        return []
    return [dict(founder) for founder in niche.founders if is_structure_founder(founder)]


def founder_rows(house: Any, founders: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Key -> the birth row of each structure founder, as `House.founders` makes one for any other founder (which
    leaves these out): the desk's name, the family (the seed's own when the key is the seed's name), the seed's
    why, and its program pointed at the desk (`niches.founder_code`). A founder whose seed is not in SEEDS has none."""
    from . import niches as niches_module

    niche = house.niches[OPTIONS_DESK]
    seeds = {row["name"]: row for row in seeds_module.SEEDS}
    out = {}
    for founder in founders:
        seed = seeds.get(founder.get("seed"))
        if seed is None:
            continue
        family = seed["family"] if founder["key"] == founder["seed"] else f"{niche.id.split('-', 1)[1]}-{seed['family'].split('-', 1)[-1]}"
        out[founder["key"]] = {"name": niche.desk, "key": founder["key"], "family": family, "niche": niche.id, "why": seed["why"],
                               "code": niches_module.founder_code(seeds_module.load(founder["seed"]), niche, founder)}
    return out


def retired_count(house: Any) -> int:
    """How many residents this rule has retired, ever: the deaths of cause `CAUSE` in the registry, which is the
    ledger's `agent.died` rows folded (restart-safe, and nothing a house.json edit can reset)."""
    return sum(1 for agent in house.registry.agents.values() if not agent.alive and agent.cause == CAUSE)


def owed(house: Any) -> list[dict[str, Any]]:
    """The structure founders no agent, living or dead, has been born as (`Agent.founder` is the key)."""
    born = {agent.founder for agent in house.registry.agents.values()}
    return [founder for founder in structure_founders(house) if founder.get("key") not in born]


# ------------------------------------------------------------------ 7-day records
def _fold(house: Any, days: float) -> list[tuple[float, str, float]]:
    """(when, agent, log growth) of every active practice `eval.block` of the last `days`, oldest first,
    folded incrementally: each call reads only the rows written since the last."""
    from .house import REAL_BOOK, _epoch

    fold = house.__dict__.setdefault("_options_desk_fold", {"after": 0, "rows": []})
    real = set(REAL_BOOK.values())
    for entry in house.ledger.iter(kinds="eval.block", after=int(fold["after"])):
        fold["after"] = entry.seq
        payload = entry.payload
        if not payload.get("active") or payload.get("book") in real:
            continue
        try:
            growth = float(payload.get("log_growth") or 0.0)
        except (TypeError, ValueError):
            continue
        fold["rows"].append((_epoch(entry.at), entry.agent, growth))
    since = house.clock() - days * 86400.0
    fold["rows"] = [row for row in fold["rows"] if row[0] >= since]
    return fold["rows"]


def records(house: Any, *, days: float = RECORD_DAYS) -> dict[str, dict[str, Any]]:
    """Agent -> {"blocks", "growth"}: its own practice record over the last `days`."""
    out: dict[str, dict[str, Any]] = {}
    for _, agent_id, growth in _fold(house, days):
        row = out.setdefault(agent_id, {"blocks": 0, "growth": 0.0})
        row["blocks"] += 1
        row["growth"] += growth
    return out


def desk_records(house: Any, *, days: float = RECORD_DAYS) -> dict[str, dict[str, Any]]:
    """Desk -> {"blocks", "growth", "agents"}: the desk's practice record over the last `days`, every agent
    ever of it, living or dead."""
    desks = {agent.id: agent.specialty for agent in house.registry.agents.values()}
    out: dict[str, dict[str, Any]] = {}
    for agent_id, row in records(house, days=days).items():
        desk = desks.get(agent_id)
        if not desk:
            continue
        total = out.setdefault(desk, {"blocks": 0, "growth": 0.0, "agents": 0})
        total["blocks"] += row["blocks"]
        total["growth"] += row["growth"]
        total["agents"] += 1
    return out


# ------------------------------------------------------------------ the seat rule
def _kept(house: Any, agent: Agent, standing: Any, own: dict[str, Any] | None, now: float, stamp: str) -> str:
    """Why the seat rule keeps `agent` (empty when it may be retired)."""
    from .house import _epoch
    from .venues import market_hours

    if standing is None:
        return "no standing yet"
    if standing.rung >= 2:
        return "real money"
    if house.is_structure_agent(agent):
        return "a structure agent"
    if (own is not None and own["growth"] > EPSILON) or standing.mean_growth > 0 or (standing.score_growth or 0) > 0:
        return "a winner"
    if house._family_proven(agent.family, agent.venue):
        return "a proven family's member"
    if now - _epoch(agent.born_at) < MIN_AGE_SECONDS:
        return "born less than two hours ago"
    for book in house.books.values():
        if agent.id not in book.accounts:
            continue
        if book.open_orders(agent.id):
            return "a working order"
        if any(market_hours(holding.instrument, stamp) is False for holding in list(book.account(agent.id).holdings.values())):
            return "holding a position while its market is shut"
    return ""


def retiree(house: Any, *, desk_only: bool = False) -> tuple[Agent | None, str, dict[str, Any]]:
    """The resident the seat rule retires next, why (or None and why none), and the numbers it was chosen by
    (the module's docstring has the rule). `desk_only`: the options desk is at its cap, so only (a)."""
    from .ledger import now_iso

    now, stamp = house.clock(), now_iso(house.clock)
    own = records(house)
    desks = desk_records(house)
    pooled = house.family_forward()
    standings = {row.agent: row for row in house.standings()}
    first: list[tuple[float, str, Agent]] = []
    then: list[tuple[float, bool, str, str, Agent]] = []
    kept: dict[str, int] = {}
    for agent in house.registry.living():
        if agent.venue != "alpaca":
            continue  # never a Kalshi desk
        mine = own.get(agent.id)
        growth = mine["growth"] if mine else 0.0
        if growth > EPSILON:
            continue  # a winner by its own 7-day record: kept, and neither list asks for it
        if agent.specialty == OPTIONS_DESK:
            if not (pooled.get(agent.family) or (0, 0.0))[1] < -EPSILON:
                continue
            why = _kept(house, agent, standings.get(agent.id), mine, now, stamp)
            if why:
                kept[why] = kept.get(why, 0) + 1
                continue
            first.append((growth, agent.born_at, agent))
        elif not desk_only and (desks.get(agent.specialty or "") or {}).get("growth", 0.0) < -EPSILON:
            why = _kept(house, agent, standings.get(agent.id), mine, now, stamp)
            if why:
                kept[why] = kept.get(why, 0) + 1
                continue
            traded = bool(house.ledger.read(kinds="book.fill", agent=agent.id, limit=1))
            then.append((growth, traded, agent.born_at, agent.id, agent))
    numbers = {"kept": kept, "desks": {desk: round(row["growth"], 6) for desk, row in desks.items() if row["growth"] < -EPSILON}}
    if first:
        growth, _, agent = min(first, key=lambda row: (row[0], row[1]))
        family_growth = (pooled.get(agent.family) or (0, 0.0))[1]
        return agent, (f"rule (a): the options desk's own resident {agent.id} of the family {agent.family}, whose pooled forward record is "
                       f"{family_growth:+.4f}, with its own {RECORD_DAYS:g}-day practice record {growth:+.4f}"), \
            {**numbers, "rule": "a", "own": round(growth, 6), "family": round(family_growth, 6)}
    if then:
        growth, has_traded, _, _, agent = min(then, key=lambda row: row[:4])
        desk = desks[agent.specialty or ""]["growth"]
        return agent, (f"rule (b): {agent.id} of the desk {agent.specialty}, whose {RECORD_DAYS:g}-day practice record is {desk:+.4f}, "
                       + (f"with its own {growth:+.4f}" if has_traded else "never having traded")), \
            {**numbers, "rule": "b", "own": round(growth, 6), "desk": round(desk, 6), "traded": has_traded}
    held = ", ".join(f"{n} {why}" for why, n in sorted(kept.items(), key=lambda item: -item[1])) or "none on a losing family or desk"
    return None, (f"no resident may be retired for it (the options desk's losing family first{'' if desk_only else ', then the losing Alpaca desks'}; "
                  f"kept: {held})"), numbers


# ------------------------------------------------------------------ births
def _state(house: Any) -> dict[str, Any]:
    with house._state_lock:
        return house._state.setdefault("options_desk", {})


def _wait(house: Any, count: int, why: str) -> None:
    """Said at most once an hour, and kept in house.json (`options_desk.waiting`)."""
    now = house.clock()
    state = _state(house)
    with house._state_lock:
        state["waiting"] = {"count": int(count), "why": str(why)[:400], "at": now}
        tell = now - float(state.get("told") or 0) >= TELL_EVERY_SECONDS
        if tell:
            state["told"] = now
    if tell:
        house.alert("warning", f"{count} structure founder{'s' if count != 1 else ''} of the options desk wait{'s' if count == 1 else ''} "
                               f"for a seat: {why}")


def _seat_needed(house: Any) -> tuple[bool, bool]:
    """(the league is at its ceiling, the options desk is at its cap)."""
    niche = house.niches[OPTIONS_DESK]
    return (len(house.registry.living()) >= int(house.game["economy"]["max_population"]),
            house.members(OPTIONS_DESK) >= niche.max_members)


def seat_founders(house: Any, *, per_tick: int = 1) -> list[Agent]:
    """Birth at most `per_tick` of the options desk's structure founders not yet born, retiring a resident by
    the seat rule for each when the league is full (the module's docstring); returns those born. Called
    from the House's births pass, inside its probe-box turn (one line after `House.enroll`). A Sail error
    is the births pass's to defer (it is infrastructure); any other failure here is said once as a warning
    and costs only this step, never the rest of the births pass or the tick."""
    from .sandbox import SandboxError

    try:
        return _seat_founders(house, per_tick=per_tick)
    except SandboxError:
        raise
    except Exception as exc:  # noqa: BLE001 - the options desk's seating never stops the House's population step
        house.alert("warning", f"the options desk's founder seating failed this tick ({type(exc).__name__}: {str(exc)[:200]})")
        return []


def _seat_founders(house: Any, *, per_tick: int = 1) -> list[Agent]:
    from .house import PROBE_BOX

    wanted = owed(house)
    if not wanted:
        return []
    state = _state(house)
    waiting = state.get("waiting") or {}
    if waiting and house.clock() - float(waiting.get("at") or 0) < RETRY_SECONDS:
        return []  # no seat a moment ago: asked again in a few minutes, not every tick
    refused = state.setdefault("refused", {})
    rows = founder_rows(house, wanted)
    wanted = [founder for founder in wanted if founder["key"] in rows
              and refused.get(founder["key"]) != code_sha(rows[founder["key"]]["code"])]
    born: list[Agent] = []
    for founder in wanted:
        if len(born) >= max(1, int(per_tick)):
            break
        row = rows[founder["key"]]
        full, desk_full = _seat_needed(house)
        if (full or desk_full) and retired_count(house) >= RETIRE_CAP:
            _wait(house, len(wanted) - len(born), f"the seat rule has retired its {RETIRE_CAP} residents, its cap")
            break
        if full or desk_full:
            candidate, why, _ = retiree(house, desk_only=desk_full)  # a look before the probe, which costs a box
            if candidate is None:
                _wait(house, len(wanted) - len(born), why)
                break
        described = house.sandbox.needs(PROBE_BOX, row["code"])  # outside the lock: about 20 s of Sail
        with house._lifecycle_lock:
            if row["key"] in {agent.founder for agent in house.registry.agents.values()}:
                continue  # born meanwhile
            unborn = _unborn(house, described)
            if unborn:
                _refuse(house, refused, row, unborn)
                continue
            full, desk_full = _seat_needed(house)
            loser, why, numbers = (None, "", {})
            if full or desk_full:
                loser, why, numbers = retiree(house, desk_only=desk_full)
                if loser is None:
                    _wait(house, len(wanted) - len(born), why)
                    break
                # The seat is freed FIRST, once the probe has said the founder can be born (as `House._admit_orphan`
                # does): a retirement that fails leaves the founder unborn and the league at its ceiling, never over.
                if not _retire(house, loser, row, why, numbers, desk_full=desk_full):
                    break
            try:
                agent = house.spawn(row["name"], row["family"], row["code"], reason=row["why"], specialty=OPTIONS_DESK,
                                    founder=row["key"], described=described)
            except ValueError as exc:
                _refuse(house, refused, row, str(exc))
                continue
            if house.evaluator.rung(agent.id) < 1:
                house.evaluator.seat(agent.id, 1, "a structure founder of the options desk: forward-tested on practice from the first day")
            house.seat(agent)
            born.append(agent)
            if loser is not None:
                house.alert("info", f"{loser.id} retired for the options desk's structure founder {row['key']} ({agent.id}): {why} "
                                    f"[{retired_count(house)} of at most {RETIRE_CAP} by this rule]")
    if born:
        with house._state_lock:
            state.pop("waiting", None)
    return born


def _unborn(house: Any, described: Any) -> str:
    """Why the probe says the founder cannot be born on the options desk (empty when it can): checked before any
    seat is freed for it, with what `House.spawn` checks of the NEEDS."""
    from . import niches as niches_module
    from .agents import niche_of

    info = getattr(described, "result", None) or {}
    if not info.get("ok"):
        return str(info.get("error") or "its NEEDS could not be read")
    try:
        niche_of(info["needs"])
        niches_module.constrain(info["needs"], house.niches[OPTIONS_DESK])
    except (KeyError, ValueError) as exc:
        return str(exc)
    return ""


def _refuse(house: Any, refused: dict[str, str], row: dict[str, Any], why: str) -> None:
    with house._state_lock:
        refused[row["key"]] = code_sha(row["code"])  # once per code version, not every tick
    house.alert("warning", f"the options desk's structure founder {row['key']} could not be born: {str(why)[:200]}")


def _retire(house: Any, loser: Agent, row: dict[str, Any], why: str, numbers: dict[str, Any], *, desk_full: bool) -> bool:
    """Retire `loser` for the founder about to be born (under the lifecycle lock), and say so: its post-mortem and
    one `ops.budget` row with the rule's count (from the ledger: `retired_count`) and cap. True when the resident is
    gone; a retirement that fails is a warning, and the founder waits (the league never goes over its ceiling)."""
    full = "the options desk was at its cap" if desk_full else "the league was at its population ceiling"
    try:
        house.kill(loser, CAUSE, f"{full} and the options desk's structure founder {row['key']} takes its seat "
                                 f"by the options desk's seat rule (Sept 25, 2026): {why}")
    except Exception as exc:  # noqa: BLE001 - checked below: only a resident that is gone frees a seat
        house.alert("warning", f"{loser.id} could not be retired for the options desk's structure founder {row['key']} "
                               f"({type(exc).__name__}: {str(exc)[:160]})")
    current = house.registry.get(loser.id)
    if current is not None and current.alive:
        return False
    house.ledger.append("ops.budget", {"what": "options desk seat rule", "retired": loser.id, "desk": loser.specialty, "family": loser.family,
                                       "founder": row["key"], "count": retired_count(house), "cap": RETIRE_CAP,
                                       "why": why[:300], **{k: v for k, v in numbers.items() if k != "desks"}})
    return True


__all__ = ["OPTIONS_DESK", "RECORD_DAYS", "CAUSE", "RETIRE_CAP", "declares_structures", "is_structure_founder", "structure_founders",
           "founder_rows", "owed", "retired_count", "records", "desk_records", "retiree", "seat_founders"]
