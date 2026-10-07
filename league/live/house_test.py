"""The House live test `house:rebound-live`: one frozen, pre-registered program traded with real money at tuition size,
only to measure its real fills and real P&L. A learning route, never evidence.

THE OWNER'S DECISION (Sept 28, 2026): asked whether to add a pre-registered live test of the one replicated edge at
tuition size, as a new shadow-to-real route, the owner answered "proceed as you see best fit, you are in the best
position possible to make these decisions", and the operator decided yes on the terms below. The pre-registration is a
private file (its sha256 is `PREREGISTRATION_SHA256`): it fixes the program, these bounds, the duration, the analysis and
the verdict's criteria, and it says plainly that the test cannot verify profitability (even 30 round trips could not
tell the program's mean from zero).

WHAT RUNS: the frozen program, byte for byte, as the House's own real instance `INSTANCE`, in the same decider child
and through the same order path as the families' real programs (`OptionsLive._real_intent`, `_send_close`, `RealBook`:
its time in force, the expiry rules, the House's closes of an orphan's positions). The public repository holds only its
three hashes (`FROZEN`): the program and its parameters are private files on the House, `<state>/house-test/
rebound-live/program.py` and `params.json` (the directory mode 700, the files 600, the House's own user's), placed there
by the operator. The House checks them before the instance is wanted (`load_private`) and again at every load, a
restart's included (`verify`, then the decider's own run sha): a missing file, a file readable by group or other, or any
hash that is not the pre-registered one, and the program does not run (a restored instance fails for good, and the House
closes what it holds as an orphan's).

WHAT IT IS NOT: a swarm family. It holds no band, never promotes and is never promoted, never writes a forward record
(`OptionsLive._export_real`), is never an agent's structure on the site, and never touches D2 or any promotion rule.

THE BOUNDS (the constitution's `options_money.house_test`, which the owner's grant pins; checked before every open in
this order, fail-closed, `HouseTest.plan`):

- one lot, only while `live.house_test` is true in `<state>/swarm.json` (off by default; off sends the instance to exits
  only, its working open cancelled within a minute), real money on, the grant active, every real-entry rule open
  (`OptionsLive.real_block`: the kill switch, the stops, reconciliation, the House) and the paper proof passed, exactly
  as the calibration's opens, and its own record writable (`<state>/house-test.sqlite`: as the calibration's, no open
  while its recorder cannot be read);
- new opens only through the `sessions`th NYSE session from the start, and while closed + open + working round trips
  are under `round_trips`;
- one structure's maximum loss at its limit plus its open and close fees at most `structure_usd`;
- at most `open` held or working;
- R + H + W + its own cost at most `envelope_usd`, where R is the test's net realized loss since the start (floored at
  zero), H every held position's maximum loss and fees twice, W every working or unresolved open's (a lost one of
  today's whole): the test can never lose more than that;
- the gateway's per-order cap, as any open; and both the book's cap and the account-wide day cap less the room the
  calibration leaves the families of the day cap (the Probe room, `money.probe_room`: `probe.max_open` x
  `probe.max_loss_share` x E since THE FAST LANE, Oct 7, 2026): the test never takes the families' last room in either.

It yields to the families: their real intents of each minute are applied before its own, the order path refuses its
open on a contract a family order works, and while its open works a family's real order refused on one of that open's
contracts AFTER the open was placed cancels it at once ("yielded", `_yield`; an older refusal never does). What it does
not yield: a position it holds refuses a family's open of the other side of that contract ("positions net across the
account"), as any held position does, for as long as it is held.

The account's own stops are shared, not the test's: its losses count toward the daily and drawdown stops like any
position's, so on a bad day it can trip them (the daily stop blocks every family's entries for the rest of that day, the
drawdown stop pauses real money until the owner releases it). Its R is NET (gains offset losses) and from the book's fee
estimates; Profit uses the broker's fees, so the two can differ by cents.

DURATION: the clock starts at the first session in which the instance is live and loaded while real entries may go (the
start's day, release and fill model version are recorded). Every NYSE session from then counts, up or not. It ends
after `sessions` sessions or `round_trips` closed round trips, and it STOPS for good once R reaches `stop_usd`. Ended or
stopped, it opens nothing again; the unchanged program keeps managing its exits until the book is flat, then retires.

RECORDS: the live book's own rows (family `FAMILY`: in Profit and in the site's positions table as the House's
`source` "house", shown as "House live test"; `trading_profit.source_of` maps exactly this family to it), the House's
refusals (`live.refusal`), the start, stop and end, each (re)load of the program (fresh memory: a deviation when it
falls inside a decision's window) and each yield (`live.instance`), all private but the positions table; and
`<state>/house-test.sqlite` (mode 0600, the calibration recorder's schema and a few columns of its own): one row per
test order, the decision snapshot's NBBO of each leg, the structure's mid and natural, the program's limit rule, tag
and note, the times, fill and fees, and its outcome. An unfilled order that ran its whole window is "cancelled" (a
sample): its time in force ran out, the House's close cutoff for expiring contracts ended it, or the venue ended it at
the session's close as a day order (`SESSION_CLOSE`; the Gym's `end_day` drops it there too); any other unfilled end is
"interrupted" (never a sample). The program's note never reaches a public row: its orders carry `OPEN_WHY` and
`CLOSE_WHY`. The program and its params also sit in the live state's `instances` row, as every real instance's do.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import math
import os
import stat
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from ..gym import legs as L
from ..gym import venue as V
from . import calibration as C
from . import money as M
from .chains import session_minutes
from .real import ROrder

FAMILY = "house:rebound-live"
INSTANCE = "house:rebound-live@0:h"
BAND = "house_test"
#: The pre-registered program: sha256 of the program's bytes, of its merged PARAMS as canonical
#: JSON (sorted keys, no spaces), and the Gym's run sha (sha256 of the first and the canonical params).
FROZEN = {
    "code_sha256": "a8b8c7449f1ecb6ee0e3e3087c62ffd09c7046b49daa22ac45afd69e38254b12",
    "merged_params_sha256": "2715f5aa0aa7202b29b0fcbab5a853e1505b249c92698a1b2dc82642186eed97",
    "run_sha": "0771b4419405f5712da6596869b5eb7f56db5e424f908c5cf1bc5f3a07815b9f",
}
PREREGISTRATION_SHA256 = "c73e2d262b8d2e9493b53c427400ba7adc37490db8c981ddd96644fdb6977954"
PRIVATE_DIR = Path("house-test") / "rebound-live"
PROGRAM, PARAMS = "program.py", "params.json"
MAX_BYTES = 1 << 20
FILE = "house-test.sqlite"
#: What the test's orders say (a fill's reason is public on the tape; the program's note never is).
OPEN_WHY = "House live test (pre-registered): open"
CLOSE_WHY = "House live test (pre-registered): close"
YIELDED = "yielded: a family's real open was refused on its contracts"
#: An unfilled order the venue ended at the session's close (a day order: status "expired", no cancel of the House's).
SESSION_CLOSE = "the session's close (a day order; the Gym's end_day drops it there too)"
#: The cancels after which an unfilled order ran its whole window, as the Gym gives it one (the pre-registration's
#: sample): its time in force, and the House's close cutoff for expiring contracts (the Gym drops it there too).
FULL_WINDOW = (C.TIF_CANCEL, "the close cutoff for expiring contracts", SESSION_CLOSE)
#: The recorder's own columns beside the calibration's schema.
EXTRA = {"pid": "INTEGER", "rule": "TEXT", "forced": "INTEGER", "tag": "TEXT", "note": "TEXT"}


def canonical(value: Any) -> str:
    from ..gym.runtime import canonical as gym_canonical

    return gym_canonical(value)


def verify(code: Any, params: Any) -> str | None:
    """Why this program and these params are not the pre-registered ones, or None."""
    if not isinstance(code, str):
        return "the program is not text"
    try:
        code_sha = hashlib.sha256(code.encode("utf-8")).hexdigest()
    except UnicodeEncodeError:
        return "the program is not UTF-8"
    if code_sha != FROZEN["code_sha256"]:
        return f"the program's sha256 {code_sha[:12]} is not the pre-registered {FROZEN['code_sha256'][:12]}"
    if not isinstance(params, Mapping):
        return "the params are not a JSON object"
    params_sha = hashlib.sha256(canonical(dict(params)).encode("utf-8")).hexdigest()
    if params_sha != FROZEN["merged_params_sha256"]:
        return f"the params' sha256 {params_sha[:12]} is not the pre-registered {FROZEN['merged_params_sha256'][:12]}"
    return None


def load_private(root: str | Path) -> tuple[str, dict] | str:
    """(code, params) from `<root>/house-test/rebound-live`, or why not: the directory mode 700 and each file 600 (no
    group or other bit), regular files, the House's own user's, the code UTF-8, the params a JSON object, and both hashes
    the pre-registered ones."""
    folder = Path(root) / PRIVATE_DIR
    try:
        st = os.lstat(folder)
    except FileNotFoundError:
        return f"no private program at <state>/{PRIVATE_DIR}"
    except OSError as exc:
        return f"<state>/{PRIVATE_DIR} cannot be read ({type(exc).__name__})"
    if not stat.S_ISDIR(st.st_mode):
        return f"<state>/{PRIVATE_DIR} is not a directory"
    if st.st_mode & 0o077:
        return f"<state>/{PRIVATE_DIR} is open to group or other (mode {st.st_mode & 0o777:o}; it must be 700)"
    if st.st_uid != os.getuid():
        return f"<state>/{PRIVATE_DIR} is not the House's own"
    data: dict[str, bytes] = {}
    for name in (PROGRAM, PARAMS):
        path = folder / name
        try:
            fst = os.lstat(path)
            if not stat.S_ISREG(fst.st_mode):
                return f"{name} is not a regular file"
            if fst.st_mode & 0o077:
                return f"{name} is readable by group or other (mode {fst.st_mode & 0o777:o}; it must be 600)"
            if fst.st_uid != os.getuid():
                return f"{name} is not the House's own"
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as f:
                data[name] = f.read(MAX_BYTES + 1)
        except FileNotFoundError:
            return f"{name} is missing"
        except OSError as exc:
            return f"{name} cannot be read ({type(exc).__name__})"
        if len(data[name]) > MAX_BYTES:
            return f"{name} is over {MAX_BYTES} bytes"
    try:
        code = data[PROGRAM].decode("utf-8")
    except UnicodeDecodeError:
        return f"{PROGRAM} is not UTF-8"
    try:
        params = json.loads(data[PARAMS].decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return f"{PARAMS} is not JSON"
    if not isinstance(params, dict):
        return f"{PARAMS} is not a JSON object"
    why = verify(code, params)
    return why if why else (code, params)


def release() -> str:
    """The release this code runs from (`<base>/releases/<id>/league/live/house_test.py`)."""
    return Path(__file__).resolve().parents[2].name


class Recorder(C.Recorder):
    """`<state>/house-test.sqlite`: the calibration recorder (its schema, its one-transaction rows, its failures caught,
    logged and alerted once, never blocking a close) with its own file and columns. While it cannot be read or written
    the test opens nothing (`HouseTest.refusal`)."""

    def __init__(self, root: str | Path, *, alert: Any = None, log: Any = None, max_rows: int = C.MAX_ROWS):
        super().__init__(root, alert=alert, log=log, max_rows=max_rows)
        self.path = Path(root) / FILE

    def _connect(self):
        if self.db is not None:
            return self.db
        db = super()._connect()
        try:
            have = {r[1] for r in db.execute("PRAGMA table_info(samples)")}
            for column, kind in EXTRA.items():
                if column not in have:
                    db.execute(f"ALTER TABLE samples ADD COLUMN {column} {kind}")
        except Exception:
            db.close()                                      # tried afresh at the next call
            self.db = None
            raise
        return db

    def _failed(self, what: str, exc: BaseException) -> None:
        if self.log is not None:
            try:
                self.log("live.house_test_record", {"what": what, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            except Exception:  # noqa: BLE001
                pass
        if not self.told and self.alert is not None:
            self.told = True
            try:
                self.alert("warning", f"live: the House live test's orders could not be recorded ({what}: "
                                      f"{type(exc).__name__}); no new open until its record reads again, its closes go on")
            except Exception:  # noqa: BLE001
                pass


class HouseTest:
    """The House live test (the module docstring), one per `OptionsLive` with a real account. Its state is the live
    state's key "house_test": {start, stopped, ended, files, wanted, numbers}."""

    def __init__(self, live: Any):
        self.live = live
        self.recorder = Recorder(live.root, alert=live.alert, log=live.state.event)
        self._files_key: Any = None
        self._files: tuple[str, dict] | str | None = None
        # `_yield`'s marks at its last pass: the working test opens then, and each instance's refusal list and length.
        self._marks: tuple[set[int], dict[str, tuple[list, int]]] | None = None

    # ------------------------------------------------------------------ state
    def _st(self) -> dict:
        return dict(self.live.state.get("house_test", {}) or {})

    def _put(self, st: Mapping[str, Any]) -> None:
        self.live.state.put("house_test", dict(st))

    def _set(self, **fields: Any) -> None:
        st = self._st()
        if any(st.get(k) != v for k, v in fields.items()):
            st.update(fields)
            self._put(st)

    def status(self) -> dict:
        """For health.json, from the House's thread: the live state only (no quote, no price, no parameter)."""
        st = self._st()
        return {"family": FAMILY, "files": st.get("files"), "wanted": st.get("wanted"), "start": st.get("start"),
                "stopped": st.get("stopped"), "ended": st.get("ended"), "numbers": st.get("numbers"),
                "frozen": {k: v[:12] for k, v in FROZEN.items()}, "preregistration": PREREGISTRATION_SHA256[:12]}

    # ------------------------------------------------------------------ the private program
    def private(self) -> tuple[str, dict] | str:
        """`load_private`, read again whenever a file's (or the directory's) stat changes."""
        folder = Path(self.live.root) / PRIVATE_DIR
        key = []
        for path in (folder, folder / PROGRAM, folder / PARAMS):
            try:
                s = os.lstat(path)
                key.append((s.st_mode, s.st_uid, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns))
            except OSError:
                key.append(None)
        if tuple(key) != self._files_key or self._files is None:
            self._files_key, self._files = tuple(key), load_private(self.live.root)
        return self._files

    def wanted_row(self) -> dict | None:
        """The instance's row for `OptionsLive.sync_families`, or None (and why, in the status): the switch on, real money
        on, the constitution's bounds not zero, neither stopped nor ended, and the private files verified."""
        live, table, st = self.live, self.live.table, self._st()
        files = self.private()
        why = None
        if not live.switches().get("house_test"):
            why = "live.house_test is off"
        elif not live._real_on():
            why = "real money is off (config.json real_money)"
        elif min(table.house_test_structure, table.house_test_open, table.house_test_envelope,
                 table.house_test_sessions, table.house_test_round_trips) <= 0:
            why = "the constitution's options_money.house_test leaves no room"
        elif st.get("stopped"):
            why = f"stopped for good: {st['stopped'].get('why')}"
        elif st.get("ended"):
            why = f"ended: {st['ended'].get('why')}"
        elif isinstance(files, str):
            why = f"the private program: {files}"
        self._set(files="verified" if not isinstance(files, str) else files, wanted=why or "yes")
        if why or isinstance(files, str):
            return None
        code, params = files
        return {"family": FAMILY, "version": 0, "band": BAND, "structure": "debit_vertical", "code": code,
                "params": dict(params), "run_sha": FROZEN["run_sha"]}

    # ------------------------------------------------------------------ the clock and the tally
    def sessions_used(self, today: dt.date) -> int:
        """NYSE sessions from the start's day through `today`, both counted (0 before the start)."""
        start = (self._st().get("start") or {}).get("day")
        if not start:
            return 0
        day, n = dt.date.fromisoformat(str(start)), 0
        while day <= today:
            if session_minutes(day) is not None:
                n += 1
            day += dt.timedelta(days=1)
        return n

    def tally(self, today: str) -> dict:
        """From the live state's own rows (never the recorder): R, H and W (the module docstring), the structures held or
        working, the round trips (every position, and every working open without one) and those closed."""
        state = self.live.state
        realized = held = working = M.ZERO
        open_n = trips = closed = 0
        for r in state.rows("SELECT qty, opened_qty, max_loss_share, fees, cash, status FROM positions WHERE family=?",
                            (FAMILY,)):
            trips += 1
            if r["status"] == "closed":
                closed += 1
                realized += M.D(r["cash"])
                continue
            units = int(r["opened_qty"]) if r["status"] == "unpriced_close" else max(0, int(r["qty"]))
            held += M.D(r["max_loss_share"]) * V.MULTIPLIER * units + 2 * M.D(r["fees"])
            open_n += 1
        for r in state.rows("SELECT qty, filled_qty, status, max_loss, fees_est, day, pid FROM orders WHERE family=? AND "
                            "action='open' AND status IN ('pending', 'working', 'unknown', 'lost')", (FAMILY,)):
            if r["status"] == "lost" and r["day"] != today:
                continue
            remaining = int(r["qty"]) if r["status"] == "lost" else max(0, int(r["qty"]) - int(r["filled_qty"]))
            working += (M.D(r["max_loss"]) + 2 * M.D(r["fees_est"])) * M.D(remaining) / max(1, int(r["qty"]))
            if r["pid"] is None:
                open_n += 1
                trips += 1
        loss = max(M.ZERO, -realized)
        return {"realized_loss": loss, "possible": loss + held + working, "open": open_n, "round_trips": trips,
                "closed": closed}

    # ------------------------------------------------------------------ the minute
    def observe(self, day: Any, mi: int) -> None:
        """Before the minute's real decisions: the clock's start (the first session the instance is live and loaded while
        real entries may go), then the latches."""
        live, st = self.live, self._st()
        if not st.get("start"):
            inst = live.instances.get(INSTANCE)
            if (inst is None or inst.mode != "live" or inst.error or inst.fatal or inst.needs is None
                    or live.real_block(opening=True) or live.proof is None or not live.proof.passed()):
                return
            start = {"day": day.day.isoformat(), "minute": int(day.open_min + mi), "at": live.clock(), "release": release(),
                     "fill_model": str(getattr(live.shadow.fill_model, "version", "")),
                     "preregistration": PREREGISTRATION_SHA256}
            st["start"] = start
            self._put(st)
            live.record("live.instance", {"instance": INSTANCE, "family": FAMILY, "state": "house test started", **start},
                        agent=FAMILY)
        self._latch(day.day)

    def step(self, day: Any, mi: int, out: dict) -> None:
        """After the minute's real intents (the families' first, then its own), before the calibration: its records
        brought up to date, the yield, the latches and the numbers for the status."""
        if self.live.book is None:
            return
        self._finish_rows()
        self.live._isolated(INSTANCE, self._yield)
        self._latch(day.day)
        inst = self.live.instances.get(INSTANCE)
        if inst is not None and inst.mode == "live" and self.wanted_row() is None:
            # Switched off (or no longer wanted for any reason): the next minute's families pass, not up to
            # `FAMILIES_EVERY` later, sends it to exits only and cancels its working open.
            self.live._families_at = float("-inf")
        today = day.day.isoformat()
        t = self.tally(today)
        self._set(numbers={"day": today, "sessions_used": self.sessions_used(day.day),
                           "sessions": self.live.table.house_test_sessions, "round_trips": t["round_trips"],
                           "closed": t["closed"], "open": t["open"], "realized_loss_usd": str(M.cents(t["realized_loss"])),
                           "possible_loss_usd": str(M.cents(t["possible"]))})
        if t["open"] or t["round_trips"]:
            out["house_test"] = {"open": t["open"], "round_trips": t["round_trips"]}

    def _latch(self, today: dt.date) -> None:
        """The stop (R reached `stop_usd`: for good) and the end (the sessions are over, or `round_trips` closed). A latch
        is recorded and alerted once, and the next families pass sends the instance to exits only."""
        live, table, st = self.live, self.live.table, self._st()
        if not st.get("start") or (st.get("stopped") and st.get("ended")):
            return
        t = self.tally(today.isoformat())
        fired = []
        if not st.get("stopped") and t["realized_loss"] >= table.house_test_stop:
            st["stopped"] = {"day": today.isoformat(), "at": live.clock(),
                             "why": f"its realized loss ${M.cents(t['realized_loss'])} reached the ${table.house_test_stop} stop"}
            fired.append(("stopped", st["stopped"]["why"]))
        if not st.get("ended"):
            used = self.sessions_used(today)
            why = (f"its {table.house_test_sessions} sessions are over" if used > table.house_test_sessions else
                   f"{t['closed']} round trips closed" if t["closed"] >= table.house_test_round_trips else None)
            if why:
                st["ended"] = {"day": today.isoformat(), "at": live.clock(), "why": why}
                fired.append(("ended", why))
        if not fired:
            return
        self._put(st)
        live._families_at = float("-inf")                   # the next pass: exits only
        for what, why in fired:
            live.record("live.instance", {"instance": INSTANCE, "family": FAMILY, "state": f"house test {what}", "why": why},
                        agent=FAMILY)
            live.alert("warning", f"live: the House live test {what}: {why}; no new open, its exits go on")

    # ------------------------------------------------------------------ opening
    def refusal(self, today: dt.date) -> str | None:
        """Why the test may open nothing now (the latches re-checked first), or None."""
        live, table = self.live, self.live.table
        if not live.switches().get("house_test"):
            return "house test: live.house_test is off"
        self._latch(today)
        st = self._st()
        if st.get("stopped"):
            return f"house test: stopped for good ({st['stopped'].get('why')})"
        if st.get("ended"):
            return f"house test: ended ({st['ended'].get('why')})"
        if live.proof is None or not live.proof.passed():
            return "the paper proof has not passed"
        blocked = live.real_block(opening=True)
        if blocked:
            return blocked
        if not st.get("start"):
            return "house test: its clock has not started"
        used = self.sessions_used(today)
        if used > table.house_test_sessions:
            return f"house test: session {used} is past its {table.house_test_sessions}"
        if self.recorder.counts() is None:
            return f"house test: its record (<state>/{FILE}) cannot be read or written"
        return None

    def plan(self, *, unit: M.Decimal, equity: M.Decimal | None, exposure: M.Exposure, day: Any) -> M.Plan:
        """One structure whose maximum loss with its open and close fees is `unit`, or none and why (the module
        docstring's bounds, in order)."""
        table = self.live.table
        cap = table.house_test_structure
        why = self.refusal(day.day)
        if why:
            return M.Plan(0, cap, why)
        if equity is None or equity <= 0:
            return M.Plan(0, cap, "no sizing equity")
        if unit <= 0:
            return M.Plan(0, cap, "the structure's maximum loss is not positive")
        t = self.tally(day.day.isoformat())
        if t["round_trips"] >= table.house_test_round_trips:
            return M.Plan(0, cap, f"house test: {t['round_trips']} round trips closed, open or working, of its "
                                  f"{table.house_test_round_trips}")
        if unit > table.house_test_structure:
            return M.Plan(0, cap, f"house test: one structure risks ${M.cents(unit)} with fees, over its "
                                  f"${table.house_test_structure} cap")
        if t["open"] >= table.house_test_open:
            return M.Plan(0, cap, f"house test: {t['open']} structures held or working, the most it holds is "
                                  f"{table.house_test_open}")
        if t["possible"] + unit > table.house_test_envelope:
            return M.Plan(0, cap, f"house test: ${M.cents(t['possible'])} could already be lost (realized, held and "
                                  f"working) and this risks ${M.cents(unit)}, over its ${table.house_test_envelope}")
        room = M.probe_room(table, equity)
        book = table.book_share * equity
        if exposure.book_loss + unit + room > book:
            return M.Plan(0, cap, f"the book's cap: ${M.cents(exposure.book_loss)} of ${M.cents(book)} open maximum "
                                  f"loss, and ${M.cents(room)} is kept for the families' opens")
        order_cap = min(table.gateway_order_max_loss, table.gateway_order_share * equity)
        if unit > order_cap:
            return M.Plan(0, cap, f"the gateway's per-order cap ${M.cents(order_cap)} is under one structure's "
                                  f"${M.cents(unit)}")
        day_cap = table.gateway_day_share * equity
        if exposure.day_opened + unit + room > day_cap:
            return M.Plan(0, cap, f"the gateway's day cap: ${M.cents(exposure.day_opened)} of ${M.cents(day_cap)} opened "
                                  f"today, and ${M.cents(room)} is kept for the families' opens")
        return M.Plan(1, cap, "house test: one structure (pre-registered)")

    @contextlib.contextmanager
    def admit(self, today: dt.date) -> Iterator[bool]:
        """`families.admit_open`'s place for the House's own instance: the test's refusal re-checked as the order is
        written."""
        yield self.refusal(today) is None

    # ------------------------------------------------------------------ yielding and records
    def _yield(self) -> None:
        """A working test open holding a contract a family's real order was refused on AFTER the open was placed is
        cancelled at once, recorded "yielded". A family's refusals stay in `book.rejects_since` until that family
        decides again, so a refusal older than the open (an hour-old one naming the same contract for another reason)
        must never cancel it: only what was added since this pass last ran counts, and only for an open that was
        already working then (the families' intents of each minute go before the test's, so no refusal of the open's
        own minute can be about it)."""
        live, book = self.live, self.live.book
        marks = self._marks
        mine = [o for o in book.orders.values()
                if o.working and o.action == "open" and o.family == FAMILY and o.cancel_sent is None]
        fresh: list[str] = []
        if marks is not None:
            for instance, whys in book.rejects_since.items():
                if instance in (INSTANCE, C.INSTANCE):
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
                self.recorder.finished(order.oid, {"cancel_reason": YIELDED})
                book._reject(INSTANCE, f"your open was cancelled: {YIELDED}")
            live.record("live.instance", {"instance": INSTANCE, "family": FAMILY, "state": "house test yielded",
                                          "oid": order.oid, "cancelled": bool(ours)}, agent=FAMILY)
        self._marks = ({o.oid for o in book.orders.values() if o.working and o.action == "open" and o.family == FAMILY},
                       {instance: (whys, len(whys)) for instance, whys in book.rejects_since.items()})

    def _finish_rows(self) -> None:
        """Each recorded order that has ended: its outcome, times, fill and fees. An unfilled order is a "cancelled"
        sample only when it ran its whole window (`FULL_WINDOW`: its time in force, the close cutoff for expiring
        contracts, or the venue's end of a day order at the session's close, whenever its time in force would run
        past the close); any other unfilled end is "interrupted", never a sample."""
        state = self.live.state
        for row in self.recorder.open_rows():
            found = state.rows("SELECT * FROM orders WHERE oid=?", (int(row["oid"]),))
            if not found:
                continue
            order = ROrder.of(found[0])
            outcome = C.outcome_of(order.status, order.filled_qty)
            if outcome is None:
                continue
            reason = row.get("cancel_reason") or order.answer.get("cancel")
            if outcome == "cancelled" and not reason and order.status == "expired" and order.cancel_sent is None:
                reason = SESSION_CLOSE                      # the venue ended it at the close; the House never cancelled
            if outcome == "cancelled" and not str(reason or "").startswith(FULL_WINDOW):
                outcome = C.INTERRUPTED
            fees = state.rows("SELECT COALESCE(SUM(fees), 0) AS f FROM fills WHERE oid=?", (order.oid,))[0]["f"]
            self.recorder.finished(order.oid, {
                "status": order.status, "outcome": outcome, "filled_qty": int(order.filled_qty), "cancel_reason": reason,
                "fill_value": float(order.fill_value) if order.filled_qty > 0 else None, "pid": order.pid,
                "venue_submitted_at": order.answer.get("submitted_at"), "filled_at": order.answer.get("filled_at"),
                "canceled_at": order.answer.get("canceled_at") or order.answer.get("expired_at"),
                "cancel_sent": order.cancel_sent, "done_at": self.live.clock(),
                "fees": float(fees) if order.filled_qty > 0 else 0.0, "fees_source": "book_estimate"})

    def record(self, order: ROrder, snap: Any, fills: Sequence[L.LegFill], intent: Mapping[str, Any] | None, *,
               forced: bool) -> None:
        """One test order's row, written before it is sent: each leg's NBBO in the snapshot it was priced from, the
        structure's mid and natural there, the program's limit rule, tag and note. Never raises."""
        try:
            action = "open" if order.action == "open" else "close"
            legs = []
            for leg, fill in zip(order.legs, fills):
                i = int(fill.idx)
                legs.append({"symbol": leg.symbol, "side": leg.side, "bid": _num(snap.bid[i]), "ask": _num(snap.ask[i]),
                             "bid_size": _int(_at(getattr(snap, "bid_size", None), i)),
                             "ask_size": _int(_at(getattr(snap, "ask_size", None), i))})
            mid = _num(L.mid_value(snap, fills))
            natural = _num(L.natural_value(snap, fills, action)[0])
            quote = {"legs": legs, "mid": mid, "natural": natural, "spot": _num(snap.spot), "minute": int(snap.minute),
                     "source": "snapshot"}
            rule = (intent or {}).get("limit", "natural") if not forced else "natural"
            offset, ticks = _offset(rule, forced)
            trip = f"pid-{order.pid}" if order.pid is not None else f"oid-{order.oid}"
            self.recorder.submitted({
                "oid": order.oid, "client_id": order.client_id, "trip": trip, "day": order.day, "symbol": order.root,
                "legs": json.dumps([leg.row() for leg in order.legs], sort_keys=True), "action": order.action,
                "offset": offset, "ticks": ticks, "cell": C.cell_of(order.root, order.action, offset),
                "limit_price": order.limit_price, "limit_value": float(order.limit_value), "qty": int(order.qty),
                "quote": json.dumps(quote, sort_keys=True), "mid": mid, "natural": natural,
                "submitted_at": float(order.placed_at), "tif": int(order.tif) if order.tif is not None else None,
                "pid": order.pid, "rule": json.dumps(rule, sort_keys=True, default=str)[:200], "forced": int(bool(forced)),
                "tag": str((intent or {}).get("tag") or "")[:80], "note": str((intent or {}).get("note") or "")[:300]})
        except Exception as exc:  # noqa: BLE001 - never blocks the order
            self.recorder._failed("submit", exc)


def _offset(rule: Any, forced: bool) -> tuple[str, int | None]:
    """The limit rule's label and its ticks from the mid (None: not a mid rule)."""
    if forced:
        return "forced", None
    if rule == "mid":
        return "mid", 0
    if rule == "natural":
        return "natural", None
    if isinstance(rule, Mapping) and "mid" in rule:
        k = rule.get("mid")
        if isinstance(k, int) and not isinstance(k, bool):
            return f"mid+{k}", k
    if isinstance(rule, Mapping) and "price" in rule:
        return "price", None
    return "other", None


def _at(values: Any, i: int) -> Any:
    try:
        return None if values is None else values[i]
    except (IndexError, TypeError):
        return None


def _num(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return round(x, 6) if math.isfinite(x) else None


def _int(value: Any) -> int | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return int(x) if math.isfinite(x) else None


__all__ = ["HouseTest", "Recorder", "FAMILY", "INSTANCE", "BAND", "FROZEN", "PREREGISTRATION_SHA256", "PRIVATE_DIR",
           "PROGRAM", "PARAMS", "FILE", "OPEN_WHY", "CLOSE_WHY", "YIELDED", "SESSION_CLOSE", "FULL_WINDOW", "verify",
           "load_private", "release"]
