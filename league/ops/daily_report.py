"""THE DAILY ONE-SCREEN REPORT BY MAIL (release 1019c; the owner's goal of Oct 19, 2026, item 5: "a daily one-screen
report (events, intents, fills, settled n, P&L by program and band, costs, evidence)", and its last line: "Report
account-shown profit first, Net after costs beside it"; PREREG-EVL-1 section 9 and PREREG-EVL-3 section 5: "Every report:
account-shown profit first, Net after metered costs beside, by program and band; the market-direction share; same-risk
buy-and-hold; the expected false passes").

ONCE A NEW YORK DAY, AFTER THE LANE'S REPORT JOB: the stall job (league/ops/stall.py, :20 and :50) sends the day's report
at its first run after the lane's own nightly `report` receipt for that day (league/events/house.py: after the score and
the screen), or from `REPORT_BY` (23:45 ET) when that job has not run, saying so; until noon the next day (a House down all
night still tells it), never twice (`stall.json` `report`: the day told, and the gateway's own key `report:<day>`). It
goes by the gateway's existing route (`POST /v1/notify`, kind `report`); the gateway composes the words
(gateway/lib/email.mjs `composeNotice` 'report': one screen on a phone, no line over 60 characters) from FIGURES ONLY:
counts, dollars, basis points and shares, days, the programs' own `EVL-...` ids, the bands' names and the stall causes'
ids. No headline, no document text, no symbol, no price ever leaves the House; the facts reach the owner's mail only,
never the receipt, stall.json or the repo.

THE FACTS (`facts`), each read-only (the lane's store through a read-only store, league/events/report.py's own readers;
`<state>/metered.json`, league/ops/metered.py; budget.json):
- `profit`: ACCOUNT-SHOWN FIRST, NET AFTER COSTS BESIDE IT. Account-shown is the event lane's realized real-money P&L as
  the account booked it: each settled real event's sale proceeds less its buy cost, at the broker's fill prices and its
  posted fees (league/events/bands.py `real_events`, from the `real_fills` the House's book writes back). Net is that
  less the MEASURED metered compute (metered.py: every meter, not the budget's lines): the day's (the New York day's
  sales against the spend of the UTC day of the same date, the cost rule's day, which ends at 20:00 ET or 19:00 ET and
  so is whole by the report's time) and to date (from the lane's first real fill; "n/a until real fills"). COSTS TO
  DATE are measured over the days metered.json covers (metered.py `since`; the review of r2/alarms, its major 2): from
  the later of the first fill's day and the first day the ledger read both meters, so a ledger begun after the first
  fill (a release that started it later, a lost metered.json) never leaves Net unknown for good; `costs_from`, `partial`
  and `missing` say what the figure covers, and the mail prints them ("costs since <day>, partly measured").
- `costs`: the UTC day's MEASURED metered spend (Sail's meter, the gateway's Claude meter with the UTC day's verdict
  dollars named inside it, OpenAI's, Cloudflare and data; the UTC day of the report's date, the day budget rule 3 holds
  every line on and `cap_breach` judges), the span its readings cover (HH:MM UTC), against the cap the rule set for that
  day, "over" when above it; the ALLOWANCE (the cap and its lines: fixed, the lane's verdicts, research) as budget.json
  set it, labelled as such (its floor when budget.json is not usable); yesterday's whole day beside it.
- `events` by family, `verdicts` by status and their dollars, the day's shadow `intents` by program and version, the
  day's real `fills` (buys, sells, fees) and THE FILL GAP: the signed mean per side over the last 20 priced fills
  against the shadow's own auction prints (positive when real money did worse; league/ops/evl_health.py `fill_gaps`,
  the goal's Done item "fills within 15 bp of replay").
- `programs`: each program that may trade real money (`programs.SEATING`: version 2 of the nine, PREREG-EVL-3, then
  version 1 of PREREG-EVL-4's three from release 1019d and of PREREG-EVL-5's three from release 1019g, then R3's
  seatable births in registration order, loaded from the lane's store for the report: `facts`), in the tables' order:
  its band, settled n (shadow TRADABLE, and real), account-shown and Net by band (metered compute shared over the
  settled real events, so the programs' Nets add up to the lane's), its next look and the TRADABLE events to go, the
  market-direction share and the benchmark's mean (shadow, PREREG-EVL-1 section 7's "beside every look"), and its
  same-risk buy-and-hold: the event's benchmark bought and held continuously from its first real buy to its last real
  sale at its average invested dollars (PREREG-EVL-1 section 9), "n/a until real fills".
- the records and controls in one line, the `expected_false_passes`, and the `alarms` standing at this run.
- `entries` (release 1019f; the captain's A80 (2): "the daily report counts venue cancels as a fill gap"): the day's
  real event buys from the book's own rows in live.sqlite (league/ops/evl_health.py `entry_facts`, the numbers
  `evl_entries` judges): planned and filled, the venue's cancels at once (A80) and the re-sends after one with how many
  filled, the never-sent by reason (the day order count, cash, the loss budget, the name wall, the program's room, ...),
  sent and not filled, the decisions' room cut; and per auction its planned, filled and the constraint that BOUND it
  most (cash, budget, room, order line, name wall, invested, or none).
- `break_even` (release 1019f): THE BREAK-EVEN EDGE OF DONE'S COMPUTE CLAUSE ("realized profit since the first promotion
  >= metered compute over the same span"), once a Probe buy exists: the measured metered compute per session since the
  first real Probe or Sized buy (metered.py `since`, as far as metered.json covers it) over the dollars bought at Probe
  or Sized size per session, in basis points of those dollars: what each Probe dollar must earn after costs, on
  average, for the clause to hold. "n/a until a Probe buy" before.
- `done`: THE DONE READER'S LINE (the goal V2, docs/goals/DONE-RULE-EVL-2.md): from `<state>/events/done.json`, which the
  House's nightly screen writes after the band review (league/events/done.py `run`), so it is the night's own reading:
  the settled real-money events at Probe size or above counted toward 300 by program, the next checkpoint (100, 200,
  ...), the 95% issuer-block lower bound of the per-event after-cost return (bp) and the benchmark-net one beside it,
  the learning events beside (never counted), and whether Done holds at a checkpoint, the pivot or the $800 stop is
  read. Every figure None while no done.json is read (a release before the reader, or its first night not yet run).
- `supply` (release 1019h, SUP-4, the captain's A97; REPORT ONLY: no money, judge or digest moves): THE DONE SUPPLY
  LINE, one row per program at Probe or Sized now: its counted Probe+ events so far (done.json's `programs`, the same
  count as `done`), its MEASURED real picks a session over the last `SUPPLY_SESSIONS` (5) sessions (the picks ROOM GAVE
  it at the book's decisions of its entry auction, live.sqlite `eq_event_decisions` `planned`, over the decisions made),
  the Probe+ buys under Done's size bar beside (the lane's `real_fills`, the judge's own `at_size`; by the cap recorded
  as their binding), and the session at which it is PROJECTED to reach Done's 50 a program at its family's STATED
  season multiplier (`SEASON_STATED`: earnings x0.2 and news x0.6 after Nov 20, 2026 to mid-January, the design's stated
  calendar shape, NOT MEASURED: `stated` says so beside every projection; the projection counts every pick given, an
  upper bound); the next checkpoint at which Done can be read (the larger of done.json's next checkpoint and 300) and
  the session the Probe+ rows' projected total reaches it; and a FLAG when fewer than 3 rows (Done's `DONE_PROGRAMS`)
  are projected to reach 50 by then (or within `SUPPLY_HORIZON` sessions when the total never reaches it).
Standard library only.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from . import budget as B
from . import guard
from . import metered as MT

NY = ZoneInfo("America/New_York")
KIND = "report"
#: The report of a day is due at the stall job's first run after the lane's `report` receipt for it, or from this New
#: York time of that day when the lane's own report job has not run; it is no longer sent from noon the next day.
REPORT_BY = dt.time(23, 45)
STALE_AFTER = dt.timedelta(hours=12)
#: The lane's store under the House's state root (league/events/store.py).
LANE = Path("events")


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _round(value: Any, places: int = 2) -> float | None:
    number = _num(value)
    return None if number is None else round(number, places)


def _get(ctx: Any, name: str, default: Any = None) -> Any:
    if isinstance(ctx, Mapping):
        return ctx.get(name, default)
    return getattr(ctx, name, default)


class ReadOnlyStore:
    """league/events/store.py's `Store` as the lane's readers read it (`db`, `meta`, `root`), over a read-only
    connection: the stall job opens nothing for writing."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.db = guard.connect_ro(self.root / "events.sqlite")

    def meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return None if row is None else str(row[0])

    def get_document(self, digest: str) -> bytes:
        """A stored document's bytes, read as the store reads them (league/events/store.py `Store.get_document`: its
        gzip file under `docs/`, checked against its digest), for the screen's readers (`evl_final`: the tickers copy
        A69 (ii) reads)."""
        from ..events.store import Store

        return Store.get_document(self, digest)  # type: ignore[arg-type]

    def close(self) -> None:
        self.db.close()


# ---------------------------------------------------------------------------------------------- when
def _lane_reported(root: Path, day: str) -> bool:
    """The lane's own report job ran for `day` (its `report` receipt, house.py `_report`)."""
    path = root / LANE / "events.sqlite"
    if not path.exists():
        return False

    def read(db: Any) -> bool:
        for (summary,) in db.execute("SELECT summary FROM receipts WHERE job='report' AND status='ok' AND started_at>=? "
                                     "ORDER BY id DESC LIMIT 20", (day,)).fetchall():
            try:
                said = json.loads(summary) if isinstance(summary, str) else None
            except ValueError:
                said = None
            if isinstance(said, Mapping) and said.get("day") == day:
                return True
        return False
    return bool(guard.read(path, read))


def due(ctx: Any, root: str | Path, now: float, *, told: Any = None) -> dict[str, Any] | None:
    """The day whose report is due at `now`, {day, lane_report}, or None: yesterday's (until noon today) or today's, the
    older first, once the lane's own report job ran for it or from `REPORT_BY`, and never a day already told (`told`:
    stall.json `report`). Only while the event lane runs on the House."""
    from . import evl_health as EV

    if EV.switched_off(ctx) or not EV.lane_on(ctx):
        return None
    root = Path(root)
    today = dt.datetime.fromtimestamp(now, NY).date()
    told_day = told.get("day") if isinstance(told, Mapping) else None
    for day in (today - dt.timedelta(days=1), today):
        key = day.isoformat()
        if told_day is not None and key <= str(told_day):
            continue
        deadline = dt.datetime.combine(day, REPORT_BY, tzinfo=NY).timestamp()
        stale = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0, 0), tzinfo=NY) + STALE_AFTER
        if now > stale.timestamp():
            continue
        try:
            ran = _lane_reported(root, key)
        except Exception:  # noqa: BLE001 - an unreadable store: the deadline decides
            ran = False
        if ran or now >= deadline:
            return {"day": key, "lane_report": ran}
    return None


# ---------------------------------------------------------------------------------------------- the Done line
def done_line(root: str | Path) -> dict[str, Any]:
    """The `done` fact (the module docstring) from `<root>/events/done.json`, figures only; the same keys always."""
    from ..events import done as DN
    from ..events import programs as P

    doc = DN.load(Path(root) / LANE / DN.FILE) or {}
    current = doc.get("current") if isinstance(doc.get("current"), Mapping) else {}
    fig = current.get("figures") if isinstance(current.get("figures"), Mapping) else {}
    bound = fig.get("bound") if isinstance(fig.get("bound"), Mapping) else {}
    a = fig.get("a") if isinstance(fig.get("a"), Mapping) else {}
    a_bound = a.get("bound") if isinstance(a.get("bound"), Mapping) else {}
    rows = {(str(r.get("id")), int(r.get("version") or 0)): r for r in (doc.get("programs") or [])
            if isinstance(r, Mapping)} if isinstance(doc.get("programs"), list) else {}

    def flag(name: str, key: str) -> bool | None:
        block = doc.get(name)
        return bool(block.get(key)) if isinstance(block, Mapping) and block.get(key) is not None else None

    def bp(value: Any) -> float | None:
        number = _num(value)
        return None if number is None else round(number * 1e4, 1)
    counted = doc.get("counted")
    learning = doc.get("learning") if isinstance(doc.get("learning"), Mapping) else {}
    return {"counted": counted if isinstance(counted, int) else None, "toward": DN.DONE_EVENTS,
            "next_checkpoint": doc.get("next_checkpoint") if isinstance(doc.get("next_checkpoint"), int) else None,
            "lower_bp": bp(bound.get("lower")), "lower_a_bp": bp(a_bound.get("lower")),
            "learning": learning.get("n") if isinstance(learning.get("n"), int) else None,
            "holds": flag("done", "holds"), "pivot": flag("pivot", "retire"), "stop": flag("stop", "spent"),
            "by_program": [{"id": p.id, "version": p.version,
                            "n": (rows.get((p.id, p.version)) or {}).get("n") if doc else None} for p in P.SEATING]}


# ---------------------------------------------------------------------------------------------- the money
def _real(store: Any) -> list[dict[str, Any]]:
    """Every settled real-money event of the programs that may trade (league/events/bands.py `real_events`, every band):
    {program, version, event, band, pnl, cost, sold_at, bought_at, entry_day, exit_day, bench}."""
    from ..events import bands as BA
    from ..events import programs as P

    out: list[dict[str, Any]] = []
    if store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='real_fills'").fetchone() is None:
        return out  # a store from before release 1019b: no real fill yet
    for prog in P.SEATING:
        for row in BA.real_events(store, prog.id, prog.version, at=("learning", "probe", "sized")):
            buy = store.db.execute("SELECT qty, price, fee, filled_at FROM real_fills WHERE program=? AND version=? AND "
                                   "event=? AND side='buy'", (prog.id, prog.version, row["event"])).fetchone()
            intent = store.db.execute("SELECT entry_day, exit_day, symbol FROM intents WHERE program=? AND version=? AND "
                                      "event=?", (prog.id, prog.version, row["event"])).fetchone()
            bench = None
            if intent is not None:
                uni = store.db.execute("SELECT bench FROM universe WHERE day=? AND symbol=?",
                                       (intent["entry_day"], intent["symbol"])).fetchone()
                bench = None if uni is None else uni["bench"]
            cost = None if buy is None else float(buy["qty"]) * float(buy["price"]) + float(buy["fee"] or 0)
            out.append({"program": prog.id, "version": prog.version, "event": row["event"], "band": row["band"],
                        "pnl": float(row["pnl"]), "cost": cost, "sold_at": row["sold_at"],
                        "bought_at": None if buy is None else str(buy["filled_at"]),
                        "entry_day": None if intent is None else str(intent["entry_day"]),
                        "exit_day": None if intent is None else str(intent["exit_day"]), "bench": bench})
    return out


def _ny_day_of(text: Any) -> str | None:
    try:
        at = dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    at = at if at.tzinfo is not None else at.replace(tzinfo=dt.timezone.utc)
    return at.astimezone(NY).date().isoformat()


def _close(store: Any, symbol: str, day: str, field: str) -> float | None:
    """The benchmark's split- and dividend-adjusted daily bar figure (`bars` adj 'all', its open or close) of `day`."""
    row = store.db.execute(f"SELECT {field} FROM bars WHERE symbol=? AND day=? AND adj='all'", (symbol, day)).fetchone()
    value = None if row is None else _num(row[0])
    return value if value is not None and value > 0 else None


def buy_and_hold(store: Any, events: list[Mapping[str, Any]]) -> dict[str, Any]:
    """SAME-RISK BUY-AND-HOLD (PREREG-EVL-1 section 9) of one program's settled real events: each event's benchmark bought
    at the open of the program's first real entry day and held continuously to the close of its last real exit day, at the
    program's average invested dollars (the buys' cost over the sessions of that span: every seatable program holds one
    session), {usd, from, to, why}; usd None ("n/a until real fills", or the benchmark's bars not in the store)."""
    rows = [e for e in events if e.get("cost") and e.get("entry_day") and e.get("exit_day") and e.get("bench")]
    if not rows:
        return {"usd": None, "why": "n/a until real fills"}
    first, last = min(e["entry_day"] for e in rows), max(e["exit_day"] for e in rows)
    sessions = store.db.execute("SELECT COUNT(*) FROM sessions WHERE day>=? AND day<=?", (first, last)).fetchone()[0]
    if not sessions:
        return {"usd": None, "why": "n/a: the span's sessions are not in the store"}
    usd = 0.0
    for bench in sorted({str(e["bench"]) for e in rows}):
        start, end = _close(store, bench, first, "o"), _close(store, bench, last, "c")
        if start is None or end is None:
            return {"usd": None, "why": f"n/a: {bench}'s bars for the span are not in the store"}
        invested = sum(float(e["cost"]) for e in rows if str(e["bench"]) == bench) / int(sessions)
        usd += invested * (end / start - 1.0)
    return {"usd": round(usd, 2), "from": first, "to": last, "why": None}


# ---------------------------------------------------------------------------------------------- the facts
def _allowance(budget: Mapping[str, Any] | None) -> dict[str, Any]:
    """The day's cap and its lines as budget.json set them (the ALLOWANCE), or the floor's when it is not usable."""
    if isinstance(budget, Mapping) and budget.get("schema") == B.SCHEMA and isinstance(budget.get("cap"), Mapping):
        cap, meters = budget["cap"], budget.get("meters") if isinstance(budget.get("meters"), Mapping) else {}
        claude = meters.get("claude") if isinstance(meters.get("claude"), Mapping) else {}
        return {"cap_usd": _round(cap.get("cap_usd_day")), "fixed_usd": _round(cap.get("fixed_usd_day")),
                "lane_usd": _round(claude.get("lane_usd_day")), "research_usd": _round(budget.get("research_usd_day")),
                "source": "budget"}
    lines = B.floor_lines()
    return {"cap_usd": _round(lines["cap_usd_day"]), "fixed_usd": _round(lines["fixed_usd_day"]),
            "lane_usd": _round(lines["lane_usd_day"]), "research_usd": _round(lines["rest_usd_day"]), "source": "floor"}


def _utc_hhmm(text: Any, day: dt.date) -> str | None:
    """HH:MM UTC of an ISO time on the UTC day `day` (24:00 for its end), or None."""
    try:
        at = dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    at = (at if at.tzinfo is not None else at.replace(tzinfo=dt.timezone.utc)).astimezone(dt.timezone.utc)
    return "24:00" if at.date() > day else at.strftime("%H:%M")


def _utc_day_of(text: Any) -> dt.date | None:
    try:
        at = dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return (at if at.tzinfo is not None else at.replace(tzinfo=dt.timezone.utc)).astimezone(dt.timezone.utc).date()


def _costs(ledger: Mapping[str, Any], day: dt.date, now: float, verdicts_usd: float | None,
           budget: Mapping[str, Any] | None) -> dict[str, Any]:
    """The UTC day `day`'s measured costs (metered.py `day_figure`: the cost rule's day, `cap_breach`'s), the span its
    readings cover in HH:MM UTC, against the cap the rule set for it; `verdicts_usd` the lane's verdict dollars of that
    UTC day (inside Claude's figure); the allowance; yesterday's."""
    figure = MT.day_figure(ledger, day, now)
    kept = (ledger.get("days") or {}).get((day - dt.timedelta(days=1)).isoformat())
    yesterday = kept if isinstance(kept, Mapping) else MT.day_figure(ledger, day - dt.timedelta(days=1), now)
    return {"spent_usd": _round(figure["spent"]), "at_least_usd": _round(figure["at_least"]),
            "sail_usd": _round(figure["sail"]), "claude_usd": _round(figure["claude"]),
            "verdicts_usd": _round(verdicts_usd), "openai_usd": _round(figure["openai"]),
            "cloudflare_usd": _round(figure["cloudflare"]), "data_usd": _round(figure["data"]),
            "from": _utc_hhmm(figure["from"], day), "to": _utc_hhmm(figure["to"], day), "whole": bool(figure["whole"]),
            "cap_usd": _round(figure["cap"]), "over": bool(figure["over"]), "allowance": _allowance(budget),
            "yesterday": {"day": str(yesterday.get("day")), "spent_usd": _round(yesterday.get("spent")),
                          "at_least_usd": _round(yesterday.get("at_least")), "cap_usd": _round(yesterday.get("cap")),
                          "whole": bool(yesterday.get("whole")), "over": bool(yesterday.get("over"))}}


def facts(ctx: Any, root: str | Path, now: float, day: str, *, ledger: Mapping[str, Any] | None = None,
          budget: Mapping[str, Any] | None = None, alarms: list[str] | None = None,
          lane_report: bool = True) -> dict[str, Any]:
    """The `report` notice's facts for New York day `day` (the module docstring): figures only. Raises when the lane's
    store cannot be read (the stall job says so and tries again at its next run).
    WITH R3'S BIRTHS (release 1019f's review, lens alarms): a seatable birth trades real money at learning size from its
    first event (A81), so its settled real round trips are in the account-shown profit (the day's and to date), it has
    its row in `programs` with its buy-and-hold, its 0.10 in `expected_false_passes` and its line in the Done reader's
    `done`. Every one of those reads `programs.SEATING`, and the stall job runs in its own process, where no lane has
    loaded the registered births: so they are loaded here from the same read-only store (league/events/programs.py
    `load_births`, as league/ops/evl_health.py `final_lags` does) for the whole of the report, and the table is left as
    this process had it (unloaded again when it held none)."""
    from ..events import programs as P

    had = tuple(P.BIRTHS)
    try:
        return _facts(ctx, root, now, day, ledger=ledger, budget=budget, alarms=alarms, lane_report=lane_report,
                      births=not had)
    finally:
        if not had:
            P.load_births(None)


def _facts(ctx: Any, root: str | Path, now: float, day: str, *, ledger: Mapping[str, Any] | None,
           budget: Mapping[str, Any] | None, alarms: list[str] | None, lane_report: bool,
           births: bool) -> dict[str, Any]:
    """`facts`, with the registered births loaded from the lane's store first when `births`."""
    from ..events import programs as P
    from ..events import report as RP
    from ..events import screen as SC

    root = Path(root)
    on = dt.date.fromisoformat(day)
    ledger = ledger if isinstance(ledger, Mapping) else MT.load(root)
    with guard.readonly():
        store = ReadOnlyStore(root / LANE)
        try:
            if births:
                P.load_births(store)
            ev, vd = RP.events(store, on), RP.verdicts(store, on)
            seating = {(p.id, p.version) for p in P.SEATING}
            statuses = {}
            for program, version in sorted(set(SC.program_versions(store)) | seating):
                statuses[(program, version)] = RP.program_status(store, program, version, on)
            real = _real(store)
            lo, hi = RP.day_bounds(on)
            # The UTC day of the same date (the cost rule's day): the lane's verdict dollars inside its Claude figure,
            # each at its settled cost (one with none stated at the lane's own figure, as its line counts it).
            ulo, uhi = (MT._iso(t) for t in MT.day_bounds(on))
            cost_verdicts = float(store.db.execute(
                f"SELECT COALESCE(SUM(COALESCE(usd, {B.VERDICT_USD_UNKNOWN})), 0) FROM verdicts WHERE answered_at>=? "
                "AND answered_at<?", (ulo, uhi)).fetchone()[0] or 0.0)
            fills, first_fill = [], None
            if store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='real_fills'").fetchone():
                fills = store.db.execute("SELECT side, COUNT(*) AS n, COALESCE(SUM(fee), 0) AS fees FROM real_fills "
                                         "WHERE filled_at>=? AND filled_at<? GROUP BY side", (lo, hi)).fetchall()
                first_fill = store.db.execute("SELECT MIN(filled_at) FROM real_fills").fetchone()[0]
            efp = SC.expected_false_passes(store)
            holds = {key: buy_and_hold(store, [e for e in real if (e["program"], e["version"]) == key]) for key in seating}
            probe = probe_buys(store, hi)
            under = under_size(store)
        finally:
            store.close()
    from . import evl_health as EV

    try:   # THE FILL GAP (the goal's "fill gaps"): the last 20 priced event twins, per side
        gap = EV.fill_gaps(EV.event_twins(root))
    except Exception:  # noqa: BLE001 - no twins read: no gap said
        gap = EV.fill_gaps([])
    entries = day_entries(root, day)
    verdicts_usd = sum(_num(v.get("usd")) or 0.0 for v in vd.values() if isinstance(v, Mapping))
    costs = _costs(ledger, on, now, cost_verdicts, budget)
    # ACCOUNT-SHOWN FIRST, NET AFTER COSTS BESIDE IT: the day's realized real P&L against the day's measured spend, and to
    # date from the lane's first real fill against the measured spend since (as far as metered.json covers it).
    day_spend = _num(costs["spent_usd"])
    shown_day = round(sum(e["pnl"] for e in real if _ny_day_of(e["sold_at"]) == day), 2)
    first_day = _ny_day_of(first_fill) if first_fill else None
    to_date: dict[str, Any] = {"since": first_day, "shown_usd": None, "net_usd": None, "metered_usd": None,
                               "events": len(real), "costs_from": None, "partial": False, "missing": []}
    per_event = None
    first_utc = _utc_day_of(first_fill) if first_fill else None
    if first_day is not None and first_utc is not None:
        span = MT.since(ledger, first_utc, now)
        shown = round(sum(e["pnl"] for e in real), 2)
        to_date.update(shown_usd=shown, metered_usd=_round(span["usd"]),
                       net_usd=None if span["usd"] is None else round(shown - span["usd"], 2),
                       costs_from=span["from"], partial=bool(span["partial"]), missing=list(span["missing"]))
        if span["usd"] is not None and real:
            per_event = float(span["usd"]) / len(real)  # THE PROGRAMS' NET: metered compute shared per settled real event
    profit = {"day": {"shown_usd": shown_day, "net_usd": None if day_spend is None else round(shown_day - day_spend, 2)},
              "to_date": to_date}
    programs = []
    for prog in P.SEATING:
        key = (prog.id, prog.version)
        status = statuses.get(key) or {}
        settled = status.get("settled") or {}
        mine = [e for e in real if (e["program"], e["version"]) == key]
        by_band = []
        for band in ("learning", "probe", "sized"):
            rows = [e for e in mine if e["band"] == band]
            if rows:
                shown = round(sum(e["pnl"] for e in rows), 2)
                by_band.append({"band": band, "n": len(rows), "shown_usd": shown,
                                "net_usd": None if per_event is None else round(shown - per_event * len(rows), 2)})
        look = status.get("next_look") or {}
        needed, have = _num(look.get("events_needed")), _num(look.get("events"))
        # (release 1019i, PREREG-EVL-6: its versions' looks are counted in settled session BLOCKS, by run or stay)
        blocks = "blocks_needed" in look
        b_need, b_have = _num(look.get("blocks_needed")), _num(look.get("blocks"))
        mean_b = _num(settled.get("mean_b_tradable"))
        programs.append({
            "id": prog.id, "version": prog.version, "band": str(status.get("band") or "learning"),
            "intents": sum(int(v or 0) for c, v in (status.get("intents_today") or {}).items() if c != "skipped"),
            "shadow_tradable": int(settled.get("n_tradable") or 0), "real": len(mine),
            "shown_usd": round(sum(e["pnl"] for e in mine), 2) if mine else None,
            "net_usd": None if not mine or per_event is None else round(sum(e["pnl"] for e in mine) - per_event * len(mine), 2),
            "by_band": by_band, "next_look": look.get("k"),
            "events_to_go": None if needed is None or have is None else int(max(0.0, needed - have)),
            "look_unit": "blocks" if blocks else "events",
            "blocks_to_go": None if b_need is None or b_have is None else int(max(0.0, b_need - b_have)),
            "look_of": f"{look['kind']} {int(look['n'])}" if blocks and look.get("kind") in ("run", "stay") else None,
            "market_share_pct": _round(None if settled.get("market_share") is None else 100 * float(settled["market_share"]), 0),
            "bench_mean_bp": _round(None if mean_b is None else mean_b * 1e4, 1),
            "buy_hold_usd": holds[key]["usd"], "buy_hold_why": holds[key]["why"]})
    intents = [{"id": p, "version": v, "n": sum(int(x or 0) for c, x in (s.get("intents_today") or {}).items() if c != "skipped"),
                "skipped": int((s.get("intents_today") or {}).get("skipped") or 0)}
               for (p, v), s in sorted(statuses.items())]
    others = [s for key, s in statuses.items() if key not in seating]
    hold_known = [h["usd"] for h in holds.values() if h["usd"] is not None]
    by_side = {str(r["side"]): (int(r["n"]), float(r["fees"] or 0.0)) for r in fills}

    def total(name: str, key: str = "total") -> int:
        return int((ev.get(name) or {}).get(key) or 0)
    done = done_line(root)
    return {
        "kind": KIND, "notice_id": f"report:{day}", "day": day, "at": MT._iso(now), "lane_report": bool(lane_report),
        "profit": profit, "costs": costs,
        "events": {"8k_202": total("8-K 2.02"), "8k_other": total("8-K other"), "form4": total("Form 4"),
                   "news": total("news"), "failed": sum(total(f, "failed") for f in ("8-K 2.02", "8-K other", "Form 4"))},
        "verdicts": {s: int((vd.get(s) or {}).get("n") or 0) for s in ("ok", "unparsed", "refused")}
                    | {"usd": round(verdicts_usd, 2)},
        "intents": [row for row in intents if row["n"] or row["skipped"]],
        "fills": {"buys": by_side.get("buy", (0, 0.0))[0], "sells": by_side.get("sell", (0, 0.0))[0],
                  "fees_usd": round(sum(f for _, f in by_side.values()), 2), "gap": gap},
        "programs": programs,
        "records": {"versions": len(others),
                    "intents": sum(sum(int(v or 0) for c, v in (s.get("intents_today") or {}).items() if c != "skipped")
                                   for s in others),
                    "settled": sum(int((s.get("settled") or {}).get("n") or 0) for s in others)},
        "buy_hold": {"usd": round(sum(hold_known), 2) if hold_known else None,
                     "why": None if hold_known else "n/a until real fills"},
        "expected_false_passes": _round(efp.get("expected"), 2), "seatable_versions": int(efp.get("versions") or 0),
        # (release 1019i, PREREG-EVL-6 section 5: the count three ways and the per-version figure beside it; an older
        # gateway reads the two keys above and ignores this one)
        "false_passes": {"count": _round(efp.get("expected"), 2), "charge": _round(efp.get("charge"), 2),
                         "versions": int(efp.get("versions") or 0), "runs": int(efp.get("runs") or 0),
                         "waiting": int(efp.get("waiting") or 0), "budget": _round(efp.get("budget"), 2),
                         "left": _round(efp.get("left"), 2), "base": _round(efp.get("base"), 2),
                         "stress": _round(efp.get("stress"), 2), "per_version": _round(efp.get("per_version"), 2)},
        "alarms": sorted(str(a) for a in (alarms or [])),
        "entries": entries,
        "break_even": break_even(ledger, probe, on, now),
        "done": done,
        "supply": supply_line(root, on, done, {key: str((statuses.get(key) or {}).get("band") or "learning")
                                               for key in seating}, under),
    }


# ---------------------------------------------------------------------------------------------- release 1019f
#: The counts the report carries (league/ops/evl_health.py `auction_entries`), figures only: each auction's, and the day's.
AUCTION_FIELDS = ("planned", "filled")
TOTAL_FIELDS = ("planned", "filled", "venue_cancels", "resent", "resent_filled", "never_sent", "unfilled", "room_cut")


def day_entries(root: str | Path, day: str) -> dict[str, Any]:
    """THE DAY'S REAL EVENT BUYS (the module docstring's `entries`): {auctions: [{at, planned, filled, bound}], totals:
    {<TOTAL_FIELDS>, never: {reason: n} (every reason of evl_health `UNSENT`)}, why}; `why` says why there is none ("no
    event table in live.sqlite", "not read (<error>)"). Every figure is the gateway's to word (gateway/lib/email.mjs
    `composeReport`)."""
    from . import evl_health as EV

    try:
        with guard.readonly():
            found = EV.entry_facts(root, EV.auctions_of(day))
    except Exception as exc:  # noqa: BLE001 - the report goes without them, saying so
        return {"auctions": [], "totals": _totals([]), "why": f"not read ({type(exc).__name__})"}
    if found is None:
        return {"auctions": [], "totals": _totals([]), "why": "no event table in live.sqlite"}
    rows = [{"at": a["at"], **{k: int(a.get(k) or 0) for k in AUCTION_FIELDS}, "bound": str(a.get("bound") or "none")}
            for a in found]
    return {"auctions": rows, "totals": _totals(found), "why": None}


def _totals(found: list[Mapping[str, Any]]) -> dict[str, Any]:
    from . import evl_health as EV

    totals = EV.entry_totals(found)
    return {**{k: int(totals.get(k) or 0) for k in TOTAL_FIELDS}, "never": dict(totals["never"])}


def probe_buys(store: Any, before: str) -> dict[str, Any] | None:
    """The lane's real buys at Probe or Sized size (`real_fills` side buy, band probe or sized) filled before `before`:
    {first, usd, n}, None with none (or no `real_fills` table)."""
    if store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='real_fills'").fetchone() is None:
        return None
    row = store.db.execute("SELECT MIN(filled_at), COALESCE(SUM(qty * price), 0), COUNT(*) FROM real_fills WHERE "
                           "side='buy' AND band IN ('probe', 'sized') AND filled_at<?", (before,)).fetchone()
    if row is None or not row[2]:
        return None
    return {"first": str(row[0]), "usd": float(row[1] or 0.0), "n": int(row[2])}


def break_even(ledger: Mapping[str, Any], probe: Mapping[str, Any] | None, on: dt.date, now: float) -> dict[str, Any]:
    """THE BREAK-EVEN EDGE OF DONE'S COMPUTE CLAUSE (the module docstring's `break_even`): {since (the first Probe or Sized
    buy's New York day, None before one), compute_per_session, probe_per_session (dollars over the NYSE sessions from
    that day through `on`), edge_bp (their ratio in basis points of the Probe dollars), partial (the meters cover the
    span in part), why}; edge_bp None ("n/a until a Probe buy", or the meters not read since)."""
    from . import evl_health as EV

    out: dict[str, Any] = {"since": None, "compute_per_session": None, "probe_per_session": None, "edge_bp": None,
                           "partial": False, "why": "n/a until a Probe buy"}
    if not probe or not probe.get("usd"):
        return out
    first, first_utc = _ny_day_of(probe["first"]), _utc_day_of(probe["first"])
    if first is None or first_utc is None:
        return {**out, "why": "n/a: the first Probe buy has no readable time"}
    sessions = len(EV.sessions(dt.date.fromisoformat(first), on)) or 1
    span = MT.since(ledger, first_utc, now)
    usd = _num(span.get("usd"))
    out.update(since=first, probe_per_session=round(float(probe["usd"]) / sessions, 2), partial=bool(span.get("partial")))
    if usd is None:
        return {**out, "why": "n/a: the meters were not read since the first Probe buy"}
    return {**out, "compute_per_session": round(usd / sessions, 2), "edge_bp": round(usd / float(probe["usd"]) * 1e4, 1),
            "why": None}


# ---------------------------------------------------------------------------------------------- release 1019h
#: SUP-4 (the captain's A97; the module docstring's `supply`): the sessions whose decisions measure a row's real picks,
#: the sessions a projection looks ahead at most, and THE STATED SEASON MULTIPLIERS (the done-speed design's stated
#: earnings-calendar shape after Nov 20, 2026 to mid-January: earnings rows x0.2, news rows x0.6 of the rate measured
#: now; any other family, and any other session, x1.0). Stated, NOT MEASURED: the line says so beside every projection.
SUPPLY_SESSIONS = 5
SUPPLY_HORIZON = 250
SEASON_STATED: tuple[tuple[dt.date, dt.date, dict[str, float]], ...] = (
    (dt.date(2026, 11, 21), dt.date(2027, 1, 15), {"ern": 0.2, "news": 0.6}),)


def season_of(family: str) -> str | None:
    """The stated season a program family follows: "ern" for the earnings families (ern, ern-react, ern-drop, ...),
    "news" for the news families (news, news-day, news-react, news-pm, news-night2), None for the rest (8-K, Form 4)."""
    family = str(family or "")
    return "ern" if family.startswith("ern") else "news" if family.startswith("news") else None


def season_multiplier(family: str, day: dt.date) -> float:
    """The stated multiplier of `family`'s measured rate on session `day` (`SEASON_STATED`; 1.0 outside it)."""
    kind = season_of(family)
    for first, last, by in SEASON_STATED:
        if kind is not None and first <= day <= last:
            return float(by.get(kind, 1.0))
    return 1.0


def picks_a_session(root: str | Path, day: dt.date, programs: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    """THE MEASURED REAL PICKS of each program of `programs` ({id: its entry auction, open | close}) over the last
    `SUPPLY_SESSIONS` NYSE sessions through `day`: {id: {per_session (the picks ROOM GAVE it, `planned`, a decision of its
    auction it was decided at, over those decisions; None with none), decisions}} from the book's `eq_event_decisions`
    in `<root>/live.sqlite` (read-only); {} with no such table."""
    from . import evl_health as EV

    days = [s["day"].isoformat() for s in EV.sessions(day - dt.timedelta(days=14), day)][-SUPPLY_SESSIONS:]
    path = Path(root) / EV.LIVE_DB
    if not days or not path.exists():
        return {}

    def read(db: Any) -> list[Any] | None:
        names = {str(r[0]) for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "eq_event_decisions" not in names:
            return None
        return guard.batched(db, "SELECT day, at, summary FROM eq_event_decisions WHERE status='done' AND day IN "
                                 "({marks})", days)
    rows = guard.read(path, read)
    if rows is None:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for program, at in programs.items():
        given = made = 0
        for r in rows:
            if str(r["at"]) != at:
                continue
            try:
                summary = json.loads(r["summary"]) if isinstance(r["summary"], str) else None
            except ValueError:
                summary = None
            mine = (summary.get("programs") or {}).get(program) if isinstance(summary, Mapping) else None
            if not isinstance(mine, Mapping) or "error" in mine:
                continue
            made += 1
            planned = _num(mine.get("planned"))
            given += int(planned) if planned is not None and planned > 0 else 0
        out[program] = {"per_session": round(given / made, 2) if made else None, "decisions": made}
    return out


def under_size(store: Any) -> dict[tuple[str, int], dict[str, Any]]:
    """The lane's real Probe+ buys UNDER DONE'S SIZE BAR (`real_fills` side buy, band probe or sized, the judge's own
    `at_size` False: a buy from before release 1019f's record reads as under), by (program, version): {n, by: {binding:
    n}} (the cap recorded as each one's binding, "none" when none was)."""
    from ..events import done as DN

    out: dict[tuple[str, int], dict[str, Any]] = {}
    if store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='real_fills'").fetchone() is None:
        return out
    have = {str(r[1]) for r in store.db.execute("PRAGMA table_info(real_fills)")}
    if not {"target_usd", "sized_usd", "binding"} <= have:
        return out
    for r in store.db.execute("SELECT program, version, target_usd, sized_usd, binding FROM real_fills WHERE side='buy' "
                              "AND band IN ('probe', 'sized')"):
        if DN.at_size(r["target_usd"], r["sized_usd"]):
            continue
        cell = out.setdefault((str(r["program"]), int(r["version"])), {"n": 0, "by": {}})
        cell["n"] += 1
        name = str(r["binding"] or "none")
        cell["by"][name] = cell["by"].get(name, 0) + 1
    return out


def _most(by: Any) -> str | None:
    """The binding most often recorded (the first in name order among equals), None with none."""
    if not isinstance(by, Mapping) or not by:
        return None
    return sorted(by.items(), key=lambda kv: (-int(kv[1] or 0), str(kv[0])))[0][0]


def _to_each(counted: int, rate: float | None, family: str, ahead: list[dt.date], each: int) -> int | None:
    """The sessions ahead (1 the next) at which `counted` reaches `each` at `rate` a session x the stated multiplier;
    0 when it is there already; None when it does not within `ahead`."""
    if counted >= each:
        return 0
    if not rate or rate <= 0:
        return None
    total = float(counted)
    for i, day in enumerate(ahead, start=1):
        total += rate * season_multiplier(family, day)
        if total >= each - 1e-9:
            return i
    return None


def supply_line(root: str | Path, on: dt.date, done: Mapping[str, Any], bands: Mapping[tuple[str, int], str],
                under: Mapping[tuple[str, int], Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """THE DONE SUPPLY LINE (the module docstring's `supply`): {rows: [{id, version, band, counted, picks_per_session,
    decisions, under_size, under_bound (the cap most often recorded on them, "none" when none was), to_50 (sessions ahead, 0 there already, None not within the horizon), on_day}],
    checkpoint, checkpoint_in (sessions ahead the rows' projected total reaches it, None not within the horizon), reach
    (rows at 50 by then), flag, horizon, stated (True: the season multipliers are stated, not measured), why}. Report
    only."""
    from ..events import done as DN
    from ..events import programs as P
    from . import evl_health as EV

    each, need = DN.DONE_PER_PROGRAM, DN.DONE_PROGRAMS
    counted = {(str(r.get("id")), int(r.get("version") or 0)): r.get("n") for r in (done.get("by_program") or [])
               if isinstance(r, Mapping)}
    probe_up = [p for p in P.SEATING if bands.get((p.id, p.version)) in ("probe", "sized")]
    out: dict[str, Any] = {"rows": [], "checkpoint": None, "checkpoint_in": None, "reach": 0, "flag": True,
                           "horizon": SUPPLY_HORIZON, "stated": True, "why": None}
    nxt = done.get("next_checkpoint") if isinstance(done.get("next_checkpoint"), int) else None
    out["checkpoint"] = max(DN.DONE_EVENTS, nxt or 0)
    if not probe_up:
        return {**out, "why": "no Probe+ row yet"}
    try:
        picks = picks_a_session(root, on, {p.id: p.entry_at for p in probe_up})
    except Exception as exc:  # noqa: BLE001 - the line goes without the measure, saying so
        picks, out["why"] = {}, f"picks not read ({type(exc).__name__})"
    ahead = [s["day"] for s in EV.sessions(on + dt.timedelta(days=1), on + dt.timedelta(days=SUPPLY_HORIZON * 2))]
    ahead = ahead[:SUPPLY_HORIZON]
    rows = []
    for p in probe_up:
        n = counted.get((p.id, p.version))
        have = n if isinstance(n, int) and not isinstance(n, bool) else 0
        rate = (picks.get(p.id) or {}).get("per_session")
        to = _to_each(have, rate, p.family, ahead, each)
        cut = (under or {}).get((p.id, p.version)) or {}
        rows.append({"id": p.id, "version": p.version, "band": bands.get((p.id, p.version)),
                     "counted": n if isinstance(n, int) and not isinstance(n, bool) else None,
                     "picks_per_session": rate, "decisions": int((picks.get(p.id) or {}).get("decisions") or 0),
                     "under_size": int(cut.get("n") or 0), "under_bound": _most(cut.get("by")),
                     "to_50": to, "on_day": None if not to else ahead[to - 1].isoformat(),
                     "_rate": rate or 0.0, "_have": have, "_family": p.family})
    # The checkpoint at which Done can first be read: the session the rows' projected total reaches it.
    total = float(sum(r["_have"] for r in rows))
    at: int | None = 0 if total >= out["checkpoint"] else None
    if at is None:
        for i, day in enumerate(ahead, start=1):
            total += sum(r["_rate"] * season_multiplier(r["_family"], day) for r in rows)
            if total >= out["checkpoint"] - 1e-9:
                at = i
                break
    limit = at if at is not None else len(ahead)
    reach = sum(1 for r in rows if r["to_50"] is not None and r["to_50"] <= limit)
    for r in rows:
        for key in ("_rate", "_have", "_family"):
            r.pop(key)
    return {**out, "rows": rows, "checkpoint_in": at, "reach": reach, "flag": reach < need}


__all__ = ["due", "facts", "done_line", "buy_and_hold", "ReadOnlyStore", "KIND", "REPORT_BY", "STALE_AFTER",
           "day_entries", "probe_buys", "break_even", "AUCTION_FIELDS", "TOTAL_FIELDS"]
#: (release 1019h, SUP-4: the Done supply line)
__all__ += ["supply_line", "picks_a_session", "under_size", "season_of", "season_multiplier", "SUPPLY_SESSIONS",
            "SUPPLY_HORIZON", "SEASON_STATED"]
