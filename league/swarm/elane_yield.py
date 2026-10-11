"""YIELD PER DOLLAR OF THE EQUITY LANES' MODEL ROUTES (release E2, Oct 2026; the owner's goal: "Choose models by measured
yield per dollar").

THE RECORD (`record`, `report`; kv `LEDGER_KEY`). One row a model route ("sail:<profile>", "openai:<model>",
"claude:<role>"), kept by the equity pass (league/swarm/elane_births.py) and the equity Train researcher
(league/swarm/elane_train.py), which ask every equity question on ONE route at a time and book its answer here:
- `requests`, `answered`, `failed` (every question: births, Train revisions); `requests_births`, `answered_births`
  (the equity pass's own requests: what THE ROUTE CHOICE samples and prices, never the revisions); `usd` (the
  answers' dollars: births and research), `usd_births`, `usd_research`, `unknown_cost` (answers whose bill was not
  known when they landed: their held dollars are booked, else none);
- `births`: the equity families its answers bore (each family remembers its birth route: spec `e2_route`; its Train
  revisions are asked on the same route, so a family's whole cost and yield sit on one row);
- read from the families at report time: `train_scored` (families with a Train-scored version), `train_passes`
  (families with a version that passed equity-v1, its STATE and START checks among it, and the equity review), and,
  FOR THE OPERATOR ONLY, `validation_entries` (E1's `elane_try` with its pre-check met), `looks`, `looks_passed` (E1's
  `elane_look`) and `live` (a family now in Probe or Sized).
`report` is what ops reads (league/ops: the dlane report, the funnel); nothing here writes outside the swarm store.

THE ROUTE CHOICE (`choose`), for each equity request (a birth pass) and each new equity family's first program:
1. THE ROUTES are `elane.e2.routes` (default `DEFAULTS["routes"]`: Sail profiles, the cheapest list price first); a
   "claude:<role>" entry is used only while the router serves that role on Claude, an "openai:<model>" entry only
   while it names a model.
2. A route is SAMPLED once it has `min_births` (10) births OR `sample_requests` (30) BIRTH requests (the equity
   pass's own: `requests_births`), answered or failed: a route that never answers, or whose answers are always cut or
   refused, is measured too, at a yield of zero births. A family's Train revisions are asked on its birth route and
   booked on its row, and count nothing here: revisions alone never make a route sampled.
3. Once EVERY route is sampled: every (`explore_every` x routes)-th request goes to the route with the fewest requests
   (each route keeps being measured: a route never starves on an early run of bad luck); every other request goes to
   the route with the most Train passes per dollar, SMOOTHED: (passes + 1) / (usd + the pooled dollars a pass), so one
   lucky pass on an expensive route does not shut out a cheap route with none yet. Ties: births per dollar, then the
   cheaper mean cost a request, then the list order.
4. Before that, EXPLORATION: every `explore_every`-th request (3; the ledger's `turn`) goes to the unsampled route
   furthest from its sample (fewest births, then fewest requests; ties: list order); every other request DEFAULTS TO
   THE CHEAPEST ROUTE THAT HAS PRODUCED BIRTHS (the lowest mean dollars a BIRTH request among routes with a birth:
   `usd_births` over `answered_births`), and with none, the first route of the list.
5. A route whose call fails is passed over for that request (the next route of the list answers; the answer is booked
   to the route that gave it, the failure to the route that failed, with whatever the swarm booked for the failed
   call's key: a hold for a call that was sent and never answered). A call that failed AFTER IT WAS SENT (a poll or
   transport timeout: Sail may still run and bill it) ends the question there: no other route is asked the same
   question on top of it, and the asker waits out a backoff (`unsent`, `SENT_UNANSWERED`).
THE YIELD IS TRAIN PASSES PER DOLLAR, NEVER A LATER STAGE (A9 D3). Validation entries, looks passed and live programs
are recorded for the operator and are never read by `choose`: a route chosen on the sealed look's outcomes would feed
the holdout back into which model writes the next programs. A Train pass is the first stage every route's programs
reach alike, and it is a Train fact. (`choose` is tested to give the same route whatever those outcomes are.)

E2'S DOLLARS: A SHARE OF THE SWARM'S SAIL MODEL LINE, COUNTED APART (`pace_share`, `usd_day`; `hold`, `pace`, `room`).
The budget rule gives the swarm ONE hourly line for Sail models (`researcher.sail_usd_per_hour` after the budget's
overlay: `model_line`; $0.3333 an hour, $8.00 a day, at the owner's ceiling and $0.0667 an hour at the floor). E2's
births, Train research and review are paid from that line and counted apart from the options researchers:
- E2'S HOURLY PACE (`usd_hour`) is `pace_share` (0.25) of the line. Before every model call (the equity pass, a Train
  write, a review or audit read) E2 reads what the swarm booked for its own request keys in the trailing hour
  (`spent_since`: the spend rows whose key is "swarm:elane:...", holds for unanswered calls included) and asks nothing
  at or over the pace (`hold`). The budget tightens it with the line: at the floor E2's pace is a quarter of the
  floor's.
- THE DAY'S LINE (`day_line`) is `usd_day` dollars a UTC day, and never more than a day at the hourly pace
  (`pace_share` x the line x 24): once E2's day (`spent_today`: the larger of this ledger's day and the swarm's meter
  for E2's keys, so a hold the ledger never heard of counts) reaches it, no equity question is asked until the next
  UTC day.
- THE OPTIONS RESEARCHERS' PACE (league/swarm/loop.py `Swarm.pace_status`) leaves E2's rows out of their own spend,
  as it leaves the architect's (F1), and gives E2's dollars of the trailing hour, at most E2's hourly pace, back to
  the line: the researchers pause at the line less what E2 took, so E2 never takes more than its share from them and
  the two together fit the line. The Sail guard's day counts every dollar; `allocation.plan_usd_per_hour`, when set,
  counts E2's dollars as research spend like any Sail model dollar.
The equity review's dollars (league/swarm/elane_review.py) are booked on rows of their own ("review:<route>"), never on
a birth route's row, so they move no route's yield.

Standard library only.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from . import elane_seal

#: The swarm store's kv key of the ledger.
LEDGER_KEY = "elane_yield"
#: The family spec's key of its birth route.
ROUTE_KEY = "e2_route"
#: The role E2's questions carry on Sail and OpenAI (their cache key and the router's books); a "claude:<role>" route
#: asks as its own role (a role `claude.roles` serves, on that role's Claude line).
ROLE = "elane"
#: E2's defaults (the `elane.e2` block; policy.json carries them, ELANE_E2_PATCHES.md). Sail profiles in list-price order
#: (league's ltcm/provider.py PROFILES, output dollars a million tokens): DeepSeek-V4-Pro asap, GLM-5.3 asap, Kimi-K3 asap.
DEFAULTS: dict[str, Any] = {
    "routes": ["sail:pro_asap", "sail:glm_asap", "sail:k3"],
    "min_births": 10,
    "sample_requests": 30,
    "explore_every": 3,
    "usd_day": 8.0,
    "pace_share": 0.25,
}
#: Bounds of the numbers above (a value outside is its default). `pace_share`: at most half the line is ever E2's.
BOUNDS = {"min_births": (1, 1000), "sample_requests": (1, 10000), "explore_every": (2, 100), "usd_day": (0.0, 100.0),
          "pace_share": (0.0, 0.5)}
#: HOW A SPEND ROW OF E2'S IS TOLD (the swarm's `spend` table): every model call's row carries its request key (`key`,
#: `hold`, `settles` or `releases` in its detail), and E2's keys are "swarm:elane:<births|train|review|audit>:..." (a
#: window fallback's key keeps the prefix). The loop's `ARCHITECT_KEY` is the same mark for the architect's pass.
SPEND_MARK = ':"swarm:elane:'
#: The spend kinds a model call of E2's is booked under (its routes: Sail, OpenAI, Claude).
SPEND_KINDS = ("sail_model", "openai", "claude")
#: The ledger rows of the equity review (league/swarm/elane_review.py): "review:<route>", apart from the birth routes.
REVIEW_PREFIX = "review:"
ROUTE_KINDS = ("sail", "openai", "claude")
#: The E1 family-state keys `report` reads for the operator (never `choose`).
TRY_KEY, LOOK_KEY = "elane_try", "elane_look"
LIVE_BANDS = ("probe", "sized")


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def e2_settings(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """The raw `elane.e2` block ({} for none)."""
    block = (settings or {}).get("elane") if isinstance(settings, Mapping) else None
    e2 = block.get("e2") if isinstance(block, Mapping) else None
    return dict(e2) if isinstance(e2, Mapping) else {}


def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """The route settings, each inside its bound (a malformed value is its default)."""
    raw = e2_settings(settings)
    out = dict(DEFAULTS)
    routes = raw.get("routes")
    if isinstance(routes, list):
        kept = [str(r) for r in routes if isinstance(r, str) and r.split(":", 1)[0] in ROUTE_KINDS and ":" in r
                and r.split(":", 1)[1].strip()]
        if kept:
            out["routes"] = list(dict.fromkeys(kept))
    for key, (lo, hi) in BOUNDS.items():
        x = _num(raw.get(key))
        if x is not None and lo <= x <= hi:
            out[key] = int(x) if isinstance(DEFAULTS[key], int) else x
    return out


@dataclass(frozen=True)
class Route:
    """One model route: `key` ("sail:pro_asap"), `kind` and `name` (the profile, model or Claude role)."""

    key: str
    kind: str
    name: str

    @staticmethod
    def of(key: str) -> "Route":
        kind, _, name = str(key).partition(":")
        return Route(str(key), kind, name)


def routes(settings: Mapping[str, Any] | None, router: Any = None) -> list[Route]:
    """The routes a request may take now (THE ROUTE CHOICE, 1): the list, less a Claude role the router does not serve."""
    return served([Route.of(key) for key in cfg(settings)["routes"]], router)


def served(candidates: Sequence[Route], router: Any = None) -> list[Route]:
    """`candidates` less a Claude role the router does not serve."""
    out = []
    for route in candidates:
        if route.kind == "claude":
            served = getattr(router, "claude_enabled", None)
            try:
                if not (callable(served) and served(route.name)):
                    continue
            except Exception:  # noqa: BLE001 - a route that cannot say it serves is not taken
                continue
        out.append(route)
    return out


# ------------------------------------------------------------------------------------------------------------ the ledger
def _today(now: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(now))


def _row() -> dict[str, Any]:
    return {"requests": 0, "answered": 0, "failed": 0, "requests_births": 0, "answered_births": 0, "usd": 0.0,
            "usd_births": 0.0, "usd_research": 0.0, "usd_review": 0.0, "unknown_cost": 0, "births": 0}


def ledger(store: Any) -> dict[str, Any]:
    """The ledger as stored: {"routes": {key: row}, "days": {YYYY-MM-DD: usd}, "turn": n}."""
    value = store.get(LEDGER_KEY)
    value = dict(value) if isinstance(value, Mapping) else {}
    value["routes"] = {str(k): {**_row(), **(v if isinstance(v, Mapping) else {})}
                       for k, v in (value.get("routes") or {}).items()}
    value["days"] = {str(k): float(v) for k, v in (value.get("days") or {}).items() if _num(v) is not None}
    value["turn"] = int(value.get("turn") or 0) if isinstance(value.get("turn"), int) else 0
    return value


def _write(store: Any, change: Any) -> dict[str, Any]:
    with store.atomic():
        book = ledger(store)
        change(book)
        days = sorted(book["days"])[-14:]  # two weeks of days is all the line reads
        book["days"] = {d: round(book["days"][d], 6) for d in days}
        store.put(LEDGER_KEY, book)
    return book


def answer_usd(answer: Mapping[str, Any] | None) -> tuple[float, bool]:
    """(the dollars an answer cost, whether its bill was known): `cost_usd`, else its `held_usd` (unknown)."""
    answer = answer or {}
    cost = _num(answer.get("cost_usd"))
    if cost is not None:
        return max(0.0, cost), True
    held = _num(answer.get("held_usd"))
    return (max(0.0, held) if held is not None else 0.0), False


def book(store: Any, key: str, *, usd: float, known: bool, purpose: str, answered: bool, now: float) -> None:
    """One request on route `key`: its dollars (`purpose` "births", "research" or "review") and whether it was
    answered."""
    def change(b: dict[str, Any]) -> None:
        row = b["routes"].setdefault(key, _row())
        row["requests"] += 1
        row["answered" if answered else "failed"] += 1
        if purpose == "births":  # THE ROUTE CHOICE's sample and price: the equity pass's own requests, never a revision
            row["requests_births"] += 1
            row["answered_births"] += int(bool(answered))
        row["usd"] = round(row["usd"] + usd, 6)
        name = {"births": "usd_births", "review": "usd_review"}.get(purpose, "usd_research")
        row[name] = round(row[name] + usd, 6)
        row["unknown_cost"] += 0 if known else 1
        day = _today(now)
        b["days"][day] = b["days"].get(day, 0.0) + usd
    _write(store, change)


def book_births(store: Any, key: str, n: int) -> None:
    """`n` equity families born of route `key`'s answer."""
    if n <= 0:
        return

    def change(b: dict[str, Any]) -> None:
        b["routes"].setdefault(key, _row())["births"] += int(n)
    _write(store, change)


def next_turn(store: Any) -> int:
    """The equity request's turn (0, 1, 2, ...): counted once a request, for THE ROUTE CHOICE's exploration."""
    out: list[int] = []

    def change(b: dict[str, Any]) -> None:
        out.append(b["turn"])
        b["turn"] += 1
    _write(store, change)
    return out[0]


def spent_since(store: Any, since: float, kinds: Sequence[str] = SPEND_KINDS) -> float:
    """What the swarm booked for E2's own request keys since `since` (seconds): the spend rows of `kinds` whose detail
    carries `SPEND_MARK`, holds for unanswered calls and their later true-ups included. 0 for a store with no spend
    table (a fake)."""
    kinds = [str(k) for k in kinds]
    if not kinds:
        return 0.0
    try:
        row = store._one(f"SELECT COALESCE(SUM(usd),0) AS usd FROM spend WHERE kind IN ({','.join('?' * len(kinds))}) "
                         "AND epoch>=? AND instr(detail, ?) > 0", (*kinds, float(since), SPEND_MARK))
    except Exception:  # noqa: BLE001 - no spend table to read: the ledger alone counts
        return 0.0
    return max(0.0, float(row["usd"])) if row else 0.0


def _day_start(now: float) -> float:
    return float(now) - float(now) % 86400.0


def spent_today(store: Any, now: float) -> float:
    """E2's model dollars this UTC day: the larger of the ledger's day (what `book` counted) and the swarm's meter for
    E2's keys (`spent_since`), so a hold the router booked for a call that never answered counts though no answer was
    booked here, and a store whose router books no spend row (a fake) reads the ledger."""
    return max(float(ledger(store)["days"].get(_today(now), 0.0)), spent_since(store, _day_start(now)))


def model_line(settings: Mapping[str, Any] | None) -> tuple[float, bool]:
    """(THE SWARM'S SAIL MODEL LINE in dollars an hour, whether it could be read): `researcher.sail_usd_per_hour`, else
    (absent or null) the legacy `researcher.usd_per_hour` (4.0 when that is absent too), exactly as the loop's
    `Swarm.pace_status` reads its limit; the settings the loop holds carry the budget's overlay. A value that is no
    finite number at or above zero is (0.0, False): the researchers pause on it, and so does E2."""
    block = (settings or {}).get("researcher") if isinstance(settings, Mapping) else None
    block = block if isinstance(block, Mapping) else {}
    raw = block.get("sail_usd_per_hour")
    raw = raw if raw is not None else block.get("usd_per_hour", 4.0)
    try:
        value = float(raw)
        valid = not isinstance(raw, bool) and math.isfinite(value) and value >= 0
    except (TypeError, ValueError, OverflowError):
        value, valid = 0.0, False
    return (value, True) if valid else (0.0, False)


def usd_hour(settings: Mapping[str, Any] | None, line: float | None = None) -> float:
    """E2'S HOURLY PACE in dollars: `pace_share` of the swarm's Sail model line (`line`: the loop's own reading, else
    `model_line`)."""
    if line is None:
        line, _ = model_line(settings)
    return max(0.0, float(cfg(settings)["pace_share"]) * max(0.0, float(line)))


def day_line(settings: Mapping[str, Any] | None) -> float:
    """THE DAY'S LINE: `usd_day`, never more than a day at E2's hourly pace (the budget's overlay tightens it with the
    line)."""
    return min(float(cfg(settings)["usd_day"]), usd_hour(settings) * 24.0)


def room(store: Any, settings: Mapping[str, Any] | None, now: float) -> float:
    """E2's model dollars left this UTC day (THE DAY'S LINE)."""
    return max(0.0, day_line(settings) - spent_today(store, now))


def pace(store: Any, settings: Mapping[str, Any] | None, now: float, *, line: float | None = None) -> dict[str, Any]:
    """E2'S HOURLY PACE now: {limit_usd_per_hour, spent_last_hour_usd, paused, reason}. Paused at or over the limit (a
    zero limit, from a zero share or a line that cannot be read, pauses at once)."""
    limit = usd_hour(settings, line)
    spent = spent_since(store, float(now) - 3600.0)
    paused = spent >= limit
    return {"limit_usd_per_hour": round(limit, 6), "spent_last_hour_usd": round(spent, 6), "paused": paused,
            "share": float(cfg(settings)["pace_share"]),
            "reason": (f"the equity lanes spent ${spent:.4f} on models in the last hour, at their ${limit:.4f} pace "
                       "(elane.e2.pace_share of the Sail model line)" if paused else None)}


#: Why E2 asks no model once its day's line is spent (`hold`; the rounds' skip text).
DAY_SPENT = "E2's model dollars for the day are spent (elane.e2.usd_day)"


def hold(store: Any, settings: Mapping[str, Any] | None, now: float) -> str | None:
    """Why E2 may ask no model now, or None: THE DAY'S LINE is spent (`DAY_SPENT`), or E2 is at ITS HOURLY PACE. Read
    before every model call of E2's (the equity pass, a Train write, a review or audit read)."""
    if room(store, settings, now) <= 0:
        return DAY_SPENT
    return pace(store, settings, now)["reason"]


# ------------------------------------------------------------------------------------------------------------ the yield
def train_counts(store: Any, train_key: str) -> dict[str, dict[str, int]]:
    """Per birth route: the E2 families born, Train-scored and Train-passed (Train facts only: E2's own record)."""
    out: dict[str, dict[str, int]] = {}
    for fam in elane_seal.equity_families(store):
        spec = fam.get("spec") or {}
        key = spec.get(ROUTE_KEY) if isinstance(spec, Mapping) else None
        if not key:
            continue
        rec = elane_seal.e2_record(fam, train_key)
        row = out.setdefault(str(key), {"families": 0, "train_scored": 0, "train_passes": 0})
        row["families"] += 1
        versions = rec.get("versions") if isinstance(rec.get("versions"), Mapping) else {}
        row["train_scored"] += int(bool(versions))
        row["train_passes"] += int(rec.get("passed_version") is not None)
    return out


def choose(store: Any, settings: Mapping[str, Any] | None, candidates: Sequence[Route], *, turn: int,
           train_key: str) -> tuple[Route | None, str]:
    """THE ROUTE CHOICE (the module docstring) among `candidates` (`routes`): (the route, why). Reads the ledger's
    dollars, birth requests and births and E2's Train passes only."""
    if not candidates:
        return None, "no route is configured or served"
    c = cfg(settings)
    rows = ledger(store)["routes"]
    passes = train_counts(store, train_key)

    def usd(r: Route) -> float:
        return float(rows.get(r.key, {}).get("usd") or 0.0)

    def births(r: Route) -> int:
        return int(rows.get(r.key, {}).get("births") or 0)

    def requests(r: Route) -> int:
        return int(rows.get(r.key, {}).get("requests_births") or 0)

    def per_request(r: Route) -> float:
        row = rows.get(r.key, {})
        n = int(row.get("answered_births") or 0)
        return float(row.get("usd_births") or 0.0) / n if n else math.inf

    def sampled(r: Route) -> bool:
        return births(r) >= c["min_births"] or requests(r) >= c["sample_requests"]

    order = {r.key: i for i, r in enumerate(candidates)}
    if all(sampled(r) for r in candidates):
        if turn % (c["explore_every"] * len(candidates)) == c["explore_every"] * len(candidates) - 1:
            pick = min(candidates, key=lambda r: (requests(r), order[r.key]))
            return pick, "exploration: every route keeps being measured (the route with the fewest requests)"
        spent = sum(usd(r) for r in candidates)
        won = sum(passes.get(r.key, {}).get("train_passes", 0) for r in candidates)
        prior = spent / won if won else max(spent, 1.0)  # the pooled dollars a Train pass (no pass yet: all spent so far)

        def key(r: Route) -> tuple:
            p = passes.get(r.key, {}).get("train_passes", 0)
            per_birth = births(r) / usd(r) if usd(r) > 0 else math.inf
            return (-(p + 1.0) / (usd(r) + prior), -per_birth, per_request(r), order[r.key])
        best = min(candidates, key=key)
        return best, "the most Train passes per dollar, smoothed (every route has its sample)"
    if turn % c["explore_every"] == c["explore_every"] - 1:
        under = [r for r in candidates if not sampled(r)]
        pick = min(under, key=lambda r: (births(r), requests(r), order[r.key]))
        return pick, f"exploration: the route furthest from its sample of {c['min_births']} births"
    bore = [r for r in candidates if births(r) > 0]
    if bore:
        pick = min(bore, key=lambda r: (per_request(r), order[r.key]))
        return pick, "the cheapest route that has produced births"
    return candidates[0], "no route has produced a birth yet: the first of the list"


def report(store: Any, settings: Mapping[str, Any] | None, *, train_key: str) -> dict[str, Any]:
    """THE RECORD for the operator (ops): each route's ledger row with its Train counts and, read from E1's family
    state, its Validation entries, looks, looks passed and live programs; and the yield per dollar. Never shown to an
    agent (A9 D3)."""
    book_ = ledger(store)
    counts = train_counts(store, train_key)
    later: dict[str, dict[str, int]] = {}
    for fam in elane_seal.equity_families(store):
        spec = fam.get("spec") or {}
        key = spec.get(ROUTE_KEY) if isinstance(spec, Mapping) else None
        if not key:
            continue
        state = fam.get("state") or {}
        row = later.setdefault(str(key), {"validation_entries": 0, "looks": 0, "looks_passed": 0, "live": 0})
        tried = state.get(TRY_KEY) if isinstance(state.get(TRY_KEY), Mapping) else {}
        row["validation_entries"] += int(bool(tried.get("entered")))
        look = state.get(LOOK_KEY) if isinstance(state.get(LOOK_KEY), Mapping) else None
        if look is not None:
            row["looks"] += 1
            verdict = look.get("verdict")
            passed = (verdict.get("passed") if isinstance(verdict, Mapping) else
                      verdict in (True, "pass", "passed"))
            row["looks_passed"] += int(passed is True)
        row["live"] += int(fam.get("band") in LIVE_BANDS and not fam.get("retired_at"))
    out: dict[str, Any] = {}
    review = {k: dict(v) for k, v in book_["routes"].items() if k.startswith(REVIEW_PREFIX)}
    for key in sorted((set(book_["routes"]) - set(review)) | set(counts) | set(later)):
        row = {**_row(), **book_["routes"].get(key, {}), **{"families": 0, "train_scored": 0, "train_passes": 0},
               **counts.get(key, {}), **{"validation_entries": 0, "looks": 0, "looks_passed": 0, "live": 0},
               **later.get(key, {})}
        spend = float(row["usd"] or 0.0)
        row["per_usd"] = {name: (round(row[name] / spend, 6) if spend > 0 else None)
                          for name in ("births", "train_passes", "validation_entries", "looks_passed", "live")}
        out[key] = row
    return {"routes": out, "review": review, "turn": book_["turn"], "days": book_["days"], "usd_day": cfg(settings)["usd_day"],
            "day_line": round(day_line(settings), 6), "pace_share": cfg(settings)["pace_share"],
            "usd_hour": round(usd_hour(settings), 6),
            "rule": "the route choice reads births, dollars and Train passes only (A9 D3)"}


# ------------------------------------------------------------------------------------------------------------ the call
def ask_on(router: Any, route: Route, *, role: str, system: str, user: str, key: str, max_output: int, effort: str,
           family: str | None = None) -> dict[str, Any]:
    """One question on exactly one route (no fallback inside the router): Sail with no paid route before it, OpenAI with
    no Sail after it, Claude for its role with nothing after it."""
    common = {"role": role, "system": system, "user": user, "family": family, "key": key, "max_output": int(max_output),
              "effort": effort, "need_usd": 1.0}
    if route.kind == "sail":
        return router.ask(openai_model=None, sail_profile=route.name, claude=False, **common)
    if route.kind == "openai":
        return router.ask(openai_model=route.name, sail_profile=None, claude=False, **common)
    if route.kind == "claude":
        return router.ask(openai_model=None, sail_profile=None, claude=True, **{**common, "role": route.name})
    raise ValueError(f"unknown route {route.key}")


#: The Provider's errors after which Sail may have run (and billed) a call whose answer never came back
#: (league/swarm/models.py `ModelRouter.UNCONFIRMED`): the question was SENT.
UNCONFIRMED = ("provider_poll_timeout", "provider_transport_timeout", "provider_transport_unconfirmed")
#: The mark `ask` puts first in its errors when a call failed after it was sent (`unsent` reads it).
SENT_UNANSWERED = "sent and unanswered"


def booked_for(store: Any, call_key: str, since: float = 0.0) -> float:
    """What the swarm booked for one request key of E2's (its window fallback's key included: it keeps the prefix) since
    `since` (seconds; the rows of a call just made are recent, and the table's index is by kind and time): the hold of
    a call that failed after it was sent, or its settled cost. 0 for a store with no spend table (a fake)."""
    try:
        row = store._one(f"SELECT COALESCE(SUM(usd),0) AS usd FROM spend WHERE kind IN ({','.join('?' * len(SPEND_KINDS))}) "
                         "AND epoch>=? AND instr(detail, ?) > 0", (*SPEND_KINDS, float(since), ':"' + str(call_key)[:120]))
    except Exception:  # noqa: BLE001 - nothing to read: nothing known
        return 0.0
    return max(0.0, float(row["usd"])) if row else 0.0


def unsent(errors: Sequence[str]) -> bool:
    """Whether `ask`'s errors say no call was left in flight (False once one failed after it was sent)."""
    return not any(str(e).startswith(SENT_UNANSWERED) for e in errors)


def ask(router: Any, store: Any, settings: Mapping[str, Any] | None, *, first: Route | None, role: str, system: str,
        user: str, key: str, max_output: int, effort: str, purpose: str, now: float,
        family: str | None = None, candidates: Sequence[Route] | None = None,
        book_as: Any = None, accept: Any = None) -> tuple[dict[str, Any] | None, Route | None, list[str]]:
    """Ask on `first` (when it is a route of the list now), then (on a failure) on each other route of the list in
    order; every attempt is booked. (the answer, the route that gave it, the errors); (None, None, errors) when no
    route answered. `candidates`: another list than `routes` (the equity review's); `book_as(route)`: the ledger row
    its dollars go to (the review's "review:<route>"), else the route's own. `accept(route)`: whether the route that
    ANSWERED may be this question's reader (the audit: never the reviewer's model, wherever the router's window
    fallback took the call); an answer it refuses is booked to the route that gave it and the next route is asked.

    A FAILED CALL IS BOOKED AT WHAT THE SWARM BOOKED FOR IT (`booked_for`: the hold of a call that was sent and never
    answered), so the route's row and E2's day carry it. A CALL THAT FAILED AFTER IT WAS SENT (an `UNCONFIRMED` error,
    or a hold booked for its key) ENDS THE QUESTION: Sail may still run and bill it, so no other route is asked the
    same question on top of it; the errors begin with `SENT_UNANSWERED` (`unsent`) and the asker backs off."""
    candidates = list(candidates) if candidates is not None else routes(settings, router)
    row_of = book_as if callable(book_as) else (lambda r: r.key)
    first = first if first is not None and any(r.key == first.key for r in candidates) else None
    ordered = ([first] if first is not None else []) + [r for r in candidates if first is None or r.key != first.key]
    errors: list[str] = []
    for route in ordered:
        call_key = f"{key}:{route.key}"
        try:
            answer = ask_on(router, route, role=role, system=system, user=user, key=call_key,
                            max_output=max_output, effort=effort, family=family)
        except Exception as exc:  # noqa: BLE001 - the next route answers; the failure is booked
            billed = sum(_num(b.get("cost_usd")) or 0.0 for b in getattr(exc, "billed", []) or [] if isinstance(b, Mapping))
            said = billed + max(0.0, _num(getattr(exc, "held_usd", 0.0)) or 0.0)
            held = booked_for(store, call_key, since=float(now) - 6 * 3600.0)
            book(store, row_of(route), usd=max(said, held), known=held <= said, purpose=purpose, answered=False, now=now)
            text = f"{type(exc).__name__}: {str(exc)[:200]}"
            errors.append(f"{route.key}: {text}")
            if held > 0 or any(code in f"{getattr(exc, 'code', '')} {text}" for code in UNCONFIRMED):
                errors.insert(0, f"{SENT_UNANSWERED}: {route.key} may still answer and bill this question; no other "
                                 "route is asked it")
                return None, None, errors
            continue
        answered = route
        moved = answer.get("sail_fallback") if isinstance(answer, Mapping) else None
        if route.kind == "sail" and isinstance(moved, Mapping) and moved.get("to"):
            answered = Route.of(f"sail:{moved['to']}")  # the router's own window fallback answered: booked to it
        usd, known = answer_usd(answer)
        book(store, row_of(answered), usd=usd, known=known, purpose=purpose, answered=True, now=now)
        if callable(accept) and not accept(answered):
            errors.append(f"{route.key}: answered by {answered.key}, which may not read this question")
            continue
        return answer, answered, errors
    return None, None, errors


__all__ = ["LEDGER_KEY", "ROUTE_KEY", "ROLE", "DEFAULTS", "BOUNDS", "REVIEW_PREFIX", "SPEND_MARK", "SPEND_KINDS", "DAY_SPENT",
           "Route", "cfg", "e2_settings", "routes", "served", "ledger", "book",
           "book_births", "next_turn", "spent_since", "spent_today", "model_line", "usd_hour", "day_line", "room", "pace",
           "hold", "answer_usd", "train_counts", "choose", "report", "ask_on", "ask", "booked_for", "unsent", "UNCONFIRMED",
           "SENT_UNANSWERED"]
