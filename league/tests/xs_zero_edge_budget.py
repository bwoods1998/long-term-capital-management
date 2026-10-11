"""THE `xs_zero_edge` JOB'S JUDGMENT AT THE REAL PANEL'S SIZE, under the ops child's own address-space limit (the ship
check's major: the job could not finish ONE program inside its 500 MB; `league/tests/test_xs_zero_edge.py`
`TheJobFitsItsMemory` drives it). Not a test module: the made-up store, and the child that judges programs on it.

THE STORE (`build`): `league.xs.synth.synthetic_panel` at the production panel's shape (505 members a day with 5% of
churn a year from 2016 to the last session: about 2,700 sessions by 700 columns, the two bar arrays about 135 MB on
disk), invented prices, the lane's switch at "train".

THE CHILD (`child`, started by `BOOT`): exactly the ops child's order (`league/ops/__main__.py`): THE LIMIT FIRST
(`limit(None, extra_mb)`: RLIMIT_AS = the address space now + `extra_mb`), then the job's imports, then the work. What
is real: the panel store, the panel runner (`league.xs.runner.Isolated`: each run's slice cut from the store and sent
whole), the House's side of the decider (`league.live.decider.Decider`: the pickle, the frame, the pipe, the answer's
JSON), the decider's own child process and its serve loop, and the job's `judge`. What is not: the engine. A real run
of three Train years takes ten seconds and the cap is on the PARENT (the child is another process with a cap of its
own), so the child's `run_bars` is `canned`: it reads the bars it was sent and answers a result of a real one's size,
"disqualified", which ends a judgment after its last run and before the bar (the restart check's own memory, one
span's slice cut again at a time, is then walked by hand: `elane_xs.slicer`).

`mode` "kept" is the judgment AS IT WAS: the store opened again for every run and every run kept whole. It does not
fit, and the test holds that too, so the measurement is known to see what it is for.

It prints one JSON line: what each judgment answered, the runs made, the kernel's high-water mark of the address
space and the cap. Synthetic figures only; nothing here is market data.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

FIRST, LAST = dt.date(2016, 1, 4), dt.date(2026, 10, 9)
MEMBERS, CHURN, SEED = 505, 0.05, 11
#: What the child is started with: `python -c BOOT <state> <extra_mb> <mode> <programs>` (the limit before any import
#: of the job's, numpy among them; `OPENBLAS_NUM_THREADS` 1 in its environment, as the ops runner sets it).
BOOT = ("import sys; from league.ops import __main__ as ops; limits = ops.limit(None, int(sys.argv[2])); "
        "from league.tests import xs_zero_edge_budget as B; B.child(sys.argv[1], sys.argv[3], int(sys.argv[4]), limits)")
#: The decider's child: the real serve loop (`league.live.decider._serve`) with the engine canned.
STUB = ("import sys; sys.path.insert(0, {repo!r}); from league.tests import xs_zero_edge_budget as B; B.serve()")
SWITCH_ON = '{"elane": {"mode": "gate", "panel": {"mode": "train"}}}'


def build(state: Path) -> dict[str, int]:
    """The panel store on disk under `state` and the lane's switch up. Returns {"sessions", "columns"}."""
    import numpy as np

    from league.xs import synth

    state.mkdir(parents=True, exist_ok=True)
    root = synth.synthetic_panel(state / "equity-daily", n_assets=MEMBERS, seed=SEED, churn=CHURN, gate=True,
                                 start=FIRST, end=LAST)
    (state / "swarm.json").write_text(SWITCH_ON, encoding="utf-8")
    raw = np.load(Path(root) / "panel" / "raw.npy", mmap_mode="r")
    return {"sessions": int(raw.shape[0]), "columns": int(raw.shape[1])}


def canned(code: str, params: Any, bars: Any, **kw: Any) -> dict[str, Any]:
    """`league.xs.runner.run_bars` without the engine: a result of a real run's size (a daily row a session of the
    bars it was sent, the calls of a run asked with them) and no decide timeout, "disqualified"."""
    days = [int(d) for d in bars.days]
    result: dict[str, Any] = {
        "status": "disqualified", "reason": "canned: no engine in this child", "window": bars.window, "needs": {},
        "daily": [[str(d), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, False, 1000.0] for d in days],
        "lots": [{"aid": i, "entry_day": str(days[0]), "exit_day": str(days[-1]), "x": 0.0} for i in range(1500)],
        "picks": [{"decided": str(d), "called": 1, "ctx_sha": "0" * 64, "targets": list(range(8))} for d in days[::5]],
        "runtime": {"calls": len(days) // 5, "errors": 0, "timeouts": 0, "disqualified": None, "decide_seconds": 0.1}}
    if kw.get("calls"):
        result["calls"] = [{"t": t, "positions": [[i, 0.1] for i in range(8)], "closed": [], "rejects": []}
                           for t in range(0, len(days), 5)]
    return result


def serve() -> None:  # pragma: no cover - the decider's child process
    """The decider child's own loop, its panel kind's engine `canned`."""
    from league.live import decider
    from league.xs import runner

    runner.run_bars = canned
    decider._serve(sys.stdin.buffer, sys.stdout.buffer)


def vm_mb(field: str) -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(field + ":"):
            return int(line.split()[1]) // 1024
    return 0


def child(state: str, mode: str, programs: int, limits: dict[str, Any]) -> None:  # pragma: no cover - a subprocess
    """`programs` judgments of the job on the store at `state` (`mode` "judge": the job's own `judge` inside the
    chunk's one store, then the restart check's slices one span at a time; "kept": as it was, every run kept whole
    and the store opened for each), and the one JSON line."""
    import tempfile

    from league.live.decider import Decider
    from league.ops import xs_zero_edge as Z
    from league.swarm import elane_xs
    from league.xs import config as xconfig
    from league.xs import runner as XR

    repo = str(Path(__file__).resolve().parents[2])
    tmp = Path(tempfile.mkdtemp(prefix="xs-zero-budget-"))
    python = tmp / "python"
    # (The decider starts `<python> -E -s -m league.live.decider`: this one drops the arguments and serves `STUB`.)
    python.write_text("#!/bin/sh\nexec " + json.dumps(sys.executable) + " -c " + json.dumps(STUB.format(repo=repo))
                      + "\n", encoding="utf-8")
    python.chmod(python.stat().st_mode | stat.S_IXUSR)
    decider = Decider(python=str(python), allow_unisolated=True)
    iso = XR.Isolated(decider, Path(state) / "equity-daily", budget_seconds=120.0, nice=None)
    years = list(xconfig.TRAIN_YEARS)
    spans = elane_xs.run_spans(None, years)      # no hidden year: the two segments whole, the largest slices there are
    runs = [0]
    plain = XR.Isolated.train

    def counted(self: Any, *a: Any, **kw: Any) -> Any:
        runs[0] += 1
        return plain(self, *a, **kw)

    XR.Isolated.train = counted  # type: ignore[method-assign]
    out: dict[str, Any] = {"mode": mode, "verdicts": [], "error": None}
    try:
        if mode == "kept":
            for i in range(programs):
                code = Z.program_code(7 + i, Z.KS[i % len(Z.KS)], "weekly")
                kept = []
                for first, last in spans:
                    kept.append(iso.train(code, {}, name=f"kept-{i}", start=first, end=last, k=1.0, style=True))
                    kept.append(iso.train(code, {}, name=f"kept-{i}", start=first, end=last, k=1.5, placebos=200,
                                          calls=True))
                    kept.extend(iso.train(code, {}, name=f"kept-{i}", start=first, end=last, k=1.5, half=half)
                                for half in (0, 1))
                out["verdicts"].append(len(kept))
        else:
            with elane_xs.one_store(iso):
                for i in range(programs):
                    code = Z.program_code(7 + i, Z.KS[i % len(Z.KS)], "weekly")
                    out["verdicts"].append(Z.judge(iso, decider, code, name=f"zero-{i}", hidden=None, years_ok=years,
                                                   placebos=200))
                    cut = elane_xs.slicer(iso, code, {}, name=f"zero-{i}")
                    for first, last in spans:      # the restart check's own reads, one span's slice at a time
                        piece = cut(first, last)
                        out["slice_sessions"] = int(len(piece.bars.days))
                        del piece
    except BaseException as exc:  # noqa: BLE001 - the measurement's own answer
        out["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        try:
            decider.close()
        except Exception:  # noqa: BLE001
            pass
        for path in (python,):
            try:
                os.unlink(path)
                os.rmdir(tmp)
            except OSError:
                pass
    out.update(runs=runs[0], spans=len(spans), vm_peak_mb=vm_mb("VmPeak"),
               cap_mb=int(limits.get("as_bytes") or 0) // 2 ** 20)
    print(json.dumps(out))


__all__ = ["FIRST", "LAST", "MEMBERS", "CHURN", "SEED", "BOOT", "STUB", "SWITCH_ON", "build", "canned", "serve",
           "vm_mb", "child"]
