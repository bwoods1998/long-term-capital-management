"""THE ATTEMPTS LEDGER (release 1019i; PREREG-EVL-7's harness changes H3 and H4, goal-2026-10-19/evl7/EDGE-RESULT.json):
every real event order the House's book sent or tried, with its states as the VENUE's own order states told the book,
kept beside `real_fills` in the lane's store (`real_attempts`, league/events/store.py `SCHEMA_1019I`), and the daily
report's fill-rate lines and the two alarms read from it.

WHAT IS WRITTEN (`book_rows`, from the book's own live.sqlite through its `rows` reader; `record`, into the lane's store
through league/events/book.py `write_attempts`, called by league/equity/live.py `_event_attempts` each minute after the
real fills' hand-back): ONE ROW PER ORDER of a real event instance (`<program>@<version>:r`, lane "event"), keyed by its
client id: the buys' limit-on-open and limit-on-close orders (`kind` loo | loc), the sales' market-on-open and
market-on-close (moo | moc), the fallback ladder's day sales (day) and A80's re-sends (`resend` 1: an order of a buy
sent after the venue cancelled an earlier order of that buy at once); its program, version, event, auction (day, at),
band, ladder rung, the client id of the order it replaced; whether it was SENT (posted to the venue: every state but
`refused`, which the House or the gateway refused before anything went), ACCEPTED (the venue showed it: its id or its
`submitted_at`), its STATE (the book's reading of the venue's order: pending, working, unknown, filled, canceled,
expired, rejected, lost, refused) and whether that is FINAL, the venue's own last status word (`venue_status`), the
quantity asked and filled, the average fill price, the limit (None for a market sale), A80's cancel time (`cancel_ms`:
the milliseconds the venue took to cancel an unfilled auction buy after its own submission, within 60 s, no cancel of
the House's own sent: the rule league/equity/live.py `venue_cancel_ms` re-sends by) and the venue's stamps (sent,
submitted, filled, cancelled, expired). And ONE ROW PER PLANNED REAL BUY THAT ENDED WITH NO ORDER AT ALL
(`unsent:<iid>`, state `unsent`, final, nothing sent) with the constraint the book recorded as its binding, so the
non-fill selection of COST-7 counts every pick, sent or not. The ledger READS the orders and never sends, changes or
cancels one: league/tests/test_events_attempts.py pins the order bodies the book sends byte-identical with it on and
off. A row moves with the book's reading (a lost order the venue shows after all is working again: the take-back);
`first_seen` keeps when the ledger first had it.

THE FILL RATES (`fill_rates`, the daily report's lines, league/ops/daily_report.py): for each auction (open, close)
over the trailing 3 and 20 sessions of the lane's calendar through the report's day: the buys sent (a pick with at least
one order sent), filled (any of its orders filled at all) and their FILL RATE; the venue-cancel share (buy orders the
venue cancelled at once over buy orders sent) and the re-send share (sent buys that had A80's re-send); the picks that
ended unsent; the sales sent and filled. Counts and shares only.

THE ALARMS (league/ops/evl_health.py `evl_fill_rate` and `evl_attempts`, raised by the stall job): a FILL-RATE DROP
(`fill_drop`: an auction's 3-session fill rate under `FILL_LOW` (85%) with at least `FILL_MIN` (5) buys sent, or more
than `FILL_FALL` (10 points) under its 20-session rate with at least `FILL_MIN` buys sent in each) and AN ATTEMPT WITH
NO FINAL STATE (`open_attempts`: an order sent whose auction ended `OPEN_GRACE` (60 minutes) ago, a day sale's at its
session's close, still not final in the ledger) or an order of the book's not in the ledger an hour after its last
change (the ledger incomplete).

Standard library only.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import calendar as C
from . import store as S

TABLE = "real_attempts"
#: The columns `record` writes (every one of the table's but `first_seen`, which it keeps).
COLUMNS = ("client_id", "venue_id", "program", "version", "event", "side", "kind", "day", "at", "band", "rung", "resend",
           "replaces", "sent", "accepted", "state", "final", "venue_status", "qty", "filled_qty", "avg_px", "limit_px",
           "cancel_ms", "sent_at", "submitted_at", "filled_at", "canceled_at", "expired_at", "binding", "updated_at")
#: (side, time in force) -> the ledger's kind; any other sale is a day sale (the ladder's), any other order "other".
KINDS = {("buy", "opg"): "loo", ("buy", "cls"): "loc", ("sell", "opg"): "moo", ("sell", "cls"): "moc"}
BUY_KINDS = ("loo", "loc")
SALE_KINDS = ("moo", "moc", "day")
#: The book's order states (league/equity/live.py `WORKING`, `TERMINAL`), and the ledger's own for a pick never sent.
WORKING = ("pending", "working", "unknown")
FINAL = ("filled", "canceled", "expired", "rejected", "lost", "missed", "refused", "unsent")
UNSENT = "unsent"
#: The book's intent states still to execute (league/equity/live.py `INTENT_LIVE`).
INTENT_LIVE = ("planned", "sent")
#: A80 (league/equity/live.py `VENUE_CANCEL_RETRY_S`, `VENUE_STAMP_SLACK_S`): a venue cancel at once.
VENUE_CANCEL_S = 60.0
VENUE_STAMP_SLACK_S = 0.001
#: The book's lane and real instances (league/events/book.py `LANE`, league/equity/live.py `REAL_SUFFIX`).
LANE = "event"
REAL_SUFFIX = ":r"
#: kv in live.sqlite: the newest `updated_at` (epoch) of the book's rows the lane's store took (`EquityBook._event_attempts`),
#: and how far before it the next read starts again (rows saved in the same second are read twice, never missed).
MARK_KEY = "eq_event_attempts_mark"
MARK_SLACK_S = 120.0
#: THE FILL RATES and THE ALARMS (the module docstring).
SESSIONS = (3, 20)
FILL_LOW = 0.85
FILL_FALL = 0.10
FILL_MIN = 5
OPEN_GRACE = dt.timedelta(minutes=60)
MISSING_AFTER_S = 3600.0
AUCTIONS = ("open", "close")


def _iso_epoch(value: Any) -> str | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    return S.iso(dt.datetime.fromtimestamp(x, dt.timezone.utc))


def _float(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _loads(text: Any) -> dict[str, Any]:
    if isinstance(text, Mapping):
        return dict(text)
    try:
        got = json.loads(text) if isinstance(text, str) and text else {}
    except ValueError:
        return {}
    return got if isinstance(got, dict) else {}


def _stamp(value: Any) -> float | None:
    """An RFC 3339 stamp of the venue's (nanoseconds allowed) as epoch seconds, or None."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    head, sep, rest = text.partition(".")
    if sep:
        digits = re.match(r"\d*", rest).group(0)
        text = f"{head}.{digits[:6].ljust(6, '0')}{rest[len(digits):]}"
    try:
        moment = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return moment.timestamp()


def venue_cancel_ms(order: Mapping[str, Any]) -> int | None:
    """A80's rule on one `eq_orders` row: the milliseconds the venue took to cancel an AUCTION BUY it ended `canceled`
    within `VENUE_CANCEL_S` of its own submission, nothing filled and no cancel of the House's own sent; None otherwise."""
    answer = _loads(order.get("answer"))
    if (str(order.get("side") or "") != "buy" or str(order.get("tif") or "") not in ("opg", "cls")
            or str(order.get("status") or "") != "canceled" or answer.get("final") != "canceled"):
        return None
    if (_float(order.get("filled_qty")) or 0.0) > 0 or "cancel_sent" in answer:
        return None
    submitted, canceled = _stamp(answer.get("submitted_at")), _stamp(answer.get("canceled_at"))
    if submitted is None or canceled is None:
        return None
    took = canceled - submitted
    if not -VENUE_STAMP_SLACK_S <= took <= VENUE_CANCEL_S:
        return None
    return max(0, int(round(took * 1000)))


def _version_of(instance: str) -> int | None:
    head = str(instance or "")
    if head.endswith(REAL_SUFFIX):
        head = head[:-len(REAL_SUFFIX)]
    _, _, version = head.rpartition("@")
    try:
        return int(version)
    except ValueError:
        return None


def _tables(rows: Callable[..., list]) -> set[str]:
    return {str(r["name"]) for r in rows("SELECT name FROM sqlite_master WHERE type='table'")}


def book_rows(rows: Callable[..., list], *, since: float = 0.0) -> tuple[list[dict[str, Any]], float | None]:
    """THE LEDGER'S ROWS FROM THE BOOK'S OWN STATE (`rows`: league/live/state.py `LiveState.rows` on live.sqlite, or any
    reader of the same SQL): every order of a real event instance of an intent with any order or intent row changed at or
    after `since` (epoch), and every planned real buy changed since then that ended with no order (the module
    docstring). Returns (the rows, the newest `updated_at` read, None when none). Reads only."""
    have = _tables(rows)
    if not {"eq_orders", "eq_instances", "eq_intents"} <= have:
        return [], None
    side_rows = "eq_event_intents" in have
    orders = rows("SELECT o.* FROM eq_orders o JOIN eq_instances i ON i.id=o.instance WHERE i.lane=? AND "
                  "substr(o.instance, -2)=? AND (o.updated_at>=? OR o.iid IN (SELECT iid FROM eq_orders WHERE "
                  "updated_at>=? AND iid IS NOT NULL)) ORDER BY o.eid", (LANE, REAL_SUFFIX, since, since))
    newest = max((float(o["updated_at"]) for o in orders), default=None)
    sides: dict[int, dict[str, Any]] = {}
    if side_rows:
        iids = sorted({int(o["iid"]) for o in orders if o.get("iid") is not None})
        for i in range(0, len(iids), 500):
            chunk = iids[i:i + 500]
            for r in rows(f"SELECT * FROM eq_event_intents WHERE iid IN ({','.join('?' * len(chunk))})", chunk):
                sides[int(r["iid"])] = dict(r)
    lids = sorted({int(o["lid"]) for o in orders if o.get("lid") is not None})
    lots: dict[int, dict[str, Any]] = {}
    for i in range(0, len(lids), 500):
        chunk = lids[i:i + 500]
        for r in rows(f"SELECT lid, family, version, info FROM eq_lots WHERE lid IN ({','.join('?' * len(chunk))})", chunk):
            lots[int(r["lid"])] = {"family": r["family"], "version": r["version"], "info": _loads(r["info"])}
    client_of = {int(o["eid"]): str(o["client_id"]) for o in orders}
    cancelled_first: dict[int, int] = {}          # iid -> the eid of its first order the venue cancelled at once
    for o in orders:
        if o.get("iid") is not None and venue_cancel_ms(o) is not None:
            cancelled_first.setdefault(int(o["iid"]), int(o["eid"]))
    out: list[dict[str, Any]] = []
    for o in orders:
        side_row = sides.get(int(o["iid"])) if o.get("iid") is not None else None
        lot = lots.get(int(o["lid"])) if o.get("lid") is not None else None
        evl = (lot or {}).get("info", {}).get("evl") if lot else None
        evl = evl if isinstance(evl, Mapping) else {}
        plan = (lot or {}).get("info", {}).get("evl_exit") if lot else None
        plan = plan if isinstance(plan, Mapping) else {}
        event = (side_row or {}).get("event") or evl.get("event")
        if not event:
            continue
        side, tif = str(o.get("side") or ""), str(o.get("tif") or "day")
        kind = KINDS.get((side, tif)) or ("day" if side == "sell" else "other")
        answer = _loads(o.get("answer"))
        state = str(o.get("status") or "")
        cancel = venue_cancel_ms(o)
        first = cancelled_first.get(int(o["iid"])) if o.get("iid") is not None else None
        limit = _float(o.get("limit_px"))
        version = (side_row or {}).get("version")
        version = int(version) if version is not None else _version_of(str(o.get("instance") or ""))
        out.append({
            "client_id": str(o["client_id"]), "venue_id": o.get("venue_id") or None,
            "program": str((side_row or {}).get("program") or o.get("family")), "version": int(version or 0),
            "event": str(event), "side": side, "kind": kind, "day": str(o.get("day") or ""),
            "at": (side_row or {}).get("at") or ("open" if tif == "opg" else "close" if tif == "cls" else "day"),
            "band": (side_row or {}).get("band") or evl.get("band"),
            "rung": (side_row or {}).get("rung") if side_row is not None else plan.get("rung"),
            "resend": int(side == "buy" and first is not None and int(o["eid"]) > first),
            "replaces": client_of.get(int(o["replaces"])) if o.get("replaces") is not None else None,
            "sent": int(state != "refused"), "accepted": int(bool(o.get("venue_id") or answer.get("submitted_at"))),
            "state": state, "final": int(state in FINAL), "venue_status": answer.get("final"),
            "qty": _float(o.get("qty")) or 0.0, "filled_qty": _float(o.get("filled_qty")) or 0.0,
            "avg_px": _float(o.get("avg_px")), "limit_px": limit if limit else None, "cancel_ms": cancel,
            "sent_at": _iso_epoch(o.get("placed_at")), "submitted_at": answer.get("submitted_at"),
            "filled_at": answer.get("filled_at"), "canceled_at": answer.get("canceled_at"),
            "expired_at": answer.get("expired_at"), "binding": (side_row or {}).get("binding") if side == "buy" else None,
            "updated_at": _iso_epoch(o.get("updated_at"))})
    if side_rows:
        picks = rows("SELECT e.*, i.status AS intent_status, i.updated_at AS intent_at FROM eq_event_intents e JOIN "
                     "eq_intents i ON i.iid=e.iid WHERE e.side='buy' AND i.updated_at>=? AND NOT EXISTS (SELECT 1 FROM "
                     "eq_orders o WHERE o.iid=e.iid) ORDER BY e.iid", (since,))
        for p in picks:
            if str(p.get("intent_status") or "") in INTENT_LIVE or not str(p.get("program") or ""):
                continue
            at_ = _float(p.get("intent_at"))
            newest = at_ if newest is None or (at_ is not None and at_ > newest) else newest
            out.append({
                "client_id": f"{UNSENT}:{int(p['iid'])}", "venue_id": None, "program": str(p["program"]),
                "version": int(p["version"]), "event": str(p["event"]), "side": "buy",
                "kind": KINDS.get(("buy", str(p.get("tif") or "")), "other"), "day": str(p.get("day") or ""),
                "at": p.get("at"), "band": p.get("band"), "rung": None, "resend": 0, "replaces": None, "sent": 0,
                "accepted": 0, "state": UNSENT, "final": 1, "venue_status": None, "qty": 0.0, "filled_qty": 0.0,
                "avg_px": None, "limit_px": _float(p.get("limit_px")) or None, "cancel_ms": None, "sent_at": None,
                "submitted_at": None, "filled_at": None, "canceled_at": None, "expired_at": None,
                "binding": p.get("binding"), "updated_at": _iso_epoch(p.get("intent_at"))})
    return out, newest


def has_table(db: Any) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone() is not None


def record(store: Any, rows: Iterable[Mapping[str, Any]], *, now: dt.datetime | None = None) -> int:
    """`rows` into the lane's `real_attempts` (`store`: `.db` and `.tx()`, league/events/store.py's Store or
    league/events/book.py's FillWriter), one transaction: a new client id inserted (its `first_seen` now), a known one
    updated only where a column differs. Returns how many rows were new or changed."""
    stamp = S.iso(now or S.utc_now())
    changed = 0
    with store.tx() as db:
        for row in rows:
            values = {c: row.get(c) for c in COLUMNS}
            values["updated_at"] = values["updated_at"] or stamp
            have = db.execute(f"SELECT * FROM {TABLE} WHERE client_id=?", (values["client_id"],)).fetchone()
            if have is None:
                cols = (*COLUMNS, "first_seen")
                db.execute(f"INSERT INTO {TABLE}({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})",
                           (*(values[c] for c in COLUMNS), stamp))
                changed += 1
                continue
            moved = [c for c in COLUMNS[1:] if have[c] != values[c]]
            if moved:
                db.execute(f"UPDATE {TABLE} SET {', '.join(f'{c}=?' for c in moved)} WHERE client_id=?",
                           (*(values[c] for c in moved), values["client_id"]))
                changed += 1
    return changed


# ---------------------------------------------------------------------------------------------- the fill rates
def _sessions(store: Any, day: dt.date, n: int) -> list[str]:
    """The last `n` sessions of the lane's calendar through `day` (`day` itself when it is one)."""
    days = [s.day for s in C.previous(store, day + dt.timedelta(days=1), n)]
    return [d.isoformat() for d in days[-n:]]


def _share(part: int, whole: int) -> float | None:
    return None if whole <= 0 else round(part / whole, 4)


def auction_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """One auction's ledger rows (any sessions) as counts: the buys (one a pick: program, version, event) sent, filled
    and their rate, the buy orders sent and the venue's cancels at once among them, the buys with a re-send, the picks
    never sent, and the sales sent and filled."""
    buys: dict[tuple[str, int, str], list[Mapping[str, Any]]] = {}
    sales: dict[tuple[str, int, str], list[Mapping[str, Any]]] = {}
    for r in rows:
        key = (str(r["program"]), int(r["version"]), str(r["event"]))
        if r["side"] == "buy":
            buys.setdefault(key, []).append(r)
        elif r["side"] == "sell":
            sales.setdefault(key + (str(r["day"]),), []).append(r)
    sent = [k for k, rs in buys.items() if any(int(r["sent"] or 0) for r in rs)]
    filled = [k for k in sent if any((_float(r["filled_qty"]) or 0.0) > 0 for r in buys[k])]
    orders = [r for rs in buys.values() for r in rs if int(r["sent"] or 0)]
    cancels = [r for r in orders if r["cancel_ms"] is not None]
    resent = [k for k in sent if any(int(r["resend"] or 0) for r in buys[k])]
    unsent = [k for k, rs in buys.items() if not any(int(r["sent"] or 0) for r in rs)]
    s_sent = [k for k, rs in sales.items() if any(int(r["sent"] or 0) for r in rs)]
    s_filled = [k for k in s_sent if any((_float(r["filled_qty"]) or 0.0) > 0 for r in sales[k])]
    return {"buys_sent": len(sent), "buys_filled": len(filled), "fill_rate": _share(len(filled), len(sent)),
            "buy_orders": len(orders), "venue_cancels": len(cancels), "venue_cancel_share": _share(len(cancels), len(orders)),
            "resent": len(resent), "resend_share": _share(len(resent), len(sent)), "unsent": len(unsent),
            "sales_sent": len(s_sent), "sales_filled": len(s_filled)}


def fill_rates(store: Any, day: dt.date) -> dict[str, Any] | None:
    """THE DAILY REPORT'S FILL-RATE LINES (the module docstring): {auction: {"3": counts, "20": counts}} over the
    trailing 3 and 20 sessions through `day`, and the sessions read; None when the store holds no ledger yet."""
    if not has_table(store.db):
        return None
    out: dict[str, Any] = {"sessions": {}, "auctions": {}}
    longest = _sessions(store, day, max(SESSIONS))
    rows = [dict(r) for r in store.db.execute(
        f"SELECT * FROM {TABLE} WHERE day IN ({','.join('?' * len(longest))})", longest)] if longest else []
    for n in SESSIONS:
        days = set(longest[-n:])
        out["sessions"][str(n)] = {"first": min(days) if days else None, "last": max(days) if days else None,
                                   "n": len(days)}
        for auction in AUCTIONS:
            # (a buy's auction is its entry's; a ladder's day sale, `at` "day", belongs to neither auction)
            mine = [r for r in rows if r["day"] in days and r["at"] == auction]
            out["auctions"].setdefault(auction, {})[str(n)] = auction_counts(mine)
    out["rows"] = len(rows)
    return out


def fill_drop(rates: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """THE FILL-RATE ALARM's findings (the module docstring): [{auction, why, rate3, rate20, sent3, sent20}], empty when
    none stands."""
    found: list[dict[str, Any]] = []
    for auction, by in ((rates or {}).get("auctions") or {}).items():
        short, long_ = by.get("3") or {}, by.get("20") or {}
        r3, r20 = short.get("fill_rate"), long_.get("fill_rate")
        n3, n20 = int(short.get("buys_sent") or 0), int(long_.get("buys_sent") or 0)
        why = None
        if r3 is not None and n3 >= FILL_MIN and r3 < FILL_LOW:
            why = "low"
        elif r3 is not None and r20 is not None and n3 >= FILL_MIN and n20 >= FILL_MIN and r3 < r20 - FILL_FALL:
            why = "fall"
        if why:
            found.append({"auction": auction, "why": why, "rate3": r3, "rate20": r20, "sent3": n3, "sent20": n20})
    return found


def auction_end(store: Any, day: str, at: str) -> dt.datetime | None:
    """When an attempt's auction ended: the session's open for an open order, its close otherwise (a day sale's too)."""
    try:
        session = C.session(store, dt.date.fromisoformat(str(day)))
    except ValueError:
        return None
    if session is None:
        return None
    return session.open_at if at == "open" else session.close_at


def open_attempts(store: Any, now: dt.datetime) -> list[dict[str, Any]]:
    """THE LEDGER'S ATTEMPTS WITH NO FINAL STATE: every row sent and not final whose auction ended `OPEN_GRACE` before
    `now` (the venue ends an auction order at its cross and a day order at the close), oldest first: [{client_id, program,
    version, kind, day, at, state, ended}] (no price)."""
    if not has_table(store.db):
        return []
    out = []
    for r in store.db.execute(f"SELECT client_id, program, version, kind, day, at, state FROM {TABLE} WHERE sent=1 AND "
                              "final=0 ORDER BY day, client_id"):
        ended = auction_end(store, r["day"], str(r["at"] or ""))
        if ended is not None and now - ended >= OPEN_GRACE:
            out.append({**dict(r), "ended": S.iso(ended)})
    return out


def missing(book: Sequence[Mapping[str, Any]], ledger: Mapping[str, Mapping[str, Any]], now: float) -> list[dict[str, Any]]:
    """THE LEDGER INCOMPLETE: each of the book's rows (`book_rows`) last changed more than `MISSING_AFTER_S` before
    `now` (epoch) that the ledger lacks, or holds in another state: [{client_id, program, state, since}]."""
    out = []
    for r in book:
        since = r.get("updated_at")
        try:
            at = S.parse_iso(since).timestamp() if since else None
        except ValueError:
            at = None
        if at is None or now - at <= MISSING_AFTER_S:
            continue
        have = ledger.get(str(r["client_id"]))
        if have is None or str(have.get("state")) != str(r["state"]):
            out.append({"client_id": r["client_id"], "program": r["program"], "state": r["state"], "since": since,
                        "ledger": None if have is None else have.get("state")})
    return out


__all__ = ["TABLE", "COLUMNS", "KINDS", "FINAL", "UNSENT", "MARK_KEY", "MARK_SLACK_S", "SESSIONS", "FILL_LOW",
           "FILL_FALL", "FILL_MIN", "OPEN_GRACE", "MISSING_AFTER_S", "venue_cancel_ms", "book_rows", "has_table",
           "record", "auction_counts", "fill_rates", "fill_drop", "auction_end", "open_attempts", "missing"]
