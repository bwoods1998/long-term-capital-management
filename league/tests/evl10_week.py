"""THE INVENTED WEEK OF THE PROOF for release 1019n-r2 (the decision scheduler and PREREG-EVL-10): league/tests/
evl5_world.py's week (release 1019e's and PREREG-EVL-5's events, two births of R3 among the programs; invented issuers,
filings, articles, verdicts and bars only), decided by the importable tree's own code, recorded whole: every intent of
every program, every decision receipt the House's code wrote (its job, status, start, finish and summary: the earlier
files' decisions, receipts and TIMING), and every seatable program's real-money picks at Tuesday's and Wednesday's
auctions (league/events/book.py `picks`).

    python league/tests/evl10_week.py OUT.json      (with the tree to judge first on PYTHONPATH)

was run on main 1c87837f (release 1019m-cost, the live release before this one) into
league/tests/fixtures/evl10_week_main.json; league/tests/test_events_evl10.py `TheProof` decides the same week on its
own tree and holds every earlier row to that file, and decides it again with PREREG-EVL-10 reading and deciding in its
slot, holding every earlier row to the week without it. Only this file's own rows (none on main) are left out of the
comparison, and its rows must have decided: the proof is not vacuous."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Callable


def equity(world: Any) -> None:
    """An account equity of $10,000 at every October close (the meta rows score.py reads), in every run alike."""
    from league.events import calendar as C

    for s in C.sessions(world.st, dt.date(2026, 10, 1), dt.date(2026, 10, 31)):
        world.st.set_meta(f"equity:{s.day.isoformat()}", "10000.0")


def record(world: Any, keep: Callable[[str], bool] = lambda program: True) -> dict[str, Any]:
    """The week as decided: intents, decision receipts and real-money picks (`keep(program)` chooses the rows)."""
    from league.tests import evl5_world as W5

    intents = [list(r) for r in world.intents() if keep(str(r[0]))]
    jobs = {int(r["id"]): str(r["job"]) for r in world.st.db.execute("SELECT id, job FROM receipts")}
    receipts = [[str(r["job"]), str(r["status"]), str(r["started_at"]), str(r["finished_at"]), named(str(r["summary"]), jobs)]
                for r in world.st.db.execute("SELECT job, status, started_at, finished_at, summary FROM receipts WHERE "
                                             "job LIKE 'decide-%' ORDER BY id")
                if keep_receipt(str(r["job"]))]
    picks = W5.picks(world, lambda p: keep(p.id))
    return {"intents": intents, "receipts": receipts, "picks": {k: [list(x) for x in v] for k, v in picks.items()}}


def named(summary: str, jobs: dict[int, str]) -> str:
    """A receipt's summary with each receipt id it names (a learner's live receipt names the House's: `house_receipt`)
    written as that receipt's job: ids are the store's row numbers, which any other receipt written before shifts."""
    import re

    return re.sub(r'"house_receipt": (\d+)', lambda m: f'"house_receipt": "{jobs.get(int(m.group(1)), m.group(1))}"',
                  summary)


def keep_receipt(job: str) -> bool:
    """Every decision receipt but this file's own slot's (`decide-close-r2:<D>`, none on main)."""
    return not job.startswith("decide-close-r2:")


def run(root: str | Path, *, during: Callable[[Any, dt.date], None] | None = None,
        keep: Callable[[str], bool] = lambda program: True) -> dict[str, Any]:
    """The week decided by the importable tree's code. `during(world, day)`: run before each of Tuesday's and
    Wednesday's live close decisions (PREREG-EVL-10's reads and its slot, at their own stored times)."""
    from league.tests import evl5_world as W5

    world = W5.World(root)
    try:
        equity(world)
        world.births()
        W5.evl4_rows(world)
        W5.evl5_rows(world)

        def close(w: Any, day: dt.date) -> None:
            if during is not None:
                during(w, day)
            w.at(W5.et(day, 15, 47)).decide("close", day)
        W5.decide_week(world, close=close)
        return record(world, keep)
    finally:
        try:
            from league.events import programs as P

            P.load_births(None)
        finally:
            world.close()


if __name__ == "__main__":   # python league/tests/evl10_week.py OUT.json (the tree to judge first on PYTHONPATH)
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        Path(sys.argv[1]).write_text(json.dumps(run(Path(tmp) / "lane"), sort_keys=True, indent=1, default=str) + "\n")
