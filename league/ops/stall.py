"""The `stall` job (every 30 minutes, 24/7; the owner's goal of Oct 7, 2026, item 6): the floor raises an alarm when it
stalls, says what the House is doing about it, and says what only the owner can do.

From Oct 3 to Oct 7 research ran 1 to 13 Gym runs a day with no birth, and nobody was told: the House's one alarm (a
pre-open FAIL) went to a ledger row no mail carries. This job reads the House's own records every half hour and names
a STALL by its cause:

- `births`: no family was born in the last `BIRTH_HOURS` hours while the living population is under its ceiling
  (`population.ceiling` as the swarm's own settings load it, the budget's tightening included);
- `gym_runs`: the Gym evaluated fewer than `MIN_GYM_RUNS` programs in the last `GYM_HOURS` hours (a run the Gym refused
  or failed is not one: `funnel.NOT_RUN`);
- `validations`: no Validation run in the last `VALIDATION_HOURS` hours while a living family holds a Train best that was
  never validated (its best version is not its validated version; with every best validated, none is owed);
- `braked`: the Sail guard was braked `BRAKED_HOURS` or more of the last `BRAKE_WINDOW_HOURS` hours, whatever the cause
  (the budget's daily stop reached by noon keeps research from running round the clock as surely as a low balance);
- `runway_sail`, `runway_claude`: a meter's days of research left at the ceiling (`budget.json` `card_runway_days`: what it
  holds above its reserve at its fixed cost plus its share of the ceiling, the figure the funding notice reads) are under
  `RUNWAY_DAYS`. The owner step is the top-up, with the budget's own amount;
- `owner_deploy`: main's head carries a change only the owner's deploy may make (the updater refused it as the owner's
  deploy, `deploys.jsonl` stage `vet`) and no release was promoted since. The owner step is that deploy.

For each stall it posts one `POST /v1/notify` kind `stall` (`notice_facts`: the cause, the numbers, how long, what the
House is doing about it, and the owner step when one is needed) through the same gateway client the budget's funding
notice uses (`budget._notifier`), at most once a cause every `NOTICE_EVERY_SECONDS` (12 h; the gateway holds the same rule
by cause, so a lost state file never mails twice), and raises a House warning at the same pace. A cause is told again
only once the gateway says it SENT the notice: a `duplicate` answer (the gateway told it within 12 h by its own clock) is
tried at the next run. `<state>/stall.json` (private) remembers each cause: since when it stands, when it was last told
and warned of. A cause that clears is named in the receipt. The receipt carries every check, stalled or not, with its
numbers.

HOW LONG: from the record when it says (the last birth, the last Validation run, the start of the guard's brake, the
first refusal of the owner's deploy), else from when this job first saw the cause standing.

NEVER ACTS. The job reads (every SQLite open `mode=ro`, inside `guard.readonly()`), writes only `stall.json`, and posts
only the notice: it moves no money, changes no setting, starts and stops nothing. Not in a maintenance pause (a pause
stops births by design).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Mapping

from . import budget as B
from . import funnel as F
from . import guard
from . import schedule as S
from .context import read_json, write_json

BIRTH_HOURS = 12
GYM_HOURS = 6
MIN_GYM_RUNS = 10
VALIDATION_HOURS = 24
BRAKE_WINDOW_HOURS = 24
BRAKED_HOURS = 12.0
RUNWAY_DAYS = 3.0
#: One notice (and one House warning) a cause at most this often.
NOTICE_EVERY_SECONDS = 12 * 3600
#: A budget.json older than this is not read for the runway (the budget job has stopped: its own warnings say so).
BUDGET_STALE_SECONDS = 36 * 3600
STATE_FILE = "stall.json"
HEARTBEAT = "swarm.heartbeat"
CAUSES = ("births", "gym_runs", "validations", "braked", "runway_sail", "runway_claude", "owner_deploy")
METER_WORDS = {"sail": "Sail", "claude": "Claude (Anthropic)"}
#: The Sail guard's causes the owner alone can clear, and the step that clears each.
GUARD_STEPS = {"under_line": "top up Sail: the Sail guard brakes the whole swarm while the balance is under its line",
               "disk": "free disk on the House box: the Sail guard brakes the swarm while the state disk is under its line"}
#: What the Sail guard does by itself about each cause of a brake.
GUARD_DOING = {
    "research_budget": "research spent the day's Sail dollars early: the guard releases at 00:00 UTC with the next day's",
    "account_budget": "Sail's own meter reached the day's account cap: the guard releases at 00:00 UTC with the next day's",
    "under_line": "the guard releases on a fresh reading above its release line",
    "balance_unreadable": "the guard reads Sail's balance again every few minutes and releases on a good reading",
    "budget_unreadable": "the budget rule could not be read: the budget job runs again at 00:30 UTC and after the close",
    "disk": "the guard releases once the state disk has room again",
    "no_reading": "the guard releases on its first good reading",
}
_OWNER_DEPLOY = re.compile(r"owner's (?:own )?deploy")


def _get(ctx: Any, name: str, default: Any = None) -> Any:
    if isinstance(ctx, Mapping):
        return ctx.get(name, default)
    return getattr(ctx, name, default)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return out if out == out and out not in (float("inf"), float("-inf")) else None


def _hours(seconds: float) -> str:
    return f"{max(0.0, seconds) / 3600:.1f}"


def _first_up(text: str) -> str:
    return text[:1].upper() + text[1:]


# ---------------------------------------------------------------------------------------------- the reads
def swarm_facts(db: Any, now: float) -> dict[str, Any]:
    """What the checks read from the swarm's store, in one read transaction (`guard.read`)."""
    iso = lambda hours: S.iso(now - hours * 3600)  # noqa: E731
    one = lambda sql, params=(): (guard.ids(db, sql, params) or [None])[0]  # noqa: E731
    out: dict[str, Any] = {}
    out["births"] = int(one("SELECT count(*) FROM events WHERE kind='swarm.born' AND at>=?", (iso(BIRTH_HOURS),)) or 0)
    out["last_birth_at"] = one("SELECT max(at) FROM events WHERE kind='swarm.born'")
    out["alive"] = int(one("SELECT count(*) FROM families WHERE retired_at IS NULL") or 0)
    passes = {"passes": 0, "no_cell": 0, "ceiling": 0, "failed": 0, "asked": 0, "proposed": 0, "born": 0}
    for text in guard.ids(db, "SELECT payload FROM events WHERE kind='swarm.architect' AND at>=? ORDER BY seq",
                          (iso(BIRTH_HOURS),)):
        try:
            row = json.loads(text)
        except (TypeError, ValueError):
            continue
        if not isinstance(row, Mapping):
            continue
        passes["passes"] += 1
        skipped = row.get("skipped")
        if skipped in ("no_cell", "ceiling"):
            passes[skipped] += 1
        elif row.get("error"):
            passes["failed"] += 1
        else:
            passes["asked"] += 1
            passes["proposed"] += int(_finite(row.get("proposed")) or 0)
        passes["born"] += len(row.get("born") or []) if isinstance(row.get("born"), list) else 0
    out["architect"] = passes
    runs = guard.rows(db, "SELECT status, count(*) AS n, max(at) AS last FROM runs WHERE at>=? GROUP BY status",
                      (iso(GYM_HOURS),))
    out["gym_runs"] = sum(int(r["n"] or 0) for r in runs if r["status"] not in F.NOT_RUN)
    out["gym_not_run"] = sum(int(r["n"] or 0) for r in runs if r["status"] in F.NOT_RUN)
    marks = ",".join("?" * len(F.NOT_RUN))
    out["last_gym_run_at"] = one(f"SELECT max(at) FROM runs WHERE status NOT IN ({marks})", F.NOT_RUN)
    out["cycles"] = int(one("SELECT count(*) FROM events WHERE kind='swarm.cycle' AND at>=?", (iso(GYM_HOURS),)) or 0)
    out["validation_runs"] = int(one("SELECT count(*) FROM runs WHERE \"window\"='validation' AND at>=?",
                                     (iso(VALIDATION_HOURS),)) or 0)
    out["last_validation_at"] = one("SELECT max(at) FROM runs WHERE \"window\"='validation'")
    out["train_bests"] = int(one("SELECT count(*) FROM families WHERE retired_at IS NULL AND best_version IS NOT NULL") or 0)
    out["awaiting"] = int(one("SELECT count(*) FROM families WHERE retired_at IS NULL AND best_version IS NOT NULL AND "
                              "(validated_version IS NULL OR validated_version != best_version)") or 0)
    last = guard.rows(db, "SELECT at, payload FROM events WHERE kind='swarm.tournament' ORDER BY seq DESC LIMIT 1")
    round_ = None
    if last:
        try:
            validation = (json.loads(last[0]["payload"]) or {}).get("validation") or {}
        except (TypeError, ValueError, AttributeError):
            validation = {}
        size = lambda value: len(value) if isinstance(value, (list, dict)) else 0  # noqa: E731
        round_ = {"at": last[0]["at"], "queued": int(_finite(validation.get("queued")) or 0),
                  "judged": size(validation.get("judged")), "waiting_robustness": size(validation.get("waiting_robustness")),
                  "waiting_drift": size(validation.get("waiting_drift")), "errors": size(validation.get("errors"))}
    out["last_round"] = round_
    out["brake"] = F.guard_hours(db, now - BRAKE_WINDOW_HOURS * 3600, now)
    raw = one("SELECT value FROM kv WHERE key='guard'")
    try:
        record = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        record = {}
    record = record if isinstance(record, Mapping) else {}
    causes = record.get("causes")
    out["guard"] = {"braked": bool(record.get("braked")), "research_held": bool(record.get("research_held")),
                    "causes": [str(c) for c in causes] if isinstance(causes, list) else []}
    return out


def owner_deploy(base: str | Path) -> dict[str, Any] | None:
    """The updater's refusals of main's head as the owner's deploy since the last promotion (`deploys.jsonl`): the first
    and the latest, the latest's sha and the protected files it names. None when there is none (or no record)."""
    promoted = None
    refusals: list[dict[str, Any]] = []
    try:
        with (Path(base) / "deploys.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                if '"promoted"' not in line and '"refused"' not in line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                at = S.epoch(row.get("at"))
                if at is None:
                    continue
                if row.get("stage") == "verdict" and row.get("verdict") == "promoted":
                    promoted = at if promoted is None else max(promoted, at)
                    refusals = [r for r in refusals if r["at"] > at]
                elif row.get("stage") == "vet" and row.get("verdict") == "refused":
                    reasons = [str(r) for r in row.get("reasons") or [] if _OWNER_DEPLOY.search(str(r))]
                    if reasons and (promoted is None or at > promoted):
                        refusals.append({"at": at, "sha": str(row.get("sha") or "")[:12],
                                         "files": [r.split(":", 1)[0].split(" ", 1)[0] for r in reasons]})
    except OSError:
        return None
    if not refusals:
        return None
    return {"first_at": refusals[0]["at"], "latest_at": refusals[-1]["at"], "sha": refusals[-1]["sha"],
            "files": refusals[-1]["files"], "promoted_at": promoted}


def _ceiling(ctx: Any, root: Path) -> tuple[int | None, str | None]:
    """`population.ceiling` as the swarm loads its settings (the budget's tightening included), or None and why."""
    given = _get(ctx, "population_ceiling")
    if given is not None:
        return int(given), None
    try:
        from ..swarm import settings as settings_mod

        config = _get(ctx, "config")
        with guard.readonly():
            loaded = settings_mod.load(root, config=config if isinstance(config, Mapping) else None)
        return int((loaded.get("population") or {}).get("ceiling")), None
    except Exception as exc:  # noqa: BLE001 - an unknown ceiling raises no births stall
        return None, f"the population ceiling could not be read ({type(exc).__name__})"


# ---------------------------------------------------------------------------------------------- the checks
def _guard_step(causes: Any) -> str | None:
    for cause in causes or []:
        if cause in GUARD_STEPS:
            return GUARD_STEPS[cause]
    return None


def _guard_words(guard_now: Mapping[str, Any]) -> str:
    if guard_now.get("braked"):
        return "the Sail guard is braked (" + (", ".join(guard_now.get("causes") or []) or "cause not named") + ")"
    if guard_now.get("research_held"):
        return "the Sail guard holds new research at the day's line (the gate's reserve goes on)"
    return "the Sail guard is clear"


def checks(swarm: Mapping[str, Any], *, now: float, ceiling: int | None, budget: Mapping[str, Any] | None,
           deploy: Mapping[str, Any] | None, heartbeat: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Every cause's check: {stalled, what, numbers, doing, owner_step, onset (epoch or None)}. Pure."""
    out: dict[str, dict[str, Any]] = {}
    guard_now = swarm.get("guard") or {}
    guard_step = _guard_step(guard_now.get("causes")) if guard_now.get("braked") else None
    beat_at = _finite((heartbeat or {}).get("at"))
    beat_min = None if beat_at is None else round(max(0.0, now - beat_at) / 60.0, 1)

    # births
    passes = swarm.get("architect") or {}
    alive, births = int(swarm.get("alive") or 0), int(swarm.get("births") or 0)
    last_birth = S.epoch(swarm.get("last_birth_at"))
    out["births"] = {
        "stalled": births == 0 and ceiling is not None and alive < ceiling,
        "what": f"No family was born in the last {BIRTH_HOURS} h while the population is {alive} of a ceiling of "
                f"{'unknown' if ceiling is None else ceiling}.",
        "numbers": {f"births_{BIRTH_HOURS}h": births, "population": alive, "ceiling": ceiling,
                    "last_birth_at": swarm.get("last_birth_at"), f"architect_passes_{BIRTH_HOURS}h": passes.get("passes", 0)},
        "doing": (f"The architect passed {passes.get('passes', 0)} times in the last {BIRTH_HOURS} h: {passes.get('no_cell', 0)} "
                  f"found no cell a birth may land in, {passes.get('ceiling', 0)} met the ceiling, {passes.get('failed', 0)} "
                  f"failed, {passes.get('asked', 0)} asked a model and proposed {passes.get('proposed', 0)} families "
                  f"({passes.get('born', 0)} born). It passes again at its own cadence; research goes on in the living families "
                  f"({alive}); {_guard_words(guard_now)}."),
        "owner_step": guard_step, "onset": last_birth}

    # gym_runs
    runs = int(swarm.get("gym_runs") or 0)
    out["gym_runs"] = {
        "stalled": runs < MIN_GYM_RUNS,
        "what": f"The Gym evaluated {runs} programs in the last {GYM_HOURS} h (fewer than {MIN_GYM_RUNS}).",
        "numbers": {f"gym_runs_{GYM_HOURS}h": runs, f"refused_or_failed_{GYM_HOURS}h": swarm.get("gym_not_run", 0),
                    "last_gym_run_at": swarm.get("last_gym_run_at"), f"researcher_cycles_{GYM_HOURS}h": swarm.get("cycles", 0),
                    "guard_braked": bool(guard_now.get("braked")), "heartbeat_age_min": beat_min},
        "doing": (f"Researchers ran {swarm.get('cycles', 0)} cycles in the last {GYM_HOURS} h; {_guard_words(guard_now)}; "
                  + ("the swarm's heartbeat is missing" if beat_min is None else f"the swarm's heartbeat is {beat_min} minutes old")
                  + ". The House restarts a swarm that stops, and research resumes by itself when the guard releases."),
        "owner_step": guard_step, "onset": None}

    # validations
    validation_runs, awaiting = int(swarm.get("validation_runs") or 0), int(swarm.get("awaiting") or 0)
    round_ = swarm.get("last_round")
    if round_:
        round_words = (f"The tournament's last round ({round_['at']}) queued {round_['queued']} and judged {round_['judged']}; "
                       f"{round_['waiting_robustness']} wait on their 1.5x robustness run, {round_['waiting_drift']} on the drift "
                       f"screen, {round_['errors']} failed on the Gym. A round runs every hour.")
    else:
        round_words = "No tournament round is on record."
    out["validations"] = {
        "stalled": validation_runs == 0 and awaiting > 0,
        "what": f"No Validation run in the last {VALIDATION_HOURS} h while {awaiting} living families hold a Train best "
                f"never validated.",
        "numbers": {f"validation_runs_{VALIDATION_HOURS}h": validation_runs, "awaiting_validation": awaiting,
                    "train_bests": swarm.get("train_bests", 0), "last_validation_at": swarm.get("last_validation_at"),
                    "last_round_at": (round_ or {}).get("at")},
        "doing": f"{round_words} {_first_up(_guard_words(guard_now))}.",
        "owner_step": guard_step, "onset": S.epoch(swarm.get("last_validation_at"))}

    # braked
    brake = swarm.get("brake") or {}
    hours = float(brake.get("hours") or 0.0)
    by_cause = brake.get("by_cause") or {}
    doing = [GUARD_DOING.get(c, f"{c}: the guard releases when it clears") for c in by_cause]
    out["braked"] = {
        "stalled": bool(brake.get("known")) and hours >= BRAKED_HOURS,
        "what": f"The Sail guard was braked {hours:.1f} of the last {BRAKE_WINDOW_HOURS} h "
                f"({', '.join(f'{c} {h:.1f} h' for c, h in by_cause.items()) or 'no cause named'}).",
        "numbers": {f"braked_hours_{BRAKE_WINDOW_HOURS}h": hours, "braked_now": bool(brake.get("braked_now")),
                    "braked_since": brake.get("braked_since"),
                    **{f"braked_hours_{c}"[:40]: h for c, h in by_cause.items()}},
        "doing": _first_up("; ".join(doing) or "the guard releases when its cause clears") + ".",
        "owner_step": _guard_step(by_cause), "onset": S.epoch(brake.get("braked_since"))}

    # runway_<meter>
    meters = (budget or {}).get("meters") if isinstance(budget, Mapping) else None
    for meter, word in METER_WORDS.items():
        row = (meters or {}).get(meter) if isinstance(meters, Mapping) else None
        row = row if isinstance(row, Mapping) else {}
        days = _finite(row.get("card_runway_days"))
        topup, research, ceiling_m = _finite(row.get("topup_usd")), _finite(row.get("research_usd_day")), _finite(row.get("ceiling_usd_day"))
        step = (f"top up {word}: about ${topup:.2f} buys {B.TOPUP_DAYS} more days of research at the ceiling"
                + (f" (the taper starts {row.get('card_date')})" if row.get("card_date") else "")) if topup is not None \
            else f"top up {word}"
        short = days is not None and days < RUNWAY_DAYS
        out[f"runway_{meter}"] = {
            "stalled": short,
            "what": f"{word} holds {'unknown' if days is None else f'{days:.1f}'} days of research at the ceiling above its "
                    f"reserve (under {RUNWAY_DAYS:g}).",
            "numbers": {"runway_days_at_ceiling": days, "runway_days_held": _finite(row.get("runway_days")),
                        "research_usd_day": research, "ceiling_usd_day": ceiling_m, "topup_usd": topup,
                        "card_date": row.get("card_date")},
            "doing": (f"The budget rule tapers research on {word} to what it holds"
                      + (f": {research:.2f} of its {ceiling_m:.2f} a day now" if research is not None and ceiling_m is not None else "")
                      + ". It never raises a cap or moves money."),
            "owner_step": step if short else None, "onset": None}

    # owner_deploy
    out["owner_deploy"] = {
        "stalled": deploy is not None,
        "what": ("Main's head changes files only the owner's deploy may change, and the updater keeps the running release."
                 if deploy else "No head of main waits for the owner's deploy."),
        "numbers": {} if not deploy else {
            "sha": deploy.get("sha"), "protected_files": len(deploy.get("files") or []),
            "first_refused_at": S.iso(deploy["first_at"]), "last_promoted_at": None if deploy.get("promoted_at") is None
            else S.iso(deploy["promoted_at"])},
        "doing": "The updater refuses each such head and keeps the running release; research and trading go on.",
        "owner_step": None if not deploy else (
            f"deploy main at {deploy.get('sha') or 'its head'} yourself (scripts/floor_box.py deploy): it changes "
            f"{', '.join((deploy.get('files') or [])[:3])}{' and more' if len(deploy.get('files') or []) > 3 else ''}, "
            "which the updater never deploys"),
        "onset": None if not deploy else deploy.get("first_at")}
    return out


# ---------------------------------------------------------------------------------------------- the notice
def notice_facts(cause: str, check: Mapping[str, Any], since: float | None, now: float) -> dict[str, Any]:
    """The `stall` notice's facts (the gateway composes the words, gateway/lib/email.mjs): the cause, the House's own
    sentence for it, the numbers, how long (hours, and since when), what the House is doing, the owner step or None."""
    # A figure is a count, a dollar or hour figure to two places, a time, yes or no, or a short token (the gateway echoes
    # only those, and an unknown one as unknown).
    numbers = {k: round(v, 2) if isinstance(v, float) else v for k, v in (check.get("numbers") or {}).items()}
    return {"kind": "stall", "notice_id": f"stall:{cause}", "cause": cause, "what": str(check.get("what") or ""),
            "numbers": numbers, "since": None if since is None else S.iso(since),
            "hours": None if since is None else _hours(now - since), "doing": str(check.get("doing") or ""),
            "owner_step": check.get("owner_step") or None, "at": S.iso(now)}


def _sent(answer: Any) -> tuple[bool, str]:
    if isinstance(answer, Mapping) and answer.get("sent") is True and answer.get("duplicate") is not True:
        return True, "sent"
    if isinstance(answer, Mapping) and answer.get("duplicate") is True:
        return False, "the gateway told this cause within 12 h by its own clock: tried again at the next run"
    reason = (answer or {}).get("reason") if isinstance(answer, Mapping) else None
    return False, str(reason or "the gateway did not send it")[:200]


def _notifier(ctx: Any) -> Callable[[Mapping[str, Any]], Any] | None:
    """The budget's funding notice's client (`budget._notifier`: `ltcm.notify.post_json` to the gateway's /v1/notify with
    the House's token), or the one the context hands in."""
    given = _get(ctx, "notify")
    if given is not None:
        return given
    config = _get(ctx, "config")
    return B._notifier(config if isinstance(config, Mapping) else {})


def _alert(ctx: Any, text: str) -> None:
    """A House warning through the job's context (`ctx.alert`, league/ops/context.py), when it has one."""
    alert = _get(ctx, "alert")
    if callable(alert):
        alert("warning", text[:900])


def run(ctx: Any) -> dict[str, Any]:
    """The job (the module docstring). `ctx` is the ops context (league/ops/context.py); it may also hand in `notify`
    (a callable posting one notice's facts) and `population_ceiling` (tests)."""
    root = Path(_get(ctx, "root"))
    base = Path(_get(ctx, "base") or root.parent)
    now = ctx.now() if callable(getattr(ctx, "now", None)) else float(_get(ctx, "now"))
    if not (root / F.SWARM_DB).exists():
        return {"status": "skipped", "why": f"no swarm store ({F.SWARM_DB}) in the state root"}
    errors: list[str] = []
    swarm = guard.read(root / F.SWARM_DB, lambda db: swarm_facts(db, now))
    ceiling, why = _ceiling(ctx, root)
    if why:
        errors.append(why)
    budget = read_json(root / "budget.json", None)
    if isinstance(budget, Mapping) and (_finite(budget.get("at")) is None or now - float(budget["at"]) > BUDGET_STALE_SECONDS):
        errors.append("budget.json is stale or undated: the runway is not read")
        budget = None
    found = checks(swarm, now=now, ceiling=ceiling, budget=budget if isinstance(budget, Mapping) else None,
                   deploy=owner_deploy(base), heartbeat=read_json(root / HEARTBEAT, None))

    state = read_json(root / STATE_FILE, {})
    state = state if isinstance(state, dict) else {}
    told = state.get("causes") if isinstance(state.get("causes"), dict) else {}
    notify = None
    notices, cleared, stalled = [], [], []
    for cause in CAUSES:
        check = found[cause]
        rec = dict(told.get(cause) or {})
        if not check["stalled"]:
            if rec.get("standing"):
                cleared.append(cause)
                rec.update(standing=False, cleared_at=S.iso(now))
            told[cause] = rec
            continue
        stalled.append(cause)
        if not rec.get("standing"):
            rec.update(standing=True, seen_at=S.iso(now))
        rec["last_seen"] = S.iso(now)
        onset = check.get("onset")
        since = onset if onset is not None and onset <= now else S.epoch(rec.get("seen_at"))
        sent_at, warned_at = S.epoch(rec.get("sent_at")), S.epoch(rec.get("warned_at"))
        facts = notice_facts(cause, check, since, now)
        outcome: dict[str, Any] = {"cause": cause, "sent": False}
        if sent_at is not None and 0 <= now - sent_at < NOTICE_EVERY_SECONDS:
            outcome["why"] = f"told at {S.iso(sent_at)}: at most once every 12 h"
        else:
            if notify is None:
                notify = _notifier(ctx) or False
            if notify is False:
                outcome["why"] = "no gateway to notify through"
                errors.append(f"stall notice for {cause} not sent: no gateway")
            else:
                try:
                    ok, words = _sent(notify(facts))
                except Exception as exc:  # noqa: BLE001 - not told: the next run tries again
                    ok, words = False, f"the notice failed ({type(exc).__name__} {getattr(exc, 'code', '') or ''})".replace(" )", ")")
                outcome.update(sent=ok, why=words)
                if ok:
                    rec.update(sent_at=S.iso(now), notice_id=facts["notice_id"])
                elif "within 12 h" not in words:
                    errors.append(f"stall notice for {cause} not sent: {words}")
        if warned_at is None or not 0 <= now - warned_at < NOTICE_EVERY_SECONDS:
            text = f"stall: {cause}: {check['what']} {check['doing']}"
            if check.get("owner_step"):
                text += f" Owner step: {check['owner_step']}."
            if not outcome["sent"] and outcome.get("why"):
                text += f" (notice: {outcome['why']})"
            _alert(ctx, text)
            rec["warned_at"] = S.iso(now)
            outcome["warned"] = True
        notices.append(outcome)
        told[cause] = rec
    write_json(root / STATE_FILE, {"schema": 1, "at": S.iso(now), "causes": told})
    return {"stalled": stalled, "cleared": cleared, "notices": notices,
            "checks": {c: {k: found[c][k] for k in ("stalled", "what", "numbers", "owner_step")} for c in CAUSES},
            "ceiling": ceiling, "errors": errors, "warning": bool(stalled or errors)}


__all__ = ["run", "checks", "swarm_facts", "owner_deploy", "notice_facts", "CAUSES", "BIRTH_HOURS", "GYM_HOURS",
           "MIN_GYM_RUNS", "VALIDATION_HOURS", "BRAKE_WINDOW_HOURS", "BRAKED_HOURS", "RUNWAY_DAYS", "NOTICE_EVERY_SECONDS",
           "STATE_FILE"]
