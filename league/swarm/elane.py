"""THE EQUITY LANES (release E1, Oct 2026): agent programs that trade long-only ETFs (and later stocks), beside the
options lanes, judged by the pinned share screen (S2, the captain's amendment A11: receipt 2; S1+F1 stays in code as
receipt 1's screen, unused while no lane pins it) and traded by the House's EquityBook.

Owner: swarm. Protected like league/swarm/dlane.py (league/ci.py FORBIDDEN; the gateway's MERGE_FORBIDDEN in a later
gateway PR). The lanes' one swarm-side home: their settings and bounds, the card box, the screen they use, the ration
(one Validation try and one holdout look a lineage), the equity roster, the three captain-seeded programs, and the
labels every view carries. With `elane.mode` "off" (the code's default; the rollback) nothing here acts.

THE LANES (`league.equity.LANES`): "beta" (structure "etf"; every view, brief, status line and report labels it MARKET
BETA: its profit is the market's direction, stated plainly) and "equity" ("etf" and "stock": trend, momentum, mean
reversion, low volatility, rotation; earnings drift waits for data). A family's lane is its card's (`card.lane`),
immutable, inherited by a fork (league/swarm/store.py: a fork stays in its parent's lane). Its spec carries the same word,
and its structure is "etf" or "stock" exactly when it has one (`store.add_family` holds them together), so every options
reader of the store skips the equity lanes (`SwarmStore.families(lanes=None)`, `bands.read(root)`). In E1
`elane.structures` is ["etf"] and the births are the three seeds (A4); the architect's and the researcher's equity
births are E2.

SETTINGS (`cfg`; policy.json "elane", swarm.json over it; `DEFAULTS` is the rollback):
- `mode` "off" | "gate" (default "off"; a malformed mode reads "off");
- `universe` (inside league/equity/config.py UNIVERSE; the constitution's `equity_money.universe` bounds it),
  `structures` (["etf"] in E1);
- `birth_share` 0 in E1 (taken out of the alpha share first, E2; bounded 0-0.5);
- `roster`, which equals `equity_money.probe.max_programs` (a test holds them equal; the two are set together, with
  the Probe sleeve, by `set_design SEATS SLEEVE`: the constitution's `probe` comment): equity Probe seats, apart from
  `dlane.roster` (league/swarm/bands.py `seating`); a setting may only lower it (0 to the default), and 0 seats no
  equity program;
- `screens`: per lane the pinned receipt's block, read from the REPOSITORY's policy.json only (never swarm.json):
  {"name" and "screen" "S2", "receipt_sha256", "c_R" 0, "c_H_floor", "c_H_margin", "c_X", and the receipt's figures}
  (A11; receipt 1's block is {"name": "S1", "receipt_sha256", "c_R", "c_X", ...}). The block's `screen` (or `name`)
  picks the screen (`SCREENS`; league/equity/screen.py `screen_of`). Tests hold the sha to the screen's file
  (docs/benchmarks/equity_screen_2.json for S2, equity_screen_1.json for S1) and the block's figures to the file's; with
  no pinned receipt the screen refuses every program (`screen_effective`, league/equity/screen.py `pinned_receipt`),
  and so does a receipt file at hand whose bytes are not the pinned sha256 (`_receipt`: THE RECEIPT'S BYTES);
- `val_tries` 1 and `looks_per_lineage` 1 (whatever is written), plus R3's one Validation-only retry when the
  receipt permits it and the first try FAILED its pre-check, the retry version's hash recorded at the first try
  (A9 D3; league/equity/screen.py `retry_permitted`);
- `program_loss_usd` -300 (a tightening only: -300 to -25).

THE ROUNDS RUN ON THEIR OWN (A3: no Gym box, no model dollar). The swarm's main loop starts the two equity rounds below on
their own thread every `ROUND_SECONDS` while the lane is on (league/swarm/loop.py `Swarm.equity_rounds`: the
tournament's step, then the gate's, so a version validated in a round takes its look in the same round). Neither the
research budget's brake nor a Gym that is down or switched off holds them, and no options round carries them: an
options Validation that fails or runs long never costs an equity family its turn.

THE ROUND (who calls what). The tournament's equity round (league/swarm/tournament.py `Tournament.equity_round`) asks
`validate` of each living Gym-band equity family's candidate version (`candidate`: its best, else its newest) while
`try_open` allows it, and retires a family whose lineage is spent (`lineage_spent`). `validate` runs the version on
Validation (2025) at k 1.0 and 1.5 in the decider-isolated child on the House (`isolated_runner`, A3: no Gym box),
records both runs (each a trial), the version's per-trade net-return sd (`SIGMA_KEY`: EDM1's sigma) and the
screen's pre-check (S1's and S2's are one rule), and the lineage's try (`TRY_KEY`); a passed pre-check makes the version
gate-ready. The gate's equity round (league/swarm/gate.py `Gate.equity_round`) asks `look` of each gate-ready equity
family: the screen's pinned receipt (none: refused, no look spent), the daily store holding the look's whole calibrated
holdout (`_holdout_gap`, A12: else the look waits), the program floor from its Train-era runs under that receipt
(`screen.floor(segments, receipt=)`: S2's exact floor for receipt 2; ineligible: refused, no look spent; a floor kept
for the version under another receipt is run again, `screen.floor_fits`), THE LINEAGE (below), the recorded Validation
run reproduced and pre-checked again, then the ONE sealed look with a freshly minted `EquityGateCapability`, judged by
`screen.verdict` under the same receipt; a pass makes the family a Candidate whose band proof is the
equity identity (`banded_evaluator` {"engine", "equity_sha256", "run_sha"}). From there the EquityBook moves its band
(league/equity/bands.py `next_band`), inside `roster` seats.

THE RUN'S STATUS, AND A RUN THAT DOES NOT RETURN. Every run the look reads is read by its status first, as Validation's
is. A Train-era run its own errors ended ("disqualified") gives no floor (refused at the floor, no look spent); one with
no data is no history there (the screen's rule). A holdout run that ended "disqualified" is a look SPENT AND FAILED: a
partial series is never judged. A holdout run the House could not make at all (the capability, the store's slice, the
NEEDS call, a child that could not be started or did not take the request, an answer that is not a result, "no_data")
is no look and is owed again, counted against no program. But once the child took the sealed run whole and no answer
came back (league/equity/runner.py `RunLost`: it ran past its budget or exited while the program held its holdout), it
is owed again only once: the second time (`LOOK_SENDS`) the look is spent and failed, with a House warning each time,
so a program cannot stop answering until its holdout suits it. The evidence child's hash seed is pinned
(`EVIDENCE_HASH_SEED`), so the run owed again is the same run.

THE REVIEW (E1). The gate's paid program review and audit read options programs. In E1 an equity look is taken only for
a captain-seeded program (its code is reviewed in the release's pull request) or a version whose state carries a passed
review and audit of its exact program (`reviewed`): the architect's and researcher's equity births (E2) wait for the
equity review.

THE LINEAGE (A9 D3): a program whose Train daily returns correlate >= 0.7 with a program already looked at in either
equity lane (`league.equity.screen.same_lineage`, over the House-only Train series each look keeps, `TRAIN_R_KEY`), or
that uses the same template in its own lane (`TEMPLATE_KEY`: its code's sha, lane-scoped by `lineage_key`), is the same
lineage: one look a lineage. The series and the template are THE LOOK'S LINEAGE RECORD: kept for good, an equity
identity adoption included (league/swarm/evaluator.py `EQUITY_SELECTION_KEYS` leaves them), and the test FAILS CLOSED:
a program already looked at that keeps no series has it written again from its looked version's Train-era runs
(`_restore_train`), and where that cannot be done the look waits (`LineageUnread`). Look and Validation outcomes of
share programs are never fed back to generators or the diagnostician: no graveyard row is written for an equity family
in E1 (the options architect reads the graveyard), and no options reader sees an equity family
(`SwarmStore.families`).

LANE-SCOPED KEYS (A8.12): lineage, spent-root and graveyard keys carry the lane (`lineage_key`), so the options lanes'
spent SPY/QQQ/IWM always-in roots never refuse an equity birth, and a REFUTED equity row binds only its own lane's cards
(league/swarm/cards.py: an equity card's cell is "<lane>:etf", and `RebirthIndex` reads each lane's rows apart).

THE SEEDS (A4; league/swarm/seeds.py `EQUITY_SEEDS`): seed-overnight-qqq, seed-reversal-index, seed-overnight-spy,
each born once as an agent-authored family (`birth_seeds`), then Validation, the screen's pre-check and one sealed look
like any family. THEIR LOOKS ARE TAKEN IN THAT DECLARED ORDER, and the order is a decision (the captain's, Oct 11,
2026, from Train-era figures only, before any Validation or look: amendment A18): the two overnight seeds share a
template and are one lineage, so only the first of them declared is ever judged and the other is refused with no
look and retired as the same lineage. Two rules hold it: `round_order` (both equity rounds walk the seeds as one block,
in the list's order, whatever second each was born in) and `seed_wait`, which is STRICT WITHIN A LINEAGE (amendment
A18): each seed's `lineage` in the list declares the lineage it is in, and a seed's look is never taken while a seed
declared before it in the same lineage is alive without a verdict (`seed_owed`). THERE IS NO TIMEOUT: the later seed
waits until the earlier one has been looked at (D3 then refuses the later one), has FAILED its Validation pre-check
with no retry owed, or is retired, so a look the House owes again, a hold or a slow data job never hands the lineage's
one look to the wrong seed. `look` asks it at its last step before the sealed run, so the wait's clock counts only the
rounds in which the later seed's own look was otherwise ready; a counted wait past `SEED_WAIT_SECONDS` is ONE House
warning naming both seeds and why the earlier one has no verdict yet (again at most daily), cleared when the wait
ends. Seeds of different lineages never wait on each other, and a family that is no seed waits for none. A version
refused at the gate before its look retires for what happened (`REFUSED_CAUSES`: the same lineage, no eligible floor),
not as a spent Validation try. Every report says plainly that these three were seeded by the captain's build agents
(`SEEDED_NOTE`), and the Done meter reads Done with and without them (`seeded`).

THE SEAT RULE'S TWO COUNTS (release E5-A; the captain's A24; league/equity/bands.py `seat_counts`, `seat_k`). A free
equity seat goes to the best-ranked waiting passed program, and its rank K is the smaller of its Validation close
days and its Train-era close days per 250 sessions. `look` writes the two counts beside the look (`SEAT_KEY`), ONCE,
from the runs it already makes before the sealed run (the recorded Validation run it reproduced, and the Train-era
runs of the floor): K is fixed when the look is recorded. A PROGRAM THAT PASSED BEFORE THE RELEASE has no record;
`seat_backfill` (called at the end of the gate's equity round) writes it once: the Validation count from the STORED
run whose `result_sha` is the one its look reproduced (the swarm store's own run file; when that file is gone, the
Validation run made again), the Train-era count from the Train-era runs made again (`Isolated.segments`: the look
keeps their series, not their lots). NO SEALED FIGURE IS READ OR PRINTED BY EITHER PATH: neither mints a gate
capability, neither calls `Isolated.look`, both read the unsealed Validation and Train-era windows only, and what
they keep is four whole numbers (close days and sessions), which count lots by size and exit day and read no price,
return or P&L. The counts are House-only (family state; a private `_counts` in the gate's event): the EquityBook reads
them in its rows (`bands.read(..., queued=True)`: `seat_activity`) and every report shows a rank position, never K.

Standard library only at import (league/equity/__init__.py and config.py); the screen, the runner and the store (numpy)
are imported where they are used, on the House.
"""

from __future__ import annotations

import dataclasses
import json
import math
import re
import threading
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..equity import BETA, EQUITY, EQUITY_ENGINE_VERSION, LANES
from ..equity import config as econfig

MODES = ("off", "gate")
STRUCTURES = ("etf", "stock")
LABELS = {BETA: "MARKET BETA", EQUITY: "EQUITY"}
#: The plain statement beside every beta figure (the goal's item 2: a BETA lane, labelled as market beta).
BETA_NOTE = "MARKET BETA: profit from market direction, reported beside the same-risk buy-and-hold; not alpha"
SEEDED_NOTE = "seeded by the captain's build agents (A4), judged by the swarm's screen like any family"
#: The store's kv key of the seeds already born ({seed id: family id}).
SEEDS_KEY = "elane_seeds"
#: THE EQUITY LANES' ROUNDS (league/swarm/loop.py `Swarm.equity_rounds`): the store's kv key of the last round's start,
#: and the seconds between two rounds (the gate's own default pace: a Validation or a look is milliseconds a year of
#: daily bars, and a look that waits for the data job is asked again each round).
ROUND_KEY = "elane_round_at"
ROUND_SECONDS = 300.0
#: THE SEEDS' DECLARED ORDER, STRICT WITHIN A LINEAGE (`seed_wait`, amendment A18): the family state's key of a seed's
#: wait for the earlier seed of its declared lineage ({for, why, since, at, waited, asks, alerted}); the counted wait
#: past which ONE House warning names both seeds (NO TIMEOUT: the wait goes on); the seconds before that warning is
#: said again while the wait lasts; and the longest time between two asks that still counts as waiting (two rounds:
#: the clock counts only the rounds in which the later seed's own look was otherwise ready).
SEED_WAIT_KEY = "elane_seed_wait"
SEED_WAIT_SECONDS = 1800.0
SEED_WAIT_REPEAT_SECONDS = 86400.0
SEED_WAIT_GAP_SECONDS = 2 * ROUND_SECONDS
#: The family state's key of its equity lineage's Validation try ({version, at, first, precheck, entered, retry_sha}).
TRY_KEY = "elane_try"
#: The family state's keys (league/equity/INTERFACES.md section 8.4): the one look ({version, at, verdict, beside,
#: activity: the invested-day shares `_invested_shares` records beside it, House-only}),
#: the program floor by version, the looked version's Train daily series (House-only: never in a view), the version's
#: lane-scoped template key, the last Validation ({version, passed, precheck, screen, status, at, result_sha, stale}),
#: each version's Validation verdict ({str(n): {entered, at, stale}}) and EDM1's sigma by version.
LOOK_KEY = "elane_look"
FLOOR_KEY = "elane_floor"
#: THE SEALED RUN, SENT AND NOT ANSWERED (`look`; league/equity/runner.py `RunLost`): the family state's count of it
#: for one program ({sha, count, at}), and how often a program's sealed run may be sent. A first run that does not
#: return is owed again (a House that lost its child once costs no lineage its look); a second spends the look as
#: FAILED. Without the line a program that stops answering when its holdout goes badly would be shown it again.
LOST_KEY = "elane_look_lost"
LOOK_SENDS = 2
#: The hash seed of the swarm's evidence child (`isolated_runner`): every Validation, Train-era and sealed run is the
#: same run on every start of the child (a program that iterates a set of strings would otherwise differ from process
#: to process; the options Gym pins PYTHONHASHSEED=0 for the same reason, league/gym/driver.py).
EVIDENCE_HASH_SEED = 0
TRAIN_R_KEY = "elane_train_r"
TEMPLATE_KEY = "elane_template"
VALIDATION_KEY = "elane_validation"
VERDICTS_KEY = "elane_verdicts"
SIGMA_KEY = "validation_r_sd_by_version"
#: K's TWO COUNTS (THE SEAT RULE'S TWO COUNTS, the module docstring), written ONCE beside the look and never again for
#: the same program: {version, run_sha, floor, validation {close_days, sessions}, train {close_days, sessions}, at,
#: source "look" | "backfill", validation_run "look" | "stored" | "rerun"}. House-only: never in a view.
SEAT_KEY = "elane_seat"
#: Seconds before a backfill that failed is tried again for the same program (`seat_backfill`; kept in this process).
SEAT_RETRY_SECONDS = 3600.0
#: The share screens a lane's block may pin (league/equity/screen.py `SCREENS`; a test holds the two lists equal): "S2"
#: is the House's gate (amendment A11, receipt 2); "S1" (A7 as amended by A9, receipt 1) stays in code, unused while no
#: lane pins it. `SCREEN` is the screen of a block that names none (receipt 1's blocks may be written so).
SCREENS = ("S1", "S2")
SCREEN = "S1"
#: The daily store's directory under the House's state root.
STORE_DIR = "equity-daily"
#: Where a receipt's file is looked for (the repository's root: `screen.receipt_path` is relative to it). The House
#: box's release carries league/, ltcm/, playbooks/, scripts/ and deploy/ only (scripts/floor_box.py `UPLOAD_TREES`), so
#: no receipt file is ever at hand there.
REPO = Path(__file__).resolve().parents[2]
#: The author every seeded version carries (A4: written by the captain's build agents, judged like any family).
SEED_AUTHOR = "captain-build-agent"
#: The mechanism classes an equity card may name: the options vocabulary's (league/swarm/cards.py `MECHANISM_CLASSES`)
#: and the lanes' own `equity_premium` (a beta card's natural class).
CLASSES: dict[str, str] = {
    "equity_premium": "the equity risk premium: holders of index ETFs are paid, on average, to bear market risk; a long "
                      "ETF position earns the market's direction (MARKET BETA), reported beside the same-risk "
                      "buy-and-hold",
}
#: What an equity program may condition on (league/equity/EQUITY.md ctx): the options vocabulary's inputs that a daily
#: bar, the calendar and the event flags carry. No implied vol, chain, skew or open interest.
INPUTS = ("underlying_price", "realized_vol", "share_volume", "event_calendar", "clock", "cross_asset")
#: A Validation run that is no try: the runner could not run it. A program's own errors ("disqualified") are its try.
NOT_A_TRY = ("error", "no_data")
#: The public causes of `lineage_spent` (a `swarm.retired` cause): rules only, no figure.
SPENT_LOOK = "its equity lineage has used its one sealed look (one Validation try and one look an equity lineage)"
SPENT_TRY = "its equity lineage has used its one Validation try (one Validation try and one look an equity lineage)"
#: A version that passed its Validation pre-check and was REFUSED AT THE GATE BEFORE ITS LOOK (`_refuse`: no look was
#: taken) retires for what happened, by the refusal's stage; a stage not named here reads `REFUSED_BEFORE_LOOK`.
SAME_LINEAGE = ("its program is the same lineage as a program already looked at (A9 D3: Train daily returns "
                "correlating at 0.7 or more, or the same template): one sealed look a lineage, so it was refused "
                "before any look")
FLOOR_INELIGIBLE = ("the share screen has no eligible program floor for it (too little Train-era history, a Train-era "
                    "run its own errors ended, or no threshold on the screen's grid): it was refused before any look")
REFUSED_BEFORE_LOOK = ("the gate refused its program before the sealed look (its recorded Validation no longer passes "
                       "the screen's pre-check, or the lineage's look was already spent): no look was taken")
REFUSED_CAUSES = {"same lineage": SAME_LINEAGE, "screen floor": FLOOR_INELIGIBLE}

DEFAULTS: dict[str, Any] = {
    "mode": "off",
    "universe": ["SPY", "QQQ", "IWM", "DIA"],
    "structures": ["etf"],
    "birth_share": 0.0,
    "roster": 6,
    "screens": {BETA: {"name": "S1", "receipt_sha256": None, "c_R": None, "c_X": None, "fp_cap": None,
                       "owner_wall": None, "retry": False, "r4": {}, "beside": None},
                EQUITY: {"name": "S1", "receipt_sha256": None, "c_R": None, "c_X": None, "fp_cap": None,
                         "owner_wall": None, "retry": False, "r4": {}, "beside": None}},
    "val_tries": 1,
    "looks_per_lineage": 1,
    "program_loss_usd": -300,
}

_SHA = re.compile(r"^[0-9a-f]{64}$")


# ----------------------------------------------------------------------------------------------------------- settings
def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def _token(value: Any) -> str:
    return re.sub(r"[\s\-]+", "_", str(value or "").strip().lower())


def _screen_name(raw: Any) -> str | None:
    """The screen a lane's block names, read as league/equity/screen.py `screen_of` reads a block (a test holds the two
    equal; that module needs numpy, and this one is read where numpy is not): its `screen` or its `name`, `SCREEN` when
    it names neither; None when the two disagree or name no screen of `SCREENS`."""
    raw = raw if isinstance(raw, Mapping) else {}
    named = [raw[key] for key in ("screen", "name") if key in raw]
    if not named:
        return SCREEN
    if not all(isinstance(x, str) for x in named) or len(set(named)) != 1:
        return None
    return named[0] if named[0] in SCREENS else None


def _screen_block(raw: Any) -> dict[str, Any]:
    """A lane's screen block as written: `name` the screen it names (`_screen_name`: "S1" | "S2", None for no screen
    this code runs); a 64-hex receipt sha else None; `c_R`, `c_X` and S2's `c_H_floor`, `c_H_margin` finite in [0, 5]
    else None; `fp_cap` and `owner_wall` in (0, 0.15] (the owner's wall) else None; `retry` True only when written so;
    `r4` a mapping of archetype -> list of words; `beside` a non-empty template string else None."""
    raw = raw if isinstance(raw, Mapping) else {}
    sha = raw.get("receipt_sha256")

    def bounded(key: str, low: float, high: float, *, open_low: bool = False) -> float | None:
        value = _num(raw.get(key))
        if value is None or value > high or value < low or (open_low and value <= low):
            return None
        return value

    r4 = raw.get("r4")
    r4 = {str(k): [str(x) for x in v] for k, v in r4.items() if isinstance(v, (list, tuple))} \
        if isinstance(r4, Mapping) else {}
    beside = raw.get("beside")
    return {"name": _screen_name(raw), "receipt_sha256": sha if isinstance(sha, str) and _SHA.match(sha) else None,
            "c_R": bounded("c_R", 0.0, 5.0), "c_X": bounded("c_X", 0.0, 5.0),
            "c_H_floor": bounded("c_H_floor", 0.0, 5.0), "c_H_margin": bounded("c_H_margin", 0.0, 5.0),
            "fp_cap": bounded("fp_cap", 0.0, 0.15, open_low=True), "owner_wall": bounded("owner_wall", 0.0, 0.15, open_low=True),
            "retry": raw.get("retry") is True, "r4": r4,
            "beside": beside if isinstance(beside, str) and beside.strip() else None}


def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """`elane` in the swarm's settings, each value inside its bound (a malformed value is its default; tightening only
    where the module docstring says so)."""
    raw = (settings or {}).get("elane") if isinstance(settings, Mapping) else None
    raw = raw if isinstance(raw, Mapping) else {}

    def number(key: str, low: float, high: float, *, count: bool = False) -> float:
        value = raw.get(key, DEFAULTS[key])
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
                or (count and not float(value).is_integer()):
            value = DEFAULTS[key]
        return float(min(high, max(low, value)))

    def words(key: str, allowed: Sequence[str], *, upper: bool = False) -> list[str]:
        value = raw.get(key)
        if not isinstance(value, list):
            return list(DEFAULTS[key])
        norm = [(str(v).strip().upper() if upper else _token(v)) for v in value if isinstance(v, str)]
        kept = list(dict.fromkeys(v for v in norm if v in allowed))
        return kept or list(DEFAULTS[key])

    mode = raw.get("mode", DEFAULTS["mode"])
    screens = raw.get("screens") if isinstance(raw.get("screens"), Mapping) else {}
    return {
        "mode": mode if mode in MODES else "off",
        "universe": words("universe", tuple(econfig.UNIVERSE), upper=True),
        "structures": words("structures", STRUCTURES),
        "birth_share": number("birth_share", 0.0, 0.5),
        # The roster's bound is its default (== equity_money.probe.max_programs): a setting may only lower it.
        "roster": int(number("roster", 0, float(DEFAULTS["roster"]), count=True)),
        "screens": {lane: _screen_block(screens.get(lane)) for lane in LANES},
        "val_tries": int(number("val_tries", 1, 1, count=True)),
        "looks_per_lineage": int(number("looks_per_lineage", 1, 1, count=True)),
        # The line's bound is its default (-300): a setting can only raise it toward zero.
        "program_loss_usd": number("program_loss_usd", float(DEFAULTS["program_loss_usd"]), -25.0),
    }


def on(settings: Mapping[str, Any] | None) -> bool:
    """`elane.mode` is "gate"."""
    return cfg(settings)["mode"] == "gate"


# ----------------------------------------------------------------------------------------------------------- the lanes
def card_lane(card: Any) -> str | None:
    """The equity lane a card (raw or canonical) declares ("beta" | "equity"), else None."""
    raw = card.get("lane") if isinstance(card, Mapping) else None
    word = _token(raw) if isinstance(raw, str) else None
    return word if word in LANES else None


def lane_of(store: Any, fam: Mapping[str, Any] | None) -> str | None:
    """"beta" | "equity" for an equity-lane family (its spec's `lane`, else its card's), else None."""
    if not isinstance(fam, Mapping):
        return None
    spec = fam.get("spec")
    if isinstance(spec, str):
        from .store import loads

        spec = loads(spec, {})
    if isinstance(spec, Mapping) and spec.get("lane") in LANES:
        return str(spec["lane"])
    fid = str(fam.get("id") or "")
    if not fid or store is None:
        return None
    try:
        from . import cards  # the cards module imports this one: read lazily

        row = cards.card_of(store, fid)
    except Exception:  # noqa: BLE001 - an unreadable card is no lane
        return None
    return card_lane((row or {}).get("card") if isinstance(row, Mapping) else None)


def label(lane: str | None) -> str:
    """"MARKET BETA" | "EQUITY" (`LABELS`); "" for another lane."""
    return LABELS.get(str(lane or ""), "")


def card_errors(card: Any, structure: Any, symbols: Any, settings: Mapping[str, Any] | None) -> list[str]:
    """Every reason an equity card is outside its lane's box (lane, structure in `elane.structures`, symbols inside
    `elane.universe`, a beta card's structure "etf" only), [] when it is inside."""
    lane = card_lane(card)
    if lane is None:
        return []
    c = cfg(settings)
    errors: list[str] = []
    if c["mode"] == "off":
        errors.append("lane: the equity lanes are closed (elane.mode is off); a card may not declare beta or equity")
    word = _token(structure)
    if word not in c["structures"]:
        errors.append(f"structure: an equity card is one of {', '.join(c['structures'])} ({structure!r} given)")
    elif lane == BETA and word != "etf":
        errors.append(f"structure: a beta card trades ETFs only (MARKET BETA; {structure!r} given)")
    names = [str(s).strip().upper() for s in symbols] if isinstance(symbols, (list, tuple)) else []
    outside = [s for s in names if s not in c["universe"]]
    if not names or outside:
        errors.append(f"symbols: an equity card trades only {', '.join(c['universe'])} (elane.universe)"
                      + (f" ({', '.join(outside)} given)" if outside else " (none given)"))
    elif len(set(names)) > econfig.MAX_SYMBOLS:
        errors.append(f"symbols: at most {econfig.MAX_SYMBOLS}")
    elif word == "etf" and any(econfig.UNIVERSE.get(s) != econfig.ETF for s in names):
        errors.append("symbols: an etf card names ETFs only")
    inputs = card.get("inputs") if isinstance(card, Mapping) else None
    if isinstance(inputs, str):
        inputs = [x for x in re.split(r"[,;/+|]", inputs) if x.strip()]
    unknown = [n for n in (_token(x) for x in inputs or []) if n not in INPUTS] if isinstance(inputs, list) else []
    if unknown:
        errors.append(f"inputs: an equity program reads daily bars, the calendar and the event flags only: one to six of "
                      f"{', '.join(INPUTS)} ({', '.join(unknown)} given)")
    ablation = card.get("ablation") if isinstance(card, Mapping) else None
    if ablation == "flat" or (isinstance(ablation, Mapping) and ablation.get("flat") is True):
        errors.append("ablation: an equity card's comparison is the same-exposure buy-and-hold (the screen's S1-X label), "
                      "never flat")
    return errors


def lineage_key(lane: str, key: str) -> str:
    """A lineage, spent-root or graveyard key scoped by its lane (A8.12): "<lane>:<key>" for an equity lane, `key`
    unchanged for an options lane (the options keys never move)."""
    return f"{lane}:{key}" if lane in LANES else str(key)


def seeded(store: Any, fid: str) -> bool:
    """Whether a family is one of the three captain-seeded programs (the Done meter's with/without split, A8.12)."""
    try:
        if str(fid) in {str(v) for v in (store.get(SEEDS_KEY) or {}).values()}:
            return True
        fam = store.family(str(fid))
    except Exception:  # noqa: BLE001 - an unreadable store: not known to be seeded
        return False
    spec = (fam or {}).get("spec") if isinstance(fam, Mapping) else None
    return isinstance(spec, Mapping) and spec.get("seeded") is True


def _seed_places(store: Any) -> dict[str, int]:
    """{family id: its place in `seeds.EQUITY_SEEDS`} of the seeds born in this store (`SEEDS_KEY`)."""
    from . import seeds

    rank = {str(spec["id"]): i for i, spec in enumerate(seeds.EQUITY_SEEDS)}
    return {str(fid): rank[str(sid)] for sid, fid in (store.get(SEEDS_KEY) or {}).items() if str(sid) in rank}


def round_order(store: Any, fams: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """THE ORDER OF AN EQUITY ROUND, which is the order the looks are taken in. D3 makes it a decision: of two programs
    of one lineage the second is refused with no look. Oldest first by the second of birth, then by id; THE
    CAPTAIN-SEEDED PROGRAMS ARE ONE BLOCK IN THE DECLARED ORDER of `seeds.EQUITY_SEEDS`, standing where the first of
    them was born, whatever second each was born in (by birth and id alone their order was the ids' alphabet, or a
    clock tick's when a second ended between two births). A store that cannot say which families are seeds leaves the
    order as given."""
    try:
        place = _seed_places(store)
    except Exception:  # noqa: BLE001
        return list(fams)
    block = min((str(f.get("born_at") or "") for f in fams if str(f.get("id")) in place), default="")

    def key(f: Mapping[str, Any]) -> tuple:
        fid = str(f.get("id"))
        if fid in place:
            return (block, 0, place[fid], fid)
        return (str(f.get("born_at") or ""), 1, 0, fid)

    return sorted(fams, key=key)


def _seed_lineages(store: Any) -> dict[str, str]:
    """{family id: the lineage its seed is DECLARED in (`seeds.EQUITY_SEEDS` `lineage`; a seed that declares none is a
    lineage of its own)} of the seeds born in this store (`SEEDS_KEY`)."""
    from . import seeds

    declared = {str(spec["id"]): str(spec.get("lineage") or spec["id"]) for spec in seeds.EQUITY_SEEDS}
    return {str(fid): declared[str(sid)] for sid, fid in (store.get(SEEDS_KEY) or {}).items() if str(sid) in declared}


def seed_owed(store: Any, fam: Mapping[str, Any] | None, settings: Mapping[str, Any] | None) -> str | None:
    """WHY A SEED HAS NO VERDICT YET (so it can still spend its lineage's one look), or None when it cannot: it is
    retired, it was looked at (its lineage's look is spent, passed or failed), or it FAILED its Validation pre-check
    with no retry owed (`lineage_spent` reads `SPENT_TRY` on a recorded failed pre-check). Everything else is a seed
    alive without a verdict, and the words say which: its look in flight, its look owed (with the gate's last word
    when it waits), its Validation or its pre-registered retry owed, or a version the gate is done with before any
    look, which the tournament's next equity step retires. The operator's hold (`gate_hold`) is no verdict."""
    if not fam or fam.get("retired_at"):
        return None
    fid = str(fam["id"])
    state = fam.get("state") or {}
    if isinstance(state.get(LOOK_KEY), Mapping) or store.lineage_looks(fid) >= cfg(settings)["looks_per_lineage"]:
        return None
    hold = "; the operator holds it (gate_hold)" if state.get("gate_hold") else ""
    if (state.get("look_inflight") or {}).get("sha"):
        return "its sealed look is in flight, or owed again after the process that sent it stopped" + hold
    held = state.get(TRY_KEY) if isinstance(state.get(TRY_KEY), Mapping) else {}
    spent = lineage_spent(store, fam, settings)
    if spent == SPENT_TRY and held.get("precheck") is False:
        return None
    if spent is not None:
        return "the gate is done with it before any look, and it retires at the tournament's next equity step" + hold
    if held.get("entered") is True and state.get("validation_version") == held.get("version"):
        word = str(state.get("gate") or "")
        return "its one sealed look is still owed" + hold + (f"; the gate's last word: {word[:120]}"
                                                             if word.startswith("waiting") else "")
    if held.get("precheck") is False:
        return "its pre-registered Validation retry is still owed" + hold
    return "its Validation is still owed" + hold


def seed_ahead(store: Any, fam: Mapping[str, Any], settings: Mapping[str, Any] | None) -> str | None:
    """THE SEED `fam`'S LOOK WAITS FOR, or None: the first seed declared before it in `seeds.EQUITY_SEEDS`, IN ITS OWN
    DECLARED LINEAGE (`_seed_lineages`), that is alive without a verdict (`seed_owed`). A seed of another lineage is
    never waited for, and a family that is no seed has none ahead. Raises as the store does."""
    place = _seed_places(store)
    fid = str(fam["id"])
    mine = place.get(fid)
    if mine is None:
        return None
    lineage = _seed_lineages(store)
    for other in sorted((f for f, rank in place.items() if rank < mine and lineage.get(f) == lineage.get(fid)),
                        key=lambda f: place[f]):
        if seed_owed(store, store.family(other), settings) is not None:
            return other
    return None


def _seed_wait_end(store: Any, fid: str, held: Mapping[str, Any]) -> None:
    """A seed's wait ended: its record (`SEED_WAIT_KEY`) is cleared, and the House warning with it when one was said
    (a `swarm.status` row with `alert` false, as the funding watch clears its own)."""
    store.set_state(str(fid), **{SEED_WAIT_KEY: None})
    if held.get("alerted") is not None:
        store.event("swarm.status", str(fid), {
            "action": "equity_seed_wait_over", "alert": False, "ahead": held.get("for"),
            "text": f"the equity seed {fid} no longer waits for {held.get('for')}, declared before it in its lineage: "
                    "the wait is over"})


def seed_wait(store: Any, fam: Mapping[str, Any], settings: Mapping[str, Any] | None) -> str | None:
    """THE SEEDS' DECLARED ORDER IS STRICT WITHIN A LINEAGE (amendment A18): the earlier-declared seed of its lineage
    `fam`'s look waits for (`seed_ahead`), or None when its look may be taken. Asked by `look` at its last step before
    the sealed run, and the wait spends nothing. THERE IS NO TIMEOUT: of two seeds of one lineage the first declared
    is the one judged, however long its look is owed (a run the House cannot make, the operator's hold, a wait of its
    own); the later seed's look is taken only once the earlier one has been looked at (D3 then refuses the later
    one), has FAILED its Validation pre-check with no retry owed, or is retired.

    THE RECORD (`SEED_WAIT_KEY` in `fam`'s state): {for, why (`seed_owed` of the earlier seed), since, at (the last
    ask), waited, asks, alerted}. `waited` counts the time between two asks only when they are at most
    `SEED_WAIT_GAP_SECONDS` apart, so rounds in which the later seed's own look was not ready, or the House was down,
    count as nothing. A counted wait of `SEED_WAIT_SECONDS` raises ONE House warning naming both seeds and why the
    earlier one has no verdict yet; it is said again after `SEED_WAIT_REPEAT_SECONDS` while the wait lasts, and
    cleared when the wait ends (`_seed_wait_end`; `seed_waits_over` for a wait that ends without being asked again).
    Raises as the store does: `look` takes no look of a seed whose order cannot be read."""
    fid = str(fam["id"])
    ahead = seed_ahead(store, fam, settings)
    state = (store.family(fid) or fam).get("state") or {}
    held = dict(state[SEED_WAIT_KEY]) if isinstance(state.get(SEED_WAIT_KEY), Mapping) else None
    if ahead is None:
        if held is not None:
            _seed_wait_end(store, fid, held)
        return None
    held = held or {}
    why = seed_owed(store, store.family(ahead), settings) or "it has no verdict yet"
    now = float(store.clock())
    last, said = _num(held.get("at")), _num(held.get("alerted"))
    step = now - last if last is not None else 0.0
    waited = float(_num(held.get("waited")) or 0.0) + (step if 0.0 <= step <= SEED_WAIT_GAP_SECONDS else 0.0)
    record = {"for": ahead, "why": why, "since": held.get("since", now), "at": now, "waited": waited,
              "asks": int(_num(held.get("asks")) or 0) + 1, "alerted": said}
    if waited >= SEED_WAIT_SECONDS and (said is None or now - said >= SEED_WAIT_REPEAT_SECONDS):
        record["alerted"] = now
        store.event("swarm.status", fid, {  # a House warning (the swarm's alerts are its status rows)
            "action": "equity_seed_waits", "alert": True, "ahead": ahead, "why": why, "minutes": int(waited // 60),
            "repeat": said is not None,
            "text": f"the equity seed {fid} has waited {int(waited // 60)} minutes for {ahead}, declared before it in "
                    f"its lineage, which has no verdict yet: {why}. There is no timeout (A18): {fid} is looked at "
                    f"only once {ahead} has been looked at (then {fid} is refused as the same lineage), has failed "
                    "its Validation pre-check with no retry owed, or is retired"})
    store.set_state(fid, **{SEED_WAIT_KEY: record})
    return ahead


def seed_waits_over(store: Any, settings: Mapping[str, Any] | None) -> list[str]:
    """THE WAITS THAT ENDED WITHOUT BEING ASKED AGAIN (the gate's equity round calls it last): a seed that keeps a
    wait's record (`SEED_WAIT_KEY`) and is retired, or has no earlier seed of its lineage without a verdict any more
    (the earlier one was looked at, so D3 refused this one before the wait's step), has the record cleared and its
    warning with it (`_seed_wait_end`). A seed still waiting, whose own look was not ready this round, keeps it.
    Returns the families whose wait ended."""
    ended: list[str] = []
    for fid in sorted(_seed_places(store)):
        fam = store.family(fid) or {}
        held = (fam.get("state") or {}).get(SEED_WAIT_KEY)
        if not isinstance(held, Mapping):
            continue
        if fam.get("retired_at") or seed_ahead(store, fam, settings) is None:
            _seed_wait_end(store, fid, held)
            ended.append(fid)
    return ended


def candidate(fam: Mapping[str, Any], store: Any = None) -> int | None:
    """The version an equity family's Validation is for: its best (`best_version`), else its newest."""
    if fam.get("best_version"):
        return int(fam["best_version"])
    if store is not None:
        latest = store.latest_version(str(fam["id"]))
        return int(latest["n"]) if latest else None
    return None


# ----------------------------------------------------------------------------------------------------------- the screen
def _policy_block(policy: Mapping[str, Any] | None, lane: str) -> Mapping[str, Any]:
    """The lane's screen block of the REPOSITORY's policy.json (`policy`: a parsed document, or its `elane` block), never
    the box's swarm.json: a receipt is pinned by a reviewed pull request, not by a setting."""
    if policy is None:
        try:
            from . import settings as settings_mod

            policy, _ = settings_mod.read_policy()
        except Exception:  # noqa: BLE001 - no file: no receipt
            policy = {}
    block = policy.get("elane") if isinstance(policy, Mapping) and isinstance(policy.get("elane"), Mapping) else policy
    screens = block.get("screens") if isinstance(block, Mapping) and isinstance(block.get("screens"), Mapping) else {}
    return screens.get(lane) if isinstance(screens.get(lane), Mapping) else {}


#: The figures a pinned block must carry beside its sha256, per screen (`screen_effective`: one missing pins nothing).
_PINNED_FIGURES = {"S1": ("c_R", "c_X", "fp_cap", "beside"),
                   "S2": ("c_R", "c_H_floor", "c_H_margin", "c_X", "fp_cap", "beside")}


def screen_name(lane: str, *, policy: Mapping[str, Any] | None = None) -> str | None:
    """The screen the lane's block of the REPOSITORY's policy.json names ("S2" under A11; "S1" for receipt 1's block or
    one naming none; None for a block naming no screen this code runs): what a Validation, a look and their events
    record."""
    return _screen_name(_policy_block(policy, lane))


def screen_effective(settings: Mapping[str, Any] | None, lane: str, *,
                     policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The screen an equity family's look uses: {lane, screen ("S2", A11; "S1" for receipt 1's block; None for a block
    naming no screen this code runs), receipt (sha or None), c_R, c_X, c_H_floor and c_H_margin (S2's; None under S1),
    figures, why}: the pinned receipt of the REPOSITORY's policy.json `elane.screens.<lane>` (`policy`: its parsed
    document; default `settings.read_policy()`), `why` naming the refusal when none is pinned."""
    raw = dict(_policy_block(policy, lane))
    block = _screen_block(raw)
    name = block["name"]
    said = name or "the share screen"
    out = {"lane": lane, "screen": name, "receipt": block["receipt_sha256"], "c_R": block["c_R"], "c_X": block["c_X"],
           "c_H_floor": block["c_H_floor"], "c_H_margin": block["c_H_margin"],
           "figures": {"fp_cap": block["fp_cap"], "owner_wall": block["owner_wall"], "retry": block["retry"],
                       "r4": block["r4"]},
           "block": raw, "why": None}
    if lane not in LANES:
        out["why"] = f"{said} refused: {lane!r} is not an equity lane"
    elif not on(settings):
        out["why"] = f"{said} refused: the equity lanes are off (elane.mode)"
    elif name is None:
        out["why"] = (f"the share screen refused: the repository's policy.json names no screen this code runs "
                      f"(elane.screens.{lane}: one of {', '.join(SCREENS)}, its `screen` and `name` agreeing)")
    elif block["receipt_sha256"] is None:
        out["why"] = f"{said} refused: no receipt sha256 is pinned in the repository's policy.json (elane.screens.{lane})"
    elif any(block[key] is None for key in _PINNED_FIGURES[name]):
        out["why"] = f"{said} refused: the pinned receipt's figures are incomplete in the repository's policy.json (elane.screens.{lane})"
    if out["why"] is not None:
        out["receipt"] = None
    return out


def _receipt_file_refusal(S: Any, receipt: Any, repo: str | Path) -> str | None:
    """THE RECEIPT'S BYTES: why the receipt file at hand is not the pinned receipt, or None. Where anything sits at the
    pinned screen's path under `repo` (`screen.receipt_path`: docs/benchmarks/equity_screen_<n>.json),
    `screen.load_receipt` must read it under the pinned sha256 (its BYTES are the pin's, and it is that screen's
    well-formed receipt) to the very figures the policy block pins. Where nothing is there, there is nothing to compare:
    docs/benchmarks/ never reaches the House box, and CI holds the pin to the file on the exact commit the box runs
    (league/tests/test_equity_screen.py `test_the_committed_pin`, league/tests/test_elane.py)."""
    rel = S.receipt_path(receipt)
    if not rel:
        return "the pinned receipt names no screen"
    path = Path(repo) / rel
    if not path.exists():
        return None
    try:
        loaded = S.load_receipt(path, pinned_sha256=receipt.receipt_sha256, screen=S.screen_of(receipt))
    except S.ScreenRefused as exc:
        return str(exc)
    if dataclasses.replace(loaded, fp={}) != dataclasses.replace(receipt, fp={}):
        return f"the share screen refuses: the figures pinned in policy.json are not the receipt file's ({rel})"
    return None


def _receipt(settings: Mapping[str, Any] | None, lane: str, *, policy: Mapping[str, Any] | None = None,
             repo: str | Path | None = None) -> tuple[Any, str | None]:
    """(the screen's receipt, None) or (None, why): `screen_effective`, then `league.equity.screen.pinned_receipt` (an
    "S1" block gives a `Receipt`, an "S2" block a `ReceiptS2`), then THE RECEIPT'S BYTES (`_receipt_file_refusal`, under
    `repo`: default `REPO`): a receipt file at hand whose bytes are not the pinned sha256 refuses the screen, so no
    Validation retry is granted and no look is spent under it."""
    eff = screen_effective(settings, lane, policy=policy)
    if eff["why"] is not None:
        return None, eff["why"]
    said = eff["screen"] or "the share screen"
    from ..equity import screen as S

    try:
        receipt = S.pinned_receipt(eff["block"])
    except Exception as exc:  # noqa: BLE001 - a receipt that cannot be read judges nothing
        return None, f"{said} refused: the pinned receipt cannot be read ({type(exc).__name__})"
    if receipt is None:
        return None, f"{said} refused: the screen does not accept the pinned receipt (elane.screens.{lane})"
    try:
        why = _receipt_file_refusal(S, receipt, REPO if repo is None else repo)
    except Exception as exc:  # noqa: BLE001 - a receipt file that cannot be judged judges nothing
        return None, f"{said} refused: the receipt file cannot be checked ({type(exc).__name__})"
    if why is not None:
        return None, f"{said} refused: {why}"
    return receipt, None


# ----------------------------------------------------------------------------------------------------------- the ration
def _members(store: Any, fid: str) -> list[str]:
    """The equity families of `fid`'s connected lineages (the set its tries and looks are counted over)."""
    row = store._one("SELECT lineage FROM families WHERE id=?", (str(fid),))
    if row is None:
        return []
    lines = store._connected_lineages(row["lineage"])
    if not lines:
        return []
    return [r["id"] for r in store._all(f"SELECT id FROM families WHERE lineage IN ({','.join('?' * len(lines))}) "
                                        "AND structure IN ('etf', 'stock')", tuple(lines))]


def lineage_tries(store: Any, fid: str) -> list[dict[str, Any]]:
    """AN EQUITY LINEAGE'S VALIDATION TRIES: [{family, version, at}], oldest first, one per distinct (family, version)
    with a Validation run at k 1.0 anywhere in `fid`'s connected lineages, whatever its verdict; a run the runner could not
    make (`NOT_A_TRY`) is none. `at` is the version's first such run: one validated again (an equity identity adoption) is
    the same try."""
    fams = _members(store, fid)
    if not fams:
        return []
    rows = store._all(f"SELECT family, version, MIN(at) AS at FROM runs WHERE family IN ({','.join('?' * len(fams))}) "
                      "AND \"window\"='validation' AND stress=1.0 AND version IS NOT NULL "
                      f"AND COALESCE(status, '') NOT IN ({','.join('?' * len(NOT_A_TRY))}) GROUP BY family, version",
                      (*fams, *NOT_A_TRY))
    out = [{"family": str(r["family"]), "version": int(r["version"]), "at": str(r["at"] or "")} for r in rows]
    out.sort(key=lambda r: (r["at"], r["family"], r["version"]))
    return out


def _run_sha(version: Mapping[str, Any] | None) -> str | None:
    """`gate.run_sha` of a version (its code sha and its params), or None."""
    if not isinstance(version, Mapping) or not version.get("sha"):
        return None
    from .gate import run_sha

    return run_sha(version)


def _retry_open(store: Any, fam: Mapping[str, Any], n: int, tries: Sequence[Mapping[str, Any]],
                settings: Mapping[str, Any] | None) -> bool:
    """R3 (A9 D3): version `n` of `fam` may take the lineage's one Validation-only retry: the lineage's first try is this
    family's, it FAILED its pre-check (no look was spent), it recorded the retry version's hash at the first try
    (`retry_sha`) and `n` is that very program, and the pinned receipt permits a retry (`screen.retry_permitted`)."""
    k = int(cfg(settings)["val_tries"])
    if len(tries) < k or str(tries[0]["family"]) != str(fam["id"]):
        return False
    held = (fam.get("state") or {}).get(TRY_KEY)
    held = held if isinstance(held, Mapping) else {}
    if held.get("version") != tries[0]["version"] or held.get("precheck") is not False or not held.get("retry_sha"):
        return False
    if _run_sha(store.version(str(fam["id"]), int(n))) != held.get("retry_sha"):
        return False
    retried = [t for t in tries[k:] if not (t["family"] == str(fam["id"]) and t["version"] == int(n))]
    if retried or len(tries) > k + 1:
        return False
    lane = lane_of(store, fam)
    receipt, _ = _receipt(settings, lane or BETA)
    if receipt is None:
        return False
    from ..equity import screen as S

    try:
        return bool(S.retry_permitted(receipt, first_precheck_failed=True))
    except Exception:  # noqa: BLE001 - a rule that cannot be read buys no retry
        return False


def try_open(store: Any, fam: Mapping[str, Any], n: Any, settings: Mapping[str, Any] | None) -> bool:
    """Whether version `n` may take its lineage's Validation try (one a lineage; R3's retry only when permitted)."""
    try:
        if lane_of(store, fam) is None:
            return False
        tries = lineage_tries(store, str(fam["id"]))
        k = int(cfg(settings)["val_tries"])
        if any(t["family"] == str(fam["id"]) and t["version"] == int(n) for t in tries[:k]):
            return True  # the lineage's own try, validated again (an equity identity adoption): the same try
        if len(tries) < k:
            return True
        if len(tries) == k + 1 and tries[k]["family"] == str(fam["id"]) and tries[k]["version"] == int(n):
            return True  # R3's retry (admitted once, by `_retry_open` alone), validated again: the same retry
        return _retry_open(store, fam, int(n), tries, settings)
    except Exception:  # noqa: BLE001 - an unreadable lineage buys no try
        return False


def next_try(store: Any, fam: Mapping[str, Any], settings: Mapping[str, Any] | None) -> int | None:
    """The version the tournament's equity round validates now, or None. First A TRY OWED AGAIN: a version already
    tried whose recorded verdict went stale (`look` found its recorded run did not reproduce after the store's daily
    write, or an equity identity adoption marked it), the lowest first, while `try_open` allows it (it does, for the
    lineage's own try and its admitted retry: the same try) and WHATEVER THE FAMILY'S CANDIDATE IS NOW: the candidate
    moves when a later version is written or an adoption clears `best_version`, and a stale verdict nobody asks about
    again would leave the family waiting for good. Then the family's candidate (`candidate`) while `try_open` allows it
    and it has no current verdict, else R3's pre-registered retry version while it is open."""
    try:
        if lane_of(store, fam) is None:
            return None
        state = fam.get("state") or {}
        verdicts = state.get(VERDICTS_KEY) if isinstance(state.get(VERDICTS_KEY), Mapping) else {}
        held = state.get(TRY_KEY) if isinstance(state.get(TRY_KEY), Mapping) else {}

        def due(n: int) -> bool:
            noted = verdicts.get(str(n))
            return not isinstance(noted, Mapping) or noted.get("stale") is True

        for n in sorted(int(key) for key, noted in verdicts.items()
                        if isinstance(noted, Mapping) and noted.get("stale") is True and str(key).isdigit()):
            if store.version(str(fam["id"]), n) is not None and try_open(store, fam, n, settings):
                return n
        n = candidate(fam, store)
        if n is not None and due(n) and try_open(store, fam, n, settings):
            return int(n)
        if held.get("precheck") is False and held.get("retry_sha"):
            tries = lineage_tries(store, str(fam["id"]))
            for v in store.versions(str(fam["id"])):
                if _run_sha(v) == held["retry_sha"] and due(int(v["n"])) \
                        and _retry_open(store, fam, int(v["n"]), tries, settings):
                    return int(v["n"])
        return None
    except Exception:  # noqa: BLE001 - a lineage that cannot be read is validated nothing
        return None


def _refused_cause(store: Any, fid: str, n: int) -> str:
    """The public cause of a version the gate refused before its look (`_refuse`): its last refusal's stage read through
    `REFUSED_CAUSES`, `REFUSED_BEFORE_LOOK` for another stage or when no row can be read. Rules only, no figure."""
    try:
        rows = [r for r in store.refusals(str(fid)) if r.get("version") == int(n)]
    except Exception:  # noqa: BLE001 - the stage cannot be read: the general words
        rows = []
    return REFUSED_CAUSES.get(str(rows[-1].get("stage") or ""), REFUSED_BEFORE_LOOK) if rows else REFUSED_BEFORE_LOOK


def lineage_spent(store: Any, fam: Mapping[str, Any], settings: Mapping[str, Any] | None) -> str | None:
    """Why the family's equity lineage can take no look, or None: its one look used (`SPENT_LOOK`), its one try failed
    (`SPENT_TRY`), or its version refused at the gate before any look (`REFUSED_CAUSES`: the same lineage as a program
    already looked at, no eligible program floor; `REFUSED_BEFORE_LOOK` otherwise)."""
    try:
        if lane_of(store, fam) is None:
            return None
        c = cfg(settings)
        fid = str(fam["id"])
        if store.lineage_looks(fid, include_inflight=True) >= c["looks_per_lineage"]:
            return SPENT_LOOK
        tries = lineage_tries(store, fid)
        if len(tries) < c["val_tries"]:
            return None
        state = fam.get("state") or {}
        held = state.get(TRY_KEY) if isinstance(state.get(TRY_KEY), Mapping) else {}
        mine = [t for t in tries if t["family"] == fid]
        if not mine:
            return SPENT_TRY
        last = mine[-1]
        if held.get("version") != last["version"]:
            return None  # its own try has no verdict yet: it is owed one, never retired unjudged
        if held.get("entered") is True:
            sha = _run_sha(store.version(fid, last["version"]))
            if sha is not None and not store.looked(sha) and state.get("gated_sha") != sha:
                return None  # it entered the gate and waits for its one look
            if sha is not None and not store.looked(sha):
                return _refused_cause(store, fid, last["version"])  # the gate refused it before any look
            return SPENT_TRY
        n_next = held.get("retry_sha")
        if n_next and len(tries) <= c["val_tries"]:
            for v in store.versions(fid):
                if _run_sha(v) == n_next and _retry_open(store, fam, int(v["n"]), tries, settings):
                    return None  # R3: its pre-registered retry is still owed
        return SPENT_TRY
    except Exception:  # noqa: BLE001 - a rule that cannot be read retires nothing
        return None


#: The public cause of `loss_line` (a `swarm.retired` cause): the rule's words, never the figure.
LOSS_LINE = ("its realized real-money net reached the equity lanes' program loss line (elane.program_loss_usd): one "
             "program cannot drain the shared Probe budget")


def loss_line(store: Any, fam: Mapping[str, Any], settings: Mapping[str, Any] | None) -> str | None:
    """THE PROGRAM LOSS LINE of the equity lanes (`elane.program_loss_usd`, -$300, A1.3's analogue; league/equity/bands.py
    EDM1 demotes at the same line): `LOSS_LINE` when the family's realized real net (its forward record's "real" rows, the
    EquityBook's closed lots: net cash after fees and dividends, every version) is at or below the line, else None. The
    tournament's equity round retires it then; its lots exit by the House's rules (a band-dropped program's lots exit at
    the next open, A8.5). A tightening, never a trade. None on any error (a rule that cannot be read retires nothing)."""
    try:
        if lane_of(store, fam) is None:
            return None
        rows = store._all("SELECT pnl FROM forward WHERE family=? AND source='real'", (str(fam["id"]),))
        if not rows:
            return None
        net = sum(float(r["pnl"]) for r in rows)
        return LOSS_LINE if math.isfinite(net) and net <= float(cfg(settings)["program_loss_usd"]) else None
    except Exception:  # noqa: BLE001
        return None


# ----------------------------------------------------------------------------------------------------------- the roster
#: `roster_seats` when swarm.json's `elane` cannot be read and this process never read a good value: no new seat.
ROSTER_CLOSED = -1
_roster_good: dict[str, int] = {}
_roster_lock = threading.Lock()


def _policy_roster() -> int:
    """`elane.roster` of the repository's policy.json, inside its bound (0 to the default, which is
    `equity_money.probe.max_programs`); the default when none is written."""
    try:
        from . import settings as settings_mod

        layer, _ = settings_mod.read_policy()
    except Exception:  # noqa: BLE001
        layer = {}
    return int(cfg({"elane": layer.get("elane") if isinstance(layer, Mapping) else None})["roster"])


def roster_seats(root: str | Path) -> int:
    """`elane.roster` from <root>/swarm.json over policy.json, FAILING CLOSED as `bands._roster_seats` does for
    `dlane.roster` (unreadable: the last good value, else no new seat)."""
    path = Path(root) / "swarm.json"
    key = str(path)
    try:
        doc = json.loads(path.read_text())
    except FileNotFoundError:
        return _policy_roster()
    except (OSError, ValueError):
        with _roster_lock:
            return _roster_good.get(key, ROSTER_CLOSED)
    block = doc.get("elane") if isinstance(doc, Mapping) else None
    bad = not isinstance(doc, Mapping) or ("elane" in doc and not isinstance(block, Mapping))
    if not bad:
        if block is None or "roster" not in block:
            return _policy_roster()
        value = block["roster"]
        bad = isinstance(value, bool) or not isinstance(value, int) or value < 0
        if not bad:
            good = min(int(value), int(DEFAULTS["roster"]))
            with _roster_lock:
                _roster_good[key] = good
            return good
    with _roster_lock:
        return _roster_good.get(key, ROSTER_CLOSED)


# ----------------------------------------------------------------------------------------------------------- the runner
_runners: dict[str, Any] = {}
_runners_lock = threading.Lock()


def isolated_runner(root: str | Path) -> Any:
    """The swarm process's `league.equity.runner.Isolated` over <root>/equity-daily with its own decider child
    (`league.live.decider.Decider`, its log <root>/equity-decider.log, its hash seed pinned: `EVIDENCE_HASH_SEED`),
    built once a process."""
    key = str(Path(root).resolve())
    with _runners_lock:
        runner = _runners.get(key)
        if runner is None:
            from ..equity.runner import Isolated
            from ..live.decider import Decider

            decider = Decider(log=Path(root) / "equity-decider.log")
            decider.hash_seed = EVIDENCE_HASH_SEED  # the evidence child is deterministic across its restarts
            runner = Isolated(decider, Path(root) / STORE_DIR)
            _runners[key] = runner
        return runner


def _runner(owner: Any) -> Any:
    """The tournament's or the gate's equity runner (`equity_runner`, tests hand one in), else the process's."""
    runner = getattr(owner, "equity_runner", None)
    return runner if runner is not None else isolated_runner(owner.store.root)


def _universe(result: Mapping[str, Any]) -> list[str]:
    symbols = result.get("symbols") or (result.get("needs") or {}).get("symbols") or []
    return [str(s) for s in symbols]


def _capital(result: Mapping[str, Any]) -> float:
    value = _num(result.get("capital")) if not isinstance(result.get("capital"), str) else None
    if value is None:
        try:
            value = float(str(result.get("capital")))
        except (TypeError, ValueError):
            value = float(econfig.SLEEVE_USD)
    return value if math.isfinite(value) and value > 0 else float(econfig.SLEEVE_USD)


def _series(S: Any, run: Any) -> Any:
    """`screen.series` of a `runner.Run`: its lots on its own bars, the program's instruments, its capital."""
    result = run.result
    return S.series(result.get("lots") or [], run.bars, universe=_universe(result), capital=_capital(result))


def _plain(value: Any, depth: int = 0) -> Any:
    """A JSON-safe copy of a screen answer (numpy scalars and arrays to floats and lists; non-finite floats to None)."""
    if depth > 6:
        return None
    if isinstance(value, Mapping):
        return {str(k): _plain(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v, depth + 1) for v in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return int(value)
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _plain(tolist(), depth + 1)
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f if math.isfinite(f) else None


# ----------------------------------------------------------------------------------------------------------- Validation
def validate(tournament: Any, fam: Mapping[str, Any], version: Mapping[str, Any]) -> dict[str, Any]:
    """An equity family's Validation (tournament.py dispatches here by lane): the isolated runner's 2025 run at k 1.0
    and 1.5, recorded as the tournament records a Validation (its `validation_r_sd_by_version`: the per-trade net
    return sd), the screen's pre-check (`league.equity.screen.precheck`: S1's and S2's one rule) as its line, the lineage's
    try recorded (`TRY_KEY`). `screen` in its answer, its state and its event is the lane's pinned screen
    (`screen_name`). Returns the tournament's verdict dict."""
    store, settings = tournament.store, tournament.settings
    fid, n = str(fam["id"]), int(version["n"])
    lane = lane_of(store, fam)
    screen = screen_name(lane) if lane is not None else None
    out: dict[str, Any] = {"version": n, "passed": False, "entered": False, "screen": screen, "lane": lane}
    if lane is None:
        return {**out, "refused": "not an equity-lane family"}
    if not on(settings):
        return {**out, "refused": "the equity lanes are off (elane.mode)"}
    if not try_open(store, fam, n, settings):
        return {**out, "refused": SPENT_TRY}
    if not version.get("code"):
        return {**out, "refused": "the version's program cannot be read"}
    from ..equity import screen as S

    runner = _runner(tournament)
    code, params = version["code"], dict(version.get("params") or {})
    try:
        base = runner.validation(code, params, name=fid, k=econfig.K_BASE)
        stressed = runner.validation(code, params, name=fid, k=econfig.K_STRESS)
    except Exception as exc:  # noqa: BLE001 - no result is no try (nothing is recorded)
        store.event("swarm.status", fid, {"action": "elane_validation_error", "version": n, "lane": lane,
                                         "error": type(exc).__name__})
        return {**out, "error": type(exc).__name__}
    result = dict(base.result or {})
    status = str(result.get("status") or "unknown")
    days = float((result.get("summary") or {}).get("days") or 0)
    years = days / 252.0 * max(1, len(_universe(result)))
    row = store.add_run(fid, n, result, window="validation", stress=econfig.K_BASE, purpose="validation",
                        program_years=years)
    twin = dict(stressed.result or {})
    store.add_run(fid, n, {"run_id": f"{row['run_id']}-s15", "status": twin.get("status") or "unknown",
                           "trials": int(twin.get("trials") or 1), "summary": dict(twin.get("summary") or {})},
                  window="validation", stress=econfig.K_STRESS, purpose="validation", program_years=years)
    if status in NOT_A_TRY:
        store.event("swarm.status", fid, {"action": "elane_validation_error", "version": n, "lane": lane, "status": status})
        return {**out, "error": status}
    if status != "ok":
        pre: dict[str, Any] = {"passed": False, "checks": {"status": False}}
    else:
        try:
            pre = dict(S.precheck(_series(S, base)))
        except Exception as exc:  # noqa: BLE001 - a pre-check that cannot be read admits nothing
            pre = {"passed": False, "checks": {"readable": False}, "error": type(exc).__name__}
    entered = bool(pre.get("passed")) and status == "ok"
    tries = lineage_tries(store, fid)
    k = int(cfg(settings)["val_tries"])
    first = any(t["family"] == fid and t["version"] == n for t in tries[:k])
    state = fam.get("state") or {}
    held = state.get(TRY_KEY) if isinstance(state.get(TRY_KEY), Mapping) else {}
    if "retry_sha" in held:
        # RECORDED ONCE, at the lineage's first try, and kept by every later Validation of the family, None included:
        # a version validated again (stale after the store's daily write or an adoption) never registers a retry
        # version that was written after the first verdict.
        retry_sha = held.get("retry_sha")
    elif first:
        # R3 (A9 D3): the retry version is pre-registered: a version written before this first try, hashed now.
        later = [v for v in store.versions(fid) if int(v["n"]) > n]
        retry_sha = _run_sha(later[0]) if later else None
    else:
        retry_sha = None
    sd = _num((result.get("summary") or {}).get("sd_net_return"))
    sigma = dict(state.get(SIGMA_KEY) or {}) if isinstance(state.get(SIGMA_KEY), Mapping) else {}
    if sd is not None and sd > 0:
        sigma[str(n)] = round(sd, 8)
    sha = _run_sha(version)
    looked = sha is not None and (store.looked(sha) or state.get("gated_sha") == sha)
    checks = {str(k): bool(v) for k, v in (pre.get("checks") or {}).items()}
    verdicts = dict(state.get(VERDICTS_KEY) or {}) if isinstance(state.get(VERDICTS_KEY), Mapping) else {}
    verdicts[str(n)] = {"entered": entered, "at": store.now(), "stale": False}
    with store.atomic():
        current = store.family(fid)
        if current is None or current.get("retired_at"):
            return {**out, "refused": "retired"}
        store.update_family(fid, validated_version=n)
        store.bump(fid, validations=1)
        store.set_state(fid, validation_version=n, gate_ready=entered and not looked,
                        **{VALIDATION_KEY: {"version": n, "passed": entered, "precheck": checks, "screen": screen,
                                            "status": status, "at": store.now(), "result_sha": result.get("result_sha"),
                                            "stale": False},
                           SIGMA_KEY: sigma, VERDICTS_KEY: verdicts,
                           TRY_KEY: {"version": n, "at": store.now(), "first": first, "precheck": bool(pre.get("passed")),
                                     "entered": entered, "retry_sha": retry_sha}})
    store.event("swarm.status", fid, {"action": "elane_validation", "version": n, "lane": lane, "label": label(lane),
                                     "screen": screen, "entered": entered, "first": first, "checks": checks})
    return {**out, "passed": entered, "entered": entered, "first": first}


# ----------------------------------------------------------------------------------------------------------- the look
def reviewed(state: Mapping[str, Any], sha: str) -> bool:
    """A passed review AND a passed audit of program `sha` recorded in the family's state (the gate's `review` shape)."""
    review = state.get("review") if isinstance(state.get("review"), Mapping) else {}
    audit = review.get("audit") if isinstance(review.get("audit"), Mapping) else {}
    return review.get("sha") == sha and review.get("verdict") == "pass" and audit.get("verdict") == "pass"


def _status(run: Any) -> str:
    """A run's status ("ok" | "disqualified" | "no_data"; "unknown" when its result names none)."""
    result = getattr(run, "result", None)
    return str((result if isinstance(result, Mapping) else {}).get("status") or "unknown")


def _segment_series(S: Any, runs: Sequence[Any]) -> tuple[list[Any], str | None]:
    """THE FLOOR'S INPUTS from the program's Train-era runs (the screen's rule: one series per span, None where the
    program has no history): ([`screen.Series` | None], None), a "no_data" run read as None; or ([], the status) when a
    run ended any other way than "ok" ("disqualified": the program's own errors ended it, so its series is partial and
    no floor is read from it)."""
    statuses = [_status(run) for run in runs]
    bad = next((s for s in statuses if s not in ("ok", "no_data")), None)
    if bad is not None:
        return [], bad
    return [None if status == "no_data" else _series(S, run) for run, status in zip(runs, statuses)], None


def _invested_shares(v: Any, segments: Sequence[Any]) -> dict[str, Any] | None:
    """THE PROGRAM'S ACTIVITY, WHERE ITS FLOOR IS BUILT AND WHERE IT IS JUDGED: the share of sessions it was invested
    on in Validation and on each Train-era span ({"validation", "train" [per span, None where it has no history],
    "ratio": Validation over the Train-era mean}). A FIGURE BESIDE THE LOOK, NEVER A CONDITION OF IT: the screen's
    floor is the program's own Train-era behaviour, so a program much sparser there than in the judged windows lowers
    its own threshold (down to the receipt's floor, never below). The rule that would refuse on it is not written (it
    needs a pre-registered factor: the review of the first non-seeded programs); until then the look records the
    figures so that review can read them. House-only, never in a view. None when they cannot be computed."""
    def share(series: Any) -> float | None:
        invested = getattr(series, "invested", None)
        values = [bool(x) for x in invested] if invested is not None else []
        return round(sum(values) / len(values), 4) if values else None

    try:
        train = [share(s) for s in segments]
        known = [x for x in train if x is not None]
        validation = share(v)
        mean = sum(known) / len(known) if known else None
        ratio = round(validation / mean, 4) if validation is not None and mean else None
        return {"validation": validation, "train": train, "ratio": ratio}
    except Exception:  # noqa: BLE001 - a figure beside the look: never its condition
        return None


def _train_series(segments: Sequence[Any]) -> dict[str, list]:
    """The Train-era daily series a look keeps for THE LINEAGE: {"days": [int ordinal], "r": [float]}, every segment's
    sessions in order (House-only: never in a view)."""
    days: list[int] = []
    r: list[float] = []
    for s in segments:
        got_days, got_r = getattr(s, "days", None), getattr(s, "r", None)
        for d, x in zip(list(got_days) if got_days is not None else [], list(got_r) if got_r is not None else []):
            value = float(x)
            days.append(int(d))
            r.append(round(value, 8) if math.isfinite(value) else 0.0)
    return {"days": days, "r": r}


class LineageUnread(RuntimeError):
    """THE LINEAGE cannot be judged: `family` was looked at (or its look is in flight) and keeps no Train series
    (`TRAIN_R_KEY`) for D3's correlation test. The look waits (`look`); it never passes D3 unjudged."""

    def __init__(self, family: str):
        super().__init__(f"{family} keeps no Train series of its look")
        self.family = str(family)


def same_lineage(store: Any, fam: Mapping[str, Any], lane: str, template: str,
                 train: Mapping[str, Sequence]) -> str | None:
    """THE LINEAGE (A9 D3): the family already looked at that `fam`'s program is the same lineage as, or None: the same
    template in its own lane (`TEMPLATE_KEY`, lane-scoped), or Train daily returns correlating >= 0.7 on their common
    sessions with any equity program already looked at, in either equity lane (`league.equity.screen.same_lineage`).
    FAILS CLOSED (`LineageUnread`): a family that was looked at, or a living one whose look is in flight, with no Train
    series kept is never skipped (a retired family's marker of a look that never landed is: nothing was looked at)."""
    import numpy as np

    from ..equity import screen as S

    mine = dict(zip(train.get("days") or [], train.get("r") or []))
    for other in store.families(lanes=LANES):
        if str(other["id"]) == str(fam["id"]):
            continue
        state = other.get("state") or {}
        looked = isinstance(state.get(LOOK_KEY), Mapping)
        if not looked and not (state.get("look_inflight") or {}).get("sha"):
            continue
        if lane_of(store, other) == lane and state.get(TEMPLATE_KEY) == template:
            return str(other["id"])
        theirs = state.get(TRAIN_R_KEY) if isinstance(state.get(TRAIN_R_KEY), Mapping) else {}
        pairs = dict(zip(theirs.get("days") or [], theirs.get("r") or []))
        if not pairs:
            if looked or not other.get("retired_at"):
                raise LineageUnread(str(other["id"]))
            continue
        common = sorted(set(mine) & set(pairs))
        if len(common) < 3:
            continue
        a = np.asarray([mine[d] for d in common], dtype=float)
        b = np.asarray([pairs[d] for d in common], dtype=float)
        if bool(S.same_lineage(a, b, same_template=False)):
            return str(other["id"])
    return None


def _restore_train(gate: Any, fid: str) -> bool:
    """THE LOOK'S LINEAGE RECORD written again: a looked-at family's missing Train series (`TRAIN_R_KEY`), from its
    looked version's Train-era runs (`Isolated.segments`: the runs its look kept the series of; Train-era data only,
    nothing sealed, no try and no look). False when it cannot be (no recorded look: the gate's round owes a look in
    flight again; no program to run; a run that failed or gave no session)."""
    store = gate.store
    other = store.family(str(fid)) or {}
    state = other.get("state") or {}
    looked = state.get(LOOK_KEY) if isinstance(state.get(LOOK_KEY), Mapping) else None
    try:
        version = store.version(str(fid), int(looked["version"])) if looked else None
    except (KeyError, TypeError, ValueError):
        version = None
    if not version or not version.get("code"):
        return False
    from ..equity import screen as S

    try:
        runs = _runner(gate).segments(version["code"], dict(version.get("params") or {}), name=str(fid))
        segments, bad = _segment_series(S, runs)
        if bad is not None:
            raise ValueError(f"a Train-era run ended {bad}")
        train = _train_series(segments)
    except Exception as exc:  # noqa: BLE001 - it stays unread, and the look that asked waits
        store.event("swarm.gate", str(fid), {"action": "equity_lineage_unread", "version": version.get("n"),
                                             "error": type(exc).__name__})
        return False
    if not train["days"]:
        return False
    store.set_state(str(fid), **{TRAIN_R_KEY: train})
    store.event("swarm.gate", str(fid), {"action": "equity_lineage_restored", "version": version.get("n"),
                                         "sessions": len(train["days"])})
    return True


def _refuse(gate: Any, fid: str, n: int, sha: str, stage: str, why: str, *, screen: str | None) -> None:
    """A refusal before the look (no look spent): the refusal row, `gated_sha` with `gate_ready` cleared (the gate is
    done with this version), the outcome, and one private `swarm.gate` event (`screen`: the lane's pinned screen)."""
    store = gate.store
    store.refuse(fid, n, stage, why)
    store.compare_and_set_state(fid, {"validation_version": n}, gated_sha=sha, gate_ready=False)
    store.set_state(fid, gate_outcome={"sha": sha, "result": "refused", "at": gate.clock()}, gate=f"refused ({why})")
    store.event("swarm.gate", fid, {"action": "refused", "version": n, "stage": stage, "lane": lane_of(store, store.family(fid)),
                                    "screen": screen, "why": why})


def _wait(gate: Any, fid: str, n: int, sha: str, why: str, *, screen: str | None) -> None:
    """The look waits (no look spent, `gate_ready` stays): its outcome "waiting" and one private event."""
    gate.store.set_state(fid, gate_outcome={"sha": sha, "result": "waiting", "at": gate.clock()}, gate=f"waiting ({why})")
    gate.store.event("swarm.gate", fid, {"action": "equity_look_waits", "version": n, "screen": screen, "why": why})


def _holdout_gap(root: str | Path) -> str | None:
    """Why the daily store under the state root cannot give the sealed look its whole calibrated holdout yet, or None.
    A12 fixes every look at the sessions `config.LOOK_FIRST` .. `config.LOOK_CAP` (the 194 the screens are calibrated
    on), and `Isolated.look` reads through min(the store's last close, the cap): a store that ends before the cap would
    spend the lineage's one look on a certain failure (the verdict's windows refuse a shorter holdout). The store's
    last day is its manifest's, never a bar (no capability is minted to read it). Raises as the store does when it
    cannot be read."""
    from ..equity.store import EquityStore

    through = EquityStore(Path(root) / STORE_DIR).fetched_through
    if through >= econfig.LOOK_CAP:
        return None
    return (f"the daily store ends {through.isoformat()}: the sealed look reads the calibrated holdout through "
            f"{econfig.LOOK_CAP.isoformat()} (A12), so it waits for the data job")


def _s1x_floor(S: Any, segments: Sequence[Any], receipt: Any) -> Mapping[str, Any] | None:
    """An S1 floor of the same Train-era series, for the S1-X label's FP beside an S2 verdict (`screen.verdict_s2`
    reads `fp_x` from an eligible S1 floor's "X" curve at c_X; without one the line says "unmeasured"). Train-era
    series only, deterministic (S1's seeds), and never a condition of the look: None under receipt 1 (its own floor
    carries the curve), when S1's floor is not eligible, or on any error."""
    if S.screen_of(receipt) != "S2":
        return None
    try:
        floor = _plain(dict(S.floor(segments, fp_cap=float(receipt.fp_cap))))
    except Exception:  # noqa: BLE001 - a label's rate that cannot be measured is stated as unmeasured
        return None
    return floor if isinstance(floor, Mapping) and floor.get("eligible") is True else None


def look(gate: Any, fam: Mapping[str, Any], version: Mapping[str, Any], sha: str) -> bool | None:
    """An equity family's ONE sealed look, on the House (gate.py dispatches here by lane), under the lane's pinned
    receipt (`_receipt`: S2's under A11; waits, nothing spent, when none is pinned or its file's bytes are not the
    pin's): the floor from the program's Train-era runs (`Isolated.segments` -> `screen.series` -> `screen.floor(...,
    receipt=)`, kept a version while `screen.floor_fits` the receipt; a floor the verdict would refuse spends no look);
    the look with a freshly minted `EquityGateCapability` (`Isolated.look`), only once the daily store holds its whole
    calibrated holdout (`_holdout_gap`); `screen.verdict` and `screen.beside_line` recorded with the look, under the
    screen that judged it. THE RUN'S STATUS FIRST (the module docstring): a Train-era run that ended "disqualified"
    refuses the floor; a holdout run that did is a look spent and failed, never judged; a sealed run sent and not
    answered is owed once, then the look is spent and failed (`LOOK_SENDS`). THE LAST STEP BEFORE THE SEALED RUN is the
    seeds' declared order (`seed_wait`, A18): a seed waits, nothing spent, while an earlier seed of its declared
    lineage is alive without a verdict. True passed (the family becomes a Candidate), False failed, None not run (no
    look spent)."""
    store, settings = gate.store, gate.settings
    fid, n = str(fam["id"]), int(version["n"])
    lane = lane_of(store, fam)
    if lane is None or not on(settings):
        return None
    screen = screen_name(lane)
    receipt, why = _receipt(settings, lane)
    if receipt is None:
        _wait(gate, fid, n, sha, why or "the share screen refused: no pinned receipt", screen=screen)
        return None
    c = cfg(settings)
    if store.looked(sha) or store.lineage_looks(fid, include_inflight=True) >= c["looks_per_lineage"]:
        _refuse(gate, fid, n, sha, "rations", "the equity lineage's one sealed look is spent", screen=screen)
        return None
    state = fam.get("state") or {}
    held = state.get(TRY_KEY) if isinstance(state.get(TRY_KEY), Mapping) else {}
    if held.get("version") != n or held.get("entered") is not True or state.get("validation_version") != n:
        return None  # not this version's entry: the tournament owes its Validation first
    if not seeded(store, fid) and not reviewed(state, sha):
        _wait(gate, fid, n, sha, "an equity look of a program the captain did not seed needs the equity review (E2)",
              screen=screen)
        return None
    from ..equity import screen as S
    from ..equity.runner import RunFailed, RunLost
    from ..equity.store import mint_equity_gate_capability
    from .evaluator import equity_fingerprint

    screen = S.screen_of(receipt) or screen  # the screen that judges it is the receipt's own
    # A12, before any run: the look reads the whole calibrated holdout or it waits (`_holdout_gap`).
    try:
        gap = _holdout_gap(store.root)
    except Exception as exc:  # noqa: BLE001 - a store that cannot be read gives no look (nothing spent)
        store.event("swarm.gate", fid, {"action": "look_failed", "version": n, "stage": "store", "error": type(exc).__name__})
        return None
    if gap is not None:
        _wait(gate, fid, n, sha, gap, screen=screen)
        return None
    try:
        proof = {"engine": EQUITY_ENGINE_VERSION, "equity_sha256": equity_fingerprint(), "run_sha": sha}
    except Exception as exc:  # noqa: BLE001 - no identity, no band proof: no look
        store.event("swarm.gate", fid, {"action": "look_failed", "version": n, "stage": "identity", "error": type(exc).__name__})
        return None
    runner = _runner(gate)
    code, params = version["code"], dict(version.get("params") or {})
    floors = state.get(FLOOR_KEY) if isinstance(state.get(FLOOR_KEY), Mapping) else {}
    try:
        runs = runner.segments(code, params, name=fid)
        segments, ended = _segment_series(S, runs)
        cached = floors.get(str(n))
        if ended is not None:
            floor = {"eligible": False, "why": f"a Train-era run ended {ended}: its series is partial"}
        elif S.floor_fits(cached, receipt):
            floor = dict(cached)  # computed once a version under this receipt (deterministic: S2 exact, S1 its seeds)
        else:
            # The pinned receipt's own floor (A11: `floor_s2` for receipt 2). A floor kept for the version under
            # another receipt (S1's, or other figures) is not this screen's: the verdict would refuse it AFTER the
            # look was spent, so it is run again here, and one that still does not fit spends no look.
            floor = _plain(dict(S.floor(segments, receipt=receipt)))
            if not S.floor_fits(floor, receipt):
                raise ValueError("the program floor does not fit the pinned receipt")
            store.set_state(fid, **{FLOOR_KEY: {**dict(floors), str(n): floor}})
    except Exception as exc:  # noqa: BLE001 - no floor, no look (nothing spent)
        store.event("swarm.gate", fid, {"action": "look_failed", "version": n, "stage": "floor", "error": type(exc).__name__})
        return None
    if not floor.get("eligible"):
        _refuse(gate, fid, n, sha, "screen floor",
                f"{screen}'s program floor is not eligible: {floor.get('why') or 'no reason given'}", screen=screen)
        return None
    template = lineage_key(lane, str(version.get("sha") or ""))
    train = _train_series(segments)
    restored: set[str] = set()
    while True:
        try:
            twin = same_lineage(store, fam, lane, template, train)
            break
        except LineageUnread as exc:
            # D3 FAILS CLOSED: a program already looked at keeps no Train series. Its looked version's Train-era runs
            # write it again (once a family a look); where they cannot, this look waits: it never passes D3 unjudged.
            if exc.family in restored or not _restore_train(gate, exc.family):
                _wait(gate, fid, n, sha, f"the lineage cannot be judged (A9 D3): {exc.family} was looked at, or its "
                      "look is in flight, and keeps no Train series to compare with", screen=screen)
                return None
            restored.add(exc.family)
        except Exception as exc:  # noqa: BLE001 - a lineage that cannot be read spends no look
            store.event("swarm.gate", fid, {"action": "look_failed", "version": n, "stage": "lineage",
                                            "error": type(exc).__name__})
            return None
    if twin is not None:
        _refuse(gate, fid, n, sha, "same lineage",
                f"the same lineage as {twin}, already looked at (A9 D3: Train correlation >= 0.7 or the same template)",
                screen=screen)
        return None
    try:
        recorded = runner.validation(code, params, name=fid, k=econfig.K_BASE)
        v = _series(S, recorded)
        pre = dict(S.precheck(v))
    except Exception as exc:  # noqa: BLE001
        store.event("swarm.gate", fid, {"action": "look_failed", "version": n, "stage": "validation", "error": type(exc).__name__})
        return None
    noted = state.get(VALIDATION_KEY) if isinstance(state.get(VALIDATION_KEY), Mapping) else {}
    if (recorded.result or {}).get("result_sha") != noted.get("result_sha"):
        # The recorded Validation run did not reproduce (the store was refetched, or the identity moved): the tournament
        # validates it again (the same try) before any look.
        verdicts = dict(state.get(VERDICTS_KEY) or {}) if isinstance(state.get(VERDICTS_KEY), Mapping) else {}
        verdicts[str(n)] = {**dict(verdicts.get(str(n)) or {}), "stale": True}
        store.compare_and_set_state(fid, {"validation_version": n}, gate_ready=False,
                                    **{VALIDATION_KEY: {**dict(noted), "stale": True}, VERDICTS_KEY: verdicts})
        store.event("swarm.gate", fid, {"action": "equity_validation_moved", "version": n})
        return None
    if not pre.get("passed"):
        _refuse(gate, fid, n, sha, "precheck", f"{screen}'s Validation pre-check does not pass on the recorded run",
                screen=screen)
        return None
    # THE SEEDS' DECLARED ORDER, STRICT WITHIN A LINEAGE (A18; `seed_wait`), asked at the last step before the sealed
    # run: everything this look needs of its own is ready, so the wait's clock counts only such rounds. What follows
    # (S1-X's rate, the activity figures) is beside the look and refuses nothing.
    try:
        ahead = seed_wait(store, fam, settings)
    except Exception as exc:  # noqa: BLE001 - a seed whose order cannot be read is not looked at (nothing spent)
        if seeded(store, fid):
            store.event("swarm.gate", fid, {"action": "look_failed", "version": n, "stage": "seed order",
                                            "error": type(exc).__name__})
            return None
        ahead = None  # a family that is no seed waits for no seed
    if ahead is not None:
        _wait(gate, fid, n, sha, f"the seeds' declared order (A18): {ahead}, declared before it in its lineage, has "
              "no verdict yet", screen=screen)
        return None
    s1x = _s1x_floor(S, segments, receipt)  # S1-X's rate beside an S2 verdict: Train-era series only, before the look
    activity = _invested_shares(v, segments)  # beside the look, never its condition
    # THE SEAT RULE'S TWO COUNTS (A24), from the runs made above, BEFORE the sealed run: K is fixed with the look.
    seat = None if seat_recorded(state, n, sha) else _seat_record(store, n, sha, recorded.result, runs, source="look",
                                                                   validation_run="look")
    marker = {"sha": sha, "n": n, "at": gate.clock(), "lane": lane}
    with store.atomic():
        current = store.family(fid) or {}
        if current.get("retired_at") or (current.get("state") or {}).get("gate_hold") or store.looked(sha) or \
                store.lineage_looks(fid, include_inflight=True) >= c["looks_per_lineage"]:
            return None
        if not store.compare_and_set_state(fid, {"validation_version": n, "look_inflight": None}, gate_ready=False,
                                           look_inflight=marker):
            return None
    try:
        capability = mint_equity_gate_capability(Path(store.root) / STORE_DIR, reason=f"the equity look of {fid} v{n}")
        ran = runner.look(code, params, name=fid, gate=capability)
        ended = _status(ran)
        if ended in NOT_A_TRY:
            raise RunFailed(f"the holdout run ended {ended}")  # the House could not run it: no look, owed again
        if ended != "ok":
            # THE RUN'S STATUS FIRST (as Validation's): a holdout run its own errors ended ("disqualified") left a
            # partial series. It is never judged: the look is spent and FAILED.
            verdict = {"screen": screen, "passed": False, "status": ended,
                       "why": f"the holdout run ended {ended}: a partial series is never judged"}
            beside = f"no verdict: {verdict['why']}"
        else:
            h = _series(S, ran)
            verdict = _plain(S.verdict(v, h, receipt=receipt, program_floor=floor, s1_floor=s1x))
            beside = str(S.beside_line(verdict, receipt))
    except RunLost as exc:
        # THE SEALED RUN WAS SENT AND DID NOT RETURN (`LOOK_SENDS`): the program held its holdout. Owed again once;
        # the second time the look is spent and FAILED, so no program is shown its holdout a third time.
        held = (store.family(fid) or {}).get("state") or {}
        held = held.get(LOST_KEY) if isinstance(held.get(LOST_KEY), Mapping) else {}
        count = (int(held.get("count") or 0) if held.get("sha") == sha else 0) + 1
        spent = count >= LOOK_SENDS
        store.event("swarm.gate", fid, {"action": "look_lost", "version": n, "lane": lane, "count": count,
                                        "spent": spent, "error": type(exc).__name__})
        store.event("swarm.status", fid, {  # a House warning (the swarm's alerts are its status rows)
            "action": "equity_look_lost", "alert": True, "version": n, "count": count, "spent": spent,
            "text": f"the sealed equity look of {fid} v{n} was sent and did not return ({count} of {LOOK_SENDS}): "
                    + ("its look is spent and failed" if spent else "it is owed once more; read equity-decider.log")})
        if not spent:
            store.compare_and_set_state(fid, {"look_inflight": marker}, look_inflight=None, gate_ready=True,
                                        **{LOST_KEY: {"sha": sha, "count": count, "at": store.now()}})
            return None
        verdict = {"screen": screen, "passed": False, "status": "lost",
                   "why": f"the sealed run was sent {LOOK_SENDS} times and did not return"}
        beside = f"no verdict: {verdict['why']}"
    except Exception as exc:  # noqa: BLE001 - the look did not land: owed again next round (no look row)
        store.compare_and_set_state(fid, {"look_inflight": marker}, look_inflight=None, gate_ready=True)
        store.event("swarm.gate", fid, {"action": "look_failed", "version": n, "stage": "look", "error": type(exc).__name__})
        return None
    passed = bool(verdict.get("passed"))
    # The screen that judged it: S1's verdict carries c_used (= max(c_R, c_p)); S2's has no pooled-t bar, and its
    # c_H is c_H,used (= max(c_H_floor, c_pF1 + c_H_margin)).
    figures = {"c_pF1": verdict.get("c_pF1")} if screen == "S2" else {"c_used": verdict.get("c_used")}
    detail = {"lane": lane, "label": label(lane), "screen": screen, "receipt": receipt.receipt_sha256,
              **figures, "c_H": verdict.get("c_H"), "s1x": verdict.get("label"),
              "seeded": seeded(store, fid), "beside": beside, "passed": passed,
              **({"status": verdict["status"], "why": verdict.get("why")} if verdict.get("status") else {})}
    with store.atomic():
        store.add_look(fid, n, sha, passed=passed, p_value=None, detail=detail)
        store.compare_and_set_state(fid, {"look_inflight": marker}, look_inflight=None)
        store.set_state(fid, gated_sha=sha, gate_ready=False, gate="pass" if passed else "fail", dormant_cycles=0,
                        gate_outcome={"sha": sha, "result": "passed" if passed else "failed", "at": gate.clock()},
                        **{LOOK_KEY: {"version": n, "at": store.now(), "verdict": verdict, "beside": beside,
                                      "activity": activity},
                           FLOOR_KEY: {**dict(floors), str(n): floor},
                           TRAIN_R_KEY: train, TEMPLATE_KEY: template, **({SEAT_KEY: seat} if seat is not None else {})})
        current = store.family(fid) or {}
        if passed and current.get("band") == "gym" and not current.get("retired_at"):
            store.set_state(fid, banded_version=n, banded_sha=version.get("sha"), banded_at=gate.clock(),
                            banded_evaluator=proof)
            store.set_band(fid, "candidate", reason=f"passed its sealed look ({screen}, {label(lane)})")
    store.event("swarm.gate", fid, {"action": "look", "version": n, "passed": passed, "lane": lane, "screen": screen,
                                    "receipt": receipt.receipt_sha256, "_verdict": verdict, "_activity": activity,
                                    "_seat": seat})
    return passed


# ----------------------------------------------------------------------------------------------------------- the seat rule
_seat_failed: dict[tuple[str, str, str], float] = {}


def seat_recorded(state: Any, version: Any, sha: Any) -> bool:
    """Whether K's two counts are already written for this exact program (`SEAT_KEY`: its version and run sha)."""
    held = state.get(SEAT_KEY) if isinstance(state, Mapping) and isinstance(state.get(SEAT_KEY), Mapping) else None
    return bool(held and sha and held.get("run_sha") == sha and held.get("version") == version)


def seat_activity(state: Any, version: Any, sha: Any) -> dict[str, Any] | None:
    """K's two counts of the program a row stands for, as the EquityBook reads them (`bands.read(..., queued=True)`:
    `seat_activity`): the `SEAT_KEY` record while it is this version's and this run sha's, else None (the program then
    ranks after every program whose counts can be read, until `seat_backfill` writes them)."""
    if not seat_recorded(state, version, sha):
        return None
    held = state[SEAT_KEY]
    return {key: dict(held[key]) for key in ("validation", "train") if isinstance(held.get(key), Mapping)}


def _seat_floor() -> Any:
    from ..equity import bands as equity_bands

    return equity_bands.seat_settings().k_floor


def _seat_record(store: Any, n: int, sha: str, validation: Any, runs: Sequence[Any], *, source: str,
                 validation_run: str) -> dict[str, Any] | None:
    """K's two counts as the family's state keeps them (`SEAT_KEY`), from a Validation run's result and the Train-era
    runs (`runner.Run`s or their results). None when they cannot be counted (a figure beside the look: never its
    condition; the backfill tries again)."""
    from ..equity import bands as equity_bands

    try:
        train = [dict(getattr(run, "result", run) or {}) for run in runs]
        counts = equity_bands.seat_counts(dict(validation or {}), train, floor=_seat_floor())
    except Exception:  # noqa: BLE001 - beside the look, never its condition
        return None
    return {"version": int(n), "run_sha": str(sha), **counts, "at": store.now(), "source": source,
            "validation_run": validation_run}


def _stored_validation(store: Any, fid: str, n: int, result_sha: Any) -> dict[str, Any] | None:
    """THE RECORDED VALIDATION RUN as the swarm store kept it in full (`validate` -> `add_run`): the base-spread run of
    version `n` whose `result_sha` is `result_sha` (the one its look reproduced, `VALIDATION_KEY`), status "ok", with
    its lots. None when no such file can be read."""
    if not result_sha:
        return None
    for row in store.version_runs(fid, int(n), window="validation", stress=econfig.K_BASE, limit=20):
        result = store.run_result(row["run_id"])
        if isinstance(result, Mapping) and result.get("result_sha") == result_sha and result.get("status") == "ok" \
                and isinstance(result.get("lots"), list):
            return dict(result)
    return None


def seat_backfill(gate: Any) -> list[str]:
    """K'S TWO COUNTS FOR THE PROGRAMS THAT PASSED BEFORE THEY WERE KEPT (release E5-A; the module docstring). For
    every living equity family in the Candidate, Probe or Sized band whose state holds no `SEAT_KEY` record of its
    banded program: the Validation count from the stored run its look reproduced (`_stored_validation`; made again
    through the House's own runner, `Isolated.validation`, when that file is gone), the Train-era count from the
    Train-era runs made again (`Isolated.segments`). Written once (never over a record that landed meanwhile), with
    one private `swarm.gate` event; a program whose counts cannot be made is tried again after `SEAT_RETRY_SECONDS`
    and said once as a House warning (it ranks last until then: league/equity/bands.py `seat_key`).

    NO SEALED FIGURE IS READ OR PRINTED: no gate capability is minted, `Isolated.look` is never called, both runs read
    unsealed windows (Validation, the Train-era spans), and what is kept is four whole numbers. No try, no look, no
    trial is counted and no band moves. Returns the families written. Never raises."""
    store, settings = gate.store, gate.settings
    written: list[str] = []
    try:
        if not on(settings) or getattr(store, "readonly", False):
            return written
        fams = store.families(alive=True, lanes=LANES)
    except Exception:  # noqa: BLE001 - nothing read, nothing written
        return written
    for fam in fams:
        fid = str(fam.get("id"))
        try:
            if fam.get("band") not in ("candidate", "probe", "sized"):
                continue
            state = fam.get("state") or {}
            n = state.get("banded_version")
            if isinstance(n, bool) or not isinstance(n, int):
                continue
            version = store.version(fid, n)
            sha = _run_sha(version)
            if sha is None or not (version or {}).get("code") or seat_recorded(state, n, sha):
                continue
            mark = (str(store.root), fid, sha)
            now = float(gate.clock())
            if now - _seat_failed.get(mark, float("-inf")) < SEAT_RETRY_SECONDS:
                continue
            noted = state.get(VALIDATION_KEY) if isinstance(state.get(VALIDATION_KEY), Mapping) else {}
            code, params = version["code"], dict(version.get("params") or {})
            runner = _runner(gate)
            try:
                validation = _stored_validation(store, fid, n, noted.get("result_sha") if noted.get("version") == n else None)
                made = "stored"
                if validation is None:
                    validation, made = runner.validation(code, params, name=fid, k=econfig.K_BASE).result, "rerun"
                record = _seat_record(store, n, sha, validation, runner.segments(code, params, name=fid),
                                      source="backfill", validation_run=made)
                if record is None:
                    raise ValueError("the runs could not be counted")
            except Exception as exc:  # noqa: BLE001 - it ranks last until the counts can be made
                first = mark not in _seat_failed
                _seat_failed[mark] = now
                store.event("swarm.gate", fid, {"action": "seat_counts_failed", "version": n, "error": type(exc).__name__})
                if first:
                    store.event("swarm.status", fid, {  # a House warning (the swarm's alerts are its status rows)
                        "action": "equity_seat_counts_failed", "alert": True, "version": n,
                        "text": f"the seat rule's two counts of {fid} v{n} could not be made ({type(exc).__name__}): it "
                                "ranks after every program whose counts can be read; tried again hourly"})
                continue
            with store.atomic():
                current = store.family(fid) or {}
                if current.get("retired_at") or seat_recorded(current.get("state") or {}, n, sha) \
                        or (current.get("state") or {}).get("banded_version") != n:
                    continue
                store.set_state(fid, **{SEAT_KEY: record})
            _seat_failed.pop(mark, None)
            store.event("swarm.gate", fid, {"action": "seat_counts", "version": n, "source": "backfill",
                                            "validation_run": made, "_counts": record})
            written.append(fid)
        except Exception as exc:  # noqa: BLE001 - one family's trouble never stops the others
            store.event("swarm.gate", fid, {"action": "seat_counts_failed", "error": type(exc).__name__})
    return written


# ----------------------------------------------------------------------------------------------------------- the seeds
def birth_seeds(store: Any, settings: Mapping[str, Any] | None) -> list[str]:
    """Born once each while the lane is on (`SEEDS_KEY`): the three A4 seeds of league/swarm/seeds.py, as
    agent-authored families of the beta lane. Returns the family ids born this call."""
    if not on(settings) or getattr(store, "readonly", False):
        return []
    from . import cards, seeds

    c = cfg(settings)
    born: list[str] = []
    for spec in seeds.EQUITY_SEEDS:
        sid = str(spec["id"])
        if sid in (store.get(SEEDS_KEY) or {}):
            continue
        if spec["structure"] not in c["structures"] or any(s not in c["universe"] for s in spec["symbols"]):
            continue  # outside the lane's box as set now (elane.structures, elane.universe): born when it is inside
        card, errors = cards.validate(spec["card"], spec["structure"], roots=list(spec["symbols"]), settings=settings)
        if errors or card is None:
            store.event("swarm.status", None, {"action": "elane_seed_refused", "seed": sid, "errors": errors[:6]})
            continue
        code, params = seeds.equity_program_for(spec)
        lane = str(spec["lane"])
        with store.atomic():
            known = dict(store.get(SEEDS_KEY) or {})
            if sid in known:
                continue
            fam = store.add_family({**seeds.equity_family_spec(spec), "card_sha": cards.card_sha(card)}, origin="seed")
            fid = str(fam["id"])
            cards.put(store, fid, card, spec["structure"])
            version = store.add_version(fid, code, params, author=SEED_AUTHOR, note=SEEDED_NOTE)
            store.update_family(fid, best_version=int(version["n"]))
            store.set_state(fid, **{TEMPLATE_KEY: lineage_key(lane, str(version["sha"]))})
            known[sid] = fid
            store.put(SEEDS_KEY, known)
            store.event("swarm.born", fid, {"parent": None, "mechanism": fam["mechanism"], "structure": fam["structure"],
                                            "roots": fam["roots"], "origin": "seed", "lane": lane, "label": label(lane),
                                            "seeded": True, "note": SEEDED_NOTE})
        born.append(fid)
    return born


# ----------------------------------------------------------------------------------------------------------- views
def view(fam: Mapping[str, Any], *, lane: str | None) -> dict[str, Any]:
    """The lane's line in a status or report: {lane, label, seeded, screen (the screen that judged its recorded look;
    None before it), try, look, beside} (labels always; figures only where the reader may see them)."""
    state = fam.get("state") if isinstance(fam.get("state"), Mapping) else {}
    spec = fam.get("spec") if isinstance(fam.get("spec"), Mapping) else {}
    held = state.get(TRY_KEY) if isinstance(state.get(TRY_KEY), Mapping) else None
    looked = state.get(LOOK_KEY) if isinstance(state.get(LOOK_KEY), Mapping) else None
    judged = (looked.get("verdict") or {}).get("screen") if looked else None
    out = {"lane": lane, "label": label(lane), "seeded": spec.get("seeded") is True,
           "screen": judged if judged in SCREENS else None,
           "try": {"version": held.get("version"), "entered": bool(held.get("entered"))} if held else None,
           "look": {"version": looked.get("version"), "passed": bool((looked.get("verdict") or {}).get("passed"))}
           if looked else None,
           "beside": looked.get("beside") if looked else None}
    notes = [BETA_NOTE] if lane == BETA else []
    if out["seeded"]:
        notes.append(SEEDED_NOTE)
        if isinstance(spec.get("provenance"), str) and spec["provenance"].strip():
            notes.append(f"where it came from: {spec['provenance']}")  # as it is: the reversal seed is not blind
    out["notes"] = notes
    return out


__all__ = ["MODES", "STRUCTURES", "LABELS", "BETA_NOTE", "SEEDED_NOTE", "SEEDS_KEY", "TRY_KEY", "DEFAULTS", "cfg", "on",
           "lane_of", "label", "card_errors", "lineage_key", "screen_effective", "screen_name", "SCREENS", "REPO",
           "try_open", "lineage_spent",
           "roster_seats", "isolated_runner", "validate", "look", "birth_seeds", "seeded", "view", "BETA", "EQUITY",
           "LANES", "LOOK_KEY", "FLOOR_KEY", "TRAIN_R_KEY", "TEMPLATE_KEY", "VALIDATION_KEY", "VERDICTS_KEY", "SIGMA_KEY", "SCREEN",
           "ROUND_KEY", "ROUND_SECONDS", "round_order", "seed_ahead", "seed_owed", "seed_wait", "seed_waits_over",
           "SEED_WAIT_KEY", "SEED_WAIT_SECONDS", "SEED_WAIT_REPEAT_SECONDS", "SEED_WAIT_GAP_SECONDS",
           "LOST_KEY", "LOOK_SENDS", "EVIDENCE_HASH_SEED", "SAME_LINEAGE",
           "FLOOR_INELIGIBLE", "REFUSED_BEFORE_LOOK", "REFUSED_CAUSES",
           "STORE_DIR", "SEED_AUTHOR", "CLASSES", "INPUTS", "NOT_A_TRY", "SPENT_LOOK", "SPENT_TRY", "ROSTER_CLOSED",
           "card_lane", "candidate", "lineage_tries", "next_try", "reviewed", "same_lineage", "LineageUnread", "LOSS_LINE",
           "loss_line", "SEAT_KEY", "SEAT_RETRY_SECONDS", "seat_recorded", "seat_activity", "seat_backfill"]
