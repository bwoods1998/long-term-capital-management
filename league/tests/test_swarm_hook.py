"""The House's side of the swarm (league/swarm/hook.py, bands.py, sitefeed.py) and the options House with the swarm
enabled (league/service.py): no agent of its own, no old research, the swarm's step in the tick."""

from __future__ import annotations

import json
import signal
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from league import publish
from league.ledger import KINDS, Ledger, now_iso
from league.swarm import bands, sitefeed
from league.swarm.hook import SKIPPED_KINDS, SwarmStep, attach
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock, result
from league.tests.test_options_house import BuildCase

SPEC = {"id": "condor-vrp", "mechanism": "Index options price more movement than follows: sell an iron condor.",
        "structure": "iron_condor", "roots": ["SPY"], "dte": [0, 2]}
ON = {"swarm": {"enabled": True}}


class Down:
    """A ledger behind a switch: while `error` is set, every write fails as the ledger itself would (a SQLite error, not
    a row's `LedgerError`); otherwise it writes to `ledger`."""

    def __init__(self, ledger, error=None):
        self.ledger, self.error = ledger, error

    def append_many(self, rows):
        if self.error is not None:
            raise sqlite3.OperationalError(self.error)
        return self.ledger.append_many(rows)


class Proc:
    def __init__(self, pid):
        self.pid = pid
        self.code = None

    def poll(self):
        return self.code


class HookCase(unittest.TestCase):
    """A fake process table: `self.procs[pid] = (cmdline, start)`; `hold(pid)` takes the swarm's lock as that process
    would (a real flock on the lock file, from another open file description), `let_go()` drops it."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name) / "state"
        self.root.mkdir()
        self.clock = Clock()
        self.signals: list[tuple[int, int]] = []
        self.spawned: list[Proc] = []
        self.procs: dict[int, tuple[str, str]] = {}
        self.held = None
        self.addCleanup(self.let_go)

    def swarm_cmd(self):
        return f"/usr/bin/python3 -m league.swarm run --root {self.root}"

    def kill(self, pid, sig):
        if pid not in self.procs:
            raise ProcessLookupError(pid)
        if sig:
            self.signals.append((pid, sig))
            if sig == signal.SIGKILL:
                self.procs.pop(pid, None)
                self.let_go()

    def spawn(self):
        proc = Proc(1000 + len(self.spawned))
        self.procs[proc.pid] = (self.swarm_cmd(), f"t{proc.pid}")
        self.spawned.append(proc)
        return proc

    def hold(self, pid, *, start=None, release="/rel/A"):
        import fcntl

        self.let_go()
        self.held = open(self.root / "swarm.lock", "a+")
        fcntl.flock(self.held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.procs.setdefault(pid, (self.swarm_cmd(), start or f"t{pid}"))
        (self.root / "swarm.lock").write_text(json.dumps({"pid": pid, "start": start or self.procs[pid][1], "release": release}))

    def let_go(self):
        if self.held is not None:
            self.held.close()
            self.held = None

    def step(self, config=ON):
        return SwarmStep(self.root, config=config, clock=self.clock, spawn=self.spawn, kill=self.kill, code_dir=Path("/rel/A"),
                         proc=lambda pid: self.procs.get(pid))

    def beat(self, pid, *, at=None, release="/rel/A", started=None):
        (self.root / "swarm.heartbeat").write_text(json.dumps({"pid": pid, "at": self.clock() if at is None else at, "release": release,
                                                              "started_at": started if started is not None else self.clock() - 3600}))


class Supervise(HookCase):
    def test_it_starts_the_swarm_once_and_leaves_a_healthy_one_alone(self):
        step = self.step()
        self.assertEqual(step.supervise()["action"], "started")
        self.hold(1000)
        self.beat(1000)
        self.clock.advance(20)
        self.assertNotIn("action", step.supervise())
        self.assertEqual(len(self.spawned), 1)

    def test_a_live_child_that_has_not_yet_beaten_or_locked_is_running(self):
        step = self.step()
        self.beat(77, at=self.clock() - 3600)  # an old swarm's last heartbeat, its pid dead
        step.supervise()
        for _ in range(4):
            self.clock.advance(31)
            out = step.supervise()
            self.assertNotEqual(out.get("action"), "started", out)
        self.assertEqual(len(self.spawned), 1, "never a second swarm while the first lives")

    def test_disabled_or_stopped_it_starts_nothing(self):
        self.assertEqual(self.step(config={"swarm": {"enabled": False}}).supervise()["idle"], "disabled")
        (self.root / "swarm.stop").write_text("x")
        self.assertIn("swarm.stop", self.step().supervise()["idle"])
        self.assertEqual(self.spawned, [])

    def test_a_house_not_open_for_business_starts_no_swarm_but_leaves_one_running(self):
        step = self.step()
        self.assertEqual(step.supervise(may_start=False)["idle"], "the House is not open for business")
        self.assertEqual(self.spawned, [])
        self.hold(1000)
        self.beat(1000)
        self.assertNotIn("idle", step.supervise(may_start=False))
        self.assertEqual(self.signals, [])

    def test_a_stale_heartbeat_is_a_hang_it_terminates_then_kills_then_restarts(self):
        step = self.step()
        step.supervise()
        self.hold(1000)
        self.beat(1000)
        self.clock.advance(300)
        self.assertIn("stale", step.supervise()["action"])
        self.assertEqual(self.signals, [(1000, signal.SIGTERM)])
        self.clock.advance(31)
        self.assertEqual(step.supervise()["action"], "terminating")
        self.assertEqual(self.signals[-1], (1000, signal.SIGKILL))
        self.spawned[0].code = -9
        self.clock.advance(60)
        self.assertEqual(step.supervise()["action"], "started")

    def test_a_swarm_on_another_release_is_restarted(self):
        self.hold(77, release="/rel/OLD")
        self.beat(77, release="/rel/OLD")
        out = self.step().supervise()
        self.assertIn("another release", out["action"])
        self.assertEqual(self.signals, [(77, signal.SIGTERM)])

    def test_it_never_signals_a_pid_that_is_not_the_swarm(self):
        self.hold(77, release="/rel/OLD")
        self.beat(77, release="/rel/OLD")
        self.procs[77] = ("/usr/bin/python3 -m league run --root /workspace/state", "t77")  # the pid now belongs to the House
        out = self.step().supervise()
        self.assertEqual(self.signals, [])
        self.assertIn("cannot verify", out["action"])

    def test_it_never_signals_a_reused_pid(self):
        self.hold(77, start="t-old", release="/rel/OLD")
        self.beat(77, release="/rel/OLD")
        self.procs[77] = (self.swarm_cmd(), "t-new")  # same number, another process start
        self.step().supervise()
        self.assertEqual(self.signals, [])

    def test_it_never_signals_itself(self):
        import os

        self.hold(os.getpid(), release="/rel/OLD")
        self.beat(os.getpid(), release="/rel/OLD")
        self.step().supervise()
        self.assertEqual(self.signals, [])

    def test_a_start_that_dies_before_it_locks_backs_off(self):
        step = self.step()
        step.supervise()
        self.spawned[-1].code = 1
        self.clock.advance(31)
        self.assertEqual(step.supervise()["action"], "started")
        self.spawned[-1].code = 1
        self.clock.advance(31)
        self.assertIn("waiting", step.supervise()["action"])

    def test_the_log_is_rotated_at_a_start(self):
        from league.swarm.hook import rotate_log

        log = self.root / "swarm.log"
        log.write_bytes(b"x" * 1000)
        rotate_log(log, max_bytes=500)
        self.assertEqual((log.exists(), (self.root / "swarm.log.1").stat().st_size), (False, 1000))

    def test_a_tick_never_raises_into_the_house(self):
        class BrokenLedger:
            def append_many(self, rows):
                raise RuntimeError("disk full")

        store = SwarmStore(self.root)
        store.event("swarm.status", None, {"x": 1})
        store.close()

        class House:
            ledger = BrokenLedger()

        out = self.step().tick(House(), open_for_business=True)
        self.assertIn("mirror_error", out)


class Mirror(HookCase):
    def test_events_reach_the_ledger_once_with_swarm_kinds_and_public_flags(self):
        store = SwarmStore(self.root)
        fam = store.add_family(SPEC, origin="seed")
        store.event("swarm.born", fam["id"], {"mechanism": fam["mechanism"], "parent": None})
        store.event("swarm.cycle", fam["id"], {"cycle": 1})
        store.event("swarm.pool", None, {"action": "box_ready"})
        store.set_band(fam["id"], "candidate", reason="passed its holdout look")
        store.event("swarm.note", fam["id"], {"text": "condors pay on quiet days"})
        ledger = Ledger(self.root / "ledger.sqlite")
        self.addCleanup(ledger.close)
        step = self.step()
        self.assertEqual(step.mirror(ledger), 5)
        self.assertEqual(step.mirror(ledger), 0)
        rows = list(ledger.iter())
        self.assertEqual([r.kind for r in rows], ["swarm.born", "swarm.band", "swarm.note"], "cycles and pool rows stay in the swarm's table")
        self.assertEqual([r.public for r in rows], [True, True, True])
        self.assertTrue(all(r.agent == "condor-vrp" for r in rows))
        (self.root / "swarm-mirror.json").unlink()
        self.assertEqual(step.mirror(ledger), 5, "a lost cursor re-mirrors idempotently")
        self.assertEqual(len(list(ledger.iter())), 3)
        store.close()
        # The tape: a note is the agent's note, a birth and a band move are the swarm's news.
        events = [e for r in rows for e in publish.to_events(r)]
        self.assertEqual([e["kind"] for e in events], ["swarm.news", "swarm.news", "agent.note"])
        self.assertIn("moves from Gym to Candidate", events[1]["payload"]["text"])

    def test_a_swarm_alert_reaches_the_houses_ops_alerts(self):
        store = SwarmStore(self.root)
        store.event("swarm.status", "fly", {"action": "not_the_plans_reviewer", "alert": True, "text": "two Sail models stood in"})
        store.event("swarm.status", None, {"action": "started"})
        store.close()
        alerts = []

        class House:
            ledger = Ledger(self.root / "ledger.sqlite")

            def alert(self, level, text, **payload):
                alerts.append((level, text))

        house = House()
        self.addCleanup(house.ledger.close)
        self.step().tick(house, open_for_business=False)
        self.assertEqual(len(alerts), 1)
        self.assertIn("two Sail models stood in", alerts[0][1])

    def test_a_batch_with_a_kind_the_ledger_does_not_know_mirrors_the_rest_and_moves_the_cursor(self):
        """Sept 26-27, 2026: two new swarm kinds the ledger did not know failed every batch (the ledger rolls a batch back
        on one bad row), the cursor never moved, and the site got no swarm news for 14 hours. An unknown kind is now
        skipped and counted; the rows around it land and the cursor moves past all of them."""
        store = SwarmStore(self.root)
        fam = store.add_family(SPEC, origin="seed")
        store.event("swarm.born", fam["id"], {"mechanism": fam["mechanism"], "parent": None})
        store.event("swarm.not_yet_a_ledger_kind", fam["id"], {"x": 1})
        store.event("swarm.not_yet_a_ledger_kind", None, {"x": 2})
        last = store.event("swarm.note", fam["id"], {"text": "condors pay on quiet days"})
        store.close()
        self.assertNotIn("swarm.not_yet_a_ledger_kind", KINDS)
        ledger = Ledger(self.root / "ledger.sqlite")
        self.addCleanup(ledger.close)

        class House:
            pass

        house = House()
        house.ledger = ledger
        step = self.step()
        out = step.tick(house, open_for_business=False)
        self.assertNotIn("mirror_error", out)
        self.assertEqual(out["mirrored"], 4)
        self.assertEqual(out["mirror_unknown_kinds"], {"swarm.not_yet_a_ledger_kind": 2})
        self.assertEqual([r.kind for r in ledger.iter()], ["swarm.born", "swarm.note"])
        self.assertEqual(json.loads((self.root / "swarm-mirror.json").read_text())["seq"], last)
        self.assertEqual(step.mirror(ledger), 0, "the cursor moved past the unknown rows")
        self.assertEqual(step.unknown_kinds, {})

    def test_the_diagnostician_and_robustness_rows_stay_in_the_swarms_table(self):
        store = SwarmStore(self.root)
        fam = store.add_family(SPEC, origin="seed")
        store.event("swarm.diagnostician", fam["id"], {"family": fam["id"], "outcome": "rewrote", "cost_usd": 0.12})
        store.event("swarm.robustness", fam["id"], {"version": 3, "action": "demoted", "why": "one quarter carried it"})
        store.event("swarm.note", fam["id"], {"text": "condors pay on quiet days"})
        store.close()
        self.assertIn("swarm.diagnostician", SKIPPED_KINDS)
        self.assertIn("swarm.robustness", SKIPPED_KINDS)
        ledger = Ledger(self.root / "ledger.sqlite")
        self.addCleanup(ledger.close)
        step = self.step()
        self.assertEqual(step.mirror(ledger), 3)
        self.assertEqual(step.unknown_kinds, {}, "skipped as private diagnostics, not as unknown kinds")
        self.assertEqual([r.kind for r in ledger.iter()], ["swarm.note"])

    def test_every_kind_the_swarm_writes_is_a_ledger_kind_or_skipped(self):
        """The mirror no longer stalls on a new kind, but a new kind should still be decided: public, private, or kept in
        the swarm's table. This catches the next one in CI instead of in the House's tick."""
        import re

        source = "\n".join(p.read_text() for p in (Path(__file__).resolve().parents[1] / "swarm").glob("*.py"))
        written = set(re.findall(r"\.event\(\s*\"(swarm\.[a-z_]+)\"", source))
        self.assertIn("swarm.diagnostician", written)
        self.assertEqual(sorted(k for k in written if k not in KINDS and k not in SKIPPED_KINDS), [])

    def house_with(self, ledger):
        """A House with `ledger` whose alerts are kept in the list returned beside it, as (level, text, payload)."""
        alerts: list[tuple[str, str, dict]] = []

        class House:
            def alert(self, level, text, **payload):
                alerts.append((level, text, payload))

        house = House()
        house.ledger = ledger
        return house, alerts

    def event(self, kind="swarm.status", family=None, payload=None):
        store = SwarmStore(self.root)
        try:
            return store.event(kind, family, payload if payload is not None else {"action": "started"})
        finally:
            store.close()

    def test_a_mirror_that_keeps_failing_is_one_house_error_then_an_info_when_it_works(self):
        """The same mirror error three ticks in a row is ONE error alert dated from the first failure (so a watch counts a
        failure that began before a promotion as inherited); a restart neither forgets nor repeats it; a success after it
        is an info."""
        self.event()
        ledger = Ledger(self.root / "ledger.sqlite")
        self.addCleanup(ledger.close)
        house, alerts = self.house_with(Down(ledger, "disk I/O error"))
        step = self.step()
        began = self.clock()
        for _ in range(2):
            self.assertIn("mirror_error", step.tick(house, open_for_business=False))
            self.clock.advance(30)
        self.assertEqual(alerts, [], "one or two failed ticks are not an alert")
        step.tick(house, open_for_business=False)
        self.assertEqual(len(alerts), 1)
        level, text, payload = alerts[0]
        self.assertEqual((level, payload["failures"]), ("error", 3))
        self.assertEqual(payload["began_at"], now_iso(lambda: began))
        self.assertIn("the mirror into the House ledger has failed 3 ticks in a row", text)
        self.assertIn("OperationalError: disk I/O error", text)
        for _ in range(3):
            self.clock.advance(30)
            step.tick(house, open_for_business=False)
        self.assertEqual(len(alerts), 1, "one alert for the run, not one a tick")
        self.clock.advance(30)
        self.step().tick(house, open_for_business=False)  # a restart (a deploy) remembers the run
        self.assertEqual(len(alerts), 1)
        house.ledger.error = None
        self.clock.advance(30)
        out = self.step().tick(house, open_for_business=False)
        self.assertNotIn("mirror_error", out)
        self.assertEqual(out["mirrored"], 1)
        self.assertEqual([a[0] for a in alerts], ["error", "info"])
        self.assertEqual((alerts[1][2]["failures"], alerts[1][2]["began_at"]), (7, now_iso(lambda: began)))
        self.assertFalse((self.root / "swarm-mirror-failing.json").exists())
        self.step().tick(house, open_for_business=False)
        self.assertEqual(len(alerts), 2, "a healthy mirror says nothing")

    def test_a_changed_mirror_error_starts_a_new_run(self):
        self.event()
        down = Down(None)
        house, alerts = self.house_with(down)
        step = self.step()
        for error in ("disk I/O error", "disk I/O error", "database is locked", "database is locked"):
            down.error = error
            step.tick(house, open_for_business=False)
        self.assertEqual(alerts, [], "two of one error, then two of another")
        step.tick(house, open_for_business=False)
        self.assertEqual(len(alerts), 1)
        self.assertIn("database is locked", alerts[0][1])

    def test_the_mirror_folds_its_error_with_the_houses_alert_key(self):
        """Review of #394: the run's key folded digit runs only, so two errors that differ in a UUID ("7974aa54-..." became
        "#aa#-fbb#-...") were two runs, each alerting on its own. The key is now the House's own `alert_key`."""
        from league.house import alert_key

        self.event()
        down = Down(None)
        house, alerts = self.house_with(down)
        step = self.step()
        for uuid in ("7974aa54-fbb9-4d9a-9aa0-61dbb64ca0d6", "daa7473c-ecf3-4897-90ef-092a4786e741", "0f1e2d3c-4b5a-4968-8776-655443322110"):
            down.error = f"database /workspace/state/ledger-{uuid}.sqlite is locked"
            out = step.tick(house, open_for_business=False)
            self.clock.advance(30)
        self.assertEqual([a[0] for a in alerts], ["error"], "three ticks of one error, whatever its ids")
        self.assertEqual(alerts[0][2]["failures"], 3)
        self.assertEqual(json.loads((self.root / "swarm-mirror-failing.json").read_text())["key"], alert_key(out["mirror_error"]))

    def test_a_mirror_that_fails_and_recovers_again_and_again_is_one_error_in_six_hours(self):
        """Review of #394: a mirror that fails three ticks, works one, fails three again was an error alert (and an info)
        each time. The same error is now an error alert at most once in six hours, across restarts; a run held back is
        said once the six hours are over, if it goes on; another error has its own six hours."""
        from league.swarm.hook import MIRROR_ERROR_COOLDOWN_SECONDS

        self.assertEqual(MIRROR_ERROR_COOLDOWN_SECONDS, 6 * 3600)
        ledger = Ledger(self.root / "ledger.sqlite")
        self.addCleanup(ledger.close)
        down = Down(ledger)
        house, alerts = self.house_with(down)

        def ticks(error, n, step):
            if error is not None:
                self.event()  # a row to mirror, so the tick writes (a tick with nothing new writes nothing)
            down.error = error
            for _ in range(n):
                step.tick(house, open_for_business=False)
                self.clock.advance(30)

        step = self.step()
        ticks("disk I/O error", 3, step)
        ticks(None, 1, step)
        self.assertEqual([a[0] for a in alerts], ["error", "info"])
        ticks("disk I/O error", 3, step)  # the same error inside six hours: held back
        ticks(None, 1, step)  # never said, so its end is not either
        ticks("disk I/O error", 3, self.step())  # a restart keeps the cooldown
        self.assertEqual([a[0] for a in alerts], ["error", "info"])
        self.clock.advance(MIRROR_ERROR_COOLDOWN_SECONDS)
        ticks("disk I/O error", 1, self.step())  # the run goes on past the cooldown: now it is said, dated from its start
        self.assertEqual([a[0] for a in alerts], ["error", "info", "error"])
        self.assertEqual(alerts[2][2]["failures"], 4)
        ticks(None, 1, step)
        self.assertEqual([a[0] for a in alerts], ["error", "info", "error", "info"])
        ticks("database is locked", 3, step)
        self.assertEqual([a[0] for a in alerts], ["error", "info", "error", "info", "error"])
        self.assertIn("database is locked", alerts[-1][1])

    def test_a_row_the_ledger_refuses_is_skipped_and_counted_with_one_warning_per_reason(self):
        """Review of #394: a batch the ledger refused for any reason but an unknown kind (an id reused with other content, a
        payload that is not canonical JSON) still stalled the mirror. The batch is written again row by row: a refused row
        is skipped and counted, the rows around it land, the cursor moves past them, and each reason is one warning."""
        from league.house import alert_key

        store = SwarmStore(self.root)
        fam = store.add_family(SPEC, origin="seed")
        store.event("swarm.born", fam["id"], {"mechanism": fam["mechanism"], "parent": None})
        refused = store.event("swarm.note", fam["id"], {"text": "condors pay on quiet days"})
        last = store.event("swarm.note", fam["id"], {"text": "calendars pay when the curve is steep"})
        store.close()
        ledger = Ledger(self.root / "ledger.sqlite")
        self.addCleanup(ledger.close)
        # A row already in the ledger under the id the mirror gives the second event, with other content.
        ledger.append("swarm.note", {"text": "another note entirely"}, agent=fam["id"], id=f"swarm:{refused}")
        house, alerts = self.house_with(ledger)
        out = self.step().tick(house, open_for_business=False)
        self.assertNotIn("mirror_error", out)
        self.assertEqual(out["mirrored"], 3)
        reason = f"LedgerConflict: ledger entry swarm:{refused} exists with different content"
        self.assertEqual(out["mirror_failed_rows"], {alert_key(reason): 1})
        self.assertEqual([(r.kind, r.payload.get("text")) for r in ledger.iter()],
                         [("swarm.note", "another note entirely"), ("swarm.born", None),
                          ("swarm.note", "calendars pay when the curve is steep")])
        self.assertEqual(json.loads((self.root / "swarm-mirror.json").read_text())["seq"], last)
        self.assertEqual(len(alerts), 1)
        level, text, payload = alerts[0]
        self.assertEqual((level, payload["skipped"], payload["swarm_kind"]), ("warning", 1, "swarm.note"))
        self.assertIn("the House ledger refused 1 mirrored row(s) one by one, first a swarm.note row (" + reason + ")", text)
        # The same reason again, in this process or after a restart: skipped and counted, not said again.
        for step in (self.step(), self.step()):
            seq = self.event("swarm.note", fam["id"], {"text": "a note the ledger already holds otherwise"})
            ledger.append("swarm.note", {"text": "and another one"}, agent=fam["id"], id=f"swarm:{seq}")
            out = step.tick(house, open_for_business=False)
            self.assertEqual(list(out["mirror_failed_rows"].values()), [1])
        self.assertEqual(len(alerts), 1)
        self.assertFalse((self.root / "swarm-mirror-failing.json").exists(), "a refused row is not a failed mirror")

    def test_a_ledger_failure_part_way_moves_the_cursor_past_the_handled_rows_only(self):
        """Row by row, a failure of the ledger itself (not a row's) stops the mirror: the rows before it land, the cursor
        moves past them and past the skipped rows among them, and the rest wait for the next tick. Nothing is skipped for
        it, and nothing is counted twice."""
        store = SwarmStore(self.root)
        fam = store.add_family(SPEC, origin="seed")
        store.event("swarm.born", fam["id"], {"mechanism": fam["mechanism"], "parent": None})
        store.event("swarm.note", fam["id"], {"text": "condors pay on quiet days"})
        store.event("swarm.cycle", fam["id"], {"cycle": 1})
        dropped = store.event("swarm.not_yet_a_ledger_kind", fam["id"], {"x": 1})
        store.event("swarm.note", fam["id"], {"text": "the disk fails on this note"})
        last = store.event("swarm.note", fam["id"], {"text": "calendars pay when the curve is steep"})
        store.close()
        ledger = Ledger(self.root / "ledger.sqlite")
        self.addCleanup(ledger.close)

        class FailsOnOneNote:
            down = True

            def append_many(self, rows):
                rows = list(rows)
                if self.down and any(r["payload"].get("text") == "the disk fails on this note" for r in rows):
                    raise sqlite3.OperationalError("disk I/O error")
                return ledger.append_many(rows)

        flaky = FailsOnOneNote()
        house, alerts = self.house_with(flaky)
        out = self.step().tick(house, open_for_business=False)
        self.assertEqual(out["mirror_error"], "OperationalError: disk I/O error")
        self.assertEqual([r.kind for r in ledger.iter()], ["swarm.born", "swarm.note"])
        self.assertEqual(json.loads((self.root / "swarm-mirror.json").read_text())["seq"], dropped,
                         "past the rows handled before the failure, never past the failure")
        self.assertEqual(out["mirror_unknown_kinds"], {"swarm.not_yet_a_ledger_kind": 1})
        self.assertNotIn("mirror_failed_rows", out, "a failure of the ledger itself skips no row")
        flaky.down = False
        out = self.step().tick(house, open_for_business=False)
        self.assertEqual(out["mirrored"], 2)
        self.assertNotIn("mirror_unknown_kinds", out, "rows before the cursor are not counted again")
        self.assertEqual([r.payload.get("text") for r in ledger.iter() if r.kind == "swarm.note"],
                         ["condors pay on quiet days", "the disk fails on this note", "calendars pay when the curve is steep"])
        self.assertEqual(json.loads((self.root / "swarm-mirror.json").read_text())["seq"], last)
        self.assertEqual([a[2].get("swarm_kind") for a in alerts], ["swarm.not_yet_a_ledger_kind"])

    def test_the_first_drop_of_an_unknown_kind_is_one_warning_naming_it(self):
        """Review of #394: an unknown kind was dropped without a word. The first time a kind is dropped, the House hears one
        warning that names it; later drops of it, in this process or after a restart, are counted only."""
        self.event("swarm.not_yet_a_ledger_kind", None, {"x": 1})
        self.event("swarm.not_yet_a_ledger_kind", None, {"x": 2})
        self.event()
        ledger = Ledger(self.root / "ledger.sqlite")
        self.addCleanup(ledger.close)
        house, alerts = self.house_with(ledger)
        step = self.step()
        out = step.tick(house, open_for_business=False)
        self.assertEqual(out["mirror_unknown_kinds"], {"swarm.not_yet_a_ledger_kind": 2})
        self.assertEqual(len(alerts), 1)
        level, text, payload = alerts[0]
        self.assertEqual((level, payload["swarm_kind"], payload["dropped"]), ("warning", "swarm.not_yet_a_ledger_kind", 2))
        self.assertIn("the mirror dropped 2 row(s) of kind swarm.not_yet_a_ledger_kind, which the House ledger does not know", text)
        self.event("swarm.not_yet_a_ledger_kind", None, {"x": 3})
        self.assertEqual(step.tick(house, open_for_business=False)["mirror_unknown_kinds"], {"swarm.not_yet_a_ledger_kind": 1})
        self.event("swarm.not_yet_a_ledger_kind", None, {"x": 4})
        self.step().tick(house, open_for_business=False)  # a restart
        self.assertEqual(len(alerts), 1, "said once")
        self.event("swarm.another_new_kind", None, {"x": 5})
        self.step().tick(house, open_for_business=False)
        self.assertEqual([a[2]["swarm_kind"] for a in alerts], ["swarm.not_yet_a_ledger_kind", "swarm.another_new_kind"])
        self.assertEqual([r.kind for r in ledger.iter()], ["swarm.status"])

    def test_public_flags_hold_when_unknown_kinds_are_mixed_in(self):
        """Review of #394: with unknown kinds mixed in, every mirrored row keeps its own public flag (the site's tape reads
        only the public ones), whether the batch lands whole or row by row."""
        expected = [("swarm.born", True), ("swarm.tournament", False), ("swarm.note", True), ("swarm.status", False),
                    ("swarm.band", True), ("swarm.gate", False), ("swarm.retired", True)]
        for row_by_row in (False, True):
            with self.subTest(row_by_row=row_by_row):
                root = Path(tempfile.mkdtemp(dir=self.dir.name))
                store = SwarmStore(root)
                fam = store.add_family(SPEC, origin="seed")
                store.event("swarm.born", fam["id"], {"mechanism": fam["mechanism"], "parent": None})
                store.event("swarm.not_yet_a_ledger_kind", fam["id"], {"x": 1})
                store.event("swarm.tournament", None, {"families": 1})
                store.event("swarm.note", fam["id"], {"text": "condors pay on quiet days"})
                taken = store.event("swarm.note", fam["id"], {"text": "a note whose id is taken"})
                store.event("swarm.not_yet_a_ledger_kind", None, {"x": 2})
                store.event("swarm.status", None, {"action": "started"})
                store.set_band(fam["id"], "candidate", reason="passed its holdout look")
                store.event("swarm.gate", fam["id"], {"verdict": "passed"})
                store.event("swarm.retired", fam["id"], {"reason": "its edge went away"})
                store.close()
                ledger = Ledger(root / "ledger.sqlite")
                self.addCleanup(ledger.close)
                if row_by_row:  # an id already taken with other content: the batch is refused, and written row by row
                    ledger.append("swarm.note", {"text": "another note entirely"}, agent=fam["id"], id=f"swarm:{taken}")
                step = SwarmStep(root, config=ON, clock=self.clock)
                self.assertEqual(step.mirror(ledger), 10)
                self.assertEqual(step.unknown_kinds, {"swarm.not_yet_a_ledger_kind": 2})
                self.assertEqual(sum(entry["count"] for entry in step.failed_rows.values()), 1 if row_by_row else 0)
                mirrored = [r for r in ledger.iter() if "swarm_seq" in r.payload]
                self.assertEqual([(r.kind, r.public) for r in mirrored if r.id != f"swarm:{taken}"], expected)
                self.assertEqual([r.public for r in mirrored], [KINDS[r.kind] for r in mirrored])
                self.assertTrue(all(r.kind != "swarm.not_yet_a_ledger_kind" for r in ledger.iter()))

    def test_the_swarm_never_writes_the_houses_own_kinds(self):
        for kind in ("swarm.born", "swarm.retired", "swarm.band", "swarm.note", "swarm.cycle", "swarm.tournament", "swarm.gate",
                     "swarm.architect", "swarm.guard", "swarm.pool", "swarm.status"):
            self.assertIn(kind, KINDS)
        source = "\n".join(p.read_text() for p in (Path(__file__).resolve().parents[1] / "swarm").glob("*.py"))
        for kind in ("agent.born", "agent.died", "agent.thought", "eval.verdict"):
            self.assertNotIn(f'"{kind}"', source)


class Reads(HookCase):
    def setUp(self):
        super().setUp()
        from league.gym.driver import build_bundle

        self.bundle = build_bundle()[1]
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"image_checkpoint": "synthetic-image"}}))

    def test_bands_read_rows_for_the_live_path(self):
        store = SwarmStore(self.root, clock=self.clock)
        a = store.add_family(SPEC, origin="seed")
        b = store.add_family({**SPEC, "id": "tuition"}, origin="seed")
        c = store.add_family({**SPEC, "id": "plain"}, origin="seed")
        for fam in (a, b, c):
            store.add_version(fam["id"], f"# {fam['id']}\nNEEDS = {{}}\n", {"k": 1}, author="seed")
        store.set_state(a["id"], banded_version=1, validation_version=1, validation_line={"passed": True}, typical_max_loss_usd=60.0)
        store.set_band(a["id"], "candidate", reason="passed")
        from league.swarm.gate import run_sha

        store.set_state(b["id"], validation_version=1, validation_image="synthetic-image", validation_bundle=self.bundle,
                        validation_line={"passed": True}, typical_max_loss_usd=45.0,
                        review={"sha": run_sha(store.version(b["id"], 1)), "verdict": "pass", "audit": {"verdict": "pass"}})
        store.close()
        rows = {r["family"]: r for r in bands.read(self.root)}
        self.assertEqual(set(rows), {"condor-vrp", "tuition"})
        self.assertEqual((rows["condor-vrp"]["holdout_passed"], rows["condor-vrp"]["validation_passed"], rows["condor-vrp"]["band"]),
                         (True, True, "candidate"))
        self.assertEqual((rows["tuition"]["holdout_passed"], rows["tuition"]["validation_passed"]), (False, True))
        self.assertEqual(set(rows["tuition"]), {"family", "band", "structure", "roots", "holdout_passed", "validation_passed", "version",
                                                "code", "params", "run_sha", "typical_max_loss_usd", "seed_era", "forward",
                                                "version_created_at"})
        self.assertIn("# tuition", rows["tuition"]["code"])
        self.assertEqual((rows["tuition"]["typical_max_loss_usd"], rows["tuition"]["seed_era"]), (45.0, True))
        bands._bundle_cache = None  # a process caches the bundle's version (`bands.BUNDLE_TTL`); new code is a new process
        with patch("league.gym.driver.build_bundle", return_value=(b"", "changed-code")):
            self.assertEqual([r["family"] for r in bands.read(self.root)], ["condor-vrp"],
                             "new Gym code requires tuition validation again; existing forward bands remain")
        bands._bundle_cache = None
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"image_checkpoint": "expanded-image"}}))
        self.assertEqual([r["family"] for r in bands.read(self.root)], ["condor-vrp"],
                         "new data requires tuition validation again; existing forward bands remain")

    def test_tuition_rows_are_only_reviewed_and_not_yet_failed_versions(self):
        from league.swarm.gate import run_sha

        store = SwarmStore(self.root, clock=self.clock)
        cases = {}
        for fid in ("unreviewed", "reviewed", "refused", "looked-failed", "demoted"):
            fam = store.add_family({**SPEC, "id": fid}, origin="seed")
            v = store.add_version(fam["id"], f"# {fid}\nNEEDS = {{}}\n", {}, author="seed")
            store.set_state(fid, validation_version=v["n"], validation_image="synthetic-image", validation_bundle=self.bundle,
                            validation_line={"passed": True})
            cases[fid] = run_sha(v)
        store.set_state("reviewed", review={"sha": cases["reviewed"], "verdict": "pass", "audit": {"verdict": "pass"}})
        fam = store.add_family({**SPEC, "id": "unaudited"}, origin="seed")
        v = store.add_version("unaudited", "# unaudited\nNEEDS = {}\n", {}, author="seed")
        store.set_state("unaudited", validation_version=v["n"], validation_image="synthetic-image", validation_bundle=self.bundle,
                        validation_line={"passed": True},
                        review={"sha": run_sha(v), "verdict": "pass"})
        store.set_state("refused", review={"sha": cases["refused"], "verdict": "fail"}, gate_outcome={"sha": cases["refused"], "result": "refused"})
        store.set_state("looked-failed", review={"sha": cases["looked-failed"], "verdict": "pass", "audit": {"verdict": "pass"}},
                        gate_outcome={"sha": cases["looked-failed"], "result": "failed"})
        store.set_state("demoted", review={"sha": cases["demoted"], "verdict": "pass", "audit": {"verdict": "pass"}},
                        gate_outcome={"sha": cases["demoted"], "result": "demoted"})
        store.close()
        self.assertEqual([r["family"] for r in bands.read(self.root)], ["reviewed"])

    def test_bands_read_never_raises(self):
        self.assertEqual(bands.read(self.root / "nowhere"), [])
        (self.root / "swarm.sqlite").write_text("not a database")
        self.assertEqual(bands.read(self.root), [])

    def test_site_inputs_are_counts_and_words_never_programs_or_results(self):
        store = SwarmStore(self.root, clock=self.clock)
        fam = store.add_family(SPEC, origin="seed")
        store.add_version(fam["id"], "SECRET_PROGRAM = 1\n", {}, author="seed")
        store.add_run(fam["id"], 1, result("x"), window="train", stress=1.0, purpose="train", program_years=2.5)
        store.add_spend("sail_model", 1.25)
        store.add_forward(fam["id"], "shadow", [{"id": "t1", "day": "d", "pnl": 3.0, "max_loss": 50.0}])
        dead = store.add_family({**SPEC, "id": "gone"}, origin="seed")
        store.retire(dead["id"], "no improvement")
        store.close()
        out = sitefeed.site_inputs(self.root)
        self.assertEqual(out["gym"]["trials"], 1)
        self.assertEqual(out["gym"]["market_years"], 2.5)
        self.assertEqual((out["gym"]["families_alive"], out["gym"]["families_retired"]), (1, 1))
        self.assertEqual(out["compute"]["sail_usd"], 1.25)
        agent = next(a for a in out["agents"] if a["id"] == "condor-vrp")
        self.assertEqual(agent["record"]["forward"], {"trades": 1, "wins": 1, "pnl_usd": 3.0})
        self.assertNotIn("SECRET_PROGRAM", json.dumps(out))
        checkpoint = publish.build_checkpoint({**out, "started_at": None}, "2026-09-26T12:00:00Z")
        self.assertEqual({a["id"] for a in checkpoint["agents"]}, {"condor-vrp", "gone"})
        self.assertEqual(checkpoint["gym"]["trials"], 1)

    def test_the_sites_real_record_is_every_real_trade_and_its_trials_the_lineages(self):
        store = SwarmStore(self.root, clock=self.clock)
        fam = store.add_family(SPEC, origin="seed")
        for i in range(3):
            store.add_run(fam["id"], 1, result(f"p{i}"), window="train", stress=1.0, purpose="train")
        store.add_forward(fam["id"], "real", [{"id": "r1", "day": "d1", "pnl": 5.0, "max_loss": 50.0}], version=1)
        store.set_state(fam["id"], banded_version=2)
        store.add_forward(fam["id"], "shadow", [{"id": "s1", "day": "d2", "pnl": -2.0, "max_loss": 50.0}], version=2)
        child = store.add_family({**SPEC, "id": "condor-on-qqq", "roots": ["QQQ"]}, origin="fork", parent=fam["id"])
        store.add_run(child["id"], 1, result("c"), window="train", stress=1.0, purpose="train")
        store.close()
        agents = {a["id"]: a for a in sitefeed.site_inputs(self.root)["agents"]}
        record = agents[fam["id"]]["record"]
        self.assertEqual(record["real"], {"trades": 1, "wins": 1, "pnl_usd": 5.0}, "real money is real whatever the version")
        self.assertEqual(record["forward"], {"trades": 1, "wins": 0, "pnl_usd": -2.0}, "the banded version's record")
        self.assertEqual((record["trials"], agents["condor-on-qqq"]["record"]["trials"]), (4, 4))

    def test_published_compute_keeps_claude_and_historical_provider_costs(self):
        """A provider switch cannot make historical costs disappear or omit the current provider from Net."""
        store = SwarmStore(self.root, clock=self.clock)
        for kind, usd in (("sail_model", 1.25), ("gym_box", 2.75), ("openai", 3.0), ("claude", 4.0)):
            store.add_spend(kind, usd)
        store.close()
        inputs = sitefeed.site_inputs(self.root)
        checkpoint = publish.build_checkpoint({**inputs, "started_at": None}, "2026-09-26T12:00:00Z")
        compute = checkpoint["compute"]
        self.assertEqual(compute["sail_usd"], "4.00")
        self.assertEqual(compute["openai_usd"], "3.00")
        self.assertEqual(compute["other_usd"], "4.00")
        self.assertEqual(sum(float(compute[k]) for k in ("sail_usd", "openai_usd", "other_usd")), 11.0)


class SwarmHouse(BuildCase):
    def build_on(self, **kw):
        spawned = []

        def fake_popen(self_step):
            spawned.append(1)
            return Proc(4242)

        with patch("league.swarm.hook.SwarmStep._popen", fake_popen):
            house = self.build(config=ON, research=True, merton=True, **kw)
        return house, spawned

    def test_the_swarms_house_builds_no_old_research_merton_or_births(self):
        house, _ = self.build_on()
        self.assertIsInstance(house.swarm, SwarmStep)
        self.assertIsNone(house.researcher)
        self.assertIsNone(house.merton)
        self.assertIsNone(getattr(house, "budget", None))
        self.assertFalse(house.settings.births)

    def test_the_site_reads_the_swarm_until_the_house_has_its_own_site_inputs(self):
        house, _ = self.build_on()
        if hasattr(type(house), "site_inputs"):  # the live path's House (#362) merges house.swarm itself
            self.assertNotIn("site_inputs", vars(house))
        else:
            self.assertEqual(house.site_inputs, house.swarm.site_inputs, "the swarm's feed stands in")
            self.assertIsInstance(house.site_inputs(), dict)

        class OwnHouse:
            def site_inputs(self):
                return {"agents": ["the House's own"]}

        own = OwnHouse()
        step = attach(own, Path(self.dir.name), ON)
        self.assertIs(own.swarm, step)
        self.assertEqual(own.site_inputs(), {"agents": ["the House's own"]}, "a House with its own is never overridden")

    def test_an_empty_root_tick_seats_no_agent_and_spends_no_research(self):
        house, _ = self.build_on()
        calls = []
        house.swarm.spawn = lambda: calls.append(1) or Proc(4343)
        house.swarm.kill = lambda pid, sig: None
        summary = house.tick()
        house.wait(60)
        self.assertEqual([e for e in house.ledger.iter(kinds="agent.born")], [])
        self.assertEqual(len(house.registry.agents), 0)
        self.assertFalse((Path(self.dir.name) / "state" / "provider.sqlite").exists(), "no old provider, no research spend")
        self.assertEqual([e for e in house.ledger.iter(kinds="provider.request")], [])
        self.assertEqual(summary["swarm"]["process"]["action"], "started")
        self.assertEqual(calls, [1])

    def test_the_state_roots_swarm_json_switches_it_on_without_a_deploy(self):
        root = Path(self.dir.name) / "state"
        root.mkdir(parents=True, exist_ok=True)
        (root / "swarm.json").write_text(json.dumps({"enabled": True}))
        house = self.build(config={"swarm": {"enabled": False}})
        self.assertIsInstance(house.swarm, SwarmStep)
        self.assertFalse(house.settings.births)

    def test_a_canary_never_runs_the_swarm(self):
        with patch("league.swarm.hook.SwarmStep._popen", side_effect=AssertionError("no swarm in a canary")):
            house = self.build(config=ON, canary=True)
        self.assertIsNone(house.swarm)


if __name__ == "__main__":
    unittest.main()
