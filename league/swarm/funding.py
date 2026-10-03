"""FUNDING CLIFFS, SAID AHEAD (Release A, Sept 30, 2026): a paid line never runs out without the operator hearing first.

On Sept 30 four cliffs stood, and none of them would have said a word (LTCM v3 retired the fourth, the burst's end: the
Sail guard's daily cap is now THE BUDGET's, league/ops/budget.py, whose own card notices go to the owner by mail):

- CLAUDE'S ROOM. The gateway's funded Claude total above `claude.reserve_usd` (and the swarm's own `claude.usd_cap`) runs
  out; every role in `claude.roles` then quietly takes its next route (`ModelRouter.ask`: OpenAI, then Sail) and the
  Claude-only diagnostician stops.
- THE OPENAI MONTH. The gateway's frontier month is a FUNDED month (`FRONTIER_FUNDED_MONTH`): its cap goes to $0 at the
  next UTC month boundary unless the owner funds the next one.
- THE SAIL GUARD. `SailGuard` brakes the Gym and the researchers when Sail's balance falls under its line (2 x the
  House's burn + `guard.margin_usd`), and releases only at the line + `guard.release_margin_usd`: while braked under
  that release line the cliff stays out (state "braked", `release_usd`), even after a top-up over the line itself.
- (retired) THE BURST'S END: `guard.burst_until` and `guard.after_burst_usd_day` are gone with the burst.

`FundingWatch.tick()` runs on the swarm's main loop (`Swarm.step`) and does two cheap things:

1. Every `funding.every_seconds` (300) it assesses each cliff from what the swarm already reads: the router's funded
   Claude room (`ModelRouter.claude_funded_room`, the gateway meter behind its two-minute cache; the budget's daily line
   is not a cliff), the frontier month's `remaining()`, the
   guard's last reading (`SailGuard.last`: balance, line, Sail's own 24-hour burn) and the swarm's spend rows. RUNWAY is
   the room left before the cliff divided by the MEASURED burn: the larger of the last 24 hours' and the last
   `funding.burn_window_hours` (6) hours' rate, each from the swarm's booked spend and from the meter's own fall between
   this watch's samples (`funding_samples`, one every ten minutes, 26 hours kept; a top-up is a rise, never negative
   spend). The larger rate gives the earlier warning. Calendar cliffs count the hours to their date.
2. Every `funding.fallback_flush_seconds` (30) it reads the router's FALLBACKS (`ModelRouter.drain_fallbacks`: a role's
   call that asked Claude and ended on another route, counted in memory by role, the Claude route's failure kind and
   where it went) and says them.

TIERS. Each cliff's hours go through its leads (`funding.lead_hours`, hours before the cliff, most distant first):
"notice" inside the first, "warning" inside the second, "urgent" inside the third, "out" once the cliff is here, "ok"
before any of them. Defaults: Claude 48/24/6, the Sail guard 72/24/6, the OpenAI month 48/24/6.

DEDUPED (`FundingWatch._decide`). Each cliff (a calendar cliff keyed by its date) says a tier as ONE `swarm.status`
event with `alert: true` when it RISES to it; a tier already said is said again only after `funding.repeat_hours` (12),
and then only as a rise or while a warning, urgent or out stands (a calendar cliff's out is said once). A fall is
silent: a runway flapping across a lead says nothing new, and a fall of two tiers or more (a top-up) makes the tiers
above it news again. A cliff that recovers past `funding.clear_factor` (1.5) x its first lead is said once as a
`funding_ok` status event without an alert, and forgotten. A runway with no burn measured (nothing booked, the meter
still) is NOT IN SIGHT: state "no burn", no tier, so it is neither a recovery nor a reason to say a tier again, and the
next measured assessment is judged against what was already said. What was said lives in the swarm's store
(`funding_alerts`), so a restart says nothing again. A fallback is said the first time its (role, kind, route) is
seen, then at most once every `funding.fallback_every_seconds` (6 h) with the count since, from `funding_fallbacks`;
only a fallback for want of room (`no_room`, a funding cliff) is an alert, the rest (a role's own daily line, an error)
are events the operator reads without an alert.

WHERE IT SHOWS. The House's swarm step (`hook.SwarmStep`) mirrors every `swarm.status` row into the House ledger
(private) and turns each one with `alert: true` into a House `ops.alert` at level WARNING, so the watch
(`scripts/floor_watch.py`) and health see it; a warning is never an error, so no watchdog rolls a release back for a
funding cliff. The last assessment is in the swarm's heartbeat (`status.funding`). Nothing here is published: the site
never shows balances, and no account number, key or secret is read.

A calendar cliff that passed more than `funding.after_end_hours` (48) ago is history, not news: a swarm started after it
says nothing. `funding.enabled` false turns the watch off. Every setting is read from `<state>/swarm.json` "funding" at
each tick (no deploy); a value that is not a finite, non-negative number is its default.

Research-side: it reads the router, the guard and the store and writes only its own kv keys and events. It never changes
a route, a line, a hold or the guard's decision. Standard library only.
"""

from __future__ import annotations

import datetime as dt
import math
import threading
import time
from typing import Any, Callable, Mapping, Sequence


#: The tiers, least severe first.
TIERS = ("ok", "notice", "warning", "urgent", "out")
RANK = {name: i for i, name in enumerate(TIERS)}
#: The tiers a standing runway is said again at (every `repeat_hours`).
REPEATED = ("warning", "urgent", "out")
#: The Claude route's failure kinds that are a funding cliff: the only fallbacks that are alerts.
FUNDING_KINDS = ("no_room",)

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "every_seconds": 300.0,
    "fallback_flush_seconds": 30.0,
    "lead_hours": {"claude_room": [48.0, 24.0, 6.0], "sail_guard": [72.0, 24.0, 6.0], "openai_month": [48.0, 24.0, 6.0]},
    "repeat_hours": 12.0,
    "clear_factor": 1.5,
    "claude_out_usd": 2.0,
    "burn_window_hours": 6.0,
    "after_end_hours": 48.0,
    "fallback_every_seconds": 21600.0,
}
#: A sample of a meter at most this often (`funding_samples`), and kept this long.
SAMPLE_SECONDS = 600.0
SAMPLES_KEPT_SECONDS = 26 * 3600.0
#: A rate from samples needs at least this long between its two ends.
MIN_SPAN_SECONDS = 3600.0
#: A guard reading older than this is not a reading of now.
GUARD_STALE_SECONDS = 3600.0
#: What was said is forgotten after this long without an assessment (`funding_alerts`, `funding_fallbacks`).
FORGET_SECONDS = 40 * 86400.0
#: After a month boundary, a reading with room may still be the old month's (the meter's cache): wait this long before
#: counting the next month as funded.
ROLLOVER_GRACE_SECONDS = 900.0


def _number(value: Any, default: float) -> float:
    """A finite, non-negative number, else `default` (a bool is not a number)."""
    if isinstance(value, bool):
        return float(default)
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float(default)
    return out if math.isfinite(out) and out >= 0 else float(default)


def _stamp(t: float) -> str:
    return dt.datetime.fromtimestamp(float(t), dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def month_end(now: float) -> float:
    """The first instant of the next UTC month: when a funded gateway month's cap goes to $0."""
    day = dt.datetime.fromtimestamp(float(now), dt.timezone.utc)
    year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return dt.datetime(year, month, 1, tzinfo=dt.timezone.utc).timestamp()


def tier_for(hours: float | None, leads: Sequence[float]) -> str:
    """The tier of a cliff `hours` away through its leads (hours before it, any order): "out" at or past it, the most
    severe lead it is inside, "ok" outside them all or when it is not in sight (None)."""
    if hours is None:
        return "ok"
    if hours <= 0:
        return "out"
    tier = "ok"
    for name, lead in zip(("notice", "warning", "urgent"), sorted(leads, reverse=True)):
        if hours <= lead:
            tier = name
    return tier


def _hours_text(hours: float) -> str:
    return f"{hours:.0f} h" if hours >= 10 else f"{hours:.1f} h"


class FundingWatch:
    """The watch (the module docstring). `router`, `guard` and `log` may be anything with the attributes it reads (a
    missing one is a cliff not in sight, never an error)."""

    def __init__(self, store: Any, settings: Mapping[str, Any], *, router: Any = None, guard: Any = None,
                 clock: Callable[[], float] = time.time, log: Callable[[str], None] | None = None):
        self.store = store
        self.settings = settings
        self.router = router
        self.guard = guard
        self.clock = clock
        self.log = log or (lambda message: None)
        self.checked_at = float("-inf")
        self.flushed_at = float("-inf")
        #: The last assessment, cliff -> {tier, hours, ...}: the heartbeat's `status.funding`.
        self.last: dict[str, Any] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ settings
    @property
    def cfg(self) -> dict[str, Any]:
        raw = self.settings.get("funding") if isinstance(self.settings, Mapping) else None
        raw = raw if isinstance(raw, Mapping) else {}
        out = {k: v for k, v in DEFAULTS.items() if k != "lead_hours"}
        for key, default in out.items():
            if key == "enabled":
                out[key] = raw.get(key, default) is not False
            elif key in raw:
                out[key] = _number(raw[key], default)
        leads = dict(DEFAULTS["lead_hours"])
        given = raw.get("lead_hours")
        if isinstance(given, Mapping):
            for cliff, default in DEFAULTS["lead_hours"].items():
                value = given.get(cliff)
                if isinstance(value, (list, tuple)) and value:
                    parsed = [_number(v, -1.0) for v in value][:3]
                    if all(v > 0 for v in parsed):
                        leads[cliff] = parsed
        out["lead_hours"] = leads
        return out

    # ------------------------------------------------------------------ the loop calls this
    def tick(self) -> dict[str, Any]:
        """Flush fallbacks (every `fallback_flush_seconds`) and assess the cliffs (every `every_seconds`). Returns what was
        said this tick (the events' payloads)."""
        cfg = self.cfg
        if not cfg["enabled"]:
            return {}
        now = float(self.clock())
        said: dict[str, Any] = {}
        with self._lock:
            if now - self.flushed_at >= cfg["fallback_flush_seconds"]:
                self.flushed_at = now
                said["fallbacks"] = self.flush_fallbacks(now, cfg)
            if now - self.checked_at >= cfg["every_seconds"]:
                self.checked_at = now
                said["cliffs"] = self.check(now, cfg)
        return {k: v for k, v in said.items() if v}

    def check(self, now: float | None = None, cfg: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        """Assess every cliff once and say what the dedupe allows. Returns the payloads said."""
        now = float(self.clock()) if now is None else float(now)
        cfg = cfg or self.cfg
        said: list[dict[str, Any]] = []
        assessed: dict[str, Any] = {}
        for name, assess in (("claude_room", self.claude_room), ("sail_guard", self.sail_guard),
                             ("openai_month", self.openai_month)):
            try:
                found = assess(now, cfg)
                payload = self._decide(found, now, cfg) if found.get("tier") is not None else None
            except Exception as exc:  # noqa: BLE001 - one cliff that cannot be read or said never hides the others
                found = {"cliff": name, "state": "error", "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
                payload = None
            assessed[name] = {k: v for k, v in found.items() if k not in ("text", "clear_text")}
            if payload is not None:
                said.append(payload)
        self.last = {"at": now, **assessed}
        return said

    # ------------------------------------------------------------------ the dedupe
    def _decide(self, found: Mapping[str, Any], now: float, cfg: Mapping[str, Any]) -> dict[str, Any] | None:
        """Say `found` or not, and remember it (`funding_alerts` {key: {tier: where it stands now, told: {tier: when it was
        said}, worst: the most severe tier said}}).

        - A RISE to a tier not yet said is said at once (the first assessment of a cliff is a rise from "ok").
        - A tier already said is said again only after `repeat_hours`, and then only as a rise or while a warning, urgent
          or out stands: a reminder twice a day. A calendar cliff's out is never said twice.
        - A FALL is silent. A fall of one tier (a runway flapping across a lead) keeps what was said, so the rise back says
          nothing new for `repeat_hours`; a fall of two tiers or more (a top-up) forgets the tiers above it, so a later
          rise is news again. A fall to a tier never said counts its reminders from now.
        - A recovery past `clear_factor` x the first lead (a measured one: no burn is not a recovery) is one `funding_ok`
          event (no alert), and the key is forgotten."""
        key, tier = str(found["key"]), str(found["tier"])
        leads = cfg["lead_hours"].get(found["cliff"]) or [0.0]
        if tier == "ok" and found.get("hours") is None:
            # Not in sight (no burn measured): neither a tier nor a recovery. What was said, and where it stood, is kept, so
            # the next measured assessment is judged against it (never a fresh alert, never a two-tier wipe).
            return None
        payload = None
        with self.store.atomic():
            stored = self.store.get("funding_alerts") or {}
            said = {k: dict(v) for k, v in stored.items() if isinstance(v, Mapping) and now - float(v.get("at") or 0) < FORGET_SECONDS}
            prev = said.get(key)
            hours = found.get("hours")
            # A runway with no burn measured (hours None) is not in sight: never a recovery by itself.
            if tier == "ok" and prev is not None and hours is not None and float(hours) > float(cfg["clear_factor"]) * max(leads):
                said.pop(key)
                payload = {"action": "funding_ok", "alert": False, "cliff": found["cliff"], "key": key, "was": prev.get("worst"),
                           "text": found.get("clear_text") or f"funding: {found['cliff']} recovered",
                           **{k: v for k, v in found.items() if k not in ("text", "clear_text", "tier", "key", "cliff")}}
            elif prev is not None or tier != "ok":
                row = prev if prev is not None else {"cliff": found["cliff"], "tier": "ok", "told": {}, "worst": None}
                told = {t: at for t, at in dict(row.get("told") or {}).items() if isinstance(at, (int, float))}
                standing = RANK.get(str(row.get("tier")), 0)
                if RANK.get(tier, 0) <= standing - 2:  # a real recovery, not a flap: the tiers above are news again
                    told = {t: at for t, at in told.items() if RANK.get(t, 0) <= RANK.get(tier, 0)}
                if tier != "ok":
                    fresh = tier not in told
                    rising = RANK.get(tier, 0) > standing
                    due = not fresh and now - float(told[tier]) >= float(cfg["repeat_hours"]) * 3600 \
                        and not (tier == "out" and found.get("calendar"))
                    if (fresh and rising) or (due and (rising or tier in REPEATED)):
                        payload = {"action": "funding_alert", "alert": True, "cliff": found["cliff"], "key": key, "tier": tier,
                                   "repeat": not fresh,
                                   **{k: v for k, v in found.items() if k not in ("tier", "key", "cliff", "clear_text")}}
                        told[tier] = now
                        worst = row.get("worst")
                        row["worst"] = tier if worst is None or RANK.get(tier, 0) > RANK.get(str(worst), 0) else worst
                    elif fresh:
                        told[tier] = now  # a fall to a tier never said: its reminders count from now
                row.update(tier=tier, told=told, at=now)  # `at`: last assessed (a standing cliff is never forgotten)
                said[key] = row
            if said != stored:
                self.store.put("funding_alerts", said)
            if payload is not None:
                self.store.event("swarm.status", None, payload)
        if payload is not None:
            self.log(str(payload.get("text") or payload.get("action")))
        return payload

    # ------------------------------------------------------------------ measured burn
    def _sample(self, name: str, now: float, *, window_hours: float, total: float | None = None,
                balance: float | None = None) -> float | None:
        """Feed one meter reading into `funding_samples` and return its rate over the last 24 hours and the burn window,
        the larger, in dollars an hour (None without two samples at least `MIN_SPAN_SECONDS` apart). `total` is a
        cumulative spend (the gateway's Claude `spent_usd`); `balance` a balance whose falls are the spend (a rise is a
        top-up, never negative spend)."""
        with self.store.atomic():
            samples = dict(self.store.get("funding_samples") or {})
            series = dict(samples.get(name) or {})
            points = [p for p in series.get("points") or [] if isinstance(p, (list, tuple)) and len(p) == 2
                      and now - float(p[0]) <= SAMPLES_KEPT_SECONDS and float(p[0]) <= now]
            if balance is not None:
                last = series.get("last")
                falls = float(series.get("falls") or 0.0)
                if isinstance(last, (int, float)) and balance < float(last):
                    falls += float(last) - balance
                series.update(last=balance, falls=round(falls, 6))
                current = falls
            elif total is not None:
                current = float(total)
            else:
                return None
            if not points or now - float(points[-1][0]) >= SAMPLE_SECONDS:
                points.append([now, round(current, 6)])
            series["points"] = points
            samples[name] = series
            self.store.put("funding_samples", samples)
        window = max(1.0, float(window_hours)) * 3600
        rates = []
        for span in (86400.0, window):
            old = [p for p in points if now - float(p[0]) <= span]
            if old and now - float(old[0][0]) >= MIN_SPAN_SECONDS:
                rates.append(max(0.0, current - float(old[0][1])) / ((now - float(old[0][0])) / 3600))
        return max(rates) if rates else None

    def _booked_rate(self, kinds: Sequence[str], now: float, cfg: Mapping[str, Any]) -> float:
        """The swarm's own booked spend of `kinds`, dollars an hour: the larger of the last 24 hours' and the window's."""
        window = max(1.0, float(cfg["burn_window_hours"]))
        day = max(0.0, float(self.store.spent(list(kinds), since=now - 86400))) / 24
        recent = max(0.0, float(self.store.spent(list(kinds), since=now - window * 3600))) / window
        return max(day, recent)

    # ------------------------------------------------------------------ the cliffs
    def claude_room(self, now: float, cfg: Mapping[str, Any]) -> dict[str, Any]:
        router = self.router
        meter = getattr(router, "claude_meter", None)
        enabled = getattr(router, "claude_enabled", None)
        claude = self.settings.get("claude") if isinstance(self.settings.get("claude"), Mapping) else {}
        roles = [str(r) for r in claude.get("roles") or [] if callable(enabled) and enabled(r)]
        if meter is None or not roles:
            return {"cliff": "claude_room", "state": "off"}
        if meter.remaining() is None:
            return {"cliff": "claude_room", "state": "unreadable"}
        # The FUNDED room: the budget's daily Claude line (league/ops/budget.py) runs out every day by design, not a cliff.
        funded = getattr(router, "claude_funded_room", None)
        room = float(funded() if callable(funded) else router.claude_room())
        spent = (getattr(meter, "last", None) or {}).get("spent_usd")
        sampled = (self._sample("claude", now, window_hours=cfg["burn_window_hours"], total=_number(spent, -1.0))
                   if _number(spent, -1.0) >= 0 else None)
        rate = max(self._booked_rate(["claude"], now, cfg), sampled or 0.0)
        out_usd = float(cfg["claude_out_usd"])
        left = room - out_usd
        if left > 0 and rate <= 0:
            # No burn measured (nothing booked, the meter still): the runway is not in sight, which is neither a tier nor a
            # recovery. No tier, so the dedupe keeps what it said and the heartbeat says why.
            return {"cliff": "claude_room", "key": "claude_room", "state": "no burn", "room_usd": round(room, 2),
                    "burn_usd_per_hour": 0.0, "hours": None, "roles": roles}
        hours = 0.0 if left <= 0 else left / rate
        tier = tier_for(hours, cfg["lead_hours"]["claude_room"])
        who = ", ".join(roles)
        found = {"cliff": "claude_room", "key": "claude_room", "tier": tier, "state": "measured", "room_usd": round(room, 2),
                 "burn_usd_per_hour": round(rate, 4), "hours": round(hours, 1), "roles": roles,
                 "runs_out_at": _stamp(now + hours * 3600)}
        if tier == "out":
            found["text"] = (f"funding: Claude's room is spent (${room:.2f} left above the reserve): {who} fall back to "
                             "their next route (OpenAI, then Sail) and a Claude-only role stops, until the funded total is "
                             "topped up (the owner's step)")
        else:
            found["text"] = (f"funding: Claude's room runs out in about {_hours_text(hours)} (about {found['runs_out_at']}): "
                             f"${room:.2f} left above the reserve at the measured ${rate:.2f}/h; then {who} fall back to "
                             "their next route (Sail) and a Claude-only role stops, until the funded total is topped up")
        found["clear_text"] = f"funding: Claude's room recovered (${room:.2f} left above the reserve)"
        return found

    def sail_guard(self, now: float, cfg: Mapping[str, Any]) -> dict[str, Any]:
        last = getattr(self.guard, "last", None) or {}
        balance, line = last.get("balance"), last.get("line")
        at = _number(last.get("at"), 0.0)
        if not isinstance(balance, (int, float)) or isinstance(balance, bool) or not isinstance(line, (int, float)) \
                or now - at > GUARD_STALE_SECONDS:
            return {"cliff": "sail_guard", "state": "unreadable"}
        balance, line = float(balance), float(line)
        burn_day = _number(last.get("burn_day"), 0.0)
        sampled = self._sample("sail", now, window_hours=cfg["burn_window_hours"], balance=balance)
        rate = max(burn_day / 24, sampled or 0.0)
        # A braked guard releases only at its line plus `guard.release_margin_usd` (`SailGuard.check`'s hysteresis): while
        # braked under that, the balance still holds the brake, so the cliff stays out after a top-up too small to release.
        guard_cfg = self.settings.get("guard") if isinstance(self.settings.get("guard"), Mapping) else {}
        release = line + _number(guard_cfg.get("release_margin_usd", 5.0), 5.0)
        held = last.get("braked") is True and balance < release
        left = 0.0 if held else balance - line
        if left > 0 and rate <= 0:
            # No burn measured: the runway is not in sight (neither a tier nor a recovery; the dedupe keeps what it said).
            return {"cliff": "sail_guard", "key": "sail_guard", "state": "no burn", "balance_usd": round(balance, 2),
                    "line_usd": round(line, 2), "burn_usd_per_hour": 0.0, "hours": None}
        hours = 0.0 if left <= 0 else left / rate
        tier = tier_for(hours, cfg["lead_hours"]["sail_guard"])
        found = {"cliff": "sail_guard", "key": "sail_guard", "tier": tier, "state": "braked" if held else "measured",
                 "balance_usd": round(balance, 2), "line_usd": round(line, 2), "burn_usd_per_hour": round(rate, 4),
                 "hours": round(hours, 1), "brakes_at": _stamp(now + hours * 3600)}
        if held:
            found["release_usd"] = round(release, 2)
        if tier == "out" and held and balance >= line:
            found["text"] = (f"funding: the Sail guard is still braked (balance ${balance:.2f} is over its line ${line:.2f} "
                             f"but under its release line ${release:.2f}): the Gym and the researchers stay stopped until "
                             "Sail is topped up past it (the owner's step); the House keeps running")
        elif tier == "out":
            found["text"] = (f"funding: the Sail guard's line is reached (balance ${balance:.2f}, line ${line:.2f}): the "
                             "Gym and the researchers stop until Sail is topped up (the owner's step); the House keeps running")
        else:
            found["text"] = (f"funding: the Sail guard brakes the swarm in about {_hours_text(hours)} (about "
                             f"{found['brakes_at']}): balance ${balance:.2f}, line ${line:.2f}, at the measured "
                             f"${rate:.2f}/h; then the Gym and the researchers stop (the House keeps running)")
        found["clear_text"] = f"funding: the Sail guard's runway recovered (balance ${balance:.2f}, line ${line:.2f})"
        return found

    def openai_models(self) -> dict[str, str]:
        """The swarm's settings that name an OpenAI model (each falls to its next route once the month is $0), read as their
        callers read them: the gate's audit asks GPT-6 Astra when `gate.audit_openai_model` is absent (`Gate.audit`)."""
        named = {}
        for section, key, absent in (("architect", "openai_model", None), ("gate", "review_openai_model", None),
                                     ("gate", "audit_openai_model", "gpt-6-astra")):
            block = self.settings.get(section)
            value = block.get(key, absent) if isinstance(block, Mapping) else absent
            if isinstance(value, str) and value.strip():
                named[f"{section}.{key}"] = value.strip()
        return named

    def openai_month(self, now: float, cfg: Mapping[str, Any]) -> dict[str, Any]:
        month = getattr(self.router, "month", None)
        if month is None:
            return {"cliff": "openai_month", "state": "off"}
        raw = month.remaining()
        if raw is None:
            return {"cliff": "openai_month", "state": "unreadable"}
        remaining = float(raw)
        end = month_end(now)
        named = self.openai_models()
        uses = ("; roles naming an OpenAI model fall to their next route: " + ", ".join(f"{k}={v}" for k, v in named.items())
                if named else "; no swarm role names an OpenAI model, so the swarm is unaffected")
        seen = self.store.get("funding_openai_seen") or {}
        seen_end = _number(seen.get("end"), 0.0) if isinstance(seen, Mapping) else 0.0
        if seen_end and now >= seen_end:
            # A month ended since a reading that had room: the rollover is the cliff (said once, while it is news). A
            # reading with room just after the boundary may be the old month's, cached (`FrontierMonth` keeps one for its
            # ttl): the next month counts as funded only once `ROLLOVER_GRACE_SECONDS` have passed.
            if remaining > 0 and now - seen_end < ROLLOVER_GRACE_SECONDS:
                return {"cliff": "openai_month", "state": "rolling over", "remaining_usd": round(remaining, 2)}
            self.store.put("funding_openai_seen", {})
            if remaining <= 0 and now - seen_end <= float(cfg["after_end_hours"]) * 3600:
                return {"cliff": "openai_month", "key": f"openai_month:{_stamp(seen_end)}", "tier": "out", "calendar": True,
                        "state": "ended", "ended_at": _stamp(seen_end), "remaining_usd": round(remaining, 2),
                        "was_usd": seen.get("remaining"), "openai_models": named,
                        "text": (f"funding: the gateway's OpenAI month ended at {_stamp(seen_end)} and its cap is now $0 "
                                 f"(${_number(seen.get('remaining'), 0.0):.2f} was left before it){uses}")}
        if remaining <= 0:
            return {"cliff": "openai_month", "state": "no room", "remaining_usd": round(remaining, 2)}
        self.store.put("funding_openai_seen", {"end": end, "remaining": round(remaining, 2)})
        hours = (end - now) / 3600
        found = {"cliff": "openai_month", "key": f"openai_month:{_stamp(end)}", "calendar": True, "state": "funded",
                 "tier": tier_for(hours, cfg["lead_hours"]["openai_month"]), "hours": round(hours, 1),
                 "ends_at": _stamp(end), "remaining_usd": round(remaining, 2), "openai_models": named,
                 "text": (f"funding: the gateway's OpenAI month ends at {_stamp(end)} (in about {_hours_text(hours)}) with "
                          f"${remaining:.2f} left; a funded month does not roll over, so OpenAI goes to $0 then unless the "
                          f"owner funds the next one{uses}")}
        return found

    # ------------------------------------------------------------------ fallbacks
    def flush_fallbacks(self, now: float, cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
        """The router's fallbacks since the last flush into `funding_fallbacks`, and each (role, kind, route) said the
        first time and then at most every `fallback_every_seconds` with the count since. Returns the payloads said."""
        drain = getattr(self.router, "drain_fallbacks", None)
        fresh = drain() if callable(drain) else {}
        state = self.store.get("funding_fallbacks") or {}
        if not fresh and not any(isinstance(v, Mapping) and v.get("pending") for v in state.values()):
            return []
        said: list[dict[str, Any]] = []
        every = float(cfg["fallback_every_seconds"])
        with self.store.atomic():
            state = {k: dict(v) for k, v in (self.store.get("funding_fallbacks") or {}).items()
                     if isinstance(v, Mapping) and now - float(v.get("seen") or v.get("at") or 0) < FORGET_SECONDS}
            for (role, kind, to), entry in fresh.items():
                key = f"{role}|{kind}|{to}"
                row = state.setdefault(key, {"role": role, "kind": kind, "to": to, "at": None, "pending": 0, "total": 0})
                if not row.get("pending"):
                    row["since"] = float(entry.get("first_at") or now)
                row["pending"] = int(row.get("pending") or 0) + int(entry.get("count") or 0)
                row["seen"] = float(entry.get("last_at") or now)
                row["reason"] = str(entry.get("reason") or "")[:240]
            for key, row in state.items():
                if not row.get("pending"):
                    continue
                if row.get("at") is not None and now - float(row["at"]) < every:
                    continue
                count, since = int(row["pending"]), float(row.get("since") or now)
                alert = row["kind"] in FUNDING_KINDS
                where = {"sail": "Sail", "openai": "OpenAI", "none": "no route (the call failed)"}.get(row["to"], row["to"])
                payload = {"action": "claude_fallback", "alert": alert, "role": row["role"], "kind": row["kind"], "to": row["to"],
                           "calls": count, "since": _stamp(since), "reason": row.get("reason"),
                           "text": (f"funding: {count} {row['role']} call(s) fell back from Claude to {where} since "
                                    f"{_stamp(since)} ({row['kind']}: {row.get('reason') or 'no reason given'})")[:600]}
                self.store.event("swarm.status", None, payload)
                said.append(payload)
                row.update(at=now, pending=0, total=int(row.get("total") or 0) + count)
            self.store.put("funding_fallbacks", state)
        for payload in said:
            if payload["alert"]:
                self.log(payload["text"])
        return said


__all__ = ["FundingWatch", "DEFAULTS", "TIERS", "FUNDING_KINDS", "tier_for", "month_end"]
