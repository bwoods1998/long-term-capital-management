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
  by default, the contract's convention). The mechanism test (league/swarm/mechanism.py) runs the program both ways;
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
twelve structures by the exposure they sell or buy: a new structure in the same group is not a new idea.

CARD-BASED REBIRTH REFUSAL (`RebirthIndex`). A proposal whose cell matches a graveyard row killed by a MECHANISM VERDICT
(`MECHANISM_VERDICTS`: the operator's pre-registered tests, refuted, self-refuted, diagnosed, trial-adjusted, drift,
stress, and a failed mechanism test) is born only with a `rebirth` that names one of those rows, says what is different
(`different`) and cites new evidence (`evidence`), and only while that row has backed fewer than
`architect.max_rebirths_per_row` (2) births. Otherwise it is refused and the refusal quotes the row's lesson, which the
architect reads in its next request. A carded row matches on the whole key (the new card's inputs no wider than the
dead card's). A row from before cards has no declared key: `infer_key` reads one from its mechanism text, structure and
days to expiry (a deterministic keyword reading, deliberately coarse), and such a row matches on class, structure family
and holding alone, since inputs cannot be read reliably from prose. A false match costs a justification, never a birth
outright. The check is deterministic and makes no model call.

Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

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
#: The graveyard tags that record a finding about the mechanism (architect.tag_of). Not IDLE (untested), THIN (activity),
#: EXHAUSTED (it reached a score), UNRESOLVED (an experiment failure), STALL (the tournament's clock) or OPERATOR-RETIRED
#: (housekeeping).
MECHANISM_VERDICTS = ("OPERATOR", "REFUTED", "SELF-REFUTED", "DIAGNOSED", "TRIALS", "DRIFT", "STRESS", "MECHANISM")
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


def validate(raw: Any) -> tuple[dict[str, Any] | None, list[str]]:
    """(the canonical card, []) or (None, every problem named). The card's fields are the module docstring's; `ablation`
    defaults to `DEFAULT_ABLATION`, and `rebirth` is kept only when given (its rows are checked by `RebirthIndex`)."""
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
    else:
        param = str(ablation.get("param") or "") if isinstance(ablation, Mapping) else ""
        off = ablation.get("off") if isinstance(ablation, Mapping) else None
        scalar = isinstance(off, (bool, int, str)) or (isinstance(off, float) and off == off and abs(off) != float("inf"))
        if not _PARAM.match(param) or not scalar or (isinstance(off, str) and len(off) > 40):
            errors.append("ablation: {\"param\": the PARAMS key that switches the signal, \"off\": the value that turns it "
                          "into the comparison} (default {\"param\": \"signal_on\", \"off\": 0})")
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
    lines = ["YOUR FAMILY CARD (fixed at birth; you research and are judged under it):",
             f"- Hypothesis: {c.get('hypothesis')}",
             f"- Mechanism class: {c.get('mechanism_class')}. Inputs: {', '.join(c.get('inputs') or [])}. Holding: "
             f"{c.get('holding')} ({HOLDING.get(str(c.get('holding')), '')}).",
             f"- Cost hurdle: about {c.get('cost', {}).get('hurdle')} of maximum loss a round trip ({c.get('cost', {}).get('why')}).",
             f"- Comparison it must beat: {c.get('comparison')}",
             f"- Ablation: PARAMS[{ab['param']!r}] = {ab['off']!r} must turn your signal into that comparison: skip ONLY the "
             "signal's condition and keep the structure, schedule, sizing and exits, so the program still trades. Declare "
             f"{ab['param']!r} in PARAMS (default on) and read it in decide.",
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


def matches(new: Mapping[str, Any], dead: Mapping[str, Any]) -> bool:
    """Does a proposal's cell `new` fall in a dead row's cell `dead`: the same class, structure family and holding, and (a
    carded row) inputs no wider than the dead card's. A legacy row (`inputs` None) matches on the first three."""
    if (new.get("class"), new.get("family"), new.get("holding")) != (dead.get("class"), dead.get("family"), dead.get("holding")):
        return False
    if dead.get("inputs") is None:
        return True
    return set(new.get("inputs") or []) <= set(dead.get("inputs") or [])


def _stem(word: str) -> str:
    """A crude stem, so "rebounds", "rebounded" and "rebound" are one word (deterministic; English suffixes only)."""
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _content(text: Any) -> set[str]:
    return {_stem(w) for w in _WORD.findall(str(text or "").lower()) if len(w) > 2 and w not in _STOP}


# ------------------------------------------------------------------------------------------ the rebirth refusal
class RebirthIndex:
    """The graveyard's rows killed by a mechanism verdict, each with its cell (its card's, else `infer_key`'s), read once
    for an architect pass. `check(card, structure, mechanism)` answers a proposal."""

    def __init__(self, store: Any, settings: Mapping[str, Any] | None = None):
        from .architect import lesson_view, tag_of  # a local import: the architect imports this module

        self.store = store
        self.settings = settings or {}
        self.cfg = self.settings.get("architect", {}) or {}
        cards: dict[str, dict[str, Any]] = {}
        backed: dict[str, int] = {}
        if _tables(store):
            for r in store._all("SELECT family, card, key FROM family_cards"):
                card = json.loads(r["card"])
                cards[r["family"]] = {"key": json.loads(r["key"]), "card": card}
                reb = card.get("rebirth") if isinstance(card, Mapping) else None
                if isinstance(reb, Mapping) and reb.get("row"):
                    backed[str(reb["row"])] = backed.get(str(reb["row"]), 0) + 1
        self.backed = backed
        families = {f["id"]: f for f in store._all("SELECT id, lineage, retire_reason, spec FROM families")}
        self.rows: list[dict[str, Any]] = []
        for g in store._all("SELECT family, at, mechanism, structure, roots, lesson FROM graveyard ORDER BY at, family"):
            fam = families.get(g["family"])
            tag = tag_of(g, fam)
            if tag not in MECHANISM_VERDICTS:
                continue
            carded = cards.get(g["family"])
            if carded is not None:
                key, legacy = carded["key"], False
            else:
                try:
                    dte = (json.loads(fam["spec"]) or {}).get("dte") if fam else None
                except (TypeError, ValueError):
                    dte = None
                key, legacy = infer_key(g["mechanism"], g["structure"], dte), True
            if key is None:
                continue
            self.rows.append({"row": g["family"], "at": g["at"], "tag": tag, "key": key, "legacy": legacy,
                              "structure": g["structure"], "mechanism": _text(g["mechanism"])[:300],
                              "lesson": lesson_view(g["lesson"])[:400]})

    @property
    def per_row(self) -> int:
        raw = self.cfg.get("max_rebirths_per_row", 2)
        try:
            return max(0, int(raw)) if raw is not None and not isinstance(raw, bool) else 2
        except (TypeError, ValueError):
            return 2

    def matched(self, card: Mapping[str, Any], structure: Any) -> list[dict[str, Any]]:
        key = key_of(card, structure)
        return [r for r in self.rows if matches(key, r["key"])]

    def check(self, card: Mapping[str, Any], structure: Any, mechanism: Any = "") -> dict[str, Any]:
        """{"ok": bool, "matched": [row ids], "reason": why refused, "row": the row the refusal points at, "lesson": its
        lesson}. ok with no match; ok with a match only through a valid `rebirth` (a matched row, a `different` that says
        more than the dead row's own mechanism, and a row with room under `max_rebirths_per_row`)."""
        hit = self.matched(card, structure)
        if not hit:
            return {"ok": True, "matched": []}
        ids = [r["row"] for r in hit]
        newest = hit[-1]
        out = {"ok": False, "matched": ids[-12:], "count": len(hit), "row": newest["row"], "lesson": newest["lesson"],
               "tag": newest["tag"], "key": key_text(key_of(card, structure))}
        reb = card.get("rebirth") if isinstance(card, Mapping) else None
        if not isinstance(reb, Mapping):
            out["reason"] = (f"its cell ({out['key']}) holds {len(hit)} graveyard row(s) killed by a mechanism verdict, the "
                             f"newest {newest['row']} ({newest['tag']}): a birth there needs card.rebirth naming one of them, "
                             "what is different and the new evidence")
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
        if self.backed.get(row["row"], 0) >= self.per_row:
            out["reason"] = (f"{row['row']} has already backed {self.backed[row['row']]} rebirth(s) (the most one row may): its "
                             "lesson stands")
            return out
        return {"ok": True, "matched": ids[-12:], "count": len(hit), "row": row["row"], "rebirth": True}

    def note_birth(self, card: Mapping[str, Any]) -> None:
        """Count a rebirth born in this pass against its row (the cap binds within a pass too)."""
        reb = card.get("rebirth") if isinstance(card, Mapping) else None
        if isinstance(reb, Mapping) and reb.get("row"):
            self.backed[str(reb["row"])] = self.backed.get(str(reb["row"]), 0) + 1

    def cells(self, limit: int = 40) -> list[str]:
        """The refuted cells, most rows first: one line each for the architect's request."""
        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for r in self.rows:
            k = r["key"]
            groups.setdefault((k["class"], k["family"], k["holding"]), []).append(r)
        ranked = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:limit]
        out = []
        for (cls, fam, hold), rows in ranked:
            carded = sum(1 for r in rows if not r["legacy"])
            out.append(f"{cls} / {fam} / {hold}: {len(rows)} rows ({carded} carded), newest {', '.join(r['row'] for r in rows[-3:])}")
        return out


__all__ = ["MECHANISM_CLASSES", "INPUTS", "HOLDING", "STRUCTURE_FAMILIES", "MECHANISM_VERDICTS", "DEFAULT_ABLATION", "validate",
           "canonical", "card_sha", "structure_family", "key_of", "key_text", "ensure", "put", "card_of", "add_evidence",
           "evidence", "vocabulary_text", "brief_text", "infer_key", "matches", "RebirthIndex"]
