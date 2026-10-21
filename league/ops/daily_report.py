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
  version 1 of PREREG-EVL-4's three from release 1019d and of PREREG-EVL-5's three from release 1019g), in the tables'
  order: its
  band, settled n (shadow TRADABLE, and real), account-shown and Net by band (metered compute shared over the settled
  real events, so the programs' Nets add up to the lane's), its next look and the TRADABLE events to go, the
  market-direction share and the benchmark's mean (shadow, PREREG-EVL-1 section 7's "beside every look"), and its
  same-risk buy-and-hold: the event's benchmark bought and held continuously from its first real buy to its last real
  sale at its average invested dollars (PREREG-EVL-1 section 9), "n/a until real fills".
- the records and controls in one line, the `expected_false_passes`, and the `alarms` standing at this run.
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
    store cannot be read (the stall job says so and tries again at its next run)."""
    from ..events import programs as P
    from ..events import report as RP
    from ..events import screen as SC

    root = Path(root)
    on = dt.date.fromisoformat(day)
    ledger = ledger if isinstance(ledger, Mapping) else MT.load(root)
    with guard.readonly():
        store = ReadOnlyStore(root / LANE)
        try:
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
        finally:
            store.close()
    from . import evl_health as EV

    try:   # THE FILL GAP (the goal's "fill gaps"): the last 20 priced event twins, per side
        gap = EV.fill_gaps(EV.event_twins(root))
    except Exception:  # noqa: BLE001 - no twins read: no gap said
        gap = EV.fill_gaps([])
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
        mean_b = _num(settled.get("mean_b_tradable"))
        programs.append({
            "id": prog.id, "version": prog.version, "band": str(status.get("band") or "learning"),
            "intents": sum(int(v or 0) for c, v in (status.get("intents_today") or {}).items() if c != "skipped"),
            "shadow_tradable": int(settled.get("n_tradable") or 0), "real": len(mine),
            "shown_usd": round(sum(e["pnl"] for e in mine), 2) if mine else None,
            "net_usd": None if not mine or per_event is None else round(sum(e["pnl"] for e in mine) - per_event * len(mine), 2),
            "by_band": by_band, "next_look": look.get("k"),
            "events_to_go": None if needed is None or have is None else int(max(0.0, needed - have)),
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
        "alarms": sorted(str(a) for a in (alarms or [])),
    }


__all__ = ["due", "facts", "buy_and_hold", "ReadOnlyStore", "KIND", "REPORT_BY", "STALE_AFTER"]
