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

THE NO-CAPTAIN CAUSES (Oct 10, 2026; the no-captain audit of every hand intervention from Oct 7 to Oct 10: each of these
was found by the captain reading the log, never by an alarm):
- THE JAM, on `births`: no family born for `JAM_HOURS` (6) while at least `JAM_PASSES` (4) architect passes wanted births
  (asked a model, found no cell, or failed: a pass at the ceiling wants none) is the owner's step at once, naming the
  main way the passes bore nothing (`jam_kind`: the card checks' incomplete cards and the fields they lack, the rebirth
  rule's refuted cells, a spent lineage, a cap, no open cell, failed or cut answers) and its lever (`LEVERS`: an agenda
  through scripts/agenda_install.py, `architect.max_rebirths_per_cell`, `architect.max_alive_per_class`, the effort).
  Only a jam a setting or an agenda clears is the owner's step (`JAM_OWNER_KINDS`): failed model calls (a provider's
  outage) heal by themselves and stand as the jam's INFO. The House loosens nothing by itself: the graveyard binds by
  design. The captain caught the graveyard wall of Oct 10, 15:41-16:22Z (births 0/0/0 under agenda v21.4, reverted by
  hand at 16:24:59Z) inside 41 minutes; no alarm would have (the 12-hour INFO, then), and these causes would not have
  either in that time (the dry window needs 2 hours, the jam 6): they catch the same wall when no captain is reading;
- `birth_yield` (INFO): over the last `YIELD_HOURS` (3) at least `YIELD_PASSES` (4) passes asked a model and bore at most
  `YIELD_MAX_BORN` (1), or the card checks refused at least `YIELD_REFUSED_SHARE` (80%) of their proposals; or no birth
  in `DRY_HOURS` (2) while `DRY_PASSES` (3) passes wanted births. Its numbers count the refusals by kind, the incomplete
  cards' top fields and the rebirth rows pointed at (`architect_tally`, from the `swarm.architect` events);
- `swarm_alerts`: the swarm's own alerts (`swarm.status` with `alert` true), which reach the swarm's record and the
  private ledger only: each kind with its count, last time and own sentence. The owner's step for the kinds only a
  setting or a fix clears (`ALERT_STEPS`: reader_cut, agenda_guard, gate_coverage...), READ FROM THE STATE where the
  swarm keeps it (`alert_states`, since the review of the no-captain build: the swarm raises most of them once, so a
  12-hour window of alerts both failed the next UTC day after a fix and dropped an unfixed one): a kind stands while
  its condition does, whatever its alert's age, and clears at the next run once it is fixed; a kind whose condition is
  not read is the owner's step on the UTC day its alert fired only. INFO for the rest, over the last `ALERT_HOURS`
  (12); the self-healing ones (`ALERT_SELF_HEALING`) never stand by themselves. Oct 9, 20:32Z: the Sail reviewer cut 4
  of 6 gate reviews and a lineage's one try was lost before the captain read `reader_cut` in the log;
- `underspend` (INFO): Sail's booked research today under `UNDERSPEND_SHARE` (70%) of what its day's figure buys by
  now at the guard's even pace (each TOP-UP RAISE counted from its hour), once the day is `UNDERSPEND_MIN_HOURS` (6) in
  and the guard braked under `UNDERSPEND_BRAKE_HOURS` (2) of it; or two settings that cannot both hold while they bind.
  Claude's reading is said beside it and never stands by itself (`PACED_METERS`: its roles' calls come as the gate and
  the strategist have work). It names the settings that bind research (`settings_binds`: a configured cap under what
  the budget buys, a class cap under the direction lane's own, an architect Claude line under one call's hold, a value
  under the release's own, the Claude lines at 0). DONE-RULE item 7 reads a day with no taper as at budget, so a
  swarm.json pin (Oct 9: gym.max_boxes 2 under the budget's 7) was invisible.

THE NOTICE: one `POST /v1/notify` kind `stall` a run at most, listing EVERY cause standing (`cause_facts` each: the
cause, the numbers, how long, what the House is doing about it, the owner step when one is needed), owner steps first,
through the same gateway client the budget's funding notice uses (`budget._notifier`). It is mailed:

- when some standing cause has an owner step: at once when one of them was not in the last owner notice, else at most
  once every `OWNER_EVERY_SECONDS` (12 h);
- when none has: at once when a standing cause was told by no notice in the last 24 h (`mail.told`; since the review
  of the no-captain build, so one cause standing for days holds no new one back), else at most once every
  `INFO_EVERY_SECONDS` (24 h) after the last notice of either kind.

The gateway holds the same pace by its own clock (it keys an owner notice on the owner causes, `stall:owner:<causes>`,
for 12 h, and one with none on the causes it tells, `stall:info:<causes>`, for 24 h), so a lost state file never mails
the same causes twice. A notice counts as told
only once the gateway says it SENT it: a `duplicate` answer (told inside the gateway's own window) is tried at the next
run. Each cause standing is also one House warning at most every `WARN_EVERY_SECONDS` (12 h). `<state>/stall.json`
(private) remembers each cause (since when it stands, when it was last warned of, when it cleared), the notices (when
the last of each kind was sent, which owner causes it told, when each cause was last told) and the Done checkpoints
told (`done_told`). A cause that clears is named in the receipt. The receipt carries every check, stalled or not, with
its numbers.

HOW LONG: from the record when it says (the last birth, the last Validation verdict, the start of the guard's brake, the
first refusal of the owner's deploy or of the grant, the pause file, the kill), else from when this job first saw the
cause standing.

NEVER ACTS. The job reads (every SQLite open `mode=ro`, inside `guard.readonly()`; the gateway's `/v1/health`, a GET),
writes only `stall.json`, and posts only the notice: it moves no money, changes no setting, starts and stops nothing. It
runs in a maintenance pause too (read-only, like `preopen` and `clock`), so a pause left on is itself reported.
"""
from __future__ import annotations

import datetime as dt
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
#: THE BIRTH YIELD (Oct 10, 2026; the no-captain audit's item 1): the window the architect's yield is read over, the passes
#: that asked a model in it below which no yield is read, the births at or under which it is a collapse, and the share
#: of the proposals the card checks refused at or above which it is one too.
YIELD_HOURS = 3.0
YIELD_PASSES = 4
YIELD_MAX_BORN = 1
YIELD_REFUSED_SHARE = 0.8
#: No birth this long while at least `DRY_PASSES` architect passes wanted births (asked a model, found no cell, failed).
DRY_HOURS = 2.0
DRY_PASSES = 3
#: THE JAM: no birth this long while at least `JAM_PASSES` passes wanted births is the `births` cause with an owner step
#: (the House cannot loosen the graveyard or the card rule, nor rewrite the agenda: only the owner can).
JAM_HOURS = 6.0
JAM_PASSES = 4
#: The ways a jam bears nothing that a setting or an agenda clears (`jam_kind`): only these make the jam the owner's step.
#: Failed model calls (`failed`: a provider's outage, a poll's timeout) heal by themselves when the route answers again,
#: and an empty answer or another refusal names no lever: those stand as the jam's INFO (the line and the kill switch,
#: which the owner does clear, are causes of their own: `runway_claude`, `kill_on`).
JAM_OWNER_KINDS = ("incomplete", "rebirth", "spent_lineage", "capped", "no_cell", "cut")
#: THE SWARM'S ALERTS (the audit's item 5): the `swarm.status` events with `alert` true read over this window.
ALERT_HOURS = 12.0
#: The alerts that ask for a setting or a fix only the owner can make, and the step that makes each. Every other kind is
#: told as INFO (`train_from_setting` among them: a note that gym.train_from was snapped, raised every ten minutes while
#: it stands, on a swarm that runs on its own span).
ALERT_STEPS = {
    "reader_cut": "raise gate.review_max_output_tokens in swarm.json (the gate's reader was cut short: no verdict, no try)",
    "agenda_guard": "fix the agenda with scripts/agenda_install.py (the architect reads it wrong)",
    "policy_layer": "fix league/swarm/policy.json in a release (it is malformed or sets an owner key)",
    "train_span_pending": "restart the swarm with the matching Gym image, or set gym.train_from back",
    "train_span_mismatch": "adopt the Gym image built for the swarm's Train span (gym.image_checkpoint) and restart",
    "gate_missing_data": "name a gate image that holds the missing holdouts (gym.gate_checkpoint)",
    "gate_coverage": "name a gate image that holds every root's holdout (gym.gate_checkpoint)",
    "look_failed_three_times": "fix the gate box, then reset look_tries for the parked version",
    "game_waits": "set gym.train_from to the learning game's seen span and restart",
}
#: The alerts that heal themselves (named in the numbers, never a cause by themselves): a Sail window that did not answer
#: falls to its fallback for an hour; the funding cliff is the budget's own funding notice's.
ALERT_SELF_HEALING = ("sail_window_stall", "funding_alert")
#: THE ALERTS' STATE (the review of the no-captain build, Oct 10, 2026): the owner kinds whose latest alert is read this
#: far back (it names what its condition is about: the image, the span, the output cap), whatever `ALERT_HOURS` says.
ALERT_LOOKBACK_KINDS = ("reader_cut", "train_span_mismatch", "gate_missing_data")
ALERT_STATE_DAYS = 7.0
#: THE LEARNING GAME (league/swarm/game.py, which only the modules its import wall names may import): its T0 in the
#: swarm's kv (`T0_KEY`: a `game_waits` stands only before the first), its seen span's first day by default
#: (`SEEN_FROM`) and the last hidden day (`HIDDEN`), under which a configured `game.seen_from` is the default.
GAME_T0_KEY = "game_t0"
GAME_SEEN_FROM = "2022-01-03"
GAME_HIDDEN_END = "2021-12-31"
#: THE UNDERSPEND (the audit's item 3): a meter's booked research today under this share of what its day's figure buys by
#: now (the guard paces the day evenly), read once the UTC day is `UNDERSPEND_MIN_HOURS` in and at least
#: `UNDERSPEND_MIN_USD` is due, while the guard braked under `UNDERSPEND_BRAKE_HOURS` of the day.
UNDERSPEND_SHARE = 0.7
UNDERSPEND_MIN_HOURS = 6.0
UNDERSPEND_MIN_USD = 1.0
UNDERSPEND_BRAKE_HOURS = 2.0
#: The meters the guard paces evenly over the day (the Sail guard's `pace_day`): only these stand as an underspend.
PACED_METERS = ("sail",)
#: What one architect call holds on its Claude line (league/swarm/architect.py `Architect.run`, `need_usd`): a smaller line
#: can never place one.
ARCHITECT_HOLD_USD = 2.0
#: The files that pause the floor (the House's maintenance pause, `House.paused`; the swarm's stop file) and the step that
#: lifts each.
PAUSE_FILES = {"PAUSE": ("maintenance", "lift the maintenance pause once its work is done (scripts/floor_box.py maintenance off)"),
               "swarm.stop": ("swarm_stop", "remove state/swarm.stop once the swarm should run again (the House starts it then)")}
CAUSES = ("births", "birth_yield", "gym_runs", "validations", "braked", "runway_sail", "runway_claude", "owner_deploy",
          "paused", "grant_refused", "kill_on", "dlane", "done", "preopen", "forward", "swarm_alerts", "underspend")
#: The causes a pause stops by design: not raised while the floor is paused.
RESEARCH_CAUSES = ("births", "birth_yield", "gym_runs", "validations", "braked", "underspend")
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


# ---------------------------------------------------------------------------------------------- the architect's yield
#: An incomplete card's refusal (league/swarm/architect.py `admit`: "incomplete card: " and the card checks' problems,
#: each "<field>: ...", joined by "; ").
INCOMPLETE_CARD = "incomplete card: "
_FIELD = re.compile(r"([a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)?):")
#: What the owner can do about each way the architect's passes bear nothing (`jam_kind`).
LEVERS = {
    "incomplete": ("the card checks refuse the architect's cards as incomplete{fields}: install an agenda whose card "
                   "section the model can fill (scripts/agenda_install.py check, then apply; the last agenda's before-copy "
                   "is swarm.json.before-agenda-*)"),
    "rebirth": ("the cards land in refuted cells and their rebirth claims do not hold (the graveyard binds by design): "
                "point the agenda at open cells (scripts/agenda_install.py), or raise architect.max_rebirths_per_cell only "
                "if the evidence warrants spending those cells again"),
    "spent_lineage": ("the direction cards join lineages whose one Validation try is spent or claimed: point the agenda at "
                      "new lineages (scripts/agenda_install.py)"),
    "capped": ("the class cap, the structure quota or the lane quota refuses the proposals: raise "
               "architect.max_alive_per_class (it must hold dlane.max_alive while the direction lane is one class) or "
               "change the lane's shares"),
    "no_cell": ("no cell a birth may land in is open (every cell's rebirth room is spent): point the agenda at other cells "
                "or roots (scripts/agenda_install.py), or raise architect.max_rebirths_per_cell"),
    "failed": "the architect's model calls fail (the swarm.architect events' errors): check its route and its line",
    "cut": ("the architect's answers are cut short with no family (its output spent reasoning): lower "
            "architect.sail_effort or raise architect.max_output_tokens"),
    "empty": "the architect's answers carry no family: read its last request and the agenda (scripts/agenda_install.py)",
    "other": "the proposals are refused before birth by the twin, cite or lane rules: read the swarm.architect events",
}


def card_fields(why: Any) -> list[str]:
    """The card fields an incomplete card's refusal names, in order, each once ("incomplete card: comparison: at least 30
    characters (9 given); falsification: ..." -> ["comparison", "falsification"]); [] for any other refusal."""
    text = str(why or "")
    if not text.startswith(INCOMPLETE_CARD):
        return []
    out: list[str] = []
    for part in text[len(INCOMPLETE_CARD):].split("; "):
        found = _FIELD.match(part.strip())
        if found and found.group(1) not in out:
            out.append(found.group(1))
    return out


def _count(value: Any) -> int:
    """A count from an event: an int, the sum of a mapping's counts, the length of a list; 0 for anything else."""
    if isinstance(value, Mapping):
        return sum(_count(v) for v in value.values())
    if isinstance(value, list):
        return len(value)
    number = _finite(value)
    return int(number) if number is not None and number > 0 else 0


def architect_tally(passes: Any, since: float) -> dict[str, Any]:
    """THE BIRTH YIELD of the architect's passes at or after `since` (`passes`: (epoch, the `swarm.architect` payload)),
    pure: the passes; those that asked a model, found no cell (`no_cell`), met the ceiling or failed; the proposals and
    births; the card checks' refusals by kind (`incomplete`, `rebirth`, `spent_lineage`); the proposals the class cap,
    the structure quota or the lane quota refused (`capped`), and of those the direction cards the class cap refused
    (`lane_class_capped`); the passes whose answer was cut (`cut`) or carried no family (`empty`); the incomplete cards'
    fields by count (`fields`, most first) and the graveyard rows the rebirth refusals point at (`rebirth_rows`,
    distinct)."""
    out: dict[str, Any] = {"passes": 0, "asked": 0, "no_cell": 0, "ceiling": 0, "failed": 0, "proposed": 0, "born": 0,
                           "incomplete": 0, "rebirth": 0, "spent_lineage": 0, "capped": 0, "cut": 0, "empty": 0,
                           "lane_class_capped": 0}
    fields: dict[str, int] = {}
    rows: set[str] = set()
    for at, row in passes or []:
        if at is None or at < since or not isinstance(row, Mapping):
            continue
        out["passes"] += 1
        out["born"] += _count(row.get("born")) if isinstance(row.get("born"), list) else 0
        skipped = row.get("skipped")
        if skipped in ("no_cell", "ceiling"):
            out[skipped] += 1
            continue
        if row.get("error"):
            out["failed"] += 1
            continue
        out["asked"] += 1
        proposed = _count(row.get("proposed"))
        out["proposed"] += proposed
        out["empty"] += 1 if proposed == 0 else 0
        out["cut"] += 1 if row.get("truncated") or row.get("incomplete_reason") else 0
        refused = row.get("card_refused") if isinstance(row.get("card_refused"), Mapping) else {}
        for kind in ("incomplete", "rebirth", "spent_lineage"):
            out[kind] += _count(refused.get(kind))
        # The class cap's refusals (`class_capped`, by class; a direction card's are named again in `lane_class_capped`,
        # never counted twice), the birth quota's (`structure_capped`) and the lane quota's (`lane_refused`).
        out["capped"] += sum(_count(row.get(k)) for k in ("class_capped", "structure_capped", "lane_refused"))
        # The direction cards the class cap refused (THE DIRECTION LANE: `lane_class_capped.cards`): the class-cap conflict
        # binds (`settings_binds`, key `class_cap`) only while these come.
        lane_capped = row.get("lane_class_capped")
        out["lane_class_capped"] += _count(lane_capped.get("cards")) if isinstance(lane_capped, Mapping) else 0
        for item in refused.get("items") or []:
            if not isinstance(item, Mapping):
                continue
            for name in card_fields(item.get("why")):
                fields[name] = fields.get(name, 0) + 1
            if item.get("row") and not str(item.get("why") or "").startswith(INCOMPLETE_CARD):
                rows.add(str(item["row"]))
    out["fields"] = dict(sorted(fields.items(), key=lambda kv: (-kv[1], kv[0])))
    out["rebirth_rows"] = len(rows)
    return out


def wanting(tally: Mapping[str, Any]) -> int:
    """The passes that wanted births: every pass but those the ceiling skipped (a pass with room asks a model, finds no
    cell a birth may land in, or fails)."""
    return int(tally.get("asked") or 0) + int(tally.get("no_cell") or 0) + int(tally.get("failed") or 0)


def card_refusals(tally: Mapping[str, Any]) -> int:
    return sum(int(tally.get(k) or 0) for k in ("incomplete", "rebirth", "spent_lineage"))


def jam_kind(tally: Mapping[str, Any]) -> str:
    """The main way the passes bore nothing (a key of `LEVERS`)."""
    if not tally.get("asked"):
        if not tally.get("no_cell") and not tally.get("failed"):
            return "other"
        return "no_cell" if int(tally.get("no_cell") or 0) >= int(tally.get("failed") or 0) else "failed"
    if not tally.get("proposed"):
        return "cut" if tally.get("cut") else "empty"
    counts = {k: int(tally.get(k) or 0) for k in ("incomplete", "rebirth", "spent_lineage", "capped")}
    kind = max(counts, key=lambda k: counts[k])
    return kind if counts[kind] > 0 else "other"


def lever(tally: Mapping[str, Any]) -> str:
    """The owner's lever for the main way the passes bore nothing, naming the incomplete cards' top fields."""
    kind = jam_kind(tally)
    top = list((tally.get("fields") or {}).items())[:3]
    named = f" (most often {', '.join(f'{k} {n}x' for k, n in top)})" if top else ""
    return LEVERS[kind].format(fields=named)


def fields_token(tally: Mapping[str, Any]) -> str:
    """The incomplete cards' top fields as one figure the gateway echoes ("comparison:6,falsification:4")."""
    return ",".join(f"{k}:{n}" for k, n in list((tally.get("fields") or {}).items())[:4])[:80] or "none"


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
    # THE NO-CAPTAIN READS (Oct 10, 2026): the architect's yield, the swarm's alerts, the day's research spend. Each one
    # unreadable is left out (its cause reads nothing), never a failed run.
    try:
        out.update(_yield_facts(db, now))
    except Exception:  # noqa: BLE001 - no yield read: birth_yield and the jam read nothing
        pass
    try:
        out["alerts"] = _alert_facts(db, now)
    except Exception:  # noqa: BLE001 - no alerts read: swarm_alerts reads nothing
        pass
    try:
        out["alert_state"] = _alert_state_facts(db, now)
    except Exception:  # noqa: BLE001 - no state read: the owner kinds are read by their window and the day rule
        pass
    try:
        out.update(_spend_facts(db, now))
    except Exception:  # noqa: BLE001 - no spend read: underspend reads nothing
        pass
    return out


def _yield_facts(db: Any, now: float) -> dict[str, Any]:
    """The architect's passes over the yield's windows (`architect_tally`: `yield.jam`, `.low`, `.dry`) and the births of
    the dry window (`births_dry`, the learning game's children included)."""
    window = max(JAM_HOURS, YIELD_HOURS, DRY_HOURS)
    passes = []
    for row in guard.rows(db, "SELECT at, payload FROM events WHERE kind='swarm.architect' AND at>=? ORDER BY seq",
                          (S.iso(now - window * 3600),)):
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError):
            continue
        if isinstance(payload, Mapping):
            passes.append((S.epoch(row["at"]), payload))
    since = S.iso(now - DRY_HOURS * 3600)
    born = guard.ids(db, "SELECT count(*) FROM events WHERE kind='swarm.born' AND at>=?", (since,))
    children = guard.ids(db, "SELECT count(*) FROM families WHERE origin=? AND born_at>=?", (GAME_ORIGIN, since))
    return {"yield": {"jam": architect_tally(passes, now - JAM_HOURS * 3600),
                      "low": architect_tally(passes, now - YIELD_HOURS * 3600),
                      "dry": architect_tally(passes, now - DRY_HOURS * 3600)},
            "births_dry": int((born or [0])[0] or 0) + int((children or [0])[0] or 0)}


def _alert_facts(db: Any, now: float) -> dict[str, dict[str, Any]]:
    """THE SWARM'S ALERTS: the `swarm.status` events with `alert` true in the last `ALERT_HOURS` (the newest 2,000), by
    action: {n, first_at, last_at, text} (the newest one's text, cut to 200 characters)."""
    out: dict[str, dict[str, Any]] = {}
    for row in guard.rows(db, "SELECT at, payload FROM events WHERE kind='swarm.status' AND at>=? ORDER BY seq DESC "
                              "LIMIT 2000", (S.iso(now - ALERT_HOURS * 3600),)):
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, Mapping) or payload.get("alert") is not True:
            continue
        action = re.sub(r"[^a-z0-9_]", "_", str(payload.get("action") or "unnamed").lower())[:40] or "unnamed"
        if not action[0].isalpha():
            action = "a_" + action[:38]
        rec = out.get(action)
        if rec is None:  # newest first: the first seen is the latest
            out[action] = {"n": 1, "first_at": row["at"], "last_at": row["at"],
                           "text": " ".join(str(payload.get("text") or "").split())[:200]}
        else:
            rec["n"] += 1
            rec["first_at"] = row["at"]
    return out


def _alert_state_facts(db: Any, now: float) -> dict[str, Any]:
    """What `alert_states` reads from the swarm's store: the latest alert of each `ALERT_LOOKBACK_KINDS` kind in the last
    `ALERT_STATE_DAYS` ({kind: {at, payload}}), and the kv rows the conditions are kept in (`gate_coverage`, the pool's
    record of each gate image's holdout; `train_objective`, the running Train span; the learning game's T0)."""
    latest: dict[str, dict[str, Any]] = {}
    patterns = [f"%{kind}%" for kind in ALERT_LOOKBACK_KINDS]
    where = " OR ".join("payload LIKE ?" for _ in patterns)
    for row in guard.rows(db, f"SELECT at, family, payload FROM events WHERE kind='swarm.status' AND at>=? AND ({where}) "
                              "ORDER BY seq DESC LIMIT 500", (S.iso(now - ALERT_STATE_DAYS * 86400), *patterns)):
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, Mapping) or payload.get("alert") is not True:
            continue
        action = payload.get("action")
        if action in ALERT_LOOKBACK_KINDS and action not in latest:  # newest first
            # The family an alert is about, while it lives (a retired one's look waits for nobody).
            alive = None
            if row["family"]:
                alive = bool(guard.ids(db, "SELECT 1 FROM families WHERE id=? AND retired_at IS NULL", (row["family"],)))
            latest[str(action)] = {"at": row["at"], "family": row["family"], "alive": alive, "payload": dict(payload)}
    kv: dict[str, Any] = {}
    for key in ("gate_coverage", "train_objective", GAME_T0_KEY):
        raw = (guard.ids(db, "SELECT value FROM kv WHERE key=?", (key,)) or [None])[0]
        try:
            kv[key] = json.loads(raw) if raw is not None else None
        except (TypeError, ValueError):
            kv[key] = None
    return {"latest": latest, "kv": kv}


def alert_states(loaded: Mapping[str, Any], facts: Mapping[str, Any], now: float) -> dict[str, dict[str, Any]]:
    """THE ALERTS' STATE (the review of the no-captain build, Oct 10, 2026): for each owner kind (`ALERT_STEPS`) whose
    condition the House can read, whether it stands NOW, from the swarm's settings as it loads them (`loaded`) and its
    store (`_alert_state_facts`): {kind: {stands, text, at}}. A kind left out is not read (its alert's window and the day
    rule decide, `_alerts_check`). The swarm raises most of these once (at its start, when the condition changes, once a
    key), so the alert's 12-hour window both kept a fixed one failing the next UTC day and dropped an unfixed one:

    - `reader_cut`: the latest stands while it fired this UTC day (the version is asked again the next day) and
      `gate.review_max_output_tokens` is no higher than the cap the cut answers met (the owner's step raises it);
    - `agenda_guard`: the agendas in swarm.json read wrong now (`loop.agenda_alert`, the swarm's own check);
    - `policy_layer`: policy.json malformed or setting an owner key now (the settings' `_policy`);
    - `train_span_pending`: `gym.train_from` asks for another Train span than the running swarm's (kv `train_objective`);
    - `train_span_mismatch`: the latest (in `ALERT_STATE_DAYS`) names the configured `gym.image_checkpoint` and the running
      span still;
    - `gate_coverage`: the pool's record of the configured gate image (kv `gate_coverage`) lacks a root of `gym.roots`;
    - `gate_missing_data`: the latest (in `ALERT_STATE_DAYS`) names the configured `gym.gate_checkpoint` still, and its
      family lives (a retired family's look waits for nobody);
    - `game_waits`: the learning game is on, has no T0, and the running span shows its hidden years.
    `look_failed_three_times` (a parked program, reset by hand) is not read. Pure but for the swarm's own imports."""
    from ..swarm import settings as settings_mod

    out: dict[str, dict[str, Any]] = {}
    latest = facts.get("latest") if isinstance(facts.get("latest"), Mapping) else {}
    kv = facts.get("kv") if isinstance(facts.get("kv"), Mapping) else {}
    gym = loaded.get("gym") if isinstance(loaded.get("gym"), Mapping) else {}

    def put(kind: str, stands: bool, text: Any, at: Any = None) -> None:
        out[kind] = {"stands": bool(stands), "text": " ".join(str(text or "").split())[:200], "at": at}

    def last(kind: str) -> tuple[dict[str, Any], Any]:
        row = latest.get(kind) if isinstance(latest.get(kind), Mapping) else {}
        payload = row.get("payload") if isinstance(row.get("payload"), Mapping) else {}
        return dict(payload), row.get("at")

    status = loaded.get("_policy")
    if isinstance(status, Mapping):
        malformed = status.get("state") == "malformed"
        ignored = [str(k) for k in status.get("ignored") or []]
        put("policy_layer", malformed or bool(ignored),
            f"league/swarm/policy.json was not read ({status.get('why')})" if malformed else
            f"league/swarm/policy.json sets {', '.join(ignored)}, the owner's switches" if ignored else "")
    try:
        from ..swarm.loop import agenda_alert

        payload = agenda_alert(loaded)
        put("agenda_guard", payload is not None, (payload or {}).get("text"))
    except Exception:  # noqa: BLE001 - not read: the window and the day rule decide
        pass
    running = settings_mod.objective_span(kv.get("train_objective"))
    try:
        wanted = settings_mod.train_from(loaded, running)
        put("train_span_pending", wanted != running,
            f"gym.train_from asks for Train from {wanted}; the running swarm scores Train from {running} until its next "
            "start migrates")
    except Exception:  # noqa: BLE001 - not read
        pass
    payload, at = last("train_span_mismatch")
    put("train_span_mismatch", bool(payload) and str(payload.get("image")) == str(gym.get("image_checkpoint"))
        and str(payload.get("span")) == running.isoformat(), payload.get("text"), at)
    image = str(gym.get("gate_checkpoint") or "")
    coverage = kv.get("gate_coverage")
    record = coverage.get(image) if isinstance(coverage, Mapping) and image else None
    lacking: list[str] = []
    if isinstance(record, Mapping):
        wanted_roots = {str(r).upper() for r in gym.get("roots") or []}
        listed = {str(r).upper() for r in record["roots"]} if isinstance(record.get("roots"), list) else None
        missing = {str(r).upper() for r in record.get("missing") or []} if isinstance(record.get("missing"), list) else set()
        lacking = sorted((wanted_roots - listed if listed is not None else set()) | (wanted_roots & missing))
    put("gate_coverage", bool(lacking), f"the gate image {image} holds no holdout for {', '.join(lacking[:8])} (gym.roots)"
        if lacking else "")
    payload, at = last("gate_missing_data")
    alive = (latest.get("gate_missing_data") or {}).get("alive") if isinstance(latest.get("gate_missing_data"), Mapping) \
        else None
    put("gate_missing_data", bool(payload) and bool(image) and str(payload.get("image")) == image and alive is not False,
        payload.get("text"), at)
    payload, at = last("reader_cut")
    fired = S.epoch(at)
    today = S.iso(now)[:10]
    cap = _finite((loaded.get("gate") or {}).get("review_max_output_tokens")) if isinstance(loaded.get("gate"), Mapping) else None
    met = _finite(payload.get("max_output_tokens"))
    raised = cap is not None and met is not None and cap > met
    put("reader_cut", fired is not None and S.iso(fired)[:10] == today and not raised, payload.get("text"), at)
    # THE LEARNING GAME (`game.cfg` as the swarm reads it: on only when `game.enabled` is true; the seen span never
    # reaches back into the hidden years).
    block = loaded.get("game") if isinstance(loaded.get("game"), Mapping) else {}
    seen = str(block.get("seen_from") or "")
    try:
        seen = dt.date.fromisoformat(seen).isoformat() if seen > GAME_HIDDEN_END else GAME_SEEN_FROM
    except ValueError:
        seen = GAME_SEEN_FROM
    t0 = kv.get(GAME_T0_KEY)
    put("game_waits", block.get("enabled") is True and running.isoformat() < seen and not (isinstance(t0, str) and t0),
        f"the learning game waits: the running Train span shows its hidden years (set gym.train_from to {seen} and "
        "restart)")
    return out


def _spend_facts(db: Any, now: float) -> dict[str, Any]:
    """The swarm's booked research of the UTC day by meter (`spent_today`: Sail's model calls and Gym boxes, Claude's
    and OpenAI's calls, as the budget counts them) and the guard's brake of the day (`brake_today`)."""
    import datetime as dt

    day = dt.datetime.fromtimestamp(now, dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    spent = {"sail": 0.0, "claude": 0.0}
    for row in guard.rows(db, "SELECT kind, sum(usd) AS usd FROM spend WHERE epoch>=? AND epoch<=? GROUP BY kind",
                          (day, now)):
        usd = _finite(row["usd"]) or 0.0
        if row["kind"] in B.SAIL_KINDS:
            spent["sail"] += usd
        elif row["kind"] in B.CLAUDE_KINDS:
            spent["claude"] += usd
    return {"spent_today": {m: round(v, 4) for m, v in spent.items()}, "day_start": day,
            "brake_today": F.guard_hours(db, day, now)}


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


def _load(ctx: Any, root: Path) -> tuple[dict[str, Any] | None, str | None]:
    """The swarm's settings as it loads them (`settings.load`: the budget's tightening included), read-only, or None and
    the error's name. The job loads them once a run (`run`) for the ceiling, the lane, the settings that bind and the
    alerts' state."""
    try:
        from ..swarm import settings as settings_mod

        config = _get(ctx, "config")
        with guard.readonly():
            return settings_mod.load(root, config=config if isinstance(config, Mapping) else None), None
    except Exception as exc:  # noqa: BLE001 - each reader says what it could not read
        return None, type(exc).__name__


def _lane_on(ctx: Any, root: Path, loaded: Mapping[str, Any] | None = None) -> bool | None:
    """The direction lane is on (`dlane.mode` not "off", as the swarm loads its settings), None when that cannot be read;
    a context may hand in `lane_on` (tests)."""
    given = _get(ctx, "lane_on")
    if given is not None:
        return bool(given)
    if loaded is None:
        loaded, _ = _load(ctx, root)
    try:
        from ..swarm import dlane as dlane_mod

        return dlane_mod.on(loaded) if loaded is not None else None
    except Exception:  # noqa: BLE001 - unknown: a stale report is still said
        return None


def _ceiling(ctx: Any, root: Path, loaded: Mapping[str, Any] | None = None) -> tuple[int | None, str | None]:
    """`population.ceiling` as the swarm loads its settings (the budget's tightening included), or None and why."""
    given = _get(ctx, "population_ceiling")
    if given is not None:
        return int(given), None
    error = None
    if loaded is None:
        loaded, error = _load(ctx, root)
    try:
        if loaded is None:
            raise RuntimeError(error)
        return int((loaded.get("population") or {}).get("ceiling")), None
    except Exception as exc:  # noqa: BLE001 - an unknown ceiling raises no births stall
        return None, f"the population ceiling could not be read ({error or type(exc).__name__})"


def release_settings() -> dict[str, Any]:
    """The values the release itself sets: the code's DEFAULTS under the repo's policy layer (league/swarm/policy.json,
    `settings.read_policy`; none when it does not read), without config.json, swarm.json or the budget's overlay."""
    from ..swarm import settings as settings_mod

    layer, _ = settings_mod.read_policy()
    out = {k: dict(v) if isinstance(v, Mapping) else v for k, v in settings_mod.DEFAULTS.items()}
    for key, value in (layer or {}).items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = {**out[key], **value}
    return out


def settings_binds(loaded: Any, release: Mapping[str, Any] | None = None) -> list[dict[str, str]]:
    """THE SETTINGS THAT BIND RESEARCH (Oct 10, 2026; the no-captain audit's item 3), from the settings as the swarm loads
    them (the budget's overlay applied: it only tightens, so a configured value under a knob the budget buys is what
    binds). Pure but for `release` left None (`release_settings`, the repo's policy.json read). Each {kind, text}, and
    `key` on a conflict:

    - `cap`: a configured cap tighter than what the budget's dollars buy (`budget.knobs`): `gym.max_boxes`,
      `researcher.sail_usd_per_hour`, `population.ceiling`, a slower `architect.every_seconds`; and `population.start`
      under the ceiling (a population at its start is not refilled to the ceiling);
    - `conflict`: two settings that cannot both hold: `architect.max_alive_per_class` under `dlane.max_alive` while the
      direction lane is on (key `class_cap`: every direction card is one class, so the class cap binds before the lane's
      own quota, as at 21:35Z Oct 9; the release's own values are such a pair, so `underspend` stands on it only while
      the architect's passes meet it, `lane_class_capped`), and an architect Claude line above 0 but under the hold one
      call needs (key `architect_line`: it can never be used);
    - `drift`: a setting under the release's own value (`release`: the code's DEFAULTS under policy.json) that the
      operator lowered in swarm.json (`researcher.dormant_cycles`, `architect.max_refill`): Oct 9, dormancy at 12 retired
      families the guard was holding (the release has since set 12 itself: the drift is what goes under it);
    - `line`: the Claude roles whose line is 0 (`claude.role_usd_day`): Claude's day figure is spent only by the other
      roles' calls, which come when the gate and the strategist have work, never at an even pace."""
    if not isinstance(loaded, Mapping):
        return []
    block = lambda name: loaded.get(name) if isinstance(loaded.get(name), Mapping) else {}  # noqa: E731
    budget = block("budget")
    knobs = budget.get("knobs") if isinstance(budget.get("knobs"), Mapping) else {}
    gym, population, architect, researcher = block("gym"), block("population"), block("architect"), block("researcher")
    out: list[dict[str, str]] = []

    def add(kind: str, text: str, key: str | None = None) -> None:
        out.append({"kind": kind, "text": text, **({"key": key} if key else {})})

    def below(name: str, value: Any, knob: Any, *, slower: bool = False) -> None:
        a, b = _finite(value), _finite(knob)
        if a is None or b is None:
            return
        if (a > b + 1e-9) if slower else (a < b - 1e-9):
            add("cap", f"{name} {a:g} {'>' if slower else '<'} {b:g} the budget buys")

    below("gym.max_boxes", gym.get("max_boxes"), knobs.get("gym.max_boxes"))
    if researcher.get("sail_usd_per_hour") is not None:
        below("researcher.sail_usd_per_hour", researcher.get("sail_usd_per_hour"), knobs.get("researcher.sail_usd_per_hour"))
    below("population.ceiling", population.get("ceiling"), knobs.get("population.ceiling"))
    below("architect.every_seconds", architect.get("every_seconds"), knobs.get("architect.every_seconds"), slower=True)
    start, ceiling = _finite(population.get("start")), _finite(population.get("ceiling"))
    if start is not None and ceiling is not None and start < ceiling:
        add("cap", f"population.start {start:g} < population.ceiling {ceiling:g}")
    try:
        from itertools import combinations

        from ..swarm import dlane as dlane_mod
        from ..swarm.strategist import mechanism_class

        lane_max, classes = None, []
        if dlane_mod.on(loaded):
            c = dlane_mod.cfg(loaded)
            lane_max = _finite(c.get("max_alive"))
            roots = list(c["roots"])
            # The classes a direction card can be in (`Architect.lane_classes`: each lane structure by root group).
            classes = sorted({mechanism_class(s, list(g)) for s in c["structures"]
                              for k in range(1, len(roots) + 1) for g in combinations(roots, k)})
    except Exception:  # noqa: BLE001 - a lane block that does not read: no conflict named from it
        lane_max, classes = None, []
    per_class = _finite(architect.get("max_alive_per_class"))
    if lane_max is not None and classes and per_class is not None and 0 < per_class * len(classes) < lane_max:
        add("conflict", f"architect.max_alive_per_class {per_class:g} x {len(classes)} direction class"
                        f"{'es' if len(classes) > 1 else ''} ({', '.join(classes)}) < dlane.max_alive {lane_max:g}: the "
                        "class cap, shared with alpha on the same structure and roots, binds the lane first", "class_cap")
    claude = block("claude")
    lines = claude.get("role_usd_day") if isinstance(claude.get("role_usd_day"), Mapping) else {}
    line = _finite(lines.get("architect"))
    if line is not None and 0 < line < ARCHITECT_HOLD_USD:
        add("conflict", f"claude.role_usd_day.architect {line:.2f} < the {ARCHITECT_HOLD_USD:.2f} one architect call holds "
                        "(it can never be used: set it to 0 or to at least the hold)", "architect_line")
    if release is None:
        try:
            release = release_settings()
        except Exception:  # noqa: BLE001 - no release values read: no drift named
            release = {}
    for name, key, given in (("researcher.dormant_cycles", ("researcher", "dormant_cycles"), researcher.get("dormant_cycles")),
                             ("architect.max_refill", ("architect", "max_refill"), architect.get("max_refill"))):
        part = release.get(key[0]) if isinstance(release.get(key[0]), Mapping) else {}
        a, b = _finite(given), _finite(part.get(key[1]))
        if a is not None and b is not None and a < b:
            add("drift", f"{name} {a:g} < the release's {b:g}")
    zero = sorted(str(role) for role, usd in lines.items() if _finite(usd) == 0)
    if zero:
        add("line", f"claude.role_usd_day is 0 for {', '.join(zero)}")
    return out


def _binds(ctx: Any, root: Path, loaded: Mapping[str, Any] | None = None) -> tuple[list[dict[str, str]] | None, str | None]:
    """`settings_binds` over the settings as the swarm loads them, or None and why; a context may hand in `binds`."""
    given = _get(ctx, "binds")
    if given is not None:
        return list(given), None
    error = None
    if loaded is None:
        loaded, error = _load(ctx, root)
    try:
        if loaded is None:
            raise RuntimeError(error)
        return settings_binds(loaded), None
    except Exception as exc:  # noqa: BLE001 - no binds named: underspend still reads the spend
        return None, f"the settings that bind research could not be read ({error or type(exc).__name__})"


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
           nightly_error_since: float | None = None, done_told: Any = (),
           binds: list[Mapping[str, str]] | None = None,
           alert_states: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
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
    room = ceiling is not None and alive < ceiling
    # THE JAM (Oct 10, 2026; the no-captain audit's item 1): no birth for `JAM_HOURS` while the architect kept wanting
    # births. The House cannot loosen the graveyard or the card rule, nor rewrite the agenda: the owner's step, naming
    # the main way the passes bore nothing and its lever (Oct 10 15:41-16:22Z: births 0/0/0 under agenda v21.4, reverted
    # by hand; the 12-hour INFO alone told nobody).
    jam = (swarm.get("yield") or {}).get("jam") or {}
    jammed = (room and wanting(jam) >= JAM_PASSES
              and (last_birth is None or now - last_birth >= JAM_HOURS * 3600))
    # Only a jam a setting or an agenda clears is the owner's step (`JAM_OWNER_KINDS`): failed calls heal by themselves.
    jam_step = (f"the architect wanted births in {wanting(jam)} passes over the last {JAM_HOURS:g} h and none was born: "
                + lever(jam)) if jammed and jam_kind(jam) in JAM_OWNER_KINDS else None
    numbers = {f"births_{BIRTH_HOURS}h": births, "population": alive, "ceiling": ceiling,
               "last_birth_at": swarm.get("last_birth_at"), f"architect_passes_{BIRTH_HOURS}h": passes.get("passes", 0)}
    if jam:
        numbers.update({f"wanting_passes_{JAM_HOURS:g}h": wanting(jam), f"card_refused_{JAM_HOURS:g}h": card_refusals(jam),
                        "jam_kind": jam_kind(jam) if jammed else "none"})
    out["births"] = {
        "stalled": (births == 0 and room) or jammed,
        "what": (f"No family was born in the last {BIRTH_HOURS} h while the population is {alive} of a ceiling of "
                 f"{'unknown' if ceiling is None else ceiling}." if births == 0 else
                 f"No family was born in the last {_hours(now - last_birth) if last_birth is not None else 'unknown'} h "
                 f"while the population is {alive} of a ceiling of {ceiling}.")
                + (f" The architect wanted births in {wanting(jam)} passes over the last {JAM_HOURS:g} h: it asked a model "
                   f"{jam.get('asked', 0)} times, proposed {jam.get('proposed', 0)}, and the card checks refused "
                   f"{card_refusals(jam)} ({jam.get('incomplete', 0)} incomplete, {jam.get('rebirth', 0)} by the rebirth rule, "
                   f"{jam.get('spent_lineage', 0)} into a spent lineage); {jam.get('capped', 0)} met a cap, "
                   f"{jam.get('no_cell', 0)} passes found no cell, {jam.get('failed', 0)} failed."
                   + ("" if jam_step else f" No owner step: {LEVERS[jam_kind(jam)].format(fields='')}; the architect asks "
                                         "again at its own cadence.") if jammed else ""),
        "numbers": numbers,
        "doing": (f"The architect passed {passes.get('passes', 0)} times in the last {BIRTH_HOURS} h: {passes.get('no_cell', 0)} "
                  f"found no cell a birth may land in, {passes.get('ceiling', 0)} met the ceiling, {passes.get('failed', 0)} "
                  f"failed, {passes.get('asked', 0)} asked a model and proposed {passes.get('proposed', 0)} families "
                  f"({passes.get('born', 0)} born). It passes again at its own cadence; research goes on in the living families "
                  f"({alive}); {_guard_words(guard_now)}."),
        "owner_step": research_step or jam_step, "onset": last_birth}
    out["birth_yield"] = _yield_check(now, swarm, ceiling)

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
    out["swarm_alerts"] = _alerts_check(now, swarm.get("alerts"), alert_states)
    out["underspend"] = _underspend_check(now, swarm, budget, binds)
    if since is not None:  # the pause stops research by design: none of its causes is raised while it stands
        for cause in RESEARCH_CAUSES:
            out[cause].update(stalled=False, paused=True)
    return out


def _yield_check(now: float, swarm: Mapping[str, Any], ceiling: int | None) -> dict[str, Any]:
    """`birth_yield` (the module docstring): the architect bears (almost) nothing while it keeps asking. Pure. INFO: the
    `births` cause carries the owner step once the jam has stood `JAM_HOURS`."""
    tallies = swarm.get("yield") or {}
    low, dry = tallies.get("low") or {}, tallies.get("dry") or {}
    alive = int(swarm.get("alive") or 0)
    room = ceiling is not None and alive < ceiling
    born, proposed, refused = int(low.get("born") or 0), int(low.get("proposed") or 0), card_refusals(low)
    asked = int(low.get("asked") or 0)
    births_dry = swarm.get("births_dry")
    is_dry = births_dry is not None and int(births_dry) == 0 and wanting(dry) >= DRY_PASSES
    starved = asked >= YIELD_PASSES and (born <= YIELD_MAX_BORN or (proposed > 0 and refused >= YIELD_REFUSED_SHARE * proposed))
    stalled = bool(tallies) and room and (is_dry or starved)
    share = None if not proposed else round(refused / proposed, 2)
    parts = []
    if starved or not is_dry:
        parts.append(f"The architect bore {born} of {proposed} proposals in the {asked} passes that asked a model over the "
                     f"last {YIELD_HOURS:g} h; the card checks refused {refused} ({low.get('incomplete', 0)} incomplete, "
                     f"{low.get('rebirth', 0)} by the rebirth rule, {low.get('spent_lineage', 0)} into a spent lineage) and "
                     f"{low.get('capped', 0)} met a cap.")
    if is_dry:
        parts.append(f"No family was born in the last {DRY_HOURS:g} h while the architect wanted births in {wanting(dry)} "
                     "passes.")
    top = list((low.get("fields") or {}).items())[:3]
    if top:
        parts.append("The incomplete cards most often lacked " + ", ".join(f"{k} ({n}x)" for k, n in top) + ".")
    kind = jam_kind(low if asked else dry)
    return {
        "stalled": stalled,
        "what": " ".join(parts),
        "numbers": {f"asked_{YIELD_HOURS:g}h": asked, f"proposed_{YIELD_HOURS:g}h": proposed, f"born_{YIELD_HOURS:g}h": born,
                    "refused_share": share, "refused_incomplete": int(low.get("incomplete") or 0),
                    "refused_rebirth": int(low.get("rebirth") or 0), "refused_spent": int(low.get("spent_lineage") or 0),
                    "capped": int(low.get("capped") or 0), "cut": int(low.get("cut") or 0), "empty": int(low.get("empty") or 0),
                    "no_cell": int(low.get("no_cell") or 0), "failed": int(low.get("failed") or 0),
                    f"births_{DRY_HOURS:g}h": births_dry, "top_fields": fields_token(low),
                    "rebirth_rows": int(low.get("rebirth_rows") or 0), "kind": kind},
        "doing": ("The architect passes again at its own cadence and shows its next request the last pass's card refusals "
                  "with their lessons; nothing loosens the graveyard or the card rule by itself. What would help: "
                  + LEVERS[kind].format(fields="") + f". After {JAM_HOURS:g} h with no birth this is the owner's step "
                  "(the births cause) when a setting or an agenda clears it (failed calls heal by themselves)."),
        "owner_step": None, "onset": S.epoch(swarm.get("last_birth_at")) if is_dry else None}


def _alerts_check(now: float, alerts: Any, states: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """`swarm_alerts` (the module docstring): the swarm's own alerts, which reach the swarm's record and the House's ledger
    only. Pure. An owner kind (`ALERT_STEPS`) whose condition is read (`states`, `alert_states`) stands with its owner
    step while its condition stands, whatever its alert's age, and not at all once it is cleared; one whose condition is
    not read is the owner's step on the UTC day its alert fired only (the alert's window, `ALERT_HOURS`, may run into the
    next day: there it is INFO), so a fix before midnight does not fail the next day's DONE-RULE item 7. The other kinds
    stand as INFO over the window; the self-healing ones (`ALERT_SELF_HEALING`) are counted, never a cause by
    themselves."""
    alerts = {str(k): v for k, v in (alerts or {}).items() if isinstance(v, Mapping)} if isinstance(alerts, Mapping) else {}
    states = {str(k): v for k, v in (states or {}).items() if isinstance(v, Mapping)} if isinstance(states, Mapping) else {}
    today = S.iso(now)[:10]
    standing: dict[str, dict[str, Any]] = {}
    cleared: list[str] = []
    for kind, rec in alerts.items():
        if kind in ALERT_SELF_HEALING:
            continue
        if kind in ALERT_STEPS and kind in states and not states[kind].get("stands"):
            cleared.append(kind)  # the alert came, its condition is gone: no cause
            continue
        standing[kind] = dict(rec)
    for kind, state in states.items():
        if kind in ALERT_STEPS and state.get("stands") and kind not in standing:
            # A condition that stands though its alert is older than the window (the swarm raises it once).
            standing[kind] = {"n": 0, "first_at": state.get("at"), "last_at": state.get("at"), "text": state.get("text")}

    def owner_kind(kind: str) -> bool:
        if kind not in ALERT_STEPS:
            return False
        if kind in states:
            return bool(states[kind].get("stands"))
        return str(standing[kind].get("last_at") or "")[:10] == today

    ordered = sorted(standing, key=lambda k: (not owner_kind(k), -(S.epoch(standing[k].get("last_at")) or 0.0), k))
    owner = [k for k in ordered if owner_kind(k)]

    def line(kind: str) -> str:
        rec = standing[kind]
        text = rec.get("text") or "no text"
        if not int(rec.get("n") or 0):
            seen = f"; last alert {rec['last_at']}" if rec.get("last_at") else ""
            return f"{kind} (stands now{seen}): {text}"
        late = kind in ALERT_STEPS and kind not in states and not owner_kind(kind)
        return (f"{kind} x{int(rec.get('n') or 0)} (last {rec.get('last_at')}"
                + ("; an earlier UTC day's, no owner step now" if late else "") + f"): {text}")

    lines = [line(k) for k in ordered[:3]]
    numbers: dict[str, Any] = {"alert_kinds": len(alerts)}
    for k in sorted(alerts, key=lambda k: -int(alerts[k].get("n") or 0))[:10]:
        numbers[k[:40]] = int(alerts[k].get("n") or 0)
    numbers.update({"standing_kinds": len(standing), "owner_kinds": len(owner), "cleared_kinds": len(cleared)})
    firsts = [S.epoch(v.get("first_at")) for v in standing.values()]
    count = sum(int(v.get("n") or 0) for v in standing.values())
    return {
        "stalled": bool(standing),
        "what": (f"{len(standing)} of the swarm's alerts stand ({count} raised in the last {ALERT_HOURS:g} h), none of "
                 "which reaches a mail of its own: " + "; ".join(lines)[:380] + "."
                 + (f" Cleared since their alert: {', '.join(sorted(cleared))}." if cleared else "")
                 if standing else f"No swarm alert stands but the self-healing ones"
                 + (f" (cleared since their alert: {', '.join(sorted(cleared))})" if cleared else "") + "."),
        "numbers": numbers,
        "doing": ("Each alert is in the swarm's record (swarm.status) and the House's ledger; the swarm goes on around it. "
                  "The owner kinds are read from the swarm's settings and store at every run, so a fix clears its cause at "
                  "the next. A Sail window that did not answer falls to its fallback for an hour by itself."),
        "owner_step": ("; ".join(ALERT_STEPS[k] for k in owner)[:400] or None) if owner else None,
        "onset": min([t for t in firsts if t is not None], default=None)}


def _expected(figure: float, raised: Mapping[str, Any] | None, day: float, now: float) -> float:
    """What a day's figure buys by `now` at an even pace (the Sail guard's `pace_day`), each hour at the figure that held
    then: the day's first figure until its first TOP-UP RAISE, each raise's figure from its hour (`raises`; a figure
    with the last raise only, `raised_from` and `raised_at`, is read as one step)."""
    raised = raised if isinstance(raised, Mapping) else {}
    steps = []
    for step in raised.get("raises") if isinstance(raised.get("raises"), list) else []:
        at, before, after = (S.epoch(step.get("at")), _finite(step.get("from")), _finite(step.get("to"))) \
            if isinstance(step, Mapping) else (None, None, None)
        if at is not None and before is not None and after is not None and day <= at <= now:
            steps.append((at, before, after))
    if not steps:
        at, before = S.epoch(raised.get("raised_at")), _finite(raised.get("raised_from"))
        if at is not None and before is not None and day <= at <= now:
            steps = [(at, before, figure)]
    if not steps:
        return figure * max(0.0, now - day) / 86400.0
    steps.sort(key=lambda s: s[0])
    first = _finite(raised.get("set_usd_day"))
    level, since, total = steps[0][1] if first is None else first, day, 0.0
    for at, _, after in steps:
        total += level * (at - since)
        level, since = after, at
    return (total + figure * (now - since)) / 86400.0


def _underspend_check(now: float, swarm: Mapping[str, Any], budget: Mapping[str, Any] | None,
                      binds: list[Mapping[str, str]] | None) -> dict[str, Any]:
    """`underspend` (the module docstring): Sail research books under `UNDERSPEND_SHARE` of what the day's figure buys by
    now, or a conflict that binds. Pure. INFO: DONE-RULE item 7 reads "at budget" as no taper, so research held under its
    dollars by a swarm.json cap is invisible there; this names it and the settings that bind.

    Only Sail is paced (the Sail guard's even pace): Claude's figure is spent by the calls of its roles with a line, which
    come when the gate and the strategist have work (the release sets the architect's and the researchers' lines to 0), so
    its reading is said beside Sail's and never stands by itself. A conflict stands by itself only while it binds: the
    class cap under the direction lane's quota (`class_cap`, the release's own pair) once the architect's passes of the
    last `JAM_HOURS` met it (`lane_class_capped`), an architect line under one call's hold (`architect_line`) always."""
    import datetime as dt

    binds = [dict(b) for b in binds or [] if isinstance(b, Mapping)]
    conflicts = [b for b in binds if b.get("kind") == "conflict"]
    lane_capped = int(((swarm.get("yield") or {}).get("jam") or {}).get("lane_class_capped") or 0)
    binding = [b for b in conflicts if b.get("key") != "class_cap" or lane_capped > 0]
    spent = swarm.get("spent_today") if isinstance(swarm.get("spent_today"), Mapping) else None
    day = _finite(swarm.get("day_start"))
    meters = (budget or {}).get("meters") if isinstance(budget, Mapping) else None
    today = dt.datetime.fromtimestamp(now, dt.timezone.utc).date().isoformat()
    brake = swarm.get("brake_today") if isinstance(swarm.get("brake_today"), Mapping) else {}
    braked = float(brake.get("hours") or 0.0)
    short, readings, numbers = [], [], {}
    for meter, word in METER_WORDS.items():
        row = (meters or {}).get(meter) if isinstance(meters, Mapping) else None
        row = row if isinstance(row, Mapping) else {}
        figure = row.get("day_figure") if isinstance(row.get("day_figure"), Mapping) else {}
        usd = _finite(row.get("research_usd_day"))
        if spent is None or day is None or usd is None or usd <= 0 or figure.get("day") != today:
            continue
        due = _expected(usd, figure, day, now)
        booked = float(spent.get(meter) or 0.0)
        share = booked / due if due > 0 else None
        numbers.update({f"{meter}_booked_today": round(booked, 2), f"{meter}_due_by_now": round(due, 2),
                        f"{meter}_share": None if share is None else round(share, 2)})
        if now - day >= UNDERSPEND_MIN_HOURS * 3600 and due >= UNDERSPEND_MIN_USD and share is not None \
                and share < UNDERSPEND_SHARE:
            reading = (f"{word} research booked {booked:.2f} of the {due:.2f} its {usd:.2f} a day buys by now "
                       f"({share:.0%})")
            if meter in PACED_METERS:
                short.append(meter)
                readings.append(reading)
            else:
                lines = [b["text"] for b in binds if b.get("kind") == "line"]
                readings.append(reading + " (not paced: its calls come with the gate's and the strategist's work"
                                + (f"; {lines[0]}" if lines else "") + ")")
    quiet = braked < UNDERSPEND_BRAKE_HOURS
    stalled = bool(short and quiet) or bool(binding)
    caps = [b["text"] for b in binds if b.get("kind") == "cap"]
    drift = [b["text"] for b in binds if b.get("kind") == "drift"]
    what = []
    if readings:
        what.append("; ".join(readings) + ("." if quiet or not short else f", but the guard braked {braked:.1f} h today."))
    if conflicts:
        what.append("Settings that cannot both hold: " + "; ".join(
            b["text"] + ("" if b in binding else " (not binding now: no direction card met the class cap in the last "
                                                 f"{JAM_HOURS:g} h)") for b in conflicts) + ".")
    if caps:
        what.append("Settings tighter than what the budget buys: " + "; ".join(caps[:5]) + ".")
    if drift:
        what.append("Settings under the release's own values: " + "; ".join(drift[:3]) + ".")
    numbers.update({"braked_hours_today": round(braked, 2), "binding_settings": len(caps), "conflicts": len(conflicts),
                    "conflicts_binding": len(binding), f"lane_class_capped_{JAM_HOURS:g}h": lane_capped,
                    "under_release": len(drift)})
    return {
        "stalled": stalled,
        "what": " ".join(what) or "Research books what its day's figure buys, and no setting conflicts.",
        "numbers": numbers,
        "doing": ("The budget only ever tightens the settings: a swarm.json value under what the dollars buy binds "
                  "silently, and DONE-RULE item 7 reads such a day as at budget. Nothing is changed by itself; the "
                  "settings named are the owner's to change (swarm.json)."),
        "owner_step": None, "onset": None}


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


def notice_id(owner: list[str], causes: list[str] | None = None) -> str:
    """The gateway's own dedupe key for the notice (gateway/lib/email.mjs `stallKey` keys it the same way, whatever id
    comes): the owner causes it tells, or, when none needs the owner, `stall:info:` and every cause it tells (since the
    review of the no-captain build, Oct 10, 2026: a new cause needing nothing is mailed at once, so the gateway's 24-hour
    key is the set told, not one key for every such notice)."""
    if owner:
        return "stall:owner:" + "+".join(sorted(owner))
    return "stall:info:" + "+".join(sorted(causes or [])) if causes else "stall:info"


def notice_facts(entries: list[dict[str, Any]], now: float) -> dict[str, Any]:
    """The `stall` notice's facts: every standing cause (`cause_facts`), owner steps first."""
    ordered = [e for e in entries if e.get("owner_step")] + [e for e in entries if not e.get("owner_step")]
    return {"kind": "stall", "notice_id": notice_id([e["cause"] for e in entries if e.get("owner_step")],
                                                    [e["cause"] for e in entries]),
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


def told_lately(mail: Mapping[str, Any], now: float) -> set[str] | None:
    """The causes a SENT notice told in the last `INFO_EVERY_SECONDS` (`stall.json` `mail.told`, {cause: when}); None for
    a state file written before the record was kept (the pace then is the 24-hour one alone)."""
    told = mail.get("told")
    if not isinstance(told, Mapping):
        return None
    return {str(c) for c, at in told.items() if _within(S.epoch(at), now, INFO_EVERY_SECONDS)}


def due_notice(stalled: list[str], owner: list[str], mail: Mapping[str, Any], now: float) -> str | None:
    """Why a notice is due now ("owner" or "info"), or None: the pace in the module docstring. A stall needing nothing is
    due 24 hours after the last notice, or AT ONCE when a cause stands that no notice told in the last 24 hours (the review
    of the no-captain build, Oct 10, 2026: one cause standing for days held every new one back up to a day, the early
    warning of `birth_yield` among them)."""
    owner_at, info_at = S.epoch(mail.get("owner_at")), S.epoch(mail.get("info_at"))
    if owner:
        told = set(mail.get("owner_causes") or []) if _within(owner_at, now, OWNER_EVERY_SECONDS) else set()
        return "owner" if set(owner) - told else None
    if stalled:
        last = max([t for t in (owner_at, info_at) if t is not None], default=None)
        if not _within(last, now, INFO_EVERY_SECONDS):
            return "info"
        told = told_lately(mail, now)
        return "info" if told is not None and set(stalled) - told else None
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
    loaded, load_error = _load(ctx, root)
    ceiling, why = _ceiling(ctx, root, loaded)
    if why:
        errors.append(why)
    binds, why = _binds(ctx, root, loaded)
    if why:
        errors.append(why)
    # THE SWARM'S ALERTS, READ FROM THE STATE (the review of the no-captain build): each owner kind's condition as the
    # swarm's settings and store hold it now; none read, each kind is an owner step on the UTC day it fired only.
    states: dict[str, dict[str, Any]] = {}
    if loaded is not None and isinstance(swarm.get("alert_state"), Mapping):
        try:
            states = alert_states(loaded, swarm["alert_state"], now)
        except Exception as exc:  # noqa: BLE001 - the alerts' window alone, with the day rule
            errors.append(f"the swarm alerts' state could not be read ({type(exc).__name__})")
    elif loaded is None:
        errors.append(f"the swarm's settings could not be read ({load_error}): its alerts are read by their window alone")
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
        lane_on = _lane_on(ctx, root, loaded)
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
                   done_told=done_told, binds=binds, alert_states=states)

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
            if ok:
                # Every cause a sent notice lists is told (`told_lately`): a new one is mailed at once, the rest by the pace.
                lately = {c: at for c, at in (mail.get("told") or {}).items()
                          if _within(S.epoch(at), now, INFO_EVERY_SECONDS)} if isinstance(mail.get("told"), Mapping) else {}
                mail["told"] = {**lately, **{c: S.iso(now) for c in stalled}}
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
           "LANE_OFF_WHAT", "architect_tally", "card_fields", "wanting", "card_refusals", "jam_kind", "lever", "LEVERS",
           "settings_binds", "YIELD_HOURS", "YIELD_PASSES", "YIELD_MAX_BORN", "YIELD_REFUSED_SHARE", "DRY_HOURS", "DRY_PASSES",
           "JAM_HOURS", "JAM_PASSES", "ALERT_HOURS", "ALERT_STEPS", "ALERT_SELF_HEALING", "UNDERSPEND_SHARE",
           "UNDERSPEND_MIN_HOURS", "UNDERSPEND_MIN_USD", "UNDERSPEND_BRAKE_HOURS", "ARCHITECT_HOLD_USD", "JAM_OWNER_KINDS",
           "PACED_METERS", "ALERT_LOOKBACK_KINDS", "ALERT_STATE_DAYS", "GAME_T0_KEY", "alert_states", "release_settings",
           "told_lately"]
