"""The hypothesis foundry: Merton writes falsifiable strategies for the desks where evidence says
they can work, replay admits them before they cost a paper seat, and exhausted ideas stop breeding.

Why this exists (measured on the production ledger, Sept 22, 2026): 94% of the previous day's births
were House-staked parameter mutations placed on the desk "with the most room" (`House._refill`), and
66% of them landed on six desks that had never produced a live agent -- crypto strikes, crypto
majors, attention, crypto alts, megacaps and props. Over the league's life those six had run 74,
52, 47, 81, 94 and 73 replays with NO pass between them, and the parent lines already carried a
median of fifteen failed trials each. The weather desk had passed 12 of its 32 replays and sent
every agent it had to paper, yet received four mutations. Replay passes 6.5% of trials and does
predict paper results, so it stays the admission test; what changes is what is sent to it.

One foundry pass:

1. **Allocate.** Every open, replayable desk is scored from its own evidence (`desk_scores`): its
   replay pass rate (shrunk toward the league's), the share of its traders earning forward, and
   how often its inputs were actually there. How EMPTY a desk is does not enter the score; a desk
   with no open seat is merely ineligible. A bounded share of passes (`exploration_share`, 20%)
   goes instead to the least-explored eligible desk, so an early winner cannot starve every new
   direction. Two more bounded routes come first (Sept 23, 2026; `allocate` has the precedence):
   `transfer_share` of calls port a mechanism that earns forward to a desk of its venue where it
   was never tried (`forward_families`), and `fast_share` rotate over the hourly, around-the-clock
   `fast_desks`.
2. **Ask.** When a seat is actually open, the frontier tier still pays for code work, the day's
   OpenAI allowance and the foundry's own window budget have room, and the last call is at least
   `call_minutes` old, Merton (the frontier model, through the same metered gateway client every
   other pass uses) is shown the desk's definition, the data that really exists, the fee model,
   the replay gate, what failed there and what is retired, the league's edge map
   (`winning_mechanisms`: what earns forward on any desk, and what died on the forward evidence)
   and, on a transfer call, the mechanism being ported, and asked for 3-4 distinct candidates.
   Each is a `hypothesis.card` (mechanism, data, edge after costs, horizon, rejection evidence)
   plus a whole strategy file. It is never shown a tape, a holdout or any replay's per-step data:
   only development-replay SUMMARIES that the researchers already see -- and never another
   agent's code: a mechanism travels as words (a card's mechanism, a founding seed's `why`, the
   purpose a program was born with).
3. **Admit.** Each card's code is checked statically, then replayed through the House's own
   candidate replay (`House._candidate_replay`: the sealed NEEDS probe, the specialty's
   constraints, parameter validation, a counted `eval.trial`). A card is its own line -- a new
   hypothesis, like a founder or an architect's strategy -- so its trial is recorded under the id
   its child will carry, and the child's lineage includes it. Only a passer is born, through
   `House.spawn`, straight onto a paper seat; a failure is a counted trial on the card's line and
   no agent ever exists for it.
4. **Retire.** A family (the House's unit of "one idea on one kind of market") with
   `retire_after_failures` counted failures and no pass is retired: `disproven` when its replays
   ran on real data and failed the gates, `blocked_data` when most of them walked an empty tape.
   Card evaluations that could not run are `blocked_data` (missing inputs) or `blocked_infra`
   (sandbox errors, timeouts, crashes), and a desk that keeps hitting them becomes a
   `repair.reported` row rather than more births. Retired families get no House mutations; a
   retired or already-tested mechanism gets no new card. `hypothesis.link` rewordings share
   FAILURE HISTORY for this heuristic only; genealogy and trial counts never follow a link.

What routine refill does now (`refill`, from `House._refill` when `replace_mutation_refill` is on):
a replay-passing card first, by desk evidence; otherwise an evidence-driven mutation of a parent
that is earning forward, within `mutation_share` of recent births; otherwise nobody. The deliberate
exceptions are kept and labelled on the ledger (`route.decision`, one row per birth): founders start
on paper without a replay pass, earner forks are paid by a parent that earned, a research
candidate's child starts on paper because its own code passed replay, and the architect's
strategies still answer to replay from rung 0.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass, asdict
from decimal import Decimal
from typing import Any, Collection, Mapping, Sequence

from .agents import Agent, niche_of
from .constitution import CONSTITUTION
from .ledger import now_iso
from .seeds import SEEDS

PROMPT_VERSION = "foundry-2026-09-24.1"
ROLE = "foundry"
TASK_CALL = "hypothesis.foundry"
TASK_EVALUATE = "hypothesis.evaluate"

#: The dials, overridden by `game.json` `hypotheses`. Kept here too so an older game file (or a test
#: game) still gets a sane, bounded foundry.
def foundry_model(game: Mapping[str, Any]) -> str | None:
    """The model the foundry writes cards with (`game.json` `hypotheses.model`), or None for the
    House's frontier model. A card is judged by replay before it costs a seat, so it need not be
    written by the dearest model: GPT-6 Sol from Sept 22, 2026, at about a fifth of Astra's price."""
    model = str(((game or {}).get("hypotheses") or {}).get("model") or "").strip()
    return model or None


DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "replace_mutation_refill": True,
    "call_minutes": 30,
    "candidates": 4,
    "max_output_tokens": 16000,
    "effort": "medium",
    "model": "",  # empty: the House's frontier model
    "budget_usd": "20",
    "budget_window_hours": 24,
    "exploration_share": 0.2,
    "exploration_window": 10,
    "retire_after_failures": 15,
    "blocked_share": 0.5,
    "repair_after_blocked": 3,
    "infra_failures": 5,
    "blocked_hours": 24,
    "max_evaluation_attempts": 3,
    "mutation_share": 0.2,
    "mutation_min_per_day": 2,
    "card_ttl_hours": 24,
    "link_min_confidence": 0.8,
    "prior_weight": 10,
    "evidence_days": 14,
    # Sept 23, 2026 (the owner: "a swarm ... that trades 24/7"): up to `fast_share` of recent calls
    # go to the best-scored desk among `fast_desks` (hourly evidence, around the clock), whose low
    # replay pass rates would otherwise never win the evidence route; the horizon Merton is told to
    # prefer where a desk allows it; and how many cards may await replay before the next call (0:
    # none, the rule until Sept 23 -- a call's four cards replay one after another, and the foundry
    # sat idle behind them).
    "fast_desks": [],
    "fast_share": 0.0,
    "prefer_horizon": "",
    "max_pending_cards": 0,
    # Sept 23, 2026 (the owner's north star: a swarm that compounds what works): up to
    # `transfer_share` of recent calls take a family with an earned forward record to a desk of its
    # venue where it has never been tried, and ask Merton to adapt its mechanism there. 0 is off.
    "transfer_share": 0.0,
    # Sept 23, 2026 (the learn-and-unblock run, S3/C3): the fast lane follows forward yield. A desk
    # whose foundry-born agents have a negative pooled forward record over at least
    # `fast_lane_min_blocks` active blocks gets no fast-lane call until one family there is positive
    # over `fast_lane_reopen_blocks` active blocks; the open fast desks are ranked by that yield.
    "fast_lane_min_blocks": 6,
    "fast_lane_reopen_blocks": 3,
    # Sept 24, 2026 (E2 of the close-the-gaps run): desks that get no card, on any route, until a family there
    # has a positive pooled forward record over `closed_reopen_blocks` active blocks (`_closed_desks`).
    "closed_desks": [],
    "closed_reopen_blocks": 3,
    # The first transfer to try (E2): a family scaled on a fair value on its own desk, before any port to a
    # desk where it never lived (`first_transfer`); {} is none. Its keys: family, desk, mechanism, feeds.
    "first_transfer": {},
}

#: The recorders of Sept 24, 2026 (league/feeds.py) a card on each desk may name (E2 of the close-the-gaps
#: run): weather ensembles, NWS forecasts and the forecast history for kalshi-weather; EDGAR 8-K acceptance
#: times and the Nasdaq calendar for the megacaps and options (and the index ETFs, whose heaviest members
#: report); SOFR and par yields for the rates series of the open Kalshi desk; ESPN odds and scoreboards for
#: sports; DVOL, settled funding, open interest and the perps snapshot for crypto; TSA volumes for the
#: attention desk; the owner's keyed feeds (EIA) where they apply. The packet shows only those the House
#: records (`Foundry._recorded_feeds`).
DESK_FEEDS: dict[str, tuple[str, ...]] = {
    "kalshi-weather": ("weather", "nws", "forecast"),
    "alpaca-megacaps": ("earnings", "earnings_date"),
    "alpaca-options": ("earnings", "earnings_date"),
    "alpaca-index-etfs": ("earnings", "earnings_date", "rates", "treasury"),
    "alpaca-crypto-majors": ("vol", "funding", "oi", "perps"),
    "alpaca-crypto-alts": ("funding", "oi", "perps"),
    "kalshi-crypto-strikes": ("vol", "funding", "oi", "perps"),
    "kalshi-crypto-15m": ("vol", "funding", "oi", "perps"),
    "kalshi-sports": ("odds", "sports"),
    "kalshi-sports-props": ("odds", "sports"),
    "kalshi-open": ("rates", "treasury", "weather", "forecast", "tsa", "eia"),
    "alpaca-open": ("earnings", "earnings_date", "vol", "funding", "oi", "perps", "rates", "treasury"),
    "kalshi-prices": ("eia",),
    "kalshi-attention": ("tsa",),
}

#: The bounded routes of `allocate`, in the order they are offered a call; `evidence` takes the rest.
ROUTES = ("transfer", "fast", "exploration")

#: A founding seed's stated reason, by seed name (`league/seeds`): the words a founder's family is
#: described in. `league/niches.json` founders name a seed and carry no `why` of their own.
SEED_WHY = {row["name"]: str(row.get("why") or "") for row in SEEDS}

#: How a parameter mutation's birth is explained (`House.fork`, the House's refill, the foundry's
#: evidence mutation). Such a child runs its parent's program, so its mechanism is its parent's.
_MUTATION_REASONS = ("a parameter mutation", "a House-staked valid mutation", "an evidence-driven House mutation")

#: Words that say a candidate's replay could not run because an INPUT was missing, not because the
#: idea failed. (`House._run_replay` raises "unsupported input: ..." for missing observed bars.)
_DATA_WORDS = ("unsupported input", "missing", "no tape", "no data", "empty tape", "not recorded", "no recorded")
#: And the words of a harness failure: the box, the clock or the platform, not the strategy.
_INFRA_WORDS = ("sandbox", "timed out", "timeout", "killed", "could not be run", "exit 137", "no result line",
                "connection", "urlerror", "httperror", "oserror", "brokenpipe", "transporterror", ": http 5", ": http 429",
                "response is not an object")

#: What a strategy sees on the REPLAY tape, which is not everything a live wake sees (league/replay.py).
#: Measured in the Sept 22, 2026 dry run: three of four megacaps cards guarded against stale quotes by
#: their `t` stamp, which replay quotes do not carry, and so never traded at all -- a counted trial
#: that tested nothing. Merton is told this as a fact of the test, not a hint about edge.
REPLAY_VIEW = {
    "every_step": ["now", "venue", "rung (0)", "params", "memory", "cash", "equity", "limits", "fees",
                   "positions (symbol or market/leg, quantity, average_cost, mark, opened_at, reason)",
                   "open_orders (order_id, side, quantity, limit_price, filled, submitted_at)"],
    "alpaca": "bars: closed bars, oldest first, up to NEEDS.bars.limit; quotes: {bid, ask} ONLY, derived from the bar with the "
              "tape's half-spread -- there is NO quote timestamp `t` in replay, so a staleness check must treat a missing `t` as fresh",
    "kalshi": "markets: the rows the contract lists, with hours_to_close; watched symbols arrive as observed.bars only",
    # Sept 23, 2026: two point-in-time histories a replay can use at once (league/feeds.py).
    "feeds": "only when NEEDS['feeds'] declares them: ctx['feeds'][feed][key], the latest row whose t is at or before the step. "
             "Backfilled over the replay window, so replayable now: vol (Deribit DVOL for BTC and ETH, hourly candles stamped at "
             "their close), funding (OKX settled funding per coin, stamped at settlement), oi (OKX hourly open interest, stamped "
             "at the hour's end), forecast (Open-Meteo GFS and ECMWF daily high, low and rain at 1-3 days' lead per settlement "
             "station, stamped 11:00 local standard time) and earnings (each 8-K Item 2.02's EDGAR acceptance time). Recorded "
             "live only, from when recording began: sports, perps, weather (ensembles), nws, earnings_date, rates, treasury, "
             "odds and tsa. A key may be absent: use it only when present",
    "absent_in_replay": ["quotes[...].t", "recent_order_outcomes", "event_risk"],
    "rule": "Code that REQUIRES a field replay does not supply never trades on replay and cannot pass. Use such fields only when present.",
}

FOUNDRY_BRIEF = """You are Merton, the theorist of a small real-money trading league, writing NEW STRATEGY
HYPOTHESES for one desk. You do not pick trades. You write programs that the House replays on recorded
history; only a program that passes that replay is given a paper seat, and only a paper record earns
real money after an independent audit.

Why you are being asked: the House used to fill empty seats with random parameter mutations of the
programs already there. Most of them landed on desks that had never produced a live agent, on lines
that had already failed a dozen replays. Your job is to replace that with a few hypotheses that have
a REASON to work, each stated so that the evidence can reject it.

Rules.
- Write exactly `batch.candidates` candidates, each a DIFFERENT MECHANISM: a different reason the edge
  exists (who is on the other side, what structural fact pays you), not one rule with other numbers.
  (A `transfer` batch is the one exception, below.)
- Stay inside `desk`: NEEDS.venue is `desk.venue`, NEEDS.horizon is one of `desk.horizons`, and NEEDS
  names series (Kalshi) or symbols (Alpaca) from `desk.universe` only. A program whose NEEDS sit
  outside the desk is refused before it runs.
- Use only data that exists (`data`). Never assume an input listed in `data.not_supplied`. Watched
  inputs (NEEDS.observe) only where `data` says replay supplies them.
- MODEL VERSUS MARKET. Every card is a model of fair value against the market's price: compute what the
  contract or the stock is worth from data the House records -- `data.recorded_feeds` lists the feeds this
  desk may read (weather ensembles and NWS forecasts, 8-K earnings times, SOFR and par yields, ESPN odds,
  DVOL and funding ...), with how to declare each in NEEDS["feeds"] and whether a replay can judge it now
  -- and trade only where the model and the price disagree by more than the fee and the spread. Name every
  feed it reads in `data`, as `data.recorded_feeds` names it.
- State the FEE each trade pays (`fee`, from `fees`: taker or maker, per side and per round trip) and the
  EDGE IT NEEDS to clear it (`edge_needed`: how far the model must be from the price, per trade, to pay that
  fee and the spread). A card that does not state both is refused before its replay.
- `forward_on_this_desk` carries each family's measured CAPACITY (markets it bids a day, its fill rate at its
  size, dollars a day at its edge): a family `at_capacity` already fills the markets it bids at the size it
  trades, so a card that only repeats it there adds nothing. Write for markets it does not fill.
- Read `failed_on_this_desk` and `retired_on_this_desk`. Do not resubmit a failed or retired mechanism
  unless `mechanism` names the specific reason it failed and why yours is different in kind.
- Model the fees in `fees` explicitly, and state `edge_after_costs` with the arithmetic. On Alpaca
  crypto a taker round trip costs 0.50% and a maker round trip 0.30%: rest post_only limits for entry
  AND exit unless the edge per trade clearly clears the taker cost. Most crypto replays on this league
  have failed out-of-sample growth by less than the fee.
- Kalshi crypto strike and fifteen-minute markets (`kalshi-crypto-strikes`, `kalshi-crypto-15m`) are
  binary options on spot. A strategy may watch the coin's Alpaca spot bars through
  NEEDS["observe"]["symbols"] (e.g. "BTC/USD"; on a Kalshi replay tape they arrive as
  ctx["observed"]["bars"] only, at NEEDS.bars.timeframe, default 1Hour) and, where `data` lists
  them, the recorded feeds through NEEDS["feeds"]. Price the binary from spot and volatility over
  the time left, and bid as a maker only where the model clears the ask plus fees. Most Kalshi
  crypto series charge makers nothing (`desk.maker_fee_series` lists the exceptions).
- On `kalshi-crypto-15m` MAKER ENTRIES ARE REQUIRED: a taker entry there costs 182 bps of notional
  (measured on 178 shadow taker fills, Sept 23, 2026), which is the whole edge of any favourite or
  fade on a fifteen-minute binary; the desk's taker programs ran -1.9% a block. Rest post-only bids
  and let the fill rate be the cost, never the fee.
- On any binary (Kalshi) market a position above 15% of the stake is a ONE-LOSS TRIAL: one lost
  settlement of that size demotes the program from real money (the allocator's hysteresis line),
  and two foundry strike programs lost $113.68 in ten settlements that way on Sept 23, 2026. Size
  binary positions under 15% of the stake unless the modelled edge is measured, not hoped for.
- Prefer `horizon_guidance.prefer` where the desk allows it: an hourly program is judged on hourly
  blocks and can reach the paper screen in hours; a daily one waits days for the same evidence.
- Read `forward_on_this_desk`: what has actually made money forward here, on paper and real money.
- Read `winning_mechanisms`: the league's edge map. `earning` is the best forward records on any desk
  (real money first), each mechanism in words; `failed_forward` is what died on the forward evidence.
  A mechanism that earns on one desk may carry to this one; one that died forward is a warning.
- When the packet has a `transfer` section, the House is porting a proven mechanism: it earns forward
  on `transfer.from_desk` (`transfer.forward_record`) and has never been tried on this desk. Write at
  least half of the batch as adaptations of `transfer.mechanism` to THIS desk's markets, data, fees and
  horizons. They share its reason for the edge, so make each a distinct expression of it (other
  markets, timing, entry or exit), and each is still a falsifiable card with its own `rejection` test;
  say in `mechanism` what carries over and what might not. You see its mechanism in words, never code.
  A `transfer` marked `scale` keeps the family on its own desk and widens it: follow `transfer.ask` (a fair
  value from the named feeds, priced on every market of the desk it can reach, bid where the model clears
  the ask and the fee).
- It must TRADE on the replay tape: `replay_gate` needs at least min_trades closed trades and
  min_blocks blocks within `replay_window`, out-of-sample growth above min_oos_growth a block (zero
  when it is not stated), and a deflated Sharpe at least min_deflated_sharpe. A program that never
  fires cannot pass; one that trades noise after fees will not either. Be specific rather than hopeful.
- Size by conviction. The owner's rule, after Druckenmiller: swing big when you see the ball, bunt
  when you don't. Every program should scale its position with the edge its signal measures -- the
  minimum useful size when the signal is marginal (a bunt: cheap evidence, many closed trades), up to
  `limits` when the modelled edge is large and the setup has paid before -- never one fixed size for
  every signal. Growth is scored in log terms, so the right size is near Kelly: large only when the
  edge is large relative to its variance. Say in `edge_after_costs` how the size follows the edge.
- The owner accepts volatility for speed and discovery: prefer bold, distinct mechanisms that trade
  often enough to be judged within days over timid ones that barely fire.
- Respect `horizon_rule` and `limits`. No shorts, no leverage; exits are always allowed.
- Read `replay_view`: replay does not supply everything a live wake does (quotes there have no
  timestamp). A program that requires a missing field never trades on replay and cannot pass.
- Follow the strategy contract below EXACTLY (imports, NEEDS, PARAMS, decide(ctx), the return shape).
  Declare custom numeric knobs in NEEDS.parameter_rules so they are valid.
- `rejection` is your public commitment: the replay or paper result that would show you were wrong.

Answer with ONE JSON object and nothing else:
{"summary": "two or three plain sentences: what you saw on this desk and what you are testing",
 "candidates": [{"name": "lowercase-words-with-dashes, under 24 characters",
                 "mechanism": "why the edge exists and who pays it",
                 "data": ["each input it requires, as NEEDS names it"],
                 "edge_after_costs": "expected edge per trade after fees and spread, with the arithmetic",
                 "fee": "the fee each trade pays, from `fees`",
                 "edge_needed": "how far the model must be from the price, per trade, to clear that fee and the spread",
                 "horizon": "how long a position is held, and the block it is judged on",
                 "rejection": "what evidence would reject it",
                 "code": "the WHOLE strategy file"}]}"""


def normalize(text: Any) -> str:
    """The mechanism text an exact-duplicate check compares: case, spacing and punctuation removed."""
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def card_id(mechanism: Any, niche: str) -> str:
    """`hypothesis.card` id: a sha256 prefix of the normalized mechanism plus the niche (shared schema)."""
    return hashlib.sha256((normalize(mechanism) + "\n" + str(niche)).encode("utf-8")).hexdigest()[:16]


def static_needs(code: str) -> dict[str, Any] | None:
    """NEEDS read WITHOUT running the module: a literal assignment only. The House still reads the
    real NEEDS in its sealed probe box; this only picks which horizon a candidate says it trades."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "NEEDS" for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                return None
            return value if isinstance(value, dict) else None
    return None


def classify_error(error: Any) -> str:
    """`blocked_data`, `blocked_infra` or `invalid` for a candidate replay that was not a trial."""
    text = str(error or "").lower()
    if any(word in text for word in _INFRA_WORDS):
        return "blocked_infra"
    if any(word in text for word in _DATA_WORDS):
        return "blocked_data"
    return "invalid"


@dataclass(frozen=True)
class DeskScore:
    niche: str
    score: float
    replay_rate: float
    forward_rate: float
    availability: float
    trials: int
    passes: int
    earning: int
    with_record: int
    cards: int
    open_seats: int
    eligible: bool
    why: str


class Foundry:
    """Merton's hypothesis work for the House. Every decision is a ledger row; the cadence and the
    in-flight evaluations are folded from the ledger, so a restart neither repeats a paid call nor
    loses a card (`house.json` holds only throttles)."""

    def __init__(self, house: Any, frontier: Any = None):
        self.house = house
        self._frontier = frontier
        self.refusal = ""
        self._scores: tuple[float, list[DeskScore]] | None = None
        self._allocation: tuple[float, Any] | None = None
        self._edge: tuple[float, dict[str, Any]] | None = None
        self._memo: dict[str, tuple[Any, Any]] = {}  # fold name -> (what it was read from, the fold) (`_folded`)
        from .yield_ledger import YieldLedger

        #: The hourly `ops.budget` yield row; None switches it off (tests that count budget rows).
        self.yield_ledger: Any = YieldLedger(house)
        state = self._state()
        if "birth_cursor" not in state:
            # Label births from the moment the foundry is switched on. The earlier ones happened
            # under the old refill; relabelling them now would stamp hundreds of rows with today's
            # time and make the day's birth count (the mutation share's base) meaningless.
            with house._state_lock:
                state["birth_cursor"] = house.ledger.head()[0]

    #: What each fold read through `_folded` depends on besides the ledger rows of its kinds: whether it reads
    #: the registry's agents (their family, desk and founder, which a birth sets and nothing changes), and the
    #: settings it reads. A fold not named here (`blocked`, which also reads the clock) is rebuilt whenever
    #: the ledger has grown.
    FOLD_INPUTS: dict[str, tuple[tuple[str, ...], bool, tuple[str, ...]]] = {
        "cards": (("hypothesis.card",), False, ()),
        "evaluations": (("trace.record",), False, ()),
        "calls": (("merton.pass",), False, ()),
        "retired": (("hypothesis.retired", "repair.status", "eval.trial"), False, ()),
        "desk_forward": (("eval.block",), True, ("fast_lane_min_blocks", "fast_lane_reopen_blocks")),
        "tried": (("merton.pass", "hypothesis.card"), True, ()),
        "families": (("eval.trial", "hypothesis.card"), True, ()),
    }

    def _folded(self, name: str, build: Any) -> Any:
        """A fold of the ledger, rebuilt only when what it reads has changed (several are read per tick).

        Sept 24, 2026 (R6-perf): keyed on the ledger's head, every fold was rebuilt whenever ANY row was
        appended, and on the box the research threads append every few seconds, so nearly every read
        rebuilt its fold from all its rows (8,206 `trace.record` rows for `evaluations`, 2,555 `eval.trial`
        for `retired` and `families`, ... on the 17:27Z snapshot; the tick's `hypotheses` step took 6.4 s at
        17:25Z and 20.6 s at its slowest that hour, and health and the refill read the same folds). A fold
        in `FOLD_INPUTS` is now keyed on the newest row of its own kinds (the ledger is append-only: no new
        row of them is no change to it), the registry's agent count when it reads agents, and its settings."""
        inputs = self.FOLD_INPUTS.get(name)
        if inputs is None:
            key: Any = self.house.ledger.head()[0]
        else:
            kinds, agents, dials = inputs
            newest = self.house.ledger.read(kinds=kinds, limit=1, newest=True)
            settings = self.settings if dials else {}
            key = (newest[-1].seq if newest else 0, len(self.house.registry.agents) if agents else None,
                   tuple(settings.get(dial) for dial in dials))
        hit = self._memo.get(name)
        if hit is not None and hit[0] == key:
            return hit[1]
        value = build()
        self._memo[name] = (key, value)
        return value

    # ------------------------------------------------------------------ dials
    @property
    def settings(self) -> dict[str, Any]:
        own = (self.house.game.get("hypotheses") or {}) if isinstance(self.house.game, Mapping) else {}
        return {**DEFAULTS, **{k: v for k, v in own.items() if not k.startswith("_")}}

    @property
    def frontier(self) -> Any:
        return self._frontier if self._frontier is not None else getattr(self.house, "frontier", None)

    def enabled(self) -> bool:
        return bool(self.settings.get("enabled"))

    def replaces_refill(self) -> bool:
        return bool(self.settings.get("enabled")) and bool(self.settings.get("replace_mutation_refill"))

    def _state(self) -> dict[str, Any]:
        with self.house._state_lock:
            return self.house._state.setdefault("hypotheses", {})

    def _now(self) -> float:
        return float(self.house.clock())

    # ------------------------------------------------------------------ folds
    def cards(self) -> dict[str, dict[str, Any]]:
        """Every card, by id, as first written (a card is written once). Code stays on the ledger
        row (`_code`, private) and is read back only when a card is replayed or born."""
        def build():
            out: dict[str, dict[str, Any]] = {}
            for entry in self.house.ledger.iter(kinds="hypothesis.card"):
                p = entry.payload
                if p.get("id") and p["id"] not in out:
                    out[p["id"]] = {**{k: v for k, v in p.items() if k != "_code"}, "_seq": entry.seq, "_at": entry.at}
            return out
        return self._folded("cards", build)

    def evaluations(self) -> dict[str, dict[str, Any]]:
        """The latest evaluation outcome of each card (`trace.record` task hypothesis.evaluate)."""
        def build():
            out: dict[str, dict[str, Any]] = {}
            for entry in self.house.ledger.iter(kinds="trace.record"):
                p = entry.payload
                if p.get("task") == TASK_EVALUATE and p.get("id"):
                    out[p["id"]] = {**p, "_seq": entry.seq, "_at": entry.at}
            return out
        return self._folded("evaluations", build)

    def born(self) -> dict[str, Agent]:
        """Card id -> the agent born from it (its `founder` is `card:<id>`, or the strategy's own name
        for a merged corrected child admitted through `takes_strategy`)."""
        by_strategy = {name: card["id"] for name, card in self.strategy_cards().items()}
        out = {}
        for a in list(self.house.registry.agents.values()):  # a copy: births land from other threads (the review of #297)
            founder = str(a.founder or "")
            if founder.startswith("card:"):
                out[founder[5:]] = a
            elif founder in by_strategy:
                out[by_strategy[founder]] = a
        return out

    def strategy_cards(self) -> dict[str, dict[str, Any]]:
        """Strategy name -> the latest card written for a merged strategy file (`takes_strategy`)."""
        out: dict[str, dict[str, Any]] = {}
        for card in sorted(self.cards().values(), key=lambda c: c["_seq"]):
            if card.get("strategy"):
                out[str(card["strategy"])] = card
        return out

    def takes_strategy(self, row: Mapping[str, Any]) -> bool:
        """Admit a merged corrected child (a strategy row with a `repair`) the way a card is admitted:
        replayed under its own line BEFORE any seat, born only on a pass (`_admit`), with the
        strategy's own name as its founder so `House.enroll` (which counts founders) and the
        engineer's `_child_born` see it exactly as before.

        Why (measured Sept 23, 2026): `House.enroll` gave the engineer's corrected children a seat
        at once, displacing the defective parent or the weakest resident, and `_retire_superseded`
        then killed every agent on the old code -- before the child had passed replay. 16 were born,
        9 passed, 7 died on rung 0 with 0 forward blocks; $0.70 a child. Now the seat is conditional
        on the replay pass, and a child that fails never takes one.

        Returns True when the foundry owns this strategy's admission (the card exists for this file
        version: pending, judged or born), False when it cannot take it (no literal NEEDS, no desk
        matches, the desk has no replay) so `enroll` keeps its own path."""
        from . import niches as niches_module
        from .safety import CodeRefused, check_code

        name, code = str(row.get("name") or ""), str(row.get("code") or "")
        if not name or not code.strip() or not isinstance(row.get("repair"), Mapping):
            return False
        sha = hashlib.sha256(code.encode("utf-8")).hexdigest()
        existing = self.strategy_cards().get(name)
        if existing is not None:
            return existing.get("code_sha256") == sha  # a new file version is a new admission
        declared = static_needs(code)
        if declared is None:
            return False
        try:
            home = niches_module.match(declared, self.house.niches)
        except Exception:  # noqa: BLE001 - an odd literal is the House's probe to judge
            return False
        if home is None or home.dormant or not home.replay:
            return False
        repair = dict(row["repair"])
        mechanism = f"{name} ({sha[:12]}): {str(row.get('why') or '')[:1500]}"
        ident = card_id(mechanism, home.id)
        if ident in self.cards():
            return False
        desk = home.desk or home.id.split("-", 1)[-1]
        line = f"{desk}-r{ident[:6]}"[:34]
        payload = {
            "id": ident, "mechanism": mechanism[:2000], "data": [], "edge_after_costs": "", "horizon": "",
            "rejection": "the House's replay gate, before any seat", "niche": home.id, "venue": home.venue,
            "author": "engineer", "lineage": [line], "parent_card": None, "created_for": f"repair:{name}",
            "name": name[:20], "line_id": line, "family": str(row.get("family") or name)[:40], "created_epoch": self._now(),
            "model": None, "prompt_version": PROMPT_VERSION, "transfer": None,
            "strategy": name, "repair": {k: repair.get(k) for k in ("key", "parent") if repair.get(k) is not None},
            "code_sha256": sha, "_code": code,
        }
        self.house.ledger.append("hypothesis.card", payload, id=f"hypothesis.card:{ident}")
        try:
            check_code(code)
        except (CodeRefused, SyntaxError) as exc:
            self._outcome(payload, "invalid", f"the strategy check refused it: {str(exc)[:200]}")
        return True

    def calls(self) -> list[dict[str, Any]]:
        return self._folded("calls", lambda: [dict(e.payload, _at=e.at) for e in self.house.ledger.iter(kinds="merton.pass")
                                              if e.payload.get("role") == ROLE])

    def links(self) -> dict[str, set[str]]:
        """Rewording groups from `hypothesis.link` (Jev or exact), above the confidence dial. Used
        ONLY to share failure history for retirement; never for genealogy or trial counts."""
        floor = float(self.settings["link_min_confidence"])
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            while parent.setdefault(x, x) != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for entry in self.house.ledger.iter(kinds="hypothesis.link"):
            p = entry.payload
            try:
                confident = p.get("method") == "exact" or float(p.get("confidence") or 0) >= floor
            except (TypeError, ValueError):
                confident = False
            if p.get("relation") == "rewording" and confident and p.get("a") and p.get("b"):
                parent[find(str(p["a"]))] = find(str(p["b"]))
        groups: dict[str, set[str]] = {}
        for key in list(parent):
            groups.setdefault(find(key), set()).add(key)
        return {member: group for group in groups.values() for member in group}

    def retired(self) -> dict[str, dict[str, Any]]:
        """Retired ids (`family:<family>`, `line:<line>` or a card id) that still stand. A later
        pass in that family lifts any retirement; a verified repair of its key lifts a blocked one."""
        return self._folded("retired", self._retired)

    def _retired(self) -> dict[str, dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for entry in self.house.ledger.iter(kinds="hypothesis.retired"):
            rows[str(entry.payload.get("id"))] = {**entry.payload, "_seq": entry.seq}
        if not rows:
            return {}
        verified = {}
        for entry in self.house.ledger.iter(kinds="repair.status"):
            if entry.payload.get("state") == "verified":
                verified[str(entry.payload.get("key"))] = entry.seq
        passes: dict[str, int] = {}
        for entry in self.house.ledger.iter(kinds="eval.trial"):
            if entry.payload.get("passed"):
                passes[str(entry.payload.get("family"))] = entry.seq
        out = {}
        for key, row in rows.items():
            family = key[7:] if key.startswith("family:") else None
            if family is not None and passes.get(family, 0) > row["_seq"]:
                continue
            repair = ((row.get("evidence") or {}).get("repair_key") if isinstance(row.get("evidence"), dict) else None)
            if row.get("reason") != "disproven" and repair and verified.get(repair, 0) > row["_seq"]:
                continue
            out[key] = row
        return out

    def _retired_niche(self, key: str, row: Mapping[str, Any]) -> str | None:
        """The desk a retirement belongs to, whoever wrote it. The v0 refill guard writes
        `line:<line>` with a text `evidence`; this module writes `family:<family>` or a card id with
        a dict that names the niche."""
        evidence = row.get("evidence")
        if isinstance(evidence, dict) and evidence.get("niche"):
            return str(evidence["niche"])
        kind, _, name = key.partition(":")
        for agent in list(self.house.registry.agents.values()):
            if (kind == "line" and (agent.line or agent.name) == name) or (kind == "family" and agent.family == name):
                return agent.specialty
        return (self.cards().get(key) or {}).get("niche")

    def _is_retired(self, agent: Agent, retired: Mapping[str, Any]) -> bool:
        """A family retired here, or a line retired by the House's own refill guard."""
        return f"family:{agent.family}" in retired or f"line:{agent.line or agent.name}" in retired

    def _retired_mechanisms(self, retired: Mapping[str, Any]) -> set[str]:
        """Mechanism ids the Jev hypothesis memory would give the strategies of retired families and
        lines (`league/hypothesis_memory.py`, when it is installed), so that a card linked to one of
        them as a rewording is not replayed. Without that module this is empty: exact card ids and
        card-to-card links still apply."""
        try:
            from .hypothesis_memory import docstring, mechanism_id  # type: ignore[attr-defined]
        except ImportError:
            return set()
        out = set()
        for agent in list(self.house.registry.agents.values()):
            if self._is_retired(agent, retired):
                text = docstring(agent.code)
                if text:
                    out.add(mechanism_id(text, agent.specialty))
        return out

    # --------------------------------------------------------------- evidence
    def _niche_of_agent(self, agent_id: str, cards_by_line: Mapping[str, str]) -> str | None:
        agent = self.house.registry.get(agent_id)
        if agent is not None:
            return agent.specialty
        return cards_by_line.get(agent_id)

    def desk_scores(self, *, fresh: bool = False) -> list[DeskScore]:
        """Opportunity by evidence, best first. Cached for five minutes (standings are not free)."""
        now = self._now()
        if not fresh and self._scores is not None and now - self._scores[0] < 300:
            return self._scores[1]
        house = self.house
        settings = self.settings
        since = now_iso(lambda: now - float(settings["evidence_days"]) * 86400)
        cards = self.cards()
        by_line = {c.get("line_id"): c.get("niche") for c in cards.values() if c.get("line_id")}
        trials: dict[str, list[int]] = {}
        empty: dict[str, int] = {}
        for entry in house.ledger.iter(kinds="eval.trial"):
            if entry.at < since:
                continue
            niche = self._niche_of_agent(entry.agent, by_line)
            if not niche:
                continue
            row = trials.setdefault(niche, [0, 0])
            row[0] += 1
            row[1] += bool(entry.payload.get("passed"))
            if not entry.payload.get("passed") and int(entry.payload.get("blocks") or 0) == 0:
                empty[niche] = empty.get(niche, 0) + 1
        blocked: dict[str, int] = {}
        attempts: dict[str, int] = {}
        for card, outcome in self.evaluations().items():
            niche = (cards.get(card) or {}).get("niche")
            if not niche or outcome.get("_at", "") < since:
                continue
            attempts[niche] = attempts.get(niche, 0) + 1
            if outcome.get("outcome") in ("blocked_data", "blocked_infra"):
                blocked[niche] = blocked.get(niche, 0) + 1
        total_trials = sum(t[0] for t in trials.values())
        total_passes = sum(t[1] for t in trials.values())
        league_rate = (total_passes + 1) / (total_trials + 15)  # 6.5% measured; a fresh ledger starts near it
        standings = [s for s in house.standings()]
        earning: dict[str, int] = {}
        record: dict[str, int] = {}
        for s in standings:
            agent = house.registry.get(s.agent)
            if agent is None or not agent.specialty:
                continue
            if s.score_observations > 0:
                record[agent.specialty] = record.get(agent.specialty, 0) + 1
                if s.score_growth > 0:
                    earning[agent.specialty] = earning.get(agent.specialty, 0) + 1
        league_forward = (sum(earning.values()) + 1) / (sum(record.values()) + 2)
        living = house.registry.living()
        members: dict[str, int] = {}
        for a in living:
            if a.specialty:
                members[a.specialty] = members.get(a.specialty, 0) + 1
        cards_per_desk: dict[str, int] = {}
        for c in cards.values():
            if c.get("_at", "") >= since:
                cards_per_desk[c.get("niche")] = cards_per_desk.get(c.get("niche"), 0) + 1
        weight = float(settings["prior_weight"])
        out = []
        for niche in house.niches.values():
            t, p = trials.get(niche.id, [0, 0])
            replay_rate = (p + weight * league_rate) / (t + weight)
            n, e = record.get(niche.id, 0), earning.get(niche.id, 0)
            forward = (e + 3 * league_forward) / (n + 3)
            tried = t + attempts.get(niche.id, 0)
            bad = empty.get(niche.id, 0) + blocked.get(niche.id, 0)
            availability = (tried - bad + 1) / (tried + 1)
            seats = max(niche.max_members - members.get(niche.id, 0), 0)
            eligible = not niche.dormant and bool(niche.replay)
            score = availability * replay_rate * (0.5 + forward) if eligible else 0.0
            why = (f"replay {p}/{t} (shrunk {replay_rate:.3f}), forward earning {e}/{n} (shrunk {forward:.2f}), "
                   f"inputs present {availability:.2f}")
            if niche.dormant:
                why = "dormant: " + (niche.dormant_reason or "closed")
            elif not niche.replay:
                why = "no historical replay: the foundry cannot admit by replay here (paper is its test)"
            out.append(DeskScore(niche.id, round(score, 6), round(replay_rate, 6), round(forward, 6), round(availability, 6),
                                 t, p, e, n, cards_per_desk.get(niche.id, 0), seats, eligible, why))
        out.sort(key=lambda d: (d.eligible, d.score, -d.cards), reverse=True)
        self._scores = (now, out)
        return out

    # ------------------------------------------------------ forward evidence
    def desk_forward(self) -> dict[str, dict[str, Any]]:
        """The forward ledger of the foundry's own children, per desk: the pooled log growth of every
        card-born agent's active `eval.block` rows (dead or alive), by desk and by family, and whether
        the desk's fast lane is `closed`.

        Why (measured Sept 23, 2026, the learn-and-unblock study): the foundry was the only paid
        source to reach real money ($0.26 a replay pass, 2 of 9 rung-2 agents ever), and also the
        practice loss engine: its Kalshi crypto cards were -$272.96 of the -$361 shadow loss since
        Sept 22 13:30Z, two BTC-strike cards -$113.68 in one day, `kalshi-crypto-strikes` -10.3% a
        block (40 born, 2 replay passes ever), `kalshi-crypto-15m` -1.9% a block on taker entries.
        A desk is closed to the fast lane once its foundry-born agents are negative over
        `fast_lane_min_blocks` active blocks, until one family there is positive over
        `fast_lane_reopen_blocks` active blocks; the calls go to the open fast desks by yield."""
        def build():
            house = self.house
            children = {a.id: a for a in list(house.registry.agents.values()) if str(a.founder or "").startswith("card:") and a.specialty}
            desks: dict[str, dict[str, Any]] = {}
            for entry in house.ledger.iter(kinds="eval.block"):
                agent = children.get(entry.agent)
                if agent is None or not entry.payload.get("active"):
                    continue
                try:
                    growth = float(entry.payload.get("log_growth") or 0.0)
                except (TypeError, ValueError):
                    continue
                row = desks.setdefault(agent.specialty, {"blocks": 0, "growth": 0.0, "agents": set(), "families": {}})
                row["blocks"] += 1
                row["growth"] += growth
                row["agents"].add(agent.id)
                family = row["families"].setdefault(agent.family, {"blocks": 0, "growth": 0.0})
                family["blocks"] += 1
                family["growth"] += growth
            floor = int(self.settings["fast_lane_min_blocks"])
            reopen = int(self.settings["fast_lane_reopen_blocks"])
            out = {}
            for desk, row in desks.items():
                positive = [f for f, r in row["families"].items() if r["blocks"] >= reopen and r["growth"] > 0]
                closed = row["blocks"] >= floor and row["growth"] < 0 and not positive
                out[desk] = {"blocks": row["blocks"], "growth": round(row["growth"], 6),
                             "per_block": round(row["growth"] / row["blocks"], 6) if row["blocks"] else 0.0,
                             "agents": len(row["agents"]), "measured": row["blocks"] >= floor, "closed": closed,
                             "positive_families": sorted(positive),
                             "families": {f: {"blocks": r["blocks"], "growth": round(r["growth"], 6)} for f, r in sorted(row["families"].items())}}
            return out
        return self._folded("desk_forward", build)

    def forward_families(self) -> list[dict[str, Any]]:
        """Every family with an earned forward record on a desk, best evidence first: a living member
        whose House standing has `score_observations > 0` and `score_growth > 0`. One row per family
        AND desk, since a family can live on more than one desk and a transfer comes from the desk
        where it earns. Real money first (an earning member on rung 2 or above), then by earned
        observations, then by growth per block. Cached for five minutes with the edge map."""
        return self._edge_fold()["families"]

    def winning_mechanisms(self) -> dict[str, Any]:
        """The league's edge map, in every packet (Sept 23, 2026: the packet showed only this desk's
        forward results, so a mechanism that earned real money on one desk was never offered to
        another): the top eight forward records and the families that died on the forward evidence."""
        fold = self._edge_fold()
        keys = ("family", "desk", "venue", "horizon", "members", "with_a_record", "earning", "best_rung", "real_money",
                "record_on", "observations", "growth_per_block")
        out: dict[str, Any] = {
            "earning": [{**{k: row[k] for k in keys}, "mechanism": row["mechanism"][:500]} for row in fold["families"][:8]],
            "failed_forward": fold["failed"],
            "note": ("A forward record is the House's own standing of a living agent: earned observations (a finished "
                     "day counts as the paper screen counts it) and after-cost log growth, here per block of the family's "
                     "horizon. real_money: an earning member trades real money now; record_on: whether the record itself was "
                     "earned on real money or on paper. Mechanisms are in words -- a card's mechanism, a founding seed's why, "
                     "the purpose a program was born with -- never code."),
        }
        if fold.get("error"):
            out["error"] = fold["error"]
        return out

    def _edge_fold(self, *, fresh: bool = False) -> dict[str, Any]:
        now = self._now()
        if not fresh and self._edge is not None and now - self._edge[0] < 300:
            return self._edge[1]
        try:
            fold = self._build_edge()
        except Exception as exc:  # noqa: BLE001 - the House's tick asks for an allocation: no transfer beats no tick
            fold = {"families": [], "failed": [], "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
        self._edge = (now, fold)
        return fold

    def _build_edge(self) -> dict[str, Any]:
        house = self.house
        groups: dict[tuple[str, str], list[tuple[Agent, Any]]] = {}
        for s in house.standings():
            agent = house.registry.get(s.agent)
            if agent is not None and agent.specialty in house.niches:
                groups.setdefault((agent.family, agent.specialty), []).append((agent, s))
        families = []
        for (family, desk), members in groups.items():
            earning = [(a, s) for a, s in members if s.score_observations > 0 and s.score_growth > 0]
            if not earning:
                continue
            observations = sum(int(s.score_observations) for _, s in earning)
            # `score_growth` is the reward rate, log growth per HOUR (House._reward_evidence); a block of
            # a daily program is 24 of them.
            per_block = sum(float(s.score_growth) * (24 if a.horizon == "day" else 1) * int(s.score_observations)
                            for a, s in earning) / observations
            ranked = sorted(earning, key=lambda pair: (-pair[1].rung, -pair[1].score_observations * pair[1].score_growth, pair[0].id))
            lead = ranked[0][0]
            words, origin = self._mechanism(lead)
            families.append({
                "family": family, "desk": desk, "venue": house.niches[desk].venue, "horizon": lead.horizon,
                "members": len(members), "rungs": sorted((int(s.rung) for _, s in members), reverse=True),
                "with_a_record": sum(1 for _, s in members if s.score_observations > 0), "earning": len(earning),
                "agents": [a.id for a, _ in ranked][:4], "best_rung": max(int(s.rung) for _, s in earning),
                "real_money": any(s.rung >= 2 for _, s in earning),
                "record_on": "real money" if any(s.score_rung >= 2 for _, s in earning) else "paper",
                "observations": observations, "growth_per_block": round(per_block, 6),
                "mechanism": words[:1500], "mechanism_from": origin,
            })
        families.sort(key=lambda r: (not r["real_money"], -r["observations"], -r["growth_per_block"], r["family"], r["desk"]))
        return {"families": families, "failed": self._failed_forward(), "error": None}

    def _failed_forward(self, limit: int = 10) -> list[str]:
        """One line per family and desk whose agents died on the forward evidence (the House's `evidence`
        death: a paper or real-money verdict, never replay, credits or displacement), most deaths first."""
        house = self.house
        rungs: dict[str, int] = {}
        for entry in house.ledger.iter(kinds="agent.postmortem"):
            if entry.payload.get("cause") == "evidence":
                found = re.search(r" died on rung (\d+) of evidence", str(entry.payload.get("text") or ""))
                if found:
                    rungs[entry.agent] = int(found.group(1))
        groups: dict[tuple[str, str], dict[str, Any]] = {}
        for entry in house.ledger.iter(kinds="agent.died"):
            agent = house.registry.get(entry.agent)
            if entry.payload.get("cause") != "evidence" or agent is None or not agent.specialty:
                continue
            row = groups.setdefault((agent.family, agent.specialty), {"deaths": 0, "rungs": set()})
            row["deaths"] += 1
            row["rungs"].add(rungs.get(agent.id, 1))
            row.update(at=entry.at, detail=str(entry.payload.get("detail") or ""), agent=agent)
        lines = []
        for (family, desk), row in sorted(groups.items(), key=lambda kv: (kv[1]["deaths"], kv[1]["at"]), reverse=True)[:limit]:
            where = " and ".join(name for name, hit in (("paper", 1 in row["rungs"]), ("real money", max(row["rungs"]) >= 2)) if hit)
            words = self._mechanism(row["agent"])[0]
            lines.append(f"{family} on {desk}: {row['deaths']} died on the forward evidence on {where}, the last on "
                         f"{row['at'][:10]} ({row['detail'][:140] or 'no reason recorded'})"
                         + (f"; mechanism: {words[:160]}" if words else ""))
        return lines

    def _mechanism(self, agent: Agent) -> tuple[str, str]:
        """(words, where they came from): what an agent's program does, stated where that program was
        written -- its card's `mechanism`, the purpose it was adopted or born with (an architect's why,
        a research candidate's purpose), its founding seed's `why` -- walking up past parameter
        mutations, which run their parent's program. Never the code."""
        house = self.house
        seeds = {f.get("key"): f.get("seed") for niche in house.niches.values() for f in niche.founders}
        current, seen = agent, set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            founder = str(current.founder or "")
            if founder.startswith("card:"):
                card = self.cards().get(founder[5:]) or {}
                if card.get("mechanism"):
                    return str(card["mechanism"]), f"hypothesis card {founder[5:]}"
            adopted = house.ledger.last("agent.strategy", agent=current.id)
            if adopted is not None and str(adopted.payload.get("reason") or "").strip():
                return str(adopted.payload["reason"]).strip(), f"the strategy {current.id} adopted"
            seed = seeds.get(founder) if current.parent is None else None
            if seed and SEED_WHY.get(seed):
                return SEED_WHY[seed], f"founding seed {seed}"
            parent = house.registry.get(current.parent) if current.parent else None
            if parent is None or parent.code_sha256 != current.code_sha256:
                born = house.ledger.get(f"born:{current.id}")
                reason = str((born.payload if born is not None else {}).get("reason") or "").strip()
                if reason and not reason.startswith(_MUTATION_REASONS):
                    return reason, f"the birth of {current.id}"
            current = parent
        return "", "not recorded"

    def _seat_available(self, desk: DeskScore, weakest: dict[str | None, bool]) -> bool:
        rules = self.house.game["economy"]
        if desk.open_seats > 0 and len(self.house.registry.living()) < int(rules["max_population"]):
            return True
        # A full desk or league seats a replay passer only over its weakest eligible resident.
        # (`weakest` memoizes `_weakest` per specialty within one allocation: it reads standings.)
        key = None if desk.open_seats > 0 else desk.niche
        if key not in weakest:
            weakest[key] = self.house._weakest(rules, specialty=key) is not None
        return weakest[key]

    def allocate(self, *, fresh: bool = False) -> tuple[DeskScore, str, str] | None:
        """(desk, route, reason) for the next foundry call, or None when no desk can take a newcomer.

        Four routes, offered the call in this order. The three bounded ones are counted over the
        same window, the last `exploration_window` calls, and each takes a call only while its own
        calls stay within its share of that window. None can grow past its share, so while the
        shares add up to one or less each keeps its own (an earlier route only takes a call first),
        and one that is due but has no desk to offer passes the call on without using its turn.

        1. `transfer` (`transfer_share`): a family with an earned forward record (`forward_families`,
           real money first) goes to the best-scored desk of its venue where it has never been tried.
        2. `fast` (`fast_share`): of the `fast_desks` other than the evidence route's desk (which that
           route already serves), the one with the fewest recent cards, then the best score: a rotation,
           so every around-the-clock desk is written for. Until Sept 23, 2026 it was always the
           best-scored fast desk (the index-ETF desk), and it stopped altogether whenever the best desk
           was itself a fast desk.
        3. `exploration` (`exploration_share`): the eligible desk with the fewest recent cards, then the
           fewest trials, other than the best.
        4. `evidence`: the best-scored desk with a seat takes every call no bounded route is due for.

        Shares adding up to more than the whole window are scaled down in proportion (`shares`), so one
        large dial cannot silently take the turns of the routes after it. With game.json's 0.3, 0.5 and
        0.2 the window rule gives transfer, fast, exploration and evidence about 27%, 45%, 18% and 9% of
        calls (simulated over 2,000 calls with every route able to take its turn); the evidence route
        keeps the calls left when all three are at their share."""
        now = self._now()
        if not fresh and self._allocation is not None and now - self._allocation[0] < 300:
            return self._allocation[1]
        picked = self._allocate()
        self._allocation = (now, picked)
        return picked

    def _waiting_with_a_seat(self) -> bool:
        """Is a replay-passing card waiting for a seat its desk could give it now? Then the next
        refill seats it, and no new card is bought meanwhile. A card whose desk has no seat -- full
        of agents that have earned theirs -- does not hold up calls for other desks. Measured Sept
        22, 2026: one weather card passed replay at 15:50Z, the weather desk filled with young
        research candidates, and the foundry refused every call, for every desk, for two hours."""
        waiting = self.inventory()
        if not waiting:
            return False
        scores = {d.niche: d for d in self.desk_scores()}
        weakest: dict[str | None, bool] = {}
        return any(card.get("niche") in scores and self._seat_available(scores[card["niche"]], weakest) for card in waiting)

    def _allocate(self) -> tuple[DeskScore, str, str] | None:
        blocked = self._blocked_desks() | set(self._closed_desks())
        # A desk that already has a replay-passing card waiting gets no more cards until it is seated,
        # nor (when cards may queue for replay) one whose last cards are still awaiting replay.
        waiting = {card.get("niche") for card in self.inventory()}
        if int(self.settings.get("max_pending_cards") or 0) > 0:
            waiting |= {card.get("niche") for card in self.pending()}
        weakest: dict[str | None, bool] = {}
        desks = [d for d in self.desk_scores() if d.eligible and d.niche not in blocked and d.niche not in waiting
                 and self._seat_available(d, weakest)]
        if not desks:
            return None
        settings = self.settings
        window = [c.get("allocation") or {} for c in self.calls()[-int(settings["exploration_window"]):]]
        shares = self.shares()
        taken = {route: sum(1 for a in window if a.get("route") == route) for route in ROUTES}

        def due(route: str) -> bool:
            return shares[route] > 0 and (taken[route] + 1) / (len(window) + 1) <= shares[route] + 1e-9

        best = desks[0]
        if due("transfer"):
            picked = self._first_transfer_pick(desks) or self._transfer_pick(desks)
            if picked is not None:
                source, pick = picked
                if source.get("scale"):
                    return pick, "transfer", (
                        f"transfer share: {taken['transfer']} of the last {len(window)} calls ported a proven mechanism; "
                        f"the first transfer to try scales {source['family']} on {pick.niche} on a fair value "
                        f"({', '.join(source.get('feeds') or []) or 'the recorded feeds'}): {str(source.get('ask') or '')[:200]}")
                return pick, "transfer", (
                    f"transfer share: {taken['transfer']} of the last {len(window)} calls ported a proven mechanism; "
                    f"{source['family']} earns forward on {source['desk']} ({source['earning']} of {source['members']} "
                    f"members earning, {source['observations']} observations, {source['growth_per_block']:+.5f} a "
                    f"{source['horizon']} block, {'on real money' if source['real_money'] else 'on paper'}) and has never "
                    f"been tried on {pick.niche}, the best-scored untried {source['venue']} desk ({pick.score:.4f})")
        fast_desks = set(settings.get("fast_desks") or [])
        forward = self.desk_forward()
        closed = {desk for desk, row in forward.items() if row["closed"]}
        fast = [d for d in desks if d.niche in fast_desks and d.niche != best.niche and d.niche not in closed]
        if fast and due("fast"):
            recent = self._recent_cards()
            # Sept 23, 2026: the measured forward yield of the desk's own foundry children first (an
            # unmeasured desk counts as zero), then the rotation by fewest recent cards, then score.
            yield_of = lambda d: forward.get(d.niche, {}).get("per_block", 0.0) if forward.get(d.niche, {}).get("measured") else 0.0  # noqa: E731
            pick = min(fast, key=lambda d: (-yield_of(d), recent.get(d.niche, 0), -d.score, d.niche))
            shut = ", ".join(f"{desk} {forward[desk]['per_block']:+.4f} a block over {forward[desk]['blocks']}" for desk in sorted(closed & fast_desks))
            return pick, "fast", (f"fast-evidence share: {taken['fast']} of the last {len(window)} calls went to hourly, "
                                  f"around-the-clock desks; {pick.niche} has the best forward yield of its foundry children "
                                  f"({yield_of(pick):+.4f} a block over {forward.get(pick.niche, {}).get('blocks', 0)}) and the "
                                  f"fewest recent cards ({recent.get(pick.niche, 0)}) of the open fast desks, score {pick.score:.4f}: {pick.why}"
                                  + (f"; closed to the fast lane on forward losses: {shut}" if shut else ""))
        if due("exploration"):
            others = [d for d in desks if d.niche != best.niche] or desks
            pick = min(others, key=lambda d: (d.cards, d.trials, d.niche))
            return pick, "exploration", (f"exploration share: {taken['exploration']} of the last {len(window)} calls explored; "
                                         f"{pick.niche} has {pick.cards} recent cards and {pick.trials} trials")
        return best, "evidence", f"highest evidence score {best.score:.4f}: {best.why}"

    def shares(self) -> dict[str, float]:
        """The bounded routes' shares of the call window. Shares adding up to more than one are scaled
        down in proportion: taken in order at face value, the first dials would leave the later routes
        nothing (the House's game designer may move these dials; they have no bounds)."""
        settings = self.settings
        shares = {route: min(max(float(settings.get(f"{route}_share") or 0), 0.0), 1.0) for route in ROUTES}
        total = sum(shares.values())
        return {route: share / total for route, share in shares.items()} if total > 1 else shares

    def _recent_cards(self) -> dict[str, int]:
        """Cards written for each desk inside the evidence window, read from the ledger as it stands
        (the desk scores are five minutes old), a call that wrote no card counting as one: a desk whose
        calls keep failing must not keep the fast route's turn."""
        since = now_iso(lambda: self._now() - float(self.settings["evidence_days"]) * 86400)
        out: dict[str, int] = {}
        for card in self.cards().values():
            if card.get("niche") and card.get("_at", "") >= since:
                out[card["niche"]] = out.get(card["niche"], 0) + 1
        for call in self.calls():
            desk = (call.get("allocation") or {}).get("desk")
            if desk and not call.get("cards") and call.get("_at", "") >= since:
                out[desk] = out.get(desk, 0) + 1
        return out

    # ---------------------------------------------------------------- transfer
    def _tried(self) -> dict[str, set[str]]:
        """Family -> the desks where it has been tried: every desk an agent of it ever lived on, and
        every desk a transfer of it was already written for (a transfer call that returned, whatever
        it wrote, and any card that call wrote). A call that failed before Merton answered tried nothing."""
        def build():
            out: dict[str, set[str]] = {}
            for agent in list(self.house.registry.agents.values()):
                if agent.specialty:
                    out.setdefault(agent.family, set()).add(agent.specialty)
            for call in self.calls():
                allocation = call.get("allocation") or {}
                source = allocation.get("transfer") or {}
                if allocation.get("route") == "transfer" and source.get("family") and allocation.get("desk") and not call.get("error"):
                    out.setdefault(str(source["family"]), set()).add(str(allocation["desk"]))
            for card in self.cards().values():
                source = card.get("transfer") or {}
                if source.get("family") and card.get("niche"):
                    out.setdefault(str(source["family"]), set()).add(str(card["niche"]))
            return out
        return self._folded("tried", build)

    def _transfer_pick(self, desks: Sequence[DeskScore]) -> tuple[dict[str, Any], DeskScore] | None:
        """(source, desk): the best forward record (`forward_families` order) that has an eligible
        desk of its own venue where its family was never tried, and the best-scored such desk."""
        tried = self._tried()
        for source in self.forward_families():
            home = tried.get(source["family"], set())
            pick = next((d for d in desks if d.niche not in home and self.house.niches[d.niche].venue == source["venue"]), None)
            if pick is not None:
                return source, pick
        return None

    def transfer_for(self, niche_id: str) -> dict[str, Any] | None:
        """The forward record a transfer call to this desk ports: the best one of the desk's venue whose
        family was never tried here. Given the same standings this is the source `_transfer_pick` chose
        for the desk (every better record has no untried eligible desk at all)."""
        niche = self.house.niches.get(niche_id)
        if niche is None:
            return None
        first = self._first_transfer()
        if first is not None and first["desk"] == niche_id:
            return first
        tried = self._tried()
        return next((source for source in self.forward_families()
                     if source["venue"] == niche.venue and niche_id not in tried.get(source["family"], set())), None)

    def _first_transfer_pick(self, desks: Sequence[DeskScore]) -> tuple[dict[str, Any], DeskScore] | None:
        """(source, desk) for `first_transfer` while it is due and its desk can take a newcomer."""
        first = self._first_transfer()
        if first is None:
            return None
        pick = next((d for d in desks if d.niche == first["desk"]), None)
        return (first, pick) if pick is not None else None

    def _first_transfer(self) -> dict[str, Any] | None:
        """`first_transfer` as a transfer source (E2 of the close-the-gaps run, Sept 24, 2026), until a call
        for it has returned: the family, on its own desk, `scale`d onto a fair value from the named feeds.

        The plan's first transfer: the weather favourites (resting bids on 0.90-0.97 daily weather
        favourites, the one family with real profit at T0: about $1.41 a day on its real seats, about $7.81
        a day at its measured capacity of 26.5 markets bid a day) bid a band of a few series; priced on the
        ensemble's fair value it can bid every Kalshi weather series (highs, lows, rain) wherever the model
        clears the ask and the fee. Its forward record comes from `forward_families` when it earns now, else
        from its members as the registry holds them (the family ledger, not an agent's luck, proves it)."""
        config = self.settings.get("first_transfer") or {}
        family, desk = str(config.get("family") or ""), str(config.get("desk") or "")
        niche = self.house.niches.get(desk)
        if not family or niche is None:
            return None
        for call in self.calls():
            ported = (call.get("allocation") or {}).get("transfer") or {}
            if ported.get("scale") and ported.get("family") == family and ported.get("desk") == desk and not call.get("error"):
                return None
        row = next((dict(r) for r in self.forward_families() if r["family"] == family and r["desk"] == desk), None)
        if row is None:
            members = sorted((a for a in list(self.house.registry.agents.values()) if a.family == family and a.specialty == desk),
                             key=lambda a: (not a.alive, a.id))
            if not members:
                return None
            words, origin = self._mechanism(members[0])
            rungs = sorted((self.house.evaluator.rung(a.id) for a in members if a.alive), reverse=True)
            row = {"family": family, "desk": desk, "venue": niche.venue, "horizon": members[0].horizon, "members": len(members),
                   "rungs": rungs, "with_a_record": 0, "earning": 0, "agents": [a.id for a in members][:4],
                   "best_rung": rungs[0] if rungs else 0, "real_money": any(r >= 2 for r in rungs), "record_on": "no earned record now",
                   "observations": 0, "growth_per_block": 0.0, "mechanism": words, "mechanism_from": origin}
        return {**row, "scale": True, "ask": str(config.get("mechanism") or ""), "feeds": [str(f) for f in config.get("feeds") or []]}

    def _closed_desks(self) -> dict[str, str]:
        """Desks that get no card on any route (E2 of the close-the-gaps run, Sept 24, 2026), with why: each of
        `closed_desks` until a family there -- of any agent that lived on the desk -- shows a positive pooled
        forward record over `closed_reopen_blocks` active blocks ON THAT DESK (`_closed_desk_forward`). Measured
        at T0: every kalshi-crypto-15m family negative on its pooled record (crypto-15m-favorites n 106, bound
        -0.0064), and kalshi-crypto-strikes -10.3% an active block, 2 replay passes in 40 births."""
        closed = [str(d) for d in (self.settings.get("closed_desks") or [])]
        if not closed:
            return {}
        need = max(1, int(self.settings.get("closed_reopen_blocks") or 3))
        try:
            forward = self._closed_desk_forward(closed)
        except Exception:  # noqa: BLE001 - an unreadable record reopens nothing
            forward = {}
        out = {}
        for desk in closed:
            if not any(blocks >= need and growth > 0 for blocks, growth in (forward.get(desk) or {}).values()):
                out[desk] = f"no family on {desk} has a positive forward record over {need} active blocks there"
        return out

    def _closed_desk_forward(self, desks: Sequence[str]) -> dict[str, dict[str, tuple[int, float]]]:
        """Desk -> family -> (its distinct active forward blocks on that desk, their summed log growth), from the
        `eval.block` rows of the family's members that lived on the desk, living or dead: one block a block key,
        however many members were active in it.

        The review of #262 (Sept 24, 2026): read from `House.family_forward`, which pools a family over every desk
        it lives on and counts each member's block, a closed desk reopened on a family's record elsewhere
        (kalshi-favorites lives on kalshi-crypto-strikes and kalshi-weather) or on one hour of siblings (three
        members of one family, active in the same hour, were three blocks: huang-hd8ff7c-3, -4 and -5 at
        2026-09-24T04 on the T4 snapshot)."""
        ledger = self.house.ledger
        rows: dict[str, dict[str, list[Any]]] = {}
        for agent in list(self.house.registry.agents.values()):
            if agent.specialty not in desks or not agent.family:
                continue
            row = rows.setdefault(agent.specialty, {}).setdefault(agent.family, [set(), 0.0])
            for entry in ledger.iter(kinds="eval.block", agent=agent.id):
                p = entry.payload
                if not p.get("active"):
                    continue
                row[0].add(str(p.get("key") or entry.id))  # a row with no block key is a block of its own
                row[1] += float(p.get("log_growth") or 0.0)
        return {desk: {family: (len(keys), growth) for family, (keys, growth) in families.items()} for desk, families in rows.items()}

    def _blocked_desks(self) -> set[str]:
        """Desks with an open foundry repair report: no more cards until it is verified."""
        return self._folded("blocked", self._blocked)

    def _blocked(self) -> set[str]:
        reported = {}
        for entry in self.house.ledger.iter(kinds="repair.reported"):
            key = str(entry.payload.get("key") or "")
            if key.startswith("shared_defect:hypothesis-replay:") or key.startswith("missing_data:hypothesis-replay:"):
                reported[key] = entry.seq
        if not reported:
            return set()
        verified = {str(e.payload.get("key")): e.seq for e in self.house.ledger.iter(kinds="repair.status")
                    if e.payload.get("state") in ("verified", "rejected")}
        # A report nobody works on must not close a desk for good: after `blocked_hours` the
        # foundry may try it again, and a fresh failure reports it again.
        since = now_iso(lambda: self._now() - float(self.settings["blocked_hours"]) * 3600)
        fresh = {str(e.payload.get("key")) for e in self.house.ledger.iter(kinds="repair.reported") if e.at >= since}
        return {key.rsplit(":", 1)[1] for key, seq in reported.items() if verified.get(key, 0) < seq and key in fresh}

    # ----------------------------------------------------------------- cadence
    def spent(self) -> Decimal:
        """What the foundry has spent in its budget window (its own `merton.pass` rows)."""
        hours = float(self.settings["budget_window_hours"])
        since = now_iso(lambda: self._now() - hours * 3600)
        total = Decimal(0)
        for call in self.calls():
            if call["_at"] >= since:
                try:
                    total += Decimal(str(call.get("cost_usd") or 0))
                except ArithmeticError:
                    continue
        return total

    def last_call(self) -> float:
        """The last call's time, from the ledger and the state file (whichever is later), so neither
        a lost `house.json` nor a restart can start a paid call early."""
        calls = self.calls()
        return max(float(self._state().get("last_call") or 0), float(calls[-1].get("at_epoch") or 0) if calls else 0.0)

    def inventory(self) -> list[dict[str, Any]]:
        """Replay-passing cards waiting for a seat."""
        born = self.born()
        cards = self.cards()
        return [cards[c] for c, row in self.evaluations().items()
                if row.get("outcome") == "passed" and c in cards and c not in born]

    def pending(self) -> list[dict[str, Any]]:
        """Cards written but not yet evaluated (a restart re-queues them), inside their TTL."""
        done = self.evaluations()
        ttl = float(self.settings["card_ttl_hours"]) * 3600
        now = self._now()
        out = []
        for card in self.cards().values():
            if card["id"] in done:
                continue
            if now - float(card.get("created_epoch") or 0) > ttl:
                continue
            out.append(card)
        return out

    def _expire(self) -> None:
        """A card never evaluated within its TTL is closed as `expired`, not silently dropped."""
        done = self.evaluations()
        ttl = float(self.settings["card_ttl_hours"]) * 3600
        for card in self.cards().values():
            if card["id"] not in done and self._now() - float(card.get("created_epoch") or 0) > ttl:
                self._outcome(card, "expired", "not evaluated within its time to live")

    def due(self) -> bool:
        """Whether a paid foundry call may start now. `refusal` says why not."""
        house = self.house
        settings = self.settings
        reason = ""
        if not settings.get("enabled"):
            reason = "disabled in game.json"
        elif self.frontier is None:
            reason = "no frontier client"
        elif house.paused():
            reason = "maintenance pause"
        elif house.deploying():
            reason = "a release is being staged"
        elif self._now() - self.last_call() < float(settings["call_minutes"]) * 60:
            reason = "cadence: the last call is too recent"
        elif house.frontier_tier() not in ("all", "earned"):
            reason = f"frontier tier {house.frontier_tier()!r} pays for no code work"
        elif not house.pacer.may_spend("openai"):
            reason = "the day's OpenAI allowance is spent"
        elif self.spent() >= Decimal(str(settings["budget_usd"])):
            reason = f"the foundry's ${settings['budget_usd']} window budget is spent"
        elif self._waiting_with_a_seat():
            reason = "a replay-passing card is already waiting for a seat"
        elif self._evaluation_backlog():
            reason = "earlier cards are still being evaluated"
        elif (lambda job: job is not None and job.is_alive())(house._jobs.get("merton:foundry")):
            # Its own call only. Until Sept 23, 2026 any Merton pass (teacher, architect, engineer)
            # held up the foundry, though each role has its own lane and its own budget.
            reason = "the last foundry call is still running"
        elif self.allocate() is None:
            reason = "no seat is open on any eligible desk"
        self.refusal = reason
        return not reason

    def _evaluation_backlog(self) -> bool:
        """Too many cards still awaiting replay for another call. With `max_pending_cards` 0 any
        pending card (or a running card replay) holds the next call, as before Sept 23, 2026."""
        limit = int(self.settings.get("max_pending_cards") or 0)
        if limit <= 0:
            return bool(self.pending()) or any(k.startswith("replay:hypothesis:") and j.is_alive() for k, j in list(self.house._jobs.items()))
        return len(self.pending()) >= limit

    def tick(self, *, open_for_business: bool) -> None:
        """Called from `House.tick`. Unpaid bookkeeping always; paid work only when open."""
        state = self._state()
        now = self._now()
        try:
            self.annotate_births()
            self._expire()
            if now - float(state.get("last_retire") or 0) >= 600:
                self.retire_exhausted()
                with self.house._state_lock:
                    state["last_retire"] = now
            # Sept 23, 2026: the hourly yield row (league/yield_ledger.py) rides on this tick, the
            # one unpaid bookkeeping pass every House tick makes, until House.tick takes it directly.
            if self.yield_ledger is not None and self.yield_ledger.due():
                self.yield_ledger.tick()
        except Exception as exc:  # noqa: BLE001 - bookkeeping must never stop a tick
            self.house.alert("warning", f"hypothesis bookkeeping failed ({type(exc).__name__}: {str(exc)[:160]})")
        if not open_for_business or not self.enabled():
            return
        if not getattr(self.house, "campaigns", None) or self.house.pacer.may_spend("sail"):
            attempts = state.setdefault("attempts", {})
            ready = []
            busy = any(k.startswith("replay:hypothesis:") and j.is_alive() for k, j in list(self.house._jobs.items()))
            for card in [] if busy else self.pending():
                count, last = attempts.get(card["id"], [0, 0])
                if now - float(last) < 600:
                    continue  # a card whose replay could not start waits ten minutes, not one tick
                if int(count) >= int(self.settings["max_evaluation_attempts"]):
                    self._outcome(card, "blocked_infra", f"its replay did not complete in {count} attempts")
                    continue
                ready.append((card["id"], int(count)))
            if ready and self.house._background("replay:hypothesis:pending", self.evaluate_all, [c for c, _ in ready]):
                with self.house._state_lock:
                    for ident, count in ready:
                        attempts[ident] = [count + 1, now]
        if self.due():
            picked = self.allocate()
            if picked is not None:
                with self.house._state_lock:
                    state["last_call"] = self._now()  # stamped at dispatch: a crash mid-call does not re-buy it at once
                self.house._background("merton:foundry", self.run, picked[0].niche, picked[1], picked[2])

    # ------------------------------------------------------------------ packet
    def packet(self, niche_id: str, *, transfer: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """What Merton is shown for one desk. Summaries of development replays only: no tape, no
        holdout, no other agent's code. `transfer`, on a transfer call, is the forward record being
        ported here (`transfer_for`): the packet then says what it is and what it earned, in words."""
        house = self.house
        niche = house.niches[niche_id]
        horizon = niche.horizons[0]
        probe = self._virtual(niche, "probe", {"venue": niche.venue, "horizon": horizon, "style": "probe",
                                              niche.key: list(niche.universe[:4])}, "", {}, family="probe")
        try:
            capabilities = house.research_capabilities(probe)
        except Exception as exc:  # noqa: BLE001 - the packet is still worth sending without it
            capabilities = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
        coverage = self._coverage(niche)
        retired = self.retired()
        cards = self.cards()
        evaluations = self.evaluations()
        families: dict[str, dict[str, Any]] = {}
        by_line = {c.get("line_id"): c.get("niche") for c in cards.values() if c.get("line_id")}
        for entry in house.ledger.iter(kinds="eval.trial"):
            if self._niche_of_agent(entry.agent, by_line) != niche_id:
                continue
            p = entry.payload
            row = families.setdefault(str(p.get("family")), {"family": p.get("family"), "trials": 0, "passes": 0, "reasons": {}})
            row["trials"] += 1
            row["passes"] += bool(p.get("passed"))
            for reason in (p.get("reasons") or [])[:3]:
                key = re.sub(r"[-+]?\d[\d.,]*", "#", str(reason))[:90]
                row["reasons"][key] = row["reasons"].get(key, 0) + 1
        seeds = {}
        for founder in niche.founders:
            # niches.json founders name a seed and carry no `why`: until Sept 23, 2026 every value here was "".
            seeds[founder.get("seed")] = founder.get("why") or SEED_WHY.get(str(founder.get("seed")), "")
        failed = []
        for row in sorted(families.values(), key=lambda r: -r["trials"]):
            if row["passes"]:
                continue
            failed.append({"family": row["family"], "trials": row["trials"],
                           "top_reasons": [k for k, _ in sorted(row["reasons"].items(), key=lambda kv: -kv[1])[:3]],
                           "retired": f"family:{row['family']}" in retired})
        for card in cards.values():
            outcome = evaluations.get(card["id"]) or {}
            if card.get("niche") == niche_id and outcome.get("outcome") not in (None, "passed"):
                failed.append({"card": card["id"], "name": card.get("name"), "mechanism": str(card.get("mechanism") or "")[:400],
                               "outcome": outcome.get("outcome"), "detail": str(outcome.get("detail") or "")[:240]})
        passed = [{"family": r["family"], "trials": r["trials"], "passes": r["passes"]} for r in families.values() if r["passes"]]
        deaths = [str(e.payload.get("text") or "")[:300] for e in house.ledger.read(kinds="agent.postmortem", limit=200, newest=True)
                  if (house.registry.get(e.agent) and house.registry.get(e.agent).specialty == niche_id)][-5:]
        desk_score = next((asdict(d) for d in self.desk_scores() if d.niche == niche_id), None)
        replay_days = (house.settings.kalshi_replay_days * 7 if horizon == "day" else house.settings.kalshi_replay_days) \
            if niche.venue == "kalshi" else (house.settings.replay_days * (6 if horizon == "day" else 1))
        row = CONSTITUTION["rungs"]["1"]
        ported = {} if transfer is None else {"transfer": {
            "family": transfer["family"], "from_desk": transfer["desk"], "venue": transfer["venue"], "horizon": transfer["horizon"],
            "forward_record": {k: transfer[k] for k in ("members", "rungs", "with_a_record", "earning", "observations",
                                                        "growth_per_block", "best_rung", "real_money", "record_on")},
            "earning_agents": list(transfer["agents"]),
            "mechanism": transfer["mechanism"], "mechanism_from": transfer["mechanism_from"],
            "never_tried_here": f"no agent of {transfer['family']} has lived on {niche_id}, and no transfer of it was written for it",
            "ask": ("Write at least half of the batch as adaptations of this mechanism to this desk's markets, data, fees and "
                    "horizons, each a distinct expression of it and a falsifiable card with its own rejection test."),
        }}
        if transfer is not None and transfer.get("scale"):
            # The first transfer to try (E2, Sept 24, 2026): the family widened on its own desk by a fair value.
            ported["transfer"].pop("never_tried_here")
            ported["transfer"].update(
                scale=True, feeds=list(transfer.get("feeds") or []),
                on_this_desk=f"{transfer['family']} trades here now, on the few markets its own band reaches",
                ask=(f"{transfer.get('ask') or 'Price every market of this desk it can reach from a fair value.'} Write at least half "
                     "of the batch as such cards, each a distinct model (other series, other data, other thresholds), each a "
                     "falsifiable card with its own rejection test, its fee and the edge it needs to clear it."))
        return {
            **ported,
            "batch": {"candidates": max(3, min(int(self.settings["candidates"]), 4)), "prompt_version": PROMPT_VERSION},
            "desk": {"id": niche.id, "title": niche.title, "venue": niche.venue, "horizons": list(niche.horizons),
                     "asset_class": niche.asset_class, "universe": list(niche.universe[:24]), "brief": niche.brief[:3000],
                     "maker_fee_series": list(niche.maker_fee_series), "evidence": desk_score},
            "data": {"replay": (capabilities.get("replay") if isinstance(capabilities, dict) else None),
                     "observations": (capabilities.get("observations") if isinstance(capabilities, dict) else None),
                     "not_supplied": ((capabilities.get("observations") or {}).get("not_supplied") if isinstance(capabilities, dict) else None),
                     "recorded_coverage": coverage,
                     "recorded_feeds": self._recorded_feeds(niche)},
            "fees": {"kalshi_taker": "0.07 x contracts x price x (1 - price) per order: 1.75 cents a contract at 50c, 0.63 cents at 90c",
                     "kalshi_maker": ("nothing, except on the series in desk.maker_fee_series, which pay a quarter of the taker "
                                      "rate: 0.0175 x contracts x price x (1 - price)"),
                     "alpaca_crypto": {"taker": 0.0025, "maker": 0.0015,
                                       "round_trip": {"maker_maker": 0.0030, "mixed": 0.0040, "taker_taker": 0.0050},
                                       "note": "the buy-side fee is taken in coins; rest post_only limits to pay the maker rate"},
                     "alpaca_equities_and_options": "no commission; you cross the spread (replay fills market orders at the touch)",
                     "replay_fills": "market orders at the touch; resting limits fill only when a later step trades strictly through them"},
            "horizon_guidance": self._horizon_guidance(niche),
            "forward_on_this_desk": self._forward_on_desk(niche_id),
            "winning_mechanisms": self.winning_mechanisms(),
            "replay_gate": dict(CONSTITUTION["ladder"]["replay"]),
            "replay_view": REPLAY_VIEW,
            "replay_window": {"days": replay_days, "step": "Kalshi day tapes step every 30 minutes; hour tapes every 5 minutes; Alpaca at NEEDS.bars.timeframe"},
            "limits": {"stake_usd": float(row["stake_usd"]), "max_position_usd": float(row["max_position_usd"]), "max_order_usd": float(row["max_order_usd"])},
            "horizon_rule": dict(house.game.get("horizon") or {}),
            "failed_on_this_desk": failed[:16],
            "retired_on_this_desk": [{"id": k, "reason": v.get("reason"), "failures": v.get("failures")} for k, v in retired.items()
                                     if self._retired_niche(k, v) == niche_id][:16],
            "passed_on_this_desk": passed[:8],
            "founder_ideas": seeds,
            "recent_postmortems": deaths,
        }

    def _horizon_guidance(self, niche: Any) -> dict[str, Any]:
        """Which horizon to write for, and why: the ladder's clock is the block."""
        prefer = str(self.settings.get("prefer_horizon") or "")
        paper = CONSTITUTION["ladder"]["paper"]
        return {"prefer": prefer if prefer in niche.horizons else niche.horizons[0], "allowed": list(niche.horizons),
                "paper_screen": {"hour": f"{paper['min_active_blocks']} active hourly blocks",
                                 "day": f"{paper['min_active_blocks_day']} finished active days "
                                        f"(1 once {((paper.get('settled_day') or {}).get('min_settled_trades'))} trades have settled, on Kalshi)"},
                "why": "evidence arrives one block at a time: an hourly program can clear the paper screen the day it is seated"}

    def _forward_on_desk(self, niche_id: str) -> list[dict[str, Any]]:
        """Forward results by family on this desk: what has actually made money after replay."""
        house = self.house
        rows: dict[str, dict[str, Any]] = {}
        try:
            standings = house.standings()
        except Exception:  # noqa: BLE001 - the packet is still worth sending without it
            return []
        for s in standings:
            agent = house.registry.get(s.agent)
            if agent is None or agent.specialty != niche_id:
                continue
            row = rows.setdefault(agent.family, {"family": agent.family, "members": 0, "on_paper": 0, "on_real_money": 0,
                                                 "with_a_record": 0, "earning": 0, "best_growth_per_block": None})
            row["members"] += 1
            row["on_paper"] += s.rung == 1
            row["on_real_money"] += s.rung >= 2
            if s.score_observations > 0:
                row["with_a_record"] += 1
                row["earning"] += s.score_growth > 0
                best = row["best_growth_per_block"]
                row["best_growth_per_block"] = round(s.score_growth, 6) if best is None else max(best, round(s.score_growth, 6))
        niche = house.niches.get(niche_id)
        for row in rows.values():
            capacity = self._capacity(row["family"], niche.venue) if niche is not None else None
            if capacity is not None:
                row["capacity"] = capacity
        return sorted(rows.values(), key=lambda r: (-r["earning"], -r["with_a_record"], r["family"]))[:12]

    def _family_record(self, family: str, venue: str) -> Mapping[str, Any] | None:
        """The family ledger's record of a family (`Allocator.family`, league/families.py), or None."""
        reader = getattr(getattr(self.house, "allocator", None), "family", None)
        if reader is None or not family:
            return None
        try:
            record = reader(family, venue)
        except Exception:  # noqa: BLE001 - `Allocator.family` never raises; a record that cannot be read says nothing
            return None
        return record if isinstance(record, Mapping) else None

    def _capacity(self, family: str, venue: str) -> dict[str, Any] | None:
        """A family's measured capacity as the family ledger holds it (E3 of the close-the-gaps run, Sept 24,
        2026; `families.capacity`, never measured again here) and whether it is at it (`lab.family_at_capacity`),
        for the packet: a card on a family at its capacity adds nothing on the markets it already fills."""
        from .families import swing_rule
        from .lab import family_at_capacity

        record = self._family_record(family, venue)
        if record is None:
            return None
        cap = record.get("capacity") if isinstance(record.get("capacity"), Mapping) else {}

        def number(value: Any, digits: int) -> float | None:
            try:
                return None if value is None else round(float(value), digits)
            except (TypeError, ValueError):
                return None

        return {"state": record.get("state"), "usd_per_day": number(cap.get("usd_per_day"), 4),
                "markets_per_day": number(cap.get("markets_per_day"), 3), "fill_rate_at_size": number(cap.get("fill_rate_at_size"), 4),
                "size_usd": number(cap.get("size_usd"), 2), "at_capacity": family_at_capacity(record, swing_rule())}

    def _at_capacity(self, agent: Agent) -> bool:
        """Whether the agent's family is at its measured capacity (`_capacity`)."""
        return bool((self._capacity(agent.family, agent.venue) or {}).get("at_capacity"))

    def _recorded_feeds(self, niche: Any) -> list[dict[str, Any]]:
        """The recorded feeds a card on this desk may read (`DESK_FEEDS`, the recorders of Deploy B: E2 of the
        close-the-gaps run, Sept 24, 2026), each with what it is, how to declare and read it, whether a replay
        can judge it now (point-in-time history) or only once its window has been recorded (a live feed), and,
        where the House records, since when and for which keys. A keyed feed whose key the owner has not placed
        says it is waiting."""
        from . import feeds as feeds_module

        recorder = getattr(self.house, "feeds", None)
        try:
            described = recorder.describe() if recorder is not None else {}
        except Exception:  # noqa: BLE001 - the list still says what may be declared
            described = {}
        examples = {"sports": "nfl", "perps": "BTC", "vol": "BTC", "funding": "BTC"}
        out = []
        for name in DESK_FEEDS.get(niche.id, ()):
            if name not in feeds_module.FEEDS:
                continue
            source = feeds_module.RECORDERS.get(name)
            example = (source.example if source is not None else "") or examples.get(name, "KEY")
            row = described.get(name) or {}
            history = name in feeds_module.HISTORY_FEEDS
            out.append({"feed": name, "what": str(getattr(source, "what", "") or feeds_module.WHAT.get(name) or "")[:240],
                        "declare": f"NEEDS['feeds'] = {{'{name}': ['{example}']}}", "read": f"ctx['feeds']['{name}'][key]",
                        "replay": ("point-in-time history, backfilled: a replay can judge a strategy that reads it now" if history
                                   else "recorded live from when recording began: a replay accepts it once its window is recorded"),
                        **{k: row[k] for k in ("recording_since", "backfilled_since", "replayable_now", "waiting") if row.get(k) is not None},
                        **({"recording": list(row.get("recording") or [])[:12]} if row else {})})
        return out

    def _coverage(self, niche: Any) -> dict[str, Any] | None:
        """What the newest `data.coverage` row (the history ingestion) says it holds for this desk's
        universe: counts and date ranges only, never the data."""
        # The history ingestion's rows only: the options store's carry `asset: "option"`, and the live
        # feeds write one `asset: "feed"` row a feed every hour (league/feeds.py), which would otherwise
        # always be the newest and hide the store this summarises.
        # Sept 24, 2026 (the close-the-gaps run's recorders): eleven more feeds write about 264 rows a
        # day, so the newest 500 rows stopped reaching back to the ingestion's row within a day and the
        # packet lost its coverage section. Look further back, a widening window at a time.
        rows = []
        for limit in (500, 5000, 50000):
            rows = [row for row in self.house.ledger.read(kinds="data.coverage", limit=limit, newest=True) if "asset" not in row.payload]
            if rows:
                break
        if not rows:
            return None
        latest = rows[-1].payload
        universe = {str(x).upper() for x in niche.universe}
        series = [{k: item.get(k) for k in ("kind", "symbol", "timeframe", "feed", "rows", "first_day", "last_day", "empty", "done")}
                  for item in (latest.get("series") or []) if isinstance(item, dict) and str(item.get("symbol") or "").upper() in universe]
        return {"source": latest.get("source"), "status": latest.get("status"), "finished_at": latest.get("finished_at"),
                "series": series[:24], "limitations": list(latest.get("limitations") or [])[:8], "states": latest.get("states"),
                "note": "Ingested history in the House's store. The replay window in `data.replay` is what a candidate is judged on."}

    # -------------------------------------------------------------------- call
    def run(self, niche_id: str, route: str = "evidence", reason: str = "") -> dict[str, Any]:
        """One paid foundry call for one desk. Never raises: a failed call is a row that says why."""
        from .frontier import FrontierError
        from .house import CONTRACT_PATH

        house = self.house
        settings = self.settings
        source = self.transfer_for(niche_id) if route == "transfer" else None
        packet = self.packet(niche_id, transfer=source)
        system = FOUNDRY_BRIEF + "\n\nTHE STRATEGY CONTRACT\n\n" + CONTRACT_PATH.read_text(encoding="utf-8")
        user = json.dumps(packet, default=str, sort_keys=True)
        inputs = hashlib.sha256((system + "\n" + user).encode("utf-8")).hexdigest()
        call = f"foundry:{inputs[:12]}:{int(self._now())}"
        allocation: dict[str, Any] = {"desk": niche_id, "route": route, "reason": reason[:500]}
        ported = ({"family": source["family"], "desk": source["desk"], **({"scale": True} if source.get("scale") else {})}
                  if source is not None else None)
        if route == "transfer":
            allocation["transfer"] = ported  # what `_tried` reads: this family has now been tried on this desk
        answer = None
        try:
            answer = self.frontier.ask(system=system, user=user, agent="merton-foundry",
                                       max_output_tokens=int(settings["max_output_tokens"]), effort=str(settings["effort"]))
            parsed = answer.json()
        except FrontierError as exc:
            cost = format(answer.cost_usd, "f") if answer is not None else "0"
            house.ledger.append("merton.pass", {"role": ROLE, "at_epoch": self._now(), "summary": f"the foundry call failed: {str(exc)[:200]}",
                                                "cost_usd": cost, "files": 0, "error": True, "call": call, "allocation": allocation})
            house.ledger.append("trace.record", {"task": TASK_CALL, "id": call, "version": PROMPT_VERSION, "model": getattr(self.frontier, "model", None),
                                                 "inputs_sha256": inputs, "outcome": "error", "cost_usd": cost, "useful": False})
            return {"call": call, "error": str(exc)}
        listed = parsed.get("candidates") if isinstance(parsed.get("candidates"), list) else []
        written, refused = [], []
        known = self.cards()
        retired = self.retired()
        links = self.links()
        for index, raw in enumerate(listed[:4]):
            card, problem = self._card(raw, niche_id, call, answer, known, retired, links, transfer=ported)
            if card is None:
                refused.append(problem)
                continue
            written.append(card)
        cost = format(answer.cost_usd, "f")
        summary = (f"{len(written)} hypothesis cards for {niche_id} ({route}"
                   + (f" of {ported['family']} from {ported['desk']}" if ported else "") + "); "
                   + (f"{len(refused)} refused before replay; " if refused else "") + str(parsed.get("summary") or "")[:600])
        house.ledger.append("merton.pass", {"role": ROLE, "at_epoch": self._now(), "summary": summary[:1500], "cost_usd": cost,
                                            "files": 0, "cards": [c["id"] for c in written], "refused": [str(r)[:200] for r in refused][:6],
                                            "call": call, "allocation": allocation, "cost_verified": bool(getattr(answer, "cost_verified", True))})
        house.ledger.append("trace.record", {"task": TASK_CALL, "id": call, "version": PROMPT_VERSION, "model": answer.model,
                                             "inputs_sha256": inputs, "outcome": f"{len(written)} cards, {len(refused)} refused",
                                             "cost_usd": cost, "useful": bool(written)})
        # One card after another, in one replay-lane job: the batch must not take every replay slot
        # from the agents, and the sealed probe box reads one module at a time.
        house._background(f"replay:hypothesis:{call}", self.evaluate_all, [c["id"] for c in written])
        return {"call": call, "cards": [c["id"] for c in written], "refused": refused, "cost_usd": cost}

    def _card(self, raw: Any, niche_id: str, call: str, answer: Any, known: Mapping[str, Any],
              retired: Mapping[str, Any], links: Mapping[str, set[str]], *,
              transfer: Mapping[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
        """Record one candidate as a card, or say why it was refused before any replay. `transfer`
        ({family, desk}) marks a card written on a transfer call: that family is then tried here."""
        from .safety import CodeRefused, check_code

        if not isinstance(raw, dict):
            return None, "a candidate that was not an object"
        mechanism = str(raw.get("mechanism") or "").strip()
        code = str(raw.get("code") or "")
        if not mechanism or not code.strip():
            return None, "a candidate without a mechanism or code"
        # E2 (Sept 24, 2026): every card states the fee it pays and the edge it needs to clear it.
        if not str(raw.get("fee") or "").strip() or not str(raw.get("edge_needed") or "").strip():
            return None, "a candidate that does not state the fee it pays and the edge it needs to clear it"
        ident = card_id(mechanism, niche_id)
        if ident in known:
            return None, f"{ident}: this exact mechanism already has a card on this desk"
        group = links.get(ident, {ident})
        if any(member in retired for member in group) or group & self._retired_mechanisms(retired):
            return None, f"{ident}: a retired mechanism (or a rewording of one)"
        name = re.sub(r"[^a-z0-9-]+", "-", str(raw.get("name") or "hypothesis").lower()).strip("-")[:20] or "hypothesis"
        niche = self.house.niches[niche_id]
        desk = niche.desk or niche_id.split("-", 1)[-1]
        line = f"{desk}-h{ident[:6]}"[:34]
        family = f"{niche_id.split('-', 1)[-1]}-{name}"[:40]
        if family in self._families():
            family = f"{family[:34]}-{ident[:5]}"  # a card is its own line: never pooled with an older family by a name clash
        payload = {
            "id": ident, "mechanism": mechanism[:2000], "data": [str(x)[:120] for x in (raw.get("data") or [])][:12]
            if isinstance(raw.get("data"), list) else [str(raw.get("data") or "")[:400]],
            "edge_after_costs": str(raw.get("edge_after_costs") or "")[:800], "horizon": str(raw.get("horizon") or "")[:300],
            "fee": str(raw.get("fee") or "")[:300], "edge_needed": str(raw.get("edge_needed") or "")[:300],
            "rejection": str(raw.get("rejection") or "")[:800], "niche": niche_id, "venue": niche.venue,
            "author": "merton", "lineage": [line], "parent_card": None, "created_for": call,
            "name": name, "line_id": line, "family": family, "created_epoch": self._now(),
            "model": getattr(answer, "model", None), "prompt_version": PROMPT_VERSION,
            "transfer": dict(transfer) if transfer else None,
            "code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(), "_code": code,
        }
        self.house.ledger.append("hypothesis.card", payload, id=f"hypothesis.card:{ident}")
        try:
            check_code(code)
        except (CodeRefused, SyntaxError) as exc:
            self._outcome(payload, "invalid", f"the strategy check refused it: {str(exc)[:200]}")
        return payload, ""

    # --------------------------------------------------------------- evaluate
    def _virtual(self, niche: Any, line: str, needs: Mapping[str, Any], code: str, params: Mapping[str, Any], *, family: str) -> Agent:
        """The card's line as the House's candidate replay needs to see it: the id its child will
        carry (so the counted trial is in that child's lineage), the desk's specialty, no parent."""
        try:
            venue, horizon, style = niche_of(needs)
        except ValueError:
            venue, horizon, style = niche.venue, niche.horizons[0], "hypothesis"
        return Agent(id=line, name=line, family=family, venue=venue, horizon=horizon, style=style, generation=1, parent=None,
                     code=code, params=dict(params or {}), wake_minutes=15, born_at=now_iso(self.house.clock),
                     needs=dict(needs), specialty=niche.id, line=line, founder=None)

    def _outcome(self, card: Mapping[str, Any], outcome: str, detail: str, **extra: Any) -> None:
        """A card's one evaluation outcome. The first one written stands: a replay that finishes
        after its card was given up on (or the reverse) must not fight over the row."""
        from .ledger import LedgerConflict

        key = f"hypothesis.evaluate:{card['id']}"
        if self.house.ledger.get(key) is not None:
            return
        try:
            self._append_outcome(card, outcome, detail, key, **extra)
        except LedgerConflict:
            pass

    def _append_outcome(self, card: Mapping[str, Any], outcome: str, detail: str, key: str, **extra: Any) -> None:
        self.house.ledger.append("trace.record", {"task": TASK_EVALUATE, "id": card["id"], "version": PROMPT_VERSION,
                                                  "model": card.get("model"), "inputs_sha256": card.get("code_sha256"),
                                                  "outcome": outcome, "cost_usd": "0", "useful": outcome == "passed",
                                                  "detail": str(detail)[:600], "niche": card.get("niche"), "line_id": card.get("line_id"),
                                                  **({"strategy": card["strategy"]} if card.get("strategy") else {}),
                                                  **extra}, id=key)

    def evaluate_all(self, idents: Sequence[str]) -> None:
        idents = list(idents)
        for index, ident in enumerate(idents):
            if self.house._closing.is_set():
                return
            result = self.evaluate(ident)
            if result is not None and result.get("infrastructure"):
                # Sail is not answering: the cards not yet tried stay pending, and this dispatch is
                # not counted as one of their attempts (only the card that met the outage is).
                self._uncount(idents[index + 1:])
                return

    def _uncount(self, idents: Sequence[str]) -> None:
        with self.house._state_lock:
            attempts = self._state().setdefault("attempts", {})
            for ident in idents:
                row = attempts.get(ident)
                if row:
                    row[0] = max(int(row[0]) - 1, 0)

    def evaluate(self, ident: str) -> dict[str, Any] | None:
        """Replay one card through the House's candidate replay. Passed, failed (a counted trial),
        invalid, blocked_data or blocked_infra; a closed allowance leaves it pending."""
        house = self.house
        card = self.cards().get(ident)
        if card is None or ident in self.evaluations():
            return None
        niche = house.niches.get(card["niche"])
        if niche is None or niche.dormant or not niche.replay:
            self._outcome(card, "invalid", "its desk is closed or has no replay")
            return None
        retired = self.retired()
        group = self.links().get(ident, {ident})
        closed = set(retired) | self._retired_mechanisms(retired)
        if closed & group:
            self._outcome(card, "retired_mechanism", "linked as a rewording of a retired mechanism before its replay: "
                          + ", ".join(sorted(closed & group))[:300])
            return None
        code = self._code(card)
        needs = static_needs(code) or {"venue": niche.venue, "horizon": niche.horizons[0]}
        agent = self._virtual(niche, card["line_id"], needs, code, {}, family=card["family"])
        if agent.venue != niche.venue or agent.horizon not in niche.horizons:
            self._outcome(card, "invalid", f"its NEEDS say {agent.venue}/{agent.horizon}, outside the {niche.id} desk")
            return None
        declared = static_needs(code)
        if declared is not None:
            # The House would show a strategy that names nothing on its desk the head of the desk's
            # universe instead (`niches.constrain`), and replay a program that was never about those
            # markets: a counted trial that tests nothing. Refuse it before the replay instead.
            from . import niches as niches_module
            try:
                home = niches_module.match(declared, house.niches)
            except Exception:  # noqa: BLE001 - an odd literal is the probe's to judge
                home = niche
            if home is None or home.id != niche.id:
                where = f"the {home.id} desk" if home is not None else f"nothing in the {niche.id} universe"
                self._outcome(card, "invalid", f"its NEEDS name {where}; a card must trade its own desk's markets")
                return None
        result = house._candidate_replay(agent, code)
        if result.get("infrastructure"):
            # The House's box or Sail did not answer: not this card's outcome and not a trial. It
            # stays pending; `max_evaluation_attempts` such tries make it `blocked_infra`.
            house.alert("warning", f"hypothesis card {ident}: its replay did not run, infrastructure "
                                   f"({str(result.get('error') or '')[:200]}); it stays pending")
            return result
        if not result.get("passed"):
            try:
                house.sandbox.retire(agent.id)  # its replay box: only a passer's child will use it
            except Exception:  # noqa: BLE001 - a box already gone is a box gone
                pass
        numbers = result.get("numbers") or {}
        if result.get("counted_as_trial"):
            outcome = "passed" if result.get("passed") else "failed"
            detail = "; ".join(str(r) for r in (numbers.get("reasons") or [])[:3]) or "passed every replay gate"
            self._outcome(card, outcome, detail, trial={k: numbers.get(k) for k in ("trades", "blocks", "sharpe", "deflated_sharpe", "trials", "passed")},
                          needs=result.get("needs"), params=result.get("params"))
            return result
        error = str(result.get("error") or "")
        if "allowance is closed" in error or "allowance" in error and "unavailable" in error:
            with house._state_lock:  # not the card's fault: it stays pending, and this try is not counted
                row = self._state().setdefault("attempts", {}).get(ident)
                if row:
                    row[0] = max(int(row[0]) - 1, 0)
            return result
        self._outcome(card, classify_error(error), error or "the replay did not run")
        return result

    def _families(self) -> set[str]:
        return self._folded("families", lambda: {a.family for a in list(self.house.registry.agents.values())}
                            | {str(e.payload.get("family")) for e in self.house.ledger.iter(kinds="eval.trial")}
                            | {str(c.get("family")) for c in self.cards().values()})

    def _code(self, card: Mapping[str, Any]) -> str:
        entry = self.house.ledger.get(f"hypothesis.card:{card['id']}")
        return str((entry.payload if entry else card).get("_code") or "")

    # ------------------------------------------------------------------ refill
    def refill(self, rules: Mapping[str, Any], *, living: Sequence[Agent], loser: Agent | None,
               mutations: bool = True, reserved: Sequence[str] = (), only: Collection[str] | None = None,
               seat_chosen: bool = False) -> Agent | None:
        """The newcomer, when routine refill is the foundry's: a replay-passing card first (best desk
        evidence first), else an evidence-driven mutation inside its share, else nobody.

        `mutations` off and `reserved` (Sept 23, 2026, the seat market): while a lab graduate waits
        for a seat the House stakes no mutation, and the desks graduates wait for are theirs first.

        `only` and `seat_chosen` (F3, the forward-first run, Sept 25, 2026: the House's seat market): only
        these cards may be admitted -- the waiters the House still counts, never one that left its queue --
        and, `seat_chosen`, into the seat the House chose (`loser`, None for a free one): its quota for a
        merged strategy's card (`House._strategy_births`)."""
        child = self._admit(rules, living=living, loser=loser, reserved=reserved, only=only, seat_chosen=seat_chosen)
        if child is None and mutations:
            child = self._evidence_mutation(rules, living=living, loser=loser)
        if child is not None and not seat_chosen:  # the quota's birth is not the refill's: its cadence stands
            with self.house._state_lock:
                self.house._state.setdefault("last_newcomer", {})["at"] = self._now()
        return child

    def _admit(self, rules: Mapping[str, Any], *, living: Sequence[Agent], loser: Agent | None,
               reserved: Sequence[str] = (), only: Collection[str] | None = None, seat_chosen: bool = False) -> Agent | None:
        house = self.house
        waiting = self.inventory()
        if only is not None:
            waiting = [c for c in waiting if c["id"] in only]  # F3: the waiters the House's seat market still counts
        if not waiting:
            return None
        rank = {d.niche: (d.score, d) for d in self.desk_scores()}
        retired = self.retired()
        waiting.sort(key=lambda c: (-(rank.get(c["niche"], (0.0, None))[0]), c["_seq"]))
        members = {}
        for a in living:
            members[a.specialty] = members.get(a.specialty, 0) + 1
        for card in waiting:
            niche = house.niches.get(card["niche"])
            if niche is None or niche.dormant or f"family:{card['family']}" in retired or f"line:{card['line_id']}" in retired:
                continue
            if niche.id in reserved:
                continue  # a lab graduate waits for this desk: its next seat is the graduate's
            evaluation = self.evaluations()[card["id"]]
            displaced = loser
            if not seat_chosen and members.get(niche.id, 0) >= niche.max_members:
                # A full desk makes room from its own weakest (which also frees a full league's
                # seat). The card passed replay: a replay-only or never-traded resident makes way
                # inside its grace (`House._weakest`, `evidenced`, Sept 23, 2026).
                displaced = house._weakest(rules, specialty=niche.id, evidenced=True)
                if displaced is None:
                    continue  # this desk is full of agents that have earned their seats
            code = self._code(card)
            desk = rank.get(niche.id, (0.0, None))[1]
            strategy = card.get("strategy")
            if strategy:
                why = (f"Merton, as engineer: the corrected child {strategy} (repair {(card.get('repair') or {}).get('key')}) "
                       f"passed replay before birth ({evaluation.get('detail')}); {str(card.get('mechanism'))[:300]}")
            else:
                why = (f"hypothesis card {card['id']} (Merton, foundry {card.get('created_for')}): {str(card.get('mechanism'))[:220]} "
                       f"-- passed replay before birth ({evaluation.get('detail')}); desk evidence {desk.why if desk else 'unscored'}")
            try:
                child = house.spawn(card["line_id"], card["family"], code, reason=why[:1500], params=evaluation.get("params") or {},
                                    endowment=rules["endowment_usd"], specialty=niche.id, founder=str(strategy) if strategy else f"card:{card['id']}")
            except ValueError as exc:
                self._outcome_admission(card, "refused_at_birth", str(exc))
                continue
            seated = child.id == card["line_id"] and child.code_sha256 == card.get("code_sha256") \
                and (evaluation.get("needs") is None or child.needs == evaluation.get("needs"))
            if seated:
                house.evaluator.seat(child.id, 1, f"its hypothesis card {card['id']} passed replay before birth, on its own line")
                with house._state_lock:
                    house._state["tried"][child.id] = child.code_sha256
                house.seat(child)
            if displaced is not None and displaced.alive:
                house.kill(displaced, "displaced", house.postmortem(displaced, "displaced",
                           "a replay-passing hypothesis card takes the seat of the weakest eligible agent"))
            self.record_birth(child, "repair" if strategy else "hypothesis",
                              f"a merged corrected child ({strategy}) that passed replay before any seat" if strategy
                              else f"a replay-passing hypothesis card for {niche.id}", {
                "card": card["id"], "desk_score": desk.score if desk else None, "desk_evidence": desk.why if desk else None,
                "replay_passed": True, "seated_on_paper": seated, "displaced": displaced.id if displaced else None,
                "allocation": self._allocation_of(card), **({"strategy": strategy, "repair": card.get("repair")} if strategy else {})})
            return child
        return None

    def _outcome_admission(self, card: Mapping[str, Any], status: str, detail: str) -> None:
        self.house.ledger.append("route.decision", {"task": f"admission:{card['id']}", "route": status, "model": None,
                                                    "reason": str(detail)[:400], "evidence": {"card": card["id"], "niche": card.get("niche")}},
                                 id=f"hypothesis.admission:{card['id']}:{status}")

    def _allocation_of(self, card: Mapping[str, Any]) -> dict[str, Any] | None:
        for call in self.calls():
            if call.get("call") == card.get("created_for"):
                return call.get("allocation")
        return None

    def _mutations_allowed(self) -> bool:
        """Evidence-driven mutations stay a bounded share of the day's births."""
        since = now_iso(lambda: self._now() - 86400)
        births = mutations = 0
        for entry in self.house.ledger.iter(kinds="agent.born"):
            if entry.at < since:
                continue
            births += 1
            route = self.house.ledger.get(f"birth-route:{entry.agent}")
            mutations += bool(route is not None and route.payload.get("route") == "evidence_mutation")
        cap = max(int(self.settings["mutation_min_per_day"]), int(float(self.settings["mutation_share"]) * births))
        return mutations < cap

    def _evidence_mutation(self, rules: Mapping[str, Any], *, living: Sequence[Agent], loser: Agent | None) -> Agent | None:
        house = self.house
        state = self._state()
        now = self._now()
        if now - float(state.get("last_mutation_look") or 0) < 600:
            return None  # standings are not free; a refill that found nobody waits ten minutes
        with house._state_lock:
            state["last_mutation_look"] = now
        if not self._mutations_allowed():
            return None
        retired = self.retired()
        rank = {d.niche: d for d in self.desk_scores()}
        # Seats a rung-0 mutation may take, a desk: never a desk's last free seat while it has no
        # member that trades (`House._mutation_room`, Sept 23, 2026).
        room = house._mutation_room(living)
        candidates = []
        for s in house.standings():
            agent = house.registry.get(s.agent)
            if agent is None or not agent.alive or (loser is not None and agent.id == loser.id):
                continue
            if not (s.score_observations > 0 and s.score_growth > 0):
                continue  # positive forward evidence, or no House-staked child
            if self._is_retired(agent, retired):
                continue  # an exhausted mechanism is not bred, however well one of its members trades
            if house._losing_family(agent.family):
                continue  # one earning member does not outvote the family's pooled forward record
            if self._at_capacity(agent):
                continue  # E3 (Sept 24, 2026): a family at its measured capacity gets no more search there
            niche = house.niche_of(agent)
            if niche is None or niche.dormant or room.get(niche.id, 0) <= 0:
                continue
            desk = rank.get(niche.id)
            candidates.append(((desk.score if desk else 0.0), s.score_growth, agent, s, desk))
        candidates.sort(key=lambda row: (row[0], row[1]), reverse=True)
        for _, growth, parent, standing, desk in candidates:
            params = house._mutated_params(parent, seed=f"newcomer:{len(house.registry.agents)}")
            if params is None:
                continue
            child = house.spawn(parent.line or parent.name, parent.family, parent.code, parent=parent.id, endowment=rules["endowment_usd"], params=params,
                                reason=(f"an evidence-driven House mutation of {parent.id}: it is earning forward "
                                        f"(growth {growth:+.5f} over {standing.score_observations} observations) on {parent.specialty}"))
            house.ledger.append("agent.forked", {"child": child.id, "endowment_usd": rules["endowment_usd"], "box_forked": False,
                                                 "reason": "evidence", "new_code": False}, agent=parent.id)
            if loser is not None and loser.alive:
                house.kill(loser, "displaced", house.postmortem(loser, "displaced",
                           "the league was full and an evidence-driven newcomer replaces its weakest eligible agent"))
            self.record_birth(child, "evidence_mutation", f"a House mutation of {parent.id}, which is earning forward", {
                "parent": parent.id, "parent_growth": growth, "parent_observations": standing.score_observations,
                "desk_score": desk.score if desk else None, "replay_passed": False, "starts_on_rung": 0,
                "displaced": loser.id if loser else None})
            return child
        return None

    # --------------------------------------------------------- birth reasons
    def record_birth(self, child: Agent, route: str, reason: str, evidence: Mapping[str, Any]) -> None:
        """The allocation reason and evidence status of one birth (`route.decision`, once each)."""
        key = f"birth-route:{child.id}"
        if self.house.ledger.get(key) is None:
            self.house.ledger.append("route.decision", {"task": f"birth:{child.id}", "route": route, "model": None,
                                                        "reason": reason[:600], "evidence": dict(evidence)}, id=key)

    def annotate_births(self) -> int:
        """Label every birth the foundry did not make itself with why it happened and what evidence
        stood behind it, so the deliberate exceptions stay explicit on the ledger."""
        house = self.house
        state = self._state()
        cursor = int(state.get("birth_cursor") or 0)
        added = 0
        founder_keys = {f.get("key") for n in house.niches.values() for f in n.founders}
        last = cursor
        for entry in house.ledger.iter(kinds="agent.born", after=cursor):
            last = entry.seq
            if house.ledger.get(f"birth-route:{entry.agent}") is not None:
                continue
            p = entry.payload
            reason = str(p.get("reason") or "")
            parent = p.get("parent")
            if str(p.get("founder") or "").startswith("card:"):
                route, why, evidence = "hypothesis", "a hypothesis card's child (its admission row was not written)", {"card": p["founder"][5:]}
            elif str(p.get("founder") or "").startswith("lab:"):  # league/lab.py writes its own; this only backs it up
                route, why, evidence = "lab", "an Alpha Lab graduate (its birth row was not written)", {"lineage": p["founder"][4:]}
            elif parent is None and p.get("founder") in founder_keys:
                route, why, evidence = "founder", "a founding seed: starts on paper without a replay pass (deliberate exception); its replay still runs and counts", \
                    {"exception": "founder_paper_start", "replay_passed": False}
            elif parent is None:
                route, why, evidence = "architect", "an architect's merged strategy: born on rung 0 and must pass replay", {"replay_passed": False, "starts_on_rung": 0}
            elif reason.startswith("a House-staked valid mutation"):
                route, why, evidence = "legacy_mutation", "a House-staked parameter mutation placed by open seats (the refill the foundry replaces)", \
                    {"replay_passed": False, "starts_on_rung": 0}
            elif reason.startswith("an evidence-driven House mutation"):
                route, why, evidence = "evidence_mutation", reason[:300], {"parent": parent, "replay_passed": False, "starts_on_rung": 0}
            else:
                forked = next((e.payload for e in house.ledger.iter(kinds="agent.forked", agent=parent) if e.payload.get("child") == entry.agent), {})
                if forked.get("new_code"):
                    route, why = "candidate", "a research candidate whose code passed replay as its parent's candidate: a versioned child on its own record"
                    evidence = {"replay_passed": True, "staked_by": forked.get("staked_by"), "parent": parent}
                else:
                    route, why = "earner_fork", "a parameter fork paid for by a parent that earned its credits (deliberate exception); the child must pass replay"
                    evidence = {"replay_passed": False, "starts_on_rung": 0, "parent": parent,
                                "parent_rung": house.evaluator.rung(parent) if parent else None}
            house.ledger.append("route.decision", {"task": f"birth:{entry.agent}", "route": route, "model": None,
                                                   "reason": why, "evidence": evidence}, id=f"birth-route:{entry.agent}")
            added += 1
        with house._state_lock:
            state["birth_cursor"] = last
        return added

    # ------------------------------------------------------------ retirement
    def retire_exhausted(self) -> list[dict[str, Any]]:
        """Stop breeding what the evidence has closed. Returns the rows written this pass."""
        house = self.house
        settings = self.settings
        limit = int(settings["retire_after_failures"])
        already = self.retired()
        cards = self.cards()
        by_line = {c.get("line_id"): c.get("niche") for c in cards.values() if c.get("line_id")}
        families: dict[str, dict[str, Any]] = {}
        for entry in house.ledger.iter(kinds="eval.trial"):
            p = entry.payload
            family = str(p.get("family") or "")
            if not family:
                continue
            row = families.setdefault(family, {"failures": 0, "passes": 0, "empty": 0, "agents": set(), "niche": None, "evidence": []})
            row["agents"].add(entry.agent)
            row["niche"] = row["niche"] or self._niche_of_agent(entry.agent, by_line)
            if p.get("passed"):
                row["passes"] += 1
                continue
            row["failures"] += 1
            if int(p.get("blocks") or 0) == 0:
                row["empty"] += 1
            row["evidence"] = (row["evidence"] + [{"seq": entry.seq, "at": entry.at, "agent": entry.agent,
                                                   "excerpt": "; ".join(str(r) for r in (p.get("reasons") or [])[:2])[:240]}])[-5:]
        written = []
        for family, row in families.items():
            key = f"family:{family}"
            if key in already or row["passes"] or row["failures"] < limit:
                continue
            blocked = row["empty"] / row["failures"] >= float(settings["blocked_share"])
            reason = "blocked_data" if blocked else "disproven"
            repair_key = f"missing_data:replay-tape:{row['niche']}:{family}" if blocked else None
            payload = {"id": key, "reason": reason, "failures": row["failures"],
                       "evidence": {"family": family, "niche": row["niche"], "passes": 0, "empty_tape_failures": row["empty"],
                                    "agents": sorted(row["agents"])[:24], "last": row["evidence"], "repair_key": repair_key,
                                    "rule": f"{limit} counted replay failures with no pass"}}
            house.ledger.append("hypothesis.retired", payload, id=f"hypothesis.retired:{key}:{row['failures']}")
            written.append(payload)
            if blocked:
                self._report(repair_key, "missing_data",
                             f"the {family} family on {row['niche']} failed {row['empty']} of {row['failures']} replays on an empty tape: "
                             "its inputs are missing, so it is retired from breeding until the data exists",
                             row["evidence"], sorted(row["agents"]), "medium")
        written.extend(self._retire_unrunnable(families, already))
        written.extend(self._retire_cards(cards, already, limit))
        written.extend(self._report_blocked_cards(cards))
        return written

    def _retire_unrunnable(self, families: Mapping[str, Mapping[str, Any]], already: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Lines whose replays mostly cannot RUN. Those are not trials, so the failure count above
        never sees them, and a mutation of such a line buys another replay that will not run. The
        House says so in its alerts (`<agent>: replay could not run (...)`, `... was not run (...)`);
        a family with `infra_failures` of them in distinct hours, at least as many as its counted
        trials and no pass, is retired `blocked_data` (a missing input) or `blocked_infra` (the box,
        a timeout, a crash), and reported for repair instead of being bred."""
        house = self.house
        since = now_iso(lambda: self._now() - float(self.settings["evidence_days"]) * 86400)
        pattern = re.compile(r"^([a-z][a-z0-9-]{1,40}): (?:replay could not run|its replay was not run|a candidate's replay was not run) \((.*)")
        seen: dict[str, dict[str, Any]] = {}
        for entry in house.ledger.iter(kinds="ops.alert"):
            if entry.at < since:
                continue
            match = pattern.match(str(entry.payload.get("text") or ""))
            if not match:
                continue
            agent = house.registry.get(match.group(1))
            detail = match.group(2)
            if agent is None or "allowance" in detail:
                continue  # a closed budget is the owner's line, not the strategy's
            kind = "blocked_data" if classify_error(detail) == "blocked_data" or "unsupported input" in detail.lower() else "blocked_infra"
            row = seen.setdefault(agent.family, {"hours": {"blocked_data": set(), "blocked_infra": set()}, "niche": agent.specialty,
                                                 "agents": set(), "evidence": []})
            key = (agent.id, entry.at[:13])
            if key in row["hours"][kind]:
                continue
            row["hours"][kind].add(key)
            row["agents"].add(agent.id)
            row["evidence"] = (row["evidence"] + [{"seq": entry.seq, "at": entry.at, "agent": agent.id, "excerpt": detail[:240]}])[-5:]
        written = []
        floor = int(self.settings["infra_failures"])
        for family, row in seen.items():
            counted = families.get(family) or {}
            if f"family:{family}" in already or counted.get("passes"):
                continue
            kind = max(row["hours"], key=lambda k: len(row["hours"][k]))
            failures = len(row["hours"][kind])
            if failures < floor or failures < int(counted.get("failures") or 0):
                continue
            repair_key = (f"missing_data:replay-input:{row['niche']}:{family}" if kind == "blocked_data"
                          else f"shared_defect:replay-harness:{row['niche']}:{family}")
            payload = {"id": f"family:{family}", "reason": kind, "failures": failures,
                       "evidence": {"family": family, "niche": row["niche"], "counted_failures": int(counted.get("failures") or 0),
                                    "agents": sorted(row["agents"])[:24], "last": row["evidence"], "repair_key": repair_key,
                                    "rule": f"{floor} replays that could not run, in distinct hours, and no pass"}}
            house.ledger.append("hypothesis.retired", payload, id=f"hypothesis.retired:family:{family}:{kind}:{failures}")
            written.append(payload)
            self._report(repair_key, "missing_data" if kind == "blocked_data" else "shared_defect",
                         f"the {family} family on {row['niche']} could not replay {failures} times "
                         + ("for a missing input" if kind == "blocked_data" else "because the replay harness failed")
                         + "; it is retired from breeding until the repair is verified",
                         row["evidence"], sorted(row["agents"]), "medium")
        return written

    def _retire_cards(self, cards: Mapping[str, Any], already: Mapping[str, Any], limit: int) -> list[dict[str, Any]]:
        """Rewordings share failure history: a group of linked cards with `limit` failures and no pass
        is retired as one mechanism. The trial counts themselves are untouched."""
        links = self.links()
        evaluations = self.evaluations()
        done, written = set(), []
        for ident in cards:
            group = links.get(ident)
            if not group or ident in done:
                continue
            done |= group
            outcomes = [evaluations.get(m, {}).get("outcome") for m in group]
            failures = sum(o == "failed" for o in outcomes)
            if "passed" in outcomes or failures < limit:
                continue
            for member in sorted(group):
                if member in already or member not in cards:
                    continue
                payload = {"id": member, "reason": "disproven", "failures": failures,
                           "evidence": {"niche": cards[member].get("niche"), "group": sorted(group), "method": "hypothesis.link rewording",
                                        "note": "failure history shared across rewordings; genealogy and trial counts are unchanged"}}
                self.house.ledger.append("hypothesis.retired", payload, id=f"hypothesis.retired:{member}:{failures}")
                written.append(payload)
        return written

    def _report_blocked_cards(self, cards: Mapping[str, Any]) -> list[dict[str, Any]]:
        """A desk whose cards keep failing to RUN is a repair, not a reason to write more cards."""
        threshold = int(self.settings["repair_after_blocked"])
        rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for ident, outcome in self.evaluations().items():
            kind = outcome.get("outcome")
            if kind not in ("blocked_data", "blocked_infra"):
                continue
            niche = (cards.get(ident) or {}).get("niche") or outcome.get("niche")
            rows.setdefault((str(kind), str(niche)), []).append(
                {"seq": outcome["_seq"], "at": outcome["_at"], "agent": outcome.get("line_id") or ident,
                 "excerpt": str(outcome.get("detail") or "")[:240]})
        written = []
        for (kind, niche), evidence in rows.items():
            if len(evidence) < threshold:
                continue
            key = f"{'missing_data' if kind == 'blocked_data' else 'shared_defect'}:hypothesis-replay:{niche}"
            summary = (f"{len(evidence)} hypothesis cards for {niche} could not be replayed "
                       + ("because inputs were missing" if kind == "blocked_data" else "because the replay harness failed")
                       + "; the foundry writes no more cards for this desk until the repair is verified")
            if self._report(key, "missing_data" if kind == "blocked_data" else "shared_defect", summary, evidence[-5:],
                            [e["agent"] for e in evidence][-12:], "high", bucket=len(evidence) // threshold):
                written.append({"key": key})
        return written

    def _report(self, key: str, kind: str, summary: str, evidence: Sequence[Mapping[str, Any]], agents: Sequence[str],
                severity: str, *, bucket: int = 1) -> bool:
        ident = f"repair.reported:{key}:{bucket}"
        if self.house.ledger.get(ident) is not None:
            return False
        self.house.ledger.append("repair.reported", {"key": key, "kind": kind, "summary": summary[:800], "evidence": list(evidence),
                                                     "agents": list(agents), "source": "triage", "severity": severity}, id=ident)
        return True

    # ------------------------------------------------------------------ health
    def stats(self) -> dict[str, Any]:
        try:
            return self._stats()
        except Exception as exc:  # noqa: BLE001 - health must be written whatever this says
            return {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}

    def _stats(self) -> dict[str, Any]:
        evaluations = self.evaluations()
        outcomes: dict[str, int] = {}
        for row in evaluations.values():
            outcomes[str(row.get("outcome"))] = outcomes.get(str(row.get("outcome")), 0) + 1
        return {"enabled": self.enabled(), "replaces_refill": self.replaces_refill(), "refusal": self.refusal,
                "cards": len(self.cards()), "outcomes": outcomes, "waiting_for_seat": len(self.inventory()),
                "pending": len(self.pending()), "spent_window_usd": format(self.spent(), "f"),
                "budget_usd": str(self.settings["budget_usd"]), "retired": len(self.retired())}
