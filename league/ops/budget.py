"""THE BUDGET RULE (LTCM v3, the owner's D4, Oct 2026): research is bought with a budget that follows realized profit, and
the desk asks for a card only when a prefund is actually short.

THE RULE (pre-registered: the constants below, changed only by the owner's own deploy; this file is FORBIDDEN to the
updater, `league/ci.py`). The `budget` job (after the close economics, and daily at 00:30 UTC) reads, for each meter m in
{sail, claude}:

- balance_m: Sail's balance as the Sail guard last read it (its provider reading, kv `guard` in the swarm store, at most
  `BALANCE_FRESH_SECONDS` old); Claude's funded total left at the gateway (`GET /v1/health`: cap - spent - in flight);
- fixed_m: Sail: the House box's and the data box's own billing over the trailing `FIXED_WINDOW_DAYS` days
  (`SailboxClient.spend`) a day, never below `guard.house_burn_usd_day` (which is also the fallback); Claude: 0;
- reserve_m: never spent (`RESERVE_USD`);

and p30: the trailing-30-calendar-day realized options P&L, fees in, every real route (`league.ops.economics.p30` when
that module is there, else its own read of the live book's closed positions and the broker's posted fee corrections).
Marks never fund research. Then, a day:

    sustainable_m = max(0, balance_m - reserve_m - R * fixed_m) / R
    floor_m       = min(sustainable_m, FLOOR_CAP * FLOOR_SPLIT[m])
    earned        = PROFIT_SHARE * max(0, p30) / 30, split across the meters by need (each meter's research spend over
                    the trailing `NEED_WINDOW_DAYS` days; `FLOOR_SPLIT` when there was none)
    research_m    = min(floor_m + earned_m, max(0, balance_m - reserve_m - W * fixed_m) / W)

so research never pushes a meter under W days. THE NO-FORWARD-EDGE STOP: once `EDGE_SESSIONS` sessions have closed since
`EDGE_START` (or since the day after the last Probe promotion, whichever is later) with no Probe promotion, earned is 0
and the state says "no forward edge; research at floor"; a promotion lifts it.

UNKNOWN IS NEVER MONEY. An unreadable balance or fixed cost gives its meter no research. An unreadable p30 earns nothing;
so does an unreadable promotion record once the stop could apply (the sessions are then counted from `EDGE_START`).

THE OUTPUT, `<state>/budget.json` (private): the inputs, each meter's research $/day, the knob values, the direction
against the last file (cut, raise or same), each meter's runway at its current total rate (fixed + research) and its
next card action date (when that runway falls to W days), and why.

ENFORCEMENT, TIGHTEN-ONLY (`overlay`, the last step of `league.swarm.settings.load` with a state root). The research
$/day become knob values (`knobs`), applied as min() against the configured `researcher.sail_usd_per_hour` (while that is
unset, against `researcher.usd_per_hour`, the combined pace that then governs Sail), `gym.max_boxes`, every
`claude.role_usd_day` line (and a line for each role in `claude.roles`) and `population.ceiling`, and as max() against
`architect.every_seconds`. A configured value that is not a number is left as it is (its reader already refuses it).
The settings' `budget` block carries the $/day to the Sail guard (its daily cap: the swarm's booked Sail today under the
Sail research $/day, Sail's own meter today under that plus fixed; `sail_caps`) and to the router (Claude's room is also
capped by the Claude research $/day less today's Claude spend). A missing, unreadable, malformed or stale (older than
`STALE_SECONDS`) budget.json is the FLOOR: `FLOOR_CAP * FLOOR_SPLIT` per meter. An operator's own `budget` key in
swarm.json is replaced, never read.

THE FUNDING NOTICE. When a meter's runway at its current total rate is under W days, one `POST /v1/notify` kind
`funding` (`notice_facts`: the meter, its balance, $/day, runway, the amount that restores R days and the dates), at
most once per meter every `NOTICE_EVERY_SECONDS` (notice id `funding:<meter>:<ISO week>`, which the gateway dedupes too;
`<state>/budget-notices.json` remembers what was sent). `drill` sends the same from a synthetic cliff with `test: true`.

Nothing here moves money, tops anything up or raises a cap: the owner pays, and the budget only ever tightens the
configured knobs. Standard library only (and `ltcm.data`'s computed NYSE calendar for the session count).
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping

REPO = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------------------------- the rule's constants
#: budget.json's format.
SCHEMA = 1
#: The rule's version (the constants below); a change is an owner deploy and a new number here.
RULE_VERSION = 1
METERS = ("sail", "claude")
#: Target runway (days) and the card line (days): research never takes a meter under W days at its current total rate.
R_DAYS = 90
W_DAYS = 60
#: The research floor, every meter together, dollars a day, and its split.
FLOOR_CAP_USD_DAY = 5.0
FLOOR_SPLIT = {"sail": 0.6, "claude": 0.4}
#: The share of trailing realized profit research may spend, and the window it is read over (calendar days).
PROFIT_SHARE = 0.5
P30_DAYS = 30
#: The close economics' p30 is used while its cutoff is the latest session close (`economics_fresh`): no session closed
#: after it, other than one whose own economics may still be running (closed less than `ECONOMICS_LAG_SECONDS` ago:
#: the job's three-hour grace and its half-hour wall). Measured in sessions, not hours, so a weekend or a holiday keeps
#: Friday's close fresh; a missed close falls back to the book. Without a calendar, `P30_FRESH_SECONDS` of wall time.
ECONOMICS_LAG_SECONDS = 3 * 3600 + 1800
P30_FRESH_SECONDS = 4 * 86400
#: Dollars on each meter research never spends.
RESERVE_USD = {"sail": 10.0, "claude": 5.0}
#: The no-forward-edge stop: this many sessions closed since `EDGE_START` (or the last Probe promotion) without one.
EDGE_START = dt.date(2026, 10, 5)
EDGE_SESSIONS = 60
#: The options record's financial basis (league/config.json `performance.start_at`): nothing opened before it is P&L.
PNL_BASIS = "2026-09-26T06:25:30Z"
#: Windows for Sail's fixed boxes and for each meter's research spend (need), days.
FIXED_WINDOW_DAYS = 7
NEED_WINDOW_DAYS = 7
#: The Sail guard's balance reading older than this is no reading.
BALANCE_FRESH_SECONDS = 6 * 3600
#: A budget.json older than this is the floor.
STALE_SECONDS = 36 * 3600
#: A funding notice per meter at most this often.
NOTICE_EVERY_SECONDS = 7 * 86400
#: The swarm's Sail spend kinds (league/swarm/guard.py SWARM_SAIL_KINDS) and Claude's.
SAIL_KINDS = ("sail_model", "gym_box")
CLAUDE_KINDS = ("claude",)

# ---------------------------------------------------------------------------------------------- the knobs' constants
#: The Sail research dollars that buy Gym boxes (the rest buys Sail models: measured Oct 2, about 60/40).
GYM_SHARE = 0.6
#: A busy Gym box's cost an hour, and the busy hours a day one budgeted box is planned for.
BOX_USD_HOUR = 0.20
BOX_DUTY_HOURS = 8.0
#: Research dollars a day per living family, and the population ceiling's least value.
FAMILY_USD_DAY = 1.0
CEILING_MIN = 8
#: The architect's cadence: every 4 hours at the floor, faster in proportion to the research dollars down to 30 minutes,
#: once a day with no research dollars at all.
ARCHITECT_FLOOR_SECONDS = 14400
ARCHITECT_MIN_SECONDS = 1800
ARCHITECT_IDLE_SECONDS = 86400

BUDGET_FILE = "budget.json"
NOTICES_FILE = "budget-notices.json"
EPSILON = 0.005


# ---------------------------------------------------------------------------------------------- small helpers
def _finite(value: Any) -> float | None:
    """A finite number (a numeric string counts; a bool does not), else None."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return out if math.isfinite(out) else None


def _amount(value: Any) -> float | None:
    """A finite, non-negative number, else None."""
    out = _finite(value)
    return out if out is not None and out >= 0 else None


def _iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(float(epoch), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch(text: Any) -> float | None:
    try:
        at = dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return (at if at.tzinfo is not None else at.replace(tzinfo=dt.timezone.utc)).timestamp()


def _day(epoch: float) -> dt.date:
    return dt.datetime.fromtimestamp(float(epoch), dt.timezone.utc).date()


def _get(ctx: Any, name: str, default: Any = None) -> Any:
    if isinstance(ctx, Mapping):
        return ctx.get(name, default)
    return getattr(ctx, name, default)


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _read_only(path: Path) -> sqlite3.Connection:
    """A read-only connection: the caller fetches, then closes before any other I/O."""
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def floor_usd_day(meter: str) -> float:
    """The floor's dollars a day for one meter (the most the floor ever is)."""
    return round(FLOOR_CAP_USD_DAY * FLOOR_SPLIT[meter], 4)


# ---------------------------------------------------------------------------------------------- the rule
def edge_state(now: float, promotions: list[float] | None) -> dict[str, Any]:
    """THE NO-FORWARD-EDGE STOP: sessions closed since the later of `EDGE_START` and the day after the last Probe
    promotion (`promotions`: their epochs; None when the record could not be read, counted as none). A calendar that
    cannot count is the stop (unknown is never money)."""
    from ltcm.data import us_equity_session

    anchor, last = EDGE_START, None
    if promotions:
        last = max(promotions)
        anchor = max(EDGE_START, _ny_day(last) + dt.timedelta(days=1))
    out: dict[str, Any] = {"anchor": anchor.isoformat(), "last_promotion": None if last is None else _iso(last),
                           "promotions_readable": promotions is not None}
    try:
        count, day, end = 0, anchor, _ny_day(now)
        while day <= end:
            session = us_equity_session(day)
            if session is not None and (_epoch(session.close_at) or float("inf")) <= now:
                count += 1
            day += dt.timedelta(days=1)
    except Exception as exc:  # noqa: BLE001 - a calendar that cannot count is the stop
        out.update(sessions=None, stop=True, why=f"the session calendar could not count ({type(exc).__name__}): earned is 0")
        return out
    stop = count >= EDGE_SESSIONS
    out.update(sessions=count, stop=stop,
               why=(f"{count} sessions since {anchor} with no Probe promotion: no forward edge; research at floor" if stop
                    else f"{count} of {EDGE_SESSIONS} sessions since {anchor} without a Probe promotion"))
    if promotions is None:
        out["why"] += " (the promotion record could not be read: counted as none)"
    return out


def _ny_day(epoch: float) -> dt.date:
    from zoneinfo import ZoneInfo

    return dt.datetime.fromtimestamp(float(epoch), ZoneInfo("America/New_York")).date()


def compute(inputs: Mapping[str, Any], *, now: float, previous: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """budget.json from the rule's inputs (`gather`'s shape):

        {"p30_usd": float | None, "p30_source": str, "edge": edge_state(...),
         "meters": {m: {"balance_usd": float | None, "fixed_usd_day": float | None, "need_usd": float, ...sources}}}

    `previous` is the last budget.json (for the direction). Pure: no I/O."""
    meters_in = inputs.get("meters") or {}
    edge = dict(inputs.get("edge") or {"stop": True, "why": "no edge state: earned is 0"})
    p30 = _finite(inputs.get("p30_usd"))
    why: list[str] = []
    if p30 is None:
        earned = 0.0
        why.append("p30 unreadable: nothing earned")
    elif edge.get("stop") is not False:
        earned = 0.0
        why.append(str(edge.get("why") or "no forward edge; research at floor"))
    else:
        earned = PROFIT_SHARE * max(0.0, p30) / P30_DAYS
        why.append(f"p30 {p30:.2f}: earned {earned:.4f} a day" if p30 > 0 else "p30 is not positive: nothing earned")
    needs = {m: _amount((meters_in.get(m) or {}).get("need_usd")) or 0.0 for m in METERS}
    total_need = sum(needs.values())
    shares = {m: needs[m] / total_need for m in METERS} if total_need > 0 else dict(FLOOR_SPLIT)
    today = _day(now)
    meters: dict[str, Any] = {}
    for m in METERS:
        given = meters_in.get(m) or {}
        balance, fixed, reserve = _finite(given.get("balance_usd")), _amount(given.get("fixed_usd_day")), RESERVE_USD[m]
        row: dict[str, Any] = {"balance_usd": balance, "fixed_usd_day": fixed, "reserve_usd": reserve,
                               "need_share": round(shares[m], 4), "earned_usd_day": round(earned * shares[m], 4)}
        if balance is None or fixed is None:
            row.update(research_usd_day=0.0, limited_by="unreadable", runway_days=None, card_date=None,
                       total_usd_day=None, restore_usd=None)
            why.append(f"{m}: the {'balance' if balance is None else 'fixed cost'} could not be read: no research")
            meters[m] = row
            continue
        room = balance - reserve
        sustainable = max(0.0, room - R_DAYS * fixed) / R_DAYS
        floor = min(sustainable, FLOOR_CAP_USD_DAY * FLOOR_SPLIT[m])
        w_cap = max(0.0, room - W_DAYS * fixed) / W_DAYS
        wanted = floor + earned * shares[m]
        research = min(wanted, w_cap)
        if wanted > w_cap:
            limited = "W"  # the card line binds: research would take the meter under W days
        else:
            limited = "sustainable" if floor < FLOOR_CAP_USD_DAY * FLOOR_SPLIT[m] else "floor"
            limited += " + earned" if earned * shares[m] > 0 else ""
        rate = fixed + research
        if room <= 0:
            runway = 0.0
        elif rate > 0:
            runway = room / rate
        else:
            runway = None  # nothing is spent: no runway to run out
        restore_rate = max(rate, fixed + FLOOR_CAP_USD_DAY * FLOOR_SPLIT[m])
        row.update(sustainable_usd_day=round(sustainable, 4), floor_usd_day=round(floor, 4), w_cap_usd_day=round(w_cap, 4),
                   research_usd_day=round(research, 4), limited_by=limited, total_usd_day=round(rate, 4),
                   runway_days=None if runway is None else round(runway, 1),
                   card_date=None if runway is None else (today + dt.timedelta(days=max(0.0, runway - W_DAYS))).isoformat(),
                   runs_out_on=None if runway is None else (today + dt.timedelta(days=runway)).isoformat(),
                   restore_usd=round(max(0.0, reserve + R_DAYS * restore_rate - balance), 2))
        meters[m] = row
    total = round(sum(meters[m]["research_usd_day"] for m in METERS), 4)
    before = _finite((previous or {}).get("research_usd_day")) if isinstance(previous, Mapping) else None
    direction = "same" if before is None or abs(total - before) <= EPSILON else ("raise" if total > before else "cut")
    for m in METERS:
        was = _finite((((previous or {}).get("meters") or {}).get(m) or {}).get("research_usd_day")) \
            if isinstance(previous, Mapping) else None
        now_m = meters[m]["research_usd_day"]
        meters[m]["direction"] = "same" if was is None or abs(now_m - was) <= EPSILON else ("raise" if now_m > was else "cut")
    if edge.get("stop") is not False and p30 is not None:
        state = "no forward edge; research at floor"
    elif earned > 0:
        state = "research at floor + profit share"
    else:
        state = "research at floor"
    if before is None:
        why.append("no earlier budget to compare")
    else:
        why.append(f"research {direction} ({before:.4f} -> {total:.4f} a day)")
    return {"schema": SCHEMA, "rule_version": RULE_VERSION, "at": float(now), "at_iso": _iso(now),
            "rule": {"R_days": R_DAYS, "W_days": W_DAYS, "floor_cap_usd_day": FLOOR_CAP_USD_DAY, "floor_split": dict(FLOOR_SPLIT),
                     "profit_share": PROFIT_SHARE, "p30_days": P30_DAYS, "reserve_usd": dict(RESERVE_USD),
                     "edge_start": EDGE_START.isoformat(), "edge_sessions": EDGE_SESSIONS},
            "inputs": {"p30_usd": p30, "p30_source": inputs.get("p30_source"), "edge": edge,
                       "meters": {m: dict(meters_in.get(m) or {}) for m in METERS}},
            "earned_usd_day": round(earned, 4), "no_forward_edge": bool(edge.get("stop") is not False and p30 is not None),
            "state": state, "meters": meters, "research_usd_day": total, "direction": direction,
            "knobs": knobs(meters["sail"]["research_usd_day"], meters["claude"]["research_usd_day"]), "why": why}


def knobs(sail_usd_day: Any, claude_usd_day: Any) -> dict[str, Any]:
    """The knob values the research dollars a day buy (pre-registered; `overlay` applies them tighten-only)."""
    sail, claude = _amount(sail_usd_day) or 0.0, _amount(claude_usd_day) or 0.0
    total = sail + claude
    gym = sail * GYM_SHARE
    if total <= 0:
        every = ARCHITECT_IDLE_SECONDS
    else:
        every = int(min(ARCHITECT_FLOOR_SECONDS, max(ARCHITECT_MIN_SECONDS, round(ARCHITECT_FLOOR_SECONDS * FLOOR_CAP_USD_DAY / total))))
    return {"researcher.sail_usd_per_hour": round(sail * (1 - GYM_SHARE) / 24, 6),
            "gym.max_boxes": max(1, int(math.floor(gym / (BOX_USD_HOUR * BOX_DUTY_HOURS) + 1e-9))),
            "claude.role_usd_day": round(claude, 4),
            "population.ceiling": max(CEILING_MIN, int(math.floor(total / FAMILY_USD_DAY + 1e-9))),
            "architect.every_seconds": every}


# ---------------------------------------------------------------------------------------------- enforcement
def floor_block(why: str) -> dict[str, Any]:
    """The settings' `budget` block at the FLOOR (no usable budget.json)."""
    return {"source": "floor", "why": why, "at": None, "state": "research at floor (no usable budget.json)",
            "sail_usd_day": floor_usd_day("sail"), "claude_usd_day": floor_usd_day("claude"), "fixed_sail_usd_day": None}


def read(root: str | Path, now: float) -> tuple[dict[str, Any] | None, str | None]:
    """(the settings' `budget` block from `<root>/budget.json`, None) or (None, why it is not usable)."""
    path = Path(root) / BUDGET_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "no budget.json yet"
    except (OSError, ValueError) as exc:
        return None, f"budget.json cannot be read ({type(exc).__name__})"
    if not isinstance(data, Mapping) or data.get("schema") != SCHEMA:
        return None, "budget.json is not schema 1"
    at = _finite(data.get("at"))
    if at is None:
        return None, "budget.json has no time"
    if at > now + 300:
        return None, "budget.json is dated in the future"
    if now - at > STALE_SECONDS:
        return None, f"budget.json is stale ({(now - at) / 3600:.0f} h old)"
    meters = data.get("meters")
    if not isinstance(meters, Mapping):
        return None, "budget.json has no meters"
    values = {}
    for m in METERS:
        row = meters.get(m)
        value = _amount(row.get("research_usd_day")) if isinstance(row, Mapping) else None
        if value is None:
            return None, f"budget.json's {m} research is not a number"
        values[m] = value
    sail = meters.get("sail") or {}
    return {"source": BUDGET_FILE, "why": None, "at": at, "state": str(data.get("state") or "")[:200],
            "sail_usd_day": values["sail"], "claude_usd_day": values["claude"],
            "fixed_sail_usd_day": _amount(sail.get("fixed_usd_day"))}, None


def _tighten(block: Any, key: str, value: float, *, larger: bool = False, integer: bool = False) -> None:
    """min() (`larger`: max()) of the configured `block[key]` and `value`; a configured value that is not a number is
    left alone (its reader refuses it already)."""
    if not isinstance(block, dict):
        return
    current = _amount(block.get(key))
    if current is None:
        return
    out = max(current, value) if larger else min(current, value)
    block[key] = int(out) if integer else out


def overlay(settings: dict[str, Any], root: str | Path, *, now: float | None = None) -> dict[str, Any]:
    """Apply the budget to merged settings in place, tighten-only (the module docstring), and set their `budget` block."""
    import time

    now = time.time() if now is None else float(now)
    try:
        block, why = read(root, now)
    except Exception as exc:  # noqa: BLE001 - anything unexpected is the floor
        block, why = None, f"budget.json could not be read ({type(exc).__name__})"
    if block is None:
        block = floor_block(why or "no budget.json")
    values = knobs(block["sail_usd_day"], block["claude_usd_day"])
    block["knobs"] = values
    researcher = settings.get("researcher")
    if isinstance(researcher, dict):
        key = "sail_usd_per_hour" if researcher.get("sail_usd_per_hour") is not None else "usd_per_hour"
        _tighten(researcher, key, values["researcher.sail_usd_per_hour"])
    _tighten(settings.get("gym"), "max_boxes", values["gym.max_boxes"], integer=True)
    _tighten(settings.get("population"), "ceiling", values["population.ceiling"], integer=True)
    _tighten(settings.get("architect"), "every_seconds", values["architect.every_seconds"], larger=True, integer=True)
    claude = settings.get("claude")
    if isinstance(claude, dict):
        lines = claude.get("role_usd_day")
        lines = {} if lines is None else lines
        if isinstance(lines, Mapping):  # anything else is read as a line of 0 for every role already
            roles = [r for r in (claude.get("roles") or []) if isinstance(r, str)] \
                if isinstance(claude.get("roles"), (list, tuple)) else []
            out = dict(lines)
            cap = values["claude.role_usd_day"]
            for role in [*lines.keys(), *roles]:
                given = lines.get(role)
                if given is None:
                    out[role] = cap
                elif _amount(given) is not None:
                    out[role] = min(_amount(given), cap)
            claude["role_usd_day"] = out
    settings["budget"] = block
    return settings


def sail_caps(settings: Mapping[str, Any]) -> dict[str, Any]:
    """The Sail guard's daily caps from the settings' `budget` block: `research` (the swarm's own booked Sail a UTC day)
    and `account` (Sail's own meter a UTC day: research + fixed). Settings that never went through a state root's
    `settings.load` (no block) are the floor; a malformed block is no research."""
    guard = settings.get("guard") if isinstance(settings.get("guard"), Mapping) else {}
    house = _amount(guard.get("house_burn_usd_day"))
    house = 1.0 if house is None else house
    block = settings.get("budget")
    if block is None:
        research, fixed, source = floor_usd_day("sail"), house, "floor (no budget block)"
    elif not isinstance(block, Mapping) or _amount(block.get("sail_usd_day")) is None:
        research, fixed, source = 0.0, house, "malformed budget block: no research"
    else:
        research = _amount(block.get("sail_usd_day"))
        measured = _amount(block.get("fixed_sail_usd_day"))
        fixed = max(house, measured) if measured is not None else house
        source = str(block.get("source") or "budget")
    return {"research": round(research, 4), "fixed": round(fixed, 4), "account": round(research + fixed, 4), "source": source}


# ---------------------------------------------------------------------------------------------- the inputs
def book_p30(root: str | Path, now: float, *, days: int = P30_DAYS) -> tuple[float | None, str]:
    """The live book's own trailing realized options P&L: every closed real position opened at or after `PNL_BASIS` and
    closed in the window, its cash (fees in) plus the broker's posted fee correction for it (the publisher's last
    activity reading in `<root>/publish.json`, when there is one). None when a closed row cannot be priced."""
    path = Path(root) / "live.sqlite"
    if not path.exists():
        return 0.0, "no live book: nothing realized"
    since, basis = now - days * 86400, _epoch(PNL_BASIS) or 0.0
    conn = _read_only(path)
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT pid, cash, qty, closed_at FROM positions WHERE status='closed' AND closed_at IS NOT NULL "
            "AND closed_at>? AND closed_at<=? AND opened_at>=?", (since, now, basis))]
    finally:
        conn.close()
    corrections: dict[str, Any] = {}
    note = "no broker fee corrections read"
    try:
        saved = json.loads((Path(root) / "publish.json").read_text(encoding="utf-8")).get("activity") or {}
        fees = (saved.get("reading") or {}).get("fees_by_pid")
        if isinstance(fees, Mapping):
            corrections, note = dict(fees), "with the broker's posted fee corrections"
    except (OSError, ValueError, AttributeError):
        pass
    total = Decimal(0)
    for row in rows:
        try:
            cash = Decimal(str(row["cash"]))
            fix = Decimal(str(corrections.get(str(row["pid"]), "0")))
        except (InvalidOperation, ValueError, TypeError):
            return None, f"position {row['pid']} cannot be priced"
        if not cash.is_finite() or not fix.is_finite() or int(row["qty"] or 0) != 0:
            return None, f"position {row['pid']} cannot be priced"
        total += cash + fix
    return float(round(total, 2)), f"the live book: {len(rows)} closed positions, {note}"


def economics_fresh(cutoff: float, now: float) -> bool:
    """The close economics at `cutoff` is the latest one there should be at `now`: no NYSE session closed after it (a
    minute's slack) and at least `ECONOMICS_LAG_SECONDS` before `now`."""
    if not 0 <= now - cutoff:
        return False
    if now - cutoff > 14 * 86400:
        return False
    try:
        from ltcm.data import us_equity_session

        day, end = _ny_day(cutoff), _ny_day(now)
        while day <= end:
            session = us_equity_session(day)
            closed = _epoch(session.close_at) if session is not None else None
            if closed is not None and cutoff + 60 < closed <= now - ECONOMICS_LAG_SECONDS:
                return False
            day += dt.timedelta(days=1)
        return True
    except Exception:  # noqa: BLE001 - without a calendar, wall time decides
        return now - cutoff <= P30_FRESH_SECONDS


def _p30(root: Path, now: float, errors: list[str]) -> tuple[float | None, str]:
    try:
        from . import economics  # league/ops/economics.py (the close economics), when it is there
    except ImportError:
        economics = None
    reader = getattr(economics, "latest", None)
    if callable(reader):
        try:
            summary = reader(root)
            cutoff = _epoch((summary or {}).get("cutoff"))
            value = _amount(((summary or {}).get("p30") or {}).get("usd"))
            if summary is None:
                pass  # no close yet (a new House): the book's own read is the source, not an error
            elif cutoff is None or not economics_fresh(cutoff, now):
                errors.append("the close economics is stale: the live book's own read is used")
            elif value is not None:
                return value, "league.ops.economics.p30"
            else:
                errors.append("league.ops.economics.p30 gave no number: the live book's own read is used")
        except Exception as exc:  # noqa: BLE001 - the book's own read stands in
            errors.append(f"league.ops.economics.p30 failed ({type(exc).__name__}): the live book's own read is used")
    try:
        return book_p30(root, now)
    except Exception as exc:  # noqa: BLE001 - unknown is never money
        errors.append(f"the live book could not be read ({type(exc).__name__}): nothing earned")
        return None, "unreadable"


def _swarm_reads(root: Path, now: float, errors: list[str]) -> dict[str, Any]:
    """From the swarm store, read-only: the Sail guard's last reading, the Probe promotions, each meter's research spend."""
    out: dict[str, Any] = {"guard": None, "promotions": None, "need": {m: 0.0 for m in METERS}}
    path = root / "swarm.sqlite"
    if not path.exists():
        errors.append("no swarm store: no guard reading, no promotion record")
        return out
    try:
        conn = _read_only(path)
        try:
            row = conn.execute("SELECT value FROM kv WHERE key='guard'").fetchone()
            bands = [dict(r) for r in conn.execute("SELECT at, payload FROM events WHERE kind='swarm.band'")]
            spend = [dict(r) for r in conn.execute("SELECT kind, COALESCE(SUM(usd),0) AS usd FROM spend WHERE epoch>=? "
                                                   "GROUP BY kind", (now - NEED_WINDOW_DAYS * 86400,))]
        finally:
            conn.close()
    except sqlite3.Error as exc:
        errors.append(f"the swarm store could not be read ({type(exc).__name__})")
        return out
    try:
        out["guard"] = json.loads(row["value"]) if row else None
    except (TypeError, ValueError):
        out["guard"] = None
    promotions = []
    for event in bands:
        try:
            payload = json.loads(event["payload"] or "{}")
        except (TypeError, ValueError):
            continue
        at = _epoch(event["at"])
        if payload.get("band_to") == "probe" and payload.get("band_from") in ("gym", "candidate") and at is not None:
            promotions.append(at)
    out["promotions"] = promotions
    by_kind = {r["kind"]: float(r["usd"] or 0.0) for r in spend}
    out["need"] = {"sail": sum(by_kind.get(k, 0.0) for k in SAIL_KINDS), "claude": sum(by_kind.get(k, 0.0) for k in CLAUDE_KINDS)}
    return out


def _house_boxes(root: Path, config: Mapping[str, Any]) -> list[str]:
    boxes = []
    pinned = (config.get("backup") or {}).get("box_id") if isinstance(config.get("backup"), Mapping) else None
    house = pinned or os.environ.get("SAILBOX_ID") or os.environ.get("SAIL_SAILBOX_ID")
    if house:
        boxes.append(str(house))
    try:
        data = json.loads((root / "data" / "data_box.json").read_text(encoding="utf-8")).get("box_id")
        if data:
            boxes.append(str(data))
    except (OSError, ValueError, AttributeError):
        pass
    return boxes


def _sail_fixed(sail: Any, boxes: list[str], now: float, house_burn: float, errors: list[str]) -> tuple[float, str]:
    """Sail's fixed cost a day: the House box's and the data box's billing over `FIXED_WINDOW_DAYS`, never below the
    configured `guard.house_burn_usd_day` (the guard's own rule; also the fallback)."""
    if sail is None or not boxes:
        return house_burn, "guard.house_burn_usd_day (no Sail client or no House box id)"
    from league.sailbox import usd

    total = 0.0
    try:
        for box in boxes:
            spent = _amount(usd(sail.spend(sailbox=box, since=_iso(now - FIXED_WINDOW_DAYS * 86400), until=_iso(now)))["total_usd"])
            if spent is None:
                raise ValueError(f"no spend for {box}")
            total += spent
    except Exception as exc:  # noqa: BLE001 - the configured burn stands in
        errors.append(f"Sail's box spend could not be read ({type(exc).__name__}): guard.house_burn_usd_day is used")
        return house_burn, "guard.house_burn_usd_day (the box spend could not be read)"
    measured = total / FIXED_WINDOW_DAYS
    if measured >= house_burn:
        return measured, f"measured: {len(boxes)} boxes over {FIXED_WINDOW_DAYS} days"
    return house_burn, f"guard.house_burn_usd_day (over the measured {measured:.4f} a day)"


def _claude_balance(health: Any) -> float | None:
    """The funded Claude total left (`/v1/health`'s `claude` block): its `remaining_usd`, else cap - spent; None when
    unconfigured or unreadable. The gateway's `spent_usd` already counts the holds in flight (gate.mjs `claudeReserve`
    adds a hold to both `spent` and `inflight`), so `inflight_usd` is never subtracted again."""
    block = health.get("claude") if isinstance(health, Mapping) else None
    if not isinstance(block, Mapping) or block.get("configured") is False:
        return None
    if block.get("remaining_usd") is not None:
        remaining = _finite(block.get("remaining_usd"))
        return None if remaining is None else round(remaining, 4)
    cap, spent = _finite(block.get("cap_usd")), _finite(block.get("spent_usd"))
    if cap is None or spent is None:
        return None
    return round(max(0.0, cap - spent), 4)


def _gateway(config: Mapping[str, Any]) -> tuple[str | None, str | None]:
    return config.get("gateway_url"), os.environ.get("GATEWAY_TOKEN")


def _health_reader(config: Mapping[str, Any]) -> Callable[[], Any] | None:
    url, token = _gateway(config)
    if not url or not token:
        return None

    def read() -> Any:
        import urllib.request

        request = urllib.request.Request(str(url).rstrip("/") + "/v1/health",
                                         headers={"Authorization": "Bearer " + str(token), "User-Agent": "ltcm-floor/1.0"})
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - https gateway only
            return json.loads(response.read(256_000))
    return read


def _notifier(config: Mapping[str, Any]) -> Callable[[Mapping[str, Any]], Any] | None:
    url, token = _gateway(config)
    if not url or not token:
        return None

    def send(facts: Mapping[str, Any]) -> Any:
        from ltcm.notify import post_json

        return post_json(str(url).rstrip("/") + "/v1/notify", str(token), facts)
    return send


def _config(ctx: Any) -> dict[str, Any]:
    config = _get(ctx, "config")
    if isinstance(config, Mapping):
        return dict(config)
    try:
        return json.loads((REPO / "league" / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _root(ctx: Any) -> Path:
    root = _get(ctx, "root") or _get(ctx, "state_root") or getattr(_get(ctx, "house"), "root", None)
    if root is None:
        raise ValueError("the budget job needs the House's state root")
    return Path(root)


def _now(ctx: Any) -> float:
    now = _get(ctx, "now")
    if callable(now):
        now = now()
    if now is None:
        clock = _get(ctx, "clock")
        import time

        now = clock() if callable(clock) else time.time()
    return float(now)


def gather(root: Path, now: float, *, config: Mapping[str, Any], settings: Mapping[str, Any], sail: Any = None,
           health: Callable[[], Any] | None = None, errors: list[str]) -> dict[str, Any]:
    """The rule's inputs (`compute`'s shape), every read guarded: what cannot be read is None, never a number."""
    swarm = _swarm_reads(root, now, errors)
    guard_cfg = settings.get("guard") if isinstance(settings.get("guard"), Mapping) else {}
    house_burn = _amount(guard_cfg.get("house_burn_usd_day"))
    house_burn = 1.0 if house_burn is None else house_burn
    last = (swarm["guard"] or {}).get("last") if isinstance(swarm["guard"], Mapping) else None
    last = last if isinstance(last, Mapping) else {}
    balance, at = _finite(last.get("balance")), _finite(last.get("at"))
    if balance is None or at is None or not 0 <= now - at <= BALANCE_FRESH_SECONDS:
        balance_source = "the Sail guard has no fresh reading"
        balance = None
    else:
        balance_source = f"the Sail guard's reading at {_iso(at)}"
    fixed, fixed_source = _sail_fixed(sail, _house_boxes(root, config), now, house_burn, errors)
    claude_balance, claude_source = None, "the gateway's /v1/health could not be read"
    if health is not None:
        try:
            claude_balance = _claude_balance(health())
            if claude_balance is not None:
                claude_source = "the gateway's /v1/health (cap - spent - in flight)"
        except Exception as exc:  # noqa: BLE001 - unknown is never money
            errors.append(f"the gateway's /v1/health could not be read ({type(exc).__name__})")
    p30, p30_source = _p30(root, now, errors)
    try:
        edge = edge_state(now, swarm["promotions"])
    except Exception as exc:  # noqa: BLE001 - the stop stands when it cannot be judged
        edge = {"stop": True, "why": f"the forward edge could not be judged ({type(exc).__name__}): earned is 0"}
    return {"p30_usd": p30, "p30_source": p30_source, "edge": edge,
            "meters": {"sail": {"balance_usd": balance, "balance_source": balance_source, "fixed_usd_day": round(fixed, 4),
                                "fixed_source": fixed_source, "need_usd": round(swarm["need"]["sail"], 4)},
                       "claude": {"balance_usd": claude_balance, "balance_source": claude_source, "fixed_usd_day": 0.0,
                                  "fixed_source": "none", "need_usd": round(swarm["need"]["claude"], 4)}}}


# ---------------------------------------------------------------------------------------------- the funding notice
def _week(now: float) -> str:
    year, week, _ = _day(now).isocalendar()
    return f"{year}-W{week:02d}"


def short(doc: Mapping[str, Any]) -> list[str]:
    """The meters whose runway at their current total rate is under W days."""
    out = []
    for m in METERS:
        runway = _finite(((doc.get("meters") or {}).get(m) or {}).get("runway_days"))
        if runway is not None and runway < W_DAYS:
            out.append(m)
    return out


def notice_facts(doc: Mapping[str, Any], meter: str, now: float, *, test: bool = False) -> dict[str, Any]:
    """The `funding` notice's facts (the gateway composes the words): decimals as strings."""
    row = (doc.get("meters") or {}).get(meter) or {}

    def money(value: Any) -> str | None:
        number = _finite(value)
        return None if number is None else f"{number:.2f}"
    # A drill's id is its own minute's (the gateway remembers funding ids for 8 days, and a second drill in the same week
    # must reach the owner again, not be answered `duplicate`).
    notice_id = f"funding-test:{meter}:{_week(now)}:{int(now // 60)}" if test else f"funding:{meter}:{_week(now)}"
    return {"kind": "funding", "notice_id": notice_id, "meter": meter,
            "balance_usd": money(row.get("balance_usd")), "usd_day": money(row.get("total_usd_day")),
            "fixed_usd_day": money(row.get("fixed_usd_day")), "research_usd_day": money(row.get("research_usd_day")),
            "runway_days": None if _finite(row.get("runway_days")) is None else f"{float(row['runway_days']):.1f}",
            "restore_usd": money(row.get("restore_usd")), "restore_days": R_DAYS, "card_line_days": W_DAYS,
            "card_date": row.get("card_date"), "runs_out_on": row.get("runs_out_on"), "at": _iso(now), "test": bool(test)}


def _sent(answer: Any) -> bool:
    return isinstance(answer, Mapping) and (answer.get("sent") is True or answer.get("duplicate") is True)


def send_notices(doc: Mapping[str, Any], root: Path, now: float, notify: Callable[[Mapping[str, Any]], Any] | None,
                 errors: list[str]) -> list[dict[str, Any]]:
    """One `funding` notice per short meter, at most once per meter every `NOTICE_EVERY_SECONDS`: a meter is recorded as
    told only when the gateway says the notice was sent (or already was)."""
    path = root / NOTICES_FILE
    try:
        told = json.loads(path.read_text(encoding="utf-8"))
        told = told if isinstance(told, dict) else {}
    except (OSError, ValueError):
        told = {}
    out: list[dict[str, Any]] = []
    changed = False
    for meter in short(doc):
        last = _finite((told.get(meter) or {}).get("sent_at")) if isinstance(told.get(meter), Mapping) else None
        if last is not None and 0 <= now - last < NOTICE_EVERY_SECONDS:
            out.append({"meter": meter, "sent": False, "why": f"told at {_iso(last)}: at most once every 7 days"})
            continue
        facts = notice_facts(doc, meter, now)
        if notify is None:
            out.append({"meter": meter, "sent": False, "why": "no gateway to notify through"})
            errors.append(f"funding notice for {meter} not sent: no gateway")
            continue
        try:
            answer = notify(facts)
        except Exception as exc:  # noqa: BLE001 - not told: the next run tries again
            out.append({"meter": meter, "sent": False, "why": f"the notice failed ({type(exc).__name__})"})
            errors.append(f"funding notice for {meter} failed ({type(exc).__name__})")
            continue
        if _sent(answer):
            told[meter] = {"sent_at": now, "notice_id": facts["notice_id"]}
            changed = True
            out.append({"meter": meter, "sent": True, "notice_id": facts["notice_id"]})
        else:
            reason = str((answer or {}).get("reason") or "the gateway did not send it")[:200] if isinstance(answer, Mapping) \
                else "the gateway did not send it"
            out.append({"meter": meter, "sent": False, "why": reason})
            errors.append(f"funding notice for {meter} not sent: {reason}")
    if changed:
        _write_json(path, told)
    return out


# ---------------------------------------------------------------------------------------------- the job
def _settings(root: Path, config: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        from league.swarm import settings as settings_mod

        return settings_mod.load(root, config=config)
    except Exception:  # noqa: BLE001 - the defaults' guard burn stands in
        return {}


def run(ctx: Any) -> dict[str, Any]:
    """The `budget` job (league/ops: after the close economics, and daily at 00:30 UTC). `ctx` gives `root` (the House's
    state root; or `state_root`, or `house.root`), and optionally `now` or `clock`, `config` (league/config.json),
    `sail` (a `SailboxClient`), `gateway_health` (a callable returning `/v1/health`'s JSON) and `notify` (a callable
    posting one notice's facts to `/v1/notify`); each one absent is built from the House's own config and environment.
    Writes `<root>/budget.json` and returns the receipt."""
    root, now, config = _root(ctx), _now(ctx), _config(ctx)
    errors: list[str] = []
    sail = _get(ctx, "sail")
    if sail is None:
        try:
            from league.sailbox import SailboxClient

            sail = SailboxClient()
        except Exception as exc:  # noqa: BLE001 - the configured burn stands in
            errors.append(f"no Sail client ({type(exc).__name__})")
    health = _get(ctx, "gateway_health") or _health_reader(config)
    notify = _get(ctx, "notify") or _notifier(config)
    inputs = gather(root, now, config=config, settings=_settings(root, config), sail=sail, health=health, errors=errors)
    try:
        previous = json.loads((root / BUDGET_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = None
    doc = compute(inputs, now=now, previous=previous if isinstance(previous, Mapping) else None)
    doc["errors"] = list(errors)
    _write_json(root / BUDGET_FILE, doc)
    notices = send_notices(doc, root, now, notify, errors)
    if notices:
        doc["notices"], doc["errors"] = notices, list(errors)
        _write_json(root / BUDGET_FILE, doc)
    return {"state": doc["state"], "direction": doc["direction"], "research_usd_day": doc["research_usd_day"],
            "earned_usd_day": doc["earned_usd_day"],
            "meters": {m: {k: doc["meters"][m].get(k) for k in ("research_usd_day", "limited_by", "runway_days", "card_date",
                                                               "direction")} for m in METERS},
            "notices": notices, "errors": errors, "warning": bool(errors)}


def drill(ctx: Any, meter: str = "sail") -> dict[str, Any]:
    """The funding drill (league/ops drills, monthly): (1) a synthetic cliff on `meter` (its balance 30 days of its fixed
    cost above the reserve) goes through `compute` and is sent as the real notice would be, with `test: true` and its
    own notice id; (2) the same meter with an unreadable balance must give no research. Writes nothing to budget.json
    or to the notices' record."""
    if meter not in METERS:
        raise ValueError(f"no meter {meter!r}")
    root, now, config = _root(ctx), _now(ctx), _config(ctx)
    fixed = 1.0
    synthetic = {"p30_usd": 0.0, "p30_source": "drill", "edge": {"stop": False, "why": "drill"},
                 "meters": {m: {"balance_usd": RESERVE_USD[m] + (30 * fixed if m == meter else 10_000.0),
                                "fixed_usd_day": fixed, "need_usd": 0.0} for m in METERS}}
    doc = compute(synthetic, now=now)
    unreadable = compute({**synthetic, "meters": {**synthetic["meters"], meter: {"balance_usd": None, "fixed_usd_day": fixed}}},
                         now=now)
    checks = {"cliff_seen": meter in short(doc),
              "unreadable_gives_no_research": unreadable["meters"][meter]["research_usd_day"] == 0.0}
    facts = notice_facts(doc, meter, now, test=True)
    notify = _get(ctx, "notify") or _notifier(config)
    answer, error = None, None
    if notify is None:
        error = "no gateway to notify through"
    else:
        try:
            answer = notify(facts)
        except Exception as exc:  # noqa: BLE001 - the drill's receipt says so
            error = f"{type(exc).__name__}"
    # Only a mail sent now counts for the drill: a `duplicate` answer proves nothing about the mail path today.
    sent = isinstance(answer, Mapping) and answer.get("sent") is True and answer.get("duplicate") is not True
    return {"drill": "funding", "meter": meter, "root": str(root), "checks": checks, "notice_id": facts["notice_id"],
            "sent": sent, "error": error, "ok": sent and all(checks.values())}


__all__ = ["compute", "knobs", "overlay", "read", "floor_block", "sail_caps", "edge_state", "book_p30", "gather",
           "notice_facts", "send_notices", "short", "run", "drill", "floor_usd_day", "METERS", "R_DAYS", "W_DAYS",
           "FLOOR_CAP_USD_DAY", "FLOOR_SPLIT", "PROFIT_SHARE", "RESERVE_USD", "EDGE_START", "EDGE_SESSIONS", "STALE_SECONDS",
           "BUDGET_FILE", "NOTICES_FILE"]
