"""RESEARCH DOLLARS BY MEASURED YIELD (Oct 15, 2026): the dlane report's `lane_yield` section.

The owner's goal asks the floor to "choose by measured yield per dollar" (item 2), to report a daily funnel of births,
runs, Validations, looks, live programs and real trades within the research line (item 3), and to "evolve generators by
measured yield per dollar" and "report compounding metrics" (item 8). The report already says each lane's funnel
(`funnel`), the swarm's spend by meter (`costs`) and the equity routes' own ledger (`equity_yield`); nothing said what a
research dollar of each lane bought. This section does, for the report's windows (24 h and 7 days), from the House's own
records only, read-only:

THE DOLLARS (`spend`): the swarm's BOOKED spend rows (the `spend` table, as `costs` reads it: holds for unanswered calls
and their later true-ups included), each given to ONE of four research groups by what the row itself says, never by a
guess about its purpose:
- "equity_lanes" (the BETA and EQUITY lanes' share programs) and "panel" (the stock panel, release E4): a row whose
  request key begins "swarm:elane:" (E2's births, Train revisions, review and audit; "swarm:elane:xs:" is the panel's),
  or whose family is an equity-lane family (a panel family is one whose structure is "panel");
- "alpha" and "direction" (the OPTIONS lanes): a row whose family is an options family, by its declared lane (the
  report's `Lanes`, the funnel's reading).
Rows no family owns are SHARED POOLS, each named, and each given to the groups it serves by a stated rule
(`ALLOCATION`), never hidden:
- "gym_boxes" (the `gym_box` rows: the Gym's boxes run only options programs; an equity Train run is on the House, no
  box) by each options lane's Gym evaluations in the window;
- "options_architect" and "options_strategist" (keys "swarm:architect:" and "swarm:strategist:") by each options lane's
  births in the window (by its Gym evaluations when it bore none);
- "equity_births" (key "swarm:elane:births:": a births pass bears share programs and panel families alike) by the
  window's equity births of each group;
- "harness" (every other row: the engineer, a postmortem, anything this reader does not know) is NOT allocated: it is
  said beside, with its dollars, so the groups' dollars never hide it and never carry it.
A pool with nothing in the window to divide it by stays unallocated and is said so (`unallocated`).
Each group's dollars are also split by route (`by_route`: "sail:<profile>", "gym_box", "claude", "openai"), from the
row's own kind and its detail's profile.

THE YIELD, per group, from the report's own funnel rows of the same window (`funnel`: the same counts the daily page
reads) and the forward record (`forward.sqlite`, read-only: release E3's registry):
- options lanes: births, Gym evaluations, Validation verdicts judged and passed (and, for the direction lane, those
  that entered the gate), holdout looks taken and passed, moves to Probe, real opens and real closes;
- equity lanes: births (the panel's apart), Train and Validation runs on the House, looks taken and passed, moves to
  Probe, real opens and closes, and THE FORWARD SUPPLY: programs registered in the forward record in the window and the
  lineages first registered in it (each lineage is one future FWD1-R verdict: league/ops/forward_screen.py);
- the panel: its births and its forward registrations (a panel row's `ugroup` begins "panel:").
`per_usd` is each count over the group's dollars (allocated pools included), `usd_per` the dollars over each count;
None where a side is zero. A count the funnel does not hold for a group is not invented: it is absent.

WHAT THIS IS NOT. It moves no money, edits no setting and gates nothing: an operator's reading (the report is
operator-only). No generator, screen or route choice reads it (league/swarm imports no ops module: E3's seal); the
equity route choice stays `elane_yield.choose` on Train facts alone (A9 D3). The dollars are the swarm's booked ones,
the `costs` basis; the account's Net after costs is `net_after_costs`.

Standard library only.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

#: The research groups, in report order. The options lanes are the swarm's (league/swarm/dlane.py ALPHA, DIRECTION).
OPTIONS = ("alpha", "direction")
EQUITY = "equity_lanes"
PANEL = "panel"
GROUPS = (*OPTIONS, EQUITY, PANEL)
#: The shared pools and the rule each is divided by (said in the section, beside the figures).
POOLS = ("gym_boxes", "options_architect", "options_strategist", "equity_births", "harness")
ALLOCATION = {
    "gym_boxes": "the options lanes, by each one's Gym evaluations in the window (an equity Train run uses no box)",
    "options_architect": "the options lanes, by each one's births in the window (by its Gym evaluations with none)",
    "options_strategist": "the options lanes, by each one's births in the window (by its Gym evaluations with none)",
    "equity_births": "the equity groups, by each one's births in the window (all to the share programs with none)",
    "harness": "not allocated: the engineer, a postmortem and every row this reader does not know, said beside",
}
#: The request-key marks a spend row's detail carries (league/swarm/models.py books `key`, a hold's `hold`, a true-up's
#: `settles` or a release's `releases`), and the prefixes this reader knows.
KEY_FIELDS = ("key", "hold", "settles", "releases")
PANEL_PREFIX = "swarm:elane:xs:"
EQUITY_BIRTHS_PREFIX = "swarm:elane:births:"
EQUITY_PREFIX = "swarm:elane:"
ARCHITECT_PREFIX = "swarm:architect"
STRATEGIST_PREFIX = "swarm:strategist"
#: The equity lanes (league.equity.LANES) and the panel's structure (league/swarm/elane_xs.py STRUCTURE), repeated so
#: this reader imports nothing of the swarm at import time (a test holds them equal).
EQUITY_LANES = ("beta", "equity")
PANEL_STRUCTURE = "panel"
#: The forward registry's panel group mark (league/ops/forward_xs.py: a panel row's `ugroup` is "panel:<panel>").
PANEL_UGROUP = "panel:"
FORWARD_DB = "forward.sqlite"
BASIS = ("the swarm's BOOKED research spend (`spend` rows, as `costs` reads them); every row given to one group by its "
         "own request key or family, the shared pools by the rules in `allocation`; the counts are the funnel's of the "
         "same window and the forward record's registry")


def _loads(text: Any, default: Any) -> Any:
    if isinstance(text, (dict, list)):
        return text
    try:
        return json.loads(text) if isinstance(text, (str, bytes)) else default
    except (TypeError, ValueError):
        return default


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def request_key(detail: Any) -> str:
    """The request key a spend row's detail names ("" for none)."""
    detail = _loads(detail, {})
    if not isinstance(detail, Mapping):
        return ""
    for field in KEY_FIELDS:
        value = detail.get(field)
        if isinstance(value, str) and value:
            return value
    return ""


def route_of(kind: Any, detail: Any) -> str:
    """A spend row's route: "sail:<profile>" for a Sail model row with a profile, else its kind ("gym_box", "claude",
    "openai", "sail_model")."""
    kind = str(kind or "")
    detail = _loads(detail, {})
    profile = detail.get("profile") if isinstance(detail, Mapping) else None
    if kind == "sail_model" and isinstance(profile, str) and profile:
        return f"sail:{profile}"
    return kind or "unknown"


class Families:
    """Each family's research group, read once a family: an equity-lane family (its spec's `lane`) is "panel" when its
    structure is "panel", else "equity_lanes"; any other family is its declared options lane (`lane_of`: the report's
    `Lanes.of`), "alpha" for a lane this reader does not know."""

    def __init__(self, store: Any, lane_of: Callable[..., str]):
        self.lane_of = lane_of
        self.rows: dict[str, dict[str, Any]] = {}
        for row in store._all("SELECT id, structure, spec FROM families"):
            spec = _loads(row.get("spec"), {})
            self.rows[str(row["id"])] = {"id": row["id"], "structure": row.get("structure"),
                                         "spec": spec if isinstance(spec, Mapping) else {}}
        self.cache: dict[str, str] = {}

    def group(self, fid: Any) -> str | None:
        """The family's group, or None for no such family."""
        fid = str(fid or "")
        if not fid or fid not in self.rows:
            return None
        if fid not in self.cache:
            fam = self.rows[fid]
            if fam["spec"].get("lane") in EQUITY_LANES:
                self.cache[fid] = PANEL if str(fam.get("structure") or "") == PANEL_STRUCTURE else EQUITY
            else:
                try:
                    lane = str(self.lane_of(fid, fam))
                except Exception:  # noqa: BLE001 - an unreadable lane is the lane's default
                    lane = OPTIONS[0]
                self.cache[fid] = lane if lane in OPTIONS else OPTIONS[0]
        return self.cache[fid]


def classify(kind: Any, family: Any, detail: Any, families: Families) -> tuple[str, str]:
    """("group", name) for a row one group owns, or ("pool", name) for a shared pool (the module docstring)."""
    if str(kind or "") == "gym_box":
        return "pool", "gym_boxes"
    key = request_key(detail)
    owner = families.group(family) if family else None
    if key.startswith(PANEL_PREFIX):
        return "group", PANEL
    if key.startswith(EQUITY_BIRTHS_PREFIX):
        return "pool", "equity_births"
    if key.startswith(EQUITY_PREFIX):
        return "group", PANEL if owner == PANEL else EQUITY
    if key.startswith(ARCHITECT_PREFIX):
        return "pool", "options_architect"
    if key.startswith(STRATEGIST_PREFIX):
        return "pool", "options_strategist"
    if owner is not None:
        return "group", owner
    return "pool", "harness"


def spend(store: Any, families: Families, since_epoch: float) -> dict[str, Any]:
    """The window's booked dollars: {"groups": {group: usd}, "pools": {pool: usd}, "by_route": {group or pool: {route:
    usd}}, "rows": n}."""
    groups = {g: 0.0 for g in GROUPS}
    pools = {p: 0.0 for p in POOLS}
    by_route: dict[str, dict[str, float]] = {}
    n = 0
    for row in store._all("SELECT kind, family, usd, detail FROM spend WHERE epoch>=?", (float(since_epoch),)):
        usd = _num(row.get("usd"))
        if usd is None:
            continue
        n += 1
        side, name = classify(row.get("kind"), row.get("family"), row.get("detail"), families)
        (groups if side == "group" else pools)[name] += usd
        route = route_of(row.get("kind"), row.get("detail"))
        by_route.setdefault(name, {})
        by_route[name][route] = by_route[name].get(route, 0.0) + usd
    return {"groups": groups, "pools": pools, "by_route": by_route, "rows": n}


def _total(value: Any) -> int:
    """A funnel count: an int, or the sum of a dict's ints (Gym runs by window, real opens by route)."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return int(value)
    if isinstance(value, Mapping):
        return sum(_total(v) for v in value.values() if not isinstance(v, Mapping))
    return 0


def _get(row: Mapping[str, Any], *path: str) -> Any:
    for key in path:
        row = row.get(key) if isinstance(row, Mapping) else None
    return row


def panel_births(store: Any, since_iso: str) -> int:
    """The window's panel births (`swarm.born` events whose payload's structure is the panel's)."""
    n = 0
    for row in store._all("SELECT payload FROM events WHERE kind='swarm.born' AND at>=?", (since_iso,)):
        payload = _loads(row.get("payload"), {})
        if isinstance(payload, Mapping) and payload.get("lane") in EQUITY_LANES \
                and payload.get("structure") == PANEL_STRUCTURE:
            n += 1
    return n


def forward_supply(root: str | Path | None, since_epoch: float) -> dict[str, Any]:
    """The forward record's registrations in the window (`forward.sqlite`, read-only), by group: {"equity_lanes":
    {"registered", "lineages"}, "panel": {...}} (the controls left out; a lineage counts in the window of its FIRST
    registration), or {"error": ...} when the record cannot be read; {"missing": True} with no record yet."""
    if root is None:
        return {"error": "no state root"}
    path = Path(root) / FORWARD_DB
    if not path.exists():
        return {"missing": True}
    try:
        from . import guard

        rows = guard.read(path, lambda db: guard.rows(
            db, "SELECT lineage, ugroup, registered_at FROM fwd_registry WHERE reason != 'control' ORDER BY pid"))
    except Exception as exc:  # noqa: BLE001 - the section says it, the report goes on
        return {"error": type(exc).__name__}
    out = {EQUITY: {"registered": 0, "lineages": 0}, PANEL: {"registered": 0, "lineages": 0}}
    seen: set[str] = set()
    for row in rows:
        at = _num(row.get("registered_at"))
        group = PANEL if str(row.get("ugroup") or "").startswith(PANEL_UGROUP) else EQUITY
        lineage = str(row.get("lineage") or "")
        first = lineage not in seen
        seen.add(lineage)
        if at is None or at < since_epoch:
            continue
        out[group]["registered"] += 1
        out[group]["lineages"] += int(first)
    return out


def yields(funnel_window: Mapping[str, Any], panel_born: int, forward: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    """Each group's counts in the window (the module docstring), from the funnel's rows and the forward supply."""
    out: dict[str, dict[str, int]] = {}
    for lane in OPTIONS:
        row = funnel_window.get(lane) if isinstance(funnel_window, Mapping) else None
        row = row if isinstance(row, Mapping) else {}
        counts = {"births": _total(row.get("births")), "gym_runs": _total(row.get("gym_runs")),
                  "validations_judged": _total(_get(row, "validations", "judged")),
                  "validations_passed": _total(_get(row, "validations", "passed")),
                  "looks_taken": _total(_get(row, "looks", "taken")), "looks_passed": _total(_get(row, "looks", "passed")),
                  "to_probe": _total(_get(row, "band_moves", "probe")), "real_opens": _total(row.get("real_opens")),
                  "real_closes": _total(row.get("real_closes"))}
        if isinstance(_get(row, "validations", "entered"), int):
            counts["validations_entered"] = _total(_get(row, "validations", "entered"))
        out[lane] = counts
    rows = [funnel_window.get(lane) for lane in EQUITY_LANES] if isinstance(funnel_window, Mapping) else []
    rows = [r for r in rows if isinstance(r, Mapping)]
    births = sum(_total(r.get("births")) for r in rows)
    equity = {"births": max(0, births - int(panel_born)),
              "train_runs": sum(_total(_get(r, "gym_runs", "train")) for r in rows),
              "validation_runs": sum(_total(_get(r, "gym_runs", "validation")) for r in rows),
              "looks_taken": sum(_total(_get(r, "looks", "taken")) for r in rows),
              "looks_passed": sum(_total(_get(r, "looks", "passed")) for r in rows),
              "to_probe": sum(_total(_get(r, "band_moves", "probe")) for r in rows),
              "real_opens": sum(_total(r.get("real_opens")) for r in rows),
              "real_closes": sum(_total(r.get("real_closes")) for r in rows)}
    panel = {"births": int(panel_born)}
    for group, counts in ((EQUITY, equity), (PANEL, panel)):
        supply = forward.get(group) if isinstance(forward, Mapping) else None
        if isinstance(supply, Mapping):
            counts["forward_registered"] = int(supply.get("registered") or 0)
            counts["forward_lineages"] = int(supply.get("lineages") or 0)
    out[EQUITY], out[PANEL] = equity, panel
    return out


def _shares(weights: Mapping[str, float]) -> dict[str, float] | None:
    total = sum(max(0.0, float(w)) for w in weights.values())
    if total <= 0:
        return None
    return {k: max(0.0, float(w)) / total for k, w in weights.items()}


def allocate(dollars: Mapping[str, Any], counts: Mapping[str, Mapping[str, int]]) -> dict[str, Any]:
    """Each group's dollars with the shared pools divided by `ALLOCATION`: {"usd": {group: usd}, "direct": {group: usd},
    "pools": {pool: {"usd", "to": {group: usd} | None}}, "unallocated_usd"}."""
    direct = {g: float(dollars["groups"].get(g, 0.0)) for g in GROUPS}
    usd = dict(direct)
    births = {lane: counts[lane]["births"] for lane in OPTIONS}
    gym = {lane: counts[lane]["gym_runs"] for lane in OPTIONS}
    rules = {"gym_boxes": _shares(gym), "options_architect": _shares(births) or _shares(gym),
             "options_strategist": _shares(births) or _shares(gym),
             "equity_births": _shares({EQUITY: counts[EQUITY]["births"], PANEL: counts[PANEL]["births"]}) or {EQUITY: 1.0},
             "harness": None}
    pools: dict[str, Any] = {}
    left = 0.0
    for pool in POOLS:
        amount = float(dollars["pools"].get(pool, 0.0))
        share = rules[pool]
        if share is None or not amount:
            pools[pool] = {"usd": round(amount, 4), "to": None}
            left += amount
            continue
        to = {g: amount * s for g, s in share.items()}
        for g, v in to.items():
            usd[g] += v
        pools[pool] = {"usd": round(amount, 4), "to": {g: round(v, 4) for g, v in to.items()}}
    return {"usd": usd, "direct": direct, "pools": pools, "unallocated_usd": left}


def per_dollar(counts: Mapping[str, int], usd: float) -> tuple[dict[str, float | None], dict[str, float | None]]:
    """(each count per dollar, the dollars per count); None where a side is zero."""
    per = {k: (round(v / usd, 4) if usd > 0 else None) for k, v in counts.items()}
    each = {k: (round(usd / v, 4) if v > 0 and usd > 0 else None) for k, v in counts.items()}
    return per, each


def window(store: Any, families: Families, funnel_window: Mapping[str, Any], *, root: str | Path | None, now: float,
           hours: float) -> dict[str, Any]:
    """One window's section: the dollars, the pools and how they were divided, and each group's counts and yields."""
    import time

    since = float(now) - float(hours) * 3600.0
    since_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(since))
    dollars = spend(store, families, since)
    forward = forward_supply(root, since)
    counts = yields(funnel_window, panel_births(store, since_iso), forward)
    money = allocate(dollars, counts)
    groups: dict[str, Any] = {}
    for g in GROUPS:
        per, each = per_dollar(counts[g], money["usd"][g])
        groups[g] = {"usd": round(money["usd"][g], 4), "usd_direct": round(money["direct"][g], 4),
                     "by_route": {r: round(v, 4) for r, v in sorted(dollars["by_route"].get(g, {}).items())},
                     "counts": counts[g], "per_usd": per, "usd_per": each}
    options_usd = sum(money["usd"][g] for g in OPTIONS)
    total = sum(dollars["groups"].values()) + sum(dollars["pools"].values())
    return {"since": since_iso, "hours": float(hours), "usd_total": round(total, 4),
            "usd_options_lanes": round(options_usd, 4),
            "usd_equity_lanes": round(money["usd"][EQUITY] + money["usd"][PANEL], 4),
            "unallocated_usd": round(money["unallocated_usd"], 4), "groups": groups,
            "pools": {p: {**money["pools"][p], "by_route": {r: round(v, 4) for r, v in
                                                           sorted(dollars["by_route"].get(p, {}).items())}}
                      for p in POOLS},
            "forward": forward if isinstance(forward, Mapping) and ("error" in forward or "missing" in forward) else None,
            "rows": dollars["rows"]}


def section(store: Any, lane_of: Callable[..., str], funnels: Mapping[str, Any], *, root: str | Path | None, now: float,
            windows: Mapping[str, float]) -> dict[str, Any]:
    """THE SECTION (the module docstring): {"windows": {name: window}, "allocation", "basis", "note"}. `funnels` is the
    report's own funnel by window name; `windows` its hours by name (the report's `WINDOWS`)."""
    families = Families(store, lane_of)
    out: dict[str, Any] = {}
    for name, hours in windows.items():
        try:
            out[name] = window(store, families, funnels.get(name) or {}, root=root, now=now, hours=hours)
        except Exception as exc:  # noqa: BLE001 - one window that cannot be read is said, the other still reads
            out[name] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    return {"windows": out, "allocation": dict(ALLOCATION), "basis": BASIS,
            "note": ("operator-only: research dollars by group against what they bought (the goal's items 2, 3 and 8); "
                     "no generator, screen or route choice reads it")}


__all__ = ["OPTIONS", "EQUITY", "PANEL", "GROUPS", "POOLS", "ALLOCATION", "request_key", "route_of", "Families",
           "classify", "spend", "panel_births", "forward_supply", "yields", "allocate", "per_dollar", "window", "section"]
