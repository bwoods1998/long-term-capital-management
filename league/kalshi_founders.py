"""Flagged founder rows seated into a full league (K1, the Kalshi-scale run, Sept 25, 2026).

`House.found` seats a desk's founder rows (`league/niches.json` `founders`) on rung 1 without a replay: they are
the owner's priors, forward-tested from the first day, their replay still run and counted as their family's first
trial. It runs only while the league is under `min_population`, and the league sits at its ceiling (128 of 128 at
the Sept 25 T0). The Kalshi-scale run adds model-versus-market sports founders to `kalshi-sports` for the weekend
slate (college football Saturday, the NFL Sunday, MLB's final weekend), each row flagged `"seat_full_league": true`;
a founder that prices games from the live `odds` feed on a day-horizon desk has no replay for 20 days, so `enroll`'s
replay path cannot seat it either.

`seat(house)` is called once a births pass (`House._births`, after `enroll`) and births at most ONE flagged founder
a call, through `house.found([key])`, holding the House's lifecycle lock (`House._lifecycle_lock`, which the lab's
births and the refill's admissions hold) from the seat question to the birth and the death that makes room:

- a flagged row of a non-dormant Kalshi desk whose `key` no agent, living or dead, was born with (`Agent.founder`):
  a founder that died is never reborn, and one already seated is not seated again, across ticks and restarts;
- a league with room and a desk with room: the free seat;
- a FULL DESK: the House's own seat market on that desk, asked as `enroll` asks (`House._displaceable(rules,
  specialty=desk, evidenced=True, newcomer=Newcomer(...))`, whose first row is `_weakest`'s);
- a FULL LEAGUE and a desk with room, first the House's own seat market: the first resident, in the House's
  ranking (`_displaceable`, league-wide, least evidence first, leaving out the desks a higher class of waiter holds
  as `enroll` does), of the desk whose pooled forward record over the last `RECORD_DAYS` (7) days is the most
  negative (`desk_records`: `House.family_forward`'s statistic -- active `eval.block` rows and their summed log
  growth, over every agent ever born there -- by desk and over the forward-first run's F3 window), then the next
  negative desk; never a desk whose record is not negative by the House's own line (`families.losing`,
  `economy.losing_family_min_blocks` active blocks). That resident dies `displaced`, as in `enroll`;
- then, when the seat market has nobody (at the Sept 25 T0 it offered no one even to an evidenced newcomer), a desk
  whose niches.json row carries `"yields_seats": {"floor": 4, "reason": "..."}` gives up one practice resident while
  it has more than `floor` members and its own 7-day pooled record is negative (`_yielded`): its weakest by the
  House's ranking (never traded first, a losing family first, then rung, growth, blocks and purse), never one on
  real money, a member of a proven or swinging family (the allocator's record; unreadable counts as proven), one of
  the founder's own family, a winner, one with research in flight, or one holding a position or a working order on
  any book, held for the open or drained by the House (it waits for it to be flat). It dies of its own cause, `desk_closed` (`DESK_CLOSED`), never
  `displaced`, so the displacement share and F3's tenure rules do not count it; its postmortem names the founder
  and the desk's record and the flag's reason, and its program stays in the graveyard like any death. The desk's
  row flag is the switch: remove it and nothing yields;
- the resident dies only once the founder is born, under the same lock, so no other newcomer takes the seat; the
  league never grows (one out, one in). Every protection of `_displaceable` holds on the first two paths, and two
  are checked again on the chosen resident: never rung 2 or above, never a proven or swinging family's member;
- nobody may make way: nothing is born, the reason is kept where health.json shows a refused birth (house.json
  `seat_refusals.founders`, `seats.last_refused_birth`) and told as one warning an hour at most.

Each birth writes its `birth-route:<agent>` row (route `founder`, with the flag, the rule, who made way, its cause
and its desk's record) before the foundry's labeller can, and an info alert naming the founder and who made way;
house.json `kalshi_founders.seated` keeps the same. A program that cannot be born (its NEEDS refused) is told once
and tried again when its code changes. An exception anywhere in here is a warning (one an hour for the same text)
and never breaks the births pass.
"""

from __future__ import annotations

import json
from contextlib import nullcontext
from typing import Any, Mapping

from . import niches as niches_module
from .agents import code_sha
from .families import losing
from .ledger import LedgerConflict, now_iso

#: The founder row's flag (`league/niches.json`): seated even in a full league.
FLAG = "seat_full_league"
#: The desk row's flag (`league/niches.json`): `{"floor": n, "reason": "..."}`, the desk gives up a practice resident
#: to a flagged founder while it has more than `floor` members and its pooled record is negative.
YIELD_FLAG = "yields_seats"
#: The cause of a death its yielding desk gave up: its own, never counted as a displacement.
DESK_CLOSED = "desk_closed"
#: The desks this module seats and asks to yield: the Kalshi desks this run owns (the options run seats its own).
VENUE = "kalshi"
#: The window of a desk's pooled forward record: the forward-first run's F3 window.
RECORD_DAYS = 7.0
#: How long the desks' records are reused (the births pass runs every 300 s at most since H5).
RECORD_CACHE_SECONDS = 300.0
_CACHE_KEY = "kalshi_founders_desk_records"
#: One warning an hour at most, for a founder that cannot be seated and for an error in here.
TELL_SECONDS = 3600.0
#: The founder rows' class in house.json `seat_refusals` (health.json `seats.last_refused_birth`).
REFUSAL_CLASS = "founders"
_STATE = "kalshi_founders"
_FLAGS: dict[str, Any] = {}  # niches.json's `yields_seats` rows, read again when the file changes


def seat(house: Any) -> Any | None:
    """One births pass's flagged founder: the Agent born, or None. Never raises (an error is a warning)."""
    try:
        lock = getattr(house, "_lifecycle_lock", None)
        with lock if lock is not None else nullcontext():
            return _seat(house)
    except Exception as exc:  # noqa: BLE001 - the births pass goes on to the refill whatever happens here
        _tell_error(house, exc)
        return None


def pending(house: Any) -> list[tuple[Any, Mapping[str, Any]]]:
    """(niche, founder row) of every flagged founder of an open Kalshi desk whose key no agent was ever born with."""
    lock = getattr(house.registry, "_lock", None)
    with lock if lock is not None else nullcontext():
        born = {a.founder for a in house.registry.agents.values() if a.founder}
    return [(niche, row) for niche in house.niches.values() if not niche.dormant and niche.venue == VENUE
            for row in niche.founders if row.get(FLAG) is True and row.get("key") and row["key"] not in born]


def desk_records(house: Any, *, days: float = RECORD_DAYS) -> dict[str, tuple[int, float]]:
    """Desk -> (active `eval.block` rows, their summed log growth) over the last `days`: the pooled forward record
    `House.family_forward` keeps for a family (every agent ever born into it, living or dead), kept for a desk (every
    agent ever born on it) over the window F3 reads. Kept for `RECORD_CACHE_SECONDS`."""
    now = house.clock()
    hit = house._data_cache.get(_CACHE_KEY)
    if hit and now - hit[0] < RECORD_CACHE_SECONDS:
        return hit[1]
    since = now_iso(lambda: now - days * 86400.0)
    lock = getattr(house.registry, "_lock", None)
    with lock if lock is not None else nullcontext():
        desk_of = {a.id: a.specialty for a in house.registry.agents.values() if a.specialty}
    out: dict[str, list[float]] = {}
    for entry in house.ledger.iter(kinds="eval.block"):
        if entry.at < since or not entry.payload.get("active"):
            continue
        desk = desk_of.get(entry.agent or "")
        if not desk:
            continue
        try:
            growth = float(entry.payload.get("log_growth") or 0.0)
        except (TypeError, ValueError):
            continue
        row = out.setdefault(desk, [0, 0.0])
        row[0] += 1
        row[1] += growth
    value = {desk: (int(n), growth) for desk, (n, growth) in out.items()}
    house._data_cache[_CACHE_KEY] = (now, value)
    return value


def yielding(house: Any) -> dict[str, dict[str, Any]]:
    """Desk -> {"floor", "reason"}: the open Kalshi desks whose niches.json row carries a valid `yields_seats`
    (`niches.load` keeps no such key, so the row is read here, from the file the House loaded its desks from)."""
    path = niches_module.NICHES_PATH
    stamp = (str(path), path.stat().st_mtime_ns)
    if _FLAGS.get("stamp") != stamp:
        doc = json.loads(path.read_text(encoding="utf-8"))
        _FLAGS.update(stamp=stamp, rows={str(row.get("id")): row.get(YIELD_FLAG) for row in doc.get("niches") or ()
                                         if row.get(YIELD_FLAG) is not None})
    out = {}
    for desk, flag in (_FLAGS.get("rows") or {}).items():
        niche = house.niches.get(desk)
        if niche is None or niche.dormant or niche.venue != VENUE or not isinstance(flag, Mapping):
            continue
        floor = flag.get("floor")
        if isinstance(floor, bool) or not isinstance(floor, int) or floor < 1:
            continue  # a malformed flag yields nothing
        out[desk] = {"floor": floor, "reason": str(flag.get("reason") or "").strip()}
    return out


def _seat(house: Any) -> Any | None:
    wanted = pending(house)
    if not wanted:
        return None
    from .house import Newcomer  # here: league.house imports this module

    rules = house.game["economy"]
    state = _state(house)
    rows = house.founders()
    by_key = {row["key"]: row for row in rows}
    desk_names = {niche.desk for niche in house.niches.values()}
    waiting, why_not, asked = [], [], set()
    for niche, raw in wanted:
        key = str(raw["key"])
        row = by_key.get(key)
        if row is None:
            continue
        if key in desk_names or sum(1 for r in rows if key in (r["key"], r["name"])) != 1:
            # `found` matches a desk's name or a key: this one would seat more than one founder.
            waiting.append(key)
            why_not.append(f"{key}: its key names a desk or another founder, and `found` would seat more than one")
            continue
        sha = code_sha(row["code"])
        if (state["refused"].get(key) or {}).get("code") == sha:
            continue  # its program could not be born (told once); asked again when its code changes
        waiting.append(key)
        if niche.id in asked:
            continue  # one seat question a desk a pass: the desk's next founder asks on the next pass
        asked.add(niche.id)
        newcomer = Newcomer(family=row["family"], venue=niche.venue, what=f"the founder {key}")
        how = _room(house, rules, niche, newcomer)
        if how.get("why"):
            why_not.append(f"{key} on {niche.id}: {how['why']}")
            continue
        born = _found(house, key, sha, niche)
        if born is None:
            waiting.remove(key)
            continue
        loser = how.get("loser")
        if loser is not None and loser.alive:
            house.kill(loser, how["cause"], house.postmortem(loser, how["cause"], _postmortem(key, born, niche, loser, how)))
        _record(house, key, born, niche, how)
        return born
    if why_not:
        _refuse(house, waiting, "; ".join(why_not))
    return None


def _room(house: Any, rules: Mapping[str, Any], niche: Any, newcomer: Any) -> dict[str, Any]:
    """Where the founder sits: `rule` ("free seat", "desk full", "league full" or "desk yields seats") with the `loser`
    that makes way and its `cause` and, from another desk, that desk's `record`; or `why` nobody may make way."""
    members, cap = house.members(niche.id), int(niche.max_members)
    if members >= cap:
        kept: dict[str, int] = {}
        rank = house._displaceable(rules, specialty=niche.id, evidenced=True, newcomer=newcomer, why=kept)
        loser = next((row[-1] for row in rank if _allowed(house, row[-1])), None)
        if loser is None:
            return {"why": f"its desk is full ({members} of {cap}) and no resident may be displaced{_kept(kept)}"}
        return {"rule": "desk full", "loser": loser, "cause": "displaced"}
    living, ceiling = len(house.registry.living()), int(rules["max_population"])
    if living < ceiling:
        return {"rule": "free seat", "loser": None, "cause": None}
    market = _displaced(house, rules, newcomer)
    if not market.get("why"):
        return market
    yielded = _yielded(house, rules, niche, newcomer.family)
    if not yielded.get("why"):
        return yielded
    return {"why": f"the league is full ({living} of {ceiling}) and {market['why']}; and no desk yields a seat: {yielded['why']}"}


def _displaced(house: Any, rules: Mapping[str, Any], newcomer: Any) -> dict[str, Any]:
    """The House's own seat market in a full league: the first resident, in its ranking, of the most negative desk."""
    minimum = int(rules.get("losing_family_min_blocks", 6))
    negative = sorted((growth, desk, blocks) for desk, (blocks, growth) in desk_records(house).items()
                      if losing(blocks, growth, minimum))
    if not negative:
        return {"why": f"no desk's pooled forward record over the last {RECORD_DAYS:g} days is negative over {minimum} "
                       "active blocks or more"}
    reserved = house._reserved_desks(house.seat_waiters(), below="strategies")
    kept: dict[str, int] = {}
    rank = house._displaceable(rules, evidenced=True, newcomer=newcomer, exclude=house._keep_for(reserved), why=kept)
    first: dict[str, Any] = {}
    losers = {desk for _, desk, _ in negative}
    for row in rank:  # the House's order: least evidence first
        agent = row[-1]
        if agent.specialty in losers and agent.specialty not in first and _allowed(house, agent):
            first[agent.specialty] = agent
    for growth, desk, blocks in negative:  # the most negative desk first
        if desk in first:
            return {"rule": "league full", "loser": first[desk], "cause": "displaced",
                    "record": {"desk": desk, "days": RECORD_DAYS, "blocks": blocks, "growth": round(growth, 6)}}
    shown = ", ".join(f"{desk} {growth:+.4f} over {blocks}" for growth, desk, blocks in negative[:4])
    held = f"; {len(reserved)} desk(s) are held for waiting newcomers of a higher class" if reserved else ""
    return {"why": f"the seat market displaces no resident of a desk whose pooled forward record over the last "
                   f"{RECORD_DAYS:g} days is negative ({shown}){held}{_kept(kept)}"}


def _yielded(house: Any, rules: Mapping[str, Any], niche: Any, family: str | None) -> dict[str, Any]:
    """A desk flagged `yields_seats` gives up its weakest practice resident that may go, the most negative desk first."""
    flags = yielding(house)
    if not flags:
        return {"why": f"no open Kalshi desk carries {YIELD_FLAG}"}
    minimum = int(rules.get("losing_family_min_blocks", 6))
    epoch = float(rules["epoch_seconds"])
    records = desk_records(house)
    pooled = house.family_forward()
    living = house.registry.living()
    notes = []
    for desk in sorted(flags, key=lambda d: (records.get(d, (0, 0.0))[1], d)):
        if desk == niche.id:
            continue  # the founder's own desk never yields to it
        flag = flags[desk]
        members = [a for a in living if a.specialty == desk]
        blocks, growth = records.get(desk, (0, 0.0))
        if len(members) <= flag["floor"]:
            notes.append(f"{desk} is at its floor ({len(members)} members, floor {flag['floor']})")
            continue
        if not losing(blocks, growth, minimum):
            notes.append(f"{desk}'s pooled forward record over the last {RECORD_DAYS:g} days is not negative "
                         f"({growth:+.4f} over {blocks} active blocks)")
            continue
        kept: dict[str, int] = {}
        ranked = []
        for agent in members:
            why = _kept_from_yield(house, agent, family)
            standing = None if why else house._standing(agent, epoch)
            if standing is not None and (standing.mean_growth > 0 or standing.score_growth > 0):
                why = "a winner"
            if why:
                kept[why] = kept.get(why, 0) + 1
                continue
            traded = standing.active_blocks > 0 or bool(house._own_fills(agent.id, enough=1))
            n, g = pooled.get(agent.family, (0, 0.0))
            # `_displaceable`'s order without its protections: never traded first, a losing family first, then
            # replay-only first, growth, how much, and its purse.
            ranked.append(((traded, not losing(n, g, minimum), standing.rung, standing.mean_growth, standing.active_blocks,
                            float(house.economy.balance(agent.id))), agent))
        if ranked:
            ranked.sort(key=lambda row: row[0])
            return {"rule": "desk yields seats", "loser": ranked[0][1], "cause": DESK_CLOSED, "reason": flag["reason"],
                    "floor": flag["floor"], "members": len(members),
                    "record": {"desk": desk, "days": RECORD_DAYS, "blocks": blocks, "growth": round(growth, 6)}}
        notes.append(f"no resident of {desk} may go{_kept(kept)}")
    return {"why": "; ".join(notes) or f"no desk but the founder's own carries {YIELD_FLAG}"}


def _kept_from_yield(house: Any, agent: Any, family: str | None) -> str:
    """Why a resident of a yielding desk may not go, or "" (the rules its flag gives up nothing against)."""
    if not agent.alive:
        return "dead"
    if house.evaluator.rung(agent.id) >= 2:
        return "real money"
    if family and agent.family == family:
        return "the founder's own family"
    if _proven(house, agent):
        return "a proven or swinging family's member"
    paused = house.registry.entries_paused(agent.id) or {}
    if paused.get("session") == getattr(house, "DRAIN_SESSION", "house:drain") or agent.id in (house._state.get("wind_down_held") or {}):
        return "drained or winding down"
    if _holding(house, agent):
        return "holding a position or a working order"
    jobs = getattr(house, "research_jobs", None)
    if jobs is not None and jobs.active(agent.id):
        return "research in flight"  # a paid session the retirement would cancel: it waits for it, as the seat market does
    return ""


def _holding(house: Any, agent: Any) -> bool:
    """A position or a working order on any book it has an account on (a demoted agent may still hold real ones)."""
    for book in list(house.books.values()):
        if agent.id not in book.accounts:
            continue
        held = list(book.account(agent.id).holdings.values())  # copied at once: wakes run beside this
        if any(h.quantity != 0 for h in held) or book.open_orders(agent.id):
            return True
    return False


def _proven(house: Any, agent: Any) -> bool:
    """The allocator's family record says proven or swinging (`House._family_proven`'s reading), failing closed: a
    record that cannot be read protects the resident."""
    reader = getattr(getattr(house, "allocator", None), "family", None)
    if not agent.family:
        return False
    if reader is None:
        return True
    try:
        record = reader(agent.family, agent.venue)
    except Exception:  # noqa: BLE001 - an unreadable record protects: this path retires outside the seat market
        return True
    return bool(record and (record.get("proven") or record.get("state") in ("proven", "swing")))


def _allowed(house: Any, agent: Any) -> bool:
    """The seat market's answer checked again on the resident chosen: alive, never on real money, never a member of
    a proven or swinging family, whoever asks."""
    return agent.alive and house.evaluator.rung(agent.id) < 2 and not _proven(house, agent)


def _kept(kept: Mapping[str, int]) -> str:
    """The rules that kept residents, most first: "(kept: a winner 12, real money 3)"."""
    if not kept:
        return ""
    return " (kept: " + ", ".join(f"{rule} {n}" for rule, n in sorted(kept.items(), key=lambda kv: (-kv[1], kv[0]))[:6]) + ")"


def _found(house: Any, key: str, sha: str, niche: Any) -> Any | None:
    """The founder, born through `House.found` (rung 1, the owner's prior), or None when its program was refused."""
    try:
        born = house.found([key])
    except ValueError as exc:  # its NEEDS were refused (`House.spawn`): told once a program version
        with house._state_lock:
            _state(house)["refused"][key] = {"code": sha, "why": str(exc)[:300], "at": now_iso(house.clock)}
        house.alert("warning", f"the flagged founder {key} could not be born on {niche.id}: {str(exc)[:200]} "
                               "(asked again when its program changes)", founder=key, desk=niche.id)
        return None
    return born[0] if born else None


def _postmortem(key: str, born: Any, niche: Any, loser: Any, how: Mapping[str, Any]) -> str:
    record = how.get("record") or {}
    measured = (f"pooled forward record over the last {record.get('days', RECORD_DAYS):g} days is "
                f"{float(record.get('growth') or 0):+.4f} over {record.get('blocks')} active blocks")
    if how["rule"] == "desk full":
        return f"its desk {niche.id} was full and the founder {key} ({born.id}) takes its seat"
    if how["rule"] == "desk yields seats":
        return (f"its desk {loser.specialty} yields seats while its pooled record is negative: {how['reason'] or 'no reason given'} "
                f"(its {measured}; {how['members']} members, floor {how['floor']}); the founder {key} ({born.id}) takes the "
                f"seat on {niche.id}")
    return f"the league was full and the founder {key} ({born.id}, on {niche.id}) takes a seat from {loser.specialty}, whose {measured}"


def _record(house: Any, key: str, born: Any, niche: Any, how: Mapping[str, Any]) -> None:
    """The birth where the watch finds it: its `birth-route` row, an info alert, and house.json."""
    loser = how.get("loser")
    evidence = {"exception": "founder_paper_start", "replay_passed": False, "starts_on_rung": 1, FLAG: True,
                "founder": key, "desk": niche.id, "rule": how["rule"], "made_way": loser.id if loser else None,
                "made_way_desk": loser.specialty if loser else None, "cause": how.get("cause"), "record": how.get("record"),
                "reason": how.get("reason")}
    route = f"birth-route:{born.id}"
    if house.ledger.get(route) is None:
        try:
            house.ledger.append("route.decision", {"task": f"birth:{born.id}", "route": "founder", "model": None,
                                                   "reason": f"a founder row flagged {FLAG} ({how['rule']}): starts on paper "
                                                             "without a replay pass (deliberate exception)",
                                                   "evidence": evidence}, id=route)
        except LedgerConflict:
            pass  # labelled already: the first reason stands
    record = how.get("record") or {}
    if loser is None:
        where = "in a free seat"
    elif how["rule"] == "desk full":
        where = f"displacing {loser.id} on its full desk"
    elif how["rule"] == "desk yields seats":
        where = (f"in the seat {loser.specialty} yields ({loser.id} retired, {DESK_CLOSED}; the desk's pooled forward record "
                 f"{float(record.get('growth') or 0):+.4f} over {record.get('blocks')} active blocks in {RECORD_DAYS:g} days)")
    else:
        where = (f"displacing {loser.id} of {loser.specialty} in a full league ({loser.specialty}'s pooled forward record: "
                 f"{float(record.get('growth') or 0):+.4f} over {record.get('blocks')} active blocks in {RECORD_DAYS:g} days)")
    house.alert("info", f"the flagged founder {key} is seated on {niche.id} as {born.id} at rung 1, {where}",
                founder=key, agent=born.id, desk=niche.id, rule=how["rule"], made_way=evidence["made_way"], cause=how.get("cause"))
    with house._state_lock:
        state = _state(house)
        state["seated"][key] = {"agent": born.id, "desk": niche.id, "rule": how["rule"], "made_way": evidence["made_way"],
                                "made_way_desk": evidence["made_way_desk"], "cause": how.get("cause"), "at": now_iso(house.clock)}
        state["refused"].pop(key, None)
        (house._state.get("seat_refusals") or {}).pop(REFUSAL_CLASS, None)
    house._data_cache.pop("seat_waiters", None)


def _refuse(house: Any, waiting: list[str], why: str) -> None:
    """As `House._refuse_birth` for its waiter classes: the reason in house.json `seat_refusals` (health.json
    `seats.last_refused_birth.founders`), told as a warning at most once an hour."""
    now = house.clock()
    count = len(waiting)
    with house._state_lock:
        house._state.setdefault("seat_refusals", {})[REFUSAL_CLASS] = {
            "count": count, "why": why[:300], "at": now_iso(house.clock), "epoch": now, "founders": waiting[:20]}
        told = house._state.setdefault("seat_refusals_told", {})
        tell = now - float(told.get(REFUSAL_CLASS) or 0) >= TELL_SECONDS
        if tell:
            told[REFUSAL_CLASS] = now
    if tell:
        house.alert("warning", f"{count} flagged founder{'' if count == 1 else 's'} wait{'s' if count == 1 else ''} for a seat: {why}"[:1000],
                    founders=waiting[:20])


def _tell_error(house: Any, exc: Exception) -> None:
    """One warning an hour for the same error: an error every births pass must not escalate (`REPEAT_WARNINGS`)."""
    text = f"the flagged founders could not be seated this pass ({type(exc).__name__}: {str(exc)[:200]}); the births pass goes on"
    try:
        now = house.clock()
        with house._state_lock:
            told = _state(house).setdefault("error_told", {})
            for old in [t for t, at in told.items() if now - float(at or 0) >= TELL_SECONDS]:
                told.pop(old, None)
            tell = text not in told
            if tell:
                told[text] = now
        if tell:
            house.alert("warning", text)
    except Exception:  # noqa: BLE001 - a House that cannot even be told this must still finish its births pass
        pass


def _state(house: Any) -> dict[str, Any]:
    """house.json `kalshi_founders`: `seated` (key -> the birth), `refused` (key -> the program refused), `error_told`."""
    with house._state_lock:
        state = house._state.setdefault(_STATE, {})
        state.setdefault("seated", {})
        state.setdefault("refused", {})
        return state
