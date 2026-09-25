"""Flagged founder rows seated into a full league (K1, the Kalshi-scale run, Sept 25, 2026).

`House.found` seats a desk's founder rows (`league/niches.json` `founders`) on rung 1 without a replay: they are
the owner's priors, forward-tested from the first day. It runs only while the league is under `min_population`,
and the league sits at its ceiling (128 of 128 at the Sept 25 T0). The Kalshi-scale run adds model-versus-market
sports founders to `kalshi-sports` for the weekend slate (college football Saturday, the NFL Sunday, MLB's final
weekend), each row flagged `"seat_full_league": true`; a founder that prices games from the live `odds` feed on a
day-horizon desk has no replay for 20 days, so `enroll`'s replay path cannot seat it either.

`seat(house)` is called once a births pass (`House._births`, right after `enroll`) and births at most ONE flagged
founder a call, through `house.found([key])`:

- a flagged row of a non-dormant Kalshi desk whose `key` no agent, living or dead, was born with (`Agent.founder`):
  a founder that died is never reborn, and one already seated is not seated again, across ticks and restarts;
- in a league with room on a desk with room: seated in the free seat;
- on a FULL DESK: the desk's weakest eligible resident makes way, asked as `enroll` asks
  (`House._weakest(rules, specialty=desk, evidenced=True, newcomer=Newcomer(...))`);
- in a FULL LEAGUE (its desk has room): a seat is taken from the desk whose pooled forward record over the last
  `RECORD_DAYS` (7) days is the most negative (`desk_records`: `House.family_forward`'s statistic -- active
  `eval.block` rows and their summed log growth, over every agent ever born there -- by desk and over the forward-
  first run's F3 window), the next negative desk when none of its residents may go, and never a desk whose record is
  not negative by the House's own line (`families.losing`, `economy.losing_family_min_blocks` active blocks). The
  resident is the first of that desk in the House's own ranking (`House._displaceable`, league-wide, least evidence
  first), leaving out the desks whose next freed seat a higher class of waiter holds (`_reserved_desks`, `_keep_for`),
  as `enroll` does;
- the resident is killed `displaced` with a postmortem naming the founder, as `enroll` does, only once the founder
  is born. Every protection of `_displaceable` holds (real money, a winner, grace and evidence clock with the
  evidenced newcomer's exceptions, a proven family's member, a position held while its market is shut, a trader
  short of its record, one displacement a desk a tick), and two are checked again on the chosen resident: never a
  seat on rung 2 or above, never a member of a proven family (`_family_proven`), whoever asks;
- nobody may be displaced: nothing is born, the reason is kept where health.json shows a refused birth
  (house.json `seat_refusals.founders`, `seats.last_refused_birth`) and told as one warning an hour at most.

Each birth writes its `birth-route:<agent>` row (route `founder`, with the flag, the rule, the resident displaced
and its desk's record) before the foundry's labeller can, and an info alert naming the founder and whom it
displaced; house.json `kalshi_founders.seated` keeps the same. A program that cannot be born (its NEEDS refused) is
told once and tried again when its code changes. An exception anywhere in here is a warning (one an hour for the
same text) and never breaks the births pass.
"""

from __future__ import annotations

from contextlib import nullcontext
from typing import Any, Mapping

from .agents import code_sha
from .families import losing
from .ledger import LedgerConflict, now_iso

#: The founder row's flag (`league/niches.json`): seated even in a full league.
FLAG = "seat_full_league"
#: The desks this module seats: the Kalshi desks this run owns (the options run seats its own founders).
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


def seat(house: Any) -> Any | None:
    """One births pass's flagged founder: the Agent born, or None. Never raises (an error is a warning)."""
    try:
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
            house.kill(loser, "displaced", house.postmortem(loser, "displaced", _postmortem(key, born, niche, loser, how)))
        _record(house, key, born, niche, how)
        return born
    if why_not:
        _refuse(house, waiting, "; ".join(why_not))
    return None


def _room(house: Any, rules: Mapping[str, Any], niche: Any, newcomer: Any) -> dict[str, Any]:
    """Where the founder sits: `rule` ("free seat", "desk full" or "league full") with the `loser` to displace and,
    in a full league, its desk's `record`; or `why` nobody may make way."""
    members, cap = house.members(niche.id), int(niche.max_members)
    if members >= cap:
        kept: dict[str, int] = {}
        rank = house._displaceable(rules, specialty=niche.id, evidenced=True, newcomer=newcomer, why=kept)
        loser = next((row[-1] for row in rank if _allowed(house, row[-1])), None)
        if loser is None:
            return {"why": f"its desk is full ({members} of {cap}) and no resident may be displaced{_kept(kept)}"}
        return {"rule": "desk full", "loser": loser}
    living, ceiling = len(house.registry.living()), int(rules["max_population"])
    if living < ceiling:
        return {"rule": "free seat", "loser": None}
    minimum = int(rules.get("losing_family_min_blocks", 6))
    negative = sorted((growth, desk, blocks) for desk, (blocks, growth) in desk_records(house).items()
                      if losing(blocks, growth, minimum))
    if not negative:
        return {"why": f"the league is full ({living} of {ceiling}) and no desk's pooled forward record over the last "
                       f"{RECORD_DAYS:g} days is negative over {minimum} active blocks or more"}
    reserved = house._reserved_desks(house.seat_waiters(), below="strategies")
    kept = {}
    rank = house._displaceable(rules, evidenced=True, newcomer=newcomer, exclude=house._keep_for(reserved), why=kept)
    first: dict[str, Any] = {}
    losers = {desk for _, desk, _ in negative}
    for row in rank:  # the House's order: least evidence first
        agent = row[-1]
        if agent.specialty in losers and agent.specialty not in first and _allowed(house, agent):
            first[agent.specialty] = agent
    for growth, desk, blocks in negative:  # the most negative desk first
        if desk in first:
            return {"rule": "league full", "loser": first[desk],
                    "record": {"desk": desk, "days": RECORD_DAYS, "blocks": blocks, "growth": round(growth, 6)}}
    shown = ", ".join(f"{desk} {growth:+.4f} over {blocks}" for growth, desk, blocks in negative[:4])
    held = f"; {len(reserved)} desk(s) are held for waiting newcomers of a higher class" if reserved else ""
    return {"why": f"the league is full ({living} of {ceiling}) and no resident of a desk whose pooled forward record over "
                   f"the last {RECORD_DAYS:g} days is negative ({shown}) may be displaced{held}{_kept(kept)}"}


def _allowed(house: Any, agent: Any) -> bool:
    """`_displaceable`'s answer checked again on the one resident chosen: alive, never on real money, never a
    member of a proven family, whoever asks."""
    if not agent.alive or house.evaluator.rung(agent.id) >= 2:
        return False
    return not house._family_proven(agent.family, agent.venue)


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
    if how["rule"] == "desk full":
        return f"its desk {niche.id} was full and the founder {key} ({born.id}) takes its seat"
    record = how["record"]
    return (f"the league was full and the founder {key} ({born.id}, on {niche.id}) takes a seat from {loser.specialty}, whose "
            f"pooled forward record over the last {record['days']:g} days is {record['growth']:+.4f} over {record['blocks']} active blocks")


def _record(house: Any, key: str, born: Any, niche: Any, how: Mapping[str, Any]) -> None:
    """The birth where the watch finds it: its `birth-route` row, an info alert, and house.json."""
    loser = how.get("loser")
    evidence = {"exception": "founder_paper_start", "replay_passed": False, "starts_on_rung": 1, FLAG: True,
                "founder": key, "desk": niche.id, "rule": how["rule"], "displaced": loser.id if loser else None,
                "displaced_desk": loser.specialty if loser else None, "record": how.get("record")}
    route = f"birth-route:{born.id}"
    if house.ledger.get(route) is None:
        try:
            house.ledger.append("route.decision", {"task": f"birth:{born.id}", "route": "founder", "model": None,
                                                   "reason": f"a founder row flagged {FLAG} ({how['rule']}): starts on paper "
                                                             "without a replay pass (deliberate exception)",
                                                   "evidence": evidence}, id=route)
        except LedgerConflict:
            pass  # labelled already: the first reason stands
    if loser is None:
        where = "in a free seat"
    elif how["rule"] == "desk full":
        where = f"displacing {loser.id} on its full desk"
    else:
        record = how["record"]
        where = (f"displacing {loser.id} of {loser.specialty} in a full league ({loser.specialty}'s pooled forward record: "
                 f"{record['growth']:+.4f} over {record['blocks']} active blocks in {record['days']:g} days)")
    house.alert("info", f"the flagged founder {key} is seated on {niche.id} as {born.id} at rung 1, {where}",
                founder=key, agent=born.id, desk=niche.id, rule=how["rule"], displaced=evidence["displaced"])
    with house._state_lock:
        state = _state(house)
        state["seated"][key] = {"agent": born.id, "desk": niche.id, "rule": how["rule"], "displaced": evidence["displaced"],
                                "displaced_desk": evidence["displaced_desk"], "at": now_iso(house.clock)}
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
