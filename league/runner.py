"""Runs one strategy decision inside an agent's box. Self-contained: standard library and
`safety.py` only, because this file is uploaded into the box as it is.

    python3 runner.py spec.json

The spec is `{"code": ..., "ctx": ..., "token": ...}`. The answer is the LAST line of stdout that
starts with `DECIDE-RESULT <token> `, followed by JSON. The token is a secret of this one run, the
strategy's own prints go to a throwaway buffer, and the process exits with `os._exit` right after
the line is written, so nothing a strategy registered can print a line of its own after it.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import signal
import sys
import threading
import time

try:
    from league.safety import CodeRefused, check_code
except ImportError:  # inside the box the files sit side by side
    from safety import CodeRefused, check_code

MARKER = "DECIDE-RESULT"
MAX_SECONDS = 5
MAX_MEMORY_BYTES = 8192
MAX_INTENTS = 8
MAX_CANCELS = 20
MAX_THOUGHT_CHARS = 1200


class TimedOut(BaseException):
    """Not an Exception: a strategy's own `except Exception` must not be able to swallow it."""


def _alarm(signum, frame):
    raise TimedOut()


def _arm() -> None:
    """Start the deadline. The alarm repeats, so code that swallows one interruption gets another."""
    if hasattr(signal, "SIGALRM") and threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGALRM, _alarm)
        signal.setitimer(signal.ITIMER_REAL, MAX_SECONDS, 0.25)


def _disarm() -> None:
    if hasattr(signal, "SIGALRM") and threading.current_thread() is threading.main_thread():
        signal.setitimer(signal.ITIMER_REAL, 0)


def decide(code: str, ctx: dict) -> dict:
    """Run `decide(ctx)` and return a cleaned result. Never raises: errors are reported in it."""
    try:
        check_code(code)
    except CodeRefused as exc:
        return {"ok": False, "error": f"code refused: {exc}"}
    namespace: dict = {"__name__": "strategy"}
    sink = io.StringIO()
    started = time.monotonic()
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            _arm()
            try:
                exec(compile(code, "strategy.py", "exec"), namespace)  # noqa: S102 - the box is the jail
                params = {**dict(namespace.get("PARAMS") or {}), **dict(ctx.get("params") or {})}
                out = namespace["decide"]({**ctx, "params": params})
            finally:
                _disarm()
        elapsed = time.monotonic() - started
        if elapsed > MAX_SECONDS:
            return {"ok": False, "error": f"decide ran past {MAX_SECONDS} seconds"}
        return clean(out, namespace.get("NEEDS"), elapsed)
    except TimedOut:
        _disarm()
        return {"ok": False, "error": f"decide ran past {MAX_SECONDS} seconds"}
    except BaseException as exc:  # noqa: BLE001 - a strategy may raise anything
        _disarm()
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}


def clean(out, needs, seconds: float) -> dict:
    if not isinstance(out, dict):
        return {"ok": False, "error": "decide must return a dict"}
    raw_intents = out.get("intents") if isinstance(out.get("intents"), list) else []
    raw_cancels = out.get("cancels") if isinstance(out.get("cancels"), list) else []
    intents = [i for i in raw_intents if isinstance(i, dict)][:MAX_INTENTS]
    cancels = [str(c) for c in raw_cancels if isinstance(c, str)][:MAX_CANCELS]
    memory = out.get("memory") if isinstance(out.get("memory"), dict) else {}
    try:
        if len(json.dumps(memory)) > MAX_MEMORY_BYTES:
            memory = {}
    except (TypeError, ValueError):
        memory = {}
    try:
        intents = json.loads(json.dumps(intents))
    except (TypeError, ValueError):
        intents = []
    return {
        "ok": True,
        "intents": intents,
        "cancels": cancels,
        "thought": str(out.get("thought") or "")[:MAX_THOUGHT_CHARS],
        "memory": memory,
        "needs": needs if isinstance(needs, dict) else {},
        "seconds": round(seconds, 4),
    }


def needs_of(code: str) -> dict:
    """A strategy's NEEDS and PARAMS, read by running only its module body."""
    try:
        check_code(code)
        namespace: dict = {"__name__": "strategy"}
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            _arm()  # a module body can loop forever too
            try:
                exec(compile(code, "strategy.py", "exec"), namespace)  # noqa: S102
            finally:
                _disarm()
        needs, params = namespace.get("NEEDS"), namespace.get("PARAMS")
        needs = json.loads(json.dumps(needs)) if isinstance(needs, dict) else {}
        params = json.loads(json.dumps(params)) if isinstance(params, dict) else {}
        return {"ok": True, "needs": needs, "params": params}
    except TimedOut:
        _disarm()
        return {"ok": False, "error": f"the strategy file ran past {MAX_SECONDS} seconds while loading"}
    except BaseException as exc:  # noqa: BLE001
        _disarm()
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}


def parse_result(stdout: str, token: str, marker: str = MARKER) -> dict | None:
    """The last line carrying this run's token, or None."""
    prefix = f"{marker} {token} "
    for line in reversed(str(stdout or "").splitlines()):
        if line.startswith(prefix):
            try:
                value = json.loads(line[len(prefix):])
            except ValueError:
                return None
            return value if isinstance(value, dict) else None
    return None


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    with open(args[0], encoding="utf-8") as handle:
        spec = json.load(handle)
    token = str(spec.get("token") or "")
    if spec.get("mode") == "needs":
        result = needs_of(str(spec.get("code") or ""))
    else:
        result = decide(str(spec.get("code") or ""), dict(spec.get("ctx") or {}))
    sys.__stdout__.write(f"\n{MARKER} {token} {json.dumps(result)}\n")
    sys.__stdout__.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
