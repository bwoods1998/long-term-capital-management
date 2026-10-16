"""THE SEAL OF THE EQUITY LANES (release E2, Oct 2026; amendment A9 D3): what of a share program an agent may read.

A9 D3 (binding): "the look and Validation outcomes of share programs are never fed to generators or the
diagnostician". The equity lanes' generators are the architect's equity pass (league/swarm/elane_births.py) and the
equity Train researcher (league/swarm/elane_train.py); the options architect, the strategist, the options researchers
and the diagnostician are generators too, of the options lanes. This module is the one place that says what crosses:

- TRAIN FACTS ONLY. An equity family is read through `train_facts`: its birth (id, lineage, lane and label, agenda
  mechanism, symbols, structure, mechanism words) and E2's own Train record (`elane_train.STATE_KEY`: each version's
  equity-v1 verdict on the Train years, and whether E2 refuted it on Train). Never its band, its retirement, its
  `validated_version`, `best_validation`, any state key in `SEALED_KEYS` (E1's try, look, floor, Train-r series and
  sigma, the options validation views, the seat rule's two counts), a look row, a forward record or a graveyard
  lesson someone else wrote.
- THE GRAVEYARD THE EQUITY GENERATORS READ is E2's own: the families E2 itself refuted on Train (`elane_train`), from
  its record, in its own words. The graveyard TABLE's rows of equity families (a retirement after a failed look writes
  one, with the options code's "best validation" words) reach no generator: `without_equity_rows` drops them from
  every graveyard read an options generator makes (league/swarm/architect.py: the digest, the 20 newest rows, the ids
  a proposal may cite, and the options rebirth index through `Architect.unseen`; league/swarm/researcher.py: the
  `graveyard` tool). The equity births' own rebirth index (league/swarm/elane_births.py `rebirth_index`) excludes
  every equity family but those E2 refuted on Train. The reader this release may not edit (league/swarm/game.py
  `visible_graveyard`, which the strategist and the diagnostician read) has its patch in ELANE_E2_PATCHES.md (4).
- THE RESERVE (A15): 2020-2021 is not Train for E2. E2 runs programs over the Train spans 2016-2019 and 2022-2024
  only (league/swarm/elane_train.py `TRAIN_SPANS`), and a result carrying a row of 2020 or 2021 is refused whole as
  one of 2025 or 2026 is (`elane_train.outside_years`), so no reserve session is run or scored and no 2020-2021
  figure or P&L reaches a family's record, the Train map, the yield ledger or any generator. WHAT THIS IS NOT: a seal
  of the reserve's BARS. On E1's runner the 2022-2024 run reads the bars before 2022-01-03 as look-back (NEEDS
  `history` + 1 sessions, up to `league.equity.config.MAX_HISTORY` + 1), so the 2022-2024 Train figures of a program
  with look-back, the sums and the pooled t they enter, and the Train map's best t are functions of reserve bars (two
  markets that differ only in 2020-2021 can give such a program other 2022-2024 rows; its 2016-2019 rows are the
  same). Even a program with no look-back reads the last 2021 session (the run's first decision is at its close):
  one reserve bar is in every program's 2022-2024 slice. Blanking the look-back before 2022-01-03 would
  need a hook in E1's runner or store and would cost a long-look-back program most of 2022: the captain's call when
  the reserve's accessor is built.
- THE HIDDEN YEAR (release E3; league/swarm/elane_folds.py, elane_memory.py): a family's hidden Train year is never a
  session of its Train runs, and its results reach no generator, its own researcher included: `elane_memory` and ops
  alone read the tables that hold them (`SEALED_TABLES`). Its bars reach the stretch that follows it as look-back, as
  the reserve's do (league/tests/test_elane_memory_seal.py holds the record, the brief, the Train map, the route
  choice and the stored runs byte for byte the same in two markets that differ only inside the hidden year).
- INVARIANCE IS THE TEST. Two stores that differ only in what happened to share programs after Train (a Validation
  try passed or failed, a look passed or failed, a band, a retirement after the look, a look row, a graveyard row with
  an outcome lesson) give the equity request, the researcher's brief and the route choice byte for byte the same
  (league/tests/test_elane_e2_seal.py). For the reserve the tests say what holds and no more: E2 asks the runner for
  the two Train spans only and keeps no reserve row, figure or day, whatever the reserve's P&L would have been
  (test_elane_e2_seal.py, an invented runner with no look-back); on E1's runner no reserve session is run, a program
  without look-back holds one reserve bar (the last 2021 session) and, holding no price against another, has the same
  figures of its own in two markets that differ only in 2020-2021 (the buy-and-hold beside its 2022 is measured from
  that bar's close and moves), and one with look-back differs in 2022-2024 only (test_elane_e2_e1.py).

Why E2 cares beyond the rule: a generator that sees which programs passed the sealed look learns the holdout, and
the screen's false-positive cap per program (the pinned share screen S2's `fp_cap`, amendment A11; S1-R's before it)
holds only for programs written blind to it.

Standard library only.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping, Sequence

from ..equity import BETA, EQUITY, LANES

#: The family-state keys no generator reads of an equity family (E1's and the options code's outcome records, and,
#: since release E5-A, the seat rule's two counts, `elane_seat`: K is written beside the look, so its presence alone
#: says a look passed, and its counts hold the Validation year's activity; league/tests/test_equity_seats_seal.py
#: holds every generator's reads to the same bytes whatever the counts are).
SEALED_KEYS = frozenset({
    "elane_try", "elane_look", "elane_floor", "elane_train_r", "validation_r_sd_by_version", "validation_r_sd",
    "banded_evaluator", "validation_line", "validation_numbers", "validation_view", "validation", "gate_ready",
    "gate_hold", "look_inflight", "look", "holdout", "forward", "band_reason", "submitted_run", "elane_seat",
    # RELEASE E4, THE PANEL (league/swarm/elane_xs.py `SEALED`; a test holds the two equal): the program's floor, its
    # two Train series (the lineage rule's), the pre-check's record, the Train placebo ranks, the halves' figures, the
    # hidden run and the look. A panel family's Train record is read through `elane_xs.train_facts` only.
    "elane_xs_floor", "elane_xs_train_x", "elane_xs_train_u", "elane_xs_precheck", "elane_xs_placebo",
    "elane_xs_halves", "elane_xs_oof", "elane_xs_look",
    # THE FORWARD SCREEN (FWD1-R; league/swarm/elane_forward.py `STATE_KEY`, a test holds the two equal): a forward
    # pass made eligible for a seat says how the forward sessions went.
    "elane_forward",
    # (step two: K's Train-era half of a passing panel version, `elane_xs.ACTIVITY_KEY`)
    "elane_xs_activity",
    # POOL1 (A55a; league/swarm/elane_forward.py `POOL_KEY`, a test holds the two equal): a pooled seat's record (P2
    # writes it) says how a cell's forward sessions went.
    "elane_pool",
})
#: The family columns no generator reads of an equity family.
SEALED_COLUMNS = frozenset({"band", "band_since", "retired_at", "retire_reason", "validated_version", "best_validation",
                            "validations", "weight"})
#: The swarm store's tables no generator reads (release E3): a hidden year's out-of-fold contribution and its daily
#: series. Named only here, in `elane_memory` and in league/ops/.
SEALED_TABLES = frozenset({"mem_contrib", "mem_series"})


def lane_of_spec(spec: Any) -> str | None:
    """"beta" | "equity" for a family spec of an equity lane (its `lane`), else None."""
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except (TypeError, ValueError):
            return None
    lane = spec.get("lane") if isinstance(spec, Mapping) else None
    return lane if lane in LANES else None


def equity_ids(store: Any) -> frozenset[str]:
    """Every family of an equity lane, alive or retired (its spec's `lane`). A read that fails raises: the callers fail
    closed (they show no row rather than an unfiltered one)."""
    rows = store._all("SELECT id, spec FROM families WHERE spec LIKE '%\"lane\"%'")
    return frozenset(str(r["id"]) for r in rows if lane_of_spec(r.get("spec")) is not None)


def without_equity_rows(store: Any, rows: Sequence[Mapping[str, Any]], *, key: str = "family") -> list[Any]:
    """`rows` less those of an equity-lane family (by `key`). An options generator's graveyard read goes through this:
    no equity row, Train-refuted or not, reaches an options generator, and none with an outcome lesson reaches any."""
    rows = list(rows)
    if not rows:
        return rows
    hidden = equity_ids(store)
    if not hidden:
        return rows
    return [r for r in rows if str((r or {}).get(key) if isinstance(r, Mapping) else r) not in hidden]


def equity_families(store: Any, *, alive: bool | None = None) -> list[dict[str, Any]]:
    """The equity-lane families (`SwarmStore.families(alive=..., lanes=LANES)`, E1's filter; a store without the `lanes`
    keyword is filtered here by the spec's lane, which is the same set)."""
    try:
        fams = store.families(alive=alive, lanes=LANES)
    except TypeError:
        fams = store.families(alive=alive)
    return [f for f in fams if lane_of_spec(f.get("spec")) is not None]


def e2_record(fam: Mapping[str, Any] | None, key: str) -> dict[str, Any]:
    """E2's own Train record of a family (its state's `key`), a dict ({} for none)."""
    state = (fam or {}).get("state") or {}
    value = state.get(key) if isinstance(state, Mapping) else None
    return dict(value) if isinstance(value, Mapping) else {}


def train_facts(fam: Mapping[str, Any], key: str) -> dict[str, Any]:
    """The only fields of an equity family a generator may read (the module docstring): its birth and E2's Train
    record under `key` (`elane_train.STATE_KEY`). Never a field of `SEALED_COLUMNS` or a state key of `SEALED_KEYS`."""
    spec = fam.get("spec") if isinstance(fam.get("spec"), Mapping) else {}
    lane = lane_of_spec(spec)
    symbols = [str(s) for s in (spec.get("symbols") or fam.get("roots") or [])]
    return {"id": str(fam.get("id")), "lineage": str(fam.get("lineage") or fam.get("id")), "lane": lane,
            "agenda": str(spec.get("agenda") or "other"), "symbols": symbols, "structure": str(fam.get("structure") or ""),
            "mechanism": " ".join(str(fam.get("mechanism") or "").split()), "born_at": str(fam.get("born_at") or ""),
            "route": str(spec.get("e2_route") or ""), "record": e2_record(fam, key)}


def lineages_of(store: Any, fid: str) -> list[str]:
    """The lineages a family's tries and looks count over (`SwarmStore.lineages`: linked lineages and the priors)."""
    try:
        return list(store.lineages(fid))
    except Exception:  # noqa: BLE001 - its own lineage at least
        fam = store.family(fid) or {}
        return [str(fam.get("lineage") or fid)]


def families_in(store: Any, lines: Iterable[str]) -> list[dict[str, Any]]:
    """Every family (alive or retired) of the given lineages."""
    lines = sorted({str(x) for x in lines if x})
    if not lines:
        return []
    rows = store._all(f"SELECT id FROM families WHERE lineage IN ({','.join('?' * len(lines))})", tuple(lines))
    out = []
    for r in rows:
        fam = store.family(str(r["id"]))
        if fam is not None:
            out.append(fam)
    return out


__all__ = ["SEALED_KEYS", "SEALED_COLUMNS", "SEALED_TABLES", "lane_of_spec", "equity_ids", "without_equity_rows",
           "equity_families", "e2_record", "train_facts", "lineages_of", "families_in", "BETA", "EQUITY", "LANES"]
