"""The `scoreboard` job (daily 23:30Z): the desk's public-safe daily page, committed through the gateway.

Built from the House's own records only: the latest close economics (`economics.latest`), the job receipts
(`ops.sqlite`), `<base>/deploys.jsonl`, `<state>/budget.json` (when the budget job has written one), the forward
ladder's own counts (`league.live.ladder.counts`, from the practice record once its tables exist), and THE FUNNEL (the
swarm's store, read-only; the swarm's settings, the start its heartbeat names, and the budget in force). It says: the
running release; self-deploys and self-rollbacks; real closes and realized options P&L (since T0 and trailing 30
days); input costs by service since T0; the one Net; how many lots are open and what they are worth at conservative
marks; the budget's state in words, the day research would stop at the present rate and the next card action date per
meter, and the budget in force (THE BUDGET IN WORDS, below); the research funnel; whether
the ladder BINDS or only RECORDS, with its counts, which route leads a research program to Probe and whether the
owner's incubator is a second route to one lot of real money; the day's jobs.

THE BUDGET IN WORDS (release F1, the captain's L8 of Oct 3, 2026). The budget rule's constants are public (the ceiling,
its split, the runway term, the reserves: league/ops/budget.py), so a meter's TAPERED research dollars a day give its
balance by arithmetic. The page therefore never prints a research cap: it says each meter's state in words (at the
ceiling, tapering, at the floor, unread: `METER_WORDS`, `meter_in_force`), the day research would stop at the present
rate when the rule gives one, and the next card action date. The dollars a day stay in the private record
(`funnel.json`'s `budget`). The research dollars actually SPENT in a window stay on the page (the desk's own cost).

THE FUNNEL (the owner's rule 3 of Oct 3, 2026: "Report the funnel daily and redesign whatever blocks it"; `funnel`).
In two windows, since the record's basis (`economics.FS`) and the last 24 hours, what happened IN the window: families
born; families with an eligible Train run; families that ran the unseen-year test (a Validation run at the normal
spread), its runs and its program versions; families that met its line and families the gate took up, each counted in
the window where one of its programs FIRST got there (the tournament's first passing verdict on a version; the gate's
first step on it: a later step on the same version, or a verdict judged again, is no second arrival); the versions the
gate refused or held, by stage; the versions that began to WAIT at the gate for the look's bar (the gate's `look_wait`
events: THE POWER HOLD IS A WAIT, league/swarm/gate.py; a wait closes nothing and bars nothing, so it is counted apart
from the holds, which do), and how many wait now (`gate.waiting`, the gate's own rule, over the living Gym families'
states); the looks made and passed; families that moved UP into Candidate, Probe and Sized,
families that moved down a band (and how many hold each band now); the research dollars booked (the swarm's `spend`)
and the dollars per birth, per unseen-year test, per gate arrival and per look. WHAT THE RESEARCH STREAM OF RELEASE F1
ADDED TO THE STORE, each counted apart from the stage it could be mistaken for: the architect's passes, those paid for
and those it skipped without asking a model, by why (`swarm.architect` events with `skipped`: no cell could bear a
birth, the hour's births were spent, the population at its ceiling; a pass with an error is counted as one that
failed); the programs set aside before the unseen-year test (`swarm.robustness` events, action `set_aside`: a drift
carrier by the gate's own rule, or a one-lot unit over the limit); the verdicts read from an identical program's
test with no run (a Validation row with no trial whose summary names its source: a copy of a record, never counted as
a test, in the chance baseline or in a cost per test); and the families whose version met the line and waits BEFORE
the gate for its unit now (`researcher.unit_waiting`: no hold, no wait of the look's, no arrival). THE CHANCE BASELINE: of the versions
tested, how many cleared the line's t check (`evidence.MIN_T`) against how many would with no edge at all (each
version's own Student t on its traded days), also over distinct results (a fork or a revival that repeats a result is
one result), so a noise pass is never read as an edge. THE LOOK'S BAR: the looks made and passed, the level the next
look is tested at (`evidence.holm_level`, every look really in flight counted as a failed one, as the gate's own hold
counts them: `SwarmStore.looks_inflight`, a retired family's too, and never a stale marker, by the gate's own rule,
`flying`), the levels the looks made were tested at, summed (an upper bound: a gate that counts a look in flight
elsewhere when a look lands tested that look at a lower level), and the
yearly Sharpe a version needs on the unseen year to clear the power hold at the next look (`sharpe_for_power` on
`evidence.holdout_power`, the hold's own figure), with the owner's switches in force as the swarm reads them
(`league.swarm.settings.load`).

The funnel's whole record is PRIVATE (`<state>/ops/funnel.json`, 0600: stages by their store names, dollars by kind,
why a line could not be read, how long each read took). The page carries its counts and thresholds in public words.
Its private `pre_validation` observations count each completed tournament round's admission dispositions and worker
errors, including the latest round, without strategy text or evaluation figures. Repeat rounds are repeat family
observations, never distinct programs. Older or malformed rounds remain unknown; the public page does not use them.
READ-ONLY AND BOUNDED: one `mode=ro` connection (`guard.connect_ro`), each read stopped at `QUERY_SECONDS` and all of
them at `FUNNEL_SECONDS` (SQLite's progress handler), rows folded as they come and never kept whole; no read touches
the notebook, and the only family states decoded are the few that hold a look in flight's marker (as the store's own
reader does) or a wait's. A line that cannot be read (no store, a locked one, a table an older store lacks, a read out
of time) is "n/a" on the page, and every other line stands.

PUBLIC: the page is built from an allowlist of figures (`build`), never from free text the House holds, and then
checked by `public_problems` (no account equity or balance, no quote, contract symbol, strike, box id, parameter or
program text, no Validation or holdout figure: the page's words for those two tests are the unseen-year test and the
unseen-market test). Research hears of a Validation run only whether its line was met and how many of its checks
passed, never which (D2a): so the chance table's figures, which say how many programs met ONE named check, are printed
for a window only over `CHANCE_MIN_PUBLIC` programs or more (the private record holds them all). A page that fails the
check is not posted (the job fails). It is
posted as `POST /v1/github/docs` to `docs/runs/desk/<YYYY-MM-DD>.md` (the gateway's docs route; until that route is
deployed the job keeps the page in `<state>/scoreboard/` and its receipt says it was not posted).
"""
from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

from . import guard
from . import schedule as S
from .context import GatewayError, read_json, write_json, write_text
from .economics import FS, T0
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


#: The forward ladder's counts on the page, in the page's order (`league.live.ladder.counts`).
LADDER_COUNTS = ("entrants", "in_practice", "would_promote", "promoted", "demoted", "failed")


def ladder_counts(root: str | Path, now: float) -> dict[str, Any]:
    """The forward ladder's OWN counts (`league.live.ladder.counts`: read-only, counts only, never a figure, a family or
    a program) through the day of `now`: `binding` (the constitution's `options_money.ladder.binding`: False, the ladder
    only records what it would promote), `entrants` (the trailing 90 days', one a cohort: its Benjamini-Hochberg
    family), `in_practice` (its cohorts practising), `would_promote` (the programs it would have promoted in that
    window), `promoted` (its `promote` receipts: what the live path and the budget rule read as a promotion; a pending
    one is none), `demoted` and `failed` (its cohorts that ended so). "n/a" for a count where the practice record has
    no ladder tables yet or cannot be read, and for `binding` where the money table is refused."""
    out: dict[str, Any] = {"binding": "n/a", **{key: "n/a" for key in LADDER_COUNTS}}
    try:
        from ..live import ladder

        out["binding"] = ladder.Rules.from_constitution().binding
        if "entrants" in _tables(Path(root) / "observe.sqlite"):
            counts = ladder.counts(root, day=S.iso(now)[:10])
            if counts is not None:
                out.update({key: counts[key] for key in LADDER_COUNTS})
    except Exception:  # noqa: BLE001 - what cannot be read stays n/a
        pass
    return out


def sealed_looks() -> bool | None:
    """Whether the gate makes the sealed look, the unseen-market test (`league.swarm.gate.SEALED_LOOKS`, a constant of
    the running release: only the owner's deploy moves it). None when it cannot be read."""
    try:
        from ..swarm import gate

        return gate.SEALED_LOOKS if isinstance(gate.SEALED_LOOKS, bool) else None
    except Exception:  # noqa: BLE001 - what cannot be read is not said
        return None


def ladder_lines(ladder: Mapping[str, Any], *, sealed: bool | None = None, incubator: bool | None = None) -> list[str]:
    """The ladder's section: whether it binds or only records, said from the table's own boolean, then its counts. While
    it only records, the page also says which route leads a research program to Probe, from the release's own switch
    (`sealed`: `sealed_looks`): the unseen-market test at the gate, beside which the ladder records; or, with that test
    off, none. Nothing is said of the route when the switch was not read. That test is the ONE route to real money only
    while the owner's incubator is off (`incubator`: `switches`' `live.incubator`; `league/live/incubator.py` trades one
    lot of real money for a program that never took it), so the page says which it is from that switch, and says
    nothing either way when it was not read. Only a boolean is a switch that was read."""
    binding = ladder.get("binding")
    on = (" The incubator is on: a program that passed the review and the audit and whose practice record is positive "
          "may trade one lot of real money{}; that is never evidence and never a promotion.")
    if binding is True:
        said = "The ladder BINDS: a practice cohort that meets every line at a checkpoint is promoted to Probe."
    elif binding is False:
        said = ("The ladder is RECORDING: it judges every practice cohort at its checkpoints and writes down what it "
                "would promote. It promotes nothing.")
        if sealed is True:
            said += (" A research program's route to Probe is the unseen-market test at the gate: a program that "
                     "passes it is a Candidate; the money table moves a Candidate that fits its Probe row to Probe with "
                     "no count of sessions to wait for, and it can trade real money at Probe size from the next session "
                     "to open. The ladder records beside that route. It makes no read of the unseen market of its own "
                     "while that test is its one reader, so its would-promote count stays 0.")
            if incubator is True:
                said += on.format(" before that test")
            elif incubator is False:
                said += " The incubator is off: no research program opens a real position before that test."
        elif sealed is False:
            said += (" The unseen-market test is off in this release and the ladder does not bind: no program has a "
                     "route to Probe.")
            if incubator is True:
                said += on.format("")
    else:
        said = "Whether the ladder binds could not be read."
    return [said, "",
            "| Entrants (90 d: the false-discovery family) | In practice | Would promote (90 d) | Promoted | Demoted | Failed |",
            "|---:|---:|---:|---:|---:|---:|",
            "| " + " | ".join(_cell(ladder.get(key)) for key in LADDER_COUNTS) + " |"]


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


#: THE BUDGET IN WORDS: a meter's research by what limits it (`league.ops.budget.compute`'s `limited_by`), in the page's
#: words. Never its dollars a day: with the rule's public constants a tapered figure gives the meter's balance.
METER_WORDS = {"ceiling": "at the ceiling", "runway": "tapering", "unreadable": "unread"}
#: The research budget against the last file, as the rule says it (`league.ops.budget.compute`'s `direction`).
DIRECTIONS = ("cut", "raise", "same")
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def _day(value: Any) -> str:
    """A calendar day as the budget rule writes one (YYYY-MM-DD), or "n/a": no other text of the file is printed here."""
    return value if isinstance(value, str) and _DAY.fullmatch(value) else "n/a"


def budget_lines(budget: Mapping[str, Any] | None) -> list[str]:
    """The budget's state and, per meter, its research in words (`METER_WORDS`), the day research would stop at the
    present rate when the rule gives one (`runs_out_on`: fixed cost and today's research, with no top-up) and the next
    card action date: the rule's own words and dates, never a balance and never a research cap (THE BUDGET IN WORDS).
    The state is printed only while it is words (a state that came to hold a figure is left out, never printed), and
    the direction only when it is one of the rule's three (`DIRECTIONS`)."""
    if not isinstance(budget, Mapping):
        return ["No budget state yet (the budget job has not written one)."]
    lines = []
    state = budget.get("state") or budget.get("status")
    if isinstance(state, str) and state and not re.search(r"\d", state):  # the rule's words; never a figure in them
        lines.append(f"State: {state}.")
    if budget.get("direction") in DIRECTIONS:
        lines.append(f"Research budget against yesterday: {budget['direction']}.")
    meters = budget.get("meters") if isinstance(budget.get("meters"), Mapping) else {}
    cards = budget.get("next_card_action") if isinstance(budget.get("next_card_action"), Mapping) else {}
    rows = []
    for meter in sorted(set(meters) | set(cards)):
        row = meters.get(meter) if isinstance(meters.get(meter), Mapping) else {}
        limited = row.get("limited_by")
        research = METER_WORDS.get(limited, "n/a") if isinstance(limited, str) else "n/a"
        card = cards.get(meter) or row.get("next_card_action") or row.get("card_date")
        rows.append(f"| {meter} | {research} | {_day(row.get('runs_out_on'))} | {_day(card)} |")
    if rows:
        lines += ["", "| Meter | Research | Would stop at the present rate on | Next card action |", "|---|---|---|---|", *rows]
    return lines or ["The budget state names no meter."]


# ------------------------------------------------------------------------------------------------ the funnel
#: The funnel's private record (under `<state>`, 0600) and its format.
FUNNEL_FILE = "ops/funnel.json"
FUNNEL_SCHEMA = 1
#: The funnel's windows: (key, the page's words, seconds back from now; None is from the record's basis, `economics.FS`).
WINDOWS: tuple[tuple[str, str, float | None], ...] = (("since_basis", "Since the basis", None),
                                                      ("last_24h", "Last 24 hours", 86400.0))
#: The read of the swarm's store is bounded: one read stops after QUERY_SECONDS and all of them after FUNNEL_SECONDS (the
#: job's own limits are 120 s of CPU and 300 s of wall time), a lock is waited for STORE_TIMEOUT, and SQLite asks the
#: clock every PROGRESS_OPS steps of its virtual machine.
QUERY_SECONDS = 10.0
FUNNEL_SECONDS = 30.0
STORE_TIMEOUT = 5.0
PROGRESS_OPS = 1000
#: Sessions a year: a yearly Sharpe is a daily one times the root of this.
SESSIONS_A_YEAR = 252
#: The bands past the Gym, in the page's order.
FUNNEL_BANDS = ("candidate", "probe", "sized")
#: The living bands by rank (`league.swarm.store.BANDS`): a move to a higher one is an entry, to a lower one a demotion.
BAND_RANK = {"gym": 0, "candidate": 1, "probe": 2, "sized": 3}
#: The fewest programs tested in a window for the page to print that window's chance figures (the module docstring's
#: PUBLIC: over one or two programs they would say which check a program met, and luck's figures are noise).
CHANCE_MIN_PUBLIC = 20
#: The funnel's reads of the swarm's store (`league/swarm/store.py`), each one line of the page. `?` is the first instant
#: of the longest window (ISO for `at`, the epoch for `spend`). None reads the notebook. `in_flight` searches every
#: family's state text, alive or retired, for a look in flight's marker (as `SwarmStore.looks_inflight` does: a look out
#: when its family retired is still recorded when it lands), and only the states it finds are decoded; which of those
#: markers are looks really in flight is `flying`'s to say. An eligible
#: Train run is found by its flag as the store writes it (`store.dumps`: sorted keys, no spaces; a run from before the
#: flag, Sept 26, 2026, is not counted).
#: Timed on a copy of production's store of Oct 3, 2026 (504 MB: 2,373 families, 81,441 runs, 161,659 events, 192,487
#: spend rows), each read alone with the file's pages in memory and (in brackets) dropped first: born 3 ms (260),
#: eligible 100 ms (870), tests 30 ms (790), line 3 ms (70), in_flight 4 ms (280), bands_now 2 ms (200), usd 33 ms
#: (780), every other read under 5 ms; the whole funnel 0.2 s (1.6 s). The reads from the basis grow with the store, a
#: row at a time. The reads release F1's research stream added (`passes`, `set_aside`, `unit_waiting`), on that copy
#: with its pages in memory: under 10 ms each.
READS = {
    "born": "SELECT born_at AS at FROM families WHERE born_at >= ? AND born_at <= ?",
    "eligible": "SELECT family, at FROM runs WHERE window='train' AND stress=1.0 AND status='ok' AND at >= ? AND at <= ? "
                "AND instr(summary, '\"train_eligible\":true') > 0",
    # `trials`: a Validation row with no trial whose summary names a source is a copy of another family's record
    # (release F1: AN IDENTICAL PROGRAM IS VALIDATED ONCE, `Tournament.judge` with `inherited`): no run, so no test
    # (`_tests` counts the copies apart).
    "tests": "SELECT family, version, at, summary, trials FROM runs WHERE window='validation' AND stress=1.0 AND status='ok' "
             "AND at >= ? AND at <= ?",
    "passes": "SELECT at, payload FROM events WHERE kind='swarm.architect' AND at >= ? AND at <= ?",
    "pre_validation": "SELECT at, CASE WHEN json_valid(payload) THEN json_extract(payload,'$.validation.pre_validation') "
                      "ELSE NULL END AS telemetry FROM events WHERE kind='swarm.tournament' AND at >= ? AND at <= ? "
                      "ORDER BY at,seq",
    "set_aside": "SELECT at, family, payload FROM events WHERE kind='swarm.robustness' AND at >= ? AND at <= ? AND family IS NOT NULL "
                 "AND instr(payload, '\"action\":\"set_aside\"') > 0",
    "line": "SELECT at, payload FROM events WHERE kind='swarm.tournament' AND at >= ? AND at <= ? "
            "AND instr(payload, '\"passed\":true') > 0",
    "gate": "SELECT at, family, payload FROM events WHERE kind='swarm.gate' AND at >= ? AND at <= ? AND family IS NOT NULL",
    "refusals": "SELECT family, version, at, stage FROM refusals WHERE at >= ? AND at <= ?",
    "holds": "SELECT family, version, at, stage FROM look_holds WHERE at >= ? AND at <= ?",
    "waits": "SELECT at, family, payload FROM events WHERE kind='swarm.gate' AND at >= ? AND at <= ? AND family IS NOT NULL "
             "AND instr(payload, '\"action\":\"look_wait\"') > 0",
    "waiting": "SELECT state FROM families WHERE retired_at IS NULL AND band='gym' AND instr(state, '\"look_wait\":{') > 0",
    "unit_waiting": "SELECT state FROM families WHERE retired_at IS NULL AND band='gym' "
                    "AND instr(state, '\"unit_wait\":{') > 0",
    "looks": "SELECT family, version, at, passed, p_value FROM looks WHERE at <= ? ORDER BY seq",
    "in_flight": "SELECT state FROM families WHERE instr(state, '\"look_inflight\":{') > 0",
    "bands_now": "SELECT band, COUNT(*) AS n FROM families WHERE retired_at IS NULL GROUP BY band",
    "band_moves": "SELECT at, family, payload FROM events WHERE kind='swarm.band' AND at >= ? AND at <= ?",
    "usd": "SELECT kind, SUM(usd) AS usd FROM spend WHERE epoch >= ? AND epoch <= ? GROUP BY kind",
}
#: The gate's events that say it took a family's version up (`league/swarm/gate.py`): a review, an audit, a look (made,
#: failed, or owed for missing data), a hold, a wait's first round, the refusal of a repeat or of a program refused
#: before, a place closed to practice.
GATE_ARRIVALS = frozenset({"review", "review_error", "audit", "audit_error", "look", "look_failed", "look_missing_data",
                           "look_hold", "look_wait", "duplicate_look", "program_bar", "to_practice"})
#: The gate's events that name a family and are no arrival: the operator's own hold, the incubator's reads and bars, the
#: ladder's free read of a program already sent to practice, and the nightly forward. A test holds every action the
#: swarm writes on a family's `swarm.gate` event to one set or the other, so a new one is placed before it is counted.
GATE_NOT_ARRIVALS = frozenset({"gate_hold", "gate_hold_cleared", "incubator_bar", "incubator_bar_error", "incubator_error",
                               "incubator_review", "incubator_review_error", "incubator_audit", "incubator_audit_error",
                               "prefilter", "forward_failed"})
#: The gate's stages in the page's words. A stage's own name never reaches the page (the store's text is not public
#: text, and one stage's name holds a word the page's filter refuses); one the page does not know is "another reason".
#: "the power hold" is a hold ROW's stage: one written before release F1, when that hold closed a version for good.
#: Since F1 it writes no row (a version it stops WAITS, and is counted with the waits: `_waits`).
STAGE_WORDS = {"experiment contract": "the experiment contract", "drift screen": "the drift screen",
               "rations": "the lineage's looks were spent", "duplicate look": "a repeat of an earlier look",
               "program bar": "the program was refused before", "review": "the review", "audit": "the audit",
               "gym": "the test could not be run", "look hold (drift)": "the drift hold",
               "look hold (power)": "the power hold", "look hold (holdout read)": "its unseen market was read before"}
#: The budget in force's source in the page's words (`budget.effective`'s `source`).
BUDGET_SOURCES = {"budget.json": "budget.json", "floor": "the floor, no usable budget.json",
                  "stale budget.json": "a stale budget.json, never above the floor"}


def _object(text: Any) -> dict[str, Any]:
    """A JSON object from the store's text, or {}."""
    try:
        value = json.loads(text) if isinstance(text, (str, bytes)) else text
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _na(value: Any, fmt: str = "{}") -> str:
    """A figure in the page's form, or "n/a" for one that was not read. Only a number is a figure: no text a record
    holds is ever printed through this."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return "n/a"
    try:
        return fmt.format(value)
    except (TypeError, ValueError):
        return "n/a"


def _at(record: Any, *path: str) -> Any:
    """`record[path...]`, None wherever a step is not there."""
    value: Any = record
    for step in path:
        value = value.get(step) if isinstance(value, Mapping) else None
    return value


def _whole(value: Any) -> bool:
    """Whether `value` is a count: an integer, never a boolean."""
    return isinstance(value, int) and not isinstance(value, bool)


class _Store:
    """The swarm's store for the funnel (the module docstring's READ-ONLY AND BOUNDED): one read-only connection in one
    read transaction. `rows` yields one bounded read's rows as they come and closes its cursor. A locked store ends the
    whole read: every later line is n/a at once, never one wait a line."""

    def __init__(self, path: Path, now: float):
        self.until = (S.iso(now), now)
        self.end = time.monotonic() + FUNNEL_SECONDS
        self.deadline = self.end
        self.dead: str | None = None
        self.db = guard.connect_ro(path, timeout=STORE_TIMEOUT)
        try:
            self.db.set_progress_handler(lambda: 1 if time.monotonic() > self.deadline else 0, PROGRESS_OPS)
            self.db.execute("BEGIN")
        except Exception:
            self.db.close()
            raise

    def rows(self, sql: str, params: Sequence[Any] = ()) -> Iterator[Any]:
        if self.dead:
            raise RuntimeError(self.dead)
        now = time.monotonic()
        if now >= self.end:
            raise TimeoutError(f"the funnel's {FUNNEL_SECONDS:g} s were spent before this read")
        self.deadline = min(self.end, now + QUERY_SECONDS)
        try:
            cursor = self.db.execute(sql, tuple(params))
            try:
                yield from cursor
            finally:
                cursor.close()
        except Exception as exc:  # noqa: BLE001 - said again in the funnel's own words; the caller's line is n/a
            text = str(exc).lower()
            if "interrupt" in text:
                raise TimeoutError(f"the read was stopped at its time limit ({QUERY_SECONDS:g} s)") from None
            if "locked" in text or "busy" in text:
                self.dead = "the store is locked"
            raise

    def close(self) -> None:
        try:
            self.db.rollback()
        finally:
            self.db.close()


def windows(now: float) -> dict[str, tuple[str, float]]:
    """Each window's first instant, (ISO, epoch), by its key (`WINDOWS`); never before the record's basis."""
    basis = S.epoch(FS) or 0.0
    out = {}
    for key, _, back in WINDOWS:
        first = basis if back is None else max(basis, float(now) - back)
        out[key] = (S.iso(first), first)
    return out


def _first(since: Mapping[str, tuple[str, float]]) -> tuple[str, float]:
    return min(since.values(), key=lambda pair: pair[1])


def _born(store: _Store, since: Mapping[str, tuple[str, float]]) -> dict[str, int]:
    born = [str(row["at"]) for row in store.rows(READS["born"], (_first(since)[0], store.until[0]))]
    return {key: sum(1 for at in born if at >= iso) for key, (iso, _) in since.items()}


def _eligible(store: _Store, since: Mapping[str, tuple[str, float]]) -> dict[str, int]:
    last: dict[str, str] = {}  # a family's newest eligible Train run
    for row in store.rows(READS["eligible"], (_first(since)[0], store.until[0])):
        if str(row["at"]) > last.get(row["family"], ""):
            last[row["family"]] = str(row["at"])
    return {key: sum(1 for at in last.values() if at >= iso) for key, (iso, _) in since.items()}


def _tests(store: _Store, since: Mapping[str, tuple[str, float]]) -> dict[str, dict[str, Any]]:
    """The unseen-year tests, and THE CHANCE BASELINE over the versions tested (a version's newest run in the window is
    its test): `cleared`, those whose daily t met the line's `evidence.MIN_T`; `by_luck`, the sum of each one's chance
    of that with no edge at all (Student's t on its own traded days less one), and `by_luck_sd`, that count's standard
    deviation were the tests independent (they share one year and many roots, so the true spread is wider); `distinct`,
    the same over distinct results (the same trades, traded days, t and P&L are one result: a fork or a revival that
    repeats a program repeats its result). `inherited`: the verdicts read from an identical program's test with no run
    (release F1: a row with no trial whose summary names its source, `Tournament.judge` with `inherited`): a copy of a
    record, so it is no test, in no count above and in no cost per test."""
    from .. import stats
    from ..swarm import evidence

    runs, copies = [], []
    for row in store.rows(READS["tests"], (_first(since)[0], store.until[0])):
        s = _object(row["summary"])
        if row["trials"] == 0 and isinstance(s.get("inherited"), dict):
            copies.append(str(row["at"]))
            continue
        days = evidence._num(s.get("days_traded"))
        runs.append((str(row["at"]), str(row["family"]), row["version"], evidence.daily_t(s), int(days or 0),
                     tuple(repr(s.get(k)) for k in ("trades", "days_traded", "t_daily", "pnl"))))
    runs.sort(key=lambda run: run[0])
    out = {}
    for key, (iso, _) in since.items():
        mine = [run for run in runs if run[0] >= iso]
        latest = {(run[1], run[2]): run for run in mine}
        judged = [run for run in latest.values() if run[3] is not None and run[4] >= 2]
        luck = [stats._t_tail(evidence.MIN_T, run[4] - 1) for run in judged]
        distinct: dict[tuple[str, ...], tuple[bool, float]] = {}
        for run, p in zip(judged, luck):
            distinct.setdefault(run[5], (run[3] >= evidence.MIN_T, p))
        out[key] = {"families": len({run[1] for run in mine}), "versions": len(latest), "runs": len(mine),
                    "inherited": sum(1 for at in copies if at >= iso),
                    "chance": {"t": evidence.MIN_T, "versions": len(judged),
                               "cleared": sum(1 for run in judged if run[3] >= evidence.MIN_T),
                               "by_luck": round(sum(luck), 2),
                               "by_luck_sd": round(math.sqrt(sum(p * (1.0 - p) for p in luck)), 2),
                               "distinct": {"results": len(distinct),
                                            "cleared": sum(1 for cleared, _ in distinct.values() if cleared),
                                            "by_luck": round(sum(p for _, p in distinct.values()), 2)}}}
    return out


#: A program's first instant at a stage, by (family, version); a row that names no version is keyed (family, None).
Firsts = dict[tuple[str, Any], str]


def _firsts(found: Iterable[tuple[Any, ...]]) -> Firsts:
    """The first instant of each program among (at, family, version) triples."""
    out: Firsts = {}
    for at, fid, version in found:
        key = (str(fid), version if _whole(version) else None)
        if key not in out or str(at) < out[key]:
            out[key] = str(at)
    return out


def _earliest(*parts: Mapping[tuple[str, Any], str]) -> Firsts:
    """Each program's first instant across `parts`."""
    return _firsts((at, fid, version) for part in parts for (fid, version), at in part.items())


def _arrived(firsts: Mapping[tuple[str, Any], str], since: Mapping[str, tuple[str, float]]) -> dict[str, int]:
    """The families with a program whose first instant is in each window."""
    return {key: len({fid for (fid, _), at in firsts.items() if at >= iso}) for key, (iso, _) in since.items()}


def _line(store: _Store, since: Mapping[str, tuple[str, float]]) -> Firsts:
    """Each program's first passing verdict at the line (the tournament's round, `validation.judged`, a verdict a
    family: a verdict judged again from a recorded result is the same program's, so no second one)."""
    def met() -> Iterator[tuple[str, str, Any]]:
        for row in store.rows(READS["line"], (_first(since)[0], store.until[0])):
            judged = _object(_object(row["payload"]).get("validation")).get("judged")
            for fid, verdict in (judged.items() if isinstance(judged, dict) else ()):
                if isinstance(verdict, dict) and verdict.get("passed") is True:
                    yield str(row["at"]), str(fid), verdict.get("version")
    return _firsts(met())


def _gate(store: _Store, since: Mapping[str, tuple[str, float]]) -> Firsts:
    """Each program's first step at the gate among its events (`GATE_ARRIVALS`)."""
    def taken() -> Iterator[tuple[str, str, Any]]:
        for row in store.rows(READS["gate"], (_first(since)[0], store.until[0])):
            payload = _object(row["payload"])
            if payload.get("action") in GATE_ARRIVALS:
                yield str(row["at"]), str(row["family"]), payload.get("version")
    return _firsts(taken())


def _stages(name: str) -> Callable[[_Store, Mapping[str, tuple[str, float]]], dict[str, Any]]:
    """The reader of a table of the gate's verdicts by stage (`refusals`, `look_holds`): a row a version. `first` is each
    program's first row."""
    def read(store: _Store, since: Mapping[str, tuple[str, float]]) -> dict[str, Any]:
        rows = [(str(row["at"]), str(row["family"]), row["version"], str(row["stage"]))
                for row in store.rows(READS[name], (_first(since)[0], store.until[0]))]
        out: dict[str, Any] = {"first": _firsts(row[:3] for row in rows)}
        for key, (iso, _) in since.items():
            stages: dict[str, int] = {}
            for at, _, _, stage in rows:
                if at >= iso:
                    stages[stage] = stages.get(stage, 0) + 1
            out[key] = {"stages": dict(sorted(stages.items()))}
        return out
    return read


def _waits(store: _Store, since: Mapping[str, tuple[str, float]]) -> dict[str, int]:
    """The programs that began to WAIT at the gate for the look's bar, by window: the gate's `look_wait` events, one the
    first time a version waits (`gate.Gate.wait_look`); a version is counted once, at its first."""
    first = _firsts((str(row["at"]), str(row["family"]), _object(row["payload"]).get("version"))
                    for row in store.rows(READS["waits"], (_first(since)[0], store.until[0]))
                    if _object(row["payload"]).get("action") == "look_wait")
    return {key: sum(1 for at in first.values() if at >= iso) for key, (iso, _) in since.items()}


def _waiting(store: _Store, since: Mapping[str, tuple[str, float]]) -> int:
    """The living Gym families whose validated version waits at the gate NOW, by the gate's own rule (`gate.waiting`:
    a marker that outlived its wait is no place). Only the states that hold a wait's marker are decoded."""
    from ..swarm import gate

    return sum(1 for row in store.rows(READS["waiting"]) if gate.waiting(_object(row["state"])) is not None)


def _unit_waiting(store: _Store, since: Mapping[str, tuple[str, float]]) -> int:
    """The living Gym families whose version met the line and waits BEFORE the gate for its unit NOW (release F1, THE
    UNIT ON VALIDATION: `researcher.unit_waiting`, the tournament's own mark, while the validation it names met the
    line): no review, audit or look is spent on it, it was not held and it holds no place at the gate, so it is counted
    apart from the holds and from the look's waits. Only the states that hold the mark are decoded."""
    from ..swarm.researcher import unit_waiting

    count = 0
    for row in store.rows(READS["unit_waiting"]):
        state = _object(row["state"])
        count += unit_waiting(state) is not None and _at(state, "validation_line", "passed") is True
    return count


#: The architect's passes that asked no model, by the event's `skipped` (`league/swarm/architect.py` SKIPPED_NO_CELL,
#: SKIPPED_PACED, SKIPPED_CEILING), in the page's order; any other word is "other".
PASS_SKIPS = ("no_cell", "paced", "ceiling")


def _passes(store: _Store, since: Mapping[str, tuple[str, float]]) -> dict[str, dict[str, Any]]:
    """The architect's passes by window (its `swarm.architect` events, one a pass): `paid`, those that asked a model;
    `failed`, those that ended in an error; `skipped`, those that asked none, by why (PASS_SKIPS: no cell a birth may
    land in could bear one, the hour's births were spent, the population at its ceiling), each counted apart: a pass
    the cells' pace stopped is not a pass no cell could bear."""
    passes = []
    for row in store.rows(READS["passes"], (_first(since)[0], store.until[0])):
        payload = _object(row["payload"])
        skipped = payload.get("skipped")
        kind = ((skipped if skipped in PASS_SKIPS else "other") if isinstance(skipped, str) and skipped
                else "failed" if payload.get("error") else "paid")
        passes.append((str(row["at"]), kind))
    out = {}
    for key, (iso, _) in since.items():
        mine = [kind for at, kind in passes if at >= iso]
        out[key] = {"paid": mine.count("paid"), "failed": mine.count("failed"),
                    "skipped": {kind: mine.count(kind) for kind in (*PASS_SKIPS, "other")}}
    return out


def _set_aside(store: _Store, since: Mapping[str, tuple[str, float]]) -> dict[str, int]:
    """The programs set aside before the unseen-year test, by window (release F1, GATE-READY AT TRAIN: the tournament's
    and the researcher's `swarm.robustness` events with action `set_aside`): a version counted once, at its first."""
    first = _firsts((str(row["at"]), str(row["family"]), _object(row["payload"]).get("version"))
                    for row in store.rows(READS["set_aside"], (_first(since)[0], store.until[0]))
                    if _object(row["payload"]).get("action") == "set_aside")
    return {key: sum(1 for at in first.values() if at >= iso) for key, (iso, _) in since.items()}


def _pre_validation(store: _Store, since: Mapping[str, tuple[str, float]]) -> dict[str, Any]:
    """Private bounded observation counts, not new evaluation evidence. A missing receipt supplies no inferred zero;
    known counts cover only `observed_rounds`, while `unknown_rounds` discloses the uncovered history. Stream each
    fixed-size receipt into the windows and retain only the latest round's receipt (None when it was unknown)."""
    from ..swarm.tournament import VALIDATION_DISPOSITIONS, VALIDATION_TELEMETRY_SCHEMA

    out = {key: {"rounds": 0, "observed_rounds": 0, "unknown_rounds": 0, "family_observations": None,
                 "dispositions": None, "worker_errors": None, "latest": None} for key in since}
    for row in store.rows(READS["pre_validation"], (_first(since)[0], store.until[0])):
        receipt = _object(row["telemetry"])
        counts = receipt.get("dispositions")
        considered, errors = receipt.get("considered"), receipt.get("worker_errors")
        valid = (type(receipt.get("schema")) is int and receipt["schema"] == VALIDATION_TELEMETRY_SCHEMA
                 and type(considered) is int and considered >= 0 and type(errors) is int and errors >= 0
                 and isinstance(counts, Mapping) and set(counts) == set(VALIDATION_DISPOSITIONS)
                 and all(type(n) is int and n >= 0 for n in counts.values())
                 and sum(counts.values()) == considered and errors <= counts["queued"])
        # Copy only the fixed schema, even if an event has extra private text beside its telemetry.
        known = ({"schema": VALIDATION_TELEMETRY_SCHEMA, "considered": considered,
                  "dispositions": {name: counts[name] for name in VALIDATION_DISPOSITIONS}, "worker_errors": errors}
                 if valid else None)
        for key, (iso, _) in since.items():
            if str(row["at"]) < iso:
                continue
            block = out[key]
            block["rounds"] += 1
            block["latest"] = {"at": str(row["at"]), "receipt": known}
            if known is None:
                block["unknown_rounds"] += 1
                continue
            if block["observed_rounds"] == 0:
                block.update(family_observations=0, dispositions=dict.fromkeys(VALIDATION_DISPOSITIONS, 0), worker_errors=0)
            block["observed_rounds"] += 1
            block["family_observations"] += considered
            block["worker_errors"] += errors
            for name in VALIDATION_DISPOSITIONS:
                block["dispositions"][name] += counts[name]
    return out


def _looks(store: _Store, since: Mapping[str, tuple[str, float]]) -> dict[str, Any]:
    """Every look the swarm has made (Holm counts them all), in order; the looks of each window; and `first`, each
    program's look inside the longest window."""
    looks = [(str(row["at"]), str(row["family"]), row["version"], bool(row["passed"]), row["p_value"])
             for row in store.rows(READS["looks"], (store.until[0],))]
    out: dict[str, Any] = {"all": [(passed, p) for _, _, _, passed, p in looks],
                           "first": _firsts(look[:3] for look in looks if look[0] >= _first(since)[0])}
    for key, (iso, _) in since.items():
        mine = [look for look in looks if look[0] >= iso]
        out[key] = {"made": len(mine), "passed": sum(1 for look in mine if look[3])}
    return out


def _in_flight(store: _Store, since: Mapping[str, tuple[str, float]]) -> list[Any]:
    """The markers of the looks out, as the store's own reader finds them (`SwarmStore.looks_inflight`): for each
    family's own marker that names a look, whether the family is alive or retired, the time it was set (whatever the
    marker holds there). Which of them are looks really in flight is `flying`'s to say."""
    states = (_object(row["state"]) for row in store.rows(READS["in_flight"]))
    return [_at(state, "look_inflight", "at") for state in states if _at(state, "look_inflight", "sha")]


def _bands_now(store: _Store, since: Mapping[str, tuple[str, float]]) -> dict[str, int]:
    held = {str(row["band"]): int(row["n"] or 0) for row in store.rows(READS["bands_now"])}
    return {band: held.get(band, 0) for band in FUNNEL_BANDS}


def _band_moves(store: _Store, since: Mapping[str, tuple[str, float]]) -> dict[str, dict[str, Any]]:
    """The families that moved UP into each band, and `demoted`, those that moved down (`SwarmStore.set_band`'s
    `swarm.band` events, from one band to another: the money table moves a family both ways), by window. A demotion is
    never an entry into the lower band; a move whose bands the event does not name is neither."""
    moves = []
    for row in store.rows(READS["band_moves"], (_first(since)[0], store.until[0])):
        payload = _object(row["payload"])
        was, to = payload.get("band_from"), payload.get("band_to")
        if isinstance(was, str) and isinstance(to, str) and was in BAND_RANK and to in BAND_RANK:
            moves.append((str(row["at"]), str(row["family"]), to, BAND_RANK[to] - BAND_RANK[was]))
    out = {}
    for key, (iso, _) in since.items():
        mine = [move for move in moves if move[0] >= iso]
        out[key] = {"entered": {band: len({fid for _, fid, to, step in mine if to == band and step > 0})
                                for band in FUNNEL_BANDS},
                    "demoted": len({fid for _, fid, _, step in mine if step < 0})}
    return out


def _usd(store: _Store, since: Mapping[str, tuple[str, float]]) -> dict[str, dict[str, Any]]:
    """The research dollars the swarm booked (its `spend`: Sail models, Gym boxes, the paid models), by window."""
    out = {}
    for key, (_, first) in since.items():
        kinds = {str(row["kind"]): round(float(row["usd"] or 0.0), 4)
                 for row in store.rows(READS["usd"], (first, store.until[1]))}
        out[key] = {"booked": round(sum(kinds.values()), 4), "by_kind": dict(sorted(kinds.items()))}
    return out


#: The funnel's parts read from the store, in the order they are read.
STORE_PARTS: tuple[tuple[str, Callable[[_Store, Mapping[str, tuple[str, float]]], Any]], ...] = (
    ("born", _born), ("eligible", _eligible), ("tests", _tests), ("line", _line), ("gate", _gate),
    ("refusals", _stages("refusals")), ("holds", _stages("holds")), ("waits", _waits), ("waiting", _waiting),
    ("looks", _looks), ("in_flight", _in_flight),
    ("bands_now", _bands_now), ("band_moves", _band_moves), ("usd", _usd),
    ("passes", _passes), ("set_aside", _set_aside), ("unit_waiting", _unit_waiting), ("pre_validation", _pre_validation))


def sharpe_for_power(power: Any, sessions: Any, level: Any) -> float | None:
    """The least all-days daily Sharpe at which the holdout's test has `power` at `level` over `sessions` days, found on
    the power hold's own figure (`league.swarm.evidence.holdout_power`, which rises with the Sharpe) by bisection. None
    when that figure cannot be made, or `power` is not strictly between 0 and 1."""
    from ..swarm import evidence

    power = evidence._num(power)
    if power is None or not 0.0 < power < 1.0 or evidence.holdout_power(0.0, sessions, level) is None:
        return None
    low, high = -10.0, 10.0
    for _ in range(80):
        middle = (low + high) / 2.0
        if evidence.holdout_power(middle, sessions, level) >= power:
            high = middle
        else:
            low = middle
    return high


def flying(marked: Sequence[Any], root: str | Path, now: float, config: Mapping[str, Any] | None = None) -> int:
    """THE LOOKS REALLY IN FLIGHT, as the gate's own hold counts them (`gate.Gate.flying_elsewhere`), by the gate's own
    rule (`gate.marker_stale`): of the markers the store holds (`marked`: the time each was set, `_in_flight`), those
    set since the running swarm started (its heartbeat's `started_at`: no Gym job survives its process) and no longer
    ago than a look is given (the run timeout as the swarm reads its settings now, and twenty minutes). A stale marker
    is no look: the gate counts none (its round owes that look again), and a page that counted one would say a lower
    level, and a higher Sharpe to clear the power hold, than the gate applies. With no heartbeat to read (no swarm has
    written one on this state, or its start is no number) only the time limit can be judged, so the page's count is
    then never under the gate's."""
    from ..swarm import HEARTBEAT, evidence, gate
    from ..swarm import settings as swarm_settings

    started = evidence._num(_at(read_json(Path(root) / HEARTBEAT, None), "started_at"))  # a finite number, or None
    effective = swarm_settings.load(root, config=config)
    return sum(1 for at in marked if not gate.marker_stale({"at": at}, started_at=-math.inf if started is None else started,
                                                           now=float(now), settings=effective))


def look_bar(looks: Sequence[tuple[bool, Any]], *, in_flight: int = 0, min_power: Any = None,
             sessions: Any = None) -> dict[str, Any]:
    """THE LOOK'S BAR (the module docstring) from every look made, in order, as (passed, p): `made`, `passed`;
    `next_level`, the level the next look is tested at under Holm across every look (`evidence.holm_level`; a look in
    flight counted as a failed one, as `gate.Gate.look_hold` counts it); `level_spent`, the sum of the levels the looks
    made were each tested at when they were made, in their order (the first at the whole 0.05: the sum passes 0.05 at
    the second look), which is the most they can have been tested at: a gate that counts a look in flight elsewhere as
    a failed one when a look lands tested that look lower;
    `sharpe_yearly_for_hold`, the yearly Sharpe at which a version's expected power at the next look reaches `min_power`
    (the power hold's line; None while that hold is off), and `sharpe_yearly_even_chance`, the one at which the look's
    own test passes half the time."""
    from ..swarm import evidence

    ps = [float(p) for _, p in looks if evidence._num(p) is not None]
    spent = sum(evidence.holm_level(ps[:k]) for k in range(len(ps)))
    level = evidence.holm_level(ps + [1.0] * max(0, int(in_flight)))
    year = math.sqrt(SESSIONS_A_YEAR)
    hold, even = sharpe_for_power(min_power, sessions, level), sharpe_for_power(0.5, sessions, level)
    return {"made": len(looks), "passed": sum(1 for passed, _ in looks if passed), "in_flight": max(0, int(in_flight)),
            "alpha": evidence.HOLDOUT_ALPHA, "next_level": round(level, 6), "level_spent": round(spent, 6),
            "sessions": sessions, "min_power": min_power,
            "sharpe_daily_for_hold": None if hold is None else round(hold, 4),
            "sharpe_yearly_for_hold": None if hold is None else round(hold * year, 2),
            "sharpe_yearly_even_chance": None if even is None else round(even * year, 2)}


def switches(root: str | Path, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The owner's switches the route to real money depends on, as the swarm reads them now
    (`league.swarm.settings.load`: the defaults, the release's config and policy, `<state>/swarm.json`), each through
    its own reader: `gate.look_holds` (`gate.look_hold_settings`: a hold that is off is None), `tournament.drift_screen`
    (`researcher.drift_settings`: only JSON false turns it off) and `live.incubator` (on only while JSON true, and, as
    the live path reads `live` from `<state>/swarm.json` alone, only while that file itself says so). `policy` is how
    the release's policy layer was read."""
    from ..swarm import gate
    from ..swarm import settings as swarm_settings
    from ..swarm.researcher import drift_settings

    effective = swarm_settings.load(root, config=config)
    drift_share, min_power = gate.look_hold_settings(effective)
    live, policy = effective.get("live"), effective.get("_policy")
    own = _at(read_json(Path(root) / "swarm.json", None), "live", "incubator")
    return {"gate.look_holds": {"drift_share": drift_share, "min_power": min_power},
            "tournament.drift_screen": drift_settings(effective) is not None,
            "live.incubator": isinstance(live, Mapping) and live.get("incubator") is True and own is True,
            "policy": policy.get("state") if isinstance(policy, Mapping) else None}


def budget_in_force(root: str | Path, now: float) -> dict[str, Any]:
    """THE BUDGET IN FORCE: the research dollars a day by meter and where they come from (`budget.effective`:
    `<state>/budget.json` when it is there and usable, a stale one never above the floor, else the floor)."""
    from . import budget

    block = budget.effective(root, now)
    return {key: block.get(key) for key in ("source", "why", "at", "state", "sail_usd_day", "claude_usd_day",
                                            "fixed_sail_usd_day")}


def funnel(root: str | Path, now: float, *, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """THE FUNNEL's record at `now` (the module docstring; what `<state>/ops/funnel.json` holds). Never raises: a part
    that cannot be read is None (the page's "n/a"), `errors` says why by part, and `seconds` how long each took."""
    root, now, began = Path(root), float(now), time.monotonic()
    errors: dict[str, str] = {}
    seconds: dict[str, float] = {}

    def part(name: str, read: Callable[[], Any]) -> Any:
        start = time.monotonic()
        try:
            return read()
        except Exception as exc:  # noqa: BLE001 - one line that cannot be read is n/a; the rest of the page stands
            errors[name] = f"{type(exc).__name__}: {str(exc)[:200]}"
            return None
        finally:
            seconds[name] = round(time.monotonic() - start, 4)

    since = windows(now)
    got: dict[str, Any] = {name: None for name, _ in STORE_PARTS}
    store = part("store", lambda: _Store(root / "swarm.sqlite", now))
    if store is not None:
        try:
            for name, read in STORE_PARTS:
                got[name] = part(name, lambda read=read: read(store, since))
        finally:
            part("close", store.close)

    def absent(name: str) -> bool:  # a table an older store lacks holds no row: no family came to the gate through it
        return "no such table" in errors.get(name, "")

    # A program's first step at the gate, across the gate's events and its tables; and its first instant at the line: its
    # first passing verdict, or that first step (a verdict that landed after its round stopped waiting is in no round's
    # event, and the gate takes up only a version that met the line).
    tables = ("refusals", "holds", "looks")
    took = None
    if got["gate"] is not None and all(got[name] is not None or absent(name) for name in tables):
        took = _earliest(got["gate"], *(got[name]["first"] for name in tables if got[name] is not None))
    arrived = None if took is None else _arrived(took, since)
    met = None if got["line"] is None or took is None else _arrived(_earliest(got["line"], took), since)

    out: dict[str, Any] = {}
    for key, (iso, _) in since.items():
        looks = got["looks"][key] if got["looks"] is not None else None
        moves = got["band_moves"][key] if got["band_moves"] is not None else None
        tests = got["tests"][key] if got["tests"] is not None else None
        usd = got["usd"][key] if got["usd"] is not None else None
        born = got["born"][key] if got["born"] is not None else None
        booked = usd["booked"] if usd is not None else None

        def per(count: Any) -> float | None:
            return None if booked is None or not count else round(booked / count, 4)

        out[key] = {
            "since": iso, "born": born,
            "train_eligible": got["eligible"][key] if got["eligible"] is not None else None,
            "tested": None if tests is None else {k: tests[k] for k in ("families", "versions", "runs")},
            "passes": got["passes"][key] if got["passes"] is not None else None,
            "pre_validation": got["pre_validation"][key] if got["pre_validation"] is not None else None,
            "set_aside": got["set_aside"][key] if got["set_aside"] is not None else None,
            "inherited": None if tests is None else tests["inherited"],
            "met_line": None if met is None else met[key],
            "gate": {"arrived": None if arrived is None else arrived[key],
                     "refused": got["refusals"][key]["stages"] if got["refusals"] is not None else None,
                     "held": got["holds"][key]["stages"] if got["holds"] is not None else None,
                     "waited": got["waits"][key] if got["waits"] is not None else None,
                     "looked": looks["made"] if looks is not None else None,
                     "passed": looks["passed"] if looks is not None else None},
            "bands": None if moves is None else moves["entered"],
            "demoted": None if moves is None else moves["demoted"],
            "usd": None if usd is None else {**usd, "per_birth": per(born), "per_test": per(tests and tests["runs"]),
                                             "per_gate_arrival": per(arrived and arrived[key]),
                                             "per_look": per(looks and looks["made"])},
            "chance": tests["chance"] if tests is not None else None}

    on = part("switches", lambda: switches(root, config))

    def bar() -> dict[str, Any]:
        from ..swarm import gate

        if got["looks"] is None or got["in_flight"] is None:
            raise RuntimeError("the looks could not be read")
        return look_bar(got["looks"]["all"], in_flight=flying(got["in_flight"], root, now, config),
                        sessions=gate.holdout_sessions(),
                        min_power=None if on is None else on["gate.look_holds"]["min_power"])

    look = part("look", bar)
    if look is not None and on is None:
        look.update(sharpe_daily_for_hold=None, sharpe_yearly_for_hold=None)  # the hold's line was not read: not said
    record = {"schema": FUNNEL_SCHEMA, "at": S.iso(now), "basis": FS, "windows": out, "bands_now": got["bands_now"],
              "waiting_now": got["waiting"], "unit_waiting_now": got["unit_waiting"], "look": look, "switches": on,
              "sealed_looks": sealed_looks(),
              "budget": part("budget", lambda: budget_in_force(root, now)), "errors": errors, "seconds": seconds}
    seconds["total"] = round(time.monotonic() - began, 4)
    return record


def funnel_record(ctx: Any, now: float) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """(THE FUNNEL's record, its line of the job's receipt): the record is written to `<state>/ops/funnel.json` (private,
    whether or not the page is posted). The funnel never stops the page: with no record its lines are "n/a". Whatever
    was not read, or a record that could not be written, is one House warning naming the parts (never why: the reasons
    are the private record's), so a funnel that goes quiet is never only an "n/a" nobody reads."""
    try:
        record = funnel(ctx.root, now, config=ctx.config)
    except Exception as exc:  # noqa: BLE001 - `funnel` answers for its own parts; anything else is a page without it
        ctx.alert("warning", "scoreboard: the funnel could not be read: its lines say n/a on today's page")
        return None, {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    receipt: dict[str, Any] = {"seconds": record["seconds"].get("total"), "not_read": sorted(record["errors"])}
    try:
        receipt["file"] = str(write_json(ctx.root / FUNNEL_FILE, record))
    except OSError as exc:
        receipt["file_error"] = type(exc).__name__
    if receipt["not_read"]:
        ctx.alert("warning", f"scoreboard: the funnel could not read {', '.join(receipt['not_read'])}: those lines say "
                             "n/a on today's page")
    if "file_error" in receipt:
        ctx.alert("warning", "scoreboard: the funnel's private record could not be written")
    return record, receipt


def meter_in_force(meter: str, usd: Any, source: Any) -> str:
    """THE BUDGET IN WORDS for one meter of the budget in force: "at the floor" (no usable budget.json), "at most the
    floor" (a stale one), and from budget.json "at the ceiling" (its whole share of the owner's ceiling), "tapering"
    (under it: the runway rule) or "none". "n/a" for a figure or a source that was not read. Never the dollars."""
    from . import budget

    if isinstance(usd, bool) or not isinstance(usd, (int, float)) or not math.isfinite(usd) \
            or not isinstance(source, str) or source not in BUDGET_SOURCES:
        return "n/a"
    if usd <= 0:
        return "none"
    if source != budget.BUDGET_FILE:
        return "at the floor" if source == "floor" else "at most the floor"
    try:
        ceiling = budget.ceiling_usd_day(meter)
    except Exception:  # noqa: BLE001 - no share to compare with: not said
        return "n/a"
    return "at the ceiling" if usd >= ceiling - budget.EPSILON else "tapering"


def budget_in_force_line(block: Any) -> str:
    """THE BUDGET IN FORCE in one line: each meter's research in words (`meter_in_force`) and the source, in the page's
    words. The dollars a day are the private record's (THE BUDGET IN WORDS)."""
    source = _at(block, "source")
    source = source if isinstance(source, str) else None
    said = ", ".join(f"{meter} {meter_in_force(meter, _at(block, f'{meter}_usd_day'), source)}" for meter in ("sail", "claude"))
    return f"In force now, research by meter: {said} (source: {BUDGET_SOURCES.get(str(source), 'n/a')})."


def _by_reason(funnel: Mapping[str, Any] | None, which: str) -> str:
    """The gate's refusals or holds by reason, each window in turn, in the page's own words for a stage."""
    said = []
    for key, words, _ in WINDOWS:
        stages = _at(funnel, "windows", key, "gate", which)
        if not isinstance(stages, Mapping):
            said.append(f"{words.lower()}: n/a")
            continue
        counts: dict[str, int] = {}
        for stage, n in stages.items():
            word = STAGE_WORDS.get(str(stage), "another reason")
            counts[word] = counts.get(word, 0) + (n if _whole(n) else 0)
        said.append(f"{words.lower()}: " + (", ".join(f"{word} {n}" for word, n in sorted(counts.items())) or "none"))
    return "; ".join(said)


def funnel_lines(funnel: Mapping[str, Any] | None) -> list[str]:
    """The funnel's section of the page, from the record's figures alone (never a family, a stage's own name or a
    reason's text): the stages, the cost, the chance baseline (a window's figures only over `CHANCE_MIN_PUBLIC`
    programs: the module docstring's PUBLIC), the bar at the next look and the switches in force."""
    def row(label: str, *path: str, fmt: str = "{}", total: bool = False, chance: bool = False) -> str:
        cells = []
        for key, _, _ in WINDOWS:
            value = _at(funnel, "windows", key, *path)
            if total and isinstance(value, Mapping):
                value = sum(n for n in value.values() if _whole(n))
            tested = _at(funnel, "windows", key, "chance", "versions")
            if chance and not (_whole(tested) and tested >= CHANCE_MIN_PUBLIC):
                value = None  # too few programs tested in this window for its chance figures to be public
            cells.append(_na(value, fmt))
        return f"| {label} | " + " | ".join(cells) + " |"

    head = " | ".join(words for _, words, _ in WINDOWS)
    rule = "|---|" + "---:|" * len(WINDOWS)
    now = [f"{_na(_at(funnel, 'bands_now', band))} {band.capitalize()}" for band in FUNNEL_BANDS]
    look, holds = _at(funnel, "look"), _at(funnel, "switches", "gate.look_holds")
    made, flying = _at(look, "made"), _at(look, "in_flight")
    number = made + flying + 1 if _whole(made) and _whole(flying) else None
    if not isinstance(holds, Mapping):
        held = "n/a"
    else:
        held = ", ".join(f"{words} {_na(holds.get(key), '{:.2f}') if holds.get(key) is not None else 'off'}"
                         for key, words in (("drift_share", "drift share"), ("min_power", "least power")))

    def switch(name: str) -> str:
        value = _at(funnel, "switches", name)
        return "on" if value is True else "off" if value is False else "n/a"

    if isinstance(look, Mapping) and look.get("min_power") is None and isinstance(holds, Mapping):
        power = "The power hold is off."
    else:
        power = ("To clear the power hold at the next look, a program needs a yearly Sharpe of at least "
                 f"{_na(_at(look, 'sharpe_yearly_for_hold'), '{:.2f}')} on the unseen-year test; one under it waits "
                 "at the gate, with no look spent, and is looked at once that bar allows.")
    waiting, sized = _at(funnel, "waiting_now"), _at(funnel, "unit_waiting_now")
    return [
        f"What research did since the record's basis ({FS}) and in the last 24 hours, in counts. Each line counts what "
        "happened inside its window: a family born last week and tested today is in today's tests, not in today's "
        "births. A family is one line of research and a program is one version of it. A family is counted at the "
        "unseen-year line and at the gate in the window where one of its programs first got there: a later step on "
        "the same program is no second arrival. The unseen-year test is a program's run on a year held back from "
        "research, of which research hears only whether the line was met and how many of its checks passed; the "
        "unseen-market test is the gate's one look at the newest market, held back from every test before it.", "",
        f"| Stage | {head} |", rule,
        row("Birth passes that asked a model", "passes", "paid"),
        row("Birth passes skipped: no cell could bear a birth", "passes", "skipped", "no_cell"),
        row("Birth passes skipped: the hour's births were spent", "passes", "skipped", "paced"),
        row("Birth passes skipped: the population was at its ceiling", "passes", "skipped", "ceiling"),
        row("Families born", "born"),
        row("Families with an eligible Train version", "train_eligible"),
        row("Programs set aside before the unseen-year test", "set_aside"),
        row("Families that ran the unseen-year test", "tested", "families"),
        row("Programs that ran the unseen-year test", "tested", "versions"),
        row("Unseen-year tests run", "tested", "runs"),
        row("Verdicts read from an identical program's test (no run)", "inherited"),
        row("Families that met the unseen-year line", "met_line"),
        row("Families that reached the gate", "gate", "arrived"),
        row("Programs refused at the gate", "gate", "refused", total=True),
        row("Programs held at the gate", "gate", "held", total=True),
        row("Programs that began to wait at the gate", "gate", "waited"),
        row("Programs looked at (the unseen-market test)", "gate", "looked"),
        row("Programs that passed it", "gate", "passed"),
        row("Families that moved up to Candidate", "bands", "candidate"),
        row("Families that moved up to Probe", "bands", "probe"),
        row("Families that moved up to Sized", "bands", "sized"),
        row("Families that moved down a band", "demoted"), "",
        f"Refused at the gate, by reason: {_by_reason(funnel, 'refused')}.",
        f"Held at the gate, by reason: {_by_reason(funnel, 'held')}.",
        "A hold closes a program's place at the gate for good. A wait closes nothing and refuses nothing: a program "
        "the power hold stops keeps its place, is judged again every round, and gets its one look when the bar at the "
        f"next look allows. Waiting at the gate now: {_na(waiting if _whole(waiting) else None)}.",
        "A skipped birth pass asked no model and cost nothing. A program is set aside before the unseen-year test when "
        "its own Train run shows what would stop it later: the gate would hold its look for market drift, or one "
        "contract of it risks more than a first real-money position may. That is no finding against the program, and "
        "it comes back when the limit moves. A family whose program met the unseen-year line with such a unit on that "
        "year waits before the gate, with no review and no look spent, and is neither held nor refused. Waiting "
        f"before the gate for its unit now: {_na(sized if _whole(sized) else None)}.",
        f"In each band now: {', '.join(now)}.", "",
        "### What research cost", "",
        f"| Research cost | {head} |", rule,
        row("USD booked", "usd", "booked", fmt="{:.2f}"),
        row("USD per family born", "usd", "per_birth", fmt="{:.2f}"),
        row("USD per unseen-year test", "usd", "per_test", fmt="{:.2f}"),
        row("USD per family that reached the gate", "usd", "per_gate_arrival", fmt="{:.2f}"),
        row("USD per look", "usd", "per_look", fmt="{:.2f}"), "",
        "### Luck against edge", "",
        "The unseen-year line asks, among its checks, for a daily t of at least "
        f"{_na(_at(funnel, 'windows', WINDOWS[0][0], 'chance', 't'), '{:g}')}. With no edge at all some programs clear "
        "that check by luck, so a count near luck's is no sign of an edge. A window with fewer than "
        f"{CHANCE_MIN_PUBLIC} programs tested shows no figure under its count: that is too few to tell luck from an "
        "edge, and research is never told which check a program met.", "",
        f"| The t check | {head} |", rule,
        row("Programs tested with a t", "chance", "versions"),
        row("Cleared the t check", "chance", "cleared", chance=True),
        row("Luck alone would clear", "chance", "by_luck", fmt="{:.1f}", chance=True),
        row("Luck's spread (one standard deviation, were the tests independent)", "chance", "by_luck_sd", fmt="{:.1f}",
            chance=True),
        row("Distinct results tested", "chance", "distinct", "results", chance=True),
        row("Distinct results that cleared", "chance", "distinct", "cleared", chance=True),
        row("Luck alone, over distinct results", "chance", "distinct", "by_luck", fmt="{:.1f}", chance=True), "",
        "### The bar at the next look", "",
        f"Looks made: {_na(made)}; passed: {_na(_at(look, 'passed'))}; in flight: {_na(flying)}. "
        f"The next look (number {_na(number)}) is tested at the {_na(_at(look, 'next_level'), '{:.4f}')} level (a "
        f"program with no edge passes at most that often): {_na(_at(look, 'alpha'), '{:g}')} shared across every look "
        "made or in flight and this one, so each look that fails lowers it for good. The looks made so far were tested "
        f"at levels that sum to at most {_na(_at(look, 'level_spent'), '{:.4f}')}, which bounds the chance that luck "
        f"alone passed any of them. {power} An even chance of passing the look itself takes a yearly Sharpe of "
        f"{_na(_at(look, 'sharpe_yearly_even_chance'), '{:.2f}')} on the unseen market.", "",
        f"The owner's switches in force: look holds: {held}; drift screen: {switch('tournament.drift_screen')}; "
        f"incubator: {switch('live.incubator')}."]


def build(*, day: str, release: str, economics: Mapping[str, Any] | None, deploys: Mapping[str, Any],
          budget: Mapping[str, Any] | None, ladder: Mapping[str, Any], jobs: Mapping[str, int], written_at: str,
          funnel: Mapping[str, Any] | None = None) -> str:
    """The page, from an allowlist of figures. `funnel` is THE FUNNEL's record (`funnel`); without one, or for any part
    of it that was not read, its lines say "n/a" and the rest of the page is as it would be."""
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
        complete = economics.get("cost_accounting_complete") is True
        cost_label = "Input costs since T0" if complete else "Known input costs since T0 (incomplete)"
        net_label = "Net (realized - costs)" if complete else "Net on priced inputs (incomplete)"
        if not complete:
            lines += ["Cost accounting is incomplete: estimates or unpriced charges remain. Unpriced costs and a Net "
                      "that depends on them are n/a; a numeric Net uses priced inputs only.", ""]
        lines += ["## Money", "", f"Cutoff: {economics.get('cutoff')}.", "", "| Measure | USD |", "|---|---:|",
                  f"| Realized options P&L since T0 (all routes, fees in) | {_cell(realized.get('realized_options_pnl_usd'))} |",
                  f"| Realized options P&L, trailing 30 days | {_cell(p30.get('usd'))} |",
                  f"| {cost_label} | {_cell(economics.get('known_input_cost_subtotal_usd', economics.get('total_costs_usd')))} |",
                  f"| **{net_label}** | **{_cell(net.get('net_usd'))}** |",
                  f"| Open lots ({n_open}) at conservative marks, unrealized | {_cell(opens.get('unrealized_conservative_usd'))} |",
                  f"| Net with open lots at conservative marks | {_cell(net.get('net_with_open_at_conservative_marks_usd'))} |", "",
                  f"Real closes since T0: {n_closed}" + (f" ({p30.get('closed_positions')} in the trailing 30 days)." if p30 else "."), "",
                  "### Input costs by service since T0", "", "| Service | USD |", "|---|---:|"]
        lines += [f"| {c.get('service')} | {_cell(c.get('usd'))} |" for c in economics.get("costs") or []]
        lines.append("")
    lines += ["## Budget", "", *budget_lines(budget), "", budget_in_force_line(_at(funnel, "budget")), "",
              "## Releases", "",
              f"Self-deployed releases since T0: {deploys.get('self_promoted', 0)} ({deploys.get('self_promoted_today', 0)} today); "
              f"self-rollbacks: {deploys.get('self_rolled_back', 0)} ({deploys.get('self_rolled_back_today', 0)} today). "
              f"Owner deploys: {deploys.get('owner_promoted', 0)} promoted, {deploys.get('owner_rolled_back', 0)} rolled back. "
              f"Rollback drills: {deploys.get('drill_rolled_back', 0)} rolled back as intended, "
              f"{deploys.get('drill_promoted', 0)} not caught.", "",
              "## The research funnel", "", *funnel_lines(funnel), "",
              "## The forward ladder", "",
              *ladder_lines(ladder, sealed=_at(funnel, "sealed_looks"), incubator=_at(funnel, "switches", "live.incubator")), "",
              "## The House's jobs today", "",
              f"Ran: {jobs.get('ok', 0)}; failed: {jobs.get('failed', 0)}; missed: {jobs.get('missed', 0)}; skipped: {jobs.get('skipped', 0)}.", ""]
    return "\n".join(lines)


def run(ctx: Any) -> dict[str, Any]:
    from .economics import latest

    now = ctx.now()
    day = S.iso(ctx.due_at)[:10]
    record, receipt = funnel_record(ctx, now)
    text = build(day=day, release=Path(ctx.release).name, economics=latest(ctx.root), deploys=deploy_counts(ctx.base, day=day),
                 budget=read_json(ctx.root / "budget.json", None), ladder=ladder_counts(ctx.root, now),
                 jobs=job_counts(ctx.root, day), written_at=S.iso(now)[11:16] + "Z", funnel=record)
    problems = public_problems(text)
    local = write_text(ctx.root / "scoreboard" / f"{day}.md", text)
    if problems:
        raise ValueError("the page failed the public filter, not posted: " + ", ".join(problems))
    path = PATH.format(day=day)
    try:
        answer = ctx.gateway.post(DOCS_ROUTE, {"path": path, "content": text, "message": f"desk: scoreboard {day}"})
    except GatewayError as exc:
        if exc.status in (404, 405):
            return {"status": "skipped", "why": "the gateway's docs route is not deployed", "local": str(local), "bytes": len(text),
                    "funnel": receipt}
        raise
    return {"posted": path, "local": str(local), "bytes": len(text),
            "commit": (answer or {}).get("commit") if isinstance(answer, dict) else None, "funnel": receipt}
