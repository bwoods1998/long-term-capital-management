"""The `scoreboard` job (daily 23:30Z): the desk's public-safe daily page, committed through the gateway.

Built from the House's own records only: the latest close economics (`economics.latest`), the job receipts
(`ops.sqlite`), `<base>/deploys.jsonl`, `<state>/budget.json` (when the budget job has written one), the practice
record and, when the forward ladder's tables exist, its counts. It says: the running release; self-deploys and
self-rollbacks; real closes and realized options P&L (since T0 and trailing 30 days); input costs by service since T0;
the one Net; how many lots are open and what they are worth at conservative marks; the budget's state and the next
card action date per meter; the ladder's counts; the day's jobs; and THE FUNNEL (the owner's goal of Oct 7, 2026, item
3), the last 24 hours beside the time since the running release began (`league/ops/funnel.py`): births, program versions,
Gym runs by window, validations judged and passed, looks taken and passed, moves to Candidate, Probe and Sized and the
bands now, real orders and closes by route (the agents' against the House's), research spend by meter, the hours the
Sail guard braked, and the stalls the `stall` job finds standing (`<state>/stall.json`, causes only). Every funnel figure
is a count or a spend, never a Validation or holdout figure.

PUBLIC: the page is built from an allowlist of figures (`build`), never from free text the House holds, and then
checked by `public_problems` (no account equity or balance, no quote, contract symbol, strike, box id, parameter or
program text, no Validation or holdout figure). A page that fails the check is not posted (the job fails). It is
posted as `POST /v1/github/docs` to `docs/runs/desk/<YYYY-MM-DD>.md` (the gateway's docs route; until that route is
deployed the job keeps the page in `<state>/scoreboard/` and its receipt says it was not posted).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from . import funnel as FN
from . import guard
from . import schedule as S
from .context import GatewayError, read_json, write_text
from .economics import T0
from .store import read_runs

DOCS_ROUTE = "/v1/github/docs"
PATH = "docs/runs/desk/{day}.md"
#: What a public page may never carry. Each is (name, pattern); a match is a problem and the page is not posted.
FORBIDDEN = (
    ("an option contract symbol", re.compile(r"\b[A-Z]{1,6}\d{6}[CP]\d{8}\b")),
    ("a Sail box or checkpoint id", re.compile(r"\bsb(?:cp)?_[0-9a-fA-F-]{6,}")),
    ("account equity", re.compile(r"\bequity\b", re.I)),
    ("an account balance", re.compile(r"\bbalances?\b", re.I)),
    ("buying power", re.compile(r"buying\s+power", re.I)),
    ("a quote", re.compile(r"\b(?:bid|ask|quote[sd]?|nbbo|mid)\b", re.I)),
    ("a strike", re.compile(r"\bstrikes?\b", re.I)),
    ("program text", re.compile(r"\bdef\s+\w+\s*\(|\bdecide\s*\(|\bPARAMS\b|\bNEEDS\b|\bimport\s+\w+")),
    ("a parameter", re.compile(r"\bparams?\b|\bparameters?\b", re.I)),
    ("a Validation or holdout figure", re.compile(r"\b(?:validation|holdout)\b", re.I)),
    ("a secret-like token", re.compile(r"\b[A-Za-z0-9_\-]{40,}\b")),
)


def public_problems(text: str) -> list[str]:
    """What in `text` a public page may not carry (empty when it is safe)."""
    return [name for name, pattern in FORBIDDEN if pattern.search(text)]


#: A rollback drill's release id starts so (`league.watchdog.DRILL_PREFIX`, `python -m league.watchdog drill-rollback`).
DRILL_PREFIX = "drill-"


def deploy_counts(base: str | Path, *, since: str = T0, day: str | None = None) -> dict[str, Any]:
    """Self-deploys (the updater's: a verdict row carrying the attested `sha`) promoted and rolled back since `since`,
    and on `day`; every verdict counted apart. A rollback drill's verdicts (its release a `DRILL_PREFIX` copy) are
    drills, never owner deploys: the drill deploys through the watchdog with no attestation, and its `rolled_back`
    is the drill passing."""
    out = {"self_promoted": 0, "self_rolled_back": 0, "self_promoted_today": 0, "self_rolled_back_today": 0,
           "owner_promoted": 0, "owner_rolled_back": 0, "drill_promoted": 0, "drill_rolled_back": 0}
    try:
        with (Path(base) / "deploys.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                if '"verdict"' not in line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("stage") != "verdict" or str(row.get("at") or "") < since:
                    continue
                verdict = row.get("verdict")
                if verdict not in ("promoted", "rolled_back"):
                    continue
                who = ("drill" if str(row.get("release") or "").startswith(DRILL_PREFIX)
                       else "self" if row.get("sha") else "owner")
                key = f"{who}_{'promoted' if verdict == 'promoted' else 'rolled_back'}"
                out[key] += 1
                if who == "self" and day and str(row.get("at") or "").startswith(day):
                    out[key + "_today"] += 1
    except OSError:
        out["error"] = "deploys.jsonl unreadable"
    return out


def _tables(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(guard.read(path, lambda db: guard.ids(db, "SELECT name FROM sqlite_master WHERE type='table'")))


def ladder_counts(root: str | Path, now: float) -> dict[str, Any]:
    """Entrants, programs in practice, promotions by the ladder and the Benjamini-Hochberg family size (the trailing
    90 days' entrants). "n/a" where the forward ladder's tables (`entrants`, `ladder_decisions`) do not exist yet."""
    root = Path(root)
    out: dict[str, Any] = {"entrants": "n/a", "in_practice": "n/a", "promoted": "n/a", "bh_family_size": "n/a"}
    try:
        if "cohorts" in _tables(root / "observe.sqlite"):
            out["in_practice"] = guard.read(root / "observe.sqlite", lambda db: guard.ids(
                db, "SELECT count(*) FROM cohorts WHERE status='active'"))[0]
    except Exception:  # noqa: BLE001 - a count that cannot be read stays n/a
        pass
    since_epoch, since_iso = now - 90 * 86400, S.iso(now - 90 * 86400)
    for name in ("observe.sqlite", "swarm.sqlite", "ladder.sqlite"):
        path = root / name
        try:
            tables = _tables(path)
            if "entrants" in tables:
                total, recent = guard.read(path, lambda db: (
                    guard.ids(db, "SELECT count(*) FROM entrants")[0],
                    guard.ids(db, "SELECT count(*) FROM entrants WHERE (typeof(entered_at) IN ('integer','real') AND entered_at>=?) "
                                  "OR (typeof(entered_at)='text' AND entered_at>=?)", (since_epoch, since_iso))[0]))
                out["entrants"], out["bh_family_size"] = total, recent
            if "ladder_decisions" in tables:
                out["promoted"] = guard.read(path, lambda db: guard.ids(
                    db, "SELECT count(*) FROM ladder_decisions WHERE lower(verdict) IN ('promote','promoted','probe')"))[0]
        except Exception:  # noqa: BLE001
            continue
    return out


def job_counts(root: str | Path, day: str) -> dict[str, int]:
    start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    rows = read_runs(root, S.iso(start.timestamp()), S.iso((start + timedelta(days=1)).timestamp()))
    out = {"ok": 0, "failed": 0, "missed": 0, "skipped": 0}
    for row in rows:
        if row["status"] in out:
            out[row["status"]] += 1
    return out


def _cell(value: Any) -> str:
    return "n/a" if value is None else str(value)


def budget_lines(budget: Mapping[str, Any] | None) -> list[str]:
    """The budget's state and the next card action date per meter: the rule's own words and dates, never a balance."""
    if not isinstance(budget, Mapping):
        return ["No budget state yet (the budget job has not written one)."]
    lines = []
    state = budget.get("state") or budget.get("status")
    if state:
        lines.append(f"State: {state}.")
    if budget.get("direction"):
        lines.append(f"Research budget against yesterday: {budget['direction']}.")
    meters = budget.get("meters") if isinstance(budget.get("meters"), Mapping) else {}
    cards = budget.get("next_card_action") if isinstance(budget.get("next_card_action"), Mapping) else {}
    rows = []
    for meter in sorted(set(meters) | set(cards)):
        row = meters.get(meter) if isinstance(meters.get(meter), Mapping) else {}
        research = row.get("research_usd_day")
        card = cards.get(meter) or row.get("next_card_action") or row.get("card_date")
        rows.append(f"| {meter} | {_cell(research)} | {_cell(card)} |")
    if rows:
        lines += ["", "| Meter | Research USD/day | Next card action |", "|---|---:|---|", *rows]
    return lines or ["The budget state names no meter."]


def engineer_lines(engineer: Mapping[str, Any] | None) -> list[str]:
    """The engineer's counts (`league/ops/engineer.py` `public_summary`): changes authored, merged, retained, reverted."""
    if not isinstance(engineer, Mapping):
        return ["The engineer has not run yet."]
    lines = ["| Authored | Merged | Retained | Reverted | Rejected | Failed | Claude USD |", "|---:|---:|---:|---:|---:|---:|---:|",
             f"| {_cell(engineer.get('authored'))} | {_cell(engineer.get('merged'))} | {_cell(engineer.get('retained'))} | "
             f"{_cell(engineer.get('reverted'))} | {_cell(engineer.get('rejected'))} | {_cell(engineer.get('failed'))} | "
             f"{_cell(engineer.get('claude_usd'))} |", ""]
    lines.append(f"In flight: {engineer.get('in_flight') or 'none'}.")
    leftover = [n for n in engineer.get("leftover_prs") or [] if isinstance(n, int) and not isinstance(n, bool)]
    if leftover:  # the gateway would not close them, or a revert that did not merge: the owner's
        lines += ["", "Engineer pull requests left open for the owner (the gateway would not close them, or a revert did "
                      "not merge): " + ", ".join(f"#{n}" for n in leftover[-20:]) + "."]
    return lines


def _pair(a: Any, b: Any) -> str:
    """`a (b)`, or n/a when `a` is unknown."""
    return "n/a" if a is None else f"{a} ({_cell(b)})"


def _dig(value: Any, *keys: str) -> Any:
    for key in keys:
        value = value.get(key) if isinstance(value, Mapping) else None
    return value


def funnel_lines(funnel: Mapping[str, Any] | None, stalls: Mapping[str, Any] | None = None) -> list[str]:
    """THE FUNNEL's section (`funnel.read`'s shape): counts and spend only, the last 24 hours beside the time since the
    release began; a window that could not be read is n/a. `stalls` is `<state>/stall.json`: its standing causes."""
    lines = ["## Funnel (last 24 h / since the release)", ""]
    if not isinstance(funnel, Mapping) or not isinstance(funnel.get("day"), Mapping):
        return lines + ["The funnel could not be read.", ""]
    day, rel = funnel["day"], funnel.get("release")
    lines.append(f"Since the release: from {funnel['since']}." if funnel.get("since") and isinstance(rel, Mapping)
                 else "The running release's start is not on record: its column is n/a.")
    lines.append("")

    def cells(*keys: str, pair: tuple[str, ...] | None = None) -> str:
        out = []
        for window in (day, rel):
            if not isinstance(window, Mapping):
                out.append("n/a")
            elif pair is not None:
                out.append(_pair(_dig(window, *keys), _dig(window, *pair)))
            else:
                out.append(_cell(_dig(window, *keys)))
        return " | ".join(out)

    rows = [("Births", cells("births")), ("Program versions written", cells("versions"))]
    labels = {"train": "train", "validation": "validations (two a program: the 1.5x twin)", "holdout": "looks",
              "forward": "forward", "probe": "probe", "mechanism": "mechanism"}
    rows += [(f"Gym runs: {labels[w]}", cells("gym_runs", w)) for w in FN.WINDOWS]
    if any(_dig(w, "gym_runs", "other") for w in (day, rel) if isinstance(w, Mapping)):
        rows.append(("Gym runs: other windows", cells("gym_runs", "other")))
    rows += [("Gym runs refused or failed", cells("gym_not_run")),
             ("Rows copied from an identical program's verdict (no Gym run)", cells("gym_no_trial")),
             ("Validations judged (passed)", cells("validations", "judged", pair=("validations", "passed")))]
    # M5 (Oct 10, 2026): a direction version that missed the line can still go to the gate by D2's pre-check
    # (`funnel.swarm_counts` `entered`). Its row shows only when a window has such an entry, so a page without one is
    # as before. (No "validation" or "holdout" word: `public_problems` refuses them, "Validations" included as plural.)
    if any(_dig(w, "validations", "entered") not in (None, _dig(w, "validations", "passed"))
           for w in (day, rel) if isinstance(w, Mapping)):
        rows.append(("Validations sent to the gate (the line, or D2's pre-check)", cells("validations", "entered")))
    rows += [("Looks taken (passed)", cells("looks", "taken", pair=("looks", "passed"))),
             ("Moves to Candidate", cells("band_moves", "candidate")), ("Moves to Probe", cells("band_moves", "probe")),
             ("Moves to Sized", cells("band_moves", "sized")),
             ("Real orders, agent routes (filled)", cells("book", "orders", "agent", pair=("book", "filled", "agent"))),
             ("Real orders, House routes (filled)", cells("book", "orders", "house", pair=("book", "filled", "house"))),
             ("Real closes, agent routes", cells("book", "closes", "agent")),
             ("Real closes, House routes", cells("book", "closes", "house")),
             ("Research spend, Sail (USD)", cells("spend_usd", "sail")),
             ("Research spend, Claude (USD)", cells("spend_usd", "claude")),
             ("Research spend, OpenAI (USD)", cells("spend_usd", "openai")),
             ("Hours the Sail guard braked", cells("braked", "hours"))]
    lines += ["| Measure | Last 24 h | Since the release |", "|---|---:|---:|", *[f"| {name} | {value} |" for name, value in rows], ""]
    now = funnel.get("bands_now")
    if isinstance(now, Mapping):
        lines += [f"Bands now: Candidate {now.get('candidate', 0)}, Probe {now.get('probe', 0)}, Sized {now.get('sized', 0)} "
                  f"(of {now.get('alive', 0)} living families).", ""]
    causes = _dig(stalls, "causes")
    if isinstance(causes, Mapping):
        # A Done checkpoint that holds is the stall job's news to the owner (`stall.NEWS_CAUSES`, Oct 10, 2026), never a
        # stall on the public page: a Done claim is the owner's to make, with its evidence beside it.
        from .stall import NEWS_CAUSES

        standing = [f"{name} (since {_cell(_dig(rec, 'seen_at'))})" for name, rec in sorted(causes.items())
                    if isinstance(rec, Mapping) and rec.get("standing") and re.fullmatch(r"[a-z_]{1,40}", str(name))
                    and name not in NEWS_CAUSES]
        lines += [f"Stalls standing now: {', '.join(standing) if standing else 'none'}.", ""]
    return lines


def build(*, day: str, release: str, economics: Mapping[str, Any] | None, deploys: Mapping[str, Any],
          budget: Mapping[str, Any] | None, ladder: Mapping[str, Any], jobs: Mapping[str, int], written_at: str,
          engineer: Mapping[str, Any] | None = None, funnel: Mapping[str, Any] | None = None,
          stalls: Mapping[str, Any] | None = None) -> str:
    """The page, from an allowlist of figures (the funnel's section only when `funnel` is given)."""
    lines = [f"# Desk scoreboard, {day}", "",
             f"Written by the House at {written_at} from its own records (release `{release}`). Money figures run from the "
             "Sept 26, 2026 reset (T0) to the latest close economics' cutoff; deposits are never profit.", ""]
    if not economics:
        lines += ["## Money", "", "No close economics yet.", ""]
    else:
        realized, net = economics.get("realized") or {}, economics.get("net") or {}
        opens = economics.get("open_positions") or {}
        n_open = sum(1 for p in economics.get("positions") or [] if p.get("status_at_cutoff") != "closed")
        n_closed = sum(int((v or {}).get("closed_positions") or 0) for v in (realized.get("by_route") or {}).values())
        p30 = economics.get("p30") or {}
        lines += ["## Money", "", f"Cutoff: {economics.get('cutoff')}.", "", "| Measure | USD |", "|---|---:|",
                  f"| Realized options P&L since T0 (all routes, fees in) | {_cell(realized.get('realized_options_pnl_usd'))} |",
                  f"| Realized options P&L, trailing 30 days | {_cell(p30.get('usd'))} |",
                  f"| Input costs since T0 | {_cell(economics.get('total_costs_usd'))} |",
                  f"| **Net (realized - costs)** | **{_cell(net.get('net_usd'))}** |",
                  f"| Open lots ({n_open}) at conservative marks, unrealized | {_cell(opens.get('unrealized_conservative_usd'))} |",
                  f"| Net with open lots at conservative marks | {_cell(net.get('net_with_open_at_conservative_marks_usd'))} |", "",
                  f"Real closes since T0: {n_closed}" + (f" ({p30.get('closed_positions')} in the trailing 30 days)." if p30 else "."), "",
                  "### Input costs by service since T0", "", "| Service | USD |", "|---|---:|"]
        lines += [f"| {c.get('service')} | {_cell(c.get('usd'))} |" for c in economics.get("costs") or []]
        lines.append("")
    lines += ["## Budget", "", *budget_lines(budget), "",
              "## Releases", "",
              f"Self-deployed releases since T0: {deploys.get('self_promoted', 0)} ({deploys.get('self_promoted_today', 0)} today); "
              f"self-rollbacks: {deploys.get('self_rolled_back', 0)} ({deploys.get('self_rolled_back_today', 0)} today). "
              f"Owner deploys: {deploys.get('owner_promoted', 0)} promoted, {deploys.get('owner_rolled_back', 0)} rolled back. "
              f"Rollback drills: {deploys.get('drill_rolled_back', 0)} rolled back as intended, "
              f"{deploys.get('drill_promoted', 0)} not caught.", "",
              "## The forward ladder", "", "| Entrants | In practice | Promoted by the ladder | BH family size (90 d) |",
              "|---:|---:|---:|---:|",
              f"| {_cell(ladder.get('entrants'))} | {_cell(ladder.get('in_practice'))} | {_cell(ladder.get('promoted'))} | "
              f"{_cell(ladder.get('bh_family_size'))} |", "",
              "## The engineer (harness changes)", "", *engineer_lines(engineer), "",
              "## The House's jobs today", "",
              f"Ran: {jobs.get('ok', 0)}; failed: {jobs.get('failed', 0)}; missed: {jobs.get('missed', 0)}; skipped: {jobs.get('skipped', 0)}.", ""]
    if funnel is not None:
        lines += funnel_lines(funnel, stalls)
    return "\n".join(lines)


def run(ctx: Any) -> dict[str, Any]:
    from .economics import latest

    now = ctx.now()
    day = S.iso(ctx.due_at)[:10]
    try:
        from .engineer import public_summary

        engineer = public_summary(ctx.root)
    except Exception:  # noqa: BLE001 - the page is written whatever the engineer's journal holds
        engineer = None
    release = Path(ctx.release).name
    try:
        funnel: Mapping[str, Any] | None = FN.read(ctx.root, ctx.base, release, now)
    except Exception:  # noqa: BLE001 - the page says the funnel could not be read; the rest still goes out
        funnel = {}
    text = build(day=day, release=release, economics=latest(ctx.root), deploys=deploy_counts(ctx.base, day=day),
                 budget=read_json(ctx.root / "budget.json", None), ladder=ladder_counts(ctx.root, now),
                 jobs=job_counts(ctx.root, day), written_at=S.iso(now)[11:16] + "Z", engineer=engineer, funnel=funnel,
                 stalls=read_json(ctx.root / "stall.json", None))
    problems = public_problems(text)
    local = write_text(ctx.root / "scoreboard" / f"{day}.md", text)
    if problems:
        raise ValueError("the page failed the public filter, not posted: " + ", ".join(problems))
    path = PATH.format(day=day)
    try:
        answer = ctx.gateway.post(DOCS_ROUTE, {"path": path, "content": text, "message": f"desk: scoreboard {day}"})
    except GatewayError as exc:
        if exc.status in (404, 405):
            return {"status": "skipped", "why": "the gateway's docs route is not deployed", "local": str(local), "bytes": len(text)}
        raise
    return {"posted": path, "local": str(local), "bytes": len(text),
            "commit": (answer or {}).get("commit") if isinstance(answer, dict) else None}
