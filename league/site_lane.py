"""The event lane on the public site (WP4, Oct 19, 2026): what `league/publish.py` publishes under `lane_v1`.

The owner's goal of Oct 19, 2026 (goal-2026-10-19/GOAL-MESSAGE-V2.txt): "Website and repo docs stay current with every
change: evolve the design, no redesign". The capital page keeps its five sections; its Agents ladder becomes the event
lane's steps (Shadow, Learning, Probe, Sized) and its Positions list the equity book's lots beside the options rows. This
module READS what that takes, read-only, from the House's state root, and the publisher allowlists it (`site_lane`):

- PROGRAMS (`read_programs`, the lane's store `<state>/events/events.sqlite`, its registered births loaded by
  league/events/book.py `open_lane`): one row per registered program, the SEATING version of each seatable program
  (`Program.can_seat`: version 3 of PREREG-EVL-1's and -2's nine, version 2 of PREREG-EVL-4's and PREREG-EVL-5's three
  and of each seatable birth of R3 registered before REGISTERED_AT_6, version 1 of a later birth: PREREG-EVL-6's
  versions; real money at learning size from its first event; its band is the lane's,
  league/events/bands.py) and version 1 of every program that never seats (the records and controls of PREREG-EVL-1,
  -2, -4 and -5, and R3's records and its READ births' controls: band "shadow"). Each row: a short plain name (`NAMES`, a
  fixed table, or for a birth its family's name and its place among the births: never a program's code or parameters),
  its band, its settled events with real money (both sides filled, any band) and in shadow (the lane's settled
  outcomes), and its next look's events to go (league/events/screen.py `next_look_v2`: the look's threshold of settled
  TRADABLE events less those it has; None for a shadow-only program, a retired one, or one whose looks are all used).
  RELEASE 1019i (PREREG-EVL-6 section 1.1): the seating version of every seatable id is its PREREG-EVL-6 version
  (version 3 of the nine, version 2 of PREREG-EVL-4's and -5's three and of each seatable birth registered before
  REGISTERED_AT_6), the row's real events its own and its superseded version's (the seat's real money before the
  release), its shadow its own record; its `look` is null (PREREG-EVL-6 counts looks in settled session blocks, which
  this contract's ring reads as events: lane_v1 is unchanged).
- THE FUNNEL: how many programs ever stood on each step since PREREG-EVL-1's registration: every registered program on
  Shadow (each has its shadow record), every seating version on Learning (its band at birth), and Probe, Sized and
  Retired from the lane's band history (and the bands now).
- THE CHECKPOINT the goal's Done reads (every 100): the settled real-money events whose buy was at Probe size or above
  (`bands.real_events`, PROBE_PLUS: necessarily after the program's promotion), and the next reading. 0 until a program
  is at Probe.
- THE VERDICT SPEND (`verdict_usd`): every Claude call the lane paid for, from its store: its verdicts (an answered
  verdict whose cost the gateway did not state counts `VERDICT_USD_UNKNOWN`, as the lane's own daily line does) and R3's
  births calls (`birth_calls`, the births job's one call a night through the lane's gateway, Claude Opus 5.5 from
  release 1019h (A109), Haiku 4.5 before it; one stored with no cost counts `BIRTH_USD_UNKNOWN`; release 1019e's
  review: the bill is never understated). The publisher adds it to the costs' Claude part, which the swarm's ledger
  alone does not hold.
- THE LOTS (`read_lots`, the equity book's tables in `<state>/live.sqlite`): every lot real money held since the reset,
  the event lane's (`lane` "event": `source` "program", `owner` its program's id on the page) and the older equity
  lanes' (`source` "agent", `owner` the agent's id), open and closed. A lot's P&L
  is its trades: its sale fills less its buy fills (`eq_fills`, exact Decimal), plus, while open, its shares at the
  book's own mark (its entry price while never marked: the House's current value, as an open options row is). The
  broker's fees on a sale (posted as fee rows with no order) and a lot's dividends and corporate-action cash are the
  account's own activity, which the positions table's "Fees & other" line already carries
  (`league/account_activity.py`: the equity book's FILLS are left out there, its fee and dividend rows are not), so a
  lot carries neither and nothing is counted twice: the options rows, the lots, Other and Unreconciled add up, to the
  cent, to the account's Profit less only what the marks of open positions differ from the broker's own value (the
  page's "Valuation difference" line, as before).

Never a price, a fill, a mark, a limit, a quote, an event's filing or headline, a verdict, a CIK or a program's rule: a
lot says what it held (the symbol, shares), when (to the minute) and its dollars. Standard library only; every read is
read-only (`mode=ro`); nothing here writes.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from contextlib import closing
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping

#: The lane's store under the House's state root (league/events/house.py `ROOT_NAME`, store.py `DB_NAME`).
LANE_DIR = "events"
LANE_DB = "events.sqlite"
#: The equity book's state (league/equity/live.py's tables live in the House's live.sqlite).
LIVE_DB = "live.sqlite"
#: The lane's steps, lowest first, and the bands a version 2 program can be in (league/events/bands.py `BANDS`).
STEPS = ("shadow", "learning", "probe", "sized")
BANDS = (*STEPS, "retired")
SEATING_BANDS = ("learning", "probe", "sized", "retired")
PROBE_PLUS = ("probe", "sized")
REAL_BANDS = ("learning", "probe", "sized")
#: The goal's Done is read every this many settled real-money events at Probe size or above.
CHECKPOINT_EVERY = 100
#: An answered verdict whose cost the gateway did not state (league/events/house.py `VERDICT_USD_UNKNOWN`).
VERDICT_USD_UNKNOWN = Decimal("0.01")
#: An answered births call stored with no cost (league/events/house.py `BIRTH_USD_UNKNOWN`: the night's whole cap).
BIRTH_USD_UNKNOWN = Decimal("0.25")
#: An event lot's `eq_lots.lane` (league/events/book.py `LANE`, league/equity/live.py `EVENT_LANE`).
EVENT_LANE = "event"
CENT = Decimal("0.01")
ZERO = Decimal(0)

#: A short plain name for each registered program: what its dot, its card and its lots' rows say. A fixed table (the
#: captain's words), never the program's id, code or parameters; a program registered later without a row here reads as
#: its family (`FAMILY_NAMES`).
NAMES = {
    # PREREG-EVL-1's seatable programs and records (registered 2026-10-19T01:08:38Z)
    "EVL-ERN-READ-O1": "Earnings read",
    "EVL-ERN-REACT-C1": "Earnings reaction",
    "EVL-8K-READ-O1": "8-K read",
    "EVL-NEWS-READ-O1": "Morning news read",
    "EVL-ERN-READ-O3": "Earnings read, longer hold",
    "EVL-INS-CLUSTER-O5": "Insider cluster",
    "EVL-CTRL-ERN-ALL-O1": "All earnings",
    "EVL-CTRL-8K-ALL-O1": "All 8-Ks",
    "EVL-CTRL-NEWS-ALL-O1": "All morning news",
    # PREREG-EVL-2's (registered 2026-10-19T03:04:07Z)
    "EVL-ERN-REACT-ON": "Earnings reaction overnight",
    "EVL-ERN-GUIDE-O1": "Guidance raised",
    "EVL-INS-BUY-O1": "Insider buy",
    "EVL-NEWS-READ-ON": "Day news read",
    "EVL-NEWS-REACT-ON": "News reaction overnight",
    "EVL-INS-BUY-O5": "Insider buy, longer hold",
    "EVL-ERN-REACT-READ-C1": "Earnings reaction read",
    "EVL-ERN-READ3-O1": "Top earnings read",
    "EVL-CTRL-NEWS-DAY-ON": "All day news",
    # PREREG-EVL-4's (registered 2026-10-19T16:01:05Z; each enters at D's close and exits at the next open)
    "EVL-8K-REACT-ON": "8-K reaction overnight",
    "EVL-8K-READ-ON": "8-K read overnight",
    "EVL-NEWSPM-READ-ON": "Premarket news read overnight",
    "EVL-CTRL-8K-ON": "All 8-Ks overnight",
    "EVL-CTRL-NEWSPM-ON": "All premarket news overnight",
    # PREREG-EVL-5's (registered 2026-10-21T21:26:21Z; each enters at D's close and exits at the next open)
    "EVL-ERN-DROP-ON": "Earnings fall overnight",
    "EVL-ERN-UNDER-ON": "Muted earnings read overnight",
    "EVL-NEWS-NIGHT2-ON": "News second night",
    "EVL-CTRL-ERN-UNDER-ON": "All muted earnings overnight",
    # PREREG-EVL-7's (registered 2026-10-22T20:14:13Z, A125; two online learners over the controls' candidates)
    "EVL-LRN-O1": "Learner, open to close",
    "EVL-LRN-ON": "Learner overnight",
    # PREREG-EVL-8's price lane and meta-learners (registered 2026-10-22T18:43:24Z, A122; release 1019n): a plain name
    # each, never the id; the meta-learners' sub-rules are never named anywhere (its section 10)
    "PX-DROP-ON": "Price drop overnight",
    "PX-SURGE-ON": "Price surge overnight",
    "PX-GAP-O1": "Premarket gap, open to close",
    "EVL-META-O1": "Meta-learner, open to close",
    "EVL-META-ON": "Meta-learner overnight",
    "CTRL-PX-ALL-ON": "Price lane control overnight",
    "CTRL-PX-ALL-O1": "Price lane control, open to close",
}
FAMILY_NAMES = {"ern": "Earnings", "ern-react": "Earnings reaction", "8k": "8-K", "news": "Morning news", "news-day": "Day news",
                "news-react": "News reaction", "ins": "Insider cluster", "ins-buy": "Insider buy",
                "8k-react": "8-K reaction overnight", "8k-day": "8-K overnight", "news-pm": "Premarket news",
                "ern-drop": "Earnings fall overnight", "ern-under": "Muted earnings overnight",
                "news-night2": "News second night"}
#: A registered birth's control (league/events/births.py `CONTROL_SUFFIX`): its name is its birth's and this.
BIRTH_CONTROL = "-CTRL"


def slug_of(program_id: Any) -> str:
    """A program's id on the site: lower case, the lane's "EVL-" prefix dropped ("EVL-8K-READ-O1" -> "8k-read-o1")."""
    text = str(program_id or "").strip().lower()
    return text[4:] if text.startswith("evl-") else text


def name_of(program: Any) -> str:
    """The program's plain name (`NAMES`), else its family's (`FAMILY_NAMES`), else "Event rule". A registered birth of
    R3 (league/events/births.py: a spec, never a row of `NAMES`) reads as its family's name, "birth" and its place in
    registration order among the births (its control: the same and "control"), so every name on the page is unique and
    none is its id, code or parameters."""
    pid = str(getattr(program, "id", ""))
    family = FAMILY_NAMES.get(str(getattr(program, "family", "")), "Event rule")
    if getattr(program, "spec", None) is None:
        return NAMES.get(pid, family)
    from .events import programs as P

    control = pid.endswith(BIRTH_CONTROL)
    base = pid[:-len(BIRTH_CONTROL)] if control else pid
    born = [p.id for p in P.BIRTHS if not p.id.endswith(BIRTH_CONTROL)]
    place = born.index(base) + 1 if base in born else len(born) + 1
    return f"{family} birth {place}" + (" control" if control else "")


def _epoch(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        moment = dt.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment.timestamp() if moment.tzinfo is not None else None


def _minute(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return dt.datetime.fromtimestamp(int(epoch // 60) * 60, dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _dec(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return out if out.is_finite() else None


def cents(value: Decimal) -> Decimal:
    out = value.quantize(CENT, rounding=ROUND_HALF_UP)
    return out if out else Decimal("0.00")


def usd(value: Decimal | None) -> str | None:
    return None if value is None else format(cents(value), ".2f")


def shares_text(value: Decimal) -> str:
    """A share quantity as the site takes it: plain digits, at most six decimals (the book's `QTY_PLACES`)."""
    text = format(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP).normalize(), "f")
    return text if text not in ("-0", "") else "0"


# ----------------------------------------------------------------------------------------------- the lane's store
def open_store(state_root: str | Path) -> Any:
    """The lane's store, read-only (league/events/book.py `open_lane`: `.db` and `.meta`, as league/events reads them),
    or None when this House keeps none (then nothing of league/events is even imported)."""
    if not (Path(state_root) / LANE_DIR / LANE_DB).is_file():
        return None
    from .events.book import open_lane

    return open_lane(state_root)


def _table(db: sqlite3.Connection, name: str) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def verdict_usd(lane: Any) -> Decimal:
    """Every Claude call the lane paid for, in dollars (unrounded): its verdicts' stated costs, `VERDICT_USD_UNKNOWN` for
    each answered verdict whose cost the gateway did not state, and (R3) every births call's stored cost
    (`birth_calls`: the stated one, else its worst case; `BIRTH_USD_UNKNOWN` for one stored with none) when the store
    has that table."""
    row = lane.db.execute("SELECT COALESCE(SUM(usd), 0), COALESCE(SUM(CASE WHEN usd IS NULL AND answered_at IS NOT NULL "
                          "THEN 1 ELSE 0 END), 0) FROM verdicts").fetchone()
    total = Decimal(str(row[0] or 0)) + VERDICT_USD_UNKNOWN * int(row[1] or 0)
    if _table(lane.db, "birth_calls"):
        born = lane.db.execute("SELECT COALESCE(SUM(usd), 0), COALESCE(SUM(CASE WHEN usd IS NULL AND answered_at IS NOT "
                               "NULL THEN 1 ELSE 0 END), 0) FROM birth_calls").fetchone()
        total += Decimal(str(born[0] or 0)) + BIRTH_USD_UNKNOWN * int(born[1] or 0)
    return total


def read_verdict_usd(state_root: str | Path) -> Decimal | None:
    """`verdict_usd` of the House's lane, ZERO when the House keeps no lane store; raises when one exists and cannot be
    read (the publisher then shows the Claude part as unknown, never understated)."""
    lane = open_store(state_root)
    if lane is None:
        if (Path(state_root) / LANE_DIR / LANE_DB).exists():
            raise RuntimeError("the lane's store exists and cannot be opened")
        return ZERO     # no lane on this House: no verdict was ever paid for
    try:
        return verdict_usd(lane)
    finally:
        lane.close()


def _bands(lane: Any) -> dict[tuple[str, int], str]:
    """{(program, version): band} for every seating version (league/events/bands.py `bands`; a store with no band table
    yet is every version 2 program at learning, as the lane's own reader says)."""
    from .events import bands as BA

    if not _table(lane.db, "bands"):
        return {key: "learning" for key in BA.seating()}
    return BA.bands(lane)


def _ever(lane: Any) -> dict[str, set[str]]:
    """{band: the program ids ever in it}, from the lane's band history."""
    out: dict[str, set[str]] = {}
    if _table(lane.db, "band_history"):
        for row in lane.db.execute("SELECT DISTINCT program, band FROM band_history"):
            out.setdefault(str(row[1]), set()).add(str(row[0]))
    return out


def _real_events(lane: Any, program: str, version: int, at: Iterable[str]) -> int:
    from .events import bands as BA

    if not _table(lane.db, "real_fills"):
        return 0
    return len(BA.real_events(lane, program, version, at=tuple(at)))


def read_programs(lane: Any, today: dt.date) -> dict[str, Any]:
    """{programs, funnel, checkpoint} from the lane's store (the module docstring). Raises when the store cannot be read."""
    from .events import programs as P
    from .events import screen as SC

    bands = _bands(lane)
    ever = _ever(lane)
    seating = {p.id: p for p in P.SEATING}
    rows, probe_events = [], 0
    for p in P.PROGRAMS:
        if p.can_seat:
            band = bands.get((p.id, p.version), "learning")
        elif p.version == 1 and p.id not in seating:
            band = "shadow"     # a record or a control: never real money
        else:
            continue            # version 1 of PREREG-EVL-1's and -2's seatable ids: their version 2 is on the page
        shadow = int(lane.db.execute("SELECT COUNT(*) FROM outcomes WHERE program=? AND version=? AND status='settled'",
                                     (p.id, p.version)).fetchone()[0])
        real = _real_events(lane, p.id, p.version, REAL_BANDS) if band != "shadow" else 0
        key = getattr(p, "superseded_key", None)
        if band != "shadow" and key is not None:
            # PREREG-EVL-6 section 1.1: the seat's real money before the release was its superseded version's (its
            # lots, its fills): the row of the seat counts both, never one twice (the superseded version bought only
            # before the release)
            real += _real_events(lane, key[0], key[1], REAL_BANDS)
        look = None
        if band in REAL_BANDS and not getattr(p, "evl6", False) and not P.is_8(p):
            nxt = SC.next_look_v2(lane, p.id, p.version, today)
            if nxt.get("k") is not None:
                need = int(nxt["events_needed"])
                look = {"need": need, "to_go": max(0, need - int(nxt["events"]))}
        # (PREREG-EVL-6's versions: their looks are counted in settled SESSION BLOCKS, which lane_v1's ring reads as
        # settled events ({need, to_go}, the page's "events to the next look"), so their `look` is null: lane_v1's
        # contract unchanged, never a figure in the wrong unit; a versioned key with the unit is the page's follow-up.
        # PREREG-EVL-8's five seats the same: THE PX SCREEN and THE META SCREEN judge them in settled session blocks
        # from the 22nd block, its section 5, never PREREG-EVL-3's screen, section 5.1; league/events/screen8.py)
        if p.can_seat:
            probe_events += _real_events(lane, p.id, p.version, PROBE_PLUS)
        rows.append({"id": slug_of(p.id), "name": name_of(p), "band": band, "real": real, "shadow": shadow, "look": look})
    learners = {slug_of(p.id) for p in P.PROGRAMS if P.is_learner(p)}
    for row in rows:        # (PREREG-EVL-7's learners: judged in settled session blocks, league/events/judge7.py, which
        if row["id"] in learners:       # lane_v1's ring cannot read; PREREG-EVL-3's next look is never theirs)
            row["look"] = None
    now_in = lambda wanted: {p.id for p in P.SEATING if bands.get((p.id, p.version)) in wanted}  # noqa: E731
    reached = lambda wanted: len(now_in(wanted) | set().union(*(ever.get(b, set()) for b in wanted)))  # noqa: E731
    funnel = {"since": P.REGISTERED_AT, "shadow": len(P.BY_ID), "learning": len(P.SEATING),
              "probe": reached(PROBE_PLUS), "sized": reached(("sized",)), "retired": reached(("retired",))}
    checkpoint = {"events": probe_events, "next": (probe_events // CHECKPOINT_EVERY + 1) * CHECKPOINT_EVERY}
    return {"programs": rows, "funnel": funnel, "checkpoint": checkpoint}


# ----------------------------------------------------------------------------------------------- the lots
def lot_rows(lots: Iterable[Mapping[str, Any]], fills: Iterable[Mapping[str, Any]], *, since: float | None) -> list[dict[str, Any]]:
    """The equity book's lots opened at or after `since` as the site's rows (unsorted; `read_lots` orders and folds), each
    with its unrounded `value` (Decimal) beside its `pnl_usd`: its sale fills less its buy fills, plus, while open, its
    shares at its mark (its entry price while never marked). A lot no field of the site can describe keeps
    `describable` False (it folds into the not-listed line, so the sum still holds)."""
    traded: dict[int, Decimal] = {}
    for f in fills:
        lid, qty, px = f.get("lid"), _dec(f.get("qty")), _dec(f.get("px"))
        if lid is None or qty is None or px is None:
            raise ValueError("a fill without a lot, a quantity or a price")
        sign = Decimal(1) if f.get("side") == "sell" else Decimal(-1) if f.get("side") == "buy" else None
        if sign is None:
            raise ValueError("a fill without a side")
        traded[int(lid)] = traded.get(int(lid), ZERO) + sign * qty * px
    out = []
    for lot in lots:
        opened = _epoch(lot.get("opened_at"))
        if opened is None:
            raise ValueError(f"lot {lot.get('lid')} without an opening time")
        if since is not None and opened < since:
            continue
        lid = int(lot["lid"])
        status = "closed" if lot.get("status") == "closed" else "open"
        held = _dec(lot.get("qty")) or ZERO
        bought = _dec(lot.get("opened_qty")) or ZERO
        value = traded.get(lid, ZERO)
        if status == "open":
            mark, entry = _dec(lot.get("mark")), _dec(lot.get("entry_px")) or ZERO
            value += max(ZERO, held) * (mark if mark is not None and mark > 0 else entry)
        info = lot.get("info") if isinstance(lot.get("info"), Mapping) else {}
        event = str(lot.get("lane") or "") == EVENT_LANE
        family = str(lot.get("family") or "")
        if event:
            evl = info.get("evl") if isinstance(info.get("evl"), Mapping) else {}
            route = evl.get("band") if evl.get("band") in REAL_BANDS else "learning"
        else:
            route = "probe" if int(lot.get("probe") or 0) else "sized"
        closed = _epoch(lot.get("closed_at")) if status == "closed" else None
        # To the minute, as the options rows; a closed lot never closes before it opened (no time: when it opened).
        closed_min = _minute(max(closed if closed is not None else opened, opened)) if status == "closed" else None
        describable = bought > 0 and (status == "closed" or held > 0)
        out.append({"id": f"lot:{lid}", "source": "program" if event else "agent", "owner": slug_of(family) if event else family,
                    "symbol": str(lot.get("symbol") or "").upper(), "route": route, "shares": shares_text(bought),
                    "open_shares": shares_text(max(ZERO, held)) if status == "open" else "0", "status": status,
                    "opened_at": _minute(opened), "closed_at": closed_min, "pnl_usd": usd(value), "value": value,
                    "describable": describable})
    return out


def read_lots(state_root: str | Path, *, at: str, start_at: Any = None) -> dict[str, Any] | None:
    """{as_of, rows, earlier, pnl_usd}: the equity book's lots since `start_at` (`lot_rows`), read in one read-only
    transaction of live.sqlite; empty when the House keeps no equity book. Rows unsorted and unfolded: the publisher's
    `site_lane` orders them, folds what the table cannot list into `earlier`, and adds them up."""
    path = Path(state_root) / LIVE_DB
    if not path.is_file():
        return {"as_of": at, "rows": [], "earlier": None, "pnl_usd": "0.00"}
    import json

    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        if not (_table(db, "eq_lots") and _table(db, "eq_fills") and _table(db, "eq_orders")):
            db.rollback()
            return {"as_of": at, "rows": [], "earlier": None, "pnl_usd": "0.00"}
        lots = []
        for r in db.execute("SELECT lid, instance, family, version, lane, symbol, qty, opened_qty, entry_px, mark, opened_at, "
                            "status, closed_at, probe, info FROM eq_lots"):
            row = dict(r)
            try:
                row["info"] = json.loads(row.get("info") or "{}") or {}
            except (TypeError, ValueError):
                row["info"] = {}
            lots.append(row)
        fills = [dict(r) for r in db.execute("SELECT f.lid AS lid, o.side AS side, f.qty AS qty, f.px AS px FROM eq_fills f "
                                             "JOIN eq_orders o ON o.eid = f.eid")]
        db.rollback()
    rows = lot_rows(lots, fills, since=_epoch(start_at))
    total = sum((cents(r["value"]) for r in rows), ZERO)
    return {"as_of": at, "rows": rows, "earlier": None, "pnl_usd": usd(total)}


# ----------------------------------------------------------------------------------------------- the view
def lane_view(state_root: str | Path, *, at: str, start_at: Any = None) -> dict[str, Any] | None:
    """{as_of, programs, funnel, checkpoint, verdict_usd, lots}: the lane's public view (the module docstring), None
    when this House keeps no lane store (a House before the lane: the page keeps its older ladder). Raises when a store
    exists and cannot be read; `lots` is None when the equity book alone cannot be read."""
    lane = open_store(state_root)
    if lane is None:
        return None
    try:
        today = dt.datetime.fromisoformat(at.replace("Z", "+00:00")).astimezone(_new_york()).date()
        view = read_programs(lane, today)
        spend = verdict_usd(lane)
    finally:
        lane.close()
    try:
        lots = read_lots(state_root, at=at, start_at=start_at)
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, InvalidOperation):
        lots = None
    return {"as_of": at, **view, "verdict_usd": usd(spend), "lots": lots}


def _new_york() -> dt.tzinfo:
    from zoneinfo import ZoneInfo

    return ZoneInfo("America/New_York")


__all__ = ["BANDS", "CHECKPOINT_EVERY", "FAMILY_NAMES", "NAMES", "STEPS", "lane_view", "lot_rows", "name_of", "read_lots",
           "read_programs", "read_verdict_usd", "slug_of", "verdict_usd"]
