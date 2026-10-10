"""FAMILY CARDS (release B, Oct 2026): the pre-declared terms every new family is researched and judged under.

WHY. On Sept 30 the House had buried 1,974 families. Most were idle-rule deaths, and new births repeated the dead ideas
under new names: 452 of that day's births were debit verticals, many of them the same rebound or trend conditioning on
another root. A graveyard read as prose, and a mechanism sentence judged by word overlap, did not stop a refuted idea
from being born again. A card makes the idea structured, so a refuted cell can be recognised without a model.

THE CARD. The architect writes one for every family it proposes (`Architect.admit` refuses a proposal without a complete
card, naming each missing or invalid field):
- `hypothesis`: the economic reason the opportunity exists (who pays, and why it persists);
- `mechanism_class`: one of `MECHANISM_CLASSES`, a small controlled vocabulary drawn from the graveyard's mechanisms;
- `inputs`: what the program conditions on, from `INPUTS` (one to six);
- `holding`: the expected holding horizon, one of `HOLDING`;
- `cost`: the round trip's spread and fee hurdle, as a fraction of maximum loss (`hurdle`) and why (`why`);
- `comparison`: the naive baseline it must beat, normally the same structure entered on the same schedule without the
  signal's condition;
- `ablation`: the PARAMS switch that turns the signal into that baseline (`param`, and the `off` value; `signal_on` = 0
  by default, the contract's convention). The mechanism test (league/swarm/mechanism.py) runs the program both ways. A
  card whose structure is not directional (`STRUCTURE_FAMILIES`) may declare `{"flat": true}` instead: the structure
  itself is the edge (unconditional premium selling, say), so the comparison is not trading; a directional structure
  never may (its comparison is its conditioning, or a drift-long exposure would pass), and neither may a credit vertical
  (`FLAT_REFUSED`: a bull put spread is a directional bet that a one-sample test against zero passes on upward drift);
- `falsification`: a concrete, pre-declared result that kills it;
- `rebirth` (only when the card falls in a refuted cell, below): the graveyard `row` it re-enters, what is `different`,
  and the new `evidence` that justifies it.

STORAGE. A card is immutable. `family_cards` holds one row a family (its canonical JSON, its sha and its cell key) and
refuses UPDATE and DELETE by trigger; the family's spec carries `card_sha`. A family born from another's spec (a fork)
reads its parent's card through that sha. Nothing edits a card: a revision that changes the hypothesis is a new
proposal, and the architect's existing lineage rules decide its lineage (no rule here ever starts a lineage or lowers a
count). `card_evidence` is the card's append-only record: each mechanism test's verdict and figures, with the program
version and the card's sha. Both tables are created on first use by this module on the store's own connection, so
`store.py` (loaded by the live path) is unchanged.

THE CELL. A card's key is (mechanism class, inputs, structure family, holding bucket). `STRUCTURE_FAMILIES` groups the
twelve structures by the exposure they sell or buy: a new structure in the same group is not a new idea. The cell of a
refusal and of a budget is (class, structure family, holding).

CARD-BASED REBIRTH REFUSAL (`RebirthIndex`). A proposal whose cell matches a graveyard row killed by a MECHANISM VERDICT
(`MECHANISM_VERDICTS`: the operator's pre-registered tests, refuted, self-refuted, diagnosed, trial-adjusted, drift,
stress, and a failed mechanism test) is refused unless its `rebirth` makes a valid case, and the refusal quotes the
row's lesson, which the architect reads in its next request. MATCHING (`match_keys`): a carded row matches on class,
structure family and holding when the input sets overlap (an unused input added to a dead card never escapes it). Inputs
for matching are read the same way on BOTH sides: the declared inputs AND those the words name (`match_inputs`, the
`infer_inputs` reading): the proposal's mechanism text and hypothesis, and a carded row's hypothesis and graveyard
mechanism text. Declared inputs are never checked against a program, so declaring inputs that avoid a dead card's while
the text reads the same ones never escapes it, and a dead card that under-declared what its words read is matched on
those words too. A row from before cards has no declared key, so `infer_key` reads one from its mechanism text,
structure and days to expiry (a deterministic keyword reading, deliberately coarse) and it matches on class, structure
family and holding alone. The proposal's own mechanism text is read the same way (`infer_key`): when it reads as another
class than the one declared, the rows of that class's cell match too (a refuted idea relabeled into an open class never
escapes). A VALID REBIRTH names one of the matched rows (`row`), says what is different (`different`: words beyond the
dead row's own mechanism, a new root, structure or horizon never counting) and adds at least one input the dead row did
not read (a carded row's `match_inputs`, a legacy row's `infer_inputs` of its text): new words alone are never a new
idea. Its `evidence` cites something checkable: a new input by name, a run id or a `card_evidence` seq in the store. It
is born only while its row has backed fewer than `architect.max_rebirths_per_row` (2) births and the row's cell has had
fewer than `architect.max_rebirths_per_cell` (3) rebirths in the last `architect.rebirth_window_days` (7): a cell whose
rows multiply never refills its own budget. A false match costs a justification and a budget slot, never an idea
outright. The check is deterministic and makes no model call.

THE CELLS A BIRTH MAY LAND IN (F1, Oct 3, 2026; `RebirthIndex.grid`, `bearable`, `cells(families=...)`). While
`architect.structures` names the types a birth may be, the request lists every cell of those types' structure families
(for debit verticals and long singles, the 44 directional cells: 11 mechanism classes by 4 holdings), each with its rows,
its rebirth room and the rows a claim may name, the cells with room first, then the cells no row is in (a card there
needs no rebirth), then the cells at room 0; no line goes to a structure type no birth may be. A cell can bear a birth
when no row of it needs a claim, or when it has rebirth room and a row that has backed fewer than
`architect.max_rebirths_per_row` rebirths; a pass with no such cell asks no model (`Architect.closed`).

THE CELL'S YIELD (`architect.cell_yield`, H2 of the Oct 1 edge study; off by default: null, every mechanism-verdict row
needs a claim, as above). A SELF-REFUTED row (its own researcher retired it, since release A at a median of under an
hour) or a DRIFT row (the idle rule's Train record failed the drift screen) is a family's outcome, not a test of the
mechanism, and the productive cells hold the most of them (Oct 1: 105 of `relative_value / directional / days_4_10`'s
134 rows were DRIFT, while its births passed the drift screen two to three times as often as the rest). Switched on
(`{"min_births": N, "floor": F, "lookback_days": D}`; `true` or `{}` takes `CELL_YIELD_DEFAULTS`), each cell is read
for its yield: the families born in it in the last D days whose outcome is settled (retired, or already holding a
drift-passing eligible Train run; one still researching without a pass is pending, and one whose eligible runs all
predate the drift figures is unknown: neither counts), and how many of them hold a drift-passing eligible Train run
(`evidence.drift_screen` under the running screen's thresholds, from the run's own Train start). A cell with at least N
settled births whose Wilson 95% upper bound on that share is below F is EXHAUSTED: every one of its rows needs a claim,
as above. In an OPEN cell (every other) a SELF-REFUTED or DRIFT row (`YIELD_EXCUSED`) no longer needs one by itself;
every other mechanism verdict (refuted, the operator's, diagnosed, trial-adjusted, stress, a failed mechanism test)
still does, and a card matching one is checked exactly as above (its claim may name any row it matches, and the
refusal points at the newest row that needs the claim). Nothing else moves: `MECHANISM_VERDICTS` and the rows indexed
(the memory lane's judge reads them), the matching, a claim's tests, both rebirth budgets, the architect's same-slice
and same-idea refusals, its lineage rules and the card's completeness. A proposal that needed no claim but carries one
is a rebirth only when that claim passes every test above; otherwise it is born without the claim (the architect strips
it before the card is stored and the birth's event says why), so no unchecked claim ever links a lineage or spends a
budget. Drift-screen figures are Train figures: no Validation or holdout figure is read.

THE DIRECTION LANE (release D-1, Oct 9, 2026; league/swarm/dlane.py; PLAN D2, HARNESS 2.1 and C2). While `dlane.mode` is
not "off" a card declares its lane: `lane` "alpha" (the default, and every card without the field, so every card born
before) or "direction". `validate` reads it and checks a direction card against the lane's box with the proposal's own
structure and roots (`dlane.card_errors`: class `equity_premium` or `trend_momentum`, a direction structure, the lane's
roots and holdings, a real ablation switch and never a flat comparison), every reason named; a lane that is neither word
is refused. `equity_premium` (`LANE_CLASSES`, its sentence `dlane.EQUITY_PREMIUM`) is a card word only while the lane is on
(`mechanism_classes`, `vocabulary_text`) and only on a direction card: `MECHANISM_CLASSES` itself is unchanged, so the
vocabulary, the cells and every reader of the eleven classes stay as they were. The lane is stored ONLY on a direction
card (`"lane": "direction"`, inside its canonical JSON and so its sha; a fork or a game child reads it through the
sha): an alpha card's canonical JSON, and so its sha, is byte for byte the release before's. A DRIFT row never binds a
direction card (`RebirthIndex.needs_claim`: the drift screen charges the profit of exposure, and in the direction lane that
profit is what counts, reported beside the same-risk buy-and-hold); every other mechanism verdict of a DIRECTION family
binds direction cards (since Oct 9 an alpha family's row binds none: the next section), and direction rows bind alpha
cards as any row does. A claim a direction card makes on a DRIFT row anyway is a
rebirth only when it holds, and then spends the row's and the cell's rebirth budgets (such an idea returns once each, as
`architect.max_rebirths_per_row` allows); one that does not hold is stripped before the card is stored (`dropped`), as in
an open cell. The BIRTH CELLS gain the lane's own cells (`equity_premium / directional / <each of the lane's holdings>`),
so a pass the old cells would have closed still asks for direction cards. Its cost (HARNESS 7.4): direction ideas the
drift screen buried may be born again, once each within the rebirth budgets. With `dlane.mode` "off" none of this acts:
`lane` is ignored as any unknown key is, and the vocabulary, the cells and every check are the release before's.

THE DIRECTION LANE'S GRAVEYARD (Oct 9, 2026; the operator's decision after the House's architect pass of 11:32Z, A
REPORTED LOOSENING). WHY: with D-1 live (10:37Z, main 2b60d94a) direction cards were refused by alpha rows. The live
refusal of low-iv-drift-call (and of calm-trend-drift-call alike): "its cell (equity_premium / directional / days_4_10 /
clock+implied_vol+underlying_price), and the trend_momentum cell its own mechanism text reads as, hold 15 graveyard
row(s) killed by a mechanism verdict, the newest persistent-ceiling-rejection-put (REFUTED) of the 7 that need a claim".
Those verdicts judged timing edges against drift under the alpha rules; they say nothing about a direction program,
which is judged as labelled beta by direction-v2, and the direction lane has its own multiplicity control (one
Validation try and one holdout look per lineage; D2's false-positive rate measured per program). THE RULE: while the
lane is on, a DIRECTION card is bound only by the graveyard rows of DIRECTION families (`RebirthIndex.binds_direction`,
`needs_claim`). A row's lane is read the way D-1 stores it (`row_lane`): its family's spec's `lane`, else its card's,
else, for a fork without a card of its own, the card its spec's `card_sha` names; a family with none of these is alpha.
A DRIFT row still never binds a direction card. A direction family's row with any other mechanism verdict binds as
before, through the whole rebirth claim (a valid `rebirth`, the row's and the cell's budgets). An alpha family's row
is still MATCHED (so a claim a direction card makes on one is checked, as on a DRIFT row: a rebirth only when it
holds, spending the budgets, else `dropped`), and `check` counts such rows (`alpha_rows`). Alpha cards are judged
exactly as before: every row binds them, a direction family's included. The architect's view follows the rule: the
LANES block says it (architect.py `lanes_block`), each BIRTH CELLS line of a cell a direction card may be declared in
(`direction_cells`) says how many of its rows bind a direction card (`cells`), and `bearable` (so `Architect.closed`)
reads a cell whose rows bind no direction card as one a direction card can bear. ITS COST: more direction births may
retry ideas similar to dead alpha ones (a call that rents a calm trend reads as the trend_momentum cell's dead timing
edges); each such lineage still gets one Validation try and one holdout look, at D2's measured false-positive rate of
10.4% per program on mixed worlds. With `dlane.mode` "off" nothing here acts (no row carries a lane, and a direction
card, which the architect never admits then, is read as D-1 read it).

THE ALWAYS-IN CARD (Oct 10, 2026; dlane.py's section of that name; A REPORTED LOOSENING). WHY: by Oct 10 the lane's cells
held 22-43 rows refuted on Train, every one a gated idea (an implied-vol, term-structure, trend or open-interest gate).
An always-in card (it enters on the clock alone: the lane's own instrument) shares the clock with those rows, so it
matched them, and it could make no rebirth claim (a claim adds an input the dead row did not read, and it reads only the
clock): the lane's own instrument could not be born, and the Probe roster could not fill. THE RULE, in `check`'s
direction path only (`matches`, `matched`, `text_cell` and every other reader of them are unchanged: an alpha card, a
legacy row and a gated direction card are judged exactly as before): while the lane is on, a DIRECTION card whose
DECLARED inputs are exactly ["clock"] (`dlane.always_in`: the card's field, never its words) is bound only by the
ALWAYS-IN direction rows on its roots (`always_in_rows`), whatever their class or holding, and by no other row; a row is
always-in when its family is a direction family (`row_lane`) whose DECLARED card (its own, else a fork's by its spec's
`card_sha`) is always-in, whatever its words say, and whose program never failed G1 (`_g1_failed`: such a family lost
the status, however it died) (`row["always_in"]`). Such a row is bound under `needs_claim` (a DRIFT
row never binds a direction card) and no claim frees it (the card reads nothing a claim could add), so the always-in
idea on a root is refused once a mechanism verdict killed it there (a SELF-REFUTED one too: the yield's open cell aside).
A claim an always-in card carries anyway is never a rebirth: it is `dropped`. The refusal names the row and the roots.
The view follows: the BIRTH CELLS end with the ALWAYS-IN line (`always_in_line`: each lane root open, bound by an
always-in row, or with its always-in lineage's try spent or claimed, which the architect reads), and `Architect.closed`
reads a lane root still open to an always-in birth as a pass that can bear one. What else binds it: the ration (one
Validation try a connected lineage, and its birth links it to every always-in lineage on its roots: architect.py
`admit`) and G1 (dlane.py: a program that does not behave always-in on Train is never validated and retires). ITS COST:
the dlane report's LOOSENED row. With the lane off nothing here acts.

Standard library only.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping

from . import dlane
from . import evidence as evidence_mod

#: The mechanism classes, each with the sentence the architect reads. Drawn from the graveyard's 1,974 rows (Sept 30):
#: every recurring mechanism there fits one.
MECHANISM_CLASSES: dict[str, str] = {
    "volatility_risk_premium": "implied volatility above the realized volatility that follows: selling premium is paid "
                               "for bearing variance risk",
    "volatility_underpricing": "implied volatility below the move that follows (compression before expansion, jumps the "
                               "surface smooths): owning convexity",
    "event_premium": "a scheduled event (FOMC, CPI, payrolls, earnings, auctions, expiration) whose variance or drift is "
                     "mispriced",
    "trend_momentum": "continuation: slow-moving capital, underreaction or trend-following flows extend a move",
    "reversal_liquidity": "reversal: forced or liquidity-demanding flow pushes price from value, and the side that absorbs "
                          "it is paid",
    "relative_value": "lead-lag or relative value across roots: one root's move predicts another's, or a spread between "
                      "related roots closes",
    "term_structure": "the implied volatility term structure (front against back expiries) is mispriced",
    "skew": "the implied volatility skew (puts against calls, wings against the center) is mispriced",
    "calendar_flow": "a clocked flow: time of day, day of week, the weekend, month or quarter end, index or benchmark "
                     "rebalancing",
    "pinning_gamma": "dealer hedging around large open interest or expiry pins or accelerates price",
    "dispersion": "index volatility against its constituents' (implied correlation) is mispriced",
}
#: THE DIRECTION LANE's own class (dlane.py; HARNESS 6.2), with the sentence the architect reads: a card word only while
#: the lane is on and only on a direction card (`mechanism_classes`). Never added to MECHANISM_CLASSES, whose eleven classes
#: every other reader (the cells, the memory judge, the yields) keeps.
LANE_CLASSES: dict[str, str] = {"equity_premium": dlane.EQUITY_PREMIUM}
#: What a program may condition on (the contract's ctx), each with its sentence.
INPUTS: dict[str, str] = {
    "underlying_price": "the root's price path (ctx.underlyings: prices, closes, highs, lows)",
    "realized_vol": "realized volatility computed from the price path",
    "implied_vol": "the level of implied volatility (the chain's iv)",
    "iv_term_structure": "implied volatility across expiries",
    "iv_skew": "implied volatility across strikes",
    "option_liquidity": "quotes' spreads and sizes",
    "open_interest": "open interest",
    "share_volume": "share volume (unknown in history without first-observation receipts: see INPUT AVAILABILITY)",
    "event_calendar": "the event calendar (ctx.events, ctx.events_next)",
    "clock": "the minute of the day and the weekday",
    "cross_asset": "another root's price or volatility",
}
#: The expected holding horizon's buckets.
HOLDING: dict[str, str] = {
    "intraday": "opened and closed in one session",
    "days_1_3": "one to three sessions",
    "days_4_10": "four to ten sessions",
    "days_11_plus": "more than ten sessions (to expiry)",
}
#: The twelve structures by the exposure they buy or sell: a new structure in the same group is not a new idea.
STRUCTURE_FAMILIES: dict[str, str] = {
    "long_call": "directional", "long_put": "directional", "long_single": "directional", "debit_vertical": "directional",
    "credit_vertical": "short_premium", "iron_condor": "short_premium", "iron_butterfly": "short_premium",
    "long_straddle": "long_volatility", "long_strangle": "long_volatility",
    "long_butterfly": "butterfly",
    "calendar": "time_spread", "diagonal": "time_spread",
}
#: Structures that may not declare a flat comparison although their family is not directional: a credit vertical sells
#: premium on one side only, so it carries the market's drift, and a one-sample test against zero would pass on it.
FLAT_REFUSED = frozenset({"credit_vertical"})
#: The graveyard tags that record a finding about the mechanism (architect.tag_of). Not IDLE (untested), THIN (activity),
#: EXHAUSTED (it reached a score), UNRESOLVED (an experiment failure), STALL (the tournament's clock) or OPERATOR-RETIRED
#: (housekeeping).
MECHANISM_VERDICTS = ("OPERATOR", "REFUTED", "SELF-REFUTED", "DIAGNOSED", "TRIALS", "DRIFT", "STRESS", "MECHANISM")
#: The mechanism verdicts a cell's yield may excuse (THE CELL'S YIELD in the module docstring): a family's own outcome
#: (its researcher's retirement, or its Train record failing the drift screen), not a test of the mechanism.
YIELD_EXCUSED = ("SELF-REFUTED", "DRIFT")
#: `architect.cell_yield` switched on with `true` or `{}`, and each key a mapping leaves out or misstates: at least 30
#: settled births in a cell over 7 days, and a Wilson 95% upper bound on their drift-pass share below 10%.
CELL_YIELD_DEFAULTS = {"min_births": 30, "floor": 0.10, "lookback_days": 7}
#: The Wilson bound's z (two-sided 95%).
WILSON_Z = 1.959963984540054
#: The ablation when a card names none: the contract's convention (1,176 of the House's 2,003 latest programs, Sept 30).
DEFAULT_ABLATION = {"param": "signal_on", "off": 0}
#: Field limits (characters after whitespace is collapsed).
LIMITS = {"hypothesis": (60, 600), "comparison": (30, 400), "falsification": (40, 400), "why": (20, 300),
          "different": (40, 400), "evidence": (40, 400)}
MAX_INPUTS = 6
_PARAM = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,39}$")
#: A falsification names a result: a figure or a comparison.
_CONCRETE = re.compile(r"\d|\b(?:below|above|under|over|less|more|fails?|loses?|negative|zero|not beat|no better|worse|"
                       r"exceeds?|matches?|equal)\b", re.I)
_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset("a an and are as at be by for from in into is it its of on or than that the their then this to when with "
                  "not no same new other now also only instead more less very just still again which while".split())
#: Words that say only a new structure, root or horizon (not a mechanism-level change): `RebirthIndex.check` discounts
#: them from a rebirth's `different` (the architect's rule: "a re-tune, a new root, a new structure or a new horizon of a
#: refuted mechanism is not a difference").
_SURFACE = frozenset("long short call calls put puts single debit credit vertical verticals iron condor condors butterfly "
                     "butterflies straddle straddles strangle strangles calendar diagonal spread spreads structure leg legs "
                     "intraday day days session sessions week weeks month months expiry expiries dte horizon hold holding "
                     "root roots ticker tickers etf etfs index width wider narrower strike strikes delta one two three four "
                     "five six ten".split())

#: The card tables, one statement each: `ensure` runs them through the store's `_exec`, never `executescript` (which would
#: commit a caller's open transaction first).
CARDS_SQL = (
    "CREATE TABLE IF NOT EXISTS family_cards (family TEXT PRIMARY KEY, sha TEXT NOT NULL, card TEXT NOT NULL, "
    "key TEXT NOT NULL, at TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS family_cards_sha ON family_cards(sha)",
    "CREATE TRIGGER IF NOT EXISTS family_cards_no_update BEFORE UPDATE ON family_cards "
    "BEGIN SELECT RAISE(ABORT, 'family cards are immutable'); END",
    "CREATE TRIGGER IF NOT EXISTS family_cards_no_delete BEFORE DELETE ON family_cards "
    "BEGIN SELECT RAISE(ABORT, 'family cards are immutable'); END",
    "CREATE TABLE IF NOT EXISTS card_evidence (seq INTEGER PRIMARY KEY AUTOINCREMENT, family TEXT NOT NULL, "
    "card_sha TEXT NOT NULL, version INTEGER, at TEXT NOT NULL, kind TEXT NOT NULL, verdict TEXT NOT NULL, detail TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS card_evidence_family ON card_evidence(family, seq)",
    "CREATE TRIGGER IF NOT EXISTS card_evidence_no_update BEFORE UPDATE ON card_evidence "
    "BEGIN SELECT RAISE(ABORT, 'card evidence is append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS card_evidence_no_delete BEFORE DELETE ON card_evidence "
    "BEGIN SELECT RAISE(ABORT, 'card evidence is append-only'); END",
)


# ----------------------------------------------------------------------------------------------------------- the lanes
def mechanism_classes(settings: Mapping[str, Any] | None = None) -> dict[str, str]:
    """The classes a card may name now: `MECHANISM_CLASSES` itself (the same object) while the direction lane is off, else
    with the lane's own classes that `dlane.classes` allows (`LANE_CLASSES`: a direction card's only)."""
    if not dlane.on(settings):
        return MECHANISM_CLASSES
    allowed = dlane.cfg(settings)["classes"]
    return {**MECHANISM_CLASSES, **{k: v for k, v in LANE_CLASSES.items() if k in allowed}}


def lane_of_card(card: Any) -> str | None:
    """"direction" for a direction card (the only lane a card stores: `validate`), else None (an alpha card, a card from
    before the lane, or none)."""
    return dlane.DIRECTION if isinstance(card, Mapping) and card.get("lane") == dlane.DIRECTION else None


def lane_cells(settings: Mapping[str, Any] | None, families: Iterable[str]) -> list[tuple[str, str, str]]:
    """THE DIRECTION LANE's own birth cells (class, structure family, holding): its classes of `LANE_CLASSES` by its
    holdings, in the directional family, while the lane is on and `families` holds that family; [] otherwise."""
    if not dlane.on(settings) or "directional" not in set(families):
        return []
    c = dlane.cfg(settings)
    return [(k, "directional", h) for k in LANE_CLASSES if k in c["classes"] for h in c["holding"] if h in HOLDING]


def direction_cells(settings: Mapping[str, Any] | None) -> set[tuple[str, str, str]]:
    """THE DIRECTION LANE'S GRAVEYARD (Oct 9, 2026): every cell a direction card may be declared in (the lane's classes,
    `trend_momentum` included, by its holdings, in the directional family: `dlane.card_errors`' box) while the lane is
    on; empty otherwise. Their BIRTH CELLS lines say how many rows bind a direction card (`RebirthIndex.cells`)."""
    if not dlane.on(settings):
        return set()
    c = dlane.cfg(settings)
    return {(k, "directional", h) for k in c["classes"] for h in c["holding"]}


def row_lane(fam: Mapping[str, Any] | None, card: Any, lanes_by_sha: Mapping[str, str]) -> str:
    """THE DIRECTION LANE'S GRAVEYARD (Oct 9, 2026): a graveyard row's lane, read the way release D-1 stores it
    (`dlane.declared_lane`, from rows already in hand): its family's spec's `lane`, else its own card's (`card`), else
    (a fork) the card its spec's `card_sha` names (`lanes_by_sha`: each stored card's lane by sha), else "alpha": every
    family born before the lane, or without a lane, is alpha."""
    raw = fam.get("spec") if isinstance(fam, Mapping) else None
    try:
        spec = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        spec = None
    spec = spec if isinstance(spec, Mapping) else {}
    if spec.get("lane") in dlane.LANES:
        return str(spec["lane"])
    if isinstance(card, Mapping):
        return dlane.lane_value(card)[0]
    return lanes_by_sha.get(str(spec.get("card_sha") or ""), dlane.ALPHA)


# ----------------------------------------------------------------------------------------------------------- the schema
def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _token(value: Any) -> str:
    return re.sub(r"[\s\-]+", "_", str(value or "").strip().lower())


def _sized(card: dict[str, Any], errors: list[str], raw: Mapping[str, Any], name: str, *, label: str | None = None) -> None:
    lo, hi = LIMITS[name]
    text = _text(raw.get(name))
    if len(text) < lo:
        errors.append(f"{label or name}: at least {lo} characters ({'missing' if not text else f'{len(text)} given'})")
    else:
        card[name] = text[:hi]


def validate(raw: Any, structure: Any = None, *, roots: Any = None,
             settings: Mapping[str, Any] | None = None) -> tuple[dict[str, Any] | None, list[str]]:
    """(the canonical card, []) or (None, every problem named). The card's fields are the module docstring's; `ablation`
    defaults to `DEFAULT_ABLATION` (a flat one, `{"flat": true}`, only for a `structure` `flat_allowed` admits), and
    `rebirth` is kept only when given (its rows are checked by `RebirthIndex`). THE DIRECTION LANE (`settings`' `dlane`;
    `roots`, the proposal's): while the lane is on, `lane` is read and a direction card is checked against the lane's box
    (`dlane.card_errors`) and keeps `"lane": "direction"`; an alpha card never stores its lane. With the lane off (or no
    settings) `lane` is ignored, as every unknown key is: the card and every message are the release before's."""
    if not isinstance(raw, Mapping):
        return None, ["card: missing (every family needs one: hypothesis, mechanism_class, inputs, holding, cost, comparison, "
                      "ablation, falsification)"]
    errors: list[str] = []
    card: dict[str, Any] = {}
    lane = None
    if dlane.on(settings):
        lane, problem = dlane.lane_value(raw)
        if problem:
            errors.append(problem)
    _sized(card, errors, raw, "hypothesis")
    classes = mechanism_classes(settings)
    cls = _token(raw.get("mechanism_class"))
    if cls in classes and (cls not in LANE_CLASSES or lane == dlane.DIRECTION):
        card["mechanism_class"] = cls
    elif cls in classes:
        errors.append(f"mechanism_class: {cls} is the direction lane's class: a card that names it declares \"lane\": "
                      "\"direction\"")
    else:
        errors.append(f"mechanism_class: {raw.get('mechanism_class')!r} is not one of {', '.join(classes)}")
    inputs = raw.get("inputs")
    if isinstance(inputs, str):  # "underlying_price, clock": a model's list written as text
        inputs = [x for x in re.split(r"[,;/+|]", inputs) if x.strip()]
    names = [_token(x) for x in inputs] if isinstance(inputs, list) else []
    unknown = [n for n in names if n not in INPUTS]
    if not names:
        errors.append(f"inputs: a list of one to {MAX_INPUTS} of {', '.join(INPUTS)}")
    elif unknown:
        errors.append(f"inputs: {', '.join(unknown)} not in {', '.join(INPUTS)}")
    elif len(set(names)) > MAX_INPUTS:
        errors.append(f"inputs: at most {MAX_INPUTS}")
    else:
        card["inputs"] = sorted(set(names))
    holding = _token(raw.get("holding"))
    if holding in HOLDING:
        card["holding"] = holding
    else:
        errors.append(f"holding: {raw.get('holding')!r} is not one of {', '.join(HOLDING)}")
    cost = raw.get("cost")
    if not isinstance(cost, Mapping):
        errors.append("cost: {\"hurdle\": the round trip's spread and fees as a fraction of maximum loss (0-1), \"why\": how}")
    else:
        hurdle = cost.get("hurdle")
        ok = isinstance(hurdle, (int, float)) and not isinstance(hurdle, bool) and 0.0 < float(hurdle) <= 1.0
        if not ok:
            errors.append(f"cost.hurdle: a fraction of maximum loss above 0 and at most 1 ({hurdle!r} given)")
        why = _text(cost.get("why"))
        if len(why) < LIMITS["why"][0]:
            errors.append(f"cost.why: at least {LIMITS['why'][0]} characters")
        if ok and len(why) >= LIMITS["why"][0]:
            card["cost"] = {"hurdle": round(float(hurdle), 4), "why": why[:LIMITS["why"][1]]}
    _sized(card, errors, raw, "comparison")
    ablation = raw.get("ablation")
    if ablation is None:
        card["ablation"] = dict(DEFAULT_ABLATION)
    elif ablation == "flat" or (isinstance(ablation, Mapping) and ablation.get("flat") is True):
        if structure is not None and not flat_allowed(structure):
            errors.append(f"ablation: a flat comparison is only for a structure that is not directional ({structure} is "
                          "directional or carries the market's drift): its comparison is the same structure without the signal's condition "
                          "(default {\"param\": \"signal_on\", \"off\": 0})")
        else:
            card["ablation"] = {"flat": True}
    else:
        param = str(ablation.get("param") or "") if isinstance(ablation, Mapping) else ""
        off = ablation.get("off") if isinstance(ablation, Mapping) else None
        scalar = isinstance(off, (bool, int, str)) or (isinstance(off, float) and off == off and abs(off) != float("inf"))
        if not _PARAM.match(param) or not scalar or (isinstance(off, str) and len(off) > 40):
            errors.append("ablation: {\"param\": the PARAMS key that switches the signal, \"off\": the value that turns it "
                          "into the comparison} (default {\"param\": \"signal_on\", \"off\": 0}; {\"flat\": true} when the "
                          "structure itself is the edge and is not directional)")
        else:
            if isinstance(off, float) and off.is_integer():
                off = int(off)
            card["ablation"] = {"param": param, "off": off}
    _sized(card, errors, raw, "falsification")
    if "falsification" in card and not _CONCRETE.search(card["falsification"]):
        errors.append("falsification: name a concrete result (a figure or a comparison) that would kill it")
        card.pop("falsification")
    rebirth = raw.get("rebirth")
    if rebirth is not None:
        if not isinstance(rebirth, Mapping) or not str(rebirth.get("row") or "").strip():
            errors.append("rebirth: {\"row\": the graveyard id it re-enters, \"different\": what changed, \"evidence\": the new "
                          "evidence}")
        else:
            reb: dict[str, Any] = {"row": str(rebirth["row"]).strip()[:80]}
            _sized(reb, errors, rebirth, "different", label="rebirth.different")
            _sized(reb, errors, rebirth, "evidence", label="rebirth.evidence")
            if len(reb) == 3:
                card["rebirth"] = reb
    if lane == dlane.DIRECTION:
        # THE DIRECTION LANE: inside the lane's box or refused, every reason named (the lane's reason for a field replaces
        # the general one, so a refusal stays inside what the next request quotes); the lane is part of the card (its sha).
        boxed = dlane.card_errors(raw, structure, roots, settings)
        fields = {e.split(":", 1)[0] for e in boxed}
        errors = [e for e in errors if e.split(":", 1)[0] not in fields] + boxed
        card["lane"] = dlane.DIRECTION
    return (card, []) if not errors else (None, errors)


def canonical(card: Mapping[str, Any]) -> str:
    return json.dumps(card, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def card_sha(card: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical(card).encode("utf-8")).hexdigest()[:24]


def structure_family(structure: Any) -> str:
    return STRUCTURE_FAMILIES.get(str(structure), str(structure))


def flat_allowed(structure: Any) -> bool:
    """May a card on this structure declare a flat comparison: not a directional structure, nor one in `FLAT_REFUSED`."""
    return structure_family(structure) != "directional" and str(structure) not in FLAT_REFUSED


def key_of(card: Mapping[str, Any], structure: Any) -> dict[str, Any]:
    """A card's cell: {class, inputs, family, holding}."""
    return {"class": card.get("mechanism_class"), "inputs": sorted(card.get("inputs") or []),
            "family": structure_family(structure), "holding": card.get("holding")}


def key_text(key: Mapping[str, Any]) -> str:
    inputs = "+".join(key.get("inputs") or []) or "?"
    return f"{key.get('class')} / {key.get('family')} / {key.get('holding')} / {inputs}"


# ----------------------------------------------------------------------------------------------------------- storage
def ensure(store: Any) -> bool:
    """Create the card tables on the store's connection (idempotent). False on a read-only store, which may still read
    them when a writer made them."""
    if getattr(store, "readonly", False):
        return False
    if getattr(store, "_cards_ready", False):
        return True
    with store.lock:
        inside = bool(store._db.in_transaction)
        for statement in CARDS_SQL:
            store._exec(statement)
        # Inside a caller's transaction the tables exist only if it commits: remember them only when they are durable.
        if not inside:
            store._cards_ready = True
    return True


def _tables(store: Any) -> bool:
    if ensure(store):
        return True
    return bool(store._one("SELECT 1 AS ok FROM sqlite_master WHERE type='table' AND name='family_cards'"))


def put(store: Any, fid: str, card: Mapping[str, Any], structure: Any) -> str:
    """Store a family's card once (the sha). A second card for the same family is refused by the table."""
    ensure(store)
    sha = card_sha(card)
    store._exec("INSERT INTO family_cards(family, sha, card, key, at) VALUES(?,?,?,?,?)",
                (fid, sha, canonical(card), canonical(key_of(card, structure)), store.now()))
    return sha


def card_of(store: Any, fid: str) -> dict[str, Any] | None:
    """The family's card: its own row, else (a fork) the card its spec's `card_sha` names. {card, sha, key, own} or None."""
    if not _tables(store):
        return None
    row = store._one("SELECT family, sha, card, key FROM family_cards WHERE family=?", (fid,))
    own = row is not None
    if row is None:
        fam = store._one("SELECT spec FROM families WHERE id=?", (fid,))
        try:
            sha = (json.loads(fam["spec"]) or {}).get("card_sha") if fam else None
        except (TypeError, ValueError):
            sha = None
        row = store._one("SELECT family, sha, card, key FROM family_cards WHERE sha=? ORDER BY at LIMIT 1", (sha,)) if sha else None
    if row is None:
        return None
    return {"card": json.loads(row["card"]), "sha": row["sha"], "key": json.loads(row["key"]), "own": own,
            "family": row["family"]}


def add_evidence(store: Any, fid: str, sha: str, version: int | None, kind: str, verdict: str, detail: Mapping[str, Any]) -> int:
    ensure(store)
    cur = store._exec("INSERT INTO card_evidence(family, card_sha, version, at, kind, verdict, detail) VALUES(?,?,?,?,?,?,?)",
                      (fid, sha, None if version is None else int(version), store.now(), str(kind), str(verdict),
                       canonical(detail)))
    return int(cur.lastrowid or 0)


def evidence(store: Any, fid: str, *, kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    if not _tables(store):
        return []
    sql, args = "SELECT * FROM card_evidence WHERE family=?", [fid]
    if kind:
        sql, args = sql + " AND kind=?", args + [kind]
    rows = store._all(sql + " ORDER BY seq DESC LIMIT ?", (*args, int(limit)))
    for r in rows:
        r["detail"] = json.loads(r["detail"])
    return list(reversed(rows))


# ------------------------------------------------------------------------------------------ the prompts' words
def vocabulary_text(settings: Mapping[str, Any] | None = None) -> str:
    """The card's vocabularies as the architect reads them (THE DIRECTION LANE's class too while the lane is on, marked as
    the lane's: `mechanism_classes`)."""
    lines = ["MECHANISM CLASSES:"] + [f"- {k}: {v}" + (" (a direction card's class only)" if k in LANE_CLASSES else "")
                                      for k, v in mechanism_classes(settings).items()]
    lines += ["INPUTS:"] + [f"- {k}: {v}" for k, v in INPUTS.items()]
    lines += ["HOLDING:"] + [f"- {k}: {v}" for k, v in HOLDING.items()]
    lines += ["STRUCTURE FAMILIES (a new structure in the same group is not a new idea): "
              + "; ".join(f"{g}: {', '.join(s for s, x in STRUCTURE_FAMILIES.items() if x == g)}"
                          for g in dict.fromkeys(STRUCTURE_FAMILIES.values()))]
    return "\n".join(lines)


def brief_text(entry: Mapping[str, Any] | None, settings: Mapping[str, Any] | None = None) -> str:
    """A family's card as its researcher reads it ("" for a family born before cards). THE DIRECTION LANE: a direction
    card's lane is named while the lane is on (`settings`; without them, or with the lane off, the brief is the release
    before's: the family is then judged as alpha, `dlane.lane_of`)."""
    if not entry:
        return ""
    c = entry["card"]
    ab = c.get("ablation") or DEFAULT_ABLATION
    if ab.get("flat"):
        switch = ("- Comparison mode: flat (your structure itself is the edge): the mechanism test runs your program alone, and its "
                  "entries must earn more than nothing after the Gym's spread and fees.")
    else:
        switch = (f"- Ablation: PARAMS[{ab['param']!r}] = {ab['off']!r} must turn your signal into that comparison: skip ONLY the "
                  "signal's condition and keep the structure, tenor, strikes, entry time, sizing and exits, so the program still "
                  f"trades (the test checks that both arms trade the same structure, tenor, strikes, time and hold). Declare "
                  f"{ab['param']!r} in PARAMS (default on) and read it in decide.")
    lines = ["YOUR FAMILY CARD (fixed at birth; you research and are judged under it):",
             f"- Hypothesis: {c.get('hypothesis')}",
             f"- Mechanism class: {c.get('mechanism_class')}. Inputs: {', '.join(c.get('inputs') or [])}. Holding: "
             f"{c.get('holding')} ({HOLDING.get(str(c.get('holding')), '')}).",
             f"- Cost hurdle (your estimate; the Gym's fills already charge it): about {c.get('cost', {}).get('hurdle')} of "
             f"maximum loss a round trip ({c.get('cost', {}).get('why')}).",
             f"- Comparison it must beat: {c.get('comparison')}", switch,
             f"- Falsification: {c.get('falsification')}"]
    reb = c.get("rebirth")
    if reb:
        lines.append(f"- Reborn from graveyard row {reb['row']}: different: {reb['different']} Evidence: {reb['evidence']}")
    if lane_of_card(c) == dlane.DIRECTION and dlane.on(settings):
        lines.insert(1, "- Lane: DIRECTION (fixed at birth): profit from the index's direction counts in it, judged by the "
                        f"direction objective ({dlane.OBJECTIVE}: YOUR LANE in your brief) and reported beside the same-risk "
                        f"buy-and-hold; {dlane.ALWAYS_IN_NOTE}.")
        if dlane.always_in(c):  # THE ALWAYS-IN CARD (Oct 10, 2026): its status is a promise about the program
            lines.insert(2, "- ALWAYS-IN (your card's declared inputs are the clock alone, fixed at birth): your program "
                            "enters on the clock alone, every session its own open positions allow, with no gate of any "
                            "kind; the lane's advice to find a regime gate is not for this family, which was born because "
                            "no gated idea's graveyard row binds an always-in card. Every Train run is checked (G1): on each "
                            "root it trades it must enter on at least "
                            f"{dlane.ALWAYS_IN_SHARE:.0%} of the sessions it holds nothing there at the open, or the version "
                            "is ineligible and the family retires before Validation. Its one Validation try is shared with "
                            "every always-in family on its roots.")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------ legacy rows (before cards)
_CLASS_WORDS: dict[str, re.Pattern[str]] = {
    "event_premium": re.compile(r"\b(?:fomc|cpi|payrolls?|jobs report|nfp|earnings|auctions?|opex|pce|ppi|macro releases?|"
                                r"scheduled|announcements?|events?)\b", re.I),
    "term_structure": re.compile(r"\b(?:term structure|front[- ](?:month|expiry|week)|back[- ]month|calendar spread|contango|"
                                 r"backwardation|tenor)\b", re.I),
    "skew": re.compile(r"\b(?:skew\w*|risk reversal|wings?|smile|put[- ]call (?:iv|vol\w*))\b", re.I),
    "dispersion": re.compile(r"\b(?:dispersion|implied correlation)\b", re.I),
    "pinning_gamma": re.compile(r"\b(?:pin\w*|gamma|dealer hedg\w*|charm|max pain)\b", re.I),
    "volatility_risk_premium": re.compile(r"\b(?:variance risk premium|volatility risk premium|vrp|rich (?:premium|iv|implied)|"
                                          r"sell\w* (?:premium|vol\w*)|theta|decay|overpric\w*|harvest\w*)\b", re.I),
    "volatility_underpricing": re.compile(r"\b(?:underpric\w*|cheap (?:vol\w*|iv|implied|convexity|options?)|compression|"
                                          r"squeeze|expansion|jumps?|convexity|realized (?:vol\w* )?(?:above|exceeds))\b", re.I),
    "calendar_flow": re.compile(r"\b(?:month[- ]end|quarter[- ]end|turn of the month|weekends?|mondays?|fridays?|day of (?:the )?week|"
                                r"time of day|overnight|last hour|first hour|closing auction|rebalanc\w*|window dressing|"
                                r"benchmark|settlement window)\b", re.I),
    "relative_value": re.compile(r"\b(?:lead\w*|lag\w*|relative (?:value|strength|return)|pairs?|ratio|residual|diverge\w*|"
                                 r"rotation|catch[- ]up|cross[- ]asset)\b", re.I),
    "trend_momentum": re.compile(r"\b(?:momentum|trend\w*|continu\w*|breakout|drift|underreact\w*|follow[- ]through|"
                                 r"persist\w*|extends?)\b", re.I),
    "reversal_liquidity": re.compile(r"\b(?:revers\w*|rebound\w*|mean[- ]revert\w*|revert\w*|overreact\w*|oversold|overbought|"
                                     r"capitulation|forced|liquidity|exhaust\w*|fade\w*|gap fill|snap ?back|bounce\w*|dip)\b", re.I),
}
#: Ties go to the more specific class (this order).
_CLASS_ORDER = tuple(_CLASS_WORDS)
_HOLDING_WORDS = (("days_11_plus", re.compile(r"\b(?:two weeks|weeks|months?|30[- ]45|multi[- ]week|to expiry)\b", re.I)),
                  ("days_4_10", re.compile(r"\b(?:a week|week|five sessions|several (?:sessions|days)|4[- ]10|few days)\b", re.I)),
                  ("days_1_3", re.compile(r"\b(?:next (?:session|day|morning)|overnight|one to three|1[- ]3|two sessions|"
                                          r"following (?:session|day)|a day or two)\b", re.I)),
                  ("intraday", re.compile(r"\b(?:intraday|same[- ]day|by the close|into the close|0[- ]?dte|end of day|"
                                          r"within the (?:day|session))\b", re.I)))


def infer_key(mechanism: Any, structure: Any, dte: Any = None) -> dict[str, Any] | None:
    """A graveyard row's cell read from its mechanism text (a row from before cards): the class with the most keyword hits
    (ties to the more specific), the holding named in the text (else from the days to expiry), the structure's family.
    None when no class word is found. `inputs` is None: prose does not say reliably what a program read."""
    text = str(mechanism or "")
    hits = {c: len(p.findall(text)) for c, p in _CLASS_WORDS.items()}
    best = max(hits.values()) if hits else 0
    if best <= 0:
        return None
    cls = next(c for c in _CLASS_ORDER if hits[c] == best)
    holding = next((h for h, p in _HOLDING_WORDS if p.search(text)), None)
    if holding is None:
        try:
            hi = int(max(dte)) if isinstance(dte, (list, tuple)) and dte else None
        except (TypeError, ValueError):
            hi = None
        holding = ("intraday" if hi is not None and hi <= 0 else "days_1_3" if hi is not None and hi <= 5
                   else "days_4_10" if hi is not None and hi <= 14 else "days_11_plus" if hi is not None else "days_1_3")
    return {"class": cls, "inputs": None, "family": structure_family(structure), "holding": holding}


def match_inputs(card: Mapping[str, Any], mechanism: Any = "") -> list[str]:
    """The inputs a proposal is matched on: its declared inputs and those its own mechanism text and hypothesis name
    (`infer_inputs`). Declared inputs are never checked against the program, so the words the proposal writes count too:
    declaring inputs that avoid a dead card's while the text reads the same information never escapes it."""
    text = f"{mechanism or ''} {card.get('hypothesis') or ''}"
    return sorted(set(card.get("inputs") or []) | set(infer_inputs(text)))


def match_keys(card: Mapping[str, Any], structure: Any, mechanism: Any = "", dte: Any = None) -> tuple[list[dict[str, Any]], str | None]:
    """The keys a card is matched on (the rebirth refusal's and the mechanism test's notion of the same hypothesis): its
    declared cell, and the cell of the class its own mechanism text reads as (`infer_key`) when that is another class, each
    with `match_inputs`. (keys, that other class or None)."""
    key = {**key_of(card, structure), "inputs": match_inputs(card, mechanism)}
    text = infer_key(mechanism, structure, dte) if mechanism else None
    if text is not None and text["class"] != key["class"]:
        return [key, {**key, "class": text["class"]}], text["class"]
    return [key], None


def matches(new: Mapping[str, Any], dead: Mapping[str, Any]) -> bool:
    """Does a proposal's cell `new` fall in a dead row's cell `dead`: the same class, structure family and holding, and (a
    carded row, when the proposal's inputs are known) inputs that overlap the dead card's. A legacy row (`inputs` None)
    matches on the first three."""
    if (new.get("class"), new.get("family"), new.get("holding")) != (dead.get("class"), dead.get("family"), dead.get("holding")):
        return False
    if dead.get("inputs") is None or new.get("inputs") is None:
        return True
    return bool(set(new.get("inputs") or []) & set(dead.get("inputs") or []))


def cell_of(key: Mapping[str, Any]) -> tuple[str, str, str]:
    """A key's refusal and budget cell: (class, structure family, holding)."""
    return (str(key.get("class")), str(key.get("family")), str(key.get("holding")))


#: What a row's mechanism text says it read (`infer_inputs`: legacy rows, whose inputs no card declared). Coarse on purpose:
#: a rebirth must add an input outside this reading.
_INPUT_WORDS: dict[str, re.Pattern[str]] = {
    "underlying_price": re.compile(r"\b(?:price\w*|returns?|moves?|gaps?|clos(?:e|es|ing)|highs?|lows?|trend\w*|rall\w*|"
                                   r"sell[- ]?offs?|drops?|declin\w*|breakouts?|momentum|revers\w*|rebound\w*|dips?|drawdowns?|"
                                   r"moving averages?|vwap|oversold|overbought)\b", re.I),
    "realized_vol": re.compile(r"\b(?:realized (?:vol\w*|variance)|ranges?|atr|true range)\b", re.I),
    "implied_vol": re.compile(r"\b(?:implied vol\w*|iv|vix|rich (?:premium|iv|implied)|cheap (?:premium|iv|implied|vol\w*))\b", re.I),
    "iv_term_structure": re.compile(r"\b(?:term structure|front[- ](?:month|expiry|week)|back[- ]month|contango|backwardation)\b",
                                    re.I),
    "iv_skew": re.compile(r"\b(?:skew\w*|risk reversals?|smile|wings?)\b", re.I),
    "option_liquidity": re.compile(r"\b(?:bid[- ]ask|quotes?|liquidity|order book|depth|spread widening)\b", re.I),
    "open_interest": re.compile(r"\b(?:open interest|max pain|pin\w*|gamma)\b", re.I),
    "share_volume": re.compile(r"\b(?:share volume|volume)\b", re.I),
    "event_calendar": re.compile(r"\b(?:fomc|cpi|payrolls?|nfp|earnings|auctions?|opex|expiration|macro|events?|announcements?)\b",
                                 re.I),
    "clock": re.compile(r"\b(?:minutes?|morning|afternoon|opening|last hour|first hour|time of day|weekdays?|mondays?|fridays?|"
                        r"weekends?|overnight|month[- ]end|quarter[- ]end|intraday)\b", re.I),
    "cross_asset": re.compile(r"\b(?:lead\w*|lag\w*|cross[- ]asset|relative|pairs?|ratio|another root|other roots?|sector)\b", re.I),
}


def infer_inputs(mechanism: Any) -> list[str]:
    """The inputs a row's mechanism text names (`_INPUT_WORDS`), sorted."""
    text = str(mechanism or "")
    return sorted(k for k, p in _INPUT_WORDS.items() if p.search(text))


def _stem(word: str) -> str:
    """A crude stem, so "rebounds", "rebounded" and "rebound" are one word (deterministic; English suffixes only)."""
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _content(text: Any) -> set[str]:
    return {_stem(w) for w in _WORD.findall(str(text or "").lower()) if len(w) > 2 and w not in _STOP}


def _parse_at(value: Any) -> dt.datetime | None:
    try:
        out = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return out if out.tzinfo else out.replace(tzinfo=dt.timezone.utc)


_SEQ = re.compile(r"card[_ ]evidence\s*(?:seq\s*)?#?\s*(\d+)", re.I)
_RUN_ID = re.compile(r"\b[0-9a-f][0-9a-f-]{15,63}\b")


# ------------------------------------------------------------------------------------------ the cell's yield
def wilson_upper(passed: int, n: int, z: float = WILSON_Z) -> float:
    """The Wilson score interval's upper bound on a share, `passed` of `n` (1.0 with no trial)."""
    if n <= 0:
        return 1.0
    p = min(max(passed / n, 0.0), 1.0)
    z2 = z * z
    centre = p + z2 / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return min(1.0, (centre + margin) / (1 + z2 / n))


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def cell_yield_settings(settings: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """`architect.cell_yield` (THE CELL'S YIELD): None while it is off (absent, null, false or anything but `true` or a
    mapping: every mechanism-verdict row needs a claim), else {min_births, floor, lookback_days}, a key the mapping leaves
    out or misstates (min_births a whole number of at least 1, floor strictly between 0 and 1, lookback_days above 0)
    taking `CELL_YIELD_DEFAULTS`."""
    raw = ((settings or {}).get("architect") or {}).get("cell_yield")
    if raw is True:
        raw = {}
    if not isinstance(raw, Mapping):
        return None
    out: dict[str, Any] = dict(CELL_YIELD_DEFAULTS)
    births, floor, days = (_number(raw.get(k)) for k in ("min_births", "floor", "lookback_days"))
    if births is not None and births >= 1 and births == int(births):
        out["min_births"] = int(births)
    if floor is not None and 0.0 < floor < 1.0:
        out["floor"] = floor
    if days is not None and days > 0:
        out["lookback_days"] = days
    return out


def cell_yields(store: Any, settings: Mapping[str, Any] | None, since: str, *,
                exclude: frozenset[str] | set[str] = frozenset()) -> dict[tuple[str, str, str], dict[str, int]]:
    """Each cell's families born at or after `since` (ISO) and their outcomes (THE CELL'S YIELD in the module docstring):
    {cell: {"births": settled births, "passed": those holding a drift-passing eligible Train run, "pending": alive without
    one, "unknown": settled, eligible, and no run with drift figures the screen can read}}. A family's cell is its card's
    (its own, else the card its spec's `card_sha` names: a fork's), else `infer_key`'s reading of its mechanism,
    structure and days to expiry; a family with neither is in no cell. A drift pass is `evidence.drift_screen` under the
    running screen's thresholds (`tournament.drift_min_t`, `drift_years_positive`; their defaults while the screen is off)
    from the run's own Train start, on a completed, eligible Train run at the normal spread (purpose train or drift).
    Train rows only, one query per 400 families, read-only. `exclude`: families left out (THE LEARNING GAME's game arm,
    which the architect never reads: `Architect.unseen`)."""
    from .researcher import CORE_SPAN, drift_settings  # a local import: the researcher imports this module

    screen = drift_settings(settings or {}) or (evidence_mod.DRIFT_MIN_T, None)
    own: dict[str, dict[str, Any]] = {}
    by_sha: dict[str, dict[str, Any]] = {}
    if _tables(store):
        for r in store._all("SELECT family, sha, key FROM family_cards ORDER BY at, family"):
            key = json.loads(r["key"])
            own[r["family"]] = key
            by_sha.setdefault(r["sha"], key)
    cell_by: dict[str, tuple[str, str, str]] = {}
    alive: set[str] = set()
    for f in store._all("SELECT id, retired_at, mechanism, structure, spec FROM families WHERE born_at >= ? "
                        "ORDER BY born_at, id", (since,)):
        if f["id"] in exclude:
            continue
        try:
            spec = json.loads(f["spec"] or "{}") or {}
        except (TypeError, ValueError):
            spec = {}
        spec = spec if isinstance(spec, Mapping) else {}
        key = own.get(f["id"]) or (by_sha.get(str(spec.get("card_sha"))) if spec.get("card_sha") else None)
        if key is None:
            key = infer_key(f["mechanism"], f["structure"], spec.get("dte"))
        if key is None:
            continue
        cell_by[f["id"]] = cell_of(key)
        if f["retired_at"] is None:
            alive.add(f["id"])
    passed: set[str] = set()
    eligible: set[str] = set()
    known: set[str] = set()
    # A version's runs made again carry the same figures: each distinct block and Train start is screened once.
    screened: dict[tuple[str, str], tuple[bool, bool]] = {}
    ids = list(cell_by)
    for start in range(0, len(ids), 400):
        part = ids[start:start + 400]
        sql = ("SELECT family, json_extract(summary, '$.drift') AS drift, json_extract(summary, '$.train_from') AS train_from "
               f"FROM runs WHERE family IN ({','.join('?' * len(part))}) AND window='train' AND stress=1.0 AND status='ok' "
               "AND purpose IN ('train', 'drift') AND json_valid(summary) AND json_extract(summary, '$.train_eligible') = 1")
        for r in store._all(sql, part):
            fid = r["family"]
            if fid in passed:
                continue
            eligible.add(fid)
            if not r["drift"]:
                continue
            year = str(r["train_from"] or CORE_SPAN)[:4]
            memo = (str(r["drift"]), year)
            if memo not in screened:
                try:
                    numbers = evidence_mod.drift_numbers(json.loads(r["drift"]))
                except (TypeError, ValueError):
                    numbers = None
                verdict = evidence_mod.drift_screen(numbers, min_t=screen[0], years_positive=screen[1],
                                                    first_year=int(year) if year.isdigit() else None) if numbers else {}
                screened[memo] = (bool(verdict.get("known")), bool(verdict.get("passed")))
            is_known, is_passed = screened[memo]
            if is_known:
                known.add(fid)
            if is_passed:
                passed.add(fid)
    out: dict[tuple[str, str, str], dict[str, int]] = {}
    for fid, cell in cell_by.items():
        tally = out.setdefault(cell, {"births": 0, "passed": 0, "pending": 0, "unknown": 0})
        if fid in passed:
            tally["births"] += 1
            tally["passed"] += 1
        elif fid in alive:
            tally["pending"] += 1
        elif fid in eligible and fid not in known:
            tally["unknown"] += 1
        else:
            tally["births"] += 1
    return out


#: THE ALWAYS-IN CARD's line of the BIRTH CELLS (`RebirthIndex.always_in_line`), before each lane root's state. Words only.
ALWAYS_IN_LINE = ("ALWAYS-IN (a direction card whose declared inputs are exactly [\"clock\"]: it enters every session on the "
                  "clock alone, with no gate, and its comparison or falsification says so): no cell's rows bind it, only "
                  "the always-in direction rows on its roots, whatever their class or holding, and no claim frees it; its "
                  "birth joins the always-in lineage on each of its roots, which has ONE Validation try; a program that "
                  "does not enter every session it is flat on Train is never validated (G1). By root: ")


def _spec_of(fam: Mapping[str, Any] | None) -> Mapping[str, Any]:
    raw = fam.get("spec") if isinstance(fam, Mapping) else None
    try:
        spec = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        spec = None
    return spec if isinstance(spec, Mapping) else {}


def _roots_of(raw: Any) -> list[str]:
    """A graveyard row's roots (stored as JSON), upper case; [] when unreadable."""
    try:
        roots = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        roots = None
    return [str(r).upper() for r in roots] if isinstance(roots, list) else []


def _g1_failed(store: Any) -> frozenset[str]:
    """THE ALWAYS-IN CARD: the retired families whose state records a G1 failure (dlane.py: `ALWAYS_IN_KEY`, or a
    version's recorded score failing "G1"): their rows are never always-in rows, whatever their card declared (a family
    its researcher retired before the tournament did keeps the rule). Empty on a store that cannot be read so."""
    try:
        return frozenset(str(r["id"]) for r in store._all(
            "SELECT f.id AS id FROM families f WHERE f.retired_at IS NOT NULL AND json_valid(f.state) AND ("
            f"json_extract(f.state, '$.{dlane.ALWAYS_IN_KEY}') IS NOT NULL OR EXISTS (SELECT 1 FROM "
            f"json_each(json_extract(f.state, '$.{dlane.STATE_KEY}.versions')) v, "
            "json_each(json_extract(v.value, '$.train.fails')) x WHERE x.value = 'G1'))"))
    except Exception:  # noqa: BLE001 - every declared always-in row then binds (the stricter reading)
        return frozenset()


def always_in_families(store: Any, roots: Iterable[str], *, exclude: Iterable[str] = ()) -> list[dict[str, Any]]:
    """THE ALWAYS-IN CARD (Oct 10, 2026): every DIRECTION family, alive or retired, whose DECLARED card (its own, else the
    one its spec's `card_sha` names) is always-in (`dlane.always_in`) and that names any of `roots`, oldest first: [{family,
    lineage, roots}]. `exclude`: families left out (`Architect.unseen`). What `Architect.admit` links an always-in birth
    to (one idea a root). Read-only; [] without the card table."""
    if not _tables(store):
        return []
    wanted = {str(r).upper() for r in roots}
    skip = {str(x) for x in exclude}
    by_family: dict[str, bool] = {}
    by_sha: dict[str, bool] = {}
    for r in store._all("SELECT family, sha, card FROM family_cards ORDER BY at, family"):
        status = dlane.always_in(json.loads(r["card"]))
        by_family[r["family"]] = status
        by_sha.setdefault(r["sha"], status)
    out = []
    for f in store._all("SELECT id, lineage, roots, spec FROM families ORDER BY born_at, id"):
        if f["id"] in skip:
            continue
        spec = _spec_of(f)
        status = by_family.get(f["id"])
        if status is None:
            status = by_sha.get(str(spec.get("card_sha") or ""), False)
        named = _roots_of(f["roots"])
        if status and wanted & set(named):
            out.append({"family": f["id"], "lineage": f["lineage"], "roots": named})
    return out


# ------------------------------------------------------------------------------------------ the rebirth refusal
class RebirthIndex:
    """The graveyard's rows killed by a mechanism verdict, each with its cell (its card's, else `infer_key`'s), and the
    rebirths already born by row and by cell, read once for an architect pass. `check(card, structure, mechanism)`
    answers a proposal. `exclude` (THE LEARNING GAME, Oct 8, 2026: `Architect.unseen`, the families the architect may
    not read): their graveyard rows, their cards' rebirths and their cell yields are left out, so no refusal quotes a
    game-arm lesson and no count moves with the game arm."""

    def __init__(self, store: Any, settings: Mapping[str, Any] | None = None, *,
                 yields: dict[tuple[str, str, str], dict[str, int]] | None = None, exclude: frozenset[str] = frozenset()):
        from .architect import lesson_view, tag_of  # a local import: the architect imports this module

        self.store = store
        self.settings = settings or {}
        self.cfg = self.settings.get("architect", {}) or {}
        # THE CELL'S YIELD (`architect.cell_yield`): read on first use (`yields`), never while it is off; `yields`, a
        # reading the same pass already made (the request's), is used as it is.
        self.yield_cfg = cell_yield_settings(self.settings)
        self._yields: dict[tuple[str, str, str], dict[str, int]] | None = yields if self.yield_cfg is not None else None
        self.yield_error: str | None = None
        self.exclude = frozenset(exclude)
        # THE DIRECTION LANE'S GRAVEYARD (Oct 9, 2026): while the lane is on each row carries its family's lane
        # (`row_lane`), read from the card table here (a fork's card by its spec's `card_sha`: `lanes_by_sha`).
        self.lane_on = dlane.on(self.settings)
        cards: dict[str, dict[str, Any]] = {}
        lanes_by_sha: dict[str, str] = {}
        always_by_sha: dict[str, bool] = {}  # THE ALWAYS-IN CARD: each stored card's declared status by sha
        if _tables(store):
            for r in store._all("SELECT family, sha, card, key, at FROM family_cards ORDER BY at, family"):
                card = json.loads(r["card"])
                if self.lane_on and r["sha"] not in lanes_by_sha:  # the oldest card of a sha, as `card_of` reads a fork's
                    lanes_by_sha[r["sha"]] = dlane.lane_value(card)[0]
                    always_by_sha[r["sha"]] = dlane.always_in(card)
                if r["family"] in self.exclude:
                    continue
                cards[r["family"]] = {"key": json.loads(r["key"]), "card": card, "at": r["at"]}
        families = {f["id"]: f for f in store._all("SELECT id, lineage, retire_reason, spec FROM families")}
        # THE ALWAYS-IN CARD (Oct 10, 2026): a family whose program failed G1 (dlane.py) lost the always-in status.
        lost = _g1_failed(store) if self.lane_on else frozenset()
        self.rows: list[dict[str, Any]] = []
        for g in store._all("SELECT family, at, mechanism, structure, roots, lesson FROM graveyard ORDER BY at, family"):
            if g["family"] in self.exclude:
                continue
            fam = families.get(g["family"])
            tag = tag_of(g, fam)
            if tag not in MECHANISM_VERDICTS:
                continue
            carded = cards.get(g["family"])
            if carded is not None:
                # Its declared inputs and those its own words name (the proposal's side is read the same way: `match_keys`).
                key, legacy = {**carded["key"], "inputs": match_inputs(carded["card"], g["mechanism"])}, False
            else:
                try:
                    dte = (json.loads(fam["spec"]) or {}).get("dte") if fam else None
                except (TypeError, ValueError):
                    dte = None
                key, legacy = infer_key(g["mechanism"], g["structure"], dte), True
            if key is None:
                continue
            row = {"row": g["family"], "at": g["at"], "tag": tag, "key": key, "legacy": legacy,
                   "inputs": sorted(key["inputs"]) if key.get("inputs") is not None else infer_inputs(g["mechanism"]),
                   "structure": g["structure"], "mechanism": _text(g["mechanism"])[:300],
                   "lesson": lesson_view(g["lesson"])[:400]}
            if self.lane_on:
                row["lane"] = row_lane(fam, carded["card"] if carded is not None else None, lanes_by_sha)
                # THE ALWAYS-IN CARD (Oct 10, 2026): a direction family's DECLARED card (its own, else a fork's by its
                # spec's card_sha), never its words, and the roots it traded.
                row["always_in"] = row["lane"] == dlane.DIRECTION and g["family"] not in lost and (
                    dlane.always_in(carded["card"]) if carded is not None
                    else always_by_sha.get(str(_spec_of(fam).get("card_sha") or ""), False))
                row["roots"] = _roots_of(g["roots"])
            self.rows.append(row)
        self.by_id = {r["row"]: r for r in self.rows}
        # The rebirths born so far: by the row each named (for ever) and by that row's cell (within the window).
        cutoff = None
        now = _parse_at(store.now()) if hasattr(store, "now") else None
        if now is not None:
            cutoff = now - dt.timedelta(days=self.window_days)
        self.backed: dict[str, int] = {}
        self.cell_births: dict[tuple[str, str, str], int] = {}
        for c in cards.values():
            reb = c["card"].get("rebirth") if isinstance(c["card"], Mapping) else None
            if not (isinstance(reb, Mapping) and reb.get("row")):
                continue
            row = str(reb["row"])
            self.backed[row] = self.backed.get(row, 0) + 1
            at = _parse_at(c.get("at"))
            if cutoff is None or (at is not None and at >= cutoff):
                cell = self._cell_of_rebirth(row, c["key"])
                self.cell_births[cell] = self.cell_births.get(cell, 0) + 1

    def _setting(self, name: str, default: int) -> int:
        raw = self.cfg.get(name, default)
        try:
            return max(0, int(raw)) if raw is not None and not isinstance(raw, bool) else default
        except (TypeError, ValueError):
            return default

    @property
    def per_row(self) -> int:
        return self._setting("max_rebirths_per_row", 2)

    @property
    def per_cell(self) -> int:
        return self._setting("max_rebirths_per_cell", 3)

    @property
    def window_days(self) -> int:
        return max(1, self._setting("rebirth_window_days", 7))

    @property
    def yields(self) -> dict[tuple[str, str, str], dict[str, int]] | None:
        """Each cell's births and drift passes over the lookback (`cell_yields`), read once; None while
        `architect.cell_yield` is off. A store that cannot be read for them leaves every cell exhausted (`yield_error`):
        the loosening never rests on figures it could not read."""
        if self.yield_cfg is None:
            return None
        if self._yields is None:
            try:
                now = _parse_at(self.store.now())
                if now is None:
                    raise ValueError(f"the store's clock reads {self.store.now()!r}")
                since = (now - dt.timedelta(days=float(self.yield_cfg["lookback_days"]))).strftime("%Y-%m-%dT%H:%M:%SZ")
                self._yields = cell_yields(self.store, self.settings, since, exclude=self.exclude)
            except Exception as exc:  # noqa: BLE001 - fail closed: today's rule for every cell
                self.yield_error = f"{type(exc).__name__}: {str(exc)[:200]}"
                self._yields = {}
        return self._yields

    def exhausted(self, cell: Any) -> bool:
        """THE CELL'S YIELD: is `cell` (class, structure family, holding) exhausted, so that every row of it needs a claim:
        at least `min_births` settled births in the lookback whose drift-pass share has a Wilson 95% upper bound below
        `floor`. Always true while the setting is off or the figures could not be read (today's rule); false for a cell
        with no birth in the lookback."""
        yields = self.yields
        if yields is None or self.yield_error is not None:
            return True
        tally = yields.get(tuple(cell))
        if tally is None:
            return False
        cfg = self.yield_cfg or CELL_YIELD_DEFAULTS
        return tally["births"] >= int(cfg["min_births"]) and wilson_upper(tally["passed"], tally["births"]) < float(cfg["floor"])

    def binds_direction(self, row: Mapping[str, Any]) -> bool:
        """THE DIRECTION LANE'S GRAVEYARD (Oct 9, 2026): may `row` bind a direction card at all: while the lane is on,
        only a direction family's row (`row_lane`); while it is off, every row (D-1's reading, which excused DRIFT
        alone)."""
        return not self.lane_on or row.get("lane") == dlane.DIRECTION

    def needs_claim(self, row: Mapping[str, Any], lane: str | None = None) -> bool:
        """Does a matched row by itself need a rebirth claim: every mechanism-verdict row while `architect.cell_yield` is
        off; with it on, every row of an exhausted cell and, in an open cell, every row but the `YIELD_EXCUSED`. `lane`
        (THE DIRECTION LANE, `lane_of_card`): a DRIFT row never needs one from a direction card, and (THE DIRECTION
        LANE'S GRAVEYARD, Oct 9, 2026) neither does an alpha family's row (`binds_direction`)."""
        if lane == dlane.DIRECTION and (row["tag"] == "DRIFT" or not self.binds_direction(row)):
            return False
        return row["tag"] not in YIELD_EXCUSED or self.exhausted(cell_of(row["key"]))

    def yield_view(self) -> dict[str, Any] | None:
        """THE CELL'S YIELD for a pass's event (Train figures only): the settings, and each cell with a birth in the
        lookback: its settled births, drift passes, pending and unknown families, the Wilson upper bound and whether it
        is exhausted. None while the setting is off."""
        yields = self.yields
        if yields is None:
            return None
        out: dict[str, Any] = {"settings": dict(self.yield_cfg or {})}
        if self.yield_error is not None:
            out["error"] = self.yield_error
        cells = []
        for cell, tally in sorted(yields.items(), key=lambda kv: (-kv[1]["births"], kv[0])):
            cells.append({"cell": " / ".join(cell), **tally, "upper": round(wilson_upper(tally["passed"], tally["births"]), 4),
                          "exhausted": self.exhausted(cell)})
        out["exhausted"] = [c["cell"] for c in cells if c["exhausted"]]
        out["cells"] = cells[:40]
        return out

    def _cell_of_rebirth(self, row: str, key: Mapping[str, Any]) -> tuple[str, str, str]:
        """A rebirth counts against the cell of the row it named (its own declared cell when that row is gone)."""
        named = self.by_id.get(row)
        return cell_of(named["key"] if named else key)

    def matched(self, card: Mapping[str, Any], structure: Any, mechanism: Any = "", dte: Any = None) -> tuple[list[dict[str, Any]], str | None]:
        """(the matched rows, oldest first; the class the proposal's own text reads as when that adds rows): the rows in its
        declared cell, and the rows of the cell its mechanism text reads as (`infer_key`'s class, with its structure family
        and holding) when that is another class; inputs are `match_inputs` (declared, and named by its own words)."""
        keys, other = match_keys(card, structure, mechanism, dte)
        hit = [r for r in self.rows if matches(keys[0], r["key"])]
        text_class = None
        if other is not None:
            extra = [r for r in self.rows if matches(keys[1], r["key"]) and r not in hit]
            if extra:
                text_class = other
                hit = sorted(hit + extra, key=lambda r: (r["at"], r["row"]))
        return hit, text_class

    def text_cell(self, mechanism: Any, structure: Any, dte: Any = None) -> dict[str, Any] | None:
        """The cell the proposal's own mechanism text reads as (`infer_key`) and how many mechanism-verdict rows share it
        (class, structure family and holding): recorded at birth for the audit of declared classes."""
        key = infer_key(mechanism, structure, dte)
        if key is None:
            return None
        rows = [r for r in self.rows if matches({**key, "inputs": None}, {**r["key"], "inputs": None})]
        return {"class": key["class"], "holding": key["holding"], "rows": len(rows)}

    def _cites(self, text: str, new_inputs: set[str]) -> bool:
        """Does a rebirth's evidence cite something checkable: a new input by name, a run id or a card_evidence seq in the
        store."""
        low = text.lower()
        if any(name in low or name.replace("_", " ") in low for name in new_inputs):
            return True
        for seq in _SEQ.findall(text):
            if _tables(self.store) and self.store._one("SELECT 1 AS ok FROM card_evidence WHERE seq=?", (int(seq),)):
                return True
        for token in set(_RUN_ID.findall(low)):
            if self.store._one("SELECT 1 AS ok FROM runs WHERE run_id=? OR run_id LIKE ?", (token, f"{token}-%")):
                return True
        return False

    def check(self, card: Mapping[str, Any], structure: Any, mechanism: Any = "", dte: Any = None, *,
              roots: Iterable[str] | None = None) -> dict[str, Any]:
        """{"ok": bool, "matched": [row ids], "reason": why refused, "row": the row the refusal points at, "lesson": its
        lesson}. ok with no match; ok with a match only through a valid `rebirth` (the module docstring). THE CELL'S
        YIELD: ok with "open" when every matched row is one an open cell excuses; "dropped" (why) when the card's claim
        there did not hold and must be stripped before the card is stored. THE DIRECTION LANE: ok with "drift_lane" (in
        place of "open") when a direction card matched rows only its lane excuses (DRIFT and, THE DIRECTION LANE'S
        GRAVEYARD, an alpha family's rows: `needs_claim`), "dropped" alike; "alpha_rows", for a direction card, the
        matched rows of alpha families (none binds it), on every verdict that matched one. THE ALWAYS-IN CARD (Oct 10,
        2026; `roots`, the proposal's: None reads every root): an always-in direction card, while the lane is on, is
        answered by `_always_in` alone."""
        if self.lane_on and dlane.always_in(card):
            return self._always_in(card, structure, mechanism, dte, roots)
        hit, text_class = self.matched(card, structure, mechanism, dte)
        if not hit:
            return {"ok": True, "matched": []}
        lane = lane_of_card(card)
        need = [r for r in hit if self.needs_claim(r, lane)]
        # THE DIRECTION LANE'S GRAVEYARD: how many matched rows its lane read as alpha (0, and no key, for an alpha card
        # and with the lane off).
        alpha = sum(1 for r in hit if not self.binds_direction(r)) if lane == dlane.DIRECTION else 0
        extra = {"alpha_rows": alpha} if alpha else {}
        if not need:
            # THE CELL'S YIELD: only an open cell's self-refuted and drift rows matched, and they need no claim. A claim
            # made anyway is a rebirth only when it holds (every test below, budgets included); else the proposal is born
            # without it (`dropped`: the architect strips it before the card is stored), so no unchecked claim links a
            # lineage or spends a budget. THE DIRECTION LANE: a direction card's DRIFT rows, and its alpha families'
            # rows, the same way ("drift_lane" when its lane, not the cell's yield, excused them).
            ids = [r["row"] for r in hit]
            why = "drift_lane" if lane is not None and any(self.needs_claim(r) for r in hit) else "open"
            out = {"ok": True, "matched": ids[-12:], "count": len(hit), why: True,
                   **({"text_class": text_class} if text_class else {}), **extra}
            if isinstance(card, Mapping) and isinstance(card.get("rebirth"), Mapping):
                claim = self._claim(card, structure, hit, text_class)
                if claim["ok"]:
                    return {**claim, why: True, **extra}
                out["dropped"] = claim["reason"]
            return out
        return {**self._claim(card, structure, hit, text_class, need if len(need) < len(hit) else None), **extra}

    def always_in_rows(self, roots: Iterable[str] | None = None) -> list[dict[str, Any]]:
        """THE ALWAYS-IN CARD (Oct 10, 2026): the always-in direction rows (`row["always_in"]`, while the lane is on) on any
        of `roots` (None: every root), oldest first, whatever their class or holding."""
        if not self.lane_on:
            return []
        wanted = None if roots is None else {str(r).upper() for r in roots}
        return [r for r in self.rows if r.get("always_in") and (wanted is None or wanted & set(r.get("roots") or ()))]

    def always_in_bound(self, roots: Iterable[str] | None = None) -> list[dict[str, Any]]:
        """The always-in rows on `roots` that bind an always-in card (`needs_claim` with the lane: never a DRIFT row)."""
        return [r for r in self.always_in_rows(roots) if self.needs_claim(r, dlane.DIRECTION)]

    def _always_in(self, card: Mapping[str, Any], structure: Any, mechanism: Any, dte: Any,
                   roots: Iterable[str] | None) -> dict[str, Any]:
        """`check` for an ALWAYS-IN direction card (the module docstring): refused when an always-in row on its roots binds
        it (no claim can free it), else ok with "always_in" and, as an audit figure, "gated_rows": the rows the rule
        before (`matched`) would have read as binding it. A claim it carries is `dropped`: no row it may name binds it."""
        named = sorted({str(r).upper() for r in roots}) if roots is not None else None
        bound = self.always_in_bound(named)
        old, _ = self.matched(card, structure, mechanism, dte)
        gated = sum(1 for r in old if not r.get("always_in") and self.needs_claim(r, dlane.DIRECTION))
        extra = {"always_in": True, **({"gated_rows": gated} if gated else {})}
        if not bound:
            out = {"ok": True, "matched": [r["row"] for r in self.always_in_rows(named)][-12:], **extra}
            if isinstance(card.get("rebirth"), Mapping):
                out["dropped"] = ("an always-in card is bound only by the always-in direction rows on its roots, and none "
                                  "binds it there: its claim is not needed and is not kept")
            return out
        newest = bound[-1]
        on = {x for r in bound for x in r.get("roots") or ()}
        on = sorted(on & set(named) if named else on)
        reason = (f"an always-in direction card (declared inputs exactly [\"clock\"]) is bound by the always-in direction rows "
                  f"on its roots, whatever their class or holding: {len(bound)} on {', '.join(on)}, the newest "
                  f"{newest['row']} ({newest['tag']}); it reads only the clock, so no rebirth claim can free it: the always-in "
                  "idea on that root is refuted (propose it on a root no always-in row binds, or a gated card)")
        return {"ok": False, "matched": [r["row"] for r in bound][-12:], "count": len(bound), "row": newest["row"],
                "lesson": newest["lesson"], "tag": newest["tag"], "key": key_text(key_of(card, structure)),
                "reason": reason, **extra}

    def always_in_line(self, ration: Mapping[str, str] | None = None) -> str:
        """THE ALWAYS-IN CARD's line of the BIRTH CELLS (the lane on): each lane root "open", bound by its newest always-in
        row (`always_in_bound`), or what the architect says of its always-in lineage's ration (`ration`: {root: words},
        `Architect.always_in_ration`). Ids and words only: no figure."""
        parts = []
        for root in dlane.cfg(self.settings)["roots"]:
            bound = self.always_in_bound([root])
            if bound:
                parts.append(f"{root} bound by {bound[-1]['row']} ({bound[-1]['tag']})"
                             + (f" and {len(bound) - 1} more" if len(bound) > 1 else ""))
            else:
                parts.append(f"{root} {(ration or {}).get(root) or 'open'}")
        return ALWAYS_IN_LINE + "; ".join(parts)

    def _claim(self, card: Mapping[str, Any], structure: Any, hit: list[dict[str, Any]], text_class: str | None,
               need: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """`check` on matched rows `hit`: refused without a valid `rebirth` naming one of them (the module docstring).
        `need` (THE CELL'S YIELD, only when some of `hit` need no claim): the rows that do, which the refusal points at."""
        ids = [r["row"] for r in hit]
        newest = hit[-1] if need is None else need[-1]
        out = {"ok": False, "matched": ids[-12:], "count": len(hit), "row": newest["row"], "lesson": newest["lesson"],
               "tag": newest["tag"], "key": key_text(key_of(card, structure))}
        if text_class:
            out["text_class"] = text_class
        where = (f"its cell ({out['key']})" + (f", and the {text_class} cell its own mechanism text reads as," if text_class else "")
                 + f" hold{'s' if not text_class else ''} {len(hit)} graveyard row(s) killed by a mechanism verdict, the newest "
                 f"{newest['row']} ({newest['tag']})")
        if need is not None:
            out["need"] = len(need)
            if lane_of_card(card) == dlane.DIRECTION:  # THE DIRECTION LANE: its DRIFT rows (and alpha rows) were excused
                where = (f"{where} of the {len(need)} that need a claim ("
                         + ("only a direction family's row binds a direction card, and never a DRIFT row" if self.lane_on
                            else "a DRIFT row binds no direction card")
                         + ("; an open cell's self-refuted and drift rows need none)" if self.yield_cfg is not None else ")"))
            else:
                where = (f"{where} of the {len(need)} that need a claim (an open cell's self-refuted and drift rows alone need "
                         "none)")
        reb = card.get("rebirth") if isinstance(card, Mapping) else None
        if not isinstance(reb, Mapping):
            out["reason"] = (f"{where}: a birth there needs card.rebirth naming one of them, what is different, an input the dead "
                             "row did not read and the new evidence")
            return out
        row = next((r for r in hit if r["row"] == reb.get("row")), None)
        if row is None:
            out["reason"] = (f"card.rebirth names {reb.get('row')!r}, which is not one of the rows its cell matches "
                             f"({', '.join(ids[-6:])})")
            return out
        out.update(row=row["row"], lesson=row["lesson"], tag=row["tag"])
        roots = {str(r).lower() for r in ((self.settings.get("gym") or {}).get("roots") or ())}
        different = _content(reb.get("different")) - _content(row["mechanism"]) - {_stem(w) for w in _SURFACE | roots}
        if len(different) < 3:
            out["reason"] = (f"card.rebirth.different restates {row['row']}'s mechanism or its own: name the mechanism-level "
                             "change (a new root, structure or horizon of a refuted idea is not one)")
            return out
        new_inputs = set(card.get("inputs") or []) - set(row["inputs"])
        if not new_inputs:
            out["reason"] = (f"card.rebirth adds no input {row['row']} did not read (it read "
                             f"{', '.join(row['inputs']) or 'nothing the text names'}{', by its text' if row['legacy'] else ''}): "
                             "new words on the same information are not a new idea")
            return out
        if not self._cites(str(reb.get("evidence") or ""), new_inputs):
            out["reason"] = (f"card.rebirth.evidence cites nothing checkable: name the new input ({', '.join(sorted(new_inputs))}) "
                             "and what it shows, or a run id or card_evidence seq in the store")
            return out
        if self.backed.get(row["row"], 0) >= self.per_row:
            out["reason"] = (f"{row['row']} has already backed {self.backed[row['row']]} rebirth(s) (the most one row may): its "
                             "lesson stands")
            return out
        cell = cell_of(row["key"])
        if self.cell_births.get(cell, 0) >= self.per_cell:
            out["reason"] = (f"the cell {' / '.join(cell)} has had {self.cell_births[cell]} rebirth(s) in the last "
                             f"{self.window_days} days (the most a cell may): look in another cell")
            return out
        return {"ok": True, "matched": ids[-12:], "count": len(hit), "row": row["row"], "rebirth": True,
                "new_inputs": sorted(new_inputs), **({"text_class": text_class} if text_class else {})}

    def note_birth(self, card: Mapping[str, Any], structure: Any = None) -> None:
        """Count a rebirth born in this pass against its row and its row's cell (the caps bind within a pass too)."""
        reb = card.get("rebirth") if isinstance(card, Mapping) else None
        if isinstance(reb, Mapping) and reb.get("row"):
            row = str(reb["row"])
            self.backed[row] = self.backed.get(row, 0) + 1
            cell = self._cell_of_rebirth(row, key_of(card, structure))
            self.cell_births[cell] = self.cell_births.get(cell, 0) + 1

    def grid(self, families: Iterable[str]) -> list[tuple[tuple[str, str, str], list[dict[str, Any]]]]:
        """THE CELLS A BIRTH MAY LAND IN (F1): every cell (mechanism class, structure family, holding) of the structure
        families `families`, each with its mechanism-verdict rows (oldest first; [] for a cell no row is in). The cells
        with rebirth room first (most rows first), then the cells with no row, then the cells at rebirth room 0."""
        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for r in self.rows:
            groups.setdefault(cell_of(r["key"]), []).append(r)
        wanted = [f for f in dict.fromkeys(STRUCTURE_FAMILIES.values()) if f in set(families)]
        cells = [(c, f, h) for f in wanted for c in MECHANISM_CLASSES for h in HOLDING]
        cells += lane_cells(self.settings, wanted)  # THE DIRECTION LANE's own cells, while it is on
        order = {cell: i for i, cell in enumerate(cells)}

        def rank(cell: tuple[str, str, str]) -> tuple[int, int, int]:
            rows = groups.get(cell, [])
            stage = 1 if not rows else 0 if self.room(cell) > 0 else 2
            return (stage, -len(rows), order[cell])

        return [(cell, groups.get(cell, [])) for cell in sorted(cells, key=rank)]

    def room(self, cell: Any) -> int:
        """The rebirths `cell` may still bear in the window (`architect.max_rebirths_per_cell` less those born)."""
        return max(0, self.per_cell - self.cell_births.get(tuple(cell), 0))

    def bearable(self, cell: Any, rows: list[dict[str, Any]], lane: str | None = None) -> bool:
        """Can a birth land in `cell` now (`rows`: its mechanism-verdict rows): no row needs a claim there (an empty cell,
        or THE CELL'S YIELD's open one), or it has rebirth room and a row a claim may still name (one that has backed
        fewer than `architect.max_rebirths_per_row` rebirths). `lane` "direction": a direction card's birth (its DRIFT rows
        and, THE DIRECTION LANE'S GRAVEYARD, its alpha families' rows need no claim: `needs_claim`)."""
        if not any(self.needs_claim(r, lane) for r in rows):
            return True
        return self.room(cell) > 0 and any(self.backed.get(r["row"], 0) < self.per_row for r in rows)

    def cells(self, limit: int = 40, claimable: int = 0, families: Iterable[str] | None = None,
              chars: int | None = None, always_in: Mapping[str, str] | None = None) -> list[str]:
        """The refuted cells, most rows first: one line each for the architect's request (with the cell's rebirth room).
        With `architect.cell_yield` on, each says whether it is open (and how many of its rows need a claim) or exhausted.
        `claimable` (`architect.claimable_rows`, 0: off) adds, for a cell with rebirth room where a claim can be needed, up
        to that many of its rows a claim may name (rows that have backed fewer than `max_rebirths_per_row` rebirths, newest
        first), each with the inputs it read, which a claim must add to; a carded row is matched only when the card's
        inputs overlap those. Ids and input names only: no figure. `families` (F1: the structure families a birth may be
        now, while `architect.structures` leaves any type out): every cell of those families and no other (`grid`: the
        ones with rebirth room first, then the ones no row is in, then the ones at room 0), whatever `limit` says; a
        cell no row is in says a card there needs no rebirth. `chars` (with `families`): the most characters the lines
        may run to; past it the last cells of the list give up their claimable rows, never their line. THE DIRECTION
        LANE'S GRAVEYARD (Oct 9, 2026; while the lane is on): each line of a cell a direction card may be declared in
        (`direction_cells`) that has rows also says how many of them bind a direction card (`needs_claim` with the
        lane: a direction family's row that is not DRIFT), so no alpha row reads as closing a direction cell. THE
        ALWAYS-IN CARD (Oct 10, 2026; while the lane is on, the list holds a cell and a directional cell may be listed):
        the list ends with `always_in_line` (`always_in`: the architect's words on each root's always-in ration), never
        cut by `chars`; a list with no cell stays empty (no graveyard row binds any card then)."""
        lane_box = direction_cells(self.settings)
        if families is not None:
            ranked = self.grid(families)
        else:
            groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
            for r in self.rows:
                groups.setdefault(cell_of(r["key"]), []).append(r)
            ranked = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:limit]
        out: list[list[str]] = []  # each cell's line and its claimable rows' words ("" when it names none)
        for cell, rows in ranked:
            if not rows:
                out.append([f"{' / '.join(cell)}: no row: a card here needs no rebirth", ""])
                continue
            carded = sum(1 for r in rows if not r["legacy"])
            room = self.room(cell)
            line = (f"{' / '.join(cell)}: {len(rows)} rows ({carded} carded), rebirth room {room}, newest "
                    f"{', '.join(r['row'] for r in rows[-3:])}")
            need = sum(1 for r in rows if self.needs_claim(r))
            if self.yield_cfg is not None:
                line += ("; exhausted: every row needs a claim" if self.exhausted(cell)
                         else f"; open: {need} of its rows need a claim" if need else "; open: no row needs a claim")
            if cell in lane_box:  # THE DIRECTION LANE'S GRAVEYARD: what binds a direction card here
                bind = sum(1 for r in rows if self.needs_claim(r, dlane.DIRECTION))
                verb = "binds" if bind == 1 else "bind"
                line += (f"; a direction card: {bind} of its rows {verb} one (direction families')" if bind
                         else "; a direction card: no row binds one (alpha families' and DRIFT rows never do)")
            named = []
            if claimable > 0 and room > 0 and need:
                named = [r for r in reversed(rows) if self.backed.get(r["row"], 0) < self.per_row][:claimable]
            out.append([line, "; claimable: " + ", ".join(
                f"{r['row']} (read {'+'.join(r['inputs']) or 'nothing named'}{'' if r['legacy'] else ', carded'})"
                for r in named) if named else ""])
        if families is not None and chars is not None:
            size = sum(len(line) + len(more) + 1 for line, more in out)
            for item in reversed(out):
                if size <= chars:
                    break
                size -= len(item[1])
                item[1] = ""
        lines = [line + more for line, more in out]
        if lines and self.lane_on and (families is None or "directional" in set(families)):
            lines.append(self.always_in_line(always_in))
        return lines


__all__ = ["MECHANISM_CLASSES", "LANE_CLASSES", "mechanism_classes", "lane_of_card", "lane_cells",
           "INPUTS", "HOLDING", "STRUCTURE_FAMILIES", "FLAT_REFUSED", "MECHANISM_VERDICTS", "DEFAULT_ABLATION",
           "validate", "canonical", "card_sha", "structure_family", "flat_allowed", "key_of", "key_text", "ensure", "put",
           "card_of", "add_evidence", "evidence", "vocabulary_text", "brief_text", "infer_key", "infer_inputs", "match_inputs",
           "match_keys", "matches", "cell_of", "RebirthIndex", "YIELD_EXCUSED", "CELL_YIELD_DEFAULTS", "WILSON_Z",
           "wilson_upper", "cell_yield_settings", "cell_yields", "direction_cells", "row_lane", "ALWAYS_IN_LINE",
           "always_in_families"]
