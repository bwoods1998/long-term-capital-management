"""THE EQUITY LANES (release E1, Oct 2026): agent programs that trade long-only ETFs (and later stocks), beside the
options lanes, judged by the share screen S1 and traded by the House's EquityBook.

Owner: swarm. Protected like league/swarm/dlane.py (league/ci.py FORBIDDEN; the gateway's MERGE_FORBIDDEN in a later
gateway PR). The lanes' one swarm-side home: their settings and bounds, the card box, the screen they use, the ration
(one Validation try and one holdout look a lineage), the equity roster, the three captain-seeded programs, and the
labels every view carries. With `elane.mode` "off" (the code's default; the rollback) nothing here acts.

THE LANES (`league.equity.LANES`): "beta" (structure "etf"; every view, brief, status line and report labels it MARKET
BETA: its profit is the market's direction, stated plainly) and "equity" ("etf" and "stock": trend, momentum, mean
reversion, low volatility, rotation; earnings drift waits for data). A family's lane is its card's (`card.lane`),
immutable, inherited by a fork. In E1 `elane.structures` is ["etf"] and the births are the three seeds (A4); the
architect's and the researcher's equity births are E2.

SETTINGS (`cfg`; policy.json "elane", swarm.json over it; `DEFAULTS` is the rollback):
- `mode` "off" | "gate" (default "off");
- `universe` (inside league/equity/config.py UNIVERSE; the constitution's `equity_money.universe` bounds it),
  `structures` (["etf"] in E1);
- `birth_share` 0 in E1 (taken out of the alpha share first, E2);
- `roster` 3, which equals `equity_money.probe.max_programs` (a test holds them equal): equity Probe seats, apart from
  `dlane.roster` (league/swarm/bands.py `waiting`);
- `screens`: per lane {"name": "S1", "receipt_sha256", "c_R", "c_X", and the receipt's figures}: read from the
  REPOSITORY's policy.json only (never swarm.json); a test holds the sha to docs/benchmarks/equity_screen_1.json; with
  no pinned receipt the screen refuses every program (`screen_effective`, league/equity/screen.py `pinned_receipt`);
- `val_tries` 1 and `looks_per_lineage` 1 (whatever is written), plus R3's one Validation-only retry when the
  receipt permits it and the first try FAILED its pre-check, the retry version's hash recorded at the first try
  (A9 D3; league/equity/screen.py `retry_permitted`);
- `program_loss_usd` -300 (a tightening only: -300 to -25).

THE LINEAGE (A9 D3): a program whose Train daily returns correlate >= 0.7 with a program already looked at
(`league.equity.screen.same_lineage`, over the House-only Train series each look keeps), or that uses the same template,
is the same lineage: one look a lineage. Look and Validation outcomes of share programs are never fed back to
generators or the diagnostician.

LANE-SCOPED KEYS (A8.12): lineage, spent-root and graveyard keys carry the lane (`lineage_key`, `graveyard_key`), so
the options lanes' spent SPY/QQQ/IWM always-in roots never refuse an equity birth, and a REFUTED equity row binds only
its own lane's cards.

THE SEEDS (A4; league/swarm/seeds.py `EQUITY_SEEDS`): seed-overnight-spy, seed-overnight-qqq, seed-reversal-index,
each born once as an agent-authored family (`birth_seeds`), then Validation, the S1 pre-check and one sealed look like
any family. Every report says plainly that these three were seeded by the captain's build agents, and the Done meter
reads Done with and without them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..equity import BETA, EQUITY, LANES

MODES = ("off", "gate")
STRUCTURES = ("etf", "stock")
LABELS = {BETA: "MARKET BETA", EQUITY: "EQUITY"}
#: The plain statement beside every beta figure (the goal's item 2: a BETA lane, labelled as market beta).
BETA_NOTE = "MARKET BETA: profit from market direction, reported beside the same-risk buy-and-hold; not alpha"
SEEDED_NOTE = "seeded by the captain's build agents (A4), judged by the swarm's screen like any family"
#: The store's kv key of the seeds already born ({seed id: family id}).
SEEDS_KEY = "elane_seeds"
#: The family state's key of its equity lineage's Validation try ({version, at, first, precheck, entered}).
TRY_KEY = "elane_try"

DEFAULTS: dict[str, Any] = {
    "mode": "off",
    "universe": ["SPY", "QQQ", "IWM", "DIA"],
    "structures": ["etf"],
    "birth_share": 0.0,
    "roster": 3,
    "screens": {BETA: {"name": "S1", "receipt_sha256": None, "c_R": None, "c_X": None, "fp_cap": None,
                       "owner_wall": None, "retry": False, "r4": {}, "beside": None},
                EQUITY: {"name": "S1", "receipt_sha256": None, "c_R": None, "c_X": None, "fp_cap": None,
                         "owner_wall": None, "retry": False, "r4": {}, "beside": None}},
    "val_tries": 1,
    "looks_per_lineage": 1,
    "program_loss_usd": -300,
}


def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """`elane` in the swarm's settings, each value inside its bound (a malformed value is its default; tightening only
    where the module docstring says so)."""
    raise NotImplementedError("swarm: league/swarm/elane.py cfg")


def on(settings: Mapping[str, Any] | None) -> bool:
    """`elane.mode` is "gate"."""
    raise NotImplementedError("swarm: league/swarm/elane.py on")


def lane_of(store: Any, fam: Mapping[str, Any] | None) -> str | None:
    """"beta" | "equity" for an equity-lane family (its spec's `lane`, else its card's), else None."""
    raise NotImplementedError("swarm: league/swarm/elane.py lane_of")


def label(lane: str | None) -> str:
    """"MARKET BETA" | "EQUITY" (`LABELS`); "" for another lane."""
    raise NotImplementedError("swarm: league/swarm/elane.py label")


def card_errors(card: Any, structure: Any, symbols: Any, settings: Mapping[str, Any] | None) -> list[str]:
    """Every reason an equity card is outside its lane's box (lane, structure in `elane.structures`, symbols inside
    `elane.universe`, a beta card's structure "etf" only), [] when it is inside."""
    raise NotImplementedError("swarm: league/swarm/elane.py card_errors")


def lineage_key(lane: str, key: str) -> str:
    """A lineage, spent-root or graveyard key scoped by its lane (A8.12): "<lane>:<key>" for an equity lane, `key`
    unchanged for an options lane (the options keys never move)."""
    raise NotImplementedError("swarm: league/swarm/elane.py lineage_key")


def screen_effective(settings: Mapping[str, Any] | None, lane: str, *,
                     policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The screen an equity family's look uses: {lane, screen "S1", receipt (sha or None), c_R, c_X, figures, why}:
    the pinned receipt of the REPOSITORY's policy.json `elane.screens.<lane>` (`policy`: its parsed document; default
    `settings.read_policy()`), `why` naming the refusal when none is pinned."""
    raise NotImplementedError("swarm: league/swarm/elane.py screen_effective")


def try_open(store: Any, fam: Mapping[str, Any], n: Any, settings: Mapping[str, Any] | None) -> bool:
    """Whether version `n` may take its lineage's Validation try (one a lineage; R3's retry only when permitted)."""
    raise NotImplementedError("swarm: league/swarm/elane.py try_open")


def lineage_spent(store: Any, fam: Mapping[str, Any], settings: Mapping[str, Any] | None) -> str | None:
    """Why the family's equity lineage can take no look (its one look used, or its one try failed), or None."""
    raise NotImplementedError("swarm: league/swarm/elane.py lineage_spent")


def roster_seats(root: str | Path) -> int:
    """`elane.roster` from <root>/swarm.json over policy.json, FAILING CLOSED as `bands._roster_seats` does for
    `dlane.roster` (unreadable: the last good value, else no new seat)."""
    raise NotImplementedError("swarm: league/swarm/elane.py roster_seats")


def isolated_runner(root: str | Path) -> Any:
    """The swarm process's `league.equity.runner.Isolated` over <root>/equity-daily with its own decider child
    (`league.live.decider.Decider`, its log <root>/equity-decider.log), built once a process."""
    raise NotImplementedError("swarm: league/swarm/elane.py isolated_runner")


def validate(tournament: Any, fam: Mapping[str, Any], version: Mapping[str, Any]) -> dict[str, Any]:
    """An equity family's Validation (tournament.py dispatches here by lane): the isolated runner's 2025 run at k 1.0
    and 1.5, recorded as the tournament records a Validation (its `validation_r_sd_by_version`: the per-trade net
    return sd), the S1 pre-check (`league.equity.screen.precheck`) as its line, the lineage's try recorded
    (`TRY_KEY`). Returns the tournament's verdict dict."""
    raise NotImplementedError("swarm: league/swarm/elane.py validate")


def look(gate: Any, fam: Mapping[str, Any], version: Mapping[str, Any], sha: str) -> bool | None:
    """An equity family's ONE sealed look, on the House (gate.py dispatches here by lane): refused when no receipt is
    pinned; the floor from the program's Train-era runs (`Isolated.segments` -> `screen.series` -> `screen.floor`);
    the look with a freshly minted `EquityGateCapability` (`Isolated.look`); `screen.verdict` and `screen.beside_line`
    recorded with the look. True passed (the family becomes a Candidate), False failed, None not run (no look spent)."""
    raise NotImplementedError("swarm: league/swarm/elane.py look")


def birth_seeds(store: Any, settings: Mapping[str, Any] | None) -> list[str]:
    """Born once each while the lane is on (`SEEDS_KEY`): the three A4 seeds of league/swarm/seeds.py, as
    agent-authored families of the beta lane. Returns the family ids born this call."""
    raise NotImplementedError("swarm: league/swarm/elane.py birth_seeds")


def seeded(store: Any, fid: str) -> bool:
    """Whether a family is one of the three captain-seeded programs (the Done meter's with/without split, A8.12)."""
    raise NotImplementedError("swarm: league/swarm/elane.py seeded")


def view(fam: Mapping[str, Any], *, lane: str | None) -> dict[str, Any]:
    """The lane's line in a status or report: {lane, label, seeded, screen, try, look, beside} (labels always; figures
    only where the reader may see them)."""
    raise NotImplementedError("swarm: league/swarm/elane.py view")


__all__ = ["MODES", "STRUCTURES", "LABELS", "BETA_NOTE", "SEEDED_NOTE", "SEEDS_KEY", "TRY_KEY", "DEFAULTS", "cfg", "on",
           "lane_of", "label", "card_errors", "lineage_key", "screen_effective", "try_open", "lineage_spent",
           "roster_seats", "isolated_runner", "validate", "look", "birth_seeds", "seeded", "view", "BETA", "EQUITY",
           "LANES"]

