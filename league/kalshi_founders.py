"""Flagged founder rows seated into a full league (K1, the Kalshi-scale run, Sept 25, 2026).

`House.found` seats a desk's founder rows (`league/niches.json` `founders`) on rung 1 without a replay: they are
the owner's priors, forward-tested from the first day, their replay still run and counted as their family's first
trial. It runs only while the league is under `min_population`, and the league sits at its ceiling (128 of 128 at
the Sept 25 T0). The Kalshi-scale run adds model-versus-market sports founders to `kalshi-sports` for the weekend
slate (college football Saturday, the NFL Sunday, MLB's final weekend), each row flagged `"seat_full_league": true`;
a founder that prices games from the live `odds` feed on a day-horizon desk has no replay for 20 days, so `enroll`'s
replay path cannot seat it either.

The seat market is the forward-first run's; these are its conditions, accepted by this run:

- `seat(house)` is ONE call line in `House._births` (after `enroll`, and after the options run's
  `options_desk.seat_founders` once that is on main). It births at most ONE flagged founder a call, through
  `house.found([key])` (rung 1; its replay still runs, and for a live-feed day strategy it is refused as unsupported
  input: a wait, not a trial). The seat question, the birth and the death that makes room are one step under the
  House's lifecycle lock (`House._lifecycle_lock`, which the lab's births, the refill's admissions, every wake and
  every death hold), so nothing races it. The founder's NEEDS probe is read in the probe box BEFORE that step,
  holding nothing but the probe box the births phase holds, and handed to `found` (`described`): a Sail call under
  the lifecycle lock stalls every wake (the review of PR 159, `House._admit_researched`). The seat question is asked
  again under the lock after the probe, and a founder is born only if the answer still holds.
- Which founders: flagged rows (`FLAG` exactly `true`) of open Kalshi desks whose `key` no agent, living or dead,
  was ever born with (`Agent.founder`): a founder that died is never reborn, and one seated is never seated twice,
  across ticks and restarts. In the order of the row's integer `"seat_priority"` (lower first, `DEFAULT_PRIORITY`
  when absent), then desk, then row: only a few seats can be freed before F3, so the order decides which founders
  trade first. A malformed row (a flag that is not `true` or `false`, no key, a priority that is not an integer) is
  skipped and told, one warning an hour.
- A founder takes ONLY A FREE SEAT OF ITS OWN DESK (the run raises the sports and weather desks' caps for them). Its
  desk full, it waits. The league under its ceiling, it is born there. The league full, room is made elsewhere, one
  resident out for the founder in, so the league never grows:
  1. *The House's own seat market* (`_displaced`), league-wide, asked as the House asks for a newcomer WITHOUT
     forward evidence (`evidenced=False`, `Newcomer(family, "kalshi", forward=None)`: a founder has none), leaving out
     the desks a higher waiter class holds (`_reserved_desks`/`_keep_for`, as `enroll` does) and each desk's last
     trading member (`_last_traders`, as the House's own refill does): the first resident, in the House's order, of
     the desk whose pooled forward record over the last `RECORD_DAYS` (7) days is the most negative (`desk_records`),
     then the next negative desk; never a desk whose record is not negative by the House's line (`families.losing`
     at `economy.losing_family_min_blocks` active blocks). That resident dies `displaced`.
  2. *Then a yielding desk* (`_yielded`): a Kalshi desk whose niches.json row carries
     `"yields_seats": {"floor": 4, "reason": "..."}` gives up one practice resident while it has more than `floor`
     members and its own 7-day pooled record is negative; its weakest in `_displaceable`'s order without the market's
     graces (never traded first, a losing family first, then rung, growth, blocks and purse), never a winner or one of
     the founder's own family. It dies of its own cause, `desk_closed` (`DESK_CLOSED`), never `displaced`, so the
     displacement share and F3's tenure rules do not count it; the desk is stamped as `kill` stamps a displacement
     (`_desk_displaced`), so the seat market takes no second resident of it in the same tick. The row's flag is the
     switch: remove it and nothing yields.
  On both paths the resident chosen is never on real money, never a member of a proven or swinging family (the
  allocator's record; unreadable counts as proven), never one holding a position or a working order on any book,
  drained by the House (`DRAIN_SESSION`) or held for the open (`wind_down_held`), and never one with research in
  flight (`_protected`).
- The founder is born BEFORE the resident dies, in the same step under the lock, so no other newcomer takes the
  seat; if `found` refuses or raises, nobody dies. Its postmortem (`kill`'s, with this module's detail) names the
  founder, the desk's record and, for a yielding desk, its members, floor and reason; the program stays in the
  graveyard like any death, and a retained candidate is handed off by `kill`.
- Nobody may make way: nothing is born, and the reason is kept where health.json shows a refused birth (house.json
  `seat_refusals.founders`, `seats.last_refused_birth`), told as one warning an hour at most. A program whose NEEDS
  are refused is told once and tried again only when its code changes.

Each birth writes its `birth-route:<agent>` row (route `founder`, with the flag, the rule, who made way, its cause
and the desk's record) before the foundry's labeller can, and an info alert naming the founder and who made way;
house.json `kalshi_founders.seated` keeps the same. `seat` never raises: an error is a warning, one an hour for the
same kind of error, and the births pass goes on to the refill.

`desk_records` is F3's "pooled forward growth over the last 7 days" by desk: `House.family_forward`'s statistic
(active `eval.block` rows and their summed log growth, over every agent ever born there, living or dead) grouped by
desk, over the blocks that BEGAN in the window (the row's block `key`; a backlog written late is not counted as new).
It is folded after a cursor, keeps only the window's rows, and is kept `RECORD_CACHE_SECONDS` (an hour, as the seat
market watch): the first read of a process reads the ledger's `eval.block` rows once, each later one only the rows
since. When F3 lands its own 7-day desk record, `desk_records` should read it instead.
"""

from __future__ import annotations

import json
import math
import re
import threading
from contextlib import nullcontext
from typing import Any, Mapping, Sequence

from . import niches as niches_module
from .agents import code_sha
from .families import losing
from .ledger import HOUSE, LedgerConflict, now_iso

#: The founder row's flag (`league/niches.json`): seated even in a full league.
FLAG = "seat_full_league"
#: The founder row's order among the flagged (an integer, lower first).
PRIORITY = "seat_priority"
DEFAULT_PRIORITY = 100
#: The desk row's flag (`league/niches.json`): `{"floor": n, "reason": "..."}`, the desk gives up a practice resident
#: to a flagged founder while it has more than `floor` members and its pooled record is negative.
YIELD_FLAG = "yields_seats"
#: The cause of a death its yielding desk gave up: its own, never counted as a displacement.
DESK_CLOSED = "desk_closed"
#: The desks this module seats and asks to yield: the Kalshi desks this run owns (the options run seats its own).
VENUE = "kalshi"
#: The window of a desk's pooled forward record: the forward-first run's F3 window.
RECORD_DAYS = 7.0
#: How long the desks' records are reused: an hour, as the seat market watch (the births pass runs every 300 s).
RECORD_CACHE_SECONDS = 3600.0
_CACHE_KEY = "kalshi_founders_desk_records"
_AGENTS_KEY = ("kalshi_founders", "agent_records")
_TAPE_KEY = "kalshi_founders_desk_tape"
#: One warning an hour at most, for a founder that cannot be seated, a malformed row and an error in here.
TELL_SECONDS = 3600.0
#: The founder rows' class in house.json `seat_refusals` (health.json `seats.last_refused_birth`).
REFUSAL_CLASS = "founders"
_STATE = "kalshi_founders"
_FLAGS: dict[str, Any] = {}  # niches.json's `yields_seats` rows, read again when the file changes
_BLOCK_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2})?$")


def seat(house: Any) -> Any | None:
    """One births pass's flagged founder: the Agent born, or None. Never raises (an error is a warning). Nothing at all
    unless the House's `Settings.kalshi_founders` is on (the floor's House; never a test's or the canary's)."""
    if not getattr(getattr(house, "settings", None), "kalshi_founders", False):
        return None
    try:
        return _seat(house)
    except Exception as exc:  # noqa: BLE001 - the births pass goes on to the refill whatever happens here
        _tell(house, f"error:{type(exc).__name__}",
              f"the flagged founders could not be seated this pass ({type(exc).__name__}: {str(exc)[:200]}); the births pass goes on")
        return None


def pending(house: Any) -> list[tuple[Any, Mapping[str, Any]]]:
    """(niche, founder row) of every flagged founder of an open Kalshi desk whose key no agent was ever born with, in
    seat order: (`seat_priority`, desk, row). A malformed row is left out and told."""
    lock = getattr(house.registry, "_lock", None)
    with lock if lock is not None else nullcontext():
        born = {a.founder for a in house.registry.agents.values() if a.founder}
    rows, bad = [], []
    for niche in list(house.niches.values()):
        if niche.dormant or niche.venue != VENUE:
            continue
        for index, row in enumerate(niche.founders):
            if not isinstance(row, Mapping) or FLAG not in row:
                continue
            flag, key = row.get(FLAG), row.get("key")
            if flag is not True:
                if flag is not False:
                    bad.append(f"{niche.id} row {index}: {FLAG} is {flag!r}, not true or false")
                continue
            if not isinstance(key, str) or not key.strip():
                bad.append(f"{niche.id} row {index}: a flagged row with no key")
                continue
            priority = row.get(PRIORITY, DEFAULT_PRIORITY)
            if isinstance(priority, bool) or not isinstance(priority, int):
                bad.append(f"{niche.id} {key}: {PRIORITY} is {priority!r}, not an integer")
                continue
            if key not in born:
                rows.append((priority, niche.id, index, niche, row))
    if bad:
        _tell(house, "malformed", f"{len(bad)} flagged founder row{'' if len(bad) == 1 else 's'} of league/niches.json "
                                  f"{'is' if len(bad) == 1 else 'are'} skipped: " + "; ".join(bad[:6]))
    rows.sort(key=lambda r: r[:3])
    return [(niche, row) for _, _, _, niche, row in rows]


#: On the yield path a resident is kept as "a winner" only when its own forward record over the window is positive WITH
#: evidence: at least `losing_family_min_blocks` active blocks and a one-sided t of at least this. Measured Sept 25,
#: 2026, 22:00Z: crypto-15m's pooled 7-day record was -4.17 over 375 active blocks, yet 6 of its 7 members passed the
#: seat market's plain rule (own mean growth > 0), three of them on noise (t 0.32 over 26 blocks, t 0.19 over 15, one
#: block): the survivors of dead losers, so the desk the run closes could never yield a seat to a founder.
WINNER_T = 1.0


class _Tape:
    """The active `eval.block` rows whose block began inside the window, folded after a cursor: (began, agent, log
    growth). Bounded: a row leaves when the window passes it, and each fold reads only the rows after the cursor."""

    def __init__(self) -> None:
        self.cursor = 0
        self.rows: list[tuple[str, str, float]] = []
        self.lock = threading.Lock()

    def fold(self, ledger: Any, since: str) -> list[tuple[str, str, float]]:
        with self.lock:
            fresh = []
            for entry in ledger.iter(kinds="eval.block", after=self.cursor):
                self.cursor = entry.seq
                p = entry.payload
                if not p.get("active") or not entry.agent or entry.agent == HOUSE:
                    continue
                try:
                    growth = float(p.get("log_growth") or 0.0)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(growth):
                    fresh.append((_began(entry), entry.agent, growth))
            self.rows = [row for row in self.rows if row[0] >= since] + [row for row in fresh if row[0] >= since]
            return list(self.rows)


def _began(entry: Any) -> str:
    """When a block began, as the ledger's ISO stamps read: its `key` (`2026-09-20T13` an hour block, `2026-09-20` a
    day block, `evaluator.block_key`), else when its row was written."""
    key = entry.payload.get("key")
    if isinstance(key, str) and _BLOCK_KEY.match(key):
        return key + (":00:00.000Z" if "T" in key else "T00:00:00.000Z")
    return str(entry.at)


def desk_records(house: Any, *, days: float = RECORD_DAYS) -> dict[str, tuple[int, float]]:
    """Desk -> (active `eval.block` rows, their summed log growth) over the blocks that began in the last `days`: the
    pooled forward record `House.family_forward` keeps for a family (every agent ever born into it, living or dead),
    kept for a desk (every agent ever born on it) over the window F3 reads. Kept for `RECORD_CACHE_SECONDS`; the
    ledger is read after a cursor, never whole again."""
    now = house.clock()
    hit = house._data_cache.get(_CACHE_KEY)
    if hit and hit[2] == days and now - hit[0] < RECORD_CACHE_SECONDS:
        return hit[1]
    since = now_iso(lambda: now - days * 86400.0)
    kept = house._data_cache.get(_TAPE_KEY)
    tape = kept[1] if kept and kept[2] == days else _Tape()
    house._data_cache[_TAPE_KEY] = (now, tape, days)
    rows = tape.fold(house.ledger, since)
    lock = getattr(house.registry, "_lock", None)
    with lock if lock is not None else nullcontext():
        desk_of = {a.id: a.specialty for a in house.registry.agents.values() if a.specialty}
    out: dict[str, list[float]] = {}
    for _, agent, growth in rows:
        desk = desk_of.get(agent)
        if desk:
            row = out.setdefault(desk, [0, 0.0])
            row[0] += 1
            row[1] += growth
    value = {desk: (int(n), growth) for desk, (n, growth) in out.items()}
    house._data_cache[_CACHE_KEY] = (now, value, days)
    agents: dict[str, list[float]] = {}
    for _, agent, growth in rows:
        agents.setdefault(agent, []).append(growth)
    house._data_cache[_AGENTS_KEY] = (now, agents, days)
    return value


def agent_records(house: Any, *, days: float = RECORD_DAYS) -> dict[str, list[float]]:
    """Agent -> the log growth of each of its active blocks that began in the last `days`: the same rows, window and
    cache as `desk_records` (which it refreshes when stale)."""
    hit = house._data_cache.get(_AGENTS_KEY)
    if not (hit and hit[2] == days and house.clock() - hit[0] < RECORD_CACHE_SECONDS):
        house._data_cache.pop(_CACHE_KEY, None)  # both are made by one fold
        desk_records(house, days=days)
        hit = house._data_cache.get(_AGENTS_KEY)
    return hit[1] if hit else {}


def evidenced_winner(growths: Sequence[float], minimum: int) -> bool:
    """A forward record that is positive with evidence: at least `minimum` active blocks, a positive mean, and a
    one-sided t of at least `WINNER_T` (every block equal and positive counts as evidence)."""
    n = len(growths)
    if n < max(2, int(minimum)):
        return False
    mean = sum(growths) / n
    if mean <= 0:
        return False
    var = sum((g - mean) ** 2 for g in growths) / (n - 1)
    return var <= 0 or mean / math.sqrt(var / n) >= WINNER_T


def yielding(house: Any) -> dict[str, dict[str, Any]]:
    """Desk -> {"floor", "reason"}: the open Kalshi desks whose niches.json row carries a valid `yields_seats`
    (`niches.load` keeps no such key, so the row is read here, from the file the House loaded its desks from). A
    malformed flag yields nothing and is told."""
    path = niches_module.NICHES_PATH
    stamp = (str(path), path.stat().st_mtime_ns)
    if _FLAGS.get("stamp") != stamp:
        doc = json.loads(path.read_text(encoding="utf-8"))
        _FLAGS.update(stamp=stamp, rows={str(row.get("id")): row.get(YIELD_FLAG) for row in doc.get("niches") or ()
                                         if isinstance(row, Mapping) and row.get(YIELD_FLAG) is not None})
    out, bad = {}, []
    for desk, flag in (_FLAGS.get("rows") or {}).items():
        niche = house.niches.get(desk)
        if niche is None or niche.dormant or niche.venue != VENUE:
            continue
        floor = flag.get("floor") if isinstance(flag, Mapping) else None
        if isinstance(floor, bool) or not isinstance(floor, int) or floor < 1:
            bad.append(f"{desk}: {YIELD_FLAG} is {flag!r}, not {{\"floor\": an integer of 1 or more, \"reason\": ...}}")
            continue
        out[desk] = {"floor": floor, "reason": str(flag.get("reason") or "").strip()}
    if bad:
        _tell(house, "malformed-yield", "a desk row of league/niches.json yields no seat: " + "; ".join(bad[:4]))
    return out


def _lock(house: Any) -> Any:
    lock = getattr(house, "_lifecycle_lock", None)
    return lock if lock is not None else nullcontext()


def _seat(house: Any) -> Any | None:
    if not pending(house):
        return None  # every flagged founder has been born: nothing to read, nothing to ask
    from .house import PROBE_BOX  # here: league.house imports this module

    with _lock(house):
        chosen = _choose(house)
    if chosen is None:
        return None
    key = chosen["row"]["key"]
    # The NEEDS probe outside the lifecycle lock: every wake takes that lock, and Sail stalling under it stalls the
    # whole tick (review of PR 159). The births phase holds the probe box; this probe re-enters it, as `found`'s does.
    described = house.sandbox.needs(PROBE_BOX, chosen["row"]["code"])
    with _lock(house):
        # The probe took seconds: a birth or a death may have moved the answer. Asked again, and the founder is born
        # only when the same founder still has a seat.
        again = _choose(house)
        if again is None or again["row"]["key"] != key or again["row"]["code"] != chosen["row"]["code"]:
            return None
        niche, how = again["niche"], again["how"]
        born = _found(house, key, code_sha(again["row"]["code"]), niche, described)
        if born is None:
            return None  # refused or born meanwhile: nobody dies
        try:
            _retire(house, key, born, niche, how)
        finally:
            _record(house, key, born, niche, how)
    return born


def _choose(house: Any) -> dict[str, Any] | None:
    """The first flagged founder, in seat order, whose own desk has a free seat and for whom the league has room or
    makes it: {"niche", "row" (the House's founder row), "how"}; or None, the reason kept (`_refuse`). One league
    question a call: the founders behind the first with a seat on its desk wait for it."""
    wanted = pending(house)
    if not wanted:
        return None
    rules = house.game["economy"]
    state = _state(house)
    rows = house.founders()
    by_key = {row["key"]: row for row in rows}
    desk_names = {niche.desk for niche in house.niches.values()}
    candidates, waiting, why_not = [], [], []
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
        if (state["refused"].get(key) or {}).get("code") == code_sha(row["code"]):
            continue  # its program could not be born (told once); asked again when its code changes
        waiting.append(key)
        candidates.append((niche, row))
    living, ceiling = len(house.registry.living()), int(rules["max_population"])
    for niche, row in candidates:
        members, cap = house.members(niche.id), int(niche.max_members)
        if members >= cap:
            why_not.append(f"{row['key']} on {niche.id}: its desk is full ({members} of {cap}), and a founder takes only a "
                           "free seat of its own desk")
            continue
        if living < ceiling:
            return {"niche": niche, "row": row, "how": {"rule": "free seat", "loser": None, "cause": None}}
        how = _room(house, rules, niche, row, living, ceiling)
        if not how.get("why"):
            return {"niche": niche, "row": row, "how": how}
        why_not.append(f"{row['key']} on {niche.id}: {how['why']}")
        break  # one league question a pass: the next founders wait behind this one
    if why_not:
        _refuse(house, waiting, "; ".join(why_not))
    return None


def _room(house: Any, rules: Mapping[str, Any], niche: Any, row: Mapping[str, Any], living: int, ceiling: int) -> dict[str, Any]:
    """Room in a full league for a founder whose desk has a free seat: `rule` ("league full" or "desk yields seats")
    with the `loser` that makes way, its `cause` and its desk's `record`; or `why` nobody may make way."""
    from .house import Newcomer  # here: league.house imports this module

    newcomer = Newcomer(family=row["family"], venue=VENUE, forward=None, what=f"the founder {row['key']}")
    market = _displaced(house, rules, newcomer)
    if not market.get("why"):
        return market
    yielded = _yielded(house, rules, niche, row["family"])
    if not yielded.get("why"):
        return yielded
    return {"why": f"the league is full ({living} of {ceiling}) and {market['why']}; and no desk yields a seat: {yielded['why']}"}


def _displaced(house: Any, rules: Mapping[str, Any], newcomer: Any) -> dict[str, Any]:
    """The House's own seat market in a full league, for a newcomer without forward evidence: the first resident, in
    its order, of the most negative desk."""
    minimum = int(rules.get("losing_family_min_blocks", 6))
    negative = sorted((growth, desk, blocks) for desk, (blocks, growth) in desk_records(house).items()
                      if losing(blocks, growth, minimum))
    if not negative:
        return {"why": f"no desk's pooled forward record over the last {RECORD_DAYS:g} days is negative over {minimum} "
                       "active blocks or more"}
    reserved = house._reserved_desks(house.seat_waiters(), below="strategies")
    exclude = set(house._keep_for(reserved)) | set(house._last_traders(house.registry.living()))
    kept: dict[str, int] = {}
    rank = house._displaceable(rules, evidenced=False, newcomer=newcomer, exclude=tuple(sorted(exclude)), why=kept)
    first: dict[str, Any] = {}
    losers = {desk for _, desk, _ in negative}
    for row in rank:  # the House's order: least evidence first
        agent = row[-1]
        if agent.specialty not in losers or agent.specialty in first:
            continue
        why = _protected(house, agent)
        if why:
            kept[why] = kept.get(why, 0) + 1
            continue
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
    own = agent_records(house)
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
        displaced_at = (getattr(house, "_desk_displaced", None) or {}).get(desk)
        if displaced_at is not None and house.clock() - float(displaced_at) < float(house.settings.tick_seconds):
            # One seat a desk a tick, whichever rule took it: the forward-first run's F3 shrinks this desk toward its floor
            # in the same births pass, before this line, and the House's own seat market stamps the desk the same way.
            notes.append(f"{desk} already gave up a seat this tick")
            continue
        if not losing(blocks, growth, minimum):
            notes.append(f"{desk}'s pooled forward record over the last {RECORD_DAYS:g} days is not negative "
                         f"({growth:+.4f} over {blocks} active blocks)")
            continue
        kept: dict[str, int] = {}
        ranked = []
        for agent in members:
            why = _protected(house, agent, family)
            standing = None if why else house._standing(agent, epoch)
            if standing is not None and evidenced_winner(own.get(agent.id) or (), minimum):
                why = "a winner"  # positive with evidence over the window (`WINNER_T`); the seat market's plain rule kept noise
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


def _protected(house: Any, agent: Any, family: str | None = None) -> str:
    """Why a resident chosen to make way for a founder may not, whichever path chose it, or "". `family`: the
    founder's own, which a yielding desk never gives up to it."""
    current = house.registry.get(agent.id)
    if current is None or not current.alive:
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
        return "research in flight"  # a paid session the death would cancel: it waits for it, as the seat market does
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
    except Exception:  # noqa: BLE001 - an unreadable record protects: this path kills outside the House's own rules
        return True
    return bool(record and (record.get("proven") or record.get("state") in ("proven", "swing")))


def _kept(kept: Mapping[str, int]) -> str:
    """The rules that kept residents, most first: "(kept: a winner 12, real money 3)"."""
    if not kept:
        return ""
    return " (kept: " + ", ".join(f"{rule} {n}" for rule, n in sorted(kept.items(), key=lambda kv: (-kv[1], kv[0]))[:6]) + ")"


def _found(house: Any, key: str, sha: str, niche: Any, described: Any) -> Any | None:
    """The founder, born through `House.found` (rung 1, the owner's prior) from the NEEDS probe read before the lock,
    or None when its program was refused or it was born meanwhile."""
    try:
        born = house.found([key], described={key: described})
    except ValueError as exc:  # its NEEDS were refused (`House.spawn`): told once a program version
        with house._state_lock:
            _state(house)["refused"][key] = {"code": sha, "why": str(exc)[:300], "at": now_iso(house.clock)}
        house.alert("warning", f"the flagged founder {key} could not be born on {niche.id}: {str(exc)[:200]} "
                               "(asked again when its program changes)", founder=key, desk=niche.id)
        return None
    return born[0] if born else None


def _retire(house: Any, key: str, born: Any, niche: Any, how: Mapping[str, Any]) -> None:
    """The resident that makes way dies, now that the founder is born (`kill` writes its postmortem)."""
    loser = how.get("loser")
    if loser is None:
        return
    current = house.registry.get(loser.id)
    if current is None or not current.alive:
        return
    house.kill(current, how["cause"], _postmortem(key, born, niche, current, how))
    if how["cause"] == DESK_CLOSED and current.specialty and isinstance(getattr(house, "_desk_displaced", None), dict):
        # One seat out of a desk a tick, as `kill` stamps a displacement: the seat market takes no second one here.
        house._desk_displaced[current.specialty] = house.clock()


def _postmortem(key: str, born: Any, niche: Any, loser: Any, how: Mapping[str, Any]) -> str:
    record = how.get("record") or {}
    measured = (f"pooled forward record over the last {record.get('days', RECORD_DAYS):g} days is "
                f"{float(record.get('growth') or 0):+.4f} over {record.get('blocks')} active blocks")
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


def _tell(house: Any, topic: str, text: str) -> None:
    """One warning an hour a topic (an error's kind, a malformed row): a warning every births pass must not
    escalate (`REPEAT_WARNINGS`). Never raises."""
    try:
        now = house.clock()
        with house._state_lock:
            told = _state(house).setdefault("told", {})
            for old in [t for t, at in told.items() if now - float(at or 0) >= TELL_SECONDS]:
                told.pop(old, None)
            tell = topic not in told
            if tell:
                told[topic] = now
        if tell:
            house.alert("warning", text[:1000])
    except Exception:  # noqa: BLE001 - a House that cannot even be told this must still finish its births pass
        pass


def _state(house: Any) -> dict[str, Any]:
    """house.json `kalshi_founders`: `seated` (key -> the birth), `refused` (key -> the program refused), `told`."""
    with house._state_lock:
        state = house._state.setdefault(_STATE, {})
        state.setdefault("seated", {})
        state.setdefault("refused", {})
        return state
