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
  failed by it again and again (RUN). A fault of the generators against the contract or the sandbox, never a verdict on
  a mechanism. It names the commonest first error (a closed class: `dq_class`) and, where the records hold one, the
  reading rule's commonest sentence for that class in the same hours (`SENTENCES`). The owner's step: the text the
  generators read needs a fix, in a release.
- `elane_births`: the last `BIRTHS_PASSES` equity passes that asked a model bore no family (every proposal refused, none
  proposed, the answer cut short, no route answered, the pass raised). It names the commonest refusals in the House's
  own closed words (`REFUSALS`; the refusal's text carries what the model wrote and never reaches a notice) and the
  symbols of the code's universe that `elane.universe` does not hold. The owner's step only once no equity family was
  born for `BIRTHS_OWNER_HOURS` and a setting clears the main way they bore nothing (`BIRTH_LEVERS`).
- `elane_idle`: work is owed (families in Train research, or births wanted) and no version was scored on Train for
  `IDLE_HOURS`. It says why in the lane's own words: STARVED when E2 may ask no model now (`elane_yield.hold`: its
  hourly pace, its day's line, or the House's Sail day and the guard), BROKEN when it may and still scores nothing (the
  Train round's own steps: failures of the House's, questions no route answered, rounds that raised, families waiting
  out a backoff, no round at all). A starved lane names its lever and needs nobody; a broken one is the owner's step.
- `elane_refused`: of the programs the generators wrote in the last `REFUSED_HOURS`, more than `REFUSED_SHARE` were
  refused before a run by ONE static rule (the reading, level or memory rule, the code rules, NEEDS; any
  "equity <name> rule" a later release adds is read the same way): the generators are not being taught that rule. It
  names the rule and its commonest sentence in closed words. The owner's step: teach it where they read it, in a
  release.

WHEN A CAUSE IS JUDGED (`lanes`). Only while the lanes are on (`elane.mode` "gate" and `elane.birth_share` above zero,
as the swarm loads its settings), release E2's rounds are in the running tree, the floor is not paused (a maintenance
pause or a stopped swarm stops the lanes by design), E2's own dollars are not set to zero (`elane.e2.usd_day` or
`elane.e2.pace_share` at 0: the lanes paused by setting), the store holds an equity family or an equity pass at all,
and the owner has not switched the four off (`<state>/ops.json` `stall.elane` false: `switched_off`). Else every cause
reads "Not judged" and says why. And only on enough evidence, counted SINCE THE RUNNING SWARM STARTED
(the heartbeat's `started_at`): a release that fixes a fault restarts the swarm, so what the generators did under the
earlier release is not held against this one, and a House that just started is not judged on its first minutes. A
cause with too little evidence says how much it has and how much it needs. A lane is not judged idle while the swarm
itself is not running (its heartbeat `BEAT_STALE_SECONDS` old): that is the options lanes' causes to tell.

WHAT IT READS. The swarm's store, read-only, in one read transaction (`facts`): the equity families the equity pass
bore and E2's own Train record of each (state `elane_e2`: versions with their fails and what a disqualification said,
the programs refused before a run), the `swarm.elane` events (the equity passes and the Train rounds' steps), the
rounds that raised (`swarm.status`), E2's kv clocks, E2's own model spend, and the lane's own reading of whether it may
ask a model now (`elane_yield.hold` over a read-only reader); the swarm's heartbeat; the swarm's settings as it loads
them. NO RECURSION INTO JUDGES: no program is read, parsed or run here, no rule is applied again, and nothing is
written: a rule's sentence comes from the record that already holds it.

AN ALARM NEVER LOOSENS A JUDGE. Nothing here changes a screen, a bar, a budget, a seat, a money rule, the graveyard or a
refusal rule. It reads, reports and notifies.

THE NOTICE (`carried`). The gateway composes a stall notice only from causes it has words for (gateway/lib/email.mjs
`STALL_CAUSES`; an unknown cause makes the whole notice a 400 and nothing is mailed), and its words are held equal to
`stall.CAUSES` by its own test. So these four stand under their own names everywhere on the House (the receipt's
`checks`, `stall.json`, the House's warnings, the daily page's standing causes, the Done meter's item 7, which reads
the receipts' checks) and reach the mail INSIDE `CARRIER`, the cause the swarm's other alerts already travel in: one
entry whose sentence names each equity cause standing, with its figures, what the floor is doing and its owner step,
each cut to the gateway's own lengths. The stall job's pace is kept by the House's names (a new equity cause is a
notice at once); the gateway's own window is keyed on the carrier, so a second equity cause inside it waits for the
window (the House tries at every run). Once the gateway words the four (a gateway deploy first), naming them in
`stall.CAUSES` sends each as its own entry: `stall.EQUITY_CAUSES`, what `carried` folds, is then empty.

THE RESEARCH FUNNEL (`research_counts`; the funnel's `equity.research`, which the `scoreboard` job's receipt carries
for the day and the release, and `python3 -m league.ops.elane_health`): equity passes (asked, barren, cut short,
skipped by reason) and families born, proposals refused by reason class, programs refused before a run by rule,
versions scored, disqualified and failed by code (Y1, Y2, P1, R1, STATE and any other the bar names), bar passes,
review refusals and passes, families retired (stalled, refuted) and E2's model dollars by purpose. Counts and E2's
own dollars only.

THE REPORT (`report`, `text`; `python3 -m league.ops.elane_health --state DIR [--hours N] [--json]`), read-only, for an
operator on the box: the four checks, the funnel, and each family's versions (the fail codes, a disqualification's
class and line) and refusals (the rule and its sentence in closed words).

Standard library only at import; the swarm's own readers (`elane`, `elane_births`, `elane_yield`, the architect and
the loop for whether E2's rounds are there; `elane_train` for the contract's sentence of an error class; the code's
universe) are imported inside the functions that need them, and a failure there is "Not judged" with its error, never
a failed run.
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
#: The stall notice's cause these travel in until the gateway words them (the module docstring, THE NOTICE): the cause
#: the swarm's own alerts reach the owner in, the equity Train's among them (`elane_train_house`, `elane_train_state`).
CARRIER = "swarm_alerts"
#: The stall job's key in `<state>/ops.json` that switches these four off (`switched_off`): `{"stall": {"elane": false}}`.
SWITCH = "elane"
SWARM_DB = "swarm.sqlite"
HEARTBEAT = "swarm.heartbeat"

# ---------------------------------------------------------------------------------------------- the thresholds
#: `elane_dq`: the window, the scored versions under which nothing is judged, and the share above which it stands. Six
#: hours is the Gym-runs window of the options lanes (`stall.GYM_HOURS`): long enough for several Train rounds of
#: several families, short enough that a fault is told within a morning. Six versions is two families at least (a
#: family has four scored versions, `elane.e2.train_budget`): one family's bad program is no fault of the contract.
#: "Most" is more than half.
DQ_HOURS = 6.0
DQ_MIN_SCORED = 6
DQ_SHARE = 0.5
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
#: scores a version in the step that wrote it, so three hours is eighteen rounds with nothing judged.
IDLE_HOURS = 3.0
#: A swarm whose heartbeat is this old is not running, and its lanes are not judged idle: the House's hook restarts a
#: swarm whose heartbeat is 240 seconds old (league/swarm/hook.py `stale_heartbeat_seconds`), and a swarm that stays
#: down is the options lanes' causes to tell (`gym_runs` says the heartbeat's age).
BEAT_STALE_SECONDS = 600.0
#: `elane_refused`: the window (as `DQ_HOURS`), the programs written under which nothing is judged (two families' worth
#: of write attempts answered, as `DQ_MIN_SCORED` reasons), and the share one rule must pass ("most": more than half).
REFUSED_HOURS = 6.0
REFUSED_MIN_ANSWERS = 8
REFUSED_SHARE = 0.5
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
                  "elane.e2.births_max_output_tokens or lower elane.e2.max_per_pass in swarm.json"),
    "raised": "the equity pass raises (the swarm log's \"elane failed\" lines): it needs a fix, in a release",
}

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
#: Kept short: a cause's sentence, this and its owner step are one House warning of 900 characters.
DOING = {
    "elane_dq": ("Each disqualified version's author is shown the line of its own file the first error was raised at and "
                 "what is wrong there; a family whose versions all end so is retired STALLED. Nothing loosens the bar or "
                 "the sandbox."),
    "elane_births": ("The equity pass asks again at its own cadence and shows its next request the last pass's refusals "
                     "with their reasons. Nothing loosens the admission."),
    "elane_refused": ("Each refusal is in its author's next brief with what to write instead; it costs one write attempt, "
                      "never a scored version. Nothing loosens a rule."),
    "starved": ("E2 asks again by itself once it may (its hour's spend under its pace, 00:00 UTC for its day, room under "
                "the Sail guard's line). Versions already written are still scored. Nothing raises a pace or a line."),
    "broken": ("The Train round comes every ten minutes while it has work; a failure of the House's backs its family off "
               "and is alerted once (elane_train_house); a question no route answered is asked again after its backoff. "
               "Nothing here repairs anything."),
    "not_judged": "Nothing: the cause is not judged.",
}
REPORT = "python3 -m league.ops.elane_health --state /workspace/state"
#: THE SHORT WORDS a cause is told in when several share the carried entry (`carried`; each check's `brief` and `step`):
#: how an equity pass bore nothing or was refused, the short owner step of each way a setting clears, why a lane is
#: idle, and the short owner step of each way it is broken.
BIRTH_BRIEFS = {"symbols": "symbols outside elane.universe", "structure": "structures outside elane.structures",
                "closed_cell": "closed cells", "tried_lineage": "lineages that have their try",
                "same_idea": "ideas already in research", "card": "cards the card checks refuse",
                "agenda": "agenda keys that are not on the agenda", "lane": "lanes that are none",
                "mechanism": "no mechanism sentence", "graveyard": "the equity graveyard", "quota": "the pass's quota",
                "store": "births the store refused", OTHER: "other refusals", "refused": "refusals",
                "truncated": "answers cut short", "empty": "answers with no family", "failed": "no route answered",
                "raised": "the pass raised"}
BIRTH_STEPS = {"symbols": "decide whether to widen elane.universe (swarm.json)",
               "structure": "decide whether to widen elane.structures (swarm.json)",
               "closed_cell": "decide whether to widen elane.universe (closed cells bind by design)",
               "tried_lineage": "decide whether to widen elane.universe (the ration binds by design)",
               "truncated": "raise elane.e2.births_max_output_tokens or lower elane.e2.max_per_pass",
               "raised": "the equity pass raises: a fix, in a release"}
IDLE_BRIEFS = {"pace": "starved at its own pace (elane.e2.pace_share)", "usd_day": "starved: its day's dollars are spent "
               "(elane.e2.usd_day)", "sail_day": "starved: the House's Sail day holds it", OTHER: "starved",
               "raised": "broken: its rounds raise", "house": "broken: Train runs fail on the House's side",
               "unanswered": "broken: no model route answers", "refused": "broken: every program is refused before a run",
               "barren": "no family yet: the equity passes bear none", "no_round": "broken: no round starts"}
IDLE_STEPS = {"raised": "the equity rounds raise (the swarm log): a fix, in a release",
              "house": "check the equity_data job's receipt and the swarm's equity-decider.log",
              "no_round": "the equity lanes start no round (the swarm log): a fix, in a release"}
#: The lever of a starved lane, said beside it (never an owner step: the lanes run as their settings say).
PACE_LEVER = ("The lever is yours: BOTH elane.e2.pace_share and elane.e2.usd_day bind (python3 set_swarm.py "
              "elane.e2.pace_share=<lines> elane.e2.usd_day=<dollars> --apply).")
#: The ways an idle lane is BROKEN that nothing on the floor heals: the owner's step.
IDLE_OWNER_KINDS = ("raised", "house", "no_round")
#: The gateway's cuts of a stall entry (gateway/lib/email.mjs: `sentence(entry.what, 400)`, `sentence(entry.doing, 700)`,
#: STALL_STEP_CHARS, STALL_NUMBERS) and the figures of each cause the carried entry shows first.
WHAT_CHARS, DOING_CHARS, STEP_CHARS, FIGURES = 400, 700, 400, 16
MAIL_FIGURES = {"elane_dq": ("scored", "faulted", "top_error"), "elane_births": ("barren_passes", "kind", "born"),
                "elane_idle": ("idle_hours", "kind", "researching"), "elane_refused": ("answers", "top_rule", "top_rule_n")}


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


def _fit(parts: Sequence[str], limit: int, sep: str = " ") -> str:
    """`parts` joined inside `limit` characters: the short ones whole, the longest cut to what they leave, evenly (a
    cut ends "...")."""
    parts = [" ".join(str(p).split()) for p in parts if p]
    if not parts:
        return ""
    room = limit - len(sep) * (len(parts) - 1)
    caps = [len(p) for p in parts]
    while sum(caps) > room and max(caps) > 0:
        longest = max(caps)
        over = [i for i, cap in enumerate(caps) if cap == longest]
        cut = min(longest - max([cap for cap in caps if cap < longest], default=0), -(-(sum(caps) - room) // len(over)))
        for i in over:
            caps[i] -= cut
    return sep.join(p if len(p) <= cap else p[:max(0, cap - 3)].rstrip() + "..." for p, cap in zip(parts, caps))[:limit]


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
    count), truncated, failed (no route answered), want, barren (asked and bore none), how (one of `BARREN`, else
    None), items (its refusals' own texts, the first twelve)}."""
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
            "failed": failed, "want": _count(p.get("equity_want")), "short": _count(p.get("equity_short")),
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
    waits (the backoffs it has on record, {"infra:<kind>" | "unanswered": until when})}. Nothing of a later stage is
    read (no band, no Validation, no look)."""
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
                    "waits": waits})
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


def _held(db: Any, loaded: Mapping[str, Any] | None, now: float) -> dict[str, Any] | None:
    """Whether E2 may ask a model NOW, in the lane's own words (`elane_yield.hold` over a read-only reader: the same
    function the equity pass and the Train round call before each model call), with its pace and day: {text, kind
    (`skip_kind`), limit_usd_hour, spent_last_hour_usd, day_line_usd, spent_today_usd}. None when it cannot be read."""
    try:
        from ..swarm import elane_yield

        store = _Reader(db)
        text = elane_yield.hold(store, loaded, now)
        pace = elane_yield.pace(store, loaded, now)
        return {"text": text, "kind": skip_kind(text), "limit_usd_hour": float(pace["limit_usd_per_hour"]),
                "spent_last_hour_usd": float(pace["spent_last_hour_usd"]),
                "day_line_usd": float(elane_yield.day_line(loaded)),
                "spent_today_usd": float(elane_yield.spent_today(store, now))}
    except Exception:  # noqa: BLE001 - not read: the idle cause says so
        return None


def facts(db: Any, now: float, loaded: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """What the checks read from the swarm's store, in one read transaction (`guard.read`): the families the equity
    pass bore (`e2_families`), the lanes' events of the last `LOOKBACK_HOURS` (`_window`), E2's kv clocks, whether any
    `swarm.elane` event is on record and the first one's time, and the lane's own reading of whether it may ask a
    model now (`_held`)."""
    out: dict[str, Any] = {"families": e2_families(db), **_window(db, now - LOOKBACK_HOURS * 3600.0, now + 1.0)}
    reader = _Reader(db)
    out["kv"] = {key: _num(reader.get(key)) for key in (BIRTHS_AT_KEY, TRAIN_AT_KEY, TRAIN_OK_KEY)}
    first = guard.rows(db, "SELECT count(*) AS n, min(at) AS at FROM events WHERE kind='swarm.elane'")
    out["events"] = int(first[0]["n"] or 0) if first else 0
    out["first_event_at"] = S.epoch(first[0]["at"]) if first else None
    out["held"] = _held(db, loaded, now)
    return out


# ---------------------------------------------------------------------------------------------- the switch
def lanes(loaded: Mapping[str, Any] | None, f: Mapping[str, Any] | None = None, *,
          paused: bool = False) -> tuple[bool, str | None, dict[str, Any]]:
    """WHEN A CAUSE IS JUDGED (the module docstring): (judged, why not, the lanes' settings the checks read:
    {births_every_seconds, pace_share, usd_day}). `f`: the store's facts, for the empty lanes."""
    c: dict[str, Any] = {}
    if not isinstance(loaded, Mapping):
        return False, "the swarm's settings could not be read", c
    try:
        from ..swarm import architect, elane, elane_births, elane_yield, loop

        wired = callable(getattr(architect.Architect, "equity_pass", None)) and hasattr(loop, "EquityResearcher")
        mode, share = elane.cfg(loaded)["mode"], elane_births.birth_share(loaded)
        money = elane_yield.cfg(loaded)
        c = {"births_every_seconds": float(elane_births.cfg(loaded)["births_every_seconds"]),
             "pace_share": float(money["pace_share"]), "usd_day": float(money["usd_day"])}
    except Exception as exc:  # noqa: BLE001 - the lanes' own readers are not in this tree, or do not read
        return False, f"release E2's readers could not be read ({type(exc).__name__})", c
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
    step, so `judged` and the `examples` (the families, versions and lines an operator reads) ride its numbers."""
    extra = {"judged": True, **({"examples": check["examples"]} if check.get("examples") else {})}
    return {**check, "judged": True, "numbers": {**check["numbers"], **extra}}


def _since(now: float, hours: float, started: float | None) -> tuple[float, str]:
    """A window's start (the later of `hours` ago and the running swarm's start) and the words for it."""
    edge = now - hours * 3600.0
    if started is not None and edge < started <= now:
        return started, f"the {_hours(now - started)} h since the swarm started"
    return edge, f"the last {hours:g} h"


# ---------------------------------------------------------------------------------------------- the checks
def refusals_tally(f: Mapping[str, Any], start: float, now: float) -> dict[str, Any]:
    """The programs the equity generators wrote in `[start, now]` and the static rules' refusals of them: {answers,
    stored, refused, by_rule, sentences {rule: {words: n}}, raises {error class: {words: n}} (the reading rule's
    sentences by the error each says its misreading raises), examples [{family, rule, line, sentence}]}. The
    researchers' programs come from the Train rounds' events (each step that read an answer); the architect's programs
    at birth from the births (`program` "v1": stored) and the families' records (a refusal named `ARCHITECT_PROGRAM`)."""
    out: dict[str, Any] = {"answers": 0, "stored": 0, "refused": 0, "by_rule": {}, "sentences": {}, "raises": {},
                           "examples": []}

    def refusal(family: Any, why: Any) -> None:
        rule = rule_of(why)
        out["refused"] += 1
        _bump(out["by_rule"], rule)
        for line, words, raises in sentences(why):
            _bump(out["sentences"].setdefault(rule, {}), words)
            if raises:
                _bump(out["raises"].setdefault(raises, {}), words)
            if len(out["examples"]) < 6:
                out["examples"].append({"family": str(family), "rule": rule, "line": line, "sentence": words})

    for at, payload in f.get("rounds") or []:
        if not start <= at <= now:
            continue
        for step in payload.get("steps") or []:
            read = step_read(step)
            if not read["answered"]:
                continue
            out["answers"] += 1
            if read["refused"] is None:
                out["stored"] += 1
            else:
                refusal(step.get("family") if isinstance(step, Mapping) else None, read["why"])
    for at, program in f.get("born") or []:
        if start <= at <= now and program == "v1":
            out["answers"] += 1
            out["stored"] += 1
    for fam in f.get("families") or []:
        for row in fam["refused"]:
            at = S.epoch(row.get("at"))
            if at is not None and start <= at <= now and str(row.get("why") or "").startswith(ARCHITECT_PROGRAM):
                out["answers"] += 1
                refusal(fam["id"], row.get("why"))
    return out


def _dq_check(f: Mapping[str, Any], now: float, started: float | None) -> dict[str, Any]:
    """`elane_dq` (the module docstring). Pure."""
    start, span = _since(now, DQ_HOURS, started)
    scored, faulted, by_code, classes, examples, firsts = 0, 0, {c: 0 for c in PROGRAM_FAULTS}, {}, [], []
    families: set[str] = set()
    for fam in f.get("families") or []:
        for n, verdict in fam["versions"].items():
            at = S.epoch(verdict.get("at"))
            if at is None or not start <= at <= now:
                continue
            scored += 1
            fails = [str(x) for x in verdict.get("fails") or []] if isinstance(verdict.get("fails"), list) else []
            if len(fails) != 1 or fails[0] not in PROGRAM_FAULTS:
                continue
            faulted += 1
            by_code[fails[0]] += 1
            families.add(fam["id"])
            firsts.append(at)
            if fails[0] == "DQ":
                name = dq_class(verdict.get("why"))
                _bump(classes, name)
                if len(examples) < 6:
                    examples.append({"family": fam["id"], "version": int(n), "error": name,
                                     "line": dq_line(verdict.get("why"))})
    numbers: dict[str, Any] = {
        "scored": scored, "faulted": faulted, "disqualified": by_code["DQ"], "load_refused": by_code["LOAD"],
        "run_failed": by_code["RUN"], "share": None if not scored else round(faulted / scored, 2), "families": len(families),
        "retired_stalled": sum(1 for at, what in f.get("retired") or [] if what == "stalled" and start <= at <= now),
        "hours": round((now - start) / 3600.0, 1), "min_scored": DQ_MIN_SCORED}
    if scored < DQ_MIN_SCORED:
        return _not_judged(f"{scored} equity versions were scored in {span} (at least {DQ_MIN_SCORED} are needed)", numbers)
    top = _top(classes, 3)
    said, hint = "", None
    if top:
        name, n = top[0]
        numbers.update(top_error=_token(name), top_error_n=n)
        said = (f" The commonest first error: {'none its record names' if name == UNNAMED else name} ({n} of "
                f"{by_code['DQ']}" + ("; then " + ", ".join(f"{k} {v}" for k, v in top[1:]) if top[1:] else "") + ").")
        told = _top(refusals_tally(f, start, now)["raises"].get(name, {}), 1)
        if told:
            said += f" The reading rule's commonest sentence for it: {told[0][0]} ({told[0][1]}x)."
        try:  # the contract's own sentence for the class (one fixed sentence a class: rules, nothing a run read)
            from ..swarm.elane_train import DQ_HINTS

            hint = DQ_HINTS.get(name)
        except Exception:  # noqa: BLE001 - the class is named without it
            hint = None
    stalled = faulted > DQ_SHARE * scored
    named = f" (the commonest first error: {top[0][0]})" if top and top[0][0] != UNNAMED else ""
    retired = numbers["retired_stalled"]
    return {
        "stalled": stalled, "judged": True,
        "what": (f"{faulted} of the {scored} equity versions scored in {span} could not be judged for a fault of their own "
                 f"program ({by_code['DQ']} disqualified, {by_code['LOAD']} refused at load, {by_code['RUN']} failed by the "
                 "decider child): no mechanism was judged in them" + (f", and {retired} families were retired STALLED"
                                                                      if retired else "") + f".{said}"),
        "numbers": numbers, "doing": DOING["elane_dq"],
        "owner_step": (f"the equity generators misread the program contract{named}: fix the text they read "
                       "(league/equity/EQUITY.md \"Reading ctx\", elane_review.READING_CTX) or the static rule that should "
                       f"refuse it, in a release; {REPORT} lists the families and lines") if stalled else None,
        "onset": min(firsts) if firsts and stalled else None, "examples": examples, "hint": hint,
        "brief": (f"{faulted} of {scored} versions scored in {numbers['hours']:g} h could not be judged (their own faults"
                  + (f", mostly {top[0][0]}" if named else "") + ")"),
        "step": ("fix the contract text the generators read" + (f" for {top[0][0]}" if named else "")
                 + " (league/equity/EQUITY.md \"Reading ctx\"), in a release") if stalled else None}


def _births_check(f: Mapping[str, Any], now: float, started: float | None) -> dict[str, Any]:
    """`elane_births` (the module docstring). Pure."""
    start, span = _since(now, BIRTHS_HOURS, started)
    # The passes that asked a model and the equity passes that raised, oldest first.
    asked = sorted([(at, pass_read(p)) for at, p in f.get("passes") or [] if start <= at <= now]
                   + [(at, {"asked": True, "barren": True, "how": "raised", "born": 0, "proposed": 0, "refused": 0,
                            "truncated": False, "skipped": None, "want": 0, "items": []})
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
    for _, row in streak:
        _bump(hows, row["how"])
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
    kind = top[0][0] if main == "refused" and top else main
    numbers.update(kind=_token(kind), top_refusal=_token(top[0][0]) if top else "none", top_refusal_n=top[0][1] if top else 0)
    stalled = len(streak) >= BIRTHS_PASSES
    symbols = ", ".join(f"{s} {n}x" for s, n in _top(named, 4))
    reasons = "; ".join(f"{REFUSAL_WORDS[k]} ({n})" for k, n in top)
    want = max([row["want"] for _, row in streak], default=0)
    # The owner's step only once the lanes had their hours to correct themselves, and only for a way a setting clears.
    dry = stalled and (now - (last_born if last_born is not None else streak[-1][0])) >= BIRTHS_OWNER_HOURS * 3600.0
    lever = BIRTH_LEVERS.get(str(kind)) if dry else None
    return {
        "stalled": stalled, "judged": True,
        "what": (f"The equity lanes' last {len(streak)} passes that asked a model bore no family"
                 + (f" (each wanted up to {want})" if want else "") + f": {hows.get('refused', 0)} had every proposal "
                 f"refused, {hows.get('empty', 0)} proposed none, {hows.get('truncated', 0)} were cut short, "
                 f"{hows.get('failed', 0)} got no answer, {hows.get('raised', 0)} raised."
                 + (f" The commonest refusals: {reasons}." if reasons else "")
                 + (f" Symbols the code knows and elane.universe does not hold, named most: {symbols}." if symbols else "")
                 if streak else
                 f"The equity lanes' latest pass that asked a model bore a family ({len(asked)} asked in {span})."),
        "numbers": numbers,
        "doing": DOING["elane_births"] + ("" if lever or not stalled else
                                          (f" After {BIRTHS_OWNER_HOURS:g} h with no equity birth this is your step when a "
                                           "setting clears it.")),
        "owner_step": (f"no equity family was born for {_hours(now - (last_born if last_born is not None else streak[-1][0]))} "
                       f"h while {len(streak)} passes asked for one: "
                       + lever.format(named=f" ({symbols})" if symbols else "")) if lever else None,
        "onset": (last_born if last_born is not None else streak[-1][0]) if stalled else None,
        "brief": (f"the last {len(streak)} passes that asked a model bore no family"
                  + (f" (mostly {BIRTH_BRIEFS.get(str(kind), 'refusals')}" + (f": {symbols}" if symbols else "") + ")"
                     if kind else "")),
        "step": BIRTH_STEPS.get(str(kind)) if lever else None}


def _idle_check(f: Mapping[str, Any], now: float, started: float | None, c: Mapping[str, Any],
                beat_age: float | None = None) -> dict[str, Any]:
    """`elane_idle` (the module docstring). Pure. `beat_age`: the age of the swarm's heartbeat in seconds, when known."""
    fams = f.get("families") or []
    researching = [fam for fam in fams if fam["alive"] and fam["status"] == "researching"]
    passes = [(at, pass_read(p)) for at, p in f.get("passes") or []]
    last = passes[-1][1] if passes else None
    births_at = (f.get("kv") or {}).get(BIRTHS_AT_KEY)
    every = float(c.get("births_every_seconds") or 7200.0)
    overdue = births_at is not None and now - births_at > max(IDLE_HOURS * 3600.0, 2.0 * every)
    # Births are wanted when the latest pass was held back, left births unfilled or bore none. A pass that may ask no
    # model is not started and leaves no event: it shows as overdue.
    wanted = bool(last and (last["skipped"] in ("pace", "usd_day", "sail_day") or last["short"] > 0 or last["barren"]))
    scored_at = [S.epoch(v.get("at")) for fam in fams for v in fam["versions"].values()]
    last_scored = max([t for t in scored_at if t is not None and t <= now], default=None)
    owed_at = [S.epoch(fam["born_at"]) for fam in researching] + [f.get("first_event_at")]
    first_owed = min([t for t in owed_at if t is not None], default=None)
    since = last_scored if last_scored is not None else first_owed
    held = f.get("held") if isinstance(f.get("held"), Mapping) else None
    numbers: dict[str, Any] = {"researching": len(researching), "births_wanted": wanted, "pass_overdue": overdue,
                               "last_scored_at": None if last_scored is None else S.iso(last_scored), "min_hours": IDLE_HOURS}
    if held is not None:
        numbers.update(held_now=held["kind"] or "none", pace_usd_hour=round(held["limit_usd_hour"], 4),
                       spent_last_hour_usd=round(held["spent_last_hour_usd"], 4), day_line_usd=round(held["day_line_usd"], 2),
                       spent_today_usd=round(held["spent_today_usd"], 2))
    if not researching and not wanted and not overdue:
        return _not_judged("no equity family is in Train research and no equity birth is wanted", numbers)
    if since is None:
        return _not_judged("nothing says since when the equity lanes owe work", numbers)
    if beat_age is not None and beat_age > BEAT_STALE_SECONDS:
        return _not_judged(f"the swarm is not running (its heartbeat is {beat_age / 60.0:.0f} min old): the House restarts "
                           "a swarm that stops, and the options lanes' causes say so", numbers)
    # Evidence counts from the running swarm's start: a swarm up for less than `IDLE_HOURS` is not judged idle.
    edge = max(since, started) if started is not None else since
    idle = now - edge
    numbers["idle_hours"] = round(idle / 3600.0, 1)
    if idle < IDLE_HOURS * 3600.0:
        if started is not None and since < started:
            return _not_judged(f"the swarm started {_hours(now - started)} h ago (the lanes are judged idle after "
                               f"{IDLE_HOURS:g} h with nothing scored)", numbers)
        return {"stalled": False, "judged": True,
                "what": (f"The last equity version was scored {_hours(idle)} h ago." if last_scored is not None else
                         f"The equity lanes have owed work for {_hours(idle)} h and scored no version yet.")
                        + f" The lanes are idle after {IDLE_HOURS:g} h with nothing scored.",
                "numbers": numbers, "doing": DOING["broken"], "owner_step": None, "onset": None}
    # WHY, since the lanes went idle: the Train rounds' own steps, the rounds that raised, the families waiting.
    tally = {"rounds": 0, "house": 0, "unanswered": 0, "refused": 0, "raised": 0, "passes": 0}
    houses: dict[str, int] = {}
    for at, payload in f.get("rounds") or []:
        if at < edge:
            continue
        tally["rounds"] += 1
        for step in payload.get("steps") or []:
            read = step_read(step)
            if read["house"]:
                tally["house"] += 1
                _bump(houses, read["house"])
            tally["unanswered"] += int(read["unanswered"])
            tally["refused"] += int(read["refused"] is not None)
    tally["raised"] = sum(1 for at, _ in f.get("raised") or [] if at >= edge)
    tally["passes"] = sum(1 for at, row in passes if at >= edge and row["barren"])
    waiting = [fam for fam in researching if any(t > now for t in fam["waits"].values())]
    for fam in waiting:
        for name, until in fam["waits"].items():
            if until > now and name.startswith("infra:"):
                _bump(houses, name.split(":", 1)[1])
    train_at = (f.get("kv") or {}).get(TRAIN_AT_KEY)
    numbers.update(train_rounds=tally["rounds"], house_failures=tally["house"], unanswered=tally["unanswered"],
                   refused_answers=tally["refused"], rounds_raised=tally["raised"], barren_passes=tally["passes"],
                   families_waiting=len(waiting),
                   train_round_age_min=None if train_at is None else round(max(0.0, now - train_at) / 60.0, 1))
    starved = held is not None and held["kind"] is not None
    if starved:
        kind = held["kind"]
        words = {
            "pace": (f"E2 is at its own hourly pace (it booked ${held['spent_last_hour_usd']:.2f} on models in the last "
                     f"hour against a pace of ${held['limit_usd_hour']:.2f}: elane.e2.pace_share {c.get('pace_share', 0):g} "
                     "of the Sail model line)"),
            "usd_day": (f"E2's model dollars for the UTC day are spent (${held['spent_today_usd']:.2f} of a day's line of "
                        f"${held['day_line_usd']:.2f}: the smaller of elane.e2.usd_day and a day at its pace)"),
            "sail_day": "the House's Sail day holds E2 (" + _sail_words(held["text"]) + ")",
        }.get(kind, "E2 may ask no model now")
        why = f"STARVED, not broken: {words}, so no model is asked." + (f" {PACE_LEVER}" if kind in ("pace", "usd_day") else "")
    else:
        # With no family in research the work owed is the equity pass's: barren passes are `elane_births`' to explain.
        kind = ("raised" if tally["raised"] else "house" if tally["house"] or houses else
                "unanswered" if tally["unanswered"] or any("unanswered" in fam["waits"] for fam in waiting) else
                "refused" if tally["refused"] else "barren" if not researching and tally["passes"] else "no_round")
        parts = [f"{tally['rounds']} Train rounds ran"]
        if tally["raised"]:
            parts.append(f"{tally['raised']} rounds raised")
        if tally["house"] or houses:
            parts.append(f"{tally['house']} steps failed on the House's side ("
                         + (", ".join(f"{k} {n}" for k, n in _top(houses, 4)) or "kind not named") + ")")
        if tally["unanswered"]:
            parts.append(f"{tally['unanswered']} questions got no answer from a model route")
        if tally["refused"]:
            parts.append(f"{tally['refused']} programs were refused before a run (see elane_refused)")
        if waiting:
            parts.append(f"{len(waiting)} of {len(researching)} families wait out a backoff")
        if train_at is not None:
            parts.append(f"the Train round last started {max(0.0, now - train_at) / 60.0:.0f} min ago")
        may = "E2 may ask a model now" if held is not None else "whether E2 may ask a model now could not be read"
        why = (f"Not starved ({may}): {tally['passes']} equity passes asked a model and bore no family, so there is none "
               "to score (see elane_births)." if kind == "barren" else
               f"BROKEN, not starved: {may} and " + "; ".join(parts) + ".")
    numbers["kind"] = kind
    owed = ((f"{len(researching)} families are in Train research" if researching else "no family is in Train research")
            + (" and births are wanted" if wanted else " and the equity pass is overdue" if overdue else ""))
    owner = None
    if not starved and kind in IDLE_OWNER_KINDS:
        owner = {"raised": "the equity lanes' rounds raise (the swarm log's \"elane failed\" and \"elane_train failed\" lines)",
                 "house": ("the equity lanes' Train runs fail on the House's side: check the equity_data job's receipt and the "
                           "swarm's equity-decider.log"),
                 "no_round": ("the equity lanes owe work, may ask a model and start no round (the swarm log's elane_train "
                              "lines)"),
                 }[kind] + f"; it needs a fix, in a release or on the box ({REPORT} prints each family's state)"
    return {
        "stalled": True, "judged": True,
        "what": f"No equity version was scored on Train for {_hours(idle)} h while {owed}. {why}",
        "numbers": numbers, "owner_step": owner, "onset": edge,
        "doing": DOING["starved" if starved else "elane_births" if kind == "barren" else "broken"],
        "brief": f"no version scored for {_hours(idle)} h, " + IDLE_BRIEFS.get(str(kind), IDLE_BRIEFS[OTHER]),
        "step": IDLE_STEPS.get(str(kind)) if owner else None}


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


def _refused_check(f: Mapping[str, Any], now: float, started: float | None) -> dict[str, Any]:
    """`elane_refused` (the module docstring). Pure."""
    start, span = _since(now, REFUSED_HOURS, started)
    tally = refusals_tally(f, start, now)
    answers, refused = tally["answers"], tally["refused"]
    rules = {k: v for k, v in tally["by_rule"].items() if k not in NOT_RULES}
    numbers: dict[str, Any] = {"answers": answers, "stored": tally["stored"], "refused": refused,
                               **{f"refused_{_token(k)}": v for k, v in sorted(tally["by_rule"].items())},
                               "hours": round((now - start) / 3600.0, 1), "min_answers": REFUSED_MIN_ANSWERS}
    if answers < REFUSED_MIN_ANSWERS:
        return _not_judged(f"the equity generators wrote {answers} programs in {span} (at least {REFUSED_MIN_ANSWERS} are "
                           "needed)", numbers)
    top = _top(rules, 1)
    rule, n = top[0] if top else ("none", 0)
    numbers.update(top_rule=_token(rule), top_rule_n=n, share=round(n / answers, 2))
    stalled = n > REFUSED_SHARE * answers
    said = _top(tally["sentences"].get(rule, {}), 2)
    words = RULE_WORDS.get(rule, f"the {rule} rule")
    by_rule = ", ".join(f"{RULE_WORDS.get(k, 'the ' + k + ' rule')} {v}" for k, v in _top(tally["by_rule"], 5))
    return {
        "stalled": stalled, "judged": True,
        "what": (f"{n} of the {answers} programs the equity generators wrote in {span} were refused before a run by ONE "
                 f"static rule, {words} ({refused} refused in all: {by_rule})."
                 + (" Its commonest sentence: " + "; then ".join(f"{s} ({k}x)" for s, k in said) + "." if said else "")
                 if top else
                 f"None of the {answers} programs the equity generators wrote in {span} was refused by a static rule."),
        "numbers": numbers, "doing": DOING["elane_refused"],
        "owner_step": (f"the equity generators are not being taught {words}: teach it where they read it "
                       "(league/equity/EQUITY.md, the researcher's system prompt, elane_review.READING_CTX), in a "
                       f"release; {REPORT} lists the refusals") if stalled else None,
        "onset": None, "examples": tally["examples"],
        "brief": (f"{n} of {answers} programs written in {numbers['hours']:g} h were refused before a run by {words}"
                  + (f": {said[0][0]}" if said else "")),
        "step": f"teach {words} where the generators read it (league/equity/EQUITY.md), in a release" if stalled else None}


def judge(f: Mapping[str, Any], *, now: float, started: float | None = None, beat_age: float | None = None,
          settings: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """The four checks over the store's facts (`facts`), each {stalled, judged, what, numbers, doing, owner_step, onset}.
    Pure. `started`: the running swarm's start (evidence counts from it); `beat_age`: its heartbeat's age in seconds;
    `settings`: `lanes`' third value."""
    found = {"elane_dq": _dq_check(f, now, started), "elane_births": _births_check(f, now, started),
             "elane_idle": _idle_check(f, now, started, settings or {}, beat_age),
             "elane_refused": _refused_check(f, now, started)}
    return {cause: _judged(check) if check["judged"] else check for cause, check in found.items()}


def heartbeat(root: str | Path, now: float) -> tuple[float | None, float | None]:
    """(when the running swarm started, the age of its heartbeat in seconds) from `<state>/swarm.heartbeat`
    (`started_at`, `at`); a None for what the file does not say."""
    beat = read_json(Path(root) / HEARTBEAT, None)
    beat = beat if isinstance(beat, Mapping) else {}
    started, at = _num(beat.get("started_at")), _num(beat.get("at"))
    return (started if started is not None and 0 < started <= now else None,
            None if at is None else max(0.0, now - at))


def switched_off(ctx: Any) -> bool:
    """THE OWNER'S SWITCH (`<state>/ops.json` `stall.elane` false; `ctx`: the job's context, or a mapping with its
    `settings`): the four causes are not judged, and the rest of the stall alarm goes on. Absent, they are judged (the
    release ships it so)."""
    settings = ctx.get("settings") if isinstance(ctx, Mapping) else getattr(ctx, "settings", None)
    block = settings.get("stall") if isinstance(settings, Mapping) else None
    return isinstance(block, Mapping) and block.get(SWITCH) is False


def checks(ctx: Any, root: str | Path, now: float, loaded: Mapping[str, Any] | None, *, paused: bool = False,
           errors: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """THE STALL JOB'S CALL (league/ops/stall.py `run`): the four causes' checks, from the swarm's store (read-only),
    its heartbeat and its settings as it loads them (`loaded`). `ctx`: the job's context (for the owner's switch,
    `switched_off`). `paused`: a maintenance pause or a stopped swarm stands. Never raises: lanes that cannot be read
    are "Not judged" and an entry of `errors`."""
    try:
        if switched_off(ctx):
            return {cause: _not_judged(f"switched off (ops.json stall.{SWITCH} is false)") for cause in CAUSES}
        on, why, _ = lanes(loaded, paused=paused)  # the switch first: lanes that are off cost no read of the store
        if on:
            f = guard.read(Path(root) / SWARM_DB, lambda db: facts(db, now, loaded))
            on, why, c = lanes(loaded, f, paused=paused)
        if not on:
            return {cause: _not_judged(str(why)) for cause in CAUSES}
        started, beat_age = heartbeat(root, now)
        return judge(f, now=now, started=started, beat_age=beat_age, settings=c)
    except Exception as exc:  # noqa: BLE001 - the stall alarm goes on without the equity lanes' causes
        if errors is not None:
            errors.append(f"the equity lanes' health could not be read ({type(exc).__name__})")
        return {cause: _not_judged(f"the equity lanes' records could not be read ({type(exc).__name__})") for cause in CAUSES}


# ---------------------------------------------------------------------------------------------- the funnel
def research_counts(db: Any, start: float, end: float) -> dict[str, Any]:
    """THE EQUITY LANES' RESEARCH FUNNEL in `[start, end)` (the module docstring), each count from the event that is the
    thing itself: the equity passes and the Train rounds' steps (`swarm.elane`), the births (`swarm.born`), E2's spend
    rows; the architect's programs refused at birth from the families' records (the last five a family keeps)."""
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
    for _, payload in w["rounds"]:
        rounds += 1
        for step in payload.get("steps") or []:
            read = step_read(step)
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
            "train_rounds": rounds, "versions": versions, "retired": retired,
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
def carried(entries: Sequence[Mapping[str, Any]], fold: Sequence[str] = CAUSES,
            found: Mapping[str, Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    """THE NOTICE (the module docstring): the stall notice's entries (`stall.cause_facts`, one a standing cause) with
    the equity causes the gateway has no words for (`fold`: `stall.EQUITY_CAUSES`) folded into ONE `CARRIER` entry: its
    `what` names each one ("elane_dq: ..."), its `numbers` open with each one's figures (`MAIL_FIGURES`, named
    "<cause>_<figure>"), its `doing` and `owner_step` hold theirs, its `since` is the earliest, each inside the
    gateway's own cut. One equity cause alone is told in its own sentence and step; several, or one beside a carrier
    that stands by itself (its own words come after theirs), each in its short words (`found`: the checks, for their
    `brief` and `step`), so the entry's 400 characters name them all. An equity cause that is not folded goes as its
    own entry with its figures only (the examples stay on the House). Pure."""
    own = [dict(e) for e in entries if e.get("cause") in fold]
    rest = [dict(e) for e in entries if e.get("cause") not in fold]
    for e in rest:
        if e.get("cause") in CAUSES and isinstance(e.get("numbers"), Mapping):
            e["numbers"] = {k: v for k, v in e["numbers"].items() if not isinstance(v, (list, dict))}
    if not own:
        return rest
    host = next((e for e in rest if e.get("cause") == CARRIER), None)
    alone = len(own) == 1 and host is None
    lead = "The equity lanes, " if alone else "The equity lanes: "
    short = {} if alone or not isinstance(found, Mapping) else found
    told, steps, numbers = [], [], {}
    for e in own:
        check = short.get(e["cause"]) if isinstance(short.get(e["cause"]), Mapping) else {}
        told.append(f"{e['cause']}: {check.get('brief') or e.get('what') or ''}")
        if e.get("owner_step"):
            steps.append(str(check.get("step") or e["owner_step"]))
        figures = e.get("numbers") if isinstance(e.get("numbers"), Mapping) else {}
        for name in MAIL_FIGURES.get(e["cause"], ()):
            if name in figures and not isinstance(figures[name], (list, dict)):
                numbers[f"{e['cause']}_{name}"[:40]] = figures[name]
    doing = list(dict.fromkeys(str(e.get("doing") or "") for e in own))
    if host is not None:
        told.append(f"Also: {host.get('what') or ''}")
        doing.append(str(host.get("doing") or ""))
        steps += [str(host["owner_step"])] if host.get("owner_step") else []
        numbers.update({k: v for k, v in (host.get("numbers") or {}).items() if k not in numbers})
    stamps = [(S.epoch(e.get("since")), e) for e in ([*own, host] if host is not None else own)]
    stamps = [(at, e) for at, e in stamps if at is not None]
    first = min(stamps, key=lambda r: r[0])[1] if stamps else None
    folded = {"cause": CARRIER, "what": lead + _fit(told, WHAT_CHARS - len(lead), " | "), "numbers": numbers,
              "since": None if first is None else first.get("since"), "hours": None if first is None else first.get("hours"),
              "doing": _fit(doing, DOING_CHARS), "owner_step": _fit(steps, STEP_CHARS, "; ") or None}
    return [folded if e is host else e for e in rest] if host is not None else [*rest, folded]


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
    found = checks(ctx, root, now, loaded, paused=paused)
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
            "checks": {c: {k: v for k, v in found[c].items() if k not in ("onset", "examples", "brief", "step")}
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
                            if v is not None and k not in ("judged", "examples"))
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


__all__ = ["CAUSES", "CARRIER", "SWITCH", "switched_off", "checks", "judge", "facts", "lanes", "heartbeat", "carried",
           "research",
           "research_counts", "report", "text", "main", "dq_class", "dq_line", "refusal_class", "foreign_symbols",
           "rule_of", "sentences", "skip_kind", "step_read", "pass_read", "refusals_tally", "e2_families",
           "DQ_HOURS", "DQ_MIN_SCORED", "DQ_SHARE", "BIRTHS_HOURS", "BIRTHS_PASSES", "BIRTHS_OWNER_HOURS", "IDLE_HOURS",
           "BEAT_STALE_SECONDS",
           "REFUSED_HOURS", "REFUSED_MIN_ANSWERS", "REFUSED_SHARE", "LOOKBACK_HOURS", "FUNNEL_HOURS", "REFUSALS",
           "REFUSAL_WORDS", "RULES", "RULE_WORDS", "SENTENCES", "BIRTH_LEVERS", "IDLE_OWNER_KINDS", "PROGRAM_FAULTS",
           "BAR_CODES", "ERROR_CLASSES", "LANES", "STATE_KEY", "ROUTE_KEY", "MAIL_FIGURES"]

if __name__ == "__main__":
    raise SystemExit(main())
