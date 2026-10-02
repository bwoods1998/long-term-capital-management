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

Standard library only.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from typing import Any, Mapping

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


def validate(raw: Any, structure: Any = None) -> tuple[dict[str, Any] | None, list[str]]:
    """(the canonical card, []) or (None, every problem named). The card's fields are the module docstring's; `ablation`
    defaults to `DEFAULT_ABLATION` (a flat one, `{"flat": true}`, only for a `structure` `flat_allowed` admits), and
    `rebirth` is kept only when given (its rows are checked by `RebirthIndex`)."""
    if not isinstance(raw, Mapping):
        return None, ["card: missing (every family needs one: hypothesis, mechanism_class, inputs, holding, cost, comparison, "
                      "ablation, falsification)"]
    errors: list[str] = []
    card: dict[str, Any] = {}
    _sized(card, errors, raw, "hypothesis")
    cls = _token(raw.get("mechanism_class"))
    if cls in MECHANISM_CLASSES:
        card["mechanism_class"] = cls
    else:
        errors.append(f"mechanism_class: {raw.get('mechanism_class')!r} is not one of {', '.join(MECHANISM_CLASSES)}")
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
def vocabulary_text() -> str:
    """The card's vocabularies as the architect reads them."""
    lines = ["MECHANISM CLASSES:"] + [f"- {k}: {v}" for k, v in MECHANISM_CLASSES.items()]
    lines += ["INPUTS:"] + [f"- {k}: {v}" for k, v in INPUTS.items()]
    lines += ["HOLDING:"] + [f"- {k}: {v}" for k, v in HOLDING.items()]
    lines += ["STRUCTURE FAMILIES (a new structure in the same group is not a new idea): "
              + "; ".join(f"{g}: {', '.join(s for s, x in STRUCTURE_FAMILIES.items() if x == g)}"
                          for g in dict.fromkeys(STRUCTURE_FAMILIES.values()))]
    return "\n".join(lines)


def brief_text(entry: Mapping[str, Any] | None) -> str:
    """A family's card as its researcher reads it ("" for a family born before cards)."""
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


def cell_yields(store: Any, settings: Mapping[str, Any] | None, since: str) -> dict[tuple[str, str, str], dict[str, int]]:
    """Each cell's families born at or after `since` (ISO) and their outcomes (THE CELL'S YIELD in the module docstring):
    {cell: {"births": settled births, "passed": those holding a drift-passing eligible Train run, "pending": alive without
    one, "unknown": settled, eligible, and no run with drift figures the screen can read}}. A family's cell is its card's
    (its own, else the card its spec's `card_sha` names: a fork's), else `infer_key`'s reading of its mechanism,
    structure and days to expiry; a family with neither is in no cell. A drift pass is `evidence.drift_screen` under the
    running screen's thresholds (`tournament.drift_min_t`, `drift_years_positive`; their defaults while the screen is off)
    from the run's own Train start, on a completed, eligible Train run at the normal spread (purpose train or drift).
    Train rows only, one query per 400 families, read-only."""
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
            try:
                numbers = evidence_mod.drift_numbers(json.loads(r["drift"])) if r["drift"] else None
            except (TypeError, ValueError):
                numbers = None
            if numbers is None:
                continue
            year = str(r["train_from"] or CORE_SPAN)[:4]
            verdict = evidence_mod.drift_screen(numbers, min_t=screen[0], years_positive=screen[1],
                                                first_year=int(year) if year.isdigit() else None)
            if verdict["known"]:
                known.add(fid)
            if verdict["passed"]:
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


# ------------------------------------------------------------------------------------------ the rebirth refusal
class RebirthIndex:
    """The graveyard's rows killed by a mechanism verdict, each with its cell (its card's, else `infer_key`'s), and the
    rebirths already born by row and by cell, read once for an architect pass. `check(card, structure, mechanism)`
    answers a proposal."""

    def __init__(self, store: Any, settings: Mapping[str, Any] | None = None):
        from .architect import lesson_view, tag_of  # a local import: the architect imports this module

        self.store = store
        self.settings = settings or {}
        self.cfg = self.settings.get("architect", {}) or {}
        # THE CELL'S YIELD (`architect.cell_yield`): read on first use (`yields`), never while it is off.
        self.yield_cfg = cell_yield_settings(self.settings)
        self._yields: dict[tuple[str, str, str], dict[str, int]] | None = None
        self.yield_error: str | None = None
        cards: dict[str, dict[str, Any]] = {}
        if _tables(store):
            for r in store._all("SELECT family, card, key, at FROM family_cards ORDER BY at, family"):
                cards[r["family"]] = {"key": json.loads(r["key"]), "card": json.loads(r["card"]), "at": r["at"]}
        families = {f["id"]: f for f in store._all("SELECT id, lineage, retire_reason, spec FROM families")}
        self.rows: list[dict[str, Any]] = []
        for g in store._all("SELECT family, at, mechanism, structure, roots, lesson FROM graveyard ORDER BY at, family"):
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
            self.rows.append({"row": g["family"], "at": g["at"], "tag": tag, "key": key, "legacy": legacy,
                              "inputs": sorted(key["inputs"]) if key.get("inputs") is not None else infer_inputs(g["mechanism"]),
                              "structure": g["structure"], "mechanism": _text(g["mechanism"])[:300],
                              "lesson": lesson_view(g["lesson"])[:400]})
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
                self._yields = cell_yields(self.store, self.settings, since)
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

    def needs_claim(self, row: Mapping[str, Any]) -> bool:
        """Does a matched row by itself need a rebirth claim: every mechanism-verdict row while `architect.cell_yield` is
        off; with it on, every row of an exhausted cell and, in an open cell, every row but the `YIELD_EXCUSED`."""
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

    def check(self, card: Mapping[str, Any], structure: Any, mechanism: Any = "", dte: Any = None) -> dict[str, Any]:
        """{"ok": bool, "matched": [row ids], "reason": why refused, "row": the row the refusal points at, "lesson": its
        lesson}. ok with no match; ok with a match only through a valid `rebirth` (the module docstring). THE CELL'S
        YIELD: ok with "open" when every matched row is one an open cell excuses; "dropped" (why) when the card's claim
        there did not hold and must be stripped before the card is stored."""
        hit, text_class = self.matched(card, structure, mechanism, dte)
        if not hit:
            return {"ok": True, "matched": []}
        need = [r for r in hit if self.needs_claim(r)]
        if not need:
            # THE CELL'S YIELD: only an open cell's self-refuted and drift rows matched, and they need no claim. A claim
            # made anyway is a rebirth only when it holds (every test below, budgets included); else the proposal is born
            # without it (`dropped`: the architect strips it before the card is stored), so no unchecked claim links a
            # lineage or spends a budget.
            ids = [r["row"] for r in hit]
            out = {"ok": True, "matched": ids[-12:], "count": len(hit), "open": True,
                   **({"text_class": text_class} if text_class else {})}
            if isinstance(card, Mapping) and isinstance(card.get("rebirth"), Mapping):
                claim = self._claim(card, structure, hit, text_class)
                if claim["ok"]:
                    return {**claim, "open": True}
                out["dropped"] = claim["reason"]
            return out
        return self._claim(card, structure, hit, text_class, need if len(need) < len(hit) else None)

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

    def cells(self, limit: int = 40, claimable: int = 0) -> list[str]:
        """The refuted cells, most rows first: one line each for the architect's request (with the cell's rebirth room).
        With `architect.cell_yield` on, each says whether it is open (and how many of its rows need a claim) or exhausted.
        `claimable` (`architect.claimable_rows`, 0: off) adds, for a cell with rebirth room where a claim can be needed, up
        to that many of its rows a claim may name (rows that have backed fewer than `max_rebirths_per_row` rebirths, newest
        first), each with the inputs it read, which a claim must add to; a carded row is matched only when the card's
        inputs overlap those. Ids and input names only: no figure."""
        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for r in self.rows:
            groups.setdefault(cell_of(r["key"]), []).append(r)
        ranked = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:limit]
        out = []
        for cell, rows in ranked:
            carded = sum(1 for r in rows if not r["legacy"])
            room = max(0, self.per_cell - self.cell_births.get(cell, 0))
            line = (f"{' / '.join(cell)}: {len(rows)} rows ({carded} carded), rebirth room {room}, newest "
                    f"{', '.join(r['row'] for r in rows[-3:])}")
            need = sum(1 for r in rows if self.needs_claim(r))
            if self.yield_cfg is not None:
                line += ("; exhausted: every row needs a claim" if self.exhausted(cell)
                         else f"; open: {need} of its rows need a claim" if need else "; open: no row needs a claim")
            if claimable > 0 and room > 0 and need:
                named = [r for r in reversed(rows) if self.backed.get(r["row"], 0) < self.per_row][:claimable]
                if named:
                    line += "; claimable: " + ", ".join(
                        f"{r['row']} (read {'+'.join(r['inputs']) or 'nothing named'}{'' if r['legacy'] else ', carded'})"
                        for r in named)
            out.append(line)
        return out


__all__ = ["MECHANISM_CLASSES", "INPUTS", "HOLDING", "STRUCTURE_FAMILIES", "FLAT_REFUSED", "MECHANISM_VERDICTS", "DEFAULT_ABLATION",
           "validate", "canonical", "card_sha", "structure_family", "flat_allowed", "key_of", "key_text", "ensure", "put",
           "card_of", "add_evidence", "evidence", "vocabulary_text", "brief_text", "infer_key", "infer_inputs", "match_inputs",
           "match_keys", "matches", "cell_of", "RebirthIndex", "YIELD_EXCUSED", "CELL_YIELD_DEFAULTS", "WILSON_Z",
           "wilson_upper", "cell_yield_settings", "cell_yields"]
