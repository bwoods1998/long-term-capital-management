"""YIELD PER DOLLAR OF THE EQUITY LANES' MODEL ROUTES (release E2, Oct 2026; the owner's goal: "Choose models by measured
yield per dollar").

THE RECORD (`record`, `report`; kv `LEDGER_KEY`). One row a model route ("sail:<profile>", "openai:<model>",
"claude:<role>"), kept by the equity pass (league/swarm/elane_births.py) and the equity Train researcher
(league/swarm/elane_train.py), which ask every equity question on ONE route at a time and book its answer here:
- `requests`, `answered`, `failed`; `usd` (the answers' dollars: births and research), `usd_births`, `usd_research`,
  `unknown_cost` (answers whose bill was not known when they landed: their held dollars are booked, else none);
- `births`: the equity families its answers bore (each family remembers its birth route: spec `e2_route`; its Train
  revisions are asked on the same route, so a family's whole cost and yield sit on one row);
- read from the families at report time: `train_scored` (families with a Train-scored version), `train_passes`
  (families with a version that passed equity-v1), and, FOR THE OPERATOR ONLY, `validation_entries` (E1's `elane_try`
  with its pre-check met), `looks`, `looks_passed` (E1's `elane_look`) and `live` (a family now in Probe or Sized).
`report` is what ops reads (league/ops: the dlane report, the funnel); nothing here writes outside the swarm store.

THE ROUTE CHOICE (`choose`), for each equity request (a birth pass) and each new equity family's first program:
1. THE ROUTES are `elane.e2.routes` (default `DEFAULTS["routes"]`: Sail profiles, the cheapest list price first); a
   "claude:<role>" entry is used only while the router serves that role on Claude, an "openai:<model>" entry only
   while it names a model.
2. A route's SAMPLE is `min_births` (10) births.
3. Once EVERY route has its sample: the route with the most Train passes per dollar (passes / usd), ties broken by
   births per dollar, then by the cheaper mean cost a request, then by the list order.
4. Before that, EXPLORATION: every `explore_every`-th request (3; the ledger's `turn`) goes to the route with the
   fewest births among those under their sample (ties: list order), so every route reaches its sample; every other
   request DEFAULTS TO THE CHEAPEST ROUTE THAT HAS PRODUCED BIRTHS (the lowest mean dollars a request among routes with
   a birth), and with none, the first route of the list.
5. A route whose call fails is passed over for that request (the next route of the list answers; the answer is booked
   to the route that gave it).
THE YIELD IS TRAIN PASSES PER DOLLAR, NEVER A LATER STAGE (A9 D3). Validation entries, looks passed and live programs
are recorded for the operator and are never read by `choose`: a route chosen on the sealed look's outcomes would feed
the holdout back into which model writes the next programs. A Train pass is the first stage every route's programs
reach alike, and it is a Train fact. (`choose` is tested to give the same route whatever those outcomes are.)

THE DAY'S LINE (`usd_day`, `room`): E2's model dollars a UTC day (births and Train research together); once spent, no
equity question is asked until the next UTC day. A tightening beside the swarm's own pace and the guard.

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
    "explore_every": 3,
    "usd_day": 8.0,
}
#: Bounds of the numbers above (a value outside is its default).
BOUNDS = {"min_births": (1, 1000), "explore_every": (2, 100), "usd_day": (0.0, 100.0)}
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
    out = []
    for key in cfg(settings)["routes"]:
        route = Route.of(key)
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
    return {"requests": 0, "answered": 0, "failed": 0, "usd": 0.0, "usd_births": 0.0, "usd_research": 0.0,
            "unknown_cost": 0, "births": 0}


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
    """One request on route `key`: its dollars (`purpose` "births" or "research") and whether it was answered."""
    def change(b: dict[str, Any]) -> None:
        row = b["routes"].setdefault(key, _row())
        row["requests"] += 1
        row["answered" if answered else "failed"] += 1
        row["usd"] = round(row["usd"] + usd, 6)
        name = "usd_births" if purpose == "births" else "usd_research"
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


def spent_today(store: Any, now: float) -> float:
    return float(ledger(store)["days"].get(_today(now), 0.0))


def room(store: Any, settings: Mapping[str, Any] | None, now: float) -> float:
    """E2's model dollars left this UTC day (THE DAY'S LINE)."""
    return max(0.0, float(cfg(settings)["usd_day"]) - spent_today(store, now))


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
    dollars and births and E2's Train passes only."""
    if not candidates:
        return None, "no route is configured or served"
    c = cfg(settings)
    rows = ledger(store)["routes"]
    passes = train_counts(store, train_key)

    def usd(r: Route) -> float:
        return float(rows.get(r.key, {}).get("usd") or 0.0)

    def births(r: Route) -> int:
        return int(rows.get(r.key, {}).get("births") or 0)

    def per_request(r: Route) -> float:
        row = rows.get(r.key, {})
        n = int(row.get("answered") or 0)
        return usd(r) / n if n else math.inf

    order = {r.key: i for i, r in enumerate(candidates)}
    sampled = [r for r in candidates if births(r) >= c["min_births"]]
    if len(sampled) == len(candidates):
        def key(r: Route) -> tuple:
            spend = usd(r)
            p = passes.get(r.key, {}).get("train_passes", 0)
            yield_ = p / spend if spend > 0 else (math.inf if p else 0.0)
            per_birth = births(r) / spend if spend > 0 else math.inf
            return (-yield_, -per_birth, per_request(r), order[r.key])
        best = min(candidates, key=key)
        return best, "the most Train passes per dollar (every route has its sample)"
    if turn % c["explore_every"] == c["explore_every"] - 1:
        under = [r for r in candidates if births(r) < c["min_births"]]
        pick = min(under, key=lambda r: (births(r), order[r.key]))
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
    for key in sorted(set(book_["routes"]) | set(counts) | set(later)):
        row = {**_row(), **book_["routes"].get(key, {}), **{"families": 0, "train_scored": 0, "train_passes": 0},
               **counts.get(key, {}), **{"validation_entries": 0, "looks": 0, "looks_passed": 0, "live": 0},
               **later.get(key, {})}
        spend = float(row["usd"] or 0.0)
        row["per_usd"] = {name: (round(row[name] / spend, 6) if spend > 0 else None)
                          for name in ("births", "train_passes", "validation_entries", "looks_passed", "live")}
        out[key] = row
    return {"routes": out, "turn": book_["turn"], "days": book_["days"], "usd_day": cfg(settings)["usd_day"],
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


def ask(router: Any, store: Any, settings: Mapping[str, Any] | None, *, first: Route | None, role: str, system: str,
        user: str, key: str, max_output: int, effort: str, purpose: str, now: float,
        family: str | None = None) -> tuple[dict[str, Any] | None, Route | None, list[str]]:
    """Ask on `first` (when it is a route of the list now), then (on a failure) on each other route of the list in
    order; every attempt is booked. (the answer, the route that gave it, the errors); (None, None, errors) when no
    route answered."""
    candidates = routes(settings, router)
    first = first if first is not None and any(r.key == first.key for r in candidates) else None
    ordered = ([first] if first is not None else []) + [r for r in candidates if first is None or r.key != first.key]
    errors: list[str] = []
    for route in ordered:
        try:
            answer = ask_on(router, route, role=role, system=system, user=user, key=f"{key}:{route.key}",
                            max_output=max_output, effort=effort, family=family)
        except Exception as exc:  # noqa: BLE001 - the next route answers; the failure is booked
            billed = sum(_num(b.get("cost_usd")) or 0.0 for b in getattr(exc, "billed", []) or [] if isinstance(b, Mapping))
            book(store, route.key, usd=billed + max(0.0, _num(getattr(exc, "held_usd", 0.0)) or 0.0), known=True,
                 purpose=purpose, answered=False, now=now)
            errors.append(f"{route.key}: {type(exc).__name__}: {str(exc)[:200]}")
            continue
        answered = route
        moved = answer.get("sail_fallback") if isinstance(answer, Mapping) else None
        if route.kind == "sail" and isinstance(moved, Mapping) and moved.get("to"):
            answered = Route.of(f"sail:{moved['to']}")  # the router's own window fallback answered: booked to it
        usd, known = answer_usd(answer)
        book(store, answered.key, usd=usd, known=known, purpose=purpose, answered=True, now=now)
        return answer, answered, errors
    return None, None, errors


__all__ = ["LEDGER_KEY", "ROUTE_KEY", "ROLE", "DEFAULTS", "BOUNDS", "Route", "cfg", "e2_settings", "routes", "ledger", "book",
           "book_births", "next_turn", "spent_today", "room", "answer_usd", "train_counts", "choose", "report", "ask_on",
           "ask"]
