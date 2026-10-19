"""PREREG-EVL-3's bands (section 2): the band each seating program version is in, and the rules that move it.

- LEARNING, the band at registration: real money at learning size from the first event (the House's event book sizes
  it: 2% of equity, whole shares, one share up to 5%).
- PROBE from the first decision after a passed look (`on_look`, called when the screen writes a version 2 look).
- SIZED: >= 150 settled real-money events at Probe size or above whose 80% session-block bootstrap lower bound of the
  per-event after-cost return is above zero (`review`).
- DEMOTION to learning: the last 50 settled real-money events at Probe size or above lost more than $150 net, or the
  last 100 such events have a negative mean after-cost return (`review`); back to Probe at the next passed look.
- RETIRED, for good: a held look whose mean after-cost abnormal return is below zero and whose one-sided sign-flip p
  for a mean below zero (the session-block test with every value's sign reversed) is at most 0.05 (`on_look`).

The lane writes `bands` and `band_history`; the House's event book (league/events/book.py) reads `bands(store)` and
writes `real_fills` through `record_fill` (one row a fill, idempotent per (program, version, event, side); a posted fee
updates its row). The House's lane (league/events/house.py) runs `review` after each night's screen. Nothing here reads
a price after an event other than the real fills the House reports and the screen's own looks.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

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


def on_look(store: S.Store, look: Mapping[str, Any], *, now: Any = None, db: Any = None) -> str | None:
    """With the screen's write of a version 2 look: retire, promote a learning program to probe, or nothing. Returns
    the new band or None. `db`: the look's own transaction (release 1019b's review: the move is written with the look
    or not at all, so a lost move can never leave a retired program trading)."""
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
                    "pnl": proceeds - cost, "r": (proceeds - cost) / cost, "sold_at": str(sell["filled_at"])})
    out.sort(key=lambda r: (r["sold_at"], r["event"]))
    return out


def review(store: S.Store, *, now: Any = None) -> list[dict[str, Any]]:
    """Demotion and Sized from the real fills (PREREG-EVL-3 section 2), for every probe or sized program."""
    changes = []
    when = S.iso(now or S.utc_now())
    for (program, version), band in bands(store).items():
        if band not in PROBE_PLUS:
            continue
        events = real_events(store, program, version)
        if not events:
            continue
        last = events[-DEMOTE_LAST:]
        net = math.fsum(e["pnl"] for e in last)
        last_mean = events[-DEMOTE_MEAN_LAST:]
        mean = math.fsum(e["r"] for e in last_mean) / len(last_mean)
        if net < DEMOTE_NET_USD or (len(last_mean) == DEMOTE_MEAN_LAST and mean < 0):
            why = (f"the last {len(last)} Probe+ events lost ${-net:.2f} net" if net < DEMOTE_NET_USD
                   else f"the last {DEMOTE_MEAN_LAST} Probe+ events' mean after-cost return {mean:.5f} < 0")
            if set_band(store, program, version, "learning", since=when, why=why, now=now):
                changes.append({"program": program, "version": version, "band": "learning", "why": why})
            continue
        if band == "probe" and len(events) >= SIZED_MIN:
            bound = SC.sized_bound(events)
            if bound["ok"] and set_band(store, program, version, "sized", since=when, now=now,
                                        why=f"{len(events)} Probe+ events, 80% session-block lower bound "
                                            f"{bound['session']['lower']:.5f} > 0"):
                changes.append({"program": program, "version": version, "band": "sized", "why": "sized"})
    return changes


def record_fill(store: S.Store, *, program: str, version: int, event: str, side: str, qty: float, price: float,
                fee: float, filled_at: str, band: str) -> bool:
    """The House's write of one real fill (league/events/book.py `write_fills`), idempotent per (program, version,
    event, side): the first write sets the row; a later write of the same key changes ONLY its fee (the broker posts a
    sale's regulatory fees after the fill, and demotion's net reads the posted fee), never its quantity, price, time or
    band. Returns whether the row is new or its fee changed."""
    if side not in ("buy", "sell") or band not in BANDS[:3]:
        raise ValueError("side buy|sell, band learning|probe|sized")
    with store.tx() as db:
        cur = db.execute("INSERT OR IGNORE INTO real_fills(program, version, event, side, qty, price, fee, filled_at, band) "
                         "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (program, int(version), event, side, float(qty), float(price), float(fee), filled_at, band))
        if cur.rowcount == 1:
            return True
        cur = db.execute("UPDATE real_fills SET fee=? WHERE program=? AND version=? AND event=? AND side=? AND fee IS NOT ?",
                         (float(fee), program, int(version), event, side, float(fee)))
        return cur.rowcount == 1


__all__ = ["BANDS", "bands", "set_band", "on_look", "retire_test", "real_events", "review", "record_fill", "seating"]
