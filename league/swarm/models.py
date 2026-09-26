"""The swarm's model calls: Sail for the inner loop and every fallback, OpenAI only when it has room.

- SAIL (`ModelRouter.sail`): the Responses API through `league.provider.Provider` (durable request rows,
  reservations before dispatch, settled costs, a per-family daily cap and a floor cap). Its own request
  file in the state root, `swarm-provider.sqlite`. Each family's calls carry its own `prompt_cache_key`,
  so its history is read from the cache on every turn.
- OPENAI (`ModelRouter.ask`): GPT-6 through the gateway (`league.frontier.Frontier`), used only when the
  gateway's month has room above the reserve (`FrontierMonth.remaining`) AND the swarm's own OpenAI
  spend is under its cap (plan: $150 for the burst). A refusal, an error or no room falls back to the
  role's Sail profile. Flex (`service_tier: "flex"`) is asked for when the gateway supports it (Wave 5).
- Every settled cost is a `spend` row (kind `sail_model` or `openai`, by family).

Standard library only.
"""

from __future__ import annotations

import json
import threading
import time
from decimal import Decimal
from typing import Any, Callable, Mapping, Sequence

from .store import SwarmStore


class ModelError(RuntimeError):
    """A model call could not be completed (the message says why)."""


def extract_json(text: str) -> dict[str, Any] | None:
    """The first JSON object in a model's text (a fenced block or a bare object), or None."""
    decoder = json.JSONDecoder()
    text = str(text or "")
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return None


class ModelRouter:
    """Routes the swarm's calls (the module docstring)."""

    def __init__(self, store: SwarmStore, provider: Any, *, settings: Mapping[str, Any], frontier_factory: Callable[[str], Any] | None = None,
                 month: Any = None, sleep: Callable[[float], None] | None = None):
        import time as _time

        self.sleep = sleep or _time.sleep
        self.store = store
        self.provider = provider
        self.settings = settings
        self.frontier_factory = frontier_factory
        self.month = month
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ Sail
    def sail(self, profile: str, items: Sequence[Any], *, family: str, key: str, tools: Sequence[Mapping[str, Any]] | None = None,
             effort: str = "low", max_output: int = 8000, cache_key: str | None = None, tool_choice: str = "auto",
             cap_usd_day: float | None = None, kind: str = "sail_model") -> Any:
        """One Sail call, deduped on `key` (a crash-retry re-reads the stored response). Raises the
        Provider's errors (`BudgetExceeded` when a cap would be breached)."""
        cap = cap_usd_day if cap_usd_day is not None else float(self.settings.get("researcher", {}).get("family_usd_day", 2.0))
        attempt = 0
        while True:
            try:
                response = self.provider.respond(profile, list(items), tools=list(tools) if tools else None, desk_id=family,
                                                 session_id=family, request_key=key[:200], reasoning_effort=effort,
                                                 max_output_tokens=int(max_output), desk_cap_usd_per_day=str(cap),
                                                 cache_key=(cache_key or family)[:128], tool_choice=tool_choice)
                break
            except Exception as exc:  # noqa: BLE001 - a rate limit or a 5xx is waited out twice (a 502 was seen on Sept 26)
                code = str(getattr(exc, "code", "") or "")
                if attempt >= 2 or not any(code.startswith(f"provider_http_{s}") for s in (429, 500, 502, 503, 504, 529)):
                    self._book_unsettled(kind, profile, family, key, exc)
                    raise
                attempt += 1
                self.sleep(float(getattr(exc, "retry_after", None) or 5 * 3 ** attempt))
        cost = float(response.cost_usd or 0)
        self._account_sail(key, cost, kind=kind, family=family.split(":", 1)[0], settled=True,
                           detail={"profile": profile, "key": key[:120], "desk": family})
        return response

    #: Errors after which Sail may have run (and billed) a call whose answer never came back.
    UNCONFIRMED = ("provider_poll_timeout", "provider_transport_timeout", "provider_transport_unconfirmed")

    def _row(self, key: str) -> Any:
        try:
            with self.provider._lock:
                return self.provider._db.execute("SELECT status, reserved_usd, cost_usd, response_id FROM requests WHERE request_key=?",
                                                 (key[:200],)).fetchone()
        except Exception:  # noqa: BLE001 - a fake Provider: nothing known
            return None

    def _account_sail(self, key: str, usd: float, *, kind: str, family: str | None,
                      settled: bool, detail: Mapping[str, Any], released: bool = False) -> bool:
        """Replace a request's booked cost atomically. A reaper or cached retry cannot book it a second time."""
        key = key[:200]
        with self.store.atomic():
            holds = dict(self.store.get("unsettled") or {})
            row = self.store._one("SELECT booked_usd, settled FROM model_costs WHERE request_key=?", (key,))
            if row and row["settled"]:
                return False
            # Upgrade an existing pre-stage-3 hold without booking it again.
            booked = float(row["booked_usd"] if row else (holds.get(key) or {}).get("usd") or 0)
            if settled:
                holds.pop(key, None)
            else:
                holds[key] = {"usd": usd, "kind": kind, "family": family, "at": time.time()}
            self.store.put("unsettled", holds)
            self.store._exec("INSERT INTO model_costs(request_key, booked_usd, settled) VALUES(?,?,?) "
                             "ON CONFLICT(request_key) DO UPDATE SET booked_usd=excluded.booked_usd, settled=excluded.settled",
                             (key, usd, int(settled and not released)))
            if usd != booked:
                self.store.add_spend(kind, usd - booked, family=family,
                                     detail={**detail, **({"replaces_hold": round(booked, 6)} if booked else {})})
            return True

    def _book_unsettled(self, kind: str, profile: str, family: str, key: str, exc: BaseException) -> None:
        """A call that failed after it was sent (a poll or transport timeout: Sail may have run it and billed it) is
        booked ONCE at the Provider's hold for it, and remembered (kv `unsettled`), so the swarm's own meter never
        undercounts: its settled cost later replaces the hold (`sail`, `settle_holds`), and a hold the Provider
        releases is reversed. A call the venue refused, or an HTTP error with nothing accepted, costs nothing."""
        row = self._row(key)
        code = str(getattr(exc, "code", "") or "")
        if row is None or row["status"] == "abandoned" or (not row["response_id"] and code not in self.UNCONFIRMED):
            return
        usd = float(row["cost_usd"] if row["cost_usd"] is not None else row["reserved_usd"] or 0)
        if usd <= 0:
            return
        self._account_sail(key, usd, kind=kind, family=family.split(":", 1)[0], settled=False,
                           detail={"profile": profile, "key": key[:120], "desk": family, "unsettled": code or type(exc).__name__})

    def settle_holds(self) -> int:
        """True up the holds booked for unanswered calls once the Provider knows: its settled cost replaces the hold,
        a released (abandoned) request reverses it. Returns how many were settled."""
        n = 0
        for key, hold in list((self.store.get("unsettled") or {}).items()):
            row = self._row(key)
            if row is None:
                continue
            if row["status"] == "abandoned" and row["cost_usd"] is None:
                cost = 0.0
            elif row["cost_usd"] is not None and row["status"] not in ("prepared", "dispatched"):
                cost = float(row["cost_usd"])
            else:
                continue  # still unknown: the hold stands
            n += int(self._account_sail(key, cost, kind=hold.get("kind") or "sail_model", family=hold.get("family"),
                                        settled=True, released=row["status"] == "abandoned" and row["cost_usd"] is None,
                                        detail={"key": key[:120], "settles_hold": round(float(hold["usd"]), 6)}))
        return n

    def compact(self, *, older_than_seconds: float = 3600.0) -> int:
        """Blank the request bodies and responses of settled calls older than an hour in the swarm's Provider file. Each
        body is the whole conversation (~65 KB measured Sept 26) and the swarm makes thousands an hour: kept, they would
        fill the House box's disk in a day. Costs, usage and statuses stay (the budgets read those); a call is re-read
        by its key only within its own cycle."""
        import sqlite3
        import time as _time

        path = getattr(self.provider, "path", None)
        if path is None:
            return 0
        cutoff = _time.strftime("%Y-%m-%dT%H:%M:%S", _time.gmtime(_time.time() - older_than_seconds))
        db = sqlite3.connect(str(path), timeout=10, isolation_level=None)
        try:
            cur = db.execute("UPDATE requests SET body='{}', response=NULL WHERE status IN "
                             "('completed','incomplete','failed','cancelled','abandoned') AND updated_at < ? "
                             "AND (body != '{}' OR response IS NOT NULL)", (cutoff,))
            return int(cur.rowcount or 0)
        finally:
            db.close()

    # ------------------------------------------------------------------ OpenAI
    def openai_room(self) -> float:
        """Dollars the swarm may still spend on OpenAI now: the lower of the gateway month's room above the
        reserve and what is left of the swarm's own cap. 0 when the month cannot be read."""
        guard = self.settings.get("guard", {})
        if self.month is None or self.frontier_factory is None:
            return 0.0
        try:
            remaining = self.month.remaining()
        except Exception:  # noqa: BLE001 - unreadable is no room
            remaining = None
        if remaining is None:
            return 0.0
        month_room = float(Decimal(str(remaining))) - float(guard.get("openai_reserve_usd", 5.0))
        cap_room = float(guard.get("openai_cap_usd", 150.0)) - self.store.spent(["openai"])
        return max(0.0, min(month_room, cap_room))

    def ask(self, *, role: str, system: str, user: str, family: str | None, key: str, openai_model: str | None, sail_profile: str,
            max_output: int = 8000, effort: str = "medium", need_usd: float = 1.0, desk: str | None = None,
            cap_usd_day: float | None = None) -> dict[str, Any]:
        """A one-shot question for a role (the architect, the reviewer, the auditor, a rewrite). OpenAI first when it has
        `need_usd` of room, else (or on any refusal) Sail. `desk` and `cap_usd_day` are the Provider's fuse for the Sail
        call (a family's role gets its own small one; the swarm's floor cap otherwise). An OpenAI call books a hold of
        `need_usd` BEFORE it is sent and settles it after (a refusal to $0; a call lost in flight keeps the hold), so the
        swarm's OpenAI cap never undercounts. Returns {text, json, route, model, cost_usd}."""
        errors = []
        if openai_model and self.openai_room() >= need_usd:
            hold = float(need_usd)
            self.store.add_spend("openai", hold, family=family, detail={"role": role, "hold": key[:120]})
            try:
                frontier = self.frontier_factory(openai_model)  # type: ignore[misc]
                answer = frontier.ask(system=system, user=user, agent=f"swarm-{role}", max_output_tokens=min(int(max_output), 16000),
                                      effort=effort)
                cost = float(answer.cost_usd or 0)
                self.store.add_spend("openai", cost - hold, family=family, detail={"role": role, "model": openai_model, "settles": key[:120]})
                if answer.status == "completed" and answer.text.strip():
                    return {"text": answer.text, "json": extract_json(answer.text), "route": "openai", "model": openai_model,
                            "cost_usd": cost}
                errors.append(f"openai answered {answer.status}")
            except Exception as exc:  # noqa: BLE001 - every OpenAI failure falls back to Sail
                status = getattr(exc, "status", None)
                if isinstance(status, int) and 400 <= status < 500:
                    self.store.add_spend("openai", -hold, family=family, detail={"role": role, "refused": status})
                errors.append(f"openai: {type(exc).__name__}: {str(exc)[:160]}")
        items = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            response = self.sail(sail_profile, items, family=desk or family or "swarm", key=key, effort=effort, max_output=max_output,
                                 cache_key=f"swarm-{role}", tool_choice="auto",
                                 cap_usd_day=float(cap_usd_day if cap_usd_day is not None else
                                                   self.settings.get("researcher", {}).get("floor_usd_day", 60.0)),
                                 kind="sail_model")
        except Exception as exc:  # noqa: BLE001
            raise ModelError("; ".join(errors + [f"sail: {type(exc).__name__}: {getattr(exc, 'code', '') or str(exc)[:160]}"])) from None
        text = response.output_text or ""
        return {"text": text, "json": extract_json(text), "route": "sail", "model": sail_profile,
                "cost_usd": float(response.cost_usd or 0), "fallback_reasons": errors}


def build_router(root: Any, store: SwarmStore, settings: Mapping[str, Any], *, config: Mapping[str, Any] | None = None) -> ModelRouter:
    """The real router on the box: a Provider on `<root>/swarm-provider.sqlite`; OpenAI through the gateway
    when the config names one and a gateway token is in the environment."""
    import os
    from pathlib import Path

    from league.provider import Provider

    researcher = settings.get("researcher", {})
    provider = Provider(Path(root) / "swarm-provider.sqlite", floor_cap_usd_per_day=str(researcher.get("floor_usd_day", 60.0)),
                        poll_timeout=900.0)
    frontier_factory = month = None
    gateway = (config or {}).get("gateway_url")
    token_name = "GATEWAY_TOKEN"
    if gateway and os.environ.get(token_name):
        from ..frontier import Frontier, FrontierMonth

        def token() -> str:
            return os.environ[token_name]

        frontier_factory = lambda model: Frontier(gateway, token, model=model, timeout=600.0)  # noqa: E731
        month = FrontierMonth(gateway, token, ttl=120.0)
    return ModelRouter(store, provider, settings=settings, frontier_factory=frontier_factory, month=month)


__all__ = ["ModelRouter", "ModelError", "build_router", "extract_json"]
