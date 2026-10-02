"""`python -m league.ops ...`: one House job in this process (the runner's child), or the receipts now.

    python -m league.ops run <job> --state DIR [--due ISO] [--result FILE] [--cpu S] [--extra-mb MB] [--base DIR]
    python -m league.ops receipts --state DIR     # write the receipts file now

`run` lowers its own priority (`nice` 19), bounds its address space at what it holds now plus `--extra-mb` (RLIMIT_AS)
and its CPU time at `--cpu` seconds (RLIMIT_CPU), then imports the job's module and calls `run(ctx)`. The outcome goes
to `--result` as JSON ({status, summary, error, alerts}), written atomically, and to stdout when no file is named. Exit
0 when the job ran (ok or skipped), 1 when it failed.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any


def vm_size_bytes() -> int | None:
    """This process's address space (VmSize), or None where /proc does not say."""
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmSize:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def limit(cpu: int | None, extra_mb: int | None) -> dict[str, Any]:
    """nice 19, RLIMIT_AS = now + extra, RLIMIT_CPU = cpu (hard 30 s later). What was set, for the receipt."""
    out: dict[str, Any] = {}
    try:
        out["nice"] = os.nice(19 - os.nice(0))
    except OSError:
        out["nice"] = None
    try:
        import resource
    except ImportError:  # not on a POSIX system: the wall-time kill still bounds it
        return out
    if extra_mb:
        base = vm_size_bytes()
        if base is not None:
            cap = base + int(extra_mb) * 2 ** 20
            hard = resource.getrlimit(resource.RLIMIT_AS)[1]
            if hard != resource.RLIM_INFINITY:
                cap = min(cap, hard)
            resource.setrlimit(resource.RLIMIT_AS, (cap, hard))
            out["as_bytes"] = cap
    if cpu:
        hard = resource.getrlimit(resource.RLIMIT_CPU)[1]
        soft = int(cpu) if hard == resource.RLIM_INFINITY else min(int(cpu), hard)
        resource.setrlimit(resource.RLIMIT_CPU, (soft, hard if hard != resource.RLIM_INFINITY else soft + 30))
        out["cpu_seconds"] = soft
    return out


def run_job(name: str, *, root: Path, due_at: float, base: Path | None = None, ctx: Any = None) -> dict[str, Any]:
    """The job `name` in this process: {status, summary, error, alerts}. Never raises."""
    from .context import Context
    from .registry import by_name

    job = by_name().get(name)
    if job is None:
        return {"status": "failed", "error": f"no job named {name}", "alerts": []}
    ctx = ctx or Context(name, root=root, due_at=due_at, base=base)
    try:
        module = importlib.import_module(job.module)
    except ModuleNotFoundError as exc:
        if exc.name == job.module:
            return {"status": "skipped", "summary": {"why": f"{job.module} is not in this release ({job.owner})"},
                    "alerts": ctx.alerts}
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}", "alerts": ctx.alerts}
    try:
        summary = module.run(ctx)
    except Exception as exc:  # noqa: BLE001 - every failure is the occurrence's failed receipt
        return {"status": "failed", "error": f"{type(exc).__name__}: {str(exc)[:600]}",
                "trace": traceback.format_exc()[-2000:], "alerts": ctx.alerts}
    summary = dict(summary) if isinstance(summary, dict) else {"value": summary}
    if summary.get("status") == "failed":  # a job that says it failed (e.g. the grant's refusal) is a failed receipt
        return {"status": "failed", "summary": summary, "error": str(summary.get("error") or "the job reported failed")[:600],
                "alerts": ctx.alerts}
    status = "skipped" if summary.get("status") == "skipped" else "ok"
    return {"status": status, "summary": summary, "alerts": ctx.alerts}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m league.ops", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("run", help="run one job in this process")
    one.add_argument("job")
    for part in (one, sub.add_parser("receipts", help="write the receipts file now")):
        part.add_argument("--state", type=Path, required=True)
        part.add_argument("--base", type=Path)
    one.add_argument("--due", help="the occurrence's ISO time (default: now)")
    one.add_argument("--result", type=Path)
    one.add_argument("--cpu", type=int, default=0)
    one.add_argument("--extra-mb", type=int, default=0)
    args = parser.parse_args(argv)
    from . import schedule as S
    from .context import write_json

    if args.command == "run":
        limits = limit(args.cpu, args.extra_mb)
        due = S.epoch(args.due) if args.due else time.time()
        result = run_job(args.job, root=args.state, due_at=due if due is not None else time.time(), base=args.base)
        result["limits"] = limits
        if args.result:
            write_json(args.result, result)
        else:
            print(json.dumps(result, sort_keys=True, indent=1, default=str))
        return 0 if result["status"] in ("ok", "skipped") else 1
    from .receipts import write

    print(write(args.state, args.base or args.state.parent, time.time()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
