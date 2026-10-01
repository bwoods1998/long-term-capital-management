"""The extension hold, the operator's side (R11-4's swarm rule; `league.swarm.researcher.extension_held`).

A Gym family whose latest validation met `researcher.extension_hold_checks` (6) of the line's checks is exempt from the
idle rule's dormancy clause until its 2017-19 extension result lands. The tournament sets the family's `extension_hold`
when such a validation lands, and ends it when a validation of the held version falls below the checks
(`researcher.judge_extension`); the operator clears it once the extension verdict is in, and on the same Gym it is never
set again for the same version. An adoption of a new Gym image or bundle (`league.swarm.evaluator.gym_changed`) clears
that record: the version is held again if it meets the checks on the new Gym, and the operator clears it again once its
extension verdict under that Gym is in. An adoption that changes only league/live keeps it. Runs ON THE HOUSE, from the
release that carries the rule:

    /workspace/.venv/bin/python /workspace/current/scripts/extension_hold.py --state /workspace/state            # list
    /workspace/.venv/bin/python /workspace/current/scripts/extension_hold.py --state /workspace/state --seed [--apply]
    /workspace/.venv/bin/python /workspace/current/scripts/extension_hold.py --state /workspace/state --clear FID ... [--apply]

LIST (the default; read-only): the alive families on hold, and the alive Gym families whose latest validation already met
the checks before the rule shipped but were never held (`--seed` holds them). `--clear FID ...` ends each named family's
hold (its version stays in `extension_versions`, so it is not held again on the same Gym; the state keeps it as
`extension_cleared`). Every write is a dry run unless `--apply`, in one store transaction. Standard library only.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from league.swarm import settings as settings_mod  # noqa: E402
from league.swarm.researcher import checks_met, extension_checks, extension_held, mark_extension  # noqa: E402
from league.swarm.store import SwarmStore  # noqa: E402


def rows(store: SwarmStore, settings: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The alive families on hold, and those whose latest validation met the checks but were never held."""
    need = extension_checks(settings)
    held, unheld = [], []
    for fam in store.families(alive=True):
        state = fam.get("state") or {}
        met, total = checks_met(state.get("validation_line"))
        row = {"family": fam["id"], "band": fam["band"], "version": state.get("validation_version"), "checks": f"{met}/{total}",
               "hold": state.get("extension_hold"), "dormant_cycles": state.get("dormant_cycles")}
        if extension_held(fam):
            held.append(row)
        elif (need > 0 and met >= need and fam["band"] == "gym" and isinstance(state.get("validation_version"), int)
              and state["validation_version"] not in (state.get("extension_versions") or [])):
            unheld.append(row)
    return {"held": held, "never_held": unheld}


def main(argv: list[str] | None = None) -> dict[str, Any]:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--state", default="/workspace/state")
    ap.add_argument("--seed", action="store_true", help="hold the alive families that met the checks before the rule shipped")
    ap.add_argument("--clear", nargs="+", metavar="FID", help="end these families' holds (their extension result landed)")
    ap.add_argument("--apply", action="store_true", help="write (a dry run otherwise)")
    a = ap.parse_args(argv)
    state = Path(a.state)
    settings = settings_mod.load(state)
    write = a.apply and (a.seed or a.clear)
    store = SwarmStore(state, readonly=not write)
    try:
        report: dict[str, Any] = {"mode": "apply" if write else "dry run", "need_checks": extension_checks(settings),
                                  **rows(store, settings)}
        if a.seed:
            report["seed"] = [r["family"] for r in report["never_held"]]
            if write:
                with store.atomic():
                    for r in report["never_held"]:
                        fam = store.family(r["family"]) or {}
                        state_ = fam.get("state") or {}
                        mark_extension(store, r["family"], int(r["version"]), state_.get("validation_line"), settings,
                                       clock=time.time)
        if a.clear:
            report["clear"] = []
            with store.atomic() if write else contextlib.nullcontext():
                for fid in a.clear:
                    fam = store.family(fid)
                    hold = ((fam or {}).get("state") or {}).get("extension_hold")
                    report["clear"].append({"family": fid, "hold": hold, "found": fam is not None})
                    if write and fam is not None and hold:
                        cleared = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                        store.set_state(fid, extension_hold=None, extension_cleared={**dict(hold), "cleared_at": cleared})
        if write:
            report.update(rows(store, settings))
        return report
    finally:
        store.close()


if __name__ == "__main__":
    print(json.dumps(main(), indent=1, default=str))
