"""PREREG-EVL-3's bands (section 2): the band each seating program version is in, and the rules that move it.

- LEARNING, the band at registration: real money at learning size from the first event (the House's event book sizes
  it: 2% of equity, whole shares, one share up to 5%).
- PROBE from the first decision after a passed look (`on_look`, called when the screen writes a look of a seating
  version: version 2 of PREREG-EVL-1's and -2's programs, version 1 of PREREG-EVL-4's).
- SIZED: >= 150 settled real-money events at Probe size or above whose 80% session-block bootstrap lower bound of the
  per-event after-cost return is above zero (`review`).
- DEMOTION to learning: the last 50 settled real-money events at Probe size or above lost more than $150 net, or the
  last 100 such events have a negative mean after-cost return (`review`); back to Probe at the next passed look. The
  two windows count the program's CURRENT Probe stay (release 1019b's second review): the events whose buy came after
  its latest move to Probe (`probe_since`, from `band_history`), so a program the next passed look returns to Probe
  is not demoted again on the events that demoted it. SIZED counts the current Probe stay too (release 1019b's third
  review, the reading that trades less): its >= 150 events and its 80% bound are over the Probe+ events bought after
  the latest move to Probe, so a program demoted from Sized and returned to Probe earns Sized again on its new stay,
  never at once on the events of the stay that was demoted.
- RETIRED, for good: a held look whose mean after-cost abnormal return is below zero and whose one-sided sign-flip p
  for a mean below zero (the session-block test with every value's sign reversed) is at most 0.05 (`on_look`).

The lane writes `bands` and `band_history`; the House's event book (league/events/book.py) reads `bands(store)` and
writes `real_fills` through `record_fill` (one row a fill, idempotent per (program, version, event, side); a posted fee
updates its row). The House's lane (league/events/house.py) runs `review` after each night's screen. Nothing here reads
a price after an event other than the real fills the House reports and the screen's own looks.

THE PROBE SIZE'S RECORD (release 1019f; a record only, no rule here reads it): a buy's row also keeps `target_usd`, the
dollars its band's target asked (the band's `position_share` x E at the previous close), `binding`, which constraint
cut it below that (`BINDINGS`; None when none did), and `sized_usd`, the dollars its send asked (the shares sent x the
limit), written with the row and never changed after. The band rules above count a fill by its `band` label, as
PREREG-EVL-3 section 2 has it; the Done reader (league/events/done.py) reads "Probe size or above" as `sized_usd` >=
0.8 x `target_usd` (the send's dollars at the limit, never the fill's cost, which the open's gap moves).
"""

from __future__ import annotations

import bisect
import datetime as dt
import json
import math
from typing import Any, Iterable, Mapping, Sequence

from . import calendar as C
from . import programs as P
from . import screen as SC
from . import store as S

BANDS = ("learning", "probe", "sized", "retired")
PROBE_PLUS = ("probe", "sized")
DEMOTE_LAST = 50
DEMOTE_NET_USD = -150.0
DEMOTE_MEAN_LAST = 100
SIZED_MIN = 150
RETIRE_P = 0.05
#: RELEASE 1019f: what may cut a real buy below its band's target, as `real_fills.binding` (and the House's
#: `eq_event_intents.binding`) records it: the House-wide CASH; the loss BUDGET at the lot's weight; the book's 100%
#: INVESTED; the NAME_WALL (the book-wide 10% a name, or the program's own share of it); the GATEWAY's final refusal (a
#: buy that never filled); the WHOLE_SHARES (no cap cut the dollars, the floor to whole shares did); the VENUE (it
#: filled less than the order asked). NULL: none did (the buy is at its target, or one share above it).
BINDINGS = ("cash", "budget", "invested", "name_wall", "gateway", "whole_shares", "venue")


def seating() -> dict[tuple[str, int], P.Program]:
    return {(p.id, p.version): p for p in P.SEATING}


def bands(store: S.Store) -> dict[tuple[str, int], str]:
    """{(program, version): band} for every version that may trade real money; no row is "learning"."""
    out = {key: "learning" for key in seating()}
    for row in store.db.execute("SELECT program, version, band FROM bands"):
        key = (str(row["program"]), int(row["version"]))
        if key in out:
            out[key] = str(row["band"])
    return out


def set_band(store: S.Store, program: str, version: int, band: str, *, since: str, why: str, now: Any = None,
             db: Any = None) -> bool:
    """Move (program, version) to `band` (a seating version only). A retired program never moves again. Returns
    whether anything changed. `db`: a transaction of `store` already open (the screen's look, `screen.write_look`),
    written in it; else in a transaction of its own."""
    if band not in BANDS:
        raise ValueError(f"{band!r} is not one of {BANDS}")
    key = (program, int(version))
    if key not in seating():
        raise ValueError(f"{program} v{version} may not trade real money (PREREG-EVL-3 section 1)")
    current = bands(store)[key]
    if current == band or current == "retired":
        return False
    written = S.iso(now or S.utc_now())

    def write(tx: Any) -> None:
        tx.execute("INSERT OR REPLACE INTO bands(program, version, band, since, why) VALUES(?, ?, ?, ?, ?)",
                   (program, int(version), band, since, why))
        tx.execute("INSERT INTO band_history(program, version, band, since, why, written_at) VALUES(?, ?, ?, ?, ?, ?)",
                   (program, int(version), band, since, why, written))
    if db is not None:
        write(db)
    else:
        with store.tx() as tx:
            write(tx)
    return True


def retire_test(session_values: Iterable[float], mean_a: float | None, seed_text: str, draws: int = SC.B) -> dict[str, Any]:
    """PREREG-EVL-3's retirement test at a held look: mean a below zero and the reversed one-sided sign-flip p (every
    session value's sign reversed, the look's own sign vectors) at most RETIRE_P."""
    values = [-float(v) for v in session_values]
    if not values or mean_a is None:
        return {"retire": False, "p_below": None}
    p_below = SC.signflip_p(values, SC.seed_of(seed_text), draws)
    return {"retire": bool(mean_a < 0 and p_below <= RETIRE_P), "p_below": p_below}


def superseded_guard(look: Mapping[str, Any], now: Any = None) -> bool:
    """PREREG-EVL-6 section 1.1, THE D7 GUARD: True when `look` is a look of a version PREREG-EVL-6 SUPERSEDES
    (league/events/programs.py `Program.superseded6`: version 2 of the nine, version 1 of PREREG-EVL-4's and -5's three,
    version 1 of a seatable birth registered before REGISTERED_AT_6) written or as of a close at or after REGISTERED_AT_6,
    whatever the release date: such a look is written and reported (the shadow record's PREREG-EVL-3 looks) and moves no
    band, no promotion, no retirement, no demotion. A look whose as-of or write time cannot be read is guarded too (the
    reading that moves nothing)."""
    prog = P.BY_KEY.get((str(look.get("program")), int(look.get("version") or 0)))
    if prog is None or not prog.superseded6:
        return False
    if P.REGISTERED_AT_6 is None:
        return True
    since = S.parse_iso(P.REGISTERED_AT_6)
    try:
        written = S.parse_iso(str(now)) if isinstance(now, str) else (now or S.utc_now())
        at = S.parse_iso(str(look.get("at")))
    except (TypeError, ValueError):
        return True
    return written >= since or at >= since


def on_look(store: S.Store, look: Mapping[str, Any], *, now: Any = None, db: Any = None) -> str | None:
    """With the screen's write of a seating version's look: retire, promote a learning program to probe, or nothing.
    Returns the new band or None. `db`: the look's own transaction (release 1019b's review: the move is written with
    the look or not at all, so a lost move can never leave a retired program trading). PREREG-EVL-6: a look of a
    version it supersedes moves nothing from REGISTERED_AT_6 (`superseded_guard`, D7); a look of a version it judges is
    `on_look6`'s (its RETIRE and PASS, section 1.4)."""
    if superseded_guard(look, now):
        return None
    prog = P.BY_KEY.get((str(look["program"]), int(look["version"])))
    if prog is not None and prog.evl6:
        return on_look6(store, look, now=now, db=db)
    key = (str(look["program"]), int(look["version"]))
    if key not in seating() or not int(look.get("held") or 0):
        return None
    if (look.get("retirement") or {}).get("retire"):
        if set_band(store, key[0], key[1], "retired", since=str(look["at"]), now=now, db=db,
                    why=f"look {look['k']}: mean a < 0, reversed p {look['retirement']['p_below']:.4f} <= {RETIRE_P}"):
            return "retired"
        return None
    if int(look.get("passed") or 0) and bands(store)[key] == "learning":
        if set_band(store, key[0], key[1], "probe", since=str(look["at"]), now=now, db=db,
                    why=f"look {look['k']} passed"):
            return "probe"
    return None


def real_events(store: S.Store, program: str, version: int, *, at: Iterable[str] = PROBE_PLUS) -> list[dict[str, Any]]:
    """The settled real-money events of (program, version) whose buy was at one of the bands `at`, oldest sale first:
    {event, entry_day, issuer, band, pnl, r} (r after fees, on the buy's cost)."""
    want = set(at)
    fills: dict[str, dict[str, Mapping[str, Any]]] = {}
    for row in store.db.execute("SELECT * FROM real_fills WHERE program=? AND version=?", (program, int(version))):
        fills.setdefault(str(row["event"]), {})[str(row["side"])] = dict(row)
    out = []
    for event, sides in fills.items():
        buy, sell = sides.get("buy"), sides.get("sell")
        if buy is None or sell is None or str(buy["band"]) not in want:
            continue
        cost = float(buy["qty"]) * float(buy["price"]) + float(buy["fee"] or 0)
        if cost <= 0:
            continue
        proceeds = float(sell["qty"]) * float(sell["price"]) - float(sell["fee"] or 0)
        intent = store.db.execute("SELECT entry_day, cik, symbol FROM intents WHERE program=? AND version=? AND event=?",
                                  (program, int(version), event)).fetchone()
        out.append({"event": event, "entry_day": intent["entry_day"] if intent else str(buy["filled_at"])[:10],
                    "issuer": (intent["cik"] or intent["symbol"]) if intent else event, "band": str(buy["band"]),
                    "pnl": proceeds - cost, "r": (proceeds - cost) / cost, "sold_at": str(sell["filled_at"]),
                    "bought_at": str(buy["filled_at"])})
    out.sort(key=lambda r: (r["sold_at"], r["event"]))
    return out


def probe_since(store: S.Store, program: str, version: int) -> Any:
    """When (program, version)'s CURRENT Probe stay began: its latest move to probe in `band_history`, at the later of
    the move's `since` (a look's as-of close) and its write (the band changed then); None when it never moved there."""
    row = store.db.execute("SELECT since, written_at FROM band_history WHERE program=? AND version=? AND band='probe' "
                           "ORDER BY id DESC LIMIT 1", (program, int(version))).fetchone()
    if row is None:
        return None
    moments = []
    for text in (row["since"], row["written_at"]):
        try:
            moments.append(S.parse_iso(str(text)))
        except (TypeError, ValueError):
            continue
    return max(moments) if moments else None


def _after(event: Mapping[str, Any], since: Any) -> bool:
    if since is None:
        return True
    try:
        return S.parse_iso(str(event["bought_at"])) > since
    except (KeyError, TypeError, ValueError):
        return True     # (a buy whose time cannot be read counts: the reading that demotes)


def review(store: S.Store, *, now: Any = None) -> list[dict[str, Any]]:
    """Demotion and Sized from the real fills (PREREG-EVL-3 section 2), for every probe or sized program. The demotion
    windows and Sized's count and bound are over the current Probe stay (`probe_since`: its Probe+ events bought after
    the latest move to Probe; release 1019b's second and third reviews)."""
    changes = []
    when = S.iso(now or S.utc_now())
    for (program, version), band in bands(store).items():
        if band not in PROBE_PLUS:
            continue
        prog = P.BY_KEY.get((program, int(version)))
        if prog is not None and prog.evl6:
            # (PREREG-EVL-6 section 3: its versions' reads, money stop, stay looks and Sized, in its order)
            changes += review6(store, program, version, now=now)
            continue
        events = real_events(store, program, version)
        if not events:
            continue
        since = probe_since(store, program, version)
        stay = [e for e in events if _after(e, since)]
        last = stay[-DEMOTE_LAST:]
        net = math.fsum(e["pnl"] for e in last)
        last_mean = stay[-DEMOTE_MEAN_LAST:]
        mean = math.fsum(e["r"] for e in last_mean) / len(last_mean) if last_mean else 0.0
        if net < DEMOTE_NET_USD or (len(last_mean) == DEMOTE_MEAN_LAST and mean < 0):
            why = (f"the last {len(last)} Probe+ events lost ${-net:.2f} net" if net < DEMOTE_NET_USD
                   else f"the last {DEMOTE_MEAN_LAST} Probe+ events' mean after-cost return {mean:.5f} < 0")
            if set_band(store, program, version, "learning", since=when, why=why, now=now):
                changes.append({"program": program, "version": version, "band": "learning", "why": why})
            continue
        if band == "probe" and len(stay) >= SIZED_MIN:
            bound = SC.sized_bound(stay)
            if bound["ok"] and set_band(store, program, version, "sized", since=when, now=now,
                                        why=f"{len(stay)} Probe+ events of the current Probe stay, 80% session-block "
                                            f"lower bound {bound['session']['lower']:.5f} > 0"):
                changes.append({"program": program, "version": version, "band": "sized", "why": "sized"})
    return changes


# ============================================================================= PREREG-EVL-6 sections 1.4 and 3
#: PREREG-EVL-6 section 3, for the versions it judges (league/events/programs.py `Program.evl6`): THE FIXED READS at
#: every READ_EVERY-th real-money Probe+ event of a stay (p <= READ_P + 1e-12 for a mean below zero, D15), THE MONEY STOP
#: over the whole stay (net after-fee P&L under -STOP_SHARE x the buy cost, D10), SIZED from a stay look's PASS with
#: >= SIZED_MIN6 settled real-money events at Probe size or above whose summed P&L is above 0 and fills within FILL_BP_6
#: of the shadow's auction prices a side (the Done reader's fill rule). PREREG-EVL-3's $150 stop, rolling last-100 read,
#: 150-event bootstrap Sized and reversed-p retirement do not apply to these versions.
READ_EVERY = 100
READ_P = 0.15
STOP_SHARE = 0.10
SIZED_MIN6 = 30
FILL_BP_6 = 15.0
#: A STAY'S REAL-MONEY EVENT UNSETTLED PAST THE LADDER (the readings that demote more and trade less, section 7, for
#: the captain's amendment before the first PREREG-EVL-6 look): the order at a close waits for THAT close's real-money
#: events, each until it has settled or until STUCK_AFTER sessions after its scheduled exit have closed with it still
#: unsettled (league/events/book.py `LADDER_CLOSES` closing crosses of the fallback ladder, then the session of its
#: first day sale: held equal by a test); the close is then judged without it, an older one never holds a later close,
#: and the House holds the version's new Probe and Sized buys while the lot is held (league/equity/live.py
#: `_event_unsettled`, with an alarm).
STUCK_AFTER = 6
#: meta: a stay's review state ({through: the last close whose reads and money stop were judged, looked: the last close
#: whose stay look is settled (held, or none due), k: the settled real-money events judged then, read: the last fixed
#: read held, unsettled: the events past the ladder}).
STAY_KEY = "evl6:stay:{program}:{version}:{n}"


def on_look6(store: S.Store, look: Mapping[str, Any], *, now: Any = None, db: Any = None) -> str | None:
    """PREREG-EVL-6 section 1.4's move of a look of a version it judges, in the look's own transaction: a RUN's RETIRE
    retires the version (for good), its PASS moves a `learning` version to `probe` (in any other band it moves nothing);
    a STAY's RETIRE demotes it to `learning` (section 3, DEMOTION 2) and its PASS moves `probe` to `sized` when the
    look carries section 3's real-money conditions as holding (`v6.sized`, judged by `review6`). Returns the new band."""
    key = (str(look["program"]), int(look["version"]))
    if key not in seating() or not int(look.get("held") or 0):
        return None
    v6 = look.get("v6") or {}
    decision = v6.get("decision")
    band = bands(store)[key]
    at = str(look["at"])
    tag = v6.get("tag") or ""
    if v6.get("kind") == "stay":
        if decision == "retire" and band in PROBE_PLUS:
            if set_band(store, key[0], key[1], "learning", since=at, now=now, db=db,
                        why=f"stay look {tag}S{v6.get('S')}: mean a < 0, q {float(v6.get('q') or 0):.5f} <= alpha "
                            f"{float(v6.get('alpha') or 0):.3f} (PREREG-EVL-6 section 3, demotion 2)"):
                return "learning"
        if decision == "pass" and band == "probe" and (v6.get("sized") or {}).get("ok"):
            if set_band(store, key[0], key[1], "sized", since=at, now=now, db=db,
                        why=f"stay look {tag}S{v6.get('S')} passed with {v6['sized'].get('n')} real Probe+ events, "
                            f"P&L ${float(v6['sized'].get('pnl') or 0):.2f} > 0 (PREREG-EVL-6 section 3, Sized)"):
                return "sized"
        return None
    if decision == "retire":
        if set_band(store, key[0], key[1], "retired", since=at, now=now, db=db,
                    why=f"look {tag}S{v6.get('S')}: mean a < 0, q {float(v6.get('q') or 0):.5f} <= alpha "
                        f"{float(v6.get('alpha') or 0):.3f} (PREREG-EVL-6 section 1.4, RETIRE)"):
            return "retired"
        return None
    if decision == "pass" and band == "learning":
        if set_band(store, key[0], key[1], "probe", since=at, now=now, db=db,
                    why=f"look {tag}S{v6.get('S')} passed (PREREG-EVL-6 section 1.4)"):
            return "probe"
    return None


def stay_events6(store: Any, program: str, version: int, since: Any, until: Any = None) -> list[dict[str, Any]]:
    """THE STAY'S REAL-MONEY EVENTS (PREREG-EVL-6 section 3): the version's real-money buys at Probe size or above (the
    buy's band probe or sized) bought after the stay's first decision at Probe (`since`) and before its demotion
    (`until`), ORDERED by scheduled exit close, then entry decision time, then event id; each {event, entry_day,
    exit_day, decided_at, issuer, band, settled (its sale filled), and when settled pnl and r (`real_events`': after
    fees, r on the buy's cost), cost (filled shares x fill price), target_usd, sized_usd}."""
    fills: dict[str, dict[str, Mapping[str, Any]]] = {}
    for row in store.db.execute("SELECT * FROM real_fills WHERE program=? AND version=?", (program, int(version))):
        fills.setdefault(str(row["event"]), {})[str(row["side"])] = dict(row)
    settled = {e["event"]: e for e in real_events(store, program, version)}
    out = []
    for event, sides in fills.items():
        buy = sides.get("buy")
        if buy is None or str(buy["band"]) not in PROBE_PLUS:
            continue
        try:
            bought = S.parse_iso(str(buy["filled_at"]))
        except (TypeError, ValueError):
            bought = None
        if since is not None and (bought is None or bought <= since):
            continue
        if until is not None and bought is not None and bought >= until:
            continue
        intent = store.db.execute("SELECT entry_day, exit_day, decided_at, cik, symbol FROM intents WHERE program=? AND "
                                  "version=? AND event=?", (program, int(version), event)).fetchone()
        done = settled.get(event)
        row = {"event": event, "entry_day": str(intent["entry_day"]) if intent else str(buy["filled_at"])[:10],
               "exit_day": str(intent["exit_day"]) if intent else str(buy["filled_at"])[:10],
               "decided_at": str(intent["decided_at"]) if intent else str(buy["filled_at"]),
               "issuer": (intent["cik"] or intent["symbol"]) if intent else event, "band": str(buy["band"]),
               "settled": done is not None, "cost": float(buy["qty"]) * float(buy["price"]),
               "target_usd": buy.get("target_usd"), "sized_usd": buy.get("sized_usd"),
               "bought_at": str(buy["filled_at"])}
        if done is not None:
            row |= {"pnl": float(done["pnl"]), "r": float(done["r"]), "sold_at": done["sold_at"]}
        out.append(row)
    out.sort(key=lambda e: (e["exit_day"], e["decided_at"], e["event"]))
    return out


def read_values6(events: Sequence[Mapping[str, Any]]) -> list[float]:
    """A fixed read's block values (section 3, read 3): the events in their order grouped by entry session (each
    session one block; the last may be partial), each block the mean of its events' r (`math.fsum`)."""
    groups: list[tuple[str, list[float]]] = []
    for e in events:
        day = str(e["entry_day"])
        if groups and groups[-1][0] == day:
            groups[-1][1].append(float(e["r"]))
        else:
            groups.append((day, [float(e["r"])]))
    return [math.fsum(v) / len(v) for _, v in groups]


def read_p6(events: Sequence[Mapping[str, Any]], seed_text: str, draws: int = SC.B, *,
            flips: SC.FlipSource | None = None) -> float:
    """A fixed read's p (section 3, read 3): the one-sided session-block sign-flip p for a mean BELOW zero over the
    events given (the stay's first k): exact over all sign vectors for <= 16 blocks, else `draws` vectors from the seed
    string f"{id}|v{version}|evl6|stay{n}|read{k}" (`flips`: the calibration's own, for the reproduction test)."""
    return SC.v6_count_p([-v for v in read_values6(events)], seed_text, draws, flips=flips)


def money_stop6(events: Sequence[Mapping[str, Any]]) -> bool:
    """THE MONEY STOP over the whole stay (section 3, DEMOTION 1, D10): the events given (the stay's settled real-money
    events so far, all of them from its first) lost, net, more than STOP_SHARE of their summed buy cost (`math.fsum`
    of their after-fee P&L under -STOP_SHARE x the `math.fsum` of filled shares x fill price)."""
    if not events:
        return False
    net = math.fsum(float(e["pnl"]) for e in events)
    cost = math.fsum(float(e["cost"]) for e in events)
    return net < -STOP_SHARE * cost


def sized_conditions6(store: Any, program: str, version: int, events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """SIZED's real-money conditions (section 3) over the stay's settled real-money events through the look's close:
    >= SIZED_MIN6 of them bought AT PROBE SIZE OR ABOVE (the buy's band probe or sized AND the Done reader's own size
    test, league/events/done.py `at_size`: the reading less likely to pass) whose summed after-fee P&L is above 0, and
    the signed mean gap per side between their fills and the shadow's auction prices within FILL_BP_6 (the Done
    reader's fill rule, its `_enrich` read only)."""
    from . import done as DN

    sized = [e for e in events if e.get("settled") and DN.at_size(e.get("target_usd"), e.get("sized_usd"))]
    pnl = math.fsum(float(e["pnl"]) for e in sized)
    rich = DN._enrich(store, program, version, [dict(e) for e in sized]) if sized else []
    gaps = {}
    for side in ("entry", "exit"):
        values = [float(r[f"{side}_gap_bp"]) for r in rich if r.get(f"{side}_gap_bp") is not None]
        gaps[side] = (math.fsum(values) / len(values)) if values else None
    fills_ok = all(g is not None and abs(g) <= FILL_BP_6 for g in gaps.values())
    ok = len(sized) >= SIZED_MIN6 and pnl > 0 and fills_ok
    return {"ok": ok, "n": len(sized), "pnl": pnl, "gaps_bp": gaps, "fills_ok": fills_ok}


def review6(store: S.Store, program: str, version: int, *, now: Any = None, today: Any = None,
            draws: int = SC.B) -> list[dict[str, Any]]:
    """PREREG-EVL-6 section 3 for one version at Probe or Sized: its current stay's closes in order, THE ORDER at each
    close once THAT close's real-money events (the stay's real-money buys scheduled to exit at it) have settled: first
    the fixed reads those settlements cross (the 100th, 200th, ... real-money event, in order; p <= 0.15 demotes), then
    the money stop, both over the stay's real-money events settled so far whose scheduled exit is at or before the close
    (an older one still unsettled is left out until it settles: the reading that demotes more), WHETHER OR NOT THE CLOSE
    IS FINAL; then the stay's look when one falls due at it. Only the look waits for its record: it is held once the
    close is final for the version (`screen.final_until`) with every intent of it and of its control scheduled to exit
    by then settled and every copy made, the reads and the stop at that close judged again first over every event
    settled by then (so the order holds when an older event settled late); the looks wait in their order, and a later
    close's reads and stop are judged meanwhile (a look as of a close is never held after a later close demoted: the
    stay is over, and it would move nothing). The look's lower tail demotes; its PASS with the real-money conditions
    moves Probe to Sized. A real-money event still unsettled `STUCK_AFTER` sessions after its scheduled exit (past the
    fallback ladder) no longer holds its close (it is judged without it), and the House holds the version's new Probe
    and Sized buys while the lot is held (league/equity/live.py `_event_unsettled`, with an alarm). A demotion is
    written at once and a fresh run is started when the lane's budget holds it (`screen.start_runs`). Returns the band
    changes."""
    from .programs import BY_KEY, uncopied

    now = now or S.utc_now()
    today = today or now.astimezone(C.NY).date()
    prog = BY_KEY.get((program, int(version)))
    changes: list[dict[str, Any]] = []
    if prog is None or not prog.evl6 or bands(store).get((program, int(version))) not in PROBE_PLUS:
        return changes
    stays = SC.stays6(store, program, version)
    if not stays or stays[-1]["until"] is not None:
        return changes
    stay = stays[-1]
    n, since = stay["n"], stay["since"]
    key = STAY_KEY.format(program=program, version=int(version), n=n)
    state = SC._meta_json(store, key) or {"through": None, "looked": None, "k": 0, "read": 0}
    real = stay_events6(store, program, version, since)
    record = [r for r in SC.settled_rows6(store, program, version) if SC._after(r, since)]
    control = SC.control_of(program)
    ctl_rows = SC.control_rows6(store, control, prog.registered_at) if control else None
    pending = SC._pending(store, program, version) + (SC._pending(store, control, 1) if control else [])
    on = SC.written6(store, program, version, "stay", n)
    consumed = set(on["consumed"])
    j = max(consumed) if consumed else 0
    tag = SC.v6_tag("stay", n)
    final = None
    start = since.astimezone(C.NY).date() if since is not None else today
    closes = [x for x in C.sessions(store, start, today) if x.close_at <= now]    # (the closes that have passed)
    days = [x.day for x in closes]

    def day_of(text: Any) -> dt.date | None:
        return dt.date.fromisoformat(str(text)[:10]) if text else None

    through = day_of(state.get("through"))      # (the last close whose reads and money stop were judged)
    looked = day_of(state.get("looked")) if "looked" in state else through     # (the last close whose look is settled)

    def exit_of(e: Mapping[str, Any]) -> dt.date:
        return dt.date.fromisoformat(str(e["exit_day"])[:10])

    def stuck(e: Mapping[str, Any]) -> bool:
        # (the sessions closed after its scheduled exit, through today)
        return not e["settled"] and len(days) - bisect.bisect_right(days, exit_of(e)) >= STUCK_AFTER

    def so_far(x: C.Session) -> list[dict[str, Any]]:
        return [e for e in real if e["settled"] and exit_of(e) <= x.day]

    def judge(x: C.Session) -> str | None:
        """The fixed reads, then the money stop, at close `x`: the demotion's why, or None."""
        events = so_far(x)
        read = int(state.get("read") or 0)
        for kk in range((read // READ_EVERY + 1) * READ_EVERY, len(events) + 1, READ_EVERY):
            p = read_p6(events[:kk], f"{program}|v{int(version)}|evl6|stay{n}|read{kk}", draws)
            state["read"] = kk
            if p <= READ_P + SC.TIE:
                return (f"the fixed read at the stay's {kk}th real-money Probe+ event: p {p:.4f} <= {READ_P} for a mean "
                        "below zero (PREREG-EVL-6 section 3, demotion 3)")
        state["k"] = len(events)
        if money_stop6(events):
            net = math.fsum(float(e["pnl"]) for e in events)
            cost = math.fsum(float(e["cost"]) for e in events)
            return (f"the money stop: the stay's {len(events)} real-money Probe+ events lost ${-net:.2f} net, more than "
                    f"{STOP_SHARE:.0%} of their ${cost:.2f} buy cost (PREREG-EVL-6 section 3, demotion 1)")
        return None

    def save() -> None:
        state.update(through=through.isoformat() if through else None, looked=looked.isoformat() if looked else None,
                     unsettled=sorted(str(e["event"]) for e in real if stuck(e)))
        store.set_meta(key, json.dumps(state, sort_keys=True))

    def demote(x: C.Session, why: str) -> list[dict[str, Any]]:
        nonlocal through, looked
        if set_band(store, program, int(version), "learning", since=S.iso(x.close_at), why=why, now=now):
            changes.append({"program": program, "version": int(version), "band": "learning", "why": why})
        through, looked = max(through or x.day, x.day), max(looked or x.day, x.day)
        save()
        SC.start_runs(store, now)
        return changes

    waiting = False     # (a stay look of an earlier close waits: every later look waits behind it, in the looks' order)
    for x in closes:
        if through is not None and x.day <= through and looked is not None and x.day <= looked:
            continue
        own = [e for e in real if exit_of(e) == x.day]
        ready = all(e["settled"] or stuck(e) for e in own)
        if ready and (through is None or x.day > through):
            why = judge(x)          # (THE ORDER at x: its reads, then its money stop, final or not)
            if why is not None:
                return demote(x, why)
            through = x.day
        if waiting or (looked is not None and x.day <= looked):
            continue
        cov = SC.covered(record, x.day)
        blk = SC.blocks6(cov)
        events = [e for b in blk[:SC.V6_RUN_BLOCKS] for e in b.events]
        S_ = min(len(blk), SC.V6_RUN_BLOCKS)
        look_due = (j < len(SC.V6_LOOKS) and len(blk) <= SC.V6_RUN_BLOCKS and S_ >= SC.V6_LOOKS[j]
                    and SC.v6_minimums(len(events), len({str(e["issuer"]) for e in events}), S_)
                    and (on["last"] is None or x.day > on["last"]))
        if not look_due:
            looked = x.day
            continue
        if not ready:
            waiting = True      # (the order at x waits for x's real-money events; a later close's reads and stop go on)
            continue
        if final is None:
            final = SC.final_until(store, program, version, today, now)
        if final[0] is None or x.day > final[0] or any(d <= x.day for _, d in pending) or uncopied(store, prog, x.day):
            waiting = True      # (the stay look of this close waits for its record; the reads and the stop do not)
            continue
        why = judge(x)          # (x's reads and stop again first, over every event settled by now that is due by x)
        if why is not None:
            return demote(x, why)
        due = so_far(x)
        reached = [i for i in range(j, len(SC.V6_LOOKS)) if S_ >= SC.V6_LOOKS[i]]
        first_entry = min(SC._day(r["entry_day"]) for r in record)
        ctl = SC.covered(ctl_rows, x.day) if ctl_rows is not None else None
        judged = SC.v6_judge(blk[:SC.V6_RUN_BLOCKS], program=program, version=version, tag=tag, control_rows=ctl,
                             control=control, draws=draws)
        look = SC._look6_row(program, version, "stay", n, reached[0] + 1, [i + 1 for i in reached[1:]], x.close_at,
                             len(C.sessions(store, first_entry, x.day)), judged)
        if judged.get("decision") == "pass":
            look["v6"]["sized"] = sized_conditions6(store, program, version, due)
        moved: list[str | None] = [None]

        def apply(db: Any, look: dict[str, Any] = look) -> None:
            moved[0] = on_look(store, look, now=now, db=db)
        SC.write_look(store, look, apply=apply, now=now)
        j = reached[-1] + 1
        if moved[0] is not None:
            what = ("the stay's lower tail at its look (PREREG-EVL-6 section 3, demotion 2)" if moved[0] == "learning"
                    else "Sized: the stay look passed with section 3's real-money conditions")
            changes.append({"program": program, "version": int(version), "band": moved[0],
                            "why": f"{what}: {look['why']}"[:400]})
        looked = x.day
        if moved[0] == "learning":
            through = max(through or x.day, x.day)
            save()
            SC.start_runs(store, now)
            return changes
    save()
    return changes


def record_fill(store: S.Store, *, program: str, version: int, event: str, side: str, qty: float, price: float,
                fee: float, filled_at: str, band: str, target_usd: float | None = None,
                binding: str | None = None, sized_usd: float | None = None) -> bool:
    """The House's write of one real fill (league/events/book.py `write_fills`), idempotent per (program, version,
    event, side): the first write sets the row; a later write of the same key changes ONLY its fee (the broker posts a
    sale's regulatory fees after the fill, and demotion's net reads the posted fee), never its quantity, price, time,
    band, target, binding or sent dollars. `target_usd`, `binding` and `sized_usd` (release 1019f): a buy's band target
    in dollars, the constraint that cut it (`BINDINGS`, None for none) and the dollars its send asked (the shares sent x
    the limit), None on a sale. Returns whether the row is new or its fee changed."""
    if side not in ("buy", "sell") or band not in BANDS[:3]:
        raise ValueError("side buy|sell, band learning|probe|sized")
    if binding is not None and binding not in BINDINGS:
        raise ValueError(f"binding {binding!r} is not one of {BINDINGS}")
    for name, amount in (("target_usd", target_usd), ("sized_usd", sized_usd)):
        if amount is not None and not (math.isfinite(float(amount)) and float(amount) >= 0):
            raise ValueError(f"{name} {amount!r} is not a finite amount >= 0")
    if side == "sell" and (target_usd is not None or binding is not None or sized_usd is not None):
        raise ValueError("a sale has no target, no binding and no sent dollars")
    with store.tx() as db:
        cur = db.execute("INSERT OR IGNORE INTO real_fills(program, version, event, side, qty, price, fee, filled_at, band, "
                         "target_usd, binding, sized_usd) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (program, int(version), event, side, float(qty), float(price), float(fee), filled_at, band,
                          None if target_usd is None else float(target_usd), binding,
                          None if sized_usd is None else float(sized_usd)))
        if cur.rowcount == 1:
            return True
        cur = db.execute("UPDATE real_fills SET fee=? WHERE program=? AND version=? AND event=? AND side=? AND fee IS NOT ?",
                         (float(fee), program, int(version), event, side, float(fee)))
        return cur.rowcount == 1


__all__ = ["BANDS", "BINDINGS", "bands", "set_band", "on_look", "retire_test", "real_events", "probe_since", "review", "record_fill",
           "seating", "superseded_guard", "on_look6", "stay_events6", "read_values6", "read_p6", "money_stop6",
           "sized_conditions6", "review6", "READ_EVERY", "READ_P", "STOP_SHARE", "SIZED_MIN6", "FILL_BP_6", "STAY_KEY",
           "STUCK_AFTER"]
