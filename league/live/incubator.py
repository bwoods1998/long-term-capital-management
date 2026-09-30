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
shadow (`:o`) and real (`:i`) decisions continue. Off, the practice league's own rule is unchanged.

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

    # ------------------------------------------------------------------ the first look
    def judge(self, today: str) -> None:
        """First looks for the cohorts not yet judged, and the re-checks of those that passed (the module docstring).
        Recorded whether or not the switch is on. Only at the session's first families pass."""
        live, table = self.live, self.live.table
        evaluator = live.observe_store.evaluator
        # A cohort completed more than `RECENT_DAYS` ago can no longer newly meet the sample (its program closes stopped
        # with its practice): only the active ones and the recently completed are read.
        since = (dt.date.fromisoformat(today) - dt.timedelta(days=RECENT_DAYS)).isoformat()
        cohorts = cohort_rows(live.root, since=since)
        if cohorts is None:
            self._alert_once(f"cohorts:{today}", "live: the incubator could not read the practice cohorts; no first look "
                                                 "and no new pin until it can")
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
            if snap.get("practice_evaluator") != evaluator or c["status"] == "failed":
                continue
            if c["status"] != "active" and c.get("reason") not in COMPLETE_OK:
                continue
            f, n = c["family"], int(c["version"])
            vk = cohort_key(f, n)
            verdict = verdicts.get(vk)
            if verdict is None:
                record = practice_record(live.root, f, n, before=today, evaluator=evaluator, unit_cap=cap)
                if record is None or record.get("sessions") is None:
                    continue
                if record["sessions"] < table.incubator_min_sessions or record["closes_program"] < table.incubator_min_trades:
                    continue                              # not yet the pre-registered sample: no look
                passed, why = M.practice_ok(table, record)
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
                    and (verdict.get("latest") or {}).get("day") != today and c["status"] == "active":
                record = practice_record(live.root, f, n, before=today, evaluator=evaluator, unit_cap=cap)
                if record is None:
                    verdict["latest"] = {"day": today, "ok": False, "why": "its practice record could not be read"}
                else:
                    ok, why = M.practice_ok(table, record, exit_check=True)
                    verdict["latest"] = {"day": today, "ok": ok, "why": why,
                                         "record": {k: record.get(k) for k in RECORD_FIELDS}}
                    if not ok:
                        verdict["ended"] = {"day": today, "why": why}
                        live.record("live.incubator", {"ended": vk, "why": why, "day": today,
                                                       **{k: record.get(k) for k in RECORD_FIELDS}}, agent=f)
                verdicts[vk] = verdict
                changed = True
        if changed:
            live.state.put(VERDICTS, verdicts)

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
        target today; empty while the switch is off. Taken at the session's first pass and kept for the day."""
        if not self.on():
            return frozenset()
        cached = self._get(KEEP)
        if cached.get("day") == today:
            return frozenset((str(f), int(n)) for f, n in cached.get("cohorts") or [])
        if not in_session:
            return frozenset()
        passing = [v for v in self.verdicts().values() if self._passing(v, today)]
        passing.sort(key=self._rank)
        cohorts = [[str(v["family"]), int(v["version"])] for v in passing[:MAX_PINS]]
        self.live.state.put(KEEP, {"day": today, "cohorts": cohorts})
        return frozenset((f, n) for f, n in cohorts)

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
            candidates = sorted((v for v in self.verdicts().values() if self._passing(v, today)), key=self._rank)
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
                "verdicts": {"judged": len(verdicts), "passed": sum(1 for v in verdicts.values() if v.get("passed")),
                             "ended": sum(1 for v in verdicts.values() if v.get("ended"))},
                "tally": tally, "week_stopped": stopped or None}


__all__ = ["Incubator", "SUFFIX", "DAY_LEGS", "DAY_OPEN_SHARE", "MAX_PINS", "VERDICTS", "PINS", "KEEP", "WEEK", "YIELDED",
           "key_of", "cohort_key", "program_sha", "week_start_of", "is_incubator"]
