"""The options desk's structure founders, seated (Sept 25, 2026; the options-desk run, builder S2).

The owner's amendment of 06:01Z (`docs/runs/2026-09-25-options-desk.md`): at least ten replay-passed
structure founders on the options desk, seated on practice, with seats freed for them from desks whose
7-day forward record is negative, without breaking the seat market's rules. A STRUCTURE FOUNDER is an
entry of the `alpaca-options` row's `founders` in `league/niches.json` whose seed's NEEDS literal says
`"structures": True` (`declares_structures`, read from the source, never run).

`House.found` seats founders only while the league is under `min_population`, which it has not been
since the rebuild (64-112 residents against a floor of a few): a founder added to niches.json now is
never born. `seat_founders` is the House's population step for them (one call line after
`House.enroll`): at most `per_tick` a tick, each born as `House.found` births one (`spawn` with the
desk and the founder's key, seated at rung 1: forward-tested on practice from the first day, its
replay still run and counted as its family's first trial), and, when the league is at its population
ceiling or the desk at its cap, the seat of the first resident `House._displaceable` offers whose
DESK's 7-day practice record is negative (`desk_records`), killed as `displaced` with a post-mortem
naming the founder. `_displaceable` keeps its every protection: never real money, a winner, one inside
its grace or its desk's evidence clock, a trader short of its record, a proven family's member, one
holding a position while its market is shut, and one displacement a desk a tick. The desks a higher
class of waiter is owed (a proven family's birth, a lab graduate, a retained candidate, a card:
`House._reserved_desks`) are left to them, as `enroll` leaves them.

The desk record is computed here: no House number is a desk's forward record over a window (the
House's `family_forward` is each family's lifetime record; the foundry's `desk_forward` counts only its
own cards). It is the sum of the log growth of the ACTIVE `eval.block` rows written on practice books
in the last seven days by every agent ever of the desk, living or dead (a desk's record, not its
survivors'), folded incrementally so a tick reads only the rows written since the last.

Idempotent and restart-safe: a founder is owed only while no agent, living or dead, carries its key
(the registry, from the ledger); a founder whose program cannot be born is not tried again until its
code changes (house.json `options_desk.refused`). Cheap when nothing is owed: one pass over the
desk's founders, whose seeds are read once a process.
"""

from __future__ import annotations

import ast
from typing import Any, Mapping

from . import seeds as seeds_module
from .agents import Agent, code_sha

#: The desk whose structure founders this seats (`league/niches.json`).
OPTIONS_DESK = "alpaca-options"
#: The window of a desk's forward record, in days.
DESK_RECORD_DAYS = 7.0
#: A record that nets to less than this is negative (a net of float noise is not a loss: `House._losing_family`).
NEGATIVE = -1e-9
#: How often a founder that waits for a seat is said, in seconds.
TELL_EVERY_SECONDS = 3600.0
#: How long after no seat could be freed the seat market is asked again, in seconds (it reads every standing).
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


def structure_founders(house: Any) -> list[dict[str, Any]]:
    """The options desk's `founders` rows whose seed declares structures, in niches.json order; none when the
    desk is missing or dormant. A seed that cannot be read is not a structure founder."""
    niche = house.niches.get(OPTIONS_DESK)
    if niche is None or niche.dormant:
        return []
    out = []
    for founder in niche.founders:
        seed = str(founder.get("seed") or "")
        if seed not in _DECLARES:
            try:
                _DECLARES[seed] = declares_structures(seeds_module.load(seed))
            except Exception:  # noqa: BLE001 - an unreadable seed seats nothing
                _DECLARES[seed] = False
        if _DECLARES[seed]:
            out.append(dict(founder))
    return out


def owed(house: Any) -> list[dict[str, Any]]:
    """The structure founders no agent, living or dead, has been born as (`Agent.founder` is the key)."""
    born = {agent.founder for agent in house.registry.agents.values()}
    return [founder for founder in structure_founders(house) if founder.get("key") not in born]


def desk_records(house: Any, *, days: float = DESK_RECORD_DAYS) -> dict[str, dict[str, Any]]:
    """Desk -> {"blocks", "growth", "agents"}: the desk's practice forward record over the last `days` (the
    module's docstring says what it counts and why it is computed here)."""
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
    desks = {agent.id: agent.specialty for agent in house.registry.agents.values()}
    out: dict[str, dict[str, Any]] = {}
    for _, agent_id, growth in fold["rows"]:
        desk = desks.get(agent_id)
        if not desk:
            continue
        row = out.setdefault(desk, {"blocks": 0, "growth": 0.0, "agents": set()})
        row["blocks"] += 1
        row["growth"] += growth
        row["agents"].add(agent_id)
    return {desk: {"blocks": row["blocks"], "growth": round(row["growth"], 8), "agents": len(row["agents"])} for desk, row in out.items()}


def free_seat(house: Any, founder: Mapping[str, Any], *, on_the_desk: bool) -> tuple[Agent | None, str]:
    """The resident whose seat `founder` takes, and why (or None and why not): the first `_displaceable` offers an
    evidenced newcomer of the founder's family whose desk's 7-day practice record is negative (`desk_records`),
    never on a desk a higher class of waiter is owed; `on_the_desk` (the options desk is at its cap) only a
    resident of the options desk, so the desk stays within its cap."""
    from .house import Newcomer

    rules = house.game["economy"]
    reserved = house._reserved_desks(house.seat_waiters(), below="strategies")
    newcomer = Newcomer(family=founder.get("family"), venue="alpaca", what=f"the options desk's structure founder {founder.get('key')}")
    rank = house._displaceable(rules, specialty=OPTIONS_DESK if on_the_desk else None, exclude=house._keep_for(reserved),
                               evidenced=True, newcomer=newcomer)
    if not rank:
        return None, "no resident may be displaced (every one is inside a protection of the seat market)"
    records = desk_records(house)
    for row in rank:
        agent = row[-1]
        record = records.get(agent.specialty or "")
        if record is not None and record["growth"] < NEGATIVE:
            return agent, (f"its desk {agent.specialty}'s practice record over the last {DESK_RECORD_DAYS:g} days is "
                           f"{record['growth']:+.4f} in log growth over {record['blocks']} active blocks")
    return None, (f"no displaceable resident is on a desk whose {DESK_RECORD_DAYS:g}-day practice record is negative "
                  f"({len(rank)} displaceable, on {len({row[-1].specialty for row in rank})} desks)")


def _state(house: Any) -> dict[str, Any]:
    with house._state_lock:
        return house._state.setdefault("options_desk", {})


def _wait(house: Any, count: int, why: str) -> None:
    """Said at most once an hour, and kept in house.json (`options_desk.waiting`) for health."""
    now = house.clock()
    state = _state(house)
    with house._state_lock:
        state["waiting"] = {"count": int(count), "why": str(why)[:300], "at": now}
        tell = now - float(state.get("told") or 0) >= TELL_EVERY_SECONDS
        if tell:
            state["told"] = now
    if tell:
        house.alert("warning", f"{count} structure founder{'s' if count != 1 else ''} of the options desk wait{'s' if count == 1 else ''} "
                               f"for a seat: {why}")


def seat_founders(house: Any, *, per_tick: int = 1) -> list[Agent]:
    """Birth at most `per_tick` of the options desk's structure founders not yet born (the module's docstring);
    returns those born. Called from the House's population step, inside its probe-box turn (a birth reads
    the founder's NEEDS in the probe box)."""
    wanted = owed(house)
    if not wanted:
        return []
    state = _state(house)
    waiting = state.get("waiting") or {}
    if waiting and house.clock() - float(waiting.get("at") or 0) < RETRY_SECONDS:
        return []  # no seat could be freed a moment ago: the seat market is asked again in a few minutes, not every tick
    refused = state.setdefault("refused", {})
    rows = {row["key"]: row for row in house.founders() if row["niche"] == OPTIONS_DESK}
    wanted = [founder for founder in wanted if founder["key"] in rows
              and refused.get(founder["key"]) != code_sha(rows[founder["key"]]["code"])]
    niche = house.niches[OPTIONS_DESK]
    rules = house.game["economy"]
    born: list[Agent] = []
    for founder in wanted:
        if len(born) >= max(1, int(per_tick)):
            break
        row = rows[founder["key"]]
        loser, why = None, ""
        desk_full = house.members(OPTIONS_DESK) >= niche.max_members
        if desk_full or len(house.registry.living()) >= int(rules["max_population"]):
            loser, why = free_seat(house, row, on_the_desk=desk_full)
            if loser is None:
                _wait(house, len(wanted) - len(born), ("the options desk is at its cap and " if desk_full else "the league is full and ") + why)
                break
        try:
            agent = house.spawn(row["name"], row["family"], row["code"], reason=row["why"], specialty=OPTIONS_DESK, founder=row["key"])
        except ValueError as exc:
            with house._state_lock:
                refused[row["key"]] = code_sha(row["code"])  # once per code version, not every tick
            house.alert("warning", f"the options desk's structure founder {row['key']} could not be born: {str(exc)[:200]}")
            continue
        if house.evaluator.rung(agent.id) < 1:
            house.evaluator.seat(agent.id, 1, "a structure founder of the options desk: forward-tested on practice from the first day")
        house.seat(agent)
        born.append(agent)
        if loser is not None:
            full = "the options desk was at its cap" if desk_full else "the league was full"
            house.kill(loser, "displaced", f"{full} and the options desk's structure founder {row['key']} ({agent.id}) "
                                           f"takes its seat: {why}")
    if born:
        with house._state_lock:
            state.pop("waiting", None)
    return born


__all__ = ["OPTIONS_DESK", "DESK_RECORD_DAYS", "declares_structures", "structure_founders", "owed", "desk_records", "free_seat",
           "seat_founders"]
