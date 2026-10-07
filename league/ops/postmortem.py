"""The `postmortem` job (weekly, Saturday 14:00Z; GOAL 5.1): the week's receipts read by code, written up by Claude Opus
5.5, kept privately and summarized publicly; on the month's first Saturday also the cost review, which proposes the data
vendor decision (the owner's D6) on numbers.

THE WEEK is the seven days to the occurrence (`window`). Code reads it, read-only (`guard.readonly`), from the House's own
records (`facts`), each part on its own (one that cannot be read is named in `unread`, the others still count):

- real orders (`live.sqlite` `orders`, by when they were placed): by outcome and route, the venue's rejections and the
  refusals before the venue (the gateway's caps, the House's own) with their reasons, and the week's real fills;
- fills against the Gym: the D3 calibration round trips' real fills against the mid at submit (`calibration.sqlite`, the
  calibration report's own arithmetic: worse than the mid in ticks and in dollars a contract, the fill rate of ended
  attempts) beside the practice book's fills, which trade under the Gym's fill rules on the same live quotes
  (`observe.sqlite` `fill` receipts: slippage to the decision's mid a contract, the share filled at the natural), and
  the practice book's rejections;
- the band moves: demotions, promotions and retirements (`swarm.sqlite` `swarm.band` and `swarm.retired` events) and,
  once the forward ladder keeps its `ladder_decisions` table, its verdicts;
- what the engineer changed: the updater's self-deploys and their verdicts (`<base>/deploys.jsonl` through
  `updater.updater_ships`), the owner's deploys, and the engineer's journal (`<state>/harness/engineer.sqlite`) when it
  exists (`journal_counts`: rows of the week by state, whatever its tables are called);
- what it cost: the week's input costs by service and its realized options P&L from the close economics (the newest
  `<state>/economics/*-close/summary.json` at the week's end less the newest at its start, `cost_delta`), the swarm's
  model spend by kind and Claude's by role (`swarm.sqlite` `spend`), and the House's jobs (`ops.sqlite`).

THE COST REVIEW (`cost_review`, on the month's first Saturday; `ops.json` `postmortem.cost_review` "always" or "never"
overrides): the trailing 30 days' costs by service and the data vendor's share of them, research activity (Gym runs,
births), the research universe (the roots of the families alive, and those first traded in the 30 days), the forward
ladder's state, and a PROPOSAL by a rule fixed here (`propose`): the vendor's Standard plan stays until the forward ladder
is live and while the universe still moves; then a one-time purchase of the universe's history when it is inside
`CORE_ROOTS` and its price (`ops.json` `postmortem.one_time_price_usd`, the owner's) pays back within `PAYBACK_MONTHS` of
Standard, else the Value plan. A proposal only: the owner decides D6 (the vendor's license is a rental, so history it
supplied is deleted within 30 days of a cancel, and a cancel waits for its replacement).

THE MODEL (`narrate`): one call to Claude, role `postmortem` (`ROLE`), through the swarm's own `ModelRouter`, so the hold
and the settled cost are `spend` rows in `swarm.sqlite` like every role's and every line applies: the role's own daily
line (`claude.role_usd_day.postmortem`, $1 by default: one run a week, so it is the run's cap), the swarm's `usd_cap`,
the gateway's funded total, and LTCM v3's research budget when it is in force. The call's worst case is also checked
against `RUN_CAP_USD` before it is asked. The role's model is `claude.role_model.postmortem` (Claude Opus 5.5 by
default); `claude.roles` must name the role, as for any role. It may spend the swarm's `claude.reserve_usd`: that reserve
is kept for the House's post-mortem. It reads the week as aggregates, MODEL-SAFE (`prompt`, checked by `model_problems`:
ASCII, no family name, no Validation or holdout figure, no date): it answers a headline, findings and actions as JSON. A
week the model cannot be asked (not configured, no room, its line spent, an error) still gets its report: the facts and
the reason the narrative is missing. A rerun of the same week reuses the narrative already written
(`<state>/postmortem/<date>.json`): a week is paid for once.

OUTPUT. Private: `<state>/postmortem/<date>.md` (every table, the reasons, the narrative, the cost review) and
`<date>.json` (the facts, the review and the narrative), mode 0600. Public: `docs/runs/desk/<date>-postmortem.md` through
the gateway's docs route (`POST /v1/github/docs`), built from an allowlist of counts and dollar figures (`public_page`)
and checked by the scoreboard's public filter (`scoreboard.public_problems`; a page that fails is never posted, and the
job fails); the model's text joins it only when it passes the same filter and names no family, else it stays private and
the page says so. Until the docs route is deployed the run is `skipped`, with the page kept beside the report. Nothing
here feeds research: no swarm role reads the post-mortem.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from . import guard
from . import schedule as S
from .context import GatewayError, read_json, write_json, write_text

ROLE = "postmortem"
#: The run's own cap: a call whose worst case (the gateway's reservation for the exact request) is above it is not asked.
RUN_CAP_USD = 1.0
WEEK_SECONDS = 7 * 86400
REVIEW_DAYS = 30
DOCS_ROUTE = "/v1/github/docs"
PUBLIC_PATH = "docs/runs/desk/{day}-postmortem.md"
#: The model's prompt is cut to this many characters (its lists first), so its worst case stays well inside the cap.
PROMPT_MAX_CHARS = 24000
#: Each list in the facts keeps at most this many rows (the private report included).
LIST_MAX = 12
#: The data vendor's plans, dollars a month (ThetaData Options list prices, GOAL D6; Standard is what the desk pays and
#: what the close economics pro-rates, `league/publish.py` SUBSCRIPTIONS_MONTHLY_USD).
VENDOR_PLANS_USD_MONTH = {"standard": 80.0, "value": 40.0}
#: The roots a one-time history purchase is sized for (GOAL D6).
CORE_ROOTS = ("SPY", "QQQ", "XSP")
#: A one-time purchase is proposed only when it pays for itself within this many months of the Standard plan.
PAYBACK_MONTHS = 12
BAND_RANK = {"gym": 0, "candidate": 1, "probe": 2, "sized": 3}
NY = ZoneInfo("America/New_York")
UTC = timezone.utc

#: The model's answer (structured output).
SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "required": ["headline", "findings", "actions", "cost_note"],
    "properties": {
        "headline": {"type": "string"},
        "findings": {"type": "array", "items": {"type": "string"}},
        "actions": {"type": "array", "items": {"type": "string"}},
        "cost_note": {"type": "string"},
    },
}

SYSTEM = """You write the weekly post-mortem of an autonomous options desk. AI researchers write trading programs; a
simulator (the Gym) replays recorded one-minute option market data to train them and assumes how orders fill; a practice
book trades the promising programs on live market data under the Gym's own fill rules; a small real book trades the few
that earn it, and the House sends one-lot calibration round trips to measure real fills. An engineer agent ships harness
changes that an updater deploys, canaries and may roll back.

You get the week's receipts as aggregates computed by code. Judge the week only by these numbers:
1. FILLS: where the real fills differ from what the Gym assumes (real slippage against the midpoint versus the practice
   book's under the Gym's rules; fill rates by cell). Say which direction the Gym is wrong in and by how much a contract.
2. ORDERS: what the rejections and refusals say about the order path.
3. RESEARCH: what the demotions, retirements and harness changes say.
4. COST: whether what the week cost bought anything, against what it earned.
Then name at most three changes for next week, each tied to a number below and to how it would be measured. Never invent
a number; when the receipts do not measure something, say so.

Your answer may be published on a public page, so write it in words such a page can carry: plain ASCII, no program
names, no dates, no prices or contract names, and never the words bid, ask, mid, quote, NBBO, strike, equity, balance,
parameter, validation or holdout (say "the midpoint", "the market", "the fill price" instead).

Answer with one JSON object: {"headline": one sentence, "findings": two to six short sentences, "actions": one to three
short sentences, "cost_note": one or two sentences}."""


# ------------------------------------------------------------------------------------------------ the week
def window(due_at: float) -> tuple[float, float]:
    """The seven days to the occurrence: [start, end)."""
    return float(due_at) - WEEK_SECONDS, float(due_at)


def month_first(due_at: float) -> bool:
    """The occurrence falls in the first seven UTC days of its month (the month's first Saturday, for the weekly job)."""
    return datetime.fromtimestamp(float(due_at), UTC).day <= 7


def ny_day(moment: float) -> str:
    return datetime.fromtimestamp(float(moment), NY).date().isoformat()


def _number(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out not in (float("inf"), float("-inf")) else None


def _r(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(float(value), digits)


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _loads(text: Any) -> Any:
    try:
        return json.loads(text) if text else None
    except (TypeError, ValueError):
        return None


def _top(counter: Mapping[str, int], n: int = LIST_MAX) -> list[dict[str, Any]]:
    return [{"text": k, "n": v} for k, v in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]


def _tables(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(guard.read(path, lambda db: guard.ids(db, "SELECT name FROM sqlite_master WHERE type='table'")))


def _columns(path: Path, table: str) -> list[str]:
    return guard.read(path, lambda db: [r["name"] for r in guard.rows(db, f'PRAGMA table_info("{table}")')])


# ------------------------------------------------------------------------------------------------ the parts
def real_orders(root: Path, start: float, end: float) -> dict[str, Any]:
    """The real orders placed in [start, end): by outcome and by route (`economics.route_of`), the reasons the venue
    rejected or the gateway or the House refused (cut short, most frequent first), and the week's real fills."""
    from .economics import route_of

    path = root / "live.sqlite"
    if not path.exists():
        return {"absent": True}

    def read(db: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows = guard.rows(db, "SELECT instance, family, tuition, status, answer FROM orders WHERE placed_at>=? AND "
                              "placed_at<? ORDER BY oid LIMIT 20000", (start, end))
        fills = guard.rows(db, "SELECT count(*) AS n, COALESCE(sum(qty), 0) AS contracts, COALESCE(sum(fees), 0) AS fees "
                               "FROM fills WHERE at>=? AND at<?", (start, end))[0]
        return rows, fills

    rows, fills = guard.read(path, read)
    by_status: dict[str, int] = {}
    by_route: dict[str, dict[str, int]] = {}
    reasons: dict[str, int] = {}
    for row in rows:
        status = str(row["status"])
        by_status[status] = by_status.get(status, 0) + 1
        route = by_route.setdefault(route_of(row), {})
        route[status] = route.get(status, 0) + 1
        if status in ("rejected", "refused"):
            answer = _loads(row["answer"]) or {}
            why = answer.get("reject_reason") or answer.get("error") if isinstance(answer, dict) else None
            key = f"{'venue' if status == 'rejected' else 'before the venue'}: {str(why or 'no reason given')[:200]}"
            reasons[key] = reasons.get(key, 0) + 1
    ended = sum(by_status.get(s, 0) for s in ("filled", "cancelled", "expired", "rejected"))
    return {"placed": len(rows), "by_status": by_status, "by_route": by_route,
            "fill_rate": _r(by_status.get("filled", 0) / ended, 4) if ended else None,
            "rejected": by_status.get("rejected", 0), "refused": by_status.get("refused", 0), "reasons": _top(reasons),
            "fills": {"n": int(fills["n"]), "contracts": int(fills["contracts"]), "fees_usd": _r(_number(fills["fees"]))}}


def calibration_fills(root: Path, start: float, end: float) -> dict[str, Any]:
    """The D3 calibration attempts submitted in [start, end), by cell: attempts, ended, filled (with partials), fill rate
    and mean fill worse than the mid at submit, in ticks and in dollars a contract (the calibration report's arithmetic,
    `league/live/calibration.py` `report`: an open paying more, or a close getting less, than the mid is worse)."""
    from ..gym.venue import MULTIPLIER
    from ..live.calibration import COUNTED, TICK

    path = root / "calibration.sqlite"
    if not path.exists():
        return {"absent": True}
    rows = guard.read(path, lambda db: guard.rows(
        db, "SELECT cell, action, outcome, fill_value, mid FROM samples WHERE submitted_at>=? AND submitted_at<? "
            "ORDER BY oid LIMIT 20000", (start, end)))
    cells: dict[str, dict[str, Any]] = {}
    worse_all: list[float] = []
    for row in rows:
        c = cells.setdefault(str(row["cell"]), {"attempts": 0, "ended": 0, "filled": 0, "_worse": []})
        c["attempts"] += 1
        outcome = row["outcome"]
        if outcome in COUNTED:
            c["ended"] += 1
        fill, mid = _number(row["fill_value"]), _number(row["mid"])
        if outcome in ("filled", "partial"):
            c["filled"] += 1
            if fill is not None and mid is not None:
                worse = (fill - mid) if row["action"] == "open" else (mid - fill)
                c["_worse"].append(worse)
                worse_all.append(worse)
    out = {}
    for cell, c in sorted(cells.items()):
        worse = c.pop("_worse")
        mean = _mean(worse)
        out[cell] = {**c, "fill_rate": _r(c["filled"] / c["ended"], 4) if c["ended"] else None,
                     "mean_worse_ticks": _r(mean / TICK, 3) if mean is not None else None,
                     "mean_worse_usd_per_contract": _r(mean * MULTIPLIER, 2) if mean is not None else None}
    mean = _mean(worse_all)
    return {"attempts": len(rows), "fills": len(worse_all), "cells": out,
            "mean_worse_usd_per_contract": _r(mean * MULTIPLIER, 2) if mean is not None else None}


def practice_fills(root: Path, start: float, end: float) -> dict[str, Any]:
    """The practice book's receipts of the session days in [start, end) (`observe.sqlite` `events`): its orders, fills
    and rejections; each fill's slippage to the decision's mid a contract (the shadow's own figure,
    `slippage_to_decision_mid_usd` / quantity), by open and close, and the share filled at the natural."""
    path = root / "observe.sqlite"
    if not path.exists():
        return {"absent": True}
    first, last = ny_day(start), ny_day(end)

    def read(db: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        counts = guard.rows(db, "SELECT kind, count(*) AS n FROM events WHERE day>=? AND day<? AND kind IN "
                                "('order', 'fill', 'rejected', 'order_end') GROUP BY kind", (first, last))
        bodies = guard.rows(db, "SELECT kind, body FROM events WHERE day>=? AND day<? AND kind IN ('fill', 'rejected') "
                                "LIMIT 20000", (first, last))
        return counts, bodies

    counts, bodies = guard.read(path, read)
    by_kind = {r["kind"]: int(r["n"]) for r in counts}
    slip: dict[str, list[float]] = {"open": [], "close": []}
    natural, priced = 0, 0
    reasons: dict[str, int] = {}
    for row in bodies:
        body = _loads(row["body"]) or {}
        if row["kind"] == "rejected":
            key = str(body.get("reason") or "no reason given")[:200]
            reasons[key] = reasons.get(key, 0) + 1
            continue
        qty, usd = _number(body.get("quantity")), _number(body.get("slippage_to_decision_mid_usd"))
        side = "open" if body.get("action") == "open" else "close"
        if qty and usd is not None:
            slip[side].append(usd / qty)
        price, nat = _number(body.get("price")), _number(body.get("decision_natural"))
        if price is not None and nat is not None:
            priced += 1
            natural += abs(price - nat) < 0.005
    every = slip["open"] + slip["close"]
    return {"orders": by_kind.get("order", 0), "fills": by_kind.get("fill", 0), "rejected": by_kind.get("rejected", 0),
            "slippage_usd_per_contract": {"all": _r(_mean(every)), "open": _r(_mean(slip["open"])),
                                          "close": _r(_mean(slip["close"]))},
            "share_at_natural": _r(natural / priced, 4) if priced else None, "reasons": _top(reasons)}


def band_moves(root: Path, start: float, end: float) -> dict[str, Any]:
    """The week's band moves (`swarm.band`: a demotion moves down `BAND_RANK`, a promotion up; a move to `retired` is a
    retirement) and retirements (`swarm.retired`), with the families and reasons (private)."""
    path = root / "swarm.sqlite"
    if not path.exists():
        return {"absent": True}
    rows = guard.read(path, lambda db: guard.rows(
        db, "SELECT at, kind, family, payload FROM events WHERE kind IN ('swarm.band', 'swarm.retired') AND at>=? AND at<? "
            "ORDER BY seq LIMIT 5000", (S.iso(start), S.iso(end))))
    demotions, promotions, retirements = [], [], []
    moves: dict[str, int] = {}
    for row in rows:
        payload = _loads(row["payload"]) or {}
        if row["kind"] == "swarm.retired":
            retirements.append({"family": row["family"], "from": payload.get("band_from"),
                                "why": str(payload.get("cause") or "")[:200]})
            continue
        was, now = payload.get("band_from"), payload.get("band_to")
        if was not in BAND_RANK or now not in BAND_RANK:
            continue
        entry = {"family": row["family"], "from": was, "to": now, "why": str(payload.get("reason") or "")[:200]}
        (demotions if BAND_RANK[now] < BAND_RANK[was] else promotions).append(entry)
        moves[f"{was} -> {now}"] = moves.get(f"{was} -> {now}", 0) + 1
    return {"demotions": len(demotions), "promotions": len(promotions), "retirements": len(retirements), "moves": moves,
            "demoted": demotions[:LIST_MAX], "promoted": promotions[:LIST_MAX], "retired": retirements[:LIST_MAX]}


TIME_COLUMNS = ("at", "decided_at", "created_at", "opened_at", "started_at", "updated_at", "recorded_at")
STATE_COLUMNS = ("verdict", "status", "outcome", "state", "decision")


def journal_counts(path: Path, start: float, end: float, *, tables: Iterable[str] | None = None) -> dict[str, Any]:
    """{table: {state: rows}} of a journal's rows in [start, end), for every table (or those named) that has a time column
    (`TIME_COLUMNS`: epoch seconds or ISO text both read) and a state column (`STATE_COLUMNS`); a table without them is
    left out. Read whatever the journal's owner called its tables: this job never writes them."""
    if not path.exists():
        return {}
    names = _tables(path) if tables is None else set(tables) & _tables(path)
    out: dict[str, Any] = {}
    for table in sorted(names):
        columns = _columns(path, table)
        when = next((c for c in TIME_COLUMNS if c in columns), None)
        state = next((c for c in STATE_COLUMNS if c in columns), None)
        if when is None or state is None:
            continue
        rows = guard.read(path, lambda db: guard.rows(
            db, f'SELECT "{state}" AS state, count(*) AS n FROM "{table}" WHERE (typeof("{when}") IN (\'integer\', \'real\') '
                f'AND "{when}">=? AND "{when}"<?) OR (typeof("{when}")=\'text\' AND "{when}">=? AND "{when}"<?) '
                f'GROUP BY "{state}"', (start, end, S.iso(start), S.iso(end))))
        out[table] = {str(r["state"]): int(r["n"]) for r in rows}
    return out


def harness_changes(root: Path, base: Path, start: float, end: float) -> dict[str, Any]:
    """The updater's self-deploys whose House restart fell in the week (`updater.updater_ships`: promoted, rolled back,
    in flight), the owner's deploys' verdicts, and the engineer's journal when it exists."""
    from ..updater import updater_ships

    history: list[dict[str, Any]] = []
    try:
        with (base / "deploys.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    history.append(row)
    except OSError:
        pass
    ships = [s for s in updater_ships(history) if start <= float(s.get("ts") or 0) < end]
    verdicts: dict[str, int] = {}
    for ship in ships:
        verdicts[str(ship["verdict"])] = verdicts.get(str(ship["verdict"]), 0) + 1
    owner: dict[str, int] = {}
    for row in history:
        at = S.epoch(row.get("at"))
        if row.get("stage") == "verdict" and not row.get("sha") and at is not None and start <= at < end:
            owner[str(row.get("verdict"))] = owner.get(str(row.get("verdict")), 0) + 1
    return {"self_deploys": verdicts, "releases": [{"release": s.get("release"), "sha": str(s.get("sha") or "")[:12],
                                                    "verdict": s.get("verdict")} for s in ships[:LIST_MAX]],
            "owner_deploys": owner, "engineer": journal_counts(root / "harness" / "engineer.sqlite", start, end)}


def ladder_verdicts(root: Path, start: float, end: float) -> dict[str, Any]:
    """The forward ladder's verdicts of the week (`ladder_decisions`, wherever it lives), or {} before it exists."""
    out: dict[str, Any] = {}
    for name in ("observe.sqlite", "swarm.sqlite", "ladder.sqlite"):
        found = journal_counts(root / name, start, end, tables=("ladder_decisions",))
        for state, n in (found.get("ladder_decisions") or {}).items():
            out[state] = out.get(state, 0) + n
    return out


def job_runs(root: Path, start: float, end: float) -> dict[str, Any]:
    from .store import read_runs

    rows = read_runs(root, S.iso(start), S.iso(end))
    by_status: dict[str, int] = {}
    failed: dict[str, int] = {}
    missed: dict[str, int] = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
        if row["status"] in ("failed", "missed"):
            bucket = failed if row["status"] == "failed" else missed
            bucket[row["job"]] = bucket.get(row["job"], 0) + 1
    return {"by_status": by_status, "failed": failed, "missed": missed}


def spend(root: Path, start: float, end: float) -> dict[str, Any]:
    """The swarm's booked model spend in [start, end) by kind, and Claude's by role (holds and their settlements)."""
    path = root / "swarm.sqlite"
    if not path.exists():
        return {"absent": True}

    def read(db: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        kinds = guard.rows(db, "SELECT kind, count(*) AS n, COALESCE(sum(usd), 0) AS usd FROM spend WHERE epoch>=? AND "
                               "epoch<? GROUP BY kind", (start, end))
        claude = guard.rows(db, "SELECT usd, detail FROM spend WHERE kind='claude' AND epoch>=? AND epoch<? LIMIT 50000",
                            (start, end))
        return kinds, claude

    kinds, claude = guard.read(path, read)
    roles: dict[str, float] = {}
    for row in claude:
        role = str((_loads(row["detail"]) or {}).get("role") or "unnamed")
        roles[role] = roles.get(role, 0.0) + float(row["usd"] or 0)
    return {"by_kind": {r["kind"]: _r(_number(r["usd"]), 4) for r in kinds},
            "claude_by_role": {k: _r(v, 4) for k, v in sorted(roles.items())}}


def family_ids(root: Path) -> set[str]:
    """Every family's id (retired ones too): the names the model's prompt and the public page may not carry."""
    path = root / "swarm.sqlite"
    if not path.exists():
        return set()
    return {str(f) for f in guard.read(path, lambda db: guard.ids(db, "SELECT id FROM families")) if f}


# ------------------------------------------------------------------------------------------------ the costs
def _summaries(root: Path) -> list[Path]:
    try:
        return sorted(p / "summary.json" for p in (root / "economics").iterdir() if p.is_dir() and p.name.endswith("-close"))
    except OSError:
        return []


def summary_at(root: Path, moment: float, *, earliest: bool = False) -> dict[str, Any] | None:
    """The newest close economics whose cutoff is at or before `moment` (or, `earliest`, the oldest one after it)."""
    from .economics import ep

    paths = _summaries(root)
    for path in (paths if earliest else reversed(paths)):
        value = read_json(path, None)
        if not isinstance(value, dict) or not value.get("cutoff"):
            continue
        at = ep(value["cutoff"])
        if (at > moment) if earliest else (at <= moment):
            return value
    return None


def cost_delta(root: Path, start: float, end: float) -> dict[str, Any]:
    """Input costs by service and realized options P&L between two close economics: the newest at `end` less the newest
    at `start` (or, before any, T0's zero when the span reaches back to T0; else the oldest inside the span, `partial`).
    Realized P&L is its close days' rows after the first cutoff's New York day (`realized.by_close_day`, regulatory fees
    by posting day)."""
    from .economics import D, T0, ep, usd

    after = summary_at(root, end)
    if after is None:
        return {"available": False, "why": "no close economics at the end of the span"}
    before = summary_at(root, start)
    partial = False
    if before is None and start > ep(T0):
        before = summary_at(root, start, earliest=True)
        partial = True
        if before is None or before.get("cutoff") == after.get("cutoff"):
            return {"available": False, "why": "one close economics in the span: nothing to difference"}
    first = ep(before["cutoff"]) if before is not None else ep(T0)
    then = {str(c.get("service")): D(c.get("usd")) for c in (before or {}).get("costs") or []}
    rows = [{"service": str(c.get("service")), "usd": usd(D(c.get("usd")) - then.get(str(c.get("service")), D(0)))}
            for c in after.get("costs") or []]
    total = sum((D(r["usd"]) for r in rows), D(0))
    from_day = ny_day(first) if before is not None else ""
    to_day = ny_day(ep(after["cutoff"]))
    days = [d for d in (after.get("realized") or {}).get("by_close_day") or [] if from_day < str(d.get("day")) <= to_day]
    realized = sum((D(d.get("total_usd")) for d in days), D(0))
    return {"available": True, "partial": partial, "from": before["cutoff"] if before is not None else T0,
            "to": after["cutoff"], "span_days": round((ep(after["cutoff"]) - first) / 86400, 2), "by_service": rows,
            "total_usd": usd(total), "realized_options_pnl_usd": usd(realized), "net_usd": usd(realized - total),
            "closed_positions": sum(int(d.get("closed_positions") or 0) for d in days), "p30": after.get("p30")}


# ------------------------------------------------------------------------------------------------ the facts
def facts(root: str | Path, base: str | Path, start: float, end: float) -> dict[str, Any]:
    """The week's receipts (the module docstring), read-only; a part that cannot be read is in `unread`."""
    root, base = Path(root), Path(base)
    parts: tuple[tuple[str, Callable[[], Any]], ...] = (
        ("orders", lambda: real_orders(root, start, end)),
        ("calibration", lambda: calibration_fills(root, start, end)),
        ("practice", lambda: practice_fills(root, start, end)),
        ("bands", lambda: band_moves(root, start, end)),
        ("ladder", lambda: ladder_verdicts(root, start, end)),
        ("harness", lambda: harness_changes(root, base, start, end)),
        ("jobs", lambda: job_runs(root, start, end)),
        ("spend", lambda: spend(root, start, end)),
        ("costs", lambda: cost_delta(root, start, end)),
    )
    out: dict[str, Any] = {"from": S.iso(start), "to": S.iso(end), "unread": {}}
    with guard.readonly():
        for name, part in parts:
            try:
                out[name] = part()
            except Exception as exc:  # noqa: BLE001 - one part that cannot be read leaves the others
                out[name] = None
                out["unread"][name] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return out


# ------------------------------------------------------------------------------------------------ the cost review
def research_activity(root: Path, start: float, end: float) -> dict[str, Any]:
    """Gym runs and births in [start, end), the roots of the families alive now (the universe), and the roots first
    traded by a family born in the span (`new_roots`: no family born before the span traded them)."""
    path = root / "swarm.sqlite"
    if not path.exists():
        return {"absent": True}

    def read(db: Any) -> tuple[int, list[dict[str, Any]]]:
        runs = guard.ids(db, "SELECT count(*) FROM runs WHERE at>=? AND at<?", (S.iso(start), S.iso(end)))[0]
        fams = guard.rows(db, "SELECT roots, born_at, retired_at FROM families")
        return runs, fams

    runs, fams = guard.read(path, read)

    def roots(row: Mapping[str, Any]) -> set[str]:
        value = _loads(row["roots"])
        return {str(r).upper() for r in value} if isinstance(value, list) else set()

    born = [f for f in fams if S.iso(start) <= str(f["born_at"]) < S.iso(end)]
    before: set[str] = set().union(*(roots(f) for f in fams if str(f["born_at"]) < S.iso(start)))
    span: set[str] = set().union(*(roots(f) for f in born))
    universe: set[str] = set().union(*(roots(f) for f in fams if not f["retired_at"]))
    return {"gym_runs": int(runs), "births": len(born), "universe": sorted(universe), "new_roots": sorted(span - before)}


def propose(*, ladder_live: bool, new_roots: Sequence[str], universe: Sequence[str],
            price_usd: float | None) -> dict[str, Any]:
    """The D6 proposal by the rule in the module docstring: {decision, why, saves_usd_month, payback_months}."""
    standard, value = VENDOR_PLANS_USD_MONTH["standard"], VENDOR_PLANS_USD_MONTH["value"]
    keep = {"decision": "keep_standard", "saves_usd_month": 0.0, "payback_months": None}
    if not ladder_live:
        return {**keep, "why": "D6 keeps the Standard plan until the forward ladder is live, and it has no entrant yet"}
    if new_roots:
        return {**keep, "why": f"the research universe still moves: {len(new_roots)} root(s) first traded in the last "
                               f"{REVIEW_DAYS} days"}
    if not universe:
        return {**keep, "why": "no family is alive, so there is no universe to size the data to"}
    core = set(universe) <= set(CORE_ROOTS)
    if core and price_usd is not None and price_usd > 0 and price_usd / standard <= PAYBACK_MONTHS:
        return {"decision": "one_time_purchase", "saves_usd_month": standard, "payback_months": round(price_usd / standard, 1),
                "why": f"the universe ({', '.join(universe)}) is fixed inside the core roots and a one-time purchase of its "
                       f"history pays back in {price_usd / standard:.1f} months of the Standard plan; the rental's data is "
                       "deleted within 30 days of a cancel, so cancel only once the purchase is in the Gym's store"}
    why = f"the universe ({', '.join(universe)}) is fixed; the Value plan saves {standard - value:.0f} USD a month"
    if core:
        why += ("; a one-time purchase of its history has no price yet (ops.json postmortem.one_time_price_usd)"
                if price_usd is None else f"; the one-time price pays back only after {price_usd / standard:.1f} months")
    return {"decision": "drop_to_value", "saves_usd_month": standard - value, "payback_months": None, "why": why}


def cost_review(root: str | Path, end: float, *, price_usd: float | None = None) -> dict[str, Any]:
    """The monthly cost review (the module docstring): its numbers and the proposal."""
    from .scoreboard import ladder_counts

    root = Path(root)
    start = end - REVIEW_DAYS * 86400
    out: dict[str, Any] = {"days": REVIEW_DAYS, "unread": {}}
    with guard.readonly():
        for name, part in (("costs", lambda: cost_delta(root, start, end)),
                           ("research", lambda: research_activity(root, start, end)),
                           ("ladder", lambda: ladder_counts(root, end))):
            try:
                out[name] = part()
            except Exception as exc:  # noqa: BLE001
                out[name] = None
                out["unread"][name] = f"{type(exc).__name__}: {str(exc)[:200]}"
    costs = out.get("costs") or {}
    vendor = next((r for r in costs.get("by_service") or [] if str(r["service"]).startswith("ThetaData")), None)
    total = _number(costs.get("total_usd"))
    out["vendor"] = {"plan": "standard", "plans_usd_month": dict(VENDOR_PLANS_USD_MONTH),
                     "usd": vendor["usd"] if vendor else None,
                     "share_of_costs": _r(_number(vendor["usd"]) / total, 4) if vendor and total else None}
    entrants = (out.get("ladder") or {}).get("entrants")
    research = out.get("research") or {}
    out["proposal"] = propose(ladder_live=isinstance(entrants, int) and entrants > 0,
                              new_roots=research.get("new_roots") or [], universe=research.get("universe") or [],
                              price_usd=price_usd)
    return out


# ------------------------------------------------------------------------------------------------ the model
_OCC = re.compile(r"\b[A-Z]{1,6}\d{6}[CP]\d{8}\b")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ][0-9:.]+Z?)?\b|\b\d{8}T\d{6}Z\b")
_LATE_YEAR = re.compile(r"(?<![0-9.$])20(?:2[5-9]|[3-9][0-9])(?![0-9.])")
_LONG_ID = re.compile(r"\b[A-Za-z0-9_-]{24,}\b")
_HELD_OUT = re.compile(r"\b(?:validation|holdout|held[- ]out)\b", re.I)
#: A calibration cell's offset ("mid", "mid+1", "mid25") as the model reads it ("midpoint", ...): the public vocabulary.
_MID = re.compile(r"\bmid(?!point)")


def _family_pattern(names: Iterable[str]) -> re.Pattern[str] | None:
    """Family ids as whole words, case-insensitive: the generated ones (a slug of four characters or more with a hyphen or
    a digit, `SwarmStore.unique_id`). A one-word id is an ordinary word ("condor") that names nothing on its own, and
    matching it would withhold every page that uses the word."""
    names = sorted({n for n in names if len(n) >= 4 and re.search(r"[-0-9]", n)}, key=len, reverse=True)
    if not names:
        return None
    return re.compile(r"(?<![A-Za-z0-9_-])(?:" + "|".join(re.escape(n) for n in names) + r")(?![A-Za-z0-9_-])", re.I)


def scrub(text: Any, families: Iterable[str] = (), *, limit: int = 160) -> str:
    """A receipt's free text made model-safe: contract symbols, dates, long ids and family names replaced, ASCII, cut."""
    out = str(text or "")
    pattern = _family_pattern(families)
    if pattern is not None:
        out = pattern.sub("<program>", out)
    out = _OCC.sub("<contract>", out)
    out = _DATE.sub("<date>", out)
    out = _LATE_YEAR.sub("<year>", out)
    out = _LONG_ID.sub("<id>", out)
    out = _HELD_OUT.sub("<withheld>", out)
    out = out.encode("ascii", "replace").decode("ascii")
    return " ".join(out.split())[:limit]


def model_problems(text: str, families: Iterable[str] = ()) -> list[str]:
    """What in a model's prompt is not model-safe (empty when it is). A bare year is not checked here: a count of the
    week can read like one, and the free text that could carry a year went through `scrub`."""
    problems = []
    if not text.isascii():
        problems.append("non-ASCII text")
    pattern = _family_pattern(families)
    if pattern is not None and pattern.search(text):
        problems.append("a family name")
    if _HELD_OUT.search(text):
        problems.append("a Validation or holdout figure")
    if _DATE.search(text):
        problems.append("a date")
    if _OCC.search(text):
        problems.append("an option contract symbol")
    return problems


def _kv(mapping: Mapping[str, Any] | None, families: Iterable[str] | None = None) -> str:
    """`a 1, b 2` (sorted), or "none"; with `families`, each key scrubbed (keys a table the job does not own supplied)."""
    items = sorted((mapping or {}).items())
    return ", ".join(f"{k if families is None else scrub(k, families, limit=60)} {v}" for k, v in items) or "none"


def prompt(week: Mapping[str, Any], review: Mapping[str, Any] | None, families: Iterable[str] = ()) -> str:
    """The week's facts as the model reads them: aggregates only, the free text scrubbed (`scrub`), no dates."""
    families = set(families)
    o, c, p = week.get("orders") or {}, week.get("calibration") or {}, week.get("practice") or {}
    b, h, j = week.get("bands") or {}, week.get("harness") or {}, week.get("jobs") or {}
    sp, costs = week.get("spend") or {}, week.get("costs") or {}
    lines = ["THE WEEK: the seven days to this run.", ""]
    if o.get("absent"):
        lines += ["REAL ORDERS: no real book on this House.", ""]
    else:
        lines += [f"REAL ORDERS: placed {o.get('placed', 0)}; by outcome: {_kv(o.get('by_status'))}; fill rate of ended "
                  f"orders {o.get('fill_rate')}; real fills {((o.get('fills') or {}).get('n'))} "
                  f"({((o.get('fills') or {}).get('contracts'))} contracts, fees {((o.get('fills') or {}).get('fees_usd'))} USD).",
                  "By route: " + "; ".join(f"{route}: {_kv(v)}" for route, v in sorted((o.get("by_route") or {}).items())) + "."]
        if o.get("reasons"):
            lines += ["Rejections and refusals (count: reason):"]
            lines += [f"- {r['n']}: {scrub(r['text'], families)}" for r in o["reasons"][:8]]
        lines.append("")
    if c.get("absent"):
        lines += ["REAL FILLS AGAINST THE MIDPOINT (calibration round trips): none recorded.", ""]
    else:
        lines += [f"REAL FILLS AGAINST THE MIDPOINT (the House's one-lot calibration round trips): {c.get('attempts', 0)} attempts, "
                  f"{c.get('fills', 0)} fills, mean {c.get('mean_worse_usd_per_contract')} USD a contract worse than the midpoint. "
                  "By cell (symbol:action:offset): attempts, ended, filled, fill rate, ticks worse than the midpoint, USD a "
                  "contract:"]
        lines += [f"- {_MID.sub('midpoint', cell)}: {v['attempts']}, {v['ended']}, {v['filled']}, {v['fill_rate']}, {v['mean_worse_ticks']}, "
                  f"{v['mean_worse_usd_per_contract']}" for cell, v in list((c.get("cells") or {}).items())[:16]]
        lines.append("")
    if p.get("absent"):
        lines += ["PRACTICE FILLS (the Gym's fill rules on live market data): no practice record.", ""]
    else:
        s = p.get("slippage_usd_per_contract") or {}
        lines += [f"PRACTICE FILLS (the Gym's fill rules on the same live market data): orders {p.get('orders')}, fills "
                  f"{p.get('fills')}, rejections {p.get('rejected')}; slippage to the decision's midpoint, USD a contract: all "
                  f"{s.get('all')}, opens {s.get('open')}, closes {s.get('close')}; share filled at the natural "
                  f"{p.get('share_at_natural')}."]
        if p.get("reasons"):
            lines += ["Practice rejections (count: reason):"]
            lines += [f"- {r['n']}: {scrub(r['text'], families)}" for r in p["reasons"][:6]]
        lines.append("")
    if not b.get("absent"):
        lines += [f"BAND MOVES: demotions {b.get('demotions', 0)}, promotions {b.get('promotions', 0)}, retirements "
                  f"{b.get('retirements', 0)}; moves: {_kv(b.get('moves'))}."]
        reasons = [scrub(m["why"], families) for m in (b.get("demoted") or [])[:6] if m.get("why")]
        lines += [f"- demoted because: {r}" for r in reasons]
        lines.append("")
    if week.get("ladder"):
        lines += [f"THE FORWARD LADDER'S VERDICTS: {_kv(week['ladder'], families)}.", ""]
    engineer = "; ".join(_kv(v, families) for _, v in sorted((h.get("engineer") or {}).items())) or "no journal"
    lines += [f"HARNESS CHANGES: self-deployed releases by verdict: {_kv(h.get('self_deploys'))}; owner deploys by verdict: "
              f"{_kv(h.get('owner_deploys'))}; the engineer's journal, rows by state: {engineer}.", "",
              f"THE HOUSE'S JOBS: {_kv(j.get('by_status'))}; failed: {_kv(j.get('failed'))}; missed: {_kv(j.get('missed'))}.", ""]
    if costs.get("available"):
        lines += [f"COSTS OF THE WEEK (USD, over {costs.get('span_days')} days{', partial' if costs.get('partial') else ''}): "
                  + "; ".join(f"{scrub(r['service'], families, limit=60)} {r['usd']}" for r in costs.get("by_service") or [])
                  + f"; total {costs.get('total_usd')}. Realized options P&L {costs.get('realized_options_pnl_usd')} over "
                  f"{costs.get('closed_positions')} closes; the week's net {costs.get('net_usd')}."]
    else:
        lines += [f"COSTS OF THE WEEK: not measured ({costs.get('why') or 'no close economics'})."]
    lines += [f"Model spend booked by the swarm (USD): {_kv(sp.get('by_kind'))}; Claude by role: {_kv(sp.get('claude_by_role'))}.", ""]
    if week.get("unread"):
        lines += ["NOT READ THIS WEEK: " + ", ".join(sorted(week["unread"])) + ".", ""]
    if review:
        rc, rr, pr = review.get("costs") or {}, review.get("research") or {}, review.get("proposal") or {}
        lines += [f"THE MONTHLY COST REVIEW ({review.get('days')} days): total costs {rc.get('total_usd')} USD; realized "
                  f"options P&L {rc.get('realized_options_pnl_usd')}; the data vendor {(review.get('vendor') or {}).get('usd')} "
                  f"USD ({(review.get('vendor') or {}).get('share_of_costs')} of costs); Gym runs {rr.get('gym_runs')}; births "
                  f"{rr.get('births')}; roots alive {', '.join(rr.get('universe') or []) or 'none'}; roots first traded "
                  f"{', '.join(rr.get('new_roots') or []) or 'none'}. The rule proposes: {pr.get('decision')} "
                  f"({scrub(pr.get('why'), families, limit=400)}).", ""]
    text = "\n".join(lines)
    return text if len(text) <= PROMPT_MAX_CHARS else text[:PROMPT_MAX_CHARS - 40] + "\n[cut at the prompt's length cap]"


def router_for(ctx: Any, store: Any, *, claude_factory: Callable[[str], Any] | None = None, claude_meter: Any = None) -> Any:
    """The swarm's `ModelRouter` for this job: the swarm's settings from the state root (with the research budget, when
    it is in force), no Sail and no OpenAI route, and `claude.reserve_usd` 0 (the reserve is kept for this job). The
    gateway's Claude client and meter come from `league/config.json` `gateway_url` and `GATEWAY_TOKEN` unless given."""
    from ..swarm import settings as settings_mod
    from ..swarm.models import ModelRouter

    settings = settings_mod.load(ctx.root, config=ctx.config)
    claude = dict(settings.get("claude") or {})
    claude["reserve_usd"] = 0.0
    settings["claude"] = claude
    url = str(ctx.config.get("gateway_url") or "")
    if claude_factory is None and url:
        from ..claude import Claude, ClaudeMeter
        from .context import token_from_env

        claude_factory = lambda model: Claude(url, token_from_env, model=model, timeout=600.0)  # noqa: E731
        claude_meter = claude_meter or ClaudeMeter(url, token_from_env, ttl=120.0)
    return ModelRouter(store, None, settings=settings, claude_factory=claude_factory, claude_meter=claude_meter)


def _clean_answer(data: Any) -> dict[str, Any] | None:
    """The model's JSON, kept to its shape: ASCII strings, at most six findings and three actions, each cut short."""
    if not isinstance(data, Mapping):
        return None

    def text(value: Any, limit: int = 500) -> str:
        return " ".join(str(value or "").encode("ascii", "replace").decode("ascii").split())[:limit]

    findings = [text(f) for f in data.get("findings") or [] if text(f)][:6]
    actions = [text(a) for a in data.get("actions") or [] if text(a)][:3]
    headline = text(data.get("headline"), 300)
    if not headline and not findings:
        return None
    return {"headline": headline, "findings": findings, "actions": actions, "cost_note": text(data.get("cost_note"), 500)}


def narrate(ctx: Any, week: Mapping[str, Any], review: Mapping[str, Any] | None, families: Iterable[str], *,
            key: str, claude_factory: Callable[[str], Any] | None = None, claude_meter: Any = None) -> dict[str, Any]:
    """One Claude call through the router (the module docstring): {"answer", "route", "model", "cost_usd", ...}, or
    {"missing": why} when it was not asked or gave nothing."""
    from ..swarm.models import ModelError
    from ..swarm.store import SwarmStore

    families = set(families)
    user = prompt(week, review, families)
    problems = model_problems(user, families)  # the facts; SYSTEM is fixed text (it names the words a public page refuses)
    if problems:
        return {"missing": "the prompt is not model-safe (" + ", ".join(problems) + "); the model was not asked"}
    if not (Path(ctx.root) / "swarm.sqlite").exists():
        return {"missing": "no swarm store to book the call in; the model was not asked"}
    try:
        store = SwarmStore(ctx.root, clock=ctx.clock)
    except Exception as exc:  # noqa: BLE001 - a store that cannot be opened books nothing: the model is not asked
        return {"missing": f"the swarm store could not be opened ({type(exc).__name__}); the model was not asked"}
    try:
        router = router_for(ctx, store, claude_factory=claude_factory, claude_meter=claude_meter)
        if not router.claude_enabled(ROLE):
            return {"missing": f"Claude does not serve the {ROLE} role (claude.roles, a gateway and its token)"}
        _, ceiling = router.claude_request(SYSTEM, user, schema=SCHEMA, role=ROLE)
        if ceiling > RUN_CAP_USD:
            return {"missing": f"the call's worst case {ceiling:.2f} USD is over the run's cap of {RUN_CAP_USD:.2f}; not asked"}
        result = router.ask(role=ROLE, system=SYSTEM, user=user, family=None, key=key, openai_model=None,
                            sail_profile=None, need_usd=0.0, claude=True, schema=SCHEMA)
    except ModelError as exc:
        return {"missing": f"Claude gave no answer: {str(exc)[:300]}"}
    except Exception as exc:  # noqa: BLE001 - the router's own failure: the week's report is written without a narrative
        return {"missing": f"the call could not be made ({type(exc).__name__}: {str(exc)[:200]})"}
    finally:
        store.close()
    answer = _clean_answer(result.get("json"))
    if answer is None:
        return {"missing": "Claude's answer had no headline or findings", "route": result.get("route"),
                "model": result.get("model"), "cost_usd": result.get("cost_usd")}
    return {"answer": answer, "route": result.get("route"), "model": result.get("model"), "cost_usd": result.get("cost_usd"),
            "held_usd": result.get("held_usd"), "worst_case_usd": round(ceiling, 4), "prompt_chars": len(user)}


# ------------------------------------------------------------------------------------------------ the pages
def _table(head: Sequence[str], rows: Iterable[Sequence[Any]]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join("n/a" if v is None else str(v) for v in row) + " |" for row in rows]
    return out


def private_report(day: str, week: Mapping[str, Any], review: Mapping[str, Any] | None, narrative: Mapping[str, Any],
                   *, written_at: str) -> str:
    """The private report: every table, the reasons as they were recorded, the families by name, the narrative."""
    o, c, p = week.get("orders") or {}, week.get("calibration") or {}, week.get("practice") or {}
    b, h, j = week.get("bands") or {}, week.get("harness") or {}, week.get("jobs") or {}
    sp, costs = week.get("spend") or {}, week.get("costs") or {}
    lines = [f"# Post-mortem, the week to {day} (private)", "",
             f"Written by the House at {written_at} for {week.get('from')} to {week.get('to')}.", ""]
    answer = narrative.get("answer")
    lines += ["## The reading", ""]
    if answer:
        lines += [f"**{answer['headline']}**", "", *[f"- {f}" for f in answer["findings"]], "", "Actions:", "",
                  *[f"{i}. {a}" for i, a in enumerate(answer["actions"], 1)], "", f"Cost: {answer['cost_note']}", "",
                  f"(Claude, role `{ROLE}`, model {narrative.get('model')}, cost {narrative.get('cost_usd')} USD, worst case "
                  f"{narrative.get('worst_case_usd')} USD.)", ""]
    else:
        lines += [f"No narrative this week: {narrative.get('missing')}.", ""]
    lines += ["## Real orders", ""]
    if o.get("absent"):
        lines += ["No real book (`live.sqlite` absent).", ""]
    else:
        lines += [f"Placed {o.get('placed')}; fill rate of ended orders {o.get('fill_rate')}; real fills "
                  f"{(o.get('fills') or {}).get('n')} ({(o.get('fills') or {}).get('contracts')} contracts, fees "
                  f"{(o.get('fills') or {}).get('fees_usd')} USD).", "",
                  *_table(("Route", "Outcomes"), ((r, _kv(v)) for r, v in sorted((o.get("by_route") or {}).items()))), "",
                  "Rejections and refusals:", "", *([f"- {r['n']} x {r['text']}" for r in o.get("reasons") or []] or ["- none"]), ""]
    lines += ["## Fills against the Gym", ""]
    if not c.get("absent"):
        lines += [f"Calibration (real): {c.get('attempts')} attempts, {c.get('fills')} fills, mean "
                  f"{c.get('mean_worse_usd_per_contract')} USD a contract worse than the mid at submit.", "",
                  *_table(("Cell", "Attempts", "Ended", "Filled", "Fill rate", "Ticks worse", "USD a contract worse"),
                          ((k, v["attempts"], v["ended"], v["filled"], v["fill_rate"], v["mean_worse_ticks"],
                            v["mean_worse_usd_per_contract"]) for k, v in (c.get("cells") or {}).items())), ""]
    if not p.get("absent"):
        s = p.get("slippage_usd_per_contract") or {}
        lines += [f"Practice (the Gym's fill rules on live quotes): orders {p.get('orders')}, fills {p.get('fills')}, "
                  f"rejections {p.get('rejected')}; slippage to the decision's mid, USD a contract: all {s.get('all')}, opens "
                  f"{s.get('open')}, closes {s.get('close')}; at the natural {p.get('share_at_natural')}.", "",
                  *[f"- {r['n']} x {r['text']}" for r in p.get("reasons") or []], ""]
    if not b.get("absent"):
        lines += ["## Band moves", "", f"Demotions {b.get('demotions')}, promotions {b.get('promotions')}, retirements "
                  f"{b.get('retirements')}.", ""]
        lines += [f"- demoted {m['family']} {m['from']} -> {m['to']}: {m['why']}" for m in b.get("demoted") or []]
        lines += [f"- promoted {m['family']} {m['from']} -> {m['to']}: {m['why']}" for m in b.get("promoted") or []]
        lines += [f"- retired {m['family']} (from {m['from']}): {m['why']}" for m in b.get("retired") or []] + [""]
    if week.get("ladder"):
        lines += [f"The forward ladder's verdicts: {_kv(week['ladder'])}.", ""]
    lines += ["## Harness changes", "", f"Self-deploys: {_kv(h.get('self_deploys'))}; owner deploys: {_kv(h.get('owner_deploys'))}.",
              *[f"- {r['release']} ({r['sha']}): {r['verdict']}" for r in h.get("releases") or []],
              f"Engineer journal: {json.dumps(h.get('engineer') or {}, sort_keys=True)}.", "",
              "## The House's jobs", "", f"{_kv(j.get('by_status'))}; failed: {_kv(j.get('failed'))}; missed: {_kv(j.get('missed'))}.", "",
              "## Costs", ""]
    if costs.get("available"):
        lines += [f"From {costs.get('from')} to {costs.get('to')} ({costs.get('span_days')} days"
                  f"{', partial' if costs.get('partial') else ''}).", "",
                  *_table(("Service", "USD"), ((r["service"], r["usd"]) for r in costs.get("by_service") or [])),
                  f"| **Total** | **{costs.get('total_usd')}** |", "",
                  f"Realized options P&L {costs.get('realized_options_pnl_usd')} over {costs.get('closed_positions')} closes; "
                  f"net {costs.get('net_usd')}.", ""]
    else:
        lines += [f"Not measured: {costs.get('why')}.", ""]
    lines += [f"Swarm model spend booked (USD): {_kv(sp.get('by_kind'))}; Claude by role: {_kv(sp.get('claude_by_role'))}.", ""]
    if review:
        lines += cost_review_lines(review, private=True)
    if week.get("unread"):
        lines += ["## Not read", "", *[f"- {k}: {v}" for k, v in sorted(week["unread"].items())], ""]
    return "\n".join(lines)


def cost_review_lines(review: Mapping[str, Any], *, private: bool) -> list[str]:
    rc, rr, pr, vendor = (review.get("costs") or {}, review.get("research") or {}, review.get("proposal") or {},
                          review.get("vendor") or {})
    words = {"keep_standard": "keep the Standard plan", "drop_to_value": "move to the Value plan",
             "one_time_purchase": "buy the universe's history once, then cancel the rental"}
    lines = [f"## Cost review, the last {review.get('days')} days", ""]
    if rc.get("available"):
        lines += _table(("Service", "USD"), ((r["service"], r["usd"]) for r in rc.get("by_service") or []))
        lines += [f"| **Total** | **{rc.get('total_usd')}** |", "",
                  f"Realized options P&L {rc.get('realized_options_pnl_usd')}; net {rc.get('net_usd')} over {rc.get('span_days')} days"
                  f"{' (partial)' if rc.get('partial') else ''}.", ""]
    else:
        lines += [f"Costs not measured: {rc.get('why') or 'unread'}.", ""]
    plans = vendor.get("plans_usd_month") or {}
    lines += [f"The data vendor: {vendor.get('usd')} USD in the span ({vendor.get('share_of_costs')} of costs); plans: Standard "
              f"{plans.get('standard')} USD a month (current), Value {plans.get('value')}.",
              f"Research: {rr.get('gym_runs')} Gym runs and {rr.get('births')} births; roots alive: "
              f"{', '.join(rr.get('universe') or []) or 'none'}; first traded in the span: {', '.join(rr.get('new_roots') or []) or 'none'}.", "",
              f"**Proposal (D6): {words.get(pr.get('decision'), pr.get('decision'))}.** {str(pr.get('why') or '')[:600]}. "
              f"Saves {pr.get('saves_usd_month')} USD a month" + (f"; pays back in {pr['payback_months']} months" if pr.get("payback_months") else "")
              + ". The owner decides.", ""]
    if private and review.get("unread"):
        lines += [f"Not read: {', '.join(sorted(review['unread']))}.", ""]
    return lines


def public_text_ok(text: str, families: Iterable[str]) -> bool:
    """The model's text may join the public page: the scoreboard's public filter passes and it names no family."""
    from .scoreboard import public_problems

    pattern = _family_pattern(families)
    return not public_problems(text) and text.isascii() and (pattern is None or not pattern.search(text))


def public_page(day: str, week: Mapping[str, Any], review: Mapping[str, Any] | None, narrative: Mapping[str, Any],
                families: Iterable[str], *, written_at: str) -> tuple[str, bool]:
    """The public page, from an allowlist of counts and dollar figures, and whether the model's text was withheld."""
    o, c, p = week.get("orders") or {}, week.get("calibration") or {}, week.get("practice") or {}
    b, h, j, costs = week.get("bands") or {}, week.get("harness") or {}, week.get("jobs") or {}, week.get("costs") or {}
    status = o.get("by_status") or {}
    lines = [f"# Desk post-mortem, the week to {day}", "",
             f"Written by the House at {written_at} from its own records for the seven days to {week.get('to')}. Counts and "
             "dollar figures only.", ""]
    answer = narrative.get("answer")
    withheld = False
    if answer:
        block = [f"**{answer['headline']}**", "", *[f"- {f}" for f in answer["findings"]], "", "Next week:", "",
                 *[f"{i}. {a}" for i, a in enumerate(answer["actions"], 1)], "", answer["cost_note"]]
        if public_text_ok("\n".join(block), families):
            lines += ["## The reading (Claude)", "", *block, ""]
        else:
            withheld = True
            lines += ["## The reading", "", "Claude's reading of the week is kept private this week: it did not pass the "
                      "public filter.", ""]
    else:
        lines += ["## The reading", "", "No reading this week (the model was not asked or gave no answer); the figures "
                  "below are the House's own.", ""]
    lines += ["## Real orders", ""]
    if o.get("absent"):
        lines += ["No real book.", ""]
    else:
        lines += _table(("Placed", "Filled", "Cancelled or expired", "Rejected by the venue", "Refused before the venue",
                         "Fill rate of ended orders"),
                        [(o.get("placed", 0), status.get("filled", 0), status.get("cancelled", 0) + status.get("expired", 0),
                          status.get("rejected", 0), status.get("refused", 0), o.get("fill_rate"))]) + [""]
    lines += ["## Fills against the Gym", "", *_table(
        ("Book", "Fills", "Mean slippage a contract, USD (against the midpoint at the decision)"),
        [("Real (the House's one-lot calibration round trips)", c.get("fills", 0) if not c.get("absent") else 0,
          c.get("mean_worse_usd_per_contract")),
         ("Practice (the Gym's fill rules on live market data)", p.get("fills", 0) if not p.get("absent") else 0,
          (p.get("slippage_usd_per_contract") or {}).get("all"))]), "",
        f"Practice rejections: {p.get('rejected', 0) if not p.get('absent') else 0}.", "",
        "## Research", "",
        f"Demotions: {b.get('demotions', 0)}; promotions: {b.get('promotions', 0)}; retirements: {b.get('retirements', 0)}."
        + (f" The forward ladder's verdicts: {_kv(week['ladder'])}." if week.get("ladder") else ""), "",
        "## Harness changes", "",
        f"Self-deployed releases: {_kv(h.get('self_deploys'))}; owner deploys: {_kv(h.get('owner_deploys'))}.", "",
        "## The House's jobs", "",
        f"{_kv(j.get('by_status'))}; failed: {_kv(j.get('failed'))}; missed: {_kv(j.get('missed'))}.", "",
        "## What the week cost", ""]
    if costs.get("available"):
        lines += _table(("Service", "USD"), ((r["service"], r["usd"]) for r in costs.get("by_service") or []))
        lines += [f"| **Total** | **{costs.get('total_usd')}** |", "",
                  f"Realized options P&L of the week (all routes, fees in): {costs.get('realized_options_pnl_usd')} over "
                  f"{costs.get('closed_positions')} closes; the week's Net: {costs.get('net_usd')}"
                  f"{' (a partial week: the close economics start inside it)' if costs.get('partial') else ''}.", ""]
    else:
        lines += [f"Not measured this week ({costs.get('why') or 'no close economics'}).", ""]
    if review:
        lines += cost_review_lines(review, private=False)
    return "\n".join(lines), withheld


# ------------------------------------------------------------------------------------------------ the job
def run(ctx: Any, *, claude_factory: Callable[[str], Any] | None = None, claude_meter: Any = None) -> dict[str, Any]:
    from .scoreboard import public_problems

    now = ctx.now()
    day = S.iso(ctx.due_at)[:10]
    start, end = window(ctx.due_at)
    mine = ctx.job_settings()
    folder = ctx.root / "postmortem"
    week = facts(ctx.root, ctx.base, start, end)
    mode = str(mine.get("cost_review") or "monthly")
    review = None
    if mode == "always" or (mode == "monthly" and month_first(ctx.due_at)):
        review = cost_review(ctx.root, end, price_usd=_number(mine.get("one_time_price_usd")))
    with guard.readonly():
        try:
            families = family_ids(ctx.root)
        except Exception:  # noqa: BLE001 - names unread: every free text stays private and the model is not asked
            families = None
    earlier = read_json(folder / f"{day}.json", None)
    if isinstance(earlier, dict) and isinstance(earlier.get("narrative"), dict) and earlier["narrative"].get("answer") \
            and earlier.get("window") == [S.iso(start), S.iso(end)]:
        narrative = {**earlier["narrative"], "reused": True}
    elif mine.get("model") is False:
        narrative = {"missing": "switched off in ops.json (postmortem.model false)"}
    elif families is None:
        narrative = {"missing": "the family names could not be read, so the prompt cannot be checked; the model was not asked"}
    else:
        narrative = narrate(ctx, week, review, families, key=f"{ROLE}:{day}", claude_factory=claude_factory,
                            claude_meter=claude_meter)
    written = S.iso(now)[11:16] + "Z"
    write_json(folder / f"{day}.json", {"window": [S.iso(start), S.iso(end)], "facts": week, "cost_review": review,
                                        "narrative": narrative, "written_at": S.iso(now)})
    report = write_text(folder / f"{day}.md", private_report(day, week, review, narrative, written_at=written))
    receipt: dict[str, Any] = {
        "report": str(report), "window": [S.iso(start), S.iso(end)], "unread": sorted(week["unread"]),
        "model": ({k: narrative.get(k) for k in ("route", "model", "cost_usd", "worst_case_usd", "reused") if k in narrative}
                  if narrative.get("answer") else {"missing": narrative.get("missing")}),
        "cost_review": (review.get("proposal") or {}).get("decision") if review else None}
    if mine.get("public") is False:
        return {**receipt, "posted": None, "why": "switched off in ops.json (postmortem.public false)"}
    text, withheld = public_page(day, week, review, narrative, families or (), written_at=written)
    local = write_text(folder / f"{day}-public.md", text)
    problems = public_problems(text)
    pattern = _family_pattern(families or ())
    if families is None:
        problems.append("the family names could not be read")
    elif pattern is not None and pattern.search(text):
        problems.append("a family name")
    if problems:
        raise ValueError("the public page failed the public filter, not posted: " + ", ".join(problems))
    path = PUBLIC_PATH.format(day=day)
    receipt.update(public_local=str(local), withheld=withheld, bytes=len(text))
    try:
        answer = ctx.gateway.post(DOCS_ROUTE, {"path": path, "content": text, "message": f"desk: post-mortem {day}"})
    except GatewayError as exc:
        if exc.status in (404, 405):
            return {**receipt, "status": "skipped", "why": "the gateway's docs route is not deployed", "posted": None}
        raise
    return {**receipt, "posted": path, "commit": (answer or {}).get("commit") if isinstance(answer, dict) else None}
