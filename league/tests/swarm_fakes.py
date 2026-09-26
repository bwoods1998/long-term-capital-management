"""Fakes for the swarm's tests (league/swarm/): Sail's box API, the Gym's driver, Sail's Responses API (behind
the real `ltcm.provider.Provider`), the gateway's frontier and its month. No network, no Gym needed."""

from __future__ import annotations

import itertools
import json
import threading
from decimal import Decimal
from typing import Any, Callable

from ltcm.provider import Provider

_N = itertools.count(1)


class Clock:
    def __init__(self, t: float = 1_790_400_000.0):
        self.t = float(t)

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def summary(trades: int = 150, days: int = 120, pnl: float = 500.0, mean: float = 0.05, t: float = 2.5, sharpe_daily: float = 0.2,
            quarters: str = "4/4") -> dict[str, Any]:
    return {"trades": trades, "days": 250, "days_traded": days, "pnl": pnl, "pnl_per_max_loss": mean, "mean_return_on_max_loss": mean,
            "t_stat": t + 1.0, "t_daily": t, "win_rate": 0.6, "profit_factor": 1.4, "sharpe": sharpe_daily * 15.87, "sharpe_daily": sharpe_daily,
            "max_drawdown": 200.0, "fees": 30.0, "quarters_positive": quarters, "avg_trade": pnl / max(trades, 1)}


def result(name: str, *, status: str = "ok", daily: list[float] | None = None, trades: int = 150, window: str = "train",
           roots: tuple[str, ...] = ("SPY",), **kw: Any) -> dict[str, Any]:
    daily = daily if daily is not None else [3.0 + (i % 5) - 1.5 for i in range(250)]
    rows = [[f"2024-01-{(i % 28) + 1:02d}", x, 10000 + x] for i, x in enumerate(daily)]
    trade_rows = [{"id": i, "day": rows[i % len(rows)][0], "root": roots[0], "type": "iron_condor", "qty": 1, "entry": -0.4, "exit": -0.1,
                   "entry_minute": 600, "max_loss": 60.0, "fees": 1.0, "pnl": 5.0 if i % 3 else -4.0, "exit_reason": "target",
                   "context": {"dte": 0}} for i in range(min(trades, 40))]
    out = {"run_id": f"run-{name}-{next(_N)}", "program": name, "status": status, "trials": 0 if status == "refused" else 1,
            "window": window, "roots": list(roots), "stress": 1.0, "params": {}, "summary": summary(trades=trades, **kw),
            "fills": {"orders": 300, "filled": 290, "fill_rate": 0.97, "reject_reasons": {}}, "breakdown": {"weekday": {"Mon": {"n": 30, "pnl": 100.0, "win_rate": 0.6, "pnl_per_max_loss": 0.05}}},
            "daily": rows, "trades": trade_rows, "worst": trade_rows[:5], "runtime": {"calls": 1000, "errors": 0, "timeouts": 0, "messages": [],
                                                                                   "disqualified": None}}
    if window == "validation":  # the Gym's validation view: no trades, dates or daily series; the stress twin's figures
        s = out["summary"]
        s["median_max_loss_per_structure"] = 60.0
        out = {k: v for k, v in out.items() if k not in ("daily", "trades", "worst")}
        out["stress_1.5"] = {"stress": 1.5, "status": status, "trades": s["trades"], "pnl": round(s["pnl"] * 0.7, 2),
                             "t_daily": s["t_daily"] * 0.7, "sharpe_daily": s["sharpe_daily"] * 0.7}
    return out


class FakeDriver:
    """The Gym's driver on one box: `answer(name, code, params, window, stress, roots)` makes each result."""

    def __init__(self, client: Any, box: str, *, answer: Callable[..., dict] | None = None, roots: tuple[str, ...] = ("SPY", "QQQ", "IWM", "XSP", "SPXW"),
                 fail: Callable[[], Exception | None] | None = None, calls: list | None = None):
        self.client, self.box, self.version = client, box, "gym-engine-1-fake"
        self.answer = answer or (lambda name, code, params, window, stress, roots: result(name, window=window, roots=tuple(roots)))
        self.roots = roots
        self.fail = fail
        self.calls = calls if calls is not None else []

    def ensure_code(self) -> str:
        return "/workspace/gym/code/fake"

    def check_data(self, window: str, roots: list[str]) -> dict:
        missing = [r for r in roots if r not in self.roots]
        if missing and len(roots) == 1:
            raise RuntimeError(f"the box is missing data: no {window} days for {missing[0]}")
        return {"roots": {r: {"nbbo": 10, "underlying": 10} for r in roots if r in self.roots}}

    def run(self, programs: dict, *, window: str, roots: list[str], workers: int = 8, split: int = 1, stress: float = 1.0,
            capital: float = 10000.0, detail: str = "full", start: Any = None, end: Any = None, gate_reason: Any = None,
            timeout: int = 900) -> dict:
        self.calls.append({"box": self.box, "programs": sorted(programs), "window": window, "roots": list(roots), "stress": stress,
                           "gate": gate_reason, "split": split})
        if self.fail is not None:
            exc = self.fail()
            if exc is not None:
                raise exc
        results = []
        for name in sorted(programs):
            code, params = programs[name]
            r = self.answer(name, code, params, window, stress, roots)
            r["program"] = name
            results.append(r)
        return {"batch": {"days": 250, "programs": len(programs), "trials": len(results), "window": window}, "results": results}


class FakeSail:
    """Sail's box API: forks, sleep, resume, terminate (recorded)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.forks: list[tuple[str, str]] = []
        self.slept: list[str] = []
        self.resumed: list[str] = []
        self.terminated: list[str] = []

    def from_checkpoint(self, checkpoint: str, *, name: str, timeout: float = 900.0) -> dict:
        with self.lock:
            box = f"sb_{len(self.forks) + 1:08d}-0000-0000-0000-000000000000"
            self.forks.append((checkpoint, box))
        return {"sailbox_id": box, "checkpoint_id": checkpoint, "status": "running"}

    def sleep(self, box: str, **kw: Any) -> dict:
        self.slept.append(box)
        return {}

    def resume(self, box: str, **kw: Any) -> dict:
        self.resumed.append(box)
        return {}

    def terminate(self, box: str) -> dict:
        self.terminated.append(box)
        return {}


def response_payload(model: str, *, text: str = "", calls: list[tuple[str, dict]] | None = None, input_tokens: int = 4000,
                     output_tokens: int = 800, cached: int = 3000) -> dict:
    output: list[dict] = []
    if text:
        output.append({"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]})
    for name, args in calls or []:
        n = next(_N)
        output.append({"type": "function_call", "id": f"fc_{n}", "call_id": f"call_{n}", "name": name, "arguments": json.dumps(args)})
    return {"id": f"resp_{next(_N)}", "status": "completed", "model": model, "output": output,
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens, "input_tokens_details": {"cached_tokens": cached}}}


class ScriptedSail:
    """Sail's Responses API for the real Provider: `script(body) -> payload kwargs` decides each answer."""

    def __init__(self, script: Callable[[dict], dict] | None = None):
        self.script = script or (lambda body: {"text": "ok"})
        self.bodies: list[dict] = []
        self.lock = threading.Lock()

    def __call__(self, method: str, route: str, body: dict | None = None, idempotency_key: str | None = None) -> dict:
        if route.startswith("/v2/usage/summary"):
            return {"available": True, "balance": 10000.0, "period_spend": 500.0, "range": "24h"}
        if method == "POST" and route == "/v1/responses":
            with self.lock:
                self.bodies.append(body or {})
            return response_payload(body["model"], **self.script(body or {}))
        raise AssertionError(f"unexpected {method} {route}")


def provider(path: Any, script: Callable[[dict], dict] | None = None, *, clock: Any = None) -> tuple[Provider, ScriptedSail]:
    sail = ScriptedSail(script)
    kwargs = {"clock": clock} if clock is not None else {}
    return Provider(path, transport=sail, floor_cap_usd_per_day="1000", **kwargs), sail


class FakeFrontier:
    def __init__(self, model: str, *, text: str = "{}", cost: str = "0.40", fail: Exception | None = None, asked: list | None = None):
        self.model, self.text, self.cost, self.fail = model, text, cost, fail
        self.asked = asked if asked is not None else []

    def ask(self, *, system: str, user: str, agent: str, max_output_tokens: int = 6000, effort: str = "medium") -> Any:
        self.asked.append({"model": self.model, "system": system, "user": user, "agent": agent})
        if self.fail is not None:
            raise self.fail

        class Answer:
            pass

        a = Answer()
        a.text, a.cost_usd, a.status = self.text, Decimal(self.cost), "completed"
        return a


class FakeMonth:
    def __init__(self, remaining: Any):
        self.value = remaining

    def remaining(self) -> Any:
        return None if self.value is None else Decimal(str(self.value))
