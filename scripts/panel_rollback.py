"""Before a CODE rollback past release E4: the alive panel families, retired (docs/operations.md, "The panel lane",
Rollback; league/swarm/E4.md section 1).

A release from before E4 knows no panel structure: its `league/swarm/store.py` `OPTIONS_ONLY_SQL` is
"structure NOT IN ('etf', 'stock')", so every options reader of it (the tournament's allocation, the options
population the architect and the idle pass count, the researcher) reads an alive panel family as an OPTIONS family.
Measured on main 8ab31e32 with three panel families in the Gym band: the tournament gave the class "panel x none" half
its allocation and the options population counted the three. No money row moves (a Gym family holds no seat), but the
options lane's research and births would share their room with families its code cannot run. So, in order, while
the E4 release still runs: `elane.panel.mode` "off" (no birth after this), then this script with `--apply`, then the
code rollback. Retired rows stay (append-only); an E4 release deployed again later reads them as retired panel
families.

Runs ON THE HOUSE, from the release that carries it:

    /workspace/.venv/bin/python /workspace/current/scripts/panel_rollback.py --state /workspace/state            # list
    /workspace/.venv/bin/python /workspace/current/scripts/panel_rollback.py --state /workspace/state --apply    # retire

LIST (the default; read-only): the setting `elane.panel.mode` and each alive panel family with its band. `--apply`
retires every one of them in one store transaction (`SwarmStore.retire`, a `swarm.retired` event each), and refuses,
writing nothing, while the setting is not "off" (a family born after the list would be missed) or while any alive
panel family is outside the Gym band (a Candidate or Probe one is the flatten-first rollback's: docs/operations.md,
"Roll back: flatten first"). In step one (at most "train") every panel family is in the Gym band. Standard library
only; it prints JSON, and exits 1 on a refusal.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from league.swarm import elane_xs  # noqa: E402
from league.swarm import settings as settings_mod  # noqa: E402
from league.swarm.store import PANEL_STRUCTURE, SwarmStore  # noqa: E402

#: The reason each retirement records (its `swarm.retired` event's cause).
REASON = ("a code rollback past release E4: a release before it reads an alive panel family as an options family "
          "(scripts/panel_rollback.py)")


def alive_panels(store: SwarmStore) -> list[dict[str, Any]]:
    """The alive panel families, oldest first: {family, band, born_at}."""
    return [{"family": fam["id"], "band": fam["band"], "born_at": fam.get("born_at")}
            for fam in store.families(alive=True, lanes="all") if fam.get("structure") == PANEL_STRUCTURE]


def main(argv: list[str] | None = None) -> dict[str, Any]:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--state", default="/workspace/state")
    ap.add_argument("--apply", action="store_true", help="retire them (a list otherwise)")
    a = ap.parse_args(argv)
    state = Path(a.state)
    setting = elane_xs.cfg(settings_mod.load(state))["mode"]
    store = SwarmStore(state, readonly=not a.apply)
    try:
        report: dict[str, Any] = {"mode": "apply" if a.apply else "list", "setting": setting,
                                  "alive_panel": alive_panels(store), "retired": []}
        if not a.apply:
            return report
        if setting != "off":
            report["refused"] = (f"elane.panel.mode is {setting!r}: set it to 'off' first (set_swarm.py "
                                 "elane.panel.mode=off --apply), so that no panel family is born after this")
            return report
        outside = [row["family"] for row in report["alive_panel"] if row["band"] != "gym"]
        if outside:
            report["refused"] = (f"outside the Gym band: {', '.join(outside)}; that is the flatten-first rollback's "
                                 "(docs/operations.md, Roll back: flatten first), not this script's")
            return report
        with store.atomic():
            for row in report["alive_panel"]:
                if store.retire(row["family"], REASON):
                    report["retired"].append(row["family"])
        report["alive_panel"] = alive_panels(store)
        return report
    finally:
        store.close()


if __name__ == "__main__":
    out = main()
    print(json.dumps(out, indent=1, default=str))
    sys.exit(1 if out.get("refused") else 0)
