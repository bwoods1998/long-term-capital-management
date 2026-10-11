"""THE EQUITY LANES' HEALTH (release E2.4, Oct 11, 2026): the equity lanes' own stall causes, raised through the `stall`
job's machinery (league/ops/stall.py), and their research funnel (league/ops/funnel.py).

WHY. On Oct 11, 2026, in the equity lanes' first three hours (release E2), most scored versions were disqualified by one
misreading of the program contract, families were retired for it, the lanes stood still at their pace, one births pass
was cut short and another bore nothing because every proposal named symbols outside the universe. No alarm fired: the
stall job watched the options lanes, and of the equity lanes it knew only Validation runs and families awaiting a try.
The captain found each fault by hand, with read-only scripts. This module is those reads, made by the House at every
run of the stall job.

THE CAUSES (`CAUSES`; `checks`). Each has `what`, `numbers`, `doing` (what the floor does about it by itself) and
`owner_step` (the command or the decision, or none), like every cause of the stall job:
- `elane_dq`: of the equity versions scored in the last `DQ_HOURS`, more than `DQ_SHARE` could not be judged for a fault
  of their own program: disqualified by their errors or timeouts (DQ), refused by the decider child at load (LOAD) or
  failed by it again and again (RUN), in at least `DQ_MIN_FAMILIES` families (one family's bad programs are no fault
  of the contract: the check then reads clear and names the family). A fault of the generators against the contract or
  the sandbox, never a verdict on a mechanism. When fewer than `DQ_MIN_SCORED` versions fall in those hours it judges
  the last `DQ_MIN_SCORED` scored since the running release started, and it stands EARLY, before the sixth version,
  once `DQ_EARLY_FAULTED` versions of two families could not be judged (4 scored and none judged by the bar; 4 of 5):
  they are most of six whatever the versions still to come are. ONCE IT STOOD UNDER A RELEASE IT HOLDS (the stall
  job keeps when, `stall.json` `elane.dq`) until versions scored after it stood are judged by the bar in
  `DQ_MIN_FAMILIES` families, or the release changes: a window that slides past a fault nothing fixed, or one
  family's bar fails beside the retired families' versions, clears nothing. It names the first error's class (a
  closed class: `dq_class`) only when one class is more than half of the disqualifications, else the classes that
  tie; and, for a class it names, the reading rule's commonest sentence for it in the same hours (`SENTENCES`) or,
  with none on record, what that class most often is (`DQ_SHORT`: one fixed short sentence a class, rules only). The
  owner's step: the text the generators read needs a fix, in a release.
- `elane_births`: the last `BIRTHS_PASSES` equity passes that asked a model bore no family (every proposal refused, none
  proposed, the answer cut short, no route answered, the pass raised). It names the commonest refusals in the House's
  own closed words (`REFUSALS`; the refusal's text carries what the model wrote and never reaches a notice) and the
  symbols of the code's universe that `elane.universe` does not hold. The owner's step only once no equity family was
  born for `BIRTHS_OWNER_HOURS` and a setting clears the main way they bore nothing (`BIRTH_LEVERS`); at once when
  every route refused the request before it was sent for a setting (the pass's event names it, `SETTINGS`): asking
  again changes nothing until the setting does.
- `elane_idle`: A BROKEN LANE, AND ONLY THAT. Work is owed (families in Train research, or births wanted) and no
  version was scored for `IDLE_HOURS` (the idle clock, below). BROKEN IS JUDGED FIRST: the lane's own record since
  it went idle shows `BROKEN_MIN_FAILS` rounds that raised, Train steps that failed on the House's side (or a family
  waiting out a House backoff after that many failures) or steps that failed with an error of their own. It stands
  with that kind's owner step WHATEVER E2's lines hold, and a second sentence says the line when E2 is also held (a
  lane whose every Train run fails scores nothing at any pace). Else it stands only when THE LANE MAY ASK A MODEL
  AND STILL SCORES NOTHING: no hold of E2's was seen in the last `IDLE_HOURS` (not now, not at an earlier run of
  the job, which keeps its last reading in `stall.json` `elane.held`, and no Train step or equity pass skipped for
  want of model dollars): questions no route answered and programs refused before a run (nobody's step: they heal
  or are `elane_refused`'s), barren passes with no family left (`elane_births`'), rounds that run and judge
  nothing or no round at all (the owner's step).
  STARVATION BY SETTINGS IS NO STANDING CAUSE. A lane held by its own hourly pace, its day's dollars or the House's
  Sail day (`elane_yield.hold`) is the budget the captain chose, at work: the cause reads JUDGED CLEAR, never
  stands and never mails, and its sentence and numbers say what the setting cost (the Train steps due in the last
  `IDLE_HOURS`, taken and skipped by reason, whether E2 is held now and by which line, `_lever`). The same counts
  are in the research funnel (`train_steps`, the passes' `skipped`). THE COST: a lane starved by a setting is read
  in the funnel and the receipt, not in the mail.
  THE IDLE CLOCK is kept per release (`stall.json` `elane.idle`: {from, down, started, beat_at}): from the later of
  the last version scored and when the work became owed (a family born after a quiet spell is not idle on a score
  of days ago), LESS THE TIME THE SWARM WAS DOWN (at a restart, from the heartbeat the last run read to the new
  start; before anything was kept, everything before the running swarm's own start). A restart resets nothing: a
  broken lane restarted every two hours is still judged idle.
- `elane_refused`: of the programs the generators wrote in the last `REFUSED_HOURS`, more than `REFUSED_SHARE` were
  refused before a run by ONE static rule (the reading, level or memory rule, the code rules, NEEDS; any
  "equity <name> rule" a later release adds is read the same way): the generators are not being taught that rule. It
  names the rule and its commonest sentence in closed words. As `elane_dq`: when fewer than `REFUSED_MIN_ANSWERS`
  fall in those hours it judges the last `REFUSED_MIN_ANSWERS` written since the running release started (a slow
  lane's fault does not read "not judged" as the window slides), and it stands EARLY once `REFUSED_EARLY` were
  refused by one rule (most of eight whatever is still to be written). The owner's step: teach it where they read
  it, in a release.

WHEN A CAUSE IS JUDGED (`lanes`). Only while the lanes are on (`elane.mode` "gate" and `elane.birth_share` above zero,
as the swarm loads its settings), release E2's rounds are in the running tree, the floor is not paused (a maintenance
pause or a stopped swarm stops the lanes by design), E2's own dollars are not set to zero (`elane.e2.usd_day` or
`elane.e2.pace_share` at 0: the lanes paused by setting), the store holds an equity family or an equity pass at all,
and the owner has not switched the four off (`<state>/ops.json` `stall.elane` false: `switched_off`). Else every cause
reads "Not judged" and says why. Lanes that cannot be read (the settings, E2's own readers, the store, the lane's
own reading of whether it may ask a model) are "Not judged" AND an entry of the job's `errors` naming the class AND
one House warning every `BLIND_WARN_SECONDS` while it lasts (`_blind`: the receipt's errors alone reach no one): an
alarm that cannot see says so. And only on enough evidence,
counted SINCE THE RUNNING RELEASE FIRST STARTED (`release_since`: the stall job keeps {release, since} in
`stall.json`, the heartbeat's `release` and the `started_at` it first saw under it): a release that fixes a fault is
a new release, so what the generators did under the earlier one is not held against this one; a restart of the same
release (the watchdog's, a settings apply) fixes nothing and resets nothing. A cause with too little evidence says how
much it has and how much it needs. WHAT THE JOB KEEPS UNDER A RELEASE (`KEPT`, beside {release, since}, dropped when
the release changes): the idle clock, the last hold of E2's a run read, when `elane_dq` first stood, when the
unreadable lanes were last warned. `checks` reads them and leaves in the same record what the next run needs; it
writes no file itself. A lane is not judged idle while the swarm itself is not running (its heartbeat
`BEAT_STALE_SECONDS` old): that is the options lanes' causes to tell.

WHAT IT READS. The swarm's store, read-only, in one read transaction (`facts`): the equity families the equity pass
bore and E2's own Train record of each (state `elane_e2`: versions with their fails and what a disqualification said,
the programs refused before a run), the `swarm.elane` events (the equity passes and the Train rounds' steps), the
rounds that raised (`swarm.status`), E2's kv clocks, E2's own model spend, and the lane's own reading of whether it may
ask a model now (`elane_yield.hold` over a read-only reader); the swarm's heartbeat; the swarm's settings as it loads
them. NO RECURSION INTO JUDGES: no program is read, parsed or run here, no rule is applied again, and nothing is
written: a rule's sentence comes from the record that already holds it.

AN ALARM NEVER LOOSENS A JUDGE. Nothing here changes a screen, a bar, a budget, a seat, a money rule, the graveyard or a
refusal rule. It reads, reports and notifies.

THE NOTICE (`mailed`). The gateway words the four (gateway/lib/email.mjs `STALL_CAUSES`, held equal to `stall.CAUSES`
by its own test; the gateway is deployed before this release: an unknown cause makes a whole notice a 400), so each
stands under its own name everywhere (the receipt's `checks`, `stall.json`, the House's warnings, the daily page's
standing causes, the Done meter's item 7) and is AN ENTRY OF ITS OWN in the mail, keyed by its own name: an equity
owner step is mailed at once whatever the swarm's own alerts told, and theirs whatever these told. `mailed` only fits
an entry to what the gateway prints: its sentence whole inside the gateway's cut (the leading sentences that fit),
the mail's figures first, and nothing that is no figure (the examples and the hint stay on the House). `warning`
fits a House warning the same way: an owner step is whole inside the alert's cut (`WARN_CHARS`), and what is
shortened is the sentences before it.

THE RESEARCH FUNNEL (`research_counts`; the funnel's `equity.research`, which the `scoreboard` job's receipt carries
for the day and the release, and `python3 -m league.ops.elane_health`): equity passes (asked, barren, cut short,
skipped by reason) and families born, proposals refused by reason class, programs refused before a run by rule,
the Train rounds' steps taken and skipped by reason (`train_steps`: pace, usd_day, sail_day, other: the work the
lanes' dollars did not reach), versions scored, disqualified and failed by code (Y1, Y2, P1, R1, STATE and any other
the bar names), bar passes, review refusals and passes, families retired (stalled, refuted) and E2's model dollars by
purpose. Counts and E2's own dollars only.

THE REPORT (`report`, `text`; `python3 -m league.ops.elane_health --state DIR [--hours N] [--json]`), read-only, for an
operator on the box: the four checks, the funnel, and each family's versions (the fail codes, a disqualification's
class and line) and refusals (the rule and its sentence in closed words).

Standard library only at import; the swarm's own readers (`elane`, `elane_births`, `elane_yield`, the architect and
the loop for whether E2's rounds are there; `elane_train` for the contract's sentence of an error class; the code's
universe) are imported inside the functions that need them, and a failure there is "Not judged" with its error and an
entry of the job's `errors`, never a failed run.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import guard
from . import schedule as S
from .context import read_json
from .context import settings as ops_settings

CAUSES = ("elane_dq", "elane_births", "elane_idle", "elane_refused")
#: The stall job's key in `<state>/ops.json` that switches these four off (`switched_off`): `{"stall": {"elane": false}}`.
SWITCH = "elane"
SWARM_DB = "swarm.sqlite"
HEARTBEAT = "swarm.heartbeat"
#: The stall job's own state file (`stall.STATE_FILE`; a test holds the two equal) and its key that keeps since when the
#: running release has run (`release_since`), and under it WHAT IS KEPT WHILE THAT RELEASE RUNS (`KEPT`): `idle` (the
#: idle clock: `_idle_clock`), `held` (the last run that read E2 held: {at, kind}), `dq` (when `elane_dq` first stood:
#: {stood_at}) and `unread` (when the lanes that cannot be read were last warned: {warned_at}).
STATE_FILE = "stall.json"
STATE_KEEP = "elane"
KEPT = ("idle", "held", "dq", "unread")

# ---------------------------------------------------------------------------------------------- the thresholds
#: `elane_dq`: the window, the scored versions under which nothing is judged, and the share above which it stands. Six
#: hours is the Gym-runs window of the options lanes (`stall.GYM_HOURS`): long enough for several Train rounds of
#: several families, short enough that a fault is told within a morning. Six versions is two families at least (a
#: family has four scored versions, `elane.e2.train_budget`), and the faulted versions must come from
#: `DQ_MIN_FAMILIES` of them: one family's bad programs are no fault of the contract. "Most" is more than half.
DQ_HOURS = 6.0
DQ_MIN_SCORED = 6
DQ_SHARE = 0.5
DQ_MIN_FAMILIES = 2
#: `elane_dq` stands EARLY, before the sixth version, once this many could not be judged, in `DQ_MIN_FAMILIES` families:
#: more than `DQ_SHARE` of `DQ_MIN_SCORED` (four of six), so whatever the versions still to come are, they are most of
#: six. At a slow pace six versions are hours away, and a lane whose first four judge nothing is told at the fourth.
DQ_EARLY_FAULTED = int(DQ_SHARE * DQ_MIN_SCORED) + 1
#: `elane_births`: the equity passes read this far back (a pass comes every 30 minutes while the lanes refill and every
#: 2 hours after: twelve hours hold several either way), and how many of the latest that asked a model must have borne
#: nothing. Three, as the options lanes' dry window (`stall.DRY_PASSES`): one barren pass is a model's bad answer, three
#: in a row is the request.
BIRTHS_HOURS = 12.0
BIRTHS_PASSES = 3
#: `elane_births` is the owner's step once no equity family was born this long (the options jam's hours,
#: `stall.JAM_HOURS`): each pass shows its next request the last one's refusals, so the lanes get that long to correct
#: themselves before anyone is asked.
BIRTHS_OWNER_HOURS = 6.0
#: `elane_idle`: no version scored on Train this long while work is owed. The Train round comes every ten minutes and
#: scores a version in the step that wrote it, so three hours is eighteen rounds with nothing judged. The same hours
#: are how long no hold of E2's must have been seen for a lane to be one that MAY ASK A MODEL and still scores nothing.
IDLE_HOURS = 3.0
#: `elane_idle`, BROKEN BY ITS OWN RECORD: this many rounds that raised, steps that failed on the House's side or steps
#: that failed with an error of their own since the lanes went idle stand whatever E2's lines hold. Two: one failure
#: before a hold (a store being rewritten for a minute, then the day's dollars spent) is no broken lane, and a failure
#: of the House's is tried again without a model, so a standing one is two within the half hour.
BROKEN_MIN_FAILS = 2
#: Why a Train step or an equity pass is skipped for want of model dollars (`skip_kind`): E2's hourly pace, its day's
#: line, the House's Sail day: THE SETTINGS' HOLDS, which never stand. Any other skip (a passing version that cannot
#: be read) is none of them.
STARVED_KINDS = ("pace", "usd_day", "sail_day")
STARVED_WORDS = {"pace": "its hourly pace", "usd_day": "its day's line", "sail_day": "the House's Sail day"}
#: A swarm whose heartbeat is this old is not running, and its lanes are not judged idle: the House's hook restarts a
#: swarm whose heartbeat is 240 seconds old (league/swarm/hook.py `stale_heartbeat_seconds`), and a swarm that stays
#: down is the options lanes' causes to tell (`gym_runs` says the heartbeat's age).
BEAT_STALE_SECONDS = 600.0
#: `elane_refused`: the window (as `DQ_HOURS`), the programs written under which nothing is judged (two families' worth
#: of write attempts answered, as `DQ_MIN_SCORED` reasons), and the share one rule must pass ("most": more than half).
REFUSED_HOURS = 6.0
REFUSED_MIN_ANSWERS = 8
REFUSED_SHARE = 0.5
#: `elane_refused` stands EARLY, before the eighth program, once this many were refused by one rule: more than
#: `REFUSED_SHARE` of `REFUSED_MIN_ANSWERS` (five of eight), so they are most of eight whatever is still to be written.
REFUSED_EARLY = int(REFUSED_SHARE * REFUSED_MIN_ANSWERS) + 1
#: LANES THAT CANNOT BE READ are one House warning this often while it lasts (`_blind`; the stall job's own pace of a
#: standing cause's warning, `stall.WARN_EVERY_SECONDS`).
BLIND_WARN_SECONDS = 12 * 3600.0
#: How far back `facts` reads the events (the longest window above).
LOOKBACK_HOURS = max(DQ_HOURS, BIRTHS_HOURS, REFUSED_HOURS, IDLE_HOURS)
#: The report's funnel covers this many hours unless it is asked another (`report`, the command's `--hours`).
FUNNEL_HOURS = 24.0

# ---------------------------------------------------------------------------------------------- E2's vocabulary
#: Spelled here so the module imports nothing of the swarm (league/tests/test_elane_health.py holds each to its source):
#: the equity lanes (`league.equity.LANES`), E2's family-state key and the spec's birth route
#: (`elane_train.STATE_KEY`, `elane_yield.ROUTE_KEY`), E2's kv clocks (`elane_births.BIRTHS_AT_KEY`,
#: `elane_train.TRAIN_AT_KEY`, `TRAIN_OK_KEY`), how a spend row of E2's is told and under which kinds
#: (`elane_yield.SPEND_MARK`, `SPEND_KINDS`), and how E2's reasons for asking no model begin (`elane_yield.DAY_SPENT`,
#: `SAIL_DAY`; its pace's reason is the third).
LANES = ("beta", "equity")
STATE_KEY = "elane_e2"
ROUTE_KEY = "e2_route"
BIRTHS_AT_KEY, TRAIN_AT_KEY, TRAIN_OK_KEY = "elane_e2_births_at", "elane_e2_train_at", "elane_e2_train_ok_at"
SPEND_MARK = ':"swarm:elane:'
SPEND_KINDS = ("sail_model", "openai", "claude")
DAY_SPENT = "E2's model dollars for the day are spent"
SAIL_DAY = "the House's Sail day"
#: The loop's names of E2's two rounds (league/swarm/loop.py `_round`): a round that raises leaves a `swarm.status`
#: event {"round": name, "error": ...} and no `swarm.elane` event.
ROUNDS = {"elane": "births", "elane_train": "train"}
#: The fails that say a PROGRAM could not be run to a judgment by its own fault (`elane_train.FAILS`): no mechanism was
#: judged. The bar's own codes are `elane_train.JUDGED` and STATE.
PROGRAM_FAULTS = ("DQ", "LOAD", "RUN")
BAR_CODES = ("Y1", "Y2", "P1", "R1", "STATE")
_CODE = re.compile(r"^[A-Z][A-Z0-9]{0,9}$")
#: The exception classes a disqualification's record may name (`elane_train.ERROR_CLASSES`: Python's own and numpy's).
ERROR_CLASSES = frozenset({
    "ArithmeticError", "AssertionError", "AttributeError", "FloatingPointError", "IndexError", "KeyError", "LookupError",
    "MemoryError", "NameError", "NotImplementedError", "OverflowError", "RecursionError", "RuntimeError", "StopIteration",
    "TypeError", "UnboundLocalError", "ValueError", "ZeroDivisionError", "LinAlgError", "AxisError", "Exception"})
#: WHAT A DISQUALIFICATION'S RECORD SAYS (`elane_train.dq_said`: counts, a line of the program's own file and an
#: exception CLASS, or one of the House's fixed sentences about what decide returned), read back into a closed class.
_DQ_FIXED = (("a malformed intent", "malformed intent"), ("a return that is no list of intents", "no list of intents"),
             ("more intents than one call may return", "too many intents"),
             ("a decide past its time limit", "time limit"), ("ran past the run's time budget", "time budget"))
_DQ_FIRST = re.compile(r"\bthe first an? ([A-Za-z]+)\b")
_DQ_LINE = re.compile(r"\bat line (\d{1,6})\b")
UNNAMED = "unnamed"
#: WHAT EACH CLASS OF ERROR MOST OFTEN IS IN AN EQUITY PROGRAM, SHORT: one fixed sentence a class for the owner's step
#: (the contract's own, longer sentence is `elane_train.DQ_HINTS`, which the report prints; a test holds the two to the
#: same classes). The House's words about the contract: rules only, nothing a run read.
DQ_SHORT: dict[str, str] = {
    "TypeError": "most often ctx.bars[sym] read by key or as rows, ctx.positions read as a dict, or None in arithmetic",
    "AttributeError": "most often a field ctx or the bars lack, a lot read by attribute, or a pandas method on an array",
    "KeyError": "most often a symbol outside NEEDS, a key a lot lacks, or a STATE key read before it was written",
    "IndexError": "most often an array shorter than the window indexed (a run's first sessions hold little history)",
    "ValueError": "most often an empty or all-NaN window handed to numpy, or a write into one of ctx's arrays",
    "ZeroDivisionError": "a division by a price, a range, a volatility or a count that is zero on some session",
    "NameError": "a name the file never defines (only math and numpy import)",
    "UnboundLocalError": "a name assigned on one path and read on another",
}

#: WHY A PROPOSAL WAS NOT BORN (league/swarm/elane_births.py `EquityPass.admit`): how each refusal begins, its class and
#: the House's sentence for the class. A refusal's own text carries what the model wrote (a lane, a symbol, a slug): only
#: the class and this table's sentence reach a notice.
REFUSALS: tuple[tuple[str, str, str], ...] = (
    ("lane: ", "lane", "a lane that is not beta or equity, or not its card's"),
    ("structure: ", "structure", "a structure outside elane.structures (a beta family trades ETFs only)"),
    ("symbols: ", "symbols", "a symbol outside elane.universe (or none, or more than a family may trade)"),
    ("agenda: ", "agenda", "an agenda key that is not on the agenda, or one whose data the House does not hold"),
    ("mechanism: ", "mechanism", "no mechanism sentence"),
    ("its cell ", "closed_cell", "a cell closed by Train refutations"),
    ("the same idea on the same symbols", "same_idea", "the same idea on the same symbols as a family in Train research"),
    ("it continues ", "tried_lineage", "a lineage that has its one Validation try"),
    ("its rebirth continues ", "tried_lineage", "a lineage that has its one Validation try"),
    ("card: ", "card", "a card the card checks refuse"),
    ("graveyard: ", "graveyard", "a refuted row of the equity graveyard binding its cell"),
    ("the equity graveyard's binding", "graveyard", "a refuted row of the equity graveyard binding its cell"),
    ("the pass's ", "quota", "more proposals than the pass's births"),
    ("the equity lanes' births are off", "quota", "more proposals than the pass's births"),
    ("the quota", "quota", "more proposals than the pass's births"),
    ("not born: ", "store", "a birth the store refused"),
)
OTHER = "other"
REFUSAL_WORDS = {**{cls: words for _, cls, words in REFUSALS}, OTHER: "another refusal"}
_FOREIGN = re.compile(r"\(([A-Z0-9., ]{1,120}) not\)$")
#: How a barren equity pass bore nothing, and the owner's lever for each way a setting clears (`elane_births`).
BARREN = ("refused", "empty", "truncated", "failed", "raised")
#: A PASS EVERY ROUTE REFUSED FOR A SETTING (league/swarm/elane_births.py `EquityPass.run`: its event's `setting`, one
#: of `elane_births.SETTING_KEYS`' values; a test holds the keys equal): the `elane.e2` key and what is wrong with it.
#: The pass's own closed word, never a route's error text.
SETTINGS = {
    "births_max_output_tokens": "elane.e2.births_max_output_tokens is above the model provider's own output limit",
    "births_effort": "elane.e2.births_effort is an effort the model provider does not take",
    "routes": "elane.e2.routes names a Sail profile the model provider does not know",
}
SETTING = "setting"
BIRTH_LEVERS = {
    "symbols": ("the architect proposes symbols elane.universe does not hold{named}: its request names the universe's "
                "own symbols only (release E2.4); widening the universe is your decision (elane.universe in swarm.json, "
                "inside league/equity/config.py UNIVERSE)"),
    "structure": "the architect proposes structures elane.structures does not hold: widening it is your decision",
    "closed_cell": ("the proposals land in cells closed by Train refutations (the equity graveyard binds by design): a "
                    "wider elane.universe opens other cells, or raise elane.e2.refuted_cell_cap only if the evidence "
                    "warrants spending those cells again"),
    "tried_lineage": ("the proposals continue lineages that have their one Validation try (the ration binds by design): "
                      "a wider elane.universe opens other slices"),
    "truncated": ("the architect's equity answers are cut short before a family can be read: raise "
                  "elane.e2.births_max_output_tokens{limit} or lower elane.e2.max_per_pass in swarm.json"),
    "raised": "the equity pass raises (the swarm log's \"elane failed\" lines): it needs a fix, in a release",
    SETTING: ("every model route refuses the equity pass's request before it is sent: {setting}; asking again changes "
              "nothing until the setting does (swarm.json; python3 set_swarm.py elane.e2.<key>=<value> --apply)"),
}
#: The ways a setting clears that wait `BIRTHS_OWNER_HOURS` for nobody: nothing the lanes do corrects them.
BIRTH_LEVERS_AT_ONCE = (SETTING,)

#: THE STATIC RULES that refuse a program before it is stored or run (league/swarm/elane_train.py `check_code`,
#: `EquityResearcher.write`): how each refusal begins and its rule. `_EQUITY_RULE` reads any "equity <name> rule" a
#: release adds the same way. The first three of `NOT_RULES` are no rule's refusal (no program, a stop too early, the
#: same file again): they count as programs written, never toward one rule's share.
RULES: tuple[tuple[str, str], ...] = (
    ("refused by the code rules", "code"), ("refused: ", "code"), ("NEEDS", "needs"),
    ("the answer held no program", "no_program"), ("a stop is accepted only once", "early_stop"),
    ("the same program as v", "same_program"),
)
_EQUITY_RULE = re.compile(r"^refused (?:before it ran )?by the equity ([a-z]{1,20}) rule\b")
NOT_RULES = ("no_program", "early_stop", "same_program", OTHER)
#: How the record names a program the architect carried at birth and a static rule refused (`EquityPass.birth`).
ARCHITECT_PROGRAM = "the architect's program: "
RULE_WORDS = {"reading": "the reading rule", "level": "the level rule", "memory": "the memory rule",
              "code": "the code rules", "needs": "the NEEDS rule", "no_program": "an answer with no program",
              "early_stop": "a stop before the bar judged a version", "same_program": "the same program again",
              OTHER: "another refusal"}
#: A STATIC RULE'S SENTENCES, IN CLOSED WORDS: for each rule, the House's own phrase that marks one of its sentences
#: (league/swarm/elane_review.py `_Reading`, `_Levels`, `memory_refusals`; league/gym/safety.py) and this table's words
#: for it. A rule's sentence quotes the program's own source, so it never reaches a notice as written: the first marker
#: found names it. Order matters where one sentence holds two markers.
SENTENCES: dict[str, tuple[tuple[str, str], ...]] = {
    "reading": (
        ("reads a symbol's bars by key",
         "a symbol's bars read by key (ctx.bars[sym] is ONE object: its arrays are read by attribute)"),
        ("reads a symbol's bars by position", "a symbol's bars read by position or as rows"),
        ("is iterated as rows", "a symbol's bars iterated as rows"),
        ("is unpacked", "a symbol's bars unpacked"),
        ("walks, counts or converts a symbol's bars", "a symbol's bars walked, counted or converted whole"),
        ("is handed a symbol's bars whole", "a symbol's bars handed whole to numpy or math"),
        ("is put into arithmetic", "a symbol's bars put into arithmetic whole"),
        ("is compared or searched", "a symbol's bars compared or searched whole"),
        ("reads ctx.positions (or ctx.closed) as a dict",
         "ctx.positions or ctx.closed read as a dict (each is a list of lots)"),
        ("subscripts a float", "ctx.prices[sym] or ctx.caps[sym] subscripted (each is one float)"),
        ("reads a lot by attribute", "a lot read by attribute (a lot is a dict)"),
        ("ctx has no field", "a field ctx does not have"),
        ("a symbol's bars have open, high, low, close, volume and ret only", "a field a symbol's bars do not have"),
        ("has no key", "a key a lot does not have"),
        ("ctx.events and ctx.events_next hold", "an event flag ctx.events does not hold"),
        ("ctx.rejects is a list of strings", "ctx.rejects read as other than a list of strings"),
        ("ctx.positions and ctx.closed are LISTS", "ctx.positions or ctx.closed read by an attribute a list does not have"),
        ("ctx.events is a dict of booleans", "ctx.events read by attribute"),
        ("ctx.bars, ctx.prices and ctx.caps are dicts by symbol", "ctx.bars, ctx.prices or ctx.caps read by attribute"),
        ("decide returns an empty dict", "an empty dict returned for no order (return [])"),
        ("which has none of", "a returned dict that is no intent (none of buy, sell, cancel)"),
        ("an intent has EXACTLY one", "an intent with two of buy, sell, cancel"),
        ("the intent's \"at\" is", "an intent whose \"at\" is neither open nor close"),
        ("the intent sells", "a sell that names a symbol or a whole lot (a lot is sold by its id)"),
        ("the intent buys", "a buy that names no symbol"),
        ("has neither \"share\" nor \"usd\"", "a buy with neither share nor usd"),
        ("the buy has both \"share\" and \"usd\"", "a buy with both share and usd"),
        ("the buy's \"", "a buy whose size is outside its range"),
    ),
    "level": (
        ("keeps the run's dollars in a lot's tag", "the run's dollars kept in a lot's tag"),
        ("the sleeve's dollars now against the run's anchor",
         "the sleeve's dollars held against the run's anchor (its own profit since it began)"),
        ("a price level with the sleeve's dollars", "a price level compared with the sleeve's dollars"),
        ("a price or volume level (or its log)", "a price or volume level held against a constant or a PARAMS value"),
        ("the ratio of two different symbols' prices",
         "the ratio of two symbols' prices held against a constant or a PARAMS value"),
        ("the sleeve's dollars of this run", "the sleeve's dollars of the run held against a constant or a PARAMS value"),
        ("nested too deeply", "a program nested too deeply to be read"),
    ),
    "memory": (
        ("an object that belongs to a module", "an object of numpy or math held as a value (memory outside STATE)"),
    ),
    "code": (
        ("does not compile", "a program that does not compile"),
        ("imports only math and numpy", "an import other than math or numpy"),
        ("is not allowed", "a name or a construct the code rules do not allow"),
        ("exactly one top-level function decide", "no single top-level decide(ctx)"),
        ("decide takes exactly one argument", "a decide that does not take ctx alone"),
        ("PARAMS", "a PARAMS that is not one simple top-level assignment"),
        ("at the top level", "a top-level assignment the contract does not allow"),
        ("characters", "a program over the length limit"),
        ("the program is empty", "an empty program"),
    ),
    "needs": (
        ("must be a literal dict", "NEEDS that is no literal dict at the top level"),
        ("must be a non-empty list", "NEEDS with no symbols"),
        ("outside the family's symbols", "NEEDS naming a symbol outside the family's own"),
    ),
}
ANOTHER = "another sentence of the rule"
_ITEM = re.compile(r"(?:^|[:;] )line (\d{1,6}): ")
#: The error classes a reading-rule sentence may say its misreading raises.
_RAISES = ("TypeError", "AttributeError", "KeyError")

#: What the floor does about each cause by itself.
#: Kept short: a cause's sentence, this and its owner step are one House warning of `WARN_CHARS` (`warning`).
DOING = {
    "elane_dq": ("Each disqualified version's author is shown the line of its first error; a family whose versions all "
                 "end so is retired STALLED. Nothing loosens the bar or the sandbox."),
    "elane_births": ("The equity pass asks again at its own cadence and tells its next request the last pass's refusals "
                     "by class, in closed words. Nothing loosens the admission."),
    "elane_refused": ("Each refusal is in its author's next brief with what to write instead; it costs one write attempt, "
                      "never a scored version. Nothing loosens a rule."),
    "starved": ("E2 asks again by itself once it may (its hour's spend under its pace, 00:00 UTC for its day, room under "
                "the Sail guard's line). Versions already written are still scored. Nothing raises a pace or a line, and "
                "nothing is mailed for a setting at work."),
    "broken": ("The Train round comes every ten minutes while it has work; a failure of the House's backs its family off "
               "and is alerted once (elane_train_house); a question no route answered is asked again after its backoff. "
               "Nothing here repairs anything."),
    "not_judged": "Nothing: the cause is not judged.",
}
REPORT = "python3 -m league.ops.elane_health --state /workspace/state"
#: The ways an idle lane is BROKEN that nothing on the floor heals: the owner's step. The first three are BROKEN BY
#: THE LANE'S OWN RECORD (`BROKEN_KINDS`): they stand whatever E2's lines hold.
IDLE_OWNER_KINDS = ("raised", "house", "errors", "silent", "no_round")
BROKEN_KINDS = ("raised", "house", "errors")
#: What a lane held by a setting says of this cause (`_idle_check`).
NO_STALL = ("A lane held by its own settings is no stall: this cause stands for a broken lane only, and what a setting "
            "costs is read here and in the equity research funnel (train_steps).")
#: The cut of a House warning (league/ops/stall.py `_alert`, league/ops/context.py `Context.alert`).
WARN_CHARS = 900
#: The gateway's cuts of a stall entry (gateway/lib/email.mjs: `sentence(entry.what, 400)`, `sentence(entry.doing, 700)`,
#: STALL_STEP_CHARS, STALL_NUMBERS), the figures of each cause its mail shows first (`mailed`), and what a check's
#: numbers hold that the mail does not list (kept on the House: the receipt and the report): what is no figure, and
#: E2's own dollar figures, which the notice's two decimal places would misstate (a pace of a cent and two thirds is
#: not $0.02; the sentence says them to the tenth of a cent).
WHAT_CHARS, DOING_CHARS, STEP_CHARS, FIGURES = 400, 700, 400, 16
MAIL_FIGURES = {"elane_dq": ("scored", "faulted", "families", "top_error", "basis"),
                "elane_births": ("barren_passes", "kind", "born", "setting"),
                "elane_idle": ("kind", "idle_hours", "researching", "held_now", "house_failures", "step_errors",
                               "rounds_raised", "train_rounds", "steps_due", "steps_skipped"),
                "elane_refused": ("answers", "top_rule", "top_rule_n", "basis")}
NOT_MAILED = ("judged", "examples", "hint", "pace_usd_hour", "spent_last_hour_usd", "day_line_usd", "spent_today_usd")


# ---------------------------------------------------------------------------------------------- small readers
def _loads(text: Any) -> dict[str, Any]:
    try:
        value = json.loads(text) if isinstance(text, (str, bytes)) else text
    except (TypeError, ValueError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def _count(value: Any) -> int:
    number = _num(value)
    return int(number) if number is not None and number > 0 else 0


def _token(text: Any) -> str:
    """A figure the gateway echoes as a token (lower case, `[a-z0-9_]`): "TypeError" -> "typeerror"."""
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")[:40] or "none"


def _top(counts: Mapping[str, int], n: int = 3) -> list[tuple[str, int]]:
    return sorted(((k, int(v)) for k, v in counts.items() if v), key=lambda kv: (-kv[1], kv[0]))[:n]


def _bump(counts: dict[str, int], key: str, by: int = 1) -> None:
    counts[key] = counts.get(key, 0) + by


def _hours(seconds: float) -> str:
    return f"{max(0.0, seconds) / 3600.0:.1f}"


def _cut(text: Any, limit: int) -> str:
    """`text` on one line inside `limit` characters (a cut ends "...")."""
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:max(0, limit - 3)].rstrip() + "..."


def _lead(parts: Sequence[str], limit: int, least: int = 80) -> str:
    """The leading sentences of `parts` that fit whole inside `limit` characters, joined (a check's sentences come
    most telling first), and the next one cut ("...") when at least `least` characters are left for it; nothing after
    a cut."""
    out = ""
    for part in (" ".join(str(p).split()) for p in parts if p):
        room = limit - len(out) - (1 if out else 0)
        if len(part) > room:
            if room >= least or not out:
                out += (" " if out else "") + _cut(part, room)
            break
        out += (" " if out else "") + part
    return out


# ---------------------------------------------------------------------------------------------- closed words
def dq_class(why: Any) -> str:
    """The closed class of a disqualification's record (`elane_train.dq_said`): an exception class of
    `ERROR_CLASSES`, "malformed intent", "no list of intents", "too many intents", "time limit", "time budget", or
    `UNNAMED` (the record names none)."""
    text = str(why or "")
    for mark, name in _DQ_FIXED:
        if mark in text:
            return name
    found = _DQ_FIRST.search(text)
    return found.group(1) if found and found.group(1) in ERROR_CLASSES else UNNAMED


def dq_line(why: Any) -> int | None:
    found = _DQ_LINE.search(str(why or ""))
    return int(found.group(1)) if found else None


def refusal_class(why: Any) -> str:
    """The class of an equity proposal's refusal (`REFUSALS`), `OTHER` for one that begins as none of them."""
    text = str(why or "")
    for start, name, _ in REFUSALS:
        if text.startswith(start):
            return name
    return OTHER


def foreign_symbols(why: Any, universe: Sequence[str] | None = None) -> list[str]:
    """The symbols a `symbols` refusal names as outside `elane.universe` that the CODE's universe holds
    (league/equity/config.py UNIVERSE: a closed list, so nothing a model made up is repeated); [] for any other
    refusal. `universe` in place of the code's (tests)."""
    found = _FOREIGN.search(str(why or "")) if refusal_class(why) == "symbols" else None
    if not found:
        return []
    if universe is None:
        try:
            from ..equity.config import UNIVERSE

            universe = tuple(UNIVERSE)
        except Exception:  # noqa: BLE001 - no closed list to hold them to: none is named
            universe = ()
    known = {str(s).upper() for s in universe}
    return [s for s in dict.fromkeys(x.strip() for x in found.group(1).split(",")) if s in known]


def rule_of(why: Any) -> str:
    """The static rule that refused a program before a run, from how its refusal begins (`RULES`, `_EQUITY_RULE`);
    a program the architect carried at birth is read past its prefix. `OTHER` for a refusal that begins as none."""
    text = str(why or "")
    if text.startswith(ARCHITECT_PROGRAM):
        text = text[len(ARCHITECT_PROGRAM):]
    found = _EQUITY_RULE.match(text)
    if found:
        return found.group(1)
    for start, name in RULES:
        if text.startswith(start):
            return name
    return OTHER


def sentences(why: Any) -> list[tuple[int | None, str, str | None]]:
    """A static refusal's sentences in closed words: (the line, this module's words for the sentence, the error class
    the sentence says its misreading raises or None), one a "line N: ..." item of the refusal (one for a refusal with
    no line). The rule's own sentence quotes the program's source and is never returned."""
    rule = rule_of(why)
    table = SENTENCES.get(rule)
    if table is None:
        return []
    text = str(why or "")
    cuts = list(_ITEM.finditer(text))
    items = [(int(m.group(1)), text[m.end():(cuts[i + 1].start() if i + 1 < len(cuts) else len(text))])
             for i, m in enumerate(cuts)] or [(None, text)]
    out = []
    for line, item in items:
        words = next((said for mark, said in table if mark in item), ANOTHER)
        raises = next((cls for cls in _RAISES if cls in item), None) if rule == "reading" else None
        out.append((line, words, raises))
    return out


def skip_kind(text: Any) -> str | None:
    """Why E2 asks no model, from the lane's own reason (`elane_yield.hold`): "usd_day", "sail_day" or "pace"; None
    for no reason; `OTHER` for a skip that is none of them."""
    if not text:
        return None
    text = str(text)
    if text.startswith(DAY_SPENT):
        return "usd_day"
    if text.startswith(SAIL_DAY):
        return "sail_day"
    return "pace" if "pace" in text else OTHER


def step_read(step: Any) -> dict[str, Any]:
    """ONE TRAIN STEP as the round's event holds it (league/swarm/elane_train.py `EquityResearcher.step` and what it
    calls), in closed words: {answered (a generator's program answer was read), refused (the static rule that refused
    it, else None), why (that refusal's own text), scored (a version was judged), fails, passed (the bar and its
    restart check), review ("pass" | "refused" | None), retired ("stalled" | "refuted" | None), house (a failure of
    the House's, by kind), skipped (`skip_kind`), unanswered (no route answered a question), error, rescored}."""
    step = step if isinstance(step, Mapping) else {}
    score = step.get("score") if isinstance(step.get("score"), Mapping) else step
    review = score.get("review") if isinstance(score.get("review"), Mapping) else None
    if review is None and (step.get("review") == "pass" or "stage" in step):
        review = step  # a review read in a later round than the score: the step is the review's own answer
    fails = [str(f) for f in score.get("fails") or []] if isinstance(score.get("fails"), list) else None
    scored = fails is not None and score.get("version") is not None and "stage" not in score and "rescored" not in score
    refused = step.get("refused") if isinstance(step.get("refused"), str) else None
    retired = None
    for holder in (step, score, review or {}, score.get("retired"), (review or {}).get("retired")):
        if isinstance(holder, Mapping):
            retired = retired or next((kind for kind in ("stalled", "refuted") if isinstance(holder.get(kind), list)), None)
    skipped = step.get("skipped") or (review or {}).get("skipped") or score.get("skipped")
    quiet = [h for h in (step, score, review or {}) if h.get("error") and "retry_in" in h and "house" not in h]
    return {"answered": refused is not None or ("route" in step and step.get("version") is not None),
            "refused": rule_of(refused) if refused is not None else None, "why": refused,
            "scored": scored, "fails": fails if scored else [], "passed": bool(scored and score.get("passed") is True),
            "review": (None if review is None else "pass" if review.get("review") == "pass" else
                       "refused" if review.get("fails") == ["REVIEW"] else None),
            "retired": retired, "house": str(score.get("house")) if score.get("house") else None,
            "skipped": skip_kind(skipped) if isinstance(skipped, str) else None, "unanswered": bool(quiet),
            "error": bool(step.get("error")) and not quiet, "rescored": score.get("rescored")}


def pass_read(payload: Any) -> dict[str, Any]:
    """ONE EQUITY PASS as its event holds it (league/swarm/elane_births.py `EquityPass.run`): {asked (a model was
    asked, or would have been: no route answered), skipped (the reason word, else None), born, proposed, refused (the
    count), truncated, failed (no route answered), setting (the `SETTINGS` key every route refused the request for,
    else None), want, barren (asked and bore none), how (one of `BARREN`, else None), items (its refusals' own texts,
    the first twelve)}."""
    p = payload if isinstance(payload, Mapping) else {}
    born = len(p["born"]) if isinstance(p.get("born"), list) else 0
    failed = bool(p.get("error"))
    asked = "proposed" in p or failed
    proposed = _count(p.get("proposed"))
    refused = p.get("refused") if isinstance(p.get("refused"), Mapping) else {}
    items = [str(i.get("why") or "") for i in refused.get("items") or [] if isinstance(i, Mapping)]
    truncated = p.get("truncated") is True
    how = None
    if asked and not born:
        how = "failed" if failed else "refused" if proposed else "truncated" if truncated else "empty"
    return {"asked": asked, "skipped": str(p["skipped"]) if isinstance(p.get("skipped"), str) else None, "born": born,
            "proposed": proposed, "refused": max(_count(refused.get("count")), len(items)), "truncated": truncated,
            "failed": failed, "setting": p.get("setting") if failed and p.get("setting") in SETTINGS else None,
            "want": _count(p.get("equity_want")), "short": _count(p.get("equity_short")),
            "barren": asked and not born, "how": how, "items": items}


# ---------------------------------------------------------------------------------------------- the reads
class _Reader:
    """The swarm's store as `elane_yield`'s readers need it (`get`, `_one`, `spent`), over a read-only connection: the
    lane's own reading of its pace, its day and the House's Sail day, with nothing written."""

    def __init__(self, db: Any):
        self.db = db

    def get(self, key: str, default: Any = None) -> Any:
        rows = guard.ids(self.db, "SELECT value FROM kv WHERE key=?", (key,))
        try:
            return json.loads(rows[0]) if rows else default
        except (TypeError, ValueError):
            return default

    def _one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        rows = guard.rows(self.db, sql, params)
        return rows[0] if rows else None

    def spent(self, kinds: Sequence[str] | None = None, *, since: float | None = None) -> float:
        sql, params = "SELECT COALESCE(SUM(usd),0) AS usd FROM spend WHERE 1=1", []
        if kinds:
            sql += f" AND kind IN ({','.join('?' * len(kinds))})"
            params += list(kinds)
        if since is not None:
            sql += " AND epoch>=?"
            params.append(float(since))
        row = self._one(sql, params)
        return float(row["usd"]) if row else 0.0


def e2_families(db: Any) -> list[dict[str, Any]]:
    """Every family the equity pass bore, alive or retired (its spec names an equity lane and its birth route), with
    E2's own Train record of it: {id, lane, born_at, alive, status, versions {n: verdict}, refused [{at, why}],
    waits (the backoffs it has on record, {"infra:<kind>" | "unanswered": until when}), house_fails (the failures of
    the House's its newest version has had one after another, `infra.count`: 0 with none on record)}. Nothing of a
    later stage is read (no band, no Validation, no look)."""
    out = []
    for row in guard.rows(db, "SELECT id, spec, state, born_at, retired_at FROM families WHERE structure IN ('etf', 'stock') "
                              "ORDER BY born_at, id"):
        spec = _loads(row["spec"])
        if spec.get("lane") not in LANES or not spec.get(ROUTE_KEY):
            continue
        record = _loads(_loads(row["state"]).get(STATE_KEY))
        versions = record.get("versions") if isinstance(record.get("versions"), Mapping) else {}
        waits = {}
        for name in ("infra", "unanswered"):
            held = record.get(name) if isinstance(record.get(name), Mapping) else {}
            if _num(held.get("next_at")) is not None:
                waits[f"infra:{held.get('kind') or 'house'}" if name == "infra" else name] = float(held["next_at"])
        out.append({"id": str(row["id"]), "lane": spec["lane"], "born_at": row["born_at"], "alive": row["retired_at"] is None,
                    "status": str(record.get("status") or "researching"),
                    "versions": {str(k): dict(v) for k, v in versions.items() if isinstance(v, Mapping) and str(k).isdigit()},
                    "refused": [dict(r) for r in record.get("refused") or [] if isinstance(r, Mapping)]
                    if isinstance(record.get("refused"), list) else [],
                    "waits": waits,
                    "house_fails": _count(record["infra"].get("count")) if isinstance(record.get("infra"), Mapping) else 0})
    return out


def _events(db: Any, kind: str, start: float, end: float, mark: str | None = None) -> list[tuple[float, dict[str, Any]]]:
    """(epoch, payload) of the `kind` events in `[start, end)`, oldest first (`mark`: only payloads that hold it)."""
    sql = "SELECT at, payload FROM events WHERE kind=? AND at>=? AND at<?"
    params: list[Any] = [kind, S.iso(start), S.iso(end)]
    if mark:
        sql += " AND instr(payload, ?) > 0"
        params.append(mark)
    out = []
    for row in guard.rows(db, sql + " ORDER BY seq", params):
        at, payload = S.epoch(row["at"]), _loads(row["payload"])
        if at is not None and payload:
            out.append((at, payload))
    return out


def _window(db: Any, start: float, end: float) -> dict[str, Any]:
    """The equity lanes' events in `[start, end)`: the equity passes (`passes`), the Train rounds (`rounds`), the
    families retired on Train (`retired`: (epoch, "stalled" | "refuted")), the rounds that raised (`raised`: (epoch,
    "births" | "train")) and the equity births (`born`: (epoch, the payload's `program`))."""
    out: dict[str, Any] = {"passes": [], "rounds": [], "retired": [], "raised": [], "born": []}
    for at, payload in _events(db, "swarm.elane", start, end):
        what = payload.get("pass")
        if what == "births":
            out["passes"].append((at, payload))
        elif what == "train":
            out["rounds"].append((at, payload))
        elif what in ("stalled", "refuted"):
            out["retired"].append((at, what))
    for at, payload in _events(db, "swarm.status", start, end, '"round"'):
        if payload.get("round") in ROUNDS and payload.get("error"):
            out["raised"].append((at, ROUNDS[payload["round"]]))
    for at, payload in _events(db, "swarm.born", start, end, '"lane"'):
        if payload.get("lane") in LANES:
            out["born"].append((at, str(payload.get("program") or "")))
    return out


def _held(db: Any, loaded: Mapping[str, Any] | None, now: float) -> tuple[dict[str, Any] | None, str | None]:
    """Whether E2 may ask a model NOW, in the lane's own words (`elane_yield.hold` over a read-only reader: the same
    function the equity pass and the Train round call before each model call), with its pace and day: ({text, kind
    (`skip_kind`), limit_usd_hour, spent_last_hour_usd, day_line_usd, spent_today_usd}, None); (None, the class of what
    failed) when it cannot be read."""
    try:
        from ..swarm import elane_yield

        store = _Reader(db)
        text = elane_yield.hold(store, loaded, now)
        pace = elane_yield.pace(store, loaded, now)
        return {"text": text, "kind": skip_kind(text), "limit_usd_hour": float(pace["limit_usd_per_hour"]),
                "spent_last_hour_usd": float(pace["spent_last_hour_usd"]),
                "day_line_usd": float(elane_yield.day_line(loaded)),
                "spent_today_usd": float(elane_yield.spent_today(store, now))}, None
    except Exception as exc:  # noqa: BLE001 - not read: the idle cause says so, and `checks` makes it an error
        return None, type(exc).__name__


def facts(db: Any, now: float, loaded: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """What the checks read from the swarm's store, in one read transaction (`guard.read`): the families the equity
    pass bore (`e2_families`), the lanes' events of the last `LOOKBACK_HOURS` (`_window`), E2's kv clocks, whether any
    `swarm.elane` event is on record and the first one's time, and the lane's own reading of whether it may ask a
    model now (`_held`: `held`, and `held_error` when it could not be read)."""
    out: dict[str, Any] = {"families": e2_families(db), **_window(db, now - LOOKBACK_HOURS * 3600.0, now + 1.0)}
    reader = _Reader(db)
    out["kv"] = {key: _num(reader.get(key)) for key in (BIRTHS_AT_KEY, TRAIN_AT_KEY, TRAIN_OK_KEY)}
    first = guard.rows(db, "SELECT count(*) AS n, min(at) AS at FROM events WHERE kind='swarm.elane'")
    out["events"] = int(first[0]["n"] or 0) if first else 0
    out["first_event_at"] = S.epoch(first[0]["at"]) if first else None
    out["held"], out["held_error"] = _held(db, loaded, now)
    return out


# ---------------------------------------------------------------------------------------------- the switch
def lanes(loaded: Mapping[str, Any] | None, f: Mapping[str, Any] | None = None, *,
          paused: bool = False) -> tuple[bool, str | None, dict[str, Any]]:
    """WHEN A CAUSE IS JUDGED (the module docstring): (judged, why not, the lanes' settings the checks read:
    {births_every_seconds, pace_share, usd_day, budget_floor}). `f`: the store's facts, for the empty lanes. LANES THAT
    COULD NOT BE READ (the settings, or E2's own readers) answer `unread` in the third value, the class that failed:
    `checks` makes it an entry of the job's `errors`, so an alarm that cannot see is never a silent "Not judged"."""
    c: dict[str, Any] = {}
    if not isinstance(loaded, Mapping):
        return False, "the swarm's settings could not be read", {"unread": "the swarm's settings"}
    try:
        from ..swarm import architect, elane, elane_births, elane_yield, loop

        wired = callable(getattr(architect.Architect, "equity_pass", None)) and hasattr(loop, "EquityResearcher")
        mode, share = elane.cfg(loaded)["mode"], elane_births.birth_share(loaded)
        money = elane_yield.cfg(loaded)
        budget = loaded.get("budget") if isinstance(loaded.get("budget"), Mapping) else {}
        c = {"births_every_seconds": float(elane_births.cfg(loaded)["births_every_seconds"]),
             "pace_share": float(money["pace_share"]), "usd_day": float(money["usd_day"]),
             "budget_floor": budget.get("source") == "floor"}
    except Exception as exc:  # noqa: BLE001 - the lanes' own readers are not in this tree, or do not read
        return False, f"release E2's readers could not be read ({type(exc).__name__})", {"unread": type(exc).__name__}
    if not wired:
        return False, "release E2's rounds are not in the running tree", c
    if mode == "off":
        return False, "the equity lanes are off (elane.mode)", c
    if share <= 0:
        return False, "the equity lanes' births are off (elane.birth_share is 0)", c
    if paused:
        return False, "the floor is paused (a maintenance pause or a stopped swarm stops the lanes by design)", c
    if c["usd_day"] <= 0 or c["pace_share"] <= 0:
        return False, ("the equity lanes' model dollars are set to zero (elane.e2.usd_day or elane.e2.pace_share): "
                       "paused by setting"), c
    if f is not None and not f.get("families") and not f.get("events"):
        return False, "the equity lanes hold no family and no equity pass is on record", c
    return True, None, c


def _not_judged(why: str, numbers: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {"stalled": False, "judged": False, "what": f"Not judged: {why}.", "numbers": {**(numbers or {}), "judged": False},
            "doing": DOING["not_judged"], "owner_step": None, "onset": None}


def _judged(check: dict[str, Any]) -> dict[str, Any]:
    """A judged check as the stall receipt keeps it: the receipt holds a check's sentence, numbers, doing and owner
    step, so `judged`, the `examples` (the families, versions and lines an operator reads) and the `hint` (the
    contract's own sentence for the error class named) ride its numbers (`NOT_MAILED`: never the mail's figures)."""
    extra = {"judged": True, **{k: check[k] for k in ("examples", "hint") if check.get(k)}}
    return {**check, "judged": True, "numbers": {**check["numbers"], **extra}}


def _since(now: float, hours: float, since: float | None) -> tuple[float, str]:
    """A window's start (the later of `hours` ago and the running release's first start) and the words for it."""
    edge = now - hours * 3600.0
    if since is not None and edge < since <= now:
        return since, f"the {_hours(now - since)} h since the running release started"
    return edge, f"the last {hours:g} h"


def _usd(value: Any) -> str:
    """A dollar figure of E2's own: two places from a dollar up, three under (a pace of a cent and a half is not $0.02)."""
    value = float(value)
    return f"${value:.2f}" if abs(value) >= 1.0 else f"${value:.3f}"


def _output_limit() -> int | None:
    """The model provider's own output limit, as the lanes' settings are held to it (`elane_yield.OUTPUT_LIMIT`)."""
    try:
        from ..swarm.elane_yield import OUTPUT_LIMIT

        return int(OUTPUT_LIMIT)
    except Exception:  # noqa: BLE001 - the lever is named without it
        return None


# ---------------------------------------------------------------------------------------------- the checks
def _answers(f: Mapping[str, Any], start: float, now: float) -> list[tuple[float, str, Any]]:
    """THE PROGRAMS THE EQUITY GENERATORS WROTE in `[start, now]`, oldest first: (when, its family, the static rule's
    refusal of it, None for one that was stored). The researchers' programs come from the Train rounds' events (each
    step that read an answer); the architect's programs at birth from the births (`program` "v1": stored) and the
    families' records (a refusal named `ARCHITECT_PROGRAM`)."""
    rows: list[tuple[float, str, Any]] = []
    for at, payload in f.get("rounds") or []:
        if not start <= at <= now:
            continue
        for step in payload.get("steps") or []:
            read = step_read(step)
            if read["answered"]:
                rows.append((at, str(step.get("family") if isinstance(step, Mapping) else None),
                             None if read["refused"] is None else str(read["why"] or "")))
    for at, program in f.get("born") or []:
        if start <= at <= now and program == "v1":
            rows.append((at, "", None))
    for fam in f.get("families") or []:
        for row in fam["refused"]:
            at = S.epoch(row.get("at"))
            if at is not None and start <= at <= now and str(row.get("why") or "").startswith(ARCHITECT_PROGRAM):
                rows.append((at, fam["id"], str(row.get("why"))))
    return sorted(rows, key=lambda row: row[0])


def refusals_tally(f: Mapping[str, Any], start: float, now: float,
                   rows: Sequence[tuple[float, str, Any]] | None = None) -> dict[str, Any]:
    """The programs the equity generators wrote in `[start, now]` (`_answers`; `rows`: these of them instead) and the
    static rules' refusals of them: {answers, stored, refused, by_rule, sentences {rule: {words: n}}, raises {error
    class: {words: n}} (the reading rule's sentences by the error each says its misreading raises), examples [{family,
    rule, line, sentence}]}."""
    out: dict[str, Any] = {"answers": 0, "stored": 0, "refused": 0, "by_rule": {}, "sentences": {}, "raises": {},
                           "examples": []}
    for _, family, why in (_answers(f, start, now) if rows is None else rows):
        out["answers"] += 1
        if why is None:
            out["stored"] += 1
            continue
        rule = rule_of(why)
        out["refused"] += 1
        _bump(out["by_rule"], rule)
        for line, words, raises in sentences(why):
            _bump(out["sentences"].setdefault(rule, {}), words)
            if raises:
                _bump(out["raises"].setdefault(raises, {}), words)
            if len(out["examples"]) < 6:
                out["examples"].append({"family": str(family), "rule": rule, "line": line, "sentence": words})
    return out


def _scored(f: Mapping[str, Any], start: float, now: float) -> list[tuple[float, str, int, dict[str, Any]]]:
    """Every equity version scored in `[start, now]`, oldest first: (when, its family, its number, its verdict)."""
    rows = []
    for fam in f.get("families") or []:
        for n, verdict in fam["versions"].items():
            at = S.epoch(verdict.get("at"))
            if at is not None and start <= at <= now:
                rows.append((at, fam["id"], int(n), verdict))
    return sorted(rows, key=lambda row: row[:3])


def _faulted(verdict: Mapping[str, Any]) -> str | None:
    """The program fault a version's verdict ended in (`PROGRAM_FAULTS`), None for one the bar judged."""
    fails = [str(x) for x in verdict.get("fails") or []] if isinstance(verdict.get("fails"), list) else []
    return fails[0] if len(fails) == 1 and fails[0] in PROGRAM_FAULTS else None


def _dq_check(f: Mapping[str, Any], now: float, since: float | None, kept: Any = None) -> dict[str, Any]:
    """`elane_dq` (the module docstring). Pure. `since`: the running release's first start (evidence counts from it);
    `kept`: when it first stood under the running release (`stall.json` `elane.dq`: {stood_at}), which HOLDS it; the
    answer's `keep` is what the next run keeps."""
    start, span = _since(now, DQ_HOURS, since)
    rows, basis = _scored(f, start, now), "window"
    if len(rows) < DQ_MIN_SCORED:
        # THE WINDOW'S EDGE: fewer than the minimum fall in the six hours. The last `DQ_MIN_SCORED` scored since the
        # running release started are judged instead (inside `LOOKBACK_HOURS`); under that many, the lane is judged
        # EARLY, and only once `DQ_EARLY_FAULTED` of them could not be judged.
        start, span = _since(now, LOOKBACK_HOURS, since)
        older = _scored(f, start, now)
        rows, basis = (older[-DQ_MIN_SCORED:], "last_scored") if len(older) >= DQ_MIN_SCORED else (older, "early")
    scored, by_code, classes, examples, firsts = len(rows), {c: 0 for c in PROGRAM_FAULTS}, {}, [], []
    families: dict[str, int] = {}
    for at, fid, n, verdict in rows:
        fault = _faulted(verdict)
        if fault is None:
            continue
        by_code[fault] += 1
        _bump(families, fid)
        firsts.append(at)
        if fault == "DQ":
            name = dq_class(verdict.get("why"))
            _bump(classes, name)
            if len(examples) < 6:
                examples.append({"family": fid, "version": n, "error": name, "line": dq_line(verdict.get("why"))})
    faulted = sum(by_code.values())
    first = rows[0][0] if rows and basis == "last_scored" else start
    numbers: dict[str, Any] = {
        "scored": scored, "faulted": faulted, "disqualified": by_code["DQ"], "load_refused": by_code["LOAD"],
        "run_failed": by_code["RUN"], "share": None if not scored else round(faulted / scored, 2), "families": len(families),
        "retired_stalled": sum(1 for at, what in f.get("retired") or [] if what == "stalled" and first <= at <= now),
        "hours": round((now - first) / 3600.0, 1), "min_scored": DQ_MIN_SCORED, "basis": basis}
    spread = len(families) >= DQ_MIN_FAMILIES
    enough = basis != "early" or (faulted >= DQ_EARLY_FAULTED and spread)
    most = enough and faulted > DQ_SHARE * scored and spread
    # ONCE IT STOOD UNDER A RELEASE IT HOLDS until versions scored AFTER it stood are judged by the bar in
    # `DQ_MIN_FAMILIES` families (the generators write programs that run), or the release changes (the record is then
    # dropped: `release_since`). Else the window slid past a fault nothing fixed, or one family's bar fails beside the
    # retired families' versions read "half", and the cause cleared and stood again by itself.
    stood = _num(kept.get("stood_at")) if isinstance(kept, Mapping) else None
    stood = stood if stood is not None and 0 < stood <= now else None
    proven = ({fid for at, fid, _, verdict in _scored(f, stood, now) if at > stood and _faulted(verdict) is None}
              if stood is not None else set())
    held = stood is not None and len(proven) < DQ_MIN_FAMILIES
    stalled = most or held
    keep = {"dq": {"stood_at": stood if held else now} if stalled else None}
    if held:
        numbers.update(standing_since=S.iso(stood), bar_families_since=len(proven))
    if not enough and not held:
        return {**_not_judged(f"{scored} equity versions were scored in {span} (at least {DQ_MIN_SCORED} are needed, or "
                              f"{DQ_EARLY_FAULTED} of {DQ_MIN_FAMILIES} families that could not be judged)", numbers),
                "keep": keep}
    # THE CLASS IS NAMED only when one is more than half of the disqualifications; else the classes that tie are.
    top = _top(classes, 4)
    one_class = bool(top) and 2 * top[0][1] > by_code["DQ"]
    name = top[0][0] if one_class and top[0][0] != UNNAMED else None
    tied = sorted(k for k, v in classes.items() if top and v == top[0][1] and k != UNNAMED)
    said, read, hint, told = "", "", None, []
    if top:
        numbers.update(top_error=_token(top[0][0]) if one_class else ",".join(_token(k) for k in tied[:3]) or "none",
                       top_error_n=top[0][1])
    if one_class:
        said = (f"The commonest first error: {name or 'none its record names'} ({top[0][1]} of {by_code['DQ']}"
                + ("; then " + ", ".join(f"{k} {v}" for k, v in top[1:3]) if top[1:] else "") + ").")
    elif top:
        said = (f"No one first error is most of the {by_code['DQ']} disqualifications: "
                + ", ".join(f"{'none its record names' if k == UNNAMED else k} {v}" for k, v in top) + ".")
    if name is not None:
        told = _top(refusals_tally(f, first, now)["raises"].get(name, {}), 1)
        if told:
            read = f"The reading rule's commonest sentence for it: {told[0][0]} ({told[0][1]}x)."
        try:  # the contract's own sentence for the class (one fixed sentence a class: rules, nothing a run read)
            from ..swarm.elane_train import DQ_HINTS

            hint = DQ_HINTS.get(name)
        except Exception:  # noqa: BLE001 - the class is named without it
            hint = None
    retired = numbers["retired_stalled"]
    head = {"window": f"{faulted} of the {scored} equity versions scored in {span}",
            "last_scored": (f"{faulted} of the last {scored} equity versions scored (over {_hours(now - first)} h: fewer "
                            f"than {DQ_MIN_SCORED} fall in the last {DQ_HOURS:g} h)"),
            "early": f"{faulted} of the {scored} equity versions scored in {span}"}[basis]
    early = (f"Fewer than {DQ_MIN_SCORED} are scored, and these {faulted} are already most of {DQ_MIN_SCORED}."
             if basis == "early" and most else "")
    hold = ""
    if held and not most:
        hold = (f"It stood at {S.iso(stood)} under the running release and HOLDS until versions scored after that are "
                f"judged by the bar in {DQ_MIN_FAMILIES} families ({len(proven)} so far), or the release changes.")
    one = ""
    if faulted > DQ_SHARE * scored and not spread and not stalled:
        # ONE FAMILY'S BAD PROGRAMS are no fault of the contract: clear, and the family is named (in the receipt and
        # the report only: a check that does not stand reaches no warning and no mail).
        one = (f"They are all of ONE family ({next(iter(families))}): one family's bad programs are no fault of the "
               f"contract (at least {DQ_MIN_FAMILIES} families are needed).")
    # THE OWNER'S STEP names the class when one is most, and what it most often is: the reading rule's own sentence
    # where the records hold one (it is in the sentence above), else the class's fixed short hint.
    named = f", mostly {name}" if name else f" (first errors: {', '.join(tied[:3])})" if tied and not one_class else ""
    short = DQ_SHORT.get(name) if name and not told else None
    step = _cut(f"the equity generators misread the program contract{named}" + (f" ({short})" if short else "")
                + ": fix the text they read (league/equity/EQUITY.md \"Reading ctx\", elane_review.READING_CTX) or the "
                f"static rule that should refuse it, in a release; {REPORT} lists the lines", STEP_CHARS)
    parts = [(f"{head} could not be judged for a fault of their own program ({by_code['DQ']} disqualified, "
              f"{by_code['LOAD']} refused at load, {by_code['RUN']} failed by the decider child): no mechanism was judged "
              "in them" + (f", and {retired} families were retired STALLED" if retired else "") + "."
              if scored else f"No equity version was scored in {span}."), early, hold, said, read, one]
    parts = [part for part in parts if part]
    return {
        "stalled": stalled, "judged": True, "what": " ".join(parts), "numbers": numbers,
        "doing": DOING["elane_dq"], "owner_step": step if stalled else None,
        "onset": (min(firsts) if firsts else stood) if stalled else None, "examples": examples, "hint": hint,
        "mail": _lead(parts, WHAT_CHARS), "parts": parts, "keep": keep}


def _births_check(f: Mapping[str, Any], now: float, since: float | None) -> dict[str, Any]:
    """`elane_births` (the module docstring). Pure. `since`: the running release's first start."""
    start, span = _since(now, BIRTHS_HOURS, since)
    # The passes that asked a model and the equity passes that raised, oldest first.
    asked = sorted([(at, pass_read(p)) for at, p in f.get("passes") or [] if start <= at <= now]
                   + [(at, {"asked": True, "barren": True, "how": "raised", "born": 0, "proposed": 0, "refused": 0,
                            "truncated": False, "skipped": None, "setting": None, "want": 0, "items": []})
                      for at, what in f.get("raised") or [] if what == "births" and start <= at <= now], key=lambda r: r[0])
    skipped: dict[str, int] = {}
    for _, row in asked:
        if row["skipped"]:
            _bump(skipped, row["skipped"])
    asked = [(at, row) for at, row in asked if row["asked"]]
    streak: list[tuple[float, dict[str, Any]]] = []
    for at, row in reversed(asked):
        if not row["barren"]:
            break
        streak.append((at, row))
    born_at = [S.epoch(fam["born_at"]) for fam in f.get("families") or []]
    last_born = max([t for t in born_at if t is not None], default=None)
    hows: dict[str, int] = {}
    classes: dict[str, int] = {}
    named: dict[str, int] = {}
    settings: dict[str, int] = {}
    for _, row in streak:
        _bump(hows, row["how"])
        if row.get("setting"):
            _bump(settings, row["setting"])
        for why in row["items"]:
            _bump(classes, refusal_class(why))
            for symbol in foreign_symbols(why):
                _bump(named, symbol)
    numbers: dict[str, Any] = {
        "barren_passes": len(streak), "asked_passes": len(asked), "born": sum(row["born"] for _, row in asked),
        "proposed": sum(row["proposed"] for _, row in streak), "refused": sum(row["refused"] for _, row in streak),
        **{f"passes_{how}": hows.get(how, 0) for how in BARREN},
        **{f"skipped_{_token(k)}": v for k, v in sorted(skipped.items())},
        "last_equity_birth_at": None if last_born is None else S.iso(last_born), "hours": round((now - start) / 3600.0, 1),
        "min_passes": BIRTHS_PASSES}
    if len(asked) < BIRTHS_PASSES:
        return _not_judged(f"{len(asked)} equity passes asked a model in {span} (at least {BIRTHS_PASSES} are needed)", numbers)
    top = _top(classes, 3)
    main = max(hows, key=lambda k: (hows[k], -BARREN.index(k))) if hows else None
    # A SETTING every route refused the request for: named when every pass of the row that got no answer names the one.
    setting = next((k for k, n in settings.items() if main == "failed" and n == hows.get("failed")), None)
    kind = SETTING if setting else top[0][0] if main == "refused" and top else main
    numbers.update(kind=_token(kind), top_refusal=_token(top[0][0]) if top else "none", top_refusal_n=top[0][1] if top else 0,
                   setting=_token(setting) if setting else "none")
    stalled = len(streak) >= BIRTHS_PASSES
    symbols = ", ".join(f"{s} {n}x" for s, n in _top(named, 4))
    reasons = "; ".join(f"{REFUSAL_WORDS[k]} ({n})" for k, n in top)
    want = max([row["want"] for _, row in streak], default=0)
    # The owner's step only once the lanes had their hours to correct themselves, and only for a way a setting clears;
    # at once for a setting every route refuses the request for (nothing the lanes do corrects it).
    dry = stalled and (now - (last_born if last_born is not None else streak[-1][0])) >= BIRTHS_OWNER_HOURS * 3600.0
    lever = BIRTH_LEVERS.get(str(kind)) if dry or (stalled and kind in BIRTH_LEVERS_AT_ONCE) else None
    limit = _output_limit()
    parts = ([f"The equity lanes' last {len(streak)} passes that asked a model bore no family"
              + (f" (each wanted up to {want})" if want else "") + f": {hows.get('refused', 0)} had every proposal "
              f"refused, {hows.get('empty', 0)} proposed none, {hows.get('truncated', 0)} were cut short, "
              f"{hows.get('failed', 0)} got no answer, {hows.get('raised', 0)} raised.",
              f"Every route refused the request before it was sent: {SETTINGS[setting]}." if setting else "",
              f"The commonest refusals: {reasons}." if reasons else "",
              f"Symbols the code knows and elane.universe does not hold, named most: {symbols}." if symbols else ""]
             if streak else
             [f"The equity lanes' latest pass that asked a model bore a family ({len(asked)} asked in {span})."])
    parts = [part for part in parts if part]
    return {
        "stalled": stalled, "judged": True, "what": " ".join(parts), "numbers": numbers,
        "doing": DOING["elane_births"] + ("" if lever or not stalled else
                                          (f" After {BIRTHS_OWNER_HOURS:g} h with no equity birth this is your step when a "
                                           "setting clears it.")),
        "owner_step": _cut(f"no equity family was born for "
                           f"{_hours(now - (last_born if last_born is not None else streak[-1][0]))} h while {len(streak)} "
                           "passes asked for one: "
                           + lever.format(named=f" ({symbols})" if symbols else "", setting=SETTINGS.get(str(setting), ""),
                                          limit="" if limit is None else f" (at most {limit}: the model provider's own "
                                                                         "output limit)"), STEP_CHARS) if lever else None,
        "onset": (last_born if last_born is not None else streak[-1][0]) if stalled else None,
        "mail": _lead(parts, WHAT_CHARS), "parts": parts}


def _work(f: Mapping[str, Any], start: float, now: float) -> dict[str, Any]:
    """THE TRAIN STEPS DUE in `[start, now]`, from the rounds' events: {due, taken, scored, skipped {pace, usd_day,
    sail_day, other}, lost (those skipped for want of model dollars: `STARVED_KINDS`)}. A step that scored a version is
    taken, whatever was put off after it (its review)."""
    out: dict[str, Any] = {"due": 0, "taken": 0, "scored": 0, "skipped": {**{kind: 0 for kind in STARVED_KINDS}, OTHER: 0}}
    for at, payload in f.get("rounds") or []:
        if not start <= at <= now:
            continue
        for step in payload.get("steps") or []:
            read = step_read(step)
            out["due"] += 1
            if read["scored"] or read["skipped"] is None:
                out["taken"] += 1
                out["scored"] += int(read["scored"])
            else:
                out["skipped"][read["skipped"] if read["skipped"] in STARVED_KINDS else OTHER] += 1
    out["lost"] = sum(out["skipped"][kind] for kind in STARVED_KINDS)
    return out


def _lever(kind: str, held: Mapping[str, Any] | None, c: Mapping[str, Any], *,
           now_held: bool = True) -> tuple[str, list[str]]:
    """WHICH OF E2'S LINES BINDS, and the owner's lever for it, from the figures the check holds (`_held`: the hourly
    pace, the day's line, what was booked against each; `lanes`' settings): (what binds, the lever's sentences: the
    lever, the budget's line where it binds first, the command that sets the lever; [] for no lever). The hourly pace
    is `elane.e2.pace_share` of the Sail model line; the day's line is the smaller of `elane.e2.usd_day` and 24 hours
    at that pace, so `usd_day` is the lever only when it is the smaller: at the release's settings the day is 24 hourly
    paces and `usd_day` does not bind. Where the settings' budget block is the floor (no usable budget.json) the model
    line itself is the floor's, and the sentence after the lever says the budget's line binds before the share (before
    the command, so a cut never keeps the command and loses it). The House's Sail day is no lever of E2's. `now_held`:
    the kind holds E2 at this moment (what was booked is then said against it)."""
    share, usd_day = _num(c.get("pace_share")), _num(c.get("usd_day"))
    floor = ["The budget holds the Sail model line at its floor (no usable budget.json): the budget's line binds before "
             "the share does."] if c.get("budget_floor") else []
    pace = ["The lever is elane.e2.pace_share.", *floor,
            "Set it with python3 set_swarm.py elane.e2.pace_share=<lines> --apply."]
    if kind == "pace":
        what = "E2's hourly pace binds"
        if held is not None and share is not None:
            booked = f"{_usd(held['spent_last_hour_usd'])} booked in the last hour against " if now_held else ""
            what += (f" ({booked}a pace of {_usd(held['limit_usd_hour'])} an hour: elane.e2.pace_share {share:g} of the "
                     "Sail model line)")
        return what, pace
    if kind == "usd_day":
        what = "E2's day's line binds"
        if held is None or usd_day is None:
            return what, []
        what += (f" ({_usd(held['spent_today_usd'])} booked this UTC day against a line of {_usd(held['day_line_usd'])})"
                 if now_held else f" (a line of {_usd(held['day_line_usd'])} a UTC day)")
        if usd_day <= held["limit_usd_hour"] * 24.0:
            return what, [f"The day's line is elane.e2.usd_day ({_usd(usd_day)}), under 24 hours at the hourly pace: the "
                          "lever is elane.e2.usd_day.",
                          "Set it with python3 set_swarm.py elane.e2.usd_day=<dollars> --apply."]
        return what, [f"The day's line is 24 hours at the hourly pace, under elane.e2.usd_day ({_usd(usd_day)}), which "
                      "does not bind: the lever is elane.e2.pace_share.", *pace[1:]]
    if kind == "sail_day":
        why = (_sail_words(held["text"]) if held is not None and held.get("kind") == "sail_day"
               else "the Sail guard's line or its brake")
        return f"the House's Sail day holds E2 ({why})", []
    return "E2 may ask no model now", []


def _idle_clock(fresh: float, last_scored: float | None, now: float, started: float | None, beat_age: float | None,
                since: float | None, kept: Any) -> tuple[float, float, dict[str, Any]]:
    """THE IDLE CLOCK, KEPT PER RELEASE (`stall.json` `elane.idle`: {from, down, started, beat_at}): (since when the
    lanes are idle, the seconds of it the swarm was down, what the next run keeps). `fresh`: since when the store says
    the lanes are idle now (the later of the last version scored and when the work became owed).

    WHAT WAS KEPT STANDS while no version was scored after it (work was owed at every run between: a run that finds
    none owed drops the record), so the clock neither starts again at a restart nor moves with the lookback's edge or
    with which family is the oldest still in research. THE TIME THE SWARM WAS DOWN is taken off: at a restart seen
    since the last run (the heartbeat's `started_at` moved), from the heartbeat as that run read it to the new start
    (the old swarm may have run on for up to one run's interval: counted as down, never as idle); with nothing kept,
    everything before the running swarm's own start (`since`, the release's first start, with no heartbeat to read)."""
    k = kept if isinstance(kept, Mapping) else {}
    was = _num(k.get("from"))
    seen, read = None, None
    if was is not None and 0 < was <= now and (last_scored is None or last_scored <= was + 1.0):
        idle_from, down = was, max(0.0, _num(k.get("down")) or 0.0)
        seen, read = _num(k.get("started")), _num(k.get("beat_at"))
        if started is not None and seen is not None and started > seen + 1.0:  # a restart since the last run
            down += max(0.0, started - max(idle_from, seen if read is None else read))
    else:
        idle_from = fresh
        edge = started if started is not None else since
        down = max(0.0, edge - idle_from) if edge is not None else 0.0
    down = min(down, max(0.0, now - idle_from))
    return idle_from, down, {"from": idle_from, "down": round(down, 1), "started": started if started is not None else seen,
                             "beat_at": read if beat_age is None else now - beat_age}


def _holds(f: Mapping[str, Any], passes: Sequence[tuple[float, Mapping[str, Any]]], now: float, kept: Any,
           held_now: str | None) -> tuple[float, str] | None:
    """THE LAST HOLD OF E2'S SEEN in the last `IDLE_HOURS`: (when, its kind), None for none. E2 held now; the last run
    of the job that read it held (`stall.json` `elane.held`: a hold between two rounds leaves no event, since no
    round starts while every family needs a model E2 may not ask); a Train step or an equity pass skipped for want of
    model dollars (`STARVED_KINDS`). A lane with none of them was FREE TO ASK for the whole of those hours."""
    edge = now - IDLE_HOURS * 3600.0
    seen: list[tuple[float, str]] = [(now, held_now)] if held_now else []
    k = kept if isinstance(kept, Mapping) else {}
    at = _num(k.get("at"))
    if at is not None and edge <= at <= now and isinstance(k.get("kind"), str):
        seen.append((at, k["kind"]))
    for at, payload in f.get("rounds") or []:
        if edge <= at <= now:
            seen += [(at, kind) for kind in (step_read(step)["skipped"] for step in payload.get("steps") or [])
                     if kind in STARVED_KINDS]
    seen += [(at, row["skipped"]) for at, row in passes if edge <= at <= now and row["skipped"] in STARVED_KINDS]
    return max(seen, key=lambda row: row[0]) if seen else None


def _idle_check(f: Mapping[str, Any], now: float, started: float | None, c: Mapping[str, Any],
                beat_age: float | None = None, since: float | None = None, kept: Any = None) -> dict[str, Any]:
    """`elane_idle` (the module docstring): A BROKEN LANE, and only that. Pure. `started`: the running swarm's own
    start; `since`: the running release's first start (the Train steps' window starts no earlier; `started` when none
    is kept); `beat_age`: the age of the swarm's heartbeat in seconds, when known; `kept`: what the job keeps under
    the release (`idle`, the clock; `held`, the last run that read E2 held). The answer's `keep` is what the next run
    keeps."""
    since = started if since is None else since
    kept = kept if isinstance(kept, Mapping) else {}
    fams = f.get("families") or []
    researching = [fam for fam in fams if fam["alive"] and fam["status"] == "researching"]
    passes = [(at, pass_read(p)) for at, p in f.get("passes") or []]
    last = passes[-1][1] if passes else None
    births_at = (f.get("kv") or {}).get(BIRTHS_AT_KEY)
    every = float(c.get("births_every_seconds") or 7200.0)
    overdue = births_at is not None and now - births_at > max(IDLE_HOURS * 3600.0, 2.0 * every)
    # Births are wanted when the latest pass was held back, left births unfilled or bore none. A pass that may ask no
    # model is not started and leaves no event: it shows as overdue.
    unfilled = lambda row: row["skipped"] in STARVED_KINDS or row["short"] > 0 or row["barren"]  # noqa: E731
    wanted = bool(last and unfilled(last))
    scored_at = [S.epoch(v.get("at")) for fam in fams for v in fam["versions"].values()]
    scored_at = [t for t in scored_at if t is not None and t <= now]
    last_scored = max(scored_at, default=None)
    scored_today = sum(1 for t in scored_at if t >= now - now % 86400.0)
    # SINCE WHEN WORK IS OWED: the oldest family still in research was born; the first of the latest passes that left
    # births unfilled; the last time the pass ran, when it is overdue. The lanes are idle from the later of that and
    # the last version scored: a family born after a quiet spell is not idle on a score of days ago.
    owed_at = [S.epoch(fam["born_at"]) for fam in researching]
    if wanted:
        first = passes[-1][0]
        for at, row in reversed(passes):
            if not unfilled(row):
                break
            first = at
        owed_at.append(first)
    if overdue:
        owed_at.append(births_at)
    first_owed = min([t for t in owed_at if t is not None], default=None)
    fresh = first_owed if last_scored is None or first_owed is None else max(last_scored, first_owed)
    held = f.get("held") if isinstance(f.get("held"), Mapping) else None
    held_now = held["kind"] if held is not None else None
    # THE TRAIN STEPS DUE in the last `IDLE_HOURS` (since the running release started), taken and skipped: what E2's
    # lines cost, said whether or not the cause stands (it never stands for them).
    edge, span = _since(now, IDLE_HOURS, since)
    work = _work(f, edge, now)
    numbers: dict[str, Any] = {"researching": len(researching), "births_wanted": wanted, "pass_overdue": overdue,
                               "last_scored_at": None if last_scored is None else S.iso(last_scored), "min_hours": IDLE_HOURS,
                               "scored_today": scored_today, "steps_due": work["due"], "steps_taken": work["taken"],
                               "steps_skipped": work["lost"],
                               **{f"skipped_{kind}": work["skipped"][kind] for kind in STARVED_KINDS}}
    if held is not None:
        numbers.update(held_now=held_now or "none", pace_usd_hour=round(held["limit_usd_hour"], 4),
                       spent_last_hour_usd=round(held["spent_last_hour_usd"], 4), day_line_usd=round(held["day_line_usd"], 2),
                       spent_today_usd=round(held["spent_today_usd"], 2))
    if not researching and not wanted and not overdue:
        return {**_not_judged("no equity family is in Train research and no equity birth is wanted", numbers),
                "keep": {"idle": None}}  # nothing owed: the idle clock is dropped
    if fresh is None:
        return _not_judged("nothing says since when the equity lanes owe work", numbers)
    if beat_age is not None and beat_age > BEAT_STALE_SECONDS:
        return _not_judged(f"the swarm is not running (its heartbeat is {beat_age / 60.0:.0f} min old): the House restarts "
                           "a swarm that stops, and the options lanes' causes say so", numbers)
    idle_from, down, clock = _idle_clock(fresh, last_scored, now, started, beat_age, since, kept.get("idle"))
    idle = (now - idle_from) - down
    seen = _holds(f, passes, now, kept.get("held"), held_now)
    keep: dict[str, Any] = {"idle": clock, **({"held": {"at": now, "kind": held_now}} if held_now else {})}
    numbers.update(idle_hours=round(idle / 3600.0, 1), down_hours=round(down / 3600.0, 1), basis="idle_hours",
                   held_lately=seen is not None)
    owed = ((f"{len(researching)} families are in Train research" if researching else "no family is in Train research")
            + (" and births are wanted" if wanted else " and the equity pass is overdue" if overdue else ""))
    # WHAT E2'S LINES COST, in sentences: the steps due, taken and skipped by reason; whether E2 is held now, or where
    # it was held; that this is no stall; the lever. Said by every reading that does not stand, when there is any.
    by = ", ".join(f"{STARVED_WORDS[k]} {work['skipped'][k]}" for k in STARVED_KINDS if work["skipped"][k])
    lost = ([f"Of the {work['due']} equity Train steps due in {span}, {work['taken']} were taken and {work['lost']} were "
             f"skipped because E2 might ask no model ({by}); {work['scored']} versions were scored."] if work["lost"] else
            [f"All {work['due']} equity Train steps due in {span} were taken; {work['scored']} versions were scored."]
            if work["due"] else [])
    most = max(STARVED_KINDS, key=lambda k: (work["skipped"][k], -STARVED_KINDS.index(k))) if work["lost"] else None
    line = held_now or most or (seen[1] if seen is not None else None)
    binds, lever = _lever(line, held, c, now_held=bool(held_now)) if line else ("", [])
    # Whether E2 is held now, by which line; else which line held it, and how long ago a hold was last seen.
    hold = (f"{binds}, so no model is asked." if held_now else
            f"{binds}; E2 may ask a model now and was last held {_hours(now - seen[0])} h ago." if seen is not None else "")
    exact = last_scored is not None and abs(idle_from - last_scored) < 1.0  # the clock starts at a version scored
    spent = (f"E2's model dollars for the UTC day are spent ({_usd(held['spent_today_usd'])} of a day's line of "
             f"{_usd(held['day_line_usd'])})" if held is not None and held_now == "usd_day" else "")
    if idle < IDLE_HOURS * 3600.0:
        if down > 0:
            # A swarm that was down is not idle on the hours it was down: under `IDLE_HOURS` of running time, not judged.
            ran = started is not None and abs((now - started) - idle) < 1.0
            return {**_not_judged((f"the swarm started {_hours(now - started)} h ago" if ran else
                                   f"nothing was scored for {_hours(now - idle_from)} h, {_hours(down)} h of them with the "
                                   "swarm down") + f" (the lanes are judged idle after {IDLE_HOURS:g} h with nothing "
                                   "scored)", numbers), "keep": keep}
        told = bool(work["lost"] or held_now)
        if spent and scored_today:
            parts = [f"{spent} and {scored_today} equity versions were scored since 00:00 UTC: no stall. E2 asks again at "
                     "00:00 UTC.", *lost, *lever]
        else:
            parts = [(f"The last equity version was scored {_hours(idle)} h ago." if exact else
                      f"The equity lanes have owed work for {_hours(idle)} h and scored no version since.")
                     + f" The lanes are idle after {IDLE_HOURS:g} h with nothing scored.",
                     *([*lost, hold[:1].upper() + hold[1:], NO_STALL, *lever] if told else [])]
        return {"stalled": False, "judged": True, "what": " ".join(parts),
                "numbers": {**numbers, **({"kind": line} if told and line else {})},
                "doing": DOING["starved" if told else "broken"], "owner_step": None, "onset": None, "keep": keep}
    # WHY, since the lanes went idle: the Train rounds' own steps, the rounds that raised, the families waiting.
    tally = {"rounds": 0, "house": 0, "unanswered": 0, "refused": 0, "errors": 0, "raised": 0, "passes": 0}
    houses: dict[str, int] = {}
    for at, payload in f.get("rounds") or []:
        if at < idle_from:
            continue
        tally["rounds"] += 1
        for step in payload.get("steps") or []:
            read = step_read(step)
            if read["house"]:
                tally["house"] += 1
                _bump(houses, read["house"])
            tally["unanswered"] += int(read["unanswered"])
            tally["refused"] += int(read["refused"] is not None)
            tally["errors"] += int(read["error"])
    tally["raised"] = sum(1 for at, _ in f.get("raised") or [] if at >= idle_from)
    tally["passes"] = sum(1 for at, row in passes if at >= idle_from and row["barren"])
    waiting = [fam for fam in researching if any(t > now for t in fam["waits"].values())]
    backed = 0  # the most failures of the House's one after another a family now waiting out its backoff has had
    for fam in waiting:
        for name, until in fam["waits"].items():
            if until > now and name.startswith("infra:"):
                _bump(houses, name.split(":", 1)[1])
                backed = max(backed, int(fam.get("house_fails") or 0))
    train_at = (f.get("kv") or {}).get(TRAIN_AT_KEY)
    numbers.update(train_rounds=tally["rounds"], house_failures=tally["house"], unanswered=tally["unanswered"],
                   refused_answers=tally["refused"], step_errors=tally["errors"], rounds_raised=tally["raised"],
                   barren_passes=tally["passes"],
                   families_waiting=len(waiting),
                   train_round_age_min=None if train_at is None else round(max(0.0, now - train_at) / 60.0, 1))
    # BROKEN IS JUDGED FIRST, by the lane's own record: rounds that raised, steps that failed on the House's side (or a
    # family waiting out a House backoff after as many failures), steps that failed with an error of their own. It
    # stands whatever E2's lines hold: a lane whose every Train run fails scores nothing at any pace.
    fails = {"raised": tally["raised"], "house": max(tally["house"], backed), "errors": tally["errors"]}
    broken = next((kind for kind in BROKEN_KINDS if fails[kind] >= BROKEN_MIN_FAILS), None)
    # "At least" unless the clock starts at a version scored: since when work is owed is read inside the lookback.
    lead = (f"No equity version was scored on Train for {'' if exact else 'at least '}{_hours(idle)} h"
            + (f" of the swarm's running time (it was down {_hours(down)} h more)" if down > 0 else "") + f" while {owed}.")
    # What the lane's own record shows since it went idle, in words.
    said = [f"{tally['rounds']} Train rounds ran"]
    if tally["raised"]:
        said.append(f"{tally['raised']} rounds raised")
    if tally["house"] or houses:
        said.append(f"{tally['house']} steps failed on the House's side ("
                    + (", ".join(f"{k} {n}" for k, n in _top(houses, 4)) or "kind not named") + ")")
    if tally["unanswered"]:
        said.append(f"{tally['unanswered']} questions got no answer from a model route")
    if tally["refused"]:
        said.append(f"{tally['refused']} programs were refused before a run (see elane_refused)")
    if tally["errors"]:
        said.append(f"{tally['errors']} steps failed with an error of their own")
    if waiting:
        said.append(f"{len(waiting)} of {len(researching)} families wait out a backoff")
    shown = len(said) > 1  # anything but how many rounds ran
    if train_at is not None:
        said.append(f"the Train round last started {max(0.0, now - train_at) / 60.0:.0f} min ago")
    if broken is None and seen is not None:
        # STARVED BY A SETTING, not broken: E2 is held, or was inside these hours, and the record shows no failing
        # lane. The captain's chosen budget at work: judged CLEAR, never standing, never mailed; the cost is said,
        # and so is what the steps taken show that is under `BROKEN_MIN_FAILS` or no failure of the lane's (questions
        # no route answered, programs a static rule refused).
        if spent and scored_today:
            head = [f"{spent} and {scored_today} equity versions were scored since 00:00 UTC: no stall. E2 asks again at "
                    "00:00 UTC."]
        else:
            head = [lead, f"STARVED BY A SETTING, not broken: {hold}"]
        parts = [*head, *(["Since the lanes went idle " + "; ".join(said) + "."] if shown else []), *lost,
                 *([] if spent and scored_today else [NO_STALL]), *lever]
        return {"stalled": False, "judged": True, "what": " ".join(parts),
                "numbers": {**numbers, "kind": line, "starved": True}, "doing": DOING["starved"], "owner_step": None,
                "onset": None, "keep": keep}
    # With no family in research the work owed is the equity pass's: barren passes are `elane_births`' to explain,
    # before anything the Train rounds of families now gone left behind (programs refused, steps that failed).
    kind = broken or ("raised" if tally["raised"] else "house" if tally["house"] or houses else
                      "unanswered" if tally["unanswered"] or any("unanswered" in fam["waits"] for fam in waiting) else
                      "barren" if not researching and tally["passes"] else
                      "refused" if tally["refused"] else "errors" if tally["errors"] else
                      "silent" if tally["rounds"] else "no_round")
    may = "E2 may ask a model now" if held is not None else "whether E2 may ask a model now could not be read"
    pace: list[str] = []
    if held_now:  # BROKEN by its record while E2 is also held: the line is said second, and is not the fault
        why = "BROKEN, whatever E2's own lines hold: " + "; ".join(said) + "."
        pace = [f"E2 is also held now: {binds}.", "That is its setting at work: a broken lane scores nothing at any pace."]
    elif kind == "barren":
        why = (f"Not starved ({may}): {tally['passes']} equity passes asked a model and bore no family, so there is none "
               "to score (see elane_births).")
    else:
        why = f"BROKEN, not starved: {may} and " + "; ".join(said) + "."
    numbers["kind"] = kind
    owner = None
    if kind in IDLE_OWNER_KINDS:
        owner = {"raised": "the equity lanes' rounds raise (the swarm log's \"elane failed\" and \"elane_train failed\" lines)",
                 "house": ("the equity lanes' Train runs fail on the House's side: check the equity_data job's receipt and the "
                           "swarm's equity-decider.log"),
                 "errors": "the equity lanes' Train steps fail with errors (the swarm log's elane_train lines)",
                 "silent": "the equity lanes' Train rounds run and judge nothing (the swarm log's elane_train lines)",
                 "no_round": ("the equity lanes owe work, may ask a model and start no round (the swarm log's elane_train "
                              "lines)"),
                 }[kind] + f"; it needs a fix, in a release or on the box ({REPORT} prints each family's state)"
    parts = [lead, why, *pace]
    return {
        "stalled": True, "judged": True, "what": " ".join(parts),
        "numbers": numbers, "owner_step": owner, "onset": idle_from,
        "doing": DOING["elane_births" if kind == "barren" else "broken"],
        "mail": _lead(parts, WHAT_CHARS), "parts": parts, "keep": keep}


def _sail_words(text: Any) -> str:
    """The House's Sail day's reason in closed words (`elane_yield.sail_day`: its text holds the guard's own reason)."""
    text = str(text or "")
    for mark, words in (("is closed: the Sail guard is braked", "the Sail guard is braked"),
                        ("holds new research", "the Sail guard holds new research at the day's line"),
                        ("has no room for an equity question",
                         "the day's Sail dollars are within a dollar of the guard's line"),
                        ("is unknown", "the Sail guard has no fresh reading"),
                        ("could not be read", "the guard's record could not be read")):
        if mark in text:
            return words
    return "its reason is not one this reader knows"


def _refused_check(f: Mapping[str, Any], now: float, since: float | None) -> dict[str, Any]:
    """`elane_refused` (the module docstring). Pure. `since`: the running release's first start."""
    start, span = _since(now, REFUSED_HOURS, since)
    rows, basis = _answers(f, start, now), "window"
    if len(rows) < REFUSED_MIN_ANSWERS:
        # THE WINDOW'S EDGE, as `elane_dq`: fewer than the minimum fall in the six hours (a slow lane writes one program
        # an hour). The last `REFUSED_MIN_ANSWERS` written since the running release started are judged instead (inside
        # `LOOKBACK_HOURS`); under that many, the lane is judged EARLY, once `REFUSED_EARLY` were refused by one rule.
        start, span = _since(now, LOOKBACK_HOURS, since)
        older = _answers(f, start, now)
        rows, basis = ((older[-REFUSED_MIN_ANSWERS:], "last_written") if len(older) >= REFUSED_MIN_ANSWERS else
                       (older, "early"))
    tally = refusals_tally(f, start, now, rows)
    answers, refused = tally["answers"], tally["refused"]
    first = rows[0][0] if rows and basis == "last_written" else start
    rules = {k: v for k, v in tally["by_rule"].items() if k not in NOT_RULES}
    top = _top(rules, 1)
    rule, n = top[0] if top else ("none", 0)
    numbers: dict[str, Any] = {"answers": answers, "stored": tally["stored"], "refused": refused,
                               **{f"refused_{_token(k)}": v for k, v in sorted(tally["by_rule"].items())},
                               "hours": round((now - first) / 3600.0, 1), "min_answers": REFUSED_MIN_ANSWERS, "basis": basis}
    if basis == "early" and n < REFUSED_EARLY:
        return _not_judged(f"the equity generators wrote {answers} programs in {span} (at least {REFUSED_MIN_ANSWERS} are "
                           f"needed, or {REFUSED_EARLY} refused by one rule)", numbers)
    numbers.update(top_rule=_token(rule), top_rule_n=n, share=round(n / answers, 2))
    stalled = n > REFUSED_SHARE * answers
    said = _top(tally["sentences"].get(rule, {}), 2)
    words = RULE_WORDS.get(rule, f"the {rule} rule")
    by_rule = ", ".join(f"{RULE_WORDS.get(k, 'the ' + k + ' rule')} {v}" for k, v in _top(tally["by_rule"], 5))
    head = {"window": f"{n} of the {answers} programs the equity generators wrote in {span}",
            "last_written": (f"{n} of the last {answers} programs the equity generators wrote (over {_hours(now - first)} h: "
                             f"fewer than {REFUSED_MIN_ANSWERS} fall in the last {REFUSED_HOURS:g} h)"),
            "early": f"{n} of the {answers} programs the equity generators wrote in {span}"}[basis]
    parts = ([f"{head} were refused before a run by ONE static rule, {words} ({refused} refused in all: {by_rule}).",
              (f"Fewer than {REFUSED_MIN_ANSWERS} are written, and these {n} are already most of {REFUSED_MIN_ANSWERS}."
               if basis == "early" else ""),
              "Its commonest sentence: " + "; then ".join(f"{s} ({k}x)" for s, k in said) + "." if said else ""]
             if top else
             [f"None of the {answers} programs the equity generators wrote in {span} was refused by a static rule."])
    parts = [part for part in parts if part]
    return {
        "stalled": stalled, "judged": True, "what": " ".join(parts),
        "numbers": numbers, "doing": DOING["elane_refused"],
        "owner_step": (f"the equity generators are not being taught {words}: teach it where they read it "
                       "(league/equity/EQUITY.md, the researcher's system prompt, elane_review.READING_CTX), in a "
                       f"release; {REPORT} lists the refusals") if stalled else None,
        "onset": None, "examples": tally["examples"], "mail": _lead(parts, WHAT_CHARS), "parts": parts}


def judge(f: Mapping[str, Any], *, now: float, started: float | None = None, beat_age: float | None = None,
          settings: Mapping[str, Any] | None = None, since: float | None = None,
          kept: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """The four checks over the store's facts (`facts`), each {stalled, judged, what, numbers, doing, owner_step, onset}
    and, where the next run needs something kept, `keep` ({a key of `KEPT`: its value, None to drop it}). Pure.
    `since`: the running release's first start (evidence counts from it; `started` when none is kept); `started`: the
    running swarm's own start; `beat_age`: its heartbeat's age in seconds; `settings`: `lanes`' third value; `kept`:
    what the stall job keeps under the running release (`KEPT`)."""
    since = started if since is None else since
    kept = kept if isinstance(kept, Mapping) else {}
    found = {"elane_dq": _dq_check(f, now, since, kept.get("dq")), "elane_births": _births_check(f, now, since),
             "elane_idle": _idle_check(f, now, started, settings or {}, beat_age, since, kept),
             "elane_refused": _refused_check(f, now, since)}
    return {cause: _judged(check) if check["judged"] else check for cause, check in found.items()}


def heartbeat(root: str | Path, now: float) -> tuple[float | None, float | None]:
    """(when the running swarm started, the age of its heartbeat in seconds) from `<state>/swarm.heartbeat`
    (`started_at`, `at`); a None for what the file does not say."""
    beat = read_json(Path(root) / HEARTBEAT, None)
    beat = beat if isinstance(beat, Mapping) else {}
    started, at = _num(beat.get("started_at")), _num(beat.get("at"))
    return (started if started is not None and 0 < started <= now else None,
            None if at is None else max(0.0, now - at))


def release_since(kept: Any, root: str | Path, now: float) -> dict[str, Any]:
    """SINCE WHEN THE RUNNING RELEASE HAS RUN, as the stall job keeps it in its state file (`STATE_FILE`'s
    `STATE_KEEP`): {release, since} and, with them, what was kept under that release (`KEPT`). `release` is the
    heartbeat's (the release directory the running swarm was started from, league/swarm/loop.py) and `since` the
    `started_at` first seen under it: KEPT while the heartbeat names the same release, so a restart that fixes nothing
    (the watchdog's, a settings apply) resets no evidence and none of the clocks kept under it; replaced when it names
    another, so what the generators did under an earlier release is not held against this one (and `KEPT` is dropped:
    a release that fixes a fault clears what stood for it). `kept`: what the last run kept. A heartbeat that names no
    release counts from the running swarm's own start, as before the record was kept (what was kept stands for that
    one run of the swarm); with no heartbeat to read, what was kept stands. Never raises."""
    try:
        kept = kept if isinstance(kept, Mapping) else {}
        old = _num(kept.get("since"))
        old = old if old is not None and 0 < old <= now else None
        named = kept.get("release") if isinstance(kept.get("release"), str) else None
        beat = read_json(Path(root) / HEARTBEAT, None)
        beat = beat if isinstance(beat, Mapping) else {}
        release = beat.get("release") if isinstance(beat.get("release"), str) and beat.get("release") else None
        started = heartbeat(root, now)[0]
        if release is not None and named == release and old is not None:
            out, same = {"release": release, "since": old if started is None else min(old, started)}, True
        elif release is None and started is None:
            out, same = {"release": named, "since": old}, True
        else:
            out = {"release": release, "since": started}
            same = release is None and named is None and old is not None and started is not None and abs(started - old) < 1.0
        if same:
            out.update({key: dict(kept[key]) for key in KEPT if isinstance(kept.get(key), Mapping)})
        return out
    except Exception:  # noqa: BLE001 - nothing kept: the evidence counts from the running swarm's start
        return {"release": None, "since": None}


def switched_off(ctx: Any) -> bool:
    """THE OWNER'S SWITCH (`<state>/ops.json` `stall.elane` false; `ctx`: the job's context, or a mapping with its
    `settings`): the four causes are not judged, and the rest of the stall alarm goes on. Absent, they are judged (the
    release ships it so)."""
    settings = ctx.get("settings") if isinstance(ctx, Mapping) else getattr(ctx, "settings", None)
    block = settings.get("stall") if isinstance(settings, Mapping) else None
    return isinstance(block, Mapping) and block.get(SWITCH) is False


def _blind(ctx: Any, kept: Any, now: float, errors: list[str] | None, text: str) -> None:
    """AN ALARM THAT CANNOT SEE SAYS SO (the review of Oct 11: an entry of the receipt's `errors` reached no one).
    `text` (it names the CLASS of what could not be read, never its message) is an entry of the job's `errors` at
    every run, and ONE House warning every `BLIND_WARN_SECONDS` while it lasts: through the job's context
    (`ctx.alert`), its time kept in the job's record (`kept`: `unread`). A call with no record to keep it in (the
    operator's report) warns nobody."""
    if errors is not None:
        errors.append(text)
    try:
        if not isinstance(kept, dict):
            return
        last = _num(kept["unread"].get("warned_at")) if isinstance(kept.get("unread"), Mapping) else None
        if last is not None and 0.0 <= now - last < BLIND_WARN_SECONDS:
            return
        alert = ctx.get("alert") if isinstance(ctx, Mapping) else getattr(ctx, "alert", None)
        if callable(alert):
            alert("warning", _cut(f"stall: the equity lanes' alarm cannot see: {text}. It is said here every "
                                  f"{BLIND_WARN_SECONDS / 3600.0:g} h while it lasts and in the stall receipt's errors at "
                                  f"every run; it needs a fix, in a release or on the box ({REPORT} shows what reads).",
                                  WARN_CHARS))
            kept["unread"] = {"warned_at": now}
    except Exception:  # noqa: BLE001 - the errors entry stands without the warning
        pass


def checks(ctx: Any, root: str | Path, now: float, loaded: Mapping[str, Any] | None, *, paused: bool = False,
           errors: list[str] | None = None, since: float | None = None,
           kept: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """THE STALL JOB'S CALL (league/ops/stall.py `run`): the four causes' checks, from the swarm's store (read-only),
    its heartbeat and its settings as it loads them (`loaded`). `ctx`: the job's context (for the owner's switch,
    `switched_off`, and its House warnings). `paused`: a maintenance pause or a stopped swarm stands. `since`: the
    running release's first start (`release_since`; None: the running swarm's own). `kept`: the job's record under the
    running release (`release_since`'s answer): read for what earlier runs kept (`KEPT`) and LEFT HOLDING what the
    next run needs, for the job to write with its state; nothing is written here. Never raises. LANES THAT CANNOT BE
    READ are "Not judged", an entry of `errors` naming the class (the settings, one of E2's own readers, the store,
    the lane's own reading of whether it may ask a model) and a House warning every `BLIND_WARN_SECONDS` (`_blind`)."""
    try:
        if switched_off(ctx):
            return {cause: _not_judged(f"switched off (ops.json stall.{SWITCH} is false)") for cause in CAUSES}
        on, why, c = lanes(loaded, paused=paused)  # the switch first: lanes that are off cost no read of the store
        if on:
            f = guard.read(Path(root) / SWARM_DB, lambda db: facts(db, now, loaded))
            on, why, c = lanes(loaded, f, paused=paused)
        if not on:
            if c.get("unread"):
                _blind(ctx, kept, now, errors, f"the equity lanes' readers could not be read ({c['unread']}): the four "
                                               "equity causes are not judged")
            return {cause: _not_judged(str(why)) for cause in CAUSES}
        if f.get("held_error"):
            _blind(ctx, kept, now, errors, "the equity lanes' own reading of whether E2 may ask a model could not be read "
                                           f"({f['held_error']}): elane_idle cannot tell a starved lane from a broken one")
        started, beat_age = heartbeat(root, now)
        found = judge(f, now=now, started=started, beat_age=beat_age, settings=c, since=since, kept=kept)
        for check in found.values():  # what the next run needs, into the job's record (None: dropped)
            for key, value in (check.pop("keep", None) or {}).items():
                if not isinstance(kept, dict) or key not in KEPT:
                    continue
                if value is None:
                    kept.pop(key, None)
                else:
                    kept[key] = value
        return found
    except Exception as exc:  # noqa: BLE001 - the stall alarm goes on without the equity lanes' causes
        _blind(ctx, kept, now, errors, f"the equity lanes' health could not be read ({type(exc).__name__})")
        return {cause: _not_judged(f"the equity lanes' records could not be read ({type(exc).__name__})") for cause in CAUSES}


# ---------------------------------------------------------------------------------------------- the funnel
def research_counts(db: Any, start: float, end: float) -> dict[str, Any]:
    """THE EQUITY LANES' RESEARCH FUNNEL in `[start, end)` (the module docstring), each count from the event that is the
    thing itself: the equity passes and the Train rounds' steps (`swarm.elane`), the births (`swarm.born`), E2's spend
    rows; the architect's programs refused at birth from the families' records (the last five a family keeps).
    `train_steps`: the rounds' steps taken and those skipped, by why (`STARVED_KINDS`: E2 might ask no model; `other`)."""
    w = _window(db, start, end)
    passes = {"passes": 0, "asked": 0, "barren": 0, "truncated": 0, "failed": 0, "raised": 0, "proposed": 0, "born": 0,
              "skipped": {}}
    refused: dict[str, Any] = {"total": 0, "by_class": {}}
    for _, payload in w["passes"]:
        row = pass_read(payload)
        passes["passes"] += 1
        passes["asked"] += int(row["asked"])
        passes["barren"] += int(row["barren"])
        passes["truncated"] += int(row["truncated"])
        passes["failed"] += int(row["failed"])
        passes["proposed"] += row["proposed"]
        passes["born"] += row["born"]
        if row["skipped"]:
            _bump(passes["skipped"], _token(row["skipped"]))
        refused["total"] += row["refused"]
        for why in row["items"]:
            _bump(refused["by_class"], refusal_class(why))
    passes["raised"] = sum(1 for _, what in w["raised"] if what == "births")
    answers: dict[str, Any] = {"written": 0, "stored": 0, "refused": 0, "by_rule": {}, "unanswered": 0}
    versions: dict[str, Any] = {"scored": 0, "disqualified": 0, "by_code": {code: 0 for code in BAR_CODES}, "passed_bar": 0,
                                "review_refused": 0, "passed": 0, "house_failures": 0, "rescored": 0}
    rounds = 0
    steps: dict[str, Any] = {"taken": 0, "skipped": {**{kind: 0 for kind in STARVED_KINDS}, OTHER: 0}}
    for _, payload in w["rounds"]:
        rounds += 1
        for step in payload.get("steps") or []:
            read = step_read(step)
            if read["scored"] or read["skipped"] is None:  # as `_work`: a step that scored a version is taken
                steps["taken"] += 1
            else:
                steps["skipped"][read["skipped"] if read["skipped"] in STARVED_KINDS else OTHER] += 1
            if read["answered"]:
                answers["written"] += 1
                answers["stored" if read["refused"] is None else "refused"] += 1
                if read["refused"] is not None:
                    _bump(answers["by_rule"], read["refused"])
            answers["unanswered"] += int(read["unanswered"])
            if read["scored"]:
                versions["scored"] += 1
                versions["passed_bar"] += int(read["passed"])
                for code in read["fails"]:
                    _bump(versions["by_code"], code if _CODE.match(code) else OTHER)
            versions["review_refused"] += int(read["review"] == "refused")
            versions["passed"] += int(read["review"] == "pass")
            versions["house_failures"] += int(read["house"] is not None)
            versions["rescored"] += int(read["rescored"] is not None)
    versions["disqualified"] = versions["by_code"].get("DQ", 0)
    for _, program in w["born"]:
        if program == "v1":  # the architect's program at birth, stored as the family's first version
            answers["written"] += 1
            answers["stored"] += 1
    for fam in e2_families(db):
        for row in fam["refused"]:
            at = S.epoch(row.get("at"))
            if at is not None and start <= at < end and str(row.get("why") or "").startswith(ARCHITECT_PROGRAM):
                answers["written"] += 1
                answers["refused"] += 1
                _bump(answers["by_rule"], rule_of(row.get("why")))
    retired = {"stalled": 0, "refuted": 0}
    for _, what in w["retired"]:
        retired[what] += 1
    usd: dict[str, list[float]] = {"births": [], "train": [], "review": [], "other": []}
    marks = (("births", SPEND_MARK + "births:"), ("train", SPEND_MARK + "train:"), ("review", SPEND_MARK + "review:"),
             ("review", SPEND_MARK + "audit:"))
    kinds = ",".join("?" * len(SPEND_KINDS))
    for row in guard.rows(db, f"SELECT usd, detail FROM spend WHERE kind IN ({kinds}) AND epoch>=? AND epoch<? AND "
                              "instr(detail, ?) > 0", (*SPEND_KINDS, float(start), float(end), SPEND_MARK)):
        value = _num(row["usd"])
        if value is not None:
            usd[next((name for name, mark in marks if mark in str(row["detail"] or "")), "other")].append(value)
    return {"birth_passes": {**passes, "skipped": dict(sorted(passes["skipped"].items()))},
            "families_born": len(w["born"]),
            "proposals_refused": {"total": refused["total"], "by_class": dict(sorted(refused["by_class"].items()))},
            "answers": {**answers, "by_rule": dict(sorted(answers["by_rule"].items()))},
            "train_rounds": rounds, "train_steps": steps, "versions": versions, "retired": retired,
            "model_usd": {**{name: round(math.fsum(values), 2) for name, values in usd.items()},
                          "total": round(math.fsum(v for values in usd.values() for v in values), 2)}}


def research(db: Any, start: float, end: float) -> dict[str, Any]:
    """`research_counts` for the funnel (league/ops/funnel.py `swarm_counts`): a read that fails is {"error": ...} and
    no count (unread is never zero), never the failure of the rest of the funnel."""
    try:
        return research_counts(db, start, end)
    except Exception as exc:  # noqa: BLE001 - unread is never zero
        return {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}


# ---------------------------------------------------------------------------------------------- the notice
def mailed(entries: Sequence[Mapping[str, Any]],
           found: Mapping[str, Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    """THE STALL JOB'S CALL for the notice (the module docstring, THE NOTICE): the notice's entries (`stall.cause_facts`,
    one a standing cause), each equity cause's fitted to what the gateway prints: its sentence whole inside the
    gateway's cut (`found`: the checks, for the sentence each fitted, `mail`), and its figures with the mail's first
    (`MAIL_FIGURES`), without what the mail does not list (`NOT_MAILED`, a list, a dict, a None). Each stays AN ENTRY
    OF ITS OWN under its own cause: none is folded into another's. Every other entry is returned as it is, and so is
    the whole list should the fitting fail: the notice goes out whatever these four hold."""
    try:
        out = []
        for entry in entries:
            e = dict(entry)
            cause = e.get("cause")
            if cause in CAUSES:
                check = found.get(cause) if isinstance(found, Mapping) and isinstance(found.get(cause), Mapping) else {}
                e["what"] = check.get("mail") or _cut(e.get("what"), WHAT_CHARS)
                figures = e.get("numbers") if isinstance(e.get("numbers"), Mapping) else {}
                keep = {k: v for k, v in figures.items()
                        if k not in NOT_MAILED and v is not None and not isinstance(v, (list, dict))}
                first = [k for k in MAIL_FIGURES.get(cause, ()) if k in keep]
                e["numbers"] = {k: keep[k] for k in (*first, *(k for k in keep if k not in first))}
            out.append(e)
        return out
    except Exception:  # noqa: BLE001 - the entries as the job made them: a notice, never none
        return [dict(e) for e in entries]


def warning(cause: str, check: Mapping[str, Any], text: str) -> str:
    """THE STALL JOB'S CALL for a House warning: `text`, the warning as the job words every cause's ("stall: <cause>:
    <what> <doing> Owner step: <step>."), returned as it is unless it is an equity cause's with an owner step and
    passes the alert's cut (`WARN_CHARS`). Then THE STEP IS KEPT WHOLE and what comes before it is the check's leading
    sentences that fit (`_lead`: its own, most telling first, then those of what the floor does): before, a long
    sentence cut the warning inside the owner step. Never raises."""
    try:
        step = check.get("owner_step")
        if cause not in CAUSES or not step or len(text) <= WARN_CHARS:
            return text
        head, tail = f"stall: {cause}: ", f" Owner step: {step}."
        parts = check.get("parts") if isinstance(check.get("parts"), list) else [check.get("what")]
        doing = re.split(r"(?<=\.)\s+", str(check.get("doing") or ""))
        return head + _lead([*parts, *doing], WARN_CHARS - len(head) - len(tail)) + tail
    except Exception:  # noqa: BLE001 - the warning as the job worded it
        return text


# ---------------------------------------------------------------------------------------------- the report
def report(root: str | Path, *, now: float, hours: float = FUNNEL_HOURS,
           settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """THE REPORT (the module docstring), read-only: {at, judged, why, checks, funnel (the last `hours`), families (each
    with its versions' fail codes, a disqualification's class and line, and its refusals' rule and sentences in closed
    words)}. `settings`: the swarm's, in place of the ones it loads from `root`."""
    root = Path(root)
    loaded = settings
    if loaded is None:
        from ..swarm import settings as settings_mod

        with guard.readonly():
            loaded = settings_mod.load(root)
    paused = any((root / name).exists() for name in ("PAUSE", "swarm.stop"))
    ctx = {"settings": ops_settings(root)}
    kept = read_json(root / STATE_FILE, None)  # the stall job's own record of the running release, read and not written
    running = release_since(kept.get(STATE_KEEP) if isinstance(kept, Mapping) else None, root, now)
    found = checks(ctx, root, now, loaded, paused=paused, since=running.get("since"), kept=running)
    on, why, _ = lanes(loaded, paused=paused)
    if switched_off(ctx):
        on, why = False, f"switched off (ops.json stall.{SWITCH} is false)"

    def read(db: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        return research(db, now - hours * 3600.0, now), e2_families(db)

    funnel, fams = guard.read(root / SWARM_DB, read)
    families = []
    for fam in fams:
        versions = {}
        for n, verdict in sorted(fam["versions"].items(), key=lambda kv: int(kv[0])):
            fails = [str(x) for x in verdict.get("fails") or []] if isinstance(verdict.get("fails"), list) else []
            row = {"at": verdict.get("at"), "passed": verdict.get("passed") is True, "fails": fails}
            if fails == ["DQ"]:
                row.update(error=dq_class(verdict.get("why")), line=dq_line(verdict.get("why")))
            versions[n] = row
        refused = [{"at": r.get("at"), "rule": rule_of(r.get("why")),
                    "sentences": [{"line": line, "sentence": words} for line, words, _ in sentences(r.get("why"))]}
                   for r in fam["refused"]]
        families.append({"id": fam["id"], "lane": fam["lane"], "born_at": fam["born_at"], "alive": fam["alive"],
                         "status": fam["status"], "versions": versions, "refused": refused,
                         "waits": {k: S.iso(v) for k, v in fam["waits"].items() if v > now}})
    return {"at": S.iso(now), "judged": on, "why": why,
            "checks": {c: {k: v for k, v in found[c].items() if k not in ("onset", "examples", "mail", "parts", "keep")}
                       for c in CAUSES},
            "funnel": {"hours": hours, **funnel}, "families": families}


def text(doc: Mapping[str, Any]) -> str:
    """`report` as plain lines for a terminal."""
    lines = [f"The equity lanes' health at {doc.get('at')}"
             + ("" if doc.get("judged") else f" (not judged: {doc.get('why')})"), ""]
    for cause, check in (doc.get("checks") or {}).items():
        state = "STANDS" if check.get("stalled") else "judged, clear" if check.get("judged") else "not judged"
        lines.append(f"{cause}: {state}")
        lines.append(f"  {check.get('what')}")
        if check.get("hint"):
            lines.append(f"  {check['hint']}.")
        if check.get("owner_step"):
            lines.append(f"  Owner step: {check['owner_step']}")
        figures = ", ".join(f"{k} {v}" for k, v in (check.get("numbers") or {}).items()
                            if v is not None and k not in ("judged", "examples", "hint"))
        lines += [f"  {figures}"] if figures else []
    funnel = doc.get("funnel") or {}
    lines += ["", f"The research funnel, last {funnel.get('hours'):g} h:" if _num(funnel.get("hours")) is not None
              else "The research funnel:"]
    for name, value in funnel.items():
        if name != "hours":
            lines.append(f"  {name}: {json.dumps(value, sort_keys=True)}")
    lines += ["", f"Families the equity pass bore: {len(doc.get('families') or [])}"]
    for fam in doc.get("families") or []:
        gone = "" if fam["alive"] else ", retired"
        lines.append(f"  {fam['id']} ({fam['lane']}, {fam['status']}{gone}; born {fam['born_at']})")
        for n, row in fam["versions"].items():
            said = "passed the bar" if row["passed"] else "failed " + ", ".join(row["fails"] or ["?"])
            where = f": {row['error']}" + (f" at line {row['line']}" if row.get("line") else "") if row.get("error") else ""
            lines.append(f"    v{n} {row.get('at')}: {said}{where}")
        for row in fam["refused"]:
            told = "; ".join((f"line {s['line']}: " if s["line"] else "") + s["sentence"] for s in row["sentences"][:4])
            lines.append(f"    refused {row.get('at')} by {RULE_WORDS.get(row['rule'], 'the ' + row['rule'] + ' rule')}"
                         + (f": {told}" if told else ""))
        for name, until in fam["waits"].items():
            lines.append(f"    waits ({name}) until {until}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    import time

    parser = argparse.ArgumentParser(prog="python3 -m league.ops.elane_health",
                                     description="The equity lanes' health and research funnel, read-only.")
    parser.add_argument("--state", required=True, help="the House's state root (it holds swarm.sqlite)")
    parser.add_argument("--hours", type=float, default=FUNNEL_HOURS, help="the funnel's window in hours")
    parser.add_argument("--json", action="store_true", help="the report as JSON")
    args = parser.parse_args(argv)
    doc = report(args.state, now=time.time(), hours=args.hours)
    print(json.dumps(doc, indent=1, sort_keys=True, default=str) if args.json else text(doc), end="")
    return 0


__all__ = ["CAUSES", "SWITCH", "switched_off", "checks", "judge", "facts", "lanes", "heartbeat", "release_since", "mailed",
           "warning", "research",
           "research_counts", "report", "text", "main", "dq_class", "dq_line", "refusal_class", "foreign_symbols",
           "rule_of", "sentences", "skip_kind", "step_read", "pass_read", "refusals_tally", "e2_families",
           "DQ_HOURS", "DQ_MIN_SCORED", "DQ_SHARE", "DQ_MIN_FAMILIES", "DQ_EARLY_FAULTED", "DQ_SHORT", "BIRTHS_HOURS",
           "BIRTHS_PASSES", "BIRTHS_OWNER_HOURS", "IDLE_HOURS", "BROKEN_MIN_FAILS", "BROKEN_KINDS", "STARVED_KINDS",
           "BEAT_STALE_SECONDS", "SETTINGS", "STATE_FILE", "STATE_KEEP", "KEPT", "NOT_MAILED", "NO_STALL", "WARN_CHARS",
           "REFUSED_HOURS", "REFUSED_MIN_ANSWERS", "REFUSED_SHARE", "REFUSED_EARLY", "BLIND_WARN_SECONDS",
           "LOOKBACK_HOURS", "FUNNEL_HOURS", "REFUSALS",
           "REFUSAL_WORDS", "RULES", "RULE_WORDS", "SENTENCES", "BIRTH_LEVERS", "IDLE_OWNER_KINDS", "PROGRAM_FAULTS",
           "BAR_CODES", "ERROR_CLASSES", "LANES", "STATE_KEY", "ROUTE_KEY", "MAIL_FIGURES"]

if __name__ == "__main__":
    raise SystemExit(main())
