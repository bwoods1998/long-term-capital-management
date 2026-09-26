"""The swarm's model calls: Sail for the inner loop and every fallback, Claude and OpenAI only when they have room.

- SAIL (`ModelRouter.sail`): the Responses API through `ltcm.provider.Provider` (durable request rows,
  reservations before dispatch, settled costs, a per-family daily cap and a floor cap). Its own request
  file in the state root, `swarm-provider.sqlite`. Each family's calls carry its own `prompt_cache_key`,
  so its history is read from the cache on every turn.
- OPENAI (`ModelRouter.ask`): GPT-6 through the gateway (`league.frontier.Frontier`), used only when the
  gateway's month has room above the reserve (`FrontierMonth.remaining`) AND the swarm's own OpenAI
  spend is under its cap (plan: $150 for the burst). A refusal, an error or no room falls back to the
  role's Sail profile. Nonurgent roles request Flex; the latency-sensitive audit requests standard.
- CLAUDE (`ModelRouter.ask(claude=True)`, Sept 26, 2026, the swarm sprint): Claude Opus 5.5 through the gateway
  (`league.claude.Claude`) for the roles in `claude.roles` (the architect, the gate's audit, the diagnostician), first
  among the paid routes while the gateway's funded total has room above `claude.reserve_usd` and the swarm's own Claude
  spend is under `claude.usd_cap`. The architect rotates: every other pass asks GPT-6 Astra first. Claude capped, erring
  or unconfigured falls to OpenAI, then Sail, exactly as before.
- Every settled cost is a `spend` row (kind `sail_model`, `openai` or `claude`, by family).

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
                 month: Any = None, sleep: Callable[[float], None] | None = None, claude_factory: Callable[[str], Any] | None = None,
                 claude_meter: Any = None):
        import time as _time

        self.sleep = sleep or _time.sleep
        self.store = store
        self.provider = provider
        self.settings = settings
        self.frontier_factory = frontier_factory
        self.month = month
        self.claude_factory = claude_factory
        self.claude_meter = claude_meter
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
    def _require_committed_store(self) -> None:
        try:
            with self.store._lock:
                pending = self.store._db.in_transaction
        except Exception:
            raise ModelError("model dispatch requires a readable budget store") from None
        if pending:
            raise ModelError("model dispatch cannot run inside an uncommitted store transaction")

    def _openai_cap_room(self) -> float:
        try:
            cap = Decimal(str(self.settings.get("guard", {}).get("openai_cap_usd", 150.0)))
            spent = Decimal(str(self.store.spent(["openai"])))
            if not cap.is_finite() or not spent.is_finite() or cap < 0:
                return 0.0
            return float(max(Decimal(0), cap - max(Decimal(0), spent)))
        except (ArithmeticError, ValueError, TypeError):
            return 0.0

    def openai_room(self) -> float:
        """Dollars the swarm may still spend on OpenAI now: the lower of the gateway month's room above the
        reserve and what is left of the swarm's own cap. 0 when the month cannot be read."""
        guard = self.settings.get("guard", {})
        if self.month is None or self.frontier_factory is None:
            return 0.0
        try:
            remaining = self.month.remaining()
            remaining = Decimal(str(remaining))
            reserve = Decimal(str(guard.get("openai_reserve_usd", 5.0)))
            if not remaining.is_finite() or not reserve.is_finite() or reserve < 0:
                return 0.0
        except Exception:  # noqa: BLE001 - unreadable is no room
            return 0.0
        return max(0.0, min(float(remaining - reserve), self._openai_cap_room()))

    # ------------------------------------------------------------------ Claude
    def _claude_cfg(self) -> Mapping[str, Any]:
        cfg = self.settings.get("claude")
        return cfg if isinstance(cfg, Mapping) else {}

    def claude_enabled(self, role: str) -> bool:
        """Claude is configured (a client and the gateway's meter), names a model, and serves `role` (`claude.roles`)."""
        cfg = self._claude_cfg()
        roles = cfg.get("roles")
        return (self.claude_factory is not None and self.claude_meter is not None and bool(cfg.get("model"))
                and isinstance(roles, (list, tuple)) and role in roles)

    def _claude_cap_room(self) -> float:
        try:
            cap = Decimal(str(self._claude_cfg().get("usd_cap", 100.0)))
            spent = Decimal(str(self.store.spent(["claude"])))
            if not cap.is_finite() or not spent.is_finite() or cap < 0:
                return 0.0
            return float(max(Decimal(0), cap - max(Decimal(0), spent)))
        except (ArithmeticError, ValueError, TypeError):
            return 0.0

    def claude_room(self) -> float:
        """Dollars the swarm may still spend on Claude now: the lower of the gateway's funded total above
        `claude.reserve_usd` and what is left of the swarm's own `claude.usd_cap`. 0 when either cannot be read."""
        if self.claude_meter is None or self.claude_factory is None:
            return 0.0
        try:
            remaining = Decimal(str(self.claude_meter.remaining()))
            reserve = Decimal(str(self._claude_cfg().get("reserve_usd", 5.0)))
            if not remaining.is_finite() or not reserve.is_finite() or reserve < 0:
                return 0.0
        except Exception:  # noqa: BLE001 - unreadable is no room
            return 0.0
        return max(0.0, min(float(remaining - reserve), self._claude_cap_room()))

    def claude_request(self, system: str, user: str, *, schema: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], float]:
        """The exact Claude request a role's question becomes, and the hold it needs (the gateway's worst case)."""
        from ..claude import EFFORTS, MAX_TOKENS, reservation_ceiling, request_body

        cfg = self._claude_cfg()
        effort = str(cfg.get("effort") or "high")
        body = request_body(str(cfg.get("model")), system, [{"role": "user", "content": user}],
                            max_tokens=int(cfg.get("max_tokens", MAX_TOKENS)), effort=effort if effort in EFFORTS else "high",
                            schema=schema, cache=True)
        return body, float(reservation_ceiling(body))

    def claude_spent(self, *, role: str | None = None, since: float | None = None) -> float:
        """The swarm's Claude spend (holds included), for one role when named, since an epoch when given."""
        sql, params = "SELECT usd, detail FROM spend WHERE kind='claude'", []
        if since is not None:
            sql += " AND epoch>=?"
            params.append(float(since))
        total = 0.0
        for row in self.store._all(sql, params):
            if role is None or (json.loads(row["detail"] or "{}") or {}).get("role") == role:
                total += float(row["usd"])
        return total

    def _ask_claude(self, *, role: str, system: str, user: str, family: str | None, key: str, need_usd: float,
                    schema: Mapping[str, Any] | None, errors: list[str]) -> dict[str, Any] | None:
        """The Claude route: the hold is booked (spend kind `claude`) and committed before the gateway hears of the call,
        so a crash never loses it. The gateway's settled cost replaces it (a refusal and a truncation are billed at their
        usage and fall through to the next route); a 4xx the gateway refused before reserving releases it; an unknown
        bill keeps it. None when there is no room, or the call refused or erred (the reason is in `errors`)."""
        from ..claude import ClaudeError

        cfg = self._claude_cfg()
        model = str(cfg.get("model"))
        hold = None
        try:
            need = Decimal(str(need_usd))
            if not need.is_finite() or need < 0:
                raise ValueError("invalid Claude minimum reservation")
            body, ceiling = self.claude_request(system, user, schema=schema)
            required = float(max(need, Decimal(str(ceiling))))
            room = self.claude_room()  # the meter's network read happens outside the write transaction
            if room < required:
                errors.append(f"claude: no room (${room:.2f} left above the reserve; this call may cost ${required:.2f})")
                return None
            admitted = False
            with self.store.atomic():
                if min(room, self._claude_cap_room()) >= required:
                    self.store.add_spend("claude", required, family=family,
                                         detail={"role": role, "hold": key[:120], "model": model, "max_tokens": body["max_tokens"]})
                    admitted = True
            if admitted:  # only after the outer transaction's commit succeeds
                hold = required
            else:
                errors.append("claude: the swarm's own Claude line has no room")
                return None
        except Exception as exc:  # noqa: BLE001 - invalid/unknown admission falls through without dispatch
            errors.append(f"claude admission: {type(exc).__name__}: {str(exc)[:160]}")
            return None

        def settle(cost: Any, detail: Mapping[str, Any]) -> float | None:
            try:
                amount = Decimal(str(cost)) if cost is not None else None
            except ArithmeticError:
                amount = None
            if amount is None or not amount.is_finite() or amount < 0:
                return None
            self.store.add_spend("claude", float(amount) - hold, family=family,
                                 detail={"role": role, "model": model, "settles": key[:120], **detail})
            return float(amount)

        try:
            client = self.claude_factory(model)  # type: ignore[misc]
            answer = client.ask(system, user, agent=f"swarm-{role}", role=role, max_tokens=body["max_tokens"],
                                effort=body["output_config"]["effort"], schema=schema, cache=True)
        except ClaudeError as exc:
            status = exc.status
            cost = settle(exc.cost_usd, {"error": type(exc).__name__, "status": status,
                                         "stop_reason": getattr(exc.answer, "stop_reason", None)})
            if cost is None and isinstance(status, int) and 400 <= status < 500:
                self.store.add_spend("claude", -hold, family=family, detail={"role": role, "refused": status})
            errors.append(f"claude: {type(exc).__name__}: {str(exc)[:160]}")
            return None
        except Exception as exc:  # noqa: BLE001 - an unknown failure keeps the hold and falls through
            errors.append(f"claude: {type(exc).__name__}: {str(exc)[:160]}")
            return None
        cost = settle(answer.cost_usd, {"stop_reason": answer.stop_reason}) if answer.cost_verified else None
        data = answer.data if schema is not None else extract_json(answer.text)
        return {"text": answer.text, "json": data, "route": "claude", "model": model, "cost_usd": cost,
                "cost_verified": cost is not None, "held_usd": 0.0 if cost is not None else hold,
                "stop_reason": answer.stop_reason, "usage": dict(answer.usage)}

    def _turn(self, role: str) -> int:
        """This call's number among the role's rotating calls (0, 1, 2, ...), kept across restarts."""
        try:
            with self.store.atomic():
                n = int(self.store.get(f"route_turn:{role}", 0) or 0)
                self.store.put(f"route_turn:{role}", n + 1)
            return n
        except Exception:  # noqa: BLE001 - an unreadable counter keeps the primary order
            return 0

    def ask(self, *, role: str, system: str, user: str, family: str | None, key: str, openai_model: str | None,
            sail_profile: str | None, max_output: int = 8000, effort: str = "medium", need_usd: float = 1.0,
            desk: str | None = None, cap_usd_day: float | None = None, claude: bool = False, rotate: bool = False,
            schema: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """A one-shot question for a role (the architect, the reviewer, the auditor, a rewrite, the diagnostician).

        The paid routes in order, then Sail: CLAUDE first when `claude` and the role is one of `claude.roles` and the
        funded total has room above its reserve (`_ask_claude`); OPENAI when it has room for both `need_usd` and the
        actual request's standard-service maximum (`_ask_openai`). `rotate` alternates the two paid routes' order every
        other call for the role (the architect's diversity: Astra's pass, when OpenAI has room, else Claude's). A paid
        route that refuses, errs or has no room falls to the next; `sail_profile` None means no Sail fallback (a
        ModelError instead). `desk` and `cap_usd_day` are the Provider's fuse for the Sail call. Admission and the
        durable hold are atomic across store connections; verified cost settles it, a 4xx refusal releases it, and an
        unknown bill retains it. Unknown cost is reported as None with held_usd, never as a free answer."""
        self._require_committed_store()
        errors: list[str] = []
        routes = (["claude"] if claude and self.claude_enabled(role) else []) + (["openai"] if openai_model else [])
        if rotate and len(routes) == 2 and self._turn(role) % 2 == 1:
            routes.reverse()
        for route in routes:
            if route == "claude":
                result = self._ask_claude(role=role, system=system, user=user, family=family, key=key, need_usd=need_usd,
                                          schema=schema, errors=errors)
            else:
                result = self._ask_openai(role=role, system=system, user=user, family=family, key=key, openai_model=openai_model,
                                          max_output=max_output, effort=effort, need_usd=need_usd, errors=errors)
            if result is not None:
                return result
        # A failed COMMIT/ROLLBACK may have left the admission store unusable. Do not turn that
        # failure into another paid call on the fallback provider.
        self._require_committed_store()
        if not sail_profile:
            raise ModelError("; ".join(errors) or "no paid route was available, and this role has no Sail fallback")
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

    def _ask_openai(self, *, role: str, system: str, user: str, family: str | None, key: str, openai_model: str,
                    max_output: int, effort: str, need_usd: float, errors: list[str]) -> dict[str, Any] | None:
        """The OpenAI route (#380): None when it has no room, refused or erred (the reason is in `errors`)."""
        hold = None
        from ..frontier import request_body, reservation_ceiling

        try:
            need = Decimal(str(need_usd))
            if not need.is_finite() or need < 0:
                raise ValueError("invalid OpenAI minimum reservation")
            tier = "default" if role == "audit" else "flex"
            body = request_body(openai_model, [{"role": "system", "content": system}, {"role": "user", "content": user}],
                                max_output_tokens=max_output, effort=effort, service_tier=tier, role=role)
            required = float(max(need, reservation_ceiling(body)))
            room = self.openai_room()  # network refresh must not hold the shared SQLite write transaction
            if room >= required:
                admitted = False
                with self.store.atomic():
                    if min(room, self._openai_cap_room()) >= required:
                        self.store.add_spend("openai", required, family=family,
                                             detail={"role": role, "hold": key[:120], "service_tier_requested": tier,
                                                     "max_output_tokens": body["max_output_tokens"]})
                        admitted = True
                if admitted:  # only after the outer transaction's commit succeeds
                    hold = required
        except Exception as exc:  # noqa: BLE001 - invalid/unknown admission falls back without dispatch
            errors.append(f"openai admission: {type(exc).__name__}: {str(exc)[:160]}")
        if hold is not None:
            try:
                frontier = self.frontier_factory(openai_model)  # type: ignore[misc]
                answer = frontier.ask(system=system, user=user, agent=f"swarm-{role}", max_output_tokens=body["max_output_tokens"],
                                      effort=effort, role=role, service_tier=tier)
                verified = getattr(answer, "cost_verified", False) is True and getattr(answer, "model", None) == openai_model
                cost = None
                if verified:
                    amount = Decimal(str(answer.cost_usd))
                    verified = amount.is_finite() and amount >= 0
                    if verified:
                        cost = float(amount)
                        self.store.add_spend("openai", cost - hold, family=family,
                                             detail={"role": role, "model": openai_model, "settles": key[:120],
                                                     "service_tier": getattr(answer, "service_tier", None)})
                if answer.status == "completed" and answer.text.strip() and getattr(answer, "model", None) == openai_model:
                    return {"text": answer.text, "json": extract_json(answer.text), "route": "openai", "model": openai_model,
                            "cost_usd": cost, "cost_verified": verified, "held_usd": 0.0 if verified else hold,
                            "service_tier": getattr(answer, "service_tier", None)}
                errors.append(f"openai answered {answer.status}")
            except Exception as exc:  # noqa: BLE001 - every OpenAI failure falls back to Sail
                status = getattr(exc, "status", None)
                if isinstance(status, int) and 400 <= status < 500:
                    self.store.add_spend("openai", -hold, family=family, detail={"role": role, "refused": status})
                errors.append(f"openai: {type(exc).__name__}: {str(exc)[:160]}")
        return None


def build_router(root: Any, store: SwarmStore, settings: Mapping[str, Any], *, config: Mapping[str, Any] | None = None) -> ModelRouter:
    """The real router on the box: a Provider on `<root>/swarm-provider.sqlite`; OpenAI and Claude through the
    gateway when the config names one and a gateway token is in the environment."""
    import os
    from pathlib import Path

    from ltcm.provider import Provider

    researcher = settings.get("researcher", {})
    provider = Provider(Path(root) / "swarm-provider.sqlite", floor_cap_usd_per_day=str(researcher.get("floor_usd_day", 60.0)),
                        poll_timeout=900.0)
    frontier_factory = month = claude_factory = claude_meter = None
    gateway = (config or {}).get("gateway_url")
    token_name = "GATEWAY_TOKEN"
    if gateway and os.environ.get(token_name):
        from ..frontier import Frontier, FrontierMonth

        def token() -> str:
            return os.environ[token_name]

        frontier_factory = lambda model: Frontier(gateway, token, model=model, timeout=600.0)  # noqa: E731
        month = FrontierMonth(gateway, token, ttl=120.0)
        from ..claude import Claude, ClaudeMeter

        claude_factory = lambda model: Claude(gateway, token, model=model, timeout=600.0)  # noqa: E731
        claude_meter = ClaudeMeter(gateway, token, ttl=120.0)
    return ModelRouter(store, provider, settings=settings, frontier_factory=frontier_factory, month=month,
                       claude_factory=claude_factory, claude_meter=claude_meter)


__all__ = ["ModelRouter", "ModelError", "build_router", "extract_json"]
