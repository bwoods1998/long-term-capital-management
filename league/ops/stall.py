"""The `stall` job (every 30 minutes, 24/7; the owner's goal of Oct 7, 2026, item 6): the floor raises an alarm when it
stalls, says what the House is doing about it, and says what only the owner can do.

From Oct 3 to Oct 7 research ran 1 to 13 Gym runs a day with no birth, and nobody was told: the House's one alarm (a
pre-open FAIL) went to a ledger row no mail carries. This job reads the House's own records every half hour and names
a STALL by its cause:

- `births`: no family was born in the last `BIRTH_HOURS` hours while the living population is under its ceiling
  (`population.ceiling` as the swarm's own settings load it, the budget's tightening included); the learning game's
  children count (they emit no `swarm.born`: their family rows' origin is "game");
- `gym_runs`: the Gym evaluated fewer than `MIN_GYM_RUNS` programs in the last `GYM_HOURS` hours (a run is a `runs` row
  with a trial whose status is not `funnel.NOT_RUN`: a run the Gym refused or failed is not one, nor a verdict read
  from an identical program's validation, F1, which writes rows with no trial);
- `validations`: no Validation verdict in the last `VALIDATION_HOURS` hours (no validation the Gym evaluated, no verdict
  read from an identical program, nothing a tournament round judged) while a living family is OWED one: its candidate
  (the version the tournament validates, `Tournament.candidate_version`: its submitted best, else the Train best the
  researcher picked by score, `state.best_train_version`) is not its validated version, and the last round within the
  window did not leave it waiting on its 1.5x robustness run or the drift screen (those are counted apart), nor named it
  as a game-arm family that waits for a CONFIRM (`waiting_game`: the learning game validates CONFIRMED versions only),
  nor as a direction family whose lineage's one Validation try is used or taken this round (`spent_lane`, `waiting_lane`:
  release D-1b's ration), or whose candidate's code names another open than a long call (`calls_refused`: release
  D-1b's calls-only code check), or an always-in family whose candidate has no G1 pass on record (`always_in_refused`:
  THE ALWAYS-IN CARD, Oct 10, 2026);
- `braked`: the Sail guard was braked `BRAKED_HOURS` or more of the last `BRAKE_WINDOW_HOURS` hours, whatever the cause
  (the budget's daily stop reached by noon keeps research from running round the clock as surely as a low balance);
- `runway_sail`, `runway_claude`: a meter's days of research left at the ceiling (`budget.json` `card_runway_days`: what it
  holds above its reserve at its fixed cost plus its share of the ceiling, the figure the funding notice reads) are under
  `RUNWAY_DAYS`. The owner step is the top-up, with the budget's own amount;
- `owner_deploy`: main's head and the running release differ in a file only the owner's deploy may change (the updater
  refused main's head as the owner's deploy, `deploys.jsonl` stage `vet`) and no release was promoted since. Either side
  may be ahead, so the owner step names both ways out. Since Oct 10, 2026 (the readiness audit's M12: the mail fired at
  16:20Z Oct 9 inside the operator's own 16:17-16:28Z deploy) a refusal counts only once it has stood
  `OWNER_DEPLOY_GRACE` (45 minutes), and not at all while a deploy is in flight (`deploy_flight`: a `deploys.jsonl`
  `start` row with no verdict yet, or the operator's own nightly stop, the owner deploy's step 2, under 2 hours old);
- `paused`: a maintenance pause (`<state>/PAUSE`) or a stopped swarm (`<state>/swarm.stop`) has stood `PAUSED_HOURS` or
  more. While either stands, births, Gym runs, Validations and the brake are not raised: a pause stops them by design;
- `grant_refused`: the standing grant refused to re-ratify (the `grant` job's receipts in `ops.sqlite`: a refusal since
  its last `ok` run). New real entries stay held until the owner ratifies;
- `kill_on`: the gateway's kill switch is on (`GET /v1/health` `kill_switch`): no real order, no Claude call and no merge
  until the owner lifts it. An unreadable health is no cause.

Since Oct 10, 2026 (the readiness audit's M6: the direction lane's alarms, K5, a Done checkpoint, a pre-open FAIL and a
dead nightly reached a ledger row no mail carries):
- `dlane`: the direction lane's report (`<state>/dlane-report.json`, the `dlane` job) carries a warning-level alarm
  (A1-A7, PL1 the program loss line, PT1 the $800 Probe total off roster 5, K5), or it is older than
  `DLANE_STALE_HOURS` while the lane is on. K5 holding (the lane reads shadow until it is cleared) or disarmed
  (`dlane.k5_clear` left true) is the owner's step;
- `done`: a FINAL Done checkpoint that holds (the report's `done.<meter>.checkpoints`, final and holding: frozen from
  report to report) that no SENT notice has told yet (`stall.json` `done_told`, which a notice carrying the cause adds
  to once the gateway says it sent it). News the owner hears at once (an owner line), never an owner step WAITING: the
  Done meter's item 7 does not count it (`dlane_report.NEWS_CAUSES`). Until the review of the weekend fixes (Oct 10,
  2026) it read the report's A8, which one report says once: a House start or a failed notice before the next stall
  run lost the claim;
- while the lane is off (`dlane.mode` "off": the dlane job writes no report, so its last one stays on disk) neither
  `dlane` nor `done` reads the report (the same review: the last report's K5 or A8 was mailed at every run for good);
- `preopen`: the latest pre-open receipt (ops.sqlite, at most `PREOPEN_HOURS` old) failed a check, or the job failed or
  was missed;
- `forward`: the nightly's ready file (`<state>/gym-forward.json`) does not carry the last session before today once
  the UTC day is `FORWARD_DUE_HOUR` hours in, the nightly's record (`<state>/data/nightly.json`) has carried an error
  `NIGHTLY_ERROR_HOURS` or more, or a nightly stop (`<state>/data/nightly.stop`) has stood `NIGHTLY_STOP_HOURS` or more
  (that one is the owner's step: the replay twins of the Done meter wait while it stands).

THE NOTICE: one `POST /v1/notify` kind `stall` a run at most, listing EVERY cause standing (`cause_facts` each: the
cause, the numbers, how long, what the House is doing about it, the owner step when one is needed), owner steps first,
through the same gateway client the budget's funding notice uses (`budget._notifier`). It is mailed:

- when some standing cause has an owner step: at once when one of them was not in the last owner notice, else at most
  once every `OWNER_EVERY_SECONDS` (12 h);
- when none has: at most once every `INFO_EVERY_SECONDS` (24 h) after the last notice of either kind.

The gateway holds the same pace by its own clock (it keys an owner notice on the owner causes, `stall:owner:<causes>`,
for 12 h, and one with none on `stall:info` for 24 h), so a lost state file never mails twice. A notice counts as told
only once the gateway says it SENT it: a `duplicate` answer (told inside the gateway's own window) is tried at the next
run. Each cause standing is also one House warning at most every `WARN_EVERY_SECONDS` (12 h). `<state>/stall.json`
(private) remembers each cause (since when it stands, when it was last warned of, when it cleared), the notices (when
the last of each kind was sent, which owner causes it told) and the Done checkpoints told (`done_told`). A cause that
clears is named in the receipt. The receipt carries every check, stalled or not, with its numbers.

HOW LONG: from the record when it says (the last birth, the last Validation verdict, the start of the guard's brake, the
first refusal of the owner's deploy or of the grant, the pause file, the kill), else from when this job first saw the
cause standing.

NEVER ACTS. The job reads (every SQLite open `mode=ro`, inside `guard.readonly()`; the gateway's `/v1/health`, a GET),
writes only `stall.json`, and posts only the notice: it moves no money, changes no setting, starts and stops nothing. It
runs in a maintenance pause too (read-only, like `preopen` and `clock`), so a pause left on is itself reported.
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
#: A maintenance pause or a stopped swarm standing this long is an owner step waiting.
PAUSED_HOURS = 6.0
#: The notice when some cause needs the owner: at once for a cause the last one did not tell, else this often at most.
OWNER_EVERY_SECONDS = 12 * 3600
#: The notice when no cause needs the owner: this often at most, after the last notice of either kind.
INFO_EVERY_SECONDS = 24 * 3600
#: One House warning a cause at most this often.
WARN_EVERY_SECONDS = 12 * 3600
#: A budget.json older than this is not read for the runway (the budget job has stopped: its own warnings say so).
BUDGET_STALE_SECONDS = 36 * 3600
STATE_FILE = "stall.json"
HEARTBEAT = "swarm.heartbeat"
OPS_DB = "ops.sqlite"
#: THE OWNER DEPLOY'S GRACE (Oct 10, 2026; the readiness audit's M12): a refusal of main's head counts as an owner step
#: only once it has stood this long. The operator's own release pushes main, then deploys: its refusal comes first.
OWNER_DEPLOY_GRACE = 45 * 60
#: A `deploys.jsonl` `start` row with no verdict is a deploy in flight this long at most (the canary, the promotion and
#: the ten-minute watch take about 12 minutes): an older one died unjudged.
DEPLOY_FLIGHT_SECONDS = 2 * 3600
#: The nightly forward daemon's stop file under the state root (league/watchdog.py NIGHTLY_STOP) and the markers
#: automation writes in it (`NIGHTLY_MARKERS`): any other content (an empty `touch`, `operator:<why>`) is the operator's.
NIGHTLY_STOP = Path("data") / "nightly.stop"
AUTOMATION_MARKERS = ("updater:", "drill:")
#: The operator's nightly stop younger than this says an owner deploy is in flight (docs/operations.md "Deploy", step 2);
#: any stop standing this long is the `forward` cause.
NIGHTLY_STOP_HOURS = 2.0
#: The nightly's ready file and record (scripts/data/nightly.py), under the state root.
FORWARD_READY = "gym-forward.json"
NIGHTLY_RECORD = Path("data") / "nightly.json"
#: The ready file must carry the last session before today once the UTC day is this many hours in (it lands ~06:14Z).
FORWARD_DUE_HOUR = 10
#: A nightly error standing this long is the `forward` cause.
NIGHTLY_ERROR_HOURS = 6.0
#: The direction lane's report (league/ops/dlane_report.py, written at the House's start, daily at 01:30Z and 30 minutes
#: before each open).
DLANE_REPORT = "dlane-report.json"
DLANE_STALE_HOURS = 30.0
#: The latest pre-open receipt is read while it is at most this old (the job runs an hour before each open).
PREOPEN_HOURS = 24.0
#: The files that pause the floor (the House's maintenance pause, `House.paused`; the swarm's stop file) and the step that
#: lifts each.
PAUSE_FILES = {"PAUSE": ("maintenance", "lift the maintenance pause once its work is done (scripts/floor_box.py maintenance off)"),
               "swarm.stop": ("swarm_stop", "remove state/swarm.stop once the swarm should run again (the House starts it then)")}
CAUSES = ("births", "gym_runs", "validations", "braked", "runway_sail", "runway_claude", "owner_deploy", "paused",
          "grant_refused", "kill_on", "dlane", "done", "preopen", "forward")
#: The causes a pause stops by design: not raised while the floor is paused.
RESEARCH_CAUSES = ("births", "gym_runs", "validations", "braked")
#: The causes that are news to the owner, not a stall nor a step WAITING (Oct 10, 2026): a Done checkpoint that holds is
#: mailed at once as an owner line, never counted against DONE-RULE item 7 (`dlane_report.NEWS_CAUSES`, held equal by a
#: test) nor listed among the stalls on the daily page (`scoreboard.funnel_lines`).
NEWS_CAUSES = ("done",)
METER_WORDS = {"sail": "Sail", "claude": "Claude (Anthropic)"}
#: The Sail guard's causes the owner alone can clear, and the step that clears each.
GUARD_STEPS = {"under_line": "top up Sail: the Sail guard brakes the whole swarm while the balance is under its line",
               "disk": "free disk on the House box: the Sail guard brakes the swarm while the state disk is under its line"}
KILL_STEP = "lift the gateway's kill switch once its cause is fixed (python3 scripts/gateway_admin.py unkill, your admin token)"
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
#: The grant job's error for a refusal (league/ops/grant.py `failed` after `LiveGrant.standing` answered `refused`).
_GRANT_REFUSED = "standing grant refused"
#: THE LEARNING GAME's children's origin (league/swarm/game.py `ORIGIN`; this job imports nothing of the swarm).
GAME_ORIGIN = "game"


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


def _within(at: float | None, now: float, seconds: float) -> bool:
    return at is not None and 0 <= now - at < seconds


def candidate(best_version: Any, state_text: Any) -> int | None:
    """The version the tournament validates for a family (`Tournament.candidate_version`): its submitted best, else the
    Train best the researcher picked by score (`state.best_train_version`), else None."""
    if best_version:
        return int(best_version)
    try:
        state = json.loads(state_text) if isinstance(state_text, str) else state_text
    except (TypeError, ValueError):
        return None
    value = state.get("best_train_version") if isinstance(state, Mapping) else None
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------------------------- the reads
def swarm_facts(db: Any, now: float) -> dict[str, Any]:
    """What the checks read from the swarm's store, in one read transaction (`guard.read`)."""
    iso = lambda hours: S.iso(now - hours * 3600)  # noqa: E731
    one = lambda sql, params=(): (guard.ids(db, sql, params) or [None])[0]  # noqa: E731
    marks = ",".join("?" * len(F.NOT_RUN))
    #: A Gym evaluation: a row with a trial the Gym neither refused nor failed (an F1 verdict's rows carry no trial).
    evaluated = f"status NOT IN ({marks}) AND trials > 0"
    out: dict[str, Any] = {}
    out["births"] = int(one("SELECT count(*) FROM events WHERE kind='swarm.born' AND at>=?", (iso(BIRTH_HOURS),)) or 0)
    out["last_birth_at"] = one("SELECT max(at) FROM events WHERE kind='swarm.born'")
    # THE LEARNING GAME's children (league/swarm/game.py `ORIGIN`) are births too, though they emit no `swarm.born`.
    children = int(one("SELECT count(*) FROM families WHERE origin=? AND born_at>=?", (GAME_ORIGIN, iso(BIRTH_HOURS))) or 0)
    if children:
        out["births"] += children
    last_child = one("SELECT max(born_at) FROM families WHERE origin=?", (GAME_ORIGIN,))
    if last_child and (out["last_birth_at"] is None or str(last_child) > str(out["last_birth_at"])):
        out["last_birth_at"] = last_child
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
    runs = guard.rows(db, "SELECT status, trials > 0 AS trial, count(*) AS n FROM runs WHERE at>=? GROUP BY status, trials > 0",
                      (iso(GYM_HOURS),))
    out["gym_runs"] = sum(int(r["n"] or 0) for r in runs if r["status"] not in F.NOT_RUN and r["trial"])
    out["gym_not_run"] = sum(int(r["n"] or 0) for r in runs if r["status"] in F.NOT_RUN)
    out["gym_no_trial"] = sum(int(r["n"] or 0) for r in runs if r["status"] not in F.NOT_RUN and not r["trial"])
    out["last_gym_run_at"] = one(f"SELECT max(at) FROM runs WHERE {evaluated}", F.NOT_RUN)
    out["cycles"] = int(one("SELECT count(*) FROM events WHERE kind='swarm.cycle' AND at>=?", (iso(GYM_HOURS),)) or 0)
    since_v = iso(VALIDATION_HOURS)
    out["validation_runs"] = int(one(f"SELECT count(*) FROM runs WHERE \"window\"='validation' AND at>=? AND {evaluated}",
                                     (since_v, *F.NOT_RUN)) or 0)
    out["validation_inherited"] = int(one(f"SELECT count(*) FROM runs WHERE \"window\"='validation' AND at>=? AND status NOT IN "
                                          f"({marks}) AND trials = 0", (since_v, *F.NOT_RUN)) or 0)
    # The last verdict with a row: a validation the Gym evaluated or one read from an identical program (F1).
    out["last_validation_at"] = one(f"SELECT max(at) FROM runs WHERE \"window\"='validation' AND status NOT IN ({marks})",
                                    F.NOT_RUN)
    judged = 0
    for verdicts in F.json_rows(db, "swarm.tournament", "$.validation.judged", since_v, S.iso(now + 1)):
        judged += len(verdicts) if isinstance(verdicts, Mapping) else 0
    out["judged"] = judged
    awaiting: list[str] = []
    bests = 0
    for fam in guard.rows(db, "SELECT id, best_version, validated_version, state FROM families WHERE retired_at IS NULL"):
        n = candidate(fam["best_version"], fam["state"])
        if n is None:
            continue
        bests += 1
        if fam["validated_version"] is None or int(fam["validated_version"]) != n:
            awaiting.append(str(fam["id"]))
    out["train_bests"], out["awaiting_ids"] = bests, awaiting
    last = guard.rows(db, "SELECT at, payload FROM events WHERE kind='swarm.tournament' ORDER BY seq DESC LIMIT 1")
    round_ = None
    if last:
        try:
            validation = (json.loads(last[0]["payload"]) or {}).get("validation") or {}
        except (TypeError, ValueError, AttributeError):
            validation = {}
        validation = validation if isinstance(validation, Mapping) else {}
        ids = lambda value: sorted({str(v) for v in value}) if isinstance(value, (list, dict)) else []  # noqa: E731
        round_ = {"at": last[0]["at"], "queued": int(_finite(validation.get("queued")) or 0),
                  "judged": len(ids(validation.get("judged"))), "waiting_robustness": ids(validation.get("waiting_robustness")),
                  "waiting_drift": ids(validation.get("waiting_drift")), "waiting_twin": ids(validation.get("waiting_twin")),
                  "waiting_game": ids(validation.get("waiting_game")),
                  # THE DIRECTION LANE'S RATION (release D-1b): a direction lineage's one try is used (`spent_lane`),
                  # or another member took this round's (`waiting_lane`): owed no Validation now. Nor is a direction
                  # candidate whose code names another open than a long call (`calls_refused`, the review's finding 3).
                  "spent_lane": sorted(set(ids(validation.get("spent_lane"))) | set(ids(validation.get("waiting_lane")))
                                       | set(ids(validation.get("calls_refused")))
                                       | set(ids(validation.get("always_in_refused")))),
                  "errors": len(ids(validation.get("errors")))}
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


def pause_facts(root: str | Path) -> dict[str, float]:
    """{"maintenance": since, "swarm_stop": since} for each pause file in the state root (its mtime), absent when none."""
    out: dict[str, float] = {}
    for name, (key, _) in PAUSE_FILES.items():
        try:
            out[key] = (Path(root) / name).stat().st_mtime
        except OSError:
            continue
    return out


def grant_facts(root: str | Path) -> dict[str, Any] | None:
    """The standing grant's refusals since its last `ok` run (the `grant` job's receipts in `ops.sqlite`, read-only):
    {refusals, first_at, last_at, why, last_ok_at}; None with no receipts store. A run that failed for another reason (a
    reading the gateway could not give) neither counts nor clears; a `skipped` one (a pause) is passed over."""
    path = Path(root) / OPS_DB
    if not path.exists():
        return None

    def read(db: Any) -> list[dict[str, Any]]:
        return guard.rows(db, "SELECT due_at, finished_at, status, error FROM runs WHERE job='grant' AND status IN ('ok', 'failed') "
                              "ORDER BY due_at DESC, id DESC LIMIT 500")

    refused: list[dict[str, Any]] = []
    last_ok = None
    for row in guard.read(path, read):
        if row["status"] == "ok":
            last_ok = row["finished_at"] or row["due_at"]
            break
        if _GRANT_REFUSED in str(row["error"] or ""):
            refused.append(row)
    if not refused:
        return {"refusals": 0, "last_ok_at": last_ok}
    text = str(refused[0]["error"] or "")
    why = text[text.index(_GRANT_REFUSED) + len(_GRANT_REFUSED):].lstrip(": ").split(" (grant ", 1)[0]
    return {"refusals": len(refused), "first_at": S.epoch(refused[-1]["finished_at"] or refused[-1]["due_at"]),
            "last_at": S.epoch(refused[0]["finished_at"] or refused[0]["due_at"]), "why": why[:200], "last_ok_at": last_ok}


def kill_facts(health: Any) -> dict[str, Any] | None:
    """{on, since} from the gateway's `/v1/health` (`kill_switch`; the latest `kill` in `admin_log`), None unreadable."""
    if not isinstance(health, Mapping) or not isinstance(health.get("kill_switch"), bool):
        return None
    since = None
    log = health.get("admin_log")
    for entry in (log.get("last") if isinstance(log, Mapping) else None) or []:  # newest first
        if isinstance(entry, Mapping) and entry.get("action") == "kill":
            since = S.epoch(entry.get("at"))
            break
    return {"on": health["kill_switch"], "since": since}


def _marker(path: Path) -> str | None:
    """What a nightly stop says (stripped; "" for an empty `touch`), None with no stop, "?" when it cannot be read."""
    try:
        return path.read_bytes()[:256].decode("utf-8", "replace").strip()
    except FileNotFoundError:
        return None
    except OSError:
        return "?"


def deploy_flight(base: str | Path, root: str | Path, now: float) -> dict[str, Any] | None:
    """A DEPLOY IN FLIGHT (Oct 10, 2026; the readiness audit's M12), or None: the newest `deploys.jsonl` `start` row whose
    deploy has no `verdict` (nor `interrupted`) row yet and is at most `DEPLOY_FLIGHT_SECONDS` old (the watchdog stages,
    canaries, promotes and watches: the owner's deploy and the updater's alike), else the operator's own nightly stop
    (`<state>/data/nightly.stop` with no automation marker: the owner deploy's step 2) at most `NIGHTLY_STOP_HOURS` old.
    {how, since, deploy or marker}."""
    starts: dict[str, float] = {}
    try:
        with (Path(base) / "deploys.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                if '"start"' not in line and '"verdict"' not in line and '"interrupted"' not in line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                key, at = str(row.get("deploy") or ""), S.epoch(row.get("at"))
                if not key or at is None:
                    continue
                if row.get("stage") == "start":
                    starts[key] = at
                elif row.get("stage") in ("verdict", "interrupted"):
                    starts.pop(key, None)
    except OSError:
        pass
    live = [(at, key) for key, at in starts.items() if 0 <= now - at <= DEPLOY_FLIGHT_SECONDS]
    if live:
        at, key = max(live)
        return {"how": "a deploy is in flight (deploys.jsonl: started, no verdict yet)", "since": at, "deploy": key[:80]}
    stop = Path(root) / NIGHTLY_STOP
    marker = _marker(stop)
    if marker is not None and not marker.startswith(AUTOMATION_MARKERS):
        try:
            since = stop.stat().st_mtime
        except OSError:
            return None
        if 0 <= now - since <= NIGHTLY_STOP_HOURS * 3600:
            return {"how": "the operator's nightly stop stands (the owner deploy's step 2)", "since": since,
                    "marker": marker[:80]}
    return None


def dlane_facts(root: str | Path) -> dict[str, Any] | None:
    """The direction lane's report as the `dlane` and `done` causes read it: {at, alarms, k5, mode, done_final}, None with
    no report. `done_final` is every FINAL checkpoint that holds ({meter, at_close}: `done.<all|screen>.checkpoints` with
    `final` and `holds` true), the report's own record of a Done claim: a final reading is frozen from report to report
    (DONE-RULE-A1 A1.4), where its A8 alarm is said by one report only."""
    doc = read_json(Path(root) / DLANE_REPORT, None)
    if not isinstance(doc, Mapping):
        return None
    alarms = [a for a in doc.get("alarms") or [] if isinstance(a, Mapping) and a.get("id")]
    k5 = doc.get("k5") if isinstance(doc.get("k5"), Mapping) else {}
    done = doc.get("done") if isinstance(doc.get("done"), Mapping) else {}
    final = []
    for name in ("all", "screen"):
        meter = done.get(name) if isinstance(done.get(name), Mapping) else {}
        for cp in meter.get("checkpoints") or []:
            if isinstance(cp, Mapping) and cp.get("holds") is True and cp.get("final") is True:
                final.append({"meter": f"done_{name}", "at_close": cp.get("at_close")})
    return {"at": S.epoch(doc.get("at")), "alarms": alarms, "k5": dict(k5),
            "mode": ((doc.get("lane") or {}) if isinstance(doc.get("lane"), Mapping) else {}).get("mode"),
            "done_final": final}


def preopen_facts(root: str | Path) -> dict[str, Any] | None:
    """The latest pre-open receipt (ops.sqlite, read-only): {due_at, status, failed, headlines, error}, None without one."""
    path = Path(root) / OPS_DB
    if not path.exists():
        return None
    rows = guard.read(path, lambda db: guard.rows(db, "SELECT due_at, status, summary_json, error FROM runs WHERE "
                                                      "job='preopen' ORDER BY due_at DESC, id DESC LIMIT 1"))
    if not rows:
        return None
    row = rows[0]
    try:
        summary = json.loads(row["summary_json"]) if row["summary_json"] else {}
    except (TypeError, ValueError):
        summary = {}
    summary = summary if isinstance(summary, Mapping) else {}
    failed = [str(f) for f in summary.get("failed") or []]
    headlines = {}
    for check in summary.get("checks") or []:
        if isinstance(check, Mapping) and check.get("ok") is False:
            headlines[f"{check.get('n')} {check.get('name')}"] = str(check.get("headline") or "")[:160]
    return {"due_at": S.epoch(row["due_at"]), "status": str(row["status"] or ""), "failed": failed,
            "headlines": headlines, "error": str(row["error"] or "")[:200] or None}


def last_session_before(day: Any) -> str | None:
    """The last NYSE session strictly before `day` (an ISO day or a date), None when none in 14 days."""
    import datetime as dt

    from ltcm.data import us_equity_session

    d = day if isinstance(day, dt.date) else dt.date.fromisoformat(str(day))
    for back in range(1, 15):
        if us_equity_session(d - dt.timedelta(days=back)) is not None:
            return (d - dt.timedelta(days=back)).isoformat()
    return None


def forward_facts(root: str | Path) -> dict[str, Any]:
    """What the `forward` cause reads: the nightly's ready file's day and time, its record's error, and its stop file
    ({ready_day, ready_at, error, record_day, stop_marker, stop_since}); each absent part None."""
    root = Path(root)
    ready = read_json(root / FORWARD_READY, None)
    record = read_json(root / NIGHTLY_RECORD, None)
    out: dict[str, Any] = {"ready_day": None, "ready_at": None, "error": None, "record_day": None,
                           "stop_marker": _marker(root / NIGHTLY_STOP), "stop_since": None}
    if isinstance(ready, Mapping):
        out["ready_day"], out["ready_at"] = ready.get("day"), ready.get("ready_at")
    if isinstance(record, Mapping):
        out["error"] = None if record.get("error") in (None, "") else str(record.get("error"))[:200]
        out["record_day"] = record.get("day")
    if out["stop_marker"] is not None:
        try:
            out["stop_since"] = (root / NIGHTLY_STOP).stat().st_mtime
        except OSError:
            pass
    return out


def _health(ctx: Any) -> Any:
    """The gateway's `/v1/health` (a GET with the House's token), or None when it cannot be read; a context may hand in
    `health` (tests)."""
    given = _get(ctx, "health")
    if given is not None:
        return given() if callable(given) else given
    try:
        return ctx.gateway.get("/v1/health")
    except Exception:  # noqa: BLE001 - an unreadable health raises no kill cause
        return None


def _lane_on(ctx: Any, root: Path) -> bool | None:
    """The direction lane is on (`dlane.mode` not "off", as the swarm loads its settings), None when that cannot be read;
    a context may hand in `lane_on` (tests)."""
    given = _get(ctx, "lane_on")
    if given is not None:
        return bool(given)
    try:
        from ..swarm import dlane as dlane_mod
        from ..swarm import settings as settings_mod

        config = _get(ctx, "config")
        with guard.readonly():
            loaded = settings_mod.load(root, config=config if isinstance(config, Mapping) else None)
        return dlane_mod.on(loaded)
    except Exception:  # noqa: BLE001 - unknown: a stale report is still said
        return None


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
           deploy: Mapping[str, Any] | None, heartbeat: Mapping[str, Any] | None, pause: Mapping[str, float] | None = None,
           grant: Mapping[str, Any] | None = None, kill: Mapping[str, Any] | None = None,
           flight: Mapping[str, Any] | None = None, dlane: Mapping[str, Any] | None = None, lane_on: bool | None = None,
           preopen: Mapping[str, Any] | None = None, forward: Mapping[str, Any] | None = None,
           nightly_error_since: float | None = None, done_told: Any = ()) -> dict[str, dict[str, Any]]:
    """Every cause's check: {stalled, what, numbers, doing, owner_step, onset (epoch or None)}. Pure."""
    out: dict[str, dict[str, Any]] = {}
    guard_now = swarm.get("guard") or {}
    killed = bool(kill and kill.get("on") is True)
    # What blocks research that only the owner can lift: the guard braked under its line or for disk, or the kill switch.
    research_step = (_guard_step(guard_now.get("causes")) if guard_now.get("braked") else None) or (KILL_STEP if killed else None)
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
        "owner_step": research_step, "onset": last_birth}

    # gym_runs
    runs = int(swarm.get("gym_runs") or 0)
    out["gym_runs"] = {
        "stalled": runs < MIN_GYM_RUNS,
        "what": f"The Gym evaluated {runs} programs in the last {GYM_HOURS} h (fewer than {MIN_GYM_RUNS}).",
        "numbers": {f"gym_runs_{GYM_HOURS}h": runs, f"refused_or_failed_{GYM_HOURS}h": swarm.get("gym_not_run", 0),
                    f"no_trial_rows_{GYM_HOURS}h": swarm.get("gym_no_trial", 0),
                    "last_gym_run_at": swarm.get("last_gym_run_at"), f"researcher_cycles_{GYM_HOURS}h": swarm.get("cycles", 0),
                    "guard_braked": bool(guard_now.get("braked")), "heartbeat_age_min": beat_min},
        "doing": (f"Researchers ran {swarm.get('cycles', 0)} cycles in the last {GYM_HOURS} h; {_guard_words(guard_now)}; "
                  + ("the swarm's heartbeat is missing" if beat_min is None else f"the swarm's heartbeat is {beat_min} minutes old")
                  + ". The House restarts a swarm that stops, and research resumes by itself when the guard releases."),
        "owner_step": research_step, "onset": None}

    # validations
    validation_runs, judged = int(swarm.get("validation_runs") or 0), int(swarm.get("judged") or 0)
    inherited = int(swarm.get("validation_inherited") or 0)
    awaiting = [str(f) for f in swarm.get("awaiting_ids") or []]
    round_ = swarm.get("last_round")
    recent = bool(round_) and _within(S.epoch(round_.get("at")), now, VALIDATION_HOURS * 3600)
    robust = set(round_.get("waiting_robustness") or []) if recent else set()
    drift = set(round_.get("waiting_drift") or []) | set(round_.get("waiting_twin") or []) if recent else set()
    waiting_robustness = [f for f in awaiting if f in robust]
    waiting_drift = [f for f in awaiting if f in drift and f not in robust]
    # THE LEARNING GAME: a game-arm family in "gate" is owed a Validation only for a CONFIRMED version, so the round's
    # `waiting_game` (no CONFIRM yet, or its tries used) owes none.
    game = set(round_.get("waiting_game") or []) if recent else set()
    # THE DIRECTION LANE'S RATION (release D-1b): a direction family whose lineage's one Validation try is used owes none.
    game |= set(round_.get("spent_lane") or []) if recent else set()
    owed = [f for f in awaiting if f not in robust and f not in drift and f not in game]
    if round_:
        round_words = (f"The tournament's last round ({round_['at']}) queued {round_['queued']} and judged {round_['judged']}; "
                       f"{len(round_.get('waiting_robustness') or [])} wait on their 1.5x robustness run, "
                       f"{len(round_.get('waiting_drift') or [])} on the drift screen, {round_['errors']} failed on the Gym. "
                       "A round runs every hour.")
    else:
        round_words = "No tournament round is on record."
    out["validations"] = {
        "stalled": validation_runs == 0 and judged == 0 and inherited == 0 and len(owed) > 0,
        "what": f"No Validation verdict in the last {VALIDATION_HOURS} h while {len(owed)} living families are owed one (a "
                f"candidate never validated, not waiting on its robustness run or the drift screen).",
        "numbers": {f"validation_runs_{VALIDATION_HOURS}h": validation_runs, f"verdicts_judged_{VALIDATION_HOURS}h": judged,
                    f"verdicts_inherited_rows_{VALIDATION_HOURS}h": inherited, "owed_validation": len(owed),
                    "waiting_robustness": len(waiting_robustness), "waiting_drift": len(waiting_drift),
                    "train_bests": swarm.get("train_bests", 0), "last_validation_at": swarm.get("last_validation_at"),
                    "last_round_at": (round_ or {}).get("at")},
        "doing": f"{round_words} {_first_up(_guard_words(guard_now))}.",
        "owner_step": research_step, "onset": S.epoch(swarm.get("last_validation_at"))}

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

    # owner_deploy: which side is ahead is not in the record, so the step names both ways out. THE GRACE AND THE FLIGHT
    # (Oct 10, 2026; the readiness audit's M12): a refusal counts once it has stood `OWNER_DEPLOY_GRACE`, and never while
    # a deploy is in flight (`deploy_flight`), so the operator's own release (push main, then deploy) mails nothing.
    files = (deploy or {}).get("files") or []
    named = f"{', '.join(files[:3])}{' and more' if len(files) > 3 else ''}"
    young = bool(deploy) and now - float(deploy["first_at"]) < OWNER_DEPLOY_GRACE
    waiting = deploy is not None and not young and not flight
    held = ("" if not deploy or waiting else
            f" Not an owner step yet: {flight['how']} since {S.iso(flight['since'])}." if flight else
            f" Not an owner step yet: refused {_hours(now - float(deploy['first_at']))} h ago, inside the "
            f"{OWNER_DEPLOY_GRACE // 60}-minute grace.")
    out["owner_deploy"] = {
        "stalled": waiting,
        "what": ("Main's head and the running release differ in files only the owner's deploy may change: the updater "
                 "refuses main's head and keeps the running release." + held if deploy else
                 "No head of main waits for the owner's deploy."),
        "numbers": {} if not deploy else {
            "sha": deploy.get("sha"), "protected_files": len(files),
            "first_refused_at": S.iso(deploy["first_at"]), "last_promoted_at": None if deploy.get("promoted_at") is None
            else S.iso(deploy["promoted_at"]), "deploy_in_flight": bool(flight),
            "grace_minutes": OWNER_DEPLOY_GRACE // 60},
        "doing": "The updater refuses each such head and keeps the running release; research and trading go on.",
        "owner_step": None if not waiting else (
            f"main's head {deploy.get('sha') or ''} and the running release differ in {named}: if main is ahead, deploy it "
            "yourself (scripts/floor_box.py deploy); if the running release is ahead, merge it to main instead"),
        "onset": None if not deploy else deploy.get("first_at")}

    # paused: a pause stops research by design, so its causes wait while it stands; one left on is the owner's step.
    pause = dict(pause or {})
    since = min(pause.values()) if pause else None
    long_ = since is not None and now - since >= PAUSED_HOURS * 3600
    steps = [step for key, step in PAUSE_FILES.values() if key in pause]
    out["paused"] = {
        "stalled": long_,
        "what": (f"The floor has been paused {_hours(now - since)} h ("
                 + " and ".join(w for k, w in (("maintenance", "a maintenance pause"), ("swarm_stop", "the swarm stopped"))
                                if k in pause) + ")." if since is not None else "The floor is not paused."),
        "numbers": {"maintenance_pause": "maintenance" in pause, "swarm_stopped": "swarm_stop" in pause,
                    "paused_since": None if since is None else S.iso(since)},
        "doing": ("The House keeps ticking (reconciliation, marks, exits); births, paid research and new entries wait for the "
                  "pause, so no research stall is raised while it stands."),
        "owner_step": "; ".join(steps) if long_ else None, "onset": since}
    if since is not None:
        for cause in RESEARCH_CAUSES:
            out[cause].update(stalled=False, paused=True)

    # grant_refused
    grant = grant or {}
    refusals = int(grant.get("refusals") or 0)
    out["grant_refused"] = {
        "stalled": refusals > 0,
        "what": (f"The standing grant refused to re-ratify ({refusals} times since its last good run): new real entries stay "
                 "held until the owner ratifies." if refusals else "The standing grant holds."),
        "numbers": {"grant_refusals": refusals, "first_refused_at": None if grant.get("first_at") is None else S.iso(grant["first_at"]),
                    "last_refused_at": None if grant.get("last_at") is None else S.iso(grant["last_at"]),
                    "last_ok_at": grant.get("last_ok_at")},
        "doing": "The grant job asks again every hour and at each House start; research, practice and exits go on.",
        "owner_step": (f"ratify the grant by hand on the box once you have read why it refused (python3 scripts/live_trading.py "
                       f"--ratify): {grant.get('why') or 'see the grant receipt'}") if refusals else None,
        "onset": grant.get("first_at")}

    # kill_on
    out["kill_on"] = {
        "stalled": killed,
        "what": ("The gateway's kill switch is on: it forwards no real order, makes no Claude call and merges no pull request."
                 if killed else "The gateway's kill switch is off." if kill else "The gateway's health could not be read."),
        "numbers": {"kill_switch": "unknown" if kill is None else bool(kill.get("on")),
                    "killed_at": None if not kill or kill.get("since") is None else S.iso(kill["since"])},
        "doing": "Research that calls no Claude model goes on; Claude research, real entries and the engineer's merges wait.",
        "owner_step": KILL_STEP if killed else None, "onset": (kill or {}).get("since")}
    out.update(_lane_checks(now, dlane, lane_on, done_told))
    out["preopen"] = _preopen_check(now, preopen)
    out["forward"] = _forward_check(now, forward, nightly_error_since)
    return out


K5_STEP = ("the direction lane reads shadow while K5 holds (no new direction Candidate, no incubator direction mark): "
           "read its losses in dlane-report.json, then clear it if the lane should trade again (swarm.json "
           "dlane.k5_clear true for one dlane run, then take it out; or delete the swarm store's kv dlane_k5)")
K5_DISARMED_STEP = "take dlane.k5_clear out of swarm.json: while it is true K5 cannot trip, whatever the lane loses"
LANE_OFF_WHAT = "The direction lane is off (dlane.mode): its last report is not read."
DONE_STEP = ("Done holds at a FINAL checkpoint ({named}): read the claim in dlane-report.json (done.<meter>.latest, beside "
             "P(Done | zero edge), the same-risk buy-and-hold and Net after costs); the plan to scale follows from it")


def done_key(meter: Any, at_close: Any) -> str:
    """A Done checkpoint's key in stall.json's `done_told` ("done_all:30")."""
    return f"{meter}:{at_close}"


def _lane_checks(now: float, dlane: Mapping[str, Any] | None, lane_on: bool | None,
                 done_told: Any = ()) -> dict[str, dict[str, Any]]:
    """`dlane` and `done` (the module docstring), from the direction lane's report (`dlane_facts`) and the Done checkpoints
    already told (`done_told`, stall.json). Pure.

    THE LANE OFF (the review of the weekend fixes, Oct 10, 2026): with `dlane.mode` "off" the dlane job writes no report,
    so the last one stays on disk for good; reading its alarms raised `dlane` (K5's owner step for a lane that is off)
    and `done` at every run until someone deleted the file. While the lane is off neither cause reads the report.

    THE DONE CLAIM, KEPT UNTIL TOLD (same review): the `done` cause read the report's A8, which one report says once (it
    is deduplicated against the previous report), so a House start or a failed notice before the next stall run lost the
    claim to a ledger row. It reads the report's FINAL holding checkpoints instead (frozen from report to report) and
    stands for each one no SENT notice has told yet (`run` records them in stall.json's `done_told`)."""
    report = dict(dlane or {})
    off = lane_on is False
    at = report.get("at")
    age = None if at is None else max(0.0, now - float(at))
    stale = bool(report) and not off and (age is None or age > DLANE_STALE_HOURS * 3600)
    alarms = [] if off else report.get("alarms") or []
    warnings = [a for a in alarms if a.get("level") == "warning"]
    k5_alarm = next((a for a in warnings if a.get("id") == "K5"), None)
    k5 = {} if off else report.get("k5") or {}
    step = None
    if k5_alarm is not None:
        step = K5_DISARMED_STEP if k5_alarm.get("disarmed") or (k5.get("cleared") and not k5.get("tripped")) else K5_STEP
    texts = "; ".join(f"{a.get('id')}: {str(a.get('text') or '')[:160]}" for a in warnings[:4])
    if off:
        what = LANE_OFF_WHAT
    elif report:
        what = ((f"The direction lane's report of {S.iso(at) if at is not None else 'an unknown time'} raised "
                 f"{len(warnings)} warnings ({texts})." if warnings else "The direction lane's report raised no warning.")
                + ((f" The report is {_hours(age)} h old" if age is not None else " The report carries no time")
                   + ": the dlane job has not written it since." if stale else ""))
    else:
        what = "No direction lane report on record."
    dlane_out = {
        "stalled": bool(warnings) or stale,
        "what": what,
        "numbers": {"alarms": ",".join(str(a.get("id")).lower() for a in warnings)[:80] or "none",
                    "report_at": None if at is None else S.iso(at),
                    "report_age_hours": None if age is None else round(age / 3600.0, 1),
                    "k5": "off" if off else "tripped" if k5.get("tripped") else "disarmed" if k5.get("cleared") else "armed",
                    "lane_mode": "off" if off else str(report.get("mode") or "unknown")[:20]},
        "doing": ("The dlane job writes the report at the House's start, daily at 01:30Z and 30 minutes before each open, "
                  "each alarm a House warning. It moves no money: K5 and the program loss line (PL1, DONE-RULE-A1 A1.3) "
                  "only tighten, and exits go on. With the lane off it writes no report and still holds the program loss "
                  "line."),
        "owner_step": step, "onset": None}
    told = {str(k) for k in done_told or ()}
    pending = [] if off else [c for c in report.get("done_final") or [] if done_key(c.get("meter"), c.get("at_close"))
                              not in told]
    named = ", ".join(f"{c.get('meter')} at close {c.get('at_close')}" for c in pending[:2])
    done_out = {
        "stalled": bool(pending),
        "what": (f"Done criteria hold at a FINAL checkpoint ({named}): DONE-RULE items 3, 4 (consistency measured, A1.1) "
                 "and 7 (research 24/7), read on final inputs (A1.4)." if pending else
                 LANE_OFF_WHAT if off else "No untold Done checkpoint holds."),
        "numbers": {"checkpoints": ",".join(done_key(c.get("meter"), c.get("at_close")) for c in pending)[:80] or "none",
                    "report_at": None if at is None else S.iso(at)},
        "doing": "The House trades on by its pre-registered rules: no program or route is paused, slowed or stopped to "
                 "protect the figure (DONE-RULE item 5).",
        "owner_step": DONE_STEP.format(named=named) if pending else None, "onset": at if pending else None,
        # Not in the receipt: what `run` records as told once a notice carrying this cause is SENT.
        "keys": [done_key(c.get("meter"), c.get("at_close")) for c in pending]}
    return {"dlane": dlane_out, "done": done_out}


def _preopen_check(now: float, preopen: Mapping[str, Any] | None) -> dict[str, Any]:
    """`preopen` (the module docstring), from the latest pre-open receipt (`preopen_facts`). Pure."""
    row = dict(preopen or {})
    due = row.get("due_at")
    recent = due is not None and 0 <= now - float(due) <= PREOPEN_HOURS * 3600
    broke = recent and row.get("status") in ("failed", "missed")
    failed = list(row.get("failed") or []) if recent else []
    lines = "; ".join(f"{name}: {line}" if line else name for name, line in list((row.get("headlines") or {}).items())[:4])
    return {
        "stalled": bool(broke or failed),
        "what": (f"The pre-open checks of {S.iso(due)} did not run ({row.get('status')}: {row.get('error') or 'no detail'})."
                 if broke else f"The pre-open checks of {S.iso(due)} failed {len(failed)} of them ({lines or ', '.join(failed)})."
                 if failed else "The latest pre-open checks passed." if recent else "No pre-open receipt in the last day."),
        "numbers": {"failed_checks": ",".join(f.replace(" ", "_") for f in failed)[:80] or "none",
                    "preopen_due_at": None if due is None else S.iso(due), "preopen_status": row.get("status") or "none"},
        "doing": ("Each FAIL is a House warning; the House trades on by its own stops and the grant (a pre-open FAIL "
                  "blocks nothing by itself). The checks run again an hour before the next open."),
        "owner_step": None, "onset": due if (broke or failed) else None}


def _forward_check(now: float, forward: Mapping[str, Any] | None, error_since: float | None) -> dict[str, Any]:
    """`forward` (the module docstring), from the nightly's files (`forward_facts`). Pure but for the session calendar."""
    import datetime as dt

    f = dict(forward or {})
    today = dt.datetime.fromtimestamp(now, dt.timezone.utc)
    late = expected = None
    if f.get("ready_day"):
        ref = today.date() if today.hour >= FORWARD_DUE_HOUR else today.date() - dt.timedelta(days=1)
        try:
            expected = last_session_before(ref)
        except Exception:  # noqa: BLE001 - no calendar: no lateness raised
            expected = None
        late = expected is not None and str(f["ready_day"]) < expected
    erring = f.get("error") is not None and error_since is not None and now - error_since >= NIGHTLY_ERROR_HOURS * 3600
    stop_since = f.get("stop_since")
    stopped = stop_since is not None and now - float(stop_since) >= NIGHTLY_STOP_HOURS * 3600
    marker = f.get("stop_marker")
    parts = []
    if late:
        parts.append(f"the nightly's ready file carries {f['ready_day']}, not the last session {expected}")
    if erring:
        parts.append(f"the nightly's record has carried an error for {_hours(now - float(error_since))} h "
                     f"({str(f.get('error'))[:120]})")
    if stopped:
        parts.append(f"a nightly stop ({marker!r}) has stood {_hours(now - float(stop_since))} h")
    step = None
    if stopped:
        who = "automation wrote it and did not lift it (check deploys.jsonl first)" if str(marker or "").startswith(
            AUTOMATION_MARKERS) else "it is the operator's"
        step = (f"remove /workspace/state/data/nightly.stop ({who}) once nothing needs the nightly stopped: the nightly "
                "forward replay, and with it the Done meter's replay twins, waits while it stands")
    onsets = [t for t, on in ((stop_since, stopped), (error_since, erring)) if on and t is not None]
    return {
        "stalled": bool(late or erring or stopped),
        "what": ("The nightly forward replay is late or stopped: " + "; ".join(parts) + "." if parts else
                 "The nightly forward replay is on time." if f.get("ready_day") else "No nightly ready file on record."),
        "numbers": {"ready_day": f.get("ready_day"), "expected_day": expected,
                    "ready_at": None if S.epoch(f.get("ready_at")) is None else S.iso(S.epoch(f.get("ready_at"))),
                    "nightly_error": f.get("error") is not None, "nightly_stop": marker is not None,
                    "nightly_stop_since": None if stop_since is None else S.iso(float(stop_since))},
        "doing": ("The House's supervisor keeps the nightly daemon alive while no stop stands and it retries a failed night "
                  "every five minutes. Until the session's replay lands, the Done meter's readings stay provisional "
                  "(DONE-RULE-A1 A1.4) and its replay twins wait."),
        "owner_step": step, "onset": min(onsets) if onsets else None}


# ---------------------------------------------------------------------------------------------- the notice
def cause_facts(cause: str, check: Mapping[str, Any], since: float | None, now: float) -> dict[str, Any]:
    """One cause in the `stall` notice (the gateway composes the words, gateway/lib/email.mjs): the cause, the House's
    own sentence for it, the numbers, how long (hours, and since when), what the House is doing, the owner step or None."""
    # A figure is a count, a dollar or hour figure to two places, a time, yes or no, or a short token (the gateway echoes
    # only those, and an unknown one as unknown).
    numbers = {k: round(v, 2) if isinstance(v, float) else v for k, v in (check.get("numbers") or {}).items()}
    return {"cause": cause, "what": str(check.get("what") or ""), "numbers": numbers,
            "since": None if since is None else S.iso(since), "hours": None if since is None else _hours(now - since),
            "doing": str(check.get("doing") or ""), "owner_step": check.get("owner_step") or None}


def notice_id(owner: list[str]) -> str:
    """The gateway's own dedupe key for the notice (gateway/lib/router.mjs keys it the same way, whatever id comes): the
    owner causes it tells, or `stall:info` when none needs the owner."""
    return "stall:owner:" + "+".join(sorted(owner)) if owner else "stall:info"


def notice_facts(entries: list[dict[str, Any]], now: float) -> dict[str, Any]:
    """The `stall` notice's facts: every standing cause (`cause_facts`), owner steps first."""
    ordered = [e for e in entries if e.get("owner_step")] + [e for e in entries if not e.get("owner_step")]
    return {"kind": "stall", "notice_id": notice_id([e["cause"] for e in entries if e.get("owner_step")]),
            "causes": ordered, "at": S.iso(now)}


def _sent(answer: Any) -> tuple[bool, str]:
    if isinstance(answer, Mapping) and answer.get("sent") is True and answer.get("duplicate") is not True:
        return True, "sent"
    if isinstance(answer, Mapping) and answer.get("duplicate") is True:
        return False, "the gateway told this inside its own window: tried again at the next run"
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


def due_notice(stalled: list[str], owner: list[str], mail: Mapping[str, Any], now: float) -> str | None:
    """Why a notice is due now ("owner" or "info"), or None: the pace in the module docstring."""
    owner_at, info_at = S.epoch(mail.get("owner_at")), S.epoch(mail.get("info_at"))
    if owner:
        told = set(mail.get("owner_causes") or []) if _within(owner_at, now, OWNER_EVERY_SECONDS) else set()
        return "owner" if set(owner) - told else None
    if stalled:
        last = max([t for t in (owner_at, info_at) if t is not None], default=None)
        return None if _within(last, now, INFO_EVERY_SECONDS) else "info"
    return None


def run(ctx: Any) -> dict[str, Any]:
    """The job (the module docstring). `ctx` is the ops context (league/ops/context.py); it may also hand in `notify`
    (a callable posting the notice's facts), `health` (the gateway's health, or a callable reading it) and
    `population_ceiling` (tests)."""
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
    try:
        grant = grant_facts(root)
    except Exception as exc:  # noqa: BLE001 - an unreadable receipts store raises no grant cause
        grant = None
        errors.append(f"the grant's receipts could not be read ({type(exc).__name__})")
    # THE LANE, THE PRE-OPEN AND THE NIGHTLY (Oct 10, 2026; the readiness audit's M6 and M12): each read on its own, an
    # unreadable one an error, never a cause.
    lane_on, dlane, preopen, forward, flight = None, None, None, {}, None
    try:
        lane_on = _lane_on(ctx, root)
        dlane = dlane_facts(root)
    except Exception as exc:  # noqa: BLE001 - no lane cause from an unreadable report
        errors.append(f"the direction lane's report could not be read ({type(exc).__name__})")
    try:
        preopen = preopen_facts(root)
    except Exception as exc:  # noqa: BLE001 - no pre-open cause from unreadable receipts
        errors.append(f"the pre-open receipts could not be read ({type(exc).__name__})")
    try:
        forward = forward_facts(root)
    except Exception as exc:  # noqa: BLE001 - no forward cause from unreadable files
        errors.append(f"the nightly's files could not be read ({type(exc).__name__})")
    try:
        flight = deploy_flight(base, root, now)
    except Exception as exc:  # noqa: BLE001 - no flight read: the grace still holds a fresh refusal back
        errors.append(f"whether a deploy is in flight could not be read ({type(exc).__name__})")
    state = read_json(root / STATE_FILE, {})
    state = state if isinstance(state, dict) else {}
    # How long the nightly's record has carried an error: from the first run that saw it (kept in stall.json).
    seen_error = state.get("nightly_error") if isinstance(state.get("nightly_error"), dict) else {}
    nightly_error = None
    if (forward or {}).get("error") is not None:
        nightly_error = {"since": seen_error.get("since") or S.iso(now)}
    # The Done checkpoints a SENT notice has told (the review of the weekend fixes, Oct 10, 2026): `done` stands for the
    # rest.
    done_told = sorted({k for k in state.get("done_told") or [] if isinstance(k, str)}
                       if isinstance(state.get("done_told"), list) else [])
    found = checks(swarm, now=now, ceiling=ceiling, budget=budget if isinstance(budget, Mapping) else None,
                   deploy=owner_deploy(base), heartbeat=read_json(root / HEARTBEAT, None), pause=pause_facts(root),
                   grant=grant, kill=kill_facts(_health(ctx)), flight=flight, dlane=dlane, lane_on=lane_on,
                   preopen=preopen, forward=forward,
                   nightly_error_since=None if nightly_error is None else S.epoch(nightly_error["since"]),
                   done_told=done_told)

    told = state.get("causes") if isinstance(state.get("causes"), dict) else {}
    mail = dict(state.get("mail")) if isinstance(state.get("mail"), dict) else {}
    cleared, stalled, warned, entries = [], [], [], []
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
        entries.append(cause_facts(cause, check, since, now))
        if not _within(S.epoch(rec.get("warned_at")), now, WARN_EVERY_SECONDS):
            warned.append(cause)
            rec["warned_at"] = S.iso(now)
        told[cause] = rec

    owner = [e["cause"] for e in entries if e["owner_step"]]
    kind = due_notice(stalled, owner, mail, now)
    notice: dict[str, Any] = {"sent": False, "causes": stalled}
    if kind is None:
        notice["why"] = ("nothing stands" if not stalled else
                         f"told at {mail.get('owner_at') or mail.get('info_at')}: the owner causes at most every 12 h, the "
                         "rest at most every 24 h")
    else:
        facts = notice_facts(entries, now)
        notice["notice_id"] = facts["notice_id"]
        notify = _notifier(ctx)
        if notify is None:
            notice["why"] = "no gateway to notify through"
            errors.append("stall notice not sent: no gateway")
        else:
            try:
                ok, words = _sent(notify(facts))
            except Exception as exc:  # noqa: BLE001 - not told: the next run tries again
                ok, words = False, f"the notice failed ({type(exc).__name__} {getattr(exc, 'code', '') or ''})".replace(" )", ")")
            notice.update(sent=ok, why=words)
            if ok and "done" in stalled:
                done_told = sorted(set(done_told) | set(found["done"].get("keys") or []))
            if ok and kind == "owner":
                # A notice for a new owner cause inside the 12 h starts them again: what both told is not told twice.
                fresh = _within(S.epoch(mail.get("owner_at")), now, OWNER_EVERY_SECONDS)
                earlier = set(mail.get("owner_causes") or []) if fresh else set()
                mail.update(owner_at=S.iso(now), owner_causes=sorted(earlier | set(owner)), notice_id=facts["notice_id"])
            elif ok:
                mail.update(info_at=S.iso(now), notice_id=facts["notice_id"])
            elif "inside its own window" not in words:
                errors.append(f"stall notice not sent: {words}")
    for cause in warned:
        check = found[cause]
        text = f"stall: {cause}: {check['what']} {check['doing']}"
        if check.get("owner_step"):
            text += f" Owner step: {check['owner_step']}."
        if kind is not None and not notice["sent"] and notice.get("why"):
            text += f" (notice: {notice['why']})"
        _alert(ctx, text)
    write_json(root / STATE_FILE, {"schema": 2, "at": S.iso(now), "causes": told, "mail": mail,
                                   "nightly_error": nightly_error, "done_told": done_told})
    return {"stalled": stalled, "cleared": cleared, "warned": warned, "notice": notice,
            "checks": {c: {k: found[c].get(k) for k in ("stalled", "what", "numbers", "doing", "owner_step")} for c in CAUSES},
            "ceiling": ceiling, "errors": errors, "warning": bool(stalled or errors)}


__all__ = ["run", "checks", "swarm_facts", "owner_deploy", "pause_facts", "grant_facts", "kill_facts", "cause_facts",
           "notice_facts", "notice_id", "due_notice", "candidate", "CAUSES", "BIRTH_HOURS", "GYM_HOURS", "MIN_GYM_RUNS",
           "VALIDATION_HOURS", "BRAKE_WINDOW_HOURS", "BRAKED_HOURS", "RUNWAY_DAYS", "PAUSED_HOURS", "OWNER_EVERY_SECONDS",
           "INFO_EVERY_SECONDS", "WARN_EVERY_SECONDS", "STATE_FILE", "deploy_flight", "dlane_facts", "preopen_facts",
           "forward_facts", "last_session_before", "OWNER_DEPLOY_GRACE", "DEPLOY_FLIGHT_SECONDS", "NIGHTLY_STOP_HOURS",
           "NIGHTLY_ERROR_HOURS", "FORWARD_DUE_HOUR", "DLANE_STALE_HOURS", "PREOPEN_HOURS", "NEWS_CAUSES", "done_key",
           "LANE_OFF_WHAT"]
