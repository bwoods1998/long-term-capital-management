"""The incubator: one lot of real money for a family whose live practice was positive. Real P&L, never evidence.

THE OWNER'S DECISION. Asked on Sept 29, 2026 whether to open the incubator, the owner answered at 14:51:12Z: "Yes, open the
incubator". The reading was settled on Sept 30, about 14:35-14:45Z: families that pass Train, pass the drift screen alone
and show positive live practice (the gate's review and audit still required) trade one lot of any approved real
structure, at most $50 of maximum loss each, at most 4 open at once, and the route stops for the week after $150 of net
realized loss. It is a new shadow-to-real route with its own money digest; it ships switched off, is ratified again at
once, the site labels it, and only then is it switched on. It never promotes: D2 is the only route to Probe and Sized.

THE UNIT is one practice COHORT `(family, version)` of the practice league (`league/live/observe.py`): its frozen
snapshot is the program the incubator trades, byte for byte, never the family's current row.

THE FIRST LOOK (pre-registered; `money.practice_ok`): taken ONCE per cohort, at the first session pin (the session's first
families pass) at which its record before today (`observe.practice_record(before=today)`, trades under the running
evaluator only) has at least `incubator.min_sessions` completed sessions and `incubator.min_trades` program-closed
trades. It passes only with decision coverage at least `incubator.min_coverage` and realized practice P&L above $0 over
program closes, over all closes, and over all closes plus the open mark. Recorded in the live state
(`incubator_verdicts`, key `<family>@<version>`, with every value and the fill model's version) and a private
`live.incubator` event WHETHER OR NOT the switch is on, so a first look is never taken again. A failed first look is
final. After a pass, each later session's first pass re-checks P3-P6 on the extended record; a failure ends the
incubation for good (re-checks can only refuse). A zero-edge program passes roughly a third to a half of the time: the
weekly envelope, not the screen, bounds the cost.

L2' (`keep`): while `live.incubator` is on, a cohort whose first look passed and whose record still passes keeps
practising past its observation target to its bounded window (at most `MAX_PINS`), so its re-checks and its paired
shadow (`:o`) and real (`:i`) decisions continue. Off, the practice league's own rule is unchanged. A READ THAT FAILS
never ends an incubation: when today's checks could not be taken (the cohorts could not be read, a first look's or a
re-check's record could not be read, or the first looks raised), the last keep's cohorts that no re-check ended stay
kept (as does an active cohort whose first look could not read its record, first look or not), today's keep is not
settled (`checked`), and the next families pass takes the checks again (at most `RETRIES` times a day). While the
cohorts themselves are unread, the practice league completes no cohort at its target (`observe.HOLD`). Within a day
the keep only grows: a cohort kept at an earlier pass leaves it only when a check ends it or its cohort is no longer
active, and a cohort kept on an untaken check never takes a checked one's place. A check retried after the session's
first pass reads the record before today but the practice row's coverage and open mark at the retry, so a retried
re-check that fails on P3 or P6 alone is no end (`deferred`: kept, and checked at the next session's first pass), nor
is a retried first look of an active cohort taken on them. It fails open for keeping a cohort practising only: a pin
still needs today's check taken and passed (`_passing`), so no `:i` trades on an unread check.

THE PINS, at the session's first families pass (a restart reuses them; no mid-session join), at most `MAX_PINS`, by
first-look return on risk then family id, and only from that day's L2' cohorts (`keep`: a pinned cohort always keeps
practising, so no pass finds it completed mid-session). A cohort is pinned only with all of: the switch on; real money
on; the table's rows above zero; its first look passed and its extended record still passing; the cohort active under
the running evaluator with its program unchanged; the swarm's facts (`bands.incubator`: alive, Gym band, not demoted,
Train and drift passed under the current evaluator, review and audit passed, not refused, failed or demoted by the gate,
not on D2's route) with the snapshot's run sha; no D2 route for the family (no `:r` or `:t` this pass, no `bands.read`
row: `:r` > `:t` > `:i`); a real structure (`Table.family_real`, `family_allowed`); and at least one sampled program
close that a one lot could open under the unit cap (`feasible`). Its instance is `<family>@<version>:i`, REAL and
tuition-flagged. Every families pass re-checks the switch, the facts, the D2 precedence and the cohort; a failure sends
it to exits only (its working opens cancelled within a minute).

ORDERS (`OptionsLive._real_intent`): `plan` (`money.plan_incubator`, the tally read afresh from `live.sqlite` for every
open) and `admit` (the facts, the pin, the switch, the cohort and the tally again, under the families' lock). Within a
minute the D2 families' intents go first, then the incubator's, then the House live test's (which yields to a later
incubator refusal on its contracts, as to a family's), then the calibration. `_yield` cancels a working incubator open
when a D2 family's real order was refused, after that open was placed, on one of its contracts ("yielded").

THE CAPS (`money.plan_incubator`) live in the House only (the gateway's own caps are the backstop; it cannot tell routes
apart): one lot; at most `incubator.max_loss_usd` a structure and a family; at most `incubator.max_open` held or working;
the weekly ENVELOPE R + H + W + the new unit at most `incubator.week_loss_usd` (so "$150 a week net" is a true bound but
for residuals: broker fees above the book's estimate, a broken structure closed leg by leg), and once the week's net
realized loss has reached it at any close, "stopped for the week" for the rest of the ISO week (a LATCH read from the
live state's closes, `IncubatorTally.week_peak_loss`: a later gain never re-opens it; alerted once a week); `DAY_LEGS`
legs and `DAY_OPEN_SHARE` of the day cap a day; and room kept in the book's and the day's caps for two Probe floors and,
while it can still open, the House live test's structure.

NEVER EVIDENCE, NEVER A PROMOTION: its orders and positions are tuition-flagged, and it is never a forward row
(`_export_real` skips tuition and every `:i`), never a band move (only `bands.read` rows are ever banded), never in
tuition's own day and week sums (`RealBook.exposure`), and the swarm never reads its rows. Its positions are Profit, on
the site as the agent's with the source "incubator".
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
from typing import Any, Iterator, Mapping

from . import calibration as C
from . import money as M
from .observe import cohort_rows, practice_record
from .real import INCUBATOR_SUFFIX, is_incubator

SUFFIX = INCUBATOR_SUFFIX
DAY_LEGS = M.INCUBATOR_DAY_LEGS
DAY_OPEN_SHARE = M.INCUBATOR_DAY_OPEN_SHARE
MAX_PINS = 8
#: Families passes a day that take today's checks again after a read failed (`checked`); then the day's keep stands, and
#: the next session's first pass reads again.
RETRIES = 12
#: A check retried after the session's first pass: the rules that read the practice row's live values (decision coverage
#: and the open mark), never the rule's first-pass values. A retried failure on these alone is no end (`_judge`).
INTRADAY = ("P3", "P6")
#: The cohorts a first look may be taken on: active, or completed by the league's own rule (never failed, never closed by
#: an evaluator change).
COMPLETE_OK = ("observation target reached", "maximum session window reached")
#: Days after its completion a cohort's first look may still be taken (its completion day's own session counts the day
#: after; a weekend and a holiday between).
RECENT_DAYS = 7
#: The live state's keys.
VERDICTS, PINS, KEEP, WEEK = "incubator_verdicts", "incubator_pins", "incubator_keep", "incubator_week"
YIELDED = "yielded: a D2 family's real order was refused on its contracts"
#: The record's values a verdict keeps (never a price, a strike or code).
RECORD_FIELDS = ("sessions", "decisions_due", "decisions_made", "coverage", "closes_program", "pnl_program", "closes_all",
                 "pnl_all", "open_mark", "return_on_risk", "feasible", "first_day", "status", "tier", "structure")


def key_of(family: str, version: int) -> str:
    """The incubator instance's key: `<family>@<version>:i`."""
    return f"{family}@{int(version)}{SUFFIX}"


def cohort_key(family: str, version: int) -> str:
    return f"{family}@{int(version)}"


def program_sha(snapshot: Mapping[str, Any]) -> str:
    """The cohort's program (its code and parameters) as one hash: the program the incubator trades must be this one."""
    text = json.dumps({"code": snapshot.get("code"), "params": snapshot.get("params") or {}}, sort_keys=True,
                      separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def week_start_of(day: dt.date) -> str:
    return (day - dt.timedelta(days=day.weekday())).isoformat()


def _ny(t: float) -> dt.datetime:
    from zoneinfo import ZoneInfo

    return dt.datetime.fromtimestamp(t, ZoneInfo("America/New_York"))


class Incubator:
    """The incubator (the module docstring), one per `OptionsLive` with a real account."""

    def __init__(self, live: Any):
        self.live = live
        # `_yield`'s marks at its last pass: the working incubator opens then, and each D2 instance's refusals.
        self._marks: tuple[set[int], dict[str, tuple[list, int]]] | None = None
        self._told: set[str] = set()
        # The held and working incubator structures at the last minute: a change is when the weekly stop is looked at.
        self._book_seen: frozenset | None = None
        # Today's checks (`judge`): {day, read (False until the pass read the cohorts and finished), active (the active
        # cohorts it read), first (the active cohorts whose first look could not read its record), deferred (the active
        # cohorts whose retried first look failed on P3 or P6 alone)}. In memory: `keep` is only re-taken after a `judge`
        # of the same families pass (`checked`), a restart's included.
        self._checks: dict[str, Any] | None = None
        self._passes: tuple[str, int] = ("", 0)      # (day, `judge`s that day): the retries (`RETRIES`)

    # ------------------------------------------------------------------ state
    def _get(self, key: str) -> dict:
        return dict(self.live.state.get(key, {}) or {})

    def verdicts(self) -> dict:
        return self._get(VERDICTS)

    def pins(self) -> dict:
        return self._get(PINS)

    def on(self) -> bool:
        return bool(self.live.switches().get("incubator"))

    def _alert_once(self, key: str, text: str) -> None:
        if key not in self._told:
            self._told.add(key)
            self.live.alert("warning", text)

    def closed(self) -> str | None:
        """Why the route can open nothing whatever the family (the switch, real money, the table), or None."""
        table = self.live.table
        if not self.on():
            return "incubator: live.incubator is off"
        if not self.live._real_on():
            return "incubator: real money is off (config.json real_money)"
        if (min(table.incubator_max_loss, table.incubator_week_loss) <= 0 or table.incubator_max_open <= 0
                or table.incubator_contracts < 1):
            return "incubator: the constitution's options_money.incubator leaves no room"
        return None

    def due(self, today: str) -> bool:
        """The session's first families pass has not pinned yet (the caller checks the session)."""
        return self.pins().get("day") != today

    def checked(self, today: str) -> bool:
        """Today's checks are taken and today's keep is settled; False while the switch is on and today's keep was not
        taken yet, or was taken on a failed read (`keep`): the next families pass takes the checks again (`judge`), at
        most `RETRIES` times a day (then the day's keep stands, carried)."""
        if not self.on():
            return True
        cached = self._get(KEEP)
        return cached.get("day") == today and (not cached.get("unread") or self._retried_out(today))

    def _retried_out(self, today: str) -> bool:
        return self._passes[0] == today and self._passes[1] > RETRIES

    def holding(self, today: str) -> bool:
        """This pass's checks could not read the cohorts (or could not finish): which cohorts the keep must hold is not
        known, so the practice league completes none at its observation target this pass (`observe.HOLD`, practising
        only: no pin without `_passing`). While the switch is on."""
        checks = self._checks
        return checks is not None and checks.get("day") == today and not checks.get("read") and self.on()

    # ------------------------------------------------------------------ the first look
    def judge(self, today: str) -> None:
        """First looks for the cohorts not yet judged, and the re-checks of those that passed (the module docstring).
        Recorded whether or not the switch is on. At the session's first families pass, and again at a later pass
        while today's checks are not all taken (`checked`). A later pass's check reads the closes and sessions before
        today, as the first pass's does, but the practice row's decision coverage and open mark at that pass (P3, P6):
        a retried re-check that fails on those alone is `deferred`, not ended, and a retried first look of an active
        cohort that fails on those alone is not taken (both kept, and checked at the next session's first pass).
        Never raises: a failure leaves today's checks untaken (`keep` carries the last keep forward, and `holding`),
        alerted once a day."""
        day, n = self._passes
        self._passes = (today, n + 1 if day == today else 1)
        self._checks = {"day": today, "read": False, "active": set(), "first": set(), "deferred": set()}
        try:
            self._judge(today)
        except Exception as exc:  # noqa: BLE001 - today's checks untaken: the next families pass takes them again
            key = f"judge:{today}:{type(exc).__name__}"
            if key not in self._told:
                with contextlib.suppress(Exception):
                    self.live.record("live.incubator", {"unread": "first looks", "day": today,
                                                        "why": f"the first looks failed ({type(exc).__name__})"})
            self._alert_once(key, f"live: the incubator's first looks failed ({type(exc).__name__}: {str(exc)[:160]}); "
                                  "the kept cohorts stay kept, nothing is pinned on an untaken check, and the next "
                                  "families pass takes them again")

    def _judge(self, today: str) -> None:
        live, table = self.live, self.live.table
        checks = self._checks if self._checks is not None else {"day": today, "read": False, "active": set(),
                                                                "first": set(), "deferred": set()}
        # A keep already taken today: an earlier families pass took (or could not take) today's checks, so this pass's
        # are retries (P3 and P6 read the practice row at this pass, not the first pass's values).
        retry = self._get(KEEP).get("day") == today
        evaluator = live.observe_store.evaluator
        # A cohort completed more than `RECENT_DAYS` ago can no longer newly meet the sample (its program closes stopped
        # with its practice): only the active ones and the recently completed are read.
        since = (dt.date.fromisoformat(today) - dt.timedelta(days=RECENT_DAYS)).isoformat()
        cohorts = cohort_rows(live.root, since=since)
        if cohorts is None:
            key = f"cohorts:{today}"
            if key not in self._told:
                live.record("live.incubator", {"unread": "cohorts", "day": today,
                                               "why": "the practice cohorts could not be read"})
            self._alert_once(key, "live: the incubator could not read the practice cohorts; no first look and no new pin "
                                  "until it can (the kept cohorts stay kept; the next families pass reads again)")
            return
        verdicts = self.verdicts()
        changed = False
        for vk in [k for k, v in verdicts.items() if v.get("evaluator") != evaluator]:
            verdicts.pop(vk)                              # another evaluator's: its cohorts can never be traded again
            changed = True
        fill_model = str(getattr(live.shadow.fill_model, "version", ""))
        cap = float(table.incubator_max_loss)
        for c in cohorts:
            snap = c["snapshot"]
            f, n = c["family"], int(c["version"])
            vk = cohort_key(f, n)
            verdict = verdicts.get(vk)
            if c["status"] == "active":
                checks["active"].add((f, n))
            if verdict is not None and c["status"] != "active" and self._unread(verdict, today):
                # Completed or failed since its unread re-check: nothing is left to keep or to read again today.
                verdict["latest"] = dict(verdict["latest"], unread=False,
                                         why="its practice record could not be read; its cohort is no longer active")
                verdicts[vk] = verdict
                changed = True
            if snap.get("practice_evaluator") != evaluator or c["status"] == "failed":
                continue
            if c["status"] != "active" and c.get("reason") not in COMPLETE_OK:
                continue
            if verdict is None:
                record = practice_record(live.root, f, n, before=today, evaluator=evaluator, unit_cap=cap)
                if record is None and c["status"] == "active":
                    # Unread, not ineligible: kept today (`keep`) so the league does not complete it at its target
                    # before the first look the next families pass takes.
                    checks["first"].add((f, n))
                    self._said_unread(vk, f, today, "its first look could not read its practice record")
                if record is None or record.get("sessions") is None:
                    continue
                if record["sessions"] < table.incubator_min_sessions or record["closes_program"] < table.incubator_min_trades:
                    continue                              # not yet the pre-registered sample: no look
                passed, why = M.practice_ok(table, record)
                if not passed and retry and c["status"] == "active" and why.startswith(INTRADAY):
                    # A retried first look on the practice row's live coverage or mark: not taken (a first look is final),
                    # kept today (`keep`), and taken at the next session's first pass.
                    checks["deferred"].add((f, n))
                    self._said(f"deferred:{vk}:{today}", {"deferred": vk, "first_look": True, "why": why, "day": today},
                               f)
                    continue
                verdict = {"family": f, "version": n, "evaluator": evaluator, "day": today, "at": live.clock(),
                           "passed": passed, "why": why, "fill_model": fill_model, "run_sha": snap.get("run_sha"),
                           "program": program_sha(snap), "structure": snap.get("structure"),
                           "record": {k: record.get(k) for k in RECORD_FIELDS},
                           "rule": {"min_sessions": table.incubator_min_sessions, "min_trades": table.incubator_min_trades,
                                    "min_coverage": str(table.incubator_min_coverage)}}
                verdicts[vk] = verdict
                changed = True
                live.record("live.incubator", {"first_look": vk, "passed": passed, "why": why, "day": today,
                                               "fill_model": fill_model, **{k: record.get(k) for k in RECORD_FIELDS}},
                            agent=f)
            elif verdict.get("passed") and not verdict.get("ended") and verdict.get("day") != today \
                    and ((verdict.get("latest") or {}).get("day") != today or self._unread(verdict, today)) \
                    and c["status"] == "active":
                record = practice_record(live.root, f, n, before=today, evaluator=evaluator, unit_cap=cap)
                if record is None:
                    if self._unread(verdict, today):
                        continue                          # already said today: the next families pass reads again
                    # Never an end (only a record that fails ends it): kept, not pinned, and read again next pass.
                    why = "its practice record could not be read"
                    verdict["latest"] = {"day": today, "ok": False, "unread": True, "why": why}
                    self._said_unread(vk, f, today, f"its re-check: {why}")
                else:
                    ok, why = M.practice_ok(table, record, exit_check=True)
                    verdict["latest"] = {"day": today, "ok": ok, "why": why,
                                         "record": {k: record.get(k) for k in RECORD_FIELDS}}
                    if not ok and retry and why.startswith(INTRADAY):
                        # Retried on the practice row's live coverage or mark: not passing today (no pin), never an end;
                        # kept (`keep`) and re-checked at the next session's first pass.
                        verdict["latest"]["deferred"] = True
                        self._said(f"deferred:{vk}:{today}", {"deferred": vk, "why": why, "day": today}, f)
                    elif not ok:
                        verdict["ended"] = {"day": today, "why": why}
                        live.record("live.incubator", {"ended": vk, "why": why, "day": today,
                                                       **{k: record.get(k) for k in RECORD_FIELDS}}, agent=f)
                verdicts[vk] = verdict
                changed = True
        if changed:
            live.state.put(VERDICTS, verdicts)
        checks["read"] = True

    def _said(self, key: str, payload: dict, family: str) -> None:
        """One private `live.incubator` event a key (a ledger failure never changes a check)."""
        if key in self._told:
            return
        self._told.add(key)
        with contextlib.suppress(Exception):
            self.live.record("live.incubator", payload, agent=family)

    def _said_unread(self, vk: str, family: str, today: str, why: str) -> None:
        """A cohort's record could not be read today: one private event a cohort a day, and one alert a day."""
        key = f"unread:{vk}:{today}"
        if key in self._told:
            return
        self._told.add(key)
        with contextlib.suppress(Exception):
            self.live.record("live.incubator", {"unread": vk, "day": today,
                                                "why": f"{why}: kept practising, not pinned, read again at the next "
                                                       "families pass"}, agent=family)
        self._alert_once(f"records:{today}", f"live: the incubator could not read {vk}'s practice record ({why}); it "
                                             "stays kept, nothing is pinned on it, and the next families pass reads "
                                             "again")

    @staticmethod
    def _unread(verdict: Mapping[str, Any], today: str) -> bool:
        """Today's re-check of a passed cohort could not read its record (never an end: it is taken again)."""
        latest = verdict.get("latest") or {}
        return latest.get("day") == today and latest.get("unread") is True and not verdict.get("ended")

    @staticmethod
    def _deferred(verdict: Mapping[str, Any], today: str) -> bool:
        """Today's re-check was retried after the session's first pass and failed on P3 or P6 alone (never an end)."""
        latest = verdict.get("latest") or {}
        return latest.get("day") == today and latest.get("deferred") is True and not verdict.get("ended")

    @staticmethod
    def _passing(verdict: Mapping[str, Any], today: str) -> bool:
        """Its first look passed, no re-check ended it, and today's check (the first look's own day, or today's
        re-check) holds."""
        if not verdict.get("passed") or verdict.get("ended"):
            return False
        if verdict.get("day") == today:
            return True
        latest = verdict.get("latest") or {}
        return latest.get("day") == today and bool(latest.get("ok"))

    @staticmethod
    def _rank(verdict: Mapping[str, Any]) -> tuple:
        rr = (verdict.get("record") or {}).get("return_on_risk")
        rr = float(rr) if isinstance(rr, (int, float)) and not isinstance(rr, bool) else float("-inf")
        return (-rr, str(verdict.get("family")), int(verdict.get("version") or 0))

    def keep(self, today: str, *, in_session: bool) -> frozenset:
        """L2' (the module docstring): the (family, version) cohorts the practice league keeps past their observation
        target today; empty while the switch is off. Taken at the session's first pass and kept for the day: at most
        `MAX_PINS` whose check passed today, by first-look return on risk (the active first). Unless today's checks could
        not all be taken (a read failed; `judge`): then the keep is marked `unread` (not settled: `checked`) and taken
        again at the next families pass, after its `judge`, and on top of the checked ones it HOLDS (`carried`, never
        counted against the cap, never pinned without `_passing`):
          - the last keep's cohorts that no check ended: a passed one whose check today is unread or `deferred`, and,
            while the cohorts are unread, every one (first look or not);
          - an active cohort whose first look could not read its record, or was `deferred`;
          - on a later pass the same day, every cohort already kept today unless a check ended it (or failed its first
            look) or its cohort is no longer active: within a day the keep only grows, so no pinned cohort is completed
            mid-session."""
        if not self.on():
            return frozenset()
        cached = self._get(KEEP)
        if cached.get("day") == today and (not cached.get("unread") or not in_session):
            return frozenset((str(f), int(n)) for f, n in cached.get("cohorts") or [])
        if not in_session:
            return frozenset()
        verdicts = self.verdicts()
        checks = self._checks if (self._checks or {}).get("day") == today else None
        # Today's checks were all read unless this pass's `judge` could not finish (no `judge` today in this process:
        # the verdicts alone, as recorded).
        read = checks is None or bool(checks.get("read"))
        active = set(checks.get("active") or ()) if checks is not None and read else None
        unread_first = {c for c in (checks or {}).get("first", ()) if cohort_key(*c) not in verdicts}
        deferred_first = {c for c in (checks or {}).get("deferred", ()) if cohort_key(*c) not in verdicts}
        same_day = cached.get("day") == today

        def of(v: Mapping[str, Any]) -> tuple[str, int]:
            return str(v["family"]), int(v["version"])

        def alive(c: tuple[str, int]) -> bool:
            return active is None or c in active

        # Checked today and passing: at most `MAX_PINS`, the active first (a completed cohort cannot practise).
        passing = sorted((v for v in verdicts.values() if self._passing(v, today)),
                         key=lambda v: (not alive(of(v)), *self._rank(v)))
        cohorts = [of(v) for v in passing[:MAX_PINS]]
        held: list[tuple[str, int]] = []
        for f, n in cached.get("cohorts") or []:
            c = (str(f), int(n))
            v = verdicts.get(cohort_key(*c))
            if v is None:
                hold = not read or c in unread_first or c in deferred_first
            elif not v.get("passed") or v.get("ended") or not alive(c):
                hold = False                              # a check ended it (or failed its first look), or it is done
            elif self._passing(v, today):
                hold = same_day                           # kept earlier today: never dropped today
            else:
                hold = same_day or not read or self._unread(v, today) or self._deferred(v, today)
            if hold and c not in cohorts and c not in held:
                held.append(c)
        held += sorted(c for c in unread_first | deferred_first if c not in cohorts and c not in held)
        cohorts += held
        carried = [[f, n] for f, n in held if not self._passing(verdicts.get(cohort_key(f, n)) or {}, today)]
        unread = not read or bool(unread_first) or any(self._unread(v, today) for v in verdicts.values())
        keep: dict[str, Any] = {"day": today, "cohorts": [[f, n] for f, n in cohorts]}
        if unread or carried:
            keep["carried"] = carried
        if unread:
            keep["unread"] = True
        self.live.state.put(KEEP, keep)
        if (unread or carried) and (not same_day or cached.get("carried") != carried):
            with contextlib.suppress(Exception):          # a ledger failure never changes the keep
                self.live.record("live.incubator", {"keep_carried": [cohort_key(f, n) for f, n in carried], "day": today,
                                                    "unread": unread,
                                                    "why": "today's checks could not all be taken: kept practising, not "
                                                           "pinned, checked again at the next families pass" if unread
                                                    else "a retried check was deferred: kept practising, not pinned, "
                                                         "checked at the next session's first pass"})
        if unread and self._retried_out(today):
            self._alert_once(f"retries:{today}", "live: the incubator's checks still could not all be read after "
                                                 f"{RETRIES} retries; today's keep stands (carried, never pinned) and "
                                                 "the next session's first pass reads again")
        return frozenset(cohorts)

    # ------------------------------------------------------------------ the pins
    def _d2(self, family: str, rows: list[Mapping[str, Any]], wanted: Mapping[str, Any]) -> bool:
        """The family has a D2 route this pass (a `:r` or `:t`, or any `bands.read` row): `:r` > `:t` > `:i`."""
        if any(str(r.get("family")) == family for r in rows):
            return True
        return any(k.startswith(f"{family}@") and k.endswith((":r", ":t")) for k in wanted)

    def _eligible(self, verdict: Mapping[str, Any], rows: list, wanted: Mapping[str, Any], *,
                  pinning: bool) -> tuple[dict | None, str | None]:
        """(the instance's row, None) when the cohort may trade now, else (None, why). `pinning`: the pin's own checks too
        (the real structure, the one-lot feasibility)."""
        live, table = self.live, self.live.table
        f, n = str(verdict["family"]), int(verdict["version"])
        if self._d2(f, rows, wanted):
            return None, "the family has a D2 route (its :r or :t, or a band row)"
        try:
            snap = live.observe_store.cohort_snapshot(f, n)
        except Exception as exc:  # noqa: BLE001 - fail-closed
            return None, f"its cohort could not be read ({type(exc).__name__})"
        if snap is None:
            return None, "its practice cohort is no longer active under the running evaluator"
        if program_sha(snap) != verdict.get("program") or snap.get("run_sha") != verdict.get("run_sha"):
            return None, "its cohort's program is not the one its first look judged"
        try:
            facts = next(iter(live.families.incubator(f, n)), None)
        except Exception as exc:  # noqa: BLE001 - an unreadable store: no pin, no open
            self._alert_once(f"facts:{type(exc).__name__}", f"live: the incubator's facts could not be read "
                                                            f"({type(exc).__name__}): no incubator pin or open until they can")
            return None, f"the swarm's facts could not be read ({type(exc).__name__})"
        if facts is None or facts.get("incubator") is not True:
            return None, "the swarm's facts do not admit it (alive, Gym, Train and drift, review and audit)"
        if not snap.get("run_sha") or facts.get("run_sha") != snap.get("run_sha"):
            return None, "the swarm's run sha is not its cohort's"
        structure = str(snap.get("structure") or facts.get("structure") or "")
        if pinning:
            if not table.family_real(structure):
                return None, f"a {structure or '?'} family does not trade real types only"
            equity = live.sizing_equity()
            why = table.family_allowed(structure, equity if equity is not None else M.ZERO)
            if why:
                return None, why
            latest = (verdict.get("latest") or {}).get("record") or verdict.get("record") or {}
            if int(latest.get("feasible") or 0) < 1:
                return None, (f"no sampled program close was one lot of ${table.incubator_max_loss} or less: it could "
                              "never open")
        row = {"family": f, "version": n, "code": snap.get("code"), "params": dict(snap.get("params") or {}),
               "run_sha": snap.get("run_sha"), "structure": structure, "roots": list(snap.get("roots") or []),
               "band": "gym", "incubator": True}
        return row, None

    def _pin(self, rows: list, wanted: Mapping[str, Any], today: str) -> dict:
        pins: dict[str, Any] = {"day": today, "order": [], "versions": {}, "run_sha": {}, "rr": {}, "refused": {}}
        closed = self.closed()
        if closed is None:
            # Only today's L2' cohorts are pinned: a pinned cohort is always one the practice league keeps (never one
            # completed at its target mid-session while its `:i` was pinned), and pins never outnumber `keep`.
            keep = self.keep(today, in_session=True)
            verdicts = self.verdicts()
            candidates = sorted((v for v in verdicts.values() if self._passing(v, today)), key=self._rank)
            for vk, verdict in verdicts.items():
                # Carried by the keep on an unread check (`keep`): practising, never pinned (fail closed), and said.
                if (verdict.get("passed") and not verdict.get("ended") and not self._passing(verdict, today)
                        and (str(verdict.get("family")), int(verdict.get("version") or 0)) in keep):
                    pins["refused"][vk] = (
                        "today's re-check was retried after the session's first pass and failed on P3 or P6 alone: kept "
                        "practising (L2'), re-checked at the next session's first pass" if self._deferred(verdict, today)
                        else "today's check of its record could not be taken (a read failed): kept practising (L2'), "
                             "never pinned on an untaken check")
            families: set[str] = set()
            for verdict in candidates:
                f, n = str(verdict["family"]), int(verdict["version"])
                vk = cohort_key(f, n)
                if (f, n) not in keep:
                    pins["refused"][vk] = (f"not among today's {MAX_PINS} kept cohorts (L2'): the incubator pins only "
                                           "those")
                    continue
                if len(pins["order"]) >= MAX_PINS:
                    pins["refused"][vk] = f"the incubator pins at most {MAX_PINS} cohorts a session"
                    continue
                if f in families:
                    pins["refused"][vk] = "another cohort of its family is pinned"
                    continue
                row, why = self._eligible(verdict, rows, wanted, pinning=True)
                if row is None:
                    pins["refused"][vk] = why
                    continue
                key = key_of(f, n)
                families.add(f)
                pins["order"].append(key)
                pins["versions"][f] = n
                pins["run_sha"][key] = row["run_sha"]
                pins["rr"][key] = (verdict.get("record") or {}).get("return_on_risk")
        else:
            pins["closed"] = closed
        self.live.state.put(PINS, pins)
        self.live.record("live.incubator", {"pins": pins["order"], "refused": pins["refused"], "closed": closed,
                                            "day": today})
        return pins

    def wanted(self, rows: list, wanted: dict, now: float) -> None:
        """The pinned cohorts' instances this families pass (the module docstring), added to `wanted`: taken afresh at the
        session's first pass, re-checked at every pass (the rest go to exits only)."""
        today = _ny(now).date().isoformat()
        pins = self.pins()
        if self.live._in_session(now) and pins.get("day") != today:
            pins = self._pin(rows, wanted, today)
        if not pins.get("order") or self.closed():
            return
        verdicts = self.verdicts()
        for key in pins["order"]:
            f, n = key[: -len(SUFFIX)].rsplit("@", 1)
            verdict = verdicts.get(cohort_key(f, int(n)))
            if verdict is None or not verdict.get("passed") or verdict.get("ended"):
                continue
            row, why = self._eligible(verdict, rows, wanted, pinning=False)
            if row is None or row["run_sha"] != (pins.get("run_sha") or {}).get(key):
                inst = self.live.instances.get(key)
                if inst is not None and inst.mode == "live":
                    self.live.record("live.incubator", {"instance": key, "exits_only": why or "its run sha changed"},
                                     agent=f)
                continue
            wanted[key] = (row, "real", True)

    # ------------------------------------------------------------------ orders
    def room(self) -> M.Decimal:
        """What an incubator open leaves the others in the book's and the day's caps: two Probe floors, and the House live
        test's structure while it can still open (its switch on, not stopped, not ended)."""
        table, live = self.live.table, self.live
        room = C.FAMILY_ROOM_PROBES * table.probe_floor
        test = getattr(live, "house_test", None)
        if test is not None and live.switches().get("house_test"):
            st = test._st()
            if not st.get("stopped") and not st.get("ended"):
                room += table.house_test_structure
        return room

    def tally(self, day: dt.date, family: str | None = None) -> M.IncubatorTally:
        return self.live.book.incubator_tally(day=day.isoformat(), week_start=week_start_of(day), family=family)

    def plan(self, *, unit: M.Decimal, equity: M.Decimal | None, exposure: M.Exposure, day: Any, family: str) -> M.Plan:
        """One lot, or none and why (`money.plan_incubator`), the tally read afresh from the live state."""
        table = self.live.table
        why = self.closed()
        if why:
            return M.Plan(0, table.incubator_max_loss, why)
        tally = self.tally(day.day, family)
        self._week_check(day.day, tally)
        return M.plan_incubator(table, unit=unit, equity=equity, tally=tally, exposure=exposure, room=self.room())

    def _week_check(self, day: dt.date, tally: M.IncubatorTally) -> None:
        """Record and alert the weekly stop once a week when the tally's latch has reached the row. The stop itself is
        `plan_incubator`'s, read from the live state's closes at every open: this record is what health and the owner
        see, never what decides."""
        if tally.week_loss_seen >= self.live.table.incubator_week_loss:
            self._week_stopped(day, tally)

    def _week_stopped(self, day: dt.date, tally: M.IncubatorTally) -> None:
        week = week_start_of(day)
        st = self._get(WEEK)
        if st.get("week") == week:
            return
        why = (f"its net realized loss this week reached ${M.cents(tally.week_loss_seen)}, at or over "
               f"${self.live.table.incubator_week_loss}: stopped for the rest of the week (exits go on)")
        self.live.state.put(WEEK, {"week": week, "at": self.live.clock(), "why": why})
        self.live.record("live.incubator", {"week_stopped": week, "why": why})
        self.live.alert("warning", f"live: the incubator {why}")

    @contextlib.contextmanager
    def admit(self, identity: Mapping[str, Any], today: dt.date, *, unit: M.Decimal, equity: M.Decimal | None,
              exposure: M.Exposure) -> Iterator[bool]:
        """`families.admit_open`'s place for an incubator open: under the families' lock, its facts row read again and
        matched, and the switch, today's pin, the cohort's identity and the tally checked again."""
        live = self.live
        family, version = str(identity.get("family")), int(identity.get("version") or 0)
        key = key_of(family, version)
        pins = self.pins()
        expected = dict(identity, run_sha=(pins.get("run_sha") or {}).get(key), incubator=True)
        admit = getattr(live.families, "admit_incubator", None)
        if admit is None or not is_incubator(key):
            yield False
            return
        with admit(expected) as allowed:
            if allowed:
                allowed = self._still(expected, key, pins, today, unit=unit, equity=equity, exposure=exposure)
            yield allowed

    def _still(self, expected: Mapping[str, Any], key: str, pins: Mapping[str, Any], today: dt.date, *, unit: M.Decimal,
               equity: M.Decimal | None, exposure: M.Exposure) -> bool:
        live = self.live
        family, version = str(expected["family"]), int(expected["version"])
        if self.closed() or pins.get("day") != today.isoformat() or key not in (pins.get("order") or []):
            return False
        if (pins.get("versions") or {}).get(family) != version:
            return False
        try:
            snap = live.observe_store.cohort_snapshot(family, version)
        except Exception:  # noqa: BLE001
            return False
        if (snap is None or snap.get("code") != expected.get("code")
                or (snap.get("params") or {}) != (expected.get("params") or {})
                or snap.get("run_sha") != expected.get("run_sha")):
            return False
        for other in live.instances.values():
            if other.family == family and other.kind == "real" and other.mode == "live" and other.key.endswith((":r", ":t")):
                return False
        tally = self.tally(today, family)
        plan = M.plan_incubator(live.table, unit=unit, equity=equity, tally=tally, exposure=exposure, room=self.room())
        return plan.qty >= 1

    # ------------------------------------------------------------------ the minute
    def step(self, day: Any, mi: int, out: dict) -> None:
        """After the minute's ranked intents: the yield to D2, and the switch's effect within the minute (off: every
        incubator instance to exits only, its working opens cancelled)."""
        live = self.live
        if live.book is None:
            return
        live._isolated("incubator", self._yield)
        if self.closed():
            moved = False
            for inst in list(live.instances.values()):
                if inst.incubator and inst.mode == "live":
                    inst.mode = "exit_only"
                    live._persist_instance(inst)
                    live.record("live.instance", {"instance": inst.key, "family": inst.family, "state": inst.mode,
                                                  "why": self.closed()}, agent=inst.family)
                    moved = True
            if moved:
                live._cancel_inactive_opens()
        held = [p for p in live.book.positions.values() if is_incubator(p.instance) and p.qty > 0]
        working = [o for o in live.book.orders.values() if is_incubator(o.instance) and o.working]
        if held or working:
            out["incubator"] = {"open": len(held), "working": len(working)}
        seen = frozenset([("p", p.pid) for p in held] + [("o", o.oid) for o in working])
        if self._book_seen is not None and self._book_seen - seen:
            # A held structure closed (or an open ended) this minute: the weekly stop is recorded and alerted now, not
            # only at the next open (the stop itself is the plan's, from the live state's closes).
            self._week_check(day.day, self.tally(day.day))
        self._book_seen = seen

    def _yield(self) -> None:
        """A working incubator open holding a contract a D2 family's real order (`:r`, `:t`) was refused on AFTER the open
        was placed is cancelled at once, recorded "yielded" (the House live test's `_yield`, for D2 only: an older
        refusal never cancels, and the D2 intents of each minute go before the incubator's)."""
        live, book = self.live, self.live.book
        marks = self._marks
        mine = [o for o in book.orders.values()
                if o.working and o.action == "open" and is_incubator(o.instance) and o.cancel_sent is None]
        fresh: list[str] = []
        if marks is not None:
            for instance, whys in book.rejects_since.items():
                if not str(instance).endswith((":r", ":t")):
                    continue
                seen = marks[1].get(instance)
                fresh += [str(why) for why in whys[seen[1] if seen is not None and seen[0] is whys else 0:]]
        refusals = [why for why in fresh if why.startswith(C.YIELD_REFUSALS)]
        for order in mine:
            if marks is None or order.oid not in marks[0]:
                continue                                    # placed since the last pass: nothing since is about it
            symbols = {leg.symbol for leg in order.legs}
            if not any(symbols & set(C.OCC.findall(why)) for why in refusals):
                continue
            ours = book.cancel(order, YIELDED) or order.answer.get("cancel") == YIELDED
            if ours:
                book._reject(order.instance, f"your open was cancelled: {YIELDED}")
            live.record("live.incubator", {"instance": order.instance, "yielded": order.oid, "cancelled": bool(ours)},
                        agent=order.family)
        self._marks = ({o.oid for o in book.orders.values() if o.working and o.action == "open" and is_incubator(o.instance)},
                       {instance: (whys, len(whys)) for instance, whys in book.rejects_since.items()})

    # ------------------------------------------------------------------ what health shows
    def status(self) -> dict:
        """For health.json, from the House's thread: the live state only (no quote, no price, no program)."""
        live, table = self.live, self.live.table
        verdicts = self.verdicts()
        pins = self.pins()
        today = _ny(live.clock()).date()
        try:
            tally = self.tally(today).as_dict() if live.book is not None else None
        except Exception:  # noqa: BLE001
            tally = None
        week = week_start_of(today)
        stopped = self._get(WEEK)
        if stopped.get("week") != week:
            stopped = {}
            seen = (tally or {}).get("week_peak_loss_usd")
            if seen is not None and max(M.D(seen), M.D(tally["realized_loss_usd"])) >= table.incubator_week_loss:
                stopped = {"week": week, "why": f"its net realized loss this week reached ${seen} (not yet recorded)"}
        return {"switch": bool((live._switches or {}).get("incubator")),
                "table": {"max_loss_usd": str(table.incubator_max_loss), "contracts": table.incubator_contracts,
                          "max_open": table.incubator_max_open, "week_loss_usd": str(table.incubator_week_loss),
                          "min_sessions": table.incubator_min_sessions, "min_trades": table.incubator_min_trades,
                          "min_coverage": str(table.incubator_min_coverage)},
                "pins": {"day": pins.get("day"), "order": pins.get("order") or [], "refused": pins.get("refused") or {},
                         "closed": pins.get("closed")},
                "keep": self._get(KEEP).get("cohorts") or [],
                "keep_carried": self._get(KEEP).get("carried") or [],
                "verdicts": {"judged": len(verdicts), "passed": sum(1 for v in verdicts.values() if v.get("passed")),
                             "ended": sum(1 for v in verdicts.values() if v.get("ended"))},
                "tally": tally, "week_stopped": stopped or None}


__all__ = ["Incubator", "SUFFIX", "DAY_LEGS", "DAY_OPEN_SHARE", "MAX_PINS", "RETRIES", "INTRADAY", "VERDICTS", "PINS",
           "KEEP", "WEEK", "YIELDED", "key_of", "cohort_key", "program_sha", "week_start_of", "is_incubator"]
