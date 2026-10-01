"""The swarm's model calls: Sail for the inner loop and every fallback, Claude and OpenAI only when they have room.

- SAIL (`ModelRouter.sail`): the Responses API through `ltcm.provider.Provider` (durable request rows,
  reservations before dispatch, settled costs, a per-family daily cap and a floor cap). Its own request
  file in the state root, `swarm-provider.sqlite`. Each family's calls carry its own `prompt_cache_key`,
  so its history is read from the cache on every turn. A one-shot answer cut short on Sail says so (`ask`: `truncated`,
  `incomplete_reason`, `usage`).
- OPENAI (`ModelRouter.ask`): GPT-6 through the gateway (`league.frontier.Frontier`), used only when the
  gateway's month has room above the reserve (`FrontierMonth.remaining`) AND the swarm's own OpenAI
  spend is under its cap (plan: $150 for the burst). A refusal, an error or no room falls back to the
  role's Sail profile. Nonurgent roles request Flex; the latency-sensitive audit requests standard.
- CLAUDE (`ModelRouter.ask(claude=True)`, Sept 26, 2026, the swarm sprint): `claude.model` (Opus 5.5 by default) or the
  role's `claude.role_model` through the gateway (`league.claude.Claude`) for the roles in `claude.roles` (by default
  the architect, the gate's audit, the diagnostician), first among the paid routes while the gateway's funded total has
  room above `claude.reserve_usd` and the swarm's own Claude spend is under `claude.usd_cap`. The architect rotates only
  while `architect.openai_model` names a model: then every other pass asks GPT-6 Astra first. Claude capped, erring or
  unconfigured falls to OpenAI, then Sail, exactly as before. Every role's call asks for Claude (Sept 29, 2026: the
  researcher's stall rewrite and the gate's review too), so `claude.roles` alone decides who gets it: adding "rewrite"
  or "review" there is the operator's opt-in, with no deploy. A role may also have its own daily line,
  `claude.role_usd_day` {role: usd} (a UTC day, holds included, each call on the day its hold was booked): a call that
  would take the role's Claude spend today past it skips Claude and falls to the role's next route. No entry is no extra
  line. `claude.role_model` {role: model id} answers a role on its own Claude model (no entry: `claude.model`), and
  `claude.role_effort` {role: effort} at its own effort when the caller names none (R11-3; no entry: `claude.effort`). An
  architect answer cut at max_tokens is handed back for salvage (`ask(claude_keep_truncated)`), not sent to the next route.
- CLAUDE'S TOOL TURNS (`ModelRouter.claude_turn`, Sept 29, 2026: the bandit's top researchers run their tool loop on
  Claude Sonnet 5.5, `claude.role_model.researcher`; league/swarm/claude_research.py). One turn of a tool loop, held,
  dispatched and settled exactly as `ask`'s Claude route (one admission, one durable hold, one settlement;
  `_claude_admit`, `_ClaudeHold`), behind four fuses: the role's line (`claude.role_usd_day`, "researcher"), the family's
  own line a UTC day (`family_usd_day`), the funded room it leaves to the one-shot roles (`keep_usd`: the researcher never
  takes the last dollars the architect, the audit and the diagnostician need), and the gateway's funded total. It never
  falls through to Sail itself: every failure is a `ModelError` naming its `kind` (no_room, line, family_fuse, refusal,
  truncated, http, stream, answer, admission, off, unknown), and the caller finishes its turn on its Sail profile from the
  same transcript.
- Every settled cost is a `spend` row (kind `sail_model`, `openai` or `claude`, by family).
- FALLBACKS (Release A, Sept 30, 2026): a call that asked Claude and ended elsewhere (`ask`: the next paid route, Sail, or
  no route when the role has no Sail profile; `claude_turn`: the caller's Sail turn) is counted in memory by role, the
  Claude route's failure kind and where it went (`note_fallback`). The swarm's `FundingWatch` drains the counts
  (`drain_fallbacks`) and says them, so a role never falls back from Claude silently (league/swarm/funding.py). Counting
  never changes a route and never raises.

Standard library only.
"""

from __future__ import annotations

import json
import math
import re
import secrets
import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Mapping, Sequence

from .store import SwarmStore


class ModelError(RuntimeError):
    """A model call could not be completed (the message says why). `billed` lists the paid attempts billed anyway (a
    refusal, a truncation, an empty answer): each `{"route", "stop_reason", "cost_usd"}`. `kind` names the failure for a
    caller that falls back on its own (`claude_turn`); `held_usd` is a paid attempt's hold that stays booked because its
    bill is unknown (the true-up settles it)."""

    def __init__(self, message: str, *, billed: list[dict[str, Any]] | None = None, kind: str = "error", held_usd: float = 0.0,
                 status: int | None = None, usage: Mapping[str, Any] | None = None, overrun_usd: float = 0.0):
        super().__init__(message)
        self.billed = list(billed or [])
        self.kind = kind
        self.held_usd = float(held_usd)
        #: The gateway's HTTP status when it answered with one; the usage of a billed answer (a refusal, a cut turn), so
        #: its tokens are measured beside its bill; how far its settled cost ran past its hold (never expected: a breaker).
        self.status = status
        self.usage = dict(usage or {})
        self.overrun_usd = float(overrun_usd)


@dataclass(frozen=True)
class ClaudeReply:
    """One Claude tool turn's answer (`claude_turn`): the client's `Answer` (its blocks, calls, usage and stop reason), the
    model, the settled cost (None when it is not verified: `held_usd` then stays booked until the true-up) and the
    gateway's request id."""

    answer: Any
    model: str
    cost_usd: float | None
    held_usd: float
    request_id: str
    #: Dollars the settled cost ran past the hold (0: the worst case held, as it always should).
    overrun_usd: float = 0.0


class _ClaudeHold:
    """One booked Claude hold (`ModelRouter._claude_admit`), settled once: the gateway's settled cost replaces it, a refusal
    the gateway made before reserving releases it, and an unknown bill leaves it filed (kv `claude_unsettled`) for
    `settle_claude_holds`. Settling takes the filing out in the same transaction that books the cost, and only while it is
    still there, so a true-up and the call's own answer never both book it."""

    def __init__(self, store: SwarmStore, *, request_id: str, usd: float, role: str, family: str | None, model: str, key: str):
        self.store, self.request_id, self.usd = store, request_id, usd
        self.role, self.family, self.model, self.key = role, family, model, key

    def resolve(self, amount: float, detail: Mapping[str, Any]) -> bool:
        """Book `amount` in place of the hold, once: only while the hold is still filed (a true-up may have)."""
        with self.store.atomic():
            filed = dict(self.store.get("claude_unsettled") or {})
            if self.request_id not in filed:
                return False
            filed.pop(self.request_id)
            self.store.put("claude_unsettled", filed)
            self.store.add_spend("claude", amount - self.usd, family=self.family,
                                 detail={"role": self.role, "model": self.model, "settles": self.key[:120], "request": self.request_id,
                                         **detail})
            return True

    def settle(self, cost: Any, detail: Mapping[str, Any]) -> float | None:
        try:
            amount = Decimal(str(cost)) if cost is not None else None
        except ArithmeticError:
            amount = None
        if amount is None or not amount.is_finite() or amount < 0:
            return None
        self.resolve(float(amount), detail)
        return float(amount)

    def unknown(self, reason: str) -> None:
        with self.store.atomic():
            filed = dict(self.store.get("claude_unsettled") or {})
            if self.request_id in filed:
                filed[self.request_id] = {**filed[self.request_id], "reason": reason[:120]}
                self.store.put("claude_unsettled", filed)

    def failed(self, exc: Any, billed: list[dict[str, Any]]) -> tuple[float | None, float]:
        """A ClaudeError's bill: (its settled cost or None, the hold left booked). A refusal, a truncation or an empty
        answer is billed at its usage and listed in `billed`; a refusal the gateway made before reserving (a 4xx, or one
        naming its `cap`) releases the hold; anything else unknown keeps it."""
        status = exc.status
        stop = getattr(exc.answer, "stop_reason", None) or type(exc).__name__
        cost = self.settle(exc.cost_usd, {"error": type(exc).__name__, "status": status, "stop_reason": stop})
        if cost is None:
            if exc.cap or (isinstance(status, int) and 400 <= status < 500):
                self.resolve(0.0, {"refused": status, "cap": exc.cap})
                return None, 0.0
            self.unknown(f"{type(exc).__name__}: {status}")
            return None, self.usd
        if cost > 0:
            billed.append({"route": "claude", "stop_reason": stop, "cost_usd": cost})
        return cost, 0.0


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
        #: (role, kind, to) -> {count, first_at, last_at, reason}: the fallbacks since the last `drain_fallbacks`.
        self._fallbacks: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._fallback_lock = threading.Lock()

    # ------------------------------------------------------------------ fallbacks (league/swarm/funding.py)
    def note_fallback(self, role: Any, kind: Any, to: str, reasons: Sequence[str] | str = ()) -> None:
        """Count one call of `role` that asked Claude and ended on `to` ("openai", "sail", or "none": no route), with the
        Claude route's failure `kind` and the last reason given. Never raises: counting is never a reason for a call to
        fail."""
        try:
            reason = reasons if isinstance(reasons, str) else (list(reasons)[-1] if reasons else "")
            claude = [r for r in ([reasons] if isinstance(reasons, str) else list(reasons)) if str(r).startswith("claude")]
            reason = str(claude[-1] if claude else reason)[:240]
            try:
                now = float(self.store.clock())
            except Exception:  # noqa: BLE001 - a store without a clock
                now = time.time()
            with self._fallback_lock:
                entry = self._fallbacks.setdefault((str(role), str(kind or "error"), str(to)),
                                                   {"count": 0, "first_at": now, "last_at": now, "reason": ""})
                entry["count"] += 1
                entry["last_at"] = now
                entry["reason"] = reason
        except Exception:  # noqa: BLE001
            pass

    def drain_fallbacks(self) -> dict[tuple[str, str, str], dict[str, Any]]:
        """The fallbacks counted since the last drain (`note_fallback`), and a fresh count."""
        with self._fallback_lock:
            drained, self._fallbacks = self._fallbacks, {}
        return drained

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
        try:  # Claude's holds, from the gateway's record of each call
            n += self.settle_claude_holds()
        except Exception:  # noqa: BLE001 - the holds stand until the next pass
            pass
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

    def claude_model(self, role: str | None = None) -> str:
        """The Claude model that answers `role`: its entry in `claude.role_model` {role: model id} when that is a non-empty
        string, else `claude.model`. A model with no verified price (`league.claude.MODEL_CEILINGS`) is never sent: its
        hold cannot be priced, so the role's call falls to its next route."""
        cfg = self._claude_cfg()
        models = cfg.get("role_model")
        chosen = models.get(role) if role is not None and isinstance(models, Mapping) else None
        return chosen.strip() if isinstance(chosen, str) and chosen.strip() else str(cfg.get("model"))

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

    @staticmethod
    def claude_system_blocks(system: str, prefix: Sequence[Mapping[str, Any]] | None = None) -> Any:
        """The `system` a Claude call sends: the role's text as it always was, or (Sept 29, 2026) the role's `prefix`
        blocks (the graveyard digest, each with its own cache marker) followed by the role's text, unmarked."""
        if not prefix:
            return system
        return [*({"text": b.get("text"), "cache": b.get("cache")} for b in prefix), {"text": system, "cache": None}]

    def _claude_hour(self) -> bool:
        """The 1-hour cache is sent only once the operator says the gateway admits it (`claude.cache_1h`)."""
        return self._claude_cfg().get("cache_1h") is True

    def claude_role_effort(self, role: str | None) -> str | None:
        """The role's own Claude effort (`claude.role_effort` {role: effort}, R11-3), or None: no entry, or one that is not
        an effort Claude takes (`league.claude.EFFORTS`: a typo never becomes the call's effort). It applies only when the
        caller names no effort; `claude.effort` stays every other role's default (the gate's reads keep "high")."""
        from ..claude import EFFORTS

        efforts = self._claude_cfg().get("role_effort")
        chosen = efforts.get(role) if role is not None and isinstance(efforts, Mapping) else None
        return chosen if isinstance(chosen, str) and chosen in EFFORTS else None

    def claude_request(self, system: str, user: str, *, schema: Mapping[str, Any] | None = None,
                       effort: str | None = None, role: str | None = None,
                       prefix: Sequence[Mapping[str, Any]] | None = None) -> tuple[dict[str, Any], float]:
        """The exact Claude request a role's question becomes, and the hold it needs (the gateway's worst case), on the
        role's model (`claude_model`). `effort` overrides the role's own effort (`claude.role_effort`, R11-3), which
        overrides `claude.effort`, for this call; `prefix` puts system blocks ahead of `system` (`claude_system_blocks`)."""
        from ..claude import EFFORTS, MAX_TOKENS, reservation_ceiling, request_body

        cfg = self._claude_cfg()
        effort = str(effort or self.claude_role_effort(role) or cfg.get("effort") or "high")
        # Streamed (`claude.stream`, the default since Sept 27, 2026): a high-effort answer outlasts Cloudflare's
        # 100-second wait for a silent origin (HTTP 524) unless its events flow as they are made.
        body = request_body(self.claude_model(role), self.claude_system_blocks(system, prefix), [{"role": "user", "content": user}],
                            max_tokens=int(cfg.get("max_tokens", MAX_TOKENS)), effort=effort if effort in EFFORTS else "high",
                            schema=schema, cache=True, stream=cfg.get("stream", True) is True, allow_hour=self._claude_hour())
        return body, float(reservation_ceiling(body))

    def claude_spent(self, *, role: str | None = None, since: float | None = None, family: str | None = None) -> float:
        """The swarm's Claude spend (holds included), for one role when named, one family when named, since an epoch when
        given.

        With `since`, a call counts from when its hold was booked, at its settled cost: the row that trues up a hold (the
        call's own `settles` row, or `settle_claude_holds`'s `settles_hold`) is booked when the bill lands, which may be
        after `since` for a hold booked before it (a call across 00:00 UTC, or a hold trued up after a gateway outage).
        Counting that row would put yesterday's release into today and lift today's line; it belongs to the hold's day."""
        sql, params = "SELECT usd, detail FROM spend WHERE kind='claude'", []
        if since is not None:
            sql += " AND epoch>=?"
            params.append(float(since))
        if family is not None:
            sql += " AND family=?"
            params.append(str(family))
        rows = []
        for row in self.store._all(sql, params):
            detail = json.loads(row["detail"] or "{}") or {}
            if role is None or detail.get("role") == role:
                rows.append((float(row["usd"]), detail))
        if since is None:
            return sum(usd for usd, _ in rows)
        booked = {d["request"] for _, d in rows if "hold" in d and d.get("request")}  # the calls held since `since`
        total = 0.0
        for usd, detail in rows:
            if "settles_hold" in detail or "settles" in detail:
                if (detail.get("settles_hold") or detail.get("request")) not in booked:
                    continue  # it settles a hold booked before `since`: that call is counted on its own day
            total += usd
        return total

    def claude_role_line(self, role: str) -> float | None:
        """The role's own daily Claude line in dollars (`claude.role_usd_day` {role: usd}), or None when it has none (no
        entry, or null). A line that is not a finite, non-negative number, or a `role_usd_day` that is not an object, is
        a line of 0: a typo never lifts a guard the operator meant to set."""
        lines = self._claude_cfg().get("role_usd_day")
        if lines is None:
            return None
        if not isinstance(lines, Mapping):
            return 0.0
        if lines.get(role) is None:
            return None
        value = lines[role]
        try:
            line = Decimal(str(value)) if not isinstance(value, bool) else Decimal("NaN")
        except ArithmeticError:
            return 0.0
        return float(line) if line.is_finite() and line >= 0 else 0.0

    #: A hold booked this long before the meter's read may not have reached the gateway when it was read: counted anyway.
    METER_MARGIN_SECONDS = 10.0

    def _claude_since_read(self) -> float:
        """The swarm's own Claude spend (holds included, each call at its settled cost) booked since the gateway's meter was
        last read (`ClaudeMeter.read_at`, less a margin), which that reading cannot show yet; 0 for a meter that does not
        say when it read."""
        read_at = getattr(self.claude_meter, "read_at", None)
        try:
            since = float(read_at) - self.METER_MARGIN_SECONDS
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, self.claude_spent(since=since)) if math.isfinite(since) else 0.0

    def claude_role_room(self, role: str) -> float | None:
        """Dollars left on the role's own Claude line this UTC day (its holds count until they settle; a call counts on the
        day its hold was booked, `claude_spent`), or None when the role has no line (`claude_role_line`)."""
        line = self.claude_role_line(role)
        if line is None:
            return None
        now = float(self.store.clock())
        spent = max(0.0, self.claude_spent(role=role, since=now - now % 86400))
        return max(0.0, line - spent)

    def claude_family_room(self, role: str, family: str | None, line: float) -> float:
        """Dollars left on one family's own Claude line for `role` this UTC day (its holds count until they settle)."""
        now = float(self.store.clock())
        return max(0.0, float(line) - max(0.0, self.claude_spent(role=role, family=family, since=now - now % 86400)))

    def _claude_admit(self, *, role: str, family: str | None, key: str, model: str, body: Mapping[str, Any], required: float,
                      errors: list[str], family_line: float | None = None, keep_usd: float = 0.0) -> tuple[str | None, str | None]:
        """Admit one Claude call and book its hold: (its X-LTCM-Request id, None) once the hold (spend kind `claude`) and its
        filing (kv `claude_unsettled`) are committed in one transaction, before the gateway hears of the call, so neither a
        crash nor a restart mid-call loses it; else (None, the kind: "line", "family_fuse" or "no_room") with the reason in
        `errors`. The lines are read before the meter's network read and again inside the write transaction (a concurrent
        call's committed hold counts): the role's own line today (`claude.role_usd_day`), the family's own line today when
        `family_line` is given, and the room above `claude.reserve_usd` and `claude.usd_cap`, less `keep_usd` (room this
        caller leaves to the other roles)."""
        request_id = re.sub(r"[^A-Za-z0-9:._-]+", "-", key)[:150] + ":" + secrets.token_hex(4)
        line = self.claude_role_room(role)  # the role's own line today (`claude.role_usd_day`), before the meter's read
        if line is not None and line < required:
            errors.append(f"claude: the {role} line for today has no room (${line:.2f} left of claude.role_usd_day; "
                          f"this call may cost ${required:.2f})")
            return None, "line"
        if family_line is not None:
            left = self.claude_family_room(role, family, family_line)
            if left < required:
                errors.append(f"claude: {family}'s own {role} line for today has no room (${left:.2f} left of "
                              f"${family_line:.2f}; this call may cost ${required:.2f})")
                return None, "family_fuse"
        room = self.claude_room()  # the meter's network read happens outside the write transaction
        if room - keep_usd < required:
            kept = f", ${keep_usd:.2f} of it kept for the other roles" if keep_usd else ""
            errors.append(f"claude: no room (${room:.2f} left above the reserve{kept}; this call may cost ${required:.2f})")
            return None, "no_room"
        admitted = False
        with self.store.atomic():
            # Every line is read again inside the write transaction: a concurrent call's committed hold counts.
            line = self.claude_role_room(role)
            if line is not None and line < required:
                errors.append(f"claude: the {role} line for today has no room")
                return None, "line"
            if family_line is not None and self.claude_family_room(role, family, family_line) < required:
                errors.append(f"claude: {family}'s own {role} line for today has no room")
                return None, "family_fuse"
            # The meter's reading is up to a minute old (its cache): the swarm's own Claude calls booked since it was
            # read are not in it yet, so they are taken off the gateway's room here (a concurrent admission's hold
            # counts, and the room kept for the other roles is never eroded by calls admitted in the same minute).
            if min(room - self._claude_since_read(), self._claude_cap_room()) - keep_usd >= required:
                self.store.add_spend("claude", required, family=family,
                                     detail={"role": role, "hold": key[:120], "request": request_id, "model": model,
                                             "max_tokens": body["max_tokens"], "effort": body["output_config"]["effort"]})
                filed = dict(self.store.get("claude_unsettled") or {})
                filed[request_id] = {"usd": required, "family": family, "role": role, "model": model,
                                     "at": self.store.clock(), "reason": "in flight"}
                self.store.put("claude_unsettled", filed)
                admitted = True
        if not admitted:  # only after the outer transaction's commit succeeds is it admitted
            errors.append("claude: the swarm's own Claude line has no room")
            return None, "no_room"
        return request_id, None

    def _ask_claude(self, *, role: str, system: str, user: str, family: str | None, key: str, need_usd: float,
                    schema: Mapping[str, Any] | None, errors: list[str], billed: list[dict[str, Any]],
                    effort: str | None = None, prefix: Sequence[Mapping[str, Any]] | None = None,
                    keep_truncated: bool = False, kinds: list[str] | None = None) -> dict[str, Any] | None:
        """The Claude route: the hold is booked (spend kind `claude`) and filed under the call's X-LTCM-Request id (kv
        `claude_unsettled`) in one transaction committed before the gateway hears of the call, so neither a crash nor a
        restart mid-call loses it: `settle_claude_holds` trues up whatever is still filed from the gateway's own record.
        The gateway's settled cost replaces the hold: a refusal, a truncation and an empty answer are billed at their
        usage, listed in `billed`, and fall through to the next route. A refusal the gateway made before reserving (a 4xx,
        or a refusal naming its `cap`: no key, the funded total, the kill switch) releases it. An unknown bill stays
        filed. Settling takes the filing out in the same transaction that books the cost, and only when it is still
        there, so a true-up and the call's own answer never both book it. None when there is no room, or the call
        refused or erred (the reason is in `errors`)."""
        from ..claude import ClaudeError, ClaudeTruncated

        kinds = kinds if kinds is not None else []
        model = self.claude_model(role)
        try:
            need = Decimal(str(need_usd))
            if not need.is_finite() or need < 0:
                raise ValueError("invalid Claude minimum reservation")
            body, ceiling = self.claude_request(system, user, schema=schema, effort=effort, role=role, prefix=prefix)
            required = float(max(need, Decimal(str(ceiling))))
            request_id, why = self._claude_admit(role=role, family=family, key=key, model=model, body=body, required=required,
                                                 errors=errors)
            if request_id is None:
                kinds.append(str(why or "no_room"))
                return None
        except Exception as exc:  # noqa: BLE001 - invalid/unknown admission falls through without dispatch
            errors.append(f"claude admission: {type(exc).__name__}: {str(exc)[:160]}")
            kinds.append("admission")
            return None
        hold = _ClaudeHold(self.store, request_id=request_id, usd=required, role=role, family=family, model=model, key=key)
        try:
            client = self.claude_factory(model)  # type: ignore[misc]
            hour = {"allow_hour": True} if self._claude_hour() else {}
            answer = client.ask(self.claude_system_blocks(system, prefix), user, agent=f"swarm-{role}", role=role,
                                max_tokens=body["max_tokens"], effort=body["output_config"]["effort"], schema=schema, cache=True,
                                request_id=request_id, stream=body.get("stream") is True, **hour)
        except ClaudeError as exc:
            cost, _ = hold.failed(exc, billed)
            errors.append(f"claude: {type(exc).__name__}: {str(exc)[:160]}")
            kinds.append("truncated" if isinstance(exc, ClaudeTruncated) else "error")
            if keep_truncated and isinstance(exc, ClaudeTruncated) and exc.answer is not None:
                # R11-3: the caller salvages a cut answer's complete parts itself (the architect's families) instead of
                # falling to the next route; it is billed like any cut answer (in `billed` too).
                return {"text": str(exc.answer.text or ""), "json": None, "route": "claude", "model": model, "cost_usd": cost,
                        "cost_verified": cost is not None, "held_usd": 0.0 if cost is not None else required,
                        "stop_reason": exc.answer.stop_reason, "usage": dict(exc.answer.usage or {}), "truncated": True}
            return None
        except Exception as exc:  # noqa: BLE001 - an unknown failure keeps the hold and falls through
            hold.unknown(type(exc).__name__)
            errors.append(f"claude: {type(exc).__name__}: {str(exc)[:160]}")
            kinds.append("error")
            return None
        cost = hold.settle(answer.cost_usd, {"stop_reason": answer.stop_reason}) if answer.cost_verified else None
        if cost is None:
            hold.unknown("the answer's cost was not verified")
        if not answer.text.strip():
            if cost:
                billed.append({"route": "claude", "stop_reason": "empty", "cost_usd": cost})
            errors.append("claude: the answer carried no text")
            return None
        data = answer.data if schema is not None else extract_json(answer.text)
        return {"text": answer.text, "json": data, "route": "claude", "model": model, "cost_usd": cost,
                "cost_verified": cost is not None, "held_usd": 0.0 if cost is not None else required,
                "stop_reason": answer.stop_reason, "usage": dict(answer.usage)}

    def claude_turn(self, *, role: str, family: str | None, key: str, system: Any, tools: Sequence[Mapping[str, Any]],
                    messages: Sequence[Mapping[str, Any]], effort: str = "medium", max_tokens: int = 16000,
                    timeout: float | None = None, family_usd_day: float | None = None, keep_usd: float = 0.0,
                    tool_choice: Any = "auto", model: str | None = None) -> ClaudeReply:
        """One turn of a role's tool loop on Claude (`_claude_turn_once`). A `ModelError` (other than `off`: Claude not
        configured for the role) is counted as a fallback to the caller's Sail turn (`note_fallback`) and raised as before."""
        try:
            return self._claude_turn_once(role=role, family=family, key=key, system=system, tools=tools, messages=messages,
                                          effort=effort, max_tokens=max_tokens, timeout=timeout, family_usd_day=family_usd_day,
                                          keep_usd=keep_usd, tool_choice=tool_choice, model=model)
        except ModelError as exc:
            if exc.kind != "off":
                self.note_fallback(role, exc.kind, "sail", str(exc))
            raise

    def _claude_turn_once(self, *, role: str, family: str | None, key: str, system: Any, tools: Sequence[Mapping[str, Any]],
                          messages: Sequence[Mapping[str, Any]], effort: str = "medium", max_tokens: int = 16000,
                          timeout: float | None = None, family_usd_day: float | None = None, keep_usd: float = 0.0,
                          tool_choice: Any = "auto", model: str | None = None) -> ClaudeReply:
        """One turn of a role's tool loop on Claude (the module docstring's CLAUDE'S TOOL TURNS): the exact body
        (`league.claude.tool_request_body`) on the role's model (`model`, else `claude_model(role)`: `claude.role_model`,
        else `claude.model`; an unpriced one is never sent) and its hold (the gateway's worst case), admitted within the role's line, the
        family's line (`family_usd_day`, a UTC day) and the funded room less `keep_usd`, then dispatched streamed and
        settled as `ask`'s Claude route. A `ClaudeReply` on an answer (`tool_use`, `end_turn`); otherwise a `ModelError`
        whose `kind` says why (a refusal and a truncation are billed at their usage and listed in `billed`; an unknown bill
        leaves `held_usd` booked). It never falls through to Sail: the caller does, so its turn keeps one transcript."""
        from ..claude import ClaudeError, ClaudeRefusal, ClaudeTruncated, reservation_ceiling, tool_request_body

        self._require_committed_store()
        if not self.claude_enabled(role):
            raise ModelError(f"claude: not configured for the {role} role", kind="off")
        errors: list[str] = []
        billed: list[dict[str, Any]] = []
        stream = self._claude_cfg().get("stream", True) is True
        model = model or self.claude_model(role)
        try:
            body = tool_request_body(model, system, messages, tools, tool_choice=tool_choice, max_tokens=max_tokens, effort=effort,
                                     stream=stream)
            required = float(reservation_ceiling(body))
            line = None if family_usd_day is None else _line(family_usd_day)
            keep = _line(keep_usd, invalid=math.inf)  # room kept for the other roles: a typo keeps it all
            request_id, kind = self._claude_admit(role=role, family=family, key=key, model=model, body=body, required=required,
                                                  errors=errors, family_line=line, keep_usd=keep)
        except Exception as exc:  # noqa: BLE001 - a body or an admission that does not read is no call
            raise ModelError(f"claude admission: {type(exc).__name__}: {str(exc)[:160]}", kind="admission") from None
        if request_id is None:
            raise ModelError("; ".join(errors), kind=kind or "no_room")
        hold = _ClaudeHold(self.store, request_id=request_id, usd=required, role=role, family=family, model=model, key=key)
        try:
            client = self.claude_factory(model)  # type: ignore[misc]
            answer = client.messages(system, messages, tools, agent=f"swarm-{role}", role=role, max_tokens=body["max_tokens"],
                                     effort=effort, tool_choice=tool_choice, request_id=request_id, stream=stream, timeout=timeout)
        except ClaudeError as exc:
            cost, held = hold.failed(exc, billed)
            if isinstance(exc, ClaudeRefusal):
                kind = "refusal"
            elif isinstance(exc, ClaudeTruncated):
                kind = "truncated"
            elif exc.status is not None or exc.cap:
                kind = "http"
            elif exc.answer is not None:
                kind = "answer"  # an answer that stopped for another reason (pause_turn)
            else:
                kind = "stream"
            usage = getattr(exc.answer, "usage", None)
            raise ModelError(f"claude: {type(exc).__name__}: {str(exc)[:160]}", kind=kind, billed=billed, held_usd=held,
                             status=exc.status if isinstance(exc.status, int) else None,
                             usage=usage if isinstance(usage, Mapping) else None,
                             overrun_usd=max(0.0, (cost or 0.0) - required)) from None
        except Exception as exc:  # noqa: BLE001 - an unknown failure keeps the hold
            hold.unknown(type(exc).__name__)
            raise ModelError(f"claude: {type(exc).__name__}: {str(exc)[:160]}", kind="unknown", held_usd=required) from None
        cost = hold.settle(answer.cost_usd, {"stop_reason": answer.stop_reason}) if answer.cost_verified else None
        if cost is None:
            hold.unknown("the answer's cost was not verified")
        return ClaudeReply(answer=answer, model=model, cost_usd=cost, held_usd=0.0 if cost is not None else required,
                           request_id=request_id, overrun_usd=max(0.0, (cost or 0.0) - required))

    def settle_claude_holds(self, *, min_age: float = 60.0, absent_after: float = 1800.0, budget_seconds: float = 30.0) -> int:
        """True up the Claude holds whose bill the House never saw (the call's answer was lost, or the swarm restarted
        mid-call), from the gateway's record of each call: its settled (or kept, unknown) cost replaces the hold; a hold
        the gateway swept to zero, or a call the gateway has no record of after `absent_after` seconds (it never reached
        the meter), is released; a call still held waits. It runs on the main loop, so it stops at the first gateway
        read that fails and after `budget_seconds`: a hung gateway never holds the heartbeat. Returns how many settled."""
        import time as _time

        deadline = _time.monotonic() + float(budget_seconds)
        holds = dict(self.store.get("claude_unsettled") or {})
        if not holds or self.claude_factory is None:
            return 0
        try:
            client = self.claude_factory(str(self._claude_cfg().get("model") or "claude-opus-5-5"))
        except Exception:  # noqa: BLE001
            return 0
        n = 0
        for request_id, hold in sorted(holds.items()):
            age = self.store.clock() - float(hold.get("at") or 0)
            if age < min_age:
                continue
            if _time.monotonic() >= deadline:
                break  # the rest wait for the next pass
            record = client.settlement(request_id) if callable(getattr(client, "settlement", None)) else None
            if record is None:
                break  # the gateway cannot be read now: every hold stands until the next pass
            state = record.get("state")
            if state in ("settled", "unknown") and record.get("cost_usd") is not None:
                cost = float(record["cost_usd"])
            elif state == "released" or (state == "absent" and age >= absent_after):
                cost = 0.0
            else:
                continue
            with self.store.atomic():
                current = dict(self.store.get("claude_unsettled") or {})
                if request_id not in current:
                    continue
                current.pop(request_id)
                self.store.put("claude_unsettled", current)
                self.store.add_spend("claude", cost - float(hold["usd"]), family=hold.get("family"),
                                     detail={"role": hold.get("role"), "model": hold.get("model"), "settles_hold": request_id,
                                             "gateway_state": state})
            n += 1
        return n

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
            schema: Mapping[str, Any] | None = None, claude_effort: str | None = None,
            claude_prefix: Sequence[Mapping[str, Any]] | None = None, claude_system: str | None = None,
            claude_user: str | None = None, claude_keep_truncated: bool = False) -> dict[str, Any]:
        """A one-shot question for a role (the architect, the reviewer, the auditor, a rewrite, the diagnostician).

        The paid routes in order, then Sail: CLAUDE first when `claude` and the role is one of `claude.roles` and the
        funded total has room above its reserve and the role's own line today has room (`claude.role_usd_day`,
        `_ask_claude`); OPENAI when it has room for both `need_usd` and the actual request's standard-service maximum
        (`_ask_openai`). `rotate` alternates the two paid routes' order every other call for the role (the architect's
        diversity: Astra's pass, when OpenAI has room, else Claude's). A paid route that refuses, errs or has no room
        falls to the next; `sail_profile` None means no Sail fallback (a ModelError instead). `desk` and `cap_usd_day`
        are the Provider's fuse for the Sail call. Admission and the durable hold are atomic across store connections;
        verified cost settles it, a 4xx refusal releases it, and an unknown bill retains it. Unknown cost is reported as
        None with held_usd, never as a free answer. A ModelError's `billed` lists the paid attempts that were billed
        without an answer (`claude_effort` overrides `claude.effort`).

        The Claude route alone may ask a different question (Sept 29, 2026): `claude_prefix` (system blocks ahead of the
        role's text, e.g. the whole graveyard as a cached digest), `claude_system` and `claude_user` replace `system` and
        `user` there only. OpenAI and Sail always get `system` and `user` (their contexts are small).

        `claude_keep_truncated` (R11-3, the architect): a Claude answer cut at max_tokens is returned as the answer, marked
        `truncated` with its partial text, instead of falling to the next route; the caller salvages it. A ModelError's
        `kind` is the Claude route's last failure ("line", "no_room", "family_fuse", "admission", "truncated", "error")
        when the call had no fallback after it.

        A Sail answer says whether it was cut (Oct 1, 2026: from 08:15Z every architect pass on Kimi-K3 came back
        `incomplete` at max_output_tokens, most of it reasoning, and read as no proposals): `truncated` (the Provider's
        `incomplete`), `incomplete_reason` (e.g. "max_output_tokens"; None when complete or not given) and `usage` (the
        Provider's, reasoning tokens included). Its `text` and `json` are as before, so a caller that does not read
        `truncated` (the gate's review and audit, the strategist, the stall rewrite) sees the same answer; the architect
        salvages a cut answer's complete families."""
        self._require_committed_store()
        errors: list[str] = []
        billed: list[dict[str, Any]] = []
        kinds: list[str] = []
        routes = (["claude"] if claude and self.claude_enabled(role) else []) + (["openai"] if openai_model else [])
        if rotate and len(routes) == 2 and self._turn(role) % 2 == 1:
            routes.reverse()
        claude_failed: str | None = None  # the Claude route's failure kind, once it was asked and gave no answer
        for route in routes:
            if route == "claude":
                result = self._ask_claude(role=role, system=claude_system if claude_system is not None else system,
                                          user=claude_user if claude_user is not None else user, family=family, key=key,
                                          need_usd=need_usd, schema=schema, errors=errors, billed=billed, effort=claude_effort,
                                          prefix=claude_prefix, keep_truncated=claude_keep_truncated, kinds=kinds)
            else:
                result = self._ask_openai(role=role, system=system, user=user, family=family, key=key, openai_model=openai_model,
                                          max_output=max_output, effort=effort, need_usd=need_usd, errors=errors)
            if result is not None:
                if claude_failed is not None:
                    self.note_fallback(role, claude_failed, route, errors)
                return result
            if route == "claude":
                claude_failed = kinds[-1] if kinds else "error"
        # A failed COMMIT/ROLLBACK may have left the admission store unusable. Do not turn that
        # failure into another paid call on the fallback provider.
        self._require_committed_store()
        if claude_failed is not None:
            self.note_fallback(role, claude_failed, "sail" if sail_profile else "none", errors)
        if not sail_profile:
            raise ModelError("; ".join(errors) or "no paid route was available, and this role has no Sail fallback", billed=billed,
                             kind=kinds[-1] if kinds else "error")
        items = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            response = self.sail(sail_profile, items, family=desk or family or "swarm", key=key, effort=effort, max_output=max_output,
                                 cache_key=f"swarm-{role}", tool_choice="auto",
                                 cap_usd_day=float(cap_usd_day if cap_usd_day is not None else
                                                   self.settings.get("researcher", {}).get("floor_usd_day", 60.0)),
                                 kind="sail_model")
        except Exception as exc:  # noqa: BLE001
            raise ModelError("; ".join(errors + [f"sail: {type(exc).__name__}: {getattr(exc, 'code', '') or str(exc)[:160]}"]),
                             billed=billed) from None
        text = response.output_text or ""
        usage = getattr(response, "usage", None)
        reason = getattr(response, "incomplete_reason", None)
        return {"text": text, "json": extract_json(text), "route": "sail", "model": sail_profile,
                "cost_usd": float(response.cost_usd or 0), "fallback_reasons": errors,
                "truncated": getattr(response, "incomplete", False) is True,
                "incomplete_reason": reason if isinstance(reason, str) else None,
                "usage": dict(usage) if isinstance(usage, Mapping) else {}}

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


def _line(value: Any, *, invalid: float = 0.0) -> float:
    """A dollar amount from settings: a finite, non-negative number, else `invalid` (0 for a line, everything for a room
    kept back: a typo never lifts a guard)."""
    try:
        line = float(value) if not isinstance(value, bool) else math.nan
    except (TypeError, ValueError):
        return invalid
    return line if math.isfinite(line) and line >= 0 else invalid


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


__all__ = ["ModelRouter", "ModelError", "ClaudeReply", "build_router", "extract_json"]
