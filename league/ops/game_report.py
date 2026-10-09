"""The `game` job (daily at 00:00Z) and THE LEARNING GAME's report (Oct 8, 2026; league/swarm/game.py and the build spec's
section 7): aggregate and OPERATOR-ONLY. No agent reads it, no rule reads it, and nothing in league/swarm, league/live or
league/gym imports this module.

THE REPORT (`report`), JSON, from `game.metrics` on the swarm store opened READ-ONLY:
- `R1` plumbing (pass or fail, the day-1 read): the leak scan of the game arm's conversations (no hidden year or figure in
  any tool output it was shown), D1 over the founders' looks (the mean of F on the SELECT year less F on the CONFIRM year,
  within 2.5 standard errors: the roles are assigned by a hash, so anything else is a leak, not selection), the hidden
  runs' failure rate (under 5%), and the share of hidden years that were ineligible (flagged above half: the 2020-21 era
  has no daily SPY/QQQ expiries). The non-interference test (R1e) is CI's (league/tests/test_game.py), not this report's.
- `R2` selection carry, both arms (the 1-3 day read): Spearman(F on SELECT, F on CONFIRM) less Spearman(seen score, F on
  CONFIRM) on the same looks.
- `R3` out-of-fold quality of what each arm would send to Validation: the CONFIRM year of the game's SELECT passers
  against control's validated versions, and each arm's gap between its seen F and its CONFIRM F.
- `R4` generation gain: children's CONFIRM F less the founders', by generation, and the SELECT burn meter.
- `R5` flow and cost (the last 24 hours and in all): looks, passes, CONFIRM reads, children by operator and directive,
  the children that beat their founder, the hidden submissions and the day's spend by meter.
- `R6` Validation and money per arm: tries, passes, median t, Spearman(selection score, Validation t), holdout looks and
  passes, Probes.
Intervals are family-cluster bootstraps (`game.BOOT_DRAWS`, 2,000 draws; 90% two-sided; seeded, so the same store gives
the same report). `decisions` reads the spec's pre-registered rules off the figures (`decide`; reported, never acted on:
the operator acts, docs/operations.md THE LEARNING GAME).

THE JOB (`run`): opens the swarm store read-only (`guard.readonly()`: every SQLite open in the child is a `mode=ro` URI)
under the swarm's own settings (`settings.load`), builds the report and writes it atomically to
`<state>/game/report-<day>.json` (the UTC day). A failed R1 is one House warning naming the failed checks (never a
figure). With the game off and no look ever made it writes nothing and says so. `scripts/game_report.py` is the same
report from the command line, on the state root or on a copy.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Mapping

DIR = "game"
#: The spec's pre-registered thresholds (section 7): the day-3 premise check and the day-7 GO-WIDE / REVERT rule.
DAY3_CI_UPPER = 0.05
GO_WIDE = 0.3
REVERT = 0.1


#: THE DIRECTION LANE (release D-1, Oct 9, 2026; the operator's decision 1): what the lane changed mid-way through the
#: game's T0 experiment, in every report while the lane is on, so no reading of R1-R6 across its deploy forgets it.
DIRECTION_LANE_NOTE = {
    "release": "D-1 (league/swarm/dlane.py)",
    "births": "the direction lane takes about half of the births while it is under half of the last 24 hours' (at most "
              "60%): alpha births fall from about 73 to about 36 a day from D-1's deploy, both arms alike",
    "prompt": "the researcher's ROLE prompt (a shared prefix) became lane-aware at D-1's deploy, for alpha researchers of "
              "both arms too: 'alpha golden' holds for code paths only, not for what alpha researchers read",
    "direction": "direction lineages never play the game (dlane.arm_fraction 0) and are kept out of R1(b) and R2",
}


def path_for(root: str | Path, day: str) -> Path:
    """`<state>/game/report-<day>.json`."""
    return Path(root) / DIR / f"report-{day}.json"


def _day(now: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(now))


def _passed(r1: Mapping[str, Any]) -> list[str]:
    """The R1 checks that failed (the leak scan, D1 over the founders, the hidden runs' failure rate)."""
    failed = []
    if not (r1.get("leak") or {}).get("passed", True):
        failed.append("leak")
    if not (r1.get("d1_founders") or {}).get("passed", True):
        failed.append("d1_founders")
    if not (r1.get("failure_rate") or {}).get("passed", True):
        failed.append("failure_rate")
    return failed


def _ci_above(block: Mapping[str, Any], key: str, bar: float) -> bool:
    value, ci = block.get(key), block.get("ci")
    return isinstance(value, (int, float)) and value >= bar and isinstance(ci, list) and len(ci) == 2 and ci[0] > 0


def decide(metrics: Mapping[str, Any], *, days: float | None) -> dict[str, Any]:
    """The spec's pre-registered rules read off `metrics` (section 7), REPORTED ONLY: day 1, R1 fails -> shadow; day 3, the
    selection carry's Delta rho at most 0 with its upper bound under 0.05 -> shadow and stop the reproduction spend; day
    7, G or Delta_sel at least +0.3 with the interval above 0 -> GO-WIDE, both at most +0.1 -> REVERT, else EXTEND (once,
    to day 14). Each rule says "pending" before its day."""
    failed = _passed(metrics.get("R1") or {})
    out: dict[str, Any] = {"days_since_t0": None if days is None else round(days, 3),
                           "R1": {"passed": not failed, "failed": failed,
                                  "action": "set game.mode to shadow and fix the plumbing" if failed else None}}
    r2 = metrics.get("R2") or {}
    rho, ci = r2.get("delta_rho"), r2.get("ci")
    if days is None or days < 3:
        out["day3"] = "pending"
    elif not isinstance(rho, (int, float)):
        out["day3"] = "no figure yet"
    elif rho <= 0 and isinstance(ci, list) and len(ci) == 2 and ci[1] < DAY3_CI_UPPER:
        out["day3"] = "the premise fails: set game.mode to shadow, report, stop the reproduction spend"
    else:
        out["day3"] = "continue"
    r3, r4 = metrics.get("R3") or {}, metrics.get("R4") or {}
    g, sel = r4.get("G"), r3.get("delta_sel")
    if days is None or days < 7:
        out["day7"] = "pending"
    elif _ci_above(r4, "G", GO_WIDE) or _ci_above(r3, "delta_sel", GO_WIDE):
        out["day7"] = "GO-WIDE (Blake approves): arm_fraction 1.0 for new births, plan Stage 2, freeze a GAME_SCREEN_1 receipt"
    elif isinstance(g, (int, float)) and isinstance(sel, (int, float)) and g <= REVERT and sel <= REVERT:
        out["day7"] = "REVERT: game.enabled false"
    else:
        out["day7"] = "EXTEND once to day 14 under the same rule" if days < 14 else "decide (day 14: the rule's last read)"
    return out


def report(root: str | Path, *, settings: Mapping[str, Any] | None = None, now: float | None = None,
           draws: int | None = None, seed: int = 0) -> dict[str, Any]:
    """The report (the module docstring), from the swarm store at `root` opened read-only, under `settings` (the swarm's
    own, `settings.load(root)`, when None)."""
    from ..swarm import game
    from ..swarm import settings as settings_mod
    from ..swarm.store import SwarmStore

    settings = settings if settings is not None else settings_mod.load(root)
    store = SwarmStore(Path(root), readonly=True)
    try:
        now = float(store.clock() if now is None else now)
        c = game.cfg(settings)
        start = game.t0(store)
        metrics = game.metrics(store, settings=settings, now=now, draws=game.BOOT_DRAWS if draws is None else int(draws),
                               seed=seed)
    finally:
        store.close()
    days = None
    if start:
        from datetime import datetime

        days = (now - datetime.fromisoformat(str(start).replace("Z", "+00:00")).timestamp()) / 86400.0
    out = {"day": _day(now), "t0": start, "game": {"enabled": c["enabled"], "mode": c["mode"],
                                                   "arm_fraction": c["arm_fraction"]},
           "draws": game.BOOT_DRAWS if draws is None else int(draws), "seed": seed, "level": game.BOOT_LEVEL,
           "decisions": decide(metrics, days=days), "operator_only": True, **metrics}
    from ..swarm import dlane

    if dlane.on(settings):  # THE DIRECTION LANE (release D-1): what it changed mid-way through the experiment, said here
        out["direction_lane"] = DIRECTION_LANE_NOTE
    return out


# ------------------------------------------------------------------------------------------------- the job
def run(ctx: Any) -> dict[str, Any]:
    from ..swarm import settings as settings_mod
    from . import guard
    from .context import write_json

    root = Path(ctx.root)
    settings = settings_mod.load(root, config=getattr(ctx, "config", None))
    with guard.readonly():
        out = report(root, settings=settings, now=ctx.now())
    if not out["game"]["enabled"] and not out["looks"]:
        return {"ok": True, "skipped": "the learning game is off and has made no look"}
    path = write_json(path_for(root, out["day"]), out)
    failed = out["decisions"]["R1"]["failed"]
    if failed and out["landed"]:
        ctx.alert("warning", f"the learning game: its plumbing check (R1) failed ({', '.join(failed)}): set game.mode to "
                             f"shadow and fix it before reading any look (docs/operations.md, THE LEARNING GAME)")
    return {"ok": True, "path": str(path), "looks": out["looks"], "landed": out["landed"], "r1_failed": failed}


__all__ = ["run", "report", "decide", "path_for", "DIR"]
