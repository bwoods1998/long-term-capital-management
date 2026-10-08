"""THE LEARNING GAME's golden round (league/tests/test_game.py `Golden`): one fixed hourly tournament over control and legacy
families, run on a fresh store, and what it leaves, normalized. `game_golden.json` beside this file is the round as the
code before the game (main at ab64c68b) played it: `python -m league.tests.game_golden` on that tree writes it. The test
plays the same round on this tree with the game off and with the game on in "gate" mode, where every family is control
(its lineage outside the game's half of the hash) or legacy (born before T0, or a root outside the core five), and each
must equal the golden byte for byte, apart from what only the game writes (its tables, its `swarm.game` events and its
private Gym jobs).

It imports nothing the code before the game lacks (no `league.swarm.game`): the game's settings and its T0 are plain data
here, which that code ignores. Deterministic: a fixed clock, a seeded allocation, results built from sha256 seeds with
their own run ids (the fakes' counter and Python's salted `hash` are never used) and summed by `math.fsum` (`sum` of floats
rounds differently since Python 3.12), so main's tree writes the same golden on Python 3.11 and 3.14.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import sys
from pathlib import Path
from typing import Any, Mapping

from league.swarm import settings as S
from league.swarm.evaluator import KEY
from league.swarm.researcher import objective_for
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import Clock, drift_block, result

GOLDEN = Path(__file__).with_name("game_golden.json")
#: The game's T0 key (`game.T0_KEY`) and the kinds and purposes only the game writes (left out of the comparison).
T0_KEY = "game_t0"
GAME_EVENTS = ("swarm.game",)
GAME_PURPOSES = ("private",)
#: Control-arm ids under the game's split (`canary.in_arm("ltcm-game-v1", "game-v1", id, 0.5)` is False for each: the test
#: asserts it), and the code of every family's version 1.
CONTROL = ("golden-0", "golden-1", "golden-2", "golden-3")
CODE = "# {fid}\nNEEDS = {{'roots': {roots!r}}}\nPARAMS = {{}}\ndef decide(ctx):\n    return []\n"
IMAGE, BUNDLE = "img-golden", "bundle-golden"


def _seed(*parts: Any) -> int:
    return int.from_bytes(hashlib.sha256("\0".join(map(str, parts)).encode()).digest()[:8], "big")


class Pool:
    """The fake Gym: submit / wait / run / cancel, its image and bundle, and results built from the job alone."""

    def __init__(self) -> None:
        self.jobs: list[Any] = []
        self.k = 0

    def image(self, kind: str = "gym") -> str:
        return IMAGE

    def bundle(self) -> str:
        return BUNDLE

    def submit(self, job: Any) -> Any:
        self.jobs.append(job)
        return job

    def answer(self, job: Any) -> dict[str, Any]:
        self.k += 1
        rng = random.Random(_seed(job.family, job.window, job.stress, job.version))
        good = job.family in ("golden-0", "golden-4") or str(job.family).startswith("golden-0-on")
        daily = [rng.gauss(6.0 if good else -1.0, 10.0) for _ in range(250)]
        out = result(job.family, daily=daily, window=job.window, pnl=math.fsum(daily), t=2.5 if good else -0.5,
                     mean=0.05 if good else -0.01, quarters="4/4" if good else "1/4", roots=tuple(job.roots or ("SPY",)))
        out.update(run_id=f"golden-{job.family}-{job.window}-{job.stress}-{self.k}", gym_image=IMAGE, gym_bundle=BUNDLE)
        return out

    def wait(self, job: Any, timeout: Any = None, late: Any = None, late_fail: Any = None) -> dict[str, Any]:
        return self.answer(job)

    def run(self, job: Any, timeout: Any = None, late: Any = None, late_fail: Any = None) -> dict[str, Any]:
        return self.wait(self.submit(job), timeout, late, late_fail)

    def cancel_family(self, family: str) -> None:
        pass


def settings(game: Mapping[str, Any] | None = None) -> dict[str, Any]:
    out = copy.deepcopy(S.DEFAULTS)
    out["population"].update(start=2, floor=0, ceiling=96)
    out["tournament"].update(fork_top=3, retire_revisions=30)
    out["gate"]["look_holds"] = None
    if game is not None:
        out["game"] = dict(game)
    return out


def _family(store: SwarmStore, fid: str, roots: tuple[str, ...], *, score: float | None, robust: float | None,
            **fields: Any) -> None:
    store.add_family({"id": fid, "mechanism": f"Index calls after a low close rebound: {fid}, a debit vertical.",
                      "structure": "debit_vertical", "roots": list(roots), "dte": [1, 5]}, origin="seed")
    v = store.add_version(fid, CODE.format(fid=fid, roots=list(roots)), {}, author="seed")
    if score is not None:
        summary = {"train_score": score, "train_eligible": True, "train_from": "2022-01-03", "gym_image": IMAGE,
                   "gym_bundle": BUNDLE, "pnl": 400.0, "drift": drift_block()}
        run = store.add_run(fid, v["n"], {"run_id": f"golden-train-{fid}", "status": "ok", "trials": 1, "summary": summary,
                                         "gym_image": IMAGE, "gym_bundle": BUNDLE},
                            window="train", stress=1.0, purpose="train")
        store.update_family(fid, best_train=score)
        store.set_state(fid, best_train_version=v["n"], best_train_run=run["run_id"],
                        train_candidates=[[score, v["n"], run["run_id"]]])
    if robust is not None:
        store.set_state(fid, robustness={str(v["n"]): {"stress_1.5": {"status": "ok", "pnl": robust, "gym_image": IMAGE,
                                                                      "gym_bundle": BUNDLE}}})
    if fields:
        store.update_family(fid, **{k: v for k, v in fields.items() if k != "state"})
        if fields.get("state"):
            store.set_state(fid, **fields["state"])


def play(root: str | Path, game: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The round on a fresh store at `root` with the swarm's settings plus `game` (None: no game block): the families, T0
    between the first (legacy: born before it) and the rest, one tournament round. What it leaves (`snapshot`)."""
    root = Path(root)
    clock = Clock(1_791_000_000.0)
    store = SwarmStore(root, clock=clock)
    try:
        conf = settings(game)
        store.put("train_objective", objective_for(conf))  # the running span: 2022-01-03 (the game's seen span)
        store.put(KEY, {"image": IMAGE, "bundle": BUNDLE, "execution": "golden"})
        _family(store, "golden-4", ("SPY",), score=2.0, robust=50.0)  # legacy: born before T0
        clock.advance(60)
        store.put(T0_KEY, store.now())
        clock.advance(60)
        _family(store, CONTROL[0], ("SPY",), score=2.0, robust=50.0)          # validated: passes, forks
        _family(store, CONTROL[1], ("QQQ",), score=1.5, robust=40.0)          # validated: fails the line
        _family(store, CONTROL[2], ("SPY",), score=1.2, robust=None)          # waits for its 1.5x run
        _family(store, CONTROL[3], ("IWM",), score=None, robust=None, since_val_revisions=31)  # retired: no improvement
        _family(store, "golden-5", ("TSLA",), score=None, robust=None, state={"dormant_cycles": 500})  # legacy root: idle
        pool = Pool()
        row = Tournament(store, pool, conf, clock=clock, rng=random.Random(7)).run()
        return snapshot(store, root, row, pool)
    finally:
        store.close()


def snapshot(store: SwarmStore, root: Path, row: Mapping[str, Any], pool: Pool) -> dict[str, Any]:
    """What the round left, without what only the game writes, every path under `root` as "<root>"."""
    def rows(sql: str) -> list[dict[str, Any]]:
        return [dict(r) for r in store._all(sql)]

    out = {"round": row,
           "families": [store.family(f["id"]) for f in sorted(store.families(), key=lambda f: f["id"])],
           "runs": [{k: v for k, v in r.items() if k != "path"} for r in rows("SELECT * FROM runs ORDER BY rowid")],
           "events": [r for r in rows("SELECT kind, family, at, payload FROM events ORDER BY seq") if r["kind"] not in GAME_EVENTS],
           "graveyard": rows("SELECT * FROM graveyard ORDER BY at, family"),
           "notebook": rows("SELECT family, at, text FROM notebook ORDER BY seq"),
           "versions": rows("SELECT family, n, sha, author FROM versions ORDER BY family, n"),
           "jobs": [[j.family, j.version, j.window, j.stress, j.purpose, list(j.roots)] for j in pool.jobs
                    if j.purpose not in GAME_PURPOSES],
           "leaderboard": store.get("leaderboard")}
    text = json.dumps(out, sort_keys=True, default=str).replace(str(root), "<root>")
    return json.loads(text)


def main() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        GOLDEN.write_text(json.dumps(play(d), sort_keys=True, indent=1) + "\n", encoding="utf-8")
    print(GOLDEN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
