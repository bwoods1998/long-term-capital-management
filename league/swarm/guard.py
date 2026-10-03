"""The Sail guard: the swarm stops spending before the House is at risk, and inside the day's research budget.

Running out of Sail credits pauses EVERY box, the House included. So every few minutes the guard reads
Sail's balance (the usage summary through `Provider.check_balance`) and brakes the swarm, Gym boxes and
researchers to zero, when:

- the balance is below 2 x the House's burn a day + `margin_usd` (plan: "two days of the House's burn
  plus $30"). The House's burn is `house_burn_usd_day`; only with `measured_burn` true (off by default) is it
  Sail's own 24-hour spend less what the swarm itself booked in those 24 hours, never less than
  `house_burn_usd_day`, which also covers any other box on the account (the data box);
- THE BUDGET's day is spent (LTCM v3, league/ops/budget.py `sail_caps`, from the settings' `budget` block): the
  swarm's own Sail spend today (UTC) reached the Sail research dollars a day, or Sail's own meter today (every fall of
  the balance since midnight, the whole account) reached that plus the fixed boxes a day. Settings with no `budget`
  block read the store root's budget.json themselves (the floor when none); a malformed block is no research. The burst trio
  (`burst_cap_usd`, `burst_until`, `after_burst_usd_day`) is gone: the budget is the one daily cap;
- the balance could not be read (FAIL CLOSED: at once, and a failed read never releases a brake), or no
  good reading is `stale_seconds` old;
- the state disk has under `min_free_disk_gb` free (the House's ledger lives there).

It releases only on a fresh good reading above the line plus `release_margin_usd` (hysteresis) with the
caps allowing. The line and that release line are `house_line`'s: THE BUDGET's Sail reserve is the release line
(league/ops/budget.py), so research tapers to zero before the balance meets this brake. Every change of state is a
`swarm.guard` event. Sail's meter since the guard first ran (`metered_spent`, from `burst_started_at`) is still kept:
the site's compute block reads it. Standard library only.

THE GATE NEVER WAITS FOR MIDNIGHT (the budget's `gate_reserve`, the caps' `gate_reserve`: the last tenth of the day's
Sail research dollars, at least $0.50). Before the brake there is a HOLD: when the swarm's own Sail spend today reaches
the research cap less that reserve (or Sail's meter the account cap less it), researcher cycles, births and the
architect stop (`allows("research")` is false, the record's `research_held` true, `held` says why), and the tournament's
validation round, the gate round and the nightly forward go on to the cap itself (`allows()` stays true until the
brake). The hold is no brake: `braked` and `causes` say nothing of it, the Gym is not scaled to zero by it, and it ends
at 00:00 UTC with the day. A brake for a low or unreadable balance, the disk or the cap itself still stops everything.
Each change of the hold is a `swarm.guard` event too (action `research_hold` or `research_release`).

Beside the human `reason` the record, its `last` and the event carry `causes`: the brake's causes by name (CAUSES), one
per braking branch of `check`. A reader that must tell THE BUDGET's designed daily stop (BUDGET_CAUSES) from the House
at risk reads the names, never the reason's text; a record with no list is cause unknown (`causes_of`). Caps that are
no reading of the rule (`budget_caps`' `read` not true: the rule could not be read or run, a malformed block) brake
the same, at no research, under their own name (`budget_unreadable`): a broken rule is never the designed stop.
"""

from __future__ import annotations

import datetime as dt
import shutil
import time
from typing import Any, Callable, Mapping

from .store import SwarmStore

SWARM_SAIL_KINDS = ("sail_model", "gym_box")
# The brake's causes, one name per braking branch of `SailGuard.check` ("no_reading": no check yet). BUDGET_CAUSES are THE
# BUDGET's own daily caps: the designed stop of each UTC day, research at its cap until 00:00 UTC. Every other cause is
# the House at risk or a guard that cannot see: "budget_unreadable" is a budget brake on caps that are no reading of the
# rule (FAIL CLOSED to no research), so it is never one of the budget's own.
CAUSES = ("balance_unreadable", "under_line", "research_budget", "account_budget", "budget_unreadable", "disk", "no_reading")
BUDGET_CAUSES = ("research_budget", "account_budget")
# What `allows(kind)` holds back at THE GATE'S RESERVE, before the brake: the work that makes new research (a researcher's
# cycle, a birth by the architect or a reseed, the diagnostician). Every other kind (the default, the Gym's and the
# gate's boxes, the tournament, the gate, the nightly forward) goes on to the day's cap.
RESEARCH_KINDS = ("research", "architect", "birth", "diagnostician")


def causes_of(record: Any) -> list[str] | None:
    """The causes a guard record names (the kv record, its `last`, a `swarm.guard` event, the heartbeat's `guard`): [] is
    no brake. None is cause UNKNOWN: a record written before the list was kept, or one whose list is not names."""
    causes = record.get("causes") if isinstance(record, Mapping) else None
    if not isinstance(causes, list) or not all(isinstance(cause, str) for cause in causes):
        return None
    return list(causes)


def house_line(cfg: Any, measured: float = 0.0) -> dict[str, float]:
    """THE HOUSE'S LINE on Sail's balance, from the `guard` settings: `house` is the House's burn a day
    (`house_burn_usd_day`, or `measured` when that is larger), `line` two days of it plus `margin_usd` (under it the
    guard brakes everything), `release` the line plus `release_margin_usd` (a braked guard, the day's cap included,
    releases only at or above it). One arithmetic for `SailGuard.check` and for THE BUDGET's Sail reserve
    (league/ops/budget.py `gather`: research tapers to zero above `release`), so the two cannot drift apart."""
    cfg = cfg if isinstance(cfg, Mapping) else {}
    house = max(float(cfg.get("house_burn_usd_day", 1.0)), float(measured))
    line = 2.0 * house + float(cfg.get("margin_usd", 30.0))
    return {"house": house, "line": line, "release": line + float(cfg.get("release_margin_usd", 5.0))}


def budget_caps(settings: Mapping[str, Any], root: Any = None, now: float | None = None) -> dict[str, Any]:
    """THE BUDGET's daily Sail caps (league/ops/budget.py `sail_caps`): {research, fixed, account, source, read,
    gate_reserve}; with `root` (the store's state root) also capped by the guard's own read of `<root>/budget.json`.
    FAIL CLOSED: a rule that cannot be read is no research, and `read` false says so (the caps are then no reading of
    the rule)."""
    try:
        from ..ops.budget import sail_caps

        return sail_caps(settings, root, now)
    except Exception as exc:  # noqa: BLE001 - no rule, no research spend
        return {"research": 0.0, "fixed": 0.0, "account": 0.0, "read": False, "gate_reserve": 0.0,
                "source": f"the budget rule could not be read ({type(exc).__name__})"}


class SailGuard:
    """The guard (the module docstring). `reader()` returns (balance_usd or None, sail_burn_usd_per_day or None);
    `disk_free()` the state root's free bytes."""

    def __init__(self, store: SwarmStore, settings: Mapping[str, Any], reader: Callable[[], tuple[Any, Any]], *,
                 clock: Callable[[], float] = time.time, disk_free: Callable[[], float] | None = None):
        self.store = store
        self.settings = settings
        self.reader = reader
        self.clock = clock
        self.disk_free = disk_free or (lambda: float(shutil.disk_usage(store.root).free))
        state = store.get("guard", {}) or {}
        self.braked: bool = bool(state.get("braked", True))  # nothing is allowed before a first good reading
        self.reason: str = str(state.get("reason") or "no reading yet")
        # The reason's causes by name (CAUSES); None is unknown (a record kept before the list was).
        self.causes: list[str] | None = causes_of(state) if state else ["no_reading"]
        self.last_ok: float = float(state.get("last_ok") or 0.0)
        self.last: dict[str, Any] = dict(state.get("last") or {})
        # The last GOOD reading {balance, at}: the budget job (league/ops/budget.py) reads it, so one failed read just
        # before the job never zeroes a day's Sail research.
        self.last_good: dict[str, Any] = dict(state.get("last_good") or {})
        # THE GATE'S RESERVE: research is held (no brake) while the day's spend is inside the reserve under a cap.
        self.research_held: bool = bool(state.get("research_held", False))
        self.held: str = str(state.get("held") or "")
        self.hold_said: bool = bool(state.get("hold_said", False))  # a `research_hold` event stands unanswered
        self.checked_at: float = 0.0
        if not store.get("burst_started_at"):
            store.put("burst_started_at", self.clock())

    @property
    def cfg(self) -> Mapping[str, Any]:
        return self.settings.get("guard", {})

    def allows(self, kind: str = "any") -> bool:
        """FAIL CLOSED: braked, or no good reading for `stale_seconds`, allows no new cycle, round or box. THE GATE'S
        RESERVE: a kind in `RESEARCH_KINDS` is also refused while research is held (the day's spend inside the reserve);
        every other kind goes on to the brake."""
        if self.braked or self.clock() - self.last_ok >= float(self.cfg.get("stale_seconds", 600)):
            return False
        return not (self.research_held and kind in RESEARCH_KINDS)

    def due(self) -> bool:
        return self.clock() - self.checked_at >= float(self.cfg.get("every_seconds", 180))

    def _metered(self, balance: float | None, now: float) -> tuple[float, float]:
        """Sail's own meter: every fall of the balance between two good readings (a rise is a top-up, never negative
        spend), since the guard first ran (`burst_started_at`, the site's compute block) and since this UTC midnight. It
        counts every box and model call on the account, booked or not."""
        spent = float(self.store.get("metered_spent", 0.0) or 0.0)
        day = dt.datetime.fromtimestamp(now, dt.timezone.utc).date().isoformat()
        today = self.store.get("metered_today") or {}
        today_spent = float(today.get("spent") or 0.0) if today.get("day") == day else 0.0
        previous = self.store.get("metered_last_balance")
        if balance is not None:
            if previous is not None and balance < float(previous):
                spent += float(previous) - balance
                today_spent += float(previous) - balance
            self.store.put("metered_last_balance", balance)
            self.store.put("metered_spent", round(spent, 4))
            self.store.put("metered_today", {"day": day, "spent": round(today_spent, 4)})
        return spent, today_spent

    def check(self) -> dict[str, Any]:
        """Read the balance and decide. Returns the reading and the decision."""
        now = self.clock()
        self.checked_at = now
        cfg = self.cfg
        try:
            balance, burn = self.reader()
        except Exception:  # noqa: BLE001 - unreadable is unknown
            balance, burn = None, None
        balance = float(balance) if balance is not None else None
        burn = float(burn) if burn is not None else None
        if balance is not None:
            self.last_good = {"balance": balance, "at": now}
        swarm_day = self.store.spent(SWARM_SAIL_KINDS, since=now - 86400)
        # `measured_burn`: Sail's own 24-hour spend less the swarm's, never below the floor. It counts every other box on
        # the account (the data box) and, for a day after a restart, whatever ran before it; false (the default) trusts
        # the configured `house_burn_usd_day` alone.
        measured = (burn - swarm_day) if burn is not None and cfg.get("measured_burn", False) else 0.0
        lines = house_line(cfg, measured)
        house, line = lines["house"], lines["line"]
        metered, metered_today = self._metered(balance, now)
        midnight = now - (now % 86400)
        today_spent = self.store.spent(SWARM_SAIL_KINDS, since=midnight)
        caps = budget_caps(self.settings, getattr(self.store, "root", None), now)
        reasons, causes = [], []  # each braking branch: what it says, and its name in CAUSES
        if balance is None:
            # FAIL CLOSED: a failed read never releases a brake, and brakes an unbraked guard at once.
            causes.append("balance_unreadable")
            reasons.append("the Sail balance could not be read" + (" (braked before it)" if self.braked else ""))
        else:
            self.last_ok = now
            release = lines["release"] if self.braked else line
            if balance < release:
                causes.append("under_line")
                reasons.append(f"the Sail balance {balance:.2f} is under the House's line {release:.2f} "
                               f"(2 x {house:.2f} a day + {float(cfg.get('margin_usd', 30.0)):.0f})")
        # THE BUDGET's day (a research budget of 0 brakes at once: nothing is ever under a cap of 0). Caps that are no
        # reading of the rule (`read` not true) brake by the same arithmetic and are named apart from the budget's own.
        unread = caps.get("read") is not True
        if today_spent >= caps["research"]:
            causes.append("budget_unreadable" if unread else "research_budget")
            reasons.append(f"today's Sail research budget is spent ({today_spent:.2f} of {caps['research']:.2f}; "
                           f"{caps['source']})")
        elif metered_today >= caps["account"]:
            causes.append("budget_unreadable" if unread else "account_budget")
            reasons.append(f"today's Sail budget is spent by Sail's meter ({metered_today:.2f} of {caps['account']:.2f} for "
                           f"the account: research {caps['research']:.2f} + fixed {caps['fixed']:.2f}; {caps['source']})")
        # THE GATE'S RESERVE: no brake, a hold on new research while the day's spend is inside the reserve under a cap
        # (either meter). The caps of a rule that could not be read hold nothing back: they brake above, at no research.
        reserve = caps.get("gate_reserve")
        reserve = float(reserve) if isinstance(reserve, (int, float)) and not isinstance(reserve, bool) and reserve > 0 else 0.0
        held = ""
        if reserve > 0 and today_spent >= caps["research"] - reserve:
            held = (f"today's Sail research is at its line ({today_spent:.2f} of {caps['research']:.2f}): the last "
                    f"{reserve:.2f} is kept for validation, the gate and the nightly forward")
        elif reserve > 0 and metered_today >= caps["account"] - reserve:
            held = (f"today's Sail research is at its line by Sail's meter ({metered_today:.2f} of {caps['account']:.2f} for "
                    f"the account): the last {reserve:.2f} is kept for validation, the gate and the nightly forward")
        try:
            free_gb = self.disk_free() / 2 ** 30
        except OSError:
            free_gb = None
        if free_gb is not None and free_gb < float(cfg.get("min_free_disk_gb", 3.0)):
            causes.append("disk")
            reasons.append(f"the state disk has {free_gb:.1f} GB free (the House's ledger needs room)")
        was = self.braked if self.store.get("guard") is not None else None  # the first check says where it starts
        self.braked = bool(reasons)
        self.reason = "; ".join(reasons)
        self.causes = causes
        self.research_held, self.held = bool(held), held
        self.last = {"balance": balance, "burn_day": burn, "house_day": round(house, 2), "line": round(line, 2),
                     "swarm_day": round(swarm_day, 4), "metered_spent": round(metered, 4),
                     "metered_today": round(metered_today, 4), "today_spent": round(today_spent, 4),
                     "budget_research_usd_day": caps["research"], "budget_account_usd_day": caps["account"],
                     "budget_source": caps["source"], "free_disk_gb": None if free_gb is None else round(free_gb, 1),
                     "gate_reserve_usd": round(reserve, 4), "research_held": self.research_held, "held": self.held,
                     "braked": self.braked, "reason": self.reason, "causes": list(causes), "at": now}
        # The hold is said when it starts on an unbraked guard and when a hold that was said ends: under a brake it is
        # moot (the brake's own event carries it), and a hold that began and ended under one is never said.
        say_hold = not self.braked and self.research_held != self.hold_said
        if say_hold:
            self.hold_said = self.research_held
        self.store.put("guard", {"braked": self.braked, "reason": self.reason, "causes": list(causes),
                                 "research_held": self.research_held, "held": self.held, "hold_said": self.hold_said,
                                 "last_ok": self.last_ok, "last": self.last, "last_good": self.last_good})
        if was != self.braked:
            self.store.event("swarm.guard", None, {"action": "brake" if self.braked else "release", **self.last})
        if say_hold:
            self.store.event("swarm.guard", None, {"action": "research_hold" if self.research_held else "research_release",
                                                   **self.last})
        return dict(self.last)


def provider_reader(provider: Any) -> Callable[[], tuple[Any, Any]]:
    """(balance, burn a day) from `ltcm.provider.Provider` (its 60-second cache)."""
    def read() -> tuple[Any, Any]:
        balance = provider.check_balance()
        return balance, provider.sail_burn_usd_per_day()
    return read


__all__ = ["SailGuard", "provider_reader", "budget_caps", "house_line", "causes_of", "SWARM_SAIL_KINDS", "CAUSES",
           "BUDGET_CAUSES", "RESEARCH_KINDS"]
