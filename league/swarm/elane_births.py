"""THE EQUITY LANES' BIRTHS (release E2, Oct 2026): the swarm itself breeds share programs for the BETA and EQUITY lanes.

The owner's goal: "a swarm of agent programs ... researching and learning 24/7", with "an EQUITY lane searching
stock/ETF strategies (trend, momentum, mean reversion, earnings drift, low volatility, rotation)". Release E1 gave the
lanes their live path, engine, store, screen and three captain-seeded programs; this module gives them births. It is
the options direction lane's architect wiring (league/swarm/dlane.py `DirectionQuota`, `lanes_text`, the architect's
LANES block), for share programs:

THE EQUITY PASS (`EquityPass`; league/swarm/architect.py `Architect.equity_pass`, its own round in the loop). Its own
request, apart from the options architect's (whose words, graveyard and births stay byte for byte as they were): the
equity architect's system prompt with the program contract (league/equity/EQUITY.md), and a request holding the
LANES/EQUITY block (`lanes_text`: the two lanes' meaning and labels, the universe, the contract in brief, the Train bar,
the ration), THE AGENDA (league/swarm/elane_train.py `AGENDA`: the mechanisms with their published priors; earnings
drift named and refused until earnings data exist), THE EQUITY QUOTA's lines, THE EQUITY TRAIN MAP (in-sample, the
swarm's own Train runs), the equity graveyard that binds (E2's Train refutations and the CLOSED cells), the lineages
whose one try is taken (seeded programs and Train passes, outcomes sealed), the equity families' Train facts, the card
vocabulary and the last pass's refusals. Its route is chosen by measured yield per dollar
(league/swarm/elane_yield.py `choose`), and its answer is booked to the route that gave it.

THE EQUITY QUOTA (`EquityQuota`; `elane.birth_share`, the owner's switch). The equity lanes' share of the swarm's births
is `birth_share` (b) of the window's (`window_hours`, 24) births across all lanes: the pass asks for the births that
bring the equity lanes to b of the window (ceil(b / (1 - b) x the options lanes' births) less the equity births
already in it), at least `min_per_pass` (1) and at most `max_per_pass` (6), and never past `max_alive` (24) families
in Train research. The equity lanes have their own population (E1's `SwarmStore.families` leaves them out of every
options count), so an options population at its ceiling stops no equity birth: the pass then asks `min_per_pass`.
The options request is unchanged; its births are not reduced (the design's "taken out of the alpha share first" is
read as the share above, since the equity births take no options place: ELANE_E2.md says why).

THE ADMISSION (`EquityPass.admit`). A proposal is born as an equity family when: its lane is "beta" or "equity"; its
structure is in `elane.structures` (a beta card's is "etf"); its symbols (1-20) are in `elane.universe` and of its
structure's class; its agenda is an available mechanism; its cell (lane x agenda x universe group) is not CLOSED; no
family in Train research holds the same idea on the same slice; its card is valid (`cards.validate`, E1's equity
admission through `elane.card_errors`); THE GRAVEYARD BINDS (the design's lane-scoped REFUTED rows, PR #519): a card in
the cell of a family E2 refuted on Train (its own lane's rows only: E1's `cards.RebirthIndex`, every other row excluded,
so no row with an outcome lesson is read) needs a valid `card.rebirth` naming the row, as an options card does, while
`architect.card_rebirth` is "refuse"; NO lineage it continues (the equity parent it names, EVERY family of its slice
with the same idea, and the row it is reborn from) has taken a Validation try (no seeded program and no Train pass in
any of them: an outcome-free rule, A9 D3; naming an untried parent hides no tried one); and THE EQUITY QUOTA admits it. Its spec carries `lane`, `symbols` (its `roots` too), `agenda`, the card's
sha and `e2_route` (the route that bore it: its yield row, and the route its Train revisions are asked on). A program
it carries that passes the static checks (league/swarm/elane_train.py `check_code`) is its version 1 (author
"architect:<route>"); one that does not is recorded, and the equity researcher writes v1. Each birth is a `swarm.born`
event with its `lane`, and the pass one `swarm.elane` event.

THE SWITCH: `elane.mode` "gate" AND `elane.birth_share` above zero (`births_on`). With either off nothing here acts.
Standard library only.
"""

from __future__ import annotations

import math
import time
from typing import Any, Mapping, Sequence

from ..equity import BETA, EQUITY, LANES
from ..equity import config as eqconfig
from . import elane_seal, elane_train, elane_yield
from .elane_train import AGENDA, STATE_KEY
from .elane_yield import ROLE

#: The store's kv keys: the last equity pass's time and its births and refusals (for the next request).
BIRTHS_AT_KEY = elane_train.BIRTHS_AT  # "elane_e2_births_at": the Train round's `due` reads it too
LAST_KEY = "elane_e2_last"
#: The equity pass's settings (`elane.e2` keys; defaults here, policy.json in ELANE_E2_PATCHES.md) and their bounds.
DEFAULTS: dict[str, Any] = {"births_every_seconds": 7200, "births_refill_seconds": 1800, "start": 8, "max_alive": 24,
                            "min_per_pass": 1, "max_per_pass": 6, "window_hours": 24, "births_max_output_tokens": 24000,
                            "births_effort": "medium", "families_shown": 30}
BOUNDS: dict[str, tuple[float, float]] = {"births_every_seconds": (300, 86400), "births_refill_seconds": (300, 86400),
                                          "start": (0, 200), "max_alive": (0, 200), "min_per_pass": (0, 20),
                                          "max_per_pass": (1, 20), "window_hours": (1, 168),
                                          "births_max_output_tokens": (4000, 64000), "families_shown": (0, 100)}
EFFORTS = elane_train.EFFORTS
MIN_MECHANISM = 30
REFUSALS_SHOWN = 12


# ----------------------------------------------------------------------------------------------------------- settings
def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """The equity pass's settings from `elane.e2`, each inside its bound (a malformed value is its default)."""
    raw = elane_yield.e2_settings(settings)
    out = dict(DEFAULTS)
    for key, (lo, hi) in BOUNDS.items():
        x = _num(raw.get(key))
        if x is not None and lo <= x <= hi:
            out[key] = int(x) if isinstance(DEFAULTS[key], int) else x
    if raw.get("births_effort") in EFFORTS:
        out["births_effort"] = raw["births_effort"]
    out["max_per_pass"] = max(out["max_per_pass"], out["min_per_pass"])
    return out


def lane_cfg(settings: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """E1's `elane.cfg` (its bounds), or None when it cannot be read (the lanes are then off: fail closed)."""
    from . import elane

    try:
        value = elane.cfg(settings)
    except Exception:  # noqa: BLE001 - an unreadable lane block is off
        return None
    return dict(value) if isinstance(value, Mapping) else None


def birth_share(settings: Mapping[str, Any] | None) -> float:
    """`elane.birth_share` (0 while the block cannot be read)."""
    c = lane_cfg(settings) or {}
    x = _num(c.get("birth_share"))
    return max(0.0, min(1.0, x)) if x is not None else 0.0


def births_on(settings: Mapping[str, Any] | None) -> bool:
    """THE SWITCH: the lanes are on (`elane.mode` "gate") and `elane.birth_share` is above zero."""
    return elane_train.lane_on(settings) and birth_share(settings) > 0


def universe(settings: Mapping[str, Any] | None) -> dict[str, list[str]]:
    """The symbols a birth may trade, by structure ({"etf": [...], "stock": [...]}): `elane.universe` inside the code's
    universe (league/equity/config.py UNIVERSE), of the structures `elane.structures` names."""
    c = lane_cfg(settings) or {}
    structures = [s for s in (c.get("structures") or []) if s in eqconfig.CLASSES]
    named = [str(s).upper() for s in (c.get("universe") or [])]
    return {s: [x for x in named if eqconfig.UNIVERSE.get(x) == s] for s in structures}


def researching(store: Any) -> int:
    """E2 families in Train research (E2's record: neither passed nor refuted nor closed). Outcome-free (A9 D3): a
    family that passed Train leaves this count whatever happens to it after."""
    n = 0
    for fam in elane_seal.equity_families(store):
        if elane_train.e2_family(fam) and elane_train.record_of(fam).get("status", "researching") == "researching":
            n += 1
    return n


def due(store: Any, settings: Mapping[str, Any] | None, *, now: float | None = None) -> bool:
    """The equity pass is due: THE SWITCH is on, E2 may ask a model now (its day's line has room and it is under its
    hourly pace: `elane_yield.hold`), and `births_every_seconds` passed since the last pass (`births_refill_seconds`
    while fewer than `start` families are in Train research)."""
    if not births_on(settings):
        return False
    now = time.time() if now is None else float(now)
    c = cfg(settings)
    last = _num(store.get(BIRTHS_AT_KEY)) or 0.0
    if now - last < min(c["births_refill_seconds"], c["births_every_seconds"]):
        return False  # inside even the shorter cadence: the families and the spend are not read on every loop pass
    if elane_yield.hold(store, settings, now) is not None:
        return False
    every = c["births_refill_seconds"] if researching(store) < c["start"] else c["births_every_seconds"]
    return now - last >= every


# ----------------------------------------------------------------------------------------------------------- the quota
class EquityQuota:
    """THE EQUITY QUOTA for one equity pass (the module docstring): the window's births by lane, read once, and the
    pass's own so far."""

    def __init__(self, store: Any, settings: Mapping[str, Any] | None, *, now: float | None = None):
        from .store import iso, loads

        c = cfg(settings)
        self.c = c
        self.on = births_on(settings)
        self.share = birth_share(settings)
        now = time.time() if now is None else float(now)
        self.window = {"options": 0, "equity": 0}
        if self.on:
            since = iso(now - c["window_hours"] * 3600.0)
            for row in store._all("SELECT payload FROM events WHERE kind='swarm.born' AND at>=?", (since,)):
                payload = loads(row.get("payload"), {}) or {}
                lane = payload.get("lane") if isinstance(payload, Mapping) else None
                self.window["equity" if lane in LANES else "options"] += 1
        self.researching = researching(store) if self.on else 0
        self.room = max(0, c["max_alive"] - self.researching) if self.on else 0
        if self.on and self.share < 1.0:
            self.target = math.ceil(self.share / (1.0 - self.share) * self.window["options"] - 1e-9)
        else:
            self.target = c["max_per_pass"] if self.on else 0
        self.deficit = max(0, self.target - self.window["equity"])
        self.want = (min(self.room, c["max_per_pass"], max(c["min_per_pass"], self.deficit))
                     if self.on and self.room else 0)
        self.passed = {BETA: 0, EQUITY: 0}
        self.refused = 0

    def why_not(self, lane: str) -> str | None:
        """Why one more equity birth may not be born in this pass, or None."""
        if not self.on:
            return "the equity lanes' births are off (elane.mode, elane.birth_share)"
        if lane not in LANES:
            return f"{lane!r} is not an equity lane"
        if sum(self.passed.values()) >= self.want:
            return f"the pass's {self.want} equity births are born"
        return None

    def admits(self, lane: str) -> bool:
        why = self.why_not(lane)
        if why is not None:
            self.refused += 1
        return why is None

    def born(self, lane: str) -> None:
        if lane in self.passed:
            self.passed[lane] += 1

    def short(self) -> int:
        return max(0, self.want - sum(self.passed.values()))

    def event(self) -> dict[str, Any]:
        return {"equity_births": dict(self.passed), "equity_refused_by_quota": self.refused, "equity_short": self.short(),
                "equity_want": self.want, "window": dict(self.window), "researching": self.researching}

    def text(self) -> str:
        """The request's quota lines ("" while off)."""
        if not self.on:
            return ""
        total = sum(self.window.values())
        share = (100.0 * self.window["equity"] / total) if total else 0.0
        return (f"EQUITY QUOTA (the last {self.c['window_hours']:g} h of births, every lane): equity lanes "
                f"{self.window['equity']} of {total} ({share:.0f}%); the equity lanes aim at {self.share:.0%} of births. "
                f"Families in Train research: {self.researching} of at most {self.c['max_alive']}. This pass: propose "
                f"{self.want}; more are not born.")


# ----------------------------------------------------------------------------------------------------------- the text
SYSTEM = """You are the architect of the swarm's EQUITY LANES: AI-written programs that trade long-only ETFs (stocks in a
later release) with real money on one brokerage account, cash only, deciding once a session after the close and trading at
the next session's open or close. Propose NEW equity-lane families: each a mechanism with a published reason to exist, a
lane, a universe slice, a card and its first program. Every program is judged the same way, in order: on the Train years
2016-19 and 2022-24 by the bar in the request; then its lineage's ONE Validation try (2025) and ONE sealed holdout look
(2026) by the share screen S2, whose rule and false-positive cap per program were pinned before any look; then, if it
passes, real money at Probe size. The Validation and holdout outcomes are SEALED: nobody who writes programs ever sees
them, you included, so they cannot be fitted; write mechanisms, not history. You know the market's history: a rule that
works only because you know which years fell is not a mechanism. Use scale-free state (returns, realized volatility, a
price against its own moving average or recent high, the calendar fields), never a price level or a date, and never the
sleeve's own dollars since the run began (ctx.equity, ctx.cash, ctx.budget, ctx.caps or a lot's value, pnl or qty against
a constant, a PARAMS value, ctx.budget or what a lot cost: every judged run starts flat, live trading never restarts where
a window does, and a rule whose trading depends on how far the run is ahead or behind is refused, whatever its spelling).

Reply with ONE JSON object: {"families": [{"slug": "short-kebab-name", "lane": "beta or equity", "agenda": "<one key of
THE AGENDA>", "mechanism": "one or two sentences: why it should make money and who pays", "structure": "etf", "symbols":
["SPY"], "rejection": "the Train result that would prove it wrong", "sketch": "how the program decides, in plain words",
"parent": "an equity family id, only when continuing its idea", "differs_from": ["<an EQUITY GRAVEYARD id>"], "card":
{"lane": "beta or equity", "structure": "etf", "symbols": ["SPY"], "hypothesis": "who pays and why the opportunity persists
(60-600 characters), naming its published prior", "mechanism_class": "<one class of the vocabulary>", "inputs": ["<what
the program conditions on>"], "holding": "<one bucket>", "cost": {"hurdle": <the round trip's half-spreads and fees as a
fraction of the position, e.g. 0.0004>, "why": "how you estimated it"}, "comparison": "the naive baseline it must beat:
the same symbols held on the same schedule without the signal's condition", "ablation": {"param": "signal_on", "off": 0},
"falsification": "the concrete result that kills it"}, "program": "<the whole Python file under THE PROGRAM CONTRACT>"}]}.

THE PROGRAM CONTRACT (league/equity/EQUITY.md):
"""


def _symbols_line(settings: Mapping[str, Any] | None) -> str:
    parts = []
    for structure, symbols in universe(settings).items():
        groups: dict[str, list[str]] = {}
        for sym in symbols:
            groups.setdefault(elane_train.symbols_group([sym]), []).append(sym)
        parts.append(f"{structure}: " + "; ".join(f"{g} {', '.join(s)}" for g, s in groups.items()))
    return " | ".join(parts) or "none (elane.universe is empty)"


def lanes_text(settings: Mapping[str, Any] | None) -> str:
    """THE LANES/EQUITY block: each lane's meaning and label, the universe, the contract in brief, the ration and the
    screen ("" while the births are off). Rules only."""
    from . import elane

    if not births_on(settings):
        return ""
    structures = list(universe(settings))
    return "\n".join([
        "THE EQUITY LANES. Two lanes; every proposal and its card declare one: \"lane\": \"beta\" or \"equity\".",
        f"- BETA (labelled {elane.LABELS[BETA]} in every view, brief and report: {elane.BETA_NOTE}): structure etf only. "
        "Programs whose profit is the market's own direction, held on a rule (the overnight effect always in, the turn of "
        "the month), reported beside the same-exposure buy-and-hold and never called alpha.",
        f"- EQUITY (labelled {elane.LABELS[EQUITY]}): structure {' or '.join(structures) or 'etf'}: timing and selection "
        "(trend, momentum and rotation, short-term reversal, low volatility, a conditioned calendar effect); long only, "
        "never short, never margin.",
        f"- THE UNIVERSE (elane.universe; a family trades 1 to {eqconfig.MAX_SYMBOLS} of them and reads only its own): "
        + _symbols_line(settings) + ".",
        "- THE CONTRACT IN BRIEF: decide(ctx) runs once a session after the close on daily bars (prices adjusted as of "
        "that day, never by a later event); an intent executes in the NEXT session, \"at\": \"open\" (default) or "
        "\"close\"; a lot is never sold in the session it was bought; the House exits a lot after its NEEDS "
        "max_hold_sessions (at most 60); an ETF position is at most half the sleeve; fills pay the half-spread (1 bp "
        "the index ETFs, 3 bp the other ETFs, 5 bp TLT and GLD) and sells the SEC and FINRA fees. The whole contract is "
        "in your system prompt.",
        "- THE RATION: ONE Validation try and ONE sealed look a LINEAGE. A family continuing an idea (its parent, or a "
        "dead family of the same slice and idea), the same template, or a program whose Train daily returns correlate "
        "0.7 or more with one already looked at, is the same lineage: once a lineage has its try, a proposal continuing "
        "it is not born, and a near-copy of a looked-at program is refused at the look. Send ideas, not variants.",
        elane_train.bar_text(),
    ])


def agenda_text() -> str:
    """THE AGENDA: the mechanisms a card's `agenda` names, each with its published prior (no figure)."""
    lines = ["THE AGENDA (\"agenda\" names one key; each a published prior, a hypothesis for Train, never evidence):"]
    for key, row in AGENDA.items():
        lines.append(f"- {key}: {row['title']} ({row['lane']}): {row['text']}. Priors: {row['priors']}."
                     + ("" if row["available"] else " REFUSED until its data exist."))
    return "\n".join(lines)


def graveyard_text(store: Any, settings: Mapping[str, Any] | None) -> str:
    """THE EQUITY GRAVEYARD that binds (E2's Train refutations, newest first, and the CLOSED cells); "" when empty."""
    rows = elane_train.refuted_rows(store)
    closed = elane_train.closed_cells(store, settings)
    if not rows and not closed:
        return ""
    lines = ["THE EQUITY GRAVEYARD (families refuted on Train by the bar, newest first; a proposal near one names it in "
             "differs_from and says the mechanism-level difference; a new symbol or parameter of a refuted idea is not "
             "one):"]
    for r in rows:
        lines.append(f"- {r['id']} ({r['lane']} / {r['agenda']} / {', '.join(r['symbols'])}): {r['mechanism']} "
                     f"Refuted on Train after {r['versions']} versions: {', '.join(r['codes']) or 'none scored'}.")
    if closed:
        lines.append("CLOSED CELLS (no birth: refuted on Train too often with no pass): "
                     + "; ".join(elane_train.cell_text(c) for c in closed) + ".")
    return "\n".join(lines)


def seeded_ids(store: Any) -> set[str]:
    """The captain-seeded equity families (E1's kv `elane.SEEDS_KEY`: {seed id: family id})."""
    from . import elane

    value = store.get(elane.SEEDS_KEY)
    return {str(v) for v in (value or {}).values()} if isinstance(value, Mapping) else set()


def tried(fam: Mapping[str, Any]) -> bool:
    """Whether a family's Validation try is taken or due by rule, outcome-free (A9 D3): any equity family E2 did not
    bear (a seeded program is validated as born), or an E2 family with a Train pass."""
    if not elane_train.e2_family(fam):
        return elane_seal.lane_of_spec(fam.get("spec")) is not None
    return elane_train.passed_version(fam) is not None


def tried_text(store: Any, *, limit: int = 40) -> str:
    """The lineages whose one try is taken (seeded programs, other equity programs, Train passes): ids, lanes, symbols;
    never an outcome. "" for none."""
    seeded = seeded_ids(store)
    rows = []
    for fam in elane_seal.equity_families(store):
        if not tried(fam):
            continue
        facts = elane_seal.train_facts(fam, STATE_KEY)
        why = ("seeded by the captain's build agents" if facts["id"] in seeded else
               f"passed Train (v{elane_train.passed_version(fam)})" if elane_train.e2_family(fam) else "born outside E2")
        rows.append(f"- {facts['id']} ({facts['lane']} / {facts['agenda']} / {', '.join(facts['symbols'])}; {why}): "
                    f"{facts['mechanism'][:160]}")
    if not rows:
        return ""
    return ("LINEAGES WITH THEIR TRY (each below has its one Validation try; its outcome is sealed and never shown; a "
            "proposal continuing one is not born):\n" + "\n".join(rows[-limit:]))


def families_text(store: Any, settings: Mapping[str, Any] | None) -> str:
    """The E2 families in Train research or refuted, the newest `families_shown`, Train facts only ("" for none)."""
    shown = cfg(settings)["families_shown"]
    rows = []
    for fam in elane_seal.equity_families(store):
        if not elane_train.e2_family(fam) or elane_train.passed_version(fam) is not None:
            continue
        facts = elane_seal.train_facts(fam, STATE_KEY)
        rec = facts["record"]
        versions = elane_train.versions_of(rec)
        state = ("refuted on Train" if rec.get("status") == "refuted" else
                 "stalled on Train (no version could be judged: nothing said of the mechanism)"
                 if rec.get("status") == "stalled" else f"in Train research, {len(versions)} versions scored")
        rows.append(f"- {facts['id']} ({facts['lane']} / {facts['agenda']} / {', '.join(facts['symbols'])}; {state}): "
                    f"{facts['mechanism'][:160]}")
    if not rows or not shown:
        return ""
    return "EQUITY FAMILIES BORN BY THIS PASS (the newest; Train facts only):\n" + "\n".join(rows[-shown:])


#: THE EQUITY CARD VOCABULARY (E1's `elane.INPUTS` and `elane.CLASSES`, as league/swarm/elane.py fixes them; the copies
#: here are what E1's names are read over when they cannot be read). An equity card's inputs are a daily bar's, the
#: calendar's and the event flags' (no implied vol, chain, skew, open interest or option liquidity: E1's `card_errors`
#: refuses them), and no holding is intraday (a lot is never sold in the session it was bought).
EQUITY_INPUTS: dict[str, str] = {
    "underlying_price": "the symbols' daily bars (ctx.bars[s].open, high, low, close; ctx.prices), always as a ratio or a "
                        "return, never a level",
    "realized_vol": "realized volatility computed from the daily bars",
    "share_volume": "daily share volume (ctx.bars[s].volume), relative to its own history",
    "event_calendar": "the event flags (ctx.events, ctx.events_next: fomc, cpi, jobs, monthly_opex, quarter_end, half_day)",
    "clock": "the session calendar (ctx.weekday, ctx.session_of_month, ctx.sessions_to_month_end)",
    "cross_asset": "another symbol's bars among the family's own",
}
EQUITY_CLASSES_FALLBACK: dict[str, str] = {
    "equity_premium": "the equity risk premium: holders of index ETFs are paid, on average, to bear market risk; a long ETF "
                      "position earns the market's direction (MARKET BETA), reported beside the same-risk buy-and-hold",
}
#: The options classes that name an equity mechanism (the others are about implied volatility, skew, pins or dispersion).
EQUITY_OPTION_CLASSES = ("trend_momentum", "reversal_liquidity", "relative_value", "calendar_flow", "event_premium")
EQUITY_HOLDING: dict[str, str] = {
    "days_1_3": "one to three sessions (a close-to-open overnight hold is one)",
    "days_4_10": "four to ten sessions",
    "days_11_plus": "more than ten sessions (the House exits a lot at its NEEDS max_hold_sessions, at most 60)",
}


def vocabulary_text(settings: Mapping[str, Any] | None) -> str:
    """THE EQUITY CARD VOCABULARY (the constants above): the mechanism classes an equity card may name (the options
    classes that name an equity mechanism, and E1's `elane.CLASSES`), the inputs (E1's `elane.INPUTS`, in equity words)
    and the holdings (no intraday). Never the options words an equity card is refused for."""
    from . import cards, elane

    classes = {k: v for k, v in getattr(cards, "MECHANISM_CLASSES", {}).items() if k in EQUITY_OPTION_CLASSES}
    own = getattr(elane, "CLASSES", None)
    classes.update(dict(own) if isinstance(own, Mapping) and own else EQUITY_CLASSES_FALLBACK)
    names = getattr(elane, "INPUTS", None)
    names = [str(n) for n in names] if isinstance(names, (tuple, list)) and names else list(EQUITY_INPUTS)
    lines = ["FAMILY CARD VOCABULARY (each equity card uses exactly these words):", "MECHANISM CLASSES:"]
    lines += [f"- {k}: {v}" for k, v in classes.items()]
    lines += ["INPUTS (an equity program reads daily bars, the calendar and the event flags only):"]
    lines += [f"- {n}: {EQUITY_INPUTS.get(n, n.replace('_', ' '))}" for n in names]
    lines += ["HOLDING:"] + [f"- {k}: {v}" for k, v in EQUITY_HOLDING.items()]
    lines += ["REBIRTH (only for a card in the cell of an EQUITY GRAVEYARD row of its lane): \"rebirth\": {\"row\": "
              "\"<that row's id>\", \"different\": \"the mechanism-level change\", \"evidence\": \"what the new input "
              "shows\"}, with an input the dead row did not read among the card's inputs."]
    return "\n".join(lines)


def last_text(store: Any) -> str:
    last = store.get(LAST_KEY)
    items = last.get("refused") if isinstance(last, Mapping) else None
    if not items:
        return ""
    lines = [f"- {i.get('slug')}: {i.get('why')}"[:600] for i in items[:REFUSALS_SHOWN] if isinstance(i, Mapping)]
    return (f"YOUR LAST EQUITY PASS'S PROPOSALS NOT BORN ({last.get('at')}; fix them or look elsewhere):\n"
            + "\n".join(lines))


# ----------------------------------------------------------------------------------------------------------- the pass
class EquityPass:
    """THE EQUITY PASS (the module docstring), over the architect's store, router, settings and clock."""

    def __init__(self, architect: Any):
        self.architect = architect
        self.store = architect.store
        self.router = architect.router
        self.settings = architect.settings
        self.clock = architect.clock
        self.refused: list[dict[str, Any]] = []

    def request(self, quota: EquityQuota) -> tuple[str, str]:
        """(the system prompt, the request)."""
        want = quota.want
        lead = ""
        last = self.store.get(LAST_KEY)
        if isinstance(last, Mapping) and int(last.get("short") or 0):
            lead = (f"YOUR LAST EQUITY PASS LEFT {int(last['short'])} OF ITS BIRTHS UNFILLED: propose families that fit "
                    "the lanes' box, the agenda and the bar below.\n\n")
        parts = [f"{lead}Propose {want} new EQUITY-LANE families (\"lane\": \"beta\" or \"equity\"), each with its card "
                 "and its first program; propose both lanes when you propose two or more.",
                 lanes_text(self.settings), agenda_text(), quota.text(),
                 elane_train.train_map_text(self.store, self.settings), graveyard_text(self.store, self.settings),
                 tried_text(self.store), families_text(self.store, self.settings), vocabulary_text(self.settings),
                 last_text(self.store)]
        return SYSTEM + elane_train.contract_text(), "\n\n".join(p for p in parts if p)

    def run(self) -> dict[str, Any]:
        """One equity pass: the quota, the route, the request, the admission, the event."""
        from .architect import read_families

        began = self.clock()
        self.store.put(BIRTHS_AT_KEY, began)
        if not births_on(self.settings):
            return self.finish({"skipped": "off", "why": "the equity lanes' births are off (elane.mode, elane.birth_share)"})
        quota = EquityQuota(self.store, self.settings, now=began)
        if quota.want <= 0:
            return self.finish({"skipped": "full", "why": "no equity birth is wanted now", **quota.event()})
        held = elane_yield.hold(self.store, self.settings, began)
        if held is not None:
            skipped = ("usd_day" if held == elane_yield.DAY_SPENT else
                       "sail_day" if held.startswith(elane_yield.SAIL_DAY) else "pace")
            return self.finish({"skipped": skipped, "why": held})
        candidates = elane_yield.routes(self.settings, self.router)
        turn = elane_yield.next_turn(self.store)
        first, why_route = elane_yield.choose(self.store, self.settings, candidates, turn=turn, train_key=STATE_KEY)
        system, user = self.request(quota)
        c = cfg(self.settings)
        answer, route, errors = elane_yield.ask(
            self.router, self.store, self.settings, first=first, role=ROLE, system=system, user=user,
            key=f"swarm:elane:births:{int(began)}", max_output=c["births_max_output_tokens"], effort=c["births_effort"],
            purpose="births", now=began)
        if answer is None or route is None:
            return self.finish({"born": [], "error": "no route answered", "errors": errors[:4], "turn": turn,
                                "route_chosen": first.key if first else None, **quota.event()})
        rows, lenient, recovered = read_families(answer)
        born = self.admit(rows or [], quota, route)
        elane_yield.book_births(self.store, route.key, len(born))
        self.store.put(LAST_KEY, {"at": self.store.now(), "born": born, "short": quota.short(), "route": route.key,
                                  "refused": self.refused[:REFUSALS_SHOWN]})
        out = {"born": born, "proposed": len(rows or []), "route": route.key, "route_chosen": first.key if first else None,
               "why_route": why_route, "turn": turn, "cost_usd": answer.get("cost_usd"),
               "truncated": bool(answer.get("truncated")),
               "refused": {"count": len(self.refused), "items": [{k: r.get(k) for k in ("slug", "why")}
                                                                 for r in self.refused[:REFUSALS_SHOWN]]},
               **quota.event()}
        if errors:
            out["route_errors"] = errors[:4]
        if lenient:
            out["lenient"] = True
        if recovered:
            out["recovered"] = recovered
        return self.finish(out)

    def finish(self, out: dict[str, Any]) -> dict[str, Any]:
        out = {"pass": "births", **out}
        self.store.event("swarm.elane", None, out)
        return out

    # ------------------------------------------------------------------ the admission
    def refuse(self, slug: str, why: str) -> None:
        self.refused.append({"slug": slug, "why": why[:600]})

    def lineage_tried(self, parent: Mapping[str, Any]) -> bool:
        """Whether the lineage a proposal continues has its one Validation try (`tried`: outcome-free, A9 D3)."""
        lines = elane_seal.lineages_of(self.store, str(parent["id"]))
        return any(tried(f) for f in elane_seal.families_in(self.store, lines))

    def rebirth_index(self) -> Any:
        """THE GRAVEYARD BINDS (the module docstring): E1's `cards.RebirthIndex` over the rows of the families E2 refuted
        on Train ONLY (every other equity family excluded: no row with an outcome lesson is read, A9 D3), or None while
        `architect.card_rebirth` is "off", or False when it cannot be read (fail closed: nothing is born unchecked)."""
        from . import cards

        mode = getattr(self.architect, "rebirth_mode", None)
        try:
            if callable(mode) and mode() != "refuse":
                return None
            keep = {r["id"] for r in elane_train.refuted_rows(self.store, limit=10 ** 6)}
            return cards.RebirthIndex(self.store, self.settings, exclude=frozenset(elane_seal.equity_ids(self.store) - keep))
        except Exception:  # noqa: BLE001 - a binding that cannot be read admits nothing
            return False

    def admit(self, rows: Sequence[Any], quota: EquityQuota, route: elane_yield.Route) -> list[str]:
        """Birth the proposals the admission admits (the module docstring); every refusal named."""
        from . import cards
        from .architect import family_slug, same_idea

        allowed = universe(self.settings)
        closed = set(elane_train.closed_cells(self.store, self.settings))
        fams = elane_seal.equity_families(self.store)
        known_rows = {r["id"] for r in elane_train.refuted_rows(self.store, limit=10 ** 6)}
        index = self.rebirth_index() if rows else None
        born: list[str] = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            mechanism = " ".join(str(row.get("mechanism") or "").split())[:600]
            slug = family_slug(row.get("slug") or mechanism or "equity")
            raw_card = row.get("card") if isinstance(row.get("card"), Mapping) else None
            lane = str((raw_card or {}).get("lane") or row.get("lane") or "").strip().lower()
            if lane not in LANES:
                self.refuse(slug, f"lane: {lane or 'none'!r} is not \"beta\" or \"equity\"")
                continue
            if raw_card is not None and raw_card.get("lane") and row.get("lane") and \
                    str(raw_card["lane"]).lower() != str(row["lane"]).lower():
                self.refuse(slug, "lane: the proposal and its card declare different lanes")
                continue
            structure = str(row.get("structure") or (raw_card or {}).get("structure") or "").strip().lower()
            if structure not in allowed:
                self.refuse(slug, f"structure: {structure or 'none'!r} is not one of {', '.join(allowed) or 'none'} "
                                  "(elane.structures)")
                continue
            if lane == BETA and structure != eqconfig.ETF:
                self.refuse(slug, "structure: a beta family trades ETFs only")
                continue
            named = row.get("symbols") if isinstance(row.get("symbols"), list) else (raw_card or {}).get("symbols")
            symbols = list(dict.fromkeys(str(s).upper() for s in (named or []) if str(s).strip()))
            foreign = [s for s in symbols if s not in allowed[structure]]
            if not symbols or len(symbols) > eqconfig.MAX_SYMBOLS or foreign:
                self.refuse(slug, f"symbols: 1 to {eqconfig.MAX_SYMBOLS} of {', '.join(allowed[structure])}"
                                  + (f" ({', '.join(foreign[:6])} not)" if foreign else ""))
                continue
            agenda = str(row.get("agenda") or "").strip().lower()
            if agenda not in AGENDA:
                self.refuse(slug, f"agenda: {agenda or 'none'!r} is not one of {', '.join(AGENDA)}")
                continue
            if not AGENDA[agenda]["available"]:
                self.refuse(slug, f"agenda: {agenda} needs data the House does not hold yet: {AGENDA[agenda]['text']}")
                continue
            if len(mechanism) < MIN_MECHANISM:
                self.refuse(slug, "mechanism: one or two sentences saying why it should make money")
                continue
            cell = elane_train.cell_of(lane, agenda, symbols)
            if cell in closed:
                self.refuse(slug, f"its cell {elane_train.cell_text(cell)} is CLOSED: refuted on Train too often with no "
                                  "pass")
                continue
            same_slice = [f for f in fams if elane_seal.lane_of_spec(f.get("spec")) == lane
                          and sorted((f.get("spec") or {}).get("symbols") or f.get("roots") or []) == sorted(symbols)
                          and same_idea(str(f.get("mechanism") or ""), mechanism)]
            # E2's record alone says a family is in research (never its retirement: A9 D3).
            busy = [f for f in same_slice if elane_train.e2_family(f)
                    and elane_train.record_of(f).get("status", "researching") == "researching"]
            if busy:
                self.refuse(slug, f"the same idea on the same symbols is in Train research: {busy[-1]['id']}")
                continue
            # THE LINEAGE IT CONTINUES, every one of them: the parent it declares AND every family of its slice with the
            # same idea (the admission checked ONE, the declared parent or else the newest of the slice, so naming any
            # untried equity family as the parent, or a newer untried family of the slice, hid a lineage that has its
            # try: the integration review's seal-3). Any of them tried refuses the birth; the lineage is assigned only
            # once all are clear.
            mother = None
            declared = str(row.get("parent") or "").strip()
            if declared:
                found = self.store.family(declared)
                if found is not None and elane_seal.lane_of_spec(found.get("spec")) is not None:
                    mother = found
            kin = ([mother] if mother is not None else []) + list(reversed(same_slice))
            tried_kin = next((f for f in kin if self.lineage_tried(f)), None)
            if tried_kin is not None:
                self.refuse(slug, f"it continues {tried_kin['id']}'s lineage, which has its one Validation try "
                                  "(outcome sealed): propose a different idea")
                continue
            parent = mother if mother is not None else (same_slice[-1] if same_slice else None)
            card = dict(raw_card or {})
            card.update({"lane": lane, "structure": structure, "symbols": symbols})
            try:
                checked, problems = cards.validate(card, structure, roots=symbols, settings=self.settings)
            except Exception as exc:  # noqa: BLE001 - a card that cannot be checked is not born
                checked, problems = None, [f"the card could not be checked: {type(exc).__name__}"]
            if checked is None:
                self.refuse(slug, "card: " + "; ".join(problems)[:500])
                continue
            if index is False:
                self.refuse(slug, "the equity graveyard's binding could not be read: not born unchecked")
                continue
            if index is not None:
                try:
                    verdict = index.check(checked, structure, mechanism, None, roots=symbols)
                except Exception as exc:  # noqa: BLE001 - a binding that cannot be read admits nothing
                    verdict = {"ok": False, "reason": f"the graveyard's binding could not be read ({type(exc).__name__})"}
                if not verdict.get("ok"):
                    self.refuse(slug, "graveyard: " + str(verdict.get("reason") or "a refuted row binds its cell")[:500])
                    continue
                if verdict.get("dropped"):
                    checked = {k: v for k, v in checked.items() if k != "rebirth"}
                if verdict.get("rebirth"):
                    reborn = self.store.family(str(verdict.get("row") or ""))
                    if reborn is not None:
                        if self.lineage_tried(reborn):  # whatever parent it declared: the row it is reborn from binds
                            self.refuse(slug, f"its rebirth continues {reborn['id']}'s lineage, which has its one "
                                              "Validation try (outcome sealed): propose a different idea")
                            continue
                        if parent is None:
                            parent = reborn
                    note = getattr(index, "note_birth", None)
                    if callable(note):
                        note(checked, structure)
            if not quota.admits(lane):
                self.refuse(slug, quota.why_not(lane) or "the quota")
                continue
            fid = self.birth(row, slug=slug, lane=lane, structure=structure, symbols=symbols, agenda=agenda,
                             mechanism=mechanism, card=checked, parent=parent, route=route, known_rows=known_rows)
            if fid is None:
                continue
            quota.born(lane)
            born.append(fid)
            fams.append(self.store.family(fid) or {"id": fid})
        return born

    def birth(self, row: Mapping[str, Any], *, slug: str, lane: str, structure: str, symbols: list[str], agenda: str,
              mechanism: str, card: Mapping[str, Any], parent: Mapping[str, Any] | None, route: elane_yield.Route,
              known_rows: set[str]) -> str | None:
        """One birth: the family, its card, its first version (when its program passes the static checks), E2's record
        and the `swarm.born` event. None when the store refused it (named among the refusals)."""
        from . import cards

        code = row.get("program") if isinstance(row.get("program"), str) else None
        why_code = elane_train.check_code(code, symbols) if code else "the proposal carried no program"
        spec = {"id": slug, "mechanism": mechanism, "structure": structure, "roots": symbols, "symbols": symbols,
                "lane": lane, "agenda": agenda, "rejection": " ".join(str(row.get("rejection") or "").split())[:400],
                "sketch": " ".join(str(row.get("sketch") or "").split())[:800], "lessons": [],
                "card_sha": cards.card_sha(card), elane_yield.ROUTE_KEY: route.key}
        cited = [str(x) for x in (row.get("differs_from") or []) if str(x) in known_rows][:3] \
            if isinstance(row.get("differs_from"), list) else []
        try:
            with self.store.atomic():
                fam = self.store.add_family(spec, origin="architect", parent=str(parent["id"]) if parent else None)
                fid = str(fam["id"])
                cards.put(self.store, fid, card, structure)
                record: dict[str, Any] = {"status": "researching", "versions": {}, "agenda": agenda,
                                          "born_route": route.key, "last_at": ""}
                if why_code is None:
                    self.store.add_version(fid, str(code), {}, author=f"architect:{route.key}",
                                           note="the architect's program at birth")
                elif code:
                    record["refused"] = [{"at": self.store.now(), "why": f"the architect's program: {why_code}"}]
                self.store.set_state(fid, **{STATE_KEY: record})
        except Exception as exc:  # noqa: BLE001 - not born; the next request names why
            self.refuse(slug, f"not born: {type(exc).__name__}: {str(exc)[:200]}")
            return None
        if spec["sketch"]:
            self.store.note(fid, f"The architect's sketch: {spec['sketch']}")
        for item in cited:
            self.store.note(fid, f"The architect: differs from {item}")
        payload = {"parent": str(parent["id"]) if parent else None, "mechanism": mechanism, "structure": structure,
                   "roots": symbols, "origin": "architect", "lane": lane, "agenda": agenda, "route": route.key,
                   "card": {"sha": spec["card_sha"], "class": card.get("mechanism_class")},
                   "program": "v1" if why_code is None else "none"}
        self.store.event("swarm.born", fid, payload)
        return fid


__all__ = ["BIRTHS_AT_KEY", "LAST_KEY", "DEFAULTS", "BOUNDS", "SYSTEM", "cfg", "lane_cfg", "birth_share", "births_on",
           "universe", "researching", "due", "EquityQuota", "lanes_text", "agenda_text", "graveyard_text", "seeded_ids",
           "tried", "tried_text", "families_text", "vocabulary_text", "last_text", "EquityPass"]
